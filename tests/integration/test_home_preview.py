from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Fixture, League, LeagueSyncTarget, Team
from app.models.home_preview import HomePreviewAttempt, HomePreviewPublication, HomePreviewVersion
from app.services.home_preview import build_db_snapshot, read_preview, recommendations
from app.services.home_preview_generation import process_fixture

NOW = datetime(2026, 10, 25, 0, tzinfo=UTC)


@pytest.fixture
def setup_db(isolated_db):
    engine, _schema = isolated_db
    tables = [t for t in Base.metadata.sorted_tables if not t.name.startswith("home_preview_")]
    Base.metadata.create_all(engine, tables=tables)
    migration = next(
        (Path(__file__).parents[2] / "supabase/migrations").glob("*home_preview_storage.sql")
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(migration.read_text())
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        league = League(
            external_id=39,
            name="Premier League",
            type="League",
            slug="epl",
            is_active=True,
            current_season=2026,
            country_name="England",
            country_code="GB",
        )
        home = Team(external_id=40, name="Liverpool", slug="liverpool")
        away = Team(external_id=51, name="Brighton", slug="brighton")
        session.add_all([league, home, away])
        session.flush()
        session.add(LeagueSyncTarget(league_id=league.id, season_year=2026, is_active=True))
        fixture = Fixture(
            external_id=1557444,
            league_id=league.id,
            season_year=2026,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=NOW + timedelta(hours=23),
            status_short="NS",
            updated_at=NOW - timedelta(minutes=10),
        )
        session.add(fixture)
        for i in range(5):
            session.add(
                Fixture(
                    external_id=100 + i,
                    league_id=league.id,
                    season_year=2026,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff_at=NOW - timedelta(days=i + 1),
                    status_short="FT",
                    goals_home=2,
                    goals_away=1,
                    updated_at=NOW - timedelta(minutes=10),
                )
            )
        session.commit()
    return engine, factory


def test_migration_and_public_db_only_round_trip(setup_db, monkeypatch):
    engine, factory = setup_db
    assert "home_preview_attempt" in inspect(engine).get_table_names()
    with factory() as session:
        before = read_preview(session, 1557444, now=NOW)
        assert before["preview"] is None and before["publication"]["generated_at"] is None
    result = process_fixture(factory, 1557444, clock=lambda: NOW)
    assert result["state"] == "succeeded"
    with factory() as session:
        value = read_preview(session, 1557444, now=NOW)
        assert value["preview"]["is_mock"] is False
        assert value["preview"]["generated_at"] is None
        assert len(value["preview"]["facts"]["home_form"]["data"]["matches"]) == 5
        assert value["preview"]["facts"]["injuries"]["data"] is None
        recommended = recommendations(session, NOW.date(), now=NOW)
        assert recommended["items"][0]["fixture_id"] == 1557444
        assert recommended["items"][0]["preview"]["state"] == "partial"
    from app import db
    from app.main import app
    from app.services.home_preview_vertex import VertexPreviewProvider
    from app.workers.daily_sync.api import ApiFootballClient

    def trap(*args, **kwargs):
        raise AssertionError("public GET attempted external call")

    monkeypatch.setattr(VertexPreviewProvider, "request", trap)
    monkeypatch.setattr(ApiFootballClient, "get", trap)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[db.get_db_session] = override
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/home/recommendations?date=2026-10-25").status_code == 200
            assert (
                client.get("/api/v1/home/fixtures/1557444/prematch").json()["preview"]["fixture"][
                    "external_id"
                ]
                == 1557444
            )
            assert client.get("/api/v1/home/fixtures/999/prematch").status_code == 404
            assert client.get("/api/v1/home/fixtures/0/prematch").status_code == 422
            assert client.get("/api/v1/home/recommendations?date=2026-02-30").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_failed_refresh_preserves_saved_version_and_duplicate_slot(setup_db):
    _, factory = setup_db
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "succeeded"
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "already_processed"
    with factory() as session:
        old = read_preview(session, 1557444, now=NOW)["preview"]
        row = session.scalar(select(Fixture).where(Fixture.external_id == 100))
        row.goals_home = 3
        session.commit()

    def failed(_):
        raise RuntimeError("private provider details must never be public")

    later = NOW + timedelta(hours=6)
    assert (
        process_fixture(factory, 1557444, provider=failed, clock=lambda: later)["state"] == "failed"
    )
    with factory() as session:
        result = read_preview(session, 1557444, now=later)
        assert result["preview"] == old
        assert result["publication"]["served"] == "previous"
        assert result["refresh"]["reason"] == "generation_failed"
        assert "private" not in str(result)


def test_window_kickoff_crossing_changed_identity_and_inactive_target(setup_db):
    _, factory = setup_db
    late = [NOW]

    def crosses(payload):
        late[0] = NOW + timedelta(hours=24)
        return payload["analysis"], {}

    assert (
        process_fixture(factory, 1557444, provider=crosses, clock=lambda: late[0])["state"]
        == "failed"
    )
    with factory() as session:
        assert session.scalar(select(HomePreviewVersion)) is None
    assert process_fixture(factory, 1557444, clock=lambda: late[0])["state"] == "outside_window"
    with factory() as session:
        target = session.scalar(select(LeagueSyncTarget))
        target.is_active = False
        session.commit()
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "ineligible"


def test_source_cutoff_penalty_and_mock_storage_rejection(setup_db):
    _, factory = setup_db
    with factory() as session:
        f = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        row = session.scalar(select(Fixture).where(Fixture.external_id == 100))
        row.status_short = "PEN"
        row.goals_home = 1
        row.goals_away = 1
        row.score_pen_home = None
        row.score_pen_away = None
        future = session.scalar(select(Fixture).where(Fixture.external_id == 101))
        future.updated_at = NOW + timedelta(minutes=1)
        session.commit()
        snapshot = build_db_snapshot(session, f, now=NOW)
        matches = snapshot["facts"]["home_form"]["data"]["matches"]
        assert (
            len(matches) == 4 and matches[0]["status"] == "PEN" and matches[0]["penalties"] is None
        )
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "succeeded"
    with factory() as session:
        version = session.scalar(select(HomePreviewVersion))
        value = dict(version.payload)
        value["is_mock"] = True
        version.payload = value
        session.commit()
        assert read_preview(session, 1557444, now=NOW)["preview"] is None


def test_max_four_primary_slots_and_busy_owner(setup_db):
    _, factory = setup_db

    def nested(payload):
        assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "busy"
        return payload["analysis"], {}

    assert (
        process_fixture(factory, 1557444, provider=nested, model="test", clock=lambda: NOW)["state"]
        == "succeeded"
    )
    for hours in (6, 12, 18):
        assert process_fixture(
            factory, 1557444, model="test", clock=lambda hours=hours: NOW + timedelta(hours=hours)
        )["state"] in ("succeeded", "unchanged")
    with factory() as session:
        f = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        f.kickoff_at = NOW + timedelta(hours=40)
        session.commit()
    assert (
        process_fixture(factory, 1557444, clock=lambda: NOW + timedelta(hours=24))["state"]
        == "limit_reached"
    )


def test_successful_attempt_starts_before_actual_generation_completion(setup_db):
    _, factory = setup_db
    current = [NOW]

    def provider(payload):
        current[0] = NOW + timedelta(seconds=30)
        return payload["analysis"], {}

    assert (
        process_fixture(factory, 1557444, provider=provider, clock=lambda: current[0])["state"]
        == "succeeded"
    )
    with factory() as session:
        result = read_preview(session, 1557444, now=current[0])
        assert result["publication"]["served"] == "current"
        assert result["refresh"]["last_attempt_at"] < result["publication"]["generated_at"]


def test_expired_owner_is_interrupted_and_previous_snapshot_is_preserved(setup_db):
    _, factory = setup_db
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "succeeded"
    with factory() as session:
        publication = session.scalar(select(HomePreviewPublication))
        publication.refresh_state = "running"
        publication.last_attempt_at = NOW - timedelta(minutes=10)
        attempt = session.scalar(select(HomePreviewAttempt))
        attempt.state = "running"
        session.commit()
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "already_processed"
    with factory() as session:
        value = read_preview(session, 1557444, now=NOW)
        assert value["publication"]["served"] == "previous"
        assert value["refresh"]["state"] == "failed"
        assert session.scalar(select(HomePreviewAttempt)).state == "interrupted"


def test_latest_two_seasons_exclude_future_target_and_null_empty_observation(setup_db):
    _, factory = setup_db
    with factory() as session:
        league = session.scalar(select(League))
        current = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        for year in (2024, 2025, 2027):
            session.add(LeagueSyncTarget(league_id=league.id, season_year=year, is_active=True))
        session.add(
            Fixture(
                external_id=888,
                league_id=league.id,
                season_year=2027,
                home_team_id=current.home_team_id,
                away_team_id=current.away_team_id,
                kickoff_at=current.kickoff_at,
                status_short="NS",
                updated_at=NOW,
            )
        )
        session.commit()
        assert [
            row["fixture_id"] for row in recommendations(session, NOW.date(), now=NOW)["items"]
        ] == [1557444]
        league.is_active = False
        session.commit()
        value = recommendations(session, NOW.date(), now=NOW)
        assert value["items"] == [] and value["as_of"] is None


def test_publication_update_failure_rolls_back_new_version_and_keeps_old_facts(setup_db):
    from sqlalchemy import event, func

    from app.models.home_preview import HomePreviewSnapshot

    engine, factory = setup_db
    assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "succeeded"
    with factory() as session:
        old = read_preview(session, 1557444, now=NOW)["preview"]
        row = session.scalar(select(Fixture).where(Fixture.external_id == 100))
        row.goals_home = 9
        session.commit()
    state = {"raised": False}

    def fail_pointer(conn, cursor, statement, parameters, context, executemany):
        if (
            not state["raised"]
            and statement.startswith("UPDATE home_preview_publication")
            and "version_id=" in statement
        ):
            state["raised"] = True
            raise RuntimeError("test publication pointer failure")

    event.listen(engine, "before_cursor_execute", fail_pointer)
    try:
        result = process_fixture(factory, 1557444, clock=lambda: NOW + timedelta(hours=6))
    finally:
        event.remove(engine, "before_cursor_execute", fail_pointer)
    assert result["state"] == "failed" and state["raised"]
    with factory() as session:
        assert read_preview(session, 1557444, now=NOW + timedelta(hours=6))["preview"] == old
        assert session.scalar(select(func.count()).select_from(HomePreviewVersion)) == 1
        assert session.scalar(select(func.count()).select_from(HomePreviewSnapshot)) == 1


def test_fixture_retention_cascades_preview_storage_without_deleting_shared_teams(setup_db):
    from sqlalchemy import func

    from app.models.home_preview import HomePreviewSnapshot

    _, factory = setup_db
    process_fixture(factory, 1557444, clock=lambda: NOW)
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        session.delete(fixture)
        session.commit()
        for model in (
            HomePreviewSnapshot,
            HomePreviewVersion,
            HomePreviewPublication,
            HomePreviewAttempt,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0
        assert session.scalar(select(func.count()).select_from(Team)) == 2
        assert session.scalar(select(func.count()).select_from(League)) == 1


def test_retention_dry_run_and_apply_touch_only_expired_preview_tables(setup_db):
    from sqlalchemy import func

    from app.services.home_preview_retention import prune_home_previews

    _, factory = setup_db
    process_fixture(factory, 1557444, clock=lambda: NOW)
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        fixture.season_year = 2024
        session.add_all(
            [
                LeagueSyncTarget(league_id=fixture.league_id, season_year=year, is_active=False)
                for year in (2025, 2024)
            ]
        )
        session.commit()
        dry = prune_home_previews(session)
        assert dry["fixture_ids"] == [1557444]
        assert session.scalar(select(func.count()).select_from(HomePreviewVersion)) == 1
        applied = prune_home_previews(session, dry_run=False)
        assert applied["counts"] == dry["counts"]
        assert session.scalar(select(func.count()).select_from(HomePreviewVersion)) == 0
        assert session.scalar(select(func.count()).select_from(Team)) == 2
        assert session.get(Fixture, fixture.id) is not None


@pytest.mark.parametrize("invalid_kind", ["mock", "cross_fixture"])
def test_invalid_evidence_is_rejected_before_calling_ai(setup_db, invalid_kind):
    _, factory = setup_db

    def evidence(payload, *, now):
        if invalid_kind == "mock":
            payload["is_mock"] = True
        else:
            payload["fixture"]["external_id"] = 999
            for source in payload["sources"]:
                source["fixture_id"] = 999
        return payload, {}

    def trap(_):
        raise AssertionError("invalid evidence reached AI")

    result = process_fixture(
        factory, 1557444, provider=trap, evidence_provider=evidence, clock=lambda: NOW
    )
    assert result["state"] == "failed"
    with factory() as session:
        assert session.scalar(select(HomePreviewVersion)) is None
        assert session.scalar(select(HomePreviewAttempt)).usage["model_requests"] == 0


def test_explicit_retry_keeps_cumulative_calls_and_stops_after_success(setup_db):
    _, factory = setup_db
    calls = []

    def evidence(payload, *, now):
        return payload, {"model_requests": 1, "api_football_requests": 3}

    def model(payload):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("incomplete_model_response")
        return payload["analysis"], {}

    assert (
        process_fixture(
            factory, 1557444, provider=model, evidence_provider=evidence, clock=lambda: NOW
        )["state"]
        == "failed"
    )
    assert (
        process_fixture(
            factory,
            1557444,
            provider=model,
            evidence_provider=evidence,
            clock=lambda: NOW,
            retry_failed=True,
        )["state"]
        == "succeeded"
    )
    assert (
        process_fixture(
            factory,
            1557444,
            provider=model,
            evidence_provider=evidence,
            clock=lambda: NOW,
            retry_failed=True,
        )["state"]
        == "already_processed"
    )
    with factory() as session:
        usage = session.scalar(select(HomePreviewAttempt)).usage
        assert (
            usage["executions"] == 2
            and usage["model_requests"] == 4
            and usage["api_football_requests"] == 6
        )
    assert len(calls) == 2


def test_injury_names_use_current_translation_by_external_id_with_safe_legacy_fallback(setup_db):
    from app.models.player import Player, PlayerTranslation
    from app.services.home_preview import localize_injury_names

    _engine, factory = setup_db
    with factory() as session:
        players = [
            Player(external_id=700 + i, name=name, slug=f"injury-translation-{i}")
            for i, name in enumerate(
                ["Changed API name", "Legacy Unique", "Duplicate", "Duplicate", "Untranslated"]
            )
        ]
        session.add_all(players)
        session.flush()
        for player, ko in zip(
            players, ["한국어 이름", "기존 선수", "동명이인 하나", "동명이인 둘", None]
        ):
            session.add(PlayerTranslation(player_id=player.id, name_ko=ko))
        session.commit()
        source_rows = [
            {"player_id": 700, "player_name": "API abbreviated"},
            {"player_name": "Legacy Unique"},
            {"player_name": "Duplicate"},
            {"player_id": 704, "player_name": "Untranslated"},
            {"player_id": 999, "player_name": "Legacy Unique"},
        ]
        from copy import deepcopy

        preview = {"facts": {"injuries": {"data": deepcopy(source_rows)}}}
        localize_injury_names(session, preview)
        assert [row["player_name"] for row in preview["facts"]["injuries"]["data"]] == [
            "한국어 이름",
            "기존 선수",
            "Duplicate",
            "Untranslated",
            "Legacy Unique",
        ]
        session.get(PlayerTranslation, players[0].id).name_ko = "수정된 이름"
        session.commit()
        localize_injury_names(session, preview)
        assert preview["facts"]["injuries"]["data"][0]["player_name"] == "수정된 이름"
        assert source_rows[0]["player_name"] == "API abbreviated"

    def evidence(snapshot, *, now):
        snapshot["as_of"] = now.isoformat()
        refs = [snapshot["sources"][0]["id"]]
        snapshot["facts"]["injuries"] = {
            "status": "available",
            "reason": None,
            "as_of": now.isoformat(),
            "source_ids": refs,
            "data": [
                {
                    "team_id": 40,
                    "player_id": 700,
                    "player_name": "API abbreviated",
                    "availability": "out",
                    "detail": "Injury",
                    "impact": "출전 불가",
                    "source_ids": refs,
                }
            ],
        }
        return snapshot, {"api_football_requests": 0}

    assert (
        process_fixture(factory, 1557444, clock=lambda: NOW, evidence_provider=evidence)["state"]
        == "succeeded"
    )
    with factory() as session:
        assert (
            read_preview(session, 1557444, now=NOW)["preview"]["facts"]["injuries"]["data"][0][
                "player_name"
            ]
            == "수정된 이름"
        )
        stored = session.scalar(select(HomePreviewVersion))
        assert stored.payload["facts"]["injuries"]["data"][0]["player_name"] == "API abbreviated"
