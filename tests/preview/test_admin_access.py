"""MP-01 관리자 접근 경계.

인증 실패(401)와 인증된 비ADMIN 거부(403)를 구분하고, ADMIN 외 역할은
모두 거부한다. STREAMER를 ADMIN의 대체 권한으로 쓰지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.auth.identity import IdentityUser
from app.auth.models import AdminSession

LOGIN = "/api/v1/auth/login"
LOGOUT = "/api/v1/auth/logout"
SESSION = "/api/v1/auth/session"
# 실제 보호 대상 경로. 프론트의 빈 실행 목록이 읽는 경로다.
PROTECTED = "/api/v1/admin/preview/runs"


def _login(client, email: str, password: str):
    return client.post(LOGIN, json={"email": email, "password": password})


def _assert_anonymous(client) -> None:
    response = client.get(PROTECTED)
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "authentication required"


def _assert_non_admin(client, role: str) -> None:
    response = client.get(PROTECTED)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "admin role required"


def test_anonymous_is_rejected(client):
    _assert_anonymous(client)


def test_login_rejects_wrong_password(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], "not-the-password")
    assert response.status_code == 401
    assert "password" not in response.text.lower()
    _assert_anonymous(client)


def test_login_rejects_unknown_email(client):
    response = _login(client, "missing@example.test", "correct-horse-battery-9")
    assert response.status_code == 401


def test_admin_login_returns_principal_without_secrets(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["role"] == "ADMIN"
    assert body["email"] == user["email"]
    assert set(body) == {"user_id", "email", "role", "session_id", "expires_at"}
    # 이 검사는 응답 본문에 비밀번호 원문과 세션 토큰 원문이 없다는 것만 확인한다.
    # 해시·설정값 일반을 모두 배제하는 주장은 아니며, 그 경계는 서명 키·해시가
    # 응답 스키마에 없고 쿠키가 HttpOnly라는 점으로 확인한다.
    serialized = response.text
    assert user["password"] not in serialized
    assert "password_hash" not in serialized
    cookie_header = response.headers.get("set-cookie", "")
    assert "HttpOnly" in cookie_header


def test_valid_admin_reaches_protected_route(client, make_user):
    user = make_user(role="ADMIN")
    assert _login(client, user["email"], user["password"]).status_code == 200
    response = client.get(PROTECTED)
    assert response.status_code == 200, response.text
    assert response.json() == {"runs": [], "next_cursor": None}

    session_body = client.get(SESSION)
    assert session_body.status_code == 200
    assert session_body.json()["role"] == "ADMIN"
    assert session_body.json()["user_id"] == user["id"]


def test_user_role_is_denied_with_403(client, make_user):
    user = make_user(role="USER")
    assert _login(client, user["email"], user["password"]).status_code == 403
    _assert_anonymous(client)


def test_streamer_is_not_treated_as_admin(client, make_user):
    user = make_user(role="STREAMER")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "admin role required"
    _assert_anonymous(client)


def test_authenticated_non_admin_gets_403_not_401(client, make_user, session_factory):
    """세션은 유효하지만 역할이 USER인 경우. 로그인 거부와 다른 경계다."""
    from app.auth.service import issue_session

    user = make_user(role="USER")
    with session_factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        raw_token = issued.token
        session.commit()

    client.cookies.set("preview_admin_session", raw_token)
    _assert_non_admin(client, "USER")
    # 세션 조회도 같은 경계를 지킨다.
    assert client.get(SESSION).status_code == 403


def test_authenticated_streamer_with_valid_session_is_denied(client, make_user, session_factory):
    """STREAMER는 유효한 세션이 있어도 ADMIN 경로에 들어오지 못한다.

    익명 401 테스트와 다른 경계다. 이 케이스는 이미 인증된 세션 위에서 역할만
    다르므로, 서버가 403으로 구분해 거부하는지 확인한다.
    """
    from app.auth.service import issue_session

    user = make_user(role="STREAMER")
    with session_factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        raw_token = issued.token
        session.commit()

    client.cookies.set("preview_admin_session", raw_token)
    _assert_non_admin(client, "STREAMER")
    assert client.get(SESSION).status_code == 403

    # 세션 자체는 살아 있으므로 401이 아니라 403이어야 한다.
    assert client.get(PROTECTED).status_code == 403


def test_inactive_admin_is_denied(client, make_user, session_factory):
    """비활성 계정은 기존 세션이 있어도 인증되지 않는다."""
    from app.auth.service import issue_session

    user = make_user(role="ADMIN", is_active=False)
    with session_factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=False
        )
        issued = issue_session(session, principal)
        session.commit()

    client.cookies.set("preview_admin_session", issued.token)
    _assert_anonymous(client)

    response = _login(client, user["email"], user["password"])
    assert response.status_code == 401


def test_expired_session_is_denied(client, make_user, session_factory):
    from app.auth.service import issue_session

    user = make_user(role="ADMIN")
    with session_factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        row = session.scalar(select(AdminSession).where(AdminSession.id == issued.session_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()
        raw_token = issued.token

    client.cookies.set("preview_admin_session", raw_token)
    _assert_anonymous(client)


def test_session_expiry_is_enforced_from_the_clock_not_a_flag(client, make_user, session_factory):
    """만료 판정이 시각 비교로 이뤄지는지 확인한다. 만료 직전은 통과, 직후는 거부."""
    from app.auth.service import issue_session

    user = make_user(role="ADMIN")
    with session_factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        raw_token = issued.token
        session.commit()

    client.cookies.set("preview_admin_session", raw_token)
    assert client.get(PROTECTED).status_code == 200

    with session_factory() as session:
        row = session.scalar(select(AdminSession).where(AdminSession.id == issued.session_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()

    _assert_anonymous(client)


def test_logout_revokes_session(client, make_user, session_factory):
    user = make_user(role="ADMIN")
    assert _login(client, user["email"], user["password"]).status_code == 200
    assert client.get(PROTECTED).status_code == 200

    assert client.post(LOGOUT).status_code == 204
    _assert_anonymous(client)

    with session_factory() as session:
        rows = session.scalars(select(AdminSession)).all()
        assert len(rows) == 1
        assert rows[0].revoked_at is not None


def test_revoked_session_token_cannot_be_replayed(client, make_user, session_factory):
    """로그아웃 뒤 남아 있던 쿠키 값을 다시 보내도 통과하지 않는다."""
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200
    stolen_token = client.cookies.get("preview_admin_session")
    assert stolen_token

    assert client.post(LOGOUT).status_code == 204
    client.cookies.set("preview_admin_session", stolen_token)
    _assert_anonymous(client)


def test_session_token_is_not_stored_in_plaintext(client, make_user, session_factory):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200
    raw_token = client.cookies.get("preview_admin_session")
    assert raw_token

    with session_factory() as session:
        row = session.scalars(select(AdminSession)).one()
        assert row.token_hash != raw_token
        assert raw_token not in row.token_hash


def test_forged_session_cookie_is_rejected(client):
    client.cookies.set("preview_admin_session", "forged-token-value")
    _assert_anonymous(client)


def test_login_response_sets_httponly_cookie(client, make_user):
    user = make_user(role="ADMIN")
    response = _login(client, user["email"], user["password"])
    assert response.status_code == 200
    cookie_header = response.headers.get("set-cookie", "")
    assert "preview_admin_session=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=lax" in cookie_header or "SameSite=Lax" in cookie_header
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
    assert response.status_code == 204


def test_session_endpoint_without_cookie_is_401(client):
    assert client.get(SESSION).status_code == 401


def test_health_reports_database_reachable(client):
    """개발 세션 저장소와 기존 계정 읽기 경로를 각각 확인한다."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "database": "ok", "identity": "ok"}
