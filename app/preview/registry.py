"""모듈 등록부.

등록은 이 파일 한 곳에서만 한다. 임의 파일을 자동 실행하는 플러그인 로더는
도입하지 않는다. 검사 화면·기록·집계는 등록된 모듈 ID와 계약을 기준으로
동작하므로, 새 모듈을 추가해도 공통 검사 경로는 그대로 쓴다.

MP-02 시점의 실제 상태:

- D0/R1/R2/R3/S1은 계약만 등록되어 있고 아직 구현이 없다. `implemented=False`로
  두어 화면에서 "사용할 수 없음"으로 표시한다. 실행 가능으로 보이게 두지 않는다.
- `mock_demo`는 MP-02가 실제로 돌리는 유일한 경로다. 이름과 표시 이름에 mock을
  드러내고 `mode_scope=(MOCK,)`로 고정한다. live 실행으로 오인되지 않게 하기 위함이다.
"""

from __future__ import annotations

from dataclasses import replace

from app.preview.contracts import (
    CONTRACT_VERSION,
    INSPECTOR_VERSION,
    MODULE_INPUT_VERSION,
    ModuleRegistration,
    RunMode,
    SectionWorkflowRegistration,
)

__all__ = [
    "MODULE_REGISTRY",
    "MOCK_DEMO_MODULE_ID",
    "REGISTRY_VERSION",
    "SECTION_WORKFLOWS",
    "describe_registry",
    "describe_section_workflows",
    "get_module",
    "get_section_workflow",
    "list_modules",
    "registered_module_ids",
    "section_workflow_ids",
]

REGISTRY_VERSION = "mp02-registry-1"

# MP-02가 실제로 실행하는 기록 시연 모듈. 외부 호출이 없다.
MOCK_DEMO_MODULE_ID = "mock_demo"


def _planned(
    module_id: str,
    display_name: str,
    description: str,
    *,
    operation: str,
    depends_on: tuple[str, ...] = (),
    expected_model_calls: int = 1,
    prompt_version: str | None = None,
    inspector_panel: str = "generic",
) -> ModuleRegistration:
    """아직 구현되지 않은 계획 모듈. 실행 가능으로 표시하지 않는다."""
    return ModuleRegistration(
        module_id=module_id,
        display_name=display_name,
        description=description,
        operation=operation,
        depends_on=depends_on,
        contract_version=MODULE_INPUT_VERSION,
        prompt_version=prompt_version,
        inspector_panel=inspector_panel,
        implemented=False,
        mode_scope=(RunMode.LIVE, RunMode.REPLAY),
        expected_model_calls=expected_model_calls,
        unrunnable_reason="아직 구현되지 않았습니다. MP-03 이후 작업에서 추가됩니다.",
    )


