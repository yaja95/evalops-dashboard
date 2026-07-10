from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoredCriterion:
    score: int
    weight: float
    required: bool


@dataclass(frozen=True)
class ScoringResult:
    overall_score: float
    passed: bool


def calculate_scoring_result(
    scored_criteria: Sequence[ScoredCriterion],
    pass_threshold: int,
) -> ScoringResult:
    total_weight = sum(criterion.weight for criterion in scored_criteria)
    if total_weight <= 0:
        raise ValueError("Total criterion weight must be greater than zero.")

    raw_weighted_score = (
        sum(criterion.score * criterion.weight for criterion in scored_criteria) / total_weight
    )
    overall_score = round(raw_weighted_score, 2)
    required_criteria_passed = all(
        criterion.score >= pass_threshold for criterion in scored_criteria if criterion.required
    )

    return ScoringResult(
        overall_score=overall_score,
        passed=raw_weighted_score >= pass_threshold and required_criteria_passed,
    )
