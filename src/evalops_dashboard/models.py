from datetime import UTC, datetime

from pydantic import ConfigDict, field_validator, model_validator
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


class UserBase(SQLModel):
    username: str = Field(min_length=1, max_length=80)


class User(UserBase, table=True):
    __table_args__ = (UniqueConstraint("username"),)

    id: int | None = Field(default=None, primary_key=True)
    password_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class UserCreate(UserBase):
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8)


class UserRead(UserBase):
    id: int
    created_at: datetime


class AuthSession(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("token"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    token: str = Field(index=True)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime


class ModelResponseBase(SQLModel):
    prompt_id: int = Field(foreign_key="prompt.id")
    model_name: str = Field(min_length=1, max_length=120)
    response_text: str = Field(min_length=1)
    latency_ms: int | None = Field(default=None, ge=0)
    provider: str | None = Field(default=None, max_length=120)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ModelResponse(ModelResponseBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)
    cost_usd: float | None = Field(default=None)


class ModelResponseCreate(ModelResponseBase):
    model_config = ConfigDict(extra="forbid")


class ModelPricingBase(SQLModel):
    provider: str = Field(min_length=1, max_length=120)
    model_name: str = Field(min_length=1, max_length=120)
    input_price_per_1k_tokens: float = Field(ge=0)
    output_price_per_1k_tokens: float = Field(ge=0)


class ModelPricing(ModelPricingBase, table=True):
    __table_args__ = (UniqueConstraint("provider", "model_name"),)

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class ModelPricingCreate(ModelPricingBase):
    model_config = ConfigDict(extra="forbid")


class ModelPricingRead(ModelPricingBase):
    id: int
    created_at: datetime


class EvaluationBase(SQLModel):
    response_id: int = Field(foreign_key="modelresponse.id", index=True)
    rubric_id: int = Field(foreign_key="rubric.id", index=True)
    overall_score: float
    passed: bool
    justification: str = Field(min_length=1)
    evaluator: str = Field(default="unassigned", max_length=80)

    @field_validator("justification", "evaluator")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Value must not be empty.")
        return stripped_value


class Evaluation(EvaluationBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utc_now)


class CriterionScoreBase(SQLModel):
    evaluation_id: int = Field(foreign_key="evaluation.id", index=True)
    criterion_id: int = Field(foreign_key="rubriccriterion.id", index=True)
    score: int
    notes: str = Field(default="")


class CriterionScore(CriterionScoreBase, table=True):
    __table_args__ = (UniqueConstraint("evaluation_id", "criterion_id"),)

    id: int | None = Field(default=None, primary_key=True)


class CriterionScoreCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    criterion_id: int
    score: int
    notes: str = Field(default="")


class EvaluationCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    rubric_id: int
    justification: str = Field(min_length=1)
    evaluator: str = Field(min_length=1, max_length=80)
    scores: list[CriterionScoreCreate] = Field(min_length=1)

    @field_validator("justification", "evaluator")
    @classmethod
    def value_must_not_be_blank(cls, value: str) -> str:
        stripped_value = value.strip()
        if not stripped_value:
            raise ValueError("Value must not be empty.")
        return stripped_value

    @model_validator(mode="after")
    def criterion_ids_must_be_unique(self) -> EvaluationCreate:
        criterion_ids = [score.criterion_id for score in self.scores]
        if len(criterion_ids) != len(set(criterion_ids)):
            raise ValueError("Each criterion may be scored only once.")
        return self


class AutoEvaluationCreate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    response_id: int
    rubric_id: int


class CriterionScoreRead(SQLModel):
    criterion_id: int
    criterion_name: str
    score: int
    weight: float
    required: bool
    notes: str


class EvaluationRead(SQLModel):
    id: int
    response_id: int
    rubric_id: int
    rubric_name: str
    rubric_version: int
    overall_score: float
    passed: bool
    justification: str
    evaluator: str
    created_at: datetime
    scores: list[CriterionScoreRead]


class ImportRowError(SQLModel):
    row: int
    detail: str


class ImportSummary(SQLModel):
    created_count: int
    errors: list[ImportRowError]


class AnalyticsSummary(SQLModel):
    prompt_count: int
    response_count: int
    evaluation_count: int
    average_overall_score: float | None
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
    def rubric_configuration_must_be_valid(self) -> RubricCreate:
        normalized_names = [criterion.name.casefold() for criterion in self.criteria]
        if len(normalized_names) != len(set(normalized_names)):
            raise ValueError("Criterion names must be unique within a rubric.")
        invalid_required_criteria = [
            criterion.name
            for criterion in self.criteria
            if criterion.required and criterion.max_score < self.pass_threshold
        ]
        if invalid_required_criteria:
            raise ValueError(
                "Required criteria must be able to meet the rubric pass threshold: "
                + ", ".join(invalid_required_criteria)
            )
        return self


class RubricCriterionRead(RubricCriterionBase):
    id: int
    rubric_id: int


class RubricRead(RubricBase):
    id: int
    created_at: datetime
    criteria: list[RubricCriterionRead]


class ComparisonRubricSummary(SQLModel):
    id: int
    name: str
    version: int
    pass_threshold: int


class ComparisonCriterionAverage(SQLModel):
    criterion_id: int
    criterion_name: str
    weight: float
    required: bool
    average_score: float


class ComparisonResponseResult(SQLModel):
    rank: int
    response_id: int
    model_name: str
    response_text: str
    latency_ms: int | None
    evaluation_count: int
    average_overall_score: float
    pass_rate: float
    latest_evaluated_at: datetime
    criterion_averages: list[ComparisonCriterionAverage]


class PromptComparisonRead(SQLModel):
    prompt_id: int
    prompt_title: str
    prompt_use_case: str
    rubric: ComparisonRubricSummary
    response_count: int
    compared_response_count: int
    comparison_ready: bool
    winner_response_id: int | None
    unscored_response_ids: list[int]
    results: list[ComparisonResponseResult]
