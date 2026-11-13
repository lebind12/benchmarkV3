"""실행 기록 저장소.

계약(§2)과 계획 §6의 인터페이스:

- `store_run`: 실행 한 건을 만든다.
- `append_attempt`: 논리 호출의 실제 시도 한 건을 덧붙인다.
- `save_module_result`: 모듈 결과의 새 버전을 저장한다. 이전 버전을 덮어쓰지 않는다.
- `get_run_detail`: 저장된 행만 읽어 상세를 만든다. 외부 호출이 없다.
- `compare_result_versions`: 같은 모듈 실행의 두 결과 버전을 비교한다.

조회 경로는 어떤 경우에도 제공자를 부르지 않는다. 이 모듈은 `httpx`·제공자
클라이언트를 import하지 않는다. 그 사실은 `test_read_does_not_call_provider`가
전송 계층을 감시해 확인한다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.preview import artifacts as artifact_store
from app.preview.contracts import (
    ContractError,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FailureCode,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    OperationKind,
    QualityStatus,
    RunDetail,
    RunMode,
    RunStatus,
    RunSummary,
    SourceKind,
    ValidationStatus,
    contract_versions,
)
from app.preview.models import (
    PreviewArtifact,
    PreviewAttempt,
    PreviewModuleExecution,
    PreviewResult,
    PreviewRun,
    PreviewSectionResult,
    PreviewSourceSnapshot,
    PreviewWriteAudit,
)

__all__ = [
    "BUNDLE_RECORD_TYPE",
    "COMPOSITION_RECORD_TYPE",
    "append_attempt",
    "cancel_run",
    "compare_result_versions",
    "get_module_execution",
    "get_run_detail",
    "get_section_result",
    "get_section_result_any_run",
    "list_runs",
    "load_information_bundle",
    "load_source_body",
    "save_composition",
    "load_composition",
    "save_information_bundle",
    "save_information_bundle_with_bodies",
    "list_section_results",
    "record_source_snapshot",
    "save_module_result",
    "save_section_result",
    "start_module_execution",
    "store_run",
    "undo_report",
    "update_module_delivery",
    "WriteConflict",
    "RunNotFound",
]


class RunNotFound(LookupError):
    pass


class WriteConflict(RuntimeError):
    """실행 취소가 다른 실행의 후속 변경과 충돌한다."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fixture_columns(fixture: FixtureIdentity | None) -> dict[str, Any]:
    if fixture is None:
        return {
            "fixture_id": None,
            "league_id": None,
            "season": None,
            "home_team_id": None,
            "away_team_id": None,
            "kickoff_at": None,
        }
    return {
        "fixture_id": fixture.fixture_id,
        "league_id": fixture.league_id,
        "season": fixture.season,
        "home_team_id": fixture.home_team_id,
        "away_team_id": fixture.away_team_id,
        "kickoff_at": fixture.kickoff_at,
    }


def _fixture_from_row(row: PreviewRun) -> FixtureIdentity | None:
    if row.fixture_id is None or row.kickoff_at is None:
        return None
    return FixtureIdentity(
        fixture_id=row.fixture_id,
        league_id=int(row.league_id or 0),
        season=int(row.season or 0),
        home_team_id=int(row.home_team_id or 0),
        away_team_id=int(row.away_team_id or 0),
        kickoff_at=row.kickoff_at,
    )


def _audit(
    session: Session,
    *,
    run_id: uuid.UUID,
    actor_id: int,
    action: str,
    target_table: str,
    target_id: str | None = None,
    detail: Mapping[str, Any] | None = None,
) -> None:
    session.add(
        PreviewWriteAudit(
            run_id=run_id,
            actor_id=actor_id,
            action=action,
            target_table=target_table,
            target_id=target_id,
            detail=dict(detail or {}),
        )
    )


# --------------------------------------------------------------------------
# 쓰기
# --------------------------------------------------------------------------


def store_run(
    session: Session,
    context: ExecutionContext,
    *,
    fixture: FixtureIdentity | None = None,
    fixture_label: str | None = None,
    label: str | None = None,
    quality: QualityStatus = QualityStatus.PENDING,
    status: RunStatus = RunStatus.RUNNING,
    write_scope: str = "preview_dev",
) -> PreviewRun:
    """실행 한 건을 만든다. 실행 ID는 호출자가 정한 문맥의 값을 그대로 쓴다."""
    if context.environment is Environment.PROD and context.mode is not RunMode.LIVE:
        raise ContractError(
            "a production environment record must be a live run; "
            "mock and replay records belong to dev or test"
        )
    existing = session.get(PreviewRun, context.run_id)
    if existing is not None:
        raise ContractError(f"run {context.run_id} already exists")

    row = PreviewRun(
        id=context.run_id,
        operation_kind=context.operation_kind.value,
        environment=context.environment.value,
        mode=context.mode.value,
        status=status.value,
        quality=quality.value,
        actor_id=context.actor_id,
        config_version=context.config_version,
        limits=context.limits.to_dict(),
        contract_versions=contract_versions(),
        fixture_label=fixture_label,
        label=label,
        write_scope=write_scope,
        started_at=_now(),
        **_fixture_columns(fixture),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        run_id=row.id,
        actor_id=context.actor_id,
        action="run_created",
        target_table="preview_runs",
        target_id=str(row.id),
        detail={"mode": row.mode, "environment": row.environment},
    )
    return row


def start_module_execution(
    session: Session,
    *,
    run_id: uuid.UUID,
    module_id: str,
    module_input: ModuleInput,
    ordinal: int = 0,
    status: ModuleStatus = ModuleStatus.RUNNING,
    quality: QualityStatus = QualityStatus.PENDING,
    actor_id: int = 0,
) -> PreviewModuleExecution:
    row = PreviewModuleExecution(
        run_id=run_id,
        module_id=module_id,
        ordinal=ordinal,
        status=status.value,
        quality=quality.value,
        input_payload=module_input.to_dict(),
        input_hash=module_input.input_hash,
        delivered_next_input={},
        started_at=_now(),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        run_id=run_id,
        actor_id=actor_id,
        action="module_started",
        target_table="preview_module_executions",
        target_id=str(row.id),
        detail={"module_id": module_id},
    )
    return row


def update_module_delivery(
    session: Session,
    module_execution_id: uuid.UUID,
    delivered: Mapping[str, Any],
    *,
    status: ModuleStatus | None = None,
    quality: QualityStatus | None = None,
    failure_code: FailureCode | None = None,
) -> PreviewModuleExecution:
    """다음 단계로 넘긴 값을 기록한다. 입력·전달값은 검사 화면의 '다음 입력' 탭이다."""
    row = session.get(PreviewModuleExecution, module_execution_id)
    if row is None:
        raise RunNotFound(f"module execution {module_execution_id} not found")
    row.delivered_next_input = dict(delivered)
    if status is not None:
        row.status = status.value
    if quality is not None:
        row.quality = quality.value
    if failure_code is not None:
        row.failure_code = failure_code.value
    if status is not None and status in (
        ModuleStatus.SUCCEEDED,
        ModuleStatus.FAILED,
    ):
        row.finished_at = _now()
    session.flush()
    return row


