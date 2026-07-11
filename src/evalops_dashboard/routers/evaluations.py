import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from evalops_dashboard.auth import CurrentUser
from evalops_dashboard.database import get_session
from evalops_dashboard.models import (
    CriterionScore,
    CriterionScoreCreate,
    CriterionScoreRead,
    Evaluation,
    EvaluationCreate,
    EvaluationRead,
    ImportRowError,
    ImportSummary,
    ModelResponse,
    Rubric,
    RubricCriterion,
)
from evalops_dashboard.scoring import ScoredCriterion, calculate_scoring_result

router = APIRouter(prefix="/evaluations", tags=["evaluations"])
SessionDep = Annotated[Session, Depends(get_session)]
UNPROCESSABLE_CONTENT = 422


@router.post("", response_model=EvaluationRead, status_code=status.HTTP_201_CREATED)
def create_evaluation(
    evaluation_create: EvaluationCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> EvaluationRead:
    evaluation = create_evaluation_from_payload(evaluation_create, session)
    return build_evaluation_responses([evaluation], session)[0]


def create_evaluation_from_payload(
    evaluation_create: EvaluationCreate,
    session: Session,
) -> Evaluation:
    model_response = session.get(ModelResponse, evaluation_create.response_id)
    if model_response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model response {evaluation_create.response_id} was not found.",
        )

    rubric = session.get(Rubric, evaluation_create.rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {evaluation_create.rubric_id} was not found.",
        )

    criteria = get_rubric_criteria(rubric.id or 0, session)
    validated_scores = validate_submitted_scores(evaluation_create, rubric, criteria)
    scoring_result = calculate_scoring_result(
        [
            ScoredCriterion(
                score=score_create.score,
                weight=criterion.weight,
                required=criterion.required,
            )
            for criterion, score_create in validated_scores
        ],
        pass_threshold=rubric.pass_threshold,
    )

    evaluation = Evaluation(
        response_id=evaluation_create.response_id,
        rubric_id=evaluation_create.rubric_id,
        overall_score=scoring_result.overall_score,
        passed=scoring_result.passed,
        justification=evaluation_create.justification,
        evaluator=evaluation_create.evaluator,
    )

    try:
        session.add(evaluation)
        session.flush()
        criterion_scores = [
            CriterionScore(
                evaluation_id=evaluation.id or 0,
                criterion_id=score_create.criterion_id,
                score=score_create.score,
                notes=score_create.notes,
            )
            for _criterion, score_create in validated_scores
        ]
        session.add_all(criterion_scores)
        session.commit()
        session.refresh(evaluation)
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail="Evaluation could not be saved because its criterion scores were invalid.",
        ) from exc

    return evaluation


@router.get("/export")
def export_evaluations_csv(
    rubric_id: int, session: SessionDep, current_user: CurrentUser
) -> Response:
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    criteria = get_rubric_criteria(rubric_id, session)
    columns = build_csv_columns(criteria)

    evaluations = list(
        session.exec(
            select(Evaluation).where(Evaluation.rubric_id == rubric_id).order_by(Evaluation.id)
        ).all()
    )
    evaluation_reads = build_evaluation_responses(evaluations, session)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for evaluation_read in evaluation_reads:
        scores_by_criterion_id = {score.criterion_id: score for score in evaluation_read.scores}
        row = [
            evaluation_read.response_id,
            evaluation_read.evaluator,
            evaluation_read.justification,
        ]
        for criterion in criteria:
            score = scores_by_criterion_id.get(criterion.id)
            row.append(score.score if score is not None else "")
            row.append(score.notes if score is not None else "")
        writer.writerow(row)

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="rubric_{rubric_id}_evaluations.csv"'
        },
    )


