"""Persisted broadcast momentum state copied from Redis."""
from __future__ import annotations

from sqlalchemy import BigInteger, DateTime, Identity, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BroadcastMomentumState(Base):
    __tablename__ = "broadcast_momentum_state"
    __table_args__ = (
        UniqueConstraint(
            "fixture_external_id",
            "redis_key_prefix",
            name="broadcast_momentum_state_fixture_prefix_key",
        ),
        Index("broadcast_momentum_state_fixture_idx", "fixture_external_id"),
        Index("broadcast_momentum_state_persisted_idx", "persisted_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    fixture_external_id: Mapped[int] = mapped_column(Integer, nullable=False)
    redis_key_prefix: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    last_state: Mapped[dict | None] = mapped_column(JSONB)
    samples: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    latest: Mapped[dict | None] = mapped_column(JSONB)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    latest_updated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    last_captured_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    persisted_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
