"""Authentication endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app import db
from app.core.config import get_settings, allowed_web_origins
from app.core import sessions
from app.services.auth import (
    EmailAlreadyRegistered,
    InactiveUser,
    InvalidCredentials,
    LoginInput,
    SignupInput,
    WeakPassword,
    login_user,
    signup_user,
    user_public_payload,
)


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

DbSession = Annotated[Session, Depends(db.get_db_session)]


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=40)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid_email")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("invalid_email")
        return normalized


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, session: DbSession):
    try:
        user = signup_user(
            session,
            SignupInput(
                email=payload.email,
                password=payload.password,
                nickname=payload.nickname,
            ),
        )
    except EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=409, detail=exc.code) from exc
    except WeakPassword as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc

    return {"user": user_public_payload(user)}


@router.post("/login")
def login(payload: LoginRequest, session: DbSession, response: Response, request: Request):
    check_origin(request)
    try:
        user = login_user(
            session,
            LoginInput(
                email=payload.email,
                password=payload.password,
            ),
        )
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail=exc.code) from exc
    except InactiveUser as exc:
        raise HTTPException(status_code=403, detail=exc.code) from exc

    try:
        tokens, refresh = sessions.issue_session(user)
    except sessions.SessionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    set_refresh_cookie(response, refresh)
    return {"user": user_public_payload(user), **tokens}


def set_refresh_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.auth_cookie_name,
        token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        max_age=7 * 86400,
        path="/api/v1/auth",
    )


def check_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin not in allowed_web_origins():
        raise HTTPException(403, "허용되지 않은 요청 출처입니다.")


@router.get("/me")
def me(user=Depends(sessions.current_user)):
    return {"user": user_public_payload(user)}


@router.post("/refresh")
def refresh(request: Request, response: Response, session: DbSession):
    check_origin(request)
    token = request.cookies.get(get_settings().auth_cookie_name)
    if not token:
        raise HTTPException(401, "다시 로그인하세요.")
    try:
        user_id, tokens, new_refresh = sessions.rotate_session(token)
        from app.models.app_user import AppUser

        user = session.get(AppUser, user_id)
        if not user or not user.is_active:
            sessions.revoke_session(new_refresh)
            raise HTTPException(401, "계정을 사용할 수 없습니다.")
    except sessions.SessionError as exc:
        raise HTTPException(401, str(exc)) from exc
    except sessions.SessionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    set_refresh_cookie(response, new_refresh)
    return {"user": user_public_payload(user), **tokens}


@router.post("/logout")
def logout(request: Request, response: Response):
    check_origin(request)
    try:
        if token := request.cookies.get(get_settings().auth_cookie_name):
            sessions.revoke_session(token)
    except sessions.SessionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    response.delete_cookie(get_settings().auth_cookie_name, path="/api/v1/auth")
    return {"logged_out": True}
