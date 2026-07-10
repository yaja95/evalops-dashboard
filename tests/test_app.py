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
    assert evaluations_response.json()[0]["overall_score"] == 4.8
    assert evaluations_response.json()[0]["passed"] is True
    assert len(evaluations_response.json()[0]["scores"]) == 3
