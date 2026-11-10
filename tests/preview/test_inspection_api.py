"""MP-02 관리자 검사 API 수용 검사.

확인 항목:

- `test_read_does_not_call_provider`: list/detail/module GET은 외부 호출을 만들지 않는다.
- `test_registered_module_uses_generic_inspector`: 등록된 모듈이 같은 공통 탭 구조로
  보이고, 등록되지 않은 모듈도 같은 구조로 표시된다.
- 관리자 경계와 범위가 한정된 undo·충돌.
"""

from __future__ import annotations

import socket

from sqlalchemy import text

from app.preview import demo_pipeline, store
from app.preview.contracts import (
    CONTRACT_VERSION,
    ExecutionContext,
    Environment,
    OperationKind,
    RunMode,
)

RUNS = "/api/v1/admin/preview/runs"
LOGIN = "/api/v1/auth/login"


def _login_admin(client, make_user) -> dict:
    user = make_user(role="ADMIN")
    response = client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
    assert response.status_code == 200, response.text
    return user


def _create_demo(client) -> dict:
    response = client.post(f"{RUNS}/mock-demo")
    assert response.status_code == 200, response.text
    return response.json()


def test_anonymous_cannot_read_or_create(client):
    assert client.get(RUNS).status_code == 401
    assert client.post(f"{RUNS}/mock-demo").status_code == 401


def test_non_admin_cannot_read_runs_or_create_demo(client, make_user):
    from app.auth.identity import IdentityUser
    from app.auth.service import issue_session
    from app.db import get_session_factory

    user = make_user(role="STREAMER")
    # 세션은 유효하지만 역할이 STREAMER인 경우: 401이 아니라 403이어야 한다.
    factory = get_session_factory()
    with factory() as session:
        principal = IdentityUser(
            id=user["id"], email=user["email"], role=user["role"], is_active=True
        )
        issued = issue_session(session, principal)
        token = issued.token
        session.commit()
    client.cookies.set("preview_admin_session", token)

    assert client.get(RUNS).status_code == 403
    assert client.post(f"{RUNS}/mock-demo").status_code == 403


def test_mock_demo_run_is_labeled_and_reports_zero_external_calls(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)

    assert created["mode"] == "mock"
    assert created["external_calls"] == 0
    assert "mock" in created["label"]
    assert len(created["result_ids"]) == 2

    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    assert detail["summary"]["mode"] == "mock"
    assert detail["summary"]["operation_kind"] == "mock_demo"
    assert detail["summary"]["label"] == demo_pipeline.MOCK_DEMO_LABEL
    assert "mock" in detail["mode_detail"]["label"]
    assert "실제 AI 호출" in detail["mode_detail"]["note"]


def test_read_does_not_call_provider(client, make_user, monkeypatch):
    """GET 경로 전체가 외부 연결을 열지 않는다."""
    _login_admin(client, make_user)
    created = _create_demo(client)

    attempted: list[object] = []
    import http.client
    import urllib.request

    def _deny(*args, **kwargs):
        attempted.append(args)
        raise AssertionError("the read path must not open an outbound connection")

    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _deny)
    monkeypatch.setattr(urllib.request, "urlopen", _deny)

    # DB 커넥션은 이미 풀에 있으므로 조회만으로 새 연결을 열지 않는다.
    assert client.get(RUNS).status_code == 200
    assert client.get(f"{RUNS}/{created['run_id']}").status_code == 200
    module_id = client.get(f"{RUNS}/{created['run_id']}").json()["inspector_modules"][0][
        "module_execution_id"
    ]
    assert client.get(f"{RUNS}/{created['run_id']}/modules/{module_id}").status_code == 200
    assert (
        client.get(
            f"{RUNS}/{created['run_id']}/results/{module_id}/versions"
        ).status_code
        == 200
    )

    assert attempted == []


