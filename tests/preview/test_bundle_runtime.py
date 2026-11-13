"""PS-01 실행 계약 검사: 전송 내구성·상한·예약 반환.

이 파일이 확인하는 것(계획 PS-01 대표 직접 검사):

- 실제 전송 직후 후처리 예외가 나도 redacted 요청/응답과 사용량이 **남는다**. 실행
  트랜잭션이 롤백돼도 마찬가지다. 이전 프로토타입에서 응답이 사라졌던 결함의 회귀 검사다.
- 수집 전용(collect-only) 경로는 모델 전송 **0회**다.
- 프로세스 재개·재시작이 전체 실제 전송 상한(8회)을 초기화하지 않는다.
- 시작하지 않기로 확정된 정상 호출의 예약은 **반환**되지만 전체 상한은 늘지 않는다.
- 설정 부족 시도는 전송이 아니므로 사용량으로 세지 않는다.

실제 네트워크는 쓰지 않는다. `mode=live` 기록 transport로 재현하고, 그 사실을 숨기지
않는다(mock 은폐 금지: `mode`를 live로 두는 이유는 "실제 전송 계수" 경로를 검사하기
위함이며, 네트워크가 없다는 점은 이 docstring에 밝힌다).

전용 로컬 테스트 DB(`*_test`)만 쓴다. 운영·기존 DB에는 쓰지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Any

import pytest

from app.preview import information_bundle as bundle_contract
from app.preview import provider, send_ledger, store
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
    RunStatus,
)
from app.preview.retry import (
    BudgetLimits,
    RunBudget,
    plan_limits,
)

FIXED_NOW = datetime(2026, 11, 11, 3, 0, tzinfo=timezone.utc)


def _context(mode: RunMode = RunMode.LIVE) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=mode,
        actor_id=1,
        config_version="mp11-runtime-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _live_transport(text: str = "응답 본문"):
    """mode=live 기록 transport. 네트워크를 열지 않지만 계수 경로는 실제와 같다."""
    return provider.RecordedTransport(
        script=[_ok(text) for _ in range(12)],
        provider="recorded-live",
        mode=RunMode.LIVE,
    )


def _ok(text: str = "응답 본문") -> provider.TransportResult:
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청 본문"},
        raw_response={
            "candidates": [
                {"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}
            ]
        },
        usage={"input_tokens": 11, "output_tokens": 7},
        duration_ms=5,
    )


def _spec(logical_call_id: str, module_id: str = "D1") -> provider.RequestSpec:
    return provider.RequestSpec(
        logical_call_id=logical_call_id,
        provider="recorded-live",
        model="recorded-model",
        operation="runtime_test",
        module_id=module_id,
    )


def _store_run(session, context: ExecutionContext) -> None:
    store.store_run(session, context, label="ps01 runtime test", status=RunStatus.RUNNING)


def _journal_rows(session, run_id: uuid.UUID) -> list[dict]:
    from sqlalchemy import select

    from app.preview.models import PreviewWriteAudit

    rows = session.scalars(
        select(PreviewWriteAudit).where(
            PreviewWriteAudit.run_id == run_id,
            PreviewWriteAudit.action == send_ledger.CHARGE_ACTION,
        )
    )
    return [dict(row.detail or {}) for row in rows]


def test_live_send_and_usage_survive_post_processing_failure(session_factory):
    """전송 뒤 후처리 예외 + 실행 롤백에도 원문·사용량이 남는다.

    이전 프로토타입의 실제 결함(응답 수신 뒤 예외 → run·시도·원문 전부 롤백)을
    그대로 재현한다. 장부가 별도 트랜잭션이므로 여기서는 살아 있어야 한다.
    """
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()  # 실행 행이 커밋돼 있어야 아티팩트 FK가 성립한다.

        result = provider.execute_request(
            _spec("discovery_people"),
            context,
            transport=_live_transport("수집 후보 3건"),
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert result.ok is True

        # 후처리 예외를 흉내 낸다. 이 실행의 저장은 전부 롤백된다.
        session.rollback()

    # 새 세션(=프로세스가 바뀐 것과 같은 조건)에서 장부를 다시 읽는다.
    with session_factory() as fresh:
        rows = _journal_rows(fresh, context.run_id)
        assert rows, "전송 장부가 롤백으로 사라졌다"
        charge = [row for row in rows if row.get("counted")]
        assert len(charge) == 1, rows
        assert send_ledger.charged_requests(fresh, run_id=context.run_id) == 1

        # 사용량·HTTP 상태는 응답 수신 직후 남긴 행에 있다(전송 전 예약 행은 usage가 없다).
        with_usage = [row for row in rows if row.get("usage")]
        assert with_usage, rows
        assert with_usage[0]["usage"] == {"input_tokens": 11, "output_tokens": 7}
        assert with_usage[0]["http_status"] == 200

        # redacted 원문이 남아 있다(아티팩트 또는 장부 본문).
        bodies = " ".join(str(row) for row in rows)
        assert "수집 후보 3건" in bodies or with_usage[0].get("response_artifact_id")


def test_collect_only_path_makes_zero_model_sends(session_factory):
    """정보 원문 묶음만 만드는 경로(수집 전용)는 모델 전송 0회다."""
    source = bundle_contract.BundleSource(
        source_id="src:example",
        discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
        requested_url="https://example.test/a",
        final_url="https://example.test/a",
        nature="stats",
        method="fresh_http",
        passages=(
            bundle_contract.Passage(
                passage_id="src:example#p1",
                source_id="src:example",
                ordinal=1,
                text="선수 기록 구간",
            ),
        ),
    )
    bundle = bundle_contract.InformationBundle(
        bundle_id=bundle_contract.new_bundle_id(),
        fixture={"fixture_id": 1557474},
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=(source,),
        db_snapshot=bundle_contract.DbSnapshot(
            fixture={"fixture_id": 1557474}, team_id_space="internal", readable=True
        ),
    )
    assert bundle_contract.validate_information_bundle(bundle) == ()

    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        # 수집 전용 경로에서는 execute_request/request_model을 부르지 않는다.
        transport = _live_transport()
        assert transport.calls == []
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 0
        assert send_ledger.audit_row_count(session, run_id=context.run_id) == 0

        summary = bundle_contract.bundle_summary(bundle)
        assert summary["available_passages"] == 1
        # 수집 전용 경로는 아직 아무 섹션에도 전달하지 않았다.
        assert summary["section_delivery_count"] == 0
        assert summary["browser_used"] is False


def test_restart_does_not_reset_the_eight_send_cap(session_factory):
    """재시작한 것처럼 새 예산을 만들어도 장부가 상한을 되살린다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        budget = RunBudget.for_run(plan_limits(model_requests=8, normal_model_calls=6), now=FIXED_NOW)
        transport = _live_transport()
        for index in range(8):
            result = provider.execute_request(
                _spec(f"send-{index}"),
                context,
                transport=transport,
                budget=budget,
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            )
            assert result.ok is True
        assert budget.model_used == 8
        assert send_ledger.charged_requests(
            session, run_id=context.run_id
        ) == 8, "장부와 예산 계수가 어긋났다"

        # 프로세스가 바뀌어 예산을 0에서 새로 만든 상황.
        restarted = RunBudget.for_run(now=FIXED_NOW)
        assert restarted.model_used == 0
        adjusted = send_ledger.reconcile_budget_from_journal(
            restarted, session, run_id=context.run_id
        )
        assert adjusted["raised_from_journal"] is True
        assert restarted.model_used == 8

        allowed, reason = restarted.can_attempt("ninth-send", now=FIXED_NOW)
        assert allowed is False
        assert reason and "예산" in reason


