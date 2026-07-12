from fastapi.testclient import TestClient

from evalops_dashboard.main import app

NONEXISTENT_ID = 999999


def test_dashboard_index_shows_section_links_and_counts() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard")

    assert response.status_code == 200
    assert "Prompts" in response.text
    assert "Model Responses" in response.text
    assert "Rubrics" in response.text
    assert "Evaluations" in response.text


def test_analytics_page_shows_seeded_criterion_charts() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/analytics")

    assert response.status_code == 200
    assert "Cross-Rubric Analytics" in response.text
    assert "Clarity" in response.text


def test_prompts_list_shows_seeded_prompt() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/prompts")

    assert response.status_code == 200
    assert "Classify support ticket urgency" in response.text


def test_prompt_detail_shows_its_model_responses() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response = client.get(f"/dashboard/prompts/{prompt_id}")

    assert response.status_code == 200
    assert "gpt-example-ops" in response.text
    assert "gpt-example-balanced" in response.text
    assert "gpt-example-fast-draft" in response.text


def test_prompt_detail_404_for_missing_prompt() -> None:
    with TestClient(app) as client:
        response = client.get(f"/dashboard/prompts/{NONEXISTENT_ID}")

    assert response.status_code == 404


def test_responses_list_shows_seeded_responses() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/responses")

    assert response.status_code == 200
    assert "gpt-example-ops" in response.text
    assert "gpt-example-balanced" in response.text
    assert "gpt-example-fast-draft" in response.text


def test_response_detail_shows_its_evaluation() -> None:
    with TestClient(app) as client:
        responses = client.get("/responses").json()
        evaluated_response_id = next(
            response["id"] for response in responses if response["model_name"] == "gpt-example-ops"
        )
        response = client.get(f"/dashboard/responses/{evaluated_response_id}")

    assert response.status_code == 200
    assert "seed" in response.text
    assert "4.8" in response.text


def test_response_detail_shows_empty_state_when_unevaluated() -> None:
    with TestClient(app) as client:
        responses = client.get("/responses").json()
        unevaluated_response_id = next(
            response["id"]
            for response in responses
            if response["model_name"] == "gpt-example-fast-draft"
        )
        response = client.get(f"/dashboard/responses/{unevaluated_response_id}")

    assert response.status_code == 200
    assert "No evaluations yet." in response.text


def test_response_detail_404_for_missing_response() -> None:
    with TestClient(app) as client:
        response = client.get(f"/dashboard/responses/{NONEXISTENT_ID}")

    assert response.status_code == 404


def test_rubrics_list_shows_seeded_rubric() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/rubrics")

    assert response.status_code == 200
    assert "Support Response Quality" in response.text


def test_rubric_detail_shows_its_criteria() -> None:
    with TestClient(app) as client:
        rubric_id = client.get("/rubrics").json()[0]["id"]
        response = client.get(f"/dashboard/rubrics/{rubric_id}")

    assert response.status_code == 200
    assert "Instruction Following" in response.text
    assert "Operational Accuracy" in response.text
    assert "Clarity" in response.text


def test_rubric_detail_404_for_missing_rubric() -> None:
    with TestClient(app) as client:
        response = client.get(f"/dashboard/rubrics/{NONEXISTENT_ID}")

    assert response.status_code == 404


def test_evaluations_list_shows_seeded_evaluations() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard/evaluations")

    assert response.status_code == 200
    assert response.text.count('class="badge badge-pass"') == 2


def test_evaluation_detail_shows_criterion_scores() -> None:
    with TestClient(app) as client:
        evaluation_id = client.get("/evaluations").json()[0]["id"]
        response = client.get(f"/dashboard/evaluations/{evaluation_id}")

    assert response.status_code == 200
    assert "Instruction Following" in response.text
    assert "production downtime" in response.text
    assert "Seed evaluation score." in response.text


def test_evaluation_detail_404_for_missing_evaluation() -> None:
    with TestClient(app) as client:
        response = client.get(f"/dashboard/evaluations/{NONEXISTENT_ID}")

    assert response.status_code == 404


def test_static_css_is_served() -> None:
    with TestClient(app) as client:
        response = client.get("/static/dashboard.css")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
