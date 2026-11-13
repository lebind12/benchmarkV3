"""Database session helpers.

원래 benchmark 앱의 public 모델(`app.models`)용 연결이다. 프리뷰 개발 저장소
(`preview_dev`)는 별도 모듈 `app.preview.db`가 소유하며, 두 `Base`를 합치지 않는다.

계약(원래 앱 유지): `make_engine()`, `engine`, `SessionLocal`, `get_db_session()`.

**자격 증명 기준은 원래 `DATABASE_URL` 하나다.** 경기·홈·일반 조회, 계정 조회
(로그인·refresh·`current_user` → `/me`·ADMIN 판정), 프리뷰 저장이 모두 같은 값으로
연결한다. 그 계정의 기존 전체 읽기·쓰기 권한을 그대로 쓴다. 강제 읽기 전용 연결
옵션이나 계정 전용 축소 역할로 분기하지 않는다.

연결 대상 확인은 `app.preview.config` 계약(`assert_local_database`, 비루프백은
명시 플래그)을 그대로 쓴다. 설정이 없으면 대체 DSN을 만들지 않고 실패한다.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import Depends, HTTPException
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import (
    MissingDatabaseUrl,
    configured_database_url,
    database_engine_kwargs,
    get_settings,
    normalize_database_url,
    resolved_database_url,
)


class DatabaseConnectionUnavailable(HTTPException):
    """DB 연결을 열 수 없다.

    로그인 성공이나 다른 역할 우회로 바꾸지 않는다. 연결 실패는 503으로 그대로
    알린다(빈 성공 응답으로 감추지 않는다).
    """

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=503, detail=detail)


def _missing_target_engine(settings) -> Engine:
    """원래 `DATABASE_URL`이 없을 때의 엔진.

    앱 import를 깨지 않기 위해 엔진 객체는 만들되, **어떤 연결 시도도** 원래 설정
    누락으로 실패하게 한다. 자리표시자 서버에 붙거나 다른 DSN으로 대체하지 않는다.
    """
    from app.core.config import PLACEHOLDER_DATABASE_URL

    def _refuse() -> None:
        raise MissingDatabaseUrl(
            "DATABASE_URL is not set (the placeholder default is not a connection "
            "target); set the original benchmark DATABASE_URL"
        )

    kwargs = database_engine_kwargs(settings)
    # NullPool does not accept pool sizing options.
    for key in ("pool_size", "max_overflow", "pool_timeout"):
        kwargs.pop(key, None)
    return create_engine(
        PLACEHOLDER_DATABASE_URL,
        creator=_refuse,
        poolclass=NullPool,
        **kwargs,
    )


def make_engine() -> Engine:
    settings = get_settings()
    url = configured_database_url(settings)
    if url is None:
        return _missing_target_engine(settings)
    return create_engine(
        normalize_database_url(url),
        **database_engine_kwargs(settings),
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def make_auth_engine() -> Engine:
    """계정 조회용 엔진.

    원래 `DATABASE_URL`과 그 계정의 기존 권한을 그대로 쓴다. 계정 읽기 전용 역할·
    별도 DSN·강제 읽기 전용 옵션을 새로 걸지 않는다(과거 제안은 폐기됐다).

    대상 검사만 `app.preview.config` 계약을 재사용한다. 설정이 없으면 대체 DSN으로
    넘어가지 않고 실패한다.
    """
    from app.preview.config import get_settings as get_preview_settings

    preview = get_preview_settings()
    try:
        preview.assert_identity_database()
        url = resolved_database_url(get_settings())
    except RuntimeError as exc:  # 확정 불가·비루프백 미동의·미설정은 연결 전에 멈춘다.
        raise DatabaseConnectionUnavailable(str(exc)) from exc
    return create_engine(
        url,
        **database_engine_kwargs(get_settings()),
    )


_auth_engine: Engine | None = None
_auth_session_factory: sessionmaker[Session] | None = None


def get_auth_session_factory() -> sessionmaker[Session]:
    global _auth_engine, _auth_session_factory
    if _auth_session_factory is None:
        _auth_engine = make_auth_engine()
        _auth_session_factory = sessionmaker(
            bind=_auth_engine, autoflush=False, autocommit=False, future=True
        )
    return _auth_session_factory


def reset_auth_engine() -> None:
    """계정 조회 연결을 다음 요청에서 설정 기준으로 다시 만든다."""
    global _auth_engine, _auth_session_factory
    if _auth_engine is not None:
        _auth_engine.dispose()
    _auth_engine = None
    _auth_session_factory = None


@contextmanager
def _account_session(base: Session | None) -> Iterator[Session]:
    """계정 조회 세션 하나를 연다.

    넘어온 `base` 세션(같은 요청의 `get_db_session`)이 있으면 그대로 쓴다. 없으면
    같은 원래 `DATABASE_URL`의 세션을 새로 연다. 어느 쪽이든 자격 증명과 권한은
    동일하다. 연결 실패는 인증 판정 전에 503으로 드러낸다(로그인 성공으로 감추지
    않는다).
    """
    if base is not None:
        try:
            base.connection()
        except (SQLAlchemyError, MissingDatabaseUrl) as exc:
            raise DatabaseConnectionUnavailable(
                "DB 연결에 실패했습니다. 원래 DATABASE_URL 설정과 대상을 확인하세요."
            ) from exc
        yield base
        return

    with SessionLocal() as session:
        try:
            session.connection()
        except (SQLAlchemyError, MissingDatabaseUrl) as exc:
            raise DatabaseConnectionUnavailable(
                "DB 연결에 실패했습니다. 원래 DATABASE_URL 설정과 대상을 확인하세요."
            ) from exc
        yield session


def get_auth_db_session(
    base: Session = Depends(get_db_session),
) -> Iterator[Session]:
    """계정 조회용 요청 세션 (FastAPI 의존성).

    `get_db_session`과 **같은 세션 객체**를 돌려준다. 계정 조회와 경기·홈 조회가
    같은 연결·같은 계정 권한을 쓰므로 연결 수·커밋 동작이 원래와 같다.
    """
    with _account_session(base) as session:
        yield session


def reset_engine() -> None:
    """검사·기동 환경을 바꿀 때 모듈 수준 엔진을 다시 만든다."""
    global engine, SessionLocal
    engine.dispose()
    reset_auth_engine()
    engine = make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def describe_target() -> dict[str, object]:
    """기동 점검용 연결 요약. **비밀값은 담지 않는다**(호스트·DB·읽기전용 여부만).

    계정 조회도 같은 자격 증명을 쓰므로 `auth_connection`은 항상 `database_url`이다.
    """
    from sqlalchemy.engine import make_url

    url = resolved_database_url(get_settings())
    parsed = make_url(url)
    return {
        "driver": parsed.drivername,
        "host": parsed.host,
        "port": parsed.port,
        "database": parsed.database,
        "read_only": False,
        "auth_connection": "database_url",
        "shared_connection": True,
    }
