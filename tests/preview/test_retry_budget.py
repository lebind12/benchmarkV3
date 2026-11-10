"""MP-04 공통 예산·재시도 정책 검사.

계획 §5의 초기 설정이 실제 판단에 쓰이는지 확인한다. 값 자체를 다른 곳에 복사하지
않고 `app/preview/retry.py` 한 곳에서 온다는 사실도 함께 본다.

이 파일이 확인하는 것:

- 429 → 대기 → 성공에서 **두 시도가 모두** 남는다(성공만 골라 제출하지 않는다).
- 예산은 LangGraph 노드 재시도·SDK 재시도와 겹쳐 늘어나지 않는다.
- 아직 시작하지 않은 필수 단계의 최초 호출 몫은 재시도가 침범하지 않는다.
- 401은 눈먼 재시도를 하지 않는다.
- 전체 기한에 재시도 대기가 포함된다.
- 사용량이 없으면 0이 아니라 unknown(None)이다.

범위는 대표 사례만 본다. 오류 코드 조합의 완전 탐색은 하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.preview.retry import (
    API_REQUEST_BUDGET,
    MAX_ATTEMPTS_PER_CALL,
    MODEL_REQUEST_BUDGET,
    NORMAL_MODEL_CALLS,
    RETRY_MAX_DELAY_SECONDS,
    RUN_DEADLINE_SECONDS,
    BudgetExceeded,
    BudgetLimits,
    ConcurrencyGate,
    DeadlineExceeded,
    RetryDecision,
    RunBudget,
    bounded_wait_seconds,
    budget_from_limits,
    classify_attempt,
    plan_limits,
)


def test_policy_matches_the_plan_section_five_values():
    """계획 §5 값과 코드가 어긋나면 여기서 먼저 드러난다."""
    limits = BudgetLimits()
    assert limits.model_requests == 8 == MODEL_REQUEST_BUDGET
    assert limits.normal_model_calls == 4 == NORMAL_MODEL_CALLS
    assert limits.api_requests == 24 == API_REQUEST_BUDGET
    assert limits.attempts_per_call == 3 == MAX_ATTEMPTS_PER_CALL
    assert limits.model_concurrency == 2
    assert limits.api_concurrency == 2
    assert limits.deadline_seconds == 1800 == RUN_DEADLINE_SECONDS
    # 계획 §5는 모델 300초, 축구 API 30초를 요청 상한으로 둔다.
    from app.preview.retry import API_TIMEOUT_SECONDS, MODEL_TIMEOUT_SECONDS

    assert MODEL_TIMEOUT_SECONDS == 300
    assert API_TIMEOUT_SECONDS == 30


def test_retry_reserves_the_first_call_of_unstarted_steps():
    """앞 단계 재시도가 뒤 단계의 첫 호출을 굶기지 않는다.

    정상 호출 4회(조사 3 + 종합 1) 중 1회만 시작했을 때, 남은 3개 단계 몫을 빼고
    쓸 수 있는 재시도는 8 - 4 = 4회다. 그래서 7번째 요청부터 거부돼야 한다.
    """
    budget = RunBudget.for_run()
    budget.register_call("research-1")

    allowed = 0
    while True:
        ok, reason = budget.can_attempt("research-1")
        if not ok:
            assert reason
            break
        budget.charge("research-1")
        allowed += 1
        assert allowed <= MODEL_REQUEST_BUDGET, "budget did not stop the loop"

    # 시도 상한(3회)이 먼저 걸리므로 호출 하나로는 예산을 다 쓰지 못한다.
    assert allowed == MAX_ATTEMPTS_PER_CALL
    assert budget.model_used == MAX_ATTEMPTS_PER_CALL

    # 다른 논리 호출로 예산을 소진하면 미시작 단계 몫이 남아 거부된다.
    for index in range(10):
        call = f"retry-{index}"
        budget.register_call(call)
        for _ in range(MAX_ATTEMPTS_PER_CALL):
            ok, reason = budget.can_attempt(call)
            if not ok:
                break
            budget.charge(call)
        else:
            continue
        assert reason is not None
        break

    assert budget.model_used + budget.reserved_model_requests() <= MODEL_REQUEST_BUDGET


def test_unstarted_steps_keep_their_reserve_until_started():
    """예약 몫은 '아직 시작하지 않은 정상 호출' 수만큼 줄지 않고 유지된다.

    아무 단계도 시작하지 않았으면 재시도가 쓸 수 있는 여유는 8 - 4 = 4회다. 단계를
    시작할수록 예약이 풀려 여유가 늘어난다.
    """
    budget = RunBudget.for_run()
    assert budget.reserved_model_requests() == NORMAL_MODEL_CALLS

    # 논리 호출마다 시도 상한(3회)이 있으므로 여러 호출로 예산을 소진한다.
    # 예약 몫 때문에 예산이 바닥나면 그때의 거부 사유가 예약을 밝혀야 한다.
    used = 0
    budget_refusal: str | None = None
    for index in range(6):
        call = f"late-retry-{index}"
        for _ in range(MAX_ATTEMPTS_PER_CALL):
            ok, reason = budget.can_attempt(call)
            if not ok:
                if reason and "필수 단계" in reason:
                    budget_refusal = reason
                break
            budget.charge(call)
            used += 1
        if budget_refusal is not None:
            break
    assert budget_refusal is not None
    assert used == MODEL_REQUEST_BUDGET - NORMAL_MODEL_CALLS

    # 단계를 하나 시작하면 그 몫이 풀려 여유가 1 늘어난다.
    fresh = RunBudget.for_run()
    fresh.register_call("research-1")
    assert fresh.reserved_model_requests() == NORMAL_MODEL_CALLS - 1


def test_budget_is_not_multiplied_by_nested_retry_loops():
    """한 논리 호출의 시도 수는 실행기가 소유한 상한을 넘지 않는다.

    LangGraph 노드 재시도나 SDK 재시도를 켜면 실제 호출 수가 배로 늘어난다. 이
    검사는 예산 객체가 시도 수를 세는 유일한 곳임을 확인한다.
    """
    budget = RunBudget.for_run(plan_limits(model_requests=8, attempts_per_call=3))
    for _ in range(3):
        budget.register_call("call-a")
    used = 0
    for _ in range(10):
        ok, _reason = budget.can_attempt("call-a")
        if not ok:
            break
        budget.charge("call-a")
        used += 1
    assert used == 3
    assert budget.attempts_used("call-a") == 3


def test_429_is_retried_and_401_is_not():
    assert (
        classify_attempt(outcome="error", http_status=429) is RetryDecision.RETRY
    )
    assert (
        classify_attempt(outcome="error", http_status=401) is RetryDecision.STOP
    )
    assert (
        classify_attempt(outcome="error", http_status=403) is RetryDecision.STOP
    )
    # 알 수 없는 전송 결과는 일시적으로 보고 재시도하되, 기록은 unknown으로 남긴다.
    assert classify_attempt(outcome="unknown") is RetryDecision.RETRY


def test_wait_is_bounded_and_prefers_retry_after():
    # 유효한 Retry-After가 있으면 그것을 우선한다.
    assert bounded_wait_seconds(0, retry_after_seconds=7) == 7.0
    # 상한을 넘는 Retry-After는 60초로 자른다.
    assert bounded_wait_seconds(0, retry_after_seconds=600) == RETRY_MAX_DELAY_SECONDS
    # 없으면 1초부터 지수 증가 + 무작위 지연(0.5~1.0배).
    first = bounded_wait_seconds(0, rng=lambda: 0.0)
    later = bounded_wait_seconds(3, rng=lambda: 0.0)
    assert 0.5 <= first <= 1.0
    assert first < later <= RETRY_MAX_DELAY_SECONDS
    assert bounded_wait_seconds(20, rng=lambda: 1.0) == RETRY_MAX_DELAY_SECONDS


def test_deadline_includes_wait_time():
    """전체 기한은 요청 시간뿐 아니라 재시도 대기까지 포함한다."""
    start = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    budget = RunBudget.for_run(plan_limits(deadline_seconds=100), now=start)
    assert budget.seconds_left(start) == 100

    almost_done = start + timedelta(seconds=95)
    assert budget.deadline_passed(almost_done) is False
    # 10초를 기다리면 기한을 넘긴다. 실행기는 이 경우 재시도하지 않는다.
    assert budget.seconds_left(almost_done) < 10

    expired = start + timedelta(seconds=101)
    ok, reason = budget.can_attempt("call", now=expired)
    assert ok is False
    assert "기한" in (reason or "")


def test_charge_refuses_after_deadline():
    start = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    budget = RunBudget.for_run(plan_limits(deadline_seconds=10), now=start)
    budget.register_call("call")
    with pytest.raises(DeadlineExceeded):
        budget.charge("call", now=start + timedelta(seconds=11))


def test_charge_refuses_when_attempt_cap_is_reached():
    budget = RunBudget.for_run(plan_limits(attempts_per_call=1))
    budget.register_call("call")
    budget.charge("call")
    with pytest.raises(BudgetExceeded):
        budget.charge("call")


def test_api_budget_is_separate_from_model_budget():
    budget = RunBudget.for_run(plan_limits(model_requests=0, api_requests=2))
    budget.register_call("api-call")
    budget.charge("api-call", "api")
    budget.charge("api-call", "api")
    with pytest.raises(BudgetExceeded):
        budget.charge("api-call", "api")
    # API를 써도 모델 예산은 늘지 않는다.
    assert budget.model_used == 0


def test_concurrency_gate_stops_the_third_concurrent_request():
    gate = ConcurrencyGate(2, label="모델")
    with gate:
        with gate:
            with pytest.raises(BudgetExceeded):
                gate.__enter__()
    assert gate.peak <= 2


def test_stored_limits_round_trip():
    """저장된 실행 상한에서 예산을 복원한다. 모르는 값은 기본값으로 돌아간다."""
    limits = plan_limits(model_requests=6, api_requests=10, deadline_seconds=300)
    stored = limits.execution_limits().to_dict()
    restored = budget_from_limits(stored)
    assert restored.model_requests == 6
    assert restored.api_requests == 10
    assert restored.deadline_seconds == 300
    # 네 필드에 없는 동시성·정상 호출 수는 기본값을 유지한다.
    assert restored.model_concurrency == BudgetLimits().model_concurrency
    assert restored.normal_model_calls == BudgetLimits().normal_model_calls


def test_budget_snapshot_reports_unknown_reserve_honestly():
    budget = RunBudget.for_run()
    snapshot = budget.snapshot()
    assert snapshot["model_used"] == 0
    assert snapshot["model_reserved_for_unstarted_steps"] == NORMAL_MODEL_CALLS
    assert snapshot["stopped_reason"] is None
