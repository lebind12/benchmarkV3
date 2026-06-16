"""Frontend-ready broadcast program snapshot service."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from sqlalchemy.orm import Session

from app.services import fixture_detail
from app.services.broadcast import (
    BROADCAST_OVERLAY_TTL_SECONDS,
    BroadcastApiFootballUnavailable,
    BroadcastOverlayError,
    _cache_get,
    _cache_set,
    lookup_broadcast_translations,
)
from app.services.broadcast_ai_commentary import (
    build_ai_commentary_payload,
    generate_ai_commentary,
    generate_match_preview,
    is_ai_review_hydrated,
    max_momentum_sample_minute,
)
from app.services.broadcast_momentum import BroadcastMomentumService
from app.services.broadcast_momentum_persistence import (
    load_persisted_broadcast_momentum_latest,
    load_persisted_broadcast_momentum_samples,
    momentum_cache_key,
    persist_broadcast_momentum_from_cache,
)
from app.workers.daily_sync.api import ApiFootballError


STAT_TYPE_MAP = {
    "Ball Possession": "점유율",
    "expected_goals": "xG",
    "Expected Goals": "xG",
    "Total Shots": "전체슈팅",
    "Shots on Goal": "유효슈팅",
    "Shots on Target": "유효슈팅",
    "Shots insidebox": "박스안슈팅",
    "Shots outsidebox": "박스밖슈팅",
    "Blocked Shots": "블록슈팅",
    "Goalkeeper Saves": "세이브",
    "Corner Kicks": "코너킥",
    "Total passes": "전체패스",
    "Passes accurate": "패스성공",
    "Passes %": "패스성공률",
    "Yellow Cards": "옐로카드",
    "Red Cards": "레드카드",
    "Fouls": "파울",
    "Offsides": "오프사이드",
}
STAT_ORDER = list(dict.fromkeys(STAT_TYPE_MAP.values()))
PROGRAM_STAT_TABS = {
    "attack": ["xG", "유효슈팅", "슈팅정확도"],
    "chance": ["전체슈팅", "박스안슈팅", "코너킥"],
    "control": ["점유율", "패스성공률", "오프사이드"],
    "discipline": ["파울", "옐로카드", "레드카드"],
}
LIVE_BLOCK_TTLS = {
    "core": 10,
    "events": 10,
    "statistics": 10,
    "players": 30,
    "lineups": 300,
}
AI_REVIEW_TTL_SECONDS = 3600


def _no_momentum_payload(now_func: Callable[[], datetime]) -> dict[str, Any]:
    return {
        "available": False,
        "home": 50,
        "away": 50,
        "trend": "unavailable",
        "intensity": "low",
        "dominance": "low",
        "tempo": "low",
        "activity": 0,
        "reasons": ["아직 이 경기의 모멘텀 데이터가 없습니다"],
        "history": [],
        "updatedAt": _now_iso(now_func),
    }


def _now_iso(now_func: Callable[[], datetime]) -> str:
    return now_func().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _ai_review_cache_key(fixture_id: int) -> str:
    return f"broadcast:fixture:{fixture_id}:ai-review"


def _is_ai_review_cache_stale(cached: dict[str, Any], current_minute: Any, *, max_age_minutes: int = 5) -> bool:
    basis = cached.get("reviewBasis") if isinstance(cached.get("reviewBasis"), dict) else {}
    cached_minute = basis.get("minute")
    if not isinstance(current_minute, int) or not isinstance(cached_minute, int):
        return False
    return current_minute - cached_minute >= max_age_minutes


def _clock_minute_value(clock: Any) -> int | None:
    text = _clean_text(clock)
    if not text:
        return None
    head = text.split("+", 1)[0].split(":", 1)[0].replace("'", "")
    return _to_int(head)


def _review_match_clock_label(timing: dict[str, Any], snapshot: dict[str, Any]) -> str | None:
    phase = str(timing.get("phase") or "")
    status = str(snapshot.get("status") or timing.get("status") or "")
    minute = timing.get("minute")
    if not isinstance(minute, int):
        minute = _clock_minute_value(snapshot.get("clock"))
    if not isinstance(minute, int):
        return None

    if phase in {"pre_match"} or status in {"경기 전", "미정"}:
        return "경기 전 기준"
    if phase in {"half_time"} or status == "하프타임":
        return "전반 45분 기준"
    if phase.startswith("extra_time") or phase in {"after_extra_time"} or status in {"연장", "연장 종료"}:
        base = max(minute - 90, 1)
        display = "15" if base >= 15 else str(base)
        extra = base - 15
        suffix = f"+{extra}" if extra > 0 else ""
        period = "연장 후반" if minute > 105 else "연장 전반"
        return f"{period} {display}{suffix}분 기준"
    if phase.startswith("early_first") or phase.startswith("mid_first") or phase.startswith("late_first") or phase == "first_half_stoppage" or status == "전반":
        display = "45" if minute >= 45 else str(max(minute, 1))
        extra = minute - 45
        suffix = f"+{extra}" if extra > 0 else ""
        return f"전반 {display}{suffix}분 기준"
    if (
        phase.startswith("early_second")
        or phase.startswith("mid_second")
        or phase.startswith("late_second")
        or phase in {"second_half_stoppage", "full_time"}
        or status in {"후반", "종료"}
    ):
        second_half_minute = max(minute - 45, 1)
        display = "45" if second_half_minute >= 45 else str(second_half_minute)
        extra = second_half_minute - 45
        suffix = f"+{extra}" if extra > 0 else ""
        return f"후반 {display}{suffix}분 기준"
    return f"{minute}분 기준"


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _name_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _to_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = value.replace("%", "")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _to_int(value: Any) -> int | None:
    parsed = _to_number(value)
    if parsed is None:
        return None
    return int(parsed)


def _display_stat(value: Any) -> str:
    if value is None:
        return "0"
    return str(value)


def _compact_code(value: Any, fallback: str = "") -> str:
    text = _clean_text(value)
    if not text or len(text) < 2:
        return fallback
    return text.upper()


def _score_from_fixture(fixture: dict[str, Any]) -> str:
    goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
    return f"{goals.get('home') or 0} : {goals.get('away') or 0}"


def _clock_from_fixture(fixture: dict[str, Any]) -> str:
    status = (fixture.get("fixture") or {}).get("status") if isinstance(fixture.get("fixture"), dict) else {}
    elapsed = status.get("elapsed") if isinstance(status, dict) else None
    if elapsed is None:
        return "00:00"
    return f"{int(elapsed):02d}:00"


def _added_time_from_fixture(fixture: dict[str, Any]) -> str:
    status = (fixture.get("fixture") or {}).get("status") if isinstance(fixture.get("fixture"), dict) else {}
    extra = status.get("extra") if isinstance(status, dict) else None
    return f"+{extra or 0}"


def _status_from_fixture(fixture: dict[str, Any]) -> str:
    status = (fixture.get("fixture") or {}).get("status") if isinstance(fixture.get("fixture"), dict) else {}
    short = str(status.get("short") or "").upper() if isinstance(status, dict) else ""
    long = status.get("long") if isinstance(status, dict) else None
    status_map = {
        "TBD": "미정",
        "NS": "경기 전",
        "1H": "전반",
        "HT": "하프타임",
        "2H": "후반",
        "ET": "연장",
        "BT": "휴식",
        "P": "승부차기",
        "SUSP": "중단",
        "INT": "중단",
        "FT": "종료",
        "AET": "연장 종료",
        "PEN": "승부차기 종료",
        "PST": "연기",
        "CANC": "취소",
        "ABD": "중단",
        "AWD": "몰수",
        "WO": "몰수",
        "LIVE": "라이브",
    }
    return status_map.get(short) or long or "라이브"


def _event_minute(event: dict[str, Any]) -> str:
    time_obj = event.get("time") if isinstance(event.get("time"), dict) else {}
    elapsed = time_obj.get("elapsed") or 0
    extra = time_obj.get("extra")
    return f"{elapsed}+{extra}'" if extra else f"{elapsed}'"


def _event_id_part(value: Any, fallback: str = "0") -> str:
    text = str(value if value not in (None, "") else fallback).strip()
    return "_".join(text.split())


def _stable_event_id(event: dict[str, Any]) -> str:
    time_obj = event.get("time") if isinstance(event.get("time"), dict) else {}
    team = event.get("team") if isinstance(event.get("team"), dict) else {}
    player = event.get("player") if isinstance(event.get("player"), dict) else {}
    assist = event.get("assist") if isinstance(event.get("assist"), dict) else {}
    return "-".join(
        [
            _event_id_part(time_obj.get("elapsed")),
            _event_id_part(time_obj.get("extra")),
            _event_id_part(event.get("type"), "event"),
            _event_id_part(event.get("detail"), "detail"),
            _event_id_part(team.get("id"), "team"),
            _event_id_part(player.get("id"), "player"),
            _event_id_part(assist.get("id"), "assist"),
        ]
    )


def _event_kind(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "").lower()
    detail = str(event.get("detail") or "").lower()
    if "goal" in event_type and "own" in detail:
        return "own-goal"
    if "goal" in event_type:
        return "goal"
    if "subst" in event_type:
        return "substitution"
    if "var" in event_type:
        return "var"
    if "card" in event_type and ("red" in detail or "second yellow" in detail):
        return "red-card"
    if "card" in event_type and "yellow" in detail:
        return "yellow-card"
    if "card" in event_type:
        return "card"
    return None


def _event_title(kind: str) -> str:
    return {
        "goal": "득점",
        "own-goal": "자책골",
        "substitution": "선수 교체",
        "yellow-card": "경고",
        "red-card": "퇴장",
        "var": "VAR 판독",
        "card": "카드",
    }.get(kind, "경기 이벤트")


def _event_detail(kind: str, event: dict[str, Any]) -> str:
    raw = _clean_text(event.get("comments")) or _clean_text(event.get("detail")) or _clean_text(event.get("type"))
    key = str(raw or "").lower()
    detail_map = {
        "normal goal": "필드골",
        "own goal": "자책골",
        "penalty": "페널티킥",
        "missed penalty": "페널티킥 실축",
        "yellow card": "옐로카드",
        "red card": "레드카드",
        "second yellow card": "경고 누적 퇴장",
        "substitution": "선수 교체",
        "goal cancelled": "득점 취소",
        "goal disallowed": "득점 취소",
        "goal confirmed": "득점 인정",
        "penalty confirmed": "페널티킥 확정",
        "penalty cancelled": "페널티킥 취소",
        "card upgrade": "카드 격상",
        "card reviewed": "카드 판독",
        "red card cancelled": "퇴장 취소",
    }
    if key in detail_map:
        return detail_map[key]
    return {
        "goal": "득점 상황",
        "own-goal": "자책골",
        "substitution": "선수 교체",
        "yellow-card": "옐로카드",
        "red-card": "레드카드",
        "card": "카드",
        "var": raw or "VAR 판독",
    }.get(kind, raw or "경기 이벤트")


def _translation_value(
    translations: dict[str, dict[str, dict[str, str | None]]],
    bucket: str,
    external_id: int | None,
    name_bucket: str,
    fallback: str,
    *,
    short: bool = False,
) -> str:
    row = None
    if external_id is not None:
        row = translations.get(bucket, {}).get(str(external_id))
    if row is None:
        row = translations.get(name_bucket, {}).get(_name_key(fallback))
    if not row:
        return fallback
    if short:
        return row.get("short_name_ko") or row.get("name_ko") or fallback
    return row.get("name_ko") or fallback


def _collect_translation_inputs(
    fixture: dict[str, Any],
    events: list[dict[str, Any]],
    lineups: list[dict[str, Any]],
) -> dict[str, list[Any]]:
    league = fixture.get("league") if isinstance(fixture.get("league"), dict) else {}
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    team_ids = [home.get("id"), away.get("id")]
    team_names = [home.get("name"), away.get("name")]
    player_ids: list[Any] = []
    player_names: list[Any] = []
    coach_ids: list[Any] = []
    coach_names: list[Any] = []

    for lineup in lineups:
        team = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
        coach = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else {}
        team_ids.append(team.get("id"))
        team_names.append(team.get("name"))
        coach_ids.append(coach.get("id"))
        coach_names.append(coach.get("name"))
        for group_key in ("startXI", "substitutes"):
            for entry in lineup.get(group_key) or []:
                player = entry.get("player") if isinstance(entry, dict) and isinstance(entry.get("player"), dict) else {}
                player_ids.append(player.get("id"))
                player_names.append(player.get("name"))

    for event in events:
        for key in ("player", "assist"):
            player = event.get(key) if isinstance(event.get(key), dict) else {}
            player_ids.append(player.get("id"))
            player_names.append(player.get("name"))

    def clean_ints(values: list[Any]) -> list[int]:
        result = []
        seen = set()
        for value in values:
            if isinstance(value, int) and value > 0 and value not in seen:
                seen.add(value)
                result.append(value)
        return result

    def clean_names(values: list[Any]) -> list[str]:
        result = []
        seen = set()
        for value in values:
            text = _clean_text(value)
            key = _name_key(text)
            if text and key not in seen:
                seen.add(key)
                result.append(text)
        return result

    return {
        "league_ids": clean_ints([league.get("id")]),
        "league_names": clean_names([league.get("name")]),
        "team_ids": clean_ints(team_ids),
        "team_names": clean_names(team_names),
        "player_ids": clean_ints(player_ids),
        "player_names": clean_names(player_names),
        "coach_ids": clean_ints(coach_ids),
        "coach_names": clean_names(coach_names),
    }


def _player_stats_map(players_payload: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for team_players in players_payload:
        for entry in team_players.get("players") or []:
            player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
            stats = entry.get("statistics") or []
            stat = stats[0] if stats and isinstance(stats[0], dict) else {}
            games = stat.get("games") if isinstance(stat.get("games"), dict) else {}
            shots = stat.get("shots") if isinstance(stat.get("shots"), dict) else {}
            passes = stat.get("passes") if isinstance(stat.get("passes"), dict) else {}
            fouls = stat.get("fouls") if isinstance(stat.get("fouls"), dict) else {}
            cards = stat.get("cards") if isinstance(stat.get("cards"), dict) else {}
            goals = stat.get("goals") if isinstance(stat.get("goals"), dict) else {}
            tackles = stat.get("tackles") if isinstance(stat.get("tackles"), dict) else {}
            duels = stat.get("duels") if isinstance(stat.get("duels"), dict) else {}
            dribbles = stat.get("dribbles") if isinstance(stat.get("dribbles"), dict) else {}
            player_id = player.get("id")
            if not isinstance(player_id, int):
                continue
            rating = _to_number(games.get("rating"))
            passes_total = _to_number(passes.get("total"))
            passes_accurate = _to_number(passes.get("accuracy"))
            passes_accuracy_pct = (
                round(passes_accurate / passes_total * 100)
                if passes_total and passes_total > 0 and passes_accurate is not None
                else None
            )
            result[player_id] = {
                "rating": f"{rating:.1f}" if rating is not None else None,
                "photoUrl": _clean_text(player.get("photo")),
                "minutes": _to_number(games.get("minutes")),
                "shotsTotal": _to_number(shots.get("total")),
                "shotsOnGoal": _to_number(shots.get("on")),
                "passesTotal": passes_total,
                "passesAccurate": passes_accurate,
                "passesAccuracyPct": passes_accuracy_pct,
                "keyPasses": _to_number(passes.get("key")),
                "foulsCommitted": _to_number(fouls.get("committed")),
                "statGoals": _to_number(goals.get("total")),
                "statAssists": _to_number(goals.get("assists")),
                "saves": _to_number(goals.get("saves")),
                "goalsConceded": _to_number(goals.get("conceded")),
                "tacklesTotal": _to_number(tackles.get("total")),
                "blocks": _to_number(tackles.get("blocks")),
                "interceptions": _to_number(tackles.get("interceptions")),
                "duelsTotal": _to_number(duels.get("total")),
                "duelsWon": _to_number(duels.get("won")),
                "dribblesAttempts": _to_number(dribbles.get("attempts")),
                "dribblesSuccess": _to_number(dribbles.get("success")),
                "statYellowCards": _to_number(cards.get("yellow")),
                "statRedCards": _to_number(cards.get("red")),
            }
    return result


def _event_player_meta(
    lineups: list[dict[str, Any]],
    player_stats: dict[int, dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for lineup in lineups:
        for group_key in ("startXI", "substitutes"):
            for entry in lineup.get(group_key) or []:
                player = entry.get("player") if isinstance(entry, dict) and isinstance(entry.get("player"), dict) else {}
                player_id = player.get("id")
                if not isinstance(player_id, int):
                    continue
                result[player_id] = {
                    **result.get(player_id, {}),
                    "number": player.get("number"),
                    "photoUrl": player_stats.get(player_id, {}).get("photoUrl"),
                }
    return result


def _normalize_statistics(statistics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    home_stats = statistics[0] if len(statistics) > 0 and isinstance(statistics[0], dict) else {}
    away_stats = statistics[1] if len(statistics) > 1 and isinstance(statistics[1], dict) else {}
    home_map = {
        stat.get("type"): _display_stat(stat.get("value"))
        for stat in home_stats.get("statistics") or []
        if isinstance(stat, dict)
    }
    away_map = {
        stat.get("type"): _display_stat(stat.get("value"))
        for stat in away_stats.get("statistics") or []
        if isinstance(stat, dict)
    }

    rows_by_label: dict[str, dict[str, Any]] = {}
    for api_type, label in STAT_TYPE_MAP.items():
        if api_type not in home_map and api_type not in away_map:
            continue
        home = home_map.get(api_type, "0")
        away = away_map.get(api_type, "0")
        home_pct, away_pct = _paired_pct(home, away)
        rows_by_label[label] = {
            "label": label,
            "home": home,
            "away": away,
            "homePct": home_pct,
            "awayPct": away_pct,
        }
    return [rows_by_label[label] for label in STAT_ORDER if label in rows_by_label]


def _paired_pct(home: str, away: str) -> tuple[int, int]:
    home_value = _to_number(home) or 0
    away_value = _to_number(away) or 0
    if "%" in home or "%" in away:
        return max(0, min(100, round(home_value))), max(0, min(100, round(away_value)))
    total = home_value + away_value
    if total <= 0:
        return 50, 50
    home_pct = round(home_value / total * 100)
    return home_pct, 100 - home_pct


def _find_stat(stats: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    return next((stat for stat in stats if stat.get("label") == label), None)


def _stat_number(stats: list[dict[str, Any]], label: str, side: str) -> float | None:
    stat = _find_stat(stats, label)
    if not stat:
        return None
    return _to_number(stat.get(side))


def _program_metric(stats: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    if label != "슈팅정확도":
        return _find_stat(stats, label)
    home_shots = _stat_number(stats, "전체슈팅", "home")
    away_shots = _stat_number(stats, "전체슈팅", "away")
    home_sog = _stat_number(stats, "유효슈팅", "home")
    away_sog = _stat_number(stats, "유효슈팅", "away")
    if None in (home_shots, away_shots, home_sog, away_sog):
        return None
    home_accuracy = (home_sog / home_shots * 100) if home_shots else 0
    away_accuracy = (away_sog / away_shots * 100) if away_shots else 0
    home_pct, away_pct = _paired_pct(str(home_accuracy), str(away_accuracy))
    return {
        "id": "shooting-accuracy",
        "label": "슈팅정확도",
        "home": f"{round(home_accuracy)}%",
        "away": f"{round(away_accuracy)}%",
        "homePct": home_pct,
        "awayPct": away_pct,
    }


def _program_stats(stats: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        tab: [metric for label in labels if (metric := _program_metric(stats, label))]
        for tab, labels in PROGRAM_STAT_TABS.items()
    }


def _event_summary(events: list[dict[str, Any]], player_stats: dict[int, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for player_id, stat in player_stats.items():
        goals = stat.get("statGoals")
        result[player_id] = {
            "goals": int(goals) if isinstance(goals, (int, float)) and goals > 0 else 0,
            "yellowCards": int(stat.get("statYellowCards") or 0),
            "redCards": int(stat.get("statRedCards") or 0),
            "cardLabel": "",
        }
    for event in events:
        kind = _event_kind(event)
        player = event.get("player") if isinstance(event.get("player"), dict) else {}
        player_id = player.get("id")
        if not isinstance(player_id, int):
            continue
        summary = result.setdefault(player_id, {"goals": 0, "yellowCards": 0, "redCards": 0, "cardLabel": ""})
        if kind == "goal" and not player_stats.get(player_id, {}).get("statGoals"):
            summary["goals"] += 1
        if kind == "yellow-card":
            summary["yellowCards"] += 1
        if kind == "red-card":
            summary["redCards"] += 1
    for summary in result.values():
        summary["cardLabel"] = "RED" if summary["redCards"] > 0 else "YEL" if summary["yellowCards"] > 0 else ""
    return result


def _substitute_numbers(substitutes: list[dict[str, Any]] | None) -> dict[str, int]:
    result: dict[str, int] = {}
    for entry in substitutes or []:
        player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
        player_id = player.get("id")
        number = player.get("number")
        if isinstance(player_id, int) and isinstance(number, int):
            result[str(player_id)] = number
    return result


def _normalize_lineups(
    lineups: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, str | None]]],
    player_stats: dict[int, dict[str, Any]],
    summaries: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for lineup in lineups:
        team = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
        coach = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else {}
        team_id = team.get("id") if isinstance(team.get("id"), int) else None
        team_name = team.get("name") or "미정 팀"
        normalized = {
            "teamId": team_id,
            "name": _translation_value(translations, "teams", team_id, "team_names", team_name),
            "code": _translation_value(translations, "teams", team_id, "team_names", team_name, short=True),
            "shape": lineup.get("formation") or "4-3-3",
            "coach": _normalize_coach(coach, translations),
            "players": [],
            "substituteNumbers": _substitute_numbers(lineup.get("substitutes")),
        }
        for index, entry in enumerate((lineup.get("startXI") or [])[:11]):
            player = entry.get("player") if isinstance(entry, dict) and isinstance(entry.get("player"), dict) else {}
            normalized["players"].append(_normalize_lineup_player(player, index, translations, player_stats, summaries))
        result.append(normalized)
    return result


def _normalize_coach(
    coach: dict[str, Any],
    translations: dict[str, dict[str, dict[str, str | None]]],
) -> dict[str, Any] | None:
    if not coach.get("name"):
        return None
    coach_id = coach.get("id") if isinstance(coach.get("id"), int) else None
    name = coach.get("name") or "감독 미정"
    return {
        "id": coach_id,
        "name": _translation_value(translations, "coaches", coach_id, "coach_names", name, short=True),
        "longName": _translation_value(translations, "coaches", coach_id, "coach_names", name),
        "photoUrl": coach.get("photo") or None,
    }


def _normalize_lineup_player(
    player: dict[str, Any],
    index: int,
    translations: dict[str, dict[str, dict[str, str | None]]],
    player_stats: dict[int, dict[str, Any]],
    summaries: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    player_id = player.get("id") if isinstance(player.get("id"), int) else None
    name = player.get("name") or f"선수 {index + 1}"
    stat = player_stats.get(player_id or -1, {})
    return {
        "id": player_id,
        "no": player.get("number") or index + 1,
        "name": _translation_value(translations, "players", player_id, "player_names", name, short=True),
        "longName": _translation_value(translations, "players", player_id, "player_names", name),
        "pos": player.get("pos") or None,
        "grid": player.get("grid") or None,
        "rating": stat.get("rating"),
        "photoUrl": stat.get("photoUrl"),
        "minutes": stat.get("minutes"),
        "shotsTotal": stat.get("shotsTotal"),
        "shotsOnGoal": stat.get("shotsOnGoal"),
        "passesTotal": stat.get("passesTotal"),
        "passesAccurate": stat.get("passesAccurate"),
        "passesAccuracyPct": stat.get("passesAccuracyPct"),
        "keyPasses": stat.get("keyPasses"),
        "foulsCommitted": stat.get("foulsCommitted"),
        "statGoals": stat.get("statGoals"),
        "statAssists": stat.get("statAssists"),
        "saves": stat.get("saves"),
        "goalsConceded": stat.get("goalsConceded"),
        "tacklesTotal": stat.get("tacklesTotal"),
        "blocks": stat.get("blocks"),
        "interceptions": stat.get("interceptions"),
        "duelsTotal": stat.get("duelsTotal"),
        "duelsWon": stat.get("duelsWon"),
        "dribblesAttempts": stat.get("dribblesAttempts"),
        "dribblesSuccess": stat.get("dribblesSuccess"),
        "statYellowCards": stat.get("statYellowCards"),
        "statRedCards": stat.get("statRedCards"),
        "eventSummary": summaries.get(player_id or -1, {"goals": 0, "yellowCards": 0, "redCards": 0, "cardLabel": ""}),
    }


def _normalize_events(
    fixture: dict[str, Any],
    events: list[dict[str, Any]],
    translations: dict[str, dict[str, dict[str, str | None]]],
    player_meta: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    home_id = home.get("id")
    away_id = away.get("id")
    home_code = _translation_value(translations, "teams", home_id, "team_names", _compact_code(home.get("code"), "Home"), short=True)
    away_code = _translation_value(translations, "teams", away_id, "team_names", _compact_code(away.get("code"), "Away"), short=True)
    result = []
    for event in events:
        kind = _event_kind(event)
        if not kind:
            continue
        team = event.get("team") if isinstance(event.get("team"), dict) else {}
        player = event.get("player") if isinstance(event.get("player"), dict) else {}
        assist = event.get("assist") if isinstance(event.get("assist"), dict) else {}
        team_id = team.get("id") if isinstance(team.get("id"), int) else None
        player_id = player.get("id") if isinstance(player.get("id"), int) else None
        assist_id = assist.get("id") if isinstance(assist.get("id"), int) else None
        player_name = player.get("name") or ""
        assist_name = assist.get("name") or ""
        player_entry = player_meta.get(player_id or -1, {})
        assist_entry = player_meta.get(assist_id or -1, {})
        event_team_code = away_code if team_id == away_id else home_code
        opponent_code = home_code if team_id == away_id else away_code
        result.append({
            "id": _stable_event_id(event),
            "kind": kind,
            "teamId": team_id,
            "teamCode": event_team_code,
            "opponentCode": opponent_code,
            "minute": _event_minute(event),
            "title": _event_title(kind),
            "detail": _event_detail(kind, event),
            "playerId": player_id,
            "player": _translation_value(translations, "players", player_id, "player_names", player_name) if player_name else None,
            "playerShortName": _translation_value(translations, "players", player_id, "player_names", player_name, short=True) if player_name else None,
            "playerNumber": player_entry.get("number"),
            "playerPhotoUrl": player_entry.get("photoUrl"),
            "assistId": assist_id,
            "assist": _translation_value(translations, "players", assist_id, "player_names", assist_name) if assist_name else None,
            "assistShortName": _translation_value(translations, "players", assist_id, "player_names", assist_name, short=True) if assist_name else None,
            "assistNumber": assist_entry.get("number"),
            "assistPhotoUrl": assist_entry.get("photoUrl"),
            "score": _score_from_fixture(fixture) if kind in {"goal", "own-goal"} else None,
            "inPlayer": _translation_value(translations, "players", assist_id, "player_names", assist_name) if kind == "substitution" and assist_name else None,
            "inPlayerShortName": _translation_value(translations, "players", assist_id, "player_names", assist_name, short=True) if kind == "substitution" and assist_name else None,
            "inPlayerNumber": assist_entry.get("number") if kind == "substitution" else None,
            "inPlayerPhotoUrl": assist_entry.get("photoUrl") if kind == "substitution" else None,
            "outPlayer": _translation_value(translations, "players", player_id, "player_names", player_name) if kind == "substitution" and player_name else None,
            "outPlayerShortName": _translation_value(translations, "players", player_id, "player_names", player_name, short=True) if kind == "substitution" and player_name else None,
            "outPlayerNumber": player_entry.get("number") if kind == "substitution" else None,
            "outPlayerPhotoUrl": player_entry.get("photoUrl") if kind == "substitution" else None,
            "teamLogoUrl": team.get("logo") or (home.get("logo") if team_id == home_id else away.get("logo") if team_id == away_id else None),
        })
    return result


class BroadcastProgramSnapshotService:
    def __init__(
        self,
        session: Session,
        *,
        api_client: Any,
        cache: Any,
        now_func: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.api_client = api_client
        self.cache = cache
        self.now_func = now_func or (lambda: datetime.now(timezone.utc))

    def _cache_key(self, external_id: int, block: str) -> str:
        return f"broadcast:fixture:{external_id}:program:{block}"

    def _cached_or_fetch(self, external_id: int, block: str, fetch: Callable[[], Any]) -> Any:
        key = self._cache_key(external_id, block)
        cached = _cache_get(self.cache, key)
        if cached is not None:
            return cached
        value = fetch()
        if value is not None:
            _cache_set(self.cache, key, value, LIVE_BLOCK_TTLS.get(block, BROADCAST_OVERLAY_TTL_SECONDS))
        return value

    def _has_redis_momentum(self, fixture_id: int) -> bool:
        return any(
            _cache_get(self.cache, momentum_cache_key(fixture_id, suffix)) is not None
            for suffix in ("latest", "samples", "last")
        )

    def _cached_or_persisted_momentum(self, fixture_id: int) -> dict[str, Any]:
        latest = _cache_get(self.cache, momentum_cache_key(fixture_id, "latest"))
        if isinstance(latest, dict):
            return latest
        persisted = load_persisted_broadcast_momentum_latest(
            self.session,
            fixture_external_id=fixture_id,
        )
        if isinstance(persisted, dict):
            return persisted
        return _no_momentum_payload(self.now_func)

    def _momentum_samples(self, fixture_id: int) -> list[dict[str, Any]]:
        samples = _cache_get(self.cache, momentum_cache_key(fixture_id, "samples"))
        if isinstance(samples, list):
            return [sample for sample in samples if isinstance(sample, dict)]
        return load_persisted_broadcast_momentum_samples(
            self.session,
            fixture_external_id=fixture_id,
        )

    def get_first_live_snapshot(self, *, league_slug: str | None = None) -> dict[str, Any] | None:
        fixtures = self.api_client.get_live_fixtures()
        if not fixtures:
            return None
        fixture = fixtures[0]
        fixture_id = ((fixture.get("fixture") or {}).get("id") if isinstance(fixture.get("fixture"), dict) else None)
        if not isinstance(fixture_id, int):
            return None
        return self.get_snapshot(fixture_id, league_slug=league_slug, core_override=fixture)

    def get_snapshot(
        self,
        external_id: int,
        *,
        league_slug: str | None = None,
        core_override: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        snapshot_key = self._cache_key(external_id, "snapshot")
        cached = _cache_get(self.cache, snapshot_key)
        if isinstance(cached, dict):
            fixture_id = cached.get("fixtureId") if isinstance(cached.get("fixtureId"), int) else external_id
            cached["momentum"] = self._cached_or_persisted_momentum(fixture_id)
            cached.pop("aiContext", None)
            cached["cacheHit"] = True
            return cached
        try:
            fixture = core_override or self._cached_or_fetch(external_id, "core", lambda: self.api_client.get_fixture(external_id))
            if not isinstance(fixture, dict):
                return None
            events = self._cached_or_fetch(external_id, "events", lambda: self.api_client.get_events(external_id)) or []
            lineups = self._cached_or_fetch(external_id, "lineups", lambda: self.api_client.get_lineups(external_id)) or []
            statistics = self._cached_or_fetch(external_id, "statistics", lambda: self.api_client.get_statistics(external_id)) or []
            players = self._cached_or_fetch(external_id, "players", lambda: self.api_client.get_players(external_id)) or []
        except (ApiFootballError, BroadcastApiFootballUnavailable) as exc:
            raise BroadcastOverlayError("broadcast_upstream_unavailable") from exc

        payload = self._assemble_snapshot(
            fixture=fixture,
            events=events,
            lineups=lineups,
            statistics=statistics,
            players=players,
            league_slug=league_slug,
        )
        _cache_set(self.cache, snapshot_key, payload, BROADCAST_OVERLAY_TTL_SECONDS)
        return payload

    def _assemble_snapshot(
        self,
        *,
        fixture: dict[str, Any],
        events: list[dict[str, Any]],
        lineups: list[dict[str, Any]],
        statistics: list[dict[str, Any]],
        players: list[dict[str, Any]],
        league_slug: str | None,
    ) -> dict[str, Any]:
        translations = lookup_broadcast_translations(self.session, **_collect_translation_inputs(fixture, events, lineups))
        league = fixture.get("league") if isinstance(fixture.get("league"), dict) else {}
        teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
        home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
        away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
        fixture_obj = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
        home_id = home.get("id") if isinstance(home.get("id"), int) else None
        away_id = away.get("id") if isinstance(away.get("id"), int) else None
        player_stats = _player_stats_map(players)
        summaries = _event_summary(events, player_stats)
        meta = _event_player_meta(lineups, player_stats)
        stats = _normalize_statistics(statistics)
        normalized_events = _normalize_events(fixture, events, translations, meta)
        fixture_id = fixture_obj.get("id") or 0
        standings = self._standings(fixture_id)
        home_name = home.get("name") or "홈"
        away_name = away.get("name") or "원정"
        home_english_code = _compact_code(home.get("code"), "Home")
        away_english_code = _compact_code(away.get("code"), "Away")

        has_redis_momentum = self._has_redis_momentum(fixture_id)
        if has_redis_momentum:
            momentum = BroadcastMomentumService(self.cache, now_func=self.now_func).update_and_get(
                fixture_id=fixture_id,
                fixture=fixture,
                statistics=statistics,
                events=normalized_events,
            )
            if momentum.get("available") is False:
                momentum = self._cached_or_persisted_momentum(fixture_id)
            else:
                try:
                    persist_broadcast_momentum_from_cache(
                        self.session,
                        self.cache,
                        fixture_external_id=fixture_id,
                        latest=momentum,
                    )
                    self.session.commit()
                except Exception:
                    self.session.rollback()
        else:
            momentum = load_persisted_broadcast_momentum_latest(
                self.session,
                fixture_external_id=fixture_id,
            ) or _no_momentum_payload(self.now_func)
            try:
                seeded = BroadcastMomentumService(self.cache, now_func=self.now_func).update_and_get(
                    fixture_id=fixture_id,
                    fixture=fixture,
                    statistics=statistics,
                    events=normalized_events,
                )
                if seeded.get("available") is not False:
                    persist_broadcast_momentum_from_cache(
                        self.session,
                        self.cache,
                        fixture_external_id=fixture_id,
                        latest=seeded,
                    )
                    self.session.commit()
            except Exception:
                self.session.rollback()

        return {
            "fixtureId": fixture_id,
            "leagueId": league.get("id"),
            "leagueName": _translation_value(translations, "leagues", league.get("id"), "league_names", league.get("name") or "API-Football 라이브"),
            "leagueShortName": _translation_value(translations, "leagues", league.get("id"), "league_names", league.get("name") or "API-Football 라이브", short=True),
            "season": league.get("season"),
            "home": _translation_value(translations, "teams", home_id, "team_names", home_name),
            "away": _translation_value(translations, "teams", away_id, "team_names", away_name),
            "homeId": home_id,
            "awayId": away_id,
            "homeCode": _translation_value(translations, "teams", home_id, "team_names", home_name, short=True),
            "awayCode": _translation_value(translations, "teams", away_id, "team_names", away_name, short=True),
            "homeEnglishCode": home_english_code,
            "awayEnglishCode": away_english_code,
            "homeLogoUrl": home.get("logo"),
            "awayLogoUrl": away.get("logo"),
            "score": _score_from_fixture(fixture),
            "clock": _clock_from_fixture(fixture),
            "addedTime": _added_time_from_fixture(fixture),
            "status": _status_from_fixture(fixture),
            "kickoffAt": fixture_obj.get("date"),
            "venue": (fixture_obj.get("venue") or {}).get("name") if isinstance(fixture_obj.get("venue"), dict) else "라이브 경기장",
            "standings": standings,
            "lineups": _normalize_lineups(lineups, translations, player_stats, summaries),
            "playerStats": {str(player_id): stat for player_id, stat in player_stats.items()},
            "playerRatings": {str(player_id): stat["rating"] for player_id, stat in player_stats.items() if stat.get("rating")},
            "stats": stats,
            "programStats": _program_stats(stats),
            "events": normalized_events,
            "momentum": momentum,
            "polling": {
                "intervalSeconds": BROADCAST_OVERLAY_TTL_SECONDS,
                "generatedAt": _now_iso(self.now_func),
            },
            "leagueSlug": league_slug,
            "cacheHit": False,
        }

    def generate_ai_review(
        self,
        external_id: int,
        *,
        league_slug: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        snapshot = self.get_snapshot(external_id, league_slug=league_slug)
        if snapshot is None:
            raise BroadcastOverlayError("fixture_not_found")
        fixture_id = snapshot.get("fixtureId") if isinstance(snapshot.get("fixtureId"), int) else external_id
        samples = self._momentum_samples(fixture_id)
        max_minute = max_momentum_sample_minute(samples)
        if not is_ai_review_hydrated(samples):
            return {
                "available": False,
                "reason": "hydration_break_pending",
                "minimumMinute": 23,
                "currentMaxMinute": max_minute,
                "message": "모멘텀 데이터가 23분까지 수집된 뒤 AI 경기리뷰를 생성할 수 있습니다.",
            }
        payload = build_ai_commentary_payload(
            snapshot,
            recent_snapshots=[],
            momentum_samples=samples,
            commentary_type="auto",
            tone="broadcast",
            detail_level="medium",
        )
        timing = payload.get("aiContext", {}).get("matchTiming", {})
        cache_key = _ai_review_cache_key(fixture_id)
        if not force_refresh:
            cached = _cache_get(self.cache, cache_key)
            if isinstance(cached, dict) and not _is_ai_review_cache_stale(cached, timing.get("minute")):
                basis = cached.get("reviewBasis") if isinstance(cached.get("reviewBasis"), dict) else {}
                if basis and not basis.get("matchClockLabel"):
                    timing = {
                        "phase": basis.get("phase"),
                        "minute": basis.get("minute"),
                        "status": basis.get("status"),
                    }
                    basis["matchClockLabel"] = _review_match_clock_label(timing, snapshot)
                    cached["reviewBasis"] = basis
                return {**cached, "cached": True}
        response = {
            "available": True,
            "minimumMinute": 23,
            "currentMaxMinute": max_minute,
            "cached": False,
            "reviewBasis": {
                "status": snapshot.get("status"),
                "clock": snapshot.get("clock"),
                "minute": timing.get("minute"),
                "phase": timing.get("phase"),
                "phaseLabel": timing.get("phaseLabel"),
                "matchClockLabel": _review_match_clock_label(timing, snapshot),
                "generatedAt": _now_iso(self.now_func),
            },
            "commentary": generate_ai_commentary(payload),
        }
        _cache_set(self.cache, cache_key, response, AI_REVIEW_TTL_SECONDS)
        return response

    def generate_match_preview(self, external_id: int, *, league_slug: str | None = None) -> dict[str, Any]:
        snapshot = self.get_snapshot(external_id, league_slug=league_slug)
        if snapshot is None:
            raise BroadcastOverlayError("fixture_not_found")

        home_name = snapshot.get("home") or "Home"
        away_name = snapshot.get("away") or "Away"
        league_name = snapshot.get("leagueName") or snapshot.get("leagueShortName") or "Football"
        lineups = snapshot.get("lineups") if isinstance(snapshot.get("lineups"), list) else []
        standings = snapshot.get("standings") if isinstance(snapshot.get("standings"), dict) else {}
        payload = {
            "fixture": {
                "fixtureId": snapshot.get("fixtureId") or external_id,
                "leagueId": snapshot.get("leagueId"),
                "leagueName": league_name,
                "leagueShortName": snapshot.get("leagueShortName"),
                "season": snapshot.get("season"),
                "round": None,
                "kickoffAt": snapshot.get("kickoffAt"),
                "venue": snapshot.get("venue"),
            },
            "teams": {
                "home": {
                    "id": snapshot.get("homeId"),
                    "name": home_name,
                    "nameKo": snapshot.get("home"),
                    "code": snapshot.get("homeEnglishCode") or snapshot.get("homeCode"),
                },
                "away": {
                    "id": snapshot.get("awayId"),
                    "name": away_name,
                    "nameKo": snapshot.get("away"),
                    "code": snapshot.get("awayEnglishCode") or snapshot.get("awayCode"),
                },
            },
            "preMatchContext": {
                "lineups": lineups,
                "standings": {
                    "group_name": standings.get("group_name") or standings.get("groupName") or "",
                    "rows": standings.get("rows") if isinstance(standings.get("rows"), list) else [],
                },
            },
            "webSearchContext": {
                "enabled": True,
                "preferredSourceTypes": [
                    "official team or federation announcements",
                    "FIFA or competition official pages",
                    "reliable sports media",
                    "recent press conference or team news articles",
                ],
                "queryHints": [
                    f"{home_name} vs {away_name} preview {league_name}",
                    f"{home_name} team news injuries latest",
                    f"{away_name} team news injuries latest",
                    f"{home_name} predicted lineup {away_name}",
                    f"{away_name} predicted lineup {home_name}",
                    f"{home_name} {away_name} score prediction",
                    f"{home_name} recent form {away_name}",
                    f"{away_name} recent form {home_name}",
                ],
            },
        }
        result = generate_match_preview(payload)
        return {
            "available": bool(result.get("available")),
            "markdown": result.get("markdown") or "",
            "generatedAt": _now_iso(self.now_func),
            "fixtureId": snapshot.get("fixtureId") or external_id,
            "reason": result.get("reason"),
        }

    def _standings(self, fixture_id: int) -> dict[str, Any] | None:
        try:
            payload = fixture_detail.get_league_standings(self.session, fixture_id)
        except Exception:
            return None
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or not rows:
            return None
        return {
            "group_name": payload.get("group_name") or "",
            "rows": [
                {
                    "rank": row.get("rank") or 0,
                    "team_id": ((row.get("team") or {}).get("external_id") if isinstance(row.get("team"), dict) else 0) or 0,
                    "team_name": (
                        ((row.get("team") or {}).get("name_ko") if isinstance(row.get("team"), dict) else None)
                        or ((row.get("team") or {}).get("name") if isinstance(row.get("team"), dict) else "")
                    ),
                    "team_code": (
                        ((row.get("team") or {}).get("short_name_ko") if isinstance(row.get("team"), dict) else None)
                        or ((row.get("team") or {}).get("name_ko") if isinstance(row.get("team"), dict) else None)
                        or ((row.get("team") or {}).get("name") if isinstance(row.get("team"), dict) else "")
                    ),
                    "played": row.get("played") or 0,
                    "win": row.get("win") or 0,
                    "draw": row.get("draw") or 0,
                    "loss": row.get("loss") or 0,
                    "goals_for": row.get("goals_for") or 0,
                    "goals_against": row.get("goals_against") or 0,
                    "goal_diff": row.get("goal_diff") or 0,
                    "points": row.get("points") or 0,
                }
                for row in rows
            ],
        }
