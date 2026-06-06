"""GET /api/v1/broadcast/fixtures/{external_id}/overlay integration tests.

Uses the shared isolated schema fixture and fixed API-Football JSON. These tests
are Red until the broadcast overlay router/service/dependency hooks exist.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.integration


class FakeUser:
    role = "ADMIN"
    user_id = 1


class FakeCache:
    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self.store = dict(initial or {})
        self.writes: list[tuple[str, Any, int | None]] = []

    def get_json(self, key: str) -> Any:
        return self.store.get(key)

    def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self.store[key] = value
        self.writes.append((key, value, ttl_seconds))

    def get(self, key: str) -> Any:
        return self.get_json(key)

    def set(self, key: str, value: Any, ex: int | None = None) -> None:
        self.set_json(key, value, ex)

    def setex(self, key: str, ttl_seconds: int, value: Any) -> None:
        self.set_json(key, value, ttl_seconds)


class FakeApiFootballClient:
    def __init__(self, fixture_payload: dict[str, Any] | None = None) -> None:
        self.fixture_payload = fixture_payload or {}
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_fixture(self, external_id: int) -> Any:
        self.calls.append(("get_fixture", (external_id,), {}))
        return self.fixture_payload.get("fixture")

    def get_events(self, external_id: int) -> Any:
        self.calls.append(("get_events", (external_id,), {}))
        return self.fixture_payload.get("events", [])

    def get_lineups(self, external_id: int) -> Any:
        self.calls.append(("get_lineups", (external_id,), {}))
        return self.fixture_payload.get("lineups", [])

    def get_statistics(self, external_id: int) -> Any:
        self.calls.append(("get_statistics", (external_id,), {}))
        return self.fixture_payload.get("statistics", [])

    def get_players(self, external_id: int) -> Any:
        self.calls.append(("get_players", (external_id,), {}))
        return self.fixture_payload.get("players", [])

    def __getattr__(self, name: str):
        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            return self.fixture_payload.get(name, [])

        return method


class FailingApiFootballClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        from app.workers.daily_sync.api import ApiFootballError

        def method(*args, **kwargs):
            self.calls.append((name, args, kwargs))
            raise ApiFootballError("upstream unavailable")

        return method


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _api_fixture_path() -> Path:
    return _project_root() / "tests/fixtures/api_football/broadcast_overlay_live_1000001.json"


def _run_alembic(args: list[str], schema: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["SQLALCHEMY_DATABASE_URL"] = db_url
    existing = env.get("PGOPTIONS", "")
    env["PGOPTIONS"] = f"-c search_path={schema} {existing}".strip()
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture(scope="function")
def migrated_db(isolated_db, test_database_url):
    engine, schema = isolated_db
    result = _run_alembic(["upgrade", "head"], schema=schema, db_url=test_database_url)
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head failed (schema={schema})\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return engine, schema


def _load_api_fixture() -> dict[str, Any]:
    return json.loads(_api_fixture_path().read_text(encoding="utf-8"))


def _insert_team(conn, *, external_id: int, name: str, slug: str, code: str) -> int:
    team_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug, code, logo_url) "
            "VALUES (:external_id, :name, :slug, :code, :logo_url) RETURNING id"
        ),
        {
            "external_id": external_id,
            "name": name,
            "slug": slug,
            "code": code,
            "logo_url": f"https://example.test/{slug}.png",
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO team_translation (team_id, name_ko, short_name_ko) "
            "VALUES (:id, :name_ko, :short_name_ko)"
        ),
        {"id": team_id, "name_ko": f"{name} KO", "short_name_ko": code},
    )
    return team_id


def _seed_fixture(conn, *, status_short: str = "2H", with_detail: bool = True) -> None:
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season, logo_url) "
            "VALUES (39, 'Premier League', 'League', 'premier-league', 2025, "
            "'https://example.test/epl.png') RETURNING id"
        )
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO league_translation (league_id, name_ko, short_name_ko) "
            "VALUES (:id, 'Premier League KO', 'EPL')"
        ),
        {"id": league_id},
    )
    home_id = _insert_team(
        conn,
        external_id=40,
        name="Liverpool",
        slug="liverpool-40",
        code="LIV",
    )
    away_id = _insert_team(
        conn,
        external_id=42,
        name="Arsenal",
        slug="arsenal-42",
        code="ARS",
    )
    fixture_id = conn.execute(
        text(
            "INSERT INTO fixture (external_id, league_id, season_year, home_team_id, "
            "away_team_id, kickoff_at, status_long, status_short, status_elapsed, "
            "goals_home, goals_away) "
            "VALUES (1000001, :league_id, 2025, :home_id, :away_id, "
            "'2026-05-24T10:00:00+00:00', :status_long, :status_short, 63, 2, 1) "
            "RETURNING id"
        ),
        {
            "league_id": league_id,
            "home_id": home_id,
            "away_id": away_id,
            "status_long": "Match Finished" if status_short == "FT" else "Second Half",
            "status_short": status_short,
        },
    ).scalar_one()
    if with_detail:
        conn.execute(
            text(
                "INSERT INTO fixture_detail (fixture_id, events, statistics, lineups, players) "
                "VALUES (:fixture_id, CAST(:events AS jsonb), CAST(:statistics AS jsonb), "
                "CAST(:lineups AS jsonb), CAST(:players AS jsonb))"
            ),
            {
                "fixture_id": fixture_id,
                "events": json.dumps(_load_api_fixture()["events"]),
                "statistics": json.dumps(_load_api_fixture()["statistics"]),
                "lineups": json.dumps(_load_api_fixture()["lineups"]),
                "players": json.dumps(_load_api_fixture()["players"]),
            },
        )


@contextmanager
def _configured_client(
    monkeypatch,
    test_database_url: str,
    schema: str,
    *,
    api_client: FakeApiFootballClient,
    cache: FakeCache,
) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URL", test_database_url)
    monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")

    from app.api.v1 import broadcast as broadcast_api
    from app.main import app

    missing = [
        name
        for name in (
            "get_broadcast_current_user",
            "get_broadcast_api_football_client",
            "get_broadcast_cache",
        )
        if not hasattr(broadcast_api, name)
    ]
    assert not missing, f"broadcast overlay integration hooks missing: {', '.join(missing)}"

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[broadcast_api.get_broadcast_current_user] = lambda: FakeUser()
    app.dependency_overrides[broadcast_api.get_broadcast_api_football_client] = (
        lambda: api_client
    )
    app.dependency_overrides[broadcast_api.get_broadcast_cache] = lambda: cache
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_bo_i01_live_cache_miss_aggregates_fixed_api_payload(
    migrated_db,
    test_database_url,
    monkeypatch,
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture(conn, status_short="2H")
    api_client = FakeApiFootballClient(_load_api_fixture())
    cache = FakeCache()

    with _configured_client(
        monkeypatch,
        test_database_url,
        schema,
        api_client=api_client,
        cache=cache,
    ) as client:
        response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 200
    body = response.json()
    assert body["fixture"]["status_short"] == "2H"
    assert body["fixture"]["goals_home"] == 2
    assert body["lineups"][0]["players"][0]["short_name_ko"]
    assert body["statistics"][0]["type"] == "possession"
    assert body["events"][-1]["kind"] == "substitution"
    assert any(key.endswith(":overlay") for key, _value, _ttl in cache.writes)


def test_bo_i02_cache_hit_avoids_api_football_calls(
    migrated_db,
    test_database_url,
    monkeypatch,
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture(conn, status_short="2H")
    cached_payload = {
        "fixture": {"external_id": 1000001, "status_short": "2H"},
        "lineups": [],
        "statistics": [],
        "events": [],
        "polling": {
            "interval_seconds": 10,
            "cache_hit": True,
            "cache_ttl_seconds": 8,
            "generated_at": "2026-05-24T00:00:00Z",
        },
    }
    api_client = FakeApiFootballClient(_load_api_fixture())
    cache = FakeCache({"broadcast:fixture:1000001:overlay": cached_payload})

    with _configured_client(
        monkeypatch,
        test_database_url,
        schema,
        api_client=api_client,
        cache=cache,
    ) as client:
        response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 200
    assert response.json()["polling"]["cache_hit"] is True
    assert api_client.calls == []


def test_bo_i07_finished_fixture_uses_db_fallback_without_api_call(
    migrated_db,
    test_database_url,
    monkeypatch,
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture(conn, status_short="FT")
    api_client = FakeApiFootballClient(_load_api_fixture())
    cache = FakeCache()

    with _configured_client(
        monkeypatch,
        test_database_url,
        schema,
        api_client=api_client,
        cache=cache,
    ) as client:
        response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 200
    body = response.json()
    assert body["fixture"]["status_short"] == "FT"
    assert body["polling"]["interval_seconds"] >= 30
    assert api_client.calls == []


def test_bo_i08_upstream_failure_without_db_detail_returns_502(
    migrated_db,
    test_database_url,
    monkeypatch,
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture(conn, status_short="2H", with_detail=False)
    api_client = FailingApiFootballClient()
    cache = FakeCache()

    with _configured_client(
        monkeypatch,
        test_database_url,
        schema,
        api_client=api_client,
        cache=cache,
    ) as client:
        response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 502
    assert response.json()["detail"] == "broadcast_upstream_unavailable"
    assert api_client.calls
