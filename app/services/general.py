"""DB-backed general site page services."""
from __future__ import annotations

from datetime import date as date_cls
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import home as home_service


TOURNAMENT_LEAGUE_IDS = {1, 2, 3, 45, 48}

TOURNAMENT_TEMPLATES = {
    1: [
        {"round_label": "32강", "slot_count": 16},
        {"round_label": "16강", "slot_count": 8},
        {"round_label": "8강", "slot_count": 4},
        {"round_label": "4강", "slot_count": 2},
        {"round_label": "3위 결정전", "slot_count": 1},
        {"round_label": "결승", "slot_count": 1},
    ],
    2: [
        {"round_label": "플레이오프", "slot_count": 16},
        {"round_label": "32강", "slot_count": 16},
        {"round_label": "16강", "slot_count": 8},
        {"round_label": "8강", "slot_count": 4},
        {"round_label": "4강", "slot_count": 2},
        {"round_label": "결승", "slot_count": 1},
    ],
    3: [
        {"round_label": "플레이오프", "slot_count": 16},
        {"round_label": "32강", "slot_count": 16},
        {"round_label": "16강", "slot_count": 8},
        {"round_label": "8강", "slot_count": 4},
        {"round_label": "4강", "slot_count": 2},
        {"round_label": "결승", "slot_count": 1},
    ],
    45: [
        {"round_label": "128강", "slot_count": 64},
        {"round_label": "64강", "slot_count": 32},
        {"round_label": "32강", "slot_count": 16},
        {"round_label": "16강", "slot_count": 8},
        {"round_label": "8강", "slot_count": 4},
        {"round_label": "4강", "slot_count": 2},
        {"round_label": "결승", "slot_count": 1},
    ],
    48: [
        {"round_label": "1라운드", "slot_count": 35},
        {"round_label": "2라운드", "slot_count": 25},
        {"round_label": "3라운드", "slot_count": 16},
        {"round_label": "16강", "slot_count": 8},
        {"round_label": "8강", "slot_count": 4},
        {"round_label": "4강", "slot_count": 2},
        {"round_label": "결승", "slot_count": 1},
    ],
}

WORLD_CUP_2026_MATCH_NUMBERS = {
    "32강": list(range(73, 89)),
    "16강": list(range(89, 97)),
    "8강": list(range(97, 101)),
    "4강": [101, 102],
    "3위 결정전": [103],
    "결승": [104],
}


def _league_ref(row: Any, *, prefix: str = "league") -> dict[str, Any] | None:
    return home_service._league_ref(row, prefix=prefix)


def _team_ref(row: Any, *, prefix: str) -> dict[str, Any] | None:
    return home_service._team_ref(row, prefix=prefix)


def _player_ref(row: Any) -> dict[str, Any]:
    return home_service._player_ref(row)


def _coach_ref(row: Any, *, prefix: str = "coach") -> dict[str, Any] | None:
    external_id = row.get(f"{prefix}_external_id")
    name = row.get(f"{prefix}_name")
    if external_id is None and name is None:
        return None
    return {
        "external_id": external_id,
        "slug": row.get(f"{prefix}_slug"),
        "name": name,
        "name_ko": row.get(f"{prefix}_name_ko"),
        "short_name_ko": row.get(f"{prefix}_short_name_ko"),
        "photo_url": row.get(f"{prefix}_photo_url"),
    }


def _iso(value: Any) -> str | None:
    return home_service._iso(value)


def _date(value: Any) -> str | None:
    return home_service._date(value)


def _is_tournament_league(league_id: int) -> bool:
    return league_id in TOURNAMENT_LEAGUE_IDS


def _is_knockout_round(round_name: str | None) -> bool:
    if not round_name:
        return False
    value = round_name.lower()
    return not any(token in value for token in ("group stage", "league stage", "regular season"))


