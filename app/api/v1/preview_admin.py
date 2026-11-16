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
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.preview.access import PreviewPrincipal, require_preview_admin
from app.preview.db import get_db
from app.preview import approvals, demo_pipeline, provider, runner, store, version_manifest
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
    from app.preview.config import get_settings
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
    from app.preview.config import get_settings
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

    # --- 섹션 재생성(계획 §5) ---------------------------------------------
    # `reuse`: 저장된 정보 원문 묶음을 재사용한다(새 수집·새 검색 호출 없음).
    # `refresh`: 새 수집을 포함한다. 예상 전송 범위를 응답에 표시한다.
    # 기본값은 기존 동작(새 수집 포함)과 같은 `refresh`다. 재사용은 관리자가 명시할 때만
    # 일어나며, 그때는 base_run_id가 필수다. 기본값으로 조용히 재사용하지 않는다.
    source_mode: str = Field(default="refresh", pattern="^(reuse|refresh)$")
    # reuse일 때 어느 묶음을 쓰는지 관리자가 고른다. 서버가 임의로 최신을 고르지 않는다.
    bundle_id: str | None = Field(default=None, max_length=120)
    base_run_id: UUID | None = None
    base_result_id: UUID | None = None
    # 관리자가 저장한 **구성본**을 지정한다. 주면 그 구성본의 선택 결과가 최종 AI 입력이
    # 된다(selected_result_ids를 비워도 된다). 저장된 값과 다르면 422로 거부한다.
    composition_id: str | None = Field(default=None, max_length=120)


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

    # --- 재생성 경계 (계획 §5) --------------------------------------------
    source_mode: str = "refresh"
    bundle_id: str | None = None
    bundle_reused: bool = False
    expected_model_calls: int | None = None
    parent_run_id: UUID | None = None
    base_result_id: UUID | None = None
    new_version: int | None = None
    # 이 실행이 실제로 쓴 구성본 ID. 쓰지 않았으면 null이다(지어내지 않는다).
    composition_id: str | None = None
    # 저장 응답 재처리처럼 **모델 전송이 없는** 동작인지. 이 값이 true면 새 호출은 없다.
    no_model_call: bool = False
    # 다른 성공 섹션을 자동으로 다시 부르지 않았다는 사실을 값으로 남긴다.
    other_sections_reused: bool = True


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


_PLAYER_SECTION_MODULE_IDS: dict[str, str] = {
    "section_players": "R4",
    "section_availability": "R2",
}


def _extract_player_section_processing(payload: dict | None) -> dict | None:
    if not isinstance(payload, dict):
        return None
    structured = payload.get("structured")
    if isinstance(structured, dict) and isinstance(structured.get("processing"), dict):
        return dict(structured["processing"])
    if isinstance(payload.get("processing"), dict):
        return dict(payload["processing"])
    return None


def _id_context_for_detail(detail, names):
    """이미 열린 표시 이름 파사드에서 경기 두 팀 범위의 외부 ID 확인 경계를 만든다."""
    from app.preview.section_structured import StructuredIdContext

    resolver = getattr(names, "names", None) if names is not None else None
    if resolver is None:
        return None
    fixture_block = getattr(detail, "fixture", None)
    fixture_ids = (
        fixture_block.to_dict() if getattr(fixture_block, "to_dict", None) else {}
    )
    try:
        return StructuredIdContext(
            resolver,
            scope_team_ids=tuple(
                int(value)
                for value in (
                    fixture_ids.get("home_team_id"),
                    fixture_ids.get("away_team_id"),
                )
                if isinstance(value, int)
            ),
        )
    except Exception:  # noqa: BLE001 - 확인 경계 실패로 조회를 깨지 않는다
        return None


def _fixture_team_names(
    fixture_label: Any, raw_processing: dict | None = None
) -> tuple[str | None, str | None]:
    """이름 해석기가 없는 오프라인 환경에서 팀 표시 라벨 보조값을 꺼낸다."""
    home_name: str | None = None
    away_name: str | None = None
    label = str(fixture_label or "").strip()
    if " vs " in label and not label.lower().startswith("fixture "):
        left, right = label.split(" vs ", 1)
        home_name = left.strip() or None
        away_name = right.strip() or None
    if isinstance(raw_processing, dict):
        if home_name is None:
            for key in ("home1", "home2"):
                slot = raw_processing.get(key)
                if isinstance(slot, dict) and isinstance(slot.get("team_name"), str) and slot["team_name"].strip():
                    home_name = slot["team_name"].strip()
                    break
        if away_name is None:
            for key in ("away1", "away2"):
                slot = raw_processing.get(key)
                if isinstance(slot, dict) and isinstance(slot.get("team_name"), str) and slot["team_name"].strip():
                    away_name = slot["team_name"].strip()
                    break
    return home_name, away_name


def _attach_player_section_processing(
    inspection: dict,
    raw_detail: dict,
    *,
    session: Session | None = None,
    id_context=None,
) -> dict:
    """저장된 NS-02 선수/부상 처리 진단을 정본 3표 재조회와 함께 실행 상세에 연결한다."""
    from app.preview import player_section_read

    by_result_id: dict[str, dict] = {}
    by_section_id: dict[str, dict] = {}
    for result in raw_detail.get("results") or ():
        if not isinstance(result, dict):
            continue
        payload = result.get("payload")
        processing = _extract_player_section_processing(payload)
        if processing is None:
            continue
        result_id = str(result.get("result_id") or "")
        section_id = str(result.get("section_id") or processing.get("workflow_id") or "")
        if result_id:
            by_result_id[result_id] = processing
        if section_id:
            by_section_id[section_id] = processing

    section_rows = []
    canonical_by_section: dict[str, dict] = {}
    for row in inspection.get("section_results") or ():
        row_copy = dict(row)
        raw_proc = None
        for res_id in row_copy.get("result_ids") or ():
            raw_proc = by_result_id.get(str(res_id))
            if raw_proc is not None:
                break
        if raw_proc is None:
            raw_proc = by_result_id.get(str(row_copy.get("result_id") or ""))
        wf_id = str(row_copy.get("workflow_id") or row_copy.get("section_id") or "")
        if raw_proc is None and wf_id:
            raw_proc = by_section_id.get(wf_id)

        if session is not None and player_section_read.is_new_player_section_contract(
            row_copy.get("output_contract_version")
        ):
            home_label, away_label = _fixture_team_names(
                (raw_detail.get("summary") or {}).get("fixture_label"), raw_proc
            )
            canonical = player_section_read.read_canonical_player_section(
                session,
                row_copy,
                raw_processing=raw_proc,
                id_context=id_context,
                home_team_name=home_label,
                away_team_name=away_label,
            )
            row_copy["player_section_processing"] = canonical.processing
            row_copy["storage_mismatch"] = canonical.storage_mismatch
            if canonical.storage_error:
                row_copy["storage_error"] = canonical.storage_error
            if wf_id:
                canonical_by_section[wf_id] = canonical.processing
        elif raw_proc is not None:
            # 구 계약/미저장 초안은 저장된 처리 결과로 오인하지 않는다.
            legacy_proc = {**raw_proc, "persisted": False}
            row_copy["player_section_processing"] = legacy_proc
            if wf_id:
                canonical_by_section[wf_id] = legacy_proc
        section_rows.append(row_copy)

    if not canonical_by_section and not by_section_id and not by_result_id:
        return {**inspection, "player_section_processing": {}}

    effective_by_section = {**by_section_id, **canonical_by_section}
    module_to_section = {mod: sec for sec, mod in _PLAYER_SECTION_MODULE_IDS.items()}
    modules = []
    for mod in inspection.get("inspector_modules") or ():
        mod_copy = dict(mod)
        sec_id = module_to_section.get(str(mod_copy.get("module_id") or ""))
        if sec_id and sec_id in effective_by_section:
            mod_copy["player_section_processing"] = effective_by_section[sec_id]
        modules.append(mod_copy)

    return {
        **inspection,
        "section_results": section_rows,
        "inspector_modules": modules,
        "player_section_processing": effective_by_section,
    }


