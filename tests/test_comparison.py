from datetime import UTC, datetime, timedelta

import pytest

from evalops_dashboard.comparison import (
    ComparisonCriterion,
    ComparisonCriterionScore,
    ComparisonDataError,
    ComparisonEvaluation,
    ComparisonResponse,
    build_comparison_summary,
)

BASE_TIME = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def test_higher_average_score_ranks_first() -> None:
    summary = build_comparison_summary(
        responses=[response(1, latency_ms=200), response(2, latency_ms=100)],
        evaluations=[
            evaluation(1, response_id=1, overall_score=4.5, passed=True),
            evaluation(2, response_id=2, overall_score=4.0, passed=True),
        ],
        criteria=[criterion(1)],
        criterion_scores=[score(1, 1, 5), score(2, 1, 4)],
    )

    assert [result.response_id for result in summary.results] == [1, 2]
    assert summary.winner_response_id == 1


def test_raw_average_score_ranks_before_displayed_average_tie_breakers() -> None:
    summary = build_comparison_summary(
        responses=[response(1, latency_ms=10), response(2, latency_ms=999)],
        evaluations=[
            evaluation(1, response_id=1, overall_score=4.00),
            evaluation(2, response_id=1, overall_score=4.01),
            evaluation(3, response_id=1, overall_score=4.01),
            evaluation(4, response_id=2, overall_score=4.01),
        ],
        criteria=[criterion(1)],
        criterion_scores=[
            score(1, 1, 4),
            score(2, 1, 4),
            score(3, 1, 4),
            score(4, 1, 4),
        ],
    )

    assert [result.average_overall_score for result in summary.results] == [4.01, 4.01]
    assert [result.response_id for result in summary.results] == [2, 1]


def test_pass_rate_breaks_average_score_tie() -> None:
    summary = build_comparison_summary(
        responses=[response(1), response(2)],
        evaluations=[
            evaluation(1, response_id=1, overall_score=4, passed=False),
            evaluation(2, response_id=2, overall_score=4, passed=True),
        ],
        criteria=[criterion(1)],
        criterion_scores=[score(1, 1, 4), score(2, 1, 4)],
    )

    assert [result.response_id for result in summary.results] == [2, 1]


def test_raw_pass_rate_ranks_before_displayed_pass_rate_tie_breakers() -> None:
    lower_raw_rate_evaluations = [
        evaluation(index, response_id=1, passed=index <= 2) for index in range(1, 8)
    ]
    higher_raw_rate_evaluations = [
        evaluation(index, response_id=2, passed=index <= 12) for index in range(8, 25)
    ]
    all_evaluations = lower_raw_rate_evaluations + higher_raw_rate_evaluations

    summary = build_comparison_summary(
        responses=[response(1, latency_ms=10), response(2, latency_ms=999)],
        evaluations=all_evaluations,
        criteria=[criterion(1)],
        criterion_scores=[
            score(comparison_evaluation.id, 1, 4) for comparison_evaluation in all_evaluations
        ],
    )

    assert [result.pass_rate for result in summary.results] == [0.29, 0.29]
    assert [result.response_id for result in summary.results] == [2, 1]


def test_latency_and_response_id_break_remaining_ties() -> None:
    summary = build_comparison_summary(
        responses=[
            response(3, latency_ms=None),
            response(2, latency_ms=100),
            response(1, latency_ms=100),
            response(4, latency_ms=200),
        ],
        evaluations=[
            evaluation(3, response_id=3),
            evaluation(2, response_id=2),
            evaluation(1, response_id=1),
            evaluation(4, response_id=4),
        ],
        criteria=[criterion(1)],
        criterion_scores=[
            score(3, 1, 4),
            score(2, 1, 4),
            score(1, 1, 4),
            score(4, 1, 4),
        ],
    )

    assert [result.response_id for result in summary.results] == [1, 2, 4, 3]
    assert [result.rank for result in summary.results] == [1, 2, 3, 4]


def test_unscored_response_ids_are_sorted_by_response_id() -> None:
    summary = build_comparison_summary(
        responses=[response(3), response(1), response(2)],
        evaluations=[evaluation(1, response_id=2)],
        criteria=[criterion(1)],
        criterion_scores=[score(1, 1, 4)],
    )

    assert summary.unscored_response_ids == [1, 3]


def test_multiple_evaluations_and_criterion_averages_are_aggregated() -> None:
    summary = build_comparison_summary(
        responses=[response(1)],
        evaluations=[
            evaluation(1, response_id=1, overall_score=5, passed=True),
            evaluation(2, response_id=1, overall_score=4, passed=False, created_at_offset=5),
        ],
        criteria=[criterion(2, name="Clarity"), criterion(1, name="Accuracy")],
        criterion_scores=[
            score(1, 2, 5),
            score(1, 1, 4),
            score(2, 2, 3),
            score(2, 1, 4),
        ],
    )

    result = summary.results[0]
    assert result.evaluation_count == 2
    assert result.average_overall_score == 4.5
    assert result.pass_rate == 0.5
    assert result.latest_evaluated_at == BASE_TIME + timedelta(minutes=5)
    assert [average.criterion_id for average in result.criterion_averages] == [1, 2]
    assert [average.average_score for average in result.criterion_averages] == [4.0, 4.0]


def test_missing_criterion_score_raises_data_error() -> None:
    with pytest.raises(ComparisonDataError):
        build_comparison_summary(
            responses=[response(1)],
            evaluations=[evaluation(1, response_id=1)],
            criteria=[criterion(1), criterion(2)],
            criterion_scores=[score(1, 1, 4)],
        )


def response(response_id: int, latency_ms: int | None = 100) -> ComparisonResponse:
    return ComparisonResponse(
        id=response_id,
        model_name=f"model-{response_id}",
        response_text=f"Response {response_id}",
        latency_ms=latency_ms,
    )


def evaluation(
    evaluation_id: int,
    response_id: int,
    overall_score: float = 4,
    passed: bool = True,
    created_at_offset: int = 0,
) -> ComparisonEvaluation:
    return ComparisonEvaluation(
        id=evaluation_id,
        response_id=response_id,
        overall_score=overall_score,
        passed=passed,
        created_at=BASE_TIME + timedelta(minutes=created_at_offset),
    )


def criterion(criterion_id: int, name: str | None = None) -> ComparisonCriterion:
    return ComparisonCriterion(
        id=criterion_id,
        name=name or f"Criterion {criterion_id}",
        weight=1,
        required=True,
    )


def score(
    evaluation_id: int,
    criterion_id: int,
    score_value: int,
) -> ComparisonCriterionScore:
    return ComparisonCriterionScore(
        evaluation_id=evaluation_id,
        criterion_id=criterion_id,
        score=score_value,
    )
