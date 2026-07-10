from datetime import UTC, datetime

from pydantic import field_validator, model_validator
from sqlalchemy import UniqueConstraint
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


class RubricBase(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    description: str = Field(default="")
    pass_threshold: int = Field(ge=1, le=5)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Name must not be empty.")
        return stripped_value


class Rubric(RubricBase, table=True):
    __table_args__ = (UniqueConstraint("name", "version"),)

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class RubricCriterionBase(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="")
    weight: float = Field(gt=0)
    min_score: int = Field(ge=1, le=5)
    max_score: int = Field(ge=1, le=5)
    required: bool = True

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Name must not be empty.")
        return stripped_value

    @model_validator(mode="after")
    def min_score_must_be_less_than_max_score(self) -> RubricCriterionBase:
        if self.min_score >= self.max_score:
            raise ValueError("min_score must be less than max_score.")
        return self


class RubricCriterion(RubricCriterionBase, table=True):
    __table_args__ = (UniqueConstraint("rubric_id", "name"),)

    id: int | None = Field(default=None, primary_key=True)
    rubric_id: int = Field(foreign_key="rubric.id")


class RubricCriterionCreate(RubricCriterionBase):
    pass


class RubricCreate(RubricBase):
    criteria: list[RubricCriterionCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def criterion_names_must_be_unique(self) -> RubricCreate:
        normalized_names = [criterion.name.casefold() for criterion in self.criteria]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Criterion names must be unique within a rubric.")
        return self


class RubricCriterionRead(RubricCriterionBase):
    id: int
    rubric_id: int


class RubricRead(RubricBase):
    id: int
    created_at: datetime
    criteria: list[RubricCriterionRead]
