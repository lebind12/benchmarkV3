"""관리자 인증 HTTP 경계.

쿠키는 HttpOnly 세션 토큰만 담는다. 비밀번호·토큰·설정값은 응답 본문에 넣지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AdminSession
from app.auth.service import (
    SESSION_COOKIE,
    AdminPrincipal,
    _hash_token,
    authenticate_admin,
    clear_session_cookie,
    require_preview_admin,
    revoke_admin_session,
    set_session_cookie,
)
from app.core.config import Settings, get_settings
from app.db import get_db

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class SessionResponse(BaseModel):
    user_id: UUID
    email: str
    role: str
    session_id: UUID
    expires_at: datetime


@router.post("/login", response_model=SessionResponse)
def login(
    payload: LoginRequest,
    response: Response,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SessionResponse:
    user, issued = authenticate_admin(session, payload.email, payload.password)
    session.commit()
    set_session_cookie(response, issued, settings)
    return SessionResponse(
        user_id=user.id,
        email=user.email,
        role=user.role,
        session_id=issued.session_id,
        expires_at=issued.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    """세션이 없어도 안전하게 204를 돌려준다. 있던 세션은 폐기한다."""
    raw_token = request.cookies.get(SESSION_COOKIE)
    if raw_token:
        row = session.scalar(
            select(AdminSession).where(AdminSession.token_hash == _hash_token(raw_token))
        )
        if row is not None:
            revoke_admin_session(session, row.id)
            session.commit()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response


@router.get("/session", response_model=SessionResponse)
def read_session(
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> SessionResponse:
    return SessionResponse(
        user_id=principal.user_id,
        email=principal.email,
        role=principal.role,
        session_id=principal.session_id,
        expires_at=principal.expires_at,
    )
