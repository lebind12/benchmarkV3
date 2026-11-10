"""MP-01 테스트 공통 설정.

테스트는 격리된 로컬 PostgreSQL만 사용한다. 운영/클라우드 DB로 향하는 URL은
수집 단계에서 실패시켜, 테스트가 조용히 다른 DB를 건드리지 않게 한다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

TEST_DATABASE_URL = os.environ.get(
    "PREVIEW_TEST_DATABASE_URL",
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test",
)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _assert_local(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.startswith("postgresql") is False:
        raise RuntimeError(f"tests require a PostgreSQL URL, got scheme {parsed.scheme!r}")
    if parsed.hostname not in LOOPBACK_HOSTS and os.environ.get("PREVIEW_ALLOW_NONLOCAL_DB") != "1":
        raise RuntimeError(
            f"tests refuse non-loopback database host {parsed.hostname!r}; "
            "MP-01 tests run against isolated local PostgreSQL only"
        )


@pytest.fixture(scope="session", autouse=True)
def _environment() -> Iterator[None]:
    _assert_local(TEST_DATABASE_URL)
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_ENV"] = "test"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    yield


@pytest.fixture()
def engine(_environment: None):
    from app.db import get_engine, reset_engine
    from app.core.config import get_settings

    reset_engine()
    get_settings.cache_clear()
    eng = get_engine()
    yield eng


@pytest.fixture()
def schema(engine) -> Iterator[None]:
    """테스트마다 스키마를 새로 만든다. 마이그레이션 대신 모델 메타데이터를 쓴다."""
    from app.db import Base
    import app.auth.models  # noqa: F401  (모델 등록)

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
    """테스트가 구현의 해시 함수에 의존하지 않도록 같은 알고리즘을 직접 쓴다."""
    from argon2 import PasswordHasher

    return PasswordHasher().hash(password)


@pytest.fixture()
def make_user(session_factory):
    """활성 상태와 역할을 지정해 테스트 사용자를 만든다. 비밀번호는 호출자가 정한다."""
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
