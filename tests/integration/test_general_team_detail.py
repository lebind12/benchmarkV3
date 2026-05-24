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


def _insert_league(conn, *, external_id: int, name: str, slug: str) -> int:
    return conn.execute(
        text(
            """
            INSERT INTO league (external_id, name, type, slug, current_season, is_active)
            VALUES (:external_id, :name, 'League', :slug, 2025, true)
            RETURNING id
            """
        ),
        {"external_id": external_id, "name": name, "slug": slug},
    ).scalar_one()


def _insert_stat(
    conn,
    *,
    player_id: int,
    team_id: int,
    league_id: int,
    season: int,
    position: str,
    appearances: int,
    goals: int,
    assists: int,
) -> None:
    conn.execute(
        text(
            """
            INSERT INTO player_season_stat (
                player_id, team_id, league_id, season_year, position,
                appearances, goals, assists, raw_stats
            )
            VALUES (
                :player_id, :team_id, :league_id, :season, :position,
                :appearances, :goals, :assists, CAST(:raw AS jsonb)
            )
            """
        ),
        {
            "player_id": player_id,
            "team_id": team_id,
            "league_id": league_id,
            "season": season,
            "position": position,
            "appearances": appearances,
            "goals": goals,
            "assists": assists,
            "raw": "{}",
        },
    )


def test_team_detail_squad_aggregates_player_rows_across_active_current_competitions(migrated_db):
    from app.services.general import get_team

    engine, _ = migrated_db
    with engine.begin() as conn:
        league_id = _insert_league(conn, external_id=39, name="Premier League", slug="premier-league")
        cup_id = _insert_league(conn, external_id=45, name="FA Cup", slug="fa-cup")
        old_id = conn.execute(
            text(
                """
                INSERT INTO league (external_id, name, type, slug, current_season, is_active)
                VALUES (999, 'Old League', 'League', 'old-league', 2024, true)
                RETURNING id
                """
            )
        ).scalar_one()
        inactive_id = conn.execute(
            text(
                """
                INSERT INTO league (external_id, name, type, slug, current_season, is_active)
                VALUES (1000, 'Inactive Cup', 'Cup', 'inactive-cup', 2025, false)
                RETURNING id
                """
            )
        ).scalar_one()
        team_id = conn.execute(
            text(
                """
                INSERT INTO team (external_id, name, slug, country, founded)
                VALUES (33, 'Manchester United', 'manchester-united-33', 'England', 1878)
                RETURNING id
                """
            )
        ).scalar_one()
        conn.execute(text("INSERT INTO team_translation (team_id, name_ko) VALUES (:id, '맨유')"), {"id": team_id})
        for lid in (league_id, cup_id):
            conn.execute(
                text("INSERT INTO team_season (team_id, league_id, season_year) VALUES (:team_id, :league_id, 2025)"),
                {"team_id": team_id, "league_id": lid},
            )
        player_id = conn.execute(
            text(
                """
                INSERT INTO player (external_id, name, slug, current_team_id)
                VALUES (1485, 'Bruno Fernandes', 'bruno-fernandes-1485', :team_id)
                RETURNING id
                """
            ),
            {"team_id": team_id},
        ).scalar_one()
        conn.execute(
            text("INSERT INTO player_translation (player_id, name_ko) VALUES (:id, '브루노 페르난데스')"),
            {"id": player_id},
        )
        _insert_stat(
            conn,
            player_id=player_id,
            team_id=team_id,
            league_id=league_id,
            season=2025,
            position="Midfielder",
            appearances=34,
            goals=8,
            assists=20,
        )
        _insert_stat(
            conn,
            player_id=player_id,
            team_id=team_id,
            league_id=cup_id,
            season=2025,
            position="Attacker",
            appearances=1,
            goals=0,
            assists=1,
        )
        _insert_stat(
            conn,
            player_id=player_id,
            team_id=team_id,
            league_id=old_id,
            season=2024,
            position="Midfielder",
            appearances=99,
            goals=99,
            assists=99,
        )
        _insert_stat(
            conn,
            player_id=player_id,
            team_id=team_id,
            league_id=inactive_id,
            season=2025,
            position="Midfielder",
            appearances=50,
            goals=50,
            assists=50,
        )

    with Session(engine) as session:
        payload = get_team(session, slug="manchester-united-33")

    assert payload is not None
    assert len(payload["squad"]) == 1
    row = payload["squad"][0]
    assert row["player"]["external_id"] == 1485
    assert row["position"] == "Midfielder"
    assert row["appearances"] == 35
    assert row["goals"] == 8
    assert row["assists"] == 21
