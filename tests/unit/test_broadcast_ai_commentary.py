from __future__ import annotations

import json

import pytest

from app.services.broadcast_ai_commentary import (
    AI_COMMENTARY_SYSTEM_PROMPT,
    build_ai_commentary_payload,
    build_ai_model_input,
    build_ai_user_prompt,
    build_delta_summary,
    build_match_timing,
    build_score_state,
    build_stats_map,
    is_ai_review_hydrated,
    validate_ai_commentary_output,
)
from app.services.broadcast_program import _is_ai_review_cache_stale

pytestmark = pytest.mark.unit


def _snapshot(**overrides):
    payload = {
        "fixtureId": 1489373,
        "leagueName": "FIFA World Cup",
        "home": "홈팀명",
        "away": "원정팀명",
        "homeCode": "홈",
        "awayCode": "원정",
        "score": "1 : 0",
        "clock": "63'",
        "addedTime": "",
        "status": "2H",
        "stats": [
            {"type": "xG", "home": 1.42, "away": 0.73, "homeDisplay": "1.42", "awayDisplay": "0.73"},
            {"type": "유효슈팅", "home": 5, "away": 2, "homeDisplay": "5", "awayDisplay": "2"},
            {"type": "코너킥", "home": 6, "away": 1, "homeDisplay": "6", "awayDisplay": "1"},
        ],
        "events": [
            {
                "kind": "goal",
                "team_side": "home",
                "minute": 23,
                "clock_label": "23'",
                "title_ko": "득점",
                "score_label": "1 : 0",
                "player": {"name": "Player Name", "name_ko": "선수명", "short_name_ko": "선수명"},
            }
        ],
        "momentum": {
            "available": True,
            "home": 64,
            "away": 36,
            "trend": "home",
            "intensity": "medium",
            "reasons": ["최근 유효슈팅 증가", "최근 코너킥 증가"],
            "history": [{"elapsed": 62, "minuteKey": 62, "displayMinute": "62'", "value": 31}],
            "updatedAt": "2026-06-14T00:00:00Z",
        },
        "lineups": [],
        "playerStats": {},
        "playerRatings": {},
        "standings": {"group_name": "", "rows": []},
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize(
    ("status", "clock", "phase", "recommended"),
    [
        ("NS", "", "pre_match", "pre_match_context"),
        ("1H", "8'", "early_first_half", "live_summary"),
        ("2H", "63'", "mid_second_half", "live_summary"),
        ("2H", "90+4'", "second_half_stoppage", "live_summary"),
        ("HT", "45'", "half_time", "halftime_summary"),
        ("FT", "90'", "full_time", "fulltime_summary"),
    ],
)
def test_match_timing_phase_cases(status, clock, phase, recommended):
    timing = build_match_timing(_snapshot(status=status, clock=clock))

    assert timing["phase"] == phase
    assert timing["recommendedCommentaryType"] == recommended
    assert timing["phaseInstruction"]
    if phase == "full_time":
        assert timing["isFinal"] is True
        assert timing["timePerspective"] == "post_match"
    if phase == "mid_second_half":
        assert "확정" in timing["phaseInstruction"]


def test_match_timing_supports_korean_status_labels():
    timing = build_match_timing(_snapshot(status="후반", clock="63'"))

    assert timing["status"] == "2H"
    assert timing["phase"] == "mid_second_half"


def test_match_timing_late_second_half_label_is_not_duplicate():
    timing = build_match_timing(_snapshot(status="2H", clock="80'"))

    assert timing["phase"] == "late_second_half"
    assert timing["phaseLabel"] == "후반 막바지"


def test_ai_review_cache_stale_after_five_match_minutes():
    cached = {"reviewBasis": {"minute": 63}}

    assert _is_ai_review_cache_stale(cached, 67) is False
    assert _is_ai_review_cache_stale(cached, 68) is True


def test_score_state_parses_leader():
    score = build_score_state(_snapshot(score="1 : 0"))

    assert score == {
        "homeScore": 1,
        "awayScore": 0,
        "scoreLabel": "1 : 0",
        "leader": "home",
        "leaderName": "홈팀명",
        "goalDiff": 1,
        "isDraw": False,
    }


def test_stats_map_uses_type_as_key():
    stats_map = build_stats_map(_snapshot())

    assert stats_map["xG"]["home"] == 1.42
    assert stats_map["유효슈팅"]["awayDisplay"] == "2"


def test_delta_summary_uses_redis_samples_window():
    summary = build_delta_summary([
        {
            "displayMinute": "62'",
            "minuteKey": 62,
            "home": {"shotsOnGoal": 1, "corners": 1, "xg": 0.08},
            "away": {"xg": 0.01},
        },
        {
            "displayMinute": "63'",
            "minuteKey": 63,
            "home": {"shots": 1},
            "away": {},
        },
    ])

    assert summary["available"] is True
    assert summary["source"] == "redis_samples"
    assert summary["fromClock"] == "62'"
    assert summary["toClock"] == "63'"
    assert summary["leader"] == "home"
    assert summary["home"]["shotsOnGoal"] == 1
    assert summary["home"]["xG"] == 0.08
    assert any("유효슈팅" in reason for reason in summary["reasons"])


def test_ai_review_hydration_requires_first_break_minute():
    assert is_ai_review_hydrated([{"minuteKey": 22}]) is False
    assert is_ai_review_hydrated([{"minuteKey": 23}]) is True


def test_ai_payload_normalizes_momentum_events_and_availability():
    payload = build_ai_commentary_payload(
        _snapshot(),
        momentum_samples=[
            {"displayMinute": "62'", "minuteKey": 62, "home": {"shotsOnGoal": 1}, "away": {}},
        ],
    )
    context = payload["aiContext"]

    assert payload["commentaryType"] == "live_summary"
    assert context["momentumSummary"]["trendTeamName"] == "홈팀명"
    assert context["majorEvents"][0]["eventType"] == "goal"
    assert context["latestMajorEvent"]["playerName"] == "선수명"
    assert context["dataAvailability"]["hasLineups"] is False
    assert context["dataAvailability"]["hasPlayerStats"] is False
    assert context["dataAvailability"]["hasStandings"] is False


def test_ai_payload_uses_translated_flat_event_player_names():
    payload = build_ai_commentary_payload(
        _snapshot(
            events=[
                {
                    "kind": "goal",
                    "teamSide": "home",
                    "minute": 23,
                    "clockLabel": "23'",
                    "title": "득점",
                    "scoreLabel": "1 : 0",
                    "player": "메리흐 데미랄",
                    "playerShortName": "데미랄",
                    "assist": "토니 포포비치",
                    "assistShortName": "포포비치",
                }
            ]
        )
    )
    event = payload["aiContext"]["majorEvents"][0]

    assert event["playerName"] == "데미랄"
    assert event["assistName"] == "포포비치"
    assert "데미랄" in event["commentaryHint"]


def test_empty_optional_data_is_marked_unavailable():
    snapshot = _snapshot(stats=[], events=[], momentum={"available": False}, lineups=[], playerStats={}, playerRatings={})
    context = build_ai_commentary_payload(snapshot)["aiContext"]

    assert context["statsMap"] == {}
    assert context["deltaSummary"]["available"] is False
    assert context["dataAvailability"]["hasStats"] is False
    assert context["dataAvailability"]["hasEvents"] is False
    assert context["dataAvailability"]["hasMomentum"] is False


def test_prompts_include_defensive_rules_and_schema():
    payload = build_ai_commentary_payload(_snapshot())
    user_prompt = build_ai_user_prompt(payload)

    assert "전방 압박" in AI_COMMENTARY_SYSTEM_PROMPT
    assert "점유율이나 승률" in user_prompt
    assert "output_json_schema" in user_prompt
    assert "phaseInstruction" in user_prompt
    assert "5~6문장" in user_prompt
    assert "JSON은 백엔드 파싱용" in user_prompt
    assert "model_input" in user_prompt
    assert "축구 분석가처럼" in user_prompt
    assert "각 판단의 이유" in user_prompt
    assert "선수명을 넣어" in user_prompt
    assert "주요 이벤트에 선수명이 제공되면" in AI_COMMENTARY_SYSTEM_PROMPT


def test_ai_model_input_uses_compact_context_not_raw_snapshot():
    payload = build_ai_commentary_payload(
        _snapshot(
            lineups=[{"large": "lineup"}],
            playerStats={"1": {"large": "player"}},
            playerRatings={"1": "7.2"},
        )
    )
    model_input = build_ai_model_input(payload)

    assert "programSnapshot" not in model_input
    assert "recentSnapshots" not in model_input
    assert "lineups" not in json.dumps(model_input, ensure_ascii=False)
    assert model_input["aiContext"]["dataAvailability"]["hasPlayerStats"] is True
    assert model_input["aiContext"]["statsMap"]["xG"]["home"] == 1.42


def test_validate_ai_output_returns_fallback_on_invalid_json():
    payload = build_ai_commentary_payload(_snapshot())
    result = validate_ai_commentary_output("not-json", payload)

    assert result["headline"] == "경기 데이터 요약"
    assert result["oneLineSummary"]
    assert result["mainCommentary"]
    assert result["limitations"]


def test_validate_ai_output_accepts_minimum_schema_shape():
    payload = build_ai_commentary_payload(_snapshot())
    valid = {
        "commentaryType": "live_summary",
        "headline": "헤드라인",
        "oneLineSummary": "한 줄 요약",
        "mainCommentary": "63분 현재 홈팀명이 1 : 0으로 앞서고 있습니다. 누적 지표에서는 홈팀명이 xG와 유효슈팅에서 우위를 보이고 있습니다. 최근 변화량 기준으로도 홈팀의 공격 지표가 올라간 흐름입니다. 모멘텀 점수 역시 홈팀 쪽이 더 높게 나타납니다. 다만 아직 후반 중반이므로 결과를 확정적으로 말할 수는 없습니다.",
        "sentenceCount": 5,
        "usedData": ["score", "stats", "delta", "momentum"],
        "limitations": [],
    }

    result = validate_ai_commentary_output(json.dumps(valid, ensure_ascii=False), payload)

    assert result["headline"] == valid["headline"]
    assert result["timing"]["phase"] == "mid_second_half"
    assert result["matchState"]["score"] == "1 : 0"
    assert result["keyStats"] == []
    assert result["sentenceCount"] == 5
    assert result["usedData"] == ["score", "stats", "delta", "momentum"]
    assert result["limitations"] == []


def test_validate_ai_output_normalizes_compact_model_shape():
    payload = build_ai_commentary_payload(_snapshot(status="FT", clock="90'", score="1 : 1"))
    compact = {
        "commentaryType": "fulltime_summary",
        "timing": {"phase": "full_time", "phaseLabel": "경기 종료"},
        "headline": "브라질과 모로코, 1대1 무승부",
        "oneLineSummary": "양 팀이 한 골씩 주고받았습니다.",
        "mainCommentary": "제공된 스코어와 주요 스탯 기준으로 경기는 균형 있게 마무리됐습니다.",
        "matchState": {"homeScore": 1, "awayScore": 1, "scoreLabel": "1 : 1", "leader": "balanced"},
        "flow": {"description": "슈팅과 xG가 대등했습니다."},
        "recentDelta": {"available": True, "description": "막판 큰 변화는 없었습니다."},
        "momentum": {"available": True, "trend": "balanced", "description": "모멘텀 점수도 균형입니다."},
        "keyStats": [{"label": "xG", "home": "1.24", "away": "1.28"}],
        "keyEvents": [{"minute": "21'", "title": "득점", "description": "선제골"}],
    }

    result = validate_ai_commentary_output(json.dumps(compact, ensure_ascii=False), payload)

    assert result["headline"] == compact["headline"]
    assert result["timing"]["timePerspective"] == "post_match"
    assert result["matchState"]["score"] == "1 : 1"
    assert result["flow"]["summary"] == "슈팅과 xG가 대등했습니다."
    assert result["momentum"]["commentary"] == "모멘텀 점수도 균형입니다."
    assert result["keyStats"][0]["type"] == "xG"
    assert result["keyEvents"][0]["clock"] == "21'"
    assert result["limitations"] == []