def append_attempt(
    session: Session,
    *,
    run_id: uuid.UUID,
    logical_call_id: str,
    attempt_ordinal: int,
    provider: str,
    mode: RunMode,
    outcome: str,
    request_spec: Mapping[str, Any],
    module_execution_id: uuid.UUID | None = None,
    module_id: str | None = None,
    model: str | None = None,
    operation: str = "",
    http_status: int | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    request_artifact_id: uuid.UUID | None = None,
    response_artifact_id: uuid.UUID | None = None,
    usage: Mapping[str, Any] | None = None,
    wait_ms: int | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    actor_id: int = 0,
) -> PreviewAttempt:
    """시도 한 건을 남긴다. 재시도는 같은 `logical_call_id`의 다음 순번이다."""
    row = PreviewAttempt(
        run_id=run_id,
        module_execution_id=module_execution_id,
        module_id=module_id,
        logical_call_id=logical_call_id,
        attempt_ordinal=attempt_ordinal,
        provider=provider,
        model=model,
        mode=mode.value,
        operation=operation,
        outcome=outcome,
        http_status=http_status,
        error_class=error_class,
        error_message=error_message,
        request_spec=dict(request_spec),
        request_artifact_id=request_artifact_id,
        response_artifact_id=response_artifact_id,
        usage=dict(usage) if usage is not None else None,
        wait_ms=wait_ms,
        started_at=started_at or _now(),
        finished_at=finished_at or _now(),
    )
    session.add(row)
    session.flush()

    if module_execution_id is not None:
        execution = session.get(PreviewModuleExecution, module_execution_id)
        if execution is not None:
            execution.attempt_count = int(execution.attempt_count or 0) + 1
            if attempt_ordinal > 0:
                execution.retry_count = int(execution.retry_count or 0) + 1

    _audit(
        session,
        run_id=run_id,
        actor_id=actor_id,
        action="attempt_appended",
        target_table="preview_attempts",
        target_id=str(row.id),
        detail={
            "logical_call_id": logical_call_id,
            "attempt_ordinal": attempt_ordinal,
            "outcome": outcome,
            "http_status": http_status,
        },
    )
    return row


def record_source_snapshot(
    session: Session,
    *,
    run_id: uuid.UUID,
    source_kind: SourceKind,
    provider: str,
    collected_at: datetime,
    validation_status: ValidationStatus,
    attempt_id: uuid.UUID | None = None,
    fixture: FixtureIdentity | None = None,
    catalog_query: Mapping[str, Any] | None = None,
    provider_updated_at: datetime | None = None,
    artifact_id: uuid.UUID | None = None,
    note: str | None = None,
    actor_id: int = 0,
) -> PreviewSourceSnapshot:
    row = PreviewSourceSnapshot(
        run_id=run_id,
        attempt_id=attempt_id,
        source_kind=source_kind.value,
        provider=provider,
        collected_at=collected_at,
        provider_updated_at=provider_updated_at,
        fixture=fixture.to_dict() if fixture else None,
        catalog_query=dict(catalog_query) if catalog_query else None,
        artifact_id=artifact_id,
        validation_status=validation_status.value,
        note=note,
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        run_id=run_id,
        actor_id=actor_id,
        action="snapshot_recorded",
        target_table="preview_source_snapshots",
        target_id=str(row.id),
        detail={"source_kind": row.source_kind, "provider": provider},
    )
    return row


def _next_version(session: Session, module_execution_id: uuid.UUID) -> int:
    current = session.scalar(
        select(func.max(PreviewResult.version)).where(
            PreviewResult.module_execution_id == module_execution_id
        )
    )
    return int(current or 0) + 1


def save_module_result(
    session: Session,
    result: ModuleResult,
    *,
    actor_id: int = 0,
) -> PreviewResult:
    """모듈 결과를 새 버전으로 저장한다.

    같은 모듈 실행에 이미 결과가 있으면 `version`을 올려 새 행을 만든다. 이전 행은
    그대로 남으므로 수정 전후 비교가 가능하다. 실행 ID와 모듈 실행 ID의 소속이
    다르면 저장하지 않는다.
    """
    execution = session.get(PreviewModuleExecution, result.module_execution_id)
    if execution is None:
        raise RunNotFound(f"module execution {result.module_execution_id} not found")
    if execution.run_id != result.run_id:
        raise ContractError("result run_id does not match its module execution run_id")

    version = _next_version(session, result.module_execution_id)
    previous = session.scalar(
        select(PreviewResult)
        .where(PreviewResult.module_execution_id == result.module_execution_id)
        .order_by(PreviewResult.version.desc())
        .limit(1)
    )
    payload = result.to_dict()
    payload["version"] = version

    row = PreviewResult(
        id=result.result_id,
        run_id=result.run_id,
        module_execution_id=result.module_execution_id,
        module_id=result.module_id,
        version=version,
        input_hash=result.input_hash,
        status=result.status.value,
        quality=result.quality.value,
        failure_code=result.failure_code.value if result.failure_code else None,
        payload=payload,
        implementation_version=result.implementation_version,
        prompt_version=result.prompt_version,
        contract_version=result.contract_version,
        supersedes_result_id=previous.id if previous is not None else None,
    )
    session.add(row)
    session.flush()

    _audit(
        session,
        run_id=result.run_id,
        actor_id=actor_id,
        action="result_saved",
        target_table="preview_results",
        target_id=str(row.id),
        detail={
            "module_id": result.module_id,
            "version": version,
            "supersedes": str(previous.id) if previous is not None else None,
        },
    )
    return row


def finish_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    status: RunStatus,
    quality: QualityStatus | None = None,
    failure_code: FailureCode | None = None,
    failure_detail: str | None = None,
    actor_id: int = 0,
) -> PreviewRun:
    row = session.get(PreviewRun, run_id)
    if row is None:
        raise RunNotFound(f"run {run_id} not found")
    row.status = status.value
    if quality is not None:
        row.quality = quality.value
    row.failure_code = failure_code.value if failure_code else None
    row.failure_detail = failure_detail
    if status in (
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
    ):
        row.finished_at = _now()
    session.flush()
    _audit(
        session,
        run_id=run_id,
        actor_id=actor_id,
        action="run_finished",
        target_table="preview_runs",
        target_id=str(run_id),
        detail={"status": status.value},
    )
    return row


# --------------------------------------------------------------------------
# 섹션 워크플로우 결과 (MP-04)
# --------------------------------------------------------------------------


