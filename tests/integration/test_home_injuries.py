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
    env["PGOPTIONS"] = f"-c search_path={schema} {env.get('PGOPTIONS', '')}".strip()
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture()
def migrated_db(isolated_db, test_database_url):
    engine, schema = isolated_db
    result = _run_alembic(["upgrade", "head"], schema=schema, db_url=test_database_url)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head 실패\n{result.stdout}\n{result.stderr}")
    return engine, schema


def test_hi_i01_returns_current_season_injuries_with_expected_return(migrated_db):
    from app.services.home import list_home_injuries

    engine, _ = migrated_db
    with engine.begin() as conn:
        league = conn.execute(
            text(
                "INSERT INTO league (external_id, name, type, slug, current_season, is_active) "
                "VALUES (39, 'Premier League', 'League', 'premier-league', 2025, true) "
                "RETURNING id"
            )
        ).scalar_one()
        team = conn.execute(
            text(
                "INSERT INTO team (external_id, name, slug) "
                "VALUES (50, 'Manchester City', 'manchester-city') RETURNING id"
            )
        ).scalar_one()
        player = conn.execute(
            text(
                "INSERT INTO player (external_id, name, slug, current_team_id) "
                "VALUES (3001, 'Rodri', 'rodri', :team) RETURNING id"
            ),
            {"team": team},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO injury "
                "(player_id, team_id, league_id, season_year, type, raw_data, reported_at) "
                "VALUES (:p, :t, :l, 2025, '햄스트링', CAST(:raw AS jsonb), "
                "'2026-05-12T00:00:00Z')"
            ),
            {
                "p": player,
                "t": team,
                "l": league,
                "raw": '{"expected_return":"2026-06-01"}',
            },
        )

    with Session(engine) as session:
        payload = list_home_injuries(session)

    assert len(payload["items"]) == 1
    assert payload["items"][0]["injury_type"] == "햄스트링"
    assert payload["items"][0]["expected_return"] == "2026-06-01"
    assert payload["items"][0]["reported_at"] == "2026-05-12"
    assert payload["items"][0]["player"]["league"]["external_id"] == 39
