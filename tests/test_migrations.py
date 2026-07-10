from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_head_creates_expected_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "migration_smoke.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("EVALOPS_DATABASE_URL", database_url)

    config = Config("alembic.ini")

    command.upgrade(config, "head")
    first_table_names = get_table_names(database_url)

    expected_tables = {
        "alembic_version",
        "prompt",
        "modelresponse",
        "evaluation",
        "criterionscore",
        "rubric",
        "rubriccriterion",
    }
    assert expected_tables.issubset(first_table_names)
    assert_columns_include(
        database_url,
        "evaluation",
        {
            "id",
            "response_id",
            "rubric_id",
            "overall_score",
            "passed",
            "justification",
            "evaluator",
            "created_at",
        },
    )
    assert_columns_include(
        database_url,
        "criterionscore",
        {"id", "evaluation_id", "criterion_id", "score", "notes"},
    )
    assert_foreign_key_exists(
        database_url,
        table_name="modelresponse",
        constrained_column="prompt_id",
        referred_table="prompt",
        referred_column="id",
    )
    assert_foreign_key_exists(
        database_url,
        table_name="rubriccriterion",
        constrained_column="rubric_id",
        referred_table="rubric",
        referred_column="id",
    )
    assert_foreign_key_exists(
        database_url,
        table_name="evaluation",
        constrained_column="response_id",
        referred_table="modelresponse",
        referred_column="id",
    )
    assert_foreign_key_exists(
        database_url,
        table_name="evaluation",
        constrained_column="rubric_id",
        referred_table="rubric",
        referred_column="id",
    )
    assert_foreign_key_exists(
        database_url,
        table_name="criterionscore",
        constrained_column="evaluation_id",
        referred_table="evaluation",
        referred_column="id",
    )
    assert_foreign_key_exists(
        database_url,
        table_name="criterionscore",
        constrained_column="criterion_id",
        referred_table="rubriccriterion",
        referred_column="id",
    )
    assert_unique_constraint_exists(database_url, "rubric", {"name", "version"})
    assert_unique_constraint_exists(
        database_url,
        "rubriccriterion",
        {"rubric_id", "name"},
    )
    assert_unique_constraint_exists(
        database_url,
        "criterionscore",
        {"evaluation_id", "criterion_id"},
    )
    assert_index_exists(database_url, "evaluation", {"response_id"})
    assert_index_exists(database_url, "evaluation", {"rubric_id"})
    assert_index_exists(database_url, "criterionscore", {"evaluation_id"})
    assert_index_exists(database_url, "criterionscore", {"criterion_id"})

    command.upgrade(config, "head")
    second_table_names = get_table_names(database_url)

    assert second_table_names == first_table_names


def test_baseline_to_head_migration_preserves_configuration_and_resets_evaluations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "baseline_to_head.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("EVALOPS_DATABASE_URL", database_url)

    config = Config("alembic.ini")
    command.upgrade(config, "20260710_0001")
    insert_baseline_records(database_url)

    command.upgrade(config, "head")

    assert count_rows(database_url, "prompt") == 1
    assert count_rows(database_url, "modelresponse") == 1
    assert count_rows(database_url, "rubric") == 1
    assert count_rows(database_url, "rubriccriterion") == 1
    assert count_rows(database_url, "evaluation") == 0
    assert "criterionscore" in get_table_names(database_url)
    assert_columns_include(
        database_url,
        "evaluation",
        {"id", "response_id", "rubric_id", "overall_score", "passed"},
    )


def insert_baseline_records(database_url: str) -> None:
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO prompt (id, title, content, use_case, owner, created_at)
                    VALUES (1, 'Prompt', 'Content', 'testing', 'tests', '2026-07-10')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO modelresponse
                    (id, prompt_id, model_name, response_text, latency_ms, created_at)
                    VALUES (1, 1, 'model', 'response', 100, '2026-07-10')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO rubric
                    (id, name, version, description, pass_threshold, created_at)
                    VALUES (1, 'Rubric', 1, 'Description', 4, '2026-07-10')
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO rubriccriterion
                    (id, rubric_id, name, description, weight, min_score, max_score, required)
                    VALUES (1, 1, 'Criterion', 'Description', 1.0, 1, 5, 1)
                    """
                )
            )
            connection.execute(
                text(
                    """
                    INSERT INTO evaluation
                    (
                        id,
                        response_id,
                        rubric_name,
                        instruction_following_score,
                        truthfulness_score,
                        completeness_score,
                        conciseness_score,
                        safety_score,
                        writing_style_score,
                        overall_score,
                        failure_category,
                        justification,
                        evaluator,
                        created_at
                    )
                    VALUES (
                        1, 1, 'Rubric v1', 4, 4, 4, 4, 4, 4, 4,
                        NULL, 'Ok', 'tests', '2026-07-10'
                    )
                    """
                )
            )
    finally:
        engine.dispose()


def get_table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def count_rows(database_url: str, table_name: str) -> int:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            return connection.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    finally:
        engine.dispose()


def assert_columns_include(
    database_url: str,
    table_name: str,
    column_names: set[str],
) -> None:
    engine = create_engine(database_url)
    try:
        columns = inspect(engine).get_columns(table_name)
    finally:
        engine.dispose()

    assert column_names.issubset({column["name"] for column in columns})


def assert_foreign_key_exists(
    database_url: str,
    table_name: str,
    constrained_column: str,
    referred_table: str,
    referred_column: str,
) -> None:
    engine = create_engine(database_url)
    try:
        foreign_keys = inspect(engine).get_foreign_keys(table_name)
    finally:
        engine.dispose()

    assert any(
        constrained_column in foreign_key["constrained_columns"]
        and foreign_key["referred_table"] == referred_table
        and referred_column in foreign_key["referred_columns"]
        for foreign_key in foreign_keys
    )


def assert_unique_constraint_exists(
    database_url: str,
    table_name: str,
    column_names: set[str],
) -> None:
    engine = create_engine(database_url)
    try:
        unique_constraints = inspect(engine).get_unique_constraints(table_name)
    finally:
        engine.dispose()

    assert any(
        set(unique_constraint["column_names"]) == column_names
        for unique_constraint in unique_constraints
    )


def assert_index_exists(
    database_url: str,
    table_name: str,
    column_names: set[str],
) -> None:
    engine = create_engine(database_url)
    try:
        indexes = inspect(engine).get_indexes(table_name)
    finally:
        engine.dispose()

    assert any(set(index["column_names"]) == column_names for index in indexes)
