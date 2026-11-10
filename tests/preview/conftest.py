"""MP-01 테스트 공통 설정.

테스트는 전용 로컬 테스트 DB만 사용한다. 대상 검사는 연결을 열기 전에
`_dbguard`에서 수행한다. 개발·운영 DB 이름이나 루프백이 아닌 주소는
파괴적 준비 단계에 도달하지 못한다.
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


@pytest.fixture(scope="session", autouse=True)
def _environment() -> Iterator[None]:
    # 연결을 열기 전에 대상부터 검사한다.
    assert_safe_test_database(TEST_DATABASE_URL)
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_ENV"] = "test"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    yield


@pytest.fixture()
def engine(_environment: None):
    from app.core.config import get_settings
    from app.db import get_engine, reset_engine

    reset_engine()
    get_settings.cache_clear()
    eng = get_engine()
    yield eng


@pytest.fixture()
def schema(engine) -> Iterator[None]:
    """테스트마다 스키마를 새로 만든다. 마이그레이션 대신 모델 메타데이터를 쓴다."""
    from sqlalchemy import text

    from app.auth import models as _models  # noqa: F401  (모델 등록)
    from app.db import Base

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(engine)
    yield
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))


@pytest.fixture()
def session_factory(engine, schema):
    from app.db import get_session_factory

    return get_session_factory()


@pytest.fixture()
def client(engine, schema) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _hash_for_fixture(password: str) -> str:
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


@pytest.fixture()
def make_user(session_factory):
    from app.auth.models import Role, User

    def _make(
        *,
        email: str | None = None,
        password: str = "correct-horse-battery-9",
        role: Role = Role.ADMIN,
        is_active: bool = True,
    ) -> dict:
        user = User(
            email=email or f"{uuid.uuid4().hex}@example.test",
            password_hash=_hash_for_fixture(password),
            role=role.value,
            is_active=is_active,
        )
        with session_factory() as session:
            session.add(user)
            session.commit()
            session.refresh(user)
            return {"id": user.id, "email": user.email, "password": password, "role": role.value}

    return _make
