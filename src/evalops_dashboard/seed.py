from sqlmodel import Session, select

from evalops_dashboard.cost import calculate_cost
from evalops_dashboard.models import (
    CriterionScore,
    Evaluation,
    ModelPricing,
    ModelResponse,
    Prompt,
    Rubric,
    RubricCriterion,
)
from evalops_dashboard.scoring import ScoredCriterion, calculate_scoring_result

SEED_PROMPT_TITLE = "Classify support ticket urgency"
SEED_RUBRIC_NAME = "Support Response Quality"
SEED_RUBRIC_VERSION = 1
SEED_PROVIDER = "openai-example"


def seed_database(session: Session) -> None:
    pricing = ensure_seed_pricing(session)
    prompt = ensure_seed_prompt(session)
    responses = ensure_seed_responses(session, prompt, pricing)
    rubric = ensure_seed_rubric(session)
    criteria = ensure_seed_criteria(session, rubric)
    ensure_seed_evaluation(
        session,
        responses["gpt-example-ops"],
        rubric,
        criteria,
        scores_by_name={
            "Instruction Following": 5,
            "Operational Accuracy": 5,
            "Clarity": 4,
        },
        justification=(
            "Correctly identifies production downtime as high urgency and gives a clear "
            "operational escalation path."
        ),
    )
    ensure_seed_evaluation(
        session,
        responses["gpt-example-balanced"],
        rubric,
        criteria,
        scores_by_name={
            "Instruction Following": 4,
            "Operational Accuracy": 4,
            "Clarity": 5,
        },
        justification=(
            "Classifies the issue correctly, but the operational escalation guidance is "
            "less direct than the strongest response."
        ),
    )


def ensure_seed_pricing(session: Session) -> dict[str, ModelPricing]:
    expected_pricing = [
        ModelPricing(
            provider=SEED_PROVIDER,
            model_name="gpt-example-ops",
            input_price_per_1k_tokens=0.01,
            output_price_per_1k_tokens=0.03,
        ),
        ModelPricing(
            provider=SEED_PROVIDER,
            model_name="gpt-example-balanced",
            input_price_per_1k_tokens=0.005,
            output_price_per_1k_tokens=0.015,
        ),
        ModelPricing(
            provider=SEED_PROVIDER,
            model_name="gpt-example-fast-draft",
            input_price_per_1k_tokens=0.001,
            output_price_per_1k_tokens=0.002,
        ),
    ]
    existing_pricing = {
        pricing.model_name: pricing
        for pricing in session.exec(
            select(ModelPricing).where(ModelPricing.provider == SEED_PROVIDER)
        ).all()
    }

    for pricing in expected_pricing:
        if pricing.model_name not in existing_pricing:
            session.add(pricing)
    session.commit()

    return {
        pricing.model_name: pricing
        for pricing in session.exec(
            select(ModelPricing).where(ModelPricing.provider == SEED_PROVIDER)
        ).all()
    }


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


def ensure_seed_responses(
    session: Session,
    prompt: Prompt,
    pricing: dict[str, ModelPricing],
) -> dict[str, ModelResponse]:
    seed_tokens = {
        "gpt-example-ops": (1200, 340),
        "gpt-example-balanced": (1200, 280),
        "gpt-example-fast-draft": (1200, 90),
    }

    def seed_cost(model_name: str) -> float | None:
        model_pricing = pricing.get(model_name)
        if model_pricing is None:
            return None
        input_tokens, output_tokens = seed_tokens[model_name]
        return calculate_cost(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_price_per_1k_tokens=model_pricing.input_price_per_1k_tokens,
            output_price_per_1k_tokens=model_pricing.output_price_per_1k_tokens,
        )

    expected_responses = [
        ModelResponse(
            prompt_id=prompt.id or 0,
            model_name="gpt-example-ops",
            response_text=(
                "High urgency. The customer reports production downtime and asks for "
                "immediate help, so the issue should be routed to the on-call support queue."
            ),
            latency_ms=842,
            provider=SEED_PROVIDER,
            input_tokens=seed_tokens["gpt-example-ops"][0],
            output_tokens=seed_tokens["gpt-example-ops"][1],
            cost_usd=seed_cost("gpt-example-ops"),
        ),
        ModelResponse(
            prompt_id=prompt.id or 0,
            model_name="gpt-example-balanced",
            response_text=(
                "High urgency because the customer says production is unavailable. "
                "Escalate to support and ask for affected service details."
            ),
            latency_ms=620,
            provider=SEED_PROVIDER,
            input_tokens=seed_tokens["gpt-example-balanced"][0],
            output_tokens=seed_tokens["gpt-example-balanced"][1],
            cost_usd=seed_cost("gpt-example-balanced"),
        ),
        ModelResponse(
            prompt_id=prompt.id or 0,
            model_name="gpt-example-fast-draft",
            response_text=("This appears urgent. A support teammate should review the issue soon."),
            latency_ms=210,
            provider=SEED_PROVIDER,
            input_tokens=seed_tokens["gpt-example-fast-draft"][0],
            output_tokens=seed_tokens["gpt-example-fast-draft"][1],
            cost_usd=seed_cost("gpt-example-fast-draft"),
        ),
    ]
    existing_responses = {
        response.model_name: response
        for response in session.exec(
            select(ModelResponse).where(ModelResponse.prompt_id == prompt.id)
        ).all()
    }

    for response in expected_responses:
        if response.model_name not in existing_responses:
            session.add(response)
    session.commit()

    return {
        response.model_name: response
        for response in session.exec(
            select(ModelResponse).where(ModelResponse.prompt_id == prompt.id)
        ).all()
        if response.model_name in {expected.model_name for expected in expected_responses}
    }


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
    scores_by_name: dict[str, int],
    justification: str,
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
        justification=justification,
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
