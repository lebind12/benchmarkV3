from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


TEAM_SQL = text(
    """
    SELECT DISTINCT
        t.external_id,
        t.name AS eng_name,
        COALESCE(t.country, '') AS context,
        COALESCE(t.code, '') AS short_context,
        COALESCE(tt.name_ko, '') AS name_ko,
        COALESCE(tt.short_name_ko, '') AS short_name_ko
    FROM team_season ts
    JOIN league l ON l.id = ts.league_id
    JOIN team t ON t.id = ts.team_id
    JOIN team_translation tt ON tt.team_id = t.id
    WHERE l.external_id = :league
      AND (:season IS NULL OR ts.season_year = :season)
      AND (:pending_only = false OR tt.name_ko IS NULL OR tt.short_name_ko IS NULL)
    ORDER BY t.name
    """
)

PLAYER_SQL = text(
    """
    SELECT
        p.external_id,
        p.name AS eng_name,
        COALESCE(NULLIF(TRIM(CONCAT_WS(' ', p.firstname, p.lastname)), ''), p.name) AS full_name,
        COALESCE(p.nationality, '') AS context,
        COALESCE(string_agg(DISTINCT t.name, '; ' ORDER BY t.name), '') AS short_context,
        COALESCE(pt.name_ko, '') AS name_ko,
        COALESCE(pt.short_name_ko, '') AS short_name_ko
    FROM player_season_stat pss
    JOIN league l ON l.id = pss.league_id
    JOIN player p ON p.id = pss.player_id
    JOIN team t ON t.id = pss.team_id
    JOIN player_translation pt ON pt.player_id = p.id
    WHERE l.external_id = :league
      AND (:season IS NULL OR pss.season_year = :season)
      AND (:pending_only = false OR pt.name_ko IS NULL OR pt.short_name_ko IS NULL)
    GROUP BY p.id, p.external_id, p.name, p.nationality, pt.name_ko,
             pt.short_name_ko
    ORDER BY p.name
    """
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export a league-scoped backfill translation queue to CSV."
    )
    parser.add_argument("--league", type=int, required=True, help="API-Football league id")
    parser.add_argument("--season", type=int, help="Season year, e.g. 2025")
    parser.add_argument("--entity", choices=("team", "player"), required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--all", action="store_true", help="Export filled rows too")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    sql = TEAM_SQL if args.entity == "team" else PLAYER_SQL
    params = {
        "league": args.league,
        "season": args.season,
        "pending_only": not args.all,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(sql, params).mappings()]

    fieldnames = [
        "external_id",
        "eng_name",
        "full_name",
        "context",
        "short_context",
        "name_ko",
        "short_name_ko",
    ]
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print({"entity": args.entity, "league": args.league, "season": args.season, "rows": len(rows), "output": str(output)})


if __name__ == "__main__":
    main()
