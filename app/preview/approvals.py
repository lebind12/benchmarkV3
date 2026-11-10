"""섹션 워크플로우 버전 승인.

정책(`AGENTS.md` 경기 프리뷰 실행과 섹션 워크플로우 승인):

- 사용자의 테스트·조정·**승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우**다.
  내부 노드나 D0 같은 자료 준비 단계마다 따로 승인하지 않는다.
- 승인 기록에는 워크플로우 ID·버전, 결과에 영향을 주는 구성 모듈/프롬프트/구현/출력
  계약 버전 집합, 확인한 실행·섹션 결과 ID, 승인자·시각을 남긴다. 매 경기마다 새
  승인을 요구하지 않는다.
- 승인 전 섹션은 관리자 시험에서만 실행하고, 기본 전체 생성은 승인된 버전을 쓴다.
- 결과 의미를 바꾸는 변경은 새 버전으로 다시 확인한다. 기존 승인과 실행 증거는
  보존하며 새 승인이 덮어쓰지 않는다.
- 구현 워커의 완료 보고·테스트 통과·worker_done은 승인이 아니다. 그래서 이 모듈에는
  자동 승인 경로가 없고, 승인자는 호출자가 넘긴 실제 관리자 ID여야 한다.
- 모의 자료는 UI 시연이며 실제 생성 승인 근거로 쓰지 않는다.

경계:

- 이 모듈은 승인 행만 쓴다. 실행·결과·원문을 만들거나 고치지 않는다.
- 승인 표는 append-only다. 이전 승인은 지우지 않고 `active`만 내린다.
- 섹션 실행·섹션 결과는 MP-09·MP-10 소유다. MP-02는 승인 계약과 경계만 고정하며,
  승인 근거가 없으면 승인을 거부한다. 없는 승인을 만들어 통과시키지 않는다.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.preview.contracts import (
    APPROVAL_CONTRACT_VERSION,
    ApprovalRequestError,
    ApprovalState,
    RunMode,
    ConstituentVersion,
    ModuleStatus,
    ReviewedSectionEvidence,
    SectionApproval,
    SectionApprovalStatus,
    SectionWorkflowRegistration,
)
from app.preview.models import (
    PreviewResult,
    PreviewRun,
    PreviewSectionApproval,
    PreviewSectionResult,
    PreviewWriteAudit,
)
from app.preview.registry import get_module, get_section_workflow, section_workflow_ids

__all__ = [
    "approval_gate_note",
    "approve_section_version",
    "describe_approvals",
    "release_version",
    "reject_approval_request",
    "section_approval_status",
    "version_hash",
]


def reject_approval_request(reason: str) -> None:
    """승인 거부를 한 곳에서 만든다. 화면과 API가 같은 문구를 쓴다."""
    raise ApprovalRequestError(reason)


def _module_versions(module_id: str, versions: Mapping[str, Any]) -> ConstituentVersion:
    """구성 모듈 하나의 버전 묶음. 없는 값은 빈 문자열로 두고 꾸미지 않는다."""
    return ConstituentVersion(
        module_id=module_id,
        prompt_version=str(versions.get("prompt_version") or ""),
        implementation_version=str(versions.get("implementation_version") or ""),
        contract_version=str(versions.get("contract_version") or ""),
    )


def release_version(
    workflow: SectionWorkflowRegistration,
    constituents: Sequence[ConstituentVersion],
) -> tuple[str, tuple[ConstituentVersion, ...]]:
    """섹션 워크플로우 버전 문자열과 구성을 만든다.

    버전은 결과에 영향을 주는 축(출력 계약 버전 + 구성 모듈 버전들)만으로 만든다.
    표시 문구 변경이 버전을 바꾸지 않게 하기 위함이다.
    """
    ordered = tuple(sorted(constituents, key=lambda item: item.module_id))
    parts = [workflow.workflow_id, workflow.output_contract_version]
    for item in ordered:
        parts.append(
            "|".join(
                [
                    item.module_id,
                    item.prompt_version,
                    item.implementation_version,
                    item.contract_version,
                ]
            )
        )
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{workflow.workflow_id}@{digest}", ordered


def version_hash(
    workflow_id: str, version: str, constituents: Sequence[ConstituentVersion]
) -> str:
    parts = [workflow_id, version]
    for item in sorted(constituents, key=lambda entry: entry.module_id):
        parts.append(
            "|".join(
                [
                    item.module_id,
                    item.prompt_version,
                    item.implementation_version,
                    item.contract_version,
                ]
            )
        )
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _registration_version(module_id: str) -> ConstituentVersion:
    try:
        registration = get_module(module_id)
        contract_version = registration.contract_version
    except KeyError:
        contract_version = ""
    return _module_versions(module_id, {"contract_version": contract_version})


def _constituents_from_results(
    workflow: SectionWorkflowRegistration,
    rows: Sequence[PreviewResult],
) -> tuple[ConstituentVersion, ...]:
    """승인 근거가 된 실행이 **실제로 남긴** 구성 버전.

    현재 manifest와 **같은 모듈 집합**을 쓴다(자료 준비·조사·본문 조립). 그래야 방금
    실행한 결과를 승인하면 그 버전이 현재 구성과 같아진다. 저장된 결과가 없는 모듈은
    현재 manifest 값으로 채우되, 저장된 값이 있으면 **저장된 값**을 쓴다(그 실행이 실제로
    무엇을 썼는지가 승인 근거다).

    옛 실행을 승인하면 그 실행의 옛 버전이 그대로 남는다. 현재 코드와 다르면 승인 현황이
    SUPERSEDED로 보여 새 버전 확인이 필요하다고 알린다.
    """
    from app.preview import version_manifest

    by_module: dict[str, PreviewResult] = {}
    for row in rows:
        if row.status != ModuleStatus.SUCCEEDED.value:
            continue
        by_module[row.module_id] = row

    versions: list[ConstituentVersion] = []
    for expected in version_manifest.constituents_for_workflow(workflow.workflow_id):
        row = by_module.get(expected.module_id)
        if row is None:
            versions.append(expected)
            continue
        versions.append(
            _module_versions(
                expected.module_id,
                {
                    # 저장값이 비어 있는 축(예: 프롬프트 없는 단계)은 그대로 빈 문자열이다.
                    "prompt_version": row.prompt_version,
                    "implementation_version": row.implementation_version,
                    "contract_version": row.contract_version or expected.contract_version,
                },
            )
        )
    return tuple(sorted(versions, key=lambda item: item.module_id))


def _latest_section_result(
    session: Session, workflow_id: str
) -> PreviewSectionResult | None:
    return session.scalars(
        select(PreviewSectionResult)
        .where(PreviewSectionResult.workflow_id == workflow_id)
        .order_by(PreviewSectionResult.created_at.desc(), PreviewSectionResult.version.desc())
        .limit(1)
    ).first()


def _results_of_run(session: Session, run_id: uuid.UUID) -> list[PreviewResult]:
    return list(
        session.scalars(
            select(PreviewResult)
            .where(PreviewResult.run_id == run_id)
            .order_by(PreviewResult.created_at, PreviewResult.version)
        )
    )


def _current_constituents(
    workflow: SectionWorkflowRegistration, session: Session
) -> tuple[ConstituentVersion, ...]:
    """지금 코드로 이 워크플로우를 실행하면 만들어질 **구성 버전**.

    `version_manifest` 한 곳에서 온다. 그래서 승인 후보가 보는 버전과 실행이 남기는
    버전이 같은 근거를 쓴다. 저장된 결과에서 역산하지 않으므로, 코드가 바뀐 뒤에는
    이전에 저장된 결과의 버전이 아니라 **현재 구성**을 후보로 보여준다.
    """
    from app.preview import version_manifest

    return version_manifest.constituents_for_workflow(workflow.workflow_id)


def _approval(row: PreviewSectionApproval) -> SectionApproval:
    return SectionApproval(
        approval_id=row.id,
        workflow_id=row.workflow_id,
        workflow_version=row.workflow_version,
        constituents=tuple(
            ConstituentVersion(
                module_id=str(entry.get("module_id", "")),
                prompt_version=str(entry.get("prompt_version", "")),
                implementation_version=str(entry.get("implementation_version", "")),
                contract_version=str(entry.get("contract_version", "")),
            )
            for entry in (row.constituents or [])
        ),
        evidence=ReviewedSectionEvidence(
            run_id=row.reviewed_run_id,
            section_result_id=row.section_result_id,
            reviewed_at=row.approved_at,
        ),
        approved_by_actor_id=str(row.approved_by_actor_id),
        approved_at=row.approved_at,
        reviewed_note=row.reviewed_note,
        supersedes_approval_id=row.supersedes_approval_id,
    )


def _rows(session: Session, workflow_id: str) -> list[PreviewSectionApproval]:
    return list(
        session.scalars(
            select(PreviewSectionApproval)
            .where(PreviewSectionApproval.workflow_id == workflow_id)
            .order_by(PreviewSectionApproval.approved_at)
        )
    )


def section_approval_status(
    session: Session, workflow_id: str
) -> SectionApprovalStatus:
    """섹션 하나의 승인 현황. 저장 결과 기준의 현재 구성과 비교한다."""
    workflow = get_section_workflow(workflow_id)
    # `release_version`은 (버전 문자열, 정렬된 구성)을 돌려준다. 버전과 구성을 바꿔
    # 받으면 승인 상태가 항상 SUPERSEDED로 보이는 결함이 생긴다.
    current_version, current = release_version(
        workflow, _current_constituents(workflow, session)
    )

    rows = _rows(session, workflow_id)
    active_row = next((row for row in rows if row.active), None)

    if active_row is None:
        return SectionApprovalStatus(
            workflow_id=workflow_id,
            state=ApprovalState.NONE,
            active_approval=None,
            pinned_approval=None,
            current_version=current_version,
            current_constituents=current,
            candidate_note=(
                "아직 승인된 버전이 없습니다. 관리자 시험에서 섹션 결과를 확인한 뒤 승인해야"
                " 기본 프리뷰 생성에 포함됩니다."
            ),
        )

    active = _approval(active_row)
    if active.workflow_version != current_version:
        return SectionApprovalStatus(
            workflow_id=workflow_id,
            state=ApprovalState.SUPERSEDED,
            active_approval=None,
            pinned_approval=active,
            current_version=current_version,
            current_constituents=current,
            candidate_note=(
                "현재 구성이 승인된 버전과 다릅니다. 결과 의미를 바꾸는 변경이면 새 버전으로"
                " 다시 확인해야 합니다. 기존 승인은 그대로 유지됩니다."
            ),
        )

    return SectionApprovalStatus(
        workflow_id=workflow_id,
        state=ApprovalState.APPROVED,
        active_approval=active,
        pinned_approval=None,
        current_version=current_version,
        current_constituents=current,
        candidate_note=None,
    )


def describe_approvals(
    session: Session, workflow_ids: Sequence[str] | None = None
) -> dict[str, Any]:
    """여러 섹션의 승인 현황. 데이터가 없으면 없는 그대로 알린다."""
    ids = tuple(workflow_ids or section_workflow_ids())
    statuses = {workflow_id: section_approval_status(session, workflow_id) for workflow_id in ids}
    return {
        "contract_version": APPROVAL_CONTRACT_VERSION,
        "workflows": {
            workflow_id: status.to_dict() for workflow_id, status in statuses.items()
        },
        "approved": [w for w, s in statuses.items() if s.approved],
        "unapproved": [w for w, s in statuses.items() if not s.approved],
        "scope_note": (
            "승인 단위는 섹션 워크플로우입니다. 내부 노드와 D0 같은 자료 준비 단계는"
            " 따로 승인하지 않습니다. 승인은 관리자가 결과를 확인한 뒤에만 만들어집니다."
        ),
    }


def approval_gate_note(status: SectionApprovalStatus) -> str:
    """기본 전체 생성 포함 여부를 화면 문구로 표현한다."""
    if status.approved:
        return "승인된 버전입니다. 기본 전체 프리뷰 생성에 포함할 수 있습니다."
    if status.state is ApprovalState.SUPERSEDED:
        return (
            "이전 승인은 유지되지만 현재 구성은 다시 확인이 필요합니다."
            " 기본 생성에는 승인된 이전 버전을 씁니다."
        )
    return "승인 전입니다. 관리자 시험 또는 명시적 미리보기에서만 실행합니다."


def _require_section_evidence(
    session: Session,
    workflow: SectionWorkflowRegistration,
    run_id: uuid.UUID,
    section_result_id: uuid.UUID | None,
) -> PreviewSectionResult:
    """승인 근거가 실제 저장된 **섹션 본문 결과**인지 확인한다.

    거부 조건을 좁게 유지한다. 근거가 없거나, 다른 실행·다른 섹션의 결과이거나,
    모의 시연으로 만든 결과이거나, 본문을 만들지 못한 결과면 승인 행을 만들지 않는다.
    """
    run = session.get(PreviewRun, run_id)
    if run is None:
        reject_approval_request("승인 근거로 지정한 실행을 찾을 수 없습니다.")
    if run.cancelled_at is not None:
        reject_approval_request("취소된 실행은 승인 근거로 쓸 수 없습니다.")
    if section_result_id is None:
        reject_approval_request(
            "승인에는 확인한 섹션 결과 ID가 필요합니다. 본문을 연 뒤에 승인하세요."
        )

    row = session.get(PreviewSectionResult, section_result_id)
    if row is None:
        reject_approval_request(
            "승인 근거로 지정한 섹션 결과를 찾을 수 없습니다."
        )
    if row.run_id != run_id:
        reject_approval_request(
            "지정한 섹션 결과는 이 실행의 결과가 아닙니다. 확인한 실행과 결과를 함께"
            " 지정해야 합니다."
        )
    if row.workflow_id != workflow.workflow_id:
        reject_approval_request(
            f"지정한 섹션 결과는 {row.workflow_id}의 결과이며"
            f" {workflow.workflow_id} 승인 근거가 아닙니다."
        )
    if row.unavailable_reason is not None or not (row.body or "").strip():
        reject_approval_request(
            "본문이 없는 섹션 결과는 승인 근거로 쓸 수 없습니다."
        )
    if row.mode == RunMode.MOCK.value:
        reject_approval_request(
            "모의 시연 결과는 승인 근거가 아닙니다. 실제 조사·생성 실행의 본문을"
            " 확인한 뒤 승인하세요."
        )
    if run.mode != row.mode:  # pragma: no cover - 같은 실행의 결과는 같은 방식이다
        reject_approval_request("실행 방식과 섹션 결과의 실행 방식이 다릅니다.")
    return row


def approve_section_version(
    session: Session,
    *,
    workflow_id: str,
    run_id: uuid.UUID,
    section_result_id: uuid.UUID | None,
    actor_id: int,
    note: str | None = None,
    now: datetime | None = None,
) -> SectionApproval:
    """관리자가 확인한 섹션 워크플로우 버전을 승인한다.

    승인 단위는 섹션을 만드는 완결된 워크플로우이며, 근거는 그 워크플로우가 실제로
    만든 **섹션 본문 결과**다. 근거가 확인되지 않으면 행을 만들지 않는다.

    같은 워크플로우에 이미 활성 승인이 있으면 그 행은 지우지 않고 `active`만 내린 뒤,
    새 승인이 `supersedes_approval_id`로 가리킨다. 그래서 "언제 무엇을 어떤 근거로
    승인했는지"가 그대로 남는다.
    """
    if actor_id is None or actor_id <= 0:
        reject_approval_request("승인자 계정 ID가 필요합니다.")
    workflow = get_section_workflow(workflow_id)
    row = _require_section_evidence(session, workflow, run_id, section_result_id)

    constituents = _constituents_from_results(
        workflow, _results_of_run(session, run_id)
    )
    workflow_version, ordered = release_version(workflow, constituents)
    moment = now or datetime.now(timezone.utc)

    active_rows = [
        entry for entry in _rows(session, workflow_id) if entry.active
    ]
    for entry in active_rows:
        entry.active = False
    session.flush()

    approval = PreviewSectionApproval(
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        version_hash=version_hash(workflow_id, workflow_version, ordered),
        constituents=[item.to_dict() for item in ordered],
        reviewed_run_id=run_id,
        section_result_id=row.id,
        approved_by_actor_id=actor_id,
        approved_at=moment,
        reviewed_note=note,
        active=True,
        supersedes_approval_id=active_rows[0].id if active_rows else None,
    )
    session.add(approval)
    session.flush()
    session.add(
        PreviewWriteAudit(
            run_id=run_id,
            actor_id=actor_id,
            action="section_approved",
            target_table="preview_section_approvals",
            target_id=str(approval.id),
            detail={
                "workflow_id": workflow_id,
                "workflow_version": workflow_version,
                "section_result_id": str(row.id),
                "evidence_mode": row.mode,
            },
        )
    )
    session.flush()
    return _approval(approval)
