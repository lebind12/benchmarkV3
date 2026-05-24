"""ADMIN API for API-Football discovery and daily-sync targets."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import db
from app.services import admin as admin_service
from app.services import sync_logs
from app.services import worker_runs
from app.workers.daily_sync.runner import (
    load_configured_sync_specs,
)


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

DbSession = Annotated[Session, Depends(db.get_db_session)]


class SyncTargetCreate(BaseModel):
    league_external_id: int = Field(ge=1)
    season_year: int = Field(ge=1900)
    is_active: bool = True
    include_details: bool = True
    include_players: bool = True
    include_standings: bool = True
    fixture_limit: int | None = Field(default=None, ge=1)


class SyncTargetUpdate(BaseModel):
    is_active: bool | None = None
    include_details: bool | None = None
    include_players: bool | None = None
    include_standings: bool | None = None
    fixture_limit: int | None = Field(default=None, ge=1)


class DailySyncRunRequest(BaseModel):
    fallback_defaults: bool = False
    skip_details: bool = False
    skip_players: bool = False
    skip_standings: bool = False
    fixture_limit: int | None = Field(default=None, ge=1)
    fail_on_errors: bool = False


class ApiFootballCatalogSyncRequest(BaseModel):
    search: str | None = Field(default=None, min_length=2)
    id: int | None = Field(default=None, ge=1)  # noqa: A003 - public field follows API-Football
    country: str | None = Field(default=None, min_length=2)
    current: bool | None = None


@router.get("/api-football/leagues")
def api_football_leagues(
    session: DbSession,
    search: str | None = Query(default=None, min_length=2),
    id: int | None = Query(default=None, ge=1),  # noqa: A002 - public query name follows API-Football
    country: str | None = Query(default=None, min_length=2),
):
    return {
        "items": admin_service.search_api_football_leagues(
            session,
            search=search,
            external_id=id,
            country=country,
        )
    }


@router.post("/api-football/leagues/sync")
def sync_api_football_catalog(payload: ApiFootballCatalogSyncRequest, session: DbSession):
    try:
        return admin_service.sync_api_football_league_catalog(
            session,
            search=payload.search,
            external_id=payload.id,
            country=payload.country,
            current=payload.current,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sync-targets")
def sync_targets(session: DbSession):
    return {"items": admin_service.list_sync_targets(session)}


@router.get("/sync-targets/plan")
def sync_target_plan(session: DbSession, fallback_defaults: bool = Query(default=False)):
    specs = load_configured_sync_specs(fallback_defaults=fallback_defaults)
    return {"specs": [spec.to_log_payload() for spec in specs]}


@router.post("/sync-targets", status_code=201)
def create_sync_target(payload: SyncTargetCreate, session: DbSession):
    try:
        target = admin_service.upsert_sync_target(
            session,
            league_external_id=payload.league_external_id,
            season_year=payload.season_year,
            options=admin_service.SyncTargetOptions(
                include_details=payload.include_details,
                include_players=payload.include_players,
                include_standings=payload.include_standings,
                fixture_limit=payload.fixture_limit,
                is_active=payload.is_active,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return target


@router.patch("/sync-targets/{target_id}")
def patch_sync_target(target_id: int, payload: SyncTargetUpdate, session: DbSession):
    changes = payload.model_dump(exclude_unset=True)
    try:
        return admin_service.update_sync_target(session, target_id, changes=changes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/sync-targets/{target_id}", status_code=204)
def remove_sync_target(target_id: int, session: DbSession):
    try:
        admin_service.delete_sync_target(session, target_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/daily-sync/run")
def run_daily_sync(payload: DailySyncRunRequest):
    try:
        return worker_runs.start_daily_sync_run(
            fallback_defaults=payload.fallback_defaults,
            include_details=not payload.skip_details,
            include_players=not payload.skip_players,
            include_standings=not payload.skip_standings,
            fixture_limit=payload.fixture_limit,
            fail_on_errors=payload.fail_on_errors,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail={"message": "daily_sync_already_running", "run_id": str(exc)},
        ) from exc


@router.get("/daily-sync/runs/{run_id}")
def daily_sync_run(run_id: str):
    try:
        return worker_runs.get_worker_run(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/daily-sync/logs")
def daily_sync_logs(session: DbSession, limit: int = Query(default=50, ge=1, le=100)):
    return {"items": sync_logs.list_worker_sync_logs(session, worker_name="daily-sync", limit=limit)}
