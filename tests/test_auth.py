from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from evalops_dashboard.auth import (
    LOGIN_RATE_LIMIT_MAX_ATTEMPTS,
    LOGIN_RATE_LIMIT_WINDOW,
    create_session,
    get_current_dashboard_user,
    get_current_user,
    hash_password,
)
from evalops_dashboard.database import engine
from evalops_dashboard.main import app
from evalops_dashboard.models import LoginAttempt, User

SEED_USERNAME = "demo"


@pytest.fixture(autouse=True)
def _disable_auth_override(override_auth: None) -> Generator[None]:  # noqa: ARG001
    """Cancels conftest.py's autouse dependency override so this file
    exercises the real login/logout/authentication flow instead of the
    fixed fake test user every other test file gets. Depends explicitly
    on override_auth (by fixture name, resolved by pytest, no import
    needed) so it's guaranteed to run after that fixture sets up.
    """
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_dashboard_user, None)
    yield


def create_real_user(username: str, password: str) -> None:
    with Session(engine) as session:
        user = User(username=username, password_hash=hash_password(password))
        session.add(user)
        session.commit()


def insert_login_attempt(username: str, created_at: datetime) -> None:
    with Session(engine) as session:
        session.add(LoginAttempt(username=username, created_at=created_at))
        session.commit()


def test_login_with_valid_credentials_succeeds() -> None:
    create_real_user("alice", "correct-horse-battery")

    with TestClient(app) as client:
        response = client.post(
            "/auth/login", json={"username": "alice", "password": "correct-horse-battery"}
        )

    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert body["user"]["username"] == "alice"
    set_cookie = response.headers.get("set-cookie", "")
    assert "session_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()