def test_module_inspector_exposes_the_four_tabs(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)
    detail = client.get(f"{RUNS}/{created['run_id']}").json()

    module = detail["inspector_modules"][0]
    assert set(module["tabs"]) == {"request", "response", "transform", "next_input"}

    request_tab = module["tabs"]["request"]
    assert request_tab["available"] is True
    assert request_tab["attempts"][0]["request_spec"]["provider"] == "recorded-fixture"
    # 실제 전송 본문(모의)에 비밀값 원문이 없다.
    assert "[REDACTED]" in request_tab["attempts"][0]["request_body"]["body"]

    response_tab = module["tabs"]["response"]
    assert response_tab["available"] is True
    assert response_tab["attempts"][0]["http_status"] == 200
    assert "recorded_mock_response" in response_tab["attempts"][0]["content"]["body"]

    transform_tab = module["tabs"]["transform"]
    assert transform_tab["available"] is True
    assert transform_tab["version"] == 2
    assert any(claim["claim_id"] == "claim-odds-1" for claim in transform_tab["claims"])

    next_input_tab = module["tabs"]["next_input"]
    assert next_input_tab["available"] is True
    assert next_input_tab["uses_latest_version"] is True
    assert next_input_tab["selected_result_ids"]


def test_registered_module_uses_generic_inspector(client, make_user, monkeypatch):
    """등록된 모듈과 미등록 모듈이 같은 공통 검사 구조를 쓴다.

    이 검사는 등록부를 읽어 패널을 정하므로, 새 모듈을 붙여도 화면 코드를 고치지
    않는다는 계약을 확인한다.
    """
    _login_admin(client, make_user)
    created = _create_demo(client)

    registry = client.get("/api/v1/admin/preview/registry").json()
    assert "mock_demo" in registry["implemented"]
    # R1·R2·R3 조사와 MP-09 S1 종합 구현이 등록됐다. D0는 공유 자료 준비 단계라
    # 단독 모듈 실행 대상이 아니므로 미구현으로 남는다.
    assert {"R1", "R2", "R3", "S1"} <= set(registry["implemented"])
    s1 = next(m for m in registry["modules"] if m["module_id"] == "S1")
    assert s1["implemented"] is True
    assert s1["prompt_version"] == "mp09-s1-prompt-1"
    assert "D0" in registry["unavailable"]
    unimplemented = next(m for m in registry["modules"] if m["module_id"] == "D0")
    assert unimplemented["implemented"] is False
    assert unimplemented["unrunnable_reason"]

    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    panel = detail["inspector_modules"][0]["panel"]
    assert panel["panel"] == "generic"
    assert panel["registered"] is True
    assert panel["available"] is True

    # 등록되지 않은 모듈 ID도 같은 네 탭 구조로 표시되고, 없다는 사실을 숨기지 않는다.
    from app.preview.inspection import build_module_inspection

    synthetic = build_module_inspection(
        {
            "module_execution_id": "00000000-0000-4000-8000-0000000000aa",
            "module_id": "unregistered_module",
            "status": "succeeded",
            "quality": "pending",
            "attempt_count": 0,
            "retry_count": 0,
            "result_versions": [],
            "latest_result": None,
            "delivered_next_input": {},
            "attempts": [],
            "input": {},
        },
        (),
        run_mode="mock",
    )
    assert synthetic["panel"]["registered"] is False
    assert set(synthetic["tabs"]) == {"request", "response", "transform", "next_input"}


def test_unimplemented_modules_are_not_runnable(client, make_user):
    """구현이 없는 모듈은 실행 가능으로 표시하지 않는다.

    MP-05가 R1 조사 구현을 등록했으므로 R1은 실행 가능하고, 나머지 미구현 모듈은
    `implemented=False`와 사유를 함께 낸다.
    """
    _login_admin(client, make_user)
    registry = client.get("/api/v1/admin/preview/registry").json()
    implemented = {module["module_id"] for module in registry["modules"] if module["implemented"]}
    assert {"mock_demo", "R1", "R2", "R3", "S1"} <= implemented
    for module in registry["modules"]:
        if module["module_id"] in {"mock_demo", "R1", "R2", "R3", "S1"}:
            assert module["unrunnable_reason"] is None
            continue
        assert module["implemented"] is False
        assert module["unrunnable_reason"]


