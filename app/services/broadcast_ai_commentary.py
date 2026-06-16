"""Build AI commentary payloads from broadcast program snapshots.

This module does not call a model. It prepares deterministic context, prompts,
and output validation so provider integrations can stay thin.
"""
from __future__ import annotations

import os
import json
import re
import tempfile
from typing import Any

import httpx

from app.core.config import get_settings


COMMENTARY_TYPES = {
    "auto",
    "live_summary",
    "momentum_update",
    "event_reaction",
    "halftime_summary",
    "fulltime_summary",
    "pre_match_context",
}
TONES = {"neutral", "broadcast", "analytical", "short"}
DETAIL_LEVELS = {"low", "medium", "high"}

PHASE_LABELS = {
    "pre_match": "경기 전",
    "early_first_half": "전반 초반",
    "mid_first_half": "전반 중반",
    "late_first_half": "전반 후반",
    "first_half_stoppage": "전반 추가시간",
    "half_time": "하프타임",
    "early_second_half": "후반 초반",
    "mid_second_half": "후반 중반",
    "late_second_half": "후반 막바지",
    "second_half_stoppage": "후반 추가시간",
    "full_time": "경기 종료",
    "extra_time_first_half": "연장 전반",
    "extra_time_second_half": "연장 후반",
    "extra_time_stoppage": "연장 추가시간",
    "after_extra_time": "연장 종료",
    "penalty_shootout": "승부차기",
    "final_after_penalties": "승부차기 종료",
    "interrupted": "경기 중단",
    "unknown": "판단 불가",
}

PHASE_INSTRUCTIONS = {
    "pre_match": "경기 전 프리뷰를 작성한다. 실시간 스탯, 모멘텀, 경기 이벤트가 없으면 언급하지 않는다.",
    "early_first_half": "전반 초반이므로 흐름을 강하게 단정하지 않고, 현재까지의 초기 지표와 주요 이벤트만 조심스럽게 설명한다.",
    "mid_first_half": "전반 중반 현재 흐름을 요약한다. 현재 스코어, 누적 스탯, 이벤트를 종합하되 전반 전체 흐름을 단정하지 않는다.",
    "late_first_half": "전반 막바지 흐름을 요약한다. 전반 스코어, 주요 이벤트, 누적 스탯을 중심으로 설명하되 경기 결과를 예단하지 않는다.",
    "first_half_stoppage": "전반 추가시간 기준으로 전반 막판 변수와 현재 스코어, 주요 스탯을 설명한다. 하프타임 전이면 전반 종료 표현은 쓰지 않는다.",
    "half_time": "전반 종료 요약을 작성한다. 전반 스코어, 주요 이벤트, 핵심 누적 스탯, 후반 관전 포인트를 포함한다.",
    "early_second_half": "후반 초반 흐름을 요약한다. 전반 이후 변화가 확인되는 데이터만 설명하고 결과 확정 표현은 사용하지 않는다.",
    "mid_second_half": "후반 중반 현재 흐름을 요약한다. 현재 스코어, 누적 스탯, 최근 변화량, 모멘텀을 종합하되 경기 결과를 확정적으로 말하지 않는다.",
    "late_second_half": "후반 막바지 기준으로 현재 스코어, 누적 스탯, 최근 변화량, 남은 변수 가능성을 설명한다. status가 FT가 아니면 결과를 확정하지 않는다.",
    "second_half_stoppage": "후반 추가시간 기준으로 현재 스코어와 마지막 변수, 누적 스탯, 최근 변화량을 설명한다. status가 FT가 아니면 경기 종료 표현은 사용하지 않는다.",
    "full_time": "경기 종료 후 리뷰를 작성한다. 최종 스코어, 승부를 가른 이벤트, 핵심 스탯, 결과와 경기 내용의 관계를 설명한다. 남은 시간이 있는 것처럼 표현하지 않는다.",
    "extra_time_first_half": "연장 전반 흐름을 요약한다. 정규시간 이후의 현재 스코어와 연장 구간 데이터만 조심스럽게 설명한다.",
    "extra_time_second_half": "연장 후반 흐름을 요약한다. 현재 스코어와 연장 막판 변수를 설명하되 종료 전이면 결과를 확정하지 않는다.",
    "extra_time_stoppage": "연장 추가시간 기준으로 마지막 변수와 현재 스코어를 설명한다. 종료 전이면 결과 확정 표현은 사용하지 않는다.",
    "after_extra_time": "연장 종료 후 요약을 작성한다. 연장까지의 최종 흐름과 승부차기 여부를 제공된 데이터 기준으로 설명한다.",
    "penalty_shootout": "승부차기 진행 상황을 요약한다. 제공된 이벤트와 스코어 외의 심리 상태나 킥 방향은 추측하지 않는다.",
    "final_after_penalties": "승부차기 종료 후 리뷰를 작성한다. 최종 결과와 제공된 이벤트, 핵심 스탯만 근거로 설명한다.",
    "interrupted": "정상 진행 상태가 아님을 안내하고, 제공된 스코어와 이벤트, 스탯만 요약한다.",
    "unknown": "경기 시점이 불명확하므로 제공된 데이터만 중립적으로 요약한다.",
}

STATUS_ALIASES = {
    "경기 전": "NS",
    "미정": "TBD",
    "전반": "1H",
    "하프타임": "HT",
    "후반": "2H",
    "연장": "ET",
    "휴식": "BT",
    "승부차기": "P",
    "중단": "SUSP",
    "종료": "FT",
    "연장 종료": "AET",
    "승부차기 종료": "PEN",
    "연기": "PST",
    "취소": "CANC",
    "몰수": "AWD",
    "라이브": "LIVE",
}

LIVE_STATUSES = {"1H", "2H", "ET", "P", "LIVE"}
PRE_MATCH_STATUSES = {"NS", "TBD"}
FINAL_STATUSES = {"FT", "AET", "PEN"}
INTERRUPTED_STATUSES = {"SUSP", "INT", "PST", "CANC", "ABD", "AWD", "WO"}

STAT_TO_DELTA_KEY = {
    "xG": "xG",
    "전체슈팅": "shots",
    "유효슈팅": "shotsOnGoal",
    "박스안슈팅": "insideBoxShots",
    "코너킥": "corners",
    "점유율": "possession",
    "패스성공": "passesAccurate",
    "옐로카드": "yellowCards",
    "레드카드": "redCards",
}

DELTA_LABELS = {
    "goals": "득점",
    "xG": "xG",
    "shots": "전체슈팅",
    "shotsOnGoal": "유효슈팅",
    "insideBoxShots": "박스 안 슈팅",
    "corners": "코너킥",
    "possession": "점유율",
    "passesAccurate": "패스 성공",
    "yellowCards": "옐로카드",
    "redCards": "레드카드",
    "cards": "카드",
    "dangerEvents": "위험 이벤트",
}

DELTA_KEYS = tuple(DELTA_LABELS.keys())