def _round_label_ko(round_name: str | None) -> str:
    if not round_name:
        return "라운드 미정"
    value = round_name.lower()

    round_of = re.search(r"round of\s+(\d+)", value)
    if round_of:
        return f"{round_of.group(1)}강"
    ordinal = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+round\b", value)
    if ordinal:
        return f"{ordinal.group(1)}라운드"
    if "3rd place" in value or "third place" in value:
        return "3위 결정전"
    if "quarter" in value:
        return "8강"
    if "semi" in value:
        return "4강"
    if "final" in value:
        return "결승"
    if "play-off" in value or "playoff" in value or "play-offs" in value or "playoffs" in value:
        return "플레이오프"
    if "qualifying" in value or "preliminary" in value:
        return "예선"
    return round_name


def _round_order(round_label: str, round_name: str | None) -> int:
    value = (round_name or round_label).lower()

    if "preliminary" in value:
        return 100
    if "qualifying" in value:
        return 200
    ordinal = re.search(r"\b(\d+)(?:st|nd|rd|th)?\s+round\b", value)
    if ordinal:
        return 300 + int(ordinal.group(1))
    round_of = re.search(r"round of\s+(\d+)", value)
    if round_of:
        return 1000 - int(round_of.group(1))
    if "play-off" in value or "playoff" in value or "play-offs" in value or "playoffs" in value:
        return 940
    if "quarter" in value:
        return 992
    if "semi" in value:
        return 996
    if "3rd place" in value or "third place" in value:
        return 999
    if "final" in value:
        return 1000
    return 500


def _tournament_template(league_id: int) -> list[dict[str, Any]]:
    return [
        {"round_label": item["round_label"], "slot_count": item["slot_count"]}
        for item in TOURNAMENT_TEMPLATES.get(league_id, [])
    ]


def _list_tournament_rounds(session: Session, *, league_id: int, season: int) -> dict[str, Any] | None:
    if not _is_tournament_league(league_id):
        return None
    rows = session.execute(
        text(
            """
            SELECT f.external_id, f.round, f.kickoff_at, f.status_short,
                   f.goals_home, f.goals_away, f.score_pen_home, f.score_pen_away,
                   f.home_winner, f.away_winner,
                   ht.external_id AS home_external_id, ht.slug AS home_slug,
                   ht.name AS home_name, ht.logo_url AS home_logo_url,
                   htt.name_ko AS home_name_ko, htt.short_name_ko AS home_short_name_ko,
                   at.external_id AS away_external_id, at.slug AS away_slug,
                   at.name AS away_name, at.logo_url AS away_logo_url,
                   att.name_ko AS away_name_ko, att.short_name_ko AS away_short_name_ko
            FROM fixture f
            JOIN league l ON l.id = f.league_id
            LEFT JOIN team ht ON ht.id = f.home_team_id
            LEFT JOIN team at ON at.id = f.away_team_id
            LEFT JOIN team_translation htt ON htt.team_id = ht.id
            LEFT JOIN team_translation att ON att.team_id = at.id
            WHERE l.external_id = :league_id
              AND f.season_year = :season
              AND f.round IS NOT NULL
            ORDER BY f.kickoff_at ASC, f.id ASC
            """
        ),
        {"league_id": league_id, "season": season},
    ).mappings()

    by_label: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not _is_knockout_round(row["round"]):
            continue
        label = _round_label_ko(row["round"])
        bucket = by_label.setdefault(
            label,
            {
                "round_label": label,
                "rounds": set(),
                "round_order": _round_order(label, row["round"]),
                "slot_count": 0,
                "fixtures": [],
            },
        )
        bucket["rounds"].add(row["round"])
        bucket["fixtures"].append(
            {
                "external_id": row["external_id"],
                "round": row["round"],
                "kickoff_at": _iso(row["kickoff_at"]),
                "status_short": row["status_short"] or "NS",
                "goals_home": row["goals_home"],
                "goals_away": row["goals_away"],
                "score_pen_home": row["score_pen_home"],
                "score_pen_away": row["score_pen_away"],
                "home_winner": row["home_winner"],
                "away_winner": row["away_winner"],
                "home": _team_ref(row, prefix="home"),
                "away": _team_ref(row, prefix="away"),
            }
        )

    template = _tournament_template(league_id)
    template_slot_counts = {item["round_label"]: item["slot_count"] for item in template}
    for item in by_label.values():
        item["slot_count"] = template_slot_counts.get(item["round_label"], len(item["fixtures"]))
        if league_id == 1:
            match_numbers = WORLD_CUP_2026_MATCH_NUMBERS.get(item["round_label"], [])
            for idx, fixture in enumerate(item["fixtures"]):
                fixture["match_no"] = match_numbers[idx] if idx < len(match_numbers) else None
    template_labels = {item["round_label"] for item in template}
    rounds = sorted(
        by_label.values(),
        key=lambda item: (item["round_order"], item["round_label"]),
    )
    return {
        "has_tournament": True,
        "template_rounds": template,
        "rounds": [
            {
                **item,
                "rounds": sorted(item["rounds"]),
                "fixture_count": len(item["fixtures"]),
                "from_template": item["round_label"] in template_labels,
            }
            for item in rounds
        ],
    }


