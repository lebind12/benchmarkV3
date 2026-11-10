"""Version-derivation acceptance tests for the approval unit."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.preview import approvals, runner, version_manifest
from app.preview.contracts import ConstituentVersion
from app.preview.registry import get_section_workflow


def test_manifest_uses_real_versions_not_placeholders():
    """구성 버전은 실제 모듈·프롬프트·구현 버전이다(빈 자리표시자가 아니다)."""
    constituents = version_manifest.constituents_for_workflow("section_form")
    by_module = {item.module_id: item for item in constituents}

    # 실제 실행 단계(자료 준비·조사·본문 조립)가 모두 들어 있다.
    assert set(by_module) == {"D0", "R1", "compose_body"}
    # 조사 모듈은 프롬프트와 구현 버전이 모두 채워진다.
    assert by_module["R1"].prompt_version == "mp05-form-prompt-2"
    assert by_module["R1"].implementation_version == "mp05-form-2"
    # 프롬프트가 없는 단계는 프롬프트만 빈 문자열이고 구현 버전은 실제 값이다.
    assert by_module["D0"].prompt_version == ""
    assert by_module["D0"].implementation_version == "mp05-stored-d0-1"
    assert by_module["compose_body"].implementation_version == "mp05-compose-2"
    # 계약 버전도 자리표시자가 아니라 실제 계약 값이다.
    for item in constituents:
        assert item.contract_version


def test_same_manifest_is_stable_and_shared_by_execution_and_approval():
    """같은 코드면 실행 버전과 승인 후보 버전이 같은 값으로 안정적이다."""
    workflow = get_section_workflow("section_form")
    first = runner.section_workflow_version(workflow)
    second = runner.section_workflow_version(workflow)
    assert first == second

    candidate, ordered = approvals.release_version(
        workflow, version_manifest.constituents_for_workflow("section_form")
    )
    assert candidate == first
    # 승인 후보의 구성 목록도 실행 구성과 같다.
    assert [item.module_id for item in ordered] == ["D0", "R1", "compose_body"]


def test_semantic_version_change_alters_candidate(monkeypatch):
    """프롬프트·구현·조립·출력 계약이 바뀌면 후보 버전이 바뀐다."""
    workflow = get_section_workflow("section_form")
    base = approvals.release_version(
        workflow, version_manifest.constituents_for_workflow("section_form")
    )[0]

    original = version_manifest.constituents_for_workflow("section_form")

    def _changed(module_id, prompt=None, impl=None):
        return tuple(
            ConstituentVersion(
                item.module_id,
                prompt if module_id == item.module_id and prompt else item.prompt_version,
                impl if module_id == item.module_id and impl else item.implementation_version,
                item.contract_version,
            )
            for item in original
        )

    for variant in (
        _changed("R1", prompt="mp05-form-prompt-3"),
        _changed("R1", impl="mp05-form-3"),
        _changed("compose_body", impl="mp05-compose-3"),
        _changed("D0", impl="mp05-stored-d0-2"),
    ):
        assert approvals.release_version(workflow, variant)[0] != base

    # 출력 계약 버전 변경도 후보를 바꾼다(승인 단위 축).
    from dataclasses import replace

    changed_workflow = replace(workflow, output_contract_version="section_form-output-2")
    assert (
        approvals.release_version(changed_workflow, original)[0] != base
    )


def test_old_result_versions_do_not_become_the_current_candidate(session_factory):
    """저장된 옛 결과의 버전은 현재 후보가 되지 않는다(옛 코드를 새 코드로 표시하지 않음)."""
    workflow = get_section_workflow("section_form")
    current = runner.section_workflow_version(workflow)

    # 옛 실행이 남긴 구성(자리표시자 시절 실행: R1 v1, compose v1)을 승인 근거로 쓸 때
    older = (
        ConstituentVersion("D0", "", "mp05-stored-d0-1", "mp02-1"),
        ConstituentVersion("R1", "mp05-form-prompt-1", "mp05-form-1", "mp02-1"),
        ConstituentVersion("compose_body", "", "mp05-compose-1", "mp02-1"),
    )
    reviewed_version = approvals.release_version(workflow, older)[0]

    # 옛 실행 버전은 현재 버전과 다르다 → 승인 현황이 새 버전 확인을 요구한다.
    assert reviewed_version != current

    # 현재 후보는 변하지 않는다(옛 결과가 현재 구성을 덮어쓰지 않는다).
    assert runner.section_workflow_version(workflow) == current