def _section_result_view(row: PreviewSectionResult) -> dict[str, Any]:
    """검사 화면·승인 근거가 함께 쓰는 표현.

    본문과 근거를 먼저 내보내고, 노드·시도는 진단으로 붙일 링크만 둔다. 모의·재생
    결과는 `mode`로 그대로 드러나므로 실제 생성으로 읽히지 않는다.
    """
    return {
        "section_result_id": str(row.id),
        "run_id": str(row.run_id),
        "workflow_id": row.workflow_id,
        "workflow_version": row.workflow_version,
        "version": row.version,
        "title": row.title,
        "body": row.body,
        "sources": list(row.sources or []),
        "mode": row.mode,
        "environment": row.environment,
        "quality": row.quality,
        "module_execution_ids": list(row.module_execution_ids or []),
        "result_ids": list(row.result_ids or []),
        "diagnostics": list(row.diagnostics or []),
        "unavailable_reason": row.unavailable_reason,
        "unavailable": row.unavailable_reason is not None,
        "output_contract_version": row.output_contract_version,
        "contract_version": row.contract_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "supersedes_section_result_id": str(row.supersedes_section_result_id)
        if row.supersedes_section_result_id
        else None,
    }


def save_section_result(
    session: Session,
    *,
    run_id: uuid.UUID,
    workflow_id: str,
    workflow_version: str,
    title: str,
    body: str,
    version: int,
    mode: RunMode,
    environment: Environment,
    quality: QualityStatus,
    output_contract_version: str,
    contract_version: str,
    sources: Sequence[Mapping[str, Any]] = (),
    module_execution_ids: Sequence[uuid.UUID] = (),
    result_ids: Sequence[uuid.UUID] = (),
    diagnostics: Sequence[str] = (),
    unavailable_reason: str | None = None,
    supersedes_section_result_id: uuid.UUID | None = None,
    section_result_id: uuid.UUID | None = None,
    actor_id: int = 0,
    now: datetime | None = None,
) -> PreviewSectionResult:
    """섹션 본문 결과를 저장한다.

    모의·재생 결과도 저장하되 `mode`를 그대로 남긴다. 승인 쪽에서 이 값을 확인하므로
    모의 결과로 승인을 만들 수 없다. 본문이 비어 있는데 `unavailable_reason`도 없으면
    저장하지 않는다. 빈 본문을 성공으로 기록하지 않기 위해서다.
    """
    run = _load_run(session, run_id)
    if not body.strip() and unavailable_reason is None:
        raise ContractError(
            "a section result needs a non-empty body, or an explicit unavailable_reason"
        )
    moment = now or _now()

    previous = session.scalar(
        select(PreviewSectionResult)
        .where(
            PreviewSectionResult.run_id == run.id,
            PreviewSectionResult.workflow_id == workflow_id,
        )
        .order_by(PreviewSectionResult.version.desc())
        .limit(1)
    )
    row = PreviewSectionResult(
        id=section_result_id or uuid.uuid4(),
        run_id=run.id,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        version=int(version),
        title=title,
        body=body,
        sources=[dict(item) for item in sources],
        mode=mode.value,
        environment=environment.value,
        quality=quality.value,
        module_execution_ids=[str(item) for item in module_execution_ids],
        result_ids=[str(item) for item in result_ids],
        diagnostics=[str(item) for item in diagnostics],
        unavailable_reason=unavailable_reason,
        output_contract_version=output_contract_version,
        contract_version=contract_version,
        created_at=moment,
        supersedes_section_result_id=supersedes_section_result_id
        or (previous.id if previous is not None else None),
    )
    session.add(row)
    session.flush()
    _audit(
        session,
        run_id=run.id,
        actor_id=actor_id,
        action="section_result_saved",
        target_table="preview_section_results",
        target_id=str(row.id),
        detail={
            "workflow_id": workflow_id,
            "version": version,
            "mode": mode.value,
            "unavailable": unavailable_reason is not None,
        },
    )
    return row


def get_section_result_any_run(
    session: Session, section_result_id: uuid.UUID
) -> PreviewSectionResult | None:
    """결과 ID로 섹션 결과를 찾는다(실행 범위 제한 없음).

    구성본은 **서로 다른 실행**의 결과를 함께 고를 수 있어야 한다. 이 함수는 관리자
    선택을 해석하는 호출자(구성본 검증)만 쓰고, 실행 범위 조회는 기존
    `get_section_result()`를 그대로 쓴다.
    """
    return session.get(PreviewSectionResult, section_result_id)


def get_section_result(
    session: Session, run_id: uuid.UUID, section_result_id: uuid.UUID
) -> PreviewSectionResult | None:
    """이 실행이 소유한 섹션 결과만 돌려준다. 다른 실행의 결과는 `None`이다."""
    row = session.get(PreviewSectionResult, section_result_id)
    if row is None or row.run_id != run_id:
        return None
    return row


def list_section_results(
    session: Session,
    run_id: uuid.UUID,
    *,
    workflow_id: str | None = None,
) -> list[dict[str, Any]]:
    """실행 하나의 섹션 결과들. 저장된 행만 읽고 외부 호출을 하지 않는다."""
    statement = (
        select(PreviewSectionResult)
        .where(PreviewSectionResult.run_id == run_id)
        .order_by(PreviewSectionResult.created_at, PreviewSectionResult.workflow_id)
    )
    if workflow_id is not None:
        statement = statement.where(PreviewSectionResult.workflow_id == workflow_id)
    return [_section_result_view(row) for row in session.scalars(statement)]


# --------------------------------------------------------------------------
# 조회 (저장된 행만 읽는다)
# --------------------------------------------------------------------------


def _summary(row: PreviewRun, session: Session) -> RunSummary:
    module_count = int(
        session.scalar(
            select(func.count())
            .select_from(PreviewModuleExecution)
            .where(PreviewModuleExecution.run_id == row.id)
        )
        or 0
    )
    attempt_count = int(
        session.scalar(
            select(func.count())
            .select_from(PreviewAttempt)
            .where(PreviewAttempt.run_id == row.id)
        )
        or 0
    )
    retry_count = int(
        session.scalar(
            select(func.count())
            .select_from(PreviewAttempt)
            .where(PreviewAttempt.run_id == row.id, PreviewAttempt.attempt_ordinal > 0)
        )
        or 0
    )
    return RunSummary(
        run_id=row.id,
        operation_kind=OperationKind(row.operation_kind),
        environment=Environment(row.environment),
        mode=RunMode(row.mode),
        status=RunStatus(row.status),
        quality=QualityStatus(row.quality),
        fixture_label=row.fixture_label,
        requested_at=row.requested_at,
        finished_at=row.finished_at,
        module_count=module_count,
        attempt_count=attempt_count,
        retry_count=retry_count,
        failure_code=FailureCode(row.failure_code) if row.failure_code else None,
        label=row.label,
        cancelled_at=row.cancelled_at,
    )


