"""API-Football 어댑터 검사 (MP-03).

이 파일이 확인하는 것(계획 §6 MP-03 수용 기준과 Review Focus 2):

- `test_empty_injuries_not_zero`: 빈 부상 응답을 '부상자 0명'으로 바꾸지 않는다.
- `test_questionable_preserved`: 출전 불확실 표기를 결장 확정으로 승격하지 않는다.
- `test_api_error_not_missing`: 제공자 오류를 '자료 없음'과 구분한다.
- 배당은 경기 전 승무패만 채택하고, 갱신 시각이 없거나 오래된 값은 채택하지 않는다.
- 요청 명세에는 비밀값 이름만 담기고, 숨은 재시도가 없다(호출당 명세 하나).

응답 본문은 `fixtures/api_football.json`에 기록한 모양이며 실제 호출 결과가 아니다.
live 검증은 공통 실행기(MP-04)가 준비된 뒤 따로 한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.preview.sources import api_football as api

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "api_football.json").read_text(encoding="utf-8")
)

MOMENT = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)


def test_empty_injuries_not_zero():
    """빈 배열은 '부상자 없음'의 증거가 아니다."""
    envelope = api.parse_envelope(FIXTURES["injuries_empty"])

    assert envelope.ok
    assert envelope.empty
    assert envelope.results == 0
    assert api.parse_injuries(envelope, fixture_id=1200001) == ()
    # 호출자가 이 상태를 '부상 없음'으로 읽지 않도록 의미 문장을 함께 제공한다.
    assert "부상자 없음" in api.EMPTY_INJURIES_MEANING
    assert "증거가 아니" in api.EMPTY_INJURIES_MEANING


def test_questionable_preserved():
    """출전 불확실은 불확실로 남고, 결장 확정으로 승격되지 않는다."""
    envelope = api.parse_envelope(FIXTURES["injuries_sample"])
    records = {record.player_id: record for record in api.parse_injuries(envelope, fixture_id=1200001)}

    doubtful = records[7101]
    assert doubtful.type_marker == "Questionable"
    assert doubtful.uncertainty == "uncertain"
    assert doubtful.is_confirmed_absence is False

    confirmed = records[7102]
    assert confirmed.uncertainty == "confirmed"
    assert confirmed.is_confirmed_absence is True

    unlabelled = records[7103]
    # 표기가 없으면 확정도 아니고 '없음'도 아니다.
    assert unlabelled.uncertainty == "unknown"
    assert unlabelled.is_confirmed_absence is False


def test_api_error_not_missing():
    """제공자 오류는 '자료 없음'이 아니라 실패다."""
    envelope = api.parse_envelope(FIXTURES["error_quota_exceeded"])

    assert envelope.ok is False
    assert envelope.errors
    assert envelope.empty is False
    with pytest.raises(api.ApiFootballError):
        envelope.require_ok()


def test_wrong_fixture_rejected():
    """다른 경기의 부상 자료를 이 경기 근거로 쓰지 않는다."""
    envelope = api.parse_envelope(FIXTURES["injuries_other_fixture"])

    with pytest.raises(api.WrongFixture):
        api.parse_injuries(envelope, fixture_id=1200001)


def test_fixture_identity_rejects_other_match():
    """경기 확인은 이름이 아니라 ID로 한다."""
    envelope = api.parse_envelope(FIXTURES["fixture"])
    record = api.parse_fixture_record(envelope.records[0])

    assert record.fixture_id == 1200001
    assert record.identity().fixture_id == 1200001
    assert record.kickoff_at == datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc)

    with pytest.raises(api.WrongFixture):
        api.verify_fixture(record, fixture_id=999999, home_team_id=50, away_team_id=49)
    with pytest.raises(api.WrongFixture):
        api.verify_fixture(record, fixture_id=1200001, home_team_id=49, away_team_id=50)


def test_odds_pre_match_market_and_freshness():
    """경기 전 승무패만 채택하고, 갱신 시각이 없거나 오래된 배당은 제외한다."""
    envelope = api.parse_envelope(FIXTURES["odds_sample"])
    odds = api.parse_odds(envelope, fixture_id=1200001)

    assert len(odds) == 1, "라이브 시장은 경기 전 배당으로 채택하지 않는다"
    record = odds[0]
    assert record.bookmaker == "Recorded Book A"
    assert (record.home, record.draw, record.away) == ("1.85", "3.60", "4.20")
    accepted, reason = api.odds_freshness(record, MOMENT)
    assert accepted is True
    assert reason is None

    stale_accepted, stale_reason = api.odds_freshness(record, MOMENT + timedelta(hours=7))
    assert stale_accepted is False
    assert "지난 배당" in (stale_reason or "")

    undated = api.parse_envelope(FIXTURES["odds_without_update"])
    without_update = api.parse_odds(undated, fixture_id=1200001)[0]
    no_time_accepted, no_time_reason = api.odds_freshness(without_update, MOMENT)
    assert no_time_accepted is False
    assert "갱신 시각이 없어" in (no_time_reason or "")


def test_request_specs_carry_names_not_secrets():
    """요청 명세에는 비밀값 이름만 담는다. 논리 호출당 명세 하나(숨은 재시도 없음)."""
    calls = api.d0_calls(
        1200001, league_id=39, season=2026, home_team_id=50, away_team_id=49
    )
    specs = [api.request_spec(call) for call in calls]

    assert len(specs) == len(calls)
    assert len({spec.logical_call_id for spec in specs}) == len(specs)
    for spec in specs:
        assert spec.provider == api.API_PROVIDER
        assert spec.model is None
        assert spec.secret_refs == (api.APIFOOTBALL_SECRET_REF,)
        assert "key" not in json.dumps(spec.parameters).lower() or "api_football_key" not in str(
            spec.parameters
        )
    assert specs[0].endpoint.startswith("/v3/")
    assert specs[0].parameters["id"] == 1200001


def test_catalog_call_is_separate_from_preview():
    """목록 수집 호출은 한 건이며 리그·날짜 조건을 그대로 담는다."""
    call = api.catalog_call(
        league_id=39, date="2026-11-12", timezone_name="Asia/Seoul", season=2026
    )
    spec = api.request_spec(call, module_id="fixture_catalog")

    assert call.topic == "fixture_catalog"
    assert spec.module_id == "fixture_catalog"
    assert spec.parameters["date"] == "2026-11-12"
    assert spec.parameters["timezone"] == "Asia/Seoul"


def test_standings_and_players_keep_missing_values_none():
    """제공되지 않은 값은 0이 아니라 None으로 남는다."""
    form = api.parse_team_statistics(
        api.parse_envelope(FIXTURES["form_home"]).records[0]
    )
    assert (form.played, form.wins, form.draws, form.losses) == (11, 6, 3, 2)
    assert form.form == "WWDLW"

    empty_players = api.parse_envelope(FIXTURES["players_away"])
    assert api.parse_player_statistics(empty_players) == ()

    players = api.parse_player_statistics(api.parse_envelope(FIXTURES["players_home"]))
    assert [player.player_id for player in players] == [7001]
    assert players[0].rating == "7.31"


def test_prediction_is_labelled_as_api_prediction():
    """제공자 알고리즘 예측은 매체 의견과 별도 종류로 다룬다."""
    envelope = api.parse_envelope(FIXTURES["predictions_sample"])
    prediction = api.parse_prediction(envelope, fixture_id=1200001)

    assert prediction is not None
    assert prediction.advice == "Recorded Home or draw"
    assert prediction.percent_home == "55%"
    assert prediction.updated_at is None


def test_module_has_no_transport_import():
    """이 어댑터는 전송 계층을 갖지 않는다. 실제 전송은 MP-04의 공통 실행기 몫이다."""
    source = (
        Path(__file__).resolve().parents[2] / "app" / "preview" / "sources" / "api_football.py"
    ).read_text(encoding="utf-8")

    for forbidden in ("import httpx", "import requests", "import socket", "urlopen"):
        assert forbidden not in source
