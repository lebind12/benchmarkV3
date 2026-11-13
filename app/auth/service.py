"""관리자 인증 동작.

계약:
- `authenticate_admin`: 기존 계정(`public.app_user`)으로 자격 증명을 확인하고
  개발 세션(`preview_dev.preview_admin_sessions`)을 발급한다.
- `require_preview_admin`: 요청의 활성·미만료 세션과 기존 계정의 현재 역할을
  확인해 ADMIN만 통과시킨다.
- `revoke_admin_session`: 로그아웃 시 해당 개발 세션을 폐기한다.

경계:
- 계정 조회는 원래 `DATABASE_URL`과 그 계정의 기존 권한을 그대로 쓴다. 계정 전용
  축소 역할·별도 읽기 DSN을 만들지 않는다(과거 제안은 폐기됐다).
- 계정 테이블은 읽기만 한다. `last_login_at`·비밀번호·역할·활성 상태를 갱신하지
  않는다. 과거 구현의 로그인 시각 갱신은 재현하지 않는다.
- 쓰기는 `preview_dev` 스키마의 세션 행 하나뿐이다.
- 비인증은 401, 인증됐지만 ADMIN이 아닌 경우는 403이다. STREAMER는 ADMIN의
  대체 권한이 아니다.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.identity import (
    DUMMY_PASSWORD_HASH_FALLBACK,
    IdentityReader,
    IdentityUser,
    get_identity_reader,
)
from app.auth.models import AdminSession, Role
from app.auth.passwords import DUMMY_PASSWORD_HASH, verify_pbkdf2_sha256
from app.auth.tokens import hash_session_token
from app.preview.config import PreviewSettings as Settings, get_settings
from app.preview.db import get_db

SESSION_COOKIE = "preview_admin_session"

__all__ = [
    "SESSION_COOKIE",
    "AdminPrincipal",
    "IssuedSession",
    "authenticate_admin",
    "clear_session_cookie",
    "get_identity",
    "hash_session_token",
    "issue_session",
    "require_preview_admin",
    "revoke_admin_session",
    "set_session_cookie",
]


@dataclass(frozen=True)
class AdminPrincipal:
    """인증된 관리자. 응답에 비밀값은 담지 않는다."""

    user_id: int
    email: str
    role: str
    session_id: UUID
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session_id: UUID
    expires_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_identity(settings: Settings = Depends(get_settings)) -> IdentityReader:
    """기존 계정 읽기 조회기. 원래 `DATABASE_URL`과 같은 자격 증명을 쓴다."""
    settings.assert_identity_database()
    return get_identity_reader(settings.resolved_identity_database_url)


def issue_session(
    session: Session, user: IdentityUser, settings: Settings | None = None
) -> IssuedSession:
    """세션 행을 만들고 원문 토큰을 한 번만 돌려준다. DB에는 해시만 남는다."""
    ttl = (settings or get_settings()).session_ttl_seconds
    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=ttl)
    row = AdminSession(
        token_hash=hash_session_token(token),
        user_id=user.id,
        email=user.email,
        expires_at=expires_at,
    )
    session.add(row)
    session.flush()
    return IssuedSession(token=token, session_id=row.id, expires_at=expires_at)


def authenticate_admin(
    identity: IdentityReader, session: Session, email: str, password: str
) -> tuple[IdentityUser, IssuedSession]:
    """자격 증명을 확인한다.

    잘못된 자격 증명과 사용할 수 없는 계정은 401, 올바른 자격 증명이지만
    ADMIN이 아닌 계정은 403으로 구분한다.
    """
    record = identity.fetch_by_email(email)

    if record is None:
        # 계정이 없어도 같은 비용의 검증을 수행한다.
        verify_pbkdf2_sha256(password, DUMMY_PASSWORD_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    stored_hash = record.password_hash or DUMMY_PASSWORD_HASH_FALLBACK
    if not verify_pbkdf2_sha256(password, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if not record.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if record.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )

    user = record.public()
    return user, issue_session(session, user)


def revoke_admin_session(session: Session, session_id: UUID) -> None:
    row = session.get(AdminSession, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        session.flush()


def _resolve_principal(
    identity: IdentityReader, session: Session, raw_token: str | None
) -> AdminPrincipal:
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    row = session.scalar(
        select(AdminSession).where(AdminSession.token_hash == hash_session_token(raw_token))
    )
    if row is None or not row.is_live():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    # 역할·활성 상태는 개발 세션 사본이 아니라 기존 계정의 현재 값으로 판정한다.
    record = identity.fetch_by_id(row.user_id)
    if record is None or not record.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    if record.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )

    return AdminPrincipal(
        user_id=record.id,
        email=record.email,
        role=record.role,
        session_id=row.id,
        expires_at=row.expires_at,
    )


def require_preview_admin(
    request: Request,
    session: Session = Depends(get_db),
    identity: IdentityReader = Depends(get_identity),
) -> AdminPrincipal:
    """모든 관리자 엔드포인트를 지키는 서버 측 경계. UI 리다이렉트는 권한이 아니다."""
    return _resolve_principal(identity, session, request.cookies.get(SESSION_COOKIE))


def set_session_cookie(response, issued: IssuedSession, settings: Settings) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=issued.token,
        max_age=settings.session_ttl_seconds,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
