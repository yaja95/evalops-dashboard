from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class PromptBase(SQLModel):
    title: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1)
    use_case: str = Field(default="general", max_length=80)
    owner: str = Field(default="unassigned", max_length=80)


class Prompt(PromptBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class PromptCreate(PromptBase):
    pass


class ModelResponseBase(SQLModel):
    prompt_id: int = Field(foreign_key="prompt.id")
    model_name: str = Field(min_length=1, max_length=120)
    response_text: str = Field(min_length=1)
    latency_ms: int | None = Field(default=None, ge=0)


class ModelResponse(ModelResponseBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class ModelResponseCreate(ModelResponseBase):
    pass


class EvaluationBase(SQLModel):
    response_id: int = Field(foreign_key="modelresponse.id")
    rubric_name: str = Field(min_length=1, max_length=120)
    instruction_following_score: int = Field(ge=1, le=5)
    truthfulness_score: int = Field(ge=1, le=5)
    completeness_score: int = Field(ge=1, le=5)
    conciseness_score: int = Field(ge=1, le=5)
    safety_score: int = Field(ge=1, le=5)
    writing_style_score: int = Field(ge=1, le=5)
    overall_score: int = Field(ge=1, le=5)
    failure_category: str | None = Field(default=None, max_length=120)
    justification: str = Field(min_length=1)
    evaluator: str = Field(default="unassigned", max_length=80)


class Evaluation(EvaluationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationCreate(EvaluationBase):
    pass


class AnalyticsSummary(SQLModel):
    prompt_count: int
    response_count: int
    evaluation_count: int
    average_overall_score: float | None
    average_truthfulness_score: float | None
    most_common_failure_category: str | None
    pass_rate: float
