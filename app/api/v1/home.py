"""Home screen API routes."""
from __future__ import annotations

from datetime import date
from types import ModuleType
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import db
from app.services import home as home_service
from app.services.home import ALLOWED_LEAGUE_IDS


router = APIRouter(tags=["home"])


def get_home_service():
    return home_service


DbSession = Annotated[Session, Depends(db.get_db_session)]
HomeService = Annotated[object, Depends(get_home_service)]


def _validate_home_league(league_id: int | None) -> None:
    if league_id is not None and league_id not in ALLOWED_LEAGUE_IDS:
        raise HTTPException(status_code=422, detail="unsupported league_id")


def _is_default_service(service: object) -> bool:
    return isinstance(service, ModuleType)


@router.get("/news")
def news(session: DbSession, service: HomeService):
    if _is_default_service(service):
        return service.list_home_news(session)
    return service.list_home_news()


@router.get("/hot-players")
def hot_players(session: DbSession, service: HomeService):
    if _is_default_service(service):
        return service.list_home_hot_players(session)
    return service.list_home_hot_players()


@router.get("/transfers")
def transfers(session: DbSession, service: HomeService):
    if _is_default_service(service):
        return service.list_home_transfers(session)
    return service.list_home_transfers()


@router.get("/injuries")
def injuries(session: DbSession, service: HomeService):
    if _is_default_service(service):
        return service.list_home_injuries(session)
    return service.list_home_injuries()


@router.get("/fixtures")
def fixtures(
    session: DbSession,
    service: HomeService,
    league_id: int | None = Query(default=None),
    period: Literal["day", "week", "month"] = "day",
    date_: date | None = Query(default=None, alias="date"),
):
    _validate_home_league(league_id)
    if _is_default_service(service):
        return service.list_home_fixtures(
            session,
            league_id=league_id,
            period=period,
            date=date_,
        )
    return service.list_fixtures(league_id=league_id, period=period, date=date_)


@router.get("/standings")
def standings(
    session: DbSession,
    service: HomeService,
    league_id: int = Query(default=39),
):
    _validate_home_league(league_id)
    if _is_default_service(service):
        return service.get_home_standings(session, league_id=league_id)
    return service.get_standings(league_id=league_id)


@router.get("/top-players")
def top_players(
    session: DbSession,
    service: HomeService,
    league_id: int = Query(default=39),
    metric: Literal["goals", "assists", "yellow_cards", "red_cards"] = "goals",
):
    if _is_default_service(service):
        return service.list_home_top_players(session, league_id=league_id, metric=metric)
    return service.list_home_top_players(league_id=league_id, metric=metric)