def test_detail_of_unknown_run_is_404(client, make_user):
    _login_admin(client, make_user)
    missing = "00000000-0000-4000-8000-0000000000ff"
    assert client.get(f"{RUNS}/{missing}").status_code == 404
    assert client.get(f"{RUNS}/{missing}/undo").status_code == 404


def test_module_of_another_run_is_not_reachable(client, make_user):
    _login_admin(client, make_user)
    first = _create_demo(client)
    second = _create_demo(client)

    detail = client.get(f"{RUNS}/{second['run_id']}").json()
    foreign_module_id = detail["inspector_modules"][0]["module_execution_id"]

    response = client.get(f"{RUNS}/{first['run_id']}/modules/{foreign_module_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "module execution not found"


def test_list_shows_mock_run_with_mode_and_counts(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)

    body = client.get(RUNS).json()
    row = next(r for r in body["runs"] if r["run_id"] == created["run_id"])
    assert row["mode"] == "mock"
    assert row["operation_kind"] == "mock_demo"
    assert row["module_count"] == 1
    assert row["attempt_count"] == 1
    assert row["retry_count"] == 0
    assert row["status"] == "succeeded"


def test_version_compare_endpoint_returns_both_versions(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)
    module_id = created["module_execution_id"]

    body = client.get(f"{RUNS}/{created['run_id']}/results/{module_id}/versions").json()
    assert body["versions_available"] == [1, 2]
    assert body["base"]["version"] == 1
    assert body["target"]["version"] == 2
    assert "claim-context-2" in body["diff"]["claims_added"]


def test_registry_and_retention_endpoints_report_state(client, make_user):
    _login_admin(client, make_user)
    _create_demo(client)

    registry = client.get("/api/v1/admin/preview/registry").json()
    assert registry["contract_version"] == CONTRACT_VERSION
    # MP-05~07 조사와 MP-09 S1 종합 구현이 등록됐다. D0는 단독 모듈이 아니라 미구현이다.
    assert {"mock_demo", "R1", "R2", "R3", "S1"} <= set(registry["implemented"])
    assert "D0" in registry["unavailable"]

    retention = client.get("/api/v1/admin/preview/retention").json()
    assert retention["policy"]["raw_artifact_days"] == 30
    assert retention["policy"]["structured_record_days"] == 180
    assert retention["policy"]["automatic_purge"] is False
    assert retention["status"]["artifacts"] >= 2


# --------------------------------------------------------------------------
# 범위가 한정된 undo
# --------------------------------------------------------------------------


def test_undo_removes_only_its_own_development_records(client, make_user, session_factory):
    _login_admin(client, make_user)
    target = _create_demo(client)
    keep = _create_demo(client)

    preview = client.get(f"{RUNS}/{target['run_id']}/undo").json()
    assert preview["write_scope"] == "preview_dev"
    assert preview["undo"]["can_cancel"] is True
    assert preview["would_remove"]["preview_results"] == 2

    response = client.post(
        f"{RUNS}/{target['run_id']}/undo", json={"reason": "개발 기록 정리"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["removed"]["preview_results"] == 2
    assert "preview_runs" in result["kept"]

    # 취소된 실행은 목록에 남되 상태가 cancelled이고, 기록은 열 수 없다.
    detail = client.get(f"{RUNS}/{target['run_id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["summary"]["status"] == "cancelled"
    assert body["summary"]["cancelled_at"] is not None
    assert body["modules"] == []
    assert body["undo"]["state"] == "cancelled"

    # 다른 실행은 그대로다.
    other = client.get(f"{RUNS}/{keep['run_id']}").json()
    assert other["summary"]["status"] == "succeeded"
    assert len(other["results"]) == 2

    with session_factory() as session:
        remaining = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results WHERE run_id = :run"
            ),
            {"run": keep["run_id"]},
        ).scalar_one()
        removed = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results WHERE run_id = :run"
            ),
            {"run": target["run_id"]},
        ).scalar_one()
    assert remaining == 2
    assert removed == 0


