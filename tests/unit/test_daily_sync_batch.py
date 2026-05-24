from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.workers.daily_sync import default_league_sync_specs
from app.workers.daily_sync import runner
from app.workers.daily_sync.runner import DailySyncBatchResult, LeagueSyncFailure

pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[2]


def test_daily_sync_specs_add_world_cup_2026_after_default_leagues():
    specs = default_league_sync_specs(include_world_cup_2026=True)

    assert [spec.league_external_id for spec in specs] == [39, 2, 3, 48, 45, 1]
    assert [spec.seasons for spec in specs[:-1]] == [None, None, None, None, None]
    assert specs[-1].seasons == (2026,)


def test_daily_sync_specs_can_skip_world_cup_for_existing_default_flow():
    specs = default_league_sync_specs(include_world_cup_2026=False)

    assert [spec.league_external_id for spec in specs] == [39, 2, 3, 48, 45]


def test_daily_sync_batch_result_reports_failures_as_errors():
    result = DailySyncBatchResult(
        failures=[
            LeagueSyncFailure(
                league_external_id=1,
                seasons=[2026],
                error="api_football_request_failed",
            )
        ]
    )

    assert result.has_errors is True
    assert result.to_log_payload()["failures"][0]["league_external_id"] == 1


def test_sync_all_leagues_plan_only_does_not_touch_external_services():
    result = subprocess.run(
        [sys.executable, "-m", "app.workers.daily_sync.cli", "sync-all-leagues", "--plan-only"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "specs": [
            {
                "league_external_id": 39,
                "seasons": None,
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
            {
                "league_external_id": 2,
                "seasons": None,
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
            {
                "league_external_id": 3,
                "seasons": None,
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
            {
                "league_external_id": 48,
                "seasons": None,
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
            {
                "league_external_id": 45,
                "seasons": None,
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
            {
                "league_external_id": 1,
                "seasons": [2026],
                "include_details": True,
                "include_players": True,
                "include_standings": True,
                "fixture_limit": None,
            },
        ]
    }


def test_backfill_players_uses_league_season_endpoint(monkeypatch):
    class FakeSession:
        def commit(self):
            pass

        def rollback(self):
            pass

    class FakeClient:
        def __init__(self):
            self.calls = []
            self.calls_total = 0
            self.calls_failed = 0

        def response(self, path, **params):
            self.calls.append((path, params))
            self.calls_total += 1
            if path == "/leagues":
                return [
                    {
                        "league": {"id": 39, "name": "Premier League", "type": "League"},
                        "country": {"name": "England"},
                        "seasons": [{"year": 2025, "current": True}],
                    }
                ]
            raise AssertionError(f"unexpected response call: {path} {params}")

        def get(self, path, **params):
            self.calls.append((path, params))
            self.calls_total += 1
            if path == "/teams":
                return {"response": [{"team": {"id": 40, "name": "Liverpool"}}]}
            if path == "/fixtures":
                return {"response": []}
            assert path == "/players"
            assert params["league"] == 39
            assert params["season"] == 2025
            assert "team" not in params
            page = params["page"]
            player_id = 1000 + page
            return {
                "response": [
                    {
                        "player": {"id": player_id, "name": f"Player {player_id}"},
                        "statistics": [
                            {
                                "team": {"id": 40},
                                "league": {"id": 39, "season": 2025},
                                "games": {},
                            }
                        ],
                    }
                ],
                "paging": {"current": page, "total": 2},
            }

    class CaptureProgress:
        def __init__(self):
            self.total = None
            self.completed = 0
            self.logs = []

        def log(self, message):
            self.logs.append(message)

        def add_total(self, amount):
            self.total = (self.total or 0) + amount

        def set_total(self, amount):
            self.total = amount

        def advance(self, amount=1, message=None):
            self.completed += amount
            if message:
                self.logs.append(message)

    stored_current_team_ids = []
    monkeypatch.setattr(runner, "upsert_league", lambda *args, **kwargs: (1, [2025]))
    monkeypatch.setattr(runner, "upsert_team_entry", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "upsert_fixture_entry", lambda *args, **kwargs: None)
    monkeypatch.setattr(runner, "ensure_team_season_from_fixtures", lambda *args, **kwargs: None)

    def fake_upsert_player_entry(*args, current_team_external_id, **kwargs):
        stored_current_team_ids.append(current_team_external_id)
        return 1

    monkeypatch.setattr(runner, "upsert_player_entry", fake_upsert_player_entry)

    client = FakeClient()
    progress = CaptureProgress()
    result = runner.backfill_league(
        FakeSession(),
        client,
        league_external_id=39,
        seasons=[2025],
        include_details=False,
        include_players=True,
        include_standings=False,
        progress=progress,
    )

    player_calls = [params for path, params in client.calls if path == "/players"]
    assert player_calls == [
        {"league": 39, "season": 2025, "page": 1},
        {"league": 39, "season": 2025, "page": 2},
    ]
    assert stored_current_team_ids == [40, 40]
    assert progress.total == 5  # league catalog + teams + fixtures + 2 player pages
    assert any("Premier League (#39)" in message for message in progress.logs)
    assert result.seasons[0].player_pages_seen == 2
    assert result.seasons[0].player_rows_seen == 2
