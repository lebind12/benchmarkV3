"""Import curated Korean player-name translations from CSV.

The CSV is translation-only. It never creates or overwrites ``player`` rows.
Rows are matched by ``player.external_id = csv.player_id`` and existing Korean
values are preserved with COALESCE.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
from app.workers.daily_sync.mappers import parse_int


@dataclass
class PlayerTranslationSeedRow:
    player_external_id: int
    team_external_id: int | None
    eng_name: str
    name_ko: str | None
    short_name_ko: str | None


@dataclass
class PlayerTranslationSeedResult:
    seen: int = 0
    applied: int = 0
    skipped_missing_player: int = 0
    skipped_invalid: int = 0


def iter_player_translation_seed(path: str | Path) -> Iterable[PlayerTranslationSeedRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            player_external_id = parse_int(row.get("player_id"))
            if player_external_id is None:
                continue
            yield PlayerTranslationSeedRow(
                player_external_id=player_external_id,
                team_external_id=parse_int(row.get("team_id")),
                eng_name=(row.get("eng_name") or "").strip(),
                name_ko=(row.get("kor_name") or "").strip() or None,
                short_name_ko=(row.get("kor_short_name") or "").strip() or None,
            )


_UPSERT_PLAYER_TRANSLATION = text(
    """
    INSERT INTO player_translation (player_id, name_ko, short_name_ko, updated_at)
    SELECT p.id, :name_ko, :short_name_ko, now()
    FROM player p
    WHERE p.external_id = :player_external_id
    ON CONFLICT (player_id) DO UPDATE SET
        name_ko = COALESCE(player_translation.name_ko, EXCLUDED.name_ko),
        short_name_ko = COALESCE(player_translation.short_name_ko, EXCLUDED.short_name_ko),
        updated_at = CASE
            WHEN player_translation.name_ko IS NULL
              OR player_translation.short_name_ko IS NULL
            THEN now()
            ELSE player_translation.updated_at
        END
    RETURNING player_id
    """
)


def import_player_translation_seed(
    session,
    path: str | Path,
    *,
    commit_every: int = 500,
) -> PlayerTranslationSeedResult:
    result = PlayerTranslationSeedResult()
    for row in iter_player_translation_seed(path):
        result.seen += 1
        if not row.name_ko and not row.short_name_ko:
            result.skipped_invalid += 1
            continue
        player_id = session.execute(
            _UPSERT_PLAYER_TRANSLATION,
            {
                "player_external_id": row.player_external_id,
                "name_ko": row.name_ko,
                "short_name_ko": row.short_name_ko,
            },
        ).scalar_one_or_none()
        if player_id is None:
            result.skipped_missing_player += 1
        else:
            result.applied += 1
        if result.seen % commit_every == 0:
            session.commit()
    session.commit()
    return result


def run(path: str | Path, *, database_url: str | None = None) -> PlayerTranslationSeedResult:
    settings = get_settings()
    engine = create_engine(
        normalize_database_url(database_url or settings.database_url),
        **database_engine_kwargs(settings),
    )
    try:
        with Session(engine) as session:
            return import_player_translation_seed(session, path)
    finally:
        engine.dispose()


def as_log_payload(result: PlayerTranslationSeedResult) -> dict[str, Any]:
    return {
        "seen": result.seen,
        "applied": result.applied,
        "skipped_missing_player": result.skipped_missing_player,
        "skipped_invalid": result.skipped_invalid,
    }