def list_leagues(session: Session) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   l.current_season, lt.name_ko AS league_name_ko,
                   lt.short_name_ko AS league_short_name_ko
            FROM league l
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE l.is_active = true
            ORDER BY CASE l.external_id
                WHEN 1 THEN 1 WHEN 39 THEN 2 WHEN 2 THEN 3 WHEN 3 THEN 4 WHEN 48 THEN 5 WHEN 45 THEN 6 ELSE 99
            END, l.name
            """
        )
    ).mappings()
    return {"items": [_league_ref(row) | {"season": row["current_season"]} for row in rows]}


def list_fixtures(
    session: Session,
    *,
    league_id: int | None = None,
    period: str = "week",
    date: date_cls | None = None,
    team_slug: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    start, end = home_service._date_window(date, period)
    where = [
        "f.kickoff_at >= :start",
        "f.kickoff_at < :end",
        "f.home_team_id IS NOT NULL",
        "f.away_team_id IS NOT NULL",
        "l.is_active = true",
    ]
    params: dict[str, Any] = {"start": start, "end": end, "limit": limit}
    if league_id is not None:
        where.append("l.external_id = :league_id")
        params["league_id"] = league_id
    if team_slug:
        where.append("(ht.slug = :team_slug OR at.slug = :team_slug)")
        params["team_slug"] = team_slug
    rows = session.execute(
        text(
            f"""
            SELECT f.external_id, f.kickoff_at, f.status_short, f.goals_home, f.goals_away,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   ht.external_id AS home_external_id, ht.slug AS home_slug,
                   ht.name AS home_name, ht.logo_url AS home_logo_url,
                   htt.name_ko AS home_name_ko, htt.short_name_ko AS home_short_name_ko,
                   at.external_id AS away_external_id, at.slug AS away_slug,
                   at.name AS away_name, at.logo_url AS away_logo_url,
                   att.name_ko AS away_name_ko, att.short_name_ko AS away_short_name_ko
            FROM fixture f
            JOIN league l ON l.id = f.league_id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            JOIN team ht ON ht.id = f.home_team_id
            JOIN team at ON at.id = f.away_team_id
            LEFT JOIN team_translation htt ON htt.team_id = ht.id
            LEFT JOIN team_translation att ON att.team_id = at.id
            WHERE {' AND '.join(where)}
            ORDER BY f.kickoff_at ASC, f.id ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return {
        "items": [
            {
                "external_id": row["external_id"],
                "league": _league_ref(row),
                "home": _team_ref(row, prefix="home"),
                "away": _team_ref(row, prefix="away"),
                "kickoff_at": _iso(row["kickoff_at"]),
                "status_short": row["status_short"] or "NS",
                "goals_home": row["goals_home"],
                "goals_away": row["goals_away"],
            }
            for row in rows
        ],
        "filters_applied": {"period": period, "league_id": league_id, "date": _date(date), "team_slug": team_slug},
    }