def test_login_with_wrong_password_returns_generic_error() -> None:
    create_real_user("bob", "correct-password")

    with TestClient(app) as client:
        response = client.post(
            "/auth/login", json={"username": "bob", "password": "wrong-password"}
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid username or password."


def test_login_with_nonexistent_username_returns_same_generic_error() -> None:
    create_real_user("carol", "correct-password")

    with TestClient(app) as client:
        wrong_password = client.post(
            "/auth/login", json={"username": "carol", "password": "wrong-password"}
        )
        nonexistent_user = client.post(
            "/auth/login", json={"username": "no-such-user", "password": "anything"}
        )

    assert wrong_password.status_code == 401
    assert nonexistent_user.status_code == 401
    assert wrong_password.json()["detail"] == nonexistent_user.json()["detail"]


def test_logout_invalidates_session() -> None:
    create_real_user("dave", "some-password")

    with TestClient(app) as client:
        login_response = client.post(
            "/auth/login", json={"username": "dave", "password": "some-password"}
        )
        token = login_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        before_logout = client.get("/prompts", headers=headers)
        client.post("/auth/logout", headers=headers)
        after_logout = client.get("/prompts", headers=headers)

    assert before_logout.status_code == 200
    assert after_logout.status_code == 401


def test_protected_api_route_without_auth_returns_401() -> None:
    with TestClient(app) as client:
        response = client.get("/prompts")

    assert response.status_code == 401


def test_protected_dashboard_route_without_auth_redirects_to_login() -> None:
    with TestClient(app) as client:
        response = client.get("/dashboard", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=/dashboard"


def test_create_user_requires_authentication() -> None:
    with TestClient(app) as client:
        response = client.post("/users", json={"username": "newbie", "password": "password123"})

    assert response.status_code == 401


def test_create_user_creates_a_user_who_can_then_log_in() -> None:
    create_real_user("existing", "existing-password")

    with TestClient(app) as client:
        login_response = client.post(
            "/auth/login", json={"username": "existing", "password": "existing-password"}
        )
        token = login_response.json()["token"]

        create_response = client.post(
            "/users",
            json={"username": "newuser", "password": "newpassword123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_response.status_code == 201
        assert "password" not in create_response.json()
        assert "password_hash" not in create_response.json()

        new_login = client.post(
            "/auth/login", json={"username": "newuser", "password": "newpassword123"}
        )

    assert new_login.status_code == 200
    assert new_login.json()["user"]["username"] == "newuser"


def test_create_user_rejects_duplicate_username() -> None:
    create_real_user("existing2", "existing-password")

    with TestClient(app) as client:
        login_response = client.post(
            "/auth/login", json={"username": "existing2", "password": "existing-password"}
        )
        token = login_response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        first = client.post(
            "/users", json={"username": "dupe", "password": "password123"}, headers=headers
        )
        second = client.post(
            "/users", json={"username": "dupe", "password": "password123"}, headers=headers
        )

    assert first.status_code == 201
    assert second.status_code == 409


def test_dashboard_login_form_success_redirects_to_dashboard() -> None:
    create_real_user(SEED_USERNAME, "form-password")

    with TestClient(app) as client:
        response = client.post(
            "/login",
            data={"username": SEED_USERNAME, "password": "form-password"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert "session_token=" in response.headers.get("set-cookie", "")


def test_dashboard_login_form_failure_rerenders_with_error() -> None:
    create_real_user("erin", "correct-password")

    with TestClient(app) as client:
        response = client.post(
            "/login",
            data={"username": "erin", "password": "wrong-password"},
            follow_redirects=False,
        )

    assert response.status_code == 401
    assert "Invalid username or password." in response.text


def test_session_token_expires() -> None:
    create_real_user("frank", "frank-password")

    with TestClient(app) as client:
        with Session(engine) as session:
            user = session.exec(select(User).where(User.username == "frank")).first()
            expired_session = create_session(user, session)
            expired_session.expires_at = datetime.now(UTC) - timedelta(days=1)
            session.add(expired_session)
            session.commit()
            token = expired_session.token

        response = client.get("/prompts", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


def test_login_blocked_after_max_failed_attempts() -> None:
    create_real_user("grace", "correct-password")

    with TestClient(app) as client:
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            response = client.post(
                "/auth/login", json={"username": "grace", "password": "wrong-password"}
            )
            assert response.status_code == 401

        blocked_response = client.post(
            "/auth/login", json={"username": "grace", "password": "correct-password"}
        )

    assert blocked_response.status_code == 429
    assert (
        blocked_response.json()["detail"]
        == "Too many failed login attempts. Please try again later."
    )


def test_login_rate_limit_resets_after_successful_login() -> None:
    create_real_user("henry", "correct-password")

    with TestClient(app) as client:
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS - 1):
            failed = client.post(
                "/auth/login", json={"username": "henry", "password": "wrong-password"}
            )
            assert failed.status_code == 401

        success_response = client.post(
            "/auth/login", json={"username": "henry", "password": "correct-password"}
        )
        assert success_response.status_code == 200

        next_failure = client.post(
            "/auth/login", json={"username": "henry", "password": "wrong-password"}
        )

    assert next_failure.status_code == 401


def test_login_rate_limit_ignores_attempts_outside_window() -> None:
    create_real_user("iris", "correct-password")
    old_timestamp = datetime.now(UTC) - LOGIN_RATE_LIMIT_WINDOW - timedelta(minutes=1)
    insert_login_attempt("iris", old_timestamp)

    with TestClient(app) as client:
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS - 1):
            failed = client.post(
                "/auth/login", json={"username": "iris", "password": "wrong-password"}
            )
            assert failed.status_code == 401

        still_allowed = client.post(
            "/auth/login", json={"username": "iris", "password": "correct-password"}
        )

    assert still_allowed.status_code == 200


def test_login_rate_limit_applies_to_nonexistent_username() -> None:
    with TestClient(app) as client:
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            response = client.post(
                "/auth/login", json={"username": "no-such-user-jones", "password": "anything"}
            )
            assert response.status_code == 401

        blocked_response = client.post(
            "/auth/login", json={"username": "no-such-user-jones", "password": "anything"}
        )

    assert blocked_response.status_code == 429


def test_dashboard_login_rate_limited_after_max_failed_attempts() -> None:
    create_real_user("jack", "correct-password")

    with TestClient(app) as client:
        for _ in range(LOGIN_RATE_LIMIT_MAX_ATTEMPTS):
            response = client.post(
                "/login",
                data={"username": "jack", "password": "wrong-password"},
                follow_redirects=False,
            )
            assert response.status_code == 401

        blocked_response = client.post(
            "/login",
            data={"username": "jack", "password": "correct-password"},
            follow_redirects=False,
        )

    assert blocked_response.status_code == 429
    assert "Too many failed login attempts" in blocked_response.text