def test_undo_is_blocked_when_a_later_version_exists(
    client, make_user, session_factory
):
    """다른 실행이 남긴 후속 버전이 있으면 취소하지 않고 충돌로 남긴다."""
    _login_admin(client, make_user)
    created = _create_demo(client)

    with session_factory() as session:
        execution = store.get_run_detail(session, created["run_id"]).modules[0]
        # 모듈 실행에 다른 실행 소유의 결과 행을 추가해 후속 변경을 흉내 낸다.
        from app.preview.models import PreviewResult

        foreign_run_id = store.store_run(
            session,
            ExecutionContext(
                run_id=__import__("uuid").uuid4(),
                operation_kind=OperationKind.MODULE,
                environment=Environment.DEV,
                mode=RunMode.MOCK,
                actor_id=99,
                config_version="conflict-test",
            ),
        ).id
        session.add(
            PreviewResult(
                run_id=foreign_run_id,
                module_execution_id=__import__("uuid").UUID(
                    execution["module_execution_id"]
                ),
                module_id="mock_demo",
                version=3,
                input_hash="other",
                status="succeeded",
                quality="pending",
                payload={},
                implementation_version="other",
                prompt_version="other",
                contract_version=CONTRACT_VERSION,
            )
        )
        session.commit()

    response = client.post(f"{RUNS}/{created['run_id']}/undo", json={"reason": "정리"})
    assert response.status_code == 409, response.text
    assert "충돌" in response.json()["detail"]

    # 아무것도 지워지지 않았다. 이 실행의 결과 2건과 다른 실행의 후속 결과가 모두 남는다.
    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    assert detail["summary"]["status"] == "succeeded"
    assert len(detail["results"]) == 2

    with session_factory() as session:
        foreign_count = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results "
                "WHERE module_execution_id = :m AND version = 3"
            ),
            {"m": created["module_execution_id"]},
        ).scalar_one()
    assert foreign_count == 1


def test_undo_keeps_the_cancellation_audit_marker(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)

    assert (
        client.post(f"{RUNS}/{created['run_id']}/undo", json={"reason": "감사 표시 확인"})
        .status_code
        == 200
    )

    audit = client.get(f"{RUNS}/{created['run_id']}/audit").json()
    actions = [event["action"] for event in audit["events"]]
    assert "run_cancelled" in actions
    cancelled = next(e for e in audit["events"] if e["action"] == "run_cancelled")
    assert cancelled["detail"]["reason"] == "감사 표시 확인"
    # 계정 ID는 bigint이며 JSON에서 문자열로 나간다(JS 숫자 안전 범위 보호).
    assert isinstance(cancelled["actor_id"], str)
    assert int(cancelled["actor_id"]) > 0
    assert audit["write_scope"] == "preview_dev"

    # 두 번째 취소는 충돌이며 아무것도 바꾸지 않는다.
    again = client.post(f"{RUNS}/{created['run_id']}/undo", json={"reason": "재시도"})
    assert again.status_code == 409


def test_undo_requires_admin(client, make_user):
    _login_admin(client, make_user)
    created = _create_demo(client)
    client.post("/api/v1/auth/logout")

    assert client.post(f"{RUNS}/{created['run_id']}/undo", json={"reason": "x"}).status_code == 401


def test_undo_never_targets_existing_game_or_account_data(client, make_user, session_factory):
    """취소 뒤에도 기존 계정 행이 그대로다."""
    user = _login_admin(client, make_user)
    created = _create_demo(client)
    client.post(f"{RUNS}/{created['run_id']}/undo", json={"reason": "범위 확인"})

    with session_factory() as session:
        row = session.execute(
            text("SELECT email, role, is_active FROM public.app_user WHERE id = :id"),
            {"id": user["id"]},
        ).one()
    assert row.email == user["email"]
    assert row.role == "ADMIN"
    assert row.is_active is True
