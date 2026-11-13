"""프리뷰 개발 저장소의 SQLAlchemy 엔진과 요청 단위 세션 (전용 이름공간).

원래 benchmark 앱의 `app.db`(`SessionLocal`/`get_db_session`, public 모델용)와
**다른 모듈**이다. 원래 앱의 `Base`와 이 `Base`를 합치지 않는다. 두 메타데이터가
섞이면 `create_all`/마이그레이션이 잘못된 스키마를 대상으로 삼는다.

연결은 원래 `DATABASE_URL` 하나이고 그 계정의 기존 전체 권한을 그대로 쓴다.
개발 저장은 `preview_dev` 스키마에만 쓰며 스키마는 항상 명시한다(전역 `search_path`
의존 없음). 기존 `public` 영역의 데이터·구조는 이 저장소가 만들거나 바꾸지 않는다.

계약(변경 금지): `get_db()`, `get_session_factory()`, `get_engine()`, `Base`,
`SCHEMA='preview_dev'`, `reset_engine()`.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import resolved_database_url
from app.preview.config import PreviewSettings, get_settings

# 개발 쓰기 영역. 기존 운영 객체와 분리된 스키마 이름이다.
SCHEMA = "preview_dev"

__all__ = [
    "SCHEMA",
    "Base",
    "get_db",
    "get_engine",
    "get_session_factory",
    "reset_engine",
]


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker[Session] | None = None


def _build(settings: PreviewSettings):
    settings.assert_local_database()
    engine = create_engine(
        resolved_database_url(),
        pool_pre_ping=True,
        future=True,
        # 개발 저장의 기본 스키마를 `preview_dev`로 고정한다. 스키마를 생략한 쿼리도
        # 개발 영역에만 떨어지게 하고, 기존 public 객체를 우연히 가리키지 않게 한다.
        # 연결 자체는 원래 계정·원래 권한 그대로이며 읽기 전용으로 제한하지 않는다.
        connect_args={"options": f"-c search_path={SCHEMA}"},
    )
    return engine, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_engine(settings: PreviewSettings | None = None):
    global _engine, _session_factory
    if _engine is None:
        _engine, _session_factory = _build(settings or get_settings())
    return _engine


def get_session_factory(settings: PreviewSettings | None = None) -> sessionmaker[Session]:
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