_REGISTRATIONS: tuple[ModuleRegistration, ...] = (
    _planned(
        "D0",
        "경기·API 자료 준비",
        "경기 식별과 최근 성적·부상·배당·API 예측 자료 수집. 모델 호출 없음.",
        operation="prepare_match_data",
        expected_model_calls=0,
    ),
    ModuleRegistration(
        module_id="R1",
        display_name="경기력·주목 선수 조사",
        description=(
            "최근 흐름과 주목 선수, 이번 경기의 의미를 근거와 함께 조사합니다."
            " 공통 모델 경로로 정상 호출 1회를 보내고, 검색 출처와 API 근거를 함께"
            " 보존합니다."
        ),
        operation="research_form",
        depends_on=("D0",),
        contract_version=MODULE_INPUT_VERSION,
        prompt_version="mp05-form-prompt-2",
        inspector_panel="form",
        implemented=True,
        mode_scope=(RunMode.LIVE, RunMode.REPLAY),
        expected_model_calls=1,
        unrunnable_reason=None,
    ),
    ModuleRegistration(
        module_id="R2",
        display_name="부상·결장 영향 조사",
        description=(
            "API 부상 상태와 검색 자료를 결합해 결장 영향과 불확실성을 정리합니다."
            " 출전 불확실은 불확실로 남기고 결장 확정으로 바꾸지 않습니다."
        ),
        operation="research_availability",
        depends_on=("D0",),
        contract_version=MODULE_INPUT_VERSION,
        prompt_version="mp06-r2-prompt-2",
        inspector_panel="availability",
        implemented=True,
        mode_scope=(RunMode.LIVE, RunMode.REPLAY),
        expected_model_calls=1,
        unrunnable_reason=None,
    ),
    ModuleRegistration(
        module_id="R3",
        display_name="배당·외부 전망 조사",
        description=(
            "공개 배당, 매체 전망, API 알고리즘 예측을 서로 다른 근거 종류로 구분해"
            " 정리합니다. 경기 전 승무패 시장만 채택합니다."
        ),
        operation="research_outlook",
        depends_on=("D0",),
        contract_version=MODULE_INPUT_VERSION,
        prompt_version="r3-outlook-1",
        inspector_panel="outlook",
        implemented=True,
        mode_scope=(RunMode.LIVE, RunMode.REPLAY),
        expected_model_calls=1,
        unrunnable_reason=None,
    ),
    _planned(
        "S1",
        "프리뷰 종합",
        "검증된 조사 결과만으로 관전 포인트와 AI 예상·이유를 종합.",
        operation="synthesize_preview",
        depends_on=("R1", "R2", "R3"),
        prompt_version="s1-pending",
    ),
    ModuleRegistration(
        module_id=MOCK_DEMO_MODULE_ID,
        display_name="기록 시연 (모의)",
        description=(
            "외부 모델·API를 호출하지 않고 저장 파이프라인 자체를 확인하는 시연 실행입니다. "
            "요청·원문 응답·정규화 변환·다음 입력을 실제 저장 구조에 남깁니다."
        ),
        operation="execute_module",
        depends_on=(),
        contract_version=MODULE_INPUT_VERSION,
        prompt_version="mock-demo-1",
        inspector_panel="generic",
        implemented=True,
        mode_scope=(RunMode.MOCK,),
        expected_model_calls=0,
        unrunnable_reason=None,
    ),
)

MODULE_REGISTRY: dict[str, ModuleRegistration] = {
    registration.module_id: registration for registration in _REGISTRATIONS
}


def list_modules() -> tuple[ModuleRegistration, ...]:
    """등록 순서를 유지한다. 화면 순서가 실행마다 달라지지 않게 하기 위함이다."""
    return _REGISTRATIONS


def get_module(module_id: str) -> ModuleRegistration:
    try:
        return MODULE_REGISTRY[module_id]
    except KeyError:
        raise KeyError(f"module {module_id!r} is not registered") from None


def registered_module_ids() -> tuple[str, ...]:
    return tuple(MODULE_REGISTRY)


def describe_registry() -> dict[str, object]:
    """화면·인계용 등록부 설명. 구현 여부를 숨기지 않는다."""
    return {
        "registry_version": REGISTRY_VERSION,
        "contract_version": CONTRACT_VERSION,
        "inspector_version": INSPECTOR_VERSION,
        "modules": [registration.to_dict() for registration in _REGISTRATIONS],
        "section_workflows": describe_section_workflows(),
        "implemented": [
            registration.module_id
            for registration in _REGISTRATIONS
            if registration.implemented
        ],
        "unavailable": [
            registration.module_id
            for registration in _REGISTRATIONS
            if not registration.implemented
        ],
    }


def _override_in_tests(
    module_id: str, **changes
) -> ModuleRegistration:  # pragma: no cover - 테스트 전용 도우미
    """테스트가 등록부에 모듈을 추가할 때 쓴다. 운영 경로에서는 쓰지 않는다."""
    global _REGISTRATIONS
    current = get_module(module_id)
    updated = replace(current, **changes)
    MODULE_REGISTRY[module_id] = updated
    _REGISTRATIONS = tuple(
        updated if registration.module_id == module_id else registration
        for registration in _REGISTRATIONS
    )
    return updated


