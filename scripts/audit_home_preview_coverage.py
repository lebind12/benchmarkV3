"""Read-only coverage audit. No secret/connection URL is written to the report."""

import argparse
import json
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

from app.core.config import normalize_database_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    values = dotenv_values(args.env_file)
    url = values.get("DATABASE_URL")
    if not url:
        report = {"status": "unavailable", "reason": "database_not_configured"}
    else:
        engine = create_engine(
            normalize_database_url(url),
            connect_args={"connect_timeout": 10},
            pool_size=1,
            max_overflow=0,
        )
        try:
            with engine.connect() as conn:
                transaction = conn.begin()
                conn.execute(text("SET TRANSACTION READ ONLY"))
                conn.execute(text("SET LOCAL statement_timeout = '15000ms'"))
                report = {
                    "status": "checked",
                    "leagues": [
                        dict(row)
                        for row in conn.execute(
                            text("""
                    SELECT l.external_id, l.name, l.type, l.is_active, f.season_year,
                           count(*) AS fixtures,
                           count(*) FILTER (WHERE f.status_short IN ('FT','AET','PEN')) AS completed,
                           max(f.updated_at) AS last_fixture_update
                    FROM league l JOIN fixture f ON f.league_id=l.id
                    GROUP BY l.external_id,l.name,l.type,l.is_active,f.season_year
                    ORDER BY l.external_id,f.season_year DESC
                """)
                        ).mappings()
                    ],
                    "injuries": dict(
                        conn.execute(
                            text("""
                    SELECT count(*) AS rows, count(fixture_id) AS fixture_scoped,
                           count(reported_at) AS with_reported_at, max(updated_at) AS last_update FROM injury
                """)
                        )
                        .mappings()
                        .one()
                    ),
                    "next_candidates": [
                        dict(row)
                        for row in conn.execute(
                            text("""
                    SELECT f.external_id,l.external_id AS league_external_id,f.status_short,
                           f.kickoff_at,f.updated_at,f.round,ht.external_id AS home_id,at.external_id AS away_id
                    FROM fixture f JOIN league l ON l.id=f.league_id
                    JOIN team ht ON ht.id=f.home_team_id JOIN team at ON at.id=f.away_team_id
                    WHERE l.is_active AND f.kickoff_at>=now() AND f.status_short='NS'
                    ORDER BY f.kickoff_at LIMIT 30
                """)
                        ).mappings()
                    ],
                }
                transaction.rollback()
        except Exception as exc:  # noqa: BLE001 - audit reports only a sanitized error type
            report = {"status": "unavailable", "reason": type(exc).__name__}
        finally:
            engine.dispose()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "reason": report.get("reason"),
                "league_season_groups": len(report.get("leagues", [])),
            }
        )
    )


if __name__ == "__main__":
    main()
