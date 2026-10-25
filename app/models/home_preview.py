"""Dedicated home preview storage; no changes to broadcast storage."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HomePreviewSnapshot(Base):
    __tablename__ = "home_preview_snapshot"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fixture.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("fixture_id", "fingerprint", name="home_preview_snapshot_input_uq"),
    )


class HomePreviewVersion(Base):
    __tablename__ = "home_preview_version"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fixture.id", ondelete="CASCADE"), index=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("home_preview_snapshot.id", ondelete="CASCADE")
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint("fixture_id", "fingerprint", name="home_preview_version_input_uq"),
    )


class HomePreviewPublication(Base):
    __tablename__ = "home_preview_publication"
    fixture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fixture.id", ondelete="CASCADE"), primary_key=True
    )
    version_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("home_preview_version.id", ondelete="SET NULL")
    )
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    refresh_state: Mapped[str] = mapped_column(
        Text, nullable=False, default="idle", server_default="idle"
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "refresh_state IN ('idle','queued','running','failed')",
            name="home_preview_refresh_state_ck",
        ),
    )


class HomePreviewAttempt(Base):
    __tablename__ = "home_preview_attempt"
    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    fixture_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("fixture.id", ondelete="CASCADE"), index=True
    )
    slot: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(36), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usage: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("fixture_id", "slot", name="home_preview_attempt_slot_uq"),
        CheckConstraint(
            "state IN ('running','succeeded','failed','interrupted','unchanged','deferred')",
            name="home_preview_attempt_state_ck",
        ),
    )
