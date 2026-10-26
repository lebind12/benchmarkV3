"""Keep authenticated collection/cancellation semantics when adding the home hook."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services import management_runs
from app.workers import home_preview


@pytest.mark.parametrize(
    "failed,enabled,preview_failed,cancelled",
    [
        (False, True, False, False),
        (False, True, True, False),
        (True, True, False, False),
        (False, False, False, False),
        (False, True, False, True),
    ],
)
def test_management_commits_before_preview_and_preserves_collection_status(
    monkeypatch,
    failed,
    enabled,
    preview_failed,
    cancelled,
):
    settings = SimpleNamespace(
        api_football_key="fixture-only",
        api_football_host="fixture",
        api_football_requests_per_minute=60,
        api_football_concurrency=1,
        home_preview_enabled=enabled,
    )
    monkeypatch.setattr(management_runs, "get_settings", lambda: settings)
    tracker = MagicMock()
    if cancelled:
        tracker.check_cancelled.side_effect = management_runs.SyncCancelled
    monkeypatch.setattr(management_runs, "RunTracker", lambda payload: tracker)
    monkeypatch.setattr(management_runs, "ApiFootballClient", MagicMock())
    plan = SimpleNamespace(unit_count=lambda **kwargs: 1, detected_seasons=[2026, 2025])
    monkeypatch.setattr(management_runs, "measure_league_sync_plan", lambda *args, **kwargs: plan)
    monkeypatch.setattr(
        management_runs,
        "backfill_measured_league",
        lambda *args, **kwargs: SimpleNamespace(
            seasons=[SimpleNamespace(errors=["failed"] if failed else [])]
        ),
    )
    factory = MagicMock()
    store = factory.return_value.__enter__.return_value
    store.get.return_value = SimpleNamespace(league_id=1)
    from app.services import management

    monkeypatch.setattr(management, "prune_league_seasons", lambda *args: None)
    monkeypatch.setattr(management_runs.db, "SessionLocal", factory)
    calls = []

    def generate(session_factory, *, execute):
        calls.append((store.commit.called, execute, session_factory is factory))
        if preview_failed:
            raise RuntimeError("private preview provider details")
        return {"state": "finished", "results": [], "deferred": []}

    monkeypatch.setattr(home_preview, "run_cycle", generate)
    item = {
        "name": "Test",
        "league_id": 39,
        "season": 2026,
        "target_id": 1,
        "status": "queued",
        "options": {
            "include_details": False,
            "include_players": False,
            "include_standings": False,
            "fixture_limit": 1,
        },
        "stored_rows": 0,
        "saved": 0,
        "failed": 0,
        "pending": 0,
    }
    payload = {"id": "test-run", "mode": "refresh", "items": [item]}
    guard = MagicMock()
    management_runs.execute_run(payload, guard)
    assert len(calls) == int(enabled and not failed and not cancelled), (
        payload,
        tracker.log.call_args_list,
    )
    assert payload["status"] == ("cancelled" if cancelled else "failed" if failed else "succeeded")
    if calls:
        assert calls == [(True, True, True)]
        assert payload["home_preview"]["state"] == ("failed" if preview_failed else "finished")
        assert "private" not in str(payload)
    guard.__exit__.assert_called_once()
