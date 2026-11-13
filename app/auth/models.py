"""관리자 접근의 데이터 구조.

개발 세션은 같은 DB의 `preview_dev` 스키마에만 둔다. 기존 운영 계정 원장
(`public.app_user`)은 읽기 전용이며 이 앱이 만들거나 바꾸지 않는다. 세션 토큰은
원문을 저장하지 않고 해시만 보관한다. STREAMER는 ADMIN의 대체 권한이 아니다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import BigInteger, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.preview.db import SCHEMA, Base


class Role(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"
    STREAMER = "STREAMER"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdminSession(Base):
    """폐기 가능하고 만료되는 관리자 세션.

    `revoked_at`이 채워지면 이후 요청은 인증되지 않은 것으로 처리한다.
    `user_id`는 기존 `public.app_user.id`를 가리키지만 FK를 걸지 않는다. 기존
    테이블에 제약을 추가하지 않는다는 경계를 지키기 위해서다.
    """

    __tablename__ = "preview_admin_sessions"
    __table_args__ = {"schema": SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def is_live(self, now: datetime | None = None) -> bool:
        moment = now or _utcnow()
        return self.revoked_at is None and self.expires_at > moment
