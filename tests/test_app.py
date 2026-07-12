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


def test_criteria_analytics_aggregates_same_criterion_name_across_different_rubrics() -> None:
    """The actual cross-rubric proof at the HTTP level: two different rubrics each
    have their own criterion with the same name (different RubricCriterion rows,
    since names are only unique within a rubric) -- the endpoint must combine them
    into one entry, not report two separate ones. Uses a criterion name not used by
    seed data so the count reflects only what this test creates.
    """
    with TestClient(app) as client:
        response_id = create_response(client, title="Analytics test prompt")

        rubric_a = create_rubric(client, "Analytics Rubric A")
        rubric_b = create_rubric(client, "Analytics Rubric B")

        create_evaluation(client, response_id, rubric_a, score=4)
        create_evaluation(client, response_id, rubric_b, score=2)

        analytics_response = client.get("/analytics/by-criterion")

    assert analytics_response.status_code == 200
    criteria = analytics_response.json()["criteria"]
    matching_entries = [
        c for c in criteria if c["criterion_name"] == "Analytics Cross Rubric Marker"
    ]

    assert len(matching_entries) == 1
    entry = matching_entries[0]
    assert entry["evaluation_count"] == 2
    assert entry["average_score"] == 3.0


def create_response(client: TestClient, title: str) -> int:
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


def create_rubric(client: TestClient, name: str) -> dict:
    response = client.post(
        "/rubrics",
        json={
            "name": name,
            "version": 1,
            "description": "Test rubric.",
            "pass_threshold": 4,
            "criteria": [
                {
                    "name": "Analytics Cross Rubric Marker",
                    "description": "Clarity criterion.",
                    "weight": 1,
                    "min_score": 1,
                    "max_score": 5,
                    "required": True,
                }
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def create_evaluation(client: TestClient, response_id: int, rubric: dict, score: int) -> None:
    evaluation_response = client.post(
        "/evaluations",
        json={
            "response_id": response_id,
            "rubric_id": rubric["id"],
            "justification": "Test justification.",
            "evaluator": "tests",
            "scores": [
                {
                    "criterion_id": rubric["criteria"][0]["id"],
                    "score": score,
                    "notes": "",
                }
            ],
        },
    )
    assert evaluation_response.status_code == 201