def _detail_or_404(session: Session, run_id: UUID) -> dict:
    try:
        detail = store.get_run_detail(session, run_id)
    except store.RunNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="run not found") from None
    raw_detail = detail.to_dict()
    inspection = build_run_inspection(
        raw_detail,
        approval_status=approvals.describe_approvals(session),
        section_workflows=describe_section_workflows(),
    )
    names = _display_names_for(session, detail)
    try:
        id_context = _id_context_for_detail(detail, names)
        return _attach_player_section_processing(
            inspection, raw_detail, session=session, id_context=id_context
        )
    finally:
        close = getattr(names, "close", None)
        if callable(close):
            close()


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """실행 상세. 요청·응답·변환·다음 입력과 결과 버전을 함께 돌려준다.

    섹션 본문은 **화면에 낼 때** 한국어 표기로 바꾼다(축구 용어 사전 + 확인된 팀·선수·
    감독 이름). 저장된 행은 그대로 두고 응답 값만 바꾼다.
    """
    detail = store.get_run_detail(session, run_id) if _run_exists(session, run_id) else None
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        )
    raw_detail = detail.to_dict()
    payload = build_run_inspection(
        raw_detail,
        approval_status=approvals.describe_approvals(session),
        section_workflows=describe_section_workflows(),
    )
    # 전송 장부 요약을 상세에 덧붙인다. 저장된 감사 행만 읽으며 외부 호출이 없다.
    payload["send_ledger"] = store.run_send_ledger_summary(session, run_id)
    names = _display_names_for(session, detail)
    try:
        id_context = _id_context_for_detail(detail, names)
        payload = _attach_player_section_processing(
            payload, raw_detail, session=session, id_context=id_context
        )
        return _localized_inspection(payload, names=names)
    finally:
        close = getattr(names, "close", None)
        if callable(close):
            close()


def _run_exists(session, run_id: UUID) -> bool:
    return session.get(PreviewRun, run_id) is not None


def _localized_inspection(payload: dict, *, names) -> dict:
    """검사 응답의 **표시 문자열만** 한국어로 바꾼 사본을 돌려준다.

    저장된 본문·원문·버전은 건드리지 않는다. NS-02 선수/부상 섹션 본문은 생성 당시
    원문을 보존하며 후속 치환으로 재작성하지 않는다.
    """
    preserved_sections = {"section_players", "section_availability"}
    rows = []
    for row in payload.get("section_results") or ():
        sec_key = row.get("workflow_id") or row.get("section_id")
        if sec_key in preserved_sections or row.get("player_section_processing") is not None:
            rows.append(row)
            continue
        body = row.get("body")
        if isinstance(body, str) and body:
            rows.append({**row, "body": _terms_only(body)})
        else:
            rows.append(row)
    if names is None or not getattr(names, "active", False):
        return {**payload, "section_results": rows}

    localized_rows = []
    for row in payload.get("section_results") or ():
        sec_key = row.get("workflow_id") or row.get("section_id")
        if sec_key in preserved_sections or row.get("player_section_processing") is not None:
            localized_rows.append(row)
            continue
        body = row.get("body")
        if not isinstance(body, str) or not body:
            localized_rows.append(row)
            continue
        try:
            rewritten = names.rewrite_body(body)
        except Exception:  # noqa: BLE001 - 표시 실패로 조회를 깨지 않는다
            rewritten = body
        localized_rows.append({**row, "body": rewritten})
    return {**payload, "section_results": localized_rows}


def _terms_only(text: str) -> str:
    """해석기 없이 용어·대회명만 바꾼다."""
    from app.preview.football_terms import rewrite_football_terms

    try:
        return rewrite_football_terms(text)
    except Exception:  # noqa: BLE001
        return text


@router.get("/runs/{run_id}/modules/{module_execution_id}")
def get_module_execution(
    run_id: UUID,
    module_execution_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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


@router.get("/fixtures/{fixture_id}")
def get_stored_fixture(
    fixture_id: int,
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """경기 번호(API-Football 외부 ID) 하나로 저장된 경기를 확인한다.

    관리자가 번호만 입력해 대진·시각을 확인하고 같은 번호로 생성을 요청하는 흐름의
    읽기 경로다. 모델·외부 API를 부르지 않고 저장된 행만 읽으며, 반환은 목록 경로의
    `fixtures[]` 항목과 **같은 FixtureCandidate 모양**이다.

    없는 번호는 404, 저장 자료를 읽을 권한/연결이 없으면 이유가 담긴 503이다. 어느
    경우에도 빈 성공 응답으로 감추지 않는다.
    """
    from app.preview import data as data_module
    from app.preview.sources import fixtures as fixtures_module

    reader = _fixture_reader()
    if reader is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "저장된 경기 자료 조회기가 설정되지 않았습니다(fixtures_database_url 비어 있음)."
                " 경기 번호를 확인할 수 없어 모델을 보내지 않습니다."
            ),
        )
    try:
        access = reader.access()
        if not access.readable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "저장된 경기 자료를 읽을 수 없습니다: "
                    + (access.detail or "읽기 권한을 확인하지 못했습니다.")
                ),
            )
        record = reader.get_fixture(fixture_id=int(fixture_id))
    except fixtures_module.FixtureReadDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 연결 실패를 빈 목록으로 감추지 않는다
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"저장된 경기 자료를 읽지 못했습니다: {type(exc).__name__}: {exc}",
        ) from None
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"저장된 경기 번호 {fixture_id}를 찾지 못했습니다.",
        )
    return data_module._candidate_from_stored(record).to_dict()