AI_COMMENTARY_SYSTEM_PROMPT = """당신은 축구 경기 데이터를 바탕으로 한국어 방송용 코멘터리를 생성하는 데이터 기반 해설 엔진이다.
당신은 실제 경기를 영상으로 본 중계자가 아니며, 반드시 제공된 데이터만 사용한다.
데이터에 없는 전술, 위치, 압박, 선수 움직임, 감독 의도, 심리 상태를 추측하지 않는다.
단순 현상 나열이 아니라 축구 분석가처럼 스코어, 주요 이벤트, 누적 스탯, 최근 변화량, 모멘텀의 관계를 해석한다.
각 핵심 판단에는 데이터상 이유를 붙인다. 예: 어떤 팀이 앞서 보이면 xG, 유효슈팅, 박스 안 슈팅, 코너킥, 최근 delta, 모멘텀 중 실제 제공된 근거를 연결해 설명한다.
이유를 설명할 때도 데이터에 없는 전술 용어, 위치 정보, 압박 방식, 선수 움직임은 추정하지 않는다.
주요 이벤트에 선수명이 제공되면 가능한 한 선수명을 포함해 설명한다.
누적 스탯, 최근 변화량 delta, 모멘텀을 반드시 구분한다.
matchTiming.phaseInstruction을 최우선으로 따른다.
경기 중이면 결과 확정 표현을 사용하지 않는다.
경기 종료 후이면 진행 중 표현을 사용하지 않는다.
하프타임이면 전반 종료 요약으로 작성한다.
경기 전이면 프리뷰만 작성한다.
interrupted이면 정상 진행 상태가 아님을 안내하고 제공된 정보만 요약한다.
programSnapshot.stats는 배열이며 type 기준으로 찾아야 한다.
aiContext.statsMap이 있으면 statsMap을 우선한다.
aiContext.deltaSummary가 있으면 deltaSummary를 최근 변화량 판단의 최우선 근거로 사용한다.
deltaSummary가 없고 recentSnapshots가 있으면 비교 가능한 값만 delta로 계산할 수 있다.
deltaSummary와 recentSnapshots가 모두 없으면 정확한 변화량 수치를 추정하지 않는다.
momentum.home과 momentum.away는 모멘텀 점수이며 승률이나 점유율이 아니다.
momentum.history.value는 방향값이며 실제 슈팅 수, 점유율, xG가 아니다.
lineups, playerStats, playerRatings, standings.rows가 비어 있으면 언급하지 않는다.
모든 응답은 한국어로 작성한다.
반드시 지정된 JSON 형식만 반환한다.

금지 표현:
- 전방 압박을 강하게 건다
- 압박 강도가 높다
- 수비 라인을 높였다
- 수비 라인을 내렸다
- 측면을 집중 공략한다
- 하프스페이스를 활용한다
- 감독의 의도가 드러난다
- 선수들이 심리적으로 흔들린다
- 경기를 완전히 지배한다
- 잠그기에 들어갔다
- 시간을 끌고 있다
- 홈팀의 승리 확률은 64%다
- 홈팀이 64%의 흐름을 점유하고 있다

권장 대체 표현:
- 누적 공격 지표에서 앞서고 있다
- xG와 유효슈팅 기준으로 더 위협적인 기회를 만들고 있다
- 모멘텀 계산상 홈팀 쪽 흐름이 더 높게 나타난다
- 최근 변화량 기준으로 홈팀의 공격 지표가 올라갔다
- 선제골 이후에도 유효슈팅과 xG 우위가 이어져 리드의 근거가 스탯에서도 확인된다
- 최근 delta에서 코너킥과 유효슈팅이 함께 늘어 흐름 변화의 근거가 된다
- 득점 이벤트와 누적 기회 지표가 같은 방향을 가리킨다
- 점유율은 높지만 위협적인 슈팅으로 이어진 정도는 함께 봐야 한다
- 스탯과 이벤트 변화량 기준으로 흐름이 기울고 있다
"""

AI_COMMENTARY_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "commentaryType",
        "headline",
        "oneLineSummary",
        "mainCommentary",
        "sentenceCount",
        "usedData",
        "limitations",
    ],
    "additionalProperties": False,
    "properties": {
        "commentaryType": {
            "type": "string",
            "enum": [
                "live_summary",
                "momentum_update",
                "event_reaction",
                "halftime_summary",
                "fulltime_summary",
                "pre_match_context",
            ],
        },
        "headline": {
            "type": "string",
            "description": "짧은 제목. 경기 흐름을 과장하지 않는다.",
        },
        "oneLineSummary": {
            "type": "string",
            "description": "한 문장 요약.",
        },
        "mainCommentary": {
            "type": "string",
            "description": "프론트에 표시할 5~6문장의 자연어 경기 코멘터리. 하나의 문단으로 작성한다.",
        },
        "sentenceCount": {
            "type": "integer",
            "minimum": 5,
            "maximum": 6,
            "description": "mainCommentary의 문장 수.",
        },
        "usedData": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["score", "events", "stats", "delta", "momentum", "standings", "lineups", "playerStats"],
            },
            "description": "코멘터리 작성에 실제로 사용한 데이터 종류.",
        },
        "limitations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "데이터 부족으로 언급하지 않은 항목. 없으면 빈 배열.",
        },
    },
}

AI_MATCH_PREVIEW_SYSTEM_PROMPT = """당신은 축구 경기 프리뷰를 작성하는 한국어 축구 분석가다.
목표는 경기 전 관점의 상세한 프리뷰를 작성하는 것이다.
내부 경기 데이터는 fixture 식별, 양 팀명, 대회명, 킥오프, 장소, 제공된 라인업, 기본 선수명 확인용으로만 사용한다.
경기가 이미 시작되었거나 종료되었더라도 fixture의 현재 status, clock, score, live events, live statistics, momentum은 프리뷰 판단에 사용하지 않는다.
현재 경기 상황을 언급하지 말고, "현재 1H", "0-0", "초반 점유율", "방금", "현재까지" 같은 라이브 표현도 쓰지 않는다.
프리뷰는 경기 시작 전 독자가 읽는 글처럼 작성한다.

Web Search 결과를 최신 맥락의 최우선 근거로 사용한다.
공식 발표, 대회/협회/구단/대표팀 공식 채널, 신뢰 가능한 스포츠 매체를 우선한다.
베팅 매체, 블로그, 위키, 커뮤니티는 보조 근거로만 사용하고 출처 성격을 구분한다.
검색 결과끼리 충돌하면 더 최신 정보와 공식 출처를 우선한다.
검색 결과가 부족하면 추측하지 말고 신뢰도를 낮추며 한계에 명시한다.

반드시 포함할 내용:
1. 경기 한줄 전망
2. 경기 배경과 맥락
3. 양 팀 주요 전략 또는 경기 접근 포인트
4. 팀별 주목할 선수
5. 예상 스코어와 그 이유
6. 변수와 리스크
7. 사용한 주요 출처와 한계
8. 마지막에 현재 작성한 프리뷰 문서 전체의 요약

분석 품질 규칙:
- 단순 소개가 아니라 왜 그런 전망이 나오는지 근거를 연결한다.
- 전략은 최근 보도, 예상 라인업, 제공된 라인업, 최근 경기 흐름, 감독/선수 발언 등 확인 가능한 정보에 근거할 때만 작성한다.
- 출처에 없는 구체 전술, 압박 방식, 수비 라인 높이, 선수 움직임, 감독 의도, 심리 상태는 단정하지 않는다.
- 다만 라인업/포메이션이 제공된 경우에는 "라인업상", "구성상", "가능성이 있다" 수준으로 보수적으로 해석할 수 있다.
- 예상 스코어는 확정처럼 쓰지 않고 프리뷰 관점의 예측으로 제시한다.
- 예상 스코어에는 confidence(low, medium, high)를 한국어로 함께 표시한다.
- 선수명은 제공된 한국어 번역명이 있으면 한국어 번역명을 우선 사용한다.
- 번역명이 없으면 원문 이름을 사용하되, 필요한 경우 괄호로 병기한다.

출력 규칙:
- 한국어로 작성한다.
- JSON을 반환하지 않는다.
- 마크다운 본문만 반환한다.
- 코드블록으로 감싸지 않는다.
- h2/h3 제목, 굵게, 목록, 표, 인용문, 링크를 적극 활용한다.
- 출처 링크는 문장 끝 또는 "주요 출처" 섹션에 마크다운 링크로 포함한다.
- 문서 마지막에는 반드시 "## 요약" 섹션을 추가하고, 핵심 판단을 3~5개 bullet로 압축한다.
"""

