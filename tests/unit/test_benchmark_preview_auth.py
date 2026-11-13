"""BI-01 직접 인증 경계 검사 — 원래 로그인 계약·권한·기존 행 무변경.

합성 입력과 루프백 전용 테스트 DB만 쓴다. 운영 DB에 이 검사를 실행하지 않는다
(파괴적 준비 전에 `tests/preview/_dbguard.py`의 `assert_safe_test_database`가
`PREVIEW_TEST_DATABASE_URL`의 목적지·이름을 확인한다. 기본값은 `*_test`다).
운영 계정을 만들거나 조회하지 않고, 실패 조건(비ADMIN·비활성)도 합성 행으로 만든다.

검사 이유(실패 시 사용자 영향):

- 로그인 응답 모양·refresh 쿠키·`/me`가 원래 프론트 계약과 달라지면 사용자는
  로컬에서 로그인할 수 없다.
- 로그인이 기존 `public.app_user` 행이나 원격 세션 저장소에 쓰면 "기존 자료 읽기
  전용" 기준을 위반한다.
- ADMIN 경계가 무너지면 비ADMIN 계정이 프리뷰 생성을 실행할 수 있다.
- 계정 조회가 경기 조회 연결(`DATABASE_URL`)로 되돌아가면 좁은 identity 읽기 역할이
  실제로 쓰이지 않고, 계정 조회가 fixture 연결 권한에 의존하게 된다.
"""

from __future__ import annotations

import os

import pytest

from tests.preview._dbguard import assert_safe_test_database

TEST_DATABASE_URL = os.environ.get(
    "PREVIEW_TEST_DATABASE_URL",
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test",
)

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
ME = "/api/v1/auth/me"
LOGOUT = "/api/v1/auth/logout"
PREVIEW_CREATE = "/api/v1/admin/preview/bundle-runs"
PREVIEW_RUNS = "/api/v1/admin/preview/runs"

IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS public.app_user (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'USER',
    nickname text,
    is_active boolean NOT NULL DEFAULT true,
    email_verified boolean NOT NULL DEFAULT false,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_user_role_check CHECK (role IN ('USER', 'STREAMER', 'ADMIN'))
)
"""

SESSION_DDL = """
CREATE TABLE IF NOT EXISTS preview_dev.preview_admin_sessions (
    id uuid PRIMARY KEY,
    user_id bigint NOT NULL,
    email text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
)
"""


@pytest.fixture(scope="module", autouse=True)
def _local_profile():
    """로컬 개발 프로필 환경을 세우고 루프백 테스트 DB에 최소 스키마를 만든다."""
    # 연결·DDL·환경변경보다 먼저 대상을 확인한다. 이 검사는 `DROP SCHEMA`를 실행하므로
    # 루프백·전용 테스트 DB 이름이 아니면 여기서 멈춘다.
    assert_safe_test_database(TEST_DATABASE_URL)

    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["LOCAL_DEV_AUTH_ENABLED"] = "true"
    os.environ["JWT_SECRET_KEY"] = "bi01-local-test-signing-key-0123456789abcdef"
    os.environ["AUTH_COOKIE_SECURE"] = "false"
    os.environ["CORS_ALLOW_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"
    os.environ["WORKER_SCHEDULER_ENABLED"] = "false"
    os.environ.pop("UPSTASH_REDIS_REST_URL", None)
    os.environ.pop("UPSTASH_REDIS_REST_TOKEN", None)

    from sqlalchemy import create_engine, text

    from app import db as benchmark_db
    from app.core.config import get_settings as benchmark_settings
    from app.preview import db as preview_db
    from app.preview.config import get_settings as preview_settings

    def _ddl_engine():
        return create_engine(
            TEST_DATABASE_URL,
            future=True,
            isolation_level="AUTOCOMMIT",
            # 잠금 대기로 검사가 멈추지 않게 한다. 다른 pytest 묶음이 같은 테스트 DB를
            # 쓰고 있으면 DDL은 기다리지 않고 실패해야 원인을 바로 알 수 있다.
            connect_args={"options": "-c lock_timeout=5000"},
        )

    def _fresh_engines() -> None:
        """모듈 수준 엔진을 버리고 새 설정으로 다시 만든다.

        엔진을 버리지 않고 스키마를 지우면 열린 연결이 DDL을 막아 검사가 멈춘다.
        """
        benchmark_settings.cache_clear()
        preview_settings.cache_clear()
        benchmark_db.reset_engine()
        preview_db.reset_engine()

    _fresh_engines()

    ddl_engine = _ddl_engine()
    with ddl_engine.connect() as conn:
        conn.execute(text("SET lock_timeout = '5s'"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        conn.execute(text(IDENTITY_DDL))
        conn.execute(text("DROP SCHEMA IF EXISTS preview_dev CASCADE"))
        conn.execute(text("CREATE SCHEMA preview_dev"))
        conn.execute(text(SESSION_DDL))
    yield
    # 정리 순서: 앱 엔진을 먼저 닫고(열린 연결이 DDL을 막지 않게) 스키마를 지운 뒤,
    # 다른 검사 묶음이 `preview_dev`를 새로 만들 수 있게 흔적을 남기지 않는다.
    benchmark_db.reset_engine()
    preview_db.reset_engine()
    with ddl_engine.connect() as conn:
        conn.execute(text("SET lock_timeout = '5s'"))
        conn.execute(text("DROP SCHEMA IF EXISTS preview_dev CASCADE"))
    ddl_engine.dispose()


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app import db as benchmark_db
    from app.preview import db as preview_db
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
    # 테스트마다 연결을 닫는다. 남은 연결이 다음 정리 DDL을 막지 않게 한다.
    benchmark_db.reset_engine()
    preview_db.reset_engine()


@pytest.fixture()
def ddl_engine():
    from sqlalchemy import create_engine

    engine = create_engine(
        TEST_DATABASE_URL,
        future=True,
        isolation_level="AUTOCOMMIT",
        connect_args={"options": "-c lock_timeout=5000"},
    )
    yield engine
    engine.dispose()


@pytest.fixture()
def make_user(ddl_engine):
    """기존 계정 원장 형태의 **합성** 행. 운영 계정을 만들지 않는다."""
    import uuid

    from sqlalchemy import text

    from app.auth.passwords import hash_pbkdf2_sha256

    def _make(*, password="correct-horse-battery-9", role="ADMIN", is_active=True) -> dict:
        email = f"{uuid.uuid4().hex}@example.test"
        with ddl_engine.connect() as conn:
            user_id = conn.execute(
                text(
                    "INSERT INTO public.app_user (email, password_hash, role, is_active) "
                    "VALUES (:email, :h, :role, :active) RETURNING id"
                ),
                {
                    "email": email,
                    "h": hash_pbkdf2_sha256(password),
                    "role": role,
                    "active": is_active,
                },
            ).scalar_one()
        return {"id": user_id, "email": email, "password": password, "role": role}

    return _make


def _account_snapshot(ddl_engine, user_id: int):
    from sqlalchemy import text

    with ddl_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT password_hash, role, is_active, nickname, last_login_at, updated_at "
                "FROM public.app_user WHERE id = :id"
            ),
            {"id": user_id},
        ).one()


def _session_rows(ddl_engine) -> list:
    from sqlalchemy import text

    with ddl_engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT token_hash, user_id, revoked_at "
                "FROM preview_dev.preview_admin_sessions ORDER BY created_at"
            )
        ).fetchall()


def _no_remote_store(monkeypatch):
    """로컬 프로필에서 원격 세션 저장소를 호출하면 즉시 실패하게 만든다."""

    def _explode(*_args, **_kwargs):
        raise AssertionError("remote session store must not be called in the local profile")

    monkeypatch.setattr("app.core.sessions.redis_command", _explode)


def test_login_keeps_the_original_response_contract(client, make_user, ddl_engine, monkeypatch):
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")

    response = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"user", "access_token", "token_type", "expires_in"}
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    assert body["access_token"].count(".") == 2  # JWT 세 부분
    assert body["user"] == {
        "id": user["id"],
        "email": user["email"],
        "role": "ADMIN",
        "nickname": None,
        "is_active": True,
    }
    cookie_header = response.headers.get("set-cookie", "")
    assert "benchmark_refresh=" in cookie_header
    assert "HttpOnly" in cookie_header
    # 비밀번호·해시는 응답 어디에도 없다.
    assert user["password"] not in response.text
    assert "password_hash" not in response.text


def test_me_returns_the_same_user_with_the_access_token(
    client, make_user, ddl_engine, monkeypatch
):
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    token = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    ).json()["access_token"]

    response = client.get(ME, headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == user["id"]
    assert response.json()["user"]["role"] == "ADMIN"
    # 토큰 없이는 401이다.
    assert client.get(ME).status_code == 401


def test_refresh_rotates_and_keeps_the_response_contract(
    client, make_user, ddl_engine, monkeypatch
):
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    first = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
    first_cookie = first.cookies.get("benchmark_refresh")
    assert first_cookie

    second = client.post(REFRESH)

    assert second.status_code == 200, second.text
    body = second.json()
    assert set(body) == {"user", "access_token", "token_type", "expires_in"}
    assert body["user"]["id"] == user["id"]
    rotated = second.cookies.get("benchmark_refresh")
    assert rotated and rotated != first_cookie
    # 회전 뒤에도 /me는 새 access 토큰으로 동작한다.
    assert (
        client.get(ME, headers={"Authorization": f"Bearer {body['access_token']}"}).status_code
        == 200
    )


def test_local_profile_never_writes_the_existing_account_or_remote_store(
    client, make_user, ddl_engine, monkeypatch
):
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    before = _account_snapshot(ddl_engine, user["id"])

    assert (
        client.post(LOGIN, json={"email": user["email"], "password": user["password"]}).status_code
        == 200
    )
    assert client.post(REFRESH).status_code == 200
    assert client.post(LOGOUT).status_code == 200

    after = _account_snapshot(ddl_engine, user["id"])
    # `last_login_at`·`updated_at`·비밀번호·역할·활성 상태가 모두 그대로다.
    assert before == after


def test_local_profile_stores_refresh_state_in_preview_dev_only(
    client, make_user, ddl_engine, monkeypatch
):
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    before_rows = len(_session_rows(ddl_engine))

    assert (
        client.post(LOGIN, json={"email": user["email"], "password": user["password"]}).status_code
        == 200
    )
    rows = _session_rows(ddl_engine)
    assert len(rows) == before_rows + 1
    assert rows[-1][1] == user["id"]
    assert rows[-1][2] is None  # 아직 폐기되지 않음

    assert client.post(LOGOUT).status_code == 200
    assert _session_rows(ddl_engine)[-1][2] is not None  # 로그아웃이 그 행을 폐기했다


def test_signup_is_closed_in_the_local_profile(client, ddl_engine):
    response = client.post(
        "/api/v1/auth/signup",
        json={"email": "new-person@example.test", "password": "longenough1"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "signup_disabled_in_local_profile"


def test_all_account_callers_share_the_original_connection(
    client, make_user, monkeypatch
):
    """계정 조회 세 caller(login·`/me`·refresh)가 **원래 `DATABASE_URL` 하나**를 쓴다.

    사용자 지시(2026-11-12)에 따라 계정 전용 읽기 역할·별도 identity DSN은 폐기됐다.
    별도 프리뷰 DSN을 세워도 앱이 그것을 읽지 않는지, 그리고 인증 판정이 모두 같은
    원래 연결의 계정 행으로 이뤄지는지 확인한다. 옛 키로 분기하면 로그인·ADMIN 판정이
    다른 계정 집합을 보게 되어 사용자는 로그인할 수 없다.
    """
    from sqlalchemy import text as sql_text

    from app import db as benchmark_db
    from app.core.config import get_settings as benchmark_settings
    from app.preview.config import get_settings as preview_settings

    _no_remote_store(monkeypatch)
    admin = make_user(role="ADMIN")
    streamer = make_user(role="STREAMER")

    # 옛 프리뷰 전용 키를 다른(닫힌) 대상으로 두어도 앱은 무시해야 한다.
    legacy = TEST_DATABASE_URL.replace("127.0.0.1:55432", "127.0.0.1:55433")
    monkeypatch.setenv("PREVIEW_IDENTITY_DATABASE_URL", legacy)
    monkeypatch.setenv("PREVIEW_FIXTURES_DATABASE_URL", legacy)
    monkeypatch.setenv("PREVIEW_NAMES_DATABASE_URL", legacy)
    monkeypatch.setenv("PREVIEW_STATS_DATABASE_URL", legacy)
    monkeypatch.setenv("PREVIEW_DATABASE_URL", legacy)
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    benchmark_settings.cache_clear()
    preview_settings.cache_clear()
    benchmark_db.reset_engine()
    try:
        # 실제 auth dependency가 고르는 세션이 원래 연결과 **같은 객체**다.
        base_dependency = benchmark_db.get_db_session()
        try:
            base_session = next(base_dependency)
            auth_dependency = benchmark_db.get_auth_db_session(base_session)
            try:
                auth_session = next(auth_dependency)
                assert auth_session is base_session
                bind = auth_session.get_bind()
                assert bind.url.port == 55432  # 원래 DATABASE_URL(닫힌 55433 아님)
                assert bind.url.database == "preview_mp01_test"
            finally:
                auth_dependency.close()
        finally:
            base_dependency.close()

        # 설정도 같은 기준값만 돌려준다(옛 키는 다른 계정으로 분기시키지 못한다).
        preview = preview_settings()
        assert preview.database_url == TEST_DATABASE_URL
        assert preview.resolved_identity_database_url == TEST_DATABASE_URL
        assert preview.fixtures_database_url == TEST_DATABASE_URL
        assert preview.names_database_url == TEST_DATABASE_URL
        assert preview.stats_database_url == TEST_DATABASE_URL

        # 강제 읽기 전용 옵션을 새로 걸지 않는다(원래 계정 권한 그대로).
        assert not getattr(benchmark_db, "AUTH_CONNECT_ARGS", None)
        assert not getattr(benchmark_db, "READ_ONLY_CONNECT_ARGS", None)

        login = client.post(
            LOGIN, json={"email": admin["email"], "password": admin["password"]}
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]
        assert login.json()["user"]["role"] == "ADMIN"

        # current_user → /me와 ADMIN 판정 둘 다 원래 연결에서 읽은 계정이다.
        me = client.get(ME, headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text
        assert me.json()["user"]["id"] == admin["id"]
        # ADMIN은 인증 경계를 통과하고, 모델 설정이 없어 실행만 열리지 않는다(422).
        assert (
            client.post(
                PREVIEW_CREATE,
                json={"fixture_id": 1557474, "mode": "live"},
                headers={"Authorization": f"Bearer {token}"},
            ).status_code
            == 422
        )

        # refresh도 계정 확인을 같은 연결에서 한다.
        assert client.post(REFRESH).status_code == 200

        # 다른 역할 계정도 같은 연결에서 읽어 403으로 판정한다(권한 우회 없음).
        client.cookies.clear()
        client.headers.pop("Authorization", None)
        other = client.post(
            LOGIN, json={"email": streamer["email"], "password": streamer["password"]}
        )
        assert other.status_code == 200, other.text
        denied = client.post(
            PREVIEW_CREATE,
            json={"fixture_id": 1557474, "mode": "live"},
            headers={"Authorization": f"Bearer {other.json()['access_token']}"},
        )
        assert denied.status_code == 403
        assert denied.json()["detail"] == "admin role required"
    finally:
        preview_settings.cache_clear()
        benchmark_settings.cache_clear()
        benchmark_db.reset_engine()


def test_missing_original_database_url_never_logs_in(
    client, make_user, monkeypatch, tmp_path
):
    """원래 `DATABASE_URL`이 없으면 로그인·/me는 503으로 실패한다.

    자리표시자를 연결 대상으로 쓰거나 프리뷰 전용 DSN으로 대체하지 않는지 확인한다.
    """
    from app import db as benchmark_db
    from app.core.config import get_settings as benchmark_settings
    from app.preview.config import get_settings as preview_settings
    from app.core.config import PLACEHOLDER_DATABASE_URL

    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    monkeypatch.chdir(tmp_path)  # 로컬 `.env`가 판정에 끼어들지 않게 한다
    monkeypatch.setenv("DATABASE_URL", PLACEHOLDER_DATABASE_URL)
    # 옛 프리뷰 DSN을 세워 두어도 대체 연결로 쓰이지 않아야 한다.
    monkeypatch.setenv("PREVIEW_IDENTITY_DATABASE_URL", TEST_DATABASE_URL)
    benchmark_settings.cache_clear()
    preview_settings.cache_clear()
    benchmark_db.reset_engine()
    try:
        response = client.post(
            LOGIN, json={"email": user["email"], "password": user["password"]}
        )
        assert response.status_code in (503, 500), response.text
        assert "access_token" not in response.text

        # 계정 조회가 필요한 가입 경로는 원래대로 403이다.
        assert (
            client.post(
                "/api/v1/auth/signup",
                json={"email": "x@example.test", "password": "longenough1"},
            ).status_code
            == 403
        )
    finally:
        # monkeypatch가 되돌리기 전에 원래 테스트 대상으로 복구한 뒤 엔진을 다시 만든다.
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        preview_settings.cache_clear()
        benchmark_settings.cache_clear()
        benchmark_db.reset_engine()


def test_unreachable_original_connection_never_logs_in(client, make_user, monkeypatch):
    """원래 연결에 붙지 못하면 로그인·/me를 500으로 흘리지 않고 503으로 멈춘다."""
    from app import db as benchmark_db
    from app.core.config import get_settings as benchmark_settings
    from app.preview.config import get_settings as preview_settings

    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    # 55433은 이 검사 환경에서 비어 있는 포트다(루프백이라 대상 검사는 통과한다).
    unreachable = TEST_DATABASE_URL.replace("127.0.0.1:55432", "127.0.0.1:55433")
    monkeypatch.setenv("DATABASE_URL", unreachable)
    monkeypatch.setenv("PREVIEW_IDENTITY_DATABASE_URL", TEST_DATABASE_URL)
    benchmark_settings.cache_clear()
    preview_settings.cache_clear()
    benchmark_db.reset_engine()
    try:
        response = client.post(
            LOGIN, json={"email": user["email"], "password": user["password"]}
        )
        assert response.status_code in (503, 500), response.text
        assert "access_token" not in response.text
    finally:
        # 다음 검사가 정상 연결을 쓰도록 원래 대상으로 되돌린 뒤 엔진을 다시 만든다.
        monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
        preview_settings.cache_clear()
        benchmark_settings.cache_clear()
        benchmark_db.reset_engine()


def test_anonymous_cannot_create_a_preview_run(client):
    response = client.post(PREVIEW_CREATE, json={"fixture_id": 1557474, "mode": "live"})
    assert response.status_code == 401


def test_non_admin_cannot_create_a_preview_run(client, make_user, monkeypatch):
    """STREAMER도 USER도 프리뷰 생성을 실행할 수 없다(401이 아니라 403)."""
    _no_remote_store(monkeypatch)
    for role in ("STREAMER", "USER"):
        client.cookies.clear()
        user = make_user(role=role)
        login = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
        assert login.status_code == 200, (role, login.text)
        token = login.json()["access_token"]

        response = client.post(
            PREVIEW_CREATE,
            json={"fixture_id": 1557474, "mode": "live"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, (role, response.text)
        assert response.json()["detail"] == "admin role required"


def test_admin_passes_the_preview_boundary_without_calling_a_model(
    client, make_user, monkeypatch
):
    """ADMIN은 인증 경계를 통과한다. 모델 설정이 없으면 실행 자체를 열지 않는다(422).

    실행이 열리지 않는 이유가 인증이 아니라 설정이라는 점이 핵심이다. 403이 아닌
    422라는 사실로 ADMIN 통과를 증명하고, 동시에 이 검사가 모델을 호출하지 않았음을
    보장한다(`no model calls`).
    """
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    login = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
    token = login.json()["access_token"]

    response = client.post(
        PREVIEW_CREATE,
        json={"fixture_id": 1557474, "mode": "live"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422, response.text
    assert "모델 설정" in response.json()["detail"]


def test_origin_check_is_still_enforced(client, make_user, monkeypatch):
    """Origin 검사를 끄지 않는다. 허용 목록 밖 출처의 로그인은 403이다."""
    _no_remote_store(monkeypatch)
    user = make_user(role="ADMIN")
    payload = {"email": user["email"], "password": user["password"]}

    denied = client.post(LOGIN, json=payload, headers={"Origin": "http://evil.example"})
    assert denied.status_code == 403

    allowed = client.post(LOGIN, json=payload, headers={"Origin": "http://localhost:5173"})
    assert allowed.status_code == 200, allowed.text