@router.post("/fixtures/import")
def import_fixtures(
    payload: FixtureImportRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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


# 섹션 하나를 다시 만들 때 필요한 모델 요청 수(설계 §실행 예산). 배당은 모델 0회다.
_SECTION_MODEL_CALLS: dict[str, int] = {
    "section_players": 1,
    "section_availability": 1,
    "section_outlook": 1,
    "section_odds": 0,
    "section_ai_forecast": 1,
    # 옛 경로(기존 섹션)도 1회다. 값을 모르는 섹션은 None으로 두고 꾸미지 않는다.
    "section_form": 1,
    "section_synthesis": 1,
}


def _expected_section_model_calls(workflow_id: str) -> int | None:
    return _SECTION_MODEL_CALLS.get(workflow_id)


def _annotate_section_reuse(
    session: Session,
    *,
    section_result_id: UUID,
    base_run_id: UUID | None,
    bundle_id: str | None,
    base_result_id: UUID | None,
    actor_id: int,
) -> None:
    """재생성 결과에 부모 실행·재사용 묶음 연결을 진단으로 남긴다.

    본문·근거 행은 그대로 두고 진단 목록에만 덧붙인다. 승인 근거(본문)를 바꾸지 않는다.
    """
    from app.preview.models import PreviewSectionResult

    row = session.get(PreviewSectionResult, section_result_id)
    if row is None:
        return
    note = (
        f"재생성: source_mode=reuse, base_run_id={base_run_id},"
        f" bundle_id={bundle_id}, base_result_id={base_result_id}"
    )
    diagnostics = list(row.diagnostics or [])
    if note not in diagnostics:
        diagnostics.append(note)
    row.diagnostics = diagnostics
    session.flush()
    store._audit(  # noqa: SLF001 - 같은 감사 경로를 재사용한다
        session,
        run_id=row.run_id,
        actor_id=actor_id,
        action="section_regenerated_reusing_bundle",
        target_table="preview_section_results",
        target_id=str(row.id),
        detail={
            "base_run_id": str(base_run_id) if base_run_id else None,
            "bundle_id": bundle_id,
            "base_result_id": str(base_result_id) if base_result_id else None,
        },
    )


@router.post("/section-runs", response_model=SectionRunResponse)
def create_section_run(
    payload: SectionRunRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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

    # --- 재생성 경계 (계획 §5, 검토 F5) -----------------------------------
    # **옛 구현 게이트보다 먼저** 분기한다. `_section_implementations`는 옛 노드 목록만
    # 보므로, 뒤에 두면 `section_odds`/`section_ai_forecast`가 422로 막혀 새 경로의 두
    # 섹션을 화면에서 다시 만들 수 없었다(검토 F5).
    from app.preview import bundle_pipeline as bundle_pipeline_module

    if (
        payload.workflow_id in bundle_pipeline_module.REGENERABLE_SECTIONS
        and mode is RunMode.LIVE
    ):
        # 요청 모양 오류를 먼저 알린다(모드 문제보다 정확한 사유).
        if payload.source_mode == "reuse" and payload.base_run_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "source_mode=reuse에는 재사용할 정보 원문 묶음의 실행(base_run_id)이"
                    " 필요합니다. 서버가 임의로 최신 묶음을 고르지 않습니다."
                ),
            )
        is_initial_run = payload.base_run_id is None
        if is_initial_run and (
            payload.base_result_id is not None or payload.composition_id is not None
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "기준 실행(base_run_id) 없이 base_result_id 또는 composition_id를"
                    " 지정할 수 없습니다."
                ),
            )
        if (
            is_initial_run
            and payload.workflow_id not in bundle_pipeline_module.INITIAL_PLAYER_SECTIONS
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"{payload.workflow_id} 섹션은 기준 실행(base_run_id) 없이 최초"
                    " 단독 실행할 수 없습니다. 주목 선수·부상 섹션만 최초 단독 실행을"
                    " 지원합니다."
                ),
            )
        if is_initial_run and payload.fixture_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "실제 실행에는 경기 식별자(fixture_id·리그·시즌·팀·킥오프)가"
                    " 필요합니다. 경기 선택 화면에서 경기를 골라 실행하세요."
                ),
            )
        transport = _model_transport(mode)
        if transport is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "모델 설정이 없거나 PREVIEW_MODEL_LIVE_ENABLED가 꺼져 있어 live 실행을"
                    " 열지 않았습니다. 모의로 대체하지 않습니다."
                ),
            )
        reader = _fixture_reader()
        try:
            if not is_initial_run:
                outcome = bundle_pipeline_module.run_section_regeneration(
                    session,
                    section_id=payload.workflow_id,
                    actor_id=principal.user_id,
                    transport=transport,
                    base_run_id=payload.base_run_id,
                    source_mode=payload.source_mode,
                    base_result_id=payload.base_result_id,
                    reader=reader,
                    limits=None,
                    # 재생성도 **관리자가 고른** 앞 섹션 결과 버전을 그대로 쓴다. 이 값을
                    # 넘기지 않던 것이 "선택은 받지만 최종 AI에 전달되지 않는" 결함이었다.
                    upstream_result_ids=tuple(payload.selected_result_ids),
                    composition_id=payload.composition_id,
                )
            else:
                record = None
                if reader is not None and callable(getattr(reader, "get_fixture", None)):
                    try:
                        record = reader.get_fixture(fixture_id=int(payload.fixture_id))
                    except Exception:  # noqa: BLE001 - D0에서 진단으로 남긴다
                        record = None
                effective_fixture = fixture
                if effective_fixture is None and record is not None:
                    kickoff = getattr(record, "kickoff_at", None)
                    if (
                        getattr(record, "home_team_id", None) is not None
                        and getattr(record, "away_team_id", None) is not None
                        and kickoff is not None
                    ):
                        effective_fixture = {
                            "fixture_id": int(record.fixture_id),
                            "league_id": int(record.league_id),
                            "season": int(record.season),
                            "home_team_id": int(record.home_team_id),
                            "away_team_id": int(record.away_team_id),
                            "kickoff_at": kickoff.isoformat(),
                        }
                if effective_fixture is None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=(
                            "실제 실행에는 경기 식별자(fixture_id·리그·시즌·팀·킥오프)가"
                            " 필요합니다. 경기 선택 화면에서 경기를 골라 실행하세요."
                        ),
                    )
                home_team = getattr(record, "home_team_name", None) if record else None
                away_team = getattr(record, "away_team_name", None) if record else None
                league_name = getattr(record, "league_name", None) if record else None
                effective_label = payload.fixture_label or (
                    getattr(record, "label", None) if record else None
                )
                if (not home_team or not away_team) and effective_label and " vs " in effective_label:
                    left, right = effective_label.split(" vs ", 1)
                    home_team = home_team or left.strip() or None
                    away_team = away_team or right.strip() or None
                outcome = bundle_pipeline_module.run_section_initial(
                    session,
                    section_id=payload.workflow_id,
                    fixture=effective_fixture,
                    actor_id=principal.user_id,
                    transport=transport,
                    reader=reader,
                    limits=None,
                    label=payload.label,
                    fixture_label=effective_label,
                    home_team=home_team,
                    away_team=away_team,
                    league=league_name,
                )
        except bundle_pipeline_module.SectionRegenerationRefused as exc:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from None
        except store.RunNotFound:
            session.rollback()
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="base run not found"
            ) from None
        finally:
            close = getattr(reader, "close", None)
            if callable(close):
                close()
        session.commit()
        if is_initial_run:
            run_note = (
                "선택한 경기의 필요한 자료만 준비해 이 섹션을 처음 생성·정본 저장했습니다."
                " 다른 섹션은 실행하지 않았습니다."
            )
        elif outcome.bundle_reused:
            run_note = (
                "저장된 정보 원문 묶음만 재사용해 이 섹션을 다시 만들었습니다."
                " 새 수집·검색 호출은 없고 다른 섹션은 다시 부르지 않았습니다."
            )
        else:
            run_note = (
                "이 섹션에 필요한 자료만 새로 수집해 다시 만들었습니다."
                " 다른 섹션 결과는 그대로 두었습니다."
            )
        return SectionRunResponse(
            run_id=outcome.run_id,
            workflow_id=outcome.section_id,
            workflow_version=version_manifest.workflow_version_of(outcome.section_id),
            mode=outcome.mode.value,
            status="succeeded" if outcome.unavailable_reason is None else "failed",
            quality=outcome.quality.value,
            section_result_id=outcome.section_result_id,
            section_result_version=outcome.section_result_version,
            external_calls=outcome.external_calls,
            budget={},
            unavailable_reason=outcome.unavailable_reason,
            note=run_note,
            source_mode=outcome.source_mode,
            bundle_id=outcome.bundle_id,
            bundle_reused=outcome.bundle_reused,
            expected_model_calls=outcome.expected_model_calls,
            parent_run_id=outcome.base_run_id,
            base_result_id=outcome.base_result_id,
            new_version=outcome.section_result_version,
            composition_id=outcome.composition_id,
            no_model_call=outcome.expected_model_calls == 0,
            other_sections_reused=not is_initial_run,
        )

    # --- 옛 경로 섹션 재생성 (기존 노드) ----------------------------------
    implementations = _section_implementations(payload.workflow_id, mode=mode)
    if mode is not RunMode.MOCK and fixture is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "실제 실행에는 경기 식별자(fixture_id·리그·시즌·팀·킥오프)가"
                " 필요합니다. 경기 선택 화면에서 경기를 골라 실행하세요."
            ),
        )
    reuse_bundle: dict | None = None
    if payload.source_mode == "reuse":
        source_run_id = payload.base_run_id
        if source_run_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "source_mode=reuse에는 재사용할 정보 원문 묶음의 실행(base_run_id)이"
                    " 필요합니다. 서버가 임의로 최신 묶음을 고르지 않습니다."
                ),
            )
        try:
            record = store.load_information_bundle(session, source_run_id)
        except store.RunNotFound:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="base run not found",
            ) from None
        if not record.get("available"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "재사용할 정보 원문 묶음이 없습니다: "
                    f"{record.get('reason') or '사유 없음'}"
                ),
            )
        if payload.bundle_id and record["bundle"].get("bundle_id") != payload.bundle_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "요청한 bundle_id가 그 실행의 저장 묶음과 다릅니다."
                    f" 저장된 값: {record['bundle'].get('bundle_id')}"
                ),
            )
        reuse_bundle = record
        # 옛 경로는 묶음을 쓰지 않는다. 재사용으로 표시하지 않는다.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{payload.workflow_id}는 정보 원문 묶음 경로로 재생성할 수 없습니다."
                " 옛 조사 경로를 묶음 재사용으로 표시하지 않습니다."
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

    expected_calls = _expected_section_model_calls(payload.workflow_id)
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
            else "새 수집을 포함해 실행한 결과입니다."
        ),
        source_mode=payload.source_mode,
        bundle_id=None,
        bundle_reused=False,
        expected_model_calls=expected_calls,
        parent_run_id=payload.base_run_id,
        base_result_id=payload.base_result_id,
        new_version=result.section_result_version,
        no_model_call=result.mode is RunMode.MOCK or expected_calls == 0,
        other_sections_reused=True,
    )