@router.post("/import", response_model=ImportSummary)
async def import_evaluations_csv(
    rubric_id: int,
    session: SessionDep,
    file: UploadFile,
    current_user: CurrentUser,
) -> ImportSummary:
    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    criteria = get_rubric_criteria(rubric_id, session)
    expected_columns = build_csv_columns(criteria)

    raw = (await file.read()).decode("utf-8")
    if not raw.strip():
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail="CSV file is empty.",
        )

    reader = csv.DictReader(io.StringIO(raw))
    actual_columns = set(reader.fieldnames or [])
    expected_columns_set = set(expected_columns)
    if actual_columns != expected_columns_set:
        missing = sorted(expected_columns_set - actual_columns)
        unexpected = sorted(actual_columns - expected_columns_set)
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail=(
                f"CSV columns do not match rubric {rubric_id}'s current criteria. "
                f"Missing: {missing}. Unexpected: {unexpected}."
            ),
        )

    created_count = 0
    errors: list[ImportRowError] = []
    for row_number, row in enumerate(reader, start=1):
        try:
            evaluation_create = EvaluationCreate(
                response_id=parse_row_int(row, "response_id", "response_id"),
                rubric_id=rubric_id,
                justification=row["justification"],
                evaluator=row["evaluator"],
                scores=[
                    CriterionScoreCreate(
                        criterion_id=criterion.id or 0,
                        score=parse_row_int(
                            row, f"{criterion.name}_score", f"Score for '{criterion.name}'"
                        ),
                        notes=row.get(f"{criterion.name}_notes") or "",
                    )
                    for criterion in criteria
                ],
            )
            create_evaluation_from_payload(evaluation_create, session)
        except ValueError as exc:
            errors.append(ImportRowError(row=row_number, detail=str(exc)))
        except ValidationError as exc:
            detail = "; ".join(error["msg"] for error in exc.errors())
            errors.append(ImportRowError(row=row_number, detail=detail))
        except HTTPException as exc:
            errors.append(ImportRowError(row=row_number, detail=str(exc.detail)))
        else:
            created_count += 1

    return ImportSummary(created_count=created_count, errors=errors)


def build_csv_columns(criteria: list[RubricCriterion]) -> list[str]:
    columns = ["response_id", "evaluator", "justification"]
    for criterion in criteria:
        columns.append(f"{criterion.name}_score")
        columns.append(f"{criterion.name}_notes")
    return columns


def parse_row_int(row: dict[str, str], column: str, label: str) -> int:
    try:
        return int(row[column])
    except ValueError, TypeError, KeyError:
        raise ValueError(f"{label} must be an integer.") from None


@router.get("", response_model=list[EvaluationRead])
def list_evaluations(session: SessionDep, current_user: CurrentUser) -> list[EvaluationRead]:
    evaluations = session.exec(select(Evaluation).order_by(Evaluation.id)).all()
    return build_evaluation_responses(list(evaluations), session)


@router.get("/{evaluation_id}", response_model=EvaluationRead)
def get_evaluation(
    evaluation_id: int,
    session: SessionDep,
    current_user: CurrentUser,
) -> EvaluationRead:
    evaluation = session.get(Evaluation, evaluation_id)
    if evaluation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Evaluation {evaluation_id} was not found.",
        )

    return build_evaluation_responses([evaluation], session)[0]


def get_rubric_criteria(rubric_id: int, session: Session) -> list[RubricCriterion]:
    return list(
        session.exec(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == rubric_id)
            .order_by(RubricCriterion.id)
        ).all()
    )


