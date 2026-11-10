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


@pytest.fixture(scope="session", autouse=True)
def _environment() -> Iterator[None]:
    # 연결을 열기 전에 대상부터 검사한다.
    assert_safe_test_database(TEST_DATABASE_URL)
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_ENV"] = "test"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    yield


@pytest.fixture()
def engine(_environment: None):
    from app.auth import identity as identity_module
    from app.core.config import get_settings
    from app.db import get_engine, reset_engine

    reset_engine()
    identity_module.reset_identity_reader()
    get_settings.cache_clear()
    eng = get_engine()
    yield eng


@pytest.fixture()
def schema(engine) -> Iterator[None]:
    """테스트마다 스키마를 새로 만든다. 마이그레이션 대신 모델 메타데이터를 쓴다."""
    from sqlalchemy import text

    from app.auth import models as _models  # noqa: F401  (모델 등록)
    from app.db import SCHEMA, Base
    from app.preview import models as _preview_models  # noqa: F401  (모델 등록)

    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        conn.execute(text(IDENTITY_DDL))
    Base.metadata.create_all(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture()
def session_factory(engine, schema):
    from app.db import get_session_factory

    return get_session_factory()


@pytest.fixture()
def identity(engine, schema):
    from app.auth.identity import build_read_only_engine, IdentityReader

    eng = build_read_only_engine(TEST_DATABASE_URL)
    yield IdentityReader(eng)
    eng.dispose()


@pytest.fixture()
def client(engine, schema) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
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
