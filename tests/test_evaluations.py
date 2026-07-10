import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from evalops_dashboard.database import engine
from evalops_dashboard.main import app
from evalops_dashboard.models import (
    CriterionScore,
    Evaluation,
    ModelResponse,
    Prompt,
    Rubric,
    RubricCriterion,
)
from evalops_dashboard.seed import seed_database


def test_create_evaluation_with_multiple_criteria() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Evaluation Quality")

        response = client.post(
            "/evaluations",
            json=evaluation_payload(response_id, rubric),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["response_id"] == response_id
    assert body["rubric_id"] == rubric["id"]
    assert body["rubric_name"] == "Evaluation Quality"
    assert body["rubric_version"] == 1
    assert body["overall_score"] == 4.67
    assert body["passed"] is True
    assert [score["criterion_name"] for score in body["scores"]] == [
        "Instruction Following",
        "Accuracy",
    ]


def test_required_criterion_failure_despite_passing_weighted_average() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(
            client,
            "Required Criterion Failure",
            criteria=[
                criterion_payload("Accuracy", weight=1, required=True),
                criterion_payload("Clarity", weight=10, required=False),
            ],
        )
        payload = evaluation_payload(response_id, rubric, scores=[3, 5])

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 201
    assert response.json()["overall_score"] == 4.82
    assert response.json()["passed"] is False


def test_low_non_required_criterion_can_still_pass() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(
            client,
            "Optional Criterion Low Score",
            criteria=[
                criterion_payload("Accuracy", weight=10, required=True),
                criterion_payload("Style", weight=1, required=False),
            ],
        )
        payload = evaluation_payload(response_id, rubric, scores=[5, 1])

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 201
    assert response.json()["overall_score"] == 4.64
    assert response.json()["passed"] is True


def test_score_that_rounds_up_to_threshold_does_not_pass() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(
            client,
            "Rounded Boundary Failure",
            criteria=[
                criterion_payload("Minor Criterion", weight=1, required=False),
                criterion_payload("Major Criterion", weight=249, required=False),
            ],
        )
        payload = evaluation_payload(response_id, rubric, scores=[3, 4])

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 201
    assert response.json()["overall_score"] == 4.0
    assert response.json()["passed"] is False


@pytest.mark.parametrize("field_name", ["overall_score", "passed"])
def test_rejects_client_submitted_calculated_fields(field_name: str) -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, f"Rejects {field_name}")
        payload = evaluation_payload(response_id, rubric)
        payload[field_name] = 5

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422


def test_rejects_duplicate_criterion_ids() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Duplicate Criterion IDs")
        first_criterion_id = rubric["criteria"][0]["id"]
        payload = evaluation_payload(response_id, rubric)
        payload["scores"][1]["criterion_id"] = first_criterion_id

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422


def test_rejects_missing_criterion_id() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Missing Criterion ID")
        payload = evaluation_payload(response_id, rubric)
        payload["scores"] = payload["scores"][:1]

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422
    assert "Missing scores" in response.json()["detail"]


def test_rejects_criterion_belonging_to_different_rubric() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Primary Rubric")
        other_rubric = create_rubric(client, "Other Rubric")
        payload = evaluation_payload(response_id, rubric)
        payload["scores"][1]["criterion_id"] = other_rubric["criteria"][0]["id"]

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422


def test_rejects_unknown_criterion_id() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Unknown Criterion ID")
        payload = evaluation_payload(response_id, rubric)
        payload["scores"][1]["criterion_id"] = 999_999

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(("score_index", "score"), [(0, 0), (1, 6)])
def test_rejects_scores_outside_criterion_bounds(score_index: int, score: int) -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, f"Invalid Score {score}")
        payload = evaluation_payload(response_id, rubric)
        payload["scores"][score_index]["score"] = score

        response = client.post("/evaluations", json=payload)

    assert response.status_code == 422


def test_create_evaluation_requires_existing_response() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Missing Response")
        response = client.post("/evaluations", json=evaluation_payload(999_999, rubric))

    assert response.status_code == 404
    assert response.json()["detail"] == "Model response 999999 was not found."


