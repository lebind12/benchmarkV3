"""Backfill coach/team_coach rows from stored fixture_detail.lineups JSONB.

The DB already stores lineup JSON for many fixtures. This script extracts the
coach payloads in memory, upserts unique coaches once, then bulk-links teams to
coaches. That avoids a slow per-fixture network round trip against Supabase.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings, normalize_database_url
from app.workers.daily_sync.mappers import compact_coach
from app.workers.daily_sync.store import (
    _UPSERT_COACH_BY_EXTERNAL_ID,
    _UPSERT_COACH_BY_SLUG,
    _UPSERT_TEAM_COACH,
)


_ENSURE_COACH_TRANSLATION = text(
    "INSERT INTO coach_translation (coach_id) VALUES (:coach_id) "
    "ON CONFLICT (coach_id) DO NOTHING"
)


def _coach_key(mapped: dict[str, Any]) -> tuple[str, int | str]:
    external_id = mapped.get("external_id")
    if external_id is not None:
        return ("id", int(external_id))
    return ("slug", str(mapped["slug"]))


def main() -> None:
    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    fixture_count = 0
    raw_links: list[dict[str, Any]] = []
    coaches: dict[tuple[str, int | str], dict[str, Any]] = {}

    with Session(engine) as session:
        rows = session.execute(
            text(
                """
                SELECT f.external_id, fd.lineups
                FROM fixture_detail fd
                JOIN fixture f ON f.id = fd.fixture_id
                WHERE fd.lineups IS NOT NULL
                ORDER BY f.kickoff_at, f.external_id
                """
            )
        ).mappings()

        for row in rows:
            lineups = row["lineups"]
            if not isinstance(lineups, list):
                continue
            fixture_count += 1
            for lineup in lineups:
                if not isinstance(lineup, dict):
                    continue
                team = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
                team_external_id = team.get("id")
                mapped = compact_coach(lineup.get("coach"))
                if team_external_id is None or mapped is None:
                    continue
                key = _coach_key(mapped)
                coaches[key] = mapped
                raw_links.append(
                    {
                        "coach_key": key,
                        "team_external_id": team_external_id,
                        "fixture_external_id": row["external_id"],
                    }
                )

        coach_ids: dict[tuple[str, int | str], int] = {}
        for key, mapped in coaches.items():
            statement = (
                _UPSERT_COACH_BY_EXTERNAL_ID
                if mapped["external_id"] is not None
                else _UPSERT_COACH_BY_SLUG
            )
            coach_id = session.execute(statement, mapped).scalar_one()
            coach_ids[key] = coach_id
            session.execute(_ENSURE_COACH_TRANSLATION, {"coach_id": coach_id})

        link_rows = [
            {
                "coach_id": coach_ids[item["coach_key"]],
                "team_external_id": item["team_external_id"],
                "fixture_external_id": item["fixture_external_id"],
            }
            for item in raw_links
            if item["coach_key"] in coach_ids
        ]
        if link_rows:
            session.execute(_UPSERT_TEAM_COACH, link_rows)
        session.commit()

    print(
        json.dumps(
            {
                "fixtures_seen": fixture_count,
                "coaches_seen": len(coaches),
                "team_coach_links_seen": len(link_rows),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
