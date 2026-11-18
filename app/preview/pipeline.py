"""MP-10 전체 프리뷰 실행: LangGraph 분기·합류·재개 + 저장 어댑터.

흐름:

    D0(저장 자료 준비, 호출 0)
      ├─ R1(경기력·주목 선수) ─┐
      ├─ R2(부상·결장 영향)   ├─ V0(근거 검증) → S1(종합 1회) → V1(표현 투영·저장)
      └─ R3(배당·외부 전망)   ─┘

무엇이 이 파일의 책임인가:

- 노드 **순서·분기·합류·재시작**은 LangGraph가 판정한다. 이 파일은 노드가 부를 기존
  모듈 구현을 조립하고, 끝난 결과를 `preview_dev`에 남기고, 진행 상태를 갱신한다.
- 판정·문장 생성·근거 검증은 `form`/`availability`/`outlook`/`synthesis` 구현이 그대로
  한다. 여기서 문장을 만들거나 필터를 다시 돌리지 않는다.

하나의 예산, 하나의 실행기:

- 조사 3 + 종합 1을 **한 `RunBudget`**으로 센다. 갈래마다 예산을 새로 만들지 않는다.
- 실제 전송·재시도·시도 기록은 기존 `provider.execute_request` 하나가 소유한다.

동시성:

- 갈래는 서로 다른 스레드에서 동시에 돈다. SQLAlchemy `Session`은 스레드에 안전하지
  않으므로 **갈래마다 자기 세션**을 열어 저장하고 커밋한 뒤 닫는다. 메인 스레드는
  요약값만 받는다.
- 네트워크 재시도 대기 중에 DB 연결을 붙들지 않는다. 갈래 세션은 자기 쓰기 단위로만
  열려 있다.

정직성:

- 승인이 없으면 기본 전체 프리뷰는 시작하지 않고 명시적 대기로 멈춘다.
- API-Football 실시간 transport 연결은 아직 없다(MP-03 잔여). D0는 저장 자료만 읽고,
  전송 계층이 없으면 그 사실을 상태·진단으로 드러낸다. 없는 성공을 만들지 않는다.
- 저장 응답 재생(`replay`)과 재개(`resume`)와 DB undo는 서로 다른 동작이다. 재개는
  성공한 결과를 **다시 호출하지 않고** 남은 단계만 이어서 돈다.
"""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Callable, Mapping, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.preview import (
    approvals,
    jobs,
    sections,
    store,
    version_manifest,
)
from app.preview.contracts import (
    CONTRACT_VERSION,
    Environment,
    ExecutionContext,
    FixtureIdentity,
    ModuleInput,
    OperationKind,
    QualityStatus,
    RunMode,
    RunStatus,
    compute_input_hash,
)
from app.preview.models import PreviewModuleExecution, PreviewResult
from app.preview.registry import get_section_workflow
from app.preview.modules import (
    availability,
    compose as compose_module,
    form,
    outlook,
    synthesis,
)
from app.preview.retry import BudgetLimits, RunBudget

__all__ = [
    "AdmissionRefused",
    "PIPELINE_CONFIG_VERSION",
    "PIPELINE_NODES",
    "PipelineOutcome",
    "RESEARCH_MODULE_IDS",
    "SECTION_WORKFLOW_IDS",
    "admission_state",
    "resume_preview_run",
    "rerun_module",
    "rerun_preview",
    "resynthesize_preview",
    "start_preview_run",
]

# 이 실행이 만드는 섹션. 순서는 표시 순서이고 승인 단위와 같다.
SECTION_WORKFLOW_IDS = (
    "section_form",
    "section_availability",
    "section_outlook",
    "section_players",
)

# 병렬 조사 갈래. 하나의 예산을 함께 쓴다.
RESEARCH_MODULE_IDS = ("R1", "R2", "R3", "R4")

# 저장되는 진행 단계. 승인 단위가 아니라 진단 단위다.
PIPELINE_NODES = ("D0", "R1", "R2", "R3", "R4", "V0", "S1", "V1")

PIPELINE_CONFIG_VERSION = "mp10-pipeline-1"

