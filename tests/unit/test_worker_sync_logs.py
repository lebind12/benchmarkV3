from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services import sync_logs

pytestmark = pytest.mark.unit


class _FakeResult:
    def __init__(self, rowcount: int = 0) -> None:
        self.rowcount = rowcount


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def execute(self, statement, params=None):
        self.calls.append((str(statement), params or {}))
        return _FakeResult(rowcount=3)


def test_persist_worker_sync_log_extracts_queryable_fields():
    session = _FakeSession()
    payload = {
        "id": "run-1",
        "worker_name": "daily-sync",
        "status": "failed",
        "total_units": 10,
        "completed_units": 8,
        "progress_percent": 80.0,
        "started_at": "2026-05-24T10:00:00+00:00",
        "finished_at": "2026-05-24T10:00:12+00:00",
        "result": {"has_errors": True},
        "error": None,
        "logs": [{"ts": "2026-05-24T10:00:01+00:00", "message": "started"}],
    }

    sync_logs.persist_worker_sync_log(session, payload)

    _, params = session.calls[0]
    assert params["run_id"] == "run-1"
    assert params["worker_name"] == "daily-sync"
    assert params["status"] == "failed"
    assert params["duration_seconds"] == 12.0
    assert params["result"] == {"has_errors": True}
    assert params["logs"][0]["message"] == "started"


def test_prune_worker_sync_logs_uses_seven_day_cutoff():
    session = _FakeSession()
    now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)

    deleted = sync_logs.prune_worker_sync_logs(session, now=now)

    assert deleted == 3
    _, params = session.calls[0]
    assert params["cutoff"] == datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)