@router.get("/runs/{run_id}/preview")
def get_reader_preview(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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

    names = _display_names_for(session, detail)
    try:
        # 새 정보 원문 묶음 경로로 만든 섹션 결과가 있으면 **그 구성본**을 먼저 투영한다.
        # 기존 S1 reader 경로는 옛 종합 결과만 읽어, 묶음으로 만든 본문이 독자 화면에
        # 나타나지 않았다. S1 결과도 없고 묶음 결과도 없을 때만 404다.
        from app.preview.section_preview import build_bundle_reader_view

        view = build_bundle_reader_view(session, detail, names=names)
        if view is None:
            view = build_reader_view(session, detail, names=names)
    finally:
        # 조회기는 본문에만 나온 상대 팀·감독을 DB에 묻는 동안 필요하다. 응답을 만든
        # 뒤에는 닫아 연결을 남기지 않는다.
        close = getattr(names, "close", None)
        if callable(close):
            close()
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "이 실행에는 독자용 프리뷰 결과가 없습니다. 종합 섹션을 먼저"
                " 실행해야 하며, 없는 본문을 만들어 응답하지 않습니다."
            ),
        )
    return view


def _stored_model_labels(detail) -> list:
    """저장된 R4 결과가 함께 남긴 `korean_labels`(모델 번역). 없으면 빈 목록.

    저장 행에서 그대로 읽는다. 이 코드가 번역을 만들지 않는다.
    """
    labels: list = []
    for row in getattr(detail, "results", ()) or ():
        if str(row.get("module_id")) != "R4":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        inner = payload.get("payload")
        source = inner if isinstance(inner, dict) else payload
        found = source.get("korean_labels")
        if isinstance(found, list):
            labels.extend(item for item in found if isinstance(item, dict))
    return labels