def validate_submitted_scores(
    evaluation_create: EvaluationCreate,
    rubric: Rubric,
    criteria: list[RubricCriterion],
) -> list[tuple[RubricCriterion, CriterionScoreCreate]]:
    if not criteria:
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail=f"Rubric {rubric.id} has no criteria to score.",
        )

    invalid_required_criteria = [
        criterion.name
        for criterion in criteria
        if criterion.required and criterion.max_score < rubric.pass_threshold
    ]
    if invalid_required_criteria:
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail=(
                "Rubric configuration is invalid because required criteria cannot meet "
                "the pass threshold: " + ", ".join(invalid_required_criteria)
            ),
        )

    criteria_by_id = {criterion.id: criterion for criterion in criteria}
    scores_by_criterion_id = {
        score_create.criterion_id: score_create for score_create in evaluation_create.scores
    }
    expected_ids = set(criteria_by_id)
    submitted_ids = set(scores_by_criterion_id)
    missing_ids = sorted(expected_ids - submitted_ids)
    extra_ids = sorted(submitted_ids - expected_ids)

    if missing_ids:
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail=f"Missing scores for rubric criteria: {missing_ids}.",
        )
    if extra_ids:
        raise HTTPException(
            status_code=UNPROCESSABLE_CONTENT,
            detail=f"Criteria do not belong to rubric {rubric.id}: {extra_ids}.",
        )

    validated_scores = []
    for criterion in criteria:
        score_create = scores_by_criterion_id[criterion.id]
        if score_create.score < criterion.min_score:
            raise HTTPException(
                status_code=UNPROCESSABLE_CONTENT,
                detail=(
                    f"Score for criterion '{criterion.name}' must be at least "
                    f"{criterion.min_score}."
                ),
            )
        if score_create.score > criterion.max_score:
            raise HTTPException(
                status_code=UNPROCESSABLE_CONTENT,
                detail=(
                    f"Score for criterion '{criterion.name}' must be no greater than "
                    f"{criterion.max_score}."
                ),
            )
        validated_scores.append((criterion, score_create))

    return validated_scores


def build_evaluation_responses(
    evaluations: list[Evaluation],
    session: Session,
) -> list[EvaluationRead]:
    if not evaluations:
        return []

    evaluation_ids = [evaluation.id for evaluation in evaluations if evaluation.id is not None]
    rubric_ids = {evaluation.rubric_id for evaluation in evaluations}

    rubrics = session.exec(select(Rubric).where(Rubric.id.in_(rubric_ids))).all()
    rubrics_by_id = {rubric.id: rubric for rubric in rubrics}

    criterion_scores = session.exec(
        select(CriterionScore)
        .where(CriterionScore.evaluation_id.in_(evaluation_ids))
        .order_by(CriterionScore.evaluation_id, CriterionScore.id)
    ).all()
    criterion_ids = {criterion_score.criterion_id for criterion_score in criterion_scores}
    criteria = session.exec(
        select(RubricCriterion).where(RubricCriterion.id.in_(criterion_ids))
    ).all()
    criteria_by_id = {criterion.id: criterion for criterion in criteria}

    scores_by_evaluation_id: dict[int, list[CriterionScore]] = {}
    for criterion_score in criterion_scores:
        scores_by_evaluation_id.setdefault(criterion_score.evaluation_id, []).append(
            criterion_score
        )

    responses = []
    for evaluation in evaluations:
        rubric = rubrics_by_id[evaluation.rubric_id]
        responses.append(
            EvaluationRead(
                id=evaluation.id or 0,
                response_id=evaluation.response_id,
                rubric_id=evaluation.rubric_id,
                rubric_name=rubric.name,
                rubric_version=rubric.version,
                overall_score=evaluation.overall_score,
                passed=evaluation.passed,
                justification=evaluation.justification,
                evaluator=evaluation.evaluator,
                created_at=evaluation.created_at,
                scores=[
                    build_criterion_score_response(criterion_score, criteria_by_id)
                    for criterion_score in scores_by_evaluation_id.get(evaluation.id or 0, [])
                ],
            )
        )
    return responses


def build_criterion_score_response(
    criterion_score: CriterionScore,
    criteria_by_id: dict[int, RubricCriterion],
) -> CriterionScoreRead:
    criterion = criteria_by_id[criterion_score.criterion_id]
    return CriterionScoreRead(
        criterion_id=criterion.id or 0,
        criterion_name=criterion.name,
        score=criterion_score.score,
        weight=criterion.weight,
        required=criterion.required,
        notes=criterion_score.notes,
    )
