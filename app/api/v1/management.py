"""API contract driven by the evaluated four-tab management frontend."""

from datetime import datetime
from typing import Annotated, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app import db
from app.core.sessions import current_user, manager_user
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


class PreviewTestRunCreate(BaseModel):
    """기간 지정 프리뷰 시험 요청.

    경계 검증만 여기서 한다. 통과한 값은 불변 범위 값으로 바꿔 안쪽에 넘긴다.
    """

    model_config = ConfigDict(extra="forbid")
    target_ids: list[int] = Field(min_length=1, max_length=20)
    # 양 끝을 포함하는 수집 기간. 시간대가 없으면 거부한다.
    fixture_from: datetime
    fixture_to: datetime
    # 외부 경기 ID 정확히 두 개(중복 불가).
    preview_fixture_ids: list[int] = Field(min_length=2, max_length=2)
    # 수집이 끝난 뒤 프리뷰 생성을 시작할지. **기본값은 기존 동작(생성함)** 이며,
    # 이 필드를 보내지 않는 기존 호출부의 의미는 바뀌지 않는다.
    #
    # `false`는 수집만 실행하는 요청이다. 그래도 자동 생성은 실제 모델을 부르므로
    # **ADMIN만** 받는다(라우터 기본 의존성은 STREAMER도 통과시킨다).
    generate_after_collection: bool = True

    @model_validator(mode="after")
    def valid_scope(self):
        if self.fixture_from.tzinfo is None or self.fixture_to.tzinfo is None:
            raise ValueError("fixture_from/fixture_to에는 시간대가 필요합니다.")
        if self.fixture_from > self.fixture_to:
            raise ValueError("fixture_from은 fixture_to보다 늦을 수 없습니다.")
        if len(set(self.target_ids)) != len(self.target_ids):
            raise ValueError("target_ids에 중복 값이 있습니다.")
        if len(set(self.preview_fixture_ids)) != 2:
            raise ValueError("preview_fixture_ids는 서로 다른 두 경기여야 합니다.")
        if any(value <= 0 for value in self.preview_fixture_ids):
            raise ValueError("preview_fixture_ids는 양의 외부 경기 ID여야 합니다.")
        return self


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


def require_admin(user: AppUser = Depends(current_user)) -> AppUser:
    """이 시험 경로 전용 ADMIN 검사.

    라우터의 `manager_user`는 STREAMER도 통과시킨다. 수집 시험은 실제 공급자 호출과
    public 자료 갱신을 일으키므로 **ADMIN만** 받는다. 기존 일반 관리 API의 STREAMER
    정책은 이 의존성을 쓰지 않으므로 그대로다.
    """
    if user.role != "ADMIN":
        raise HTTPException(403, "이 시험 기능은 관리자 권한이 필요합니다.")
    return user


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


@router.post("/runs/preview-test")
def create_preview_test_run(payload: PreviewTestRunCreate, session: Db, user: Manager):
    """기간을 지정해 수집하고, 종료 뒤 지정 두 경기의 프리뷰를 생성하는 시험 실행.

    기존 관리 인증·실행/취소/조회 구조를 그대로 쓴다. `mode`는 refresh로 고정이며
    정기 6시간 정책은 이 요청 범위 밖에서 바뀌지 않는다.

    `generate_after_collection=false`(수집만 실행)는 자동 생성을 끄는 값이므로
    **ADMIN**을 추가로 요구한다. 기본값 `true`의 권한 계약은 기존 그대로다.
    """
    if payload.generate_after_collection is False and user.role != "ADMIN":
        raise HTTPException(403, "수집만 실행은 관리자 권한이 필요합니다.")
    return call(
        lambda: runs.start_preview_test_run(
            session,
            target_ids=payload.target_ids,
            fixture_from=payload.fixture_from,
            fixture_to=payload.fixture_to,
            preview_fixture_ids=payload.preview_fixture_ids,
            generate_after_collection=payload.generate_after_collection,
            user=user,
        )
    )


class PreviewTestCollectionRunCreate(BaseModel):
    """수집만 실행하는 시험 요청(새 전용 POST).

    `generate_after_collection`을 받지 않는다. 이 경로는 **수집만** 하며, 생성은
    사용자가 화면에서 명시적으로 시작한다. 필드 이름·의미를 두 경로에서 다르게
    만들지 않으려고 요청 모델을 분리했다.
    """

    model_config = ConfigDict(extra="forbid")
    fixture_ids: list[int] = Field(min_length=2, max_length=2)
    fixture_from: datetime
    fixture_to: datetime

    @model_validator(mode="after")
    def valid_scope(self):
        if self.fixture_from.tzinfo is None or self.fixture_to.tzinfo is None:
            raise ValueError("fixture_from/fixture_to에는 시간대가 필요합니다.")
        if self.fixture_from > self.fixture_to:
            raise ValueError("fixture_from은 fixture_to보다 늦을 수 없습니다.")
        if len(set(self.fixture_ids)) != 2:
            raise ValueError("fixture_ids는 서로 다른 두 경기여야 합니다.")
        if any(value <= 0 for value in self.fixture_ids):
            raise ValueError("fixture_ids는 양의 외부 경기 ID여야 합니다.")
        return self


