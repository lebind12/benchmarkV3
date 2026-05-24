"""DB-backed fixture detail services."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.home import LEAGUE_SLUGS


class FixtureNotFoundError(LookupError):
    def __init__(self, external_id: int):
        super().__init__(f"fixture_not_found:{external_id}")
        self.external_id = external_id


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _league_ref(row: Any, *, prefix: str = "league") -> dict[str, Any]:
    external_id = row[f"{prefix}_external_id"]
    return {
        "external_id": external_id,
        "slug": LEAGUE_SLUGS.get(external_id, row.get(f"{prefix}_slug") or f"league-{external_id}"),
        "name": row.get(f"{prefix}_name"),
        "name_ko": row.get(f"{prefix}_name_ko"),
        "short_name_ko": row.get(f"{prefix}_short_name_ko"),
        "logo_url": row.get(f"{prefix}_logo_url"),
    }


def _team_ref(row: Any, *, prefix: str) -> dict[str, Any]:
    return {
        "external_id": row[f"{prefix}_external_id"],
        "slug": row.get(f"{prefix}_slug"),
        "name": row.get(f"{prefix}_name"),
        "name_ko": row.get(f"{prefix}_name_ko"),
        "short_name_ko": row.get(f"{prefix}_short_name_ko"),
        "logo_url": row.get(f"{prefix}_logo_url"),
    }


def _compact_slug(value: str, fallback_id: int | None) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    if not slug:
        slug = "player"
    return f"{slug}-{fallback_id}" if fallback_id is not None else slug


def _fallback_player(external_id: int | None, name: str | None) -> dict[str, Any]:
    player_id = external_id or 0
    player_name = name or "Unknown Player"
    return {
        "external_id": player_id,
        "slug": _compact_slug(player_name, player_id),
        "name": player_name,
        "name_ko": None,
        "photo_url": None,
    }


def _coach_ref(
    session: Session,
    *,
    external_id: int | None,
    name: str | None = None,
) -> dict[str, Any] | None:
    if external_id is None and not name:
        return None
    row = None
    if external_id is not None:
        row = session.execute(
            text(
                """
                SELECT c.external_id AS coach_external_id, c.slug AS coach_slug,
                       c.name AS coach_name, c.photo_url AS coach_photo_url,
                       ct.name_ko AS coach_name_ko,
                       ct.short_name_ko AS coach_short_name_ko
                FROM coach c
                LEFT JOIN coach_translation ct ON ct.coach_id = c.id
                WHERE c.external_id = :external_id
                """
            ),
            {"external_id": external_id},
        ).mappings().first()
    if row is None and name:
        row = session.execute(
            text(
                """
                SELECT c.external_id AS coach_external_id, c.slug AS coach_slug,
                       c.name AS coach_name, c.photo_url AS coach_photo_url,
                       ct.name_ko AS coach_name_ko,
                       ct.short_name_ko AS coach_short_name_ko
                FROM coach c
                LEFT JOIN coach_translation ct ON ct.coach_id = c.id
                WHERE lower(c.name) = lower(:name)
                ORDER BY c.external_id NULLS LAST
                LIMIT 1
                """
            ),
            {"name": name},
        ).mappings().first()
    if row is None:
        coach_name = name or "Unknown Coach"
        return {
            "external_id": external_id,
            "slug": _compact_slug(coach_name, external_id),
            "name": coach_name,
            "name_ko": None,
            "short_name_ko": None,
            "photo_url": None,
        }
    return {
        "external_id": row["coach_external_id"],
        "slug": row["coach_slug"],
        "name": row["coach_name"],
        "name_ko": row["coach_name_ko"],
        "short_name_ko": row["coach_short_name_ko"],
        "photo_url": row["coach_photo_url"],
    }


def _player_ref(
    session: Session,
    *,
    external_id: int | None,
    name: str | None = None,
) -> dict[str, Any]:
    if external_id is None:
        return _fallback_player(None, name)
    row = session.execute(
        text(
            """
            SELECT p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko
            FROM player p
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            WHERE p.external_id = :external_id
            """
        ),
        {"external_id": external_id},
    ).mappings().first()
    if not row:
        return _fallback_player(external_id, name)
    return {
        "external_id": row["player_external_id"],
        "slug": row["player_slug"],
        "name": row["player_name"],
        "name_ko": row["player_name_ko"],
        "photo_url": row["player_photo_url"],
    }


_FIXTURE_SQL = text(
    """
    SELECT f.id, f.external_id, f.season_year, f.home_team_id, f.away_team_id,
           f.round, f.status_short, f.status_long,
           f.kickoff_at, f.referee, f.goals_home, f.goals_away,
           f.score_pen_home AS penalty_home, f.score_pen_away AS penalty_away,
           v.name AS venue_name, v.city AS venue_city,
           l.external_id AS league_external_id, l.slug AS league_slug,
           l.name AS league_name, l.logo_url AS league_logo_url,
           lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
           ht.external_id AS home_external_id, ht.slug AS home_slug,
           ht.name AS home_name, ht.logo_url AS home_logo_url,
           htt.name_ko AS home_name_ko, htt.short_name_ko AS home_short_name_ko,
           at.external_id AS away_external_id, at.slug AS away_slug,
           at.name AS away_name, at.logo_url AS away_logo_url,
           att.name_ko AS away_name_ko, att.short_name_ko AS away_short_name_ko,
           fd.events, fd.statistics, fd.lineups, fd.players
    FROM fixture f
    JOIN league l ON l.id = f.league_id
    LEFT JOIN league_translation lt ON lt.league_id = l.id
    LEFT JOIN venue v ON v.id = f.venue_id
    LEFT JOIN team ht ON ht.id = f.home_team_id
    LEFT JOIN team at ON at.id = f.away_team_id
    LEFT JOIN team_translation htt ON htt.team_id = ht.id
    LEFT JOIN team_translation att ON att.team_id = at.id
    LEFT JOIN fixture_detail fd ON fd.fixture_id = f.id
    WHERE f.external_id = :external_id
    """
)


def _fixture_row(session: Session, external_id: int):
    row = session.execute(_FIXTURE_SQL, {"external_id": external_id}).mappings().first()
    if not row:
        raise FixtureNotFoundError(external_id)
    return row


def _event_time(event: dict[str, Any]) -> tuple[int, int | None]:
    time_obj = event.get("time") if isinstance(event.get("time"), dict) else {}
    return int(time_obj.get("elapsed") or 0), time_obj.get("extra")


def _event_type(event: dict[str, Any]) -> str | None:
    kind = str(event.get("type") or "").lower()
    detail = str(event.get("detail") or "").lower()
    if kind == "goal":
        if "penalty" in detail:
            return "goal_penalty"
        if "own" in detail:
            return "goal_own"
        return "goal"
    if kind == "card":
        if "second" in detail or "yellow/red" in detail:
            return "yellow_red"
        if "red" in detail:
            return "red_card"
        return "yellow_card"
    if kind in {"subst", "substitution"}:
        return "substitution"
    if kind == "var":
        return "var"
    return None


def _normalize_event(session: Session, event: dict[str, Any], index: int, fixture_external_id: int) -> dict[str, Any] | None:
    mapped_type = _event_type(event)
    if mapped_type is None:
        return None
    minute, extra = _event_time(event)
    team = event.get("team") if isinstance(event.get("team"), dict) else {}
    player = event.get("player") if isinstance(event.get("player"), dict) else {}
    assist = event.get("assist") if isinstance(event.get("assist"), dict) else {}
    return {
        "id": f"{fixture_external_id}:{index}",
        "minute": minute,
        "extra": extra,
        "team_external_id": team.get("id"),
        "type": mapped_type,
        "player": _player_ref(session, external_id=player.get("id"), name=player.get("name")),
        "assist": _player_ref(session, external_id=assist.get("id"), name=assist.get("name")) if assist.get("id") or assist.get("name") else None,
        "player_out": _player_ref(session, external_id=assist.get("id"), name=assist.get("name")) if mapped_type == "substitution" and (assist.get("id") or assist.get("name")) else None,
        "detail": event.get("detail"),
    }


def get_match_detail(session: Session, external_id: int) -> dict[str, Any]:
    row = _fixture_row(session, external_id)
    events = row.get("events") or []
    goal_events = []
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            continue
        normalized = _normalize_event(session, event, index, external_id)
        if normalized and normalized["type"] in {"goal", "goal_penalty", "goal_own"}:
            goal_events.append(
                {
                    "minute": normalized["minute"],
                    "extra": normalized["extra"],
                    "scorer": normalized["player"],
                    "team_external_id": normalized["team_external_id"],
                    "type": {
                        "goal": "normal",
                        "goal_penalty": "penalty",
                        "goal_own": "own_goal",
                    }[normalized["type"]],
                }
            )
    goal_events.sort(key=lambda item: (item["minute"], item["extra"] or 0))
    return {
        "external_id": row["external_id"],
        "league": _league_ref(row),
        "round": row["round"],
        "status_short": row["status_short"],
        "status_long": row["status_long"] or row["status_short"],
        "kickoff_at": _iso(row["kickoff_at"]),
        "venue": {"name": row["venue_name"], "city": row["venue_city"]} if row["venue_name"] else None,
        "referee": row["referee"],
        "home": _team_ref(row, prefix="home"),
        "away": _team_ref(row, prefix="away"),
        "goals_home": row["goals_home"],
        "goals_away": row["goals_away"],
        "penalty_home": row["penalty_home"],
        "penalty_away": row["penalty_away"],
        "goal_events": goal_events,
    }


def get_fixture_events(session: Session, external_id: int) -> dict[str, Any]:
    row = _fixture_row(session, external_id)
    events = []
    for index, event in enumerate(row.get("events") or []):
        if isinstance(event, dict):
            normalized = _normalize_event(session, event, index, external_id)
            if normalized:
                events.append(normalized)
    events.sort(key=lambda item: (item["minute"], item["extra"] or 0))
    return {"events": events}


def _parse_decimal(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _players_detail_map(players_payload: Any) -> dict[int, dict[str, Any]]:
    stats: dict[int, dict[str, Any]] = {}
    if not isinstance(players_payload, list):
        return stats
    for team_entry in players_payload:
        for entry in team_entry.get("players") or []:
            player = entry.get("player") or {}
            player_id = player.get("id")
            if player_id is None:
                continue
            games = ((entry.get("statistics") or [{}])[0].get("games") or {})
            stats[int(player_id)] = {
                "rating": _parse_decimal(games.get("rating")),
                "minutes": games.get("minutes"),
                "number": games.get("number"),
                "position": games.get("position"),
            }
    return stats


def _empty_lineup(row: Any, side: str) -> dict[str, Any]:
    return {"team": _team_ref(row, prefix=side), "formation": None, "coach": None, "start_xi": [], "bench": []}


def _lineup_player(session: Session, item: dict[str, Any], player_stats: dict[int, dict[str, Any]]) -> dict[str, Any]:
    player = item.get("player") or {}
    player_id = player.get("id")
    detail = player_stats.get(int(player_id), {}) if player_id is not None else {}
    return {
        "player": _player_ref(session, external_id=player_id, name=player.get("name")),
        "number": player.get("number") or detail.get("number"),
        "position": player.get("pos") or detail.get("position") or "",
        "grid": player.get("grid"),
        "rating": detail.get("rating"),
        "minutes": detail.get("minutes"),
    }


def get_fixture_lineups(session: Session, external_id: int) -> dict[str, Any]:
    row = _fixture_row(session, external_id)
    payload = row.get("lineups")
    if not isinstance(payload, list) or not payload:
        return {"home": _empty_lineup(row, "home"), "away": _empty_lineup(row, "away")}
    stats = _players_detail_map(row.get("players"))
    by_team_id = {
        row["home_external_id"]: _empty_lineup(row, "home"),
        row["away_external_id"]: _empty_lineup(row, "away"),
    }
    for lineup in payload:
        if not isinstance(lineup, dict):
            continue
        team_id = (lineup.get("team") or {}).get("id")
        target = by_team_id.get(team_id)
        if target is None:
            continue
        target["formation"] = lineup.get("formation")
        coach = lineup.get("coach") if isinstance(lineup.get("coach"), dict) else None
        target["coach"] = _coach_ref(
            session,
            external_id=coach.get("id"),
            name=coach.get("name"),
        ) if coach else None
        target["start_xi"] = [
            _lineup_player(session, item, stats)
            for item in lineup.get("startXI") or []
            if isinstance(item, dict)
        ]
        target["bench"] = [
            _lineup_player(session, item, stats)
            for item in lineup.get("substitutes") or []
            if isinstance(item, dict)
        ]
    return {"home": by_team_id[row["home_external_id"]], "away": by_team_id[row["away_external_id"]]}


STAT_KEYS = {
    "Ball Possession": "possession",
    "Total Shots": "shots_total",
    "Shots on Goal": "shots_on_target",
    "Total passes": "passes_total",
    "Passes %": "passes_accuracy",
    "Corner Kicks": "corners",
    "Fouls": "fouls",
    "Yellow Cards": "yellow",
    "Red Cards": "red",
    "Offsides": "offsides",
}


def _stat_number(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.replace("%", "").strip()
    try:
        return int(Decimal(str(value)))
    except Exception:
        return None


def _empty_stats(team_external_id: int) -> dict[str, Any]:
    return {"team_external_id": team_external_id, **{key: None for key in STAT_KEYS.values()}}


def get_statistics(session: Session, external_id: int) -> dict[str, Any]:
    row = _fixture_row(session, external_id)
    result = {
        row["home_external_id"]: _empty_stats(row["home_external_id"]),
        row["away_external_id"]: _empty_stats(row["away_external_id"]),
    }
    for entry in row.get("statistics") or []:
        if not isinstance(entry, dict):
            continue
        team_id = (entry.get("team") or {}).get("id")
        if team_id not in result:
            continue
        for stat in entry.get("statistics") or []:
            key = STAT_KEYS.get(stat.get("type"))
            if key:
                result[team_id][key] = _stat_number(stat.get("value"))
    return {"home": result[row["home_external_id"]], "away": result[row["away_external_id"]]}


def get_h2h(session: Session, external_id: int, limit: int = 5) -> dict[str, Any]:
    row = _fixture_row(session, external_id)
    rows = session.execute(
        text(
            """
            SELECT h.external_id, h.kickoff_at, h.status_short, h.goals_home, h.goals_away,
                   h.league_external_id, h.league_name,
                   l.slug AS league_slug, lt.short_name_ko AS league_short_name_ko,
                   ht.external_id AS home_external_id, ht.slug AS home_slug,
                   ht.name AS home_name, ht.logo_url AS home_logo_url,
                   htt.name_ko AS home_name_ko, htt.short_name_ko AS home_short_name_ko,
                   at.external_id AS away_external_id, at.slug AS away_slug,
                   at.name AS away_name, at.logo_url AS away_logo_url,
                   att.name_ko AS away_name_ko, att.short_name_ko AS away_short_name_ko
            FROM h2h_fixture h
            JOIN team ht ON ht.id = h.home_team_id
            JOIN team at ON at.id = h.away_team_id
            LEFT JOIN team_translation htt ON htt.team_id = ht.id
            LEFT JOIN team_translation att ON att.team_id = at.id
            LEFT JOIN league l ON l.external_id = h.league_external_id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE LEAST(h.home_team_id, h.away_team_id) = LEAST(:home_id, :away_id)
              AND GREATEST(h.home_team_id, h.away_team_id) = GREATEST(:home_id, :away_id)
              AND h.external_id <> :external_id
              AND h.status_short IN ('FT', 'AET', 'PEN')
            ORDER BY h.kickoff_at DESC
            LIMIT :limit
            """
        ),
        {
            "home_id": row["home_team_id"],
            "away_id": row["away_team_id"],
            "external_id": external_id,
            "limit": limit,
        },
    ).mappings()
    return {
        "h2h": [
            {
                "external_id": item["external_id"],
                "league": {
                    "external_id": item["league_external_id"],
                    "slug": LEAGUE_SLUGS.get(item["league_external_id"], item["league_slug"] or f"league-{item['league_external_id']}"),
                    "short_name_ko": item["league_short_name_ko"],
                    "name": item["league_name"],
                },
                "kickoff_at": _iso(item["kickoff_at"]),
                "home": _team_ref(item, prefix="home"),
                "away": _team_ref(item, prefix="away"),
                "goals_home": item["goals_home"],
                "goals_away": item["goals_away"],
                "status_short": item["status_short"],
            }
            for item in rows
        ]
    }


def get_league_standings(session: Session, external_id: int) -> dict[str, Any]:
    fixture = _fixture_row(session, external_id)
    rows = list(
        session.execute(
            text(
                """
                SELECT s.rank, s.played, s.win, s.draw, s.loss, s.goals_for,
                       s.goals_against, COALESCE(s.goals_diff, s.goals_for - s.goals_against) AS goal_diff,
                       s.points, s.group_name,
                       t.external_id AS team_external_id, t.slug AS team_slug,
                       t.name AS team_name, t.logo_url AS team_logo_url,
                       tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko
                FROM standings s
                JOIN team t ON t.id = s.team_id
                LEFT JOIN team_translation tt ON tt.team_id = t.id
                WHERE s.league_id = (SELECT league_id FROM fixture WHERE external_id = :external_id)
                  AND s.season_year = (SELECT season_year FROM fixture WHERE external_id = :external_id)
                ORDER BY s.group_name NULLS FIRST, s.rank ASC, s.id ASC
                """
            ),
            {"external_id": external_id},
        ).mappings()
    )
    home_id = fixture["home_external_id"]
    away_id = fixture["away_external_id"]
    home_groups = {r["group_name"] for r in rows if r["team_external_id"] == home_id}
    away_groups = {r["group_name"] for r in rows if r["team_external_id"] == away_id}
    shared = [group for group in home_groups.intersection(away_groups) if group is not None]
    group_name = shared[0] if shared else None
    if group_name is not None:
        rows = [r for r in rows if r["group_name"] == group_name]
    elif any(r["group_name"] is not None for r in rows):
        rows = [r for r in rows if r["group_name"] is None]
    return {
        "league": _league_ref(fixture),
        "season": fixture["season_year"],
        "group_name": group_name,
        "highlighted_team_ids": [home_id, away_id],
        "rows": [
            {
                "rank": r["rank"],
                "team": _team_ref(r, prefix="team"),
                "played": r["played"],
                "win": r["win"],
                "draw": r["draw"],
                "loss": r["loss"],
                "goals_for": r["goals_for"],
                "goals_against": r["goals_against"],
                "goal_diff": r["goal_diff"],
                "points": r["points"],
                "group_name": r["group_name"],
            }
            for r in rows
        ],
    }
