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


def _seed_base(conn):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season, is_active) "
            "VALUES (39, 'Premier League', 'League', 'premier-league', 2025, true) "
            "RETURNING id"
        )
    ).scalar_one()
    from_team = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (168, 'Bayer Leverkusen', 'leverkusen') RETURNING id"
        )
    ).scalar_one()
    to_team = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (40, 'Liverpool', 'liverpool') RETURNING id"
        )
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO team_season (team_id, league_id, season_year) "
            "VALUES (:team, :league, 2025)"
        ),
        {"team": to_team, "league": league_id},
    )
    player = conn.execute(
        text(
            "INSERT INTO player (external_id, name, slug, current_team_id) "
            "VALUES (2002, 'Florian Wirtz', 'florian-wirtz', :team) RETURNING id"
        ),
        {"team": to_team},
    ).scalar_one()
    return player, from_team, to_team


def test_ht_i01_returns_recent_resolved_transfers_in_target_scope(migrated_db):
    from app.services.home import list_home_transfers

    engine, _ = migrated_db
    with engine.begin() as conn:
        player, from_team, to_team = _seed_base(conn)
        conn.execute(
            text(
                "INSERT INTO transfer (player_id, transfer_date, type, from_team_id, to_team_id) "
                "VALUES (:p, '2026-05-08', '€120m', :f, :t), "
                "(:p, '2026-04-01', NULL, :f, :t), "
                "(:p, '2026-05-10', 'Free', NULL, :t)"
            ),
            {"p": player, "f": from_team, "t": to_team},
        )

    with Session(engine) as session:
        payload = list_home_transfers(session)

    assert len(payload["items"]) == 2
    assert payload["items"][0]["transfer_date"] == "2026-05-08"
    assert payload["items"][0]["fee"] == "€120m"
    assert payload["items"][0]["from_team"]["slug"] == "leverkusen"
    assert payload["items"][0]["to_team"]["slug"] == "liverpool"