MATCH_PREVIEW_REQUIRED_SECTIONS = [
    "## 한줄 전망",
    "## 경기 배경",
    "## 주요 전략 포인트",
    "## 주목할 선수",
    "## 예상 스코어",
    "## 변수와 리스크",
    "## 주요 출처와 한계",
    "## 요약",
]


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _status_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return STATUS_ALIASES.get(text, text.upper())


def parse_clock(clock: Any) -> dict[str, int | str | None]:
    text = _clean_text(clock)
    if not text:
        return {"clock": None, "baseMinute": None, "extraMinute": None, "minute": None}
    match = re.search(r"(\d+)(?:\s*\+\s*(\d+))?", text)
    if not match:
        return {"clock": text, "baseMinute": None, "extraMinute": None, "minute": None}
    base = int(match.group(1))
    extra = int(match.group(2) or 0)
    return {
        "clock": text,
        "baseMinute": base,
        "extraMinute": extra if extra else None,
        "minute": base + extra,
    }


def build_match_timing(snapshot: dict[str, Any]) -> dict[str, Any]:
    status = _status_code(snapshot.get("status"))
    parsed_clock = parse_clock(snapshot.get("clock"))
    base_minute = parsed_clock["baseMinute"]
    extra_minute = parsed_clock["extraMinute"]
    minute = parsed_clock["minute"]

    phase = "unknown"
    if status in PRE_MATCH_STATUSES:
        phase = "pre_match"
    elif status == "HT":
        phase = "half_time"
    elif status in INTERRUPTED_STATUSES:
        phase = "interrupted"
    elif status == "FT":
        phase = "full_time"
    elif status == "AET":
        phase = "after_extra_time"
    elif status == "PEN":
        phase = "final_after_penalties"
    elif status == "P":
        phase = "penalty_shootout"
    elif status == "1H" and isinstance(minute, int):
        if extra_minute or minute > 45:
            phase = "first_half_stoppage"
        elif minute <= 15:
            phase = "early_first_half"
        elif minute <= 30:
            phase = "mid_first_half"
        else:
            phase = "late_first_half"
    elif status == "2H" and isinstance(minute, int):
        if extra_minute or minute >= 90:
            phase = "second_half_stoppage"
        elif minute <= 60:
            phase = "early_second_half"
        elif minute <= 75:
            phase = "mid_second_half"
        else:
            phase = "late_second_half"
    elif status in {"ET", "BT"} and isinstance(minute, int):
        if extra_minute or minute > 120:
            phase = "extra_time_stoppage"
        elif minute <= 105:
            phase = "extra_time_first_half"
        else:
            phase = "extra_time_second_half"
    elif status == "LIVE":
        phase = "unknown"

    if phase == "pre_match":
        perspective = "pre_match"
    elif phase in {"half_time"}:
        perspective = "break"
    elif phase in {"full_time", "after_extra_time", "final_after_penalties"}:
        perspective = "post_match"
    elif phase == "interrupted":
        perspective = "interrupted"
    elif phase == "unknown":
        perspective = "unknown"
    else:
        perspective = "in_progress"

    recommended = {
        "pre_match": "pre_match_context",
        "half_time": "halftime_summary",
        "full_time": "fulltime_summary",
        "after_extra_time": "fulltime_summary",
        "final_after_penalties": "fulltime_summary",
    }.get(phase, "live_summary" if perspective == "in_progress" else "auto")

    return {
        "status": status or None,
        "clock": parsed_clock["clock"],
        "addedTime": snapshot.get("addedTime") or None,
        "baseMinute": base_minute,
        "extraMinute": extra_minute,
        "minute": minute,
        "phase": phase,
        "phaseLabel": PHASE_LABELS[phase],
        "isLive": perspective == "in_progress",
        "isFinal": perspective == "post_match",
        "isPreMatch": perspective == "pre_match",
        "isHalfTime": phase == "half_time",
        "isExtraTime": phase.startswith("extra_time") or phase == "after_extra_time",
        "isPenaltyShootout": phase in {"penalty_shootout", "final_after_penalties"},
        "timePerspective": perspective,
        "recommendedCommentaryType": recommended,
        "phaseInstruction": PHASE_INSTRUCTIONS[phase],
    }


def build_score_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    score_label = _clean_text(snapshot.get("score"))
    home_score = away_score = None
    if score_label:
        match = re.search(r"(\d+)\s*[:\-]\s*(\d+)", score_label)
        if match:
            home_score = int(match.group(1))
            away_score = int(match.group(2))
    if home_score is None or away_score is None:
        leader = "unclear"
    elif home_score > away_score:
        leader = "home"
    elif away_score > home_score:
        leader = "away"
    else:
        leader = "balanced"
    leader_name = snapshot.get("home") if leader == "home" else snapshot.get("away") if leader == "away" else None
    goal_diff = abs(home_score - away_score) if home_score is not None and away_score is not None else None
    return {
        "homeScore": home_score,
        "awayScore": away_score,
        "scoreLabel": score_label,
        "leader": leader,
        "leaderName": leader_name,
        "goalDiff": goal_diff,
        "isDraw": leader == "balanced",
    }


def build_stats_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats_map: dict[str, dict[str, Any]] = {}
    for stat in snapshot.get("stats") or []:
        if not isinstance(stat, dict):
            continue
        key = _clean_text(stat.get("type") or stat.get("label"))
        if not key:
            continue
        stats_map[key] = {
            "home": stat.get("home"),
            "away": stat.get("away"),
            "homeDisplay": stat.get("homeDisplay") or stat.get("home_display") or str(stat.get("home") if stat.get("home") is not None else ""),
            "awayDisplay": stat.get("awayDisplay") or stat.get("away_display") or str(stat.get("away") if stat.get("away") is not None else ""),
        }
    return stats_map


def _empty_delta_summary() -> dict[str, Any]:
    return {
        "available": False,
        "source": "unavailable",
        "windowMinutes": None,
        "fromClock": None,
        "toClock": None,
        "home": {},
        "away": {},
        "leader": "unclear",
        "reasons": [],
    }


