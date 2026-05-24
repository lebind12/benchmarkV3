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


def _seed_stat(conn, *, player_ext: int, score: int, active: bool = True):
    league_ext = 39 if active else 999
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season, is_active) "
            "VALUES (:ext, :name, 'League', :slug, 2025, :active) "
            "ON CONFLICT (external_id) DO UPDATE SET is_active=EXCLUDED.is_active RETURNING id"
        ),
        {
            "ext": league_ext,
            "name": "Premier League" if active else "Inactive League",
            "slug": "premier-league" if active else "inactive-league",
            "active": active,
        },
    ).scalar_one()
    team_id = conn.execute(
        text("INSERT INTO team (external_id, name, slug) VALUES (:e, :n, :s) RETURNING id"),
        {"e": 5000 + player_ext, "n": f"Team {player_ext}", "s": f"team-{player_ext}"},
    ).scalar_one()
    player_id = conn.execute(
        text(
            "INSERT INTO player (external_id, name, slug, current_team_id) "
            "VALUES (:e, :n, :s, :t) RETURNING id"
        ),
        {"e": player_ext, "n": f"Player {player_ext}", "s": f"player-{player_ext}", "t": team_id},
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO player_season_stat "
            "(player_id, team_id, league_id, season_year, goals, assists, raw_stats) "
            "VALUES (:p, :t, :l, 2025, :g, :a, CAST(:raw AS jsonb))"
        ),
        {"p": player_id, "t": team_id, "l": league_id, "g": score, "a": 0, "raw": "{}"},
    )


def test_hhp_i01_scores_sort_desc_limit_and_filters_inactive(migrated_db):
    from app.services.home import list_home_hot_players

    engine, _ = migrated_db
    with engine.begin() as conn:
        for offset, score in enumerate([10, 9, 8, 7, 6, 5], start=1):
            _seed_stat(conn, player_ext=2000 + offset, score=score)
        _seed_stat(conn, player_ext=2999, score=99, active=False)
        _seed_stat(conn, player_ext=2888, score=0)

    with Session(engine) as session:
        payload = list_home_hot_players(session)

    assert len(payload["items"]) == 5
    assert [item["score"] for item in payload["items"]] == [10, 9, 8, 7, 6]
    assert all(item["player"]["external_id"] != 2999 for item in payload["items"])
