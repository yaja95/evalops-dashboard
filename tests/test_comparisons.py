from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from evalops_dashboard.database import engine
from evalops_dashboard.main import app
from evalops_dashboard.models import CriterionScore, Evaluation, ModelResponse, Prompt
from evalops_dashboard.seed import (
    SEED_PROMPT_TITLE,
    SEED_RUBRIC_NAME,
    SEED_RUBRIC_VERSION,
    seed_database,
)


def test_nonexistent_prompt_returns_404() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Prompt 404 Rubric")
        response = client.get(f"/prompts/999999/comparison?rubric_id={rubric['id']}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Prompt 999999 was not found."


def test_nonexistent_rubric_returns_404() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Rubric 404 Prompt")
        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id=999999")

    assert response.status_code == 404
    assert response.json()["detail"] == "Rubric 999999 was not found."


def test_prompt_with_no_responses_returns_not_ready_comparison() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "No Responses Prompt")
        rubric = create_rubric(client, "No Responses Rubric")

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["response_count"] == 0
    assert body["compared_response_count"] == 0
    assert body["comparison_ready"] is False
    assert body["winner_response_id"] is None
    assert body["unscored_response_ids"] == []
    assert body["results"] == []


def test_prompt_with_responses_but_no_matching_evaluations_returns_unscored_ids() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Unscored Responses Prompt")
        rubric = create_rubric(client, "Unscored Responses Rubric")
        first_response = create_model_response(client, prompt["id"], "model-a")
        second_response = create_model_response(client, prompt["id"], "model-b")

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["response_count"] == 2
    assert body["compared_response_count"] == 0
    assert body["comparison_ready"] is False
    assert body["unscored_response_ids"] == [first_response["id"], second_response["id"]]
    assert body["results"] == []


def test_one_comparable_response_is_not_comparison_ready() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "One Comparable Prompt")
        rubric = create_rubric(client, "One Comparable Rubric")
        first_response = create_model_response(client, prompt["id"], "model-a")
        second_response = create_model_response(client, prompt["id"], "model-b")
        create_evaluation(client, first_response["id"], rubric, scores=[5, 4])

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    body = response.json()
    assert response.status_code == 200
    assert body["comparison_ready"] is False
    assert body["winner_response_id"] is None
    assert body["compared_response_count"] == 1
    assert body["unscored_response_ids"] == [second_response["id"]]


def test_two_comparable_responses_rank_and_set_winner() -> None:
    with TestClient(app) as client:
        prompt, rubric, response_ids = create_ranked_dataset(client)

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    body = response.json()
    assert response.status_code == 200
    assert body["comparison_ready"] is True
    assert body["winner_response_id"] == response_ids["better"]
    assert [result["rank"] for result in body["results"]] == [1, 2]
    assert [result["response_id"] for result in body["results"]] == [
        response_ids["better"],
        response_ids["slower"],
    ]


def test_higher_average_score_ranks_first() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Average Score Ranking Prompt")
        rubric = create_rubric(client, "Average Score Ranking Rubric")
        lower = create_model_response(client, prompt["id"], "lower", latency_ms=100)
        higher = create_model_response(client, prompt["id"], "higher", latency_ms=900)
        create_evaluation(client, lower["id"], rubric, scores=[4, 4])
        create_evaluation(client, higher["id"], rubric, scores=[5, 5])

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert [result["response_id"] for result in response.json()["results"]] == [
        higher["id"],
        lower["id"],
    ]


def test_raw_average_score_ranks_before_displayed_average_tie_breakers() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Raw Average Boundary Prompt")
        rubric = create_rubric(
            client,
            "Raw Average Boundary Rubric",
            criteria=[
                criterion_payload("Dominant", weight=99, required=True),
                criterion_payload("Small", weight=1, required=False),
            ],
        )
        response_a = create_model_response(client, prompt["id"], "raw-lower-fast", latency_ms=10)
        response_b = create_model_response(client, prompt["id"], "raw-higher-slow", latency_ms=999)
        create_evaluation(client, response_a["id"], rubric, scores=[4, 4], evaluator="a-one")
        create_evaluation(client, response_a["id"], rubric, scores=[4, 5], evaluator="a-two")
        create_evaluation(client, response_a["id"], rubric, scores=[4, 5], evaluator="a-three")
        create_evaluation(client, response_b["id"], rubric, scores=[4, 5], evaluator="b-one")

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    results = response.json()["results"]
    assert [result["average_overall_score"] for result in results] == [4.01, 4.01]
    assert [result["response_id"] for result in results] == [response_b["id"], response_a["id"]]


