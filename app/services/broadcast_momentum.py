"""Redis-backed live match momentum calculation for broadcast snapshots."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.services.broadcast import _cache_get, _cache_set


MOMENTUM_TTL_SECONDS = 60 * 60 * 3
MOMENTUM_FRESH_SECONDS = 8
MOMENTUM_LOCK_SECONDS = 5
MAX_SAMPLES = 900
WINDOW_SAMPLES = 12
MOMENTUM_BASE = 12.0
LIVE_STATUS_CODES = {"1H", "HT", "2H", "ET", "BT", "P", "SUSP", "INT", "LIVE"}


STAT_KEYS = {
    "expected_goals": "xg",
    "Expected Goals": "xg",
    "Total Shots": "shots",
    "Shots on Goal": "shotsOnGoal",
    "Shots on Target": "shotsOnGoal",
    "Shots insidebox": "insideBoxShots",
    "Corner Kicks": "corners",
    "Ball Possession": "possession",
    "Total passes": "passes",
    "Passes accurate": "passesAccurate",
    "Yellow Cards": "yellowCards",
    "Red Cards": "redCards",
}

DELTA_CAPS = {
    "goals": 3.0,
    "xg": 1.5,
    "shots": 5.0,
    "shotsOnGoal": 3.0,
    "insideBoxShots": 4.0,
    "corners": 3.0,
    "passesAccurate": 80.0,
    "yellowCards": 4.0,
    "redCards": 2.0,
    "dangerEvents": 3.0,
}


def _now_iso(now_func: Callable[[], datetime]) -> str:
    return now_func().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_fresh(payload: Any, *, now: datetime, max_age_seconds: int = MOMENTUM_FRESH_SECONDS) -> bool:
    if not isinstance(payload, dict):
        return False
    updated_at = _parse_iso(payload.get("updatedAt"))
    if updated_at is None:
        return False
    age = now.astimezone(timezone.utc) - updated_at.astimezone(timezone.utc)
    return 0 <= age.total_seconds() <= max_age_seconds


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


def _status_short(fixture: dict[str, Any]) -> str:
    fixture_obj = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    status = fixture_obj.get("status") if isinstance(fixture_obj.get("status"), dict) else {}
    return str(status.get("short") or "").upper()


def _elapsed(fixture: dict[str, Any]) -> int | None:
    fixture_obj = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    status = fixture_obj.get("status") if isinstance(fixture_obj.get("status"), dict) else {}
    elapsed = _to_number(status.get("elapsed"))
    return int(elapsed) if elapsed is not None else None


def _extra(fixture: dict[str, Any]) -> int | None:
    fixture_obj = fixture.get("fixture") if isinstance(fixture.get("fixture"), dict) else {}
    status = fixture_obj.get("status") if isinstance(fixture_obj.get("status"), dict) else {}
    extra = _to_number(status.get("extra"))
    return int(extra) if extra is not None else None


def _minute_key(elapsed: int | None, extra: int | None) -> int | None:
    if elapsed is None:
        return None
    return elapsed + max(0, extra or 0)


def _display_minute(elapsed: int | None, extra: int | None) -> str | None:
    if elapsed is None:
        return None
    if extra and extra > 0:
        return f"{elapsed}+{extra}'"
    return f"{elapsed}'"


def _team_ids(fixture: dict[str, Any]) -> tuple[int | None, int | None]:
    teams = fixture.get("teams") if isinstance(fixture.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    return home.get("id") if isinstance(home.get("id"), int) else None, away.get("id") if isinstance(away.get("id"), int) else None


def _score_state(fixture: dict[str, Any]) -> dict[str, int | None]:
    goals = fixture.get("goals") if isinstance(fixture.get("goals"), dict) else {}
    home = _to_number(goals.get("home"))
    away = _to_number(goals.get("away"))
    return {
        "home": int(home) if home is not None else None,
        "away": int(away) if away is not None else None,
    }


def _side_for_team(team_id: int | None, home_id: int | None, away_id: int | None) -> str | None:
    if team_id is None:
        return None
    if team_id == home_id:
        return "home"
    if team_id == away_id:
        return "away"
    return None


def _stats_side(entry: dict[str, Any]) -> dict[str, float]:
    values = {
        "xg": 0.0,
        "shots": 0.0,
        "shotsOnGoal": 0.0,
        "insideBoxShots": 0.0,
        "corners": 0.0,
        "possession": 0.0,
        "passes": 0.0,
        "passesAccurate": 0.0,
        "yellowCards": 0.0,
        "redCards": 0.0,
    }
    for stat in entry.get("statistics") or []:
        if not isinstance(stat, dict):
            continue
        key = STAT_KEYS.get(stat.get("type"))
        if not key:
            continue
        values[key] = _to_number(stat.get("value")) or 0.0
    return values


def _stats_state(statistics: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    home = statistics[0] if len(statistics) > 0 and isinstance(statistics[0], dict) else {}
    away = statistics[1] if len(statistics) > 1 and isinstance(statistics[1], dict) else {}
    return {"home": _stats_side(home), "away": _stats_side(away)}


def _event_id(event: dict[str, Any]) -> str:
    return str(event.get("id") or "")


def _event_counts(events: list[dict[str, Any]], home_id: int | None, away_id: int | None) -> dict[str, dict[str, float]]:
    counts = {
        "home": {"dangerEvents": 0.0},
        "away": {"dangerEvents": 0.0},
    }
    for event in events:
        side = _side_for_team(event.get("teamId") if isinstance(event.get("teamId"), int) else None, home_id, away_id)
        if side is None:
            continue
        kind = str(event.get("kind") or "").lower()
        detail = str(event.get("detail") or "").lower()
        if kind == "var" or "penalty" in detail:
            counts[side]["dangerEvents"] += 1
    return counts


def _state(
    fixture_id: int,
    fixture: dict[str, Any],
    statistics: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    now_func: Callable[[], datetime],
) -> dict[str, Any]:
    home_id, away_id = _team_ids(fixture)
    elapsed = _elapsed(fixture)
    extra = _extra(fixture)
    return {
        "fixtureId": fixture_id,
        "elapsed": elapsed,
        "extra": extra,
        "minuteKey": _minute_key(elapsed, extra),
        "displayMinute": _display_minute(elapsed, extra),
        "status": _status_short(fixture),
        "score": _score_state(fixture),
        "stats": _stats_state(statistics),
        "eventIds": [_event_id(event) for event in events if _event_id(event)],
        "eventCounts": _event_counts(events, home_id, away_id),
        "capturedAt": _now_iso(now_func),
    }


def _empty_delta(
    elapsed: int | None,
    captured_at: str,
    *,
    extra: int | None = None,
    minute_key: int | None = None,
    display_minute: str | None = None,
) -> dict[str, Any]:
    return {
        "elapsed": elapsed,
        "extra": extra,
        "minuteKey": minute_key if minute_key is not None else _minute_key(elapsed, extra),
        "displayMinute": display_minute if display_minute is not None else _display_minute(elapsed, extra),
        "capturedAt": captured_at,
        "home": {},
        "away": {},
    }


def _baseline_sample(captured_at: str) -> dict[str, Any]:
    return _empty_delta(0, captured_at)


def _diff(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    sample = _empty_delta(
        current.get("elapsed"),
        current.get("capturedAt"),
        extra=current.get("extra"),
        minute_key=current.get("minuteKey"),
        display_minute=current.get("displayMinute"),
    )
    for side in ("home", "away"):
        sample[side] = {}
        for key, value in current["stats"][side].items():
            previous_value = previous.get("stats", {}).get(side, {}).get(key, 0.0)
            raw_delta = float(value or 0.0) - float(previous_value or 0.0)
            if key == "possession":
                sample[side][key] = max(-10.0, min(10.0, raw_delta))
            else:
                sample[side][key] = min(DELTA_CAPS.get(key, float("inf")), max(0.0, raw_delta))
        for key, value in current["eventCounts"][side].items():
            previous_value = previous.get("eventCounts", {}).get(side, {}).get(key, 0.0)
            raw_delta = max(0.0, float(value or 0.0) - float(previous_value or 0.0))
            sample[side][key] = min(DELTA_CAPS.get(key, float("inf")), raw_delta)
        current_goals = current.get("score", {}).get(side)
        previous_goals = previous.get("score", {}).get(side)
        if current_goals is not None and previous_goals is not None:
            sample[side]["goals"] = min(
                DELTA_CAPS["goals"],
                max(0.0, float(current_goals) - float(previous_goals)),
            )
        else:
            sample[side]["goals"] = 0.0
        sample[side]["cards"] = sample[side].get("yellowCards", 0.0) + sample[side].get("redCards", 0.0)
    return sample


def _delta_score(delta: dict[str, float], opponent_delta: dict[str, float]) -> float:
    has_xg_signal = delta.get("xg", 0.0) > 0.0 or opponent_delta.get("xg", 0.0) > 0.0
    if has_xg_signal:
        shot_score = (
            delta.get("xg", 0.0) * 16.0
            + delta.get("shots", 0.0) * 0.8
            + delta.get("shotsOnGoal", 0.0) * 2.0
            + delta.get("insideBoxShots", 0.0) * 1.2
        )
    else:
        shot_score = (
            delta.get("shots", 0.0) * 1.2
            + delta.get("shotsOnGoal", 0.0) * 3.0
            + delta.get("insideBoxShots", 0.0) * 2.0
        )
    return (
        delta.get("goals", 0.0) * 8.0
        + shot_score
        + delta.get("corners", 0.0) * 1.0
        + delta.get("dangerEvents", 0.0) * 3.0
        + min(delta.get("passesAccurate", 0.0) * 0.02, 2.0)
        + opponent_delta.get("yellowCards", 0.0) * 0.4
        - delta.get("yellowCards", 0.0) * 0.3
    )


def _possession_bias(current: dict[str, Any] | None, side: str) -> float:
    if not isinstance(current, dict):
        return 0.0
    opponent = "away" if side == "home" else "home"
    stats = current.get("stats") if isinstance(current.get("stats"), dict) else {}
    side_possession = stats.get(side, {}).get("possession") if isinstance(stats.get(side), dict) else None
    opponent_possession = stats.get(opponent, {}).get("possession") if isinstance(stats.get(opponent), dict) else None
    if side_possession is None or opponent_possession is None:
        return 0.0
    return min(2.0, max(0.0, (float(side_possession) - float(opponent_possession)) * 0.03))


def _manpower_bias(current: dict[str, Any] | None, side: str) -> float:
    if not isinstance(current, dict):
        return 0.0
    opponent = "away" if side == "home" else "home"
    stats = current.get("stats") if isinstance(current.get("stats"), dict) else {}
    side_reds = stats.get(side, {}).get("redCards", 0.0) if isinstance(stats.get(side), dict) else 0.0
    opponent_reds = stats.get(opponent, {}).get("redCards", 0.0) if isinstance(stats.get(opponent), dict) else 0.0
    return float(opponent_reds or 0.0) * 2.5 - float(side_reds or 0.0) * 2.5


def _level(value: float, *, medium: float, high: float) -> str:
    if value < medium:
        return "low"
    if value < high:
        return "medium"
    return "high"


def _summed_recent(samples: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    result = {"home": {}, "away": {}}
    for sample in samples[-WINDOW_SAMPLES:]:
        for side in ("home", "away"):
            for key, value in (sample.get(side) or {}).items():
                result[side][key] = result[side].get(key, 0.0) + float(value or 0.0)
    return result


def _reasons(samples: list[dict[str, Any]], leading_side: str) -> list[str]:
    if leading_side not in {"home", "away"}:
        return []
    recent = _summed_recent(samples)[leading_side]
    candidates = [
        ("goals", "최근 득점"),
        ("xg", "최근 xG 상승"),
        ("shotsOnGoal", "최근 유효슈팅 증가"),
        ("shots", "최근 슈팅 증가"),
        ("insideBoxShots", "최근 박스 안 슈팅 증가"),
        ("corners", "최근 코너킥 증가"),
        ("passesAccurate", "최근 패스 성공 증가"),
    ]
    return [label for key, label in candidates if recent.get(key, 0.0) > 0][:3]


def _calculate(samples: list[dict[str, Any]], *, updated_at: str, current: dict[str, Any] | None = None) -> dict[str, Any]:
    if not samples:
        return {
            "available": True,
            "home": 50,
            "away": 50,
            "trend": "balanced",
            "intensity": "low",
            "dominance": "low",
            "tempo": "low",
            "activity": 0,
            "reasons": ["모멘텀 데이터 수집 중"],
            "history": [],
            "updatedAt": updated_at,
        }

    def weighted_raw(window_samples: list[dict[str, Any]], current: dict[str, Any] | None = None) -> tuple[float, float]:
        home_total = 0.0
        away_total = 0.0
        for index, sample in enumerate(reversed(window_samples)):
            weight = weights[index] if index < len(weights) else weights[-1]
            home_delta = sample.get("home") or {}
            away_delta = sample.get("away") or {}
            home_total += _delta_score(home_delta, away_delta) * weight
            away_total += _delta_score(away_delta, home_delta) * weight
        home_total += _manpower_bias(current, "home") + _possession_bias(current, "home")
        away_total += _manpower_bias(current, "away") + _possession_bias(current, "away")
        return home_total, away_total

    def chart_point(window_samples: list[dict[str, Any]]) -> dict[str, int]:
        home_total, away_total = weighted_raw(window_samples)
        home_base = MOMENTUM_BASE + max(0.0, home_total)
        away_base = MOMENTUM_BASE + max(0.0, away_total)
        home_pct = round(home_base / (home_base + away_base) * 100)
        away_pct = 100 - home_pct
        value = max(-100, min(100, home_pct - away_pct))
        activity = round(max(0.0, home_total) + max(0.0, away_total))
        return {
            "value": value,
            "home": home_pct,
            "away": away_pct,
            "activity": activity,
            "dominance": abs(value),
        }

    history: list[dict[str, Any]] = []
    weights = [1.0, 0.92, 0.84, 0.76, 0.68, 0.60, 0.52, 0.44, 0.36, 0.28, 0.20, 0.12]
    window = samples[-WINDOW_SAMPLES:]
    for sample_index, sample in enumerate(samples):
        rolling_window = samples[max(0, sample_index - WINDOW_SAMPLES + 1): sample_index + 1]
        point = chart_point(rolling_window)
        history.append({
            "elapsed": sample.get("elapsed"),
            "extra": sample.get("extra"),
            "minuteKey": sample.get("minuteKey"),
            "displayMinute": sample.get("displayMinute"),
            **point,
        })

    home_raw, away_raw = weighted_raw(window, current)
    home_base = MOMENTUM_BASE + max(0.0, home_raw)
    away_base = MOMENTUM_BASE + max(0.0, away_raw)
    home = round(home_base / (home_base + away_base) * 100)
    away = 100 - home
    diff = abs(home - away)
    trend = "balanced" if diff < 8 else "home" if home > away else "away"
    dominance = _level(diff, medium=8.0, high=20.0)
    activity = round(max(0.0, home_raw) + max(0.0, away_raw))
    tempo = _level(activity, medium=5.0, high=15.0)
    minute_history: dict[int, dict[str, Any]] = {}
    floating_history: list[dict[str, Any]] = []
    for point in history:
        minute_key = point.get("minuteKey")
        if isinstance(minute_key, int):
            minute_history[minute_key] = point
        else:
            floating_history.append(point)
    return {
        "available": True,
        "home": home,
        "away": away,
        "trend": trend,
        "intensity": dominance,
        "dominance": dominance,
        "tempo": tempo,
        "activity": activity,
        "reasons": _reasons(samples, trend),
        "history": [*floating_history, *[minute_history[key] for key in sorted(minute_history)]],
        "updatedAt": updated_at,
    }


class BroadcastMomentumService:
    def __init__(self, cache: Any, *, now_func: Callable[[], datetime] | None = None) -> None:
        self.cache = cache
        self.now_func = now_func or (lambda: datetime.now(timezone.utc))

    def _key(self, fixture_id: int, suffix: str) -> str:
        return f"broadcast:fixture:{fixture_id}:momentum:{suffix}"

    def _acquire_lock(self, fixture_id: int) -> bool | None:
        method = getattr(self.cache, "acquire_lock", None)
        if not callable(method):
            return None
        return bool(method(self._key(fixture_id, "lock"), MOMENTUM_LOCK_SECONDS))

    def update_and_get(
        self,
        *,
        fixture_id: int,
        fixture: dict[str, Any],
        statistics: list[dict[str, Any]],
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        now = self.now_func()
        updated_at = now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        if _status_short(fixture) not in LIVE_STATUS_CODES:
            return {
                "available": False,
                "home": 50,
                "away": 50,
                "trend": "unavailable",
                "intensity": "low",
                "dominance": "low",
                "tempo": "low",
                "activity": 0,
                "reasons": ["중계되지 않은 경기는 제공하지 않습니다"],
                "history": [],
                "updatedAt": updated_at,
            }

        current = _state(fixture_id, fixture, statistics, events, now_func=self.now_func)
        try:
            latest = _cache_get(self.cache, self._key(fixture_id, "latest"))
            if _is_fresh(latest, now=now):
                return latest

            lock_acquired = self._acquire_lock(fixture_id)
            if lock_acquired is False and isinstance(latest, dict):
                return latest
            if lock_acquired is False:
                return {
                    "available": True,
                    "home": 50,
                    "away": 50,
                    "trend": "balanced",
                    "intensity": "low",
                    "dominance": "low",
                    "tempo": "low",
                    "activity": 0,
                    "reasons": ["모멘텀 계산 대기 중"],
                    "history": [],
                    "updatedAt": updated_at,
                }

            previous = _cache_get(self.cache, self._key(fixture_id, "last"))
            samples = _cache_get(self.cache, self._key(fixture_id, "samples"))
            if not isinstance(samples, list):
                samples = []
            if isinstance(previous, dict):
                sample = _diff(current, previous)
                samples = [*samples, sample][-MAX_SAMPLES:]
            elif not samples:
                samples = [_baseline_sample(current["capturedAt"])]
            result = _calculate(samples, updated_at=current["capturedAt"], current=current)
            _cache_set(self.cache, self._key(fixture_id, "last"), current, MOMENTUM_TTL_SECONDS)
            _cache_set(self.cache, self._key(fixture_id, "samples"), samples, MOMENTUM_TTL_SECONDS)
            _cache_set(self.cache, self._key(fixture_id, "latest"), result, MOMENTUM_TTL_SECONDS)
            return result
        except Exception:
            return {
                "available": True,
                "home": 50,
                "away": 50,
                "trend": "balanced",
                "intensity": "low",
                "dominance": "low",
                "tempo": "low",
                "activity": 0,
                "reasons": ["모멘텀 계산 대기 중"],
                "history": [],
                "updatedAt": updated_at,
            }
