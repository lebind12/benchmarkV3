"""bundle 승인 판정과 저장·manifest 계약 축 일치 검사.

검사 이유(실패 시 사용자 영향):

- 수집 자동 생성이 실제로 만들지 않는 섹션(form/synthesis)의 승인을 요구하면, 승인된
  저장본이 있어도 생성이 영원히 시작되지 않는다.
- 실제로 만드는 섹션(odds/ai_forecast)을 판정에서 빠뜨리면 승인 없는 섹션이 게시된다.
- 저장 결과와 현재 계산이 서로 다른 계약 축을 쓰면, 같은 본문을 승인했는데도 매번
  `superseded`로 보여 사용자가 다시 승인해야 하는 것처럼 오해한다.

**합성 검사다.** 실제 DB에 연결하지 않는다. 승인 상태 조회는 대역으로 바꾸고, 판정 대상
집합과 계약 축 계산만 실제 코드로 확인한다.
"""

from __future__ import annotations

import pytest

from app.preview import pipeline, version_manifest
from app.preview.contracts import CONTRACT_VERSION, SECTION_RESULT_CONTRACT_VERSION

pytestmark = pytest.mark.unit


def test_bundle_workflows_match_the_generation_service_section_ids():
    """판정 대상이 생성 서비스의 SECTION_IDS와 **같은 출처**에서 나온다.

    검사 이유: 둘이 따로 정의되면 한쪽만 바뀌어 판정과 생성물이 다시 어긋난다.
    """
    from app.preview import information_bundle

    assert pipeline.bundle_workflows() == tuple(information_bundle.SECTION_IDS)
    # 실제로 만드는 섹션을 포함하고, 만들지 않는 섹션은 요구하지 않는다.
    assert "section_odds" in pipeline.bundle_workflows()
    assert "section_ai_forecast" in pipeline.bundle_workflows()
    assert "section_form" not in pipeline.bundle_workflows()
    assert "section_synthesis" not in pipeline.bundle_workflows()


def test_legacy_required_workflows_keeps_its_own_meaning():
    """옛 전체 프리뷰 판정은 그대로 남는다(그 경로의 의미 보존)."""
    legacy = pipeline.required_workflows()
    assert "section_form" in legacy
    assert "section_synthesis" in legacy
    # 두 집합은 다르며, 그래서 경계별로 골라 써야 한다.
    assert set(legacy) != set(pipeline.bundle_workflows())


def _fake_status(approved_workflow_ids):
    """승인 상태 대역. 지정한 워크플로우만 approved로 본다."""
    from app.preview.contracts import ApprovalState

    def factory(session, workflow_id):
        approved = workflow_id in approved_workflow_ids
        return type(
            "Status",
            (),
            {
                "workflow_id": workflow_id,
                "approved": approved,
                "state": ApprovalState.APPROVED if approved else ApprovalState.NONE,
                "active_approval": (
                    type("A", (), {"workflow_version": version_manifest.workflow_version_of(workflow_id)})()
                    if approved
                    else None
                ),
                "pinned_approval": None,
            },
        )()

    return factory


def test_bundle_admission_requires_exactly_the_generated_sections(monkeypatch):
    """bundle 판정은 생성 섹션 5개가 모두 승인돼야 ready다.

    사용자 영향: form/synthesis 승인이 없다는 이유로 막히지 않고, 실제 생성 섹션이
    빠지면 반대로 ready가 되지 않는다.
    """
    wanted = set(pipeline.bundle_workflows())
    monkeypatch.setattr(
        pipeline.approvals, "section_approval_status", _fake_status(wanted)
    )
    state = pipeline.bundle_admission_state(session=None)
    assert state["ready"] is True
    assert state["missing_approval"] == []
    assert state["scope"] == "bundle"

    # 실제 생성 섹션 하나가 빠지면 ready가 아니다.
    partial = wanted - {"section_odds"}
    monkeypatch.setattr(
        pipeline.approvals, "section_approval_status", _fake_status(partial)
    )
    blocked = pipeline.bundle_admission_state(session=None)
    assert blocked["ready"] is False
    assert blocked["missing_approval"] == ["section_odds"]


