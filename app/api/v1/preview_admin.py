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

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.service import AdminPrincipal, require_preview_admin
from app.db import get_db
from app.preview import demo_pipeline, store
from app.preview.contracts import ContractError, RunMode
from app.preview.inspection import build_run_inspection
from app.preview.models import PreviewRun
from app.preview.registry import describe_registry
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
    return build_run_inspection(detail.to_dict())


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


@router.get("/registry")
def get_registry(
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> dict:
    """등록된 모듈과 구현 여부. 미구현 모듈을 실행 가능으로 보이지 않게 한다."""
    return describe_registry()


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