def list_runs(
    session: Session,
    *,
    limit: int = 50,
    include_cancelled: bool = True,
    mode: RunMode | None = None,
    environment: Environment | None = None,
) -> list[RunSummary]:
    """실행 목록. 저장된 행만 읽고 외부 호출을 하지 않는다."""
    statement = select(PreviewRun).order_by(PreviewRun.requested_at.desc()).limit(limit)
    if not include_cancelled:
        statement = statement.where(PreviewRun.status != RunStatus.CANCELLED.value)
    if mode is not None:
        statement = statement.where(PreviewRun.mode == mode.value)
    if environment is not None:
        statement = statement.where(PreviewRun.environment == environment.value)
    return [_summary(row, session) for row in session.scalars(statement)]


def _attempt_view(row: PreviewAttempt) -> dict[str, Any]:
    return {
        "attempt_id": str(row.id),
        "logical_call_id": row.logical_call_id,
        "attempt_ordinal": row.attempt_ordinal,
        "module_execution_id": str(row.module_execution_id)
        if row.module_execution_id
        else None,
        "module_id": row.module_id,
        "provider": row.provider,
        "model": row.model,
        "mode": row.mode,
        "operation": row.operation,
        "outcome": row.outcome,
        "http_status": row.http_status,
        "error_class": row.error_class,
        "error_message": row.error_message,
        "request_spec": row.request_spec,
        "request_artifact_id": str(row.request_artifact_id)
        if row.request_artifact_id
        else None,
        "response_artifact_id": str(row.response_artifact_id)
        if row.response_artifact_id
        else None,
        "usage": row.usage,
        "wait_ms": row.wait_ms,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _result_view(row: PreviewResult) -> dict[str, Any]:
    return {
        "result_id": str(row.id),
        "module_id": row.module_id,
        "module_execution_id": str(row.module_execution_id),
        "version": row.version,
        "input_hash": row.input_hash,
        "status": row.status,
        "quality": row.quality,
        "failure_code": row.failure_code,
        "contract_version": row.contract_version,
        "prompt_version": row.prompt_version,
        "implementation_version": row.implementation_version,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "supersedes_result_id": str(row.supersedes_result_id)
        if row.supersedes_result_id
        else None,
        "payload": row.payload,
    }


def _module_view(
    row: PreviewModuleExecution,
    results: Sequence[PreviewResult],
    attempts: Sequence[PreviewAttempt],
) -> dict[str, Any]:
    return {
        "module_execution_id": str(row.id),
        "run_id": str(row.run_id),
        "module_id": row.module_id,
        "ordinal": row.ordinal,
        "status": row.status,
        "quality": row.quality,
        "failure_code": row.failure_code,
        "input": row.input_payload,
        "delivered_next_input": row.delivered_next_input,
        # 저장된 카운터가 0이어도 실제로 붙은 시도가 있으면 그 수를 보여 준다.
        # 예전 행은 시도에 실행 ID가 없어 카운터가 갱신되지 않았다(읽기 보정).
        "attempt_count": max(int(row.attempt_count or 0), len(attempts)),
        "retry_count": row.retry_count,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "result_versions": [r.version for r in results],
        "latest_result": _result_view(results[-1]) if results else None,
        "attempts": [_attempt_view(a) for a in attempts],
    }


def _load_run(session: Session, run_id: uuid.UUID) -> PreviewRun:
    row = session.get(PreviewRun, run_id)
    if row is None:
        raise RunNotFound(f"run {run_id} not found")
    return row


def get_run_detail(
    session: Session, run_id: uuid.UUID, *, include_artifact_bodies: bool = True
) -> RunDetail:
    """저장된 행만으로 실행 상세를 만든다. 외부 호출이 없다."""
    row = _load_run(session, run_id)

    executions = list(
        session.scalars(
            select(PreviewModuleExecution)
            .where(PreviewModuleExecution.run_id == row.id)
            .order_by(
                PreviewModuleExecution.created_at,
                PreviewModuleExecution.ordinal,
                PreviewModuleExecution.module_id,
            )
        )
    )
    results = list(
        session.scalars(
            select(PreviewResult)
            .where(PreviewResult.run_id == row.id)
            .order_by(PreviewResult.created_at, PreviewResult.version)
        )
    )
    attempts = list(
        session.scalars(
            select(PreviewAttempt)
            .where(PreviewAttempt.run_id == row.id)
            .order_by(PreviewAttempt.started_at, PreviewAttempt.attempt_ordinal)
        )
    )
    snapshots = list(
        session.scalars(
            select(PreviewSourceSnapshot)
            .where(PreviewSourceSnapshot.run_id == row.id)
            .order_by(PreviewSourceSnapshot.collected_at)
        )
    )
    artifact_rows = list(
        session.scalars(
            select(PreviewArtifact)
            .where(PreviewArtifact.run_id == row.id)
            .order_by(PreviewArtifact.created_at)
        )
    )

    results_by_execution: dict[uuid.UUID, list[PreviewResult]] = {}
    for result in results:
        results_by_execution.setdefault(result.module_execution_id, []).append(result)
    attempts_by_execution: dict[uuid.UUID, list[PreviewAttempt]] = {}
    for attempt in attempts:
        if attempt.module_execution_id is not None:
            attempts_by_execution.setdefault(attempt.module_execution_id, []).append(attempt)

    # 예전에 저장된 실행에는 시도의 `module_execution_id`가 비어 있다(노드가 실행 ID를
    # 넘기지 않던 결함). 그 행을 읽기만 해서는 응답 원문을 찾을 수 없으므로, **같은 실행에
    # 그 모듈의 실행이 정확히 하나뿐일 때만** 그 실행에 붙여 읽기 시점에 보여 준다.
    # 저장 행은 고치지 않는다(마이그레이션·백필 없음). 모듈이 여럿이면 붙이지 않고
    # 실행 단위 미배정 호출로 따로 노출한다(`unassigned_attempts`).
    executions_by_module: dict[str, list[uuid.UUID]] = {}
    for execution in executions:
        executions_by_module.setdefault(execution.module_id, []).append(execution.id)
    unassigned: list[PreviewAttempt] = []
    for attempt in attempts:
        if attempt.module_execution_id is not None:
            continue
        candidates = executions_by_module.get(attempt.module_id or "", [])
        if len(candidates) == 1:
            attempts_by_execution.setdefault(candidates[0], []).append(attempt)
        else:
            unassigned.append(attempt)

    modules = tuple(
        _module_view(
            execution,
            results_by_execution.get(execution.id, []),
            attempts_by_execution.get(execution.id, []),
        )
        for execution in executions
    )
    artifacts = tuple(artifact_store.artifact_view(a) for a in artifact_rows)
    if not include_artifact_bodies:
        artifacts = tuple({**view, "body": None} for view in artifacts)

    section_results = list(
        session.scalars(
            select(PreviewSectionResult)
            .where(PreviewSectionResult.run_id == row.id)
            .order_by(PreviewSectionResult.created_at, PreviewSectionResult.workflow_id)
        )
    )

    summary = _summary(row, session)
    return RunDetail(
        summary=summary,
        # 계정 ID는 bigint다. JS 숫자의 안전 범위를 넘을 수 있으므로 문자열로 내보낸다.
        actor_id=str(row.actor_id),
        config_version=row.config_version,
        limits=ExecutionLimits(**(row.limits or {})),
        fixture=_fixture_from_row(row),
        modules=modules,
        results=tuple(_result_view(r) for r in results),
        sources=tuple(
            {
                "snapshot_id": str(s.id),
                "source_kind": s.source_kind,
                "provider": s.provider,
                "collected_at": s.collected_at.isoformat(),
                "provider_updated_at": s.provider_updated_at.isoformat()
                if s.provider_updated_at
                else None,
                "validation_status": s.validation_status,
                "fixture": s.fixture,
                "catalog_query": s.catalog_query,
                "artifact_id": str(s.artifact_id) if s.artifact_id else None,
                "note": s.note,
            }
            for s in snapshots
        ),
        attempts=tuple(_attempt_view(a) for a in attempts),
        artifacts=artifacts,
        contract_versions=row.contract_versions or contract_versions(),
        undo=_undo_view(session, row),
        section_results=tuple(_section_result_view(r) for r in section_results),
        unassigned_attempts=tuple(_attempt_view(a) for a in unassigned),
    )


def run_send_ledger_summary(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    """실행 하나의 전송 장부 요약. 조회 경로가 화면에 그대로 낼 수 있는 값이다."""
    from app.preview import send_ledger as ledger_module

    return {
        "charged_requests": ledger_module.charged_requests(session, run_id=run_id),
        "unresolved_sends": list(ledger_module.unresolved_sends(session, run_id=run_id)),
        "ledger_action": ledger_module.CHARGE_ACTION,
    }


def get_module_execution(
    session: Session, run_id: uuid.UUID, module_execution_id: uuid.UUID
) -> dict[str, Any] | None:
    """모듈 실행 하나. 다른 실행의 모듈 실행 ID를 넣으면 `None`이다."""
    execution = session.get(PreviewModuleExecution, module_execution_id)
    if execution is None or execution.run_id != run_id:
        return None
    results = list(
        session.scalars(
            select(PreviewResult)
            .where(PreviewResult.module_execution_id == execution.id)
            .order_by(PreviewResult.version)
        )
    )
    attempts = list(
        session.scalars(
            select(PreviewAttempt)
            .where(PreviewAttempt.module_execution_id == execution.id)
            .order_by(PreviewAttempt.attempt_ordinal)
        )
    )
    artifact_rows = list(
        session.scalars(
            select(PreviewArtifact).where(
                PreviewArtifact.id.in_(
                    [
                        artifact_id
                        for artifact_id in (
                            [a.response_artifact_id for a in attempts]
                            + [a.request_artifact_id for a in attempts]
                        )
                        if artifact_id is not None
                    ]
                    or [uuid.UUID(int=0)]
                )
            )
        )
    )
    view = _module_view(execution, results, attempts)
    view["artifacts"] = [artifact_store.artifact_view(a) for a in artifact_rows]
    return view


def compare_result_versions(
    session: Session,
    module_execution_id: uuid.UUID,
    *,
    base_version: int | None = None,
    target_version: int | None = None,
) -> dict[str, Any]:
    """같은 모듈 실행의 두 결과 버전을 비교한다.

    버전을 지정하지 않으면 가장 최근 두 버전을 쓴다. 이전 결과를 지우지 않았으므로
    수정 전후 비교가 항상 가능하다.
    """
    rows = list(
        session.scalars(
            select(PreviewResult)
            .where(PreviewResult.module_execution_id == module_execution_id)
            .order_by(PreviewResult.version)
        )
    )
    if not rows:
        raise RunNotFound(f"no results for module execution {module_execution_id}")
    by_version = {row.version: row for row in rows}
    if target_version is None:
        target = rows[-1]
    else:
        target = by_version.get(target_version)
        if target is None:
            raise RunNotFound(f"version {target_version} not found")
    if base_version is None:
        older = [row for row in rows if row.version < target.version]
        base = older[-1] if older else None
    else:
        base = by_version.get(base_version)
        if base is None:
            raise RunNotFound(f"version {base_version} not found")

    return {
        "module_execution_id": str(module_execution_id),
        "module_id": target.module_id,
        "base": _result_view(base) if base is not None else None,
        "target": _result_view(target),
        "diff": _diff_results(base, target),
        "versions_available": [row.version for row in rows],
    }


def _claims_of(row: PreviewResult) -> dict[str, Mapping[str, Any]]:
    claims = (row.payload or {}).get("claims") or []
    return {str(claim.get("claim_id")): claim for claim in claims}


def _coverage_of(row: PreviewResult) -> dict[str, Mapping[str, Any]]:
    coverage = (row.payload or {}).get("coverage") or []
    return {str(entry.get("topic")): entry for entry in coverage}


def _diff_results(
    base: PreviewResult | None, target: PreviewResult
) -> dict[str, Any]:
    target_claims = _claims_of(target)
    base_claims = _claims_of(base) if base is not None else {}

    added = sorted(set(target_claims) - set(base_claims))
    removed = sorted(set(base_claims) - set(target_claims))
    changed = sorted(
        claim_id
        for claim_id in set(target_claims) & set(base_claims)
        if target_claims[claim_id] != base_claims[claim_id]
    )

    target_coverage = _coverage_of(target)
    base_coverage = _coverage_of(base) if base is not None else {}
    coverage_changes = {
        topic: {
            "from": (base_coverage.get(topic) or {}).get("state"),
            "to": (target_coverage.get(topic) or {}).get("state"),
        }
        for topic in sorted(set(target_coverage) | set(base_coverage))
        if (base_coverage.get(topic) or {}).get("state")
        != (target_coverage.get(topic) or {}).get("state")
    }

    payload_keys_changed = sorted(
        key
        for key in set((base.payload if base is not None else {}) or {})
        | set(target.payload or {})
        if (base.payload if base is not None else {}).get(key)
        != (target.payload or {}).get(key)
    )

    return {
        "status": {
            "from": base.status if base is not None else None,
            "to": target.status,
        },
        "quality": {
            "from": base.quality if base is not None else None,
            "to": target.quality,
        },
        "input_hash": {
            "from": base.input_hash if base is not None else None,
            "to": target.input_hash,
            "changed": (base.input_hash if base is not None else None) != target.input_hash,
        },
        "contract_version": {
            "from": base.contract_version if base is not None else None,
            "to": target.contract_version,
        },
        "prompt_version": {
            "from": base.prompt_version if base is not None else None,
            "to": target.prompt_version,
        },
        "claims_added": added,
        "claims_removed": removed,
        "claims_changed": changed,
        "coverage_changes": coverage_changes,
        "payload_keys_changed": payload_keys_changed,
    }


# --------------------------------------------------------------------------
# 범위가 한정된 실행 취소
# --------------------------------------------------------------------------


def _undo_view(session: Session, row: PreviewRun) -> dict[str, Any]:
    """취소 가능 여부와 이유. 화면이 그대로 보여줄 수 있는 형태로 만든다."""
    if row.cancelled_at is not None:
        return {
            "state": "cancelled",
            "cancelled_at": row.cancelled_at.isoformat(),
            "cancelled_by_actor_id": (
                str(row.cancelled_by_actor_id)
                if row.cancelled_by_actor_id is not None
                else None
            ),
            "reason": row.cancellation_reason,
            "can_cancel": False,
            "blocked_reason": "이미 취소된 실행입니다. 기록은 감사용으로 남습니다.",
        }
    conflict = _cancel_conflict(session, row)
    return {
        "state": "cancellable" if conflict is None else "blocked",
        "cancelled_at": None,
        "cancelled_by_actor_id": None,
        "reason": None,
        "can_cancel": conflict is None,
        "blocked_reason": conflict,
    }


def _cancel_conflict(session: Session, row: PreviewRun) -> str | None:
    """취소 전에 확인하는 조건. 통과하면 `None`.

    범위 조건 두 가지(개발 영역·개발 환경)와, 다른 실행이 남긴 후속 버전이 없는지
    확인한다. 후속 버전이 있으면 그 기록까지 함께 지우게 되므로 충돌로 중단한다.
    """
    if row.write_scope != "preview_dev":
        return (
            f"이 실행의 쓰기 범위({row.write_scope})는 취소 대상이 아닙니다. "
            "개발 영역(preview_dev) 기록만 취소할 수 있습니다."
        )
    if row.environment == Environment.PROD.value:
        return "운영 환경 기록은 개발 취소 대상이 아닙니다."

    owned_executions = select(PreviewModuleExecution.id).where(
        PreviewModuleExecution.run_id == row.id
    )
    foreign = session.execute(
        select(PreviewResult.module_execution_id, PreviewResult.version, PreviewResult.run_id)
        .where(
            PreviewResult.module_execution_id.in_(owned_executions),
            PreviewResult.run_id != row.id,
        )
        .order_by(PreviewResult.version)
    ).all()
    if foreign:
        described = ", ".join(
            f"{execution_id} v{version} (실행 {owner_id})"
            for execution_id, version, owner_id in foreign
        )
        return (
            "이 실행이 만든 모듈 실행에 다른 실행이 남긴 결과 버전이 있습니다: "
            f"{described}. 현재 값을 되돌리면 그 기록도 사라지므로 충돌로 중단합니다."
        )
    return None


def cancel_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    actor_id: int,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """이 실행이 만든 개발 영역 기록만 지우고, 실행 행과 감사 표시는 남긴다.

    지우는 대상은 이 실행 ID로 만들어진 모듈 실행·시도·결과·자료 스냅샷·원문이다.
    기존 경기·계정 자료는 처음부터 쓰지 않으므로 대상이 아니다. 다른 실행의 기록을
    건드리지 않는다.
    """
    row = _load_run(session, run_id)
    conflict = _cancel_conflict(session, row)
    if row.cancelled_at is not None:
        raise WriteConflict(
            _undo_view(session, row)["blocked_reason"] or "already cancelled"
        )
    if conflict is not None:
        raise WriteConflict(conflict)

    moment = now or datetime.now(timezone.utc)

    artifacts = list(
        session.scalars(select(PreviewArtifact).where(PreviewArtifact.run_id == row.id))
    )
    snapshots = list(
        session.scalars(
            select(PreviewSourceSnapshot).where(PreviewSourceSnapshot.run_id == row.id)
        )
    )
    attempts = list(
        session.scalars(select(PreviewAttempt).where(PreviewAttempt.run_id == row.id))
    )
    results = list(
        session.scalars(select(PreviewResult).where(PreviewResult.run_id == row.id))
    )
    executions = list(
        session.scalars(
            select(PreviewModuleExecution).where(PreviewModuleExecution.run_id == row.id)
        )
    )
    section_results = list(
        session.scalars(
            select(PreviewSectionResult).where(PreviewSectionResult.run_id == row.id)
        )
    )

    removed = {
        "preview_artifacts": len(artifacts),
        "preview_source_snapshots": len(snapshots),
        "preview_attempts": len(attempts),
        "preview_results": len(results),
        "preview_section_results": len(section_results),
        "preview_module_executions": len(executions),
    }

    for artifact in artifacts:
        session.delete(artifact)
    session.flush()
    for snapshot in snapshots:
        session.delete(snapshot)
    session.flush()
    for attempt in attempts:
        session.delete(attempt)
    session.flush()
    for section_result in section_results:
        session.delete(section_result)
    session.flush()
    for result in results:
        session.delete(result)
    session.flush()
    for execution in executions:
        session.delete(execution)
    session.flush()

    row.status = RunStatus.CANCELLED.value
    row.cancelled_at = moment
    row.cancelled_by_actor_id = actor_id
    row.cancellation_reason = reason
    row.finished_at = row.finished_at or moment
    session.flush()

    _audit(
        session,
        run_id=row.id,
        actor_id=actor_id,
        action="run_cancelled",
        target_table="preview_runs",
        target_id=str(row.id),
        detail={"removed": removed, "reason": reason},
    )
    return {
        "run_id": str(row.id),
        "cancelled_at": moment.isoformat(),
        "removed": removed,
        "kept": ["preview_runs", "preview_write_audit"],
        "reason": reason,
    }


def undo_report(
    session: Session, run_id: uuid.UUID
) -> dict[str, Any]:
    """화면이 '무엇이 지워지는지' 먼저 보여줄 수 있게 한다."""
    row = _load_run(session, run_id)
    counts = {
        "preview_artifacts": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewArtifact)
                .where(PreviewArtifact.run_id == row.id)
            )
            or 0
        ),
        "preview_source_snapshots": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewSourceSnapshot)
                .where(PreviewSourceSnapshot.run_id == row.id)
            )
            or 0
        ),
        "preview_attempts": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewAttempt)
                .where(PreviewAttempt.run_id == row.id)
            )
            or 0
        ),
        "preview_results": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewResult)
                .where(PreviewResult.run_id == row.id)
            )
            or 0
        ),
        "preview_section_results": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewSectionResult)
                .where(PreviewSectionResult.run_id == row.id)
            )
            or 0
        ),
        "preview_module_executions": int(
            session.scalar(
                select(func.count())
                .select_from(PreviewModuleExecution)
                .where(PreviewModuleExecution.run_id == row.id)
            )
            or 0
        ),
    }
    return {
        "run_id": str(row.id),
        "write_scope": row.write_scope,
        "would_remove": counts,
        "undo": _undo_view(session, row),
    }