# --------------------------------------------------------------------------
# 섹션 워크플로우 — 사용자가 테스트·조정·승인하는 단위
# --------------------------------------------------------------------------

# 정책(AGENTS.md): 사용자 테스트·승인 단위는 프리뷰 섹션을 만드는 완결된
# 워크플로우다. 내부 노드와 D0 같은 자료 준비 단계에는 별도 승인을 요구하지 않는다.
# 그래서 D0는 여기 없다. 각 섹션은 자기 결과에 영향을 주는 모듈 목록을 갖는다.
_SECTION_WORKFLOWS: tuple[SectionWorkflowRegistration, ...] = (
    SectionWorkflowRegistration(
        workflow_id="section_form",
        display_name="경기력·주목 선수 섹션",
        description=(
            "공유 자료 준비(D0)와 경기력 조사(R1)를 묶어 관전 포인트·주목 선수 본문을"
            " 만드는 섹션입니다."
        ),
        module_ids=("D0", "R1"),
        output_contract_version="section_form-output-1",
        implemented=True,
        unrunnable_reason=None,
    ),
    SectionWorkflowRegistration(
        workflow_id="section_availability",
        display_name="부상·결장 영향 섹션",
        description="API 부상 자료와 검색 근거로 결장 영향 본문을 만드는 섹션입니다.",
        module_ids=("D0", "R2"),
        output_contract_version="section_availability-output-1",
        implemented=True,
        unrunnable_reason=None,
    ),
    SectionWorkflowRegistration(
        workflow_id="section_outlook",
        display_name="배당·외부 전망 섹션",
        description="공개 배당·매체 전망·API 예측을 구분해 전망 본문을 만드는 섹션입니다.",
        module_ids=("D0", "R3"),
        output_contract_version="section_outlook-output-1",
        implemented=True,
        unrunnable_reason=None,
    ),
    SectionWorkflowRegistration(
        workflow_id="section_synthesis",
        display_name="AI 예상·종합 섹션",
        description=(
            "검증된 조사 결과를 조합해 AI 예상과 이유를 만드는 섹션입니다."
            " 다른 섹션들의 결과를 입력으로 받습니다."
        ),
        module_ids=("R1", "R2", "R3", "S1"),
        output_contract_version="section_synthesis-output-1",
        implemented=False,
        unrunnable_reason="아직 구현되지 않았습니다. MP-09 이후 확인할 수 있습니다.",
    ),
)

SECTION_WORKFLOWS: dict[str, SectionWorkflowRegistration] = {
    workflow.workflow_id: workflow for workflow in _SECTION_WORKFLOWS
}


def describe_section_workflows() -> dict[str, object]:
    """화면·인계용 섹션 목록. 구현 여부를 숨기지 않는다."""
    return {
        "registry_version": REGISTRY_VERSION,
        "workflows": [workflow.to_dict() for workflow in _SECTION_WORKFLOWS],
        "implemented": [
            workflow.workflow_id for workflow in _SECTION_WORKFLOWS if workflow.implemented
        ],
        "unavailable": [
            workflow.workflow_id
            for workflow in _SECTION_WORKFLOWS
            if not workflow.implemented
        ],
        "approval_scope_note": (
            "승인 단위는 섹션 워크플로우다. 내부 노드와 D0 같은 자료 준비 단계는"
            " 따로 승인하지 않는다."
        ),
    }


def get_section_workflow(workflow_id: str) -> SectionWorkflowRegistration:
    try:
        return SECTION_WORKFLOWS[workflow_id]
    except KeyError:
        raise KeyError(f"section workflow {workflow_id!r} is not registered") from None


def section_workflow_ids() -> tuple[str, ...]:
    return tuple(SECTION_WORKFLOWS)
