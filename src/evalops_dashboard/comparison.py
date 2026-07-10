from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


class ComparisonDataError(ValueError):
    pass


@dataclass(frozen=True)
class ComparisonResponse:
    id: int
    model_name: str
    response_text: str
    latency_ms: int | None


@dataclass(frozen=True)
class ComparisonEvaluation:
    id: int
    response_id: int
    overall_score: float
    passed: bool
    created_at: datetime


@dataclass(frozen=True)
class ComparisonCriterion:
    id: int
    name: str
    weight: float
    required: bool


@dataclass(frozen=True)
class ComparisonCriterionScore:
    evaluation_id: int
    criterion_id: int
    score: int


@dataclass(frozen=True)
class CriterionAverage:
    criterion_id: int
    criterion_name: str
    weight: float
    required: bool
    average_score: float


@dataclass(frozen=True)
class ResponseComparison:
    rank: int
    response_id: int
    model_name: str
    response_text: str
    latency_ms: int | None
    evaluation_count: int
    average_overall_score: float
    pass_rate: float
    latest_evaluated_at: datetime
    criterion_averages: list[CriterionAverage]


@dataclass(frozen=True)
class ComparisonSummary:
    response_count: int
    compared_response_count: int
    comparison_ready: bool
    winner_response_id: int | None
    unscored_response_ids: list[int]
    results: list[ResponseComparison]


def build_comparison_summary(
    responses: Sequence[ComparisonResponse],
    evaluations: Sequence[ComparisonEvaluation],
    criteria: Sequence[ComparisonCriterion],
    criterion_scores: Sequence[ComparisonCriterionScore],
) -> ComparisonSummary:
    criteria_by_id = {criterion.id: criterion for criterion in criteria}
    expected_criterion_ids = set(criteria_by_id)
    evaluation_ids = {evaluation.id for evaluation in evaluations}
    evaluations_by_response_id: dict[int, list[ComparisonEvaluation]] = {}
    scores_by_evaluation_id: dict[int, list[ComparisonCriterionScore]] = {}

    for evaluation in evaluations:
        evaluations_by_response_id.setdefault(evaluation.response_id, []).append(evaluation)

    for criterion_score in criterion_scores:
        if criterion_score.evaluation_id not in evaluation_ids:
            raise ComparisonDataError(
                f"Criterion score {criterion_score.criterion_id} belongs to an excluded evaluation."
            )
        if criterion_score.criterion_id not in expected_criterion_ids:
            raise ComparisonDataError(
                f"Criterion score references unknown criterion {criterion_score.criterion_id}."
            )
        scores_by_evaluation_id.setdefault(criterion_score.evaluation_id, []).append(
            criterion_score
        )

    for evaluation in evaluations:
        actual_criterion_ids = {
            criterion_score.criterion_id
            for criterion_score in scores_by_evaluation_id.get(evaluation.id, [])
        }
        if actual_criterion_ids != expected_criterion_ids:
            raise ComparisonDataError(
                f"Evaluation {evaluation.id} does not have scores for every rubric criterion."
            )

    response_comparisons = [
        build_response_comparison(
            response=response,
            evaluations=evaluations_by_response_id[response.id],
            criteria=list(criteria),
            scores_by_evaluation_id=scores_by_evaluation_id,
        )
        for response in responses
        if response.id in evaluations_by_response_id
    ]
    ranked_results = assign_ranks(response_comparisons)
    compared_response_ids = {result.response_id for result in ranked_results}
    unscored_response_ids = [
        response.id for response in responses if response.id not in compared_response_ids
    ]
    comparison_ready = len(ranked_results) >= 2

    return ComparisonSummary(
        response_count=len(responses),
        compared_response_count=len(ranked_results),
        comparison_ready=comparison_ready,
        winner_response_id=ranked_results[0].response_id if comparison_ready else None,
        unscored_response_ids=unscored_response_ids,
        results=ranked_results,
    )


def build_response_comparison(
    response: ComparisonResponse,
    evaluations: Sequence[ComparisonEvaluation],
    criteria: Sequence[ComparisonCriterion],
    scores_by_evaluation_id: dict[int, list[ComparisonCriterionScore]],
) -> ResponseComparison:
    evaluation_count = len(evaluations)
    criterion_averages = []

    for criterion in sorted(criteria, key=lambda item: item.id):
        scores = [
            criterion_score.score
            for evaluation in evaluations
            for criterion_score in scores_by_evaluation_id[evaluation.id]
            if criterion_score.criterion_id == criterion.id
        ]
        if len(scores) != evaluation_count:
            raise ComparisonDataError(
                f"Response {response.id} has inconsistent scores for criterion {criterion.id}."
            )
        criterion_averages.append(
            CriterionAverage(
                criterion_id=criterion.id,
                criterion_name=criterion.name,
                weight=criterion.weight,
                required=criterion.required,
                average_score=round(sum(scores) / len(scores), 2),
            )
        )

    return ResponseComparison(
        rank=0,
        response_id=response.id,
        model_name=response.model_name,
        response_text=response.response_text,
        latency_ms=response.latency_ms,
        evaluation_count=evaluation_count,
        average_overall_score=round(
            sum(evaluation.overall_score for evaluation in evaluations) / evaluation_count,
            2,
        ),
        pass_rate=round(
            len([evaluation for evaluation in evaluations if evaluation.passed]) / evaluation_count,
            2,
        ),
        latest_evaluated_at=max(evaluation.created_at for evaluation in evaluations),
        criterion_averages=criterion_averages,
    )


def assign_ranks(results: Sequence[ResponseComparison]) -> list[ResponseComparison]:
    sorted_results = sorted(
        results,
        key=lambda result: (
            -result.average_overall_score,
            -result.pass_rate,
            result.latency_ms is None,
            result.latency_ms if result.latency_ms is not None else 0,
            result.response_id,
        ),
    )
    return [
        ResponseComparison(
            rank=index,
            response_id=result.response_id,
            model_name=result.model_name,
            response_text=result.response_text,
            latency_ms=result.latency_ms,
            evaluation_count=result.evaluation_count,
            average_overall_score=result.average_overall_score,
            pass_rate=result.pass_rate,
            latest_evaluated_at=result.latest_evaluated_at,
            criterion_averages=result.criterion_averages,
        )
        for index, result in enumerate(sorted_results, start=1)
    ]
