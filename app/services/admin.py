"""ADMIN services for API-Football league discovery and sync targets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.league import ApiFootballLeagueCatalog, League, LeagueSyncTarget, LeagueTranslation
from app.workers.daily_sync.api import ApiFootballClient
from app.workers.daily_sync.store import StoreCounts, upsert_league


@dataclass
class SyncTargetOptions:
    include_details: bool = True
    include_players: bool = True
    include_standings: bool = True
    fixture_limit: int | None = None
    is_active: bool = True


def _season_payload(season: dict[str, Any]) -> dict[str, Any]:
    coverage = season.get("coverage") if isinstance(season.get("coverage"), dict) else {}
    fixtures = coverage.get("fixtures") if isinstance(coverage.get("fixtures"), dict) else {}
    return {
        "year": season.get("year"),
        "start": season.get("start"),
        "end": season.get("end"),
        "current": bool(season.get("current")),
        "coverage": {
            "fixtures": bool(fixtures.get("events") or fixtures.get("lineups") or fixtures.get("statistics")),
            "standings": bool(coverage.get("standings")),
            "players": bool(coverage.get("players")),
            "top_scorers": bool(coverage.get("top_scorers")),
            "injuries": bool(coverage.get("injuries")),
        },
    }


def _api_league_payload(entry: dict[str, Any]) -> dict[str, Any]:
    league = entry.get("league") or {}
    country = entry.get("country") or {}
    seasons = [
        _season_payload(season)
        for season in (entry.get("seasons") or [])
        if isinstance(season, dict) and season.get("year")
    ]
    seasons.sort(key=lambda item: int(item["year"]), reverse=True)
    return {
        "external_id": league.get("id"),
        "name": league.get("name"),
        "type": league.get("type"),
        "logo_url": league.get("logo"),
        "country": {
            "name": country.get("name"),
            "code": country.get("code"),
            "flag": country.get("flag"),
        },
        "seasons": seasons,
    }


def _current_season_from_payload(seasons: list[dict[str, Any]]) -> int | None:
    for season in seasons:
        if season.get("current") and season.get("year"):
            return int(season["year"])
    if seasons:
        return int(seasons[0]["year"])
    return None


def _catalog_payload(row: ApiFootballLeagueCatalog) -> dict[str, Any]:
    seasons = list(row.seasons or [])
    seasons.sort(key=lambda item: int(item["year"]), reverse=True)
    return {
        "external_id": row.external_id,
        "name": row.name,
        "type": row.type,
        "logo_url": row.logo_url,
        "country": {
            "name": row.country_name,
            "code": row.country_code,
            "flag": row.country_flag,
        },
        "seasons": seasons,
        "current_season": row.current_season,
        "last_synced_at": row.last_synced_at,
    }


def _catalog_to_api_entry(row: ApiFootballLeagueCatalog) -> dict[str, Any]:
    return {
        "league": {
            "id": row.external_id,
            "name": row.name,
            "type": row.type,
            "logo": row.logo_url,
        },
        "country": {
            "name": row.country_name,
            "code": row.country_code,
            "flag": row.country_flag,
        },
        "seasons": list(row.seasons or []),
    }


def search_api_football_leagues(
    session: Session,
    *,
    search: str | None = None,
    external_id: int | None = None,
    country: str | None = None,
) -> list[dict[str, Any]]:
    query = select(ApiFootballLeagueCatalog)
    if external_id is not None:
        query = query.where(ApiFootballLeagueCatalog.external_id == external_id)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(ApiFootballLeagueCatalog.name.ilike(pattern))
    if country:
        country_pattern = f"%{country.strip()}%"
        query = query.where(
            or_(
                ApiFootballLeagueCatalog.country_name.ilike(country_pattern),
                ApiFootballLeagueCatalog.country_code.ilike(country_pattern),
            )
        )
    query = query.order_by(ApiFootballLeagueCatalog.name.asc()).limit(100)
    return [_catalog_payload(row) for row in session.execute(query).scalars()]


def _raw_api_football_leagues(
    *,
    search: str | None = None,
    external_id: int | None = None,
    country: str | None = None,
    current: bool | None = None,
) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.api_football_key:
        raise RuntimeError("API_FOOTBALL_KEY is required")
    params: dict[str, Any] = {}
    if external_id is not None:
        params["id"] = external_id
    if search:
        params["search"] = search
    if country:
        params["country"] = country
    if current is not None:
        params["current"] = "true" if current else "false"
    elif not params:
        # No params intentionally means "full catalog" for manual sync.
        pass

    client = ApiFootballClient(
        api_key=settings.api_football_key,
        host=settings.api_football_host,
        requests_per_minute=settings.api_football_requests_per_minute,
    )
    try:
        return client.response("/leagues", **params)
    finally:
        client.close()


def sync_api_football_league_catalog(
    session: Session,
    *,
    search: str | None = None,
    external_id: int | None = None,
    country: str | None = None,
    current: bool | None = None,
) -> dict[str, Any]:
    raw_entries = _raw_api_football_leagues(
        search=search,
        external_id=external_id,
        country=country,
        current=current,
    )
    values: list[dict[str, Any]] = []
    for entry in raw_entries:
        payload = _api_league_payload(entry)
        external_id_value = payload.get("external_id")
        name = payload.get("name")
        if external_id_value is None or not name:
            continue
        league_type = payload.get("type") or "League"
        if league_type not in {"League", "Cup"}:
            league_type = "Cup"
        seasons = payload["seasons"]
        country_payload = payload["country"]
        values.append(
            {
                "external_id": int(external_id_value),
                "name": name,
                "type": league_type,
                "logo_url": payload.get("logo_url"),
                "country_name": country_payload.get("name"),
                "country_code": country_payload.get("code"),
                "country_flag": country_payload.get("flag"),
                "current_season": _current_season_from_payload(seasons),
                "seasons": seasons,
            }
        )
    if values:
        statement = insert(ApiFootballLeagueCatalog).values(values)
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            index_elements=[ApiFootballLeagueCatalog.external_id],
            set_={
                "name": excluded.name,
                "type": excluded.type,
                "logo_url": excluded.logo_url,
                "country_name": excluded.country_name,
                "country_code": excluded.country_code,
                "country_flag": excluded.country_flag,
                "current_season": excluded.current_season,
                "seasons": excluded.seasons,
                "last_synced_at": func.now(),
                "updated_at": func.now(),
            },
        )
        session.execute(statement)
    session.commit()
    total = session.execute(select(func.count()).select_from(ApiFootballLeagueCatalog)).scalar_one()
    return {
        "api_count": len(raw_entries),
        "synced_count": len(values),
        "catalog_count": total,
    }


def _league_ref(league: League, translation: LeagueTranslation | None = None) -> dict[str, Any]:
    return {
        "external_id": league.external_id,
        "slug": league.slug,
        "name": league.name,
        "name_ko": translation.name_ko if translation else None,
        "short_name_ko": translation.short_name_ko if translation else None,
        "type": league.type,
        "logo_url": league.logo_url,
        "country_name": league.country_name,
        "current_season": league.current_season,
    }


def list_sync_targets(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(
        select(LeagueSyncTarget, League, LeagueTranslation)
        .join(League, League.id == LeagueSyncTarget.league_id)
        .outerjoin(LeagueTranslation, LeagueTranslation.league_id == League.id)
        .order_by(LeagueSyncTarget.is_active.desc(), League.external_id, LeagueSyncTarget.season_year.desc())
    ).all()
    return [
        {
            "id": target.id,
            "league": _league_ref(league, translation),
            "season_year": target.season_year,
            "is_active": target.is_active,
            "include_details": target.include_details,
            "include_players": target.include_players,
            "include_standings": target.include_standings,
            "fixture_limit": target.fixture_limit,
            "created_at": target.created_at,
            "updated_at": target.updated_at,
        }
        for target, league, translation in rows
    ]


def upsert_sync_target(
    session: Session,
    *,
    league_external_id: int,
    season_year: int,
    options: SyncTargetOptions,
) -> dict[str, Any]:
    catalog = session.execute(
        select(ApiFootballLeagueCatalog).where(ApiFootballLeagueCatalog.external_id == league_external_id)
    ).scalar_one_or_none()
    if catalog is None:
        raise ValueError("api_football_catalog_not_synced")
    season_years = {
        int(season["year"])
        for season in (catalog.seasons or [])
        if isinstance(season, dict) and season.get("year")
    }
    if season_year not in season_years:
        raise ValueError("api_football_season_not_found")

    counts = StoreCounts()
    league_id, _ = upsert_league(session, _catalog_to_api_entry(catalog), counts)
    target = session.execute(
        select(LeagueSyncTarget).where(
            LeagueSyncTarget.league_id == league_id,
            LeagueSyncTarget.season_year == season_year,
        )
    ).scalar_one_or_none()
    if target is None:
        target = LeagueSyncTarget(league_id=league_id, season_year=season_year)
        session.add(target)

    target.is_active = options.is_active
    target.include_details = options.include_details
    target.include_players = options.include_players
    target.include_standings = options.include_standings
    target.fixture_limit = options.fixture_limit
    session.commit()
    session.refresh(target)
    return get_sync_target(session, target.id)


def _raw_api_football_league(league_external_id: int) -> list[dict[str, Any]]:
    return _raw_api_football_leagues(external_id=league_external_id)


def get_sync_target(session: Session, target_id: int) -> dict[str, Any]:
    row = session.execute(
        select(LeagueSyncTarget, League, LeagueTranslation)
        .join(League, League.id == LeagueSyncTarget.league_id)
        .outerjoin(LeagueTranslation, LeagueTranslation.league_id == League.id)
        .where(LeagueSyncTarget.id == target_id)
    ).first()
    if row is None:
        raise ValueError("sync_target_not_found")
    target, league, translation = row
    return {
        "id": target.id,
        "league": _league_ref(league, translation),
        "season_year": target.season_year,
        "is_active": target.is_active,
        "include_details": target.include_details,
        "include_players": target.include_players,
        "include_standings": target.include_standings,
        "fixture_limit": target.fixture_limit,
        "created_at": target.created_at,
        "updated_at": target.updated_at,
    }


def update_sync_target(
    session: Session,
    target_id: int,
    *,
    changes: dict[str, Any],
) -> dict[str, Any]:
    target = session.get(LeagueSyncTarget, target_id)
    if target is None:
        raise ValueError("sync_target_not_found")
    for key, value in changes.items():
        if value is not None:
            setattr(target, key, value)
    session.commit()
    session.refresh(target)
    return get_sync_target(session, target.id)


def delete_sync_target(session: Session, target_id: int) -> None:
    target = session.get(LeagueSyncTarget, target_id)
    if target is None:
        raise ValueError("sync_target_not_found")
    session.delete(target)
    session.commit()
