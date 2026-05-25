"""ADMIN worker run registry.

The in-memory registry is only for polling this process. Scheduled daily-sync
execution is additionally guarded by a PostgreSQL advisory lock so other
processes cannot run the same sync concurrently.
"""
from __future__ import annotations

import os
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
from app.workers.daily_sync.runner import load_configured_sync_specs, run_backfill_batch


MAX_LOG_LINES = 1000
DAILY_SYNC_ADVISORY_LOCK_KEY = 202605240001


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _origin_payload() -> dict[str, Any]:
    keys = [
        "KOYEB_APP_NAME",
        "KOYEB_SERVICE_NAME",
        "KOYEB_SERVICE_ID",
        "KOYEB_INSTANCE_ID",
        "KOYEB_REGION",
        "KOYEB_DEPLOYMENT_ID",
        "HOSTNAME",
    ]
    env = {key: value for key in keys if (value := os.getenv(key))}
    return {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "env": env,
    }


@dataclass
class WorkerRun:
    id: str
    worker_name: str
    status: str = "queued"
    total_units: int = 0
    completed_units: int = 0
    total_units_fixed: bool = False
    logs: list[dict[str, str]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    origin: dict[str, Any] = field(default_factory=_origin_payload)
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def payload(self) -> dict[str, Any]:
        progress_percent = 0
        if self.total_units:
            progress_percent = min(100, round((self.completed_units / self.total_units) * 100, 2))
        return {
            "id": self.id,
            "worker_name": self.worker_name,
            "status": self.status,
            "total_units": self.total_units,
            "completed_units": self.completed_units,
            "progress_percent": progress_percent,
            "logs": list(self.logs),
            "result": self.result,
            "error": self.error,
            "origin": dict(self.origin),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class WorkerRunTracker:
    def __init__(self, run: WorkerRun, lock: threading.RLock) -> None:
        self._run = run
        self._lock = lock

    def log(self, message: str) -> None:
        with self._lock:
            self._run.logs.append({"ts": _now(), "message": message})
            if len(self._run.logs) > MAX_LOG_LINES:
                self._run.logs = self._run.logs[-MAX_LOG_LINES:]

    def add_total(self, amount: int) -> None:
        if amount <= 0:
            return
        with self._lock:
            self._run.total_units_fixed = False
            self._run.total_units += amount

    def set_total(self, amount: int) -> None:
        with self._lock:
            self._run.total_units_fixed = True
            self._run.total_units = max(0, amount)
            if self._run.completed_units > self._run.total_units:
                self._run.completed_units = self._run.total_units

    def advance(self, amount: int = 1, message: str | None = None) -> None:
        if amount <= 0:
            return
        with self._lock:
            self._run.completed_units += amount
            if self._run.completed_units > self._run.total_units:
                if self._run.total_units_fixed:
                    self._run.completed_units = self._run.total_units
                else:
                    self._run.total_units = self._run.completed_units
        if message:
            self.log(message)


_runs: dict[str, WorkerRun] = {}
_lock = threading.RLock()


def _serialize_run(run: WorkerRun) -> dict[str, Any]:
    with _lock:
        return run.payload()


def get_worker_run(run_id: str) -> dict[str, Any]:
    with _lock:
        run = _runs.get(run_id)
        if run is None:
            raise ValueError("worker_run_not_found")
        return run.payload()


def _running_run(worker_name: str) -> WorkerRun | None:
    for run in _runs.values():
        if run.worker_name == worker_name and run.status in {"queued", "running"}:
            return run
    return None


def _persist_finished_run(run: WorkerRun) -> None:
    from app import db
    from app.services import sync_logs

    with db.SessionLocal() as session:
        sync_logs.persist_worker_sync_log(session, run.payload())
        sync_logs.prune_worker_sync_logs(session)
        session.commit()


def _try_persist_finished_run(run: WorkerRun, tracker: WorkerRunTracker) -> None:
    try:
        _persist_finished_run(run)
    except Exception as exc:  # noqa: BLE001 - log persistence must not fail the worker
        tracker.log(f"daily-sync: log persistence failed: {exc}")


class _DailySyncAdvisoryLock:
    def __init__(self) -> None:
        self._engine = None
        self._connection = None
        self.acquired = False

    def __enter__(self) -> "_DailySyncAdvisoryLock":
        settings = get_settings()
        kwargs = {
            **database_engine_kwargs(settings),
            "pool_size": 1,
            "max_overflow": 0,
            "pool_timeout": min(settings.db_pool_timeout, 5),
        }
        self._engine = create_engine(
            normalize_database_url(settings.database_url),
            **kwargs,
        )
        self._connection = self._engine.connect()
        self.acquired = bool(
            self._connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": DAILY_SYNC_ADVISORY_LOCK_KEY},
            ).scalar_one()
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self.acquired and self._connection is not None:
                self._connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": DAILY_SYNC_ADVISORY_LOCK_KEY},
                )
        finally:
            if self._connection is not None:
                self._connection.close()
            if self._engine is not None:
                self._engine.dispose()


def start_daily_sync_run(
    *,
    fallback_defaults: bool = False,
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    fixture_limit: int | None = None,
    fail_on_errors: bool = False,
) -> dict[str, Any]:
    with _lock:
        running = _running_run("daily-sync")
        if running is not None:
            raise RuntimeError(running.id)
        run = WorkerRun(id=str(uuid4()), worker_name="daily-sync")
        _runs[run.id] = run

    tracker = WorkerRunTracker(run, _lock)

    def target() -> None:
        started = time.monotonic()
        with _lock:
            run.status = "running"
            run.started_at = _now()
        tracker.log(f"daily-sync: run started origin={run.origin}")
        try:
            with _DailySyncAdvisoryLock() as distributed_lock:
                if not distributed_lock.acquired:
                    with _lock:
                        run.result = {
                            "skipped": True,
                            "reason": "daily_sync_advisory_lock_held",
                        }
                        run.status = "succeeded"
                        run.finished_at = _now()
                    tracker.log("daily-sync: skipped because distributed lock is held")
                    _try_persist_finished_run(run, tracker)
                    return

                tracker.log(
                    f"daily-sync: acquired advisory lock key={DAILY_SYNC_ADVISORY_LOCK_KEY}"
                )
                specs = load_configured_sync_specs(fallback_defaults=fallback_defaults)
                tracker.log(f"daily-sync: loaded {len(specs)} configured specs")
                result = run_backfill_batch(
                    specs=specs,
                    include_details=include_details,
                    include_players=include_players,
                    include_standings=include_standings,
                    fixture_limit=fixture_limit,
                    progress=tracker,
                )
            payload = result.to_log_payload()
            with _lock:
                run.result = payload
                run.status = "failed" if result.has_errors else "succeeded"
                run.finished_at = _now()
            tracker.log(
                f"daily-sync: run finished status={run.status} duration={round(time.monotonic() - started, 2)}s"
            )
            _try_persist_finished_run(run, tracker)
        except Exception as exc:  # noqa: BLE001 - surface worker errors to ADMIN polling
            with _lock:
                run.status = "failed"
                run.error = str(exc)
                run.finished_at = _now()
            tracker.log(f"daily-sync: run failed: {exc}")
            _try_persist_finished_run(run, tracker)

    thread = threading.Thread(target=target, name=f"daily-sync-{run.id}", daemon=True)
    thread.start()
    return _serialize_run(run)
