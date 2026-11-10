"""MP-10 재개·울타리(fencing)·unknown 결과 검사.

확인하는 것:

- 한 갈래가 실패해도 성공한 갈래 결과가 지워지지 않고, 재개가 성공한 조사를
  **다시 호출하지 않는다**.
- 오래된 실행자(울타리 토큰이 뒤처진 쪽)는 최신 결과를 덮어쓰지 못한다.
- 재개는 저장된 **남은 예산**을 이어 쓴다(예산을 새로 주지 않는다).
- 전송 뒤 응답을 보존하지 못한 시도는 `unknown`으로 남고 성공으로 세지 않는다.

실제 모델·API 호출은 0회다. 준비된 응답 transport만 쓴다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.preview import jobs, pipeline, provider
from app.preview.contracts import RequestClass, RunMode
from app.preview.retry import BudgetLimits, RunBudget

from tests.preview.test_pipeline import _Reader, _fixture, _transport, _start

FIXED_NOW = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)


def test_resume_keeps_successful_results_and_does_not_rebuy_them(session_factory):
    """한 갈래가 실패해도 성공한 결과가 남고, 재개는 남은 예산으로 잇는다."""
    with session_factory() as session:
        first = _start(session, _transport())
        session.commit()

        # 첫 실행이 남긴 결과 수를 기록한다. 갈래 하나가 실패해도 0으로 돌아가면 안 된다.
        before = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results"
                " WHERE run_id = :run AND module_id IN ('R1','R2','R3')"
            ),
            {"run": str(first.run_id)},
        ).scalar()
        assert before >= 1, "조사 갈래 결과가 하나도 저장되지 않았다"

        state = jobs.load_state(session, first.run_id)
        assert state is not None
        used_before = int(state.budget_state.get("model_used") or 0)

        # 실행을 미완료 상태로 되돌리고 재개한다(프로세스 중단을 흉내낸다).
        jobs.set_active(session, run_id=first.run_id, active=True)
        session.execute(
            text(
                "UPDATE preview_dev.preview_pipeline_runs SET stage='R1'"
                " WHERE id = :run"
            ),
            {"run": str(first.run_id)},
        )
        session.execute(
            text(
                "UPDATE preview_dev.preview_runs SET status='running', finished_at=NULL"
                " WHERE id = :run"
            ),
            {"run": str(first.run_id)},
        )
        session.commit()

        resumed = pipeline.resume_preview_run(
            session,
            run_id=first.run_id,
            actor_id=7,
            transport=_transport(),
            reader=_Reader(),
        )
        session.commit()

        # 성공한 결과는 그대로 남아 있다(삭제·덮어쓰기 없음).
        after = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results"
                " WHERE run_id = :run AND module_id IN ('R1','R2','R3')"
            ),
            {"run": str(first.run_id)},
        ).scalar()
        assert after >= before
        assert resumed.resume_of_run_id == first.run_id
        # 재개는 저장된 예산을 이어 쓴다. 예산을 0으로 되돌리지 않는다.
        assert resumed.budget["model_used"] >= used_before


def test_stale_worker_cannot_overwrite_result(session_factory):
    """울타리 토큰이 뒤처진 실행자의 저장은 반영되지 않는다."""
    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()
        state = jobs.load_state(session, outcome.run_id)
        assert state is not None

        # 최신 소유자가 임차를 가져가 토큰을 올린다.
        new_token = pipeline.jobs.claim_lease(
            session, run_id=outcome.run_id, owner_id="newer-owner"
        )
        session.commit()
        assert new_token is not None
        stale_token = state.fencing_token
        assert stale_token != new_token

        # 오래된 실행자의 진행 저장은 거부된다.
        saved = jobs.save_progress(
            session,
            run_id=outcome.run_id,
            fencing_token=stale_token,
            stage="stale-write",
        )
        session.commit()
        assert saved is False, "오래된 실행자의 쓰기가 반영됐다"

        fresh = jobs.load_state(session, outcome.run_id)
        assert fresh.stage != "stale-write"

        # 오래된 실행자의 종료 확정도 거부된다.
        finished = jobs.finish_pipeline(
            session,
            run_id=outcome.run_id,
            fencing_token=stale_token,
            stage="stale-finish",
        )
        session.commit()
        assert finished is False


def test_unknown_attempt_outcome_is_preserved(session_factory):
    """전송 뒤 응답 보존 전 중단은 unknown으로 남고 성공으로 세지 않는다."""
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        ExecutionLimits,
        OperationKind,
    )
    from app.preview.retry import BudgetLimits

    class _UnknownTransport:
        provider = "recorded-model"
        mode = RunMode.MOCK
        request_class = RequestClass.MODEL

        def __init__(self) -> None:
            self.calls = []

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            # 요청은 나갔지만 응답을 보존하지 못한 상태.
            return provider.TransportResult(
                http_status=None,
                raw_request={"contents": "recorded"},
                raw_response=None,
                outcome_unknown=True,
                error_message="전송 뒤 응답을 받지 못했습니다.",
            )

    transport = _UnknownTransport()
    with session_factory() as session:
        from app.preview import store

        run_id = uuid.uuid4()
        context = ExecutionContext(
            run_id=run_id,
            operation_kind=OperationKind.PREVIEW,
            environment=Environment.DEV,
            mode=RunMode.MOCK,
            actor_id=7,
            config_version="mp10-test",
            limits=ExecutionLimits(model_requests=8, attempts_per_call=1),
        )
        store.store_run(session, context, label="unknown outcome 검사")
        session.commit()

        result = provider.request_model(
            logical_call_id="preview/unknown",
            contents=[{"role": "user", "parts": [{"text": "x"}]}],
            context=context,
            transport=transport,
            budget=RunBudget.for_run(BudgetLimits(attempts_per_call=1)),
            session=session,
            module_id="R1",
        )
        session.commit()

        assert result.response.outcome.value == "unknown"
        stored = session.execute(
            text(
                "SELECT outcome FROM preview_dev.preview_attempts"
                " WHERE run_id = :run AND logical_call_id = 'preview/unknown'"
                " ORDER BY attempt_ordinal"
            ),
            {"run": str(run_id)},
        ).scalars().all()
        assert stored == ["unknown"], stored


def test_resume_refuses_successful_run(session_factory):
    """성공으로 끝난 실행은 재개하지 않는다. 의도적 재실행은 새 ID를 쓴다."""
    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()
        # 이 실행은 성공으로 끝났다. 재개는 "미완료 실행을 잇는" 동작이므로 거부한다.
        assert outcome.status.value == "succeeded", outcome.status
        with pytest.raises(ValueError) as excinfo:
            pipeline.resume_preview_run(
                session,
                run_id=outcome.run_id,
                actor_id=7,
                transport=_transport(),
                reader=_Reader(),
            )
        session.rollback()
        assert "already finished" in str(excinfo.value)


def test_resynthesize_requires_selected_results(session_factory):
    """재종합은 선택한 결과 ID 없이는 실행하지 않는다."""
    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()
        with pytest.raises(ValueError):
            pipeline.resynthesize_preview(
                session,
                run_id=outcome.run_id,
                actor_id=7,
                selected_result_ids=(),
            )
        session.rollback()


def test_rerun_module_rejects_unknown_module(session_factory):
    """조사 모듈이 아닌 대상은 모듈 재실행 경로로 받지 않는다."""
    with session_factory() as session:
        outcome = _start(session, _transport())
        session.commit()
        with pytest.raises(ValueError):
            pipeline.rerun_module(
                session,
                run_id=outcome.run_id,
                module_id="S1",
                actor_id=7,
                transport=_transport(),
                reader=_Reader(),
            )
        session.rollback()


def test_resume_reuses_successful_research_without_new_calls(session_factory):
    """재개는 성공한 조사 갈래를 다시 호출하지 않는다(새 과금 0).

    첫 실행이 남긴 성공 결과를 그대로 입력으로 쓰고, 호출은 늘어나지 않아야 한다.
    이것이 "성공한 모듈 재호출 없음" 요구의 직접 증거다.
    """
    with session_factory() as session:
        first_transport = _transport()
        first = _start(session, first_transport)
        session.commit()
        first_calls = len(first_transport.calls)
        # 조사 4(R1·R2·R3·R4) + 종합 1 = 5.
        assert first_calls == 5, [c.logical_call_id for c in first_transport.calls]

        # 프로세스가 멈춘 상태를 흉내낸다: 실행은 미완료, 결과는 저장된 채로 남는다.
        jobs.set_active(session, run_id=first.run_id, active=True)
        session.execute(
            text(
                "UPDATE preview_dev.preview_runs SET status='running', finished_at=NULL"
                " WHERE id = :run"
            ),
            {"run": str(first.run_id)},
        )
        session.commit()

        resume_transport = _transport()
        pipeline.resume_preview_run(
            session,
            run_id=first.run_id,
            actor_id=7,
            transport=resume_transport,
            reader=_Reader(),
        )
        session.commit()

        # 성공한 조사 갈래는 다시 부르지 않는다. 이 기록 입력에서는 R1만 성공하므로
        # R1 호출은 재개 때 없어야 한다. 실패했던 R2/R3는 남은 예산으로 다시 시도한다.
        resumed_ids = [call.logical_call_id for call in resume_transport.calls]
        assert "R1-form" not in resumed_ids, f"성공한 R1을 다시 호출했다: {resumed_ids}"
        statuses = dict(
            session.execute(
                text(
                    "SELECT module_id, status FROM preview_dev.preview_results"
                    " WHERE run_id = :run AND module_id IN ('R1','R2','R3')"
                ),
                {"run": str(first.run_id)},
            ).all()
        )
        assert statuses["R1"] == "succeeded"

        # 저장된 조사 결과 행은 남아 있다(삭제·덮어쓰기 없음).
        stored = session.execute(
            text(
                "SELECT count(*) FROM preview_dev.preview_results"
                " WHERE run_id = :run AND module_id IN ('R1','R2','R3')"
            ),
            {"run": str(first.run_id)},
        ).scalar()
        assert stored == 3
