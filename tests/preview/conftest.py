"""MP-01 테스트 공통 설정.

테스트는 전용 로컬 테스트 DB만 사용한다. 대상 검사(`_dbguard`)는 세션 범위
autouse 픽스처 `_environment`에서 첫 테스트 준비 시점에 한 번 실행된다. 이는
import·수집(collection) 시점이 아니며, 수집만으로는 DB 연결이 열리지 않는다.
`engine`·`schema`는 `_environment`에 의존하므로, 검사에 실패하면 파괴적 준비
단계에 도달하지 못한다.

기존 계정 원장(`public.app_user`) 형태도 같은 테스트 DB에 만든다. 운영 원장에
직접 fixture를 실행하지 않는다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.preview._dbguard import assert_safe_test_database

TEST_DATABASE_URL = os.environ.get(
    "PREVIEW_TEST_DATABASE_URL",
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test",
)

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


def _configure_environment() -> None:
    """테스트 DB를 가리키는 환경을 **수집 시점에** 세운다.

    통합 앱은 모듈 import 시점에 `app.db`의 엔진을 만든다. 그 엔진이 기본
    placeholder URL을 붙잡으면 검사 중 원격 접속을 시도하게 된다. 그래서 환경은
    픽스처가 아니라 conftest import에서 세운다. **연결은 열지 않는다**(값만 설정).

    원격 세션 저장소·수집 scheduler·자동 홈 프리뷰는 테스트에서 켜지 않는다.
    """
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_ENV"] = "test"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    # 원래 benchmark 설정도 같은 테스트 DB를 본다.
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["LOCAL_DEV_AUTH_ENABLED"] = "true"
    os.environ.setdefault(
        "JWT_SECRET_KEY", "tests-only-signing-key-do-not-use-outside-tests"
    )
    os.environ["AUTH_COOKIE_SECURE"] = "false"
    os.environ["WORKER_SCHEDULER_ENABLED"] = "false"
    os.environ["HOME_PREVIEW_ENABLED"] = "false"
    os.environ["CORS_ALLOW_ORIGINS"] = "http://localhost:5173,http://127.0.0.1:5173"
    os.environ.pop("UPSTASH_REDIS_REST_URL", None)
    os.environ.pop("UPSTASH_REDIS_REST_TOKEN", None)


_configure_environment()


@pytest.fixture(scope="session", autouse=True)
def _environment() -> Iterator[None]:
    # 연결을 열기 전에 대상부터 검사한다.
    assert_safe_test_database(TEST_DATABASE_URL)
    yield


@pytest.fixture()
def engine(_environment: None):
    """테스트마다 프리뷰 엔진을 새로 만든다.

    통합 앱의 원래 앱 엔진(public 모델용)도 함께 버려 이전 테스트의 연결이 남지 않게
    한다. 두 엔진 모두 테스트 DB를 가리킨다.
    """
    from app import db as benchmark_db
    from app.auth import identity as identity_module
    from app.preview.config import get_settings
    from app.preview.db import get_engine, reset_engine

    reset_engine()
    benchmark_db.reset_engine()
    identity_module.reset_identity_reader()
    get_settings.cache_clear()
    eng = get_engine()
    yield eng


@pytest.fixture()
def schema(engine) -> Iterator[None]:
    """테스트마다 스키마를 새로 만든다. 마이그레이션 대신 모델 메타데이터를 쓴다."""
    from sqlalchemy import text

    from app.auth import models as _models  # noqa: F401  (모델 등록)
    from app.preview import models as _preview_models  # noqa: F401  (모델 등록)
    from app.preview.db import SCHEMA, Base

    with engine.begin() as conn:
        # 잠금 대기로 검사가 무한정 멈추지 않게 한다. 다른 pytest 묶음이 같은 테스트
        # DB를 쓰고 있으면 DDL이 기다리지 않고 실패해야 원인이 보인다.
        conn.execute(text("SET lock_timeout = '10s'"))
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(IDENTITY_DDL))
    Base.metadata.create_all(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("SET lock_timeout = '10s'"))
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture()
def session_factory(engine, schema):
    from app.preview.db import get_session_factory

    return get_session_factory()


@pytest.fixture()
def identity(engine, schema):
    from app.auth.identity import build_read_only_engine, IdentityReader

    eng = build_read_only_engine(TEST_DATABASE_URL)
    yield IdentityReader(eng)
    eng.dispose()


class BearerTestClient(TestClient):
    """원래 프론트와 같은 방식으로 토큰을 쓰는 테스트 클라이언트.

    통합 앱의 보호 경로는 `Authorization: Bearer <access_token>`을 요구한다(원래
    프론트의 `stores/auth`가 access 토큰을 들고 API를 호출한다). 세션 쿠키는 refresh
    전용이다. 그래서 로그인 응답을 받으면 access 토큰을 기억해 두고 이후 요청에
    기본 헤더로 붙인다. 브라우저가 하는 일과 같으며, 서버 계약을 우회하지 않는다.

    로그아웃하면 기억한 토큰을 지운다(프론트도 같은 시점에 지운다).
    """

    access_token: str | None = None

    def request(self, method, url, *args, **kwargs):  # type: ignore[override]
        response = super().request(method, url, *args, **kwargs)
        path = str(url)
        if method.upper() == "POST":
            if path.endswith("/api/v1/auth/login") or path.endswith("/api/v1/auth/refresh"):
                if response.status_code == 200:
                    token = response.json().get("access_token")
                    if token:
                        self.access_token = token
                        self.headers["Authorization"] = f"Bearer {token}"
            elif path.endswith("/api/v1/auth/logout"):
                self.access_token = None
                self.headers.pop("Authorization", None)
        return response


@pytest.fixture()
def client(engine, schema) -> Iterator[BearerTestClient]:
    from app.main import create_app

    with BearerTestClient(create_app()) as test_client:
        yield test_client


def _hash_for_fixture(password: str) -> str:
    from app.auth.passwords import hash_pbkdf2_sha256

    return hash_pbkdf2_sha256(password)


@pytest.fixture()
def make_user(session_factory):
    """기존 계정 원장 형태의 합성 행을 만든다. 운영 계정을 만들지 않는다."""
    from sqlalchemy import text

    def _make(
        *,
        email: str | None = None,
        password: str = "correct-horse-battery-9",
        role: str = "ADMIN",
        is_active: bool = True,
    ) -> dict:
        normalized = email or f"{uuid.uuid4().hex}@example.test"
        with session_factory() as session:
            user_id = session.execute(
                text(
                    "INSERT INTO public.app_user (email, password_hash, role, is_active) "
                    "VALUES (:email, :h, :role, :active) RETURNING id"
                ),
                {
                    "email": normalized,
                    "h": _hash_for_fixture(password),
                    "role": role,
                    "active": is_active,
                },
            ).scalar_one()
            session.commit()
        return {"id": user_id, "email": normalized, "password": password, "role": role}

    return _make
