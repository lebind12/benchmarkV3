"""Fixture-detail match endpoint integration tests.

Uses the shared isolated schema fixture. No external services are called.
"""

from __future__ import annotations

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


def _seed_base_fixture(conn, *, status_short="FT", goals_home=3, goals_away=1):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug) "
            "VALUES (39, 'Premier League', 'League', 'premier-league') RETURNING id"
        )
    ).scalar()
    conn.execute(
        text(
            "INSERT INTO league_translation (league_id, name_ko, short_name_ko) "
            "VALUES (:id, '프리미어리그', 'EPL')"
        ),
        {"id": league_id},
    )
    venue_id = conn.execute(
        text(
            "INSERT INTO venue (external_id, name, city) "
            "VALUES (500, 'Anfield', 'Liverpool') RETURNING id"
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
    player_id = conn.execute(
        text(
            "INSERT INTO player (external_id, name, slug, current_team_id) "
            "VALUES (1001, 'Mohamed Salah', 'mohamed-salah-1001', :team) RETURNING id"
        ),
        {"team": home_id},
    ).scalar()
    conn.execute(
        text("INSERT INTO player_translation (player_id, name_ko, short_name_ko) VALUES (:id, '모하메드 살라', '살라')"),
        {"id": player_id},
    )
    fixture_id = conn.execute(
        text(
            "INSERT INTO fixture (external_id, league_id, season_year, round, home_team_id, "
            "away_team_id, venue_id, referee, timezone, kickoff_at, status_long, status_short, "
            "goals_home, goals_away) VALUES (1000001, :league, 2026, '32라운드', :home, "
            ":away, :venue, 'J. Pratt', 'UTC', '2026-05-13T10:00:00+00:00', "
            "'Match Finished', :status, :gh, :ga) RETURNING id"
        ),
        {
            "league": league_id,
            "home": home_id,
            "away": away_id,
            "venue": venue_id,
            "status": status_short,
            "gh": goals_home,
            "ga": goals_away,
        },
    ).scalar()
    return fixture_id


def test_match_i01_reads_joined_match_from_db(migrated_db, test_database_url, monkeypatch):
    engine, schema = migrated_db
    with engine.begin() as conn:
        fixture_id = _seed_base_fixture(conn)
        conn.execute(
            text(
                "INSERT INTO fixture_detail (fixture_id, events) "
                "VALUES (:fixture_id, CAST(:events AS jsonb))"
            ),
            {
                "fixture_id": fixture_id,
                "events": (
                    '[{"time":{"elapsed":23,"extra":null},"team":{"id":40},'
                    '"player":{"id":1001,"name":"Mohamed Salah"},'
                    '"assist":null,"type":"Goal","detail":"Normal Goal"}]'
                ),
            },
        )

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001")

    assert response.status_code == 200
    body = response.json()
    assert body["league"]["name_ko"] == "프리미어리그"
    assert body["home"]["name_ko"] == "리버풀"
    assert body["away"]["name_ko"] == "아스널"
    assert body["venue"] == {"name": "Anfield", "city": "Liverpool"}
    assert body["goal_events"][0]["scorer"]["name_ko"] == "모하메드 살라"


def test_match_i02_missing_fixture_returns_404(migrated_db, test_database_url, monkeypatch):
    _engine, schema = migrated_db

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000099")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"


def test_match_i03_ns_fixture_returns_null_scores_and_empty_goal_events(
    migrated_db, test_database_url, monkeypatch
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_base_fixture(conn, status_short="NS", goals_home=None, goals_away=None)

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001")

    assert response.status_code == 200
    body = response.json()
    assert body["status_short"] == "NS"
    assert body["goals_home"] is None
    assert body["goals_away"] is None
    assert body["goal_events"] == []
