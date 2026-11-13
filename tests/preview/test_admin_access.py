"""관리자 접근 경계 — 통합 앱의 원래 JWT 인증 기준.

이 파일은 BI-01 통합 이후 계약으로 갱신됐다. 이전에는 프리뷰 전용 세션 쿠키
(`preview_admin_session`)와 `/api/v1/auth/session`을 검사했지만, 이제 인증은 **원래
benchmark JWT**다(`/api/v1/auth/login` → access 토큰 + `benchmark_refresh` 쿠키,
`/api/v1/auth/me`). 검사 의도는 그대로다.

- 비인증은 401, 인증됐지만 ADMIN이 아닌 경우는 403이다. STREAMER는 ADMIN의 대체
  권한이 아니다.
- 로그인 자체는 역할로 막지 않는다. 원래 로그인 계약이 역할과 무관하게 동작하고,
  **프리뷰 관리 경로**가 ADMIN만 통과시킨다.
- 비밀번호·해시·토큰 원문은 응답에 실리지 않고, 쿠키는 HttpOnly다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.auth.models import AdminSession

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
REFRESH = "/api/v1/auth/refresh"
# 실제 보호 대상 경로. 프론트의 빈 실행 목록이 읽는 경로다.
PROTECTED = "/api/v1/admin/preview/runs"


def _login(client, email: str, password: str):
    return client.post(LOGIN, json={"email": email, "password": password})


def _auth(client, make_user, role: str = "ADMIN") -> dict:
    """합성 계정으로 로그인하고 Bearer 헤더를 돌려준다."""
    user = make_user(role=role)
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _assert_anonymous(client) -> None:
    response = client.get(PROTECTED)
    assert response.status_code == 401, response.text


def _assert_non_admin(client, headers) -> None:
    response = client.get(PROTECTED, headers=headers)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "admin role required"


def test_anonymous_is_rejected(client):
    _assert_anonymous(client)


def test_login_rejects_wrong_password(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], "not-the-password")
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"
    assert "password" not in response.text.lower()
    _assert_anonymous(client)


def test_login_rejects_unknown_email(client):
    response = _login(client, "missing@example.test", "correct-horse-battery-9")
    assert response.status_code == 401


def test_admin_login_returns_the_original_contract_without_secrets(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"user", "access_token", "token_type", "expires_in"}
    assert body["user"]["role"] == "ADMIN"
    assert body["user"]["email"] == user["email"]
    assert set(body["user"]) == {"id", "email", "role", "nickname", "is_active"}
    # 비밀번호 원문과 해시는 응답에 없다.
    serialized = response.text
    assert user["password"] not in serialized
    assert "password_hash" not in serialized
    cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie_header


def test_valid_admin_reaches_protected_route(client, make_user):
    headers = _auth(client, make_user, "ADMIN")

    response = client.get(PROTECTED, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"runs": [], "next_cursor": None}

    me = client.get(ME, headers=headers)
    assert me.status_code == 200
    assert me.json()["user"]["role"] == "ADMIN"


def test_user_and_streamer_can_log_in_but_are_denied_the_preview_path(client, make_user):
    """로그인은 역할로 막지 않는다. 프리뷰 관리 경로만 ADMIN을 요구한다."""
    for role in ("USER", "STREAMER"):
        client.cookies.clear()
        headers = _auth(client, make_user, role)
        _assert_non_admin(client, headers)
        assert client.get(ME, headers=headers).status_code == 200


def test_inactive_admin_cannot_log_in(client, make_user):
    user = make_user(role="ADMIN", is_active=False)
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 403
    assert response.json()["detail"] == "inactive_user"
    _assert_anonymous(client)


def test_expired_session_row_is_denied(client, make_user, session_factory):
    """개발 세션 행이 만료되면 refresh로 새 access 토큰을 받을 수 없다."""
    user = make_user(role="ADMIN")
    assert _login(client, user["email"], user["password"]).status_code == 200

    with session_factory() as session:
        row = session.scalar(select(AdminSession))
        assert row is not None
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    assert client.post(REFRESH).status_code == 401


def test_refresh_rotates_the_cookie_and_rejects_replay(client, make_user):
    user = make_user(role="ADMIN")
    assert _login(client, user["email"], user["password"]).status_code == 200
    first = client.cookies.get("benchmark_refresh")
    assert first

    rotated = client.post(REFRESH)
    assert rotated.status_code == 200, rotated.text
    second = rotated.cookies.get("benchmark_refresh")
    assert second and second != first

    # 이미 회전된 토큰을 다시 보내면 거부된다(재사용 방지).
    client.cookies.set("benchmark_refresh", first)
    assert client.post(REFRESH).status_code == 401


def test_logout_revokes_the_development_session_row(client, make_user, session_factory):
    headers = _auth(client, make_user, "ADMIN")
    assert client.get(PROTECTED, headers=headers).status_code == 200

    assert client.post(LOGOUT).status_code == 200
    client.cookies.clear()

    with session_factory() as session:
        rows = session.scalars(select(AdminSession)).all()
        assert len(rows) == 1
        assert rows[0].revoked_at is not None


def test_session_token_is_not_stored_in_plaintext(client, make_user, session_factory):
    user = make_user(role="ADMIN")
    assert _login(client, user["email"], user["password"]).status_code == 200
    raw_token = client.cookies.get("benchmark_refresh")
    assert raw_token

    with session_factory() as session:
        row = session.scalars(select(AdminSession)).one()
        assert len(row.token_hash) == 64  # SHA-256 hex
        assert raw_token not in row.token_hash


def test_forged_refresh_cookie_is_rejected(client):
    client.cookies.set("benchmark_refresh", "forged-token-value")
    assert client.post(REFRESH).status_code == 401
    _assert_anonymous(client)


def test_login_response_sets_an_httponly_refresh_cookie(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "benchmark_refresh=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert user["password"] not in cookie_header


@pytest.mark.parametrize("payload", [{}, {"email": ""}, {"email": "a@b.test"}, {"password": "x"}])
def test_login_requires_both_fields(client, payload):
    response = client.post(LOGIN, json=payload)
    assert response.status_code == 422


def test_login_with_malformed_json_does_not_500(client):
    response = client.post(
        LOGIN, content=b"not-json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 422


def test_logout_without_session_is_safe(client):
    response = client.post(LOGOUT)
    assert response.status_code == 200
    assert response.json() == {"logged_out": True}


def test_me_without_token_is_401(client):
    assert client.get(ME).status_code == 401


def test_health_endpoint_is_liveness_only(client):
    """통합 앱의 `/health`는 원래 계약(프로세스 생존)을 유지한다.

    DB 상태 확인은 `/health`로 꾸미지 않는다. DB 연결은 각 경로가 자기 오류로
    드러낸다(예: 저장소 읽기 실패 503).
    """
    response = client.get("/health")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok"}