def test_create_evaluation_requires_existing_rubric() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        response = client.post(
            "/evaluations",
            json={
                "response_id": response_id,
                "rubric_id": 999_999,
                "justification": "Missing rubric.",
                "evaluator": "ajay",
                "scores": [{"criterion_id": 1, "score": 4}],
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Rubric 999999 was not found."


def test_get_nonexistent_evaluation_returns_404() -> None:
    with TestClient(app) as client:
        response = client.get("/evaluations/999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation 999999 was not found."


def test_list_and_detail_include_nested_scores_with_deterministic_order() -> None:
    with TestClient(app) as client:
        first_response_id = create_response(client, title="First evaluation prompt")
        second_response_id = create_response(client, title="Second evaluation prompt")
        rubric = create_rubric(client, "Nested Scores")
        first_create = client.post(
            "/evaluations",
            json=evaluation_payload(first_response_id, rubric, scores=[4, 4]),
        )
        second_create = client.post(
            "/evaluations",
            json=evaluation_payload(second_response_id, rubric, scores=[5, 4]),
        )

        list_response = client.get("/evaluations")
        detail_response = client.get(f"/evaluations/{second_create.json()['id']}")

    evaluation_ids = [evaluation["id"] for evaluation in list_response.json()]
    assert first_create.status_code == 201
    assert second_create.status_code == 201
    assert evaluation_ids == sorted(evaluation_ids)
    assert [score["criterion_name"] for score in detail_response.json()["scores"]] == [
        "Instruction Following",
        "Accuracy",
    ]


def test_invalid_request_leaves_no_partial_records() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Rollback Validation")
        starting_count = len(client.get("/evaluations").json())
        payload = evaluation_payload(response_id, rubric)
        payload["scores"] = payload["scores"][:1]

        response = client.post("/evaluations", json=payload)
        ending_count = len(client.get("/evaluations").json())

    assert response.status_code == 422
    assert ending_count == starting_count


def test_database_error_during_criterion_score_insert_rolls_back_evaluation() -> None:
    trigger_name = "reject_criterionscore_insert"
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Forced Rollback")
        with Session(engine) as session:
            starting_counts = object_counts(session)
            session.execute(
                text(
                    f"""
                    CREATE TRIGGER {trigger_name}
                    BEFORE INSERT ON criterionscore
                    BEGIN
                        SELECT RAISE(ABORT, 'forced criterionscore insert failure');
                    END
                    """
                )
            )
            session.commit()

        try:
            response = client.post(
                "/evaluations",
                json=evaluation_payload(response_id, rubric),
            )
        finally:
            with Session(engine) as session:
                session.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
                session.commit()

        with Session(engine) as session:
            ending_counts = object_counts(session)

    assert response.status_code == 422
    assert ending_counts["evaluations"] == starting_counts["evaluations"]
    assert ending_counts["criterion_scores"] == starting_counts["criterion_scores"]


def test_invalid_required_criterion_rubric_configuration_is_rejected_at_evaluation_time() -> None:
    with Session(engine) as session:
        prompt = Prompt(
            title="Invalid rubric config prompt",
            content="Evaluate this.",
            use_case="testing",
            owner="tests",
        )
        session.add(prompt)
        session.commit()
        session.refresh(prompt)
        response = ModelResponse(
            prompt_id=prompt.id or 0,
            model_name="gpt-example-invalid-rubric",
            response_text="A response.",
        )
        rubric = Rubric(
            name="Invalid Stored Rubric",
            version=1,
            description="Invalid required max score.",
            pass_threshold=4,
        )
        session.add(response)
        session.add(rubric)
        session.commit()
        session.refresh(response)
        session.refresh(rubric)
        criterion = RubricCriterion(
            rubric_id=rubric.id or 0,
            name="Impossible Required Criterion",
            description="Cannot meet threshold.",
            weight=1,
            min_score=1,
            max_score=3,
            required=True,
        )
        session.add(criterion)
        session.commit()
        session.refresh(criterion)

        response_id = response.id or 0
        rubric_id = rubric.id or 0
        criterion_id = criterion.id or 0

    with TestClient(app) as client:
        response = client.post(
            "/evaluations",
            json={
                "response_id": response_id,
                "rubric_id": rubric_id,
                "justification": "This should be rejected.",
                "evaluator": "ajay",
                "scores": [{"criterion_id": criterion_id, "score": 3}],
            },
        )

    assert response.status_code == 422
    assert "Rubric configuration is invalid" in response.json()["detail"]


def test_seed_data_is_idempotent() -> None:
    with Session(engine) as session:
        seed_database(session)
        counts_after_first_seed = object_counts(session)
        seed_database(session)
        counts_after_second_seed = object_counts(session)

    assert counts_after_second_seed == counts_after_first_seed


def test_analytics_use_calculated_scores_and_stored_pass_fail() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(
            client,
            "Analytics Rubric",
            criteria=[
                criterion_payload("Required", weight=1, required=True),
                criterion_payload("Optional", weight=10, required=False),
            ],
        )
        client.post("/evaluations", json=evaluation_payload(response_id, rubric, scores=[3, 5]))

        summary_response = client.get("/analytics/summary")
        evaluations_response = client.get("/evaluations")

    evaluations = evaluations_response.json()
    average_overall_score = round(
        sum(evaluation["overall_score"] for evaluation in evaluations) / len(evaluations),
        2,
    )
    pass_rate = round(
        len([evaluation for evaluation in evaluations if evaluation["passed"]]) / len(evaluations),
        2,
    )
    assert summary_response.json() == {
        "prompt_count": len({evaluation["response_id"] for evaluation in evaluations}),
        "response_count": len(evaluations),
        "evaluation_count": len(evaluations),
        "average_overall_score": average_overall_score,
        "pass_rate": pass_rate,
    }


def test_sqlite_enforces_foreign_keys() -> None:
    with pytest.raises(IntegrityError):
        with Session(engine) as session:
            session.add(
                CriterionScore(
                    evaluation_id=999_999,
                    criterion_id=999_999,
                    score=4,
                )
            )
            session.commit()


def create_response(
    client: TestClient,
    title: str = "Evaluate response quality",
) -> int:
    prompt_response = client.post(
        "/prompts",
        json={
            "title": title,
            "content": "Evaluate this model response.",
            "use_case": "evaluation",
            "owner": "tests",
        },
    )
    prompt_id = prompt_response.json()["id"]
    model_response = client.post(
        "/responses",
        json={
            "prompt_id": prompt_id,
            "model_name": "gpt-example-test",
            "response_text": "This is the model response to evaluate.",
            "latency_ms": 100,
        },
    )
    return model_response.json()["id"]


def create_rubric(
    client: TestClient,
    name: str,
    criteria: list[dict] | None = None,
) -> dict:
    response = client.post(
        "/rubrics",
        json={
            "name": name,
            "version": 1,
            "description": "Test rubric.",
            "pass_threshold": 4,
            "criteria": criteria
            or [
                criterion_payload("Instruction Following", weight=2, required=True),
                criterion_payload("Accuracy", weight=1, required=True),
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def criterion_payload(name: str, weight: float, required: bool) -> dict:
    return {
        "name": name,
        "description": f"{name} criterion.",
        "weight": weight,
        "min_score": 1,
        "max_score": 5,
        "required": required,
    }


def evaluation_payload(
    response_id: int,
    rubric: dict,
    scores: list[int] | None = None,
) -> dict:
    criterion_scores = scores or [5, 4]
    return {
        "response_id": response_id,
        "rubric_id": rubric["id"],
        "justification": "The response followed the task and was accurate.",
        "evaluator": "ajay",
        "scores": [
            {
                "criterion_id": criterion["id"],
                "score": criterion_scores[index],
                "notes": f"Score for {criterion['name']}.",
            }
            for index, criterion in enumerate(rubric["criteria"])
        ],
    }


def object_counts(session: Session) -> dict[str, int]:
    return {
        "prompts": len(session.exec(select(Prompt)).all()),
        "responses": len(session.exec(select(ModelResponse)).all()),
        "rubrics": len(session.exec(select(Rubric)).all()),
        "criteria": len(session.exec(select(RubricCriterion)).all()),
        "evaluations": len(session.exec(select(Evaluation)).all()),
        "criterion_scores": len(session.exec(select(CriterionScore)).all()),
    }
