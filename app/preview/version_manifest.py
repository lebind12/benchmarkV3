"""섹션 워크플로우 구성을 만드는 **단일 버전 원천**.

이 파일이 책임지는 것:

- 지금 코드가 실제로 실행할 노드 구현의 버전(모듈·프롬프트·구현·계약)을 한 곳에서 정한다.
- 실행(`runner`)과 승인 후보(`approvals`)가 **같은 근거**로 같은 버전을 계산하게 한다.

정직성 규칙:

- 값은 **코드에 고정된 버전 상수**에서만 온다. 프로세스 상태·현재 시각·경기 ID·무작위
  해시·Git HEAD에서 만들지 않는다. 그래야 같은 코드가 같은 버전을 낸다.
- 실제로 실행되지 않는 축을 섞지 않는다. 이 워크플로우가 실행하는 노드만 넣는다.
- 표시 문구만 바뀌는 변경은 여기 값에 영향을 주지 않는다(버전 축이 아니다).
"""

from __future__ import annotations

from typing import Mapping

from app.preview.contracts import (
    CONTRACT_VERSION,
    SECTION_RESULT_CONTRACT_VERSION,
    ConstituentVersion,
)
from app.preview.registry import get_section_workflow

__all__ = [
    "BUNDLE_WORKFLOW_IDS",
    "COMPOSE_MODULE_ID",
    "DATA_MODULE_ID",
    "constituents_for_workflow",
    "workflow_version_of",
]

DATA_MODULE_ID = "D0"
COMPOSE_MODULE_ID = "compose_body"

# 새 기본 경로(정보 원문 묶음 기반) 섹션 워크플로우. 이 목록의 워크플로우만 C 작성
# 어댑터(bundle_sections)의 버전 축을 쓴다. 옛 섹션(section_form 등)은 그대로 둔다.
BUNDLE_WORKFLOW_IDS: frozenset[str] = frozenset(
    {
        "section_players",
        "section_availability",
        "section_outlook",
        "section_odds",
        "section_ai_forecast",
    }
)


def _bundle_manifest(module_id: str) -> tuple[str, str] | None:
    """새 기본 경로(bundle 섹션)의 (프롬프트 버전, 구현 버전). 없으면 None.

    C 작성 어댑터가 자기 버전 표를 소유한다. 여기서 문자열을 복사하지 않는다.
    """
    from app.preview.modules import bundle_sections

    try:
        implementation_version, prompt_version = bundle_sections.bundle_module_versions(
            module_id
        )
    except KeyError:
        return None
    return prompt_version, implementation_version


def _module_manifest(module_id: str) -> tuple[str, str] | None:
    """구현 모듈의 (프롬프트 버전, 구현 버전). 미구현 모듈이면 None.

    각 모듈 파일이 자기 버전 상수를 소유한다(`modules.module_versions`가 그 표다).
    여기에 문자열을 복사해 두지 않는다. 그 함수는 (**구현**, **프롬프트**) 순서를
    돌려주므로 여기서 뒤집어 쓴다.
    """
    from app.preview import modules as module_versions_registry

    try:
        implementation_version, prompt_version = module_versions_registry.module_versions(
            module_id
        )
    except KeyError:
        return None
    return prompt_version, implementation_version


def _prepare_manifest(workflow_id: str) -> tuple[str, str]:
    """자료 준비 노드의 (프롬프트, 구현) 버전.

    조사 섹션들은 같은 D0 노드를 쓴다. `section_synthesis`는 새 자료를 수집하지 않고
    **선택된 결과 버전을 읽어 검증**하는 노드를 쓰므로 구현 버전이 다르다. 프롬프트가
    없는 단계라 프롬프트 버전은 빈 문자열이다.
    """
    from app.preview import sections

    if workflow_id == "section_synthesis":
        from app.preview.modules import synthesis

        return "", synthesis.SELECTED_INPUT_IMPLEMENTATION_VERSION
    return "", sections.STORED_DATA_IMPLEMENTATION_VERSION


