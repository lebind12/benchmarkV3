"""Persisted worker sync run logs with short retention."""
from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, Identity, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WorkerSyncLog(Base):
    __tablename__ = "worker_sync_log"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="worker_sync_log_status_check",
        ),
        Index("worker_sync_log_worker_created_idx", "worker_name", "created_at"),
        Index("worker_sync_log_status_idx", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    worker_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    completed_units: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    started_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    origin: Mapped[dict | None] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    logs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
