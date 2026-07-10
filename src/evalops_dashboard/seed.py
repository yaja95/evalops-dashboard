from sqlmodel import Session, select

from evalops_dashboard.models import (
    CriterionScore,
    Evaluation,
    ModelResponse,
    Prompt,
    Rubric,
    RubricCriterion,
)
from evalops_dashboard.scoring import ScoredCriterion, calculate_scoring_result

SEED_PROMPT_TITLE = "Classify support ticket urgency"
SEED_RUBRIC_NAME = "Support Response Quality"
SEED_RUBRIC_VERSION = 1


def seed_database(session: Session) -> None:
    prompt = ensure_seed_prompt(session)
    response = ensure_seed_response(session, prompt)
    rubric = ensure_seed_rubric(session)
    criteria = ensure_seed_criteria(session, rubric)
    ensure_seed_evaluation(session, response, rubric, criteria)


def ensure_seed_prompt(session: Session) -> Prompt:
    prompt = session.exec(select(Prompt).where(Prompt.title == SEED_PROMPT_TITLE)).first()
    if prompt is not None:
        return prompt

    prompt = Prompt(
        title=SEED_PROMPT_TITLE,
        content=(
            "Classify the customer message as low, medium, or high urgency and explain "
            "the operational reason for the classification."
        ),
        use_case="support triage",
        owner="evalops",
    )
    session.add(prompt)
    session.commit()
    session.refresh(prompt)
    return prompt


def ensure_seed_response(session: Session, prompt: Prompt) -> ModelResponse:
    response = session.exec(
        select(ModelResponse).where(
            ModelResponse.prompt_id == prompt.id,
            ModelResponse.model_name == "gpt-example-ops",
        )
    ).first()
    if response is not None:
        return response

    response = ModelResponse(
        prompt_id=prompt.id or 0,
        model_name="gpt-example-ops",
        response_text=(
            "High urgency. The customer reports production downtime and asks for immediate "
            "help, so the issue should be routed to the on-call support queue."
        ),
        latency_ms=842,
    )
    session.add(response)
    session.commit()
    session.refresh(response)
    return response


def ensure_seed_rubric(session: Session) -> Rubric:
    rubric = session.exec(
        select(Rubric).where(
            Rubric.name == SEED_RUBRIC_NAME,
            Rubric.version == SEED_RUBRIC_VERSION,
        )
    ).first()
    if rubric is not None:
        return rubric

    rubric = Rubric(
        name=SEED_RUBRIC_NAME,
        version=SEED_RUBRIC_VERSION,
        description="Evaluates customer-support responses.",
        pass_threshold=4,
    )
    session.add(rubric)
    session.commit()
    session.refresh(rubric)
    return rubric


def ensure_seed_criteria(session: Session, rubric: Rubric) -> list[RubricCriterion]:
    expected_criteria = [
        RubricCriterion(
            rubric_id=rubric.id or 0,
            name="Instruction Following",
            description="The response addresses the requested task.",
            weight=2,
            min_score=1,
            max_score=5,
            required=True,
        ),
        RubricCriterion(
            rubric_id=rubric.id or 0,
            name="Operational Accuracy",
            description="The response accurately identifies the operational situation.",
            weight=2,
            min_score=1,
            max_score=5,
            required=True,
        ),
        RubricCriterion(
            rubric_id=rubric.id or 0,
            name="Clarity",
            description="The response is clear and understandable.",
            weight=1,
            min_score=1,
            max_score=5,
            required=False,
        ),
    ]
    existing_criteria = {
        criterion.name: criterion
        for criterion in session.exec(
            select(RubricCriterion).where(RubricCriterion.rubric_id == rubric.id)
        ).all()
    }

    for criterion in expected_criteria:
        if criterion.name not in existing_criteria:
            session.add(criterion)
    session.commit()

    return list(
        session.exec(
            select(RubricCriterion)
            .where(RubricCriterion.rubric_id == rubric.id)
            .order_by(RubricCriterion.id)
        ).all()
    )


def ensure_seed_evaluation(
    session: Session,
    response: ModelResponse,
    rubric: Rubric,
    criteria: list[RubricCriterion],
) -> None:
    existing_evaluation = session.exec(
        select(Evaluation).where(
            Evaluation.response_id == response.id,
            Evaluation.rubric_id == rubric.id,
            Evaluation.evaluator == "seed",
        )
    ).first()
    if existing_evaluation is not None:
        return

    scores_by_name = {
        "Instruction Following": 5,
        "Operational Accuracy": 5,
        "Clarity": 4,
    }
    scoring_result = calculate_scoring_result(
        [
            ScoredCriterion(
                score=scores_by_name[criterion.name],
                weight=criterion.weight,
                required=criterion.required,
            )
            for criterion in criteria
        ],
        pass_threshold=rubric.pass_threshold,
    )
    evaluation = Evaluation(
        response_id=response.id or 0,
        rubric_id=rubric.id or 0,
        overall_score=scoring_result.overall_score,
        passed=scoring_result.passed,
        justification=(
            "Correctly identifies production downtime as high urgency and gives a clear "
            "operational escalation path."
        ),
        evaluator="seed",
    )
    session.add(evaluation)
    session.flush()

    session.add_all(
        [
            CriterionScore(
                evaluation_id=evaluation.id or 0,
                criterion_id=criterion.id or 0,
                score=scores_by_name[criterion.name],
                notes="Seed evaluation score.",
            )
            for criterion in criteria
        ]
    )
    session.commit()
