"""Broadcast-specific read helpers."""
from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
from threading import BoundedSemaphore
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.home import LEAGUE_SLUGS
from app.workers.daily_sync.api import ApiFootballClient, ApiFootballError
from app.models.coach import Coach, CoachTranslation
from app.models.league import League, LeagueTranslation
from app.models.player import Player, PlayerTranslation
from app.models.team import Team, TeamTranslation


def _clean_ids(values: Iterable[int] | None, *, limit: int = 500) -> list[int]:
    if not values:
        return []

    cleaned: list[int] = []
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break

    return cleaned


def _translation_row(name_ko: str | None, short_name_ko: str | None) -> dict[str, str | None]:
    return {
        "name_ko": name_ko,
        "short_name_ko": short_name_ko,
    }


def _clean_names(values: Iterable[str] | None, *, limit: int = 500) -> list[str]:
    if not values:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
        if len(cleaned) >= limit:
            break

    return cleaned


def lookup_broadcast_translations(
    session: Session,
    *,
    league_ids: Iterable[int] | None = None,
    league_names: Iterable[str] | None = None,
    team_ids: Iterable[int] | None = None,
    team_names: Iterable[str] | None = None,
    player_ids: Iterable[int] | None = None,
    player_names: Iterable[str] | None = None,
    coach_ids: Iterable[int] | None = None,
    coach_names: Iterable[str] | None = None,
) -> dict[str, dict[str, dict[str, str | None]]]:
    """Return Korean display names for API-Football external IDs."""
    payload: dict[str, dict[str, dict[str, str | None]]] = {
        "leagues": {},
        "league_names": {},
        "teams": {},
        "team_names": {},
        "players": {},
        "player_names": {},
        "coaches": {},
        "coach_names": {},
    }

    clean_league_ids = _clean_ids(league_ids)
    if clean_league_ids:
        rows = session.execute(
            select(
                League.external_id,
                LeagueTranslation.name_ko,
                LeagueTranslation.short_name_ko,
            )
            .join(LeagueTranslation, LeagueTranslation.league_id == League.id)
            .where(League.external_id.in_(clean_league_ids))
        )
        payload["leagues"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_league_names = _clean_names(league_names)
    if clean_league_names:
        rows = session.execute(
            select(
                func.lower(League.name).label("name_key"),
                LeagueTranslation.name_ko,
                LeagueTranslation.short_name_ko,
            )
            .join(LeagueTranslation, LeagueTranslation.league_id == League.id)
            .where(func.lower(League.name).in_(clean_league_names))
        )
        payload["league_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_team_ids = _clean_ids(team_ids)
    if clean_team_ids:
        rows = session.execute(
            select(
                Team.external_id,
                TeamTranslation.name_ko,
                TeamTranslation.short_name_ko,
            )
            .join(TeamTranslation, TeamTranslation.team_id == Team.id)
            .where(Team.external_id.in_(clean_team_ids))
        )
        payload["teams"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_team_names = _clean_names(team_names)
    if clean_team_names:
        rows = session.execute(
            select(
                func.lower(Team.name).label("name_key"),
                TeamTranslation.name_ko,
                TeamTranslation.short_name_ko,
            )
            .join(TeamTranslation, TeamTranslation.team_id == Team.id)
            .where(func.lower(Team.name).in_(clean_team_names))
        )
        payload["team_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_player_ids = _clean_ids(player_ids)
    if clean_player_ids:
        rows = session.execute(
            select(
                Player.external_id,
                PlayerTranslation.name_ko,
                PlayerTranslation.short_name_ko,
            )
            .join(PlayerTranslation, PlayerTranslation.player_id == Player.id)
            .where(Player.external_id.in_(clean_player_ids))
        )
        payload["players"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_player_names = _clean_names(player_names)
    if clean_player_names:
        rows = session.execute(
            select(
                func.lower(Player.name).label("name_key"),
                PlayerTranslation.name_ko,
                PlayerTranslation.short_name_ko,
            )
            .join(PlayerTranslation, PlayerTranslation.player_id == Player.id)
            .where(func.lower(Player.name).in_(clean_player_names))
        )
        payload["player_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_coach_ids = _clean_ids(coach_ids)
    if clean_coach_ids:
        rows = session.execute(
            select(
                Coach.external_id,
                CoachTranslation.name_ko,
                CoachTranslation.short_name_ko,
            )
            .join(CoachTranslation, CoachTranslation.coach_id == Coach.id)
            .where(Coach.external_id.in_(clean_coach_ids))
        )
        payload["coaches"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
            if row.external_id is not None
        }

    clean_coach_names = _clean_names(coach_names)
    if clean_coach_names:
        rows = session.execute(
            select(
                func.lower(Coach.name).label("name_key"),
                CoachTranslation.name_ko,
                CoachTranslation.short_name_ko,
            )
            .join(CoachTranslation, CoachTranslation.coach_id == Coach.id)
            .where(func.lower(Coach.name).in_(clean_coach_names))
        )
        payload["coach_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    return payload


ALLOWED_BROADCAST_LEAGUE_SLUGS = set(LEAGUE_SLUGS.values())
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
FINISHED_STATUSES = {"FT", "AET", "PEN"}
BROADCAST_OVERLAY_TTL_SECONDS = 10
BROADCAST_FINISHED_POLL_SECONDS = 60
_API_FOOTBALL_SEMAPHORE = BoundedSemaphore(6)


class BroadcastOverlayError(RuntimeError):
    """Raised when a live overlay has no usable upstream or DB fallback."""


class BroadcastApiFootballUnavailable(BroadcastOverlayError):
    """Raised when API-Football is required but not configured."""


class BroadcastApiFootballLiveClient:
    """API-Football client wrapper exposing the methods used by the overlay service."""

    def __init__(self, client: ApiFootballClient) -> None:
        self._client = client

    def _response(self, path: str, **params: Any) -> list[dict[str, Any]]:
        with _API_FOOTBALL_SEMAPHORE:
            return self._client.response(path, **params)

    def get_fixture(self, external_id: int) -> dict[str, Any] | None:
        rows = self._response("/fixtures", id=external_id)
        return rows[0] if rows else None

    def get_live_fixtures(self) -> list[dict[str, Any]]:
        return self._response("/fixtures", live="all")

    def get_events(self, external_id: int) -> list[dict[str, Any]]:
        return self._response("/fixtures/events", fixture=external_id)

    def get_lineups(self, external_id: int) -> list[dict[str, Any]]:
        return self._response("/fixtures/lineups", fixture=external_id)

    def get_statistics(self, external_id: int) -> list[dict[str, Any]]:
        return self._response("/fixtures/statistics", fixture=external_id)

    def get_players(self, external_id: int) -> list[dict[str, Any]]:
        return self._response("/fixtures/players", fixture=external_id)


class UnavailableBroadcastApiFootballClient:
    def _raise(self, *_args: Any, **_kwargs: Any) -> None:
        raise BroadcastApiFootballUnavailable("api_football_not_configured")

    get_fixture = _raise
    get_live_fixtures = _raise
    get_events = _raise
    get_lineups = _raise
    get_statistics = _raise
    get_players = _raise


class NoopBroadcastCache:
    def get_json(self, _key: str) -> Any:
        return None

    def set_json(self, _key: str, _value: Any, ttl_seconds: int | None = None) -> None:
        return None

    def acquire_lock(self, _key: str, ttl_seconds: int) -> bool:
        return False


class UpstashRestBroadcastCache:
    """Small Upstash REST cache adapter with the fake-cache test interface."""

    def __init__(self, rest_url: str, token: str, timeout: float = 3.0, key_prefix: str = "") -> None:
        self._url = rest_url.rstrip("/")
        self._key_prefix = key_prefix
        self._client = httpx.Client(
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )

    def _key(self, key: str) -> str:
        if not self._key_prefix:
            return key
        if self._key_prefix.endswith(":"):
            return f"{self._key_prefix}{key}"
        return f"{self._key_prefix}:{key}"

    def get_json(self, key: str) -> Any:
        response = self._client.get(f"{self._url}/get/{quote(self._key(key), safe='')}")
        response.raise_for_status()
        value = response.json().get("result")
        return _decode_cache_value(value)

    def set_json(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        command: list[Any] = ["SET", self._key(key), json.dumps(value, separators=(",", ":"))]
        if ttl_seconds is not None:
            command.extend(["EX", ttl_seconds])
        response = self._client.post(self._url, json=command)
        response.raise_for_status()

    def acquire_lock(self, key: str, ttl_seconds: int) -> bool:
        command: list[Any] = ["SET", self._key(key), "1", "NX", "EX", ttl_seconds]
        response = self._client.post(self._url, json=command)
        response.raise_for_status()
        return response.json().get("result") == "OK"


@lru_cache(maxsize=1)
def make_broadcast_api_football_client() -> Any:
    settings = get_settings()
    if not settings.api_football_key:
        return UnavailableBroadcastApiFootballClient()
    return BroadcastApiFootballLiveClient(
        ApiFootballClient(
            api_key=settings.api_football_key,
            host=settings.api_football_host,
            requests_per_minute=settings.api_football_requests_per_minute,
        )
    )


@lru_cache(maxsize=1)
def make_broadcast_cache() -> Any:
    settings = get_settings()
    if settings.upstash_redis_rest_url and settings.upstash_redis_rest_token:
        return UpstashRestBroadcastCache(
            settings.upstash_redis_rest_url,
            settings.upstash_redis_rest_token,
            key_prefix=settings.upstash_redis_key_prefix,
        )
    return NoopBroadcastCache()


def _decode_cache_value(value: Any) -> Any:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _cache_get(cache: Any, key: str) -> Any:
    for method_name in ("get_json", "get"):
        method = getattr(cache, method_name, None)
        if callable(method):
            value = method(key)
            if value is not None:
                return _decode_cache_value(value)
    return None


def _cache_set(cache: Any, key: str, value: Any, ttl_seconds: int) -> None:
    for method_name, ttl_name in (("set_json", "ttl_seconds"), ("set", "ex")):
        method = getattr(cache, method_name, None)
        if callable(method):
            method(key, value, **{ttl_name: ttl_seconds})
            return
    method = getattr(cache, "setex", None)
    if callable(method):
        method(key, ttl_seconds, value)


_OVERLAY_FIXTURE_SQL = text(
    """
    SELECT f.id AS fixture_id, f.external_id, f.season_year, f.status_short,
           f.status_long, f.status_elapsed, f.goals_home, f.goals_away,
           l.external_id AS league_external_id, l.slug AS league_slug,
           l.name AS league_name, l.logo_url AS league_logo_url,
           lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
           ht.external_id AS home_external_id, ht.slug AS home_slug,
           ht.name AS home_name, ht.code AS home_code, ht.logo_url AS home_logo_url,
           htt.name_ko AS home_name_ko, htt.short_name_ko AS home_short_name_ko,
           at.external_id AS away_external_id, at.slug AS away_slug,
           at.name AS away_name, at.code AS away_code, at.logo_url AS away_logo_url,
           att.name_ko AS away_name_ko, att.short_name_ko AS away_short_name_ko,
           fd.events, fd.statistics, fd.lineups, fd.players
    FROM fixture f
    JOIN league l ON l.id = f.league_id
    LEFT JOIN league_translation lt ON lt.league_id = l.id
    LEFT JOIN team ht ON ht.id = f.home_team_id
    LEFT JOIN team at ON at.id = f.away_team_id
    LEFT JOIN team_translation htt ON htt.team_id = ht.id
    LEFT JOIN team_translation att ON att.team_id = at.id
    LEFT JOIN fixture_detail fd ON fd.fixture_id = f.id
    WHERE f.external_id = :external_id
    """
)

_OVERLAY_GROUP_STANDINGS_SQL = text(
    """
    SELECT s.rank, s.played, s.win, s.draw, s.loss, s.goals_for,
           s.goals_against, COALESCE(s.goals_diff, s.goals_for - s.goals_against) AS goal_diff,
           s.points, s.group_name,
           t.id AS team_id,
           t.external_id AS team_external_id,
           t.name AS team_name,
           t.code AS team_code,
           tt.name_ko AS team_name_ko,
           tt.short_name_ko AS team_short_name_ko
    FROM standings s
    JOIN team t ON t.id = s.team_id
    LEFT JOIN team_translation tt ON tt.team_id = t.id
    WHERE s.league_id = (SELECT league_id FROM fixture WHERE external_id = :external_id)
      AND s.season_year = (SELECT season_year FROM fixture WHERE external_id = :external_id)
    ORDER BY s.group_name NULLS FIRST, s.rank ASC, s.id ASC
    """
)


def _fixture_row(session: Session, external_id: int) -> dict[str, Any] | None:
    row = session.execute(_OVERLAY_FIXTURE_SQL, {"external_id": external_id}).mappings().first()
    return dict(row) if row is not None else None


def _team_display_code(
    row: dict[str, Any],
    *,
    fallback: str | None = None,
) -> str:
    short_name = row.get("short_name_ko") or row.get("short_name")
    code = row.get("code") or row.get("team_code") or short_name
    if isinstance(code, str):
        trimmed = code.strip()
        if trimmed:
            return trimmed[:4].upper()

    name = row.get("name")
    if isinstance(name, str) and name.strip():
        letters = "".join(ch for ch in name.upper() if ch.isalnum())
        compact = letters[:3]
        if compact:
            return compact

    if isinstance(fallback, str) and fallback.strip():
        letters = "".join(ch for ch in fallback.upper() if ch.isalnum())
        return (letters[:3] or "TBD")
    return "TBD"


def _group_standings_block(
    session: Session,
    row: dict[str, Any],
    external_id: int,
) -> dict[str, Any] | None:
    if row.get("season_year") is None:
        return None

    rows = list(
        session.execute(
            _OVERLAY_GROUP_STANDINGS_SQL,
            {"external_id": external_id},
        ).mappings()
    )
    if not rows:
        return None

    home_id = row.get("home_external_id")
    away_id = row.get("away_external_id")
    home_groups = {
        mapping["group_name"] for mapping in rows if mapping.get("team_external_id") == home_id and mapping.get("group_name") is not None
    }
    away_groups = {
        mapping["group_name"] for mapping in rows if mapping.get("team_external_id") == away_id and mapping.get("group_name") is not None
    }
    shared = [group for group in home_groups.intersection(away_groups) if group is not None]
    group_name = shared[0] if shared else None
    if group_name is None:
        return {
            "group_name": None,
            "rows": [],
        }

    target_rows = [mapping for mapping in rows if mapping.get("group_name") == group_name]
    return {
        "group_name": group_name,
        "rows": [
            {
                "rank": int(mapping.get("rank") or 0),
                "team_id": mapping.get("team_external_id"),
                "team_name": mapping.get("team_name_ko") or mapping.get("team_name") or "Unknown",
                "team_code": _team_display_code(
                    {
                        "code": mapping.get("team_code"),
                        "short_name": mapping.get("team_short_name_ko"),
                        "name": mapping.get("team_name"),
                    },
                    fallback=str(mapping.get("team_name") or "TEAM"),
                ),
                "played": int(mapping.get("played") or 0),
                "win": int(mapping.get("win") or 0),
                "draw": int(mapping.get("draw") or 0),
                "loss": int(mapping.get("loss") or 0),
                "goals_for": int(mapping.get("goals_for") or 0),
                "goals_against": int(mapping.get("goals_against") or 0),
                "goal_diff": int(mapping.get("goal_diff") or 0),
                "points": int(mapping.get("points") or 0),
            }
            for mapping in target_rows
        ],
    }


def _theme_slug(league_external_id: int | None, fallback_slug: str | None) -> str:
    if league_external_id in LEAGUE_SLUGS:
        return LEAGUE_SLUGS[int(league_external_id)]
    if fallback_slug in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        return str(fallback_slug)
    return "premier-league"


def _team_code(row: dict[str, Any], side: str) -> str:
    code = row.get(f"{side}_short_name_ko") or row.get(f"{side}_code")
    if isinstance(code, str) and code.strip():
        return code.strip()[:4].upper()
    name = str(row.get(f"{side}_name") or side)
    letters = "".join(ch for ch in name.upper() if ch.isalnum())
    return (letters[:3] or side[:3].upper())


def _team_ref(row: dict[str, Any], side: str) -> dict[str, Any]:
    logo_url = row.get(f"{side}_logo_url")
    return {
        "external_id": row.get(f"{side}_external_id"),
        "slug": row.get(f"{side}_slug"),
        "name": row.get(f"{side}_name"),
        "name_ko": row.get(f"{side}_name_ko"),
        "short_name_ko": row.get(f"{side}_short_name_ko"),
        "logo_url": logo_url,
        "badge_url": logo_url,
        "code": _team_code(row, side),
    }


def _api_status(core: dict[str, Any] | None) -> dict[str, Any]:
    fixture = core.get("fixture") if isinstance(core, dict) else {}
    status = fixture.get("status") if isinstance(fixture, dict) else {}
    return status if isinstance(status, dict) else {}


def _api_goals(core: dict[str, Any] | None) -> dict[str, Any]:
    goals = core.get("goals") if isinstance(core, dict) else {}
    return goals if isinstance(goals, dict) else {}


def _clock_label(status_short: str | None, elapsed: int | None, extra: int | None) -> str:
    if status_short in {"FT", "AET", "PEN", "HT", "NS", "PST", "CANC", "SUSP"}:
        return status_short or "NS"
    if elapsed is None:
        return status_short or "LIVE"
    return f"{elapsed}+{extra}:00" if extra else f"{elapsed}:00"


def _fixture_block(
    row: dict[str, Any],
    *,
    core: dict[str, Any] | None,
    league_slug: str | None,
) -> dict[str, Any]:
    status = _api_status(core)
    goals = _api_goals(core)
    status_short = status.get("short") or row.get("status_short")
    elapsed = status.get("elapsed")
    if elapsed is None:
        elapsed = row.get("status_elapsed")
    extra = status.get("extra")
    league_external_id = row.get("league_external_id")
    theme_slug = _theme_slug(league_external_id, row.get("league_slug") or league_slug)
    return {
        "external_id": row["external_id"],
        "league": {
            "external_id": league_external_id,
            "slug": row.get("league_slug") or theme_slug,
            "name": row.get("league_name"),
            "name_ko": row.get("league_name_ko"),
            "short_name_ko": row.get("league_short_name_ko"),
            "logo_url": row.get("league_logo_url"),
            "theme_slug": theme_slug,
        },
        "status_short": status_short,
        "status_long": status.get("long") or row.get("status_long") or status_short,
        "elapsed": elapsed,
        "extra": extra,
        "clock_label": _clock_label(status_short, elapsed, extra),
        "added_time_label": f"+{extra}" if extra is not None else None,
        "home": _team_ref(row, "home"),
        "away": _team_ref(row, "away"),
        "goals_home": goals.get("home", row.get("goals_home")),
        "goals_away": goals.get("away", row.get("goals_away")),
    }


def _first_stat(entry: dict[str, Any]) -> dict[str, Any]:
    stats = entry.get("statistics")
    if isinstance(stats, list) and stats and isinstance(stats[0], dict):
        return stats[0]
    return {}


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("%", "").strip()
        if not value:
            return None
    try:
        return int(Decimal(str(value)))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_external_team_id(value: Any) -> int | str | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else str(int(value))
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return value
    return None


def _player_stats_map(players_payload: Any) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(players_payload, list):
        return result
    for team_entry in players_payload:
        if not isinstance(team_entry, dict):
            continue
        for entry in team_entry.get("players") or []:
            if not isinstance(entry, dict):
                continue
            player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
            player_id = player.get("id")
            if player_id is None:
                continue
            stat = _first_stat(entry)
            games = stat.get("games") if isinstance(stat.get("games"), dict) else {}
            goals = stat.get("goals") if isinstance(stat.get("goals"), dict) else {}
            cards = stat.get("cards") if isinstance(stat.get("cards"), dict) else {}
            substitutes = (
                stat.get("substitutes") if isinstance(stat.get("substitutes"), dict) else {}
            )
            result[int(player_id)] = {
                "name": player.get("name"),
                "number": games.get("number"),
                "position": games.get("position"),
                "rating": _to_float(games.get("rating")),
                "goals": _to_int(goals.get("total")) or 0,
                "yellow_cards": _to_int(cards.get("yellow")) or 0,
                "red_cards": _to_int(cards.get("red")) or 0,
                "sub_in": _to_int(substitutes.get("in")) or 0,
                "sub_out": _to_int(substitutes.get("out")) or 0,
            }
    return result


def _event_player_ids(events_payload: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(events_payload, list):
        return ids
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        for key in ("player", "assist"):
            value = event.get(key)
            if isinstance(value, dict) and value.get("id") is not None:
                ids.add(int(value["id"]))
    return ids


def _lineup_player_ids(lineups_payload: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(lineups_payload, list):
        return ids
    for lineup in lineups_payload:
        if not isinstance(lineup, dict):
            continue
        for group in ("startXI", "substitutes"):
            for item in lineup.get(group) or []:
                player = item.get("player") if isinstance(item, dict) else None
                if isinstance(player, dict) and player.get("id") is not None:
                    ids.add(int(player["id"]))
    return ids


def _lineup_coach_ids(lineups_payload: Any) -> set[int]:
    ids: set[int] = set()
    if not isinstance(lineups_payload, list):
        return ids
    for lineup in lineups_payload:
        if not isinstance(lineup, dict):
            continue
        coach = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else None
        if isinstance(coach, dict):
            coach_id = coach.get("id")
            if coach_id is not None:
                try:
                    ids.add(int(coach_id))
                except (TypeError, ValueError):
                    pass
    return ids


def _player_translation_map(
    session: Session,
    player_ids: Iterable[int],
) -> dict[int, dict[str, str | None]]:
    ids = sorted({int(player_id) for player_id in player_ids if player_id is not None})
    if not ids:
        return {}
    rows = session.execute(
        select(
            Player.external_id,
            Player.name,
            PlayerTranslation.name_ko,
            PlayerTranslation.short_name_ko,
        )
        .outerjoin(PlayerTranslation, PlayerTranslation.player_id == Player.id)
        .where(Player.external_id.in_(ids))
    )
    return {
        int(row.external_id): {
            "name": row.name,
            "name_ko": row.name_ko,
            "short_name_ko": row.short_name_ko,
        }
        for row in rows
    }


def _coach_translation_map(
    session: Session,
    coach_ids: Iterable[int],
) -> dict[int, dict[str, str | None]]:
    ids = sorted({int(coach_id) for coach_id in coach_ids if coach_id is not None})
    if not ids:
        return {}
    rows = session.execute(
        select(
            Coach.external_id,
            Coach.name,
            CoachTranslation.name_ko,
            CoachTranslation.short_name_ko,
        )
        .outerjoin(CoachTranslation, CoachTranslation.coach_id == Coach.id)
        .where(Coach.external_id.in_(ids))
    )
    return {
        int(row.external_id): {
            "name": row.name,
            "name_ko": row.name_ko,
            "short_name_ko": row.short_name_ko,
        }
        for row in rows
        if row.external_id is not None
    }


def _player_ref(
    external_id: int | None,
    name: str | None,
    translations: dict[int, dict[str, str | None]],
) -> dict[str, Any] | None:
    if external_id is None and name is None:
        return None
    item = translations.get(int(external_id)) if external_id is not None else None
    source_name = (item or {}).get("name") or name
    name_ko = (item or {}).get("name_ko")
    short_name_ko = (item or {}).get("short_name_ko") or name_ko or source_name
    return {
        "external_id": external_id,
        "name": source_name,
        "name_ko": name_ko or source_name,
        "short_name_ko": short_name_ko,
    }


def _coach_ref(
    external_id: int | None,
    name: str | None,
    translations: dict[int, dict[str, str | None]],
) -> dict[str, Any] | None:
    if external_id is None and name is None:
        return None
    item = translations.get(int(external_id)) if external_id is not None else None
    source_name = (item or {}).get("name") or name
    name_ko = (item or {}).get("name_ko")
    short_name_ko = (item or {}).get("short_name_ko") or name_ko or source_name
    return {
        "external_id": external_id,
        "name": name_ko or source_name,
        "name_ko": name_ko or source_name,
        "short_name_ko": short_name_ko,
    }


def _event_stat_counts(events_payload: Any) -> dict[int, dict[str, int | str]]:
    counts: dict[int, dict[str, int | str]] = {}
    if not isinstance(events_payload, list):
        return counts
    for event in events_payload:
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "").lower()
        detail = str(event.get("detail") or "").lower()
        player = event.get("player") if isinstance(event.get("player"), dict) else {}
        assist = event.get("assist") if isinstance(event.get("assist"), dict) else {}
        player_id = player.get("id")
        if player_id is not None:
            current = counts.setdefault(
                int(player_id),
                {"goals": 0, "yellow_cards": 0, "red_cards": 0, "substitution": "none"},
            )
            if event_type == "goal":
                current["goals"] = int(current["goals"]) + 1
            if event_type == "card" and "yellow" in detail:
                current["yellow_cards"] = int(current["yellow_cards"]) + 1
            if event_type == "card" and "red" in detail:
                current["red_cards"] = int(current["red_cards"]) + 1
            if event_type in {"subst", "substitution"}:
                current["substitution"] = "in"
        assist_id = assist.get("id")
        if event_type in {"subst", "substitution"} and assist_id is not None:
            current = counts.setdefault(
                int(assist_id),
                {"goals": 0, "yellow_cards": 0, "red_cards": 0, "substitution": "none"},
            )
            current["substitution"] = "out"
    return counts


def _lineup_player(
    item: dict[str, Any],
    *,
    player_stats: dict[int, dict[str, Any]],
    event_counts: dict[int, dict[str, int | str]],
    translations: dict[int, dict[str, str | None]],
) -> dict[str, Any]:
    player = item.get("player") if isinstance(item.get("player"), dict) else {}
    player_id = player.get("id")
    stats = player_stats.get(int(player_id), {}) if player_id is not None else {}
    event_stats = event_counts.get(int(player_id), {}) if player_id is not None else {}
    substitution = "none"
    if stats.get("sub_in"):
        substitution = "in"
    elif stats.get("sub_out"):
        substitution = "out"
    elif event_stats.get("substitution"):
        substitution = str(event_stats["substitution"])
    player_ref = _player_ref(player_id, player.get("name"), translations) or {}
    return {
        "player_external_id": player_id,
        "number": player.get("number") or stats.get("number"),
        "name": player_ref.get("name") or player.get("name"),
        "name_ko": player_ref.get("name_ko"),
        "short_name_ko": player_ref.get("short_name_ko") or player.get("name"),
        "position": player.get("pos") or stats.get("position"),
        "grid": player.get("grid"),
        "rating": stats.get("rating"),
        "goals": stats.get("goals", event_stats.get("goals", 0)),
        "yellow_cards": stats.get("yellow_cards", event_stats.get("yellow_cards", 0)),
        "red_cards": stats.get("red_cards", event_stats.get("red_cards", 0)),
        "substitution": substitution,
    }


def _empty_lineup(row: dict[str, Any], side: str) -> dict[str, Any]:
    team = _team_ref(row, side)
    return {
        "team_external_id": team["external_id"],
        "team_side": side,
        "team_name": team["name"],
        "team_name_ko": team["name_ko"],
        "team_code": team["code"],
        "team_logo_url": team["logo_url"],
        "formation": None,
        "coach": None,
        "substitute_numbers": {},
        "players": [],
    }


def _lineups_block(
    row: dict[str, Any],
    lineups_payload: Any,
    *,
    players_payload: Any,
    events_payload: Any,
    translations: dict[int, dict[str, str | None]],
    coach_translations: dict[int, dict[str, str | None]],
) -> list[dict[str, Any]]:
    home_external_id = _coerce_external_team_id(row.get("home_external_id"))
    away_external_id = _coerce_external_team_id(row.get("away_external_id"))
    by_team = {
        home_external_id: _empty_lineup(row, "home"),
        away_external_id: _empty_lineup(row, "away"),
    }
    if not isinstance(lineups_payload, list):
        return [
            by_team[home_external_id],
            by_team[away_external_id],
        ]
    player_stats = _player_stats_map(players_payload)
    event_counts = _event_stat_counts(events_payload)
    for lineup in lineups_payload:
        if not isinstance(lineup, dict):
            continue
        team = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
        team_id = _coerce_external_team_id(team.get("id"))
        target = by_team.get(team_id)
        if target is None:
            continue
        target["formation"] = lineup.get("formation")
        coach = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else None
        if coach:
            coach_ref = _coach_ref(coach.get("id"), coach.get("name"), coach_translations)
            target["coach"] = {
                "id": coach.get("id"),
                "name": (coach_ref or {}).get("name_ko") or coach.get("name"),
                "photo_url": coach.get("photo"),
            }
        substitute_numbers: dict[str, int] = {}
        for item in lineup.get("substitutes") or []:
            if not isinstance(item, dict):
                continue
            player_id = item.get("player")["id"] if isinstance(item.get("player"), dict) else None
            player_number = item.get("player", {}).get("number") if isinstance(item.get("player"), dict) else None
            if isinstance(player_id, int | str) and player_id is not None:
                if isinstance(player_number, int | str):
                    try:
                        substitute_numbers[str(int(player_id))] = int(player_number)
                    except (TypeError, ValueError):
                        pass
        target["substitute_numbers"] = substitute_numbers
        players = [
            _lineup_player(
                item,
                player_stats=player_stats,
                event_counts=event_counts,
                translations=translations,
            )
            for item in lineup.get("startXI") or []
            if isinstance(item, dict)
        ]
        if players:
            target["players"] = players
    return [
        by_team.get(home_external_id, _empty_lineup(row, "home")),
        by_team.get(away_external_id, _empty_lineup(row, "away")),
    ]


STAT_TYPE_MAP = {
    "ball possession": "possession",
    "total shots": "shots_total",
    "shots on goal": "shots_on_goal",
    "shots on target": "shots_on_goal",
    "shots total": "shots_total",
    "fouls": "fouls",
    "foul": "fouls",
    "fouls committed": "fouls",
    "fouls won": "fouls",
    "corner kicks": "corner_kicks",
    "passes %": "passes_pct",
    "passes_accuracy": "passes_pct",
    "passes accurate %": "passes_pct",
    "passes accurate": "passes_pct",
    "offsides": "offsides",
    "yellow cards": "yellow_cards",
    "yellow card": "yellow_cards",
    "red cards": "red_cards",
    "red card": "red_cards",
}
STAT_LABELS_KO = {
    "possession": "점유율",
    "shots_total": "전체슈팅",
    "shots_on_goal": "유효슈팅",
    "corner_kicks": "코너킥",
    "passes_pct": "패스성공률",
    "fouls": "파울",
    "offsides": "오프사이드",
    "yellow_cards": "옐로카드",
    "red_cards": "레드카드",
}
STAT_ORDER = [
    "possession",
    "shots_total",
    "shots_on_goal",
    "corner_kicks",
    "passes_pct",
    "fouls",
    "offsides",
    "yellow_cards",
    "red_cards",
]


def _display_stat(value: Any, stat_type: str) -> str:
    parsed = _to_int(value)
    if parsed is None:
        return "-"
    return f"{parsed}%" if stat_type in {"possession", "passes_pct"} else str(parsed)


def _stat_pct(home: int | None, away: int | None, stat_type: str) -> tuple[int, int]:
    if stat_type in {"possession", "passes_pct"}:
        if home is not None and away is not None:
            return home, away
        if home is not None:
            return home, max(0, 100 - home)
        if away is not None:
            return max(0, 100 - away), away
    if home is None and away is None:
        return 50, 50
    home_value = home or 0
    away_value = away or 0
    total = home_value + away_value
    if total <= 0:
        return 50, 50
    home_pct = round(home_value / total * 100)
    return home_pct, 100 - home_pct


def _statistics_block(row: dict[str, Any], statistics_payload: Any) -> list[dict[str, Any]]:
    values: dict[str, dict[str, Any]] = {key: {"home": None, "away": None} for key in STAT_ORDER}
    side_by_team = {
        _coerce_external_team_id(row.get("home_external_id")): "home",
        _coerce_external_team_id(row.get("away_external_id")): "away",
    }
    if isinstance(statistics_payload, list):
        for team_entry in statistics_payload:
            if not isinstance(team_entry, dict):
                continue
            team = team_entry.get("team") if isinstance(team_entry.get("team"), dict) else {}
            team_id = _coerce_external_team_id(team.get("id"))
            side = side_by_team.get(team_id)
            if side is None:
                continue
            for stat in team_entry.get("statistics") or []:
                if not isinstance(stat, dict):
                    continue
                stat_type = STAT_TYPE_MAP.get(str(stat.get("type") or "").lower())
                if stat_type:
                    values[stat_type][side] = stat.get("value")
    api_type_labels = {
        "possession": "Ball Possession",
        "shots_total": "Total Shots",
        "shots_on_goal": "Shots on Goal",
        "corner_kicks": "Corner Kicks",
        "passes_pct": "Passes %",
        "fouls": "Fouls",
        "offsides": "Offsides",
        "yellow_cards": "Yellow Cards",
        "red_cards": "Red Cards",
    }

    rows: list[dict[str, Any]] = []
    for stat_type in STAT_ORDER:
        raw_home = values[stat_type]["home"]
        raw_away = values[stat_type]["away"]
        if raw_home is None and raw_away is None:
            continue
        home = _to_int(raw_home)
        away = _to_int(raw_away)
        home_pct, away_pct = _stat_pct(home, away, stat_type)
        rows.append(
            {
                "type": api_type_labels.get(stat_type, stat_type),
                "type_key": stat_type,
                "label_ko": STAT_LABELS_KO[stat_type],
                "home": home,
                "away": away,
                "home_display": _display_stat(raw_home, stat_type),
                "away_display": _display_stat(raw_away, stat_type),
                "home_pct": home_pct,
                "away_pct": away_pct,
            }
        )
    return rows


def _event_kind(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "").lower()
    detail = str(event.get("detail") or "").lower()
    if event_type == "goal":
        return "goal"
    if event_type == "card":
        return "red-card" if "red" in detail else "yellow-card"
    if event_type in {"subst", "substitution"}:
        return "substitution"
    if event_type == "var":
        return "var"
    return None


def _event_title(kind: str) -> str:
    return {
        "goal": "득점",
        "yellow-card": "경고",
        "red-card": "퇴장",
        "substitution": "선수 교체",
        "var": "VAR",
    }.get(kind, "경기 이벤트")


def _event_time(event: dict[str, Any]) -> tuple[int | None, int | None]:
    time_obj = event.get("time") if isinstance(event.get("time"), dict) else {}
    return time_obj.get("elapsed"), time_obj.get("extra")


def _event_clock_label(minute: int | None, extra: int | None) -> str | None:
    if minute is None:
        return None
    return f"{minute}+{extra}:00" if extra else f"{minute}:00"


def _events_block(
    row: dict[str, Any],
    events_payload: Any,
    *,
    translations: dict[int, dict[str, str | None]],
) -> list[dict[str, Any]]:
    if not isinstance(events_payload, list):
        return []
    side_by_team = {
        _coerce_external_team_id(row.get("home_external_id")): "home",
        _coerce_external_team_id(row.get("away_external_id")): "away",
    }
    code_by_side = {"home": _team_code(row, "home"), "away": _team_code(row, "away")}
    logo_by_side = {
        "home": row.get("home_logo_url"),
        "away": row.get("away_logo_url"),
    }
    score_label = f"{row.get('goals_home') or 0} : {row.get('goals_away') or 0}"
    result: list[dict[str, Any]] = []
    for index, event in enumerate(events_payload):
        if not isinstance(event, dict):
            continue
        kind = _event_kind(event)
        if kind is None:
            continue
        team = event.get("team") if isinstance(event.get("team"), dict) else {}
        player = event.get("player") if isinstance(event.get("player"), dict) else {}
        assist = event.get("assist") if isinstance(event.get("assist"), dict) else {}
        minute, extra = _event_time(event)
        team_id = _coerce_external_team_id(team.get("id"))
        team_side = side_by_team.get(team_id)
        event_player = _player_ref(player.get("id"), player.get("name"), translations)
        event_assist = _player_ref(assist.get("id"), assist.get("name"), translations)
        in_player = event_assist if kind == "substitution" else None
        out_player = event_player if kind == "substitution" else None
        result.append(
            {
                "event_id": f"{row['external_id']}:{index}",
                "kind": kind,
                "team_external_id": team_id,
                "team_side": team_side,
                "team_code": code_by_side.get(team_side),
                "team_logo_url": logo_by_side.get(team_side),
                "minute": minute,
                "extra": extra,
                "clock_label": _event_clock_label(minute, extra),
                "title_ko": _event_title(kind),
                "detail_ko": event.get("detail") or (event_player or {}).get("short_name_ko"),
                "score_label": score_label,
                "player": event_player,
                "assist": event_assist if kind in {"goal", "substitution"} else None,
                "in_player": in_player,
                "out_player": out_player,
                "stat": None,
            }
        )
    result.sort(key=lambda item: (item["minute"] or 0, item["extra"] or 0))
    return result[-8:]


def _generated_at(now_func: Callable[[], datetime]) -> str:
    return now_func().astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _assemble_overlay(
    session: Session,
    row: dict[str, Any],
    *,
    core: dict[str, Any] | None,
    events: Any,
    lineups: Any,
    statistics: Any,
    players: Any,
    standings: dict[str, Any] | None,
    league_slug: str | None,
    cache_hit: bool,
    interval_seconds: int,
    now_func: Callable[[], datetime],
) -> dict[str, Any]:
    player_ids = _lineup_player_ids(lineups) | _event_player_ids(events) | set(_player_stats_map(players))
    coach_ids = _lineup_coach_ids(lineups)
    player_translations = _player_translation_map(session, player_ids)
    coach_translations = _coach_translation_map(session, coach_ids)
    return {
        "fixture": _fixture_block(row, core=core, league_slug=league_slug),
        "lineups": _lineups_block(
            row,
            lineups,
            players_payload=players,
            events_payload=events,
            translations=player_translations,
            coach_translations=coach_translations,
        ),
        "statistics": _statistics_block(row, statistics),
        "events": _events_block(row, events, translations=player_translations),
        "standings": standings,
        "polling": {
            "interval_seconds": interval_seconds,
            "cache_hit": cache_hit,
            "cache_ttl_seconds": 0,
            "generated_at": _generated_at(now_func),
        },
    }


def _fallback_row_from_api(external_id: int, core: dict[str, Any]) -> dict[str, Any]:
    league = core.get("league") if isinstance(core.get("league"), dict) else {}
    teams = core.get("teams") if isinstance(core.get("teams"), dict) else {}
    home = teams.get("home") if isinstance(teams.get("home"), dict) else {}
    away = teams.get("away") if isinstance(teams.get("away"), dict) else {}
    status = _api_status(core)
    goals = _api_goals(core)
    league_external_id = league.get("id")
    league_slug = _theme_slug(league_external_id, None)
    return {
        "external_id": external_id,
        "league_external_id": league_external_id,
        "league_slug": league_slug,
        "league_name": league.get("name"),
        "league_logo_url": league.get("logo"),
        "league_name_ko": None,
        "league_short_name_ko": None,
        "status_short": status.get("short"),
        "status_long": status.get("long"),
        "status_elapsed": status.get("elapsed"),
        "goals_home": goals.get("home"),
        "goals_away": goals.get("away"),
        "home_external_id": home.get("id"),
        "home_slug": None,
        "home_name": home.get("name"),
        "home_code": None,
        "home_logo_url": home.get("logo"),
        "home_name_ko": None,
        "home_short_name_ko": None,
        "away_external_id": away.get("id"),
        "away_slug": None,
        "away_name": away.get("name"),
        "away_code": None,
        "away_logo_url": away.get("logo"),
        "away_name_ko": None,
        "away_short_name_ko": None,
        "events": [],
        "statistics": [],
        "lineups": [],
        "players": [],
    }


def _has_overlay_detail_fallback(row: dict[str, Any]) -> bool:
    return any(row.get(key) for key in ("events", "statistics", "lineups", "players"))


class BroadcastOverlayService:
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
        return f"broadcast:fixture:{external_id}:{block}"

    def _cached_or_fetch(
        self,
        external_id: int,
        block: str,
        ttl_seconds: int,
        fetch: Callable[[], Any],
    ) -> Any:
        key = self._cache_key(external_id, block)
        cached = _cache_get(self.cache, key)
        if cached is not None:
            return cached
        value = fetch()
        if value is not None:
            _cache_set(self.cache, key, value, ttl_seconds)
        return value

    def _live_blocks(self, external_id: int) -> dict[str, Any]:
        return {
            "core": self._cached_or_fetch(
                external_id,
                "core",
                BROADCAST_OVERLAY_TTL_SECONDS,
                lambda: self.api_client.get_fixture(external_id),
            ),
            "events": self._cached_or_fetch(
                external_id,
                "events",
                BROADCAST_OVERLAY_TTL_SECONDS,
                lambda: self.api_client.get_events(external_id),
            ),
            "statistics": self._cached_or_fetch(
                external_id,
                "statistics",
                60,
                lambda: self.api_client.get_statistics(external_id),
            ),
            "players": self._cached_or_fetch(
                external_id,
                "players",
                60,
                lambda: self.api_client.get_players(external_id),
            ),
            "lineups": self._cached_or_fetch(
                external_id,
                "lineups",
                300,
                lambda: self.api_client.get_lineups(external_id),
            ),
        }

    def get_overlay(
        self,
        external_id: int,
        user: Any,
        league_slug: str | None = None,
    ) -> dict[str, Any] | None:
        overlay_key = self._cache_key(external_id, "overlay")
        cached_overlay = _cache_get(self.cache, overlay_key)
        if cached_overlay is not None:
            if isinstance(cached_overlay, dict):
                polling = cached_overlay.setdefault("polling", {})
                if isinstance(polling, dict):
                    polling["cache_hit"] = True
            return cached_overlay

        row = _fixture_row(self.session, external_id)
        status_short = row.get("status_short") if row else None
        use_api = row is None or status_short not in FINISHED_STATUSES

        if use_api:
            upstream_failed = False
            try:
                blocks = self._live_blocks(external_id)
            except (ApiFootballError, BroadcastApiFootballUnavailable):
                upstream_failed = True
                blocks = {
                    "core": None,
                    "events": None,
                    "statistics": None,
                    "players": None,
                    "lineups": None,
                }
            if row is None:
                if upstream_failed:
                    raise BroadcastOverlayError("broadcast_upstream_unavailable")
                if not isinstance(blocks["core"], dict):
                    return None
                row = _fallback_row_from_api(external_id, blocks["core"])
            elif upstream_failed and not _has_overlay_detail_fallback(row):
                raise BroadcastOverlayError("broadcast_upstream_unavailable")
            payload = _assemble_overlay(
                self.session,
                row,
                core=blocks["core"],
                events=blocks["events"] if blocks["events"] is not None else row.get("events"),
                lineups=blocks["lineups"] if blocks["lineups"] is not None else row.get("lineups"),
                statistics=(
                    blocks["statistics"]
                    if blocks["statistics"] is not None
                    else row.get("statistics")
                ),
                players=blocks["players"] if blocks["players"] is not None else row.get("players"),
                standings=_group_standings_block(self.session, row, external_id),
                league_slug=league_slug,
                cache_hit=False,
                interval_seconds=BROADCAST_OVERLAY_TTL_SECONDS,
                now_func=self.now_func,
            )
            _cache_set(self.cache, overlay_key, payload, BROADCAST_OVERLAY_TTL_SECONDS)
            return payload

        if row is None:
            return None

        live_blocks_for_non_live: dict[str, Any] | None = None
        try:
            live_blocks_for_non_live = self._live_blocks(external_id)
        except (ApiFootballError, BroadcastApiFootballUnavailable):
            live_blocks_for_non_live = None

        if live_blocks_for_non_live:
            row_events = (
                live_blocks_for_non_live["events"]
                if live_blocks_for_non_live["events"] is not None
                else row.get("events")
            )
            row_lineups = (
                live_blocks_for_non_live["lineups"]
                if live_blocks_for_non_live["lineups"] is not None
                else row.get("lineups")
            )
            row_statistics = (
                live_blocks_for_non_live["statistics"]
                if live_blocks_for_non_live["statistics"] is not None
                else row.get("statistics")
            )
            row_players = (
                live_blocks_for_non_live["players"]
                if live_blocks_for_non_live["players"] is not None
                else row.get("players")
            )
            if (
                row_events
                or row_lineups
                or row_statistics
                or row_players
            ):
                payload = _assemble_overlay(
                    self.session,
                    row,
                    core=None,
                    events=row_events or [],
                    lineups=row_lineups or [],
                    statistics=row_statistics or [],
                    players=row_players or [],
                    standings=_group_standings_block(self.session, row, external_id),
                    league_slug=league_slug,
                cache_hit=False,
                interval_seconds=BROADCAST_OVERLAY_TTL_SECONDS,
                now_func=self.now_func,
            )
            _cache_set(self.cache, overlay_key, payload, BROADCAST_OVERLAY_TTL_SECONDS)
            return payload

        interval = (
            BROADCAST_FINISHED_POLL_SECONDS
            if status_short in FINISHED_STATUSES
            else BROADCAST_OVERLAY_TTL_SECONDS
        )
        payload = _assemble_overlay(
            self.session,
            row,
            core=None,
            events=row.get("events") or [],
            lineups=row.get("lineups") or [],
            statistics=row.get("statistics") or [],
            players=row.get("players") or [],
            standings=_group_standings_block(self.session, row, external_id),
            league_slug=league_slug,
            cache_hit=False,
            interval_seconds=interval,
            now_func=self.now_func,
        )
        _cache_set(self.cache, overlay_key, payload, interval)
        return payload
