"""Security regressions required by the evaluated management UI."""

import pytest
import jwt
from app.core import sessions
from app.core.config import Settings


def settings():
    return Settings(_env_file=None, jwt_secret_key="s" * 48, upstash_redis_key_prefix="local:")


def test_access_rejects_expiry_wrong_type_and_wrong_audience(monkeypatch):
    monkeypatch.setattr(sessions, "get_settings", settings)
    token = sessions.encode_token(7, "access", lifetime=60)
    assert sessions.decode_token(token, "access")["sub"] == "7"
    with pytest.raises(sessions.SessionError):
        sessions.decode_token(token, "refresh")
    with pytest.raises(sessions.SessionError):
        sessions.decode_token(sessions.encode_token(7, "access", lifetime=-1), "access")
    forged = jwt.encode(
        {"sub": "7", "type": "access", "exp": 9999999999, "iss": "benchmark", "aud": "other"},
        "s" * 48,
        algorithm="HS256",
    )
    with pytest.raises(sessions.SessionError):
        sessions.decode_token(forged, "access")


def test_missing_secret_fails_closed(monkeypatch):
    monkeypatch.setattr(sessions, "get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(sessions.SessionUnavailable):
        sessions.encode_token(1, "access", lifetime=60)


def test_refresh_store_uses_prefix_hash_and_explicit_ttl(monkeypatch):
    from types import SimpleNamespace
    import re

    calls = []
    monkeypatch.setattr(sessions, "get_settings", settings)
    monkeypatch.setattr(sessions, "redis_command", lambda *args: calls.append(args) or "OK")
    tokens, refresh = sessions.issue_session(SimpleNamespace(id=7))
    assert sessions.decode_token(tokens["access_token"], "access")["sub"] == "7"
    command = calls[0]
    assert command[0] == "SET"
    assert command[1].startswith("local:auth:refresh:")
    assert re.fullmatch("[a-f0-9]{64}", command[2])
    assert refresh != command[2]
    assert command[3:] == ("EX", 7 * 86400, "NX")


def test_refresh_store_refuses_missing_environment_namespace(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        sessions, "get_settings", lambda: Settings(_env_file=None, jwt_secret_key="s" * 48)
    )
    with pytest.raises(sessions.SessionUnavailable):
        sessions.issue_session(SimpleNamespace(id=7))


def test_default_cors_and_cookie_auth_accept_the_same_local_origins(monkeypatch):
    from fastapi import HTTPException
    from starlette.requests import Request
    from app.core.config import allowed_web_origins
    from app.api.v1 import auth

    origins = allowed_web_origins(Settings(_env_file=None, cors_allow_origins="*"))
    assert "http://127.0.0.1:5173" in origins
    monkeypatch.setattr(auth, "allowed_web_origins", lambda: origins)
    auth.check_origin(Request({"type": "http", "headers": [(b"origin", b"http://127.0.0.1:5173")]}))
    with pytest.raises(HTTPException) as error:
        auth.check_origin(
            Request({"type": "http", "headers": [(b"origin", b"https://untrusted.example")]})
        )
    assert error.value.status_code == 403
