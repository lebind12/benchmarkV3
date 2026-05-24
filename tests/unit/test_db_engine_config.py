from __future__ import annotations

import pytest

from app.core.config import Settings, database_engine_kwargs, normalize_database_url

pytestmark = pytest.mark.unit


def test_database_url_normalization_uses_psycopg3_driver():
    assert (
        normalize_database_url("postgresql://user:pass@localhost:5432/postgres")
        == "postgresql+psycopg://user:pass@localhost:5432/postgres"
    )
    assert (
        normalize_database_url("postgres://user:pass@localhost:5432/postgres")
        == "postgresql+psycopg://user:pass@localhost:5432/postgres"
    )
    assert (
        normalize_database_url("postgresql+psycopg://user:pass@localhost:5432/postgres")
        == "postgresql+psycopg://user:pass@localhost:5432/postgres"
    )


def test_database_engine_kwargs_are_conservative_for_session_pooler():
    settings = Settings(
        database_url="postgresql://user:pass@localhost:5432/postgres",
        db_pool_size=3,
        db_max_overflow=1,
        db_pool_timeout=7,
        db_pool_recycle=120,
    )

    assert database_engine_kwargs(settings) == {
        "future": True,
        "pool_pre_ping": True,
        "pool_size": 3,
        "max_overflow": 1,
        "pool_timeout": 7,
        "pool_recycle": 120,
    }


def test_make_engine_applies_database_pool_settings(monkeypatch):
    from app import db

    settings = Settings(
        database_url="postgresql://user:pass@localhost:5432/postgres",
        db_pool_size=3,
        db_max_overflow=1,
        db_pool_timeout=7,
        db_pool_recycle=120,
    )
    monkeypatch.setattr(db, "get_settings", lambda: settings)

    engine = db.make_engine()
    try:
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 1
        assert engine.pool._timeout == 7
        assert engine.pool._recycle == 120
    finally:
        engine.dispose()
