from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ConfigDict
from sqlmodel import Session, SQLModel, select

from evalops_dashboard.auth import (
    SESSION_LIFETIME,
    CurrentUser,
    authenticate_user,
    create_session,
    hash_password,
    invalidate_session,
    is_login_rate_limited,
    record_login_attempt_result,
    resolve_token_from_request,
)
from evalops_dashboard.database import get_session
from evalops_dashboard.models import User, UserCreate, UserRead

SessionDep = Annotated[Session, Depends(get_session)]
templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

INVALID_CREDENTIALS_DETAIL = "Invalid username or password."
RATE_LIMIT_DETAIL = "Too many failed login attempts. Please try again later."


class LoginRequest(SQLModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class LoginResponse(SQLModel):
    token: str
    user: UserRead


router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(tags=["auth"])
dashboard_auth_router = APIRouter(tags=["dashboard-auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    login_request: LoginRequest,
    response: Response,
    session: SessionDep,
) -> LoginResponse:
    if is_login_rate_limited(login_request.username, session):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=RATE_LIMIT_DETAIL,
        )

    user = authenticate_user(login_request.username, login_request.password, session)
    record_login_attempt_result(login_request.username, succeeded=user is not None, session=session)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=INVALID_CREDENTIALS_DETAIL,
        )

    auth_session = create_session(user, session)
    response.set_cookie(
        key="session_token",
        value=auth_session.token,
        httponly=True,
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return LoginResponse(
        token=auth_session.token,
        user=UserRead(id=user.id or 0, username=user.username, created_at=user.created_at),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    session: SessionDep,
    token: Annotated[str | None, Depends(resolve_token_from_request)],
) -> None:
    if token:
        invalidate_session(session, token)
    response.delete_cookie("session_token")


@users_router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_create: UserCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> UserRead:
    del current_user  # unused; the dependency's role is enforcing authentication

    existing_user = session.exec(select(User).where(User.username == user_create.username)).first()
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Username '{user_create.username}' is already taken.",
        )

    user = User(username=user_create.username, password_hash=hash_password(user_create.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserRead(id=user.id or 0, username=user.username, created_at=user.created_at)


@dashboard_auth_router.get("/login")
def login_page(request: Request, next: str = "/dashboard"):
    return templates.TemplateResponse(request, "login.html", {"error": None, "next": next})


@dashboard_auth_router.post("/login")
def login_submit(
    request: Request,
    session: SessionDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next: Annotated[str, Form()] = "/dashboard",
):
    if is_login_rate_limited(username, session):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": RATE_LIMIT_DETAIL, "next": next},
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    user = authenticate_user(username, password, session)
    record_login_attempt_result(username, succeeded=user is not None, session=session)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": INVALID_CREDENTIALS_DETAIL, "next": next},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    auth_session = create_session(user, session)
    redirect = RedirectResponse(url=next or "/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="session_token",
        value=auth_session.token,
        httponly=True,
        samesite="lax",
        max_age=int(SESSION_LIFETIME.total_seconds()),
    )
    return redirect


@dashboard_auth_router.post("/logout")
def logout_submit(
    session: SessionDep,
    token: Annotated[str | None, Depends(resolve_token_from_request)],
):
    if token:
        invalidate_session(session, token)
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie("session_token")
    return redirect
