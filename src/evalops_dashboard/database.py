import os
from collections.abc import Generator

from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

DATABASE_URL = os.getenv("EVALOPS_DATABASE_URL", "sqlite:///./evalops.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
pool_args = {"poolclass": StaticPool} if DATABASE_URL == "sqlite://" else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, **pool_args)

REQUIRED_EVALUATION_COLUMNS = {
    "instruction_following_score",
    "truthfulness_score",
    "completeness_score",
    "conciseness_score",
    "safety_score",
    "writing_style_score",
    "overall_score",
    "failure_category",
    "justification",
}


def reset_legacy_sqlite_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "evaluation" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("evaluation")}
    if REQUIRED_EVALUATION_COLUMNS.issubset(existing_columns):
        return

    SQLModel.metadata.drop_all(engine)


def create_db_and_tables() -> None:
    reset_legacy_sqlite_schema()
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session]:
    with Session(engine) as session:
        yield session
