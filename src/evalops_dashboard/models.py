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
    score: int = Field(ge=1, le=5)
    passed: bool
    notes: str = Field(default="")
    evaluator: str = Field(default="unassigned", max_length=80)


class Evaluation(EvaluationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class EvaluationCreate(EvaluationBase):
    pass
