"""SQLAlchemy 엔진과 요청 단위 세션.

개발 쓰기 연결은 `preview_dev` 스키마만 대상으로 한다. 스키마는 항상 명시하고
전역 `search_path`에 의존하지 않는다. 기존 `public` 영역의 쓰기 권한은 DB 역할에
없다. 신원 읽기는 `app/auth/identity.py`가 별도 읽기 전용 엔진으로 처리한다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.db_target import normalize_driver

# 개발 쓰기 영역. 기존 운영 객체와 분리된 스키마 이름이다.
SCHEMA = "preview_dev"


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker[Session] | None = None


def _build(settings: Settings):
    settings.assert_local_database()
    engine = create_engine(
        normalize_driver(settings.database_url),
        pool_pre_ping=True,
        future=True,
        # 개발 연결의 기본 스키마를 고정한다. 스키마를 생략한 쿼리도 개발 영역에만
        # 떨어지게 하고, 기존 public 객체를 우연히 가리키지 않게 한다.
        connect_args={"options": f"-c search_path={SCHEMA}"},
    )
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
