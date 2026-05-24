"""Integration tests for GET /api/v1/fixtures/{external_id}/statistics."""

from __future__ import annotations

import json
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


def _insert_league(conn):
    return conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season) "
            "VALUES (39, 'Premier League', 'League', 'premier-league', 2025) RETURNING id"
        )
    ).scalar_one()


def _insert_team(conn, *, external_id: int, name: str, slug: str):
    return conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug, country) "
            "VALUES (:external_id, :name, :slug, 'England') RETURNING id"
        ),
        {"external_id": external_id, "name": name, "slug": slug},
    ).scalar_one()


def _insert_fixture(
    conn,
    *,
    external_id: int,
    league_id: int,
    home_team_id: int,
    away_team_id: int,
    status_short: str = "FT",
):
    return conn.execute(
        text(
            "INSERT INTO fixture "
            "(external_id, league_id, season_year, home_team_id, away_team_id, kickoff_at, status_short) "
            "VALUES (:external_id, :league_id, 2025, :home_team_id, :away_team_id, "
            "'2026-05-13T19:00:00Z', :status_short) RETURNING id"
        ),
        {
            "external_id": external_id,
            "league_id": league_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "status_short": status_short,
        },
    ).scalar_one()


def test_statistics_i01_raw_api_football_jsonb_is_normalized(migrated_db, client):
    engine, _schema = migrated_db
    raw_statistics = [
        {
            "team": {"id": 40},
            "statistics": [
                {"type": "Ball Possession", "value": "58%"},
                {"type": "Total Shots", "value": 16},
                {"type": "Shots on Goal", "value": 7},
                {"type": "Total passes", "value": 540},
                {"type": "Passes %", "value": "88%"},
                {"type": "Corner Kicks", "value": 8},
                {"type": "Fouls", "value": 9},
                {"type": "Yellow Cards", "value": 1},
                {"type": "Red Cards", "value": 0},
                {"type": "Offsides", "value": 2},
            ],
        },
        {
            "team": {"id": 42},
            "statistics": [
                {"type": "Ball Possession", "value": "42%"},
                {"type": "Total Shots", "value": 11},
                {"type": "Shots on Goal", "value": 4},
                {"type": "Total passes", "value": 392},
                {"type": "Passes %", "value": "82%"},
                {"type": "Corner Kicks", "value": 5},
                {"type": "Fouls", "value": 12},
                {"type": "Yellow Cards", "value": 2},
                {"type": "Red Cards", "value": 1},
                {"type": "Offsides", "value": 3},
            ],
        },
    ]
    with engine.begin() as conn:
        league_id = _insert_league(conn)
        home = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool")
        away = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal")
        fixture_id = _insert_fixture(
            conn,
            external_id=1000001,
            league_id=league_id,
            home_team_id=home,
            away_team_id=away,
        )
        conn.execute(
            text(
                "INSERT INTO fixture_detail (fixture_id, statistics) "
                "VALUES (:fixture_id, CAST(:statistics AS JSONB))"
            ),
            {"fixture_id": fixture_id, "statistics": json.dumps(raw_statistics)},
        )

    response = client.get("/api/v1/fixtures/1000001/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["home"]["team_external_id"] == 40
    assert payload["home"]["possession"] == 58
    assert payload["home"]["shots_on_target"] == 7
    assert payload["home"]["passes_accuracy"] == 88
    assert payload["home"]["red"] == 0
    assert payload["away"]["team_external_id"] == 42
    assert payload["away"]["red"] == 1
    assert "possession_pct" not in payload["home"]


def test_statistics_i02_missing_statistics_row_returns_null_metrics(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(conn)
        home = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool")
        away = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal")
        _insert_fixture(
            conn,
            external_id=1000002,
            league_id=league_id,
            home_team_id=home,
            away_team_id=away,
            status_short="NS",
        )

    response = client.get("/api/v1/fixtures/1000002/statistics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["home"]["team_external_id"] == 40
    assert all(value is None for key, value in payload["home"].items() if key != "team_external_id")
    assert all(value is None for key, value in payload["away"].items() if key != "team_external_id")


def test_statistics_i03_unknown_fixture_returns_404(client):
    response = client.get("/api/v1/fixtures/999999/statistics")

    assert response.status_code == 404
