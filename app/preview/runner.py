"""MP-04 LangGraph 섹션 워크플로우 실행기.

역할 경계:

- **섹션 워크플로우**가 사용자의 테스트·승인 단위다. 관리자는 섹션 하나를 골라
  실행하고, 받은 실행 ID로 전체 결과(본문·근거·노드 진단)를 다시 연다.
- 내부 노드(`prepare_data` → `research` → `compose_body` → `finalize`)는 진단·구성
  단위이며 노드마다 승인하지 않는다.
- 실제 모델 호출은 `provider.execute_request`/`request_model`을 통해서만 나간다.
  그래서 예산·시도 기록이 한 곳에 남는다.
- 프레임워크는 단계 실행과 상태 전달을 맡고, 제품은 본문·근거·버전·승인·개발 쓰기
  취소를 `preview_dev`에 남긴다. LangGraph 내부 객체는 공개 API 계약으로 노출하지
  않는다. 저장되는 것은 `preview_runs`/`preview_module_executions`/`preview_attempts`/
  `preview_results`/`preview_section_results` 행뿐이다.

정직성 규칙:

- 등록되지 않은 단계는 **없는 그대로** 표시하고 본문을 만들어 채우지 않는다.
- 모의 실행으로 만든 섹션 결과는 `mode=mock`으로 저장되고 승인 근거가 되지 않는다.
- 예산·기한은 `retry.RunBudget` 하나가 소유한다. LangGraph 노드 재시도나 SDK
  재시도를 겹쳐 켜지 않는다.
- 체크포인터는 선택 주입이며 MP-04는 재개를 지원한다고 주장하지 않는다(MP-10 소유).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.preview import artifacts as artifact_store
from app.preview import store
from app.preview.contracts import (
    CONTRACT_VERSION,
    MODULE_INPUT_VERSION,
    SECTION_RESULT_CONTRACT_VERSION,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    OperationKind,
    QualityStatus,
    RunMode,
    RunStatus,
    SourceKind,
    ValidationStatus,
    compute_input_hash,
)
from app.preview.models import PreviewModuleExecution, PreviewSectionResult
from app.preview.registry import get_section_workflow
from app.preview.retry import BudgetLimits, RunBudget

__all__ = [
    "DATA_MODULE_ID",
    "NODE_ORDER",
    "NodeImplementation",
    "NodeOutcome",
    "SectionNodeContext",
    "SectionRunResult",
    "SectionState",
    "WorkflowImplementations",
    "build_section_workflow",
    "mock_section_implementations",
    "run_module",
    "run_section_workflow",
    "section_run_availability",
    "section_workflow_version",
]

NODE_ORDER = ("prepare_data", "research", "compose_body", "finalize")

# 구성 모듈 중 공유 자료 준비 단계. 승인 단위가 아니라 섹션의 한 구성 요소다.
DATA_MODULE_ID = "D0"
COMPOSE_MODULE_ID = "compose_body"


class SectionState(TypedDict, total=False):
    """그래프가 노드 사이로 넘기는 상태.

    값은 모두 JSON 직렬화 가능한 기본형이다. 프레임워크 내부 객체(SQLAlchemy 세션
    등)는 상태에 넣지 않고 노드 클로저가 따로 들고 있다.
    """

    workflow_id: str
    workflow_version: str
    mode: str
    fixture: dict[str, Any] | None
    data: dict[str, Any] | None
    research: dict[str, Any] | None
    title: str
    body: str
    sources: list[dict[str, Any]]
    quality: str
    diagnostics: list[str]
    unavailable_reason: str | None
    module_execution_ids: list[str]
    result_ids: list[str]
    step_log: list[dict[str, Any]]


@dataclass(frozen=True)
class NodeOutcome:
    """노드 하나의 산출. 없는 값은 `None`으로 두고 빈 문자열로 채우지 않는다."""

    payload: Mapping[str, Any] = field(default_factory=dict)
    title: str | None = None
    body: str | None = None
    sources: Sequence[Mapping[str, Any]] = ()
    quality: QualityStatus | None = None
    diagnostics: Sequence[str] = ()
    unavailable_reason: str | None = None
    # 이 노드가 실제로 보낸 외부 호출 수. 기록의 mode를 여기서 추론하지 않는다.
    external_calls: int = 0


@dataclass(frozen=True)
class SectionNodeContext:
    """노드가 쓰는 실행 문맥. `session`만 저장에 쓰고 나머지는 판단 근거다."""

    session: Session
    context: ExecutionContext
    budget: RunBudget
    workflow_id: str
    workflow_version: str
    fixture: Mapping[str, Any] | None
    mode: RunMode
    transport: Any | None
    actor_id: int
    module_execution_id: uuid.UUID | None = None
    snapshot_ids: tuple[uuid.UUID, ...] = ()
    selected_result_ids: tuple[uuid.UUID, ...] = ()


NodeRunner = Callable[[SectionNodeContext, SectionState], NodeOutcome]


@dataclass(frozen=True)
class NodeImplementation:
    """노드 하나의 주입 가능한 구현.

    `mode`는 이 구현이 무엇을 근거로 결과를 만드는지 밝힌다. 모의 자료면 mock,
    저장 응답이면 replay, 실제 생성이면 live다. 실행 기록과 섹션 결과의 mode는 이
    값에서만 나오며 호출자가 임의로 바꾸지 않는다.
    """

    module_id: str
    implementation_version: str
    prompt_version: str | None
    mode: RunMode
    run: NodeRunner


@dataclass(frozen=True)
class WorkflowImplementations:
    """섹션 하나를 만드는 구현 묶음. 없는 항목은 그대로 '미구현'이다."""

    prepare_data: NodeImplementation | None = None
    research: tuple[NodeImplementation, ...] = ()
    compose_body: NodeImplementation | None = None

    def missing_for(self, workflow) -> tuple[str, ...]:
        """필수 구현 중 빠진 것. 화면·API가 그대로 보여줄 수 있는 이름 목록."""
        missing: list[str] = []
        if self.prepare_data is None:
            missing.extend(
                module_id
                for module_id in workflow.module_ids
                if module_id == DATA_MODULE_ID
            )
        if not self.research:
            missing.extend(
                module_id
                for module_id in workflow.module_ids
                if module_id != DATA_MODULE_ID
            )
        if self.compose_body is None:
            missing.append(COMPOSE_MODULE_ID)
        return tuple(dict.fromkeys(missing))

    @property
    def nodes(self) -> tuple[NodeImplementation, ...]:
        nodes: list[NodeImplementation] = []
        if self.prepare_data is not None:
            nodes.append(self.prepare_data)
        nodes.extend(self.research)
        if self.compose_body is not None:
            nodes.append(self.compose_body)
        return tuple(nodes)

    @property
    def mode(self) -> RunMode:
        """실행 방식은 구현이 밝힌 근거에서만 나온다.

        여러 구현이 섞이면 가장 보수적인 값(mock → replay → live)을 쓴다. 일부가
        모의인 실행을 live 성공으로 기록하지 않기 위해서다.
        """
        modes = {node.mode for node in self.nodes}
        for candidate in (RunMode.MOCK, RunMode.REPLAY, RunMode.LIVE):
            if candidate in modes:
                return candidate
        return RunMode.MOCK


# --------------------------------------------------------------------------
# 버전 계산 (승인 대상 축)
# --------------------------------------------------------------------------


def section_workflow_version(workflow) -> str:
    """섹션 워크플로우 버전. 결과 의미를 바꾸는 축만 쓴다.

    구성 버전은 `version_manifest` 한 곳에서 온다. 그래서 실행이 남기는 버전과 승인
    후보가 보는 버전이 같은 근거를 쓴다. 실제 모듈·프롬프트·구현 버전을 채우므로,
    그 축이 바뀌면 버전도 바뀐다(빈 문자열 자리표시자를 쓰지 않는다).
    """
    from app.preview import approvals, version_manifest

    constituents = version_manifest.constituents_for_workflow(workflow.workflow_id)
    return approvals.release_version(workflow, constituents)[0]


# --------------------------------------------------------------------------
# 노드 실행 (내부 구성 요소 — 승인 단위 아님)
# --------------------------------------------------------------------------


def _log(state: SectionState, node: str, outcome: NodeOutcome) -> list[dict[str, Any]]:
    log = list(state.get("step_log") or [])
    log.append(
        {
            "node": node,
            "unavailable": outcome.unavailable_reason is not None,
            "external_calls": outcome.external_calls,
        }
    )
    return log


def _module_input(
    *,
    module_id: str,
    fixture: Mapping[str, Any] | None,
    snapshot_ids: Sequence[uuid.UUID],
    selected_result_ids: Sequence[uuid.UUID],
    prompt_version: str,
    implementation_version: str,
    parameters: Mapping[str, Any],
) -> ModuleInput:
    identity = FixtureIdentity.from_dict(dict(fixture)) if fixture else None
    return ModuleInput(
        module_id=module_id,
        fixture=identity,
        snapshot_ids=tuple(snapshot_ids),
        selected_result_ids=tuple(selected_result_ids),
        input_hash=compute_input_hash(
            {
                "module_id": module_id,
                "fixture": dict(fixture or {}),
                "snapshot_ids": [str(item) for item in snapshot_ids],
                "selected_result_ids": [str(item) for item in selected_result_ids],
            }
        ),
        prompt_version=prompt_version,
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=implementation_version,
        parameters=dict(parameters),
    )


def _next_ordinal(session: Session, run_id: uuid.UUID, module_id: str) -> int:
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


def _run_node(
    ctx: SectionNodeContext,
    state: SectionState,
    implementation: NodeImplementation | None,
    *,
    node_name: str,
) -> tuple[NodeOutcome, uuid.UUID | None, uuid.UUID | None]:
    """노드 하나를 실행하고 모듈 실행·결과를 남긴다.

    구현이 없으면 정직하게 "사용할 수 없음"을 돌려준다. 없는 구현을 흉내 내어 본문을
    만들지 않는다. 그 진단 문장은 관리자 기록에만 남고 독자용 본문에는 들어가지
    않는다.

    반환값: (노드 산출, 모듈 실행 ID, 모듈 결과 ID)
    """
    if implementation is None:
        return (
            NodeOutcome(
                unavailable_reason=(
                    f"{node_name} 단계 구현이 등록되지 않았습니다. 이 섹션의 본문을"
                    " 실제로 만들 수 없습니다."
                )
            ),
            None,
            None,
        )

    module_input = _module_input(
        module_id=implementation.module_id,
        fixture=ctx.fixture,
        snapshot_ids=ctx.snapshot_ids,
        selected_result_ids=ctx.selected_result_ids,
        prompt_version=implementation.prompt_version or "",
        implementation_version=implementation.implementation_version,
        parameters={"node": node_name},
    )
    execution = store.start_module_execution(
        ctx.session,
        run_id=ctx.context.run_id,
        module_id=implementation.module_id,
        module_input=module_input,
        ordinal=_next_ordinal(ctx.session, ctx.context.run_id, implementation.module_id),
        actor_id=ctx.actor_id,
    )

    # 실행 문맥에도 이번 모듈 실행 ID를 넣는다. 노드가 `context.module_execution_id`를
    # 읽어 시도를 기록하는 경로(예: R4 → request_model)가 있는데, 여기서 넣지 않으면
    # 그 시도가 `module_execution_id=NULL`로 저장되어 검사 화면의 응답 탭에서 원문을
    # 찾을 수 없다. 노드 문맥과 실행 문맥을 같은 실행으로 맞춘다.
    node_ctx = SectionNodeContext(
        session=ctx.session,
        context=replace(ctx.context, module_execution_id=execution.id),
        budget=ctx.budget,
        workflow_id=ctx.workflow_id,
        workflow_version=ctx.workflow_version,
        fixture=ctx.fixture,
        mode=ctx.mode,
        transport=ctx.transport,
        actor_id=ctx.actor_id,
        module_execution_id=execution.id,
        snapshot_ids=ctx.snapshot_ids,
        selected_result_ids=ctx.selected_result_ids,
    )
    outcome = implementation.run(node_ctx, state)

    status = (
        ModuleStatus.FAILED
        if outcome.unavailable_reason is not None
        else ModuleStatus.SUCCEEDED
    )
    quality = outcome.quality or QualityStatus.PENDING
    result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=implementation.module_id,
        module_execution_id=execution.id,
        run_id=ctx.context.run_id,
        version=1,
        input_hash=module_input.input_hash,
        status=status,
        quality=quality,
        claims=tuple((outcome.payload or {}).get("claims") or ()),
        coverage=tuple((outcome.payload or {}).get("coverage") or ()),
        diagnostics=tuple(outcome.diagnostics),
        implementation_version=implementation.implementation_version,
        prompt_version=implementation.prompt_version or "",
        contract_version=CONTRACT_VERSION,
        payload=dict(outcome.payload),
    )
    saved = store.save_module_result(ctx.session, result, actor_id=ctx.actor_id)
    store.update_module_delivery(
        ctx.session,
        execution.id,
        {
            "target_module_id": None,
            "selected_result_ids": [str(saved.id)],
            "values": [
                {"key": "node", "value": node_name},
                {"key": "unavailable", "value": outcome.unavailable_reason is not None},
            ],
            "note": (
                "섹션 워크플로우 내부 노드의 전달값입니다. 승인 단위가 아니라 진단"
                " 정보입니다."
            ),
        },
        status=status,
        quality=quality,
    )
    return outcome, execution.id, saved.id


def _merge(
    state: SectionState,
    *,
    node_name: str,
    outcome: NodeOutcome,
    module_execution_id: uuid.UUID | None,
    result_id: uuid.UUID | None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """노드 결과를 공통 상태 조각으로 합친다. 실패 원인은 첫 것만 유지한다."""
    return {
        "diagnostics": list(state.get("diagnostics") or [])
        + [str(item) for item in outcome.diagnostics],
        "unavailable_reason": state.get("unavailable_reason")
        or outcome.unavailable_reason,
        "module_execution_ids": list(state.get("module_execution_ids") or [])
        + ([str(module_execution_id)] if module_execution_id else []),
        "result_ids": list(state.get("result_ids") or [])
        + ([str(result_id)] if result_id else []),
        "step_log": _log(state, node_name, outcome),
        **dict(extra or {}),
    }


# --------------------------------------------------------------------------
# 워크플로우 팩토리
# --------------------------------------------------------------------------


def build_section_workflow(
    *,
    implementations: WorkflowImplementations,
    ctx: SectionNodeContext,
    checkpointer: Any | None = None,
):
    """섹션 하나를 실행하는 LangGraph 그래프를 만든다.

    노드는 네 단계로 고정하고, 섹션마다 다른 것은 주입된 구현과 조사 단계 수다.
    체크포인터는 선택이며, 넘길 때는 `preview_dev` 범위의 것만 쓴다. 넘기지 않으면
    상태를 저장하지 않으므로 재개를 지원한다고 말하지 않는다.
    """
    graph: StateGraph = StateGraph(SectionState)

    def prepare_data(state: SectionState) -> dict[str, Any]:
        outcome, execution_id, result_id = _run_node(
            ctx, state, implementations.prepare_data, node_name="prepare_data"
        )
        return _merge(
            state,
            node_name="prepare_data",
            outcome=outcome,
            module_execution_id=execution_id,
            result_id=result_id,
            extra={"data": dict(outcome.payload)},
        )

    def research(state: SectionState) -> dict[str, Any]:
        collected: dict[str, Any] = {}
        diagnostics = list(state.get("diagnostics") or [])
        module_ids = list(state.get("module_execution_ids") or [])
        result_ids = list(state.get("result_ids") or [])
        sources = list(state.get("sources") or [])
        unavailable = state.get("unavailable_reason")
        external_calls = 0

        targets: Sequence[NodeImplementation | None] = (
            implementations.research or (None,)
        )
        for implementation in targets:
            outcome, execution_id, result_id = _run_node(
                ctx, state, implementation, node_name="research"
            )
            external_calls += outcome.external_calls
            diagnostics.extend(str(item) for item in outcome.diagnostics)
            sources.extend(dict(item) for item in outcome.sources)
            if execution_id:
                module_ids.append(str(execution_id))
            if result_id:
                result_ids.append(str(result_id))
            if outcome.unavailable_reason:
                unavailable = unavailable or outcome.unavailable_reason
            elif implementation is not None:
                collected[implementation.module_id] = dict(outcome.payload)

        return {
            "research": collected,
            "diagnostics": diagnostics,
            "sources": sources,
            "unavailable_reason": unavailable,
            "module_execution_ids": module_ids,
            "result_ids": result_ids,
            "step_log": _log(
                state, "research", NodeOutcome(external_calls=external_calls)
            ),
        }

    def compose_body(state: SectionState) -> dict[str, Any]:
        outcome, execution_id, result_id = _run_node(
            ctx, state, implementations.compose_body, node_name="compose_body"
        )
        return _merge(
            state,
            node_name="compose_body",
            outcome=outcome,
            module_execution_id=execution_id,
            result_id=result_id,
            extra={
                "title": outcome.title or state.get("title") or "",
                "body": outcome.body or "",
                "sources": list(state.get("sources") or [])
                + [dict(item) for item in outcome.sources],
                "quality": (outcome.quality or QualityStatus.PENDING).value,
            },
        )

    def finalize(state: SectionState) -> dict[str, Any]:
        """본문이 없으면 실패로 확정한다. 빈 본문을 성공으로 남기지 않는다."""
        body = str(state.get("body") or "").strip()
        unavailable = state.get("unavailable_reason")
        diagnostics = list(state.get("diagnostics") or [])
        if not body and not unavailable:
            unavailable = "섹션 본문을 만들지 못했습니다."
        quality = state.get("quality") or QualityStatus.PENDING.value
        if unavailable:
            quality = QualityStatus.INSUFFICIENT.value
        return {
            "body": body,
            "diagnostics": diagnostics,
            "unavailable_reason": unavailable,
            "quality": quality,
            "step_log": _log(
                state, "finalize", NodeOutcome(unavailable_reason=unavailable)
            ),
        }

    graph.add_node("prepare_data", prepare_data)
    graph.add_node("research", research)
    graph.add_node("compose_body", compose_body)
    graph.add_node("finalize", finalize)
    graph.add_edge(START, "prepare_data")
    graph.add_edge("prepare_data", "research")
    graph.add_edge("research", "compose_body")
    graph.add_edge("compose_body", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


# --------------------------------------------------------------------------
# 실행 진입점
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionRunResult:
    """섹션 실행의 결론. 화면이 열 실행 ID와 저장된 섹션 결과를 담는다."""

    run_id: uuid.UUID
    workflow_id: str
    workflow_version: str
    mode: RunMode
    status: RunStatus
    quality: QualityStatus
    section_result_id: uuid.UUID | None
    section_result_version: int | None
    body: str
    sources: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[str, ...]
    step_log: tuple[Mapping[str, Any], ...]
    external_calls: int
    budget: Mapping[str, Any]
    module_execution_ids: tuple[uuid.UUID, ...] = ()
    result_ids: tuple[uuid.UUID, ...] = ()
    unavailable_reason: str | None = None

    @property
    def unavailable(self) -> bool:
        return self.unavailable_reason is not None


def section_run_availability(
    workflow_id: str, implementations: Mapping[str, WorkflowImplementations]
) -> dict[str, Any]:
    """화면·API가 그대로 보여줄 수 있는 실행 가능 여부. 미구현을 숨기지 않는다."""
    workflow = get_section_workflow(workflow_id)
    bundle = implementations.get(workflow_id)
    missing = bundle.missing_for(workflow) if bundle else tuple(workflow.module_ids) + (
        COMPOSE_MODULE_ID,
    )
    modes = sorted({node.mode.value for node in bundle.nodes}) if bundle else []
    # 모의 구현만 있으면 실행은 되지만 실제 생성은 아니다. 두 사실을 따로 낸다.
    demo_only = bool(modes) and set(modes) == {RunMode.MOCK.value}
    real_generation = any(mode != RunMode.MOCK.value for mode in modes)
    if not missing and demo_only:
        note = (
            "지금 등록된 구현은 명시적 모의 시연뿐입니다. 화면·저장 경로는 확인할 수"
            " 있지만 실제 조사·생성 결과가 아니며 승인 근거로도 쓰지 않습니다."
        )
    elif not missing:
        note = None
    else:
        note = (
            "이 섹션의 모든 단계 구현이 등록되지 않았습니다. 본문을 실제로 만들 수"
            " 없으며, 모의 시연으로도 없는 본문을 만들지 않습니다."
        )
    return {
        "workflow_id": workflow_id,
        "display_name": workflow.display_name,
        "module_ids": list(workflow.module_ids),
        "output_contract_version": workflow.output_contract_version,
        "implemented": not missing,
        "missing_implementations": list(missing),
        "modes": modes,
        # 모의 시연만 가능한 상태인지, 실제 생성이 가능한 상태인지 구분한다.
        "demo_only": demo_only,
        "real_generation_available": real_generation,
        "note": note,
    }


def _limits_or_default(limits: BudgetLimits | None) -> BudgetLimits:
    return limits or BudgetLimits()


def run_section_workflow(
    session: Session,
    *,
    workflow_id: str,
    implementations: WorkflowImplementations,
    actor_id: int,
    environment: Environment = Environment.DEV,
    fixture: Mapping[str, Any] | None = None,
    fixture_label: str | None = None,
    transport: Any | None = None,
    label: str | None = None,
    limits: BudgetLimits | None = None,
    checkpointer: Any | None = None,
    configuration_version: str = "mp04-section-1",
    now: datetime | None = None,
    selected_result_ids: Sequence[uuid.UUID] = (),
) -> SectionRunResult:
    """섹션 워크플로우 하나를 실행하고 결과를 `preview_dev`에 남긴다.

    반환값의 `run_id`로 관리자 검사 화면을 다시 열 수 있다. 실제 외부 호출은 노드
    구현이 `execute_request`를 통과할 때만 일어나며, 그 기록은 같은 실행 ID 아래에
    남는다.

    `selected_result_ids`는 **앞선 모듈의 저장 결과 버전을 명시적으로 고르는** 입력이다
    (MP-09 종합). 넘기지 않으면 빈 값이며, 노드 문맥과 모듈 입력 해시에 그대로 들어가
    "무엇을 입력으로 썼는지"가 기록에 남는다. 실행기가 결과를 대신 골라 채우지 않는다.
    """
    workflow = get_section_workflow(workflow_id)
    moment = now or datetime.now(timezone.utc)
    mode = implementations.mode
    budget_limits = _limits_or_default(limits)
    workflow_version = section_workflow_version(workflow)

    run_id = uuid.uuid4()
    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.SECTION,
        environment=environment,
        mode=mode,
        actor_id=actor_id,
        config_version=configuration_version,
        limits=budget_limits.execution_limits(),
    )

    store.store_run(
        session,
        context,
        fixture=FixtureIdentity.from_dict(dict(fixture)) if fixture else None,
        fixture_label=fixture_label,
        label=label or _default_label(workflow.display_name, mode),
        status=RunStatus.RUNNING,
    )

    budget = RunBudget.for_run(budget_limits, now=moment)
    ctx = SectionNodeContext(
        session=session,
        context=context,
        budget=budget,
        workflow_id=workflow.workflow_id,
        workflow_version=workflow_version,
        fixture=fixture,
        mode=mode,
        transport=transport,
        actor_id=actor_id,
        selected_result_ids=tuple(selected_result_ids),
    )
    graph = build_section_workflow(
        implementations=implementations, ctx=ctx, checkpointer=checkpointer
    )
    final_state: Mapping[str, Any] = graph.invoke(
        {
            "workflow_id": workflow.workflow_id,
            "workflow_version": workflow_version,
            "mode": mode.value,
            "fixture": dict(fixture) if fixture else None,
            "title": workflow.display_name,
            "body": "",
            "sources": [],
            "quality": QualityStatus.PENDING.value,
            "diagnostics": [],
            "unavailable_reason": None,
            "module_execution_ids": [],
            "result_ids": [],
            "step_log": [],
        },
        {"configurable": {"thread_id": str(run_id)}},
    )

    body = str(final_state.get("body") or "")
    unavailable = final_state.get("unavailable_reason")
    if not body.strip() and unavailable is None:
        unavailable = "섹션 본문을 만들지 못했습니다."
    quality = QualityStatus(final_state.get("quality") or QualityStatus.PENDING.value)
    if unavailable:
        quality = QualityStatus.INSUFFICIENT
    sources = tuple(dict(item) for item in final_state.get("sources") or ())
    diagnostics = tuple(str(item) for item in final_state.get("diagnostics") or ())
    module_execution_ids = tuple(
        uuid.UUID(item) for item in final_state.get("module_execution_ids") or ()
    )
    result_ids = tuple(uuid.UUID(item) for item in final_state.get("result_ids") or ())

    row = store.save_section_result(
        session,
        run_id=run_id,
        workflow_id=workflow.workflow_id,
        workflow_version=workflow_version,
        title=str(final_state.get("title") or workflow.display_name),
        body=body,
        version=1,
        mode=mode,
        environment=environment,
        quality=quality,
        output_contract_version=workflow.output_contract_version,
        contract_version=SECTION_RESULT_CONTRACT_VERSION,
        sources=sources,
        module_execution_ids=module_execution_ids,
        result_ids=result_ids,
        diagnostics=diagnostics,
        unavailable_reason=unavailable,
        actor_id=actor_id,
        now=moment,
    )

    # 실행 자체는 끝까지 돌았으므로 succeeded다. 근거 확보 여부는 quality로 따로 둔다.
    store.finish_run(
        session, run_id, status=RunStatus.SUCCEEDED, quality=quality, actor_id=actor_id
    )

    return SectionRunResult(
        run_id=run_id,
        workflow_id=workflow.workflow_id,
        workflow_version=workflow_version,
        mode=mode,
        status=RunStatus.SUCCEEDED,
        quality=quality,
        section_result_id=row.id,
        section_result_version=row.version,
        body=body,
        sources=sources,
        diagnostics=diagnostics,
        step_log=tuple(dict(item) for item in final_state.get("step_log") or ()),
        external_calls=sum(
            int(step.get("external_calls") or 0)
            for step in final_state.get("step_log") or ()
        ),
        budget=budget.snapshot(),
        module_execution_ids=module_execution_ids,
        result_ids=result_ids,
        unavailable_reason=unavailable,
    )


def _default_label(display_name: str, mode: RunMode) -> str:
    suffix = {
        RunMode.LIVE: "실호출",
        RunMode.REPLAY: "저장 응답 재생",
        RunMode.MOCK: "모의 시연 (외부 호출 없음)",
    }[mode]
    return f"{display_name} · {suffix}"


# --------------------------------------------------------------------------
# 모듈 단독 실행 (내부 진단용 — 승인 단위 아님)
# --------------------------------------------------------------------------


def run_module(
    session: Session,
    *,
    module_id: str,
    module_input: ModuleInput,
    context: ExecutionContext,
    implementation: NodeImplementation,
    transport: Any | None = None,
    budget: RunBudget | None = None,
    state: Mapping[str, Any] | None = None,
) -> ModuleResult:
    """모듈 하나를 단독 실행한다. 검사·구성용이며 사용자 승인 단위가 아니다.

    `state`는 앞 단계가 남긴 상태(예: 전체 프리뷰의 D0 산출)다. 넘기지 않으면 지금까지
    처럼 빈 상태로 실행한다. 전체 프리뷰(MP-10)의 조사 갈래는 D0 산출을 `state["data"]`로
    받아야 하므로 이 인자로 전달한다(모듈 계약은 그대로다).
    """
    run_budget = budget or RunBudget.for_run()
    execution = store.start_module_execution(
        session,
        run_id=context.run_id,
        module_id=module_id,
        module_input=module_input,
        ordinal=_next_ordinal(session, context.run_id, module_id),
        actor_id=context.actor_id,
    )
    ctx = SectionNodeContext(
        session=session,
        context=context,
        budget=run_budget,
        workflow_id="",
        workflow_version="",
        fixture=module_input.fixture.to_dict() if module_input.fixture else None,
        mode=implementation.mode,
        transport=transport,
        actor_id=context.actor_id,
        module_execution_id=execution.id,
        snapshot_ids=module_input.snapshot_ids,
        selected_result_ids=module_input.selected_result_ids,
    )
    outcome = implementation.run(
        ctx,
        {
            "workflow_id": "",
            "fixture": ctx.fixture,
            "step_log": [],
            "diagnostics": [],
            **(dict(state) if state else {}),
        },
    )
    status = (
        ModuleStatus.FAILED
        if outcome.unavailable_reason is not None
        else ModuleStatus.SUCCEEDED
    )
    quality = outcome.quality or QualityStatus.PENDING
    result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=module_id,
        module_execution_id=execution.id,
        run_id=context.run_id,
        version=1,
        input_hash=module_input.input_hash,
        status=status,
        quality=quality,
        claims=tuple((outcome.payload or {}).get("claims") or ()),
        coverage=tuple((outcome.payload or {}).get("coverage") or ()),
        diagnostics=tuple(outcome.diagnostics),
        implementation_version=implementation.implementation_version,
        prompt_version=implementation.prompt_version or "",
        contract_version=CONTRACT_VERSION,
        payload=dict(outcome.payload),
    )
    saved = store.save_module_result(session, result, actor_id=context.actor_id)
    store.update_module_delivery(
        session,
        execution.id,
        {
            "target_module_id": None,
            "selected_result_ids": [str(saved.id)],
            "values": [{"key": "module_id", "value": module_id}],
            "note": "단독 모듈 실행입니다. 사용자 승인 단위가 아닙니다.",
        },
        status=status,
        quality=quality,
    )
    return ModuleResult(
        result_id=saved.id,
        module_id=module_id,
        module_execution_id=execution.id,
        run_id=context.run_id,
        version=saved.version,
        input_hash=module_input.input_hash,
        status=status,
        quality=quality,
        diagnostics=tuple(outcome.diagnostics),
        payload=dict(outcome.payload),
    )


# --------------------------------------------------------------------------
# 명시적 모의 시연 (MP-04 스캐폴딩)
# --------------------------------------------------------------------------

MOCK_SECTION_MARKER = "mock_section_demo"


def mock_section_implementations(workflow_id: str) -> WorkflowImplementations:
    """섹션 워크플로우를 화면에서 확인하기 위한 **명시적 모의** 구현.

    외부 모델·API를 호출하지 않는다. 기록에는 `mode=mock`으로 남고, 만든 섹션 결과도
    `mode=mock`이라 승인 근거가 되지 않는다. 실제 조사는 MP-05~07이 구현을 등록한
    뒤에 열린다.
    """
    from app.preview.contracts import (
        ClaimDecision,
        ClaimKind,
        CoverageEntry,
        CoverageState,
        EvidenceClaim,
    )

    workflow = get_section_workflow(workflow_id)
    research_module_id = next(
        (module_id for module_id in workflow.module_ids if module_id != DATA_MODULE_ID),
        "R1",
    )

    def prepare(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        moment = datetime.now(timezone.utc)
        artifact = artifact_store.save_artifact(
            ctx.session,
            run_id=ctx.context.run_id,
            kind=artifact_store.ArtifactKind.RAW_RESPONSE,
            content={
                "marker": MOCK_SECTION_MARKER,
                "note": (
                    "외부 API에서 받은 자료가 아니라 저장 경로 확인용 모의 자료입니다."
                ),
                "fixture": state.get("fixture"),
            },
            actor_id=ctx.actor_id,
            now=moment,
        )
        snapshot = store.record_source_snapshot(
            ctx.session,
            run_id=ctx.context.run_id,
            source_kind=SourceKind.API,
            provider="mock-recorded",
            collected_at=moment,
            validation_status=ValidationStatus.UNVERIFIED,
            fixture=None,
            artifact_id=artifact.id,
            note="모의 자료입니다. 실제 수집이 아닙니다.",
            actor_id=ctx.actor_id,
        )
        return NodeOutcome(
            payload={
                "snapshot_id": str(snapshot.id),
                "claims": [],
                "coverage": [
                    CoverageEntry(
                        topic="section_material",
                        state=CoverageState.NOT_RUN,
                        detail="모의 시연에서는 실제 수집 단계를 실행하지 않았습니다.",
                    ).to_dict()
                ],
            },
            diagnostics=("공유 자료 준비는 모의 자료로 대체했습니다.",),
        )

    def research(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        claims = (
            EvidenceClaim(
                claim_id=f"{workflow.workflow_id}-mock-1",
                kind=ClaimKind.AI_INTERPRETATION,
                text="모의 시연용 문장입니다.",
                decision=ClaimDecision.ADOPTED,
                decision_reason="모의 자료로 만든 시연 문장이며 실제 조사 결과가 아닙니다.",
            ),
        )
        return NodeOutcome(
            payload={
                "claims": [claim.to_dict() for claim in claims],
                "coverage": [
                    CoverageEntry(
                        topic="research",
                        state=CoverageState.NOT_RUN,
                        detail="실제 조사 구현은 MP-05 이후에 등록됩니다.",
                    ).to_dict()
                ],
            },
            diagnostics=("조사 단계는 모의 구현입니다. 실제 모델 호출은 없습니다.",),
        )

    def compose(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        display = workflow.display_name
        body = (
            f"{display} 모의 시연 본문입니다.\n\n"
            "이 본문은 화면과 저장 경로를 확인하기 위한 예시이며 실제 경기 조사 결과가"
            " 아닙니다. 실제 조사·생성 구현이 등록되면 같은 화면에서 실제 본문을 봅니다."
        )
        return NodeOutcome(
            title=f"{display} (모의 시연)",
            body=body,
            sources=(
                {
                    "label": "모의 자료 (실제 출처 아님)",
                    "kind": "mock",
                    "url": None,
                    "note": "외부 API·검색 호출 없이 만든 예시입니다.",
                },
            ),
            quality=QualityStatus.PENDING,
            diagnostics=("본문은 모의 자료로만 구성했습니다.",),
        )

    return WorkflowImplementations(
        prepare_data=NodeImplementation(
            module_id=DATA_MODULE_ID,
            implementation_version="mp04-mock-d0-1",
            prompt_version=None,
            mode=RunMode.MOCK,
            run=prepare,
        ),
        research=(
            NodeImplementation(
                module_id=research_module_id,
                implementation_version="mp04-mock-research-1",
                prompt_version="mp04-mock-research-1",
                mode=RunMode.MOCK,
                run=research,
            ),
        ),
        compose_body=NodeImplementation(
            module_id=COMPOSE_MODULE_ID,
            implementation_version="mp04-mock-compose-1",
            prompt_version="mp04-mock-compose-1",
            mode=RunMode.MOCK,
            run=compose,
        ),
    )