def test_bundle_admission_ignores_form_and_synthesis_approvals(monkeypatch):
    """form/synthesis 승인 유무는 bundle 판정을 바꾸지 않는다.

    사용자 영향: 두 섹션은 실제로 생성되지 않으므로, 그 승인 부재로 자동 생성이 막히면
    승인된 저장본이 있어도 홈 문서가 만들어지지 않는다.
    """
    wanted = set(pipeline.bundle_workflows()) | {"section_form", "section_synthesis"}
    monkeypatch.setattr(pipeline.approvals, "section_approval_status", _fake_status(wanted))
    with_legacy = pipeline.bundle_admission_state(session=None)
    assert with_legacy["ready"] is True
    # 판정 대상 목록 자체에 form/synthesis가 없다.
    assert "section_form" not in with_legacy["workflows"]
    assert "section_synthesis" not in with_legacy["workflows"]


def test_stale_approval_still_blocks_bundle_generation(monkeypatch):
    """저장 버전이 현재 구성과 다르면 여전히 차단한다(승인 정책 유지).

    사용자 영향: 승인 이후 구성이 바뀌었는데 그대로 게시하면, 확인하지 않은 결과가
    승인된 것으로 취급된다.
    """
    from app.preview.contracts import ApprovalState

    approved = set(pipeline.bundle_workflows())

    def factory(session, workflow_id):
        is_approved = workflow_id in approved
        return type(
            "Status",
            (),
            {
                "workflow_id": workflow_id,
                "approved": is_approved,
                "state": ApprovalState.APPROVED if is_approved else ApprovalState.NONE,
                "active_approval": (
                    # 승인된 버전이 현재 계산과 **다르다**.
                    type("A", (), {"workflow_version": f"{workflow_id}@old"})()
                    if is_approved
                    else None
                ),
                "pinned_approval": None,
            },
        )()

    monkeypatch.setattr(pipeline.approvals, "section_approval_status", factory)
    state = pipeline.bundle_admission_state(session=None)
    assert state["ready"] is False
    assert set(state["stale_approval"]) == approved


# --------------------------------------------------------------------------
# 저장 경로와 manifest의 계약 축 일치
# --------------------------------------------------------------------------


def test_bundle_workflow_constituents_use_the_section_result_contract_axis():
    """bundle 워크플로우의 모듈 계약 축이 저장 경로와 같다.

    사용자 영향: 축이 다르면 같은 본문을 승인했는데도 매번 superseded로 보여 사용자가
    불필요하게 다시 승인해야 하는 것처럼 오해한다.
    """
    checked = 0
    for workflow_id in pipeline.bundle_workflows():
        entries = version_manifest.constituents_for_workflow(workflow_id)
        module_contracts = {
            entry.contract_version for entry in entries if entry.module_id not in {"D0", "compose_body"}
        }
        if not module_contracts:
            # `section_odds`는 모델 모듈 없이 수집·정규화 결과를 쓴다. 비교할 모듈 축이 없다.
            assert workflow_id == "section_odds"
            continue
        # 모델 모듈 결과는 mp04 축으로 저장된다.
        assert module_contracts == {SECTION_RESULT_CONTRACT_VERSION}, workflow_id
        checked += 1
    # 실제로 모듈이 있는 섹션(players/availability/outlook/ai_forecast)을 확인했다.
    assert checked == 4


def test_legacy_workflow_keeps_the_original_contract_axis():
    """옛 워크플로우(form)의 계약 축은 바꾸지 않는다.

    사용자 영향: 옛 경로의 승인 기록을 흔들면 그 경로의 승인 판단이 바뀐다.
    """
    entries = version_manifest.constituents_for_workflow("section_form")
    module_contracts = {
        entry.contract_version for entry in entries if entry.module_id not in {"D0", "compose_body"}
    }
    assert module_contracts == {CONTRACT_VERSION}


def test_d0_and_compose_keep_the_pipeline_contract_axis():
    """D0·compose는 무조건 바꾸지 않는다(이번 변경 범위 밖).

    사용자 영향: 이 두 단계의 계약 표기가 바뀌면 실제 의미가 같아도 버전 문자열이 달라져
    승인 상태가 흔들린다.
    """
    entries = version_manifest.constituents_for_workflow("section_players")
    by_module = {entry.module_id: entry.contract_version for entry in entries}
    assert by_module["D0"] == CONTRACT_VERSION
    assert by_module["compose_body"] == CONTRACT_VERSION


def test_workflow_version_is_stable_for_the_same_constituents():
    """같은 구성이면 버전 문자열이 같다(불필요한 stale을 만들지 않는다)."""
    first = version_manifest.workflow_version_of("section_players")
    second = version_manifest.workflow_version_of("section_players")
    assert first == second