def _delta_score(delta: dict[str, Any]) -> float:
    return (
        float(delta.get("goals") or 0) * 10.0
        + float(delta.get("xG") or delta.get("xg") or 0) * 12.0
        + float(delta.get("shots") or 0) * 2.0
        + float(delta.get("shotsOnGoal") or 0) * 4.0
        + float(delta.get("insideBoxShots") or 0) * 3.0
        + float(delta.get("corners") or 0) * 1.5
        + float(delta.get("dangerEvents") or 0) * 4.0
        + float(delta.get("possession") or 0) * 0.05
        + float(delta.get("passesAccurate") or 0) * 0.03
    )


def _normalize_delta_side(side: dict[str, Any]) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for key in DELTA_KEYS:
        raw_key = "xg" if key == "xG" and "xG" not in side else key
        value = side.get(raw_key)
        if isinstance(value, (int, float)):
            normalized[key] = round(float(value), 3)
    if "cards" not in normalized:
        cards = normalized.get("yellowCards", 0.0) + normalized.get("redCards", 0.0)
        if cards:
            normalized["cards"] = cards
    return normalized


def _delta_reason(side_label: str, key: str, value: float) -> str:
    display = f"{value:+.2f}" if key == "xG" else f"{value:+g}"
    return f"{side_label} {DELTA_LABELS.get(key, key)} {display}"


def _sum_delta_sides(samples: list[dict[str, Any]]) -> tuple[dict[str, float], dict[str, float]]:
    home: dict[str, float] = {}
    away: dict[str, float] = {}
    for sample in samples:
        for target, side in ((home, sample.get("home") or {}), (away, sample.get("away") or {})):
            normalized = _normalize_delta_side(side)
            for key, value in normalized.items():
                target[key] = round(target.get(key, 0.0) + value, 3)
    return home, away


