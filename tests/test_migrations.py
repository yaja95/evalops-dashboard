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

    command.upgrade(config, "head")
    second_table_names = get_table_names(database_url)

    assert second_table_names == first_table_names


def get_table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
