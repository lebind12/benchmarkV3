"""Fixture-detail API routes."""
from __future__ import annotations

from types import ModuleType
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import db
from app.services import fixture_detail as service_module


router = APIRouter(prefix="/api/v1/fixtures", tags=["fixture-detail"])


def get_fixture_detail_service():
    return service_module


DbSession = Annotated[Session, Depends(db.get_db_session)]
FixtureDetailService = Annotated[object, Depends(get_fixture_detail_service)]


def _is_default_service(service: object) -> bool:
    return isinstance(service, ModuleType)


def _missing() -> HTTPException:
    return HTTPException(status_code=404, detail="fixture_not_found")


@router.get("/{external_id}")
def match_detail(external_id: int, session: DbSession, service: FixtureDetailService):
    try:
        if _is_default_service(service):
            return service.get_match_detail(session, external_id)
        payload = service.get_match_detail(external_id)
        if payload is None:
            raise _missing()
        return payload
    except service_module.FixtureNotFoundError as exc:
        raise _missing() from exc


@router.get("/{external_id}/events")
def fixture_events(external_id: int, session: DbSession, service: FixtureDetailService):
    try:
        if _is_default_service(service):
            return service.get_fixture_events(session, external_id)
        payload = service.get_fixture_events(external_id)
        if payload is None:
            raise _missing()
        return payload
    except service_module.FixtureNotFoundError as exc:
        raise _missing() from exc


@router.get("/{external_id}/lineups")
def fixture_lineups(external_id: int, session: DbSession, service: FixtureDetailService):
    try:
        if _is_default_service(service):
            return service.get_fixture_lineups(session, external_id)
        payload = service.get_fixture_lineups(external_id)
        if payload is None:
            raise _missing()
        return payload
    except service_module.FixtureNotFoundError as exc:
        raise _missing() from exc