def _compose_manifest(workflow_id: str) -> tuple[str, str]:
    """본문 조립 노드의 (프롬프트, 구현) 버전. 섹션마다 조립기가 다르다."""
    from app.preview import sections

    if workflow_id == sections.FORM_SECTION_ID:
        return "", sections.FORM_COMPOSE_IMPLEMENTATION_VERSION
    if workflow_id == "section_availability":
        from app.preview.modules import availability

        return "", availability.COMPOSE_IMPLEMENTATION_VERSION
    if workflow_id == "section_outlook":
        return "", sections.OUTLOOK_COMPOSE_IMPLEMENTATION_VERSION
    if workflow_id == "section_players":
        from app.preview.modules import players

        return "", players.COMPOSE_IMPLEMENTATION_VERSION
    if workflow_id == "section_synthesis":
        from app.preview.modules import synthesis

        return "", synthesis.COMPOSE_IMPLEMENTATION_VERSION
    if workflow_id == "section_odds":
        # 배당은 모델 프롬프트가 없지만(0회) **공급 경로**가 결과 의미를 바꾼다.
        # 공개 표 우선 + 제공자 `/odds` 보충(최대 3개 고유 업체·실행당 1회)이 승인 축에
        # 들어가야, 그 경로가 바뀐 뒤에도 이전 승인 버전과 구분된다.
        from app.preview.sources import provider_odds

        return "", provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION
    return "", ""


def constituents_for_workflow(workflow_id: str) -> tuple[ConstituentVersion, ...]:
    """이 워크플로우가 **실제로 실행하는** 구성 요소의 버전 묶음.

    실행 그래프는 `prepare_data`(D0) → 조사 모듈 → `compose_body` 순서다. 그래서
    등록된 조사 모듈과 D0, 조립 단계를 모두 넣는다. 승인 단위는 이 묶음 전체다.
    """
    workflow = get_section_workflow(workflow_id)
    entries: list[ConstituentVersion] = []

    prepare_prompt, prepare_impl = _prepare_manifest(workflow.workflow_id)
    entries.append(
        ConstituentVersion(
            module_id=DATA_MODULE_ID,
            prompt_version=prepare_prompt,
            implementation_version=prepare_impl,
            contract_version=CONTRACT_VERSION,
        )
    )

    for module_id in workflow.module_ids:
        if module_id == DATA_MODULE_ID:
            continue
        # 새 기본 경로(정보 원문 묶음) 섹션은 C 작성 어댑터의 버전을 쓴다. 옛 경로는
        # 기존 모듈 버전을 그대로 쓴다(옛 실행·승인 기록을 흔들지 않는다).
        manifest = (
            _bundle_manifest(module_id)
            if workflow.workflow_id in BUNDLE_WORKFLOW_IDS
            else None
        ) or _module_manifest(module_id)
        if manifest is None:
            continue
        prompt_version, implementation_version = manifest
        # 계약 축은 **그 결과가 실제로 저장될 때 쓰는 축**과 같아야 한다. bundle 경로는
        # `SECTION_RESULT_CONTRACT_VERSION`으로 모듈 결과를 기록하므로(bundle_pipeline의
        # ModuleInput), 여기서 전역 `CONTRACT_VERSION`을 쓰면 같은 실행을 서로 다른 계약으로
        # 계산해 승인이 늘 stale로 보인다. 옛 워크플로우는 기존 축을 그대로 유지한다.
        module_contract_version = (
            SECTION_RESULT_CONTRACT_VERSION
            if workflow.workflow_id in BUNDLE_WORKFLOW_IDS
            else CONTRACT_VERSION
        )
        entries.append(
            ConstituentVersion(
                module_id=module_id,
                prompt_version=prompt_version,
                implementation_version=implementation_version,
                contract_version=module_contract_version,
            )
        )

    compose_prompt, compose_impl = _compose_manifest(workflow.workflow_id)
    entries.append(
        ConstituentVersion(
            module_id=COMPOSE_MODULE_ID,
            prompt_version=compose_prompt,
            implementation_version=compose_impl,
            contract_version=CONTRACT_VERSION,
        )
    )

    return tuple(sorted(entries, key=lambda item: item.module_id))


def workflow_version_of(workflow_id: str) -> str:
    """이 워크플로우를 지금 코드로 실행했을 때의 버전 문자열."""
    from app.preview import approvals

    workflow = get_section_workflow(workflow_id)
    return approvals.release_version(workflow, constituents_for_workflow(workflow_id))[0]
