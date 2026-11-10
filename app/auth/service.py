"""관리자 인증 동작.

계약:
- `authenticate_admin`: 자격 증명으로 관리자 세션을 발급한다.
- `require_preview_admin`: 요청의 활성·미만료 세션을 검사해 ADMIN만 통과시킨다.
- `revoke_admin_session`: 로그아웃 시 해당 세션을 폐기한다.

비인증은 401, 인증됐지만 ADMIN이 아닌 경우는 403이다. STREAMER는 ADMIN의
대체 권한이 아니다.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AdminSession, Role, User
from app.core.config import Settings, get_settings
from app.db import get_db

SESSION_COOKIE = "preview_admin_session"

_hasher = PasswordHasher()
# 사용자를 찾지 못한 경우에도 같은 비용의 검증을 수행해 응답 시간 차이로
# 계정 존재 여부를 알아내지 못하게 한다.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing-equalisation")


@dataclass(frozen=True)
class AdminPrincipal:
    """인증된 관리자. 응답에 비밀값은 담지 않는다."""

    user_id: UUID
    email: str
    role: str
    session_id: UUID
    expires_at: datetime


@dataclass(frozen=True)
class IssuedSession:
    token: str
    session_id: UUID
    expires_at: datetime


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_session(session: Session, user: User, settings: Settings | None = None) -> IssuedSession:
    """세션 행을 만들고 원문 토큰을 한 번만 돌려준다. DB에는 해시만 남는다."""
    ttl = (settings or get_settings()).session_ttl_seconds
    token = secrets.token_urlsafe(32)
    expires_at = _now() + timedelta(seconds=ttl)
    row = AdminSession(token_hash=_hash_token(token), user_id=user.id, expires_at=expires_at)
    session.add(row)
    session.flush()
    return IssuedSession(token=token, session_id=row.id, expires_at=expires_at)


def authenticate_admin(
    session: Session, email: str, password: str
) -> tuple[User, IssuedSession]:
    """자격 증명을 확인한다.

    잘못된 자격 증명과 사용할 수 없는 계정은 401, 올바른 자격 증명이지만
    ADMIN이 아닌 계정은 403으로 구분한다.
    """
    normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == normalized))

    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials"
        )

    if user.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )

    return user, issue_session(session, user)


def revoke_admin_session(session: Session, session_id: UUID) -> None:
    row = session.get(AdminSession, session_id)
    if row is not None and row.revoked_at is None:
        row.revoked_at = _now()
        session.flush()


def _resolve_principal(session: Session, raw_token: str | None) -> AdminPrincipal:
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    row = session.scalar(select(AdminSession).where(AdminSession.token_hash == _hash_token(raw_token)))
    if row is None or not row.is_live():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )

    if user.role != Role.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="admin role required"
        )

    return AdminPrincipal(
        user_id=user.id,
        email=user.email,
        role=user.role,
        session_id=row.id,
        expires_at=row.expires_at,
    )


def require_preview_admin(
    request: Request, session: Session = Depends(get_db)
) -> AdminPrincipal:
    """모든 관리자 엔드포인트를 지키는 서버 측 경계. UI 리다이렉트는 권한이 아니다."""
    return _resolve_principal(session, request.cookies.get(SESSION_COOKIE))


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
