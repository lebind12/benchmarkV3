from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


PLAYER_SQL = text(
    """
    WITH target_teams AS (
        SELECT DISTINCT ts.team_id
        FROM team_season ts
        JOIN league l ON l.id = ts.league_id
        WHERE l.external_id = :league
          AND ts.season_year = :season
    )
    SELECT
        p.external_id,
        p.name AS eng_name,
        COALESCE(NULLIF(TRIM(CONCAT_WS(' ', p.firstname, p.lastname)), ''), p.name) AS full_name,
        COALESCE(p.nationality, '') AS context,
        COALESCE(t.name, '') AS short_context,
        COALESCE(pt.name_ko, '') AS name_ko,
        COALESCE(pt.short_name_ko, '') AS short_name_ko
    FROM player p
    JOIN target_teams tt ON tt.team_id = p.current_team_id
    JOIN team t ON t.id = p.current_team_id
    JOIN player_translation pt ON pt.player_id = p.id
    WHERE (:pending_only = false OR pt.name_ko IS NULL OR pt.short_name_ko IS NULL)
    ORDER BY t.name, p.name
    """
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export current-team player translation queue for a league/season."
    )
    parser.add_argument("--league", type=int, default=1)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--all", action="store_true", help="Export filled rows too")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    params = {
        "league": args.league,
        "season": args.season,
        "pending_only": not args.all,
    }

    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(PLAYER_SQL, params).mappings()]

    fieldnames = [
        "external_id",
        "eng_name",
        "full_name",
        "context",
        "short_context",
        "name_ko",
        "short_name_ko",
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(
        {
            "entity": "player",
            "league": args.league,
            "season": args.season,
            "rows": len(rows),
            "output": str(output),
        }
    )


if __name__ == "__main__":
    main()