def _preview_test_plan(session, fixture_ids):
    from app.services import preview_test

    return preview_test.build_plan(session, fixture_ids)


@router.get("/preview-test/candidates")
def preview_test_candidates(session: Db, user: Annotated[AppUser, Depends(require_admin)]):
    """기간 수집 시험의 후보 경기. **읽기만** 하며 모델·공급자를 호출하지 않는다."""
    from app.services import preview_test

    return preview_test.candidates(session)


@router.get("/preview-test/plan")
def preview_test_plan(
    session: Db,
    user: Annotated[AppUser, Depends(require_admin)],
    fixture_ids: Annotated[list[int], Query()] = (),
):
    """선택한 두 경기의 수집 기간·활성 대상을 해석한다(쓰기 없음).

    `fixture_ids`는 반복 query다(`?fixture_ids=1&fixture_ids=2`). 정확히 두 개가
    아니면 422이며, 개수는 서비스가 판정한다.
    """
    return call(lambda: _preview_test_plan(session, list(fixture_ids)))


@router.post("/preview-test/runs")
def create_preview_test_collection_run(
    payload: PreviewTestCollectionRunCreate,
    session: Db,
    user: Annotated[AppUser, Depends(require_admin)],
):
    """**수집만** 실행한다(ADMIN 전용). 생성은 이 요청에서 시작하지 않는다.

    대상 재검증은 기존 `start_preview_test_run`이 한다(경계 검증 단일 지점). 기존
    수집 잠금이 중복 실행을 409로 거부하며, 응답은 기존 management run 형식이다.
    """
    return call(
        lambda: runs.start_preview_test_run(
            session,
            target_ids=_targets_for_fixtures(session, payload.fixture_ids),
            fixture_from=payload.fixture_from,
            fixture_to=payload.fixture_to,
            preview_fixture_ids=payload.fixture_ids,
            generate_after_collection=False,
            user=user,
        )
    )


def _targets_for_fixtures(session, fixture_ids):
    """두 경기의 리그/시즌에서 **활성 수집 대상**을 서버가 해석한다.

    화면이 내부 target_id를 만들거나 입력하지 않게 하려면 서버가 정해야 한다. 대상이
    없으면 기존 `start_run` 검증이 422로 거부하므로 여기서 임의 값을 만들지 않는다.
    """
    from app.models import Fixture, LeagueSyncTarget

    fixtures = list(
        session.scalars(select(Fixture).where(Fixture.external_id.in_(list(fixture_ids))))
    )
    if len(fixtures) != len(set(fixture_ids)):
        missing = sorted(set(fixture_ids) - {int(row.external_id) for row in fixtures})
        raise service.ManagementError(
            f"경기 {', '.join(str(value) for value in missing)}를 저장된 경기에서"
            " 찾지 못했습니다. 수집된 경기만 시험 대상으로 지정할 수 있습니다.",
            422,
        )
    ids: list[int] = []
    for fixture in fixtures:
        target = session.scalar(
            select(LeagueSyncTarget).where(
                LeagueSyncTarget.league_id == fixture.league_id,
                LeagueSyncTarget.season_year == fixture.season_year,
            )
        )
        if target is None:
            raise service.ManagementError(
                f"경기 {fixture.external_id}의 리그/시즌"
                f"({fixture.league_id}/{fixture.season_year})에 수집 대상이 없습니다.",
                422,
            )
        if target.id not in ids:
            ids.append(target.id)
    return ids


@router.get("/preview-test/runs")
def list_preview_test_runs(
    session: Db, user: Annotated[AppUser, Depends(require_admin)]
):
    """수집 시험 실행 목록. **부작용이 없다**(기존 run_list의 삭제·복구 미호출)."""
    from app.services import preview_test

    return preview_test.list_test_runs(session)


@router.get("/preview-test/runs/{run_id}")
def get_preview_test_run(
    run_id: str, session: Db, user: Annotated[AppUser, Depends(require_admin)]
):
    """수집 시험 실행 하나. 없는 실행·다른 실행의 내용을 돌려주지 않는다."""
    from app.services import preview_test

    return call(lambda: preview_test.test_run(session, run_id))


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
