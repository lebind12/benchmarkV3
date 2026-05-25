from __future__ import annotations

import time

import pytest

from app.services import worker_runs
from app.workers.daily_sync import LeagueSyncSpec
from app.workers.daily_sync.runner import DailySyncBatchResult

pytestmark = pytest.mark.unit


class _FakeAdvisoryLock:
    acquired = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def test_daily_sync_run_exposes_backend_logs_and_progress(monkeypatch):
    with worker_runs._lock:  # noqa: SLF001 - reset in-memory registry between tests
        worker_runs._runs.clear()  # noqa: SLF001

    def fake_load_configured_sync_specs(*, fallback_defaults=False):
        return [LeagueSyncSpec(league_external_id=39, seasons=(2025,))]

    def fake_run_backfill_batch(*, progress, specs, **kwargs):
        progress.log("daily-sync: fake worker entered")
        progress.add_total(2)
        progress.advance(message="daily-sync: unit one")
        progress.advance(message="daily-sync: unit two")
        return DailySyncBatchResult(specs=[spec.to_log_payload() for spec in specs])

    monkeypatch.setattr(worker_runs, "load_configured_sync_specs", fake_load_configured_sync_specs)
    monkeypatch.setattr(worker_runs, "run_backfill_batch", fake_run_backfill_batch)
    monkeypatch.setattr(worker_runs, "_DailySyncAdvisoryLock", _FakeAdvisoryLock)
    persisted = []
    monkeypatch.setattr(worker_runs, "_persist_finished_run", lambda run: persisted.append(run.payload()))

    started = worker_runs.start_daily_sync_run()
    run_id = started["id"]
    deadline = time.monotonic() + 2
    current = started
    while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = worker_runs.get_worker_run(run_id)

    assert current["status"] == "succeeded"
    assert current["completed_units"] == 2
    assert current["total_units"] == 2
    assert current["progress_percent"] == 100
    assert [line["message"] for line in current["logs"] if "unit" in line["message"]] == [
        "daily-sync: unit one",
        "daily-sync: unit two",
    ]
    assert persisted[0]["id"] == run_id
    assert persisted[0]["status"] == "succeeded"
    assert persisted[0]["origin"]["pid"]


def test_daily_sync_run_skips_when_distributed_lock_is_held(monkeypatch):
    with worker_runs._lock:  # noqa: SLF001 - reset in-memory registry between tests
        worker_runs._runs.clear()  # noqa: SLF001

    class _HeldAdvisoryLock:
        acquired = False

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    monkeypatch.setattr(worker_runs, "_DailySyncAdvisoryLock", _HeldAdvisoryLock)
    persisted = []
    monkeypatch.setattr(worker_runs, "_persist_finished_run", lambda run: persisted.append(run.payload()))

    started = worker_runs.start_daily_sync_run()
    run_id = started["id"]
    deadline = time.monotonic() + 2
    current = started
    while current["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.01)
        current = worker_runs.get_worker_run(run_id)

    assert current["status"] == "succeeded"
    assert current["result"] == {
        "skipped": True,
        "reason": "daily_sync_advisory_lock_held",
    }
    assert persisted[0]["result"]["skipped"] is True


def test_worker_run_set_total_keeps_progress_total_fixed():
    run = worker_runs.WorkerRun(id="fixed-total", worker_name="daily-sync")
    tracker = worker_runs.WorkerRunTracker(run, worker_runs._lock)  # noqa: SLF001

    tracker.set_total(2)
    tracker.advance()
    tracker.advance()
    tracker.advance()

    payload = run.payload()
    assert payload["total_units"] == 2
    assert payload["completed_units"] == 2
    assert payload["progress_percent"] == 100
