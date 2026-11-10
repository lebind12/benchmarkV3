"""MP-10 전체 프리뷰 실행의 작업 소유·진행·예산 상태 (DB 계층).

이 파일이 책임지는 것:

- 실행 하나의 **진행 상태**(stage·남은 단계·완료 단계)를 DB에 남긴다.
- **작업 소유권**을 임차(lease)로 관리하고, 소유권이 바뀔 때마다 올라가는
  `fencing_token`으로 오래된 실행자의 쓰기를 막는다.
- 같은 경기·입력·버전 조합의 진행 중 요청이 오면 **기존 실행에 붙인다**(중복 방지).
- 남은 예산을 저장해 재개가 이어지게 한다.

이 파일이 책임지지 않는 것:

- 그래프 실행·노드 순서(LangGraph)와 결과 저장(`store`). 그 둘은 `pipeline`이 맡는다.
- 새 스케줄러·큐·워커 프로세스. 동시 실행은 같은 프로세스의 스레드로 충분하다.

정직성 규칙:

- 외부 호출의 **정확히 한 번 실행**을 보장하지 않는다. 울타리(fencing)는 "오래된
  실행자가 저장을 덮어쓰지 못하게" 막는 장치이고, 제공자 쪽 중복 실행을 되돌리지
  못한다. 전송 뒤 응답 보존 전에 멈춘 시도는 `unknown`으로 남는다(기존 기록 계약).
- 만료되지 않은 임차를 빼앗지 않는다. 그래서 동시에 두 실행자가 같은 실행을
  갱신하지 않는다.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.preview.models import PreviewPipelineRun

__all__ = [
    "ADMISSION_MODE",
    "DEFAULT_LEASE_SECONDS",
    "PipelineRunState",
    "claim_lease",
    "dedup_key",
    "find_active_run",
    "finish_pipeline",
    "load_state",
    "mark_waiting",
    "new_pipeline_run",
    "save_progress",
    "set_active",
]


class ADMISSION_MODE:
    """이 실행이 어떤 근거로 승인됐는지. 화면·기록에 그대로 노출한다."""

    # 승인된 섹션 워크플로우 버전으로 도는 기본 전체 프리뷰.
    APPROVED = "approved"
    # 승인이 없지만 관리자가 명시적으로 연 시험 실행. 승인 근거가 아니다.
    ADMIN_PREVIEW = "admin_preview"


DEFAULT_LEASE_SECONDS = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clone(value: Any) -> Any:
    """JSONB에 넣을 기본형. 매핑·시퀀스를 그대로 두지 않는다."""
    if isinstance(value, Mapping):
        return {str(key): _clone(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clone(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value


@dataclass(frozen=True)
class PipelineRunState:
    """한 실행의 작업 상태 스냅샷. 화면·API가 그대로 쓴다."""

    run_id: uuid.UUID
    dedup_key: str
    active: bool
    admission: str
    stage: str
    pending_nodes: tuple[str, ...]
    completed_nodes: tuple[str, ...]
    owner_id: str | None
    lease_expires_at: datetime | None
    fencing_token: int
    budget_state: dict[str, Any]
    deadline_at: datetime | None
    waiting_reason: str | None
    failure_code: str | None
    failure_detail: str | None
    workflow_versions: dict[str, Any]
    selected_result_ids: tuple[str, ...]
    resume_of_run_id: uuid.UUID | None
    rerun_of_run_id: uuid.UUID | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "dedup_key": self.dedup_key,
            "active": self.active,
            "admission": self.admission,
            "stage": self.stage,
            "pending_nodes": list(self.pending_nodes),
            "completed_nodes": list(self.completed_nodes),
            "owner_id": self.owner_id,
            "lease_expires_at": self.lease_expires_at.isoformat()
            if self.lease_expires_at
            else None,
            "fencing_token": self.fencing_token,
            "budget_state": dict(self.budget_state),
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "waiting_reason": self.waiting_reason,
            "failure_code": self.failure_code,
            "failure_detail": self.failure_detail,
            "workflow_versions": dict(self.workflow_versions),
            "selected_result_ids": list(self.selected_result_ids),
            "resume_of_run_id": str(self.resume_of_run_id) if self.resume_of_run_id else None,
            "rerun_of_run_id": str(self.rerun_of_run_id) if self.rerun_of_run_id else None,
        }


def _state(row: PreviewPipelineRun) -> PipelineRunState:
    return PipelineRunState(
        run_id=row.id,
        dedup_key=row.dedup_key,
        active=bool(row.active),
        admission=row.admission,
        stage=row.stage,
        pending_nodes=tuple(row.pending_nodes or ()),
        completed_nodes=tuple(row.completed_nodes or ()),
        owner_id=row.owner_id,
        lease_expires_at=row.lease_expires_at,
        fencing_token=int(row.fencing_token or 0),
        budget_state=dict(row.budget_state or {}),
        deadline_at=row.deadline_at,
        waiting_reason=row.waiting_reason,
        failure_code=row.failure_code,
        failure_detail=row.failure_detail,
        workflow_versions=dict(row.workflow_versions or {}),
        selected_result_ids=tuple(row.selected_result_ids or ()),
        resume_of_run_id=row.resume_of_run_id,
        rerun_of_run_id=row.rerun_of_run_id,
    )


def dedup_key(
    *,
    fixture: Mapping[str, Any] | None,
    snapshot_ids: Sequence[str],
    versions: Mapping[str, str],
) -> str:
    """같은 조합인지 판정하는 키. 경기·입력 스냅샷·모델/프롬프트/구현 버전.

    진행 중 중복 요청을 합치는 용도이며, 결과 동일성을 주장하는 해시가 아니다.
    그래서 값은 정렬해 순서 차이로 키가 갈리지 않게 한다.
    """
    fixture_id = None
    if isinstance(fixture, Mapping):
        fixture_id = fixture.get("fixture_id")
    payload = {
        "fixture_id": str(fixture_id) if fixture_id is not None else None,
        "snapshot_ids": sorted(str(item) for item in snapshot_ids),
        "versions": {str(k): str(v) for k, v in sorted(versions.items())},
    }
    serialized = "|".join(
        [
            f"fixture={payload['fixture_id']}",
            f"snapshots={','.join(payload['snapshot_ids'])}",
            "versions=" + ",".join(f"{k}={v}" for k, v in payload["versions"].items()),
        ]
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def find_active_run(session: Session, key: str) -> PreviewPipelineRun | None:
    """진행 중인 같은 조합의 실행. 없으면 `None`. 저장된 행만 읽는다."""
    return session.scalar(
        select(PreviewPipelineRun).where(
            PreviewPipelineRun.dedup_key == key,
            PreviewPipelineRun.active.is_(True),
        )
    )


def new_pipeline_run(
    session: Session,
    *,
    run_id: uuid.UUID,
    key: str,
    admission: str,
    pending_nodes: Sequence[str],
    workflow_versions: Mapping[str, Any],
    budget_state: Mapping[str, Any],
    deadline_at: datetime | None,
    selected_result_ids: Sequence[str] = (),
    resume_of_run_id: uuid.UUID | None = None,
    rerun_of_run_id: uuid.UUID | None = None,
    now: datetime | None = None,
) -> PipelineRunState:
    """실행의 작업 상태 행을 만든다. 실행 기록(`preview_runs`)은 호출자가 먼저 만든다."""
    row = PreviewPipelineRun(
        id=run_id,
        dedup_key=key,
        active=True,
        resume_of_run_id=resume_of_run_id,
        rerun_of_run_id=rerun_of_run_id,
        admission=admission,
        workflow_versions=_clone(dict(workflow_versions)),
        selected_result_ids=[str(item) for item in selected_result_ids],
        stage="created",
        pending_nodes=[str(node) for node in pending_nodes],
        completed_nodes=[],
        fencing_token=0,
        budget_state=_clone(dict(budget_state)),
        deadline_at=deadline_at,
        created_at=now or _now(),
        updated_at=now or _now(),
    )
    session.add(row)
    session.flush()
    return _state(row)


def claim_lease(
    session: Session,
    *,
    run_id: uuid.UUID,
    owner_id: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> int | None:
    """이 실행의 작업 소유권을 가져온다. 성공하면 새 `fencing_token`, 아니면 `None`.

    같은 소유자가 다시 부르면 연장된다(토큰도 올라간다). 만료되지 않은 다른 소유자의
    임차는 빼앗지 않는다.
    """
    moment = now or _now()
    expiry = moment + timedelta(seconds=lease_seconds)
    result = session.execute(
        update(PreviewPipelineRun)
        .where(
            PreviewPipelineRun.id == run_id,
            (PreviewPipelineRun.owner_id.is_(None))
            | (PreviewPipelineRun.owner_id == owner_id)
            | (PreviewPipelineRun.lease_expires_at.is_(None))
            | (PreviewPipelineRun.lease_expires_at < moment),
        )
        .values(
            owner_id=owner_id,
            lease_expires_at=expiry,
            fencing_token=PreviewPipelineRun.fencing_token + 1,
            updated_at=moment,
        )
    )
    session.flush()
    if result.rowcount != 1:
        return None
    return int(
        session.scalar(
            select(PreviewPipelineRun.fencing_token).where(
                PreviewPipelineRun.id == run_id
            )
        )
        or 0
    )


def save_progress(
    session: Session,
    *,
    run_id: uuid.UUID,
    fencing_token: int,
    stage: str | None = None,
    completed_nodes: Sequence[str] | None = None,
    pending_nodes: Sequence[str] | None = None,
    budget_state: Mapping[str, Any] | None = None,
    waiting_reason: str | None = None,
    now: datetime | None = None,
) -> bool:
    """진행 상태를 저장한다. **울타리 토큰이 최신일 때만** 반영한다.

    반환값이 `False`면 그 쓰기는 버려졌다는 뜻이다(오래된 실행자).
    """
    values: dict[str, Any] = {"updated_at": now or _now()}
    if stage is not None:
        values["stage"] = stage
    if completed_nodes is not None:
        values["completed_nodes"] = [str(node) for node in completed_nodes]
    if pending_nodes is not None:
        values["pending_nodes"] = [str(node) for node in pending_nodes]
    if budget_state is not None:
        values["budget_state"] = _clone(dict(budget_state))
    if waiting_reason is not None:
        values["waiting_reason"] = waiting_reason

    result = session.execute(
        update(PreviewPipelineRun)
        .where(
            PreviewPipelineRun.id == run_id,
            PreviewPipelineRun.fencing_token == fencing_token,
        )
        .values(**values)
    )
    session.flush()
    return result.rowcount == 1


def mark_waiting(
    session: Session,
    *,
    run_id: uuid.UUID,
    reason: str,
    pending_nodes: Sequence[str] | None = None,
    now: datetime | None = None,
) -> None:
    """승인·설정 대기로 멈춘 상태. 실패와 구분해 남긴다(`active`는 유지)."""
    values: dict[str, Any] = {
        "stage": "waiting_for_approval",
        "waiting_reason": reason,
        "updated_at": now or _now(),
    }
    if pending_nodes is not None:
        values["pending_nodes"] = [str(node) for node in pending_nodes]
    session.execute(
        update(PreviewPipelineRun).where(PreviewPipelineRun.id == run_id).values(**values)
    )
    session.flush()


def finish_pipeline(
    session: Session,
    *,
    run_id: uuid.UUID,
    fencing_token: int,
    stage: str,
    failure_code: str | None = None,
    failure_detail: str | None = None,
    keep_active: bool = False,
    now: datetime | None = None,
) -> bool:
    """종료 상태를 원자적으로 확정한다.

    성공·실패 모두 `active=false`로 내려 중복 방지 키를 풀어 준다. 그래야 같은
    경기의 다음 요청이 새 실행을 만들 수 있다(오래된 실행을 덮어쓰지 않는다).
    실패는 `failure_code`로 남기고 성공으로 바꾸지 않는다.
    """
    values: dict[str, Any] = {
        "stage": stage,
        "updated_at": now or _now(),
        "pending_nodes": [],
    }
    if not keep_active:
        values["active"] = False
    if failure_code is not None:
        values["failure_code"] = failure_code
    if failure_detail is not None:
        values["failure_detail"] = failure_detail
    result = session.execute(
        update(PreviewPipelineRun)
        .where(
            PreviewPipelineRun.id == run_id,
            PreviewPipelineRun.fencing_token == fencing_token,
        )
        .values(**values)
    )
    session.flush()
    return result.rowcount == 1


def set_active(session: Session, *, run_id: uuid.UUID, active: bool) -> None:
    session.execute(
        update(PreviewPipelineRun)
        .where(PreviewPipelineRun.id == run_id)
        .values(active=active, updated_at=_now())
    )
    session.flush()


def load_state(session: Session, run_id: uuid.UUID) -> PipelineRunState | None:
    """저장된 작업 상태. 없으면 `None`(전체 실행이 아닌 실행)."""
    row = session.get(PreviewPipelineRun, run_id)
    return _state(row) if row is not None else None
