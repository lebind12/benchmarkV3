"""Sync players/coaches and translations for one API-Football fixture.

This is intentionally fixture-scoped: it reads the live API-Football fixture
payloads, compares only those player ids against the DB, upserts missing
players/fixture_detail rows, then fills missing player_translation and
coach_translation rows for those same fixture participants.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, text

from app.core.config import get_settings
from app.db import SessionLocal, engine
from app.workers.daily_sync.api import ApiFootballClient
from app.workers.daily_sync.mappers import parse_int
from app.workers.daily_sync.store import (
    StoreCounts,
    upsert_fixture_detail,
    upsert_fixture_entry,
    upsert_league,
    upsert_player_entry,
)
from app.workers.translation_filler import openai_client as openai_client_module
from app.workers.translation_filler import prompt as prompt_module


@dataclass
class FixturePlayerSyncResult:
    fixture_external_id: int
    api_player_ids: list[int] = field(default_factory=list)
    api_coach_ids: list[int] = field(default_factory=list)
    db_players_missing_before: list[int] = field(default_factory=list)
    db_coaches_missing_before: list[int] = field(default_factory=list)
    player_profiles_fetched: int = 0
    player_profiles_fetch_failed: list[int] = field(default_factory=list)
    player_translations_missing_before: list[int] = field(default_factory=list)
    coach_translations_missing_before: list[int] = field(default_factory=list)
    players_upserted: int = 0
    fixture_detail_upserted: bool = False
    player_translations_from_seed: int = 0
    player_translations_from_openai: int = 0
    coach_translations_from_openai: int = 0
    player_translations_still_missing: list[int] = field(default_factory=list)
    coach_translations_still_missing: list[int] = field(default_factory=list)
    counts: dict[str, Any] = field(default_factory=dict)


def _load_seed_translations(seed_dir: Path) -> dict[int, dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    for path in sorted(seed_dir.glob("player_translation*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames or "external_id" not in reader.fieldnames:
                continue
            if "name_ko" not in reader.fieldnames or "short_name_ko" not in reader.fieldnames:
                continue
            for row in reader:
                external_id = parse_int(row.get("external_id"))
                name_ko = (row.get("name_ko") or "").strip()
                short_name_ko = (row.get("short_name_ko") or "").strip()
                if external_id is None or not name_ko or not short_name_ko:
                    continue
                rows.setdefault(
                    external_id,
                    {"name_ko": name_ko, "short_name_ko": short_name_ko},
                )
    return rows


def _iter_fixture_player_entries(
    *,
    fixture_players: list[dict[str, Any]],
    fixture_events: list[dict[str, Any]],
    fixture_lineups: list[dict[str, Any]],
) -> dict[int, tuple[dict[str, Any], int | None]]:
    entries: dict[int, tuple[dict[str, Any], int | None]] = {}

    def add_player(player: dict[str, Any] | None, team_external_id: int | None, statistics: list[Any] | None = None) -> None:
        if not isinstance(player, dict):
            return
        player_id = parse_int(player.get("id"))
        if player_id is None:
            return
        entry = {
            "player": {
                "id": player_id,
                "name": player.get("name") or f"Player {player_id}",
                "photo": player.get("photo"),
            },
            "statistics": statistics or [],
        }
        existing = entries.get(player_id)
        if existing is None or (not existing[0].get("statistics") and statistics):
            entries[player_id] = (entry, team_external_id)

    for team_block in fixture_players:
        if not isinstance(team_block, dict):
            continue
        team_external_id = parse_int((team_block.get("team") or {}).get("id"))
        for row in team_block.get("players") or []:
            if isinstance(row, dict):
                add_player(row.get("player"), team_external_id, row.get("statistics") or [])

    for lineup in fixture_lineups:
        if not isinstance(lineup, dict):
            continue
        team_external_id = parse_int((lineup.get("team") or {}).get("id"))
        for section in ("startXI", "substitutes"):
            for row in lineup.get(section) or []:
                if isinstance(row, dict):
                    add_player(row.get("player"), team_external_id)

    for event in fixture_events:
        if not isinstance(event, dict):
            continue
        team_external_id = parse_int((event.get("team") or {}).get("id"))
        add_player(event.get("player"), team_external_id)
        add_player(event.get("assist"), team_external_id)

    return entries


def _fixture_coach_external_ids(fixture_lineups: list[dict[str, Any]]) -> list[int]:
    coach_ids: set[int] = set()
    for lineup in fixture_lineups:
        if not isinstance(lineup, dict):
            continue
        coach_id = parse_int((lineup.get("coach") or {}).get("id"))
        if coach_id is not None:
            coach_ids.add(coach_id)
    return sorted(coach_ids)


def _fetch_player_profiles(
    *,
    external_ids: list[int],
    season_year: int | None,
    fallback_entries: dict[int, tuple[dict[str, Any], int | None]],
    result: FixturePlayerSyncResult,
) -> dict[int, dict[str, Any]]:
    if not external_ids or season_year is None:
        return {}

    settings = get_settings()
    client = ApiFootballClient(
        api_key=settings.api_football_key or "",
        host=settings.api_football_host,
        requests_per_minute=settings.api_football_requests_per_minute,
    )
    profiles: dict[int, dict[str, Any]] = {}
    try:
        for external_id in external_ids:
            try:
                rows = client.response("/players", id=external_id, season=season_year)
            except Exception:  # noqa: BLE001 - keep fixture sync moving; fallback row is still usable
                result.player_profiles_fetch_failed.append(external_id)
                continue
            if not rows:
                result.player_profiles_fetch_failed.append(external_id)
                continue
            profile = rows[0]
            fallback_entry = fallback_entries.get(external_id)
            if fallback_entry is not None:
                _entry, team_external_id = fallback_entry
                if team_external_id is not None:
                    profile = dict(profile)
                    profile["_fixture_team_external_id"] = team_external_id
            profiles[external_id] = profile
            result.player_profiles_fetched += 1
    finally:
        client.close()
    return profiles


_PLAYERS_BY_EXTERNAL_IDS = (
    text(
        """
        SELECT p.external_id
        FROM player p
        WHERE p.external_id IN :external_ids
        """
    ).bindparams(bindparam("external_ids", expanding=True))
)

_COACHES_BY_EXTERNAL_IDS = (
    text(
        """
        SELECT c.external_id
        FROM coach c
        WHERE c.external_id IN :external_ids
        """
    ).bindparams(bindparam("external_ids", expanding=True))
)

_MISSING_PLAYER_TRANSLATIONS = (
    text(
        """
        SELECT p.id AS player_id,
               p.external_id,
               p.name,
               p.nationality,
               pt.name_ko,
               pt.short_name_ko
        FROM player p
        JOIN player_translation pt ON pt.player_id = p.id
        WHERE p.external_id IN :external_ids
          AND (pt.name_ko IS NULL OR pt.short_name_ko IS NULL)
        ORDER BY p.external_id
        """
    ).bindparams(bindparam("external_ids", expanding=True))
)

_MISSING_COACH_TRANSLATIONS = (
    text(
        """
        SELECT c.id AS coach_id,
               c.external_id,
               c.name,
               ct.name_ko,
               ct.short_name_ko
        FROM coach c
        JOIN coach_translation ct ON ct.coach_id = c.id
        WHERE c.external_id IN :external_ids
          AND (ct.name_ko IS NULL OR ct.short_name_ko IS NULL)
        ORDER BY c.external_id
        """
    ).bindparams(bindparam("external_ids", expanding=True))
)

_UPDATE_PLAYER_TRANSLATION = text(
    """
    UPDATE player_translation
    SET name_ko = COALESCE(name_ko, :name_ko),
        short_name_ko = COALESCE(short_name_ko, :short_name_ko),
        updated_at = now()
    WHERE player_id = :player_id
    """
)

_UPDATE_COACH_TRANSLATION = text(
    """
    UPDATE coach_translation
    SET name_ko = COALESCE(name_ko, :name_ko),
        short_name_ko = COALESCE(short_name_ko, :short_name_ko),
        updated_at = now()
    WHERE coach_id = :coach_id
    """
)


def _existing_player_external_ids(session, external_ids: list[int]) -> set[int]:
    if not external_ids:
        return set()
    return {int(row[0]) for row in session.execute(_PLAYERS_BY_EXTERNAL_IDS, {"external_ids": external_ids})}


def _existing_coach_external_ids(session, external_ids: list[int]) -> set[int]:
    if not external_ids:
        return set()
    return {int(row[0]) for row in session.execute(_COACHES_BY_EXTERNAL_IDS, {"external_ids": external_ids})}


async def _translate_missing_with_openai(
    rows: list[dict[str, Any]],
    *,
    entity_type: str,
    id_key: str,
) -> dict[int, dict[str, str]]:
    if not rows:
        return {}
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:  # pragma: no cover - local dependency issue
        raise RuntimeError("openai package is required for untranslated fixture participants") from exc

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    translated: dict[int, dict[str, str]] = {}
    for row in rows:
        messages = prompt_module.build_prompt(
            entity_type=entity_type,
            name=row["name"] or "",
            context={"nationality": row.get("nationality") or ""} if entity_type == "player" else {},
        )
        parsed = await openai_client_module.call(messages, client=client)
        if parsed:
            translated[int(row[id_key])] = parsed
    return translated


def sync_fixture_players(fixture_external_id: int) -> FixturePlayerSyncResult:
    settings = get_settings()
    if not settings.api_football_key:
        raise RuntimeError("API_FOOTBALL_KEY is not configured")

    result = FixturePlayerSyncResult(fixture_external_id=fixture_external_id)
    counts = StoreCounts()
    client = ApiFootballClient(
        api_key=settings.api_football_key,
        host=settings.api_football_host,
        requests_per_minute=settings.api_football_requests_per_minute,
    )
    try:
        fixture_entries = client.response("/fixtures", id=fixture_external_id)
        if not fixture_entries:
            raise RuntimeError(f"API-Football returned no fixture id={fixture_external_id}")
        fixture_entry = fixture_entries[0]
        league_payload = fixture_entry.get("league") or {}
        league_external_id = parse_int(league_payload.get("id"))
        season_year = parse_int(league_payload.get("season"))
        if league_external_id is None:
            raise RuntimeError("fixture response missing league.id")

        league_entries = client.response("/leagues", id=league_external_id, season=season_year)
        if not league_entries:
            league_entries = client.response("/leagues", id=league_external_id)
        if not league_entries:
            raise RuntimeError(f"API-Football returned no league id={league_external_id}")

        events = client.response("/fixtures/events", fixture=fixture_external_id)
        statistics = client.response("/fixtures/statistics", fixture=fixture_external_id)
        lineups = client.response("/fixtures/lineups", fixture=fixture_external_id)
        players = client.response("/fixtures/players", fixture=fixture_external_id)
    finally:
        client.close()

    player_entries = _iter_fixture_player_entries(
        fixture_players=players,
        fixture_events=events,
        fixture_lineups=lineups,
    )
    result.api_player_ids = sorted(player_entries)
    result.api_coach_ids = _fixture_coach_external_ids(lineups)

    seed_translations = _load_seed_translations(Path("seeds"))
    with SessionLocal() as session:
        existing_before = _existing_player_external_ids(session, result.api_player_ids)
        result.db_players_missing_before = [
            external_id for external_id in result.api_player_ids if external_id not in existing_before
        ]
        fetched_player_profiles = _fetch_player_profiles(
            external_ids=result.db_players_missing_before,
            season_year=season_year,
            fallback_entries=player_entries,
            result=result,
        )
        existing_coaches_before = _existing_coach_external_ids(session, result.api_coach_ids)
        result.db_coaches_missing_before = [
            external_id for external_id in result.api_coach_ids if external_id not in existing_coaches_before
        ]

        upsert_league(session, league_entries[0], counts)
        upsert_fixture_entry(session, fixture_entry, counts)
        detail_ok = upsert_fixture_detail(
            session,
            fixture_external_id=fixture_external_id,
            events=events,
            statistics=statistics,
            lineups=lineups,
            players=players,
            counts=counts,
        )
        result.fixture_detail_upserted = detail_ok

        for player_id, (entry, team_external_id) in player_entries.items():
            fetched_entry = fetched_player_profiles.get(player_id)
            if fetched_entry is not None:
                entry = fetched_entry
                team_external_id = parse_int(fetched_entry.get("_fixture_team_external_id")) or team_external_id
            if team_external_id is None:
                continue
            if upsert_player_entry(
                session,
                entry,
                counts,
                current_team_external_id=team_external_id,
                set_current_team=True,
            ):
                result.players_upserted += 1
        session.commit()

        missing_translation_rows = [
            dict(row._mapping)
            for row in session.execute(
                _MISSING_PLAYER_TRANSLATIONS,
                {"external_ids": result.api_player_ids},
            )
        ]
        result.player_translations_missing_before = [int(row["external_id"]) for row in missing_translation_rows]

        missing_coach_translation_rows = [
            dict(row._mapping)
            for row in session.execute(
                _MISSING_COACH_TRANSLATIONS,
                {"external_ids": result.api_coach_ids},
            )
        ]
        result.coach_translations_missing_before = [
            int(row["external_id"]) for row in missing_coach_translation_rows
        ]

        openai_rows: list[dict[str, Any]] = []
        for row in missing_translation_rows:
            seed = seed_translations.get(int(row["external_id"]))
            if seed is None:
                openai_rows.append(row)
                continue
            session.execute(
                _UPDATE_PLAYER_TRANSLATION,
                {
                    "player_id": row["player_id"],
                    "name_ko": seed["name_ko"],
                    "short_name_ko": seed["short_name_ko"],
                },
            )
            result.player_translations_from_seed += 1
        session.commit()

        translated = asyncio.run(
            _translate_missing_with_openai(openai_rows, entity_type="player", id_key="player_id")
        )
        for player_id, parsed in translated.items():
            session.execute(
                _UPDATE_PLAYER_TRANSLATION,
                {
                    "player_id": player_id,
                    "name_ko": parsed["name_ko"],
                    "short_name_ko": parsed["short_name_ko"],
                },
            )
            result.player_translations_from_openai += 1
        coach_translated = asyncio.run(
            _translate_missing_with_openai(
                missing_coach_translation_rows,
                entity_type="coach",
                id_key="coach_id",
            )
        )
        for coach_id, parsed in coach_translated.items():
            session.execute(
                _UPDATE_COACH_TRANSLATION,
                {
                    "coach_id": coach_id,
                    "name_ko": parsed["name_ko"],
                    "short_name_ko": parsed["short_name_ko"],
                },
            )
            result.coach_translations_from_openai += 1
        session.commit()

        still_missing = [
            dict(row._mapping)
            for row in session.execute(
                _MISSING_PLAYER_TRANSLATIONS,
                {"external_ids": result.api_player_ids},
            )
        ]
        result.player_translations_still_missing = [int(row["external_id"]) for row in still_missing]
        coaches_still_missing = [
            dict(row._mapping)
            for row in session.execute(
                _MISSING_COACH_TRANSLATIONS,
                {"external_ids": result.api_coach_ids},
            )
        ]
        result.coach_translations_still_missing = [
            int(row["external_id"]) for row in coaches_still_missing
        ]
        result.counts = asdict(counts)

    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture_external_id", type=int)
    args = parser.parse_args()
    try:
        result = sync_fixture_players(args.fixture_external_id)
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
