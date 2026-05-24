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


def _seed_league_team_player(conn, *, player_ext: int, goals: int):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug, current_season, is_active) "
            "VALUES (39, 'Premier League', 'League', 'premier-league', 2025, true) "
            "ON CONFLICT (external_id) DO UPDATE SET name=EXCLUDED.name RETURNING id"
        )
    ).scalar_one()
    team_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (:ext, :name, :slug) RETURNING id"
        ),
        {"ext": 50 + player_ext, "name": f"Team {player_ext}", "slug": f"team-{player_ext}"},
    ).scalar_one()
    player_id = conn.execute(
        text(
            "INSERT INTO player (external_id, name, slug, current_team_id) "
            "VALUES (:ext, :name, :slug, :team_id) RETURNING id"
        ),
        {
            "ext": player_ext,
            "name": f"Player {player_ext}",
            "slug": f"player-{player_ext}",
            "team_id": team_id,
        },
    ).scalar_one()
    conn.execute(text("INSERT INTO team_translation (team_id, name_ko) VALUES (:id, :ko)"),
                 {"id": team_id, "ko": f"팀 {player_ext}"})
    conn.execute(text("INSERT INTO player_translation (player_id, name_ko) VALUES (:id, :ko)"),
                 {"id": player_id, "ko": f"선수 {player_ext}"})
    conn.execute(text("INSERT INTO league_translation (league_id, name_ko) VALUES (:id, '프리미어리그') "
                      "ON CONFLICT (league_id) DO NOTHING"), {"id": league_id})
    conn.execute(
        text(
            "INSERT INTO player_season_stat "
            "(player_id, team_id, league_id, season_year, goals, assists, yellow_cards, "
            "red_cards, raw_stats) "
            "VALUES (:p, :t, :l, 2025, :g, 0, 0, 0, CAST(:raw AS jsonb))"
        ),
        {"p": player_id, "t": team_id, "l": league_id, "g": goals, "raw": "{}"},
    )


def test_htp_i01_orders_by_metric_and_assigns_rank(migrated_db):
    from app.services.home import list_home_top_players

    engine, _ = migrated_db
    with engine.begin() as conn:
        _seed_league_team_player(conn, player_ext=1001, goals=5)
        _seed_league_team_player(conn, player_ext=1002, goals=9)
        _seed_league_team_player(conn, player_ext=1003, goals=0)

    with Session(engine) as session:
        payload = list_home_top_players(session, league_id=39, metric="goals")

    assert payload["league"]["external_id"] == 39
    assert payload["metric"] == "goals"
    assert [row["player"]["external_id"] for row in payload["rows"]] == [1002, 1001]
    assert [row["rank"] for row in payload["rows"]] == [1, 2]


def test_htp_i02_zero_metric_rows_are_excluded(migrated_db):
    from app.services.home import list_home_top_players

    engine, _ = migrated_db
    with engine.begin() as conn:
        _seed_league_team_player(conn, player_ext=1004, goals=0)

    with Session(engine) as session:
        payload = list_home_top_players(session, league_id=39, metric="goals")

    assert payload["rows"] == []
