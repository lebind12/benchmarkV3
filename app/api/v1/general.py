"""General site API routes backed by persisted DB data."""
from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import db
from app.services import general as general_service
from app.services.home import ALLOWED_LEAGUE_IDS


router = APIRouter(prefix="/api/v1", tags=["general"])


DbSession = Annotated[Session, Depends(db.get_db_session)]


def _validate_league(league_id: int | None) -> None:
    if league_id is not None and league_id not in ALLOWED_LEAGUE_IDS:
        raise HTTPException(status_code=422, detail="unsupported league_id")


@router.get("/leagues")
def leagues(session: DbSession):
    return general_service.list_leagues(session)


@router.get("/fixtures")
def fixtures(
    session: DbSession,
    league_id: int | None = Query(default=None),
    period: Literal["day", "week", "month"] = "week",
    date_: date | None = Query(default=None, alias="date"),
    team_slug: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
):
    _validate_league(league_id)
    return general_service.list_fixtures(
        session,
        league_id=league_id,
        period=period,
        date=date_,
        team_slug=team_slug,
        limit=limit,
    )


@router.get("/standings")
def standings(
    session: DbSession,
    league_id: int = Query(default=39),
):
    _validate_league(league_id)
    return general_service.get_standings(session, league_id=league_id)


@router.get("/teams")
def teams(
    session: DbSession,
    league_id: int | None = Query(default=None),
    query: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=300),
):
    _validate_league(league_id)
    return general_service.list_teams(session, league_id=league_id, query=query, limit=limit)


@router.get("/teams/{slug}")
def team_detail(slug: str, session: DbSession):
    payload = general_service.get_team(session, slug=slug)
    if payload is None:
        raise HTTPException(status_code=404, detail="team_not_found")
    return payload


@router.get("/players")
def players(
    session: DbSession,
    league_id: int | None = Query(default=None),
    query: str | None = Query(default=None),
    metric: Literal["goals", "assists", "yellow_cards", "red_cards"] = "goals",
    limit: int = Query(default=100, ge=1, le=300),
):
    _validate_league(league_id)
    return general_service.list_players(
        session,
        league_id=league_id,
        query=query,
        metric=metric,
        limit=limit,
    )


@router.get("/players/{slug}")
def player_detail(slug: str, session: DbSession):
    payload = general_service.get_player(session, slug=slug)
    if payload is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    return payload


@router.get("/coaches")
def coaches(
    session: DbSession,
    league_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
):
    _validate_league(league_id)
    return general_service.list_coaches(session, league_id=league_id, limit=limit)


@router.get("/stats")
def stats(
    session: DbSession,
    league_id: int = Query(default=39),
):
    _validate_league(league_id)
    return general_service.get_stats(session, league_id=league_id)


@router.get("/news")
def news(session: DbSession, limit: int = Query(default=30, ge=1, le=100)):
    return general_service.list_news(session, limit=limit)
