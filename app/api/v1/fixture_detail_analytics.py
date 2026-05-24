"""Fixture-detail analytical endpoints."""
from __future__ import annotations

from types import ModuleType
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import db
from app.services import fixture_detail as service_module


FixtureNotFoundError = service_module.FixtureNotFoundError

router = APIRouter(prefix="/api/v1/fixtures", tags=["fixture-detail"])


def get_session():
    yield from db.get_db_session()


def get_fixture_detail_analytics_service():
    return service_module


DbSession = Annotated[Session, Depends(get_session)]
AnalyticsService = Annotated[object, Depends(get_fixture_detail_analytics_service)]


def _is_default_service(service: object) -> bool:
    return isinstance(service, ModuleType)


def _not_found(external_id: int) -> HTTPException:
    return HTTPException(status_code=404, detail=f"fixture_not_found:{external_id}")


@router.get("/{external_id}/statistics")
def fixture_statistics(external_id: int, session: DbSession, service: AnalyticsService):
    try:
        if _is_default_service(service):
            return service.get_statistics(session, external_id)
        return service.get_statistics(external_id)
    except FixtureNotFoundError as exc:
        raise _not_found(external_id) from exc


@router.get("/{external_id}/h2h")
def fixture_h2h(
    external_id: int,
    session: DbSession,
    service: AnalyticsService,
    limit: int = Query(default=5, ge=1, le=10),
):
    try:
        if _is_default_service(service):
            return service.get_h2h(session, external_id, limit=limit)
        return service.get_h2h(external_id, limit=limit)
    except FixtureNotFoundError as exc:
        raise _not_found(external_id) from exc


@router.get("/{external_id}/league-standings")
def fixture_league_standings(external_id: int, session: DbSession, service: AnalyticsService):
    try:
        if _is_default_service(service):
            return service.get_league_standings(session, external_id)
        return service.get_league_standings(external_id)
    except FixtureNotFoundError as exc:
        raise _not_found(external_id) from exc
