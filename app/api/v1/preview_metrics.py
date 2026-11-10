"""관리자 운영 지표 API (MP-08).

경계:

- 모든 경로는 `require_preview_admin`으로 서버에서 ADMIN만 통과시킨다. 화면 숨김은
  권한이 아니다. 비인증 401, 인증된 비ADMIN 403이다.
- 이 라우터는 **읽기만** 한다. 저장된 실행·모듈 실행·시도·결과 행을 집계할 뿐
  실행을 만들거나 지우지 않고, 외부 모델·API를 호출하지 않는다. 제공자 클라이언트나
  HTTP 전송 계층을 import하지 않는다.
- 기본 조회는 운영(prod)·실호출(live)만 집계한다. 개발·모의·재생 기록은 환경·실행
  방식 필터를 명시했을 때만 나타나고, 걸러낸 건수는 응답의 `excluded`에 드러낸다.
- 경기 목록 수집(`fixture_catalog`)과 모듈 단독 실행(`module`)은 전체 프리뷰 완료율과
  섞지 않는다. 전자는 지표 대상에서 빠지고, 후자는 별도 범위로 표시한다.
- 없는 값은 0으로 채우지 않는다. 표본이 없는 지표는 `available=false`와 사유로,
  제공자가 주지 않은 사용량은 `null`과 누락 건수로 남긴다. 비용은 미확인(`null`)이다.

앱 연결은 공유 파일 소유자인 MP-04 통합 담당자가 `app/main.py`에서
`app.include_router(preview_metrics.router)` 한 줄로 추가한다. frontend 경로·메뉴
연결도 같은 소유자다. 이 파일의 prefix는 이미 `/api/v1/admin/preview`다.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth.service import AdminPrincipal, require_preview_admin
from app.db import get_db
from app.preview.contracts import Environment, MetricsQuery, RunMode
from app.preview.metrics import METRIC_VERSION, MetricsQueryError, query_metrics

router = APIRouter(prefix="/api/v1/admin/preview", tags=["preview-metrics"])

__all__ = ["router", "metrics"]


def _parse_environments(values: list[str]) -> tuple[Environment, ...]:
    parsed: list[Environment] = []
    for raw in values:
        try:
            parsed.append(Environment(raw))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown environment: {raw}",
            ) from None
    return tuple(dict.fromkeys(parsed))


def _parse_modes(values: list[str]) -> tuple[RunMode, ...]:
    parsed: list[RunMode] = []
    for raw in values:
        try:
            parsed.append(RunMode(raw))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown mode: {raw}",
            ) from None
    return tuple(dict.fromkeys(parsed))


@router.get("/metrics")
def metrics(
    session: Session = Depends(get_db),
    principal: AdminPrincipal = Depends(require_preview_admin),
    from_at: datetime | None = Query(default=None, description="집계 시작 시각(포함, ISO8601)"),
    to_at: datetime | None = Query(default=None, description="집계 종료 시각(미포함, ISO8601)"),
    environment: list[str] = Query(default_factory=list),
    mode: list[str] = Query(default_factory=list),
    module_id: list[str] = Query(default_factory=list),
    model: list[str] = Query(default_factory=list),
    contract_version: list[str] = Query(default_factory=list),
    metric: list[str] = Query(
        default_factory=list,
        description="원하는 지표만 골라 받는다. 비우면 전체를 돌려준다.",
    ),
) -> dict[str, Any]:
    """저장된 기록만으로 운영 지표를 집계한다.

    분모와 표본 수를 그대로 돌려주고, 각 지표에 내려갈 실행 ID(`detail_run_ids`)와
    실행·모듈 실행·시도 목록(`runs`)을 함께 담는다. 그래서 화면이 지표에서 해당
    실행의 시도 원문으로 이동할 수 있다.
    """
    query = MetricsQuery(
        from_at=from_at,
        to_at=to_at,
        environments=_parse_environments(environment),
        modes=_parse_modes(mode),
        module_ids=tuple(m for m in module_id if m),
        models=tuple(m for m in model if m),
        contract_versions=tuple(v for v in contract_version if v),
    )
    try:
        report = query_metrics(session, query)
    except MetricsQueryError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from None

    payload = report.to_dict()
    wanted = {m for m in metric if m}
    if wanted:
        known = {row.metric for row in report.rows}
        unknown = wanted - known
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown metric: {', '.join(sorted(unknown))}",
            )
        payload["rows"] = [row for row in payload["rows"] if row["metric"] in wanted]
    payload["metric_version"] = METRIC_VERSION
    payload["read_only"] = True
    payload["note"] = (
        "저장된 실행 기록만 읽은 지표입니다. 이 조회는 외부 모델·API를 호출하지 않으며, "
        "모의·재생 기록은 환경·실행 방식 필터를 지정했을 때만 나타납니다."
    )
    return payload
