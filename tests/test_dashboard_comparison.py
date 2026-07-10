from fastapi.testclient import TestClient

from evalops_dashboard.main import app

NONEXISTENT_ID = 999999


def test_seeded_comparison_shows_scores_and_unscored_response() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response = client.get(f"/dashboard/prompts/{prompt_id}/comparison")

    assert response.status_code == 200
    assert "gpt-example-ops" in response.text
    assert "gpt-example-balanced" in response.text
    assert "4.80" in response.text
    assert "4.20" in response.text
    assert "Winner" in response.text
    assert "Response #" in response.text


def test_auto_selects_when_exactly_one_applicable_rubric() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response = client.get(f"/dashboard/prompts/{prompt_id}/comparison")

    assert response.status_code == 200
    assert "rubric-select-form" not in response.text
    assert "Quality (overall score)" in response.text


def test_shows_selection_form_with_multiple_applicable_rubrics() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response_id = client.get("/responses").json()[0]["id"]
        second_rubric = create_rubric(client, "Second Rubric")
        create_evaluation(client, response_id, second_rubric, scores=[5])

        response = client.get(f"/dashboard/prompts/{prompt_id}/comparison")

    assert response.status_code == 200
    assert "rubric-select-form" in response.text
    assert "Select a rubric above to view the comparison." in response.text
    assert "Quality (overall score)" not in response.text


def test_shows_not_ready_message_with_fewer_than_two_scored_responses() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Single Response Prompt")
        rubric = create_rubric(client, "Single Response Rubric")
        response = create_model_response(client, prompt["id"], "solo-model")
        create_evaluation(client, response["id"], rubric, scores=[5])

        page = client.get(f"/dashboard/prompts/{prompt['id']}/comparison")

    assert page.status_code == 200
    assert "Not enough evaluated responses yet" in page.text
    assert "Quality (overall score)" not in page.text


def test_shows_empty_state_with_zero_applicable_rubrics() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "No Evaluations Prompt")
        response = client.get(f"/dashboard/prompts/{prompt['id']}/comparison")

    assert response.status_code == 200
    assert "No rubric has evaluated any responses for this prompt yet." in response.text
    assert "rubric-select-form" not in response.text


def test_404_for_missing_prompt() -> None:
    with TestClient(app) as client:
        response = client.get(f"/dashboard/prompts/{NONEXISTENT_ID}/comparison")

    assert response.status_code == 404


def test_404_for_rubric_that_never_evaluated_this_prompt() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        unrelated_rubric = create_rubric(client, "Unrelated Rubric")

        response = client.get(
            f"/dashboard/prompts/{prompt_id}/comparison?rubric_id={unrelated_rubric['id']}"
        )

    assert response.status_code == 404


def test_404_for_nonexistent_rubric_id() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response = client.get(
            f"/dashboard/prompts/{prompt_id}/comparison?rubric_id={NONEXISTENT_ID}"
        )

    assert response.status_code == 404


def test_prompt_detail_links_to_comparison_page() -> None:
    with TestClient(app) as client:
        prompt_id = client.get("/prompts").json()[0]["id"]
        response = client.get(f"/dashboard/prompts/{prompt_id}")

    assert response.status_code == 200
    assert f"/dashboard/prompts/{prompt_id}/comparison" in response.text


def create_prompt(client: TestClient, title: str) -> dict:
    response = client.post(
        "/prompts",
        json={
            "title": title,
            "content": "Compare model responses for this prompt.",
            "use_case": "comparison",
            "owner": "tests",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_model_response(
    client: TestClient,
    prompt_id: int,
    model_name: str,
    latency_ms: int | None = 100,
) -> dict:
    response = client.post(
        "/responses",
        json={
            "prompt_id": prompt_id,
            "model_name": model_name,
            "response_text": f"Response from {model_name}.",
            "latency_ms": latency_ms,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_rubric(client: TestClient, name: str, version: int = 1) -> dict:
    response = client.post(
        "/rubrics",
        json={
            "name": name,
            "version": version,
            "description": "Dashboard comparison test rubric.",
            "pass_threshold": 4,
            "criteria": [
                {
                    "name": "Overall",
                    "description": "Overall quality.",
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


def create_evaluation(
    client: TestClient,
    response_id: int,
    rubric: dict,
    scores: list[int],
    evaluator: str = "test-evaluator",
) -> dict:
    response = client.post(
        "/evaluations",
        json={
            "response_id": response_id,
            "rubric_id": rubric["id"],
            "justification": "Dashboard comparison test evaluation.",
            "evaluator": evaluator,
            "scores": [
                {
                    "criterion_id": criterion["id"],
                    "score": scores[index],
                    "notes": "",
                }
                for index, criterion in enumerate(rubric["criteria"])
            ],
        },
    )
    assert response.status_code == 201
    return response.json()