def _display_names_for(session, detail):
    """이 실행의 표시 이름 파사드. 설정이 없거나 실패하면 `None`(원문 유지)."""
    from app.preview.config import get_settings
    from app.preview.display_names import open_display_names

    summary = getattr(detail, "summary", None)
    fixture = getattr(detail, "fixture", None)
    fixture_dict = (
        fixture.to_dict() if fixture is not None and hasattr(fixture, "to_dict") else None
    )
    label = getattr(summary, "fixture_label", None) or ""
    try:
        bridge = open_display_names(
            fixture=fixture_dict,
            dsn=get_settings().names_database_url,
            fallback_label=str(label),
        )
        # 저장된 생성 응답이 준 번역 표기를 반영한다(DB 값이 있으면 DB가 이긴다).
        bridge.register_model_labels(_stored_model_labels(detail))
        return bridge
    except Exception:  # noqa: BLE001 - 표시 이름 때문에 조회를 실패시키지 않는다
        return None


@router.get("/runs/{run_id}/preview/diagnostics")
def get_preview_diagnostics(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
    include_structured: bool = Query(default=True),
) -> dict:
    """이 실행이 저장한 섹션 본문 결과들. 저장된 행만 읽는다.

    `include_structured=true`(기본)면 각 섹션 결과에 **저장 payload에서 뽑은 구조 값**을
    `structured`로 덧붙인다(선수명/선정이유 분리, 부상 상태 원문, 매체 점수 미제시 유지,
    정규시간 1X2 배당 표, AI 예상). 값은 저장된 것만 옮기며 새로 만들지 않는다.
    payload가 없으면 `structured`는 비어 있고 `available=false`다.
    """
    from app.preview import player_section_read
    from app.preview.section_structured import (
        STRUCTURED_VERSION,
        structured_row_from_section_result,
    )

    try:
        detail = store.get_run_detail(session, run_id)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None

    rows = store.list_section_results(session, run_id)
    if include_structured:
        payload_by_result: dict[str, dict] = {}
        for result in detail.results:
            result_id = str(result.get("result_id"))
            payload = result.get("payload")
            if isinstance(payload, dict):
                payload_by_result[result_id] = payload
        # 내부 ID → 외부 ID 확인 경계. 표시 이름 파사드가 이미 여는 읽기 전용 조회기를
        # **재사용**한다(새 연결·새 grant 없음). 없으면 외부 ID/사진은 `None`이다.
        names = _display_names_for(session, detail)
        id_context = _id_context_for_detail(detail, names)
        decorated: list[dict] = []
        try:
            for row in rows:
                payload = None
                for result_id in row.get("result_ids") or ():
                    candidate = payload_by_result.get(str(result_id))
                    if candidate is not None:
                        payload = candidate
                        break
                raw_processing = _extract_player_section_processing(payload)
                if player_section_read.is_new_player_section_contract(
                    row.get("output_contract_version")
                ):
                    home_label, away_label = _fixture_team_names(
                        getattr(getattr(detail, "summary", None), "fixture_label", None),
                        raw_processing,
                    )
                    canonical = player_section_read.read_canonical_player_section(
                        session,
                        row,
                        raw_processing=raw_processing,
                        id_context=id_context,
                        home_team_name=home_label,
                        away_team_name=away_label,
                    )
                    decorated.append(
                        {
                            **row,
                            **canonical.structured_result_fields(),
                            "player_section_processing": canonical.processing,
                        }
                    )
                else:
                    legacy_proc = (
                        {**raw_processing, "persisted": False}
                        if raw_processing is not None
                        else None
                    )
                    decorated.append(
                        {
                            **row,
                            **structured_row_from_section_result(
                                row, payload=payload, id_context=id_context
                            ),
                            "persisted": False,
                            "storage_mismatch": False,
                            "player_section_processing": legacy_proc,
                        }
                    )
        finally:
            # 파사드가 연 읽기 전용 연결을 요청 단위로 닫는다.
            close = getattr(names, "close", None)
            if callable(close):
                close()
        rows = decorated

    return {
        "run_id": str(run_id),
        "structured_version": STRUCTURED_VERSION if include_structured else None,
        "section_results": rows,
    }


@router.get("/runs/{run_id}/information-bundle")
def get_information_bundle(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
    include_passages: bool = Query(default=True),
) -> dict:
    """이 실행의 정보 원문 묶음. 관리자 검사용이며 저장된 행만 읽는다.

    - 본문·전달 구간·DB 입력·출처 성격·실패 목록을 함께 보여준다. 노드별 원문 응답은
      실행 상세(`/runs/{run_id}`)에서 펼친다.
    - 묶음이 없으면 빈 묶음을 만들지 않고 `available=false`와 실제 사유를 낸다.
    - 이 응답은 저장된 아티팩트를 읽기만 한다. 외부 모델·API 호출이 없다.
    """
    try:
        record = store.load_information_bundle(session, run_id)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None

    from app.preview import information_bundle as bundle_contract

    if not include_passages and record.get("bundle"):
        bundle = dict(record["bundle"])
        bundle["available_passages"] = []
        bundle["sources"] = [
            {**dict(source), "passages": []}
            for source in bundle.get("sources") or ()
            if isinstance(source, dict)
        ]
        record["bundle"] = bundle
        record["summary"] = bundle_contract.bundle_summary(bundle)

    # 응답 계약: `availability`는 **중첩 객체**다(manifest §4·프론트 파서와 동일).
    # 평면 키로 내보내면 화면이 사유를 잃는다(검토 F6). 값은 그대로 옮기고 새로 만들지 않는다.
    payload = {
        "run_id": str(run_id),
        "availability": {
            "available": bool(record.get("available")),
            "reason": record.get("reason"),
            "artifact_id": record.get("artifact_id"),
            "sequence": record.get("sequence"),
        },
        "bundle": record.get("bundle"),
        "summary": record.get("summary"),
    }
    if not include_passages:
        # 구간 생략 여부는 응답 최상위에 남긴다(화면이 "생략됨"을 알 수 있어야 한다).
        payload["passages_omitted"] = True
        payload["passage_note"] = (
            "구간 본문을 요청에 따라 생략했습니다. 관리자 검사에서 전체를 보려면"
            " include_passages=true로 다시 여세요."
        )
    return payload


