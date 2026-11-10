"""MP-04 섹션 워크플로우 실행기 검사.

이 파일이 확인하는 것:

- 실제 LangGraph `StateGraph`로 섹션 워크플로우가 실행되고, 노드 상태가 다음
  노드로 전달된다. 별도 실행 엔진을 만들지 않았다는 사실을 구조로 확인한다.
- 섹션 본문과 근거가 `preview_dev.preview_section_results`에 저장되고, 실행 ID로
  다시 열 수 있다(영속성).
- 승인은 **실제 섹션 본문 결과**에만 연결된다. 모의 결과는 거부된다.
- 등록되지 않은 단계는 본문을 만들어 채우지 않고 정직하게 실패로 남는다.
- 저장 응답 재생(`replay_result`)은 외부 호출 0회이며 원본 결과를 덮어쓰지 않는다.

실제 모델·API 호출은 하지 않는다. 모의 구현과 모의 transport로 확인하며, 그 사실을
live 성공으로 표현하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.preview import approvals, provider, runner, store
from app.preview.contracts import (
    ApprovalState,
    AttemptOutcome,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
    RunStatus,
)
from app.preview.registry import get_section_workflow

FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
LOGIN = "/api/v1/auth/login"
SECTION_RUNS = "/api/v1/admin/preview/section-runs"
RUNS = "/api/v1/admin/preview/runs"


def _login_admin(client, make_user) -> dict:
    user = make_user(role="ADMIN")
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    return user


def _fixture() -> dict:
    return {
        "fixture_id": 1000039,
        "league_id": 39,
        "season": 2026,
        "home_team_id": 50,
        "away_team_id": 49,
        "kickoff_at": "2026-11-11T12:00:00+00:00",
    }


# --------------------------------------------------------------------------
# 실행 구조
# --------------------------------------------------------------------------


def test_section_run_uses_langgraph_state_graph(session_factory):
    """실행이 LangGraph StateGraph 컴파일 결과로 돌아간다(자체 엔진 아님)."""
    from langgraph.graph.state import CompiledStateGraph

    with session_factory() as session:
        implementations = runner.mock_section_implementations("section_form")
        ctx = runner.SectionNodeContext(
            session=session,
            context=ExecutionContext(
                run_id=uuid.uuid4(),
                operation_kind=OperationKind.SECTION,
                environment=Environment.DEV,
                mode=RunMode.MOCK,
                actor_id=1,
                config_version="mp04-test",
                limits=ExecutionLimits(),
            ),
            budget=runner.RunBudget.for_run(now=FIXED_NOW),
            workflow_id="section_form",
            workflow_version="v1",
            fixture=_fixture(),
            mode=RunMode.MOCK,
            transport=None,
            actor_id=1,
        )
        graph = runner.build_section_workflow(implementations=implementations, ctx=ctx)
        assert isinstance(graph, CompiledStateGraph)
        # 노드 순서가 계획과 같다.
        assert runner.NODE_ORDER == (
            "prepare_data",
            "research",
            "compose_body",
            "finalize",
        )


def test_section_run_persists_reader_facing_body_and_sources(session_factory):
    """섹션 본문·근거·버전·실행 방식이 저장되고 실행 ID로 다시 열린다."""
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=7,
            fixture=_fixture(),
            fixture_label="테스트 경기",
            now=FIXED_NOW,
        )
        session.commit()

        assert result.body.strip()
        assert result.sources
        assert result.section_result_id is not None
        assert result.section_result_version == 1
        assert result.mode is RunMode.MOCK

        # 저장된 행만으로 다시 연다(외부 호출 없음).
        detail = store.get_run_detail(session, result.run_id)
        assert detail.summary.operation_kind is OperationKind.SECTION
        assert detail.summary.mode is RunMode.MOCK
        assert len(detail.section_results) == 1
        stored = detail.section_results[0]
        assert stored["workflow_id"] == "section_form"
        assert stored["body"] == result.body
        assert stored["sources"] == [dict(item) for item in result.sources]
        assert stored["mode"] == "mock"
        assert stored["version"] == 1
        # 본문을 만든 내부 노드 실행이 진단으로 연결돼 있다.
        assert stored["module_execution_ids"]
        assert stored["result_ids"]
        assert detail.summary.module_count == len(stored["module_execution_ids"])


def test_section_run_records_node_steps_for_diagnostics(session_factory):
    """노드 단계는 진단으로 남는다. 사용자 승인 단위는 섹션이다."""
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=7,
            now=FIXED_NOW,
        )
        session.commit()

        nodes = [step["node"] for step in result.step_log]
        assert nodes == ["prepare_data", "research", "compose_body", "finalize"]
        # 모의 실행은 실제 외부 호출이 없다.
        assert result.external_calls == 0


def test_missing_implementation_produces_no_body(session_factory):
    """구현이 없으면 본문을 만들어 채우지 않고 정직하게 실패로 남는다."""
    empty = runner.WorkflowImplementations()
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=empty,
            actor_id=7,
            now=FIXED_NOW,
        )
        session.commit()

        assert result.body == ""
        assert result.unavailable is True
        assert result.unavailable_reason
        assert result.quality.value == "insufficient"
        stored = store.get_run_detail(session, result.run_id).section_results[0]
        assert stored["unavailable"] is True
        assert stored["body"] == ""


def test_availability_reports_missing_implementations_honestly():
    """실행 가능성 조회는 미구현을 숨기지 않는다."""
    availability = runner.section_run_availability("section_form", {})
    assert availability["implemented"] is False
    assert "D0" in availability["missing_implementations"]
    assert availability["note"]

    built = {
        "section_form": runner.mock_section_implementations("section_form"),
    }
    ready = runner.section_run_availability("section_form", built)
    assert ready["implemented"] is True
    assert ready["modes"] == ["mock"]


# --------------------------------------------------------------------------
# 승인 연결
# --------------------------------------------------------------------------


def test_approval_links_to_the_real_section_result(client, make_user):
    """승인은 실제 섹션 본문 결과와 실행에 연결된다."""
    _login_admin(client, make_user)
    created = client.post(
        SECTION_RUNS, json={"workflow_id": "section_form", "mode": "mock"}
    ).json()
    assert created["section_result_id"]

    # 모의 결과는 승인 근거가 아니다.
    refused = client.post(
        "/api/v1/admin/preview/sections/section_form/approvals",
        json={
            "run_id": created["run_id"],
            "section_result_id": created["section_result_id"],
        },
    )
    assert refused.status_code == 422
    assert "모의" in refused.json()["detail"]


def test_approval_is_written_when_a_matching_non_mock_result_exists(
    session_factory,
):
    """실제 생성 결과가 있으면 승인 행이 만들어지고 증거 ID가 함께 남는다.

    이 검사는 승인 **경로**를 확인한다. 실제 생성 구현은 MP-05 이후이므로 여기서는
    live 모드를 밝힌 테스트 구현으로 근거를 만든다. 이 결과를 실제 조사 결과라고
    주장하지 않는다.
    """
    from app.preview.contracts import QualityStatus

    def compose_live(ctx, state):  # noqa: ANN001 - 노드 계약
        return runner.NodeOutcome(
            title="검증용 섹션",
            body="검증용 본문입니다.",
            sources=({"label": "검증 출처", "url": "https://example.test/a"},),
            quality=QualityStatus.PENDING,
        )

    implementations = runner.WorkflowImplementations(
        prepare_data=runner.NodeImplementation(
            module_id="D0",
            implementation_version="test-d0",
            prompt_version=None,
            mode=RunMode.LIVE,
            run=lambda ctx, state: runner.NodeOutcome(payload={"ok": True}),
        ),
        research=(
            runner.NodeImplementation(
                module_id="R1",
                implementation_version="test-r1",
                prompt_version="test-r1-p1",
                mode=RunMode.LIVE,
                run=lambda ctx, state: runner.NodeOutcome(payload={"claims": []}),
            ),
        ),
        compose_body=runner.NodeImplementation(
            module_id=runner.COMPOSE_MODULE_ID,
            implementation_version="test-compose",
            prompt_version="test-compose-p1",
            mode=RunMode.LIVE,
            run=compose_live,
        ),
    )

    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=implementations,
            actor_id=11,
            now=FIXED_NOW,
        )
        session.flush()

        approval = approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=result.run_id,
            section_result_id=result.section_result_id,
            actor_id=11,
            note="검증용 승인 경로 확인",
            now=FIXED_NOW,
        )
        session.commit()

        assert approval.workflow_id == "section_form"
        assert approval.evidence.run_id == result.run_id
        assert approval.evidence.section_result_id == result.section_result_id
        assert approval.approved_by_actor_id == "11"
        # 승인 대상 구성은 이 실행이 **실제로 돌린** 노드들이다: 자료 준비(D0)·조사(R1)·
        # 본문 조립(compose_body). 본문 조립도 결과 문장을 바꾸는 실행 단계이므로
        # 구성에서 빼지 않는다.
        assert [item.module_id for item in approval.constituents] == [
            "D0",
            "R1",
            "compose_body",
        ]
        by_module = {item.module_id: item for item in approval.constituents}
        # 승인은 그 실행이 남긴 실제 버전을 가리킨다(지어낸 값이 아니다).
        assert by_module["D0"].implementation_version == "test-d0"
        assert by_module["R1"].prompt_version == "test-r1-p1"
        assert by_module["compose_body"].implementation_version == "test-compose"

        status = approvals.section_approval_status(session, "section_form")
        # 이 실행은 테스트용 버전(test-*)으로 만들었으므로 현재 코드 구성과 다르다.
        # 그래서 옛 결과가 현재 버전을 조용히 승인하지 않고 새 버전 확인을 요구한다.
        assert status.state is ApprovalState.SUPERSEDED
        assert status.active_approval is None
        assert status.pinned_approval is not None
        assert status.pinned_approval.workflow_version == approval.workflow_version
        # 현재 후보 버전은 실행이 남긴 옛 버전과 다르다(덮어쓰지 않는다).
        assert status.current_version != approval.workflow_version


def test_approval_refuses_a_section_result_from_another_run(session_factory):
    """다른 실행의 섹션 결과는 승인 근거로 쓸 수 없다."""
    with session_factory() as session:
        first = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=7,
            now=FIXED_NOW,
        )
        second = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=7,
            now=FIXED_NOW,
        )
        session.flush()

        with pytest.raises(approvals.ApprovalRequestError):
            approvals.approve_section_version(
                session,
                workflow_id="section_form",
                run_id=first.run_id,
                section_result_id=second.section_result_id,
                actor_id=11,
            )


# --------------------------------------------------------------------------
# 저장 응답 재생
# --------------------------------------------------------------------------


def test_replay_has_zero_network_calls(session_factory, monkeypatch):
    """저장 응답 재생은 외부 호출 0회이며 원본 결과를 덮어쓰지 않는다."""
    import socket

    def _deny(*args, **kwargs):
        raise AssertionError("replay must not open an outbound connection")

    monkeypatch.setattr(socket.socket, "connect", _deny)

    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=7,
            now=FIXED_NOW,
        )
        session.commit()

        detail = store.get_run_detail(session, result.run_id)
        source = detail.results[0]
        source_id = uuid.UUID(source["result_id"])

        outcome = provider.replay_result(
            session,
            source_result_id=source_id,
            transform=lambda raw_body, payload: {
                "claims": (payload or {}).get("claims") or [],
                "coverage": (payload or {}).get("coverage") or [],
                "diagnostics": ["저장된 원문으로 다시 변환했습니다."],
                "payload": {"raw_present": raw_body is not None},
            },
            actor_id=7,
            now=FIXED_NOW,
        )
        session.commit()

        assert outcome.external_calls == 0
        assert outcome.new_result_id != source_id
        assert outcome.new_version == source["version"] + 1

        after = store.get_run_detail(session, result.run_id)
        # 원본 결과가 그대로 남아 있다.
        versions = {
            row["result_id"]: row["version"]
            for row in after.results
            if row["module_execution_id"] == source["module_execution_id"]
        }
        assert versions[str(source_id)] == source["version"]
        assert versions[str(outcome.new_result_id)] == outcome.new_version


def test_section_api_rejects_live_until_implementations_exist(client, make_user):
    """모델 설정이 없는 live 실행을 성공으로 꾸미지 않는다.

    R1 구현이 등록된 뒤에도 live는 `PREVIEW_MODEL_LIVE_ENABLED`와 실제 모델 설정이
    있어야 열린다. 설정이 없으면 모의로 대체하지 않고 422로 거부한다.
    """
    _login_admin(client, make_user)
    response = client.post(
        SECTION_RUNS, json={"workflow_id": "section_form", "mode": "live"}
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "모델 설정" in detail or "mock" in detail


def test_section_api_requires_admin(client):
    assert client.post(SECTION_RUNS, json={"workflow_id": "section_form"}).status_code == 401
    assert client.get("/api/v1/admin/preview/sections").status_code == 401


def test_section_detail_exposes_body_before_diagnostics(client, make_user):
    """검사 화면 응답은 섹션 본문·근거를 먼저 주고 노드 진단은 뒤에 둔다."""
    _login_admin(client, make_user)
    created = client.post(
        SECTION_RUNS, json={"workflow_id": "section_form", "mode": "mock"}
    ).json()

    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    assert detail["section_results"]
    row = detail["section_results"][0]
    assert row["body"]
    assert row["mode_label"]
    assert row["approvable"] is False  # 모의 결과는 승인 대상이 아니다
    # 모의 결과는 승인 근거 ID로 쓰이지 않는다.
    assert detail["section_result_id"] is None
    # 노드 진단은 여전히 같은 실행 안에 있다.
    assert detail["inspector_modules"]
    assert "모의" in detail["approval_note"]


# --------------------------------------------------------------------------
# 수용 기준: 429 → 대기 → 성공 흔적이 검사 화면 응답에 남는다
# --------------------------------------------------------------------------


def test_retry_trace_is_visible_in_the_run_inspection(client, make_user, session_factory):
    """429 뒤 성공한 실행을 검사 화면 응답에서 그대로 확인한다.

    제공자 응답·시도를 실제로 저장한 뒤 `GET /runs/{id}`의 검사 구조에 두 시도가
    모두 나타나는지 본다. 이 검사는 **모의 transport**로 재현한 것이며 실제 계정의
    429 발생률 측정이 아니다.
    """
    import uuid as uuid_module

    from app.preview import provider
    from app.preview.contracts import (
        ExecutionContext,
        ExecutionLimits,
        OperationKind,
        RunMode,
        RunStatus,
    )
    from app.preview.retry import RunBudget

    user = _login_admin(client, make_user)
    run_id = uuid_module.uuid4()
    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=RunMode.MOCK,
        actor_id=user["id"],
        config_version="mp04-retry-trace",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )

    with session_factory() as session:
        store.store_run(session, context, label="MP-04 429 검증", status=RunStatus.RUNNING)
        transport = provider.RecordedTransport(
            script=[
                provider.TransportResult(
                    http_status=429,
                    raw_request={"contents": "요청"},
                    raw_response={"error": {"code": 429, "message": "rate limited"}},
                    error_class="rate_limited",
                    error_message="rate limited",
                    retry_after_seconds=2.0,
                ),
                provider.TransportResult(
                    http_status=200,
                    raw_request={"contents": "요청"},
                    raw_response={
                        "candidates": [
                            {"content": {"parts": [{"text": "성공 응답"}], "role": "model"}}
                        ]
                    },
                ),
            ]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_form/research-1",
                provider="mock-transport",
                model="mock-model",
                operation="request_model",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert result.attempt_count == 2
        store.finish_run(session, run_id, status=RunStatus.SUCCEEDED)
        session.commit()

    detail = client.get(f"{RUNS}/{run_id}").json()
    attempts = detail["attempts"]
    assert [row["http_status"] for row in attempts] == [429, 200]
    assert attempts[1]["attempt_ordinal"] == 1
    # 재시도 대기가 기록에 남는다(2초).
    assert attempts[1]["wait_ms"] == 2000
    # 실행 요약이 재시도 1건을 센다.
    assert detail["summary"]["attempt_count"] == 2
    assert detail["summary"]["retry_count"] == 1
    # 모의 transport 기록이 live로 표시되지 않는다.
    assert detail["summary"]["mode"] == "mock"


# --------------------------------------------------------------------------
# 저장 경기 자료 연결 (MP-03 소유 파일의 설정·조회기 연결)
# --------------------------------------------------------------------------


def test_fixture_list_reports_unreadable_access_instead_of_empty(client, make_user):
    """읽기 연결이 없으면 빈 목록으로 감추지 않고 사유를 남긴다."""
    _login_admin(client, make_user)
    body = client.get("/api/v1/admin/preview/fixtures").json()
    assert "candidates" in body or "fixtures" in body
    access = body.get("stored_access") or {}
    # 연결이 없으면 readable=false와 사유가 있어야 한다. 빈 목록을 "경기 없음"으로
    # 단정하지 않는다.
    if not access.get("readable"):
        assert access.get("detail")


def test_fixture_import_records_a_mock_catalog_run(client, make_user):
    """경기 목록 수집은 fixture_catalog로 기록되고 외부 호출 0회로 표시된다."""
    _login_admin(client, make_user)
    response = client.post(
        "/api/v1/admin/preview/fixtures/import",
        json={"league_id": 39, "date": "2026-11-21", "timezone": "UTC"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["external_calls"] == 0
    assert "모의" in body["note"]
