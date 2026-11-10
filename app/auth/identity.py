"""기존 운영 계정(`public.app_user`) 읽기 전용 접근.

경계:
- 이 모듈은 `SELECT`만 실행한다. 연결은 `default_transaction_read_only=on`이고
  트랜잭션마다 statement timeout을 건다.
- 스키마는 항상 명시한다(`public.app_user`). 전역 `search_path`에 의존하지 않는다.
- 비밀번호 해시는 검증 입력으로만 쓰고 로그·응답·보고서에 담지 않는다.
- 기존 행을 갱신하지 않는다. 과거 구현의 `last_login_at` 갱신은 재현하지 않는다.

읽기 역할은 `public.app_user`에 `SELECT`만 가진 별도 계정이다. 같은 연결로
개발 세션을 쓰지 않는다(개발 세션 쓰기는 `app/db.py`의 별도 연결).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import BigInteger, Boolean, DateTime, Text, create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.db_target import normalize_driver

READ_ONLY_STATEMENT_TIMEOUT_MS = 5_000

__all__ = [
    "AppUserRow",
    "DUMMY_PASSWORD_HASH_FALLBACK",
    "IdentityReader",
    "IdentityRecord",
    "IdentityUser",
    "ProductionIdentityError",
    "build_read_only_engine",
    "get_identity_reader",
    "reset_identity_reader",
]


class _IdentityBase(DeclarativeBase):
    """기존 운영 테이블 매핑 전용 메타데이터.

    앱의 개발용 `Base`와 섞지 않는다. 이 메타데이터로 `create_all`을 호출하지
    않는다. 기존 테이블 구조를 만드는 것은 이 앱의 권한이 아니다.
    """


class AppUserRow(_IdentityBase):
    __tablename__ = "app_user"
    __table_args__ = {"schema": "public"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False)
    last_login_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class IdentityUser:
    """검증에 필요한 최소 신원 정보. 비밀번호 해시는 여기에 담지 않는다."""

    id: int
    email: str
    role: str
    is_active: bool


@dataclass(frozen=True)
class IdentityRecord:
    """내부용 조회 결과. 해시를 포함하지만 이 모듈 밖으로 내보내지 않는다.

    `__repr__`에서도 해시를 숨겨 예외 메시지·로그로 새지 않게 한다.
    """

    id: int
    email: str
    role: str
    is_active: bool
    password_hash: str

    def __repr__(self) -> str:  # pragma: no cover - 표현 확인용
        return (
            f"IdentityRecord(id={self.id!r}, email={self.email!r}, "
            f"role={self.role!r}, is_active={self.is_active!r}, password_hash=<redacted>)"
        )

    def public(self) -> IdentityUser:
        return IdentityUser(
            id=self.id, email=self.email, role=self.role, is_active=self.is_active
        )


class ProductionIdentityError(RuntimeError):
    """기존 계정 저장소에 접근할 수 없다."""


def _record(row: AppUserRow) -> IdentityRecord:
    return IdentityRecord(
        id=row.id,
        email=row.email,
        role=row.role,
        is_active=row.is_active,
        password_hash=row.password_hash,
    )


def _statement_timeout() -> text:
    return text(f"SET LOCAL statement_timeout = {READ_ONLY_STATEMENT_TIMEOUT_MS}")


class IdentityReader:
    """읽기 전용 신원 조회기."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _session(self) -> Session:
        return self._factory()

    def fetch_by_email(self, email: str) -> IdentityRecord | None:
        normalized = email.strip().lower()
        with self._session() as session:
            with session.begin():
                session.execute(_statement_timeout())
                row = session.scalar(
                    select(AppUserRow).where(func.lower(AppUserRow.email) == normalized)
                )
                return None if row is None else _record(row)

    def fetch_by_id(self, user_id: int) -> IdentityRecord | None:
        with self._session() as session:
            with session.begin():
                session.execute(_statement_timeout())
                row = session.get(AppUserRow, user_id)
                return None if row is None else _record(row)

    def count_rows(self) -> int:
        """연결·권한 확인용. 행 내용은 읽지 않는다."""
        with self._session() as session:
            with session.begin():
                session.execute(_statement_timeout())
                return int(session.scalar(select(func.count()).select_from(AppUserRow)) or 0)

    def dispose(self) -> None:
        self._engine.dispose()


def build_read_only_engine(url: str) -> Engine:
    """읽기 전용 계약을 연결 옵션으로 강제한다."""
    return create_engine(
        normalize_driver(url),
        pool_pre_ping=True,
        future=True,
        connect_args={"options": "-c default_transaction_read_only=on"},
    )


_reader: IdentityReader | None = None


def get_identity_reader(url: str) -> IdentityReader:
    global _reader
    if _reader is None:
        _reader = IdentityReader(build_read_only_engine(url))
    return _reader


def reset_identity_reader() -> None:
    global _reader
    if _reader is not None:
        _reader.dispose()
    _reader = None


# 미지원/손상 해시를 만났을 때 같은 비용의 검증에 쓸 값. 어떤 계정의 해시도 아니다.
DUMMY_PASSWORD_HASH_FALLBACK = (
    "pbkdf2_sha256$260000$"
    "AAAAAAAAAAAAAAAAAAAAAA$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
)
