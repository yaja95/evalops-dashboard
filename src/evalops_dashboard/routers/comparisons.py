from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from evalops_dashboard.comparison import (
    ComparisonCriterion,
    ComparisonCriterionScore,
    ComparisonDataError,
    ComparisonEvaluation,
    ComparisonResponse,
    build_comparison_summary,
)
from evalops_dashboard.database import get_session
from evalops_dashboard.models import (
    ComparisonCriterionAverage,
    ComparisonResponseResult,
    ComparisonRubricSummary,
    CriterionScore,
    Evaluation,
    ModelResponse,
    Prompt,
    PromptComparisonRead,
    Rubric,
    RubricCriterion,
)

router = APIRouter(prefix="/prompts", tags=["comparisons"])
SessionDep = Annotated[Session, Depends(get_session)]


@router.get("/{prompt_id}/comparison", response_model=PromptComparisonRead)
def compare_prompt_responses(
    prompt_id: int,
    rubric_id: int,
    session: SessionDep,
) -> PromptComparisonRead:
    prompt = session.get(Prompt, prompt_id)
    if prompt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prompt {prompt_id} was not found.",
        )

    rubric = session.get(Rubric, rubric_id)
    if rubric is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rubric {rubric_id} was not found.",
        )

    criteria = list(
        session.exec(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == rubric.id)
            .order_by(RubricCriterion.id)
        ).all()
    )
    responses = list(
        session.exec(
            select(ModelResponse)
            .where(ModelResponse.prompt_id == prompt.id)
            .order_by(ModelResponse.id)
        ).all()
    )
    response_ids = [response.id for response in responses if response.id is not None]

    evaluations = []
    criterion_scores = []
    if response_ids:
        evaluations = list(
            session.exec(
                select(Evaluation)
                .where(
                    Evaluation.response_id.in_(response_ids),
                    Evaluation.rubric_id == rubric.id,
                )
                .order_by(Evaluation.response_id, Evaluation.id)
            ).all()
        )
        evaluation_ids = [evaluation.id for evaluation in evaluations if evaluation.id is not None]
        if evaluation_ids:
            criterion_scores = list(
                session.exec(
                    select(CriterionScore)
                    .where(CriterionScore.evaluation_id.in_(evaluation_ids))
                    .order_by(CriterionScore.evaluation_id, CriterionScore.criterion_id)
                ).all()
            )

    try:
        summary = build_comparison_summary(
            responses=[
                ComparisonResponse(
                    id=response.id or 0,
                    model_name=response.model_name,
                    response_text=response.response_text,
                    latency_ms=response.latency_ms,
                )
                for response in responses
            ],
            evaluations=[
                ComparisonEvaluation(
                    id=evaluation.id or 0,
                    response_id=evaluation.response_id,
                    overall_score=evaluation.overall_score,
                    passed=evaluation.passed,
                    created_at=evaluation.created_at,
                )
                for evaluation in evaluations
            ],
            criteria=[
                ComparisonCriterion(
                    id=criterion.id or 0,
                    name=criterion.name,
                    weight=criterion.weight,
                    required=criterion.required,
                )
                for criterion in criteria
            ],
            criterion_scores=[
                ComparisonCriterionScore(
                    evaluation_id=criterion_score.evaluation_id,
                    criterion_id=criterion_score.criterion_id,
                    score=criterion_score.score,
                )
                for criterion_score in criterion_scores
            ],
        )
    except ComparisonDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return PromptComparisonRead(
        prompt_id=prompt.id or 0,
        prompt_title=prompt.title,
        prompt_use_case=prompt.use_case,
        rubric=ComparisonRubricSummary(
            id=rubric.id or 0,
            name=rubric.name,
            version=rubric.version,
            pass_threshold=rubric.pass_threshold,
        ),
        response_count=summary.response_count,
        compared_response_count=summary.compared_response_count,
        comparison_ready=summary.comparison_ready,
        winner_response_id=summary.winner_response_id,
        unscored_response_ids=summary.unscored_response_ids,
        results=[
            ComparisonResponseResult(
                rank=result.rank,
                response_id=result.response_id,
                model_name=result.model_name,
                response_text=result.response_text,
                latency_ms=result.latency_ms,
                evaluation_count=result.evaluation_count,
                average_overall_score=result.average_overall_score,
                pass_rate=result.pass_rate,
                latest_evaluated_at=result.latest_evaluated_at,
                criterion_averages=[
                    ComparisonCriterionAverage(
                        criterion_id=criterion_average.criterion_id,
                        criterion_name=criterion_average.criterion_name,
                        weight=criterion_average.weight,
                        required=criterion_average.required,
                        average_score=criterion_average.average_score,
                    )
                    for criterion_average in result.criterion_averages
                ],
            )
            for result in summary.results
        ],
    )
