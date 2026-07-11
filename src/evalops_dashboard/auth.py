import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import bcrypt
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlmodel import Session, select

from evalops_dashboard.database import get_session
from evalops_dashboard.models import AuthSession, User

SESSION_TOKEN_BYTES = 32
SESSION_LIFETIME = timedelta(days=7)

SessionDep = Annotated[Session, Depends(get_session)]


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))


def generate_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def create_session(user: User, session: Session) -> AuthSession:
    now = datetime.now(UTC)
    auth_session = AuthSession(
        user_id=user.id or 0,
        token=generate_session_token(),
        created_at=now,
        expires_at=now + SESSION_LIFETIME,
    )
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    return auth_session


def authenticate_user(username: str, password: str, session: Session) -> User | None:
    """Returns the matching user if username/password are valid, else None.

    Deliberately does not distinguish "no such user" from "wrong password" —
    callers must surface one generic error message to avoid username enumeration.
    """
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def resolve_session_token(session: Session, token: str) -> User | None:
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is None:
        return None
    # SQLite drops tzinfo on datetime round-trip, so a value just read back
    # from the DB is naive even though it was stored as an aware UTC instant
    # (see create_session). Re-attach UTC before comparing against "now".
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < datetime.now(UTC):
        return None
    return session.get(User, auth_session.user_id)


def invalidate_session(session: Session, token: str) -> None:
    auth_session = session.exec(select(AuthSession).where(AuthSession.token == token)).first()
    if auth_session is not None:
        session.delete(auth_session)
        session.commit()


class DashboardAuthRequired(Exception):
    def __init__(self, next_path: str) -> None:
        self.next_path = next_path


def resolve_token_from_request(
    session_token: Annotated[str | None, Cookie()] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> str | None:
    if session_token:
        return session_token
    if authorization and authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ")
    return None


def get_current_user(
    session: SessionDep,
    token: Annotated[str | None, Depends(resolve_token_from_request)],
) -> User:
    user = resolve_session_token(session, token) if token else None
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing authentication credentials.",
        )
    return user


def get_current_dashboard_user(
    request: Request,
    session: SessionDep,
    token: Annotated[str | None, Depends(resolve_token_from_request)],
) -> User:
    user = resolve_session_token(session, token) if token else None
    if user is None:
        raise DashboardAuthRequired(next_path=request.url.path)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentDashboardUser = Annotated[User, Depends(get_current_dashboard_user)]