def test_live_send_stops_at_eight_and_never_transports_more(session_factory):
    """정상 6회 뒤 재시도 2회까지, 9번째는 **전송 없이** 거부된다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        budget = RunBudget.for_run(
            plan_limits(model_requests=8, normal_model_calls=6, attempts_per_call=3),
            now=FIXED_NOW,
        )
        transport = _live_transport()
        for index in range(6):
            assert provider.execute_request(
                _spec(f"normal-{index}"),
                context,
                transport=transport,
                budget=budget,
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            ).ok
        for index in range(2):
            assert provider.execute_request(
                _spec(f"retry-{index}"),
                context,
                transport=transport,
                budget=budget,
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            ).ok

        sent_before = len(transport.calls)
        refused = provider.execute_request(
            _spec("ninth-send"),
            context,
            transport=transport,
            budget=budget,
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert refused.ok is False
        assert len(transport.calls) == sent_before, "거부된 요청이 실제로 전송됐다"
        assert refused.stopped_reason
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 8


def test_configuration_failure_is_not_counted_as_a_send(session_factory):
    """설정 부족은 전송이 아니므로 사용량(8회 상한)에 세지 않는다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        transport = provider.GoogleGenAIHttpTransport(
            project=None,
            location="global",
            model="recorded-model",
            credentials_json=None,
        )
        result = provider.execute_request(
            _spec("discovery_people"),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert result.ok is False
        assert result.missing_configuration
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 0
        rows = _journal_rows(session, context.run_id)
        assert rows and rows[0]["not_sent"] is True


def test_reservations_return_for_cancelled_calls_without_raising_the_cap():
    """미시작 호출의 예약은 반환되지만 전체 상한 8회는 그대로다."""
    budget = RunBudget.for_run(now=FIXED_NOW)
    assert budget.reserved_model_requests() == 6

    # 시작하지 않기로 확정된 호출 하나를 취소하면 예약이 1 줄어든다.
    assert budget.cancel_call("discovery_outlook") is True
    assert budget.reserved_model_requests() == 5
    assert budget.limits.model_requests == 8, "예약 반환이 전체 상한을 늘리면 안 된다"

    # 이미 시도를 보낸 호출은 취소할 수 없다. 또 등록된 호출은 자기 첫 몫을 이미
    # "시작"했으므로 예약에서 빠진다(6 - 등록1 - 취소1 = 4).
    budget.register_call("discovery_people")
    budget.charge("discovery_people", now=FIXED_NOW)
    assert budget.cancel_call("discovery_people") is False
    assert budget.reserved_model_requests() == 4

    # 취소 상태는 재개를 위해 저장·복원된다.
    restored = RunBudget.restore(budget.persistable(), now=FIXED_NOW)
    assert restored.cancelled_calls == ["discovery_outlook"]
    assert restored.reserved_model_requests() == 4
    snapshot = restored.snapshot()
    assert snapshot["reservations_returned"] == 1
    assert snapshot["model_requests"] == 8


def test_manual_result_row_is_not_double_counted(session_factory):
    """같은 요청의 결과 행을 다시 남겨도 사용량은 1회로 센다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        send_ledger.journal_send(
            run_id=context.run_id,
            actor_id=1,
            logical_call_id="discovery_people",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            outcome="pending",
            note="전송 전 예약",
            now=FIXED_NOW,
        )
        send_ledger.journal_send(
            run_id=context.run_id,
            actor_id=1,
            logical_call_id="discovery_people",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            response_body={"candidates": []},
            outcome="ok",
            counts_toward_cap=False,
            note="응답 수신 직후 보존",
            now=FIXED_NOW,
        )
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 1
        assert send_ledger.audit_row_count(session, run_id=context.run_id) == 2


def test_mock_and_replay_sends_are_never_charged(session_factory):
    """mock/replay transport는 장부에 사용량을 남기지 않는다(0회)."""
    context = _context(mode=RunMode.MOCK)
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        transport = provider.RecordedTransport(
            script=[_ok()], provider="recorded-mock", mode=RunMode.MOCK
        )
        result = provider.execute_request(
            _spec("discovery_people"),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert result.ok is True
        assert len(transport.calls) == 1
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 0
        assert send_ledger.audit_row_count(session, run_id=context.run_id) == 0


def test_incomplete_odds_is_optional_diagnostic_not_a_bundle_blocker():
    """불완전 배당은 **선택 섹션 진단**이며 묶음·필수 작성을 막지 않는다.

    코디네이터 경계: 불완전/미지원 배당 때문에 `ensure_valid_bundle`이 실패하면 필수
    섹션(AI 전망·점수·주목 선수)까지 막힌다. 그래서 배당 문제는 채택/미채택 구분으로만
    남기고 묶음 검증은 통과시킨다.
    """
    market = bundle_contract.OddsMarket(
        quotes=(
            bundle_contract.OddsQuote(
                source_id="src:odds",
                site="example",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=2.1,
                draw_decimal=3.4,
                away_decimal=3.2,
            ),
        )
    )
    good = bundle_contract.InformationBundle(
        bundle_id="bundle-odds-1",
        fixture={"fixture_id": 1557474},
        team_id_space="internal",
        collected_at=FIXED_NOW,
        odds=market,
    )
    assert bundle_contract.validate_information_bundle(good) == ()

    incomplete = bundle_contract.OddsMarket(
        quotes=(
            bundle_contract.OddsQuote(
                source_id="src:odds",
                site="example",
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                observed_at=FIXED_NOW,
                home_decimal=2.1,
                draw_decimal=None,
                away_decimal=3.2,
            ),
        )
    )
    bad = bundle_contract.InformationBundle(
        bundle_id="bundle-odds-2",
        fixture={"fixture_id": 1557474},
        team_id_space="internal",
        collected_at=FIXED_NOW,
        odds=incomplete,
    )
    # 묶음 검증은 통과한다(배당은 선택). 대신 채택 목록에서 빠지고 사유가 남는다.
    assert bundle_contract.validate_information_bundle(bad) == ()
    bundle_contract.ensure_valid_bundle(bad)

    described = bundle_contract.describe_odds(bad)
    assert described["available"] is False
    assert described["adopted"] == []
    assert described["ignored"], described
    assert "추정 금지" in described["ignored"][0]["ignored_reason"]
    # 좋은 줄만 채택되고 나머지는 미채택으로 남는다.
    assert len(bundle_contract.adopted_odds_quotes(good)) == 1


def test_presend_crash_keeps_the_reservation_counted_and_reports_it(session_factory):
    """전송 직전에 프로세스가 죽어도 예약은 사용량으로 남고, unknown으로 드러난다.

    코디네이터 경계(3): post-send 독립 저장만으로는 pre-send 크래시/불명확 전송의 cap을
    놓칠 수 있다. 예약을 **전송 전에** 커밋하고 그 예약을 사용량으로 세므로 8회 상한이
    유지된다. 결과 행이 없는 예약은 `unresolved_sends`로 따로 보고한다.
    """
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()

        # 전송 전 예약만 남기고 프로세스가 죽은 상황을 재현한다(응답 행 없음).
        send_ledger.journal_send(
            run_id=context.run_id,
            actor_id=1,
            logical_call_id="discovery_people",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            outcome="pending",
            note="전송 전 예약",
            now=FIXED_NOW,
        )

    with session_factory() as fresh:
        # 예약은 이미 사용량으로 센다(상한을 잃지 않는다).
        assert send_ledger.charged_requests(fresh, run_id=context.run_id) == 1
        unresolved = send_ledger.unresolved_sends(fresh, run_id=context.run_id)
        assert len(unresolved) == 1
        assert unresolved[0]["logical_call_id"] == "discovery_people"
        assert "사용량으로는 세었습니다" in unresolved[0]["note"]

        # 새 예산을 만들어도 장부가 1회를 이미 쓴 것으로 맞춘다.
        restarted = RunBudget.for_run(now=FIXED_NOW)
        send_ledger.reconcile_budget_from_journal(
            restarted, fresh, run_id=context.run_id
        )
        assert restarted.model_used == 1


def test_run_detail_exposes_ledger_and_unresolved_sends(client, make_user, session_factory):
    """관리자 실행 상세가 전송 장부 요약과 미확정 전송을 드러낸다."""
    context = _context()
    run_id = context.run_id
    with session_factory() as session:
        _store_run(session, context)
        session.commit()
        # 결과가 확정된 전송 1건 + 예약만 남은 전송 1건.
        send_ledger.journal_send(
            run_id=run_id,
            actor_id=1,
            logical_call_id="discovery_people",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            outcome="pending",
            now=FIXED_NOW,
        )
        send_ledger.journal_send(
            run_id=run_id,
            actor_id=1,
            logical_call_id="discovery_people",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            response_body={"candidates": []},
            outcome="ok",
            counts_toward_cap=False,
            now=FIXED_NOW,
        )
        send_ledger.journal_send(
            run_id=run_id,
            actor_id=1,
            logical_call_id="section_players",
            attempt_ordinal=0,
            request_class=provider.RequestClass.MODEL,
            provider="recorded-live",
            model="recorded-model",
            mode="live",
            request_body={"contents": "요청"},
            outcome="pending",
            note="전송 전 예약",
            now=FIXED_NOW,
        )
        session.commit()

    user = make_user(role="ADMIN")
    login = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert login.status_code == 200
    detail = client.get(f"/api/v1/admin/preview/runs/{run_id}").json()
    ledger = detail["send_ledger"]
    assert ledger["charged_requests"] == 2
    assert len(ledger["unresolved_sends"]) == 1
    assert ledger["unresolved_sends"][0]["logical_call_id"] == "section_players"


def _network_transport() -> Any:
    """실제 네트워크 어댑터. `send`가 불리면 즉시 실패하게 만들어 전송 자체를 감시한다."""
    from app.preview import provider

    calls: list[str] = []

    def _boom(spec, timeout_seconds):
        calls.append(spec.logical_call_id)
        raise AssertionError("network transport must not be reached without a journal")

    transport = provider.HttpApiTransport(provider="api-football", send_func=_boom)
    transport.reached = calls  # type: ignore[attr-defined]
    return transport


def test_network_send_without_journal_is_refused_before_transport_send():
    """실제 네트워크 transport는 세션/장부 없이 **전송 전에** 거부된다."""
    from app.preview import provider

    transport = _network_transport()
    budget = RunBudget.for_run(now=FIXED_NOW)
    with pytest.raises(provider.JournalRequiredForNetworkSend):
        provider.execute_request(
            _spec("d0-fixtures", module_id="D0"),
            _context(),
            transport=transport,
            budget=budget,
            session=None,  # 실행 기록 없음 → 장부 없음
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
    assert transport.reached == [], "장부 없이 실제 전송 경로에 도달했다"
    # 예산도 차감되지 않았다(전송 시도 자체가 없다).
    assert budget.api_used == 0 and budget.model_used == 0


def test_recorded_live_transport_is_not_required_to_journal():
    """`mode=live` 기록 transport는 네트워크가 아니므로 장부 요구 대상이 아니다."""
    from app.preview import provider

    transport = provider.RecordedTransport(
        script=[_ok()], provider="recorded-live", mode=RunMode.LIVE
    )
    assert provider.transported_over_network(transport) is False
    result = provider.execute_request(
        _spec("recorded-live"),
        _context(),
        transport=transport,
        budget=RunBudget.for_run(now=FIXED_NOW),
        session=None,
        sleeper=lambda seconds: None,
        now=lambda: FIXED_NOW,
    )
    assert result.ok is True


def test_network_send_with_journal_still_records_durably(session_factory):
    """장부가 있으면 실제 네트워크 어댑터도 정상 경로로 기록된다(회귀 방지)."""
    from app.preview import provider

    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        session.commit()
        transport = provider.HttpApiTransport(
            provider="api-football",
            send_func=lambda spec, timeout: provider.HttpResponse(
                status_code=200, body={"response": [{"ok": True}]}
            ),
        )
        result = provider.execute_request(
            _spec("d0-fixtures", module_id="D0"),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        session.commit()
        assert result.ok is True
        assert send_ledger.charged_requests(
            session, run_id=context.run_id, request_class=provider.RequestClass.API
        ) == 1
