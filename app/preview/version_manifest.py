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
    ConstituentVersion,
)
from app.preview.registry import get_section_workflow

__all__ = [
    "COMPOSE_MODULE_ID",
    "DATA_MODULE_ID",
    "constituents_for_workflow",
    "workflow_version_of",
]

DATA_MODULE_ID = "D0"
COMPOSE_MODULE_ID = "compose_body"


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


def _prepare_manifest() -> tuple[str, str]:
    """D0(공유 자료 준비) 노드의 (프롬프트, 구현) 버전.

    섹션마다 같은 D0 노드를 쓴다. 프롬프트가 없는 단계라 프롬프트 버전은 빈 문자열이다.
    """
    from app.preview import sections

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
    return "", ""


def constituents_for_workflow(workflow_id: str) -> tuple[ConstituentVersion, ...]:
    """이 워크플로우가 **실제로 실행하는** 구성 요소의 버전 묶음.

    실행 그래프는 `prepare_data`(D0) → 조사 모듈 → `compose_body` 순서다. 그래서
    등록된 조사 모듈과 D0, 조립 단계를 모두 넣는다. 승인 단위는 이 묶음 전체다.
    """
    workflow = get_section_workflow(workflow_id)
    entries: list[ConstituentVersion] = []

    prepare_prompt, prepare_impl = _prepare_manifest()
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
        manifest = _module_manifest(module_id)
        if manifest is None:
            continue
        prompt_version, implementation_version = manifest
        entries.append(
            ConstituentVersion(
                module_id=module_id,
                prompt_version=prompt_version,
                implementation_version=implementation_version,
                contract_version=CONTRACT_VERSION,
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
