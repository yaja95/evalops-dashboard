from evalops_dashboard.scoring import ScoredCriterion, calculate_scoring_result


def test_weighted_score_calculation() -> None:
    result = calculate_scoring_result(
        [
            ScoredCriterion(score=5, weight=2, required=True),
            ScoredCriterion(score=4, weight=1, required=True),
        ],
        pass_threshold=4,
    )

    assert result.overall_score == 4.67
    assert result.passed is True


def test_required_criterion_can_cause_failure_despite_passing_average() -> None:
    result = calculate_scoring_result(
        [
            ScoredCriterion(score=3, weight=1, required=True),
            ScoredCriterion(score=5, weight=10, required=False),
        ],
        pass_threshold=4,
    )

    assert result.overall_score == 4.82
    assert result.passed is False


def test_low_non_required_criterion_can_still_pass() -> None:
    result = calculate_scoring_result(
        [
            ScoredCriterion(score=5, weight=10, required=True),
            ScoredCriterion(score=1, weight=1, required=False),
        ],
        pass_threshold=4,
    )

    assert result.overall_score == 4.64
    assert result.passed is True
