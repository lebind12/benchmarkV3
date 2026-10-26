"""Signed access tokens and atomic refresh rotation in namespaced Upstash keys."""

from __future__ import annotations

import hashlib
import secrets
import time
from typing import Any

import httpx
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import db
from app.core.config import get_settings
from app.models.app_user import AppUser


class SessionError(ValueError):
    pass


class SessionUnavailable(RuntimeError):
    pass


def _secret() -> str:
    value = get_settings().jwt_secret_key
    if not value or len(value) < 32:
        raise SessionUnavailable("인증 서명 키가 설정되지 않았습니다.")
    return value


def encode_token(user_id: int, kind: str, *, lifetime: int, family: str | None = None) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": kind,
            "iat": now,
            "exp": now + lifetime,
            "iss": "benchmark",
            "aud": "benchmark-web",
            "jti": secrets.token_urlsafe(24),
            **({"family": family} if family else {}),
        },
        _secret(),
        algorithm="HS256",
    )


def decode_token(token: str, kind: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=["HS256"],
            audience="benchmark-web",
            issuer="benchmark",
            options={"require": ["exp", "iat", "sub", "jti", "type"]},
        )
        if payload["type"] != kind or not str(payload["sub"]).isdigit():
            raise SessionError("유효하지 않은 인증 정보입니다.")
        if kind == "refresh" and not isinstance(payload.get("family"), str):
            raise SessionError("유효하지 않은 갱신 정보입니다.")
        return payload
    except jwt.PyJWTError as exc:
        raise SessionError("로그인이 만료되었습니다. 다시 로그인하세요.") from exc


def redis_command(*command: Any) -> Any:
    settings = get_settings()
    if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
        raise SessionUnavailable("세션 저장소가 설정되지 않았습니다.")
    try:
        response = httpx.post(
            settings.upstash_redis_rest_url,
            json=list(command),
            headers={"Authorization": f"Bearer {settings.upstash_redis_rest_token}"},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("error"):
            raise SessionUnavailable("세션 저장소 요청에 실패했습니다.")
        return payload.get("result")
    except (httpx.HTTPError, ValueError) as exc:
        raise SessionUnavailable("세션 저장소에 연결하지 못했습니다.") from exc


def _key(family: str) -> str:
    prefix = get_settings().upstash_redis_key_prefix
    if not prefix or not prefix.endswith(":"):
        raise SessionUnavailable("세션 저장소의 환경 prefix가 필요합니다.")
    return f"{prefix}auth:refresh:{family}"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


_ROTATE = """
local old = redis.call('GET', KEYS[1])
if not old then return 0 end
if old ~= ARGV[1] then redis.call('DEL', KEYS[1]); return -1 end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3]); return 1
"""


def issue_session(user: AppUser) -> tuple[dict, str]:
    family = secrets.token_urlsafe(24)
    refresh = encode_token(user.id, "refresh", lifetime=7 * 86400, family=family)
    access = encode_token(user.id, "access", lifetime=900)
    if redis_command("SET", _key(family), _digest(refresh), "EX", 7 * 86400, "NX") != "OK":
        raise SessionUnavailable("세션을 저장하지 못했습니다.")
    return {"access_token": access, "token_type": "bearer", "expires_in": 900}, refresh


def rotate_session(token: str) -> tuple[int, dict, str]:
    payload = decode_token(token, "refresh")
    user_id = int(payload["sub"])
    refresh = encode_token(user_id, "refresh", lifetime=7 * 86400, family=payload["family"])
    access = encode_token(user_id, "access", lifetime=900)
    result = redis_command(
        "EVAL", _ROTATE, 1, _key(payload["family"]), _digest(token), _digest(refresh), 7 * 86400
    )
    if result != 1:
        raise SessionError("이미 사용했거나 만료된 갱신 정보입니다. 다시 로그인하세요.")
    return user_id, {"access_token": access, "token_type": "bearer", "expires_in": 900}, refresh


def revoke_session(token: str) -> None:
    try:
        payload = decode_token(token, "refresh")
    except SessionError:
        return
    redis_command("DEL", _key(payload["family"]))


_bearer = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: Session = Depends(db.get_db_session),
) -> AppUser:
    if not credentials:
        raise HTTPException(401, "로그인이 필요합니다.", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(credentials.credentials, "access")
    except SessionError as exc:
        raise HTTPException(401, str(exc), headers={"WWW-Authenticate": "Bearer"}) from exc
    except SessionUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    user = session.get(AppUser, int(claims["sub"]))
    if not user or not user.is_active:
        raise HTTPException(401, "비활성화되었거나 존재하지 않는 계정입니다.")
    return user


def manager_user(user: AppUser = Depends(current_user)) -> AppUser:
    if user.role not in {"STREAMER", "ADMIN"}:
        raise HTTPException(403, "스트리머 또는 관리자 권한이 필요합니다.")
    return user
