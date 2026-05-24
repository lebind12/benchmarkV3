"""Broadcast-specific read helpers."""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.coach import Coach, CoachTranslation
from app.models.league import League, LeagueTranslation
from app.models.player import Player, PlayerTranslation
from app.models.team import Team, TeamTranslation


def _clean_ids(values: Iterable[int] | None, *, limit: int = 500) -> list[int]:
    if not values:
        return []

    cleaned: list[int] = []
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            continue
        if value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
        if len(cleaned) >= limit:
            break

    return cleaned


def _translation_row(name_ko: str | None, short_name_ko: str | None) -> dict[str, str | None]:
    return {
        "name_ko": name_ko,
        "short_name_ko": short_name_ko,
    }


def _clean_names(values: Iterable[str] | None, *, limit: int = 500) -> list[str]:
    if not values:
        return []

    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
        if len(cleaned) >= limit:
            break

    return cleaned


def lookup_broadcast_translations(
    session: Session,
    *,
    league_ids: Iterable[int] | None = None,
    league_names: Iterable[str] | None = None,
    team_ids: Iterable[int] | None = None,
    team_names: Iterable[str] | None = None,
    player_ids: Iterable[int] | None = None,
    player_names: Iterable[str] | None = None,
    coach_ids: Iterable[int] | None = None,
    coach_names: Iterable[str] | None = None,
) -> dict[str, dict[str, dict[str, str | None]]]:
    """Return Korean display names for API-Football external IDs."""
    payload: dict[str, dict[str, dict[str, str | None]]] = {
        "leagues": {},
        "league_names": {},
        "teams": {},
        "team_names": {},
        "players": {},
        "player_names": {},
        "coaches": {},
        "coach_names": {},
    }

    clean_league_ids = _clean_ids(league_ids)
    if clean_league_ids:
        rows = session.execute(
            select(
                League.external_id,
                LeagueTranslation.name_ko,
                LeagueTranslation.short_name_ko,
            )
            .join(LeagueTranslation, LeagueTranslation.league_id == League.id)
            .where(League.external_id.in_(clean_league_ids))
        )
        payload["leagues"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_league_names = _clean_names(league_names)
    if clean_league_names:
        rows = session.execute(
            select(
                func.lower(League.name).label("name_key"),
                LeagueTranslation.name_ko,
                LeagueTranslation.short_name_ko,
            )
            .join(LeagueTranslation, LeagueTranslation.league_id == League.id)
            .where(func.lower(League.name).in_(clean_league_names))
        )
        payload["league_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_team_ids = _clean_ids(team_ids)
    if clean_team_ids:
        rows = session.execute(
            select(
                Team.external_id,
                TeamTranslation.name_ko,
                TeamTranslation.short_name_ko,
            )
            .join(TeamTranslation, TeamTranslation.team_id == Team.id)
            .where(Team.external_id.in_(clean_team_ids))
        )
        payload["teams"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_team_names = _clean_names(team_names)
    if clean_team_names:
        rows = session.execute(
            select(
                func.lower(Team.name).label("name_key"),
                TeamTranslation.name_ko,
                TeamTranslation.short_name_ko,
            )
            .join(TeamTranslation, TeamTranslation.team_id == Team.id)
            .where(func.lower(Team.name).in_(clean_team_names))
        )
        payload["team_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_player_ids = _clean_ids(player_ids)
    if clean_player_ids:
        rows = session.execute(
            select(
                Player.external_id,
                PlayerTranslation.name_ko,
                PlayerTranslation.short_name_ko,
            )
            .join(PlayerTranslation, PlayerTranslation.player_id == Player.id)
            .where(Player.external_id.in_(clean_player_ids))
        )
        payload["players"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_player_names = _clean_names(player_names)
    if clean_player_names:
        rows = session.execute(
            select(
                func.lower(Player.name).label("name_key"),
                PlayerTranslation.name_ko,
                PlayerTranslation.short_name_ko,
            )
            .join(PlayerTranslation, PlayerTranslation.player_id == Player.id)
            .where(func.lower(Player.name).in_(clean_player_names))
        )
        payload["player_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    clean_coach_ids = _clean_ids(coach_ids)
    if clean_coach_ids:
        rows = session.execute(
            select(
                Coach.external_id,
                CoachTranslation.name_ko,
                CoachTranslation.short_name_ko,
            )
            .join(CoachTranslation, CoachTranslation.coach_id == Coach.id)
            .where(Coach.external_id.in_(clean_coach_ids))
        )
        payload["coaches"] = {
            str(row.external_id): _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
            if row.external_id is not None
        }

    clean_coach_names = _clean_names(coach_names)
    if clean_coach_names:
        rows = session.execute(
            select(
                func.lower(Coach.name).label("name_key"),
                CoachTranslation.name_ko,
                CoachTranslation.short_name_ko,
            )
            .join(CoachTranslation, CoachTranslation.coach_id == Coach.id)
            .where(func.lower(Coach.name).in_(clean_coach_names))
        )
        payload["coach_names"] = {
            row.name_key: _translation_row(row.name_ko, row.short_name_ko)
            for row in rows
        }

    return payload
