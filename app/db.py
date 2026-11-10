"""SQLAlchemy 엔진과 요청 단위 세션."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker[Session] | None = None


def _build(settings: Settings):
    settings.assert_local_database()
    engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_engine(settings: Settings | None = None):
    global _engine, _session_factory
    if _engine is None:
        _engine, _session_factory = _build(settings or get_settings())
    return _engine


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    get_engine(settings)
    assert _session_factory is not None
    return _session_factory


def get_db() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """테스트가 다른 DB를 가리킬 때 엔진을 버린다."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
