from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_expected_tables(
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
        "rubric",
        "rubriccriterion",
    }
    assert expected_tables.issubset(first_table_names)
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
    assert_unique_constraint_exists(database_url, "rubric", {"name", "version"})
    assert_unique_constraint_exists(
        database_url,
        "rubriccriterion",
        {"rubric_id", "name"},
    )

    command.upgrade(config, "head")
    second_table_names = get_table_names(database_url)

    assert second_table_names == first_table_names


def get_table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


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
