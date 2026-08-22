"""team_color migration, EPL seed, join, constraints, and downgrade tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


EPL_TEAMS = [
    (42, "Arsenal"),
    (66, "Aston Villa"),
    (35, "Bournemouth"),
    (55, "Brentford"),
    (51, "Brighton"),
    (49, "Chelsea"),
    (1346, "Coventry"),
    (52, "Crystal Palace"),
    (45, "Everton"),
    (36, "Fulham"),
    (64, "Hull City"),
    (57, "Ipswich"),
    (63, "Leeds"),
    (40, "Liverpool"),
    (50, "Manchester City"),
    (33, "Manchester United"),
    (34, "Newcastle"),
    (65, "Nottingham Forest"),
    (746, "Sunderland"),
    (47, "Tottenham"),
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_alembic(
    args: list[str], schema: str, db_url: str
) -> subprocess.CompletedProcess:
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


def _assert_alembic_succeeded(result: subprocess.CompletedProcess) -> None:
    if result.returncode != 0:
        pytest.fail(
            "alembic command failed\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def _insert_epl_teams(conn) -> None:
    conn.execute(
        text(
            """
            INSERT INTO team (external_id, name, slug)
            VALUES (:external_id, :name, :slug)
            """
        ),
        [
            {
                "external_id": external_id,
                "name": name,
                "slug": f"team-{external_id}",
            }
            for external_id, name in EPL_TEAMS
        ],
    )


def test_team_color_upgrade_seeds_and_joins_all_20_epl_teams(
    isolated_db, test_database_url
):
    engine, schema = isolated_db
    _assert_alembic_succeeded(
        _run_alembic(
            ["upgrade", "0014_broadcast_momentum_state"],
            schema,
            test_database_url,
        )
    )
    with engine.begin() as conn:
        _insert_epl_teams(conn)

    _assert_alembic_succeeded(
        _run_alembic(["upgrade", "head"], schema, test_database_url)
    )

    with engine.begin() as conn:
        columns = {
            row.column_name
            for row in conn.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = :schema AND table_name = 'team_color'
                    """
                ),
                {"schema": schema},
            )
        }
        assert columns == {
            "id",
            "team_id",
            "primary_color",
            "secondary_color",
            "accent_color",
            "source_url",
            "verified_at",
            "created_at",
            "updated_at",
        }
        assert "external_id" not in columns

        rows = conn.execute(
            text(
                """
                SELECT
                    tc.id AS team_color_id,
                    t.id AS team_id,
                    t.external_id,
                    t.name,
                    tc.primary_color,
                    tc.secondary_color,
                    tc.accent_color,
                    tc.source_url,
                    tc.verified_at
                FROM team t
                JOIN team_color tc ON tc.team_id = t.id
                ORDER BY t.external_id
                """
            )
        ).mappings().all()
        assert len(rows) == 20
        assert {row["external_id"] for row in rows} == {
            external_id for external_id, _ in EPL_TEAMS
        }
        assert all(row["team_color_id"] > 0 for row in rows)
        assert all(row["team_id"] > 0 for row in rows)
        assert all(row["source_url"] for row in rows)
        assert all(row["verified_at"] is not None for row in rows)

        arsenal = next(row for row in rows if row["external_id"] == 42)
        assert arsenal["primary_color"] == "#EF0107"
        assert arsenal["secondary_color"] == "#063672"
        assert arsenal["accent_color"] == "#9C824A"

        arsenal_team_id = arsenal["team_id"]
        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        """
                        INSERT INTO team_color (team_id, primary_color)
                        VALUES (:team_id, '#123456')
                        """
                    ),
                    {"team_id": arsenal_team_id},
                )

        with pytest.raises(IntegrityError):
            with conn.begin_nested():
                conn.execute(
                    text(
                        """
                        UPDATE team_color
                        SET primary_color = 'red'
                        WHERE team_id = :team_id
                        """
                    ),
                    {"team_id": arsenal_team_id},
                )

        conn.execute(
            text("DELETE FROM team WHERE id = :team_id"),
            {"team_id": arsenal_team_id},
        )
        assert (
            conn.execute(
                text("SELECT count(*) FROM team_color WHERE team_id = :team_id"),
                {"team_id": arsenal_team_id},
            ).scalar_one()
            == 0
        )


def test_team_color_downgrade_removes_only_the_team_color_table(
    isolated_db, test_database_url
):
    engine, schema = isolated_db
    _assert_alembic_succeeded(
        _run_alembic(["upgrade", "head"], schema, test_database_url)
    )
    _assert_alembic_succeeded(
        _run_alembic(
            ["downgrade", "0014_broadcast_momentum_state"],
            schema,
            test_database_url,
        )
    )

    with engine.connect() as conn:
        tables = {
            row.table_name
            for row in conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = :schema
                    """
                ),
                {"schema": schema},
            )
        }
    assert "team_color" not in tables
    assert "team" in tables
    assert "broadcast_momentum_state" in tables