def iter_audit(session: Session, run_id: uuid.UUID) -> Iterable[dict[str, Any]]:
    rows = session.scalars(
        select(PreviewWriteAudit)
        .where(PreviewWriteAudit.run_id == run_id)
        .order_by(PreviewWriteAudit.created_at)
    )
    for row in rows:
        yield {
            "action": row.action,
            "target_table": row.target_table,
            "target_id": row.target_id,
            "detail": row.detail,
            "actor_id": str(row.actor_id),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


# --------------------------------------------------------------------------
# 정보 원문 묶음 저장·조회 (PS-01)
# --------------------------------------------------------------------------

# 묶음 아티팩트를 다른 정규화 변환과 구별하는 표식. 새 테이블을 만들지 않고 기존
# `preview_artifacts`(JSONB 그릇)만 쓴다. 그래서 개발 마이그레이션이 필요 없다.
BUNDLE_RECORD_TYPE = "information_bundle"
# 섹션 결과 버전을 **관리자가 골라 묶은 구성본**. 새 테이블을 만들지 않고 기존
# `preview_artifacts`(normalized_transform)에 기록 유형으로 남긴다.
COMPOSITION_RECORD_TYPE = "section_composition"


def save_information_bundle(
    session: Session,
    *,
    run_id: uuid.UUID,
    bundle: Mapping[str, Any],
    actor_id: int = 0,
    secret_values: Sequence[str] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """정보 원문 묶음을 저장한다. 계약 위반은 저장 전에 거부한다.

    반환값은 조회와 같은 모양(`available/artifact_id/bundle/summary`)이라 호출자가
    저장 직후 화면에 그대로 쓸 수 있다.
    """
    from app.preview import information_bundle as bundle_contract

    row = _load_run(session, run_id)
    bundle_contract.ensure_valid_bundle(bundle)
    payload = bundle_contract.bundle_to_dict(bundle)
    # 같은 실행에서 묶음을 여러 번 저장할 수 있다(섹션 전달 기록 추가 등). 생성 시각이
    # 같아도 "가장 최근 저장"을 확정할 수 있도록 실행별 순번을 남긴다.
    previous = [
        row
        for row in session.scalars(
            select(PreviewArtifact).where(
                PreviewArtifact.run_id == row.id,
                PreviewArtifact.kind
                == artifact_store.ArtifactKind.NORMALIZED_TRANSFORM.value,
            )
        )
    ]
    record = {
        "record_type": BUNDLE_RECORD_TYPE,
        "sequence": len(previous) + 1,
        "bundle_version": payload.get("bundle_version"),
        "bundle": payload,
    }
    artifact = artifact_store.save_artifact(
        session,
        run_id=row.id,
        kind=artifact_store.ArtifactKind.NORMALIZED_TRANSFORM,
        content=record,
        secret_values=secret_values,
        actor_id=actor_id,
        now=now,
    )
    _audit(
        session,
        run_id=row.id,
        actor_id=actor_id,
        action="information_bundle_saved",
        target_table="preview_artifacts",
        target_id=str(artifact.id),
        detail={
            "bundle_id": payload.get("bundle_id"),
            "bundle_hash": payload.get("bundle_hash"),
            "source_count": len(payload.get("sources") or ()),
            "usable_source_count": payload.get("usable_source_count"),
        },
    )
    return {
        "available": True,
        "reason": None,
        "artifact_id": str(artifact.id),
        "bundle": payload,
        "summary": bundle_contract.bundle_summary(payload),
    }


def load_information_bundle(
    session: Session, run_id: uuid.UUID
) -> dict[str, Any]:
    """이 실행의 최신 정보 원문 묶음. 없으면 `available=false`와 실제 사유를 낸다.

    빈 묶음을 만들어 내지 않는다. 만료된 아티팩트는 `available=false`이며 사유가
    "보관 기간이 지났다"임을 밝힌다(읽기 실패와 다른 상태).
    """
    _load_run(session, run_id)  # 실행이 없으면 RunNotFound
    candidates = list(
        session.scalars(
            select(PreviewArtifact)
            .where(
                PreviewArtifact.run_id == run_id,
                PreviewArtifact.kind == artifact_store.ArtifactKind.NORMALIZED_TRANSFORM.value,
            )
            .order_by(PreviewArtifact.created_at.desc())
        )
    )
    matches: list[tuple[int, datetime, PreviewArtifact, Mapping[str, Any]]] = []
    for row in candidates:
        if row.body is None:
            continue
        try:
            record = json.loads(row.body)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, Mapping) or record.get("record_type") != BUNDLE_RECORD_TYPE:
            continue
        bundle = record.get("bundle")
        if not isinstance(bundle, Mapping):
            continue
        matches.append(
            (int(record.get("sequence") or 0), row.created_at, row, dict(bundle))
        )
    if matches:
        # 가장 최근 저장본. 순번이 같으면(옛 기록) 생성 시각으로 비교한다.
        matches.sort(key=lambda item: (item[0], item[1]))
        _sequence, _created, row, bundle = matches[-1]
        from app.preview import information_bundle as bundle_contract

        return {
            "available": True,
            "reason": None,
            "artifact_id": str(row.id),
            "sequence": _sequence,
            "bundle": bundle,
            "summary": bundle_contract.bundle_summary(bundle),
        }
    expired = [row for row in candidates if row.body is None]
    if expired:
        return {
            "available": False,
            "reason": (
                "정보 원문 묶음의 보관 기간이 지나 본문을 열 수 없습니다."
                " 요약과 해시는 남아 있습니다."
            ),
            "artifact_id": str(expired[0].id),
            "bundle": None,
            "summary": expired[0].summary,
        }
    return {
        "available": False,
        "reason": (
            "이 실행에는 정보 원문 묶음이 저장되어 있지 않습니다. 묶음을 만들지 않은"
            " 실행이거나, 수집 단계 이전에 끝난 실행입니다."
        ),
        "artifact_id": None,
        "bundle": None,
        "summary": None,
    }

def save_information_bundle_with_bodies(
    session: Session,
    *,
    run_id: uuid.UUID,
    collection: Any,
    actor_id: int = 0,
    secret_values: Sequence[str] = (),
    now: datetime | None = None,
    db_snapshot: Any | None = None,
) -> dict[str, Any]:
    """B의 수집 결과(`CollectionOutput`)를 **전문 아티팩트와 함께** 저장한다.

    묶음에는 전문을 넣지 않는다(계약). 대신 출처마다 `body_artifact_id`를 채워
    "전문이 어디 있는지"를 가리킨다. 그래서 관리자 화면은 묶음만으로 출처·구간을
    보여주고, 전문은 그 아티팩트 ID로 연다.

    `collection`에 전문이 없으면(옛 모양) 아티팩트를 만들지 않고 묶음만 저장한다.
    없는 전문을 빈 문자열로 만들어 채우지 않는다.
    """
    from app.preview import information_bundle as bundle_contract

    row = _load_run(session, run_id)
    bundle = bundle_contract.bundle_from_collection(
        collection=collection,
        db_snapshot=(
            bundle_contract.DbSnapshot.from_dict(db_snapshot)
            if isinstance(db_snapshot, Mapping)
            else db_snapshot
        ),
    )
    bodies = bundle_contract.collection_bodies(collection)

    artifact_by_source: dict[str, uuid.UUID] = {}
    moment = now or _now()
    for body in bodies:
        source_id = str(getattr(body, "source_id", "") or "")
        text = str(getattr(body, "text", "") or "")
        if not source_id or not text:
            continue
        artifact = artifact_store.save_artifact(
            session,
            run_id=row.id,
            kind=artifact_store.ArtifactKind.RAW_RESPONSE,
            content={
                "record_type": "source_body",
                "source_id": source_id,
                "requested_url": getattr(body, "requested_url", None),
                "final_url": getattr(body, "final_url", None),
                "captured_at": getattr(body, "captured_at", None),
                "extractor": getattr(body, "extractor", None),
                "extraction": getattr(body, "extraction", None),
                "html_sha256": getattr(body, "html_sha256", None),
                "body_sha256": getattr(body, "body_sha256", None),
                "body_chars": len(text),
                "text": text,
            },
            media_type="application/json",
            secret_values=secret_values,
            actor_id=actor_id,
            now=moment,
        )
        artifact_by_source[source_id] = artifact.id

    if artifact_by_source:
        from dataclasses import replace as _replace

        patched = tuple(
            _replace(
                source,
                body_artifact_id=artifact_by_source.get(source.source_id)
                or source.body_artifact_id,
            )
            for source in bundle.sources
        )
        bundle = _replace(bundle, sources=patched)

    return save_information_bundle(
        session,
        run_id=row.id,
        bundle=bundle,
        actor_id=actor_id,
        secret_values=secret_values,
        now=now,
    )


def save_composition(
    session: Session,
    *,
    run_id: uuid.UUID,
    composition: Mapping[str, Any],
    actor_id: int = 0,
    secret_values: Sequence[str] = (),
    now: datetime | None = None,
) -> dict[str, Any]:
    """관리자가 고른 섹션 결과 버전 묶음(구성본)을 저장한다.

    새 테이블을 만들지 않고 `preview_artifacts`(normalized_transform)에 기록 유형
    `section_composition`으로 남긴다. 구성본은 **선택 ID 집합**과 각 항목의 출처 실행을
    함께 보관해야 하므로, 호출자가 만든 그대로를 저장하고 여기서 값을 만들지 않는다.
    """
    row = _load_run(session, run_id)
    record = {
        "record_type": COMPOSITION_RECORD_TYPE,
        "composition": dict(composition),
    }
    artifact = artifact_store.save_artifact(
        session,
        run_id=row.id,
        kind=artifact_store.ArtifactKind.NORMALIZED_TRANSFORM,
        content=record,
        secret_values=secret_values,
        actor_id=actor_id,
        now=now,
    )
    _audit(
        session,
        run_id=row.id,
        actor_id=actor_id,
        action="section_composition_saved",
        target_table="preview_artifacts",
        target_id=str(artifact.id),
        detail={
            "composition_id": (composition or {}).get("composition_id"),
            "item_count": len((composition or {}).get("items") or ()),
        },
    )
    return {
        "available": True,
        "artifact_id": str(artifact.id),
        "composition": dict(composition),
    }


def load_composition(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    """이 실행의 최신 구성본. 없으면 `available=false`와 실제 사유를 낸다."""
    _load_run(session, run_id)
    rows = list(
        session.scalars(
            select(PreviewArtifact)
            .where(
                PreviewArtifact.run_id == run_id,
                PreviewArtifact.kind == artifact_store.ArtifactKind.NORMALIZED_TRANSFORM.value,
            )
            .order_by(PreviewArtifact.created_at.desc())
        )
    )
    for row in rows:
        if row.body is None:
            continue
        try:
            record = json.loads(row.body)
        except (TypeError, ValueError):
            continue
        if not isinstance(record, Mapping):
            continue
        if record.get("record_type") != COMPOSITION_RECORD_TYPE:
            continue
        composition = record.get("composition")
        if not isinstance(composition, Mapping):
            continue
        return {
            "available": True,
            "reason": None,
            "artifact_id": str(row.id),
            "composition": dict(composition),
        }
    return {
        "available": False,
        "reason": "이 실행에는 저장된 구성본이 없습니다.",
        "artifact_id": None,
        "composition": None,
    }


def load_source_body(
    session: Session, run_id: uuid.UUID, source_id: str
) -> dict[str, Any]:
    """정보 원문 묶음 출처의 전문. 없으면 `available=false`와 사유를 낸다.

    묶음이 가리키는 아티팩트가 이 실행 소유가 아니면(재사용·부모 실행) 읽을 수 없다고
    정직하게 알린다. 다른 실행의 원문을 권한 없이 열지 않는다.
    """
    record = load_information_bundle(session, run_id)
    if not record.get("available"):
        return {
            "available": False,
            "source_id": source_id,
            "reason": record.get("reason"),
            "body": None,
        }
    sources = [
        source
        for source in (record.get("bundle") or {}).get("sources") or ()
        if str(source.get("source_id")) == source_id
    ]
    if not sources:
        return {
            "available": False,
            "source_id": source_id,
            "reason": "이 정보 원문 묶음에 해당 출처가 없습니다.",
            "body": None,
        }
    source = sources[0]
    artifact_id = source.get("body_artifact_id")
    if not artifact_id:
        return {
            "available": False,
            "source_id": source_id,
            "reason": (
                "이 출처의 전문 아티팩트가 없습니다. 후보로만 남았거나 본문을 확보하지"
                " 못한 출처입니다."
            ),
            "body": None,
        }
    artifact = session.get(PreviewArtifact, uuid.UUID(str(artifact_id)))
    if artifact is None or artifact.run_id != run_id:
        return {
            "available": False,
            "source_id": source_id,
            "reason": (
                "전문 아티팩트가 이 실행 소유가 아니어서 열 수 없습니다(재사용·부모"
                " 실행 원문)."
            ),
            "body": None,
        }
    if artifact.body is None:
        return {
            "available": False,
            "source_id": source_id,
            "reason": "전문 아티팩트의 보관 기간이 지나 본문을 열 수 없습니다.",
            "body": None,
        }
    try:
        payload = json.loads(artifact.body)
    except (TypeError, ValueError):
        payload = {"text": artifact.body}
    return {
        "available": True,
        "source_id": source_id,
        "reason": None,
        "artifact_id": str(artifact.id),
        "body": payload if isinstance(payload, Mapping) else {"text": str(payload)},
    }
