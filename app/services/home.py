"""DB-backed services for the main home screen."""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session


ALLOWED_LEAGUE_IDS = {39, 2, 3, 48, 45, 1}
METRICS = {"goals", "assists", "yellow_cards", "red_cards"}
KST = ZoneInfo("Asia/Seoul")

LEAGUE_SLUGS = {
    39: "premier-league",
    2: "champions-league",
    3: "europa-league",
    48: "carabao-cup",
    45: "fa-cup",
    1: "world-cup-2026",
}


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


def _date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _league_ref(row: Any, *, prefix: str = "league") -> dict[str, Any] | None:
    external_id = row.get(f"{prefix}_external_id")
    if external_id is None:
        return None
    return {
        "external_id": external_id,
        "slug": LEAGUE_SLUGS.get(external_id, row.get(f"{prefix}_slug") or f"league-{external_id}"),
        "name_ko": row.get(f"{prefix}_name_ko"),
        "short_name_ko": row.get(f"{prefix}_short_name_ko"),
        "name": row.get(f"{prefix}_name"),
        "logo_url": row.get(f"{prefix}_logo_url"),
    }


def _team_ref(row: Any, *, prefix: str) -> dict[str, Any] | None:
    external_id = row.get(f"{prefix}_external_id")
    if external_id is None:
        return None
    return {
        "external_id": external_id,
        "slug": row.get(f"{prefix}_slug"),
        "name_ko": row.get(f"{prefix}_name_ko"),
        "short_name_ko": row.get(f"{prefix}_short_name_ko"),
        "name": row.get(f"{prefix}_name"),
        "logo_url": row.get(f"{prefix}_logo_url"),
    }


def _player_ref(row: Any) -> dict[str, Any]:
    team = _team_ref(row, prefix="team")
    league = _league_ref(row)
    return {
        "external_id": row["player_external_id"],
        "slug": row["player_slug"],
        "name_ko": row.get("player_name_ko"),
        "name": row["player_name"],
        "photo_url": row.get("player_photo_url"),
        "team": team,
        "league": league,
    }


def _current_kst_date() -> date_cls:
    return datetime.now(KST).date()


def _date_window(value: date_cls | None, period: str) -> tuple[datetime, datetime]:
    day = value or _current_kst_date()
    start_kst = datetime.combine(day, time.min, tzinfo=KST)
    days = {"day": 1, "week": 7, "month": 31}[period]
    end_kst = start_kst + timedelta(days=days)
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)


