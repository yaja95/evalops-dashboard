import os
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

import anthropic
import ollama
from fastapi import Depends, HTTPException, status

from evalops_dashboard.models import (
    CriterionScoreCreate,
    EvaluationCreate,
    ModelResponse,
    Rubric,
    RubricCriterion,
)

ANTHROPIC_JUDGE_MODEL_FALLBACK = "claude-haiku-4-5-20251001"
OLLAMA_JUDGE_MODEL_FALLBACK = "qwen2.5:1.5b"
JUDGE_TOOL_NAME = "submit_evaluation"


@dataclass(frozen=True)
class JudgeCriterionScore:
    criterion_id: int
    score: int


@dataclass(frozen=True)
class JudgeResult:
    scores: list[JudgeCriterionScore]
    justification: str
    input_tokens: int | None
    output_tokens: int | None
    model: str


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


def build_judge_result_from_tool_input(
    tool_input: dict[str, Any],
    criteria: list[RubricCriterion],
    input_tokens: int | None,
    output_tokens: int | None,
    model: str,
) -> JudgeResult:
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

    return JudgeResult(
        scores=scores,
        justification=justification.strip(),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
    )


def parse_anthropic_tool_response(message: Any, criteria: list[RubricCriterion]) -> JudgeResult:
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
    usage = getattr(message, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage is not None else None
    output_tokens = getattr(usage, "output_tokens", None) if usage is not None else None
    return build_judge_result_from_tool_input(
        tool_use_block.input, criteria, input_tokens, output_tokens, message.model
    )


def parse_ollama_tool_response(response: Any, criteria: list[RubricCriterion]) -> JudgeResult:
    tool_calls = response.message.tool_calls
    if not tool_calls:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LLM judge did not return a structured evaluation.",
        )
    return build_judge_result_from_tool_input(
        dict(tool_calls[0].function.arguments),
        criteria,
        response.prompt_eval_count,
        response.eval_count,
        response.model,
    )


class JudgeClient(Protocol):
    evaluator_name: str
    provider: str

    def evaluate(self, response_text: str, criteria: list[RubricCriterion]) -> JudgeResult: ...


class AnthropicJudgeClient:
    evaluator_name = "claude-judge"
    provider = "anthropic"

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

        return parse_anthropic_tool_response(message, criteria)


class OllamaJudgeClient:
    evaluator_name = "ollama-judge"
    provider = "ollama"

    def __init__(self) -> None:
        self._client: ollama.Client | None = None

    def _get_client(self) -> ollama.Client:
        if self._client is None:
            host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
            self._client = ollama.Client(host=host)
        return self._client

    def evaluate(self, response_text: str, criteria: list[RubricCriterion]) -> JudgeResult:
        client = self._get_client()
        model = os.getenv("OLLAMA_JUDGE_MODEL", OLLAMA_JUDGE_MODEL_FALLBACK)
        try:
            response = client.chat(
                model=model,
                messages=[{"role": "user", "content": build_judge_prompt(response_text, criteria)}],
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": JUDGE_TOOL_NAME,
                            "description": (
                                "Submit the per-criterion scores and overall justification "
                                "for this evaluation."
                            ),
                            "parameters": build_judge_tool_schema(criteria),
                        },
                    }
                ],
            )
        except ConnectionError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Ollama is not reachable; the LLM judge is unavailable.",
            ) from exc
        except (ollama.ResponseError, ollama.RequestError) as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM judge request failed: {exc}",
            ) from exc

        return parse_ollama_tool_response(response, criteria)


def get_judge_client() -> JudgeClient:
    if os.getenv("LLM_JUDGE_PROVIDER", "anthropic").lower() == "ollama":
        return OllamaJudgeClient()
    return AnthropicJudgeClient()


JudgeClientDep = Annotated[JudgeClient, Depends(get_judge_client)]


def build_auto_evaluation_create(
    model_response: ModelResponse,
    rubric: Rubric,
    judge_result: JudgeResult,
    evaluator_name: str,
) -> EvaluationCreate:
    return EvaluationCreate(
        response_id=model_response.id or 0,
        rubric_id=rubric.id or 0,
        justification=judge_result.justification,
        evaluator=evaluator_name,
        scores=[
            CriterionScoreCreate(criterion_id=score.criterion_id, score=score.score, notes="")
            for score in judge_result.scores
        ],
    )
