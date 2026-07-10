import os

os.environ["EVALOPS_DATABASE_URL"] = "sqlite://"

from fastapi.testclient import TestClient

from evalops_dashboard.main import app


def test_health_endpoint() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "evalops-dashboard"}


def test_seeded_records_are_available() -> None:
    with TestClient(app) as client:
        prompts_response = client.get("/prompts")
        responses_response = client.get("/responses")
        evaluations_response = client.get("/evaluations")

    assert prompts_response.status_code == 200
    assert responses_response.status_code == 200
    assert evaluations_response.status_code == 200
    assert prompts_response.json()[0]["title"] == "Classify support ticket urgency"
    assert responses_response.json()[0]["model_name"] == "gpt-example-ops"
    assert evaluations_response.json()[0]["passed"] is True


def test_create_prompt_response_and_evaluation() -> None:
    with TestClient(app) as client:
        prompt_response = client.post(
            "/prompts",
            json={
                "title": "Summarize renewal risk",
                "content": "Summarize the renewal risk in one paragraph.",
                "use_case": "account management",
                "owner": "field-team",
            },
        )
        prompt_id = prompt_response.json()["id"]

        model_response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "gpt-example-field",
                "response_text": (
                    "The account is at medium renewal risk due to open support issues."
                ),
                "latency_ms": 517,
            },
        )
        response_id = model_response.json()["id"]

        evaluation_response = client.post(
            "/evaluations",
            json={
                "response_id": response_id,
                "rubric_name": "Renewal risk rubric v1",
                "score": 4,
                "passed": True,
                "notes": "Clear enough for a customer success follow-up.",
                "evaluator": "ajay",
            },
        )

    assert prompt_response.status_code == 201
    assert model_response.status_code == 201
    assert evaluation_response.status_code == 201
    assert evaluation_response.json()["score"] == 4
