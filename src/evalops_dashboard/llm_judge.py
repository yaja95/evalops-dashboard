import os
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import anthropic
from fastapi import Depends, HTTPException, status

from evalops_dashboard.models import (
    CriterionScoreCreate,
    EvaluationCreate,
    ModelResponse,
    Rubric,
    RubricCriterion,
)

ANTHROPIC_JUDGE_MODEL_FALLBACK = "claude-haiku-4-5-20251001"
JUDGE_TOOL_NAME = "submit_evaluation"


@dataclass(frozen=True)
class JudgeCriterionScore:
    criterion_id: int
    score: int


@dataclass(frozen=True)
class JudgeResult:
    scores: list[JudgeCriterionScore]
    justification: str


def criterion_property_name(criterion: RubricCriterion) -> str:
    return f"criterion_{criterion.id}"


def build_judge_prompt(response_text: str, criteria: list[RubricCriterion]) -> str:
    criteria_lines = "\n".join(
        f"- {criterion.name} (score {criterion.min_score}-{criterion.max_score}"
        f"{', required' if criterion.required else ''}): {criterion.description}"
        for criterion in criteria
    )
    return (
        "You are evaluating an AI model's response against a scoring rubric.\n\n"
        f"Model response to evaluate:\n{response_text}\n\n"
        f"Rubric criteria:\n{criteria_lines}\n\n"
        "Score every criterion within its stated range and call the "
        f"{JUDGE_TOOL_NAME} tool with your scores and a brief overall justification."
    )


def build_judge_tool_schema(criteria: list[RubricCriterion]) -> dict[str, Any]:
    properties: dict[str, Any] = {
        criterion_property_name(criterion): {
            "type": "integer",
            "minimum": criterion.min_score,
            "maximum": criterion.max_score,
            "description": f"Score for criterion '{criterion.name}': {criterion.description}",
        }
        for criterion in criteria
    }
    properties["justification"] = {
        "type": "string",
        "description": "Brief overall justification for the scores given.",
    }
    return {
        "type": "object",
        "properties": properties,
        "required": [*properties.keys()],
        "additionalProperties": False,
    }


def parse_judge_tool_response(message: Any, criteria: list[RubricCriterion]) -> JudgeResult:
    tool_use_block = next(
        (
            block
            for block in message.content
            if getattr(block, "type", None) == "tool_use"
            and getattr(block, "name", None) == JUDGE_TOOL_NAME
        ),
        None,
    )
    if tool_use_block is None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM judge did not return a structured evaluation.",
        )

    tool_input = tool_use_block.input
    scores: list[JudgeCriterionScore] = []
    for criterion in criteria:
        key = criterion_property_name(criterion)
        value = tool_input.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM judge did not return a valid integer score for criterion "
                f"'{criterion.name}'.",
            )
        if not (criterion.min_score <= value <= criterion.max_score):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM judge returned an out-of-range score for criterion "
                f"'{criterion.name}'.",
            )
        scores.append(JudgeCriterionScore(criterion_id=criterion.id or 0, score=value))

    justification = tool_input.get("justification")
    if not isinstance(justification, str) or not justification.strip():
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM judge did not return a justification.",
        )

    return JudgeResult(scores=scores, justification=justification.strip())


class JudgeClient(Protocol):
    def evaluate(self, response_text: str, criteria: list[RubricCriterion]) -> JudgeResult: ...


class AnthropicJudgeClient:
    def __init__(self) -> None:
        self._client: anthropic.Anthropic | None = None

    def _client_or_503(self) -> anthropic.Anthropic:
        if self._client is None:
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="ANTHROPIC_API_KEY is not configured; the LLM judge is unavailable.",
                )
            self._client = anthropic.Anthropic(api_key=api_key)
        return self._client

    def evaluate(self, response_text: str, criteria: list[RubricCriterion]) -> JudgeResult:
        client = self._client_or_503()
        model = os.getenv("ANTHROPIC_JUDGE_MODEL", ANTHROPIC_JUDGE_MODEL_FALLBACK)
        try:
            message = client.messages.create(
                model=model,
                max_tokens=1024,
                tools=[
                    {
                        "name": JUDGE_TOOL_NAME,
                        "description": (
                            "Submit the per-criterion scores and overall justification "
                            "for this evaluation."
                        ),
                        "input_schema": build_judge_tool_schema(criteria),
                    }
                ],
                tool_choice={"type": "tool", "name": JUDGE_TOOL_NAME},
                messages=[{"role": "user", "content": build_judge_prompt(response_text, criteria)}],
            )
        except anthropic.APIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM judge request failed: {exc}",
            ) from exc

        return parse_judge_tool_response(message, criteria)


def get_judge_client() -> JudgeClient:
    return AnthropicJudgeClient()


JudgeClientDep = Annotated[JudgeClient, Depends(get_judge_client)]


def build_auto_evaluation_create(
    model_response: ModelResponse,
    rubric: Rubric,
    criteria: list[RubricCriterion],
    judge_client: JudgeClient,
) -> EvaluationCreate:
    if not criteria:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Rubric {rubric.id} has no criteria to score.",
        )
    judge_result = judge_client.evaluate(model_response.response_text, criteria)
    return EvaluationCreate(
        response_id=model_response.id or 0,
        rubric_id=rubric.id or 0,
        justification=judge_result.justification,
        evaluator="claude-judge",
        scores=[
            CriterionScoreCreate(criterion_id=score.criterion_id, score=score.score, notes="")
            for score in judge_result.scores
        ],
    )