def get_standings(session: Session, *, league_id: int = 39) -> dict[str, Any]:
    payload = home_service.get_home_standings(session, league_id=league_id)
    league = payload["league"]
    season = payload["season"]
    if league is None or season is None:
        return {**payload, "groups": []}
    grouped_rows = session.execute(
        text(
            """
            SELECT s.group_name, s.rank, s.points, s.played, s.win, s.draw, s.loss,
                   s.goals_for, s.goals_against,
                   COALESCE(s.goals_diff, s.goals_for - s.goals_against) AS goal_diff,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko
            FROM standings s
            JOIN league l ON l.id = s.league_id
            JOIN team t ON t.id = s.team_id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            WHERE l.external_id = :league_id AND s.season_year = :season
            ORDER BY s.group_name NULLS LAST, s.rank ASC, s.id ASC
            """
        ),
        {"league_id": league_id, "season": season},
    ).mappings()
    groups: dict[str | None, list[dict[str, Any]]] = {}
    for row in grouped_rows:
        groups.setdefault(row["group_name"], []).append(
            {
                "group_name": row["group_name"],
                "rank": row["rank"],
                "team": _team_ref(row, prefix="team"),
                "points": row["points"],
                "played": row["played"],
                "win": row["win"],
                "draw": row["draw"],
                "loss": row["loss"],
                "goals_for": row["goals_for"],
                "goals_against": row["goals_against"],
                "goal_diff": row["goal_diff"],
            }
        )
    return {
        **payload,
        "rows": [item for group_rows in groups.values() for item in group_rows],
        "groups": [{"group_name": group_name, "rows": group_rows} for group_name, group_rows in groups.items()],
        "tournament": _list_tournament_rounds(session, league_id=league_id, season=season),
    }


