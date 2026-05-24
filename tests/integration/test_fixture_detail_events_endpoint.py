"""Fixture-detail events endpoint integration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

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
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return engine, schema


def _client_for_schema(monkeypatch, test_database_url: str, schema: str) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URL", test_database_url)
    monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")
    from app.main import app

    return TestClient(app)


def _seed_fixture(conn):
    league_id = conn.execute(
        text(
            "INSERT INTO league (external_id, name, type, slug) "
            "VALUES (39, 'Premier League', 'League', 'premier-league') RETURNING id"
        )
    ).scalar()
    home_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (40, 'Liverpool', 'liverpool-40') RETURNING id"
        )
    ).scalar()
    away_id = conn.execute(
        text(
            "INSERT INTO team (external_id, name, slug) "
            "VALUES (42, 'Arsenal', 'arsenal-42') RETURNING id"
        )
    ).scalar()
    for external_id, name, slug, team_id in [
        (1001, "Mohamed Salah", "mohamed-salah-1001", home_id),
        (1002, "Trent Alexander-Arnold", "trent-alexander-arnold-1002", home_id),
        (1003, "Bukayo Saka", "bukayo-saka-1003", away_id),
    ]:
        player_id = conn.execute(
            text(
                "INSERT INTO player (external_id, name, slug, current_team_id) "
                "VALUES (:external_id, :name, :slug, :team_id) RETURNING id"
            ),
            {
                "external_id": external_id,
                "name": name,
                "slug": slug,
                "team_id": team_id,
            },
        ).scalar()
        conn.execute(
            text("INSERT INTO player_translation (player_id, name_ko) VALUES (:id, :name_ko)"),
            {"id": player_id, "name_ko": f"선수 {external_id}"},
        )
    fixture_id = conn.execute(
        text(
            "INSERT INTO fixture (external_id, league_id, season_year, home_team_id, "
            "away_team_id, kickoff_at, status_long, status_short, goals_home, goals_away) "
            "VALUES (1000001, :league, 2026, :home, :away, "
            "'2026-05-13T10:00:00+00:00', 'Match Finished', 'FT', 3, 1) RETURNING id"
        ),
        {"league": league_id, "home": home_id, "away": away_id},
    ).scalar()
    return fixture_id


def test_events_i01_normalizes_and_sorts_jsonb_events(migrated_db, test_database_url, monkeypatch):
    engine, schema = migrated_db
    with engine.begin() as conn:
        fixture_id = _seed_fixture(conn)
        conn.execute(
            text(
                "INSERT INTO fixture_detail (fixture_id, events) "
                "VALUES (:fixture_id, CAST(:events AS jsonb))"
            ),
            {
                "fixture_id": fixture_id,
                "events": (
                    "["
                    '{"time":{"elapsed":60,"extra":null},"team":{"id":40},'
                    '"player":{"id":1002,"name":"Trent Alexander-Arnold"},'
                    '"assist":null,"type":"subst","detail":"Substitution"},'
                    '{"time":{"elapsed":23,"extra":null},"team":{"id":40},'
                    '"player":{"id":1001,"name":"Mohamed Salah"},'
                    '"assist":{"id":1002,"name":"Trent Alexander-Arnold"},'
                    '"type":"Goal","detail":"Normal Goal"},'
                    '{"time":{"elapsed":45,"extra":2},"team":{"id":42},'
                    '"player":{"id":1003,"name":"Bukayo Saka"},'
                    '"assist":null,"type":"Card","detail":"Yellow Card"},'
                    '{"time":{"elapsed":78,"extra":null},"team":{"id":42},'
                    '"player":{"id":1003,"name":"Bukayo Saka"},'
                    '"assist":null,"type":"Var","detail":"Goal cancelled"}'
                    "]"
                ),
            },
        )

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001/events")

    assert response.status_code == 200
    events = response.json()["events"]
    assert [(event["minute"], event["extra"]) for event in events] == [
        (23, None),
        (45, 2),
        (60, None),
        (78, None),
    ]
    assert [event["type"] for event in events] == [
        "goal",
        "yellow_card",
        "substitution",
        "var",
    ]
    assert events[0]["assist"]["external_id"] == 1002


def test_events_i02_existing_fixture_without_detail_returns_empty_list(
    migrated_db, test_database_url, monkeypatch
):
    engine, schema = migrated_db
    with engine.begin() as conn:
        _seed_fixture(conn)

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000001/events")

    assert response.status_code == 200
    assert response.json() == {"events": []}


def test_events_i03_missing_fixture_returns_404(migrated_db, test_database_url, monkeypatch):
    _engine, schema = migrated_db

    client = _client_for_schema(monkeypatch, test_database_url, schema)
    response = client.get("/api/v1/fixtures/1000099/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"
