"""Pure mapping helpers for API-Football payloads."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

FINISHED_STATUS = {"FT", "AET", "PEN"}


def parse_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    match = re.search(r"-?\d+", str(value))
    if not match:
        return None
    return int(match.group(0))


def parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    raw = str(value)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def slugify(name: str | None, external_id: int | None, fallback: str) -> str:
    base = name or fallback
    normalized = unicodedata.normalize("NFKD", base)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    if not slug:
        slug = fallback
    if external_id is None:
        return slug
    return f"{slug}-{external_id}"


def select_latest_two_actual_seasons(league_payload: dict[str, Any]) -> list[int]:
    seasons = league_payload.get("seasons") or []
    years = sorted(
        {int(season["year"]) for season in seasons if isinstance(season, dict) and season.get("year")},
        reverse=True,
    )
    if not years:
        return []

    current = None
    for season in seasons:
        if isinstance(season, dict) and season.get("current") and season.get("year"):
            current = int(season["year"])
            break
    if current is None:
        current = years[0]

    previous = next((year for year in years if year < current), None)
    return [year for year in (current, previous) if year is not None]


def compact_team(team: dict[str, Any] | None) -> dict[str, Any] | None:
    if not team or not team.get("id"):
        return None
    return {
        "external_id": int(team["id"]),
        "name": team.get("name") or f"Team {team['id']}",
        "code": team.get("code"),
        "country": team.get("country"),
        "founded": parse_int(team.get("founded")),
        "is_national": bool(team.get("national")) if team.get("national") is not None else False,
        "logo_url": team.get("logo"),
        "slug": slugify(team.get("name"), int(team["id"]), "team"),
    }


def compact_venue(venue: dict[str, Any] | None) -> dict[str, Any] | None:
    if not venue:
        return None
    external_id = parse_int(venue.get("id"))
    # Avoid inserting duplicate NULL-external venues from fixture-only payloads.
    if external_id is None:
        return None
    name = venue.get("name")
    if not name:
        return None
    return {
        "external_id": external_id,
        "name": name,
        "city": venue.get("city"),
        "country": venue.get("country"),
        "capacity": parse_int(venue.get("capacity")),
        "surface": venue.get("surface"),
        "address": venue.get("address"),
        "image_url": venue.get("image"),
    }


def compact_coach(coach: dict[str, Any] | None) -> dict[str, Any] | None:
    if not coach:
        return None
    name = coach.get("name")
    external_id = parse_int(coach.get("id"))
    if not name:
        return None
    return {
        "external_id": external_id,
        "name": name,
        "photo_url": coach.get("photo"),
        "slug": slugify(name, external_id, "coach"),
    }


def league_from_api(entry: dict[str, Any]) -> dict[str, Any] | None:
    league = entry.get("league") or {}
    country = entry.get("country") or {}
    external_id = parse_int(league.get("id"))
    if external_id is None:
        return None
    league_type = league.get("type") or "League"
    if league_type not in {"League", "Cup"}:
        league_type = "Cup"
    current_season = None
    for season in entry.get("seasons") or []:
        if isinstance(season, dict) and season.get("current") and season.get("year"):
            current_season = parse_int(season.get("year"))
            break
    return {
        "external_id": external_id,
        "name": league.get("name") or f"League {external_id}",
        "type": league_type,
        "logo_url": league.get("logo"),
        "country_name": country.get("name"),
        "country_code": country.get("code"),
        "country_flag": country.get("flag"),
        "slug": slugify(league.get("name"), external_id, "league"),
        "current_season": current_season,
    }


def fixture_from_api(entry: dict[str, Any]) -> dict[str, Any] | None:
    fixture = entry.get("fixture") or {}
    league = entry.get("league") or {}
    fixture_external_id = parse_int(fixture.get("id"))
    league_external_id = parse_int(league.get("id"))
    season_year = parse_int(league.get("season"))
    if fixture_external_id is None or league_external_id is None or season_year is None:
        return None

    teams = entry.get("teams") or {}
    home = teams.get("home") or {}
    away = teams.get("away") or {}
    goals = entry.get("goals") or {}
    score = entry.get("score") or {}
    periods = fixture.get("periods") or {}
    status = fixture.get("status") or {}
    venue = compact_venue(fixture.get("venue") or {})
    kickoff = parse_datetime(fixture.get("date"))
    if kickoff is None:
        timestamp = parse_int(fixture.get("timestamp"))
        kickoff = datetime.fromtimestamp(timestamp or 0, timezone.utc)

    def score_part(name: str, side: str) -> int | None:
        part = score.get(name) or {}
        return parse_int(part.get(side))

    return {
        "external_id": fixture_external_id,
        "league_external_id": league_external_id,
        "season_year": season_year,
        "round": league.get("round"),
        "home_team_external_id": parse_int(home.get("id")),
        "away_team_external_id": parse_int(away.get("id")),
        "venue_external_id": venue["external_id"] if venue else None,
        "referee": fixture.get("referee"),
        "timezone": fixture.get("timezone"),
        "kickoff_at": kickoff,
        "timestamp_unix": parse_int(fixture.get("timestamp")),
        "status_long": status.get("long"),
        "status_short": status.get("short") or "TBD",
        "status_elapsed": parse_int(status.get("elapsed")),
        "period_first": parse_int(periods.get("first")),
        "period_second": parse_int(periods.get("second")),
        "goals_home": parse_int(goals.get("home")),
        "goals_away": parse_int(goals.get("away")),
        "score_ht_home": score_part("halftime", "home"),
        "score_ht_away": score_part("halftime", "away"),
        "score_ft_home": score_part("fulltime", "home"),
        "score_ft_away": score_part("fulltime", "away"),
        "score_et_home": score_part("extratime", "home"),
        "score_et_away": score_part("extratime", "away"),
        "score_pen_home": score_part("penalty", "home"),
        "score_pen_away": score_part("penalty", "away"),
        "home_winner": home.get("winner"),
        "away_winner": away.get("winner"),
    }


def player_from_api(player: dict[str, Any], *, current_team_external_id: int | None = None) -> dict[str, Any] | None:
    if not player or not player.get("id"):
        return None
    birth = player.get("birth") or {}
    external_id = int(player["id"])
    return {
        "external_id": external_id,
        "name": player.get("name") or f"Player {external_id}",
        "firstname": player.get("firstname"),
        "lastname": player.get("lastname"),
        "age": parse_int(player.get("age")),
        "birth_date": parse_date(birth.get("date")),
        "birth_place": birth.get("place"),
        "birth_country": birth.get("country"),
        "nationality": player.get("nationality"),
        "height_cm": parse_int(player.get("height")),
        "weight_kg": parse_int(player.get("weight")),
        "injured": bool(player.get("injured")) if player.get("injured") is not None else False,
        "photo_url": player.get("photo"),
        "current_team_external_id": current_team_external_id,
        "slug": slugify(player.get("name"), external_id, "player"),
    }


def standing_rows_from_api(entry: dict[str, Any]) -> list[dict[str, Any]]:
    league = entry.get("league") or {}
    league_external_id = parse_int(league.get("id"))
    season_year = parse_int(league.get("season"))
    if league_external_id is None or season_year is None:
        return []
    rows: list[dict[str, Any]] = []
    groups = league.get("standings") or []
    for group_rows in groups:
        if not isinstance(group_rows, list):
            continue
        for row in group_rows:
            if not isinstance(row, dict):
                continue
            team = row.get("team") or {}
            team_external_id = parse_int(team.get("id"))
            if team_external_id is None:
                continue
            all_stats = row.get("all") or {}
            all_goals = all_stats.get("goals") or {}
            rows.append(
                {
                    "league_external_id": league_external_id,
                    "season_year": season_year,
                    "team_external_id": team_external_id,
                    "group_name": row.get("group"),
                    "rank": parse_int(row.get("rank")) or 0,
                    "points": parse_int(row.get("points")) or 0,
                    "played": parse_int(all_stats.get("played")) or 0,
                    "win": parse_int(all_stats.get("win")) or 0,
                    "draw": parse_int(all_stats.get("draw")) or 0,
                    "loss": parse_int(all_stats.get("lose")) or 0,
                    "goals_for": parse_int(all_goals.get("for")) or 0,
                    "goals_against": parse_int(all_goals.get("against")) or 0,
                    "goals_diff": parse_int(row.get("goalsDiff")),
                    "form": row.get("form"),
                    "status": row.get("status"),
                    "description": row.get("description"),
                    "home_away_breakdown": {
                        "home": row.get("home"),
                        "away": row.get("away"),
                    },
                    "raw_data": row,
                }
            )
    return rows


def player_stat_from_api(stat: dict[str, Any]) -> dict[str, Any] | None:
    team = stat.get("team") or {}
    league = stat.get("league") or {}
    games = stat.get("games") or {}
    goals = stat.get("goals") or {}
    cards = stat.get("cards") or {}
    if not team.get("id") or not league.get("id") or not league.get("season"):
        return None
    return {
        "team_external_id": int(team["id"]),
        "league_external_id": int(league["id"]),
        "season_year": int(league["season"]),
        "position": games.get("position"),
        "shirt_number": parse_int(games.get("number")),
        "appearances": parse_int(games.get("appearences")),
        "minutes": parse_int(games.get("minutes")),
        "rating": parse_decimal(games.get("rating")),
        "goals": parse_int(goals.get("total")),
        "assists": parse_int(goals.get("assists")),
        "yellow_cards": parse_int(cards.get("yellow")),
        "red_cards": parse_int(cards.get("red")),
        "raw_stats": stat,
    }
