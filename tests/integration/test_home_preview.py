from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Fixture, League, LeagueSyncTarget, Team
from app.models.home_preview import HomePreviewAttempt, HomePreviewPublication, HomePreviewVersion
from app.services.home_preview import build_db_snapshot, read_preview, recommendations
from app.services.home_preview_generation import LEASE_SECONDS, process_fixture

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
            kickoff_at=NOW + timedelta(hours=5),
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


def test_failed_explicit_retry_preserves_saved_version_and_duplicate_slot(setup_db):
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

    with factory() as session:
        attempt = session.scalar(select(HomePreviewAttempt))
        attempt.state = (
            "failed"  # repair an interrupted publication without discarding its saved version
        )
        session.commit()
    later = NOW + timedelta(hours=1)
    assert (
        process_fixture(factory, 1557444, provider=failed, clock=lambda: later, retry_failed=True)[
            "state"
        ]
        == "failed"
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


def test_one_primary_slot_and_busy_owner(setup_db):
    _, factory = setup_db

    def nested(payload):
        assert process_fixture(factory, 1557444, clock=lambda: NOW)["state"] == "busy"
        return payload["analysis"], {}

    assert (
        process_fixture(factory, 1557444, provider=nested, model="test", clock=lambda: NOW)["state"]
        == "succeeded"
    )
    for hours in (1, 2, 4):
        assert (
            process_fixture(
                factory,
                1557444,
                model="test",
                clock=lambda hours=hours: NOW + timedelta(hours=hours),
            )["state"]
            == "already_processed"
        )
    with factory() as session:
        assert len(list(session.scalars(select(HomePreviewAttempt)))) == 1
    assert (
        process_fixture(factory, 1557444, clock=lambda: NOW + timedelta(hours=5))["state"]
        == "outside_window"
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
        publication.last_attempt_at = NOW - timedelta(seconds=LEASE_SECONDS + 1)
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
    with factory() as session:
        attempt = session.scalar(select(HomePreviewAttempt))
        attempt.state = "failed"
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
        result = process_fixture(
            factory, 1557444, clock=lambda: NOW + timedelta(hours=1), retry_failed=True
        )
    finally:
        event.remove(engine, "before_cursor_execute", fail_pointer)
    assert result["state"] == "failed" and state["raised"]
    with factory() as session:
        assert read_preview(session, 1557444, now=NOW + timedelta(hours=1))["preview"] == old
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
        player = session.get(Player, players[0].id)
        player.photo_url = "https://media.api-sports.io/football/players/700.png"
        session.commit()
        spotlight_only = {
            "facts": {
                "injuries": {"data": None},
                "player_spotlights": {"data": [{"player_id": 700, "player_name": "Player"}]},
            }
        }
        localize_injury_names(session, spotlight_only)
        shown = spotlight_only["facts"]["player_spotlights"]["data"][0]
        assert shown["player_name"] == "수정된 이름" and shown["photo_url"] == player.photo_url
        assert (
            read_preview(session, 1557444, now=NOW)["preview"]["facts"]["injuries"]["data"][0][
                "photo_url"
            ]
            == player.photo_url
        )


def test_injury_importance_uses_db_participation_and_excludes_future_records(setup_db):
    from app.models.player import Player, PlayerSeasonStat
    from app.services.home_preview_injuries import enrich_importance

    _engine, factory = setup_db
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        player = Player(external_id=700, name="Starter", slug="importance-starter")
        session.add(player)
        session.flush()
        stat = PlayerSeasonStat(
            player_id=player.id,
            team_id=fixture.home_team_id,
            league_id=fixture.league_id,
            season_year=2026,
            appearances=12,
            minutes=900,
            raw_stats={},
            updated_at=NOW - timedelta(minutes=1),
        )
        session.add(stat)
        session.commit()
        value = build_db_snapshot(session, fixture, now=NOW)
        value["facts"]["injuries"]["data"] = [
            {"team_id": 40, "player_id": 700, "player_name": "Starter", "source_ids": ["inj"]}
        ]
        enrich_importance(session, value, now=NOW)
        result = value["facts"]["injuries"]["data"][0]["importance_evidence"]
        assert (
            result["eligible"]
            and result["recent_starts"] is None
            and result["recent_minutes"] is None
        )
        assert result["seasons"] == [{"season_year": 2026, "appearances": 12, "minutes": 900}]
        stat.updated_at = NOW + timedelta(minutes=1)
        session.commit()
        fresh = build_db_snapshot(session, fixture, now=NOW)
        fresh["facts"]["injuries"]["data"] = [
            {"team_id": 40, "player_id": 700, "player_name": "Starter", "source_ids": ["inj"]}
        ]
        enrich_importance(session, fresh, now=NOW)
        assert "importance_evidence" not in fresh["facts"]["injuries"]["data"][0]


def test_verified_identity_can_be_considered_for_recognition_without_invented_minutes(setup_db):
    from app.models.player import Player
    from app.services.home_preview_injuries import enrich_importance

    _engine, factory = setup_db
    with factory() as session:
        player = Player(
            external_id=555,
            name="Recognized Player",
            slug="recognition-test",
            updated_at=NOW - timedelta(minutes=1),
        )
        session.add(player)
        session.commit()
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        value = build_db_snapshot(session, fixture, now=NOW)
        value["facts"]["injuries"]["data"] = [
            {"team_id": 40, "player_id": 555, "player_name": "R. Player", "source_ids": ["inj"]}
        ]
        enrich_importance(session, value, now=NOW)
        evidence = value["facts"]["injuries"]["data"][0]["importance_evidence"]
        assert evidence["eligible"] and evidence["recognition_name"] == "Recognized Player"
        assert evidence["recent_minutes"] is None and evidence["seasons"] == []
        assert "출전 기록" not in evidence["selection_reason"]


def test_player_watchlist_uses_season_and_exact_recent_fixture_sequence(setup_db):
    from app.models import FixtureDetail
    from app.models.player import Player, PlayerSeasonStat
    from app.services.home_preview_players import enrich_player_spotlights

    _engine, factory = setup_db
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        player = Player(
            external_id=777,
            name="Attacker",
            slug="watchlist-test",
            updated_at=NOW - timedelta(minutes=1),
        )
        session.add(player)
        session.flush()
        session.add(
            PlayerSeasonStat(
                player_id=player.id,
                team_id=fixture.home_team_id,
                league_id=fixture.league_id,
                season_year=2026,
                appearances=8,
                goals=6,
                assists=2,
                minutes=600,
                raw_stats={},
                updated_at=NOW - timedelta(minutes=1),
            )
        )
        recent = list(
            session.scalars(
                select(Fixture)
                .where(Fixture.external_id.in_([100, 101, 102, 103, 104]))
                .order_by(Fixture.kickoff_at.desc())
            )
        )
        for i, row in enumerate(recent):
            session.add(
                FixtureDetail(
                    fixture_id=row.id,
                    players=[
                        {
                            "team": {"id": 40},
                            "players": [
                                {
                                    "player": {"id": 777},
                                    "statistics": [
                                        {"goals": {"total": 1 if i < 3 else 0, "assists": 0}}
                                    ],
                                }
                            ],
                        }
                    ],
                    updated_at=NOW - timedelta(minutes=1),
                    fetched_at=NOW - timedelta(minutes=1),
                )
            )
        session.commit()
        value = build_db_snapshot(session, fixture, now=NOW)
        enrich_player_spotlights(session, value, now=NOW)
        result = value["facts"]["player_spotlights"]["data"][0]
        assert result["scoring_streak"] == 3 and result["goals"] == 6
        session.get(FixtureDetail, recent[1].id).fetched_at = NOW + timedelta(minutes=1)
        session.commit()
        fresh = build_db_snapshot(session, fixture, now=NOW)
        enrich_player_spotlights(session, fresh, now=NOW)
        assert fresh["facts"]["player_spotlights"]["data"][0]["scoring_streak"] == 1
        assert (
            fresh["facts"]["player_spotlights"]["data"][0]["record_notes"]["scoring_streak"] is None
        )


@pytest.mark.parametrize(
    "mutate_selection,resume_optional",
    [(False, False), (True, False), (False, True), (False, "incomplete")],
)
def test_post_selection_causes_keep_identity_and_count_the_extra_search(
    setup_db, mutate_selection, resume_optional
):
    from copy import deepcopy

    from app.models.player import Player, PlayerSeasonStat
    from app.services.home_preview_retry import ModelRun

    _engine, factory = setup_db
    run = (
        ModelRun(clock=lambda: NOW, sleep=lambda _: None, jitter=lambda: 0)
        if resume_optional
        else None
    )
    calls = {"evidence": 0, "analysis": 0, "causes": 0}
    if resume_optional == "incomplete":
        factory = sessionmaker(bind=_engine)
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        player = Player(
            external_id=777,
            name="Known Player",
            slug="cause-hook-test",
            updated_at=NOW - timedelta(minutes=1),
        )
        session.add(player)
        session.flush()
        session.add(
            PlayerSeasonStat(
                player_id=player.id,
                team_id=fixture.home_team_id,
                league_id=fixture.league_id,
                season_year=2026,
                appearances=12,
                minutes=900,
                raw_stats={},
                updated_at=NOW - timedelta(minutes=1),
            )
        )
        session.commit()

    def evidence(payload, *, now):
        calls["evidence"] += 1
        if run:
            run.request("forecast", lambda _: None, timeout=90)
        payload["as_of"] = now.isoformat()
        payload["sources"].append(
            {
                "id": "api-injury",
                "fixture_id": 1557444,
                "kind": "api",
                "title": "Injury",
                "url": "https://v3.football.api-sports.io/injuries?fixture=1557444",
                "published_at": None,
                "retrieved_at": now.isoformat(),
            }
        )
        payload["facts"]["injuries"] = {
            "status": "available",
            "reason": None,
            "as_of": now.isoformat(),
            "source_ids": ["api-injury"],
            "data": [
                {
                    "team_id": 40,
                    "player_id": 777,
                    "player_name": "Known Player",
                    "availability": "out",
                    "detail": "Muscle Injury",
                    "impact": "Out",
                    "source_ids": ["api-injury"],
                }
            ],
        }
        return payload, {"model_requests": 1, "api_football_requests": 4}

    def model(payload):
        calls["analysis"] += 1
        if run:
            run.request("analysis", lambda _: None, timeout=90)
        analysis = deepcopy(payload["analysis"])
        row = payload["facts"]["injuries"]["data"][0]
        refs = row["source_ids"] + row["importance_evidence"]["source_ids"]
        analysis["key_absences"] = {
            "status": "available",
            "reason": None,
            "as_of": payload["as_of"],
            "source_ids": refs,
            "data": [
                {
                    "team_id": 40,
                    "player_id": 777,
                    "reason": row["importance_evidence"]["selection_reason"],
                    "evidence_ids": refs,
                }
            ],
        }
        return analysis, {}

    def causes(payload, *, now):
        calls["causes"] += 1
        if run:

            def operation(_):
                if calls["causes"] == 1 and resume_optional is True:
                    raise ValueError("invalid_cause_discovery_response")

            try:
                run.request("causes", operation, timeout=180)
            except ValueError:
                return payload, {
                    "model_requests": 1,
                    "cause_search_failed": True,
                    "cause_failure_type": "ValueError",
                }
        if mutate_selection:
            payload["analysis"]["key_absences"]["data"][0]["player_id"] = 999
        if not any(source["id"] == "cause-web" for source in payload["sources"]):
            payload["sources"].append(
                {
                    "id": "cause-web",
                    "fixture_id": 1557444,
                    "kind": "web",
                    "title": "Club news",
                    "url": "https://www.liverpoolfc.com/news/club",
                    "published_at": None,
                    "retrieved_at": now.isoformat(),
                }
            )
        payload["facts"]["injuries"]["data"][0]["cause"] = {
            "status": "available",
            "reason": None,
            "as_of": now.isoformat(),
            "source_ids": ["cause-web"],
            "data": {
                "code": "muscle",
                "label": "근육 부상",
                "occurred_on": "2026-10-18",
                "occurred_month": None,
            },
        }
        if resume_optional == "incomplete" and calls["causes"] == 1:
            payload["facts"]["injuries"]["data"][0]["cause"]["data"]["occurred_on"] = None
        return payload, {
            "model_requests": 1,
            "cause_search_requests": 1,
            "search_queries": 2,
            "_evidence": [],
        }

    result = process_fixture(
        factory,
        1557444,
        clock=lambda: NOW,
        provider=model,
        evidence_provider=evidence,
        cause_provider=causes,
        runtime=run,
    )
    assert result["state"] == ("failed" if mutate_selection else "succeeded")
    if resume_optional:
        with factory() as session:
            old_id = session.scalar(select(HomePreviewPublication)).version_id
            assert bool(
                session.scalar(select(HomePreviewAttempt)).usage.get("cause_search_failed")
            ) == (resume_optional is True)
        run = ModelRun(clock=lambda: NOW, sleep=lambda _: None, jitter=lambda: 0)
        result = process_fixture(
            factory,
            1557444,
            clock=lambda: NOW,
            provider=model,
            evidence_provider=evidence,
            cause_provider=causes,
            runtime=run,
            retry_failed=True,
            retry_research=resume_optional == "incomplete",
        )
        assert result["state"] == "succeeded"
        assert calls == {"evidence": 1, "analysis": 1, "causes": 2}
        with factory() as session:
            assert session.scalar(select(HomePreviewPublication)).version_id != old_id
            old_injury = session.get(HomePreviewVersion, old_id).payload["facts"]["injuries"][
                "data"
            ][0]
            if resume_optional == "incomplete":
                assert old_injury["cause"]["data"]["occurred_on"] is None
            else:
                assert "cause" not in old_injury
    with factory() as session:
        usage = session.scalar(select(HomePreviewAttempt)).usage
        assert usage["model_requests"] == (4 if resume_optional else 3)
        if resume_optional:
            assert not usage.get("cause_search_failed") and usage["api_football_requests"] == 4
        if not mutate_selection:
            assert (
                read_preview(session, 1557444, now=NOW)["preview"]["facts"]["injuries"]["data"][0][
                    "cause"
                ]["data"]["occurred_on"]
                == "2026-10-18"
            )


@pytest.mark.parametrize("changed_model", [False, True])
def test_durable_model_retry_resumes_valid_checkpoint_and_invalidates_changed_model(
    setup_db, changed_model
):
    from app.models.home_preview import HomePreviewSnapshot
    from app.services.home_preview_retry import ModelRun

    _, factory = setup_db
    calls = {"evidence": 0, "analysis": 0}
    active = [None]

    def new_runtime():
        return ModelRun(clock=lambda: NOW, sleep=lambda _: None, jitter=lambda: 0)

    def evidence(payload, *, now):
        calls["evidence"] += 1
        active[0].request("forecast", lambda _: None, timeout=90)
        return payload, {"model_requests": 1, "api_football_requests": 2}

    def model(payload):
        calls["analysis"] += 1

        def operation(_):
            if calls["analysis"] == 1:
                raise ValueError("incomplete_model_response")
            return payload["analysis"], {}

        return active[0].request("analysis", operation, timeout=90)

    active[0] = new_runtime()
    assert (
        process_fixture(
            factory,
            1557444,
            provider=model,
            evidence_provider=evidence,
            runtime=active[0],
            model="test",
            clock=lambda: NOW,
        )["state"]
        == "failed"
    )
    with factory() as session:
        attempt = session.scalar(select(HomePreviewAttempt))
        checkpoint_id = attempt.usage["checkpoints"]["evidence"]
        assert attempt.usage["model_requests"] == 2
        assert (
            session.get(HomePreviewSnapshot, checkpoint_id).payload["checkpoint"]["stage"]
            == "evidence"
        )
    active[0] = new_runtime()
    result = process_fixture(
        factory,
        1557444,
        provider=model,
        evidence_provider=evidence,
        runtime=active[0],
        model="changed" if changed_model else "test",
        clock=lambda: NOW,
        retry_failed=True,
    )
    assert result["state"] == "succeeded"
    assert calls == {"evidence": 2 if changed_model else 1, "analysis": 2}
    with factory() as session:
        usage = session.scalar(select(HomePreviewAttempt)).usage
        assert usage["model_requests"] == (4 if changed_model else 3)
        assert usage["api_football_requests"] == (4 if changed_model else 2)
        assert "failure_type" not in usage and usage["previous_failures"]
        assert set(usage["checkpoints"]) == {"evidence", "analysis", "causes"}


def test_direct_worker_json_survives_checkpoint_retry_and_fresh_db_read(setup_db):
    from copy import deepcopy

    from sqlalchemy import event

    from app.models.home_preview import HomePreviewSnapshot
    from app.services.home_preview_retry import ModelRun
    from app.services.home_preview_web import update_prediction_coverage

    engine, factory = setup_db
    calls, raw = [], []

    def provider(payload):
        result = deepcopy(payload)
        result["generated_at"] = NOW.isoformat()
        update_prediction_coverage(result, candidate_count=0, checked_at=NOW)
        calls.append(1)
        raw.append(deepcopy(result))
        return result, {
            "_direct_generation": {
                "raw_llm_response": deepcopy(result),
                "raw_llm_text": __import__("json").dumps(result),
            }
        }

    def fail_pointer(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("UPDATE home_preview_publication") and "version_id=" in statement:
            raise RuntimeError("publication write interrupted")

    event.listen(engine, "before_cursor_execute", fail_pointer)
    try:
        result = process_fixture(
            factory,
            1557444,
            payload_provider=provider,
            model="test",
            clock=lambda: NOW,
            runtime=ModelRun(clock=lambda: NOW),
        )
        assert result["state"] == "failed"
    finally:
        event.remove(engine, "before_cursor_execute", fail_pointer)
    assert (
        process_fixture(
            factory,
            1557444,
            payload_provider=provider,
            model="test",
            clock=lambda: NOW,
            runtime=ModelRun(clock=lambda: NOW),
            retry_failed=True,
        )["state"]
        == "succeeded"
    )
    assert len(calls) == 1
    with factory() as session:
        version = session.scalar(select(HomePreviewVersion))
        audit = session.get(HomePreviewSnapshot, version.snapshot_id).payload["direct_generation"]
        assert version.payload == raw[0] == audit["raw_llm_response"]
        assert read_preview(session, 1557444, now=NOW)["preview"] == raw[0]
    assert (
        process_fixture(factory, 1557444, payload_provider=provider, clock=lambda: NOW)["state"]
        == "already_processed"
    )


def test_worker_candidates_are_six_hour_priority_window_only(setup_db):
    from types import SimpleNamespace

    from app.workers.home_preview import run_cycle

    _, factory = setup_db
    settings = SimpleNamespace(
        home_preview_vertex_model="test", google_cloud_project="", home_preview_search_enabled=True
    )
    assert run_cycle(factory, settings=settings, clock=lambda: NOW)["candidates"] == [1557444]
    assert (
        run_cycle(factory, settings=settings, execute=True, clock=lambda: NOW)["state"]
        == "not_configured"
    )
    with factory() as session:
        assert session.scalar(select(HomePreviewAttempt)) is None
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        fixture.kickoff_at = NOW + timedelta(hours=6, seconds=1)
        session.commit()
    assert run_cycle(factory, settings=settings, clock=lambda: NOW)["candidates"] == []
    with factory() as session:
        fixture = session.scalar(select(Fixture).where(Fixture.external_id == 1557444))
        fixture.kickoff_at = NOW + timedelta(hours=6)
        session.commit()
        assert read_preview(session, 1557444, now=NOW)["generation_due_at"] is not None
    assert run_cycle(factory, settings=settings, clock=lambda: NOW)["candidates"] == [1557444]
    assert (
        run_cycle(factory, settings=settings, clock=lambda: NOW + timedelta(hours=6))["candidates"]
        == []
    )
