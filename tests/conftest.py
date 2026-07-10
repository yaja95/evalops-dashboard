import os
from collections.abc import Generator

import pytest
from sqlmodel import SQLModel

EXPECTED_TEST_DATABASE_URL = "sqlite://"

# Tests deliberately override external DB config so destructive setup cannot hit real data.
os.environ["EVALOPS_DATABASE_URL"] = EXPECTED_TEST_DATABASE_URL

import evalops_dashboard.models  # noqa: F401, E402
from evalops_dashboard.database import engine  # noqa: E402

if str(engine.url) != EXPECTED_TEST_DATABASE_URL:
    raise RuntimeError(
        f"Test database engine must use in-memory SQLite; got {engine.url!s} instead."
    )


@pytest.fixture(autouse=True)
def reset_test_database() -> Generator[None]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)