def list_teams(
    session: Session,
    *,
    league_id: int | None = None,
    query: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    where = ["l.is_active = true"]
    params: dict[str, Any] = {"limit": limit}
    if league_id is not None:
        where.append("l.external_id = :league_id")
        params["league_id"] = league_id
    if query:
        where.append("(t.name ILIKE :query OR tt.name_ko ILIKE :query OR tt.short_name_ko ILIKE :query)")
        params["query"] = f"%{query}%"
    rows = session.execute(
        text(
            f"""
            SELECT DISTINCT ON (t.id, l.external_id)
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   t.country, t.founded,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   s.rank, s.points, s.played
            FROM team_season ts
            JOIN team t ON t.id = ts.team_id
            JOIN league l ON l.id = ts.league_id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            LEFT JOIN standings s ON s.team_id = t.id AND s.league_id = l.id AND s.season_year = ts.season_year
            WHERE {' AND '.join(where)}
            ORDER BY t.id, l.external_id, COALESCE(s.rank, 9999), t.name
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return {
        "items": [
            {
                "team": _team_ref(row, prefix="team"),
                "league": _league_ref(row),
                "country": row["country"],
                "founded": row["founded"],
                "rank": row["rank"],
                "points": row["points"],
                "played": row["played"],
            }
            for row in rows
        ]
    }


def get_team(session: Session, *, slug: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT t.id, t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   t.country, t.founded, tt.name_ko AS team_name_ko,
                   tt.short_name_ko AS team_short_name_ko,
                   v.name AS venue_name, v.city AS venue_city, v.capacity AS venue_capacity
            FROM team t
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN venue v ON v.id = t.venue_id
            WHERE t.slug = :slug
            """
        ),
        {"slug": slug},
    ).mappings().first()
    if not row:
        return None
    leagues = session.execute(
        text(
            """
            SELECT l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   ts.season_year
            FROM team_season ts
            JOIN league l ON l.id = ts.league_id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE ts.team_id = :team_id AND l.is_active = true
            ORDER BY ts.season_year DESC, l.name
            """
        ),
        {"team_id": row["id"]},
    ).mappings()
    squad = session.execute(
        text(
            """
            SELECT p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko,
                   (
                       ARRAY_AGG(
                           pss.position
                           ORDER BY COALESCE(pss.appearances, 0) DESC, l.external_id
                       ) FILTER (WHERE pss.position IS NOT NULL)
                   )[1] AS position,
                   SUM(COALESCE(pss.appearances, 0)) AS appearances,
                   SUM(COALESCE(pss.goals, 0)) AS goals,
                   SUM(COALESCE(pss.assists, 0)) AS assists
            FROM player p
            JOIN player_season_stat pss ON pss.player_id = p.id
            JOIN league l ON l.id = pss.league_id
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            WHERE pss.team_id = :team_id
              AND l.is_active = true
              AND pss.season_year = l.current_season
            GROUP BY p.id, p.external_id, p.slug, p.name, p.photo_url, pt.name_ko
            ORDER BY SUM(COALESCE(pss.appearances, 0)) DESC, p.name ASC
            LIMIT 40
            """
        ),
        {"team_id": row["id"]},
    ).mappings()
    fixtures = list_fixtures(session, team_slug=slug, period="month", limit=20)["items"]
    coach = session.execute(
        text(
            """
            SELECT c.external_id AS coach_external_id, c.slug AS coach_slug,
                   c.name AS coach_name, c.photo_url AS coach_photo_url,
                   ct.name_ko AS coach_name_ko, ct.short_name_ko AS coach_short_name_ko,
                   tc.last_seen_at,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko
            FROM team_coach tc
            JOIN coach c ON c.id = tc.coach_id
            LEFT JOIN coach_translation ct ON ct.coach_id = c.id
            LEFT JOIN league l ON l.id = tc.league_id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE tc.team_id = :team_id
            ORDER BY tc.last_seen_at DESC NULLS LAST, c.name ASC
            LIMIT 1
            """
        ),
        {"team_id": row["id"]},
    ).mappings().first()
    return {
        "team": _team_ref(row, prefix="team"),
        "country": row["country"],
        "founded": row["founded"],
        "coach": {
            "coach": _coach_ref(coach),
            "league": _league_ref(coach) if coach and coach["league_external_id"] is not None else None,
            "last_seen_at": _iso(coach["last_seen_at"]) if coach else None,
        } if coach else None,
        "venue": {
            "name": row["venue_name"],
            "city": row["venue_city"],
            "capacity": row["venue_capacity"],
        } if row["venue_name"] else None,
        "leagues": [{"league": _league_ref(item), "season": item["season_year"]} for item in leagues],
        "fixtures": fixtures,
        "squad": [
            {
                "player": {
                    "external_id": item["player_external_id"],
                    "slug": item["player_slug"],
                    "name": item["player_name"],
                    "name_ko": item["player_name_ko"],
                    "photo_url": item["player_photo_url"],
                },
                "position": item["position"],
                "appearances": item["appearances"],
                "goals": item["goals"],
                "assists": item["assists"],
            }
            for item in squad
        ],
    }


def list_players(
    session: Session,
    *,
    league_id: int | None = None,
    query: str | None = None,
    metric: str = "goals",
    limit: int = 100,
) -> dict[str, Any]:
    if metric not in home_service.METRICS:
        metric = "goals"
    where = ["l.is_active = true", "pss.season_year = l.current_season"]
    params: dict[str, Any] = {"limit": limit}
    if league_id is not None:
        where.append("l.external_id = :league_id")
        params["league_id"] = league_id
    if query:
        where.append("(p.name ILIKE :query OR pt.name_ko ILIKE :query)")
        params["query"] = f"%{query}%"
    rows = session.execute(
        text(
            f"""
            SELECT p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   pss.position, pss.appearances, pss.minutes, pss.rating,
                   pss.goals, pss.assists, pss.yellow_cards, pss.red_cards,
                   pss.{metric} AS metric_value
            FROM player_season_stat pss
            JOIN player p ON p.id = pss.player_id
            JOIN team t ON t.id = pss.team_id
            JOIN league l ON l.id = pss.league_id
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE {' AND '.join(where)}
            ORDER BY COALESCE(pss.{metric}, 0) DESC, COALESCE(pss.appearances, 0) DESC, p.name ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return {
        "items": [
            {
                "player": _player_ref(row),
                "position": row["position"],
                "appearances": row["appearances"],
                "minutes": row["minutes"],
                "rating": float(row["rating"]) if row["rating"] is not None else None,
                "goals": row["goals"],
                "assists": row["assists"],
                "yellow_cards": row["yellow_cards"],
                "red_cards": row["red_cards"],
                "metric_value": row["metric_value"] or 0,
            }
            for row in rows
        ],
        "coaches": list_coaches(session, league_id=league_id)["items"],
        "metric": metric,
    }


def list_coaches(
    session: Session,
    *,
    league_id: int | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    where = ["l.is_active = true"]
    params: dict[str, Any] = {"limit": limit}
    if league_id is not None:
        where.append("l.external_id = :league_id")
        params["league_id"] = league_id
    rows = session.execute(
        text(
            f"""
            SELECT DISTINCT ON (tc.team_id)
                   c.external_id AS coach_external_id, c.slug AS coach_slug,
                   c.name AS coach_name, c.photo_url AS coach_photo_url,
                   ct.name_ko AS coach_name_ko, ct.short_name_ko AS coach_short_name_ko,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   tc.last_seen_at
            FROM team_coach tc
            JOIN coach c ON c.id = tc.coach_id
            JOIN team t ON t.id = tc.team_id
            JOIN league l ON l.id = tc.league_id
            LEFT JOIN coach_translation ct ON ct.coach_id = c.id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE {' AND '.join(where)}
            ORDER BY tc.team_id, tc.last_seen_at DESC NULLS LAST, c.name ASC
            LIMIT :limit
            """
        ),
        params,
    ).mappings()
    return {
        "items": [
            {
                "coach": _coach_ref(row),
                "team": _team_ref(row, prefix="team"),
                "league": _league_ref(row),
                "last_seen_at": _iso(row["last_seen_at"]),
            }
            for row in rows
        ]
    }


def get_player(session: Session, *, slug: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT p.id, p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko, p.firstname, p.lastname, p.age,
                   p.birth_date, p.birth_place, p.birth_country, p.nationality,
                   p.height_cm, p.weight_kg,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko
            FROM player p
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            LEFT JOIN team t ON t.id = p.current_team_id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            WHERE p.slug = :slug
            """
        ),
        {"slug": slug},
    ).mappings().first()
    if not row:
        return None
    stats = session.execute(
        text(
            """
            SELECT pss.season_year, pss.position, pss.appearances, pss.minutes,
                   pss.rating, pss.goals, pss.assists, pss.yellow_cards, pss.red_cards,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko
            FROM player_season_stat pss
            JOIN league l ON l.id = pss.league_id
            JOIN team t ON t.id = pss.team_id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            WHERE pss.player_id = :player_id
            ORDER BY pss.season_year DESC, l.name
            """
        ),
        {"player_id": row["id"]},
    ).mappings()
    return {
        "player": {
            "external_id": row["player_external_id"],
            "slug": row["player_slug"],
            "name": row["player_name"],
            "name_ko": row["player_name_ko"],
            "photo_url": row["player_photo_url"],
        },
        "profile": {
            "firstname": row["firstname"],
            "lastname": row["lastname"],
            "age": row["age"],
            "birth_date": _date(row["birth_date"]),
            "birth_place": row["birth_place"],
            "birth_country": row["birth_country"],
            "nationality": row["nationality"],
            "height_cm": row["height_cm"],
            "weight_kg": row["weight_kg"],
        },
        "current_team": _team_ref(row, prefix="team") if row["team_external_id"] is not None else None,
        "season_stats": [
            {
                "season": item["season_year"],
                "league": _league_ref(item),
                "team": _team_ref(item, prefix="team"),
                "position": item["position"],
                "appearances": item["appearances"],
                "minutes": item["minutes"],
                "rating": float(item["rating"]) if item["rating"] is not None else None,
                "goals": item["goals"],
                "assists": item["assists"],
                "yellow_cards": item["yellow_cards"],
                "red_cards": item["red_cards"],
            }
            for item in stats
        ],
    }


def get_stats(session: Session, *, league_id: int = 39) -> dict[str, Any]:
    return {
        "league_id": league_id,
        "leaders": {
            metric: home_service.list_home_top_players(session, league_id=league_id, metric=metric, limit=10)
            for metric in ("goals", "assists", "yellow_cards", "red_cards")
        },
        "standings": get_standings(session, league_id=league_id),
    }


def list_news(session: Session, *, limit: int = 30) -> dict[str, Any]:
    return home_service.list_home_news(session, limit=limit)
