import os
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from evalops_dashboard.llm_judge import (
    AnthropicJudgeClient,
    JudgeCriterionScore,
    JudgeResult,
    build_judge_prompt,
    build_judge_tool_schema,
    get_judge_client,
    parse_judge_tool_response,
)
from evalops_dashboard.main import app
from evalops_dashboard.models import RubricCriterion


class FakeJudgeClient:
    def __init__(self, result: JudgeResult | None = None, error: Exception | None = None) -> None:
        self._result = result
        self._error = error

    def evaluate(self, response_text: str, criteria: list[RubricCriterion]) -> JudgeResult:
        if self._error is not None:
            raise self._error
        if self._result is not None:
            return self._result
        return JudgeResult(
            scores=[
                JudgeCriterionScore(criterion_id=criterion.id or 0, score=criterion.max_score)
                for criterion in criteria
            ],
            justification="Default fake justification.",
        )


@pytest.fixture(autouse=True)
def _default_judge_client() -> Generator[None]:
    """Stubs get_judge_client for every test in this file so none reach the
    network by default. Individual tests can still override
    app.dependency_overrides[get_judge_client] for a specific scenario.
    """
    app.dependency_overrides[get_judge_client] = lambda: FakeJudgeClient()
    yield
    app.dependency_overrides.pop(get_judge_client, None)


def make_criterion(criterion_id: int, min_score: int = 1, max_score: int = 5) -> RubricCriterion:
    return RubricCriterion(
        id=criterion_id,
        rubric_id=1,
        name="Clarity",
        description="Is the response clear?",
        weight=1,
        min_score=min_score,
        max_score=max_score,
        required=True,
    )


def make_tool_use_message(tool_input: dict) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", name="submit_evaluation", input=tool_input)]
    )


# --- pure function tests (zero mocking) ---


def test_build_judge_prompt_includes_response_text_and_criteria() -> None:
    criterion = make_criterion(1)
    prompt = build_judge_prompt("The sky is blue.", [criterion])

    assert "The sky is blue." in prompt
    assert "Clarity" in prompt
    assert "Is the response clear?" in prompt


def test_build_judge_tool_schema_bounds_each_criterion_by_min_max() -> None:
    criterion = make_criterion(7, min_score=2, max_score=4)
    schema = build_judge_tool_schema([criterion])

    assert schema["properties"]["criterion_7"] == {
        "type": "integer",
        "minimum": 2,
        "maximum": 4,
        "description": "Score for criterion 'Clarity': Is the response clear?",
    }
    assert "justification" in schema["properties"]
    assert set(schema["required"]) == {"criterion_7", "justification"}
    assert schema["additionalProperties"] is False


def test_parse_judge_tool_response_happy_path() -> None:
    criterion = make_criterion(1)
    message = make_tool_use_message({"criterion_1": 4, "justification": "Solid response."})

    result = parse_judge_tool_response(message, [criterion])

    assert result.scores == [JudgeCriterionScore(criterion_id=1, score=4)]
    assert result.justification == "Solid response."


def test_parse_judge_tool_response_raises_502_when_tool_not_called() -> None:
    criterion = make_criterion(1)
    message = SimpleNamespace(content=[SimpleNamespace(type="text", name=None, input=None)])

    with pytest.raises(HTTPException) as exc_info:
        parse_judge_tool_response(message, [criterion])

    assert exc_info.value.status_code == 502


def test_parse_judge_tool_response_raises_502_for_out_of_range_score() -> None:
    criterion = make_criterion(1, min_score=1, max_score=5)
    message = make_tool_use_message({"criterion_1": 9, "justification": "Too high."})

    with pytest.raises(HTTPException) as exc_info:
        parse_judge_tool_response(message, [criterion])

    assert exc_info.value.status_code == 502


def test_anthropic_judge_client_raises_503_when_api_key_missing() -> None:
    original = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        with pytest.raises(HTTPException) as exc_info:
            AnthropicJudgeClient().evaluate("text", [])
        assert exc_info.value.status_code == 503
    finally:
        if original is not None:
            os.environ["ANTHROPIC_API_KEY"] = original


# --- router tests (TestClient, dependency override) ---


def test_create_auto_evaluation_happy_path() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Auto Evaluation Quality")

        response = client.post(
            "/evaluations/auto",
            json={"response_id": response_id, "rubric_id": rubric["id"]},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["response_id"] == response_id
    assert body["rubric_id"] == rubric["id"]
    assert body["evaluator"] == "claude-judge"
    assert len(body["scores"]) == len(rubric["criteria"])


def test_create_auto_evaluation_returns_404_for_missing_response() -> None:
    with TestClient(app) as client:
        rubric = create_rubric(client, "Auto Evaluation Missing Response")

        response = client.post(
            "/evaluations/auto",
            json={"response_id": 999999, "rubric_id": rubric["id"]},
        )

    assert response.status_code == 404


def test_create_auto_evaluation_returns_404_for_missing_rubric() -> None:
    with TestClient(app) as client:
        response_id = create_response(client)

        response = client.post(
            "/evaluations/auto",
            json={"response_id": response_id, "rubric_id": 999999},
        )

    assert response.status_code == 404


def test_create_auto_evaluation_returns_502_when_judge_fails() -> None:
    app.dependency_overrides[get_judge_client] = lambda: FakeJudgeClient(
        error=HTTPException(
            status_code=502, detail="LLM judge did not return a structured evaluation."
        )
    )

    with TestClient(app) as client:
        response_id = create_response(client)
        rubric = create_rubric(client, "Auto Evaluation Judge Failure")

        response = client.post(
            "/evaluations/auto",
            json={"response_id": response_id, "rubric_id": rubric["id"]},
        )

    assert response.status_code == 502


def create_response(client: TestClient, title: str = "Evaluate response quality") -> int:
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


def create_rubric(client: TestClient, name: str, criteria: list[dict] | None = None) -> dict:
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
