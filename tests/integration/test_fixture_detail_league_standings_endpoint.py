"""Integration tests for GET /api/v1/fixtures/{external_id}/league-standings."""

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


def _insert_league(
    conn,
    *,
    external_id: int,
    name: str,
    slug: str,
    league_type: str = "League",
    name_ko: str | None = None,
    short_name_ko: str | None = None,
):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season) "
            "VALUES (:external_id, :name, :league_type, :slug, 2025) RETURNING id"
        ),
        {"external_id": external_id, "name": name, "league_type": league_type, "slug": slug},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO league_translation (league_id, name_ko, short_name_ko) "
            "VALUES (:league_id, :name_ko, :short_name_ko)"
        ),
        {"league_id": league_id, "name_ko": name_ko, "short_name_ko": short_name_ko},
    )
    return league_id


def _insert_team(
    conn,
    *,
    external_id: int,
    name: str,
    slug: str,
    name_ko: str | None = None,
    short_name_ko: str | None = None,
):
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
        {"team_id": team_id, "name_ko": name_ko, "short_name_ko": short_name_ko},
    )
    return team_id


def _insert_fixture(conn, *, external_id: int, league_id: int, home_team_id: int, away_team_id: int):
    conn.execute(
        text(
            "INSERT INTO fixture "
            "(external_id, league_id, season_year, home_team_id, away_team_id, kickoff_at, status_short) "
            "VALUES (:external_id, :league_id, 2025, :home_team_id, :away_team_id, "
            "'2026-05-13T19:00:00Z', 'FT')"
        ),
        {
            "external_id": external_id,
            "league_id": league_id,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    )


def _insert_standing(
    conn,
    *,
    league_id: int,
    team_id: int,
    rank: int,
    points: int,
    group_name: str | None = None,
):
    conn.execute(
        text(
            "INSERT INTO standings "
            "(league_id, season_year, team_id, group_name, rank, points, played, win, draw, loss, "
            "goals_for, goals_against, goals_diff, form) "
            "VALUES (:league_id, 2025, :team_id, :group_name, :rank, :points, 32, 20, 7, 5, "
            ":goals_for, :goals_against, :goals_diff, 'WWDLW')"
        ),
        {
            "league_id": league_id,
            "team_id": team_id,
            "group_name": group_name,
            "rank": rank,
            "points": points,
            "goals_for": 60 + rank,
            "goals_against": 30,
            "goals_diff": 30 + rank,
        },
    )


def test_league_standings_i01_epl_table_sorted_and_highlighted(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(
            conn,
            external_id=39,
            name="Premier League",
            slug="premier-league",
            name_ko="프리미어 리그",
            short_name_ko="EPL",
        )
        liverpool = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool", name_ko="리버풀", short_name_ko="리버풀")
        arsenal = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal", name_ko="아스널", short_name_ko="아스널")
        city = _insert_team(conn, external_id=50, name="Manchester City", slug="man-city", name_ko="맨체스터 시티", short_name_ko="맨시티")
        _insert_fixture(conn, external_id=1000001, league_id=league_id, home_team_id=liverpool, away_team_id=arsenal)
        _insert_standing(conn, league_id=league_id, team_id=city, rank=1, points=72)
        _insert_standing(conn, league_id=league_id, team_id=liverpool, rank=2, points=70)
        _insert_standing(conn, league_id=league_id, team_id=arsenal, rank=3, points=68)

    response = client.get("/api/v1/fixtures/1000001/league-standings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["league"]["external_id"] == 39
    assert payload["league"]["short_name_ko"] == "EPL"
    assert payload["season"] == 2025
    assert payload["group_name"] is None
    assert payload["highlighted_team_ids"] == [40, 42]
    assert [row["rank"] for row in payload["rows"]] == [1, 2, 3]
    assert [row["team"]["external_id"] for row in payload["rows"]] == [50, 40, 42]


def test_league_standings_i02_group_stage_returns_only_fixture_group(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(
            conn,
            external_id=2,
            name="UEFA Champions League",
            slug="champions-league",
            league_type="Cup",
            name_ko="챔피언스리그",
            short_name_ko="UCL",
        )
        home = _insert_team(conn, external_id=100, name="Team A1", slug="team-a1", name_ko="A1")
        away = _insert_team(conn, external_id=101, name="Team A2", slug="team-a2", name_ko="A2")
        other_a = _insert_team(conn, external_id=102, name="Team A3", slug="team-a3", name_ko="A3")
        other_b = _insert_team(conn, external_id=201, name="Team B1", slug="team-b1", name_ko="B1")
        _insert_fixture(conn, external_id=1000007, league_id=league_id, home_team_id=home, away_team_id=away)
        _insert_standing(conn, league_id=league_id, team_id=home, rank=1, points=12, group_name="Group A")
        _insert_standing(conn, league_id=league_id, team_id=away, rank=2, points=10, group_name="Group A")
        _insert_standing(conn, league_id=league_id, team_id=other_a, rank=3, points=6, group_name="Group A")
        _insert_standing(conn, league_id=league_id, team_id=other_b, rank=1, points=12, group_name="Group B")

    response = client.get("/api/v1/fixtures/1000007/league-standings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_name"] == "Group A"
    assert payload["highlighted_team_ids"] == [100, 101]
    team_ids = [row["team"]["external_id"] for row in payload["rows"]]
    assert team_ids == [100, 101, 102]
    assert 201 not in team_ids


def test_league_standings_i03_tournament_without_rows_returns_empty_payload(migrated_db, client):
    engine, _schema = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(
            conn,
            external_id=48,
            name="League Cup",
            slug="carabao-cup",
            league_type="Cup",
            name_ko="카라바오컵",
            short_name_ko="카라바오컵",
        )
        home = _insert_team(conn, external_id=40, name="Liverpool", slug="liverpool", name_ko="리버풀")
        away = _insert_team(conn, external_id=42, name="Arsenal", slug="arsenal", name_ko="아스널")
        _insert_fixture(conn, external_id=1000006, league_id=league_id, home_team_id=home, away_team_id=away)

    response = client.get("/api/v1/fixtures/1000006/league-standings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["group_name"] is None
    assert payload["highlighted_team_ids"] == [40, 42]


def test_league_standings_i04_unknown_fixture_returns_404(client):
    response = client.get("/api/v1/fixtures/999999/league-standings")

    assert response.status_code == 404
