"""GET /api/v1/home/standings integration tests.

Runs against a temporary Postgres schema via `isolated_db`. No external service
is called. The service import is intentionally Red until be-dev implements it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

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
            f"{result.stdout}\n{result.stderr}"
        )
    return engine, schema


def _insert_league(
    conn,
    *,
    external_id: int,
    name: str,
    slug: str,
    current_season: int,
):
    league_id = conn.execute(
        text(
            "INSERT INTO league "
            "(external_id, name, type, slug, current_season, is_active) "
            "VALUES (:external_id, :name, :type, :slug, :season, true) "
            "RETURNING id"
        ),
        {
            "external_id": external_id,
            "name": name,
            "type": "League" if external_id == 39 else "Cup",
            "slug": slug,
            "season": current_season,
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO league_translation "
            "(league_id, name_ko, short_name_ko) "
            "VALUES (:id, :name_ko, :short_name_ko)"
        ),
        {"id": league_id, "name_ko": f"{name} KO", "short_name_ko": slug[:3].upper()},
    )
    return league_id


def _insert_team(
    conn,
    *,
    external_id: int,
    name: str,
    slug: str,
    name_ko: str | None,
):
    team_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug, logo_url) "
            "VALUES (:external_id, :name, :slug, :logo_url) RETURNING id"
        ),
        {
            "external_id": external_id,
            "name": name,
            "slug": slug,
            "logo_url": f"https://example.test/{slug}.png",
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO team_translation (team_id, name_ko, short_name_ko) "
            "VALUES (:id, :name_ko, :short_name_ko)"
        ),
        {"id": team_id, "name_ko": name_ko, "short_name_ko": name_ko},
    )
    return team_id


def _insert_standing(
    conn,
    *,
    league_id: int,
    team_id: int,
    season_year: int,
    rank: int,
    points: int,
):
    conn.execute(
        text(
            "INSERT INTO standings "
            "(league_id, season_year, team_id, rank, points, played, win, draw, "
            "loss, goals_for, goals_against) "
            "VALUES (:league_id, :season_year, :team_id, :rank, :points, "
            ":played, :win, :draw, :loss, :goals_for, :goals_against)"
        ),
        {
            "league_id": league_id,
            "season_year": season_year,
            "team_id": team_id,
            "rank": rank,
            "points": points,
            "played": 10,
            "win": 7,
            "draw": 1,
            "loss": 2,
            "goals_for": 21,
            "goals_against": 9,
        },
    )


def _seed_standings_data(conn):
    epl_id = _insert_league(
        conn,
        external_id=39,
        name="Premier League",
        slug="premier-league",
        current_season=2025,
    )
    fa_id = _insert_league(
        conn,
        external_id=45,
        name="FA Cup",
        slug="fa-cup",
        current_season=2025,
    )
    arsenal_id = _insert_team(
        conn,
        external_id=42,
        name="Arsenal",
        slug="arsenal-42",
        name_ko="아스널",
    )
    liverpool_id = _insert_team(
        conn,
        external_id=40,
        name="Liverpool",
        slug="liverpool-40",
        name_ko=None,
    )

    # Insert out of order; service must return rank ASC.
    _insert_standing(
        conn,
        league_id=epl_id,
        team_id=arsenal_id,
        season_year=2025,
        rank=2,
        points=68,
    )
    _insert_standing(
        conn,
        league_id=epl_id,
        team_id=liverpool_id,
        season_year=2025,
        rank=1,
        points=72,
    )
    # Previous season row must not leak into current season response.
    _insert_standing(
        conn,
        league_id=epl_id,
        team_id=liverpool_id,
        season_year=2024,
        rank=10,
        points=40,
    )
    return {"epl_id": epl_id, "fa_id": fa_id}


def test_hs_i01_i02_i03_current_season_ordering_and_fallback(migrated_db):
    from app.services.home import get_home_standings

    engine, _schema = migrated_db
    with engine.begin() as conn:
        _seed_standings_data(conn)

    with Session(engine) as session:
        payload = get_home_standings(session, league_id=39)

    assert payload["league"]["external_id"] == 39
    assert payload["season"] == 2025
    assert [row["rank"] for row in payload["rows"]] == [1, 2]
    assert [row["points"] for row in payload["rows"]] == [72, 68]
    assert payload["rows"][0]["team"]["name_ko"] is None
    assert payload["rows"][0]["team"]["name"] == "Liverpool"


def test_hs_i04_empty_cup_standings_returns_league_and_season(migrated_db):
    from app.services.home import get_home_standings

    engine, _schema = migrated_db
    with engine.begin() as conn:
        _seed_standings_data(conn)

    with Session(engine) as session:
        payload = get_home_standings(session, league_id=45)

    assert payload["league"]["external_id"] == 45
    assert payload["season"] == 2025
    assert payload["rows"] == []
