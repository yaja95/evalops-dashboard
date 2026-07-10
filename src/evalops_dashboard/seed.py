from sqlmodel import Session, select

from evalops_dashboard.models import Evaluation, ModelResponse, Prompt


def seed_database(session: Session) -> None:
    existing_prompt = session.exec(select(Prompt)).first()
    if existing_prompt is not None:
        return

    prompt = Prompt(
        title="Classify support ticket urgency",
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

    evaluation = Evaluation(
        response_id=response.id or 0,
        rubric_name="Support urgency rubric v1",
        score=5,
        passed=True,
        notes="Correctly identifies business impact and escalation path.",
        evaluator="seed",
    )
    session.add(evaluation)
    session.commit()
