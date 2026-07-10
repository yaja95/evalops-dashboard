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
    assert evaluations_response.json()[0]["overall_score"] == 5
    assert evaluations_response.json()[0]["failure_category"] is None


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
                "instruction_following_score": 4,
                "truthfulness_score": 4,
                "completeness_score": 3,
                "conciseness_score": 5,
                "safety_score": 5,
                "writing_style_score": 4,
                "overall_score": 4,
                "failure_category": None,
                "justification": "Clear enough for a customer success follow-up.",
                "evaluator": "ajay",
            },
        )

    assert prompt_response.status_code == 201
    assert model_response.status_code == 201
    assert evaluation_response.status_code == 201
    assert evaluation_response.json()["overall_score"] == 4


def test_create_evaluation_requires_existing_response() -> None:
    with TestClient(app) as client:
        evaluation_response = client.post(
            "/evaluations",
            json={
                "response_id": 999_999,
                "rubric_name": "Missing response rubric",
                "instruction_following_score": 4,
                "truthfulness_score": 4,
                "completeness_score": 4,
                "conciseness_score": 4,
                "safety_score": 5,
                "writing_style_score": 4,
                "overall_score": 4,
                "failure_category": None,
                "justification": "This should fail because the response does not exist.",
                "evaluator": "ajay",
            },
        )

    assert evaluation_response.status_code == 404
    assert evaluation_response.json()["detail"] == "Model response 999999 was not found."


def test_evaluation_scores_must_be_between_one_and_five() -> None:
    with TestClient(app) as client:
        evaluation_response = client.post(
            "/evaluations",
            json={
                "response_id": 1,
                "rubric_name": "Invalid score rubric",
                "instruction_following_score": 6,
                "truthfulness_score": 4,
                "completeness_score": 4,
                "conciseness_score": 4,
                "safety_score": 5,
                "writing_style_score": 4,
                "overall_score": 4,
                "failure_category": "instruction_following",
                "justification": "The instruction following score is outside the rubric scale.",
                "evaluator": "ajay",
            },
        )

    assert evaluation_response.status_code == 422


def test_analytics_summary() -> None:
    with TestClient(app) as client:
        starting_summary = client.get("/analytics/summary").json()

        prompt_response = client.post(
            "/prompts",
            json={
                "title": "Check claim support",
                "content": "Identify whether the answer makes unsupported claims.",
                "use_case": "quality assurance",
                "owner": "evalops",
            },
        )
        prompt_id = prompt_response.json()["id"]

        model_response = client.post(
            "/responses",
            json={
                "prompt_id": prompt_id,
                "model_name": "gpt-example-qa",
                "response_text": "The answer references a contract clause that was not provided.",
                "latency_ms": 622,
            },
        )
        response_id = model_response.json()["id"]

        evaluation_response = client.post(
            "/evaluations",
            json={
                "response_id": response_id,
                "rubric_name": "Unsupported claim rubric v1",
                "instruction_following_score": 4,
                "truthfulness_score": 2,
                "completeness_score": 3,
                "conciseness_score": 4,
                "safety_score": 5,
                "writing_style_score": 4,
                "overall_score": 3,
                "failure_category": "unsupported_claim",
                "justification": "The response cites evidence that is not present in the prompt.",
                "evaluator": "ajay",
            },
        )

        summary_response = client.get("/analytics/summary")
        evaluations_response = client.get("/evaluations")

    evaluations = evaluations_response.json()
    average_overall_score = round(
        sum(evaluation["overall_score"] for evaluation in evaluations) / len(evaluations),
        2,
    )
    average_truthfulness_score = round(
        sum(evaluation["truthfulness_score"] for evaluation in evaluations) / len(evaluations),
        2,
    )
    pass_rate = round(
        len([evaluation for evaluation in evaluations if evaluation["overall_score"] >= 4])
        / len(evaluations),
        2,
    )

    assert prompt_response.status_code == 201
    assert model_response.status_code == 201
    assert evaluation_response.status_code == 201
    assert summary_response.status_code == 200
    assert summary_response.json() == {
        "prompt_count": starting_summary["prompt_count"] + 1,
        "response_count": starting_summary["response_count"] + 1,
        "evaluation_count": starting_summary["evaluation_count"] + 1,
        "average_overall_score": average_overall_score,
        "average_truthfulness_score": average_truthfulness_score,
        "most_common_failure_category": "unsupported_claim",
        "pass_rate": pass_rate,
    }
