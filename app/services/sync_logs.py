"""Persist and query short-lived worker sync logs."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session


RETENTION_DAYS = 7


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if started_at is None or finished_at is None:
        return None
    return max(0.0, (finished_at - started_at).total_seconds())


_UPSERT_WORKER_SYNC_LOG = (
    text(
        """
        INSERT INTO worker_sync_log (
            run_id, worker_name, status, total_units, completed_units,
            progress_percent, started_at, finished_at, duration_seconds,
            origin, result, error, logs
        )
        VALUES (
            :run_id, :worker_name, :status, :total_units, :completed_units,
            :progress_percent, :started_at, :finished_at, :duration_seconds,
            :origin, :result, :error, :logs
        )
        ON CONFLICT (run_id) DO UPDATE SET
            worker_name = EXCLUDED.worker_name,
            status = EXCLUDED.status,
            total_units = EXCLUDED.total_units,
            completed_units = EXCLUDED.completed_units,
            progress_percent = EXCLUDED.progress_percent,
            started_at = EXCLUDED.started_at,
            finished_at = EXCLUDED.finished_at,
            duration_seconds = EXCLUDED.duration_seconds,
            origin = EXCLUDED.origin,
            result = EXCLUDED.result,
            error = EXCLUDED.error,
            logs = EXCLUDED.logs
        """
    )
    .bindparams(bindparam("origin", type_=JSONB))
    .bindparams(bindparam("result", type_=JSONB))
    .bindparams(bindparam("logs", type_=JSONB))
)

_PRUNE_WORKER_SYNC_LOGS = text(
    """
    DELETE FROM worker_sync_log
    WHERE created_at < :cutoff
    """
)

_LIST_WORKER_SYNC_LOGS = text(
    """
    SELECT
        run_id, worker_name, status, total_units, completed_units,
        progress_percent, started_at, finished_at, duration_seconds,
        origin, result, error, logs, created_at
    FROM worker_sync_log
    WHERE worker_name = :worker_name
    ORDER BY created_at DESC
    LIMIT :limit
    """
)


def persist_worker_sync_log(session: Session, payload: dict[str, Any]) -> None:
    started_at = _parse_datetime(payload.get("started_at"))
    finished_at = _parse_datetime(payload.get("finished_at"))
    session.execute(
        _UPSERT_WORKER_SYNC_LOG,
        {
            "run_id": payload["id"],
            "worker_name": payload["worker_name"],
            "status": payload["status"],
            "total_units": int(payload.get("total_units") or 0),
            "completed_units": int(payload.get("completed_units") or 0),
            "progress_percent": float(payload.get("progress_percent") or 0),
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": _duration_seconds(started_at, finished_at),
            "origin": payload.get("origin"),
            "result": payload.get("result"),
            "error": payload.get("error"),
            "logs": payload.get("logs") or [],
        },
    )


def prune_worker_sync_logs(
    session: Session,
    *,
    retention_days: int = RETENTION_DAYS,
    now: datetime | None = None,
) -> int:
    resolved_now = now or datetime.now(timezone.utc)
    cutoff = resolved_now - timedelta(days=retention_days)
    result = session.execute(_PRUNE_WORKER_SYNC_LOGS, {"cutoff": cutoff})
    return int(result.rowcount or 0)


def list_worker_sync_logs(
    session: Session,
    *,
    worker_name: str = "daily-sync",
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = session.execute(
        _LIST_WORKER_SYNC_LOGS,
        {"worker_name": worker_name, "limit": limit},
    ).mappings().all()
    return [dict(row) for row in rows]
