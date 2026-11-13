"""로컬 개발 프로필의 세션 adapter.

원래 `app.core.sessions`는 refresh 상태를 원격 Upstash에 쓰고, 로그인은
`public.app_user.last_login_at`을 갱신한다. 로컬에서 기존 계정 원장은 읽기 전용
이므로 그 두 쓰기를 재현하지 않는다. 대신 **같은 JWT 형식**을 유지하고 refresh
상태만 같은 DB의 `preview_dev.preview_admin_sessions`에 남긴다.

계약(원본과 동일):

- `issue_session(user) -> (dict, str)`
  `dict`는 `{"access_token", "token_type", "expires_in"}`, `str`은 refresh 토큰.
- `rotate_session(token) -> (int, dict, str)`
  `(user_id, tokens, new_refresh)`. 이미 쓴·만료된 토큰은 `SessionError`.
- `revoke_session(token) -> None`
  해당 refresh 토큰의 행을 폐기한다. 없는 토큰은 조용히 넘어간다.

경계:

- 원본 `app.core.sessions`의 서명·JWT 클레임(`sub`/`type`/`iss`/`aud`/`jti`/
  `family`)을 그대로 쓰고, 저장 위치와 계정 행 갱신 여부만 다르다.
- 쓰기는 `preview_dev.preview_admin_sessions` 한 테이블이다. `public` 스키마에는
  쓰지 않는다.
- 토큰 원문은 저장하지 않는다(SHA-256 해시만). 만료·폐기는 행으로 판정한다.
- refresh 회전은 조건부 UPDATE 하나로 처리해, 같은 토큰의 동시 회전이면 한 쪽만
  성공하게 한다(원본의 원자적 회전 의미 유지).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.sessions import SessionError, encode_token, decode_token
from app.models.app_user import AppUser
from app.preview.db import get_session_factory

REFRESH_LIFETIME_SECONDS = 7 * 86400
ACCESS_LIFETIME_SECONDS = 900

__all__ = [
    "ACCESS_LIFETIME_SECONDS",
    "REFRESH_LIFETIME_SECONDS",
    "issue_session",
    "revoke_session",
    "rotate_session",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _tokens(user_id: int) -> dict:
    access = encode_token(user_id, "access", lifetime=ACCESS_LIFETIME_SECONDS)
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": ACCESS_LIFETIME_SECONDS,
    }


def _session_row_model():
    """세션 행 모델. 개발 저장소 모듈에서만 가져온다(원본 public 모델이 아니다)."""
    from app.auth.models import AdminSession

    return AdminSession


def issue_session(user: AppUser) -> tuple[dict, str]:
    """개발 세션 행을 만들고 refresh 토큰을 한 번만 돌려준다."""
    family = secrets.token_urlsafe(24)
    refresh = encode_token(
        user.id, "refresh", lifetime=REFRESH_LIFETIME_SECONDS, family=family
    )
    AdminSession = _session_row_model()
    factory = get_session_factory()
    with factory() as session:
        session.add(
            AdminSession(
                token_hash=_digest(refresh),
                user_id=user.id,
                email=user.email,
                expires_at=_now() + timedelta(seconds=REFRESH_LIFETIME_SECONDS),
            )
        )
        session.commit()
    return _tokens(user.id), refresh


def rotate_session(token: str) -> tuple[int, dict, str]:
    """쓰인 refresh 토큰을 새 토큰으로 회전한다. 재사용은 거부한다."""
    payload = decode_token(token, "refresh")
    user_id = int(payload["sub"])
    family = payload["family"]
    new_refresh = encode_token(
        user_id, "refresh", lifetime=REFRESH_LIFETIME_SECONDS, family=family
    )
    AdminSession = _session_row_model()
    factory = get_session_factory()
    with factory() as session:
        # 조건부 UPDATE 하나로 회전한다. 같은 토큰으로 두 번 회전하면 한 번만 성공한다.
        result = session.execute(
            update(AdminSession)
            .where(
                AdminSession.token_hash == _digest(token),
                AdminSession.revoked_at.is_(None),
                AdminSession.expires_at > _now(),
            )
            .values(
                token_hash=_digest(new_refresh),
                expires_at=_now() + timedelta(seconds=REFRESH_LIFETIME_SECONDS),
            )
        )
        if result.rowcount != 1:
            session.rollback()
            raise SessionError("이미 사용했거나 만료된 갱신 정보입니다. 다시 로그인하세요.")
        session.commit()
    return user_id, _tokens(user_id), new_refresh


def revoke_session(token: str) -> None:
    """로그아웃: 해당 refresh 토큰의 행을 폐기한다. 해석 불가 토큰은 무시한다."""
    try:
        payload = decode_token(token, "refresh")
    except SessionError:
        return

    AdminSession = _session_row_model()
    factory = get_session_factory()
    with factory() as session:
        row = session.scalar(
            select(AdminSession).where(AdminSession.token_hash == _digest(token))
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = _now()
            session.commit()
