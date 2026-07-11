import os
from collections.abc import Generator

import pytest
from sqlmodel import SQLModel

EXPECTED_TEST_DATABASE_URL = "sqlite://"

# Tests deliberately override external DB config so destructive setup cannot hit real data.
os.environ["EVALOPS_DATABASE_URL"] = EXPECTED_TEST_DATABASE_URL

import evalops_dashboard.models  # noqa: F401, E402
from evalops_dashboard.auth import get_current_dashboard_user, get_current_user  # noqa: E402
from evalops_dashboard.database import engine  # noqa: E402
from evalops_dashboard.main import app  # noqa: E402
from evalops_dashboard.models import User  # noqa: E402

if str(engine.url) != EXPECTED_TEST_DATABASE_URL:
    raise RuntimeError(
        f"Test database engine must use in-memory SQLite; got {engine.url!s} instead."
    )

TEST_USER_ID = 1
TEST_USERNAME = "test-user"


@pytest.fixture(autouse=True)
def reset_test_database() -> Generator[None]:
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    SQLModel.metadata.drop_all(engine)


def _fake_current_user() -> User:
    return User(id=TEST_USER_ID, username=TEST_USERNAME, password_hash="unused")


@pytest.fixture(autouse=True)
def override_auth() -> Generator[None]:
    """Injects a fixed fake user for every test so the other ~121 existing
    tests need no individual changes. tests/test_auth.py disables this to
    exercise the real login/logout/authentication flow.
    """
    app.dependency_overrides[get_current_user] = _fake_current_user
    app.dependency_overrides[get_current_dashboard_user] = _fake_current_user
    yield
    app.dependency_overrides.clear()
