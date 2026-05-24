"""GET /api/v1/home/fixtures integration tests.

Runs against a temporary Postgres schema via `isolated_db`. No external service
is called. The service import is intentionally Red until be-dev implements it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timezone
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


def _insert_league(conn, *, external_id: int, name: str, slug: str, current_season: int):
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


def _insert_fixture(
    conn,
    *,
    external_id: int,
    league_id: int,
    season_year: int,
    kickoff_at: datetime,
    home_team_id: int | None,
    away_team_id: int | None,
):
    conn.execute(
        text(
            "INSERT INTO fixture "
            "(external_id, league_id, season_year, kickoff_at, status_short, "
            "home_team_id, away_team_id, goals_home, goals_away) "
            "VALUES (:external_id, :league_id, :season_year, :kickoff_at, :status_short, "
            ":home_team_id, :away_team_id, :goals_home, :goals_away)"
        ),
        {
            "external_id": external_id,
            "league_id": league_id,
            "season_year": season_year,
            "kickoff_at": kickoff_at,
            "status_short": "NS",
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "goals_home": None,
            "goals_away": None,
        },
    )


def _seed_fixture_data(conn):
    epl_id = _insert_league(
        conn,
        external_id=39,
        name="Premier League",
        slug="premier-league",
        current_season=2025,
    )
    ucl_id = _insert_league(
        conn,
        external_id=2,
        name="UEFA Champions League",
        slug="champions-league",
        current_season=2025,
    )
    home_id = _insert_team(
        conn,
        external_id=33,
        name="Manchester United",
        slug="manchester-united-33",
        name_ko="맨체스터 유나이티드",
    )
    away_id = _insert_team(
        conn,
        external_id=40,
        name="Liverpool",
        slug="liverpool-40",
        name_ko=None,
    )

    # 2026-05-14 00:30 KST, inside date=2026-05-14.
    _insert_fixture(
        conn,
        external_id=7001,
        league_id=epl_id,
        season_year=2025,
        kickoff_at=datetime(2026, 5, 13, 15, 30, tzinfo=timezone.utc),
        home_team_id=home_id,
        away_team_id=away_id,
    )
    # 2026-05-15 00:00 KST, exclusive upper bound for date=2026-05-14.
    _insert_fixture(
        conn,
        external_id=7002,
        league_id=epl_id,
        season_year=2025,
        kickoff_at=datetime(2026, 5, 14, 15, 0, tzinfo=timezone.utc),
        home_team_id=home_id,
        away_team_id=away_id,
    )
    # Same KST day but different league.
    _insert_fixture(
        conn,
        external_id=7003,
        league_id=ucl_id,
        season_year=2025,
        kickoff_at=datetime(2026, 5, 13, 16, 0, tzinfo=timezone.utc),
        home_team_id=home_id,
        away_team_id=away_id,
    )
    # Cup/draw placeholder shape is not supported by the home summary.
    _insert_fixture(
        conn,
        external_id=7004,
        league_id=epl_id,
        season_year=2025,
        kickoff_at=datetime(2026, 5, 13, 17, 0, tzinfo=timezone.utc),
        home_team_id=None,
        away_team_id=away_id,
    )


def test_hf_i01_i02_i03_kst_day_league_filter_and_fallback(migrated_db):
    from app.services.home import list_home_fixtures

    engine, _schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture_data(conn)

    with Session(engine) as session:
        payload = list_home_fixtures(
            session,
            league_id=39,
            period="day",
            date=date(2026, 5, 14),
        )

    assert [item["external_id"] for item in payload["items"]] == [7001]
    item = payload["items"][0]
    assert item["league"]["external_id"] == 39
    assert item["home"]["name_ko"] == "맨체스터 유나이티드"
    assert item["away"]["name_ko"] is None
    assert item["away"]["name"] == "Liverpool"
    assert payload["filters_applied"] == {"period": "day", "league_id": 39}


def test_hf_i04_placeholder_rows_are_excluded(migrated_db):
    from app.services.home import list_home_fixtures

    engine, _schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture_data(conn)

    with Session(engine) as session:
        payload = list_home_fixtures(
            session,
            league_id=None,
            period="day",
            date=date(2026, 5, 14),
        )

    assert 7004 not in [item["external_id"] for item in payload["items"]]


def test_hf_i05_empty_result_echoes_filters(migrated_db):
    from app.services.home import list_home_fixtures

    engine, _schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture_data(conn)

    with Session(engine) as session:
        payload = list_home_fixtures(
            session,
            league_id=39,
            period="day",
            date=date(2026, 5, 20),
        )

    assert payload == {
        "items": [],
        "filters_applied": {"period": "day", "league_id": 39},
    }