def list_home_news(session: Session, *, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    rows = session.execute(
        text(
            """
            SELECT id, source, source_url, original_title, image_url, title_ko,
                   summary_ko, published_at
            FROM news_article
            ORDER BY published_at DESC, id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "title_ko": row["title_ko"],
                "title": row["original_title"],
                "summary_ko": row["summary_ko"],
                "source": row["source"],
                "url": row["source_url"],
                "thumbnail_url": row["image_url"],
                "published_at": _iso(row["published_at"]),
            }
            for row in rows
        ]
    }


def list_home_fixtures(
    session: Session,
    *,
    league_id: int | None = None,
    period: str = "day",
    date: date_cls | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    start, end = _date_window(date, period)
    where = [
        "f.kickoff_at >= :start",
        "f.kickoff_at < :end",
        "f.home_team_id IS NOT NULL",
        "f.away_team_id IS NOT NULL",
    ]
    params: dict[str, Any] = {"start": start, "end": end, "limit": limit}
    if league_id is not None:
        where.append("l.external_id = :league_id")
        params["league_id"] = league_id

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
        "filters_applied": {"period": period, "league_id": league_id},
    }


def get_home_standings(session: Session, *, league_id: int = 39) -> dict[str, Any]:
    league = session.execute(
        text(
            """
            SELECT l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   l.current_season, lt.name_ko AS league_name_ko,
                   lt.short_name_ko AS league_short_name_ko
            FROM league l
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE l.external_id = :league_id
            """
        ),
        {"league_id": league_id},
    ).mappings().first()
    if not league:
        return {"league": None, "season": None, "rows": []}
    season = league["current_season"]
    rows = session.execute(
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
            WHERE l.external_id = :league_id
              AND s.season_year = :season
            ORDER BY s.group_name NULLS LAST, s.rank ASC, s.id ASC
            """
        ),
        {"league_id": league_id, "season": season},
    ).mappings()
    return {
        "league": _league_ref(league),
        "season": season,
        "rows": [
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
            for row in rows
        ],
    }


def _player_rows(session: Session, *, league_id: int, metric: str, limit: int) -> list[dict[str, Any]]:
    if metric not in METRICS:
        raise ValueError(f"unsupported metric: {metric}")
    return list(
        session.execute(
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
                       ps.goals, ps.assists, ps.yellow_cards, ps.red_cards,
                       ps.{metric} AS metric_value
                FROM player_season_stat ps
                JOIN player p ON p.id = ps.player_id
                JOIN team t ON t.id = ps.team_id
                JOIN league l ON l.id = ps.league_id
                LEFT JOIN player_translation pt ON pt.player_id = p.id
                LEFT JOIN team_translation tt ON tt.team_id = t.id
                LEFT JOIN league_translation lt ON lt.league_id = l.id
                WHERE l.external_id = :league_id
                  AND ps.season_year = l.current_season
                  AND COALESCE(ps.{metric}, 0) > 0
                ORDER BY ps.{metric} DESC, p.name ASC
                LIMIT :limit
                """
            ),
            {"league_id": league_id, "limit": limit},
        ).mappings()
    )


def list_home_top_players(
    session: Session,
    *,
    league_id: int = 39,
    metric: str = "goals",
    limit: int = 10,
) -> dict[str, Any]:
    league = session.execute(
        text(
            """
            SELECT l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   l.current_season, lt.name_ko AS league_name_ko,
                   lt.short_name_ko AS league_short_name_ko
            FROM league l
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE l.external_id = :league_id
            """
        ),
        {"league_id": league_id},
    ).mappings().first()
    if not league:
        return {"league": None, "season": None, "metric": metric, "rows": []}

    rows = _player_rows(session, league_id=league_id, metric=metric, limit=limit)
    return {
        "league": _league_ref(league),
        "season": league["current_season"],
        "metric": metric,
        "rows": [
            {"rank": idx, "player": _player_ref(row), "metric_value": row["metric_value"]}
            for idx, row in enumerate(rows, start=1)
        ],
    }


def list_home_hot_players(session: Session, *, limit: int = 5) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   COALESCE(ps.goals, 0) AS goals,
                   COALESCE(ps.assists, 0) AS assists,
                   COALESCE(ps.goals, 0) + COALESCE(ps.assists, 0) AS score
            FROM player_season_stat ps
            JOIN player p ON p.id = ps.player_id
            JOIN team t ON t.id = ps.team_id
            JOIN league l ON l.id = ps.league_id
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE l.is_active = true
              AND ps.season_year = l.current_season
              AND COALESCE(ps.goals, 0) + COALESCE(ps.assists, 0) > 0
            ORDER BY score DESC, goals DESC, p.name ASC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return {
        "items": [
            {
                "player": _player_ref(row),
                "goals": row["goals"],
                "assists": row["assists"],
                "score": row["score"],
            }
            for row in rows
        ]
    }


def list_home_transfers(session: Session, *, limit: int = 5) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT tr.id, tr.transfer_date, tr.type,
                   p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko,
                   cur.external_id AS team_external_id, cur.slug AS team_slug,
                   cur.name AS team_name, cur.logo_url AS team_logo_url,
                   curtt.name_ko AS team_name_ko, curtt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko,
                   ft.external_id AS from_team_external_id, ft.slug AS from_team_slug,
                   ft.name AS from_team_name, ft.logo_url AS from_team_logo_url,
                   ftt.name_ko AS from_team_name_ko, ftt.short_name_ko AS from_team_short_name_ko,
                   tt.external_id AS to_team_external_id, tt.slug AS to_team_slug,
                   tt.name AS to_team_name, tt.logo_url AS to_team_logo_url,
                   ttt.name_ko AS to_team_name_ko, ttt.short_name_ko AS to_team_short_name_ko
            FROM transfer tr
            JOIN player p ON p.id = tr.player_id
            JOIN team tt ON tt.id = tr.to_team_id
            JOIN team_season ts ON ts.team_id = tt.id
            JOIN league l ON l.id = ts.league_id AND l.is_active = true
            LEFT JOIN team cur ON cur.id = p.current_team_id
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            LEFT JOIN team_translation curtt ON curtt.team_id = cur.id
            LEFT JOIN team ft ON ft.id = tr.from_team_id
            LEFT JOIN team_translation ftt ON ftt.team_id = ft.id
            LEFT JOIN team_translation ttt ON ttt.team_id = tt.id
            WHERE tr.from_team_id IS NOT NULL
              AND tr.to_team_id IS NOT NULL
            ORDER BY tr.transfer_date DESC, tr.id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    return {
        "items": [
            {
                "id": str(row["id"]),
                "player": _player_ref(row),
                "from_team": _team_ref(row, prefix="from_team"),
                "to_team": _team_ref(row, prefix="to_team"),
                "transfer_date": _date(row["transfer_date"]),
                "fee": row["type"],
            }
            for row in rows
        ]
    }


def list_home_injuries(session: Session, *, limit: int = 5) -> dict[str, Any]:
    rows = session.execute(
        text(
            """
            SELECT i.id, i.type, i.raw_data, i.reported_at,
                   p.external_id AS player_external_id, p.slug AS player_slug,
                   p.name AS player_name, p.photo_url AS player_photo_url,
                   pt.name_ko AS player_name_ko,
                   t.external_id AS team_external_id, t.slug AS team_slug,
                   t.name AS team_name, t.logo_url AS team_logo_url,
                   tt.name_ko AS team_name_ko, tt.short_name_ko AS team_short_name_ko,
                   l.external_id AS league_external_id, l.slug AS league_slug,
                   l.name AS league_name, l.logo_url AS league_logo_url,
                   lt.name_ko AS league_name_ko, lt.short_name_ko AS league_short_name_ko
            FROM injury i
            JOIN player p ON p.id = i.player_id
            JOIN team t ON t.id = i.team_id
            JOIN league l ON l.id = i.league_id
            LEFT JOIN player_translation pt ON pt.player_id = p.id
            LEFT JOIN team_translation tt ON tt.team_id = t.id
            LEFT JOIN league_translation lt ON lt.league_id = l.id
            WHERE l.is_active = true
              AND i.season_year = l.current_season
            ORDER BY i.reported_at DESC NULLS LAST, i.id DESC
            LIMIT :limit
            """
        ),
        {"limit": limit},
    ).mappings()
    items = []
    for row in rows:
        raw_data = row["raw_data"] or {}
        expected_return = raw_data.get("expected_return") if isinstance(raw_data, dict) else None
        items.append(
            {
                "id": str(row["id"]),
                "player": _player_ref(row),
                "injury_type": row["type"] or "부상",
                "expected_return": expected_return,
                "reported_at": _date(row["reported_at"]),
            }
        )
    return {"items": items}
