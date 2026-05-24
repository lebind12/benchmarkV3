"""Integration tests for GET /api/v1/fixtures/{external_id}/h2h.

Uses an isolated Postgres schema and overrides the endpoint DB session dependency to
avoid prod schema access.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_alembic(args: list[str], schema: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
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
            f"alembic upgrade head failed (schema={schema})\n{result.stdout}\n{result.stderr}"
        )
    return engine, schema


@pytest.fixture(scope="function")
def client(migrated_db):
    engine, _schema = migrated_db
    from app.api.v1 import fixture_detail_analytics as analytics
    from app.main import app

    def override_session():
        with Session(engine) as session:
            yield session

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[analytics.get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _insert_league(conn, *, external_id=39, name="Premier League", slug="premier-league"):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season) "
            "VALUES (:external_id, :name, 'League', :slug, 2025) RETURNING id"
        ),
        {"external_id": external_id, "name": name, "slug": slug},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO league_translation (league_id, name_ko, short_name_ko) "
            "VALUES (:league_id, :name_ko, :short_name_ko)"
        ),
        {"league_id": league_id, "name_ko": "프리미어 리그", "short_name_ko": "EPL"},
    )
    return league_id


def _insert_team(conn, *, external_id: int, name: str, slug: str, name_ko: str):
    team_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug, country) "
            "VALUES (:external_id, :name, :slug, 'England') RETURNING id"
        ),
        {"external_id": external_id, "name": name, "slug": slug},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO team_translation (team_id, name_ko, short_name_ko) "
            "VALUES (:team_id, :name_ko, :short_name_ko)"
        ),
        {"team_id": team_id, "name_ko": name_ko, "short_name_ko": name_ko},
    )
    return team_id


def _insert_fixture(
    conn,
    *,
    external_id: int,
    league_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff_at: str = "2026-05-13T19:00:00Z",
    status_short: str = "FT",
):
    return conn.execute(
        text(
            "INSERT INTO fixture "
            "(external_id, league_id, season_year, home_team_id, away_team_id, kickoff_at, status_short) "
            "VALUES (:external_id, :league_id, 2025, :home_team_id, :away_team_id, :kickoff_at, :status_short) "
            "RETURNING id"
        ),
        {
            "external_id": external_id,
            "league_id": league_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "kickoff_at": kickoff_at,
            "status_short": status_short,
        },
    ).scalar_one()


def _insert_h2h(
    conn,
    *,
    external_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff_at: str,
    status_short: str = "FT",
    goals_home: int = 1,
    goals_away: int = 0,
):
    conn.execute(
        text(
            "INSERT INTO h2h_fixture "
            "(external_id, home_team_id, away_team_id, league_external_id, league_name, "
            "season_year, kickoff_at, status_short, goals_home, goals_away) "
            "VALUES (:external_id, :home_team_id, :away_team_id, 39, 'Premier League', "
            "2025, :kickoff_at, :status_short, :goals_home, :goals_away)"
        ),
        {
            "external_id": external_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "kickoff_at": kickoff_at,
            "status_short": status_short,
            "goals_home": goals_home,
            "goals_away": goals_away,
        },
    )


def test_h2h_i01_pair_query_sorts_excludes_current_and_non_finished(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(conn)
        liverpool = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool", name_ko="리버풀")
        arsenal = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal", name_ko="아스널")
        chelsea = _insert_team(conn, external_id=49, name="Chelsea", slug="chelsea", name_ko="첼시")
        _insert_fixture(
            conn,
            external_id=1000001,
            league_id=league_id,
            home_team_id=liverpool,
            away_team_id=arsenal,
        )
        _insert_h2h(conn, external_id=999001, home_team_id=arsenal, away_team_id=liverpool, kickoff_at="2025-12-21T15:00:00Z", goals_home=1, goals_away=2)
        _insert_h2h(conn, external_id=999002, home_team_id=liverpool, away_team_id=arsenal, kickoff_at="2025-08-19T15:00:00Z", goals_home=1, goals_away=1)
        _insert_h2h(conn, external_id=1000001, home_team_id=liverpool, away_team_id=arsenal, kickoff_at="2026-05-13T19:00:00Z")
        _insert_h2h(conn, external_id=999999, home_team_id=liverpool, away_team_id=arsenal, kickoff_at="2026-01-01T15:00:00Z", status_short="NS")
        _insert_h2h(conn, external_id=888888, home_team_id=liverpool, away_team_id=chelsea, kickoff_at="2025-12-31T15:00:00Z")

    response = client.get("/api/v1/fixtures/1000001/h2h?limit=5")

    assert response.status_code == 200
    rows = response.json()["h2h"]
    assert [row["external_id"] for row in rows] == [999001, 999002]
    assert all(row["status_short"] == "FT" for row in rows)
    assert rows[0]["home"]["external_id"] == 42
    assert rows[0]["away"]["name_ko"] == "리버풀"
    assert rows[0]["league"]["short_name_ko"] == "EPL"


def test_h2h_i03_empty_pair_returns_empty_array(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(conn)
        home = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool", name_ko="리버풀")
        away = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal", name_ko="아스널")
        _insert_fixture(
            conn,
            external_id=1000002,
            league_id=league_id,
            home_team_id=home,
            away_team_id=away,
        )

    response = client.get("/api/v1/fixtures/1000002/h2h")

    assert response.status_code == 200
    assert response.json() == {"h2h": []}


def test_h2h_i04_unknown_fixture_returns_404(client):
    response = client.get("/api/v1/fixtures/999999/h2h")

    assert response.status_code == 404