@router.get("/runs/{run_id}/information-bundle/sources/{source_id}")
def get_information_bundle_source(
    run_id: UUID,
    source_id: str,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """묶음 출처 하나의 **전문**. 이 실행이 소유한 아티팩트만 연다.

    묶음 인라인 응답에는 구간만 있고 전문은 아티팩트에 있다. 재사용·부모 실행에서
    가져온 묶음이면 전문이 이 실행 소유가 아니므로 읽을 수 없다고 그대로 알린다.
    """
    try:
        record = store.load_source_body(session, run_id, source_id)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None
    return {"run_id": str(run_id), **record}


@router.post(
    "/results/{result_id}/replays", response_model=ReplayResultResponse
)
def replay_stored_result(
    result_id: UUID,
    payload: ReplayResultRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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


class CompositionRequest(BaseModel):
    """여러 실행의 섹션 결과 버전을 골라 구성본을 만든다."""

    fixture_id: int | None = None
    selected_result_ids: list[UUID] = Field(default_factory=list)
    label: str | None = Field(default=None, max_length=200)


class CompositionResponse(BaseModel):
    composition_id: str
    fixture_id: int | None
    items: list[dict] = Field(default_factory=list)
    refused: list[dict] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    section_result_ids: list[str] = Field(default_factory=list)
    external_calls: int = 0
    note: str


@router.post("/runs/{run_id}/composition", response_model=CompositionResponse)
def create_run_composition(
    run_id: UUID,
    payload: CompositionRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> CompositionResponse:
    """선택한 섹션 결과 버전들을 **이 실행의 구성본**으로 저장한다.

    선택 ID는 각자 **자기 실행**에서 확인하므로 서로 다른 실행의 같은 경기 결과를 함께
    고를 수 있다. 다른 경기·없는 결과·중복 섹션은 조용히 대체하지 않고 `refused`에
    사유와 함께 돌려준다. 이 호출은 모델·HTTP를 쓰지 않는다(외부 호출 0회).
    """
    from app.preview import bundle_pipeline as bundle_pipeline_module

    try:
        detail = store.get_run_detail(session, run_id, include_artifact_bodies=False)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None
    expected_fixture = payload.fixture_id
    if expected_fixture is None and detail.fixture is not None:
        expected_fixture = detail.fixture.fixture_id
    if not payload.selected_result_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "구성본에는 관리자가 고른 섹션 결과 ID가 필요합니다. 서버가 최신 결과를"
                " 임의로 고르지 않습니다."
            ),
        )
    try:
        outcome = bundle_pipeline_module.save_composition(
            session,
            run_id=run_id,
            fixture_id=expected_fixture,
            selected_result_ids=tuple(payload.selected_result_ids),
            actor_id=principal.user_id,
        )
    except bundle_pipeline_module.CompositionRefused as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    session.commit()
    composition = dict(outcome["composition"])
    return CompositionResponse(
        composition_id=str(composition.get("composition_id")),
        fixture_id=composition.get("fixture_id"),
        items=[dict(item) for item in outcome["items"]],
        refused=[dict(item) for item in outcome["refused"]],
        diagnostics=[str(item) for item in outcome["diagnostics"]],
        section_result_ids=[str(item) for item in composition.get("section_result_ids") or ()],
        external_calls=0,
        note=(
            "선택한 결과 버전으로 구성본을 저장했습니다. 모델·외부 호출은 없습니다."
            " 선택되지 않은 결과는 넣지 않았습니다."
        ),
    )


@router.get("/runs/{run_id}/composition")
def get_run_composition(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """이 실행의 구성본. 없으면 빈 구성본을 만들지 않고 사유를 낸다."""
    try:
        record = store.load_composition(session, run_id)
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="run not found"
        ) from None
    return {"run_id": str(run_id), **record}


@router.get("/registry")
def get_registry(
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """보관 정책과 현재 상태. 자동 삭제 스케줄러는 없다."""
    return {
        "policy": retention_policy(),
        "status": retention_summary(session),
    }


@router.post("/retention/expire", response_model=dict)
def run_expiry(
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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
    principal: PreviewPrincipal = Depends(require_preview_admin),
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


# --------------------------------------------------------------------------
# MP-10 전체 프리뷰 실행·재개·모듈 재실행·재종합
# --------------------------------------------------------------------------


class PreviewRunRequest(BaseModel):
    """전체 프리뷰 실행 요청.

    `admission`은 이 실행이 **승인된 버전**으로 도는지, 관리자가 명시적으로 연
    **시험**인지 구분한다. 기본값은 승인 버전이며, 승인이 없으면 실행하지 않고
    대기 상태를 돌려준다. 시험 실행은 승인 근거가 아니다.
    """

    fixture_id: int | None = None
    league_id: int | None = None
    season: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    kickoff_at: datetime | None = None
    mode: str = RunMode.MOCK.value
    admission: str = "approved"
    label: str | None = Field(default=None, max_length=200)
    explicit_rerun: bool = False


class PreviewRunResponse(BaseModel):
    run_id: UUID | None = None
    admission: str
    status: str
    quality: str
    stage: str
    mode: str
    external_calls: int
    joined_existing: bool
    waiting: bool
    waiting_reason: str | None
    unavailable_reason: str | None
    note: str
    budget: dict = Field(default_factory=dict)
    workflow_versions: dict = Field(default_factory=dict)
    section_result_ids: dict = Field(default_factory=dict)
    resume_of_run_id: UUID | None = None


class ModuleRerunRequest(BaseModel):
    module_id: str
    mode: str = RunMode.MOCK.value


class SynthesisRunRequest(BaseModel):
    selected_result_ids: list[UUID] = Field(default_factory=list)
    mode: str = RunMode.MOCK.value


def _pipeline_transport(mode: RunMode):
    """전체 프리뷰용 transport. live는 설정이 있을 때만 열고, 없으면 거부한다."""
    transport = _model_transport(mode)
    if transport is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "모델 설정이 없거나 live 실행이 설정으로 열려 있지 않아 전체 프리뷰를"
                " 시작하지 않았습니다. 모의로 대체하지 않습니다."
            ),
        )
    return transport


def _preview_fixture(payload) -> dict:
    required = (
        payload.fixture_id,
        payload.league_id,
        payload.season,
        payload.home_team_id,
        payload.away_team_id,
        payload.kickoff_at,
    )
    if any(value is None for value in required):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "전체 프리뷰에는 경기 식별자(fixture_id·리그·시즌·팀·킥오프)가"
                " 필요합니다. 경기 선택 화면에서 경기를 고르세요."
            ),
        )
    return {
        "fixture_id": payload.fixture_id,
        "league_id": payload.league_id,
        "season": payload.season,
        "home_team_id": payload.home_team_id,
        "away_team_id": payload.away_team_id,
        "kickoff_at": payload.kickoff_at.isoformat(),
    }


