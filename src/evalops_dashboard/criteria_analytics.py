from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CriterionScoreInput:
    criterion_name: str
    model_name: str
    score: int


@dataclass(frozen=True)
class ModelCriterionAverage:
    model_name: str
    evaluation_count: int
    average_score: float


@dataclass(frozen=True)
class CriterionAnalytics:
    criterion_name: str
    evaluation_count: int
    average_score: float
    models: list[ModelCriterionAverage]


@dataclass(frozen=True)
class CriteriaAnalyticsSummary:
    criteria: list[CriterionAnalytics]


def build_criteria_analytics_summary(
    scores: Sequence[CriterionScoreInput],
) -> CriteriaAnalyticsSummary:
    scores_by_criterion_name: dict[str, list[CriterionScoreInput]] = {}
    for score in scores:
        scores_by_criterion_name.setdefault(score.criterion_name, []).append(score)

    criteria = [
        build_criterion_analytics(criterion_name, criterion_scores)
        for criterion_name, criterion_scores in scores_by_criterion_name.items()
    ]
    criteria.sort(key=lambda criterion: criterion.criterion_name)

    return CriteriaAnalyticsSummary(criteria=criteria)


def build_criterion_analytics(
    criterion_name: str, scores: Sequence[CriterionScoreInput]
) -> CriterionAnalytics:
    scores_by_model_name: dict[str, list[int]] = {}
    for score in scores:
        scores_by_model_name.setdefault(score.model_name, []).append(score.score)

    models = [
        ModelCriterionAverage(
            model_name=model_name,
            evaluation_count=len(model_scores),
            average_score=round(sum(model_scores) / len(model_scores), 2),
        )
        for model_name, model_scores in scores_by_model_name.items()
    ]
    models.sort(key=lambda model: model.model_name)

    all_scores = [score.score for score in scores]
    return CriterionAnalytics(
        criterion_name=criterion_name,
        evaluation_count=len(all_scores),
        average_score=round(sum(all_scores) / len(all_scores), 2),
        models=models,
    )
