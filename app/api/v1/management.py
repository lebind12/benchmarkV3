"""API contract driven by the evaluated four-tab management frontend."""

from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app import db
from app.core.sessions import manager_user
from app.models import AppUser, ApiFootballLeagueCatalog
from app.services import admin, management as service, management_runs as runs

router = APIRouter(
    prefix="/api/v1/admin/management", tags=["management"], dependencies=[Depends(manager_user)]
)
Db = Annotated[Session, Depends(db.get_db_session)]
Manager = Annotated[AppUser, Depends(manager_user)]


class TargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    league_id: int = Field(ge=1)
    season: int = Field(ge=1900)
    is_active: bool = True
    include_details: bool = True
    include_players: bool = True
    include_standings: bool = True
    fixture_limit: int | None = Field(default=None, ge=1)


class TargetPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_active: bool | None = None
    include_details: bool | None = None
    include_players: bool | None = None
    include_standings: bool | None = None
    fixture_limit: int | None = Field(default=None, ge=1)
    # Existing evaluated editor submits these immutable identity values.
    league_id: int | None = Field(default=None, ge=1)
    season: int | None = Field(default=None, ge=1900)

    @model_validator(mode="after")
    def nonnull_flags(self):
        if any(
            getattr(self, key) is None for key in self.model_fields_set if key != "fixture_limit"
        ):
            raise ValueError("fixture_limit 외의 설정에는 null을 사용할 수 없습니다.")
        return self


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_ids: list[int] = Field(min_length=1, max_length=20)
    mode: Literal["initial", "refresh"]
    parent_run_id: str | None = None


class TranslationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_ko: str | None = Field(max_length=80)
    short_name_ko: str | None = Field(max_length=40)
    expected_version: int = Field(ge=0)


def call(action):
    try:
        return action()
    except service.ManagementError as exc:
        return JSONResponse(
            {"message": str(exc), "code": exc.code, "current": exc.current}, status_code=exc.status
        )


@router.get("/catalog")
def catalog(
    session: Db,
    query: str = Query(default="", max_length=120),
    id: int | None = Query(default=None, ge=1),
    country: str = Query(default="", max_length=100),
    type: Literal["", "League", "Cup"] = "",
    group: Literal["", "national", "asia", "club"] = "",
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=100, ge=1, le=100),
):
    return service.catalog_list(
        session, query, id, country=country, kind=type, group=group, page=page, page_size=page_size
    )


@router.post("/catalog/refresh")
def refresh_catalog(session: Db):
    try:
        result = admin.sync_api_football_league_catalog(session)
        result["updated_at"] = service.iso(
            session.scalar(select(func.max(ApiFootballLeagueCatalog.last_synced_at)))
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(
            409 if str(exc) == "catalog_sync_running" else 502,
            "카탈로그 최신화가 이미 진행 중입니다."
            if str(exc) == "catalog_sync_running"
            else "카탈로그 최신화에 실패했습니다. 기존 자료는 유지됩니다.",
        ) from exc


@router.get("/targets")
def targets(session: Db, request: Request):
    result = service.targets_list(session)
    scheduler = getattr(request.app.state, "worker_scheduler", None)
    result["scheduler_enabled"] = bool(scheduler and scheduler.running)
    return result


@router.post("/targets", status_code=201)
def create_target(payload: TargetCreate, session: Db):
    return call(lambda: service.save_target(session, payload.model_dump()))


@router.patch("/targets/{target_id}")
def patch_target(target_id: int, payload: TargetPatch, session: Db):
    return call(
        lambda: service.save_target(session, payload.model_dump(exclude_unset=True), target_id)
    )


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, session: Db):
    return call(lambda: service.remove_target(session, target_id))


@router.get("/runs")
def list_runs(session: Db):
    return runs.run_list(session)


@router.get("/runs/{run_id}")
def get_run(run_id: str, session: Db):
    return call(lambda: runs.get_run(session, run_id))


@router.post("/runs")
def create_run(payload: RunCreate, session: Db, user: Manager):
    return call(
        lambda: runs.start_run(
            session, payload.target_ids, payload.mode, user, payload.parent_run_id
        )
    )


@router.post("/runs/{run_id}/cancel")
def cancel(run_id: str, session: Db):
    return call(lambda: runs.cancel_run(session, run_id))


@router.get("/translations/affiliation-filters")
def translation_affiliation_filters(
    session: Db,
    type: Literal["player", "coach"] = "player",
    league_id: int | None = Query(default=None, ge=1),
):
    return call(lambda: service.translation_affiliation_filters(session, type, league_id))


@router.get("/translations")
def translations(
    session: Db,
    query: str = Query(default="", max_length=120),
    type: Literal["all", "league", "team", "player", "coach"] = "all",
    status: Literal["all", "translated", "untranslated"] = "all",
    page: int = Query(default=1, ge=1, le=10000),
    league_id: int | None = Query(default=None, ge=1),
    team_id: int | None = Query(default=None, ge=1),
):
    return call(
        lambda: service.translations_list(
            session,
            query=query,
            kind=type,
            status=status,
            page=page,
            league_id=league_id,
            team_id=team_id,
        )
    )


@router.patch("/translations/{kind}/{entity_id}")
def edit_translation(
    kind: str, entity_id: int, payload: TranslationPatch, session: Db, user: Manager
):
    return call(
        lambda: service.edit_translation(session, kind, entity_id, payload.model_dump(), user)
    )


@router.get("/translations/{kind}/{entity_id}/history")
def history(kind: str, entity_id: int, session: Db):
    return call(lambda: service.translation_history(session, kind, entity_id))