def _admission_response(outcome) -> PreviewRunResponse:
    return PreviewRunResponse(
        run_id=outcome.run_id,
        admission=outcome.admission,
        status=outcome.status.value,
        quality=outcome.quality.value,
        stage=outcome.stage,
        mode=outcome.mode.value,
        external_calls=outcome.external_calls,
        joined_existing=outcome.joined_existing,
        waiting=outcome.waiting_reason is not None,
        waiting_reason=outcome.waiting_reason,
        unavailable_reason=outcome.unavailable_reason,
        note=(
            "승인된 섹션 워크플로우 버전으로 실행한 전체 프리뷰입니다."
            if outcome.admission == "approved"
            else (
                "관리자 명시 시험 실행입니다. 승인 근거가 아니며 공개 프리뷰로"
                " 게시되지 않습니다."
            )
        ),
        budget=dict(outcome.budget),
        workflow_versions=dict(outcome.workflow_versions),
        section_result_ids={
            key: str(value) for key, value in outcome.section_result_ids.items()
        },
        resume_of_run_id=outcome.resume_of_run_id,
    )


class BundlePreviewRunRequest(BaseModel):
    """새 기본 경로(정보 원문 묶음) 전체 프리뷰 실행 요청.

    정상 입력은 **경기 번호 하나**(`fixture_id`)와 `mode='live'`다. 서버가 저장된
    경기에서 리그·시즌·팀·킥오프를 해석하므로 화면이 내부 ID를 만들 필요가 없다.

    과거의 전체 식별자 입력(리그·시즌·팀·킥오프)은 **호환을 위해 계속 받는다.**
    값이 저장된 경기와 다르면 다른 경기를 만들지 않고 422로 거부한다. 값이 없으면
    저장된 값을 쓴다. `mode`는 live만 허용하며, 설정이 없으면 422다(모의 대체 없음).
    """

    fixture_id: int
    # 경기 식별자의 나머지 필드는 선택이다(경기 번호만으로 실행). 주어지면 저장된
    # 경기와 **같은지 확인**하고, 다르면 422다.
    league_id: int | None = None
    season: int | None = None
    home_team_id: int | None = None
    away_team_id: int | None = None
    kickoff_at: datetime | None = None
    mode: str = RunMode.MOCK.value
    label: str | None = Field(default=None, max_length=200)


class BundlePreviewRunResponse(BaseModel):
    run_id: UUID
    mode: str
    status: str
    quality: str
    bundle_id: str | None
    bundle_hash: str | None
    bundle_artifact_id: str | None
    section_result_ids: dict[str, str] = Field(default_factory=dict)
    section_quality: dict[str, str] = Field(default_factory=dict)
    section_unavailable: dict[str, str] = Field(default_factory=dict)
    discovery_status: dict[str, str] = Field(default_factory=dict)
    external_calls: int
    budget: dict = Field(default_factory=dict)
    unavailable_reason: str | None = None
    note: str


@router.post("/bundle-runs", response_model=BundlePreviewRunResponse)
def create_bundle_preview_run(
    payload: BundlePreviewRunRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> BundlePreviewRunResponse:
    """경기 번호 하나로 전체 프리뷰를 **한 번** 생성하고 저장한다.

    계약:

    - 입력은 `fixture_id`(API-Football 외부 번호)와 `mode='live'`다. 서버가 저장된
      경기에서 리그·시즌·팀·킥오프를 해석한다.
    - 서로 다른 경기를 만들지 않는다. 저장된 경기와 **다른 값**이 함께 오면 422다.
      번호가 저장 자료에 없으면 404, 저장 자료를 읽을 수 없으면 503이며, 두 경우
      모두 모델 전송은 0회다.
    - 재시도 의미는 **각 논리 AI 모듈의 최초 포함 최대 3회**다(전체 8회 제한 없음).
    - 응답은 기존 `BundlePreviewRunResponse`이며 `run_id`로 저장 결과를 다시 읽는다.
      본문·근거는 `/runs/{run_id}/section-results`, 묶음은
      `/runs/{run_id}/information-bundle`에서 **DB만** 조회한다.
    """
    from app.services import match_preview as service

    try:
        mode = RunMode(payload.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown run mode"
        ) from None
    if mode is RunMode.REPLAY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "저장 응답 재생은 결과 단위 재변환 경로를 씁니다. 전체 실행의 재생 모드는"
                " 열지 않았습니다."
            ),
        )
    if mode is not RunMode.LIVE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "새 정보 원문 경로는 실제 모델 호출이 필요합니다. 모의 실행은"
                " 섹션 단위 시험(/section-runs)으로 화면을 확인하고, 이 경로는"
                " live로 실행하세요. 모의 응답을 만들어 본문을 채우지 않습니다."
            ),
        )
    transport = _model_transport(mode)
    if transport is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "모델 설정이 없거나 PREVIEW_MODEL_LIVE_ENABLED가 꺼져 있어 live 실행을"
                " 열지 않았습니다. 모의로 대체하지 않습니다."
            ),
        )

    reader = _fixture_reader()
    # 완전 식별자 입력은 **저장된 경기와 대조**한다. 다르면 다른 경기를 만들지 않는다.
    _refuse_conflicting_fixture_identifiers(payload, reader=reader)

    try:
        outcome = service.generate_match_preview(
            fixture_id=int(payload.fixture_id),
            actor_id=principal.user_id,
            trigger="admin",
            session=session,
            transport=transport,
            reader=reader,
            label=payload.label,
            mode=mode,
        )
    except service.FixtureResolutionError as exc:
        raise HTTPException(
            status_code=exc.status_hint or status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from None
    finally:
        close = getattr(reader, "close", None)
        if callable(close):
            close()
    session.commit()
    return BundlePreviewRunResponse(
        run_id=outcome.run_id,
        mode=outcome.mode.value,
        status=outcome.status.value,
        quality=outcome.quality.value,
        bundle_id=outcome.bundle_id,
        bundle_hash=outcome.bundle_hash,
        bundle_artifact_id=outcome.bundle_artifact_id,
        section_result_ids=dict(outcome.section_result_ids),
        section_quality=dict(outcome.section_quality),
        section_unavailable=dict(outcome.section_unavailable),
        discovery_status=dict(outcome.discovery_status),
        external_calls=outcome.external_calls,
        budget=dict(outcome.budget),
        unavailable_reason=outcome.unavailable_reason,
        note=(
            # `quality`/`status`는 **기술 실행·저장 사실**이다. 본문 표시·재전송의
            # 품질 문턱으로 쓰지 않는다. 글의 성공 판단은 사용자가 한다.
            "실행·저장 결과입니다. 섹션 본문과 근거는"
            f" /runs/{outcome.run_id}/section-results, 묶음은"
            f" /runs/{outcome.run_id}/information-bundle에서 확인하세요."
            " 부분 본문도 저장되며, 내용의 성공 여부는 자동 판정하지 않습니다."
        ),
    )


def _refuse_conflicting_fixture_identifiers(
    payload: "BundlePreviewRunRequest", *, reader: Any = None
) -> None:
    """이전 전체 식별자 입력이 **저장된 경기와 충돌**하면 422로 거부한다.

    관리자 화면은 번호만 보낸다. 과거 입력(리그·시즌·팀·킥오프)을 계속 받되, 저장된
    경기와 다른 값을 보내면 다른 경기를 만들지 않고 멈춘다. 저장 자료가 없으면
    해석 단계에서 503/404로 처리하므로 여기서는 비교만 한다.
    """
    supplied = {
        "league_id": payload.league_id,
        "season": payload.season,
        "home_team_id": payload.home_team_id,
        "away_team_id": payload.away_team_id,
        "kickoff_at": payload.kickoff_at,
    }
    if all(value is None for value in supplied.values()):
        return
    opener = reader if reader is not None else _fixture_reader()
    if opener is None:
        return
    borrowed = reader is None
    try:
        access = opener.access()
        if not getattr(access, "readable", False):
            return
        record = opener.get_fixture(fixture_id=int(payload.fixture_id))
    except Exception:  # noqa: BLE001 - 해석 실패는 service가 정확한 상태로 보고한다
        return
    finally:
        if borrowed:
            close = getattr(opener, "close", None)
            if callable(close):
                close()
    if record is None:
        return
    conflicts: list[str] = []
    for key, value in supplied.items():
        if value is None:
            continue
        if key == "kickoff_at":
            assert payload.kickoff_at is not None
            incoming = payload.kickoff_at
            stored_dt = record.kickoff_at
            if incoming.tzinfo is None:
                incoming = incoming.replace(tzinfo=stored_dt.tzinfo)
            if incoming.astimezone(stored_dt.tzinfo) != stored_dt:
                conflicts.append(f"{key}={payload.kickoff_at.isoformat()}")
            continue
        if int(value) != int(getattr(record, key)):
            conflicts.append(f"{key}={value}")
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"요청한 경기 식별자({', '.join(conflicts)})가 저장된 경기"
                f" {record.fixture_id}의 값과 다릅니다. 다른 경기를 만들지 않습니다."
            ),
        )


