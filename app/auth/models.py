"""관리자 접근의 데이터 구조.

사용자 신원·역할과 폐기 가능한 만료 세션 두 가지만 둔다. 세션 토큰은 원문을
저장하지 않고 해시만 보관한다. STREAMER는 ADMIN의 대체 권한이 아니다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, Enum):
    ADMIN = "admin"
    USER = "user"
    STREAMER = "streamer"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "preview_users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    sessions: Mapped[list[AdminSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value


class AdminSession(Base):
    """폐기 가능하고 만료되는 관리자 세션.

    `revoked_at`이 채워지면 이후 요청은 인증되지 않은 것으로 처리한다.
    """

    __tablename__ = "preview_admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("preview_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

    def is_live(self, now: datetime | None = None) -> bool:
        moment = now or _utcnow()
        return self.revoked_at is None and self.expires_at > moment
