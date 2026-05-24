"""Fixture-detail lineups endpoint integration tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


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


def _client_for_schema(monkeypatch, test_database_url: str, schema: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URL", test_database_url)
    monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")
    from app.main import app

    return TestClient(app)


def _seed_fixture_and_players(conn):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug) "
            "VALUES (39, 'Premier League', 'League', 'premier-league') RETURNING id"
        )
    ).scalar()
    home_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (40, 'Liverpool', 'liverpool-40') RETURNING id"
        )
    ).scalar()
    away_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (42, 'Arsenal', 'arsenal-42') RETURNING id"
        )
    ).scalar()
    conn.execute(
        text("INSERT INTO team_translation (team_id, name_ko, short_name_ko) VALUES (:id, '리버풀', '리버풀')"),
        {"id": home_id},
    )
    conn.execute(
        text("INSERT INTO team_translation (team_id, name_ko, short_name_ko) VALUES (:id, '아스널', '아스널')"),
        {"id": away_id},
    )
    for index in range(1, 31):
        team_id = home_id if index <= 15 else away_id
        player_id = conn.execute(
            text(
                "INSERT INTO player (external_id, name, slug, current_team_id) "
                "VALUES (:external_id, :name, :slug, :team_id) RETURNING id"
            ),
            {
                "external_id": 2000 + index,
                "name": f"Player {index}",
                "slug": f"player-{2000 + index}",
                "team_id": team_id,
            },
        ).scalar()
        conn.execute(
            text("INSERT INTO player_translation (player_id, name_ko) VALUES (:id, :name_ko)"),
            {"id": player_id, "name_ko": f"선수 {index}"},
        )
    fixture_id = conn.execute(
        text(
            "INSERT INTO fixture (external_id, league_id, season_year, home_team_id, "
            "away_team_id, kickoff_at, status_long, status_short, goals_home, goals_away) "
            "VALUES (1000001, :league, 2026, :home, :away, "
            "'2026-05-13T10:00:00+00:00', 'Match Finished', 'FT', 3, 1) RETURNING id"
        ),
        {"league": league_id, "home": home_id, "away": away_id},
    ).scalar()
    return fixture_id


def _lineup_payload():
    def player(index: int):
        return {
            "player": {
                "id": 2000 + index,
                "name": f"Player {index}",
                "number": index,
                "pos": "G" if index in (1, 16) else "M",
                "grid": "1:1" if index in (1, 16) else "3:2",
            }
        }

    return [
        {
            "team": {"id": 40, "name": "Liverpool"},
            "formation": "4-3-3",
            "coach": {"name": "Arne Slot"},
            "startXI": [player(index) for index in range(1, 12)],
            "substitutes": [player(index) for index in range(12, 16)],
        },
        {
            "team": {"id": 42, "name": "Arsenal"},
            "formation": "4-2-3-1",
            "coach": {"name": "Mikel Arteta"},
            "startXI": [player(index) for index in range(16, 27)],
            "substitutes": [player(index) for index in range(27, 31)],
        },
    ]


def test_lineups_i01_normalizes_jsonb_lineups(migrated_db, test_database_url, monkeypatch):
    engine, schema = migrated_db
    with engine.begin() as conn:
        fixture_id = _seed_fixture_and_players(conn)
        conn.execute(
            text(
                "INSERT INTO fixture_detail (fixture_id, lineups) "
                "VALUES (:fixture_id, CAST(:lineups AS jsonb))"
            ),
            {"fixture_id": fixture_id, "lineups": json.dumps(_lineup_payload())},
        )

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001/lineups")

    assert response.status_code == 200
    body = response.json()
    assert body["home"]["team"]["name_ko"] == "리버풀"
    assert body["home"]["formation"] == "4-3-3"
    assert body["home"]["coach"]["name"] == "Arne Slot"
    assert len(body["home"]["start_xi"]) == 11
    assert body["home"]["start_xi"][0]["player"]["name_ko"] == "선수 1"
    assert body["away"]["formation"] == "4-2-3-1"
    assert len(body["away"]["bench"]) == 4


def test_lineups_i02_existing_fixture_without_detail_returns_empty_shape(
    migrated_db, test_database_url, monkeypatch
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture_and_players(conn)

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001/lineups")

    assert response.status_code == 200
    body = response.json()
    assert body["home"]["formation"] is None
    assert body["home"]["start_xi"] == []
    assert body["home"]["bench"] == []
    assert body["away"]["start_xi"] == []


def test_lineups_i03_missing_fixture_returns_404(migrated_db, test_database_url, monkeypatch):
    _engine, schema = migrated_db

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000099/lineups")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"