# 갈래가 만드는 섹션: 조사 모듈 → 워크플로우.
_MODULE_TO_SECTION = {
    "R1": "section_form",
    "R2": "section_availability",
    "R3": "section_outlook",
    "R4": "section_players",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AdmissionRefused(RuntimeError):
    """승인이 없거나 현재 구성이 승인 버전과 달라 기본 전체 프리뷰를 시작할 수 없다."""

    def __init__(self, message: str, *, missing: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.message = message
        self.missing = tuple(missing)


@dataclass(frozen=True)
class PipelineOutcome:
    """전체 실행의 결론. 화면은 `run_id`로 저장된 결과를 다시 연다."""

    run_id: uuid.UUID
    admission: str
    status: RunStatus
    quality: QualityStatus
    stage: str
    mode: RunMode
    workflow_versions: dict[str, str] = field(default_factory=dict)
    section_result_ids: dict[str, uuid.UUID] = field(default_factory=dict)
    selected_result_ids: tuple[uuid.UUID, ...] = ()
    external_calls: int = 0
    budget: Mapping[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None
    waiting_reason: str | None = None
    diagnostics: tuple[str, ...] = ()
    completed_nodes: tuple[str, ...] = ()
    joined_existing: bool = False
    resume_of_run_id: uuid.UUID | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "admission": self.admission,
            "status": self.status.value,
            "quality": self.quality.value,
            "stage": self.stage,
            "mode": self.mode.value,
            "workflow_versions": dict(self.workflow_versions),
            "section_result_ids": {
                key: str(value) for key, value in self.section_result_ids.items()
            },
            "selected_result_ids": [str(item) for item in self.selected_result_ids],
            "external_calls": self.external_calls,
            "budget": dict(self.budget),
            "unavailable_reason": self.unavailable_reason,
            "waiting_reason": self.waiting_reason,
            "diagnostics": list(self.diagnostics),
            "completed_nodes": list(self.completed_nodes),
            "joined_existing": self.joined_existing,
            "resume_of_run_id": str(self.resume_of_run_id) if self.resume_of_run_id else None,
        }


# --------------------------------------------------------------------------
# 승인 게이트
# --------------------------------------------------------------------------


def required_workflows() -> tuple[str, ...]:
    """기본 전체 프리뷰가 실행하는 섹션 워크플로우(조사 3 + 종합)."""
    return SECTION_WORKFLOW_IDS + (synthesis.SECTION_WORKFLOW_ID,)


def bundle_workflows() -> tuple[str, ...]:
    """공통 생성 서비스(`bundle_pipeline`)가 **실제로 만드는** 섹션 집합.

    출처를 하나로 쓴다. 생성 서비스가 만드는 섹션은
    `information_bundle.SECTION_IDS`이므로, 승인 판정도 같은 값을 순회해야 실제 생성물과
    어긋나지 않는다. 옛 파이프라인 경로(`required_workflows`)의 의미는 그대로 둔다.
    """
    from app.preview import information_bundle

    return tuple(information_bundle.SECTION_IDS)


def _judge(workflows: Sequence[str], session: Session) -> dict[str, Any]:
    """주어진 워크플로우 집합에 대한 승인 준비 상태. 두 경로가 같은 판정 로직을 쓴다."""
    statuses = {
        workflow_id: approvals.section_approval_status(session, workflow_id)
        for workflow_id in workflows
    }
    approved = [wf for wf, status in statuses.items() if status.approved]
    missing = [wf for wf in workflows if wf not in approved]
    current = {wf: version_manifest.workflow_version_of(wf) for wf in workflows}
    approved_versions = {
        wf: (statuses[wf].active_approval.workflow_version if statuses[wf].active_approval else None)
        for wf in workflows
    }
    # 승인된 버전과 지금 코드의 구성이 다르면 그 섹션은 "승인됨"이 아니다.
    stale = [
        wf
        for wf in workflows
        if approved_versions.get(wf) and approved_versions[wf] != current[wf]
    ]
    return {
        "ready": not missing and not stale,
        "missing_approval": missing,
        "stale_approval": stale,
        "approved": approved,
        "current_versions": current,
        "approved_versions": approved_versions,
    }


def bundle_admission_state(session: Session) -> dict[str, Any]:
    """공통 생성 서비스가 만드는 섹션 집합의 승인 준비 상태(**진단·표시용**).

    `admission_state`(옛 전체 프리뷰 대상)와 달리 form/synthesis를 요구하지 않고
    odds/ai_forecast를 포함한다. 승인 행은 읽기만 한다.

    현재 이 판정은 **자동 생성을 막지 않는다.** 수집 후 자동 생성은 승인 게이트를 쓰지
    않으므로(2026-11-18 확정), 이 값이 `ready=false`여도 생성과 홈 공개는 그대로 진행된다.
    값의 의미는 "그 섹션들의 워크플로우 버전 승인이 저장돼 있는지"까지다.
    """
    judged = _judge(bundle_workflows(), session)
    return {
        **judged,
        "scope": "bundle",
        "workflows": list(bundle_workflows()),
        "note": (
            "공통 생성 서비스가 만드는 정보 원문 묶음 섹션의 워크플로우 버전 승인 현황입니다."
            " 이 값은 자동 생성을 막지 않습니다(수집 후 생성·홈 공개는 승인과 무관)."
            " 승인 행을 만들거나 바꾸지도 않습니다."
        ),
    }


def admission_state(session: Session) -> dict[str, Any]:
    """**legacy 전체 프리뷰 경로**의 섹션 워크플로우 버전 승인 현황.

    이 값이 뜻하는 것: legacy `start_preview_run`(기본 전체 프리뷰)이 요구하는 섹션
    워크플로우 **버전 승인이 저장돼 있는지**다. 번역 후보의 검수 상태나 선수 연결 상태를
    뜻하지 않는다(그 둘은 다른 저장 경로가 소유한다).

    현재 범위와의 관계: 수집 후 자동 생성, bundle 생성, 홈 문서·추천은 이 값을 **쓰지
    않는다**(2026-11-18 확정: 승인은 게시 허가가 아니다). 다만 legacy 전체 프리뷰 시작은
    지금도 이 승인을 요구하며, 그 경로에서는 이 판정이 실행을 막는다. 판정 로직·버전
    계산은 그대로이며 문구만 실제 범위에 맞췄다.
    """
    workflows = required_workflows()
    judged = _judge(workflows, session)
    missing = judged["missing_approval"]
    stale = judged["stale_approval"]
    approved = judged["approved"]
    current = judged["current_versions"]
    approved_versions = judged["approved_versions"]
    return {
        "ready": judged["ready"],
        "missing_approval": missing,
        "stale_approval": stale,
        "approved": approved,
        "current_versions": current,
        "approved_versions": approved_versions,
        "note": (
            "이 값은 **legacy 전체 프리뷰 경로**의 섹션 워크플로우 버전 승인 현황입니다."
            " 번역 후보 검수 상태나 선수 연결을 뜻하지 않습니다. 현재 수집 후 자동 생성·"
            "bundle 생성·홈 공개는 이 값과 무관하며, 승인되지 않은 본문도 홈에 표시됩니다."
            " 다만 legacy 전체 프리뷰 시작은 지금도 승인을 요구하므로 그 경로에서만"
            " 이 판정이 실행을 막습니다."
        ),
    }


# --------------------------------------------------------------------------
# 실행 계획 (한 번의 호출 안에서만 사는 판단 근거)
# --------------------------------------------------------------------------


@dataclass
class _Plan:
    run_id: uuid.UUID
    fixture: Mapping[str, Any] | None
    mode: RunMode
    admission: str
    transport: Any | None
    reader: Any | None
    budget: RunBudget
    actor_id: int
    now: datetime
    selected_result_ids: tuple[uuid.UUID, ...] = ()
    # 이미 성공한 조사 결과를 재사용할지. 재개·시작은 재사용하고, 명시적 모듈
    # 재실행만 새 버전을 만든다.
    reuse_existing: bool = True

    @property
    def identity(self) -> FixtureIdentity | None:
        if not isinstance(self.fixture, Mapping) or not self.fixture:
            return None
        try:
            return FixtureIdentity.from_dict(dict(self.fixture))
        except (KeyError, TypeError, ValueError):
            return None


def _module_input(
    *,
    module_id: str,
    plan: _Plan,
    implementation_version: str,
    prompt_version: str,
    snapshot_ids: Sequence[uuid.UUID] = (),
    selected_result_ids: Sequence[uuid.UUID] = (),
    node: str = "pipeline",
) -> ModuleInput:
    return ModuleInput(
        module_id=module_id,
        fixture=plan.identity,
        snapshot_ids=tuple(snapshot_ids),
        selected_result_ids=tuple(selected_result_ids),
        input_hash=compute_input_hash(
            {
                "module_id": module_id,
                "run_id": str(plan.run_id),
                "fixture": dict(plan.fixture or {}),
                "snapshot_ids": [str(item) for item in snapshot_ids],
                "selected_result_ids": [str(item) for item in selected_result_ids],
                "implementation": implementation_version,
                "prompt": prompt_version,
            }
        ),
        prompt_version=prompt_version,
        contract_version=CONTRACT_VERSION,
        implementation_version=implementation_version,
        parameters={"node": node},
    )


# --------------------------------------------------------------------------
# D0 — 저장 자료 준비 (외부 호출 0)
# --------------------------------------------------------------------------


def _prepare_node(*, plan: _Plan) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """저장된 경기·순위·부상 자료를 읽어 공유 사실을 만든다. 외부 호출은 0회다.

    실제 API 수집(API-Football live)은 MP-03 잔여 범위이며 여기서 만들지 않는다.
    읽기 연결이 없으면 그 사실을 진단으로 남기고 빈 사실을 지어내지 않는다.
    """

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = plan_session_factory()()
        try:
            stored = sections.read_stored_context(
                session,
                fixture=plan.fixture,
                reader=plan.reader,
                run_id=plan.run_id,
                actor_id=plan.actor_id,
                now=plan.now,
            )
            facts = stored.facts
            payload = {
                "fixture": {
                    "fixture_id": facts.fixture_id,
                    "league_id": facts.league_id,
                    "season": facts.season,
                    "home_team_id": facts.home_team_id,
                    "away_team_id": facts.away_team_id,
                    "kickoff_at": facts.kickoff_at.isoformat(),
                    "home_team": facts.home_team,
                    "away_team": facts.away_team,
                    "league": facts.league,
                },
                "facts": [fact.to_dict() for fact in facts.facts],
                "snapshot_ids": list(stored.snapshot_ids),
                "claims": [],
                "coverage": [entry.to_dict() for entry in stored.coverage],
            }
            _save_step_result(
                session,
                plan=plan,
                module_id="D0",
                implementation_version=sections.STORED_DATA_IMPLEMENTATION_VERSION,
                prompt_version="",
                node="prepare_data",
                payload=payload,
                diagnostics=stored.diagnostics,
                quality=QualityStatus.READY,
                status_value="succeeded",
            )
            session.commit()
            return {
                "data": payload,
                "diagnostics": [str(item) for item in stored.diagnostics],
                "completed": ["D0"],
            }
        except Exception as exc:  # noqa: BLE001 - 실패를 숨기지 않고 상태로 남긴다
            session.rollback()
            reason = f"저장 자료 준비에 실패했습니다: {exc}"
            return {
                "data": None,
                "diagnostics": [reason],
                "unavailable_reason": reason,
                "completed": ["D0"],
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# 갈래 실행기 (갈래마다 자기 세션)
# --------------------------------------------------------------------------

_SESSION_FACTORY: sessionmaker | None = None


def bind_session_factory(factory: sessionmaker) -> None:
    """이 프로세스가 쓸 세션 팩토리. 갈래마다 여기서 새 세션을 연다."""
    global _SESSION_FACTORY
    _SESSION_FACTORY = factory


def plan_session_factory() -> sessionmaker:
    if _SESSION_FACTORY is None:
        from app.preview.db import get_session_factory

        return get_session_factory()
    return _SESSION_FACTORY


def _next_execution_ordinal(session: Session, run_id: uuid.UUID, module_id: str) -> int:
    from sqlalchemy import func

    return int(
        session.scalar(
            select(func.count())
            .select_from(PreviewModuleExecution)
            .where(
                PreviewModuleExecution.run_id == run_id,
                PreviewModuleExecution.module_id == module_id,
            )
        )
        or 0
    )


def _save_step_result(
    session: Session,
    *,
    plan: _Plan,
    module_id: str,
    implementation_version: str,
    prompt_version: str,
    node: str,
    payload: Mapping[str, Any],
    diagnostics: Sequence[str] = (),
    quality: QualityStatus = QualityStatus.READY,
    status_value: str = "succeeded",
    selected_result_ids: Sequence[uuid.UUID] = (),
    snapshot_ids: Sequence[uuid.UUID] = (),
) -> uuid.UUID:
    """단계 하나의 실행·결과 행을 저장한다. 오래된 실행자면 결과를 만들지 않는다."""
    execution = store.start_module_execution(
        session,
        run_id=plan.run_id,
        module_id=module_id,
        ordinal=_next_execution_ordinal(session, plan.run_id, module_id),
        module_input=_module_input(
            module_id=module_id,
            plan=plan,
            implementation_version=implementation_version,
            prompt_version=prompt_version,
            snapshot_ids=snapshot_ids,
            selected_result_ids=selected_result_ids,
            node=node,
        ),
        actor_id=plan.actor_id,
    )
    from app.preview.contracts import ModuleResult, ModuleStatus

    saved = store.save_module_result(
        session,
        ModuleResult(
            result_id=uuid.uuid4(),
            module_id=module_id,
            module_execution_id=execution.id,
            run_id=plan.run_id,
            version=1,
            input_hash=execution.input_hash,
            status=ModuleStatus(status_value),
            quality=quality,
            claims=tuple((payload or {}).get("claims") or ()),
            coverage=tuple((payload or {}).get("coverage") or ()),
            diagnostics=tuple(str(item) for item in diagnostics),
            implementation_version=implementation_version,
            prompt_version=prompt_version,
            contract_version=CONTRACT_VERSION,
            payload=dict(payload),
        ),
        actor_id=plan.actor_id,
    )
    store.update_module_delivery(
        session,
        execution.id,
        {
            "target_module_id": None,
            "selected_result_ids": [str(saved.id)],
            "values": [{"key": "node", "value": node}],
            "note": "전체 프리뷰 내부 단계입니다. 승인 단위가 아니라 진단 정보입니다.",
        },
        status=ModuleStatus(status_value),
        quality=quality,
    )
    return saved.id


def _branch_node(module_id: str, *, plan: _Plan) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """조사 갈래 하나. 자기 세션에서 실행하고 저장한 뒤 요약만 돌려준다."""

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        data = state.get("data")
        if not isinstance(data, Mapping) or not data:
            reason = (
                f"{module_id} 조사에 필요한 공유 자료가 없어 이 갈래를 실행하지 않았습니다."
            )
            # 시작하지 않기로 확정된 호출의 예약을 반환한다. 전체 상한은 늘지 않는다.
            plan.budget.cancel_call(_branch_logical_call_id(module_id))
            return {
                "research": [{"module_id": module_id, "result_id": None, "status": "failed"}],
                "diagnostics": [reason],
                "completed": [module_id],
            }

        # 재개·재시작은 성공한 조사 결과를 **다시 호출하지 않는다**. 같은 구현 버전의
        # 성공 결과가 이미 있으면 그 행을 그대로 입력으로 쓴다(새 과금 없음).
        if plan.reuse_existing:
            reused = _existing_success(session_factory=plan_session_factory(), plan=plan, module_id=module_id)
            if reused is not None:
                # 성공한 결과를 다시 부르지 않는다. 그 호출의 예약 몫도 반환한다.
                plan.budget.cancel_call(_branch_logical_call_id(module_id))
                return {
                    "research": [reused],
                    "diagnostics": [],
                    "completed": [module_id],
                }

        # 갈래마다 새 세션을 연다. Session은 스레드에 안전하지 않다.
        session = plan_session_factory()()
        try:
            implementation = _implementation_for(module_id, plan=plan)
            from app.preview.runner import run_module

            result = run_module(
                session,
                module_id=module_id,
                module_input=_module_input(
                    module_id=module_id,
                    plan=plan,
                    implementation_version=implementation.implementation_version,
                    prompt_version=implementation.prompt_version or "",
                    node="research",
                ),
                context=ExecutionContext(
                    run_id=plan.run_id,
                    operation_kind=OperationKind.PREVIEW,
                    environment=Environment.DEV,
                    mode=plan.mode,
                    actor_id=plan.actor_id,
                    config_version=PIPELINE_CONFIG_VERSION,
                    limits=plan.budget.limits.execution_limits(),
                ),
                implementation=implementation,
                transport=plan.transport,
                budget=plan.budget,
                # 모듈 계약은 앞 단계 산출을 `state["data"]`에서 읽는다. D0 payload를
                # 최상위로 펼치면 사실이 없는 것으로 보여 모든 주장이 근거 없음이 된다.
                state={"data": dict(data), "fixture": plan.fixture},
            )
            session.commit()
            payload = dict(result.payload or {})
            return {
                "research": [
                    {
                        "module_id": module_id,
                        "result_id": str(result.result_id),
                        "status": result.status.value,
                        "quality": result.quality.value,
                        "unavailable_reason": payload.get("unavailable_reason"),
                    }
                ],
                "diagnostics": [str(item) for item in result.diagnostics],
                "completed": [module_id],
            }
        except Exception as exc:  # noqa: BLE001
            # 한 갈래가 실패해도 다른 갈래의 저장 결과를 지우지 않는다.
            session.rollback()
            return {
                "research": [{"module_id": module_id, "result_id": None, "status": "failed"}],
                "diagnostics": [f"{module_id} 조사 갈래가 실패했습니다: {exc}"],
                "completed": [module_id],
            }
        finally:
            session.close()

    return run


def _branch_logical_call_id(module_id: str) -> str:
    """갈래의 논리 호출 ID. 모듈이 실제로 쓰는 값을 그대로 가리킨다.

    예산의 예약 반환은 "이 호출을 시작하지 않는다"는 판단과 같은 이름을 써야 한다.
    다른 이름을 쓰면 반환이 아무 효과도 없거나 엉뚱한 몫을 푼다.
    """
    if module_id == "S1":
        return synthesis.LOGICAL_CALL_ID
    if module_id == "R2":
        return availability.LOGICAL_CALL_ID
    if module_id == "R3":
        # outlook 모듈은 `f"{MODULE_ID}-outlook"` 형식을 쓴다.
        return f"{outlook.MODULE_ID}-outlook"
    if module_id == "R4":
        from app.preview.modules import players as players_module

        return players_module.LOGICAL_CALL_ID
    # R1은 `research_form`의 기본 인자와 같은 값을 쓴다.
    return "R1-form"


def _implementation_for(module_id: str, *, plan: _Plan):
    """모듈 id → 기존 노드 구현. 섹션 실행과 같은 팩토리를 쓴다."""
    if module_id == "R1":
        return sections._research_node(transport=plan.transport, now=plan.now)  # noqa: SLF001
    if module_id == "R2":
        return availability.availability_research_node(
            transport=plan.transport, reader=plan.reader, now=plan.now, mode=plan.mode
        )
    if module_id == "R3":
        return outlook.outlook_node_implementation(mode=plan.mode, transport=plan.transport)
    if module_id == "R4":
        from app.preview.modules import players as players_module

        return players_module.players_research_node(
            transport=plan.transport,
            resolver=sections._name_resolver(reader=plan.reader),  # noqa: SLF001
            roster=(),
            id_space="internal",
            now=plan.now,
            mode=plan.mode,
        )
    if module_id == "S1":
        return synthesis.build_synthesis_implementations(
            transport=plan.transport, reader=plan.reader, now=plan.now, mode=plan.mode
        ).research[0]
    raise KeyError(f"no implementation for module {module_id!r}")


# --------------------------------------------------------------------------
# V0 — 근거 검증 (기존 validate_evidence 재사용, 외부 호출 0)
# --------------------------------------------------------------------------


def _validation_node(*, plan: _Plan) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """갈래 결과를 모아 S1 입력(ValidatedEvidence)을 만든다.

    검증 규칙은 `validation.validate_evidence`가 소유한다. 여기서 새 필터나 판정을
    만들지 않는다. 선택된 결과 ID는 갈래가 실제로 저장한 결과와 같아야 한다.
    """

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        results = [item for item in (state.get("research") or []) if isinstance(item, Mapping)]
        result_ids = [
            uuid.UUID(str(item["result_id"]))
            for item in results
            if item.get("result_id")
        ]
        session = plan_session_factory()()
        try:
            from app.preview.validation import validate_evidence

            selected, snapshots, _names = synthesis.load_selected_results(
                session, run_id=plan.run_id, selected_result_ids=result_ids
            )
            evidence = validate_evidence(
                fixture=plan.identity,
                results=selected,
                snapshots=snapshots,
                module_ids=RESEARCH_MODULE_IDS,
                selected_result_ids=result_ids,
                now=plan.now,
            )
            payload = evidence.to_dict()
            _save_step_result(
                session,
                plan=plan,
                module_id="V0",
                implementation_version="mp10-evidence-validation-1",
                prompt_version="",
                node="validate_evidence",
                payload=payload,
                diagnostics=tuple(gap.to_text() for gap in evidence.gaps),
                quality=(
                    QualityStatus.READY
                    if evidence.core_evidence_satisfied
                    else QualityStatus.INSUFFICIENT
                ),
                selected_result_ids=result_ids,
                snapshot_ids=tuple(evidence.snapshot_ids),
            )
            session.commit()
            return {
                "validated": payload,
                "completed": ["V0"],
                "diagnostics": [gap.to_text() for gap in evidence.gaps],
                "unavailable_reason": (
                    None
                    if evidence.core_evidence_satisfied
                    else "참조가 붙은 채택 사실이 없어 종합 단계로 진행하지 않습니다."
                ),
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"근거 검증에 실패했습니다: {exc}"
            return {
                "validated": None,
                "completed": ["V0"],
                "diagnostics": [reason],
                "unavailable_reason": reason,
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# S1 — 종합 1회 (기존 synthesis 재사용)
# --------------------------------------------------------------------------


def _synthesis_node(*, plan: _Plan) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """검증된 입력으로 S1을 **한 번** 호출한다. 새 검색·숨은 재검토 호출은 없다."""

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        validated = state.get("validated")
        if not isinstance(validated, Mapping) or not validated:
            reason = (
                "검증된 입력이 없어 S1 종합을 실행하지 않았습니다."
                " 근거 검증 사유는 관리자 기록에 남겼습니다."
            )
            return {
                "synthesis": {"status": "skipped"},
                "completed": ["S1"],
                "diagnostics": [reason],
                "unavailable_reason": reason,
            }
        result_ids = [
            uuid.UUID(str(item))
            for item in (validated.get("selected_result_ids") or [])
            if item
        ]
        session = plan_session_factory()()
        try:
            implementation = _implementation_for("S1", plan=plan)
            from app.preview.runner import run_module

            result = run_module(
                session,
                module_id="S1",
                module_input=_module_input(
                    module_id="S1",
                    plan=plan,
                    implementation_version=implementation.implementation_version,
                    prompt_version=implementation.prompt_version or "",
                    selected_result_ids=result_ids,
                    node="research",
                ),
                context=ExecutionContext(
                    run_id=plan.run_id,
                    operation_kind=OperationKind.PREVIEW,
                    environment=Environment.DEV,
                    mode=plan.mode,
                    actor_id=plan.actor_id,
                    config_version=PIPELINE_CONFIG_VERSION,
                    limits=plan.budget.limits.execution_limits(),
                ),
                implementation=implementation,
                transport=plan.transport,
                budget=plan.budget,
                state={
                    "data": {
                        "validated": dict(validated),
                        "fixture": plan.fixture,
                        "fixture_names": {},
                    }
                },
            )
            session.commit()
            payload = dict(result.payload or {})
            return {
                "synthesis": {
                    "result_id": str(result.result_id),
                    "status": result.status.value,
                    "quality": result.quality.value,
                },
                "completed": ["S1"],
                "diagnostics": [str(item) for item in result.diagnostics],
                "unavailable_reason": (
                    payload.get("unavailable_reason")
                    if isinstance(payload.get("unavailable_reason"), str)
                    else None
                ),
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"S1 종합 단계가 실패했습니다: {exc}"
            return {
                "synthesis": {"status": "failed"},
                "completed": ["S1"],
                "diagnostics": [reason],
                "unavailable_reason": reason,
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# V1 — 표현 투영·섹션 결과 저장 (외부 호출 0)
# --------------------------------------------------------------------------


def _projection_node(*, plan: _Plan) -> Callable[[Mapping[str, Any]], dict[str, Any]]:
    """조사 결과와 S1 결과를 **섹션 결과 행**으로 남긴다.

    각 섹션 결과는 그 섹션을 실제로 만든 모듈 결과 행만 가리킨다. 그래야 승인이
    검토한 본문의 구성(manifest)과 스탬프를 그대로 쓸 수 있다(기존 F3 계약).
    """

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        results = [item for item in (state.get("research") or []) if isinstance(item, Mapping)]
        by_module = {
            str(item.get("module_id")): str(item.get("result_id"))
            for item in results
            if item.get("result_id")
        }
        experiment = state.get("synthesis") or {}
        session = plan_session_factory()()
        saved: dict[str, str] = {}
        diagnostics: list[str] = []
        try:
            for module_id, workflow_id in _MODULE_TO_SECTION.items():
                result_id = by_module.get(module_id)
                if not result_id:
                    diagnostics.append(
                        f"{workflow_id} 섹션 결과를 만들지 않았습니다:"
                        f" {module_id} 조사 결과가 없습니다."
                    )
                    continue
                section_row_id = _save_section_from_module(
                    session,
                    plan=plan,
                    workflow_id=workflow_id,
                    module_result_id=uuid.UUID(result_id),
                )
                saved[workflow_id] = str(section_row_id)
            if experiment.get("result_id"):
                section_row_id = _save_section_from_module(
                    session,
                    plan=plan,
                    workflow_id=synthesis.SECTION_WORKFLOW_ID,
                    module_result_id=uuid.UUID(str(experiment["result_id"])),
                )
                saved[synthesis.SECTION_WORKFLOW_ID] = str(section_row_id)
            session.commit()
            return {
                "projection": saved,
                "completed": ["V1"],
                "diagnostics": diagnostics,
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"섹션 결과 저장에 실패했습니다: {exc}"
            return {
                "projection": {},
                "completed": ["V1"],
                "diagnostics": [reason],
                "unavailable_reason": reason,
            }
        finally:
            session.close()

    return run


def _save_section_from_module(
    session: Session,
    *,
    plan: _Plan,
    workflow_id: str,
    module_result_id: uuid.UUID,
) -> uuid.UUID:
    """모듈 결과 하나로 섹션 결과 행을 만든다. 본문·근거·버전을 저장 행에서 그대로 쓴다."""
    from app.preview.contracts import SECTION_RESULT_CONTRACT_VERSION

    workflow = get_section_workflow(workflow_id)
    module_row = session.get(PreviewResult, module_result_id)
    if module_row is None:
        raise store.RunNotFound(f"module result {module_result_id} not found")
    stored = dict(module_row.payload or {})
    inner = stored.get("payload")
    body_payload = dict(inner) if isinstance(inner, Mapping) else stored

    body = ""
    title = workflow.display_name
    sources: Sequence[Mapping[str, Any]] = ()
    quality = QualityStatus(module_row.quality)
    unavailable = body_payload.get("unavailable_reason")

    if workflow_id == synthesis.SECTION_WORKFLOW_ID:
        reader = body_payload.get("reader_preview") or {}
        body = str(reader.get("body") or "")
        title = str(reader.get("headline") or workflow.display_name)
        sources = tuple(
            dict(item) for item in (reader.get("sources") or ()) if isinstance(item, Mapping)
        )
    elif workflow_id == "section_form" and not unavailable:
        composed = compose_module.compose_form_body(body_payload)
        body = composed.body
        title = composed.title
        sources = tuple(row for row in composed.sources if row.get("kind") == "api")
        quality = composed.quality
        unavailable = composed.unavailable_reason
    elif workflow_id == "section_availability" and not unavailable:
        composed = availability.compose_availability_body(body_payload)
        body = composed.body
        title = composed.title
        sources = tuple(composed.sources)
        quality = composed.quality
        # 이 조립 결과는 `unavailable_reason`을 따로 두지 않는다. 본문이 비면 그 자체가
        # "만들 수 없음"이므로 빈 본문을 성공으로 저장하지 않게 여기서 정한다.
        if not body.strip():
            unavailable = "근거가 확인된 부상·결장 항목이 없어 섹션 본문을 만들지 않았습니다."
    elif workflow_id == "section_players" and not unavailable:
        from app.preview.modules import players as players_module

        composed = players_module.compose_players_body(body_payload)
        body = composed.body
        title = composed.title
        sources = tuple(composed.sources)
        quality = composed.quality
        if not body.strip():
            unavailable = "표시할 주목 선수 이름·이유가 없어 섹션 본문을 만들지 않았습니다."
    elif workflow_id == "section_outlook" and not unavailable:
        composed = outlook.compose_outlook_section(body_payload)
        body = composed.body
        title = composed.title
        sources = tuple(composed.sources)
        quality = composed.quality
        unavailable = composed.unavailable_reason

    manifest = version_manifest.constituents_for_workflow(workflow_id)
    workflow_version = version_manifest.workflow_version_of(workflow_id)
    version = _next_section_version(session, plan.run_id, workflow_id)

    row = store.save_section_result(
        session,
        run_id=plan.run_id,
        workflow_id=workflow_id,
        workflow_version=workflow_version,
        title=title or workflow.display_name,
        body=body,
        version=version,
        mode=plan.mode,
        environment=Environment.DEV,
        quality=quality,
        output_contract_version=workflow.output_contract_version,
        contract_version=SECTION_RESULT_CONTRACT_VERSION,
        sources=sources,
        module_execution_ids=[module_row.module_execution_id],
        result_ids=[module_row.id],
        diagnostics=(
            tuple(str(item) for item in module_row.payload.get("diagnostics") or ())
            if isinstance(module_row.payload, Mapping)
            else ()
        ),
        unavailable_reason=str(unavailable) if unavailable else None,
        actor_id=plan.actor_id,
        now=plan.now,
    )
    return row.id


def _next_section_version(session: Session, run_id: uuid.UUID, workflow_id: str) -> int:
    from app.preview.models import PreviewSectionResult

    current = session.scalar(
        select(PreviewSectionResult.version)
        .where(
            PreviewSectionResult.run_id == run_id,
            PreviewSectionResult.workflow_id == workflow_id,
        )
        .order_by(PreviewSectionResult.version.desc())
        .limit(1)
    )
    return int(current or 0) + 1


# --------------------------------------------------------------------------
# 그래프 조립
# --------------------------------------------------------------------------


class _GraphState(TypedDict, total=False):
    """그래프가 노드 사이로 넘기는 상태.

    병렬 갈래가 같은 키에 쓰므로 리듀서를 붙인다. 값은 JSON 직렬화 가능한 기본형만
    넣는다(SQLAlchemy 객체·세션은 상태에 넣지 않는다).
    """

    data: dict[str, Any] | None
    research: Annotated[list, operator.add]
    validated: dict[str, Any] | None
    synthesis: dict[str, Any] | None
    projection: dict[str, Any] | None
    diagnostics: Annotated[list, operator.add]
    completed: Annotated[list, operator.add]
    # 갈래 셋이 같은 단계 키에 쓰므로 문자열 하나로 두면 충돌한다. 완료 단계 목록이
    # 진행 상태의 근거이고, 마지막 단계 이름은 그 목록에서 계산한다.
    unavailable_reason: str | None


def build_preview_graph(*, plan: _Plan, checkpointer: Any | None = None):
    """전체 프리뷰 그래프. 분기·합류는 그래프가, 판정은 노드가 맡는다.

        START → D0 → (R1‖R2‖R3) → V0 → S1 → V1 → END
    """
    graph: StateGraph = StateGraph(_GraphState)

    graph.add_node("D0", _prepare_node(plan=plan))
    for module_id in RESEARCH_MODULE_IDS:
        graph.add_node(module_id, _branch_node(module_id, plan=plan))
    graph.add_node("V0", _validation_node(plan=plan))
    graph.add_node("S1", _synthesis_node(plan=plan))
    graph.add_node("V1", _projection_node(plan=plan))

    graph.add_edge(START, "D0")
    for module_id in RESEARCH_MODULE_IDS:
        graph.add_edge("D0", module_id)
        graph.add_edge(module_id, "V0")
    graph.add_edge("V0", "S1")
    graph.add_edge("S1", "V1")
    graph.add_edge("V1", END)

    return graph.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------


def _run_graph(
    *,
    plan: _Plan,
    checkpointer: Any | None = None,
    resume: bool = False,
) -> Mapping[str, Any]:
    app = build_preview_graph(plan=plan, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": str(plan.run_id)}}
    initial: dict[str, Any] = {
        "research": [],
        "diagnostics": [],
        "completed": [],
    }
    if resume and checkpointer is not None:
        # 재개는 저장된 체크포인트에서 이어 간다. 성공한 갈래를 다시 부르지 않는다.
        return app.invoke(None, config)
    return app.invoke(initial, config)


def _outcome(
    *,
    plan: _Plan,
    final: Mapping[str, Any],
    budget: RunBudget,
    joined_existing: bool = False,
) -> PipelineOutcome:
    projection = dict(final.get("projection") or {})
    section_results = {
        key: uuid.UUID(str(value)) for key, value in projection.items() if value
    }
    unavailable = final.get("unavailable_reason")
    quality = (
        QualityStatus.INSUFFICIENT
        if unavailable
        else QualityStatus.READY
    )
    return PipelineOutcome(
        run_id=plan.run_id,
        admission=plan.admission,
        status=RunStatus.SUCCEEDED if not unavailable else RunStatus.FAILED,
        quality=quality,
        stage=_last_stage(final),
        mode=plan.mode,
        workflow_versions={
            workflow_id: version_manifest.workflow_version_of(workflow_id)
            for workflow_id in required_workflows()
        },
        section_result_ids=section_results,
        selected_result_ids=tuple(
            uuid.UUID(str(item))
            for item in ((final.get("validated") or {}).get("selected_result_ids") or ())
            if item
        ),
        external_calls=0,
        budget=budget.snapshot(),
        unavailable_reason=str(unavailable) if unavailable else None,
        diagnostics=tuple(str(item) for item in final.get("diagnostics") or ()),
        completed_nodes=tuple(str(item) for item in final.get("completed") or ()),
        joined_existing=joined_existing,
    )


def start_preview_run(
    session: Session,
    *,
    fixture: Mapping[str, Any] | None,
    actor_id: int,
    transport: Any | None = None,
    reader: Any | None = None,
    admission: str = jobs.ADMISSION_MODE.APPROVED,
    mode: RunMode | None = None,
    limits: BudgetLimits | None = None,
    label: str | None = None,
    explicit_rerun: bool = False,
    now: datetime | None = None,
    checkpointer_factory: Callable[[uuid.UUID], Any] | None = None,
) -> PipelineOutcome:
    """전체 프리뷰를 시작한다. 승인 없는 기본 실행은 거부한다.

    - `admission=approved`(기본)면 필요한 섹션이 모두 승인되어 있고 **승인된 버전이
      지금 코드 구성과 같아야** 한다. 아니면 `AdmissionRefused`로 멈춘다.
    - `admission=admin_preview`는 승인 없이도 실행하지만 승인 근거가 아니다.
    - 같은 경기·입력·버전 조합이 진행 중이면 새로 만들지 않고 그 실행에 붙는다.
      `explicit_rerun=True`면 붙지 않고 새 실행을 만든다.
    """
    moment = now or _now()
    run_mode = mode or (getattr(transport, "mode", None) or RunMode.MOCK)
    if run_mode is RunMode.REPLAY:
        raise ValueError(
            "전체 프리뷰는 저장 응답 재생 모드로 실행하지 않습니다."
            " 재생은 결과 단위 재변환 경로를 씁니다."
        )

    state = admission_state(session)
    if admission == jobs.ADMISSION_MODE.APPROVED and not state["ready"]:
        missing = tuple(state["missing_approval"]) + tuple(state["stale_approval"])
        raise AdmissionRefused(
            "승인된 섹션 워크플로우가 없어 기본 전체 프리뷰를 시작하지 않았습니다."
            f" 필요한 섹션: {', '.join(missing)}. 관리자 시험으로는 실행할 수 있지만"
            " 그 결과는 승인 근거가 아닙니다.",
            missing=missing,
        )
    if admission not in (jobs.ADMISSION_MODE.APPROVED, jobs.ADMISSION_MODE.ADMIN_PREVIEW):
        raise ValueError(f"unknown admission {admission!r}")

    workflow_versions = {
        workflow_id: version_manifest.workflow_version_of(workflow_id)
        for workflow_id in required_workflows()
    }
    key = jobs.dedup_key(
        fixture=fixture, snapshot_ids=(), versions=workflow_versions
    )
    if not explicit_rerun:
        existing = jobs.find_active_run(session, key)
        if existing is not None:
            loaded = jobs.load_state(session, existing.id)
            if loaded is not None:
                return _joined_outcome(session, loaded, transport=transport)

    budget_limits = limits or BudgetLimits()
    run_id = uuid.uuid4()
    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=run_mode,
        actor_id=actor_id,
        config_version=PIPELINE_CONFIG_VERSION,
        limits=budget_limits.execution_limits(),
    )
    identity = None
    if isinstance(fixture, Mapping) and fixture:
        try:
            identity = FixtureIdentity.from_dict(dict(fixture))
        except (KeyError, TypeError, ValueError):
            identity = None
    store.store_run(
        session,
        context,
        fixture=identity,
        fixture_label=(
            f"fixture {identity.fixture_id}" if identity is not None else None
        ),
        label=label or _default_label(admission, run_mode),
        status=RunStatus.RUNNING,
    )
    budget = RunBudget.for_run(budget_limits, now=moment)
    jobs.new_pipeline_run(
        session,
        run_id=run_id,
        key=key,
        admission=admission,
        pending_nodes=[node for node in PIPELINE_NODES],
        workflow_versions=workflow_versions,
        budget_state=budget.persistable(),
        deadline_at=moment + timedelta(seconds=budget_limits.deadline_seconds),
        now=moment,
    )
    session.commit()

    plan = _Plan(
        run_id=run_id,
        fixture=fixture,
        mode=run_mode,
        admission=admission,
        transport=transport,
        reader=reader,
        budget=budget,
        actor_id=actor_id,
        now=moment,
    )
    final = _run_graph(
        plan=plan,
        checkpointer=(
            checkpointer_factory(run_id) if checkpointer_factory is not None else None
        ),
    )
    outcome = _outcome(plan=plan, final=final, budget=budget)
    _persist_outcome(session, outcome=outcome, budget=budget, actor_id=actor_id)
    return outcome


def _joined_outcome(
    session: Session,
    state: jobs.PipelineRunState,
    *,
    transport: Any | None,
) -> PipelineOutcome:
    """진행 중인 같은 조합의 실행에 붙었을 때 돌려줄 결론. 새 호출을 만들지 않는다."""
    detail_sections = {
        row["workflow_id"]: uuid.UUID(row["section_result_id"])
        for row in store.list_section_results(session, state.run_id)
    }
    return PipelineOutcome(
        run_id=state.run_id,
        admission=state.admission,
        status=RunStatus.RUNNING if state.active else RunStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
        stage=state.stage,
        mode=getattr(transport, "mode", RunMode.MOCK),
        workflow_versions=dict(state.workflow_versions),
        section_result_ids=detail_sections,
        selected_result_ids=tuple(
            uuid.UUID(str(item)) for item in state.selected_result_ids if item
        ),
        budget=dict(state.budget_state),
        waiting_reason=state.waiting_reason,
        joined_existing=True,
    )


def _default_label(admission: str, mode: RunMode) -> str:
    suffix = {
        RunMode.LIVE: "실호출",
        RunMode.MOCK: "모의 (외부 호출 없음)",
        RunMode.REPLAY: "저장 응답 재생",
    }[mode]
    admission_label = (
        "승인 버전"
        if admission == jobs.ADMISSION_MODE.APPROVED
        else "관리자 시험 (승인 근거 아님)"
    )
    return f"전체 프리뷰 · {admission_label} · {suffix}"


def _persist_outcome(
    session: Session,
    *,
    outcome: PipelineOutcome,
    budget: RunBudget,
    actor_id: int,
) -> None:
    """종료 상태를 원자적으로 확정한다. 실패를 성공으로 바꾸지 않는다."""
    from app.preview.contracts import FailureCode

    state = jobs.load_state(session, outcome.run_id)
    if state is None:
        return
    token = state.fencing_token
    finished = jobs.finish_pipeline(
        session,
        run_id=outcome.run_id,
        fencing_token=token,
        stage=outcome.stage,
        failure_code=(
            FailureCode.UNKNOWN_OUTCOME.value
            if outcome.status is RunStatus.FAILED and outcome.unavailable_reason
            else None
        ),
        failure_detail=outcome.unavailable_reason,
    )
    if not finished:
        # 다른 실행자가 이 실행의 소유권을 가져갔다. 이 실행자의 결론은 버린다.
        session.rollback()
        return
    jobs.save_progress(
        session,
        run_id=outcome.run_id,
        fencing_token=token,
        budget_state=budget.persistable(),
        # 어디까지 끝냈는지 남긴다. 재개는 이 목록으로 미완료 단계를 판정한다.
        completed_nodes=list(outcome.completed_nodes),
        pending_nodes=[],
    )
    store.finish_run(
        session,
        outcome.run_id,
        status=outcome.status,
        quality=outcome.quality,
        failure_detail=outcome.unavailable_reason,
        actor_id=actor_id,
    )
    session.commit()


def resume_preview_run(
    session: Session,
    *,
    run_id: uuid.UUID,
    actor_id: int,
    transport: Any | None = None,
    reader: Any | None = None,
    owner_id: str | None = None,
    now: datetime | None = None,
) -> PipelineOutcome:
    """멈춘 전체 프리뷰를 **남은 예산**으로 이어서 돈다.

    - 이미 성공한 모듈 결과는 다시 호출하지 않는다. 그래프는 저장된 체크포인트가
      있으면 그 지점부터, 없으면 처음부터 돌되 성공한 갈래 결과를 재사용한다.
    - 예산은 저장된 값을 그대로 복원한다. 재개가 예산을 새로 주지 않는다.
    - 소유권은 임차로 가져오고, 그 사이 다른 실행자가 가져갔으면 거부한다.
    """
    moment = now or _now()
    state = jobs.load_state(session, run_id)
    if state is None:
        raise store.RunNotFound(f"run {run_id} is not a whole-preview run")
    run_row = store.get_run_detail(session, run_id).summary
    if run_row.status in (RunStatus.SUCCEEDED, RunStatus.CANCELLED):
        # 이미 끝난 실행을 다시 돌리면 새 ID를 쓴다. 종료 결과를 덮어쓰지 않는다.
        raise ValueError(
            f"run {run_id} already finished with status {run_row.status.value}."
            " 의도적 재실행은 새 실행으로 만드세요."
        )

    owner = owner_id or f"resume-{uuid.uuid4()}"
    token = jobs.claim_lease(session, run_id=run_id, owner_id=owner, now=moment)
    if token is None:
        raise RuntimeError(
            "다른 실행자가 이 실행의 작업 소유권을 가지고 있습니다(임차가 만료되지"
            " 않았습니다). 잠시 뒤 다시 시도하세요."
        )
    session.commit()

    budget = RunBudget.restore(state.budget_state, now=moment)
    plan = _Plan(
        run_id=run_id,
        fixture=None,
        mode=getattr(transport, "mode", None) or RunMode.MOCK,
        admission=state.admission,
        transport=transport,
        reader=reader,
        budget=budget,
        actor_id=actor_id,
        now=moment,
    )
    final = _run_graph(plan=plan)
    base = _outcome(plan=plan, final=final, budget=budget)
    outcome = replace(base, resume_of_run_id=run_id)
    _persist_outcome(session, outcome=outcome, budget=budget, actor_id=actor_id)
    return outcome


def rerun_module(
    session: Session,
    *,
    run_id: uuid.UUID,
    module_id: str,
    actor_id: int,
    transport: Any | None = None,
    reader: Any | None = None,
    now: datetime | None = None,
) -> PipelineOutcome:
    """선택한 모듈만 **새 결과 버전**으로 다시 돈다. 다른 모듈 결과는 지우지 않는다.

    이 실행은 새 결과를 기존 결과 위에 버전으로 쌓는다. 그래서 옛 결과와 새 결과가
    함께 남고, 종합 재실행은 `resynthesize_preview`로 따로 한다.
    """
    moment = now or _now()
    state = jobs.load_state(session, run_id)
    if state is None:
        raise store.RunNotFound(f"run {run_id} is not a whole-preview run")
    if module_id not in RESEARCH_MODULE_IDS:
        raise ValueError(
            f"module {module_id!r} cannot be rerun through this path."
            f" 지원하는 모듈: {', '.join(RESEARCH_MODULE_IDS)}"
        )

    owner = f"rerun-{module_id}-{uuid.uuid4()}"
    token = jobs.claim_lease(session, run_id=run_id, owner_id=owner, now=moment)
    if token is None:
        raise RuntimeError(
            "다른 실행자가 이 실행의 작업 소유권을 가지고 있어 모듈 재실행을 시작하지"
            " 않았습니다."
        )
    session.commit()

    budget = RunBudget.restore(state.budget_state, now=moment)
    plan = _Plan(
        run_id=run_id,
        fixture=None,
        mode=getattr(transport, "mode", None) or RunMode.MOCK,
        admission=state.admission,
        transport=transport,
        reader=reader,
        budget=budget,
        actor_id=actor_id,
        now=moment,
        # 명시적 모듈 재실행은 새 결과 버전을 만드는 요청이다. 기존 성공을 재사용하면
        # "다시 돌렸다"는 요청과 기록이 어긋난다.
        reuse_existing=False,
    )
    result = _branch_node(module_id, plan=plan)(_stored_data_for(session, run_id))
    jobs.save_progress(
        session,
        run_id=run_id,
        fencing_token=token,
        budget_state=budget.persistable(),
        now=moment,
    )
    session.commit()

    outcome = PipelineOutcome(
        run_id=run_id,
        admission=state.admission,
        status=RunStatus.SUCCEEDED,
        quality=QualityStatus.PENDING,
        stage=f"rerun:{module_id}",
        mode=plan.mode,
        workflow_versions=dict(state.workflow_versions),
        budget=budget.snapshot(),
        diagnostics=tuple(str(item) for item in result.get("diagnostics") or ()),
    )
    return outcome


def resynthesize_preview(
    session: Session,
    *,
    run_id: uuid.UUID,
    actor_id: int,
    selected_result_ids: Sequence[uuid.UUID],
    transport: Any | None = None,
    now: datetime | None = None,
) -> PipelineOutcome:
    """**명시적으로 고른 결과 버전**으로 종합만 다시 한다.

    선택을 넘기지 않으면 실행하지 않는다(어떤 결과로 종합했는지 모호해지기 때문).
    조사 갈래는 다시 호출하지 않는다.
    """
    moment = now or _now()
    if not selected_result_ids:
        raise ValueError(
            "재종합에는 선택한 결과 ID가 필요합니다. 어떤 버전으로 종합했는지"
            " 기록에 남아야 합니다."
        )
    state = jobs.load_state(session, run_id)
    if state is None:
        raise store.RunNotFound(f"run {run_id} is not a whole-preview run")

    owner = f"resynth-{uuid.uuid4()}"
    token = jobs.claim_lease(session, run_id=run_id, owner_id=owner, now=moment)
    if token is None:
        raise RuntimeError(
            "다른 실행자가 이 실행의 작업 소유권을 가지고 있어 재종합을 시작하지"
            " 않았습니다."
        )
    jobs.save_progress(
        session,
        run_id=run_id,
        fencing_token=token,
        now=moment,
    )
    session.commit()

    budget = RunBudget.restore(state.budget_state, now=moment)
    plan = _Plan(
        run_id=run_id,
        fixture=None,
        mode=getattr(transport, "mode", None) or RunMode.MOCK,
        admission=state.admission,
        transport=transport,
        reader=None,
        budget=budget,
        actor_id=actor_id,
        now=moment,
        selected_result_ids=tuple(selected_result_ids),
    )
    # 검증 → 종합 → 투영만 다시 돈다. 조사 갈래는 부르지 않는다.
    validation = _validation_node(plan=plan)
    validated_state = validation(_stored_data_for(session, run_id))
    synthesis_state = _synthesis_node(plan=plan)({"validated": validated_state.get("validated")})
    projection_state = _projection_node(plan=plan)(
        {"research": validated_state.get("research") or [], "synthesis": synthesis_state.get("synthesis")}
    )
    session.commit()
    jobs.save_progress(
        session,
        run_id=run_id,
        fencing_token=token,
        budget_state=budget.persistable(),
        now=moment,
    )
    session.commit()
    return PipelineOutcome(
        run_id=run_id,
        admission=state.admission,
        status=RunStatus.SUCCEEDED,
        quality=QualityStatus.READY,
        stage="V1",
        mode=plan.mode,
        workflow_versions=dict(state.workflow_versions),
        section_result_ids={
            key: uuid.UUID(str(value))
            for key, value in (projection_state.get("projection") or {}).items()
            if value
        },
        selected_result_ids=tuple(selected_result_ids),
        budget=budget.snapshot(),
        diagnostics=tuple(str(item) for item in synthesis_state.get("diagnostics") or ()),
    )


def _stored_data_for(session: Session, run_id: uuid.UUID) -> dict[str, Any]:
    """저장된 D0 결과를 복원한다. 재실행·재종합이 자료를 다시 수집하지 않게 한다."""
    rows = list(
        session.scalars(
            select(PreviewResult)
            .where(PreviewResult.run_id == run_id, PreviewResult.module_id == "D0")
            .order_by(PreviewResult.version.desc())
        )
    )
    if not rows:
        return {"data": None}
    stored = dict(rows[0].payload or {})
    inner = stored.get("payload")
    data = dict(inner) if isinstance(inner, Mapping) else stored
    return {"data": data, "fixture": data.get("fixture")}


def rerun_preview(
    session: Session,
    *,
    run_id: uuid.UUID,
    actor_id: int,
    transport: Any | None = None,
    reader: Any | None = None,
    now: datetime | None = None,
) -> PipelineOutcome:
    """기존 실행 전체를 **새 실행 ID**로 다시 돈다(의도적 재실행).

    종료된 실행의 기록은 그대로 남고, 새 실행이 별도 행으로 생긴다. 같은 실행을
    덮어쓰지 않으므로 이전 결과와 비교할 수 있다.
    """
    moment = now or _now()
    state = jobs.load_state(session, run_id)
    if state is None:
        raise store.RunNotFound(f"run {run_id} is not a whole-preview run")
    detail = store.get_run_detail(session, run_id)
    fixture = detail.fixture.to_dict() if getattr(detail, "fixture", None) else None
    outcome = start_preview_run(
        session,
        fixture=fixture,
        actor_id=actor_id,
        transport=transport,
        reader=reader,
        admission=state.admission,
        mode=getattr(transport, "mode", None) or RunMode.MOCK,
        explicit_rerun=True,
        now=moment,
    )
    jobs_progress = jobs.load_state(session, outcome.run_id)
    if jobs_progress is not None:
        from sqlalchemy import update as _update

        from app.preview.models import PreviewPipelineRun

        session.execute(
            _update(PreviewPipelineRun)
            .where(PreviewPipelineRun.id == outcome.run_id)
            .values(rerun_of_run_id=run_id)
        )
        session.commit()
    return outcome


def _last_stage(final: Mapping[str, Any]) -> str:
    """그래프가 실제로 끝낸 마지막 단계. 없으면 `created`(성공을 꾸미지 않는다)."""
    order = {node: index for index, node in enumerate(PIPELINE_NODES)}
    done = [str(item) for item in (final.get("completed") or []) if str(item) in order]
    if not done:
        return "created"
    return max(done, key=lambda node: order[node])


def _existing_success(
    *,
    session_factory: sessionmaker,
    plan: _Plan,
    module_id: str,
) -> dict[str, Any] | None:
    """같은 실행에 이미 성공한 조사 결과가 있으면 그 요약을 돌려준다.

    재개가 성공한 갈래를 다시 부르지 않게 하는 판정이다. 구현 버전이 다르면 재사용하지
    않는다(다른 코드로 만든 결과를 새 코드의 결과처럼 쓰지 않는다).
    """
    implementation = _implementation_for(module_id, plan=plan)
    session = session_factory()
    try:
        row = session.scalar(
            select(PreviewResult)
            .where(
                PreviewResult.run_id == plan.run_id,
                PreviewResult.module_id == module_id,
                PreviewResult.status == "succeeded",
                PreviewResult.implementation_version
                == implementation.implementation_version,
            )
            .order_by(PreviewResult.created_at.desc())
            .limit(1)
        )
        if row is None:
            return None
        payload = dict(row.payload or {})
        inner = payload.get("payload")
        body = inner if isinstance(inner, Mapping) else payload
        return {
            "module_id": module_id,
            "result_id": str(row.id),
            "status": row.status,
            "quality": row.quality,
            "unavailable_reason": (
                body.get("unavailable_reason")
                if isinstance(body.get("unavailable_reason"), str)
                else None
            ),
            "reused": True,
        }
    finally:
        session.close()