def build_delta_summary(momentum_samples: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    samples = [sample for sample in (momentum_samples or []) if isinstance(sample, dict)]
    if not samples:
        return _empty_delta_summary()

    window_samples = samples[-12:]
    current = window_samples[-1]
    previous = window_samples[0] if len(window_samples) >= 2 else None
    home, away = _sum_delta_sides(window_samples)
    if not home and not away:
        return _empty_delta_summary()

    home_score = _delta_score(home)
    away_score = _delta_score(away)
    if abs(home_score - away_score) < 1.0:
        leader = "balanced"
    else:
        leader = "home" if home_score > away_score else "away"

    reasons: list[str] = []
    for side_key, side_label, delta in (("home", "홈팀", home), ("away", "원정팀", away)):
        _ = side_key
        for key in ("goals", "shotsOnGoal", "corners", "xG", "shots", "insideBoxShots", "dangerEvents"):
            value = float(delta.get(key) or 0)
            if value > 0:
                reasons.append(_delta_reason(side_label, key, value))
            if len(reasons) >= 5:
                break
        if len(reasons) >= 5:
            break

    from_minute = previous.get("displayMinute") if previous else None
    to_minute = current.get("displayMinute")
    from_key = previous.get("minuteKey") if previous else None
    to_key = current.get("minuteKey")
    window = to_key - from_key if isinstance(from_key, int) and isinstance(to_key, int) and to_key >= from_key else None
    return {
        "available": True,
        "source": "redis_samples",
        "windowMinutes": window,
        "fromClock": from_minute,
        "toClock": to_minute,
        "home": home,
        "away": away,
        "leader": leader,
        "reasons": reasons,
    }


def build_momentum_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    momentum = snapshot.get("momentum") if isinstance(snapshot.get("momentum"), dict) else {}
    trend = momentum.get("trend") or "unavailable"
    trend_team = snapshot.get("home") if trend == "home" else snapshot.get("away") if trend == "away" else None
    return {
        "available": bool(momentum.get("available")),
        "homeScore": momentum.get("home") if momentum.get("available") else None,
        "awayScore": momentum.get("away") if momentum.get("available") else None,
        "trend": trend,
        "trendTeamName": trend_team,
        "intensity": momentum.get("intensity") if momentum.get("available") else None,
        "dominance": momentum.get("dominance") if momentum.get("available") else None,
        "tempo": momentum.get("tempo") if momentum.get("available") else None,
        "activity": momentum.get("activity") if momentum.get("available") else None,
        "reasons": momentum.get("reasons") or [],
        "history": momentum.get("history") or [],
        "updatedAt": momentum.get("updatedAt"),
    }


def _player_display_name(player: Any) -> str | None:
    if isinstance(player, str):
        return player or None
    if not isinstance(player, dict):
        return None
    return player.get("short_name_ko") or player.get("name_ko") or player.get("name")


def _event_player_display_name(event: dict[str, Any], *, short_key: str, name_key: str, raw_key: str) -> str | None:
    value = event.get(short_key) or event.get(name_key)
    if isinstance(value, str) and value:
        return value
    return _player_display_name(event.get(raw_key))


def _event_type(event: dict[str, Any]) -> str:
    kind = str(event.get("kind") or "").lower()
    title = str(event.get("title_ko") or event.get("detail_ko") or "").lower()
    if "own" in kind or "자책" in title:
        return "own_goal"
    if "goal" in kind or "득점" in title:
        return "goal"
    if "red" in kind or "퇴장" in title:
        return "red_card"
    if "penalty" in kind or "penalty" in title or "페널티" in title:
        return "penalty"
    if "var" in kind or "var" in title:
        return "var"
    if "yellow" in kind or "경고" in title:
        return "yellow_card"
    if "substitution" in kind or "교체" in title:
        return "substitution"
    return kind or "event"


def _event_priority(event_type: str) -> int:
    order = {
        "goal": 1,
        "own_goal": 2,
        "red_card": 3,
        "penalty": 4,
        "var": 5,
        "yellow_card": 7,
        "substitution": 8,
    }
    return order.get(event_type, 99)


def _event_minute_sort_value(event: dict[str, Any]) -> tuple[int, int]:
    minute = event.get("minute")
    extra = event.get("extra")
    if isinstance(minute, int):
        return minute + (extra if isinstance(extra, int) and extra > 0 else 0), (
            extra if isinstance(extra, int) and extra > 0 else 0
        )
    parsed = parse_clock(minute)
    parsed_minute = parsed.get("minute")
    parsed_extra = parsed.get("extraMinute")
    if isinstance(parsed_minute, int):
        return parsed_minute, parsed_extra if isinstance(parsed_extra, int) else 0
    return -1, 0


def build_major_events(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    events: list[dict[str, Any]] = []
    for event in snapshot.get("events") or []:
        if not isinstance(event, dict):
            continue
        event_type = _event_type(event)
        if _event_priority(event_type) > 8:
            continue
        team_side = event.get("team_side") or event.get("teamSide")
        team_name = snapshot.get("home") if team_side == "home" else snapshot.get("away") if team_side == "away" else None
        player_name = _event_player_display_name(
            event,
            short_key="playerShortName",
            name_key="player",
            raw_key="player",
        )
        assist_name = _event_player_display_name(
            event,
            short_key="assistShortName",
            name_key="assist",
            raw_key="assist",
        )
        if event_type == "substitution":
            player_name = event.get("outPlayerShortName") or event.get("outPlayer") or player_name
            assist_name = event.get("inPlayerShortName") or event.get("inPlayer") or assist_name
        clock = event.get("clock_label") or event.get("clockLabel") or (
            f"{event.get('minute')}+{event.get('extra')}'" if event.get("extra") else f"{event.get('minute')}'"
        )
        title = event.get("title_ko") or event.get("title") or event_type
        hint_parts = [str(clock), str(team_name or ""), str(title)]
        if player_name:
            hint_parts.append(str(player_name))
        sort_minute, sort_extra = _event_minute_sort_value(event)
        normalized = {
            "clock": clock,
            "minute": event.get("minute"),
            "extra": event.get("extra"),
            "_sortMinute": sort_minute,
            "_sortExtra": sort_extra,
            "teamSide": team_side,
            "teamName": team_name,
            "eventType": event_type,
            "title": title,
            "playerName": player_name,
            "assistName": assist_name,
            "scoreAtEvent": event.get("score_label") or event.get("scoreLabel"),
            "commentaryHint": " ".join(part for part in hint_parts if part),
        }
        events.append(normalized)
    events.sort(
        key=lambda item: (
            item.get("_sortMinute") or -1,
            item.get("_sortExtra") or 0,
            -_event_priority(str(item.get("eventType"))),
        )
    )
    latest = events[-1] if events else None
    events.sort(
        key=lambda item: (
            _event_priority(str(item.get("eventType"))),
            -(item.get("_sortMinute") or -1),
            -(item.get("_sortExtra") or 0),
        )
    )
    for item in events:
        item.pop("_sortMinute", None)
        item.pop("_sortExtra", None)
    if latest:
        latest.pop("_sortMinute", None)
        latest.pop("_sortExtra", None)
    return events[:12], latest


def build_data_availability(
    snapshot: dict[str, Any],
    *,
    recent_snapshots: list[dict[str, Any]] | None,
    stats_map: dict[str, Any],
    delta_summary: dict[str, Any],
    momentum_summary: dict[str, Any],
) -> dict[str, bool]:
    standings = snapshot.get("standings") if isinstance(snapshot.get("standings"), dict) else {}
    return {
        "hasStats": bool(stats_map),
        "hasRecentSnapshots": bool(recent_snapshots),
        "hasDeltaSummary": delta_summary.get("available") is True,
        "hasMomentum": momentum_summary.get("available") is True,
        "hasEvents": bool(snapshot.get("events")),
        "hasLineups": bool(snapshot.get("lineups")),
        "hasPlayerStats": bool(snapshot.get("playerStats")),
        "hasPlayerRatings": bool(snapshot.get("playerRatings")),
        "hasStandings": bool(standings.get("rows")),
    }


def build_ai_context(
    program_snapshot: dict[str, Any],
    *,
    recent_snapshots: list[dict[str, Any]] | None = None,
    momentum_samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    stats_map = build_stats_map(program_snapshot)
    delta_summary = build_delta_summary(momentum_samples)
    momentum_summary = build_momentum_summary(program_snapshot)
    major_events, latest_major_event = build_major_events(program_snapshot)
    context = {
        "matchTiming": build_match_timing(program_snapshot),
        "scoreState": build_score_state(program_snapshot),
        "statsMap": stats_map,
        "deltaSummary": delta_summary,
        "momentumSummary": momentum_summary,
        "majorEvents": major_events,
        "latestMajorEvent": latest_major_event,
        "dataAvailability": {},
    }
    context["dataAvailability"] = build_data_availability(
        program_snapshot,
        recent_snapshots=recent_snapshots,
        stats_map=stats_map,
        delta_summary=delta_summary,
        momentum_summary=momentum_summary,
    )
    return context


def build_ai_commentary_payload(
    program_snapshot: dict[str, Any],
    *,
    recent_snapshots: list[dict[str, Any]] | None = None,
    momentum_samples: list[dict[str, Any]] | None = None,
    commentary_type: str = "auto",
    tone: str = "broadcast",
    detail_level: str = "medium",
) -> dict[str, Any]:
    if commentary_type not in COMMENTARY_TYPES:
        commentary_type = "auto"
    if tone not in TONES:
        tone = "broadcast"
    if detail_level not in DETAIL_LEVELS:
        detail_level = "medium"
    ai_context = build_ai_context(
        program_snapshot,
        recent_snapshots=recent_snapshots,
        momentum_samples=momentum_samples,
    )
    if commentary_type == "auto":
        commentary_type = ai_context["matchTiming"]["recommendedCommentaryType"]
    return {
        "commentaryType": commentary_type,
        "tone": tone,
        "detailLevel": detail_level,
        "programSnapshot": program_snapshot,
        "recentSnapshots": recent_snapshots or [],
        "aiContext": ai_context,
    }


def build_ai_user_prompt(payload: dict[str, Any]) -> str:
    model_input = build_ai_model_input(payload)
    return (
        "다음 축구 경기 요약 데이터와 서버 전처리 aiContext를 바탕으로 프론트에 표시할 경기 데이터 요약 코멘터리를 생성하세요.\n"
        "최종 사용자는 JSON을 보지 않는다. JSON은 백엔드 파싱용이며, 자연어 코멘터리는 headline, oneLineSummary, mainCommentary에만 담으세요.\n"
        "mainCommentary는 반드시 5~6문장의 한국어 자연어 문단으로 작성하세요. 줄바꿈 없이 하나의 문단으로 작성하세요.\n"
        "mainCommentary는 호출 시점의 경기 상태, 스코어, 주요 이벤트, 누적 공격 지표, 최근 변화량(delta), 모멘텀을 가능한 범위에서 종합하세요.\n"
        "현상만 나열하지 말고 축구 분석가처럼 각 판단의 이유를 설명하세요. 단, 이유는 반드시 제공된 데이터의 관계에서만 도출하세요.\n"
        "예를 들어 리드 팀을 평가할 때는 득점 이벤트, xG, 유효슈팅, 박스 안 슈팅, 코너킥, 최근 delta, 모멘텀 중 실제 있는 근거를 연결하세요.\n"
        "주요 이벤트에 playerName 또는 assistName이 있으면 선수명을 넣어 장면을 구체화하세요.\n"
        "해당 데이터가 비어 있으면 그 항목은 언급하지 말고, limitations에 짧게 기록하세요.\n"
        "aiContext.matchTiming의 phase, timePerspective, phaseInstruction을 최우선으로 따르세요.\n"
        "statsMap을 누적 스탯의 기준으로 사용하세요.\n"
        "aiContext.deltaSummary가 있으면 최근 변화량 판단의 최우선 근거로 사용하세요.\n"
        "deltaSummary와 recentSnapshots가 없으면 delta 수치를 추정하지 마세요.\n"
        "momentum.home과 momentum.away는 점유율이나 승률이 아닌 모멘텀 점수입니다.\n"
        "누적 스탯, 최근 변화량, 모멘텀을 구분해서 설명하세요.\n"
        "데이터에 없는 실제 전술, 위치, 압박, 선수 움직임, 감독 의도는 추측하지 마세요.\n"
        "경기 중이면 결과 확정 표현을 쓰지 말고, 경기 종료 후이면 진행 중 표현을 쓰지 마세요.\n"
        "반드시 아래 output_json_schema와 동일한 키만 가진 JSON 객체 하나만 반환하세요. 마크다운 코드블록, 설명문, 접두사, 접미사를 붙이지 마세요.\n\n"
        f"model_input:\n{json.dumps(model_input, ensure_ascii=False, separators=(',', ':'))}\n\n"
        f"output_json_schema:\n{json.dumps(AI_COMMENTARY_OUTPUT_SCHEMA, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_match_preview_user_prompt(payload: dict[str, Any]) -> str:
    """Build a pre-match preview prompt that deliberately ignores live match state."""
    fixture = payload.get("fixture") if isinstance(payload.get("fixture"), dict) else {}
    teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
    pre_match_context = (
        payload.get("preMatchContext") if isinstance(payload.get("preMatchContext"), dict) else {}
    )
    web_search_context = (
        payload.get("webSearchContext") if isinstance(payload.get("webSearchContext"), dict) else {}
    )

    preview_input = {
        "fixture": {
            "fixtureId": fixture.get("fixtureId") or fixture.get("externalId") or fixture.get("id"),
            "leagueName": fixture.get("leagueName"),
            "season": fixture.get("season"),
            "round": fixture.get("round"),
            "kickoffAt": fixture.get("kickoffAt"),
            "venue": fixture.get("venue"),
            "homeTeam": teams.get("home"),
            "awayTeam": teams.get("away"),
        },
        "preMatchContext": {
            "lineups": pre_match_context.get("lineups"),
            "recentForm": pre_match_context.get("recentForm"),
            "standings": pre_match_context.get("standings"),
            "h2h": pre_match_context.get("h2h"),
            "injuries": pre_match_context.get("injuries"),
            "playerTranslations": pre_match_context.get("playerTranslations"),
            "coachTranslations": pre_match_context.get("coachTranslations"),
        },
        "webSearchContext": web_search_context,
        "excludedLiveFields": [
            "fixture.status",
            "fixture.clock",
            "fixture.score",
            "live events",
            "live statistics",
            "momentum",
            "in-match player stats",
        ],
    }

    return (
        "다음 입력을 바탕으로 축구 경기 프리뷰를 작성하세요.\n"
        "이 프리뷰는 경기 시작 전 읽는 글이어야 합니다. fixture가 이미 진행 중이어도 현재 경기 상태를 반영하지 마세요.\n"
        "현재 스코어, 현재 시간, 라이브 이벤트, 실시간 스탯, 모멘텀, 경기 중 선수 기록은 절대 언급하지 마세요.\n"
        "Web Search 결과가 있으면 최신성 있는 팀 뉴스, 부상/결장, 예상 라인업, 감독/선수 발언, 최근 경기 맥락의 근거로 우선 사용하세요.\n"
        "내부 데이터는 팀명, 대회, 킥오프, 장소, 라인업/선수명 확인용으로만 사용하세요.\n"
        "양 팀의 주요 전략은 근거가 있을 때만 자세히 작성하고, 근거가 부족한 전술적 표현은 가능성 또는 한계로 처리하세요.\n"
        "주목할 선수는 팀별 2명 이상을 추천하고, 각 선수마다 왜 주목해야 하는지 구체적으로 설명하세요.\n"
        "예상 스코어는 하나만 제시하고, confidence와 최소 4개의 이유를 함께 작성하세요.\n"
        "아래 섹션 제목을 유지하되, 각 섹션은 충분히 상세하게 작성하세요.\n"
        f"필수 섹션:\n{chr(10).join(f'- {section}' for section in MATCH_PREVIEW_REQUIRED_SECTIONS)}\n\n"
        "마크다운 본문만 반환하세요. JSON, 코드블록, 접두사, 접미사는 반환하지 마세요.\n\n"
        f"preview_input:\n{json.dumps(preview_input, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_ai_model_input(payload: dict[str, Any]) -> dict[str, Any]:
    snapshot = payload.get("programSnapshot") if isinstance(payload.get("programSnapshot"), dict) else {}
    context = payload.get("aiContext") if isinstance(payload.get("aiContext"), dict) else {}
    standings = snapshot.get("standings") if isinstance(snapshot.get("standings"), dict) else {}
    data_availability = context.get("dataAvailability") if isinstance(context.get("dataAvailability"), dict) else {}

    return {
        "commentaryType": payload.get("commentaryType"),
        "tone": payload.get("tone"),
        "detailLevel": payload.get("detailLevel"),
        "match": {
            "fixtureId": snapshot.get("fixtureId"),
            "leagueName": snapshot.get("leagueName"),
            "leagueShortName": snapshot.get("leagueShortName"),
            "season": snapshot.get("season"),
            "home": snapshot.get("home"),
            "away": snapshot.get("away"),
            "homeCode": snapshot.get("homeCode"),
            "awayCode": snapshot.get("awayCode"),
            "score": snapshot.get("score"),
            "clock": snapshot.get("clock"),
            "addedTime": snapshot.get("addedTime"),
            "status": snapshot.get("status"),
            "kickoffAt": snapshot.get("kickoffAt"),
            "venue": snapshot.get("venue"),
        },
        "aiContext": {
            "matchTiming": context.get("matchTiming"),
            "scoreState": context.get("scoreState"),
            "statsMap": context.get("statsMap"),
            "deltaSummary": context.get("deltaSummary"),
            "momentumSummary": context.get("momentumSummary"),
            "majorEvents": context.get("majorEvents"),
            "latestMajorEvent": context.get("latestMajorEvent"),
            "dataAvailability": data_availability,
        },
        "standings": {
            "group_name": standings.get("group_name"),
            "rows": standings.get("rows", [])[:8] if data_availability.get("hasStandings") else [],
        },
    }


def max_momentum_sample_minute(samples: list[dict[str, Any]] | None) -> int | None:
    minutes: list[int] = []
    for sample in samples or []:
        if not isinstance(sample, dict):
            continue
        minute_key = sample.get("minuteKey")
        if isinstance(minute_key, int):
            minutes.append(minute_key)
            continue
        elapsed = sample.get("elapsed")
        extra = sample.get("extra")
        if isinstance(elapsed, int):
            minutes.append(elapsed + (extra if isinstance(extra, int) and extra > 0 else 0))
    return max(minutes) if minutes else None


def is_ai_review_hydrated(samples: list[dict[str, Any]] | None, *, minimum_minute: int = 23) -> bool:
    max_minute = max_momentum_sample_minute(samples)
    return isinstance(max_minute, int) and max_minute >= minimum_minute


def fallback_ai_commentary(payload: dict[str, Any], reason: str = "validation_failed") -> dict[str, Any]:
    timing = payload.get("aiContext", {}).get("matchTiming", {})
    snapshot = payload.get("programSnapshot", {})
    return {
        "commentaryType": payload.get("commentaryType") or "auto",
        "timing": {
            "phase": timing.get("phase") or "unknown",
            "phaseLabel": timing.get("phaseLabel"),
            "timePerspective": timing.get("timePerspective") or "unknown",
            "minute": timing.get("minute"),
            "clock": timing.get("clock"),
            "status": timing.get("status"),
            "isLive": bool(timing.get("isLive")),
            "isFinal": bool(timing.get("isFinal")),
        },
        "headline": "경기 데이터 요약",
        "oneLineSummary": "현재 제공된 경기 데이터를 기준으로 코멘터리를 생성하지 못했습니다.",
        "mainCommentary": "스코어와 주요 스탯은 제공되어 있으나, AI 응답 형식 검증에 실패했습니다.",
        "matchState": {
            "clock": snapshot.get("clock"),
            "addedTime": snapshot.get("addedTime"),
            "score": snapshot.get("score"),
            "status": snapshot.get("status"),
            "statusText": timing.get("phaseLabel"),
        },
        "flow": {
            "leader": "unclear",
            "leaderName": None,
            "summary": "검증 실패로 흐름 요약을 생성하지 못했습니다.",
            "confidence": "low",
            "basis": [],
        },
        "recentDelta": {
            "available": False,
            "source": "unavailable",
            "windowMinutes": None,
            "fromClock": None,
            "toClock": None,
            "leader": "unclear",
            "summary": None,
            "items": [],
        },
        "momentum": {
            "available": False,
            "trend": "unavailable",
            "trendTeamName": None,
            "intensity": None,
            "homeScore": None,
            "awayScore": None,
            "commentary": None,
            "reasons": [],
        },
        "keyStats": [],
        "keyEvents": [],
        "playerSpotlights": [],
        "standingsContext": None,
        "limitations": [f"AI 응답 검증 실패: {reason}"],
    }


def _extract_json_object(raw: str) -> str | None:
    text = raw.strip()
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if fenced:
        return fenced.group(1)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


def validate_ai_commentary_output(raw: str | dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if isinstance(raw, str):
            data = json.loads(_extract_json_object(raw) or raw)
        else:
            data = raw
    except json.JSONDecodeError:
        return fallback_ai_commentary(payload, "invalid_json")
    if not isinstance(data, dict):
        return fallback_ai_commentary(payload, "not_object")
    for key in ("headline", "oneLineSummary", "mainCommentary"):
        if not _clean_text(data.get(key)):
            return fallback_ai_commentary(payload, f"empty_{key}")
    return normalize_ai_commentary_output(data, payload)


def normalize_ai_commentary_output(data: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    timing = payload.get("aiContext", {}).get("matchTiming", {})
    snapshot = payload.get("programSnapshot", {})
    score_state = payload.get("aiContext", {}).get("scoreState", {})
    delta = payload.get("aiContext", {}).get("deltaSummary", {})
    momentum = payload.get("aiContext", {}).get("momentumSummary", {})

    output = dict(data)
    output["commentaryType"] = _clean_text(output.get("commentaryType")) or payload.get("commentaryType") or "auto"
    output["timing"] = _normalize_timing_output(output.get("timing"), timing)
    output["matchState"] = _normalize_match_state_output(output.get("matchState"), snapshot, timing)
    output["flow"] = _normalize_flow_output(output.get("flow"), score_state)
    output["recentDelta"] = _normalize_recent_delta_output(output.get("recentDelta"), delta, snapshot)
    output["momentum"] = _normalize_momentum_output(output.get("momentum"), momentum)
    output["keyStats"] = _normalize_key_stats_output(output.get("keyStats"))
    output["keyEvents"] = _normalize_key_events_output(output.get("keyEvents"))
    output["playerSpotlights"] = output.get("playerSpotlights") if isinstance(output.get("playerSpotlights"), list) else []
    output["standingsContext"] = output.get("standingsContext") if isinstance(output.get("standingsContext"), str) else None
    output["sentenceCount"] = _normalize_sentence_count(output.get("sentenceCount"), output.get("mainCommentary"))
    output["usedData"] = _normalize_used_data(output.get("usedData"), payload)
    output["limitations"] = output.get("limitations") if isinstance(output.get("limitations"), list) else []
    return output


def _normalize_sentence_count(value: Any, commentary: Any) -> int:
    if isinstance(value, int) and value > 0:
        return value
    text = _clean_text(commentary)
    if not text:
        return 0
    markers = re.findall(r"(?:다\.|[.!?。！？])", text)
    return len(markers) if markers else 1


def _normalize_used_data(value: Any, payload: dict[str, Any]) -> list[str]:
    allowed = {"score", "events", "stats", "delta", "momentum", "standings", "lineups", "playerStats"}
    if isinstance(value, list):
        normalized = [item for item in value if isinstance(item, str) and item in allowed]
        if normalized:
            return normalized

    availability = payload.get("aiContext", {}).get("dataAvailability", {})
    used = ["score"]
    if availability.get("hasEvents"):
        used.append("events")
    if availability.get("hasStats"):
        used.append("stats")
    if availability.get("hasDeltaSummary"):
        used.append("delta")
    if availability.get("hasMomentum"):
        used.append("momentum")
    if availability.get("hasStandings"):
        used.append("standings")
    if availability.get("hasLineups"):
        used.append("lineups")
    if availability.get("hasPlayerStats"):
        used.append("playerStats")
    return used


def _normalize_timing_output(value: Any, timing: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "phase": source.get("phase") or timing.get("phase") or "unknown",
        "phaseLabel": source.get("phaseLabel") or timing.get("phaseLabel"),
        "timePerspective": source.get("timePerspective") or timing.get("timePerspective") or "unknown",
        "minute": source.get("minute") if source.get("minute") is not None else timing.get("minute"),
        "clock": source.get("clock") or timing.get("clock"),
        "status": source.get("status") or timing.get("status"),
        "isLive": bool(source.get("isLive") if source.get("isLive") is not None else timing.get("isLive")),
        "isFinal": bool(source.get("isFinal") if source.get("isFinal") is not None else timing.get("isFinal")),
    }


def _normalize_match_state_output(value: Any, snapshot: dict[str, Any], timing: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "clock": source.get("clock") or snapshot.get("clock"),
        "addedTime": source.get("addedTime") or snapshot.get("addedTime"),
        "score": source.get("score") or source.get("scoreLabel") or snapshot.get("score"),
        "status": source.get("status") or snapshot.get("status"),
        "statusText": source.get("statusText") or timing.get("phaseLabel"),
    }


def _normalize_flow_output(value: Any, score_state: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    leader = source.get("leader") or score_state.get("leader") or "unclear"
    if leader not in {"home", "away", "balanced", "unclear"}:
        leader = "unclear"
    basis = source.get("basis") if isinstance(source.get("basis"), list) else []
    return {
        "leader": leader,
        "leaderName": source.get("leaderName") or score_state.get("leaderName"),
        "summary": source.get("summary") or source.get("description") or "",
        "confidence": source.get("confidence") if source.get("confidence") in {"high", "medium", "low"} else "medium",
        "basis": basis,
    }


def _normalize_recent_delta_output(value: Any, delta: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    available = bool(source.get("available") if source.get("available") is not None else delta.get("available"))
    leader = source.get("leader") or delta.get("leader") or "unclear"
    if leader not in {"home", "away", "balanced", "unclear"}:
        leader = "unclear"
    return {
        "available": available,
        "source": source.get("source") or ("deltaSummary" if delta.get("available") else "unavailable"),
        "windowMinutes": source.get("windowMinutes") if source.get("windowMinutes") is not None else delta.get("windowMinutes"),
        "fromClock": source.get("fromClock") or delta.get("fromClock"),
        "toClock": source.get("toClock") or delta.get("toClock") or snapshot.get("clock"),
        "leader": leader,
        "summary": source.get("summary") or source.get("description"),
        "items": source.get("items") if isinstance(source.get("items"), list) else [],
    }


def _normalize_momentum_output(value: Any, momentum: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    trend = source.get("trend") or momentum.get("trend") or "unavailable"
    if trend not in {"home", "away", "balanced", "unavailable"}:
        trend = "unavailable"
    return {
        "available": bool(source.get("available") if source.get("available") is not None else momentum.get("available")),
        "trend": trend,
        "trendTeamName": source.get("trendTeamName") or momentum.get("trendTeamName"),
        "intensity": source.get("intensity") or momentum.get("intensity"),
        "homeScore": source.get("homeScore") if source.get("homeScore") is not None else momentum.get("homeScore"),
        "awayScore": source.get("awayScore") if source.get("awayScore") is not None else momentum.get("awayScore"),
        "commentary": source.get("commentary") or source.get("description"),
        "reasons": source.get("reasons") if isinstance(source.get("reasons"), list) else momentum.get("reasons") or [],
    }


def _normalize_key_stats_output(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "type": item.get("type") or item.get("label") or "",
                "homeValue": item.get("homeValue") if item.get("homeValue") is not None else item.get("home"),
                "awayValue": item.get("awayValue") if item.get("awayValue") is not None else item.get("away"),
                "homeDisplay": item.get("homeDisplay") or (str(item.get("home")) if item.get("home") is not None else None),
                "awayDisplay": item.get("awayDisplay") or (str(item.get("away")) if item.get("away") is not None else None),
                "interpretation": item.get("interpretation") or item.get("description") or "",
            }
        )
    return normalized


def _normalize_key_events_output(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "clock": item.get("clock") or item.get("minute") or "",
                "teamSide": item.get("teamSide"),
                "teamName": item.get("teamName"),
                "eventType": item.get("eventType") or item.get("title") or "",
                "title": item.get("title") or item.get("eventType") or "",
                "playerName": item.get("playerName"),
                "scoreAtEvent": item.get("scoreAtEvent"),
                "commentary": item.get("commentary") or item.get("description") or "",
            }
        )
    return normalized


def _vertex_access_token() -> str:
    _materialize_google_credentials_json()
    try:
        import google.auth  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except Exception as exc:
        raise RuntimeError("google_auth_unavailable") from exc

    credentials, _project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    credentials.refresh(Request())
    token = getattr(credentials, "token", None)
    if not isinstance(token, str) or not token:
        raise RuntimeError("google_auth_token_unavailable")
    return token


def _materialize_google_credentials_json() -> None:
    settings = get_settings()
    credentials_json = _clean_text(settings.google_application_credentials_json)
    if not credentials_json:
        return

    path = os.path.join(tempfile.gettempdir(), "benchmark-google-application-credentials.json")
    current = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if current == path and os.path.exists(path):
        return

    with open(path, "w", encoding="utf-8") as file:
        file.write(credentials_json)
    os.chmod(path, 0o600)
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path


def generate_ai_commentary(payload: dict[str, Any]) -> dict[str, Any]:
    """Call Vertex AI if configured; otherwise return a validated fallback."""
    settings = get_settings()
    if not settings.google_cloud_project:
        return fallback_ai_commentary(payload, "ai_provider_not_configured")

    try:
        token = _vertex_access_token()
        location = settings.google_cloud_location
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/"
            f"projects/{settings.google_cloud_project}/locations/{location}/"
            f"publishers/google/models/{settings.vertex_ai_model}:generateContent"
        )
        body = {
            "systemInstruction": {
                "parts": [{"text": AI_COMMENTARY_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_ai_user_prompt(payload)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.4,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(part.get("text") or "" for part in parts if isinstance(part, dict))
        return validate_ai_commentary_output(text, payload)
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        body = exc.response.text[:240].replace("\n", " ")
        return fallback_ai_commentary(payload, f"ai_provider_http_{status_code}:{body}")
    except Exception as exc:
        return fallback_ai_commentary(payload, f"ai_provider_error:{type(exc).__name__}")


def fallback_match_preview(payload: dict[str, Any], reason: str) -> dict[str, Any]:
    fixture = payload.get("fixture") if isinstance(payload.get("fixture"), dict) else {}
    teams = payload.get("teams") if isinstance(payload.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_name = home.get("nameKo") or home.get("name") or "홈팀"
    away_name = away.get("nameKo") or away.get("name") or "원정팀"
    league_name = fixture.get("leagueName") or "경기"
    safe_reason = str(reason).replace("`", "'")
    markdown = (
        "## 한줄 전망\n\n"
        f"**{home_name} vs {away_name}** 프리뷰를 생성하지 못했습니다.\n\n"
        "## 경기 배경\n\n"
        f"- 대회: {league_name}\n"
        f"- 경기: {home_name} vs {away_name}\n\n"
        "## 주요 출처와 한계\n\n"
        f"- AI 프리뷰 생성 과정에서 오류가 발생했습니다: `{safe_reason}`\n"
        "- 현재 화면에는 내부 fixture 정보만 표시할 수 있습니다.\n"
    )
    return {
        "available": False,
        "markdown": markdown,
        "reason": reason,
    }


def generate_match_preview(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate a markdown pre-match preview with Vertex AI Google Search grounding."""
    settings = get_settings()
    if not settings.google_cloud_project:
        return fallback_match_preview(payload, "ai_provider_not_configured")

    try:
        token = _vertex_access_token()
        location = settings.google_cloud_location
        host = "aiplatform.googleapis.com" if location == "global" else f"{location}-aiplatform.googleapis.com"
        url = (
            f"https://{host}/v1/"
            f"projects/{settings.google_cloud_project}/locations/{location}/"
            f"publishers/google/models/{settings.vertex_ai_model}:generateContent"
        )
        body = {
            "systemInstruction": {
                "parts": [{"text": AI_MATCH_PREVIEW_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": build_match_preview_user_prompt(payload)}],
                }
            ],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "temperature": 0.45,
                "maxOutputTokens": 8192,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=body,
            timeout=90.0,
        )
        response.raise_for_status()
        data = response.json()
        parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        markdown = "".join(part.get("text") or "" for part in parts if isinstance(part, dict)).strip()
        if not markdown:
            return fallback_match_preview(payload, "empty_model_response")
        return {
            "available": True,
            "markdown": markdown,
            "groundingMetadata": ((data.get("candidates") or [{}])[0]).get("groundingMetadata"),
        }
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        body = exc.response.text[:240].replace("\n", " ")
        return fallback_match_preview(payload, f"ai_provider_http_{status_code}:{body}")
    except Exception as exc:
        return fallback_match_preview(payload, f"ai_provider_error:{type(exc).__name__}")
