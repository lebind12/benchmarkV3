"""관리자 전용 실행 목록.

MP-01에서는 실행 기록 저장소가 아직 없다. 그래서 실제로 읽을 수 있는 것이
없다는 사실을 그대로 빈 목록으로 돌려주고, 가짜 통계로 채우지 않는다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.service import AdminPrincipal, require_preview_admin

router = APIRouter(prefix="/api/v1/admin/preview", tags=["preview-admin"])


class RunListResponse(BaseModel):
    runs: list[dict]
    next_cursor: str | None = None


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    principal: AdminPrincipal = Depends(require_preview_admin),
) -> RunListResponse:
    return RunListResponse(runs=[], next_cursor=None)