@router.post("/runs", response_model=PreviewRunResponse)
def create_preview_run(
    payload: PreviewRunRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> PreviewRunResponse:
    """전체 프리뷰를 시작한다. 승인이 없으면 실행하지 않고 대기 상태를 돌려준다."""
    from app.preview import jobs as jobs_module
    from app.preview import pipeline as pipeline_module

    try:
        mode = RunMode(payload.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown run mode"
        ) from None
    if payload.admission not in (
        jobs_module.ADMISSION_MODE.APPROVED,
        jobs_module.ADMISSION_MODE.ADMIN_PREVIEW,
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="admission은 approved 또는 admin_preview만 쓸 수 있습니다.",
        )
    fixture = _preview_fixture(payload)
    transport = _pipeline_transport(mode)
    try:
        outcome = pipeline_module.start_preview_run(
            session,
            fixture=fixture,
            actor_id=principal.user_id,
            transport=transport,
            reader=_fixture_reader(),
            admission=payload.admission,
            mode=mode,
            label=payload.label,
            explicit_rerun=payload.explicit_rerun,
        )
    except pipeline_module.AdmissionRefused as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": exc.message,
                "missing": list(exc.missing),
                "state": pipeline_module.admission_state(session),
            },
        ) from None
    session.commit()
    return _admission_response(outcome)


@router.post("/runs/{run_id}/resume", response_model=PreviewRunResponse)
def resume_preview_run(
    run_id: UUID,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> PreviewRunResponse:
    """멈춘 전체 프리뷰를 남은 예산으로 이어서 돈다. 성공한 조사는 다시 부르지 않는다."""
    from app.preview import pipeline as pipeline_module

    detail = _detail_or_404(session, run_id)
    mode = RunMode(detail["summary"]["mode"])
    transport = _pipeline_transport(mode)
    try:
        outcome = pipeline_module.resume_preview_run(
            session,
            run_id=run_id,
            actor_id=principal.user_id,
            transport=transport,
            reader=_fixture_reader(),
        )
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="preview run not found"
        ) from None
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from None
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    session.commit()
    return _admission_response(outcome)


@router.post("/runs/{run_id}/module-reruns", response_model=PreviewRunResponse)
def rerun_preview_module(
    run_id: UUID,
    payload: ModuleRerunRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> PreviewRunResponse:
    """조사 모듈 하나를 새 결과 버전으로 다시 돈다. 다른 결과는 지우지 않는다."""
    from app.preview import pipeline as pipeline_module

    try:
        mode = RunMode(payload.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown run mode"
        ) from None
    transport = _pipeline_transport(mode)
    try:
        outcome = pipeline_module.rerun_module(
            session,
            run_id=run_id,
            module_id=payload.module_id,
            actor_id=principal.user_id,
            transport=transport,
            reader=_fixture_reader(),
        )
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="preview run not found"
        ) from None
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    session.commit()
    return _admission_response(outcome)


@router.post("/runs/{run_id}/synthesis-runs", response_model=PreviewRunResponse)
def rerun_preview_synthesis(
    run_id: UUID,
    payload: SynthesisRunRequest,
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> PreviewRunResponse:
    """관리자가 고른 결과 버전으로 종합만 다시 한다. 선택 없이는 실행하지 않는다."""
    from app.preview import pipeline as pipeline_module

    try:
        mode = RunMode(payload.mode)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown run mode"
        ) from None
    transport = _pipeline_transport(mode)
    try:
        outcome = pipeline_module.resynthesize_preview(
            session,
            run_id=run_id,
            actor_id=principal.user_id,
            selected_result_ids=tuple(payload.selected_result_ids),
            transport=transport,
        )
    except store.RunNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="preview run not found"
        ) from None
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None
    except RuntimeError as exc:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    session.commit()
    return _admission_response(outcome)


@router.get("/admission")
def get_admission_state(
    session: Session = Depends(get_db),
    principal: PreviewPrincipal = Depends(require_preview_admin),
) -> dict:
    """지금 코드로 기본 전체 프리뷰를 돌릴 수 있는지. 저장된 승인 행만 읽는다."""
    from app.preview import pipeline as pipeline_module

    return pipeline_module.admission_state(session)