def test_pass_rate_breaks_average_score_tie() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Pass Rate Ranking Prompt")
        rubric = create_rubric(
            client,
            "Pass Rate Ranking Rubric",
            criteria=[
                criterion_payload("Required", weight=1, required=True),
                criterion_payload("Optional", weight=1, required=False),
            ],
        )
        lower_pass_rate = create_model_response(client, prompt["id"], "lower-pass-rate")
        higher_pass_rate = create_model_response(client, prompt["id"], "higher-pass-rate")
        create_evaluation(client, lower_pass_rate["id"], rubric, scores=[3, 5])
        create_evaluation(client, higher_pass_rate["id"], rubric, scores=[4, 4])

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert [result["response_id"] for result in response.json()["results"]] == [
        higher_pass_rate["id"],
        lower_pass_rate["id"],
    ]
    assert [result["pass_rate"] for result in response.json()["results"]] == [1.0, 0.0]


def test_exact_rubric_version_isolation() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Exact Rubric Version Prompt")
        rubric_v1 = create_rubric(client, "Versioned Comparison Rubric", version=1)
        rubric_v2 = create_rubric(client, "Versioned Comparison Rubric", version=2)
        response_a = create_model_response(client, prompt["id"], "version-one-lower")
        response_b = create_model_response(client, prompt["id"], "version-one-winner")
        create_evaluation(client, response_a["id"], rubric_v1, scores=[4, 4], evaluator="v1-a")
        create_evaluation(client, response_b["id"], rubric_v1, scores=[5, 5], evaluator="v1-b")
        create_evaluation(client, response_a["id"], rubric_v2, scores=[5, 5], evaluator="v2-a")
        create_evaluation(client, response_b["id"], rubric_v2, scores=[1, 1], evaluator="v2-b")

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric_v1['id']}")

    body = response.json()
    assert body["rubric"]["version"] == 1
    assert body["comparison_ready"] is True
    assert body["compared_response_count"] == 2
    assert body["winner_response_id"] == response_b["id"]
    assert [
        (result["response_id"], result["average_overall_score"]) for result in body["results"]
    ] == [
        (response_b["id"], 5.0),
        (response_a["id"], 4.0),
    ]


def test_latency_and_response_id_tie_breakers_are_deterministic() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Latency Tie Prompt")
        rubric = create_rubric(client, "Latency Tie Rubric")
        null_latency = create_model_response(client, prompt["id"], "null-latency", latency_ms=None)
        slower = create_model_response(client, prompt["id"], "slower", latency_ms=200)
        first_fast = create_model_response(client, prompt["id"], "first-fast", latency_ms=100)
        second_fast = create_model_response(client, prompt["id"], "second-fast", latency_ms=100)
        for model_response in [null_latency, slower, first_fast, second_fast]:
            create_evaluation(client, model_response["id"], rubric, scores=[4, 4])

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert [result["response_id"] for result in response.json()["results"]] == [
        first_fast["id"],
        second_fast["id"],
        slower["id"],
        null_latency["id"],
    ]


def test_multiple_evaluations_and_criterion_averages_are_calculated() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Multiple Evaluations Prompt")
        rubric = create_rubric(client, "Multiple Evaluations Rubric")
        model_response = create_model_response(client, prompt["id"], "multi-eval")
        create_evaluation(client, model_response["id"], rubric, scores=[5, 3], evaluator="one")
        create_evaluation(client, model_response["id"], rubric, scores=[3, 5], evaluator="two")

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    result = response.json()["results"][0]
    assert result["evaluation_count"] == 2
    assert result["average_overall_score"] == 4.0
    assert [average["criterion_id"] for average in result["criterion_averages"]] == sorted(
        average["criterion_id"] for average in result["criterion_averages"]
    )
    assert [average["average_score"] for average in result["criterion_averages"]] == [4.0, 4.0]


def test_evaluations_for_other_rubrics_and_prompts_are_excluded() -> None:
    with TestClient(app) as client:
        prompt = create_prompt(client, "Filtering Prompt")
        other_prompt = create_prompt(client, "Other Filtering Prompt")
        rubric = create_rubric(client, "Filtering Rubric")
        other_rubric = create_rubric(client, "Other Filtering Rubric")
        included = create_model_response(client, prompt["id"], "included")
        excluded_by_rubric = create_model_response(client, prompt["id"], "excluded-rubric")
        excluded_by_prompt = create_model_response(client, other_prompt["id"], "excluded-prompt")
        create_evaluation(client, included["id"], rubric, scores=[4, 4])
        create_evaluation(client, excluded_by_rubric["id"], other_rubric, scores=[5, 5])
        create_evaluation(client, excluded_by_prompt["id"], rubric, scores=[5, 5])

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    body = response.json()
    assert [result["response_id"] for result in body["results"]] == [included["id"]]
    assert body["unscored_response_ids"] == [excluded_by_rubric["id"]]


