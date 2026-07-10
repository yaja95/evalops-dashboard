import os
from collections.abc import Generator

import pytest
from sqlmodel import SQLModel

os.environ.setdefault("EVALOPS_DATABASE_URL", "sqlite://")

import evalops_dashboard.models  # noqa: F401, E402
from evalops_dashboard.database import engine  # noqa: E402


@pytest.fixture(autouse=True)
def reset_test_database() -> Generator[None]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)
