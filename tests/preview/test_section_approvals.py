"""MP-02 섹션 워크플로우 승인 수용 검사.

정책(`AGENTS.md` 경기 프리뷰 실행과 섹션 워크플로우 승인)에서 이 파일이 확인하는 것:

- 승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우이며, 내부 모듈·D0에는 별도
  승인을 요구하지 않는다.
- 승인 전 섹션은 승인된 것처럼 표시되지 않는다.
- 승인에는 워크플로우 버전, 구성 모듈/프롬프트/구현/계약 버전 집합, 확인한 실행·섹션
  결과 ID, 승인자·시각이 남는다.
- 근거 없는 승인은 만들어지지 않는다. 완료 보고·테스트 통과는 승인이 아니다.
- 모의 자료는 UI 시연이며 승인 근거가 아니다.

범위는 대표 사례만 본다. 승인 조합의 완전 탐색은 하지 않는다.
"""

from __future__ import annotations

from sqlalchemy import text

from app.preview import approvals
from app.preview.contracts import ApprovalState
from app.preview.registry import section_workflow_ids

RUNS = "/api/v1/admin/preview/runs"
APPROVALS = "/api/v1/admin/preview/approvals"
REGISTRY = "/api/v1/admin/preview/registry"
LOGIN = "/api/v1/auth/login"


def _login_admin(client, make_user) -> dict:
    user = make_user(role="ADMIN")
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    return user


def test_unapproved_sections_are_not_shown_as_approved(client, make_user):
    _login_admin(client, make_user)
    body = client.get(APPROVALS).json()

    assert body["approved"] == []
    # 구현되지 않은 섹션은 모두 미승인으로 남는다. 테스트 통과나 완료 보고로
    # 승인이 생기지 않는다는 사실을 이 초기 상태가 보여준다.
    assert set(body["unapproved"]) == set(section_workflow_ids())
    assert body["workflows"]["section_form"]["state"] == ApprovalState.NONE.value
    assert body["workflows"]["section_form"]["candidate_note"]
    assert "섹션 워크플로우" in body["scope_note"]


def test_approval_unit_is_a_section_not_an_inner_module(client, make_user):
    """D0 같은 자료 준비 단계에는 승인 단위가 없다."""
    _login_admin(client, make_user)
    body = client.get(APPROVALS).json()

    assert "D0" not in body["workflows"]
    # D0는 섹션 구성 모듈로만 등장한다.
    form_modules = body["sections"]["workflows"]
    form = next(w for w in form_modules if w["workflow_id"] == "section_form")
    assert "D0" in form["module_ids"]
    assert "R1" in form["module_ids"]
    assert "자료\n 준비" in body["scope_note"] or "자료 준비" in body["scope_note"]


def test_approval_is_refused_without_section_evidence(client, make_user):
    """섹션 결과 저장이 없으므로 승인 행을 만들지 않고 거부한다."""
    _login_admin(client, make_user)
    created = client.post(f"{RUNS}/mock-demo").json()

    response = client.post(
        "/api/v1/admin/preview/sections/section_form/approvals",
        json={
            "run_id": created["run_id"],
            "section_result_id": "00000000-0000-4000-8000-000000000000",
            "note": "확인했다고 가정한 요청",
        },
    )
    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert "구현되지 않았습니다" in detail or "섹션 결과" in detail

    # 승인 행이 생기지 않았다.
    assert client.get(APPROVALS).json()["approved"] == []


def test_unknown_section_is_404(client, make_user):
    _login_admin(client, make_user)
    created = client.post(f"{RUNS}/mock-demo").json()
    response = client.post(
        "/api/v1/admin/preview/sections/not_a_section/approvals",
        json={
            "run_id": created["run_id"],
            "section_result_id": "00000000-0000-4000-8000-000000000000",
        },
    )
    assert response.status_code == 404


def test_approval_requires_admin(client, make_user):
    _login_admin(client, make_user)
    created = client.post(f"{RUNS}/mock-demo").json()
    client.post("/api/v1/auth/logout")

    payload = {
        "run_id": created["run_id"],
        "section_result_id": "00000000-0000-4000-8000-000000000000",
    }
    assert (
        client.post(
            "/api/v1/admin/preview/sections/section_form/approvals", json=payload
        ).status_code
        == 401
    )
    assert client.get(APPROVALS).status_code == 401


def test_mock_run_detail_shows_sections_without_claiming_approval(client, make_user):
    _login_admin(client, make_user)
    created = client.post(f"{RUNS}/mock-demo").json()

    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    assert "섹션" in detail["approval_note"]
    # MP-09까지 네 섹션 모두 구현이 등록됐다. 그래도 승인 상태는 비어 있어야 한다:
    # 구현 존재가 승인을 만들지 않는다.
    assert set(detail["section_workflows"]["implemented"]) == {
        "section_form",
        "section_availability",
        "section_outlook",
        "section_synthesis",
    }
    assert detail["section_workflows"]["unavailable"] == []
    states = {row["workflow_id"]: row["state"] for row in detail["section_approvals"]}
    assert states
    assert set(states.values()) == {ApprovalState.NONE.value}


def test_recording_a_workflow_version_changes_when_versions_change():
    """같은 구성은 같은 버전, 구성이 바뀌면 다른 버전이 된다.

    표시 문구 변경이 아니라 결과에 영향을 주는 축만 버전을 바꾼다는 계약을 확인한다.
    """
    from app.preview.contracts import ConstituentVersion
    from app.preview.registry import get_section_workflow

    workflow = get_section_workflow("section_form")
    base = (
        ConstituentVersion("D0", "", "impl-d0", "c1"),
        ConstituentVersion("R1", "r1-v1", "impl-r1", "c1"),
    )
    version_a, ordered_a = approvals.release_version(workflow, base)
    version_b, _ = approvals.release_version(workflow, tuple(reversed(base)))
    # 모듈 순서가 달라도 같은 버전이다.
    assert version_a == version_b
    assert [item.module_id for item in ordered_a] == ["D0", "R1"]

    changed = (
        ConstituentVersion("D0", "", "impl-d0", "c1"),
        ConstituentVersion("R1", "r1-v2", "impl-r1", "c1"),
    )
    version_c, _ = approvals.release_version(workflow, changed)
    assert version_c != version_a


def test_approval_status_reads_stored_rows_only(client, make_user, session_factory):
    """승인 현황 조회가 외부 호출 없이 저장 행만 읽는다."""
    _login_admin(client, make_user)
    client.get(APPROVALS)
    client.get(f"{REGISTRY}")

    with session_factory() as session:
        row_count = session.execute(
            text("SELECT count(*) FROM preview_dev.preview_section_approvals")
        ).scalar_one()
    assert row_count == 0
