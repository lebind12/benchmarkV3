"""team_color ORM metadata and curated EPL seed contract tests."""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest
from sqlalchemy import CheckConstraint, DateTime, String, Text, UniqueConstraint

pytestmark = pytest.mark.unit


def _load_migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0015_team_color.py"
    )
    spec = importlib.util.spec_from_file_location("team_color_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_scoreboard_mode_migration_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "0016_team_color_scoreboard_mode.py"
    )
    spec = importlib.util.spec_from_file_location("team_color_scoreboard_mode_migration", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def table():
    from app.models import Base, TeamColor  # noqa: F401

    return Base.metadata.tables["team_color"]


def test_team_color_columns_and_types(table):
    assert set(table.columns.keys()) == {
        "id",
        "team_id",
        "primary_color",
        "secondary_color",
        "accent_color",
        "scoreboard_color_mode",
        "source_url",
        "verified_at",
        "created_at",
        "updated_at",
    }
    assert table.columns["id"].primary_key
    assert isinstance(table.columns["primary_color"].type, String)
    assert table.columns["primary_color"].type.length == 7
    assert table.columns["primary_color"].nullable is False
    assert table.columns["secondary_color"].nullable is True
    assert table.columns["accent_color"].nullable is True
    assert isinstance(table.columns["scoreboard_color_mode"].type, String)
    assert table.columns["scoreboard_color_mode"].type.length == 24
    assert table.columns["scoreboard_color_mode"].nullable is False
    assert isinstance(table.columns["source_url"].type, Text)
    assert isinstance(table.columns["verified_at"].type, DateTime)
    assert table.columns["created_at"].server_default is not None
    assert table.columns["updated_at"].server_default is not None


def test_team_color_is_one_to_one_with_team_and_cascades(table):
    team_id = table.columns["team_id"]
    assert team_id.nullable is False
    foreign_keys = list(team_id.foreign_keys)
    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "team.id"
    assert foreign_keys[0].ondelete == "CASCADE"
    assert any(
        isinstance(constraint, UniqueConstraint)
        and list(constraint.columns.keys()) == ["team_id"]
        for constraint in table.constraints
    )


def test_team_color_hex_checks_are_declared(table):
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert set(checks) == {
        "team_color_primary_hex_check",
        "team_color_secondary_hex_check",
        "team_color_accent_hex_check",
        "team_color_scoreboard_color_mode_check",
    }
    assert all(
        "[0-9A-Fa-f]{6}" in checks[name]
        for name in (
            "team_color_primary_hex_check",
            "team_color_secondary_hex_check",
            "team_color_accent_hex_check",
        )
    )
    assert "PRIMARY_LIGHT" in checks["team_color_scoreboard_color_mode_check"]
    assert "SECONDARY" in checks["team_color_scoreboard_color_mode_check"]


def test_scoreboard_secondary_mode_matches_reference_clubs():
    migration = _load_scoreboard_mode_migration_module()
    assert set(migration.SECONDARY_SCOREBOARD_TEAM_EXTERNAL_IDS) == {
        35,
        47,
        50,
        52,
        55,
        63,
        66,
        746,
    }


def test_epl_seed_has_20_unique_team_external_ids_and_valid_colors():
    migration = _load_migration_module()
    rows = migration.TEAM_COLOR_SEEDS
    expected_external_ids = {
        33,
        34,
        35,
        36,
        40,
        42,
        45,
        47,
        49,
        50,
        51,
        52,
        55,
        57,
        63,
        64,
        65,
        66,
        746,
        1346,
    }
    assert len(rows) == 20
    assert {row["external_id"] for row in rows} == expected_external_ids
    assert len({row["external_id"] for row in rows}) == len(rows)

    hex_pattern = re.compile(r"^#[0-9A-Fa-f]{6}$")
    for row in rows:
        assert hex_pattern.fullmatch(row["primary_color"])
        for field in ("secondary_color", "accent_color"):
            value = row[field]
            assert value is None or hex_pattern.fullmatch(value)
        assert row["source_url"].startswith("https://")


def test_liverpool_chroma_adjacent_color_is_not_the_primary_or_secondary():
    migration = _load_migration_module()
    liverpool = next(
        row for row in migration.TEAM_COLOR_SEEDS if row["external_id"] == 40
    )
    assert liverpool["primary_color"] == "#C8102E"
    assert liverpool["secondary_color"] == "#F6EB61"
    assert liverpool["accent_color"] == "#00B2A9"