def test_repeated_requests_return_identical_ordering() -> None:
    with TestClient(app) as client:
        prompt, rubric, _response_ids = create_ranked_dataset(client)

        first_response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")
        second_response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    assert [result["response_id"] for result in first_response.json()["results"]] == [
        result["response_id"] for result in second_response.json()["results"]
    ]


def test_seed_data_is_idempotent() -> None:
    with Session(engine) as session:
        seed_database(session)
        counts_after_first_seed = object_counts(session)
        seed_database(session)
        counts_after_second_seed = object_counts(session)

    assert counts_after_second_seed == counts_after_first_seed


def test_seeded_data_produces_comparison_ready_result() -> None:
    with TestClient(app) as client:
        prompt = client.get("/prompts").json()[0]
        rubric = client.get("/rubrics").json()[0]

        response = client.get(f"/prompts/{prompt['id']}/comparison?rubric_id={rubric['id']}")

    body = response.json()
    assert prompt["title"] == SEED_PROMPT_TITLE
    assert rubric["name"] == SEED_RUBRIC_NAME
    assert rubric["version"] == SEED_RUBRIC_VERSION
    assert body["comparison_ready"] is True
    assert body["response_count"] == 3
    assert body["compared_response_count"] == 2
    assert body["results"][0]["model_name"] == "gpt-example-ops"
    assert body["unscored_response_ids"]


def test_comparison_endpoint_uses_bounded_select_queries() -> None:
    with TestClient(app) as client:
        small_prompt, small_rubric, _small_ids = create_ranked_dataset(
            client,
            prompt_title="Small Query Prompt",
            rubric_name="Small Query Rubric",
        )
        large_prompt, large_rubric = (
            create_prompt(client, "Large Query Prompt"),
            create_rubric(
                client,
                "Large Query Rubric",
            ),
        )
        for index in range(8):
            model_response = create_model_response(
                client,
                large_prompt["id"],
                f"large-model-{index}",
                latency_ms=100 + index,
            )
            create_evaluation(client, model_response["id"], large_rubric, scores=[4, 4])

        small_select_count = count_selects_during(
            lambda: client.get(
                f"/prompts/{small_prompt['id']}/comparison?rubric_id={small_rubric['id']}"
            )
        )
        large_select_count = count_selects_during(
            lambda: client.get(
                f"/prompts/{large_prompt['id']}/comparison?rubric_id={large_rubric['id']}"
            )
        )

    # Protects the endpoint from slipping into per-response or per-evaluation SELECTs.
    assert small_select_count == large_select_count
    assert large_select_count <= 6


def create_ranked_dataset(
    client: TestClient,
    prompt_title: str = "Ranked Prompt",
    rubric_name: str = "Ranked Rubric",
) -> tuple[dict, dict, dict[str, int]]:
    prompt = create_prompt(client, prompt_title)
    rubric = create_rubric(client, rubric_name)
    better = create_model_response(client, prompt["id"], "better", latency_ms=300)
    slower = create_model_response(client, prompt["id"], "slower", latency_ms=600)
    create_evaluation(client, better["id"], rubric, scores=[5, 4])
    create_evaluation(client, slower["id"], rubric, scores=[4, 4])
    return prompt, rubric, {"better": better["id"], "slower": slower["id"]}


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


def create_rubric(
    client: TestClient,
    name: str,
    version: int = 1,
    criteria: list[dict] | None = None,
) -> dict:
    response = client.post(
        "/rubrics",
        json={
            "name": name,
            "version": version,
            "description": "Comparison test rubric.",
            "pass_threshold": 4,
            "criteria": criteria
            or [
                criterion_payload("Instruction Following", weight=1, required=True),
                criterion_payload("Accuracy", weight=1, required=True),
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
            "justification": "Comparison test evaluation.",
            "evaluator": evaluator,
            "scores": [
                {
                    "criterion_id": criterion["id"],
                    "score": scores[index],
                    "notes": f"Score for {criterion['name']}.",
                }
                for index, criterion in enumerate(rubric["criteria"])
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


def object_counts(session: Session) -> dict[str, int]:
    return {
        "prompts": len(session.exec(select(Prompt)).all()),
        "responses": len(session.exec(select(ModelResponse)).all()),
        "evaluations": len(session.exec(select(Evaluation)).all()),
        "criterion_scores": len(session.exec(select(CriterionScore)).all()),
    }


def count_selects_during(callback: Callable[[], object]) -> int:
    statements = []

    def before_cursor_execute(
        conn,
        cursor,
        statement,
        parameters,
        context,
        executemany,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        callback()
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    return len(statements)
