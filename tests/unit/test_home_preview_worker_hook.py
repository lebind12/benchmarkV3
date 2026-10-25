import time
from types import SimpleNamespace

import pytest

from app.services import worker_runs
from app.workers import home_preview
from tests.unit.test_admin_worker_runs import _FakeAdvisoryLock


@pytest.mark.parametrize(
    "sync_failed,enabled,provider_failed",
    [(False, True, False), (True, True, False), (False, False, False), (False, True, True)],
)
def test_successful_collection_only_hook_preserves_collection_result(
    monkeypatch, sync_failed, enabled, provider_failed
):
    with worker_runs._lock:
        worker_runs._runs.clear()
    monkeypatch.setattr(worker_runs, "_DailySyncAdvisoryLock", _FakeAdvisoryLock)
    monkeypatch.setattr(
        worker_runs, "get_settings", lambda: SimpleNamespace(home_preview_enabled=enabled)
    )
    monkeypatch.setattr(worker_runs, "load_configured_sync_specs", lambda **kwargs: [])
    monkeypatch.setattr(
        worker_runs,
        "run_backfill_batch",
        lambda **kwargs: SimpleNamespace(
            has_errors=sync_failed, to_log_payload=lambda: {"collected": True}
        ),
    )
    monkeypatch.setattr(worker_runs, "_persist_finished_run", lambda run: None)
    calls = []

    def generate(factory, **kwargs):
        calls.append(kwargs)
        if provider_failed:
            raise RuntimeError("sensitive_provider_detail")
        return {"state": "finished", "results": [], "deferred": []}

    monkeypatch.setattr(home_preview, "run_cycle", generate)
    started = worker_runs.start_daily_sync_run()
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        run = worker_runs.get_worker_run(started["id"])
        if run["status"] not in ("queued", "running"):
            break
        time.sleep(0.01)
    assert run["status"] == ("failed" if sync_failed else "succeeded")
    assert len(calls) == int(enabled and not sync_failed)
    if calls:
        assert calls[0]["execute"] is True
        assert run["result"]["home_preview"]["state"] == (
            "failed" if provider_failed else "finished"
        )
    assert "sensitive_provider_detail" not in str(run)
