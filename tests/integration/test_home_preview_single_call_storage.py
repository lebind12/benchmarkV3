import json
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import sessionmaker

from app.models import Base, Fixture, League, Team
from app.models.home_preview import HomePreviewPublication, HomePreviewSnapshot, HomePreviewVersion
from app.schemas.home_preview import clock
from app.services.home_preview import read_preview
from app.services.home_preview_policy import identity
from app.services.home_preview_single_call_storage import publish_existing_preview
from app.services.home_preview_web import update_prediction_coverage


@pytest.fixture
def storage(isolated_db):
    engine, _ = isolated_db
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    fixture_data = json.loads(
        (Path(__file__).parents[1] / "fixtures/home_preview/section-targets.json").read_text()
    )
    payload = fixture_data["payload"]
    payload["analysis"]["key_absences"]["data"][0]["reason"] = (
        "선발 출전 비중을 고려해 이번 경기의 주요 변수로 선택했습니다."
    )
    payload["facts"]["injuries"]["data"][0]["cause"] = {
        "status": "available",
        "reason": None,
        "as_of": payload["as_of"],
        "source_ids": ["web-sportsmole"],
        "data": {
            "code": None,
            "label": "토트넘전 부상",
            "occurred_on": "2026-10-10",
            "occurred_month": None,
        },
    }
    update_prediction_coverage(
        payload, candidate_count=3, checked_at=clock(payload["generated_at"])
    )
    with factory() as s:
        league = League(
            external_id=39,
            name="Test League",
            slug="test-league",
            type="League",
            is_active=True,
            current_season=2026,
        )
        teams = [
            Team(
                external_id=payload["fixture"][side]["external_id"],
                name=payload["fixture"][side]["name"],
                slug="test-" + side,
            )
            for side in ("home", "away")
        ]
        s.add_all([league, *teams])
        s.flush()
        match = Fixture(
            external_id=payload["fixture"]["external_id"],
            league_id=league.id,
            season_year=2026,
            home_team_id=teams[0].id,
            away_team_id=teams[1].id,
            kickoff_at=clock(payload["fixture"]["kickoff_at"]),
            status_short="NS",
        )
        s.add(match)
        s.commit()
        ident = identity(match)

    def publish(s, candidate=None, raw=None, previous=None, started="2026-10-26T00:00:00Z"):
        return publish_existing_preview(
            s,
            candidate or payload,
            input_data={"output_template": fixture_data["template"]},
            raw_response=raw or payload,
            resolution={},
            grounding={},
            actual_started_at=started,
            actual_finished_at="2026-10-26T00:01:00Z",
            expected_version_id=previous,
            expected_identity=ident,
            replay_as_of=payload["as_of"],
        )

    return engine, factory, payload, publish


def test_real_postgres_roundtrip_preserves_reason_score_injury_dates_and_media(storage):
    _engine, factory, payload, publish = storage
    with factory.begin() as s:
        result = publish(s)
    with factory() as s:
        actual = read_preview(s, payload["fixture"]["external_id"])["preview"]
        assert actual == payload
        unknown = actual["facts"]["injuries"]["data"][0]["cause"]["data"]
        assert unknown["code"] is None
        assert unknown["occurred_on"] == "2026-10-10"
        assert "2026-10-10" in actual["facts"]["injuries"]["data"][0]["detail"]
        assert (
            actual["facts"]["injuries"]["data"][1]["cause"]["data"]["occurred_on"] == "2026-10-03"
        )
        assert actual["analysis"]["player_watchpoints"] == payload["analysis"]["player_watchpoints"]
        assert len(actual["external"]["predictions"]["data"]) == 3
        evidence = s.get(HomePreviewSnapshot, result["snapshot_id"])
        assert evidence.payload["raw_llm_response"] == payload
        assert evidence.payload["targets"]["state"] == "pending_post_commit_readback"
        assert evidence.payload["actual_started_at"] == "2026-10-26T00:00:00Z"


def test_goal_failure_is_judged_from_the_committed_unmodified_payload(storage):
    from app.services.home_preview_targets import section_target_report

    _, factory, payload, publish = storage
    bad = deepcopy(payload)
    bad["external"]["predictions"]["data"].pop()
    update_prediction_coverage(bad, candidate_count=3, checked_at=clock(bad["generated_at"]))
    with factory.begin() as s:
        saved = publish(s, bad, raw=bad)
    with factory() as s:
        actual = s.get(HomePreviewVersion, saved["version_id"]).payload
        assert actual == bad
        assert not section_target_report(actual)["passed"]


def test_date_lost_between_response_and_storage_is_fatal(storage):
    _, factory, payload, publish = storage
    changed = deepcopy(payload)
    changed["facts"]["injuries"]["data"][1]["cause"]["data"]["occurred_on"] = None
    with pytest.raises(ValueError, match="llm_json_changed"), factory.begin() as s:
        publish(s, changed, raw=payload)
    with factory() as s:
        assert s.scalar(select(func.count()).select_from(HomePreviewVersion)) == 0


def test_failed_pointer_update_rolls_back_new_snapshot_and_version(storage):
    engine, factory, _payload, publish = storage
    with factory.begin() as s:
        old = publish(s)

    def fail(_conn, _cursor, statement, _params, _context, _many):
        if statement.startswith("UPDATE home_preview_publication"):
            raise RuntimeError("injected publication write failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"), factory.begin() as s:
            publish(s, previous=old["version_id"], started="2026-10-26T00:02:00Z")
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with factory() as s:
        assert s.scalar(select(HomePreviewPublication)).version_id == old["version_id"]
        assert s.scalar(select(func.count()).select_from(HomePreviewVersion)) == 1
        assert s.scalar(select(func.count()).select_from(HomePreviewSnapshot)) == 1
