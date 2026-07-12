from evalops_dashboard.criteria_analytics import (
    CriterionScoreInput,
    build_criteria_analytics_summary,
)


def test_empty_input_produces_no_criteria() -> None:
    summary = build_criteria_analytics_summary([])

    assert summary.criteria == []


def test_single_criterion_single_model_averages_scores() -> None:
    summary = build_criteria_analytics_summary(
        [
            score("Clarity", "gpt-example-ops", 4),
            score("Clarity", "gpt-example-ops", 5),
        ]
    )

    assert len(summary.criteria) == 1
    criterion = summary.criteria[0]
    assert criterion.criterion_name == "Clarity"
    assert criterion.evaluation_count == 2
    assert criterion.average_score == 4.5
    assert len(criterion.models) == 1
    assert criterion.models[0].model_name == "gpt-example-ops"
    assert criterion.models[0].evaluation_count == 2
    assert criterion.models[0].average_score == 4.5


def test_same_criterion_name_from_different_rubrics_aggregates_together() -> None:
    """The actual cross-rubric proof: two scores against the same criterion name,
    which in practice come from two entirely different RubricCriterion rows in two
    different rubrics (name is only unique within a rubric), still combine into one
    CriterionAnalytics entry rather than two separate ones."""
    summary = build_criteria_analytics_summary(
        [
            score("Clarity", "gpt-example-ops", 4),  # from Rubric A's "Clarity" criterion
            score("Clarity", "gpt-example-ops", 2),  # from Rubric B's unrelated "Clarity" criterion
        ]
    )

    assert len(summary.criteria) == 1
    criterion = summary.criteria[0]
    assert criterion.criterion_name == "Clarity"
    assert criterion.evaluation_count == 2
    assert criterion.average_score == 3.0


def test_per_model_breakdown_within_one_criterion() -> None:
    summary = build_criteria_analytics_summary(
        [
            score("Accuracy", "model-a", 5),
            score("Accuracy", "model-a", 3),
            score("Accuracy", "model-b", 4),
        ]
    )

    criterion = summary.criteria[0]
    assert criterion.evaluation_count == 3
    assert criterion.average_score == 4.0

    assert [model.model_name for model in criterion.models] == ["model-a", "model-b"]
    assert criterion.models[0].evaluation_count == 2
    assert criterion.models[0].average_score == 4.0
    assert criterion.models[1].evaluation_count == 1
    assert criterion.models[1].average_score == 4.0


def test_criteria_sorted_alphabetically_by_name() -> None:
    summary = build_criteria_analytics_summary(
        [
            score("Zeal", "model-a", 5),
            score("Accuracy", "model-a", 4),
            score("Mood", "model-a", 3),
        ]
    )

    assert [criterion.criterion_name for criterion in summary.criteria] == [
        "Accuracy",
        "Mood",
        "Zeal",
    ]


def score(criterion_name: str, model_name: str, value: int) -> CriterionScoreInput:
    return CriterionScoreInput(criterion_name=criterion_name, model_name=model_name, score=value)
