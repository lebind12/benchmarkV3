"""관리자 실행 기록·검사 API.

경계:

- 모든 경로는 `require_preview_admin`으로 서버에서 ADMIN만 통과시킨다. 화면 숨김은
  권한이 아니다. 비인증 401, 인증된 비ADMIN 403이다.
- GET 계열은 저장된 행만 읽는다. 외부 모델·API를 호출하지 않는다. 이 모듈은
  제공자 클라이언트나 HTTP 전송 계층을 import하지 않는다.
- 실행을 만드는 유일한 경로는 명시적 POST `/runs/mock-demo`이며, 이름에 mock이
  들어간 녹화 실행만 만든다. 실제 모델 실행 경로는 MP-04가 붙인다.
- 실행 취소(undo)는 이 실행이 만든 개발 영역 기록에만 적용한다. 기존 경기·계정
  자료나 다른 실행의 기록은 대상이 아니다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import AdminPrincipal, require_preview_admin
from app.db import get_db
from app.preview import approvals, demo_pipeline, provider, runner, store
from app.preview.contracts import (
    ApprovalRequestError,
    AttemptOutcome,
    ContractError,
    Environment,
    RunMode,
)
from app.preview.inspection import build_run_inspection
from app.preview.models import PreviewRun
from app.preview.registry import (
    describe_registry,
    describe_section_workflows,
    get_section_workflow,
)
from app.preview.retention import (
    expire_raw_artifacts,
    retention_policy,
    retention_summary,
)

router = APIRouter(prefix="/api/v1/admin/preview", tags=["preview-admin"])


class RunListResponse(BaseModel):
    runs: list[dict]
    next_cursor: str | None = None


class CreateMockRunResponse(BaseModel):
    run_id: UUID
    module_execution_id: UUID
    result_ids: list[UUID]
    mode: str
    label: str
    external_calls: int
    note: str


class CancelRunRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class CancelRunResponse(BaseModel):
    run_id: UUID
    cancelled_at: datetime
    removed: dict[str, int]
    kept: list[str]
    reason: str


class ApproveSectionRequest(BaseModel):
    """관리자가 확인한 섹션 워크플로우 버전을 승인한다.

    승인 근거는 실제 섹션 실행 결과여야 한다. 섹션 결과 저장은 MP-09 소유이므로
    지금은 요청이 거부된다. 근거 없는 승인 행을 만들지 않기 위한 것이다.
    """

    run_id: UUID
    section_result_id: UUID
    note: str | None = Field(default=None, max_length=1000)


def _fixture_reader():
    """저장 경기 자료 조회기. 설정이 없으면 `None`이며 그 사실이 응답에 드러난다."""
    from app.core.config import get_settings
    from app.preview.sources.fixtures import StoredFixtureReader

    settings = get_settings()
    url = settings.fixtures_database_url
    if not url:
        return None
    return StoredFixtureReader.from_url(url)


def _model_transport(mode: RunMode):
    """섹션 실행용 모델 transport. 설정이 없으면 `None`(실행하지 않는다).

    모델 이름·프로젝트·리전은 설정에서만 읽는다. 여기서 대체 모델을 고르지 않는다.
    `PREVIEW_MODEL_LIVE_ENABLED`가 꺼져 있으면 live 실행을 열지 않는다.
    """
    from app.core.config import get_settings
    from app.preview.contracts import RunMode as _RunMode

    settings = get_settings()
    if mode is not _RunMode.LIVE:
        return provider.RecordedTransport(
            script=(),
            provider="section-mock-transport",
            mode=_RunMode.MOCK,
        )
    if not settings.model_live_enabled:
        return None
    return provider.GoogleGenAIHttpTransport(
        project=settings.model_project,
        location=settings.model_location,
        model=settings.model_name,
        credentials_json=settings.model_credentials_json,
        mode=_RunMode.LIVE,
    )


class FixtureImportRequest(BaseModel):
    """관리자 명시 요청으로 경기 후보를 수집한다. 외부 API 예산(24회)을 쓴다."""

    league_id: int
    date: str
    timezone: str = "UTC"
    season: int | None = None
    label: str | None = Field(default=None, max_length=200)


class SectionRunRequest(BaseModel):
    """섹션 워크플로우 단독 실행 요청.

    `mode`는 화면·API가 실제 실행 방식을 고르는 값이다. `mock`은 외부 호출 없는
    시연이고, `live`는 실제 제공자 호출이다. `live`는 모델 설정이 없으면 제공자를
    부르지 않고 설정 오류로 실패한다(모의로 대체하지 않는다).
    """

    workflow_id: str
    mode: str = RunMode.MOCK.value
    fixture_id: int | None = None
    league_id: int | None = None
    season: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    kickoff_at: datetime | None = None
    fixture_label: str | None = Field(default=None, max_length=200)
    label: str | None = Field(default=None, max_length=200)
    # 종합(section_synthesis)처럼 앞선 저장 결과를 입력으로 쓰는 섹션은 **관리자가
    # 고른 결과 버전 ID**를 그대로 넘긴다. 서버가 임의로 "최신"을 골라 채우지 않는다.
    selected_result_ids: list[UUID] = Field(default_factory=list)


class SectionRunResponse(BaseModel):
    run_id: UUID
    workflow_id: str
    workflow_version: str
    mode: str
    status: str
    quality: str
    section_result_id: UUID | None
    section_result_version: int | None
    external_calls: int
    budget: dict
    unavailable_reason: str | None
    note: str


class ReplayResultRequest(BaseModel):
    """저장 응답 재생 요청. 외부 모델 호출은 0회다."""

    note: str | None = Field(default=None, max_length=500)


class ReplayResultResponse(BaseModel):
    run_id: UUID
    source_result_id: UUID
    new_result_id: UUID
    new_version: int
    raw_artifact_id: UUID | None
    external_calls: int
    note: str


class CompareResponse(BaseModel):
    module_execution_id: UUID
    module_id: str
    base: dict | None
    target: dict
    diff: dict
    versions_available: list[int]


def _detail_or_404(session: Session, run_id: UUID) -> dict:
    try:
        detail = store.get_run_detail(session, run_id)
    except store.RunNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found") from None
    return build_run_inspection(
        detail.to_dict(),
        approval_status=approvals.describe_approvals(session),
        section_workflows=describe_section_workflows(),
    )


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
    limit: int = Query(default=50, ge=1, le=200),
    include_cancelled: bool = Query(default=True),
) -> RunListResponse:
    """저장된 실행 목록. 외부 호출 없이 DB 행만 읽는다.

    각 행이 실행 방식(mode)·환경(environment)·자료 출처를 함께 담는다. 보관 정책과
    등록부는 `/retention`·`/registry`에서 따로 읽는다.
    """
    runs = store.list_runs(session, limit=limit, include_cancelled=include_cancelled)
    return RunListResponse(
        runs=[summary.to_dict() for summary in runs],
        next_cursor=None,
    )


@router.post("/runs/mock-demo", response_model=CreateMockRunResponse)
def create_mock_demo_run(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> CreateMockRunResponse:
    """녹화된 모의 실행을 만든다. 외부 모델·API 호출은 0회다.

    관리자가 명시적으로 눌러야만 실행된다. 조회 경로가 이 함수를 부르지 않는다.
    """
    result = demo_pipeline.create_recorded_mock_run(session, actor_id=principal.user_id)
    session.commit()
    return CreateMockRunResponse(
        run_id=result.run_id,
        module_execution_id=result.module_execution_id,
        result_ids=list(result.result_ids),
        mode=RunMode.MOCK.value,
        label=demo_pipeline.MOCK_DEMO_LABEL,
        external_calls=0,
        note=(
            "저장된 모의 자료로 만든 실행입니다. 실제 모델·API 호출이나 실제 AI 조사 결과가 아닙니다."
        ),
    )


@router.get("/runs/{run_id}")
def get_run(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """실행 상세. 요청·응답·변환·다음 입력과 결과 버전을 함께 돌려준다."""
    return _detail_or_404(session, run_id)


@router.get("/runs/{run_id}/modules/{module_execution_id}")
def get_module_execution(
    run_id: UUID,
    module_execution_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """모듈 실행 하나의 공통 검사 뷰. 등록된 모듈이면 같은 구조로 보인다."""
    detail = _detail_or_404(session, run_id)
    for module in detail["inspector_modules"]:
        if module["module_execution_id"] == str(module_execution_id):
            return module
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="module execution not found"
    )


@router.get("/runs/{run_id}/results/{module_execution_id}/versions")
def compare_result_versions(
    run_id: UUID,
    module_execution_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
    base_version: int | None = Query(default=None),
    target_version: int | None = Query(default=None),
) -> CompareResponse:
    """같은 모듈 실행의 두 결과 버전을 비교한다. 이전 버전은 지우지 않는다."""
    module = store.get_module_execution(session, run_id, module_execution_id)
    if module is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="module execution not found"
        )
    try:
        comparison = store.compare_result_versions(
            session,
            module_execution_id,
            base_version=base_version,
            target_version=target_version,
        )
    except store.RunNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from None
    return CompareResponse(**comparison)


@router.get("/approvals")
def get_approvals(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """섹션 워크플로우 승인 현황. 승인 기록이 없으면 없다고 알린다.

    승인 전 섹션을 승인된 것처럼 표시하지 않는다. 조회는 저장된 행만 읽는다.
    """
    status = approvals.describe_approvals(session)
    status["sections"] = describe_section_workflows()
    status["mock_demo_module_id"] = demo_pipeline.MOCK_DEMO_MODULE_ID
    status["mock_demo_note"] = (
        "모의 시연 실행은 UI 확인용이며 실제 섹션 생성 승인 근거로 쓰지 않습니다."
        " 승인 단위는 섹션 워크플로우입니다."
    )
    return status


@router.post("/sections/{workflow_id}/approvals", response_model=dict)
def approve_section(
    workflow_id: str,
    payload: ApproveSectionRequest,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """관리자가 확인한 섹션 워크플로우 버전을 승인한다.

    승인 단위는 섹션을 만드는 완결된 워크플로우이며, 내부 노드·D0에는 따로 승인하지
    않는다. 개발 완료 보고·테스트 통과·worker_done은 승인이 아니다. 섹션 결과 저장이
    없는 지금은 근거가 없으므로 422로 거부한다.
    """
    try:
        approval = approvals.approve_section_version(
            session,
            workflow_id=workflow_id,
            run_id=payload.run_id,
            section_result_id=payload.section_result_id,
            actor_id=principal.user_id,
            note=payload.note,
        )
    except KeyError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="section workflow not found"
        ) from None
    except ApprovalRequestError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    session.commit()
    return approval.to_dict()


@router.get("/fixtures")
def list_stored_fixtures(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
    league_id: int | None = Query(default=None),
    date: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """저장된 경기 후보. 이 경로는 수집을 일으키지 않고 외부 API도 부르지 않는다.

    기존 DB 경기 자료는 읽기 전용 연결로 읽는다. 권한이 없으면 빈 목록으로 감추지
    않고 `stored_access`에 사유를 남긴다.
    """
    from app.preview import data as data_module
    from app.preview.contracts import FixtureCatalogQuery

    query = (
        FixtureCatalogQuery(league_id=league_id, date=date, timezone="UTC")
        if league_id is not None and date
        else None
    )
    reader = _fixture_reader()
    try:
        result = data_module.list_fixtures(
            session, query=query, reader=reader, limit=limit
        )
    finally:
        if reader is not None:
            reader.close()
    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


@router.post("/fixtures/import")
def import_fixtures(
    payload: FixtureImportRequest,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """관리자가 명시한 조건으로 경기 후보를 수집한다(모의 실행기, 외부 호출 0회).

    실제 API 전송은 API 자격 증명이 연결된 실행기에서만 일어난다. 지금은 저장 경로와
    예산 기록만 확인하는 모의 수집이며, 응답의 `external_calls`가 그 사실을 밝힌다.
    """
    from app.preview import data as data_module
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        FixtureCatalogQuery,
        OperationKind,
        RunMode,
        compute_input_hash,
    )
    from app.preview.sources.api_football import ApiExchange

    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.FIXTURE_CATALOG,
        environment=Environment.DEV,
        mode=RunMode.MOCK,
        actor_id=principal.user_id,
        config_version="mp04-fixture-catalog-1",
    )
    query = FixtureCatalogQuery(
        league_id=payload.league_id, date=payload.date, timezone=payload.timezone
    )

    def _mock_executor(spec):
        return ApiExchange(
            response=provider.ProviderResponse(
                attempt_id=uuid.uuid4(),
                outcome=AttemptOutcome.OK,
                http_status=200,
            ),
            body={
                "response": [],
                "results": 0,
                "mock": True,
                "note": "모의 수집 응답입니다. 실제 API 호출이 아닙니다.",
                "logical_call_id": spec.logical_call_id,
                "input_hash_hint": compute_input_hash(spec.to_dict()),
            },
        )

    result = data_module.import_fixtures(
        session,
        query,
        context=context,
        executor=_mock_executor,
        season=payload.season,
        actor_id=principal.user_id,
    )
    session.commit()
    payload_out = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    payload_out["note"] = (
        "모의 실행기로 수집한 결과입니다. 외부 API를 호출하지 않았습니다."
    )
    return payload_out


def _section_implementations(workflow_id: str, *, mode: RunMode = RunMode.MOCK):
    """섹션 실행에 쓸 구현 묶음.

    - `mock`: 명시적 모의 시연. 외부 호출이 없고 승인 근거가 아니다.
    - `live`: 실제 구현이 있는 섹션만. 구현이 없으면 422로 거부한다. 모의로
      대체해 성공처럼 보이게 하지 않는다.
    """
    from app.preview import sections as section_factories
    from app.preview.contracts import RunMode as _RunMode

    if mode is _RunMode.MOCK:
        return runner.mock_section_implementations(workflow_id)
    if workflow_id not in section_factories.implemented_section_ids():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{workflow_id} 섹션의 실제 조사·생성 구현이 아직 등록되지 않았습니다."
                " 모의 시연으로 대체하지 않습니다."
            ),
        )
    transport = _model_transport(mode)
    if transport is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "모델 설정이 없거나 PREVIEW_MODEL_LIVE_ENABLED가 꺼져 있어 live"
                " 실행을 열지 않았습니다. 대체 모델로 실행하지 않습니다."
            ),
        )
    return section_factories.build_implementations(
        workflow_id, transport=transport, reader=_fixture_reader()
    )


def _section_run_availability(workflow_id: str) -> dict:
    """섹션 하나의 실행 가능성. 미구현을 숨기지 않고 그대로 알린다."""
    try:
        get_section_workflow(workflow_id)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="section workflow not found"
        ) from None
    from app.preview import sections as section_factories

    built: dict = {}
    mock_bundle = runner.mock_section_implementations(workflow_id)
    built[workflow_id] = mock_bundle
    availability = runner.section_run_availability(workflow_id, built)
    # 실제 구현이 있는 섹션은 모의 시연 여부와 별개로 그 사실을 따로 알린다.
    real_generatable = workflow_id in section_factories.implemented_section_ids()
    transport = _model_transport(RunMode.LIVE)
    model_status = (
        provider.model_configuration_status(transport)
        if transport is not None
        else {"configured": False, "problem": "live 실행이 설정으로 열려 있지 않습니다."}
    )
    availability["real_generation_available"] = real_generatable
    availability["model"] = model_status
    if real_generatable:
        availability["note"] = (
            "실제 조사·본문 조립 구현이 등록되어 있습니다. 실행 방식(live)은 모델 설정이"
            " 갖춰지고 관리자가 명시적으로 실행할 때만 열립니다. 모의 시연은 승인"
            " 근거가 아닙니다."
        )
    return availability


@router.get("/sections")
def list_sections(
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """섹션 워크플로우 실행 가능성 목록. 저장된 행만 읽고 외부 호출이 없다.

    `implemented=false`인 섹션은 본문을 실제로 만들 수 없다. 모의 시연으로 실행할 수는
    있지만 그 결과는 승인 근거가 아니다. 실제 구현이 있는 섹션은 모의 시연과 실제
    생성 가능성을 따로 표시한다.
    """
    workflows = describe_section_workflows()
    return {
        "workflows": workflows["workflows"],
        "availability": {
            row["workflow_id"]: _section_run_availability(row["workflow_id"])
            for row in workflows["workflows"]
        },
        "mock_demo_note": (
            "모의 시연은 외부 모델·API를 호출하지 않으며 승인 근거로 쓰지 않습니다."
            " 실제 구현이 있는 섹션은 live 실행 가능성을 따로 표시합니다."
        ),
    }


@router.post("/section-runs", response_model=SectionRunResponse)
def create_section_run(
    payload: SectionRunRequest,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> SectionRunResponse:
    """섹션 워크플로우 하나를 실행하고 실행 ID를 돌려준다.

    관리자는 이 ID로 저장된 전체 결과(본문·근거·노드 진단)를 다시 연다. 실행 기록은
    `preview_dev`에 남고, 모의 실행은 `mode=mock`으로 표시된다. 실제 조사 구현이
    등록되지 않은 단계는 본문을 만들어 채우지 않고 그대로 실패로 남긴다.
    """
    try:
        mode = RunMode(payload.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="unknown run mode",
        ) from None
    if mode is RunMode.REPLAY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "저장 응답 재생은 결과 단위 재변환 경로를 씁니다. 섹션 실행의 재생"
                " 모드는 아직 열지 않았습니다."
            ),
        )

    implementations = _section_implementations(payload.workflow_id, mode=mode)
    fixture = None
    if payload.fixture_id is not None and payload.kickoff_at is not None:
        fixture = {
            "fixture_id": payload.fixture_id,
            "league_id": payload.league_id or 0,
            "season": payload.season or 0,
            "home_team_id": payload.home_team_id or 0,
            "away_team_id": payload.away_team_id or 0,
            "kickoff_at": payload.kickoff_at.isoformat(),
        }
    if mode is not RunMode.MOCK and fixture is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "실제 실행에는 경기 식별자(fixture_id·리그·시즌·팀·킥오프)가"
                " 필요합니다. 경기 선택 화면에서 경기를 골라 실행하세요."
            ),
        )

    result = runner.run_section_workflow(
        session,
        workflow_id=payload.workflow_id,
        implementations=implementations,
        actor_id=principal.user_id,
        environment=Environment.DEV,
        fixture=fixture,
        fixture_label=payload.fixture_label,
        label=payload.label,
        selected_result_ids=tuple(payload.selected_result_ids),
    )
    session.commit()
    return SectionRunResponse(
        run_id=result.run_id,
        workflow_id=result.workflow_id,
        workflow_version=result.workflow_version,
        mode=result.mode.value,
        status=result.status.value,
        quality=result.quality.value,
        section_result_id=result.section_result_id,
        section_result_version=result.section_result_version,
        external_calls=result.external_calls,
        budget=dict(result.budget),
        unavailable_reason=result.unavailable_reason,
        note=(
            "모의 시연 실행입니다. 외부 모델·API를 호출하지 않았고, 이 결과는 승인"
            " 근거가 아닙니다."
            if result.mode is RunMode.MOCK
            else "실행 결과를 저장했습니다."
        ),
    )


@router.get("/runs/{run_id}/preview")
def get_reader_preview(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """MP-09 독자용 프리뷰. **ADMIN 전용**이며 저장된 행만 읽는다.

    이 응답은 독자에게 그대로 보여줄 수 있는 **엄격한 투영**이다. 진단·커버리지·
    스냅샷·결과 ID·시도 정보는 넣지 않는다. 같은 실행의 진단은 이 경로가 아니라
    실행 상세(`/runs/{run_id}`)와 `diagnostics` 경로에서 본다.

    섹션 본문에는 독자용 문장만 담기므로, 관리자 화면도 이 응답의 `body`와 `sources`를
    먼저 보여주고 노드별 원문은 진단에서 펼친다.
    """
    from app.preview.modules import synthesis as synthesis_module
    from app.preview.section_preview import build_reader_view

    try:
        detail = store.get_run_detail(session, run_id, include_artifact_bodies=False)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None

    view = build_reader_view(session, detail)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "이 실행에는 독자용 프리뷰 결과가 없습니다. 종합 섹션을 먼저"
                " 실행해야 하며, 없는 본문을 만들어 응답하지 않습니다."
            ),
        )
    return view


@router.get("/runs/{run_id}/preview/diagnostics")
def get_preview_diagnostics(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """MP-09 독자용 프리뷰의 **관리자 진단**. 독자용 응답과 분리된 경로다."""
    from app.preview.section_preview import build_diagnostics_view

    try:
        detail = store.get_run_detail(session, run_id, include_artifact_bodies=False)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None
    return build_diagnostics_view(session, detail)


@router.get("/runs/{run_id}/section-results")
def get_section_results(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """이 실행이 저장한 섹션 본문 결과들. 저장된 행만 읽는다."""
    try:
        store.get_run_detail(session, run_id)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None
    return {
        "run_id": str(run_id),
        "section_results": store.list_section_results(session, run_id),
    }


@router.post(
    "/results/{result_id}/replays", response_model=ReplayResultResponse
)
def replay_stored_result(
    result_id: UUID,
    payload: ReplayResultRequest,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> ReplayResultResponse:
    """저장된 응답으로 변환만 다시 한다. 외부 모델 호출은 0회다.

    이 경로를 LangGraph 체크포인트의 재실행(유료 time travel)이나 DB undo와 혼동하지
    않는다. 원본 결과와 시도·원문은 그대로 남고, 새 결과 버전이 추가된다.
    """
    from app.preview.models import PreviewResult

    source = session.get(PreviewResult, result_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="result not found"
        )

    def transform(raw_body, previous_payload):  # noqa: ANN001 - 콜백 계약
        return {
            "claims": (previous_payload or {}).get("claims") or [],
            "coverage": (previous_payload or {}).get("coverage") or [],
            "diagnostics": [
                "저장된 원문으로 변환을 다시 했습니다. 외부 호출은 없습니다.",
            ],
            "payload": {
                "replay_note": payload.note,
                "replay_raw_present": raw_body is not None,
            },
        }

    try:
        outcome = provider.replay_result(
            session,
            source_result_id=result_id,
            transform=transform,
            actor_id=principal.user_id,
        )
    except store.RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from None
    session.commit()
    return ReplayResultResponse(
        run_id=outcome.run_id,
        source_result_id=outcome.source_result_id,
        new_result_id=outcome.new_result_id,
        new_version=outcome.new_version,
        raw_artifact_id=outcome.raw_artifact_id,
        external_calls=outcome.external_calls,
        note="저장 응답 재생입니다. 외부 모델·API 호출이 없습니다.",
    )


@router.get("/registry")
def get_registry(
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """등록된 모듈과 구현 여부. 미구현 모듈을 실행 가능으로 보이지 않게 한다.

    섹션 워크플로우에는 지금 실행 가능한 방식(`modes`)을 함께 붙인다. 등록부의
    `implemented=False`는 "실제 생성 구현이 없다"는 뜻이고, `modes=['mock']`은
    "모의 시연만 가능하다"는 뜻이다. 두 값을 섞어 실제 생성이 되는 것처럼 보이지
    않게 따로 내보낸다.
    """
    registry = describe_registry()
    workflow_ids = [
        row["workflow_id"] for row in describe_section_workflows()["workflows"]
    ]
    section_availability = {
        workflow_id: _section_run_availability(workflow_id) for workflow_id in workflow_ids
    }
    registry["section_availability"] = section_availability
    registry["section_modes"] = {
        workflow_id: availability["modes"]
        for workflow_id, availability in section_availability.items()
    }
    return registry


@router.get("/retention")
def get_retention(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """보관 정책과 현재 상태. 자동 삭제 스케줄러는 없다."""
    return {
        "policy": retention_policy(),
        "status": retention_summary(session),
    }


@router.post("/retention/expire", response_model=dict)
def run_expiry(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """만료 처리를 한 번 실행한다. 운영에서 자동으로 돌리지 않는다.

    지우는 것은 보관 기간이 지난 원문 본문뿐이다. 요약·해시·기간은 남는다.
    """
    expired = expire_raw_artifacts(session)
    session.commit()
    return {
        "expired": len(expired),
        "artifacts": [str(row.id) for row in expired],
        "note": "원문 본문만 삭제했습니다. 요약과 기간, 실행 기록은 남아 있습니다.",
    }


@router.get("/runs/{run_id}/undo")
def preview_undo(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """취소하면 무엇이 지워지는지 먼저 보여준다."""
    try:
        return store.undo_report(session, run_id)
    except store.RunNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found") from None


@router.post("/runs/{run_id}/undo", response_model=CancelRunResponse)
def cancel_run(
    run_id: UUID,
    payload: CancelRunRequest,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> CancelRunResponse:
    """이 실행이 만든 preview_dev 기록만 취소한다. 실행 행과 감사 표시는 남긴다.

    다른 실행이 남긴 후속 결과 버전이 있으면 충돌로 중단하고 아무것도 지우지 않는다.
    """
    try:
        result = store.cancel_run(
            session, run_id, actor_id=principal.user_id, reason=payload.reason
        )
    except store.RunNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found") from None
    except store.WriteConflict as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    except ContractError as exc:  # pragma: no cover - 방어적 경로
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    session.commit()
    return CancelRunResponse(**result)


@router.get("/runs/{run_id}/audit")
def get_audit(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """이 실행이 남긴 개발 영역 쓰기 내역. 값이 아니라 동작만 남는다."""
    run = session.get(PreviewRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found")
    return {
        "run_id": str(run.id),
        "write_scope": run.write_scope,
        "events": list(store.iter_audit(session, run_id)),
    }
