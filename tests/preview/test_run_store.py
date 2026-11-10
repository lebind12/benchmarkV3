"""MP-02 실행 기록 저장소 수용 검사.

검사 범위는 계획 §6 MP-02의 수용 기준 그대로다.

- `test_trace_survives_restart`: 앱을 다시 만들어도 같은 실행·원문·버전이 남는다.
- `test_trace_redacts_secrets`: 저장된 원문과 응답 어디에도 비밀값이 없다.
- `test_version_compare_keeps_old_result`: 새 결과가 이전 버전을 지우지 않는다.

`test_read_does_not_call_provider`와 만료·등록부 검사는 각각
`test_inspection_api.py`, `test_retention.py`, `test_inspection_api.py`에 있다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.preview import demo_pipeline, store
from app.preview.contracts import (
    CONTRACT_VERSION,
    ClaimDecision,
    ClaimKind,
    Environment,
    EvidenceClaim,
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
    compute_input_hash,
)

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "recorded_run.json").read_text(encoding="utf-8")
)


def _fixture_identity() -> FixtureIdentity:
    return FixtureIdentity(
        fixture_id=800_001,
        league_id=39,
        season=2026,
        home_team_id=50,
        away_team_id=49,
        kickoff_at=datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc),
    )


def _context(mode=RunMode.MOCK, operation=OperationKind.MODULE) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=operation,
        environment=Environment.DEV,
        mode=mode,
        actor_id=7,
        config_version=f"test/{CONTRACT_VERSION}",
        limits=ExecutionLimits(model_requests=0, api_requests=0),
    )


def _module_input(module_id: str = "mock_demo") -> ModuleInput:
    fixture = _fixture_identity()
    return ModuleInput(
        module_id=module_id,
        fixture=fixture,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash({"fixture": fixture.to_dict()}),
        prompt_version="test-prompt-1",
        contract_version=CONTRACT_VERSION,
        implementation_version="test-impl-1",
    )


def _result(
    run_id, execution_id, module_id="mock_demo", *, status=ModuleStatus.SUCCEEDED
) -> ModuleResult:
    return ModuleResult(
        result_id=uuid.uuid4(),
        module_id=module_id,
        module_execution_id=execution_id,
        run_id=run_id,
        version=1,
        input_hash="input-hash",
        status=status,
        quality=QualityStatus.PENDING,
        claims=(
            EvidenceClaim(
                claim_id="claim-1",
                kind=ClaimKind.FACT,
                text="첫 번째 버전의 사실",
                decision=ClaimDecision.ADOPTED,
            ),
        ),
    )


def test_trace_survives_restart(session_factory, engine):
    """저장한 실행을 앱을 새로 만든 뒤에도 같은 값으로 다시 읽는다."""
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()

    from app.main import create_app

    # 새 앱 인스턴스는 새 세션 팩토리를 쓴다. 메모리에 남은 상태가 없다.
    create_app()
    with session_factory() as session:
        detail = store.get_run_detail(session, created.run_id)

    assert detail.summary.run_id == created.run_id
    assert detail.summary.mode is RunMode.MOCK
    assert detail.summary.status is RunStatus.SUCCEEDED
    assert detail.summary.label == demo_pipeline.MOCK_DEMO_LABEL

    module = detail.modules[0]
    assert module["module_id"] == "mock_demo"
    assert module["result_versions"] == [1, 2]

    attempts = detail.attempts
    assert len(attempts) == 1
    assert attempts[0]["outcome"] == "ok"
    assert attempts[0]["response_artifact_id"] is not None

    # 원문이 저장되어 있고, 다음 조회에서도 같은 본문을 준다.
    responses = [a for a in detail.artifacts if a["kind"] == "raw_response"]
    assert len(responses) == 1
    assert responses[0]["status"] == "available"
    assert "recorded_mock_response" in responses[0]["body"]

    with session_factory() as session:
        again = store.get_run_detail(session, created.run_id)
    assert again.artifacts == detail.artifacts
    assert again.results == detail.results


def test_trace_redacts_secrets(session_factory):
    """저장된 원문·API 응답 어디에도 비밀값 원문이 남지 않는다."""
    secrets = FIXTURE["secrets_that_must_not_be_stored"]
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()

        detail = store.get_run_detail(session, created.run_id)
        serialized = json.dumps(detail.to_dict(), ensure_ascii=False, default=str)

        # DB에 실제로 남은 본문도 직접 확인한다. 직렬화 결과만 보는 것으로는
        # 저장 자체가 안전한지 알 수 없다.
        stored_bodies = list(
            session.execute(text("SELECT body FROM preview_dev.preview_artifacts")).scalars()
        )
        stored_json = json.dumps(
            [row for row in session.execute(text(
                "SELECT request_spec::text, usage::text FROM preview_dev.preview_attempts"
            ))],
            default=str,
        )

    for secret in secrets:
        assert secret not in serialized
        for body in stored_bodies:
            assert body is None or secret not in body
        assert secret not in stored_json

    # 제거 표시는 남아 있어 어떤 필드가 지워졌는지 화면에서 확인할 수 있다.
    request_artifact = next(a for a in detail.artifacts if a["kind"] == "raw_request")
    assert "[REDACTED]" in request_artifact["body"]
    assert request_artifact["redacted"] is True


def test_version_compare_keeps_old_result(session_factory):
    """새 결과를 저장해도 이전 버전이 남고, 비교가 두 버전을 함께 보여준다."""
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()

        detail = store.get_run_detail(session, created.run_id)
        versions = [row["version"] for row in detail.results]
        assert versions == [1, 2], "두 버전이 모두 남아야 한다"

        comparison = store.compare_result_versions(session, created.module_execution_id)
        assert comparison["base"]["version"] == 1
        assert comparison["target"]["version"] == 2
        assert comparison["versions_available"] == [1, 2]
        # 두 번째 버전에서 추가된 claim이 diff에 드러난다.
        assert "claim-context-2" in comparison["diff"]["claims_added"]
        # 같은 입력으로 만든 버전이므로 input_hash는 그대로다.
        assert comparison["diff"]["input_hash"]["changed"] is False


def test_new_module_result_version_appends_and_links_previous(session_factory):
    """같은 모듈 실행의 결과를 다시 저장하면 새 버전 행이 추가된다."""
    with session_factory() as session:
        context = _context()
        run = store.store_run(session, context, fixture=_fixture_identity())
        execution = store.start_module_execution(
            session, run_id=run.id, module_id="mock_demo", module_input=_module_input()
        )
        first = store.save_module_result(session, _result(run.id, execution.id))

        revised = _result(run.id, execution.id)
        revised = ModuleResult(
            **{
                **revised.__dict__,
                "claims": (
                    EvidenceClaim(
                        claim_id="claim-1",
                        kind=ClaimKind.FACT,
                        text="정정된 사실",
                        decision=ClaimDecision.ADOPTED,
                    ),
                ),
            }
        )
        second = store.save_module_result(session, revised)
        session.commit()

        assert first.version == 1
        assert second.version == 2
        assert second.supersedes_result_id == first.id

        comparison = store.compare_result_versions(session, execution.id)
        assert comparison["diff"]["claims_changed"] == ["claim-1"]

        # 첫 버전의 payload는 바뀌지 않았다.
        stored_first = session.get(type(first), first.id)
        assert stored_first.payload["claims"][0]["text"] == "첫 번째 버전의 사실"


def test_result_rejects_foreign_module_execution(session_factory):
    """다른 실행의 모듈 실행에 결과를 붙이려 하면 저장하지 않는다."""
    from app.preview.contracts import ContractError

    with session_factory() as session:
        run_a = store.store_run(session, _context(), fixture=_fixture_identity())
        run_b = store.store_run(session, _context(), fixture=_fixture_identity())
        execution_a = store.start_module_execution(
            session, run_id=run_a.id, module_id="mock_demo", module_input=_module_input()
        )
        session.flush()

        with pytest.raises(ContractError):
            store.save_module_result(session, _result(run_b.id, execution_a.id))


def test_production_environment_rejects_non_live_run(session_factory):
    """운영 환경 기록은 live만 허용한다. 모의·재생을 운영으로 세지 않기 위함이다."""
    from app.preview.contracts import ContractError

    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.PROD,
        mode=RunMode.MOCK,
        actor_id=1,
        config_version="test",
    )
    with session_factory() as session:
        with pytest.raises(ContractError):
            store.store_run(session, context)


def test_run_detail_carries_source_kind_and_mode_separately(session_factory):
    """자료 출처(api/search)와 실행 방식(mock)이 별도 필드로 남는다."""
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()
        detail = store.get_run_detail(session, created.run_id)

    assert detail.summary.mode is RunMode.MOCK
    assert detail.summary.environment is Environment.DEV
    assert [source["source_kind"] for source in detail.sources] == ["api"]
    assert detail.contract_versions["contract"] == CONTRACT_VERSION
