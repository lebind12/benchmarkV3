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
    HTTP_LOCAL_SHARE,
    HTTP_OWNER_ARTICLES,
    HTTP_OWNER_ODDS,
    HTTP_TOTAL_LIMIT,
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
    """계획 값과 코드가 어긋나면 여기서 먼저 드러난다.

    2026-11-11 확정 설계가 정상 경로를 **조사 2 + 작성 3 + 최종 전망 1 = 6회**로
    명시 변경했다. 전체 실제 전송 상한 8회는 그대로이며, 재시도 여유만 2회다.
    """
    limits = BudgetLimits()
    assert limits.model_requests == 8 == MODEL_REQUEST_BUDGET
    assert limits.normal_model_calls == 6 == NORMAL_MODEL_CALLS
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


# --------------------------------------------------------------------------
# 사용자 확정 2026-11-12: 한 생성 실행의 **각 논리 모듈 최초 포함 3회**
# --------------------------------------------------------------------------
#
# 이것이 확인하는 것:
#
# - 여섯 모듈이 각각 3회를 다 써도 다른 모듈이나 전체 8회가 막지 않는다.
# - 어느 모듈이든 4번째 전송은 나가지 않는다.
# - 경기 B는 경기 A의 계수에 막히지 않는다(실행이 다르면 새 3회).
# - 같은 실행 복구는 장부에 남은 사용분을 **유지**한다(0으로 초기화하지 않는다).
# - 집계 설명(6×3=18)은 공용 여유 예산이 아니다.

FIXED_NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)

SIX_MODULES = (
    "discovery_people",
    "discovery_outlook",
    "section_players",
    "section_availability",
    "section_outlook",
    "section_ai_forecast",
)


def _generation_budget(prior=None):
    from app.preview.retry import RunBudget

    return RunBudget.for_generation(SIX_MODULES, prior_module_usage=prior, now=FIXED_NOW)


def test_each_of_the_six_modules_can_use_three_sends_without_starving_others():
    """여섯 모듈이 각각 3회를 다 써도 서로를 막지 않는다(전체 8회 병목 없음)."""
    budget = _generation_budget()

    for module in SIX_MODULES:
        for _ in range(3):
            allowed, reason = budget.can_attempt(module)
            assert allowed, (module, reason)
            budget.charge(module)

    assert budget.model_used == 18
    # 파생 상한은 모듈 수 × 3이며, 옛 8회 상한이 병목이 되지 않는다.
    assert budget.effective_model_requests() == 18


def test_no_module_sends_a_fourth_time_even_when_others_are_exhausted():
    """어느 모듈이든 4번째 전송은 거부된다. 다른 모듈이 남아 있어도 마찬가지다."""
    budget = _generation_budget()
    for _ in range(3):
        budget.charge("section_players")

    # 다른 모듈은 아직 여유가 있다.
    assert budget.can_attempt("section_outlook")[0] is True

    allowed, reason = budget.can_attempt("section_players")
    assert allowed is False
    assert reason and "상한" in reason
    with pytest.raises(BudgetExceeded):
        budget.charge("section_players")
    # 4번째 시도는 세지 않았다.
    assert budget.module_total("section_players") == 3


def test_another_fixture_has_its_own_three_sends():
    """경기 B는 경기 A의 계수에 막히지 않는다. 실행이 다르면 새 3회다."""
    fixture_a = _generation_budget()
    for module in SIX_MODULES:
        for _ in range(3):
            fixture_a.charge(module)
    assert fixture_a.can_attempt("section_players")[0] is False

    # 별도 생성 실행(다른 경기)은 자기 3회를 새로 갖는다.
    fixture_b = _generation_budget()
    allowed, reason = fixture_b.can_attempt("section_players")
    assert allowed, reason
    fixture_b.charge("section_players")
    assert fixture_b.module_total("section_players") == 1


def test_previous_trial_usage_is_reported_but_does_not_block():
    """이전 시험 집합의 사용량은 표시용이며 상한에서 차감하지 않는다."""
    budget = _generation_budget(prior={module: 3 for module in SIX_MODULES})

    for module in SIX_MODULES:
        allowed, reason = budget.can_attempt(module)
        assert allowed, (module, reason)
        budget.charge(module)

    # 과거 값은 남아 있지만 이번 실행 계수와 합산되지 않는다.
    assert budget.module_prior_total("section_players") == 3
    assert budget.module_total("section_players") == 1
    snapshot = budget.snapshot()
    assert snapshot["prior_module_usage"]["section_players"] == 3
    assert snapshot["sent_by_module"]["section_players"] == 1


def test_recovery_keeps_the_usage_already_charged():
    """같은 실행 복구는 장부의 사용분을 유지한다(새 run으로 0이 되지 않는다)."""
    from app.preview.retry import RunBudget

    started = _generation_budget()
    for _ in range(2):
        started.charge("section_players")

    resumed = RunBudget.restore(started.persistable(), now=FIXED_NOW)
    assert resumed.module_total("section_players") == 2
    # 남은 한 번만 보낼 수 있다.
    allowed, _reason = resumed.can_attempt("section_players")
    assert allowed is True
    resumed.charge("section_players")
    assert resumed.can_attempt("section_players")[0] is False
    assert resumed.module_total("section_players") == 3


def test_eighteen_is_an_arithmetic_description_not_a_shared_budget():
    """18은 가능한 전송 수의 설명이며, 한 모듈이 남의 여유를 가져다 쓰는 정책이 아니다."""
    budget = _generation_budget()
    for _ in range(3):
        budget.charge("section_players")

    # 남은 모듈 몫(15)은 다른 모듈 것으로 남아 있고, 이미 3회를 쓴 모듈은 쓸 수 없다.
    assert budget.remaining() == 15
    assert budget.can_attempt("section_players")[0] is False


def test_generation_policy_does_not_enforce_the_global_deadline():
    """전역 1800초는 새 생성 경로의 독립 중단 기준이 아니다(요청별 300초는 유지)."""
    budget = _generation_budget()
    assert budget.deadline_enforced is False
    # 남은 기한은 '무제한'으로 보고되어, 요청별 타임아웃을 깎지 않는다.
    assert budget.seconds_left(FIXED_NOW) == float("inf")
    assert budget.snapshot()["seconds_left"] is None

    # 한참 뒤에도 모듈 재시도는 계속 허용된다.
    late = FIXED_NOW + timedelta(seconds=10_000)
    allowed, reason = budget.can_attempt("section_players", now=late)
    assert allowed, reason


# --- HTTP 로직별 보호 몫 (사용자 확정 2026-11-19: 각 10, 공유 10, 총 30) ---------


def _http_budget():
    """bundle 생성 경로와 같은 예산(보호 몫 정책 켜짐)."""
    return RunBudget.for_generation(("section_odds",), now=FIXED_NOW)


def test_articles_exhausting_their_share_leaves_ten_for_odds():
    """기사 20회를 다 써도 배당이 10회를 쓸 수 있다.

    검사 이유(실패 시 사용자 영향): 이전에는 기사 수집이 단일 24회 예산을 다 먹으면
    배당 읽기가 아예 나가지 못해 배당 섹션이 비었다(2026-11-19 실제 실행에서 관측).
    """
    budget = _http_budget()
    articles = sum(1 for _ in range(50) if budget.http_charge(HTTP_OWNER_ARTICLES)[0])

    assert articles == HTTP_LOCAL_SHARE * 2  # 보호 10 + 공유 10
    assert budget.http_remaining(HTTP_OWNER_ODDS) == HTTP_LOCAL_SHARE
    # 실제로 배당을 10회 보낼 수 있다.
    odds = sum(1 for _ in range(50) if budget.http_charge(HTTP_OWNER_ODDS)[0])
    assert odds == HTTP_LOCAL_SHARE


def test_reverse_order_reserves_ten_for_articles():
    """반대 순서(배당 먼저 20회)에서도 기사가 10회를 쓸 수 있다."""
    budget = _http_budget()
    odds = sum(1 for _ in range(50) if budget.http_charge(HTTP_OWNER_ODDS)[0])

    assert odds == HTTP_LOCAL_SHARE * 2
    assert budget.http_remaining(HTTP_OWNER_ARTICLES) == HTTP_LOCAL_SHARE
    articles = sum(1 for _ in range(50) if budget.http_charge(HTTP_OWNER_ARTICLES)[0])
    assert articles == HTTP_LOCAL_SHARE


def test_thirty_first_http_hop_is_blocked_and_reason_names_the_limit():
    """두 로직 합계는 30을 넘지 못하고, 31번째는 사유와 함께 거부된다."""
    budget = _http_budget()
    for _ in range(20):
        budget.http_charge(HTTP_OWNER_ARTICLES)
    for _ in range(10):
        budget.http_charge(HTTP_OWNER_ODDS)
    assert budget.api_used == HTTP_TOTAL_LIMIT

    allowed, reason = budget.http_charge(HTTP_OWNER_ARTICLES)
    assert allowed is False
    assert "30" in (reason or "")


def test_http_release_returns_only_the_owner_share():
    """보내지 않은 예약은 **그 소유자 몫으로만** 돌아간다(다른 로직 몫을 늘리지 않는다)."""
    budget = _http_budget()
    odds_before = budget.http_remaining(HTTP_OWNER_ODDS)

    reserved = budget.http_reserve(HTTP_OWNER_ARTICLES, 12)
    assert reserved == 12
    assert budget.http_owner_used(HTTP_OWNER_ARTICLES) == 12

    returned = budget.http_release(HTTP_OWNER_ARTICLES, 2)
    assert returned == 2
    assert budget.http_owner_used(HTTP_OWNER_ARTICLES) == 10
    # 반환은 기사 사용량만 줄인다. 배당이 쓸 수 있는 몫은 예약 전과 같다
    # (기사 반환이 배당 몫을 **늘리지도** 줄이지도 않는다).
    assert budget.http_remaining(HTTP_OWNER_ODDS) == odds_before


def test_legacy_run_budget_keeps_the_single_api_cap():
    """legacy `for_run`은 새 보호 몫 정책에 들어가지 않는다(기존 24 단일 상한 유지)."""
    budget = RunBudget.for_run(now=FIXED_NOW)

    assert budget.http_owner_quotas is False
    # legacy 경로는 전역 기한이 켜져 있으므로 판정 시각을 고정한다(시계 축은 그대로).
    used = sum(
        1 for _ in range(50) if budget.http_charge(HTTP_OWNER_ARTICLES, now=FIXED_NOW)[0]
    )
    assert used == budget.limits.api_requests  # 24 (보호 몫 아님)


def test_unknown_or_missing_http_owner_is_refused_without_changing_counters():
    """보호 몫 실행에서 소유자 미지정/미등록 이름은 거부되고 총량도 소유량도 변하지 않는다.

    검사 이유(실패 시 사용자 영향): 분류를 생략한 호출자가 공유 몫을 잠식해 두 로직의
    보호 몫을 함께 깎고, 오타 하나로 **없는 보호 몫 10**을 받아 실제 로직(배당)을 굶길 수
    있었다(2026-11-19 HB-REVIEW 지적). 계약은 "분류를 생략해 보호몫을 우회하는 경로를
    남기지 않는다"를 요구한다.
    """
    budget = _http_budget()

    # 소유자 미지정과 미등록 이름 모두 거부된다(차감·예약 두 경로).
    for bad_owner in (None, "rogue", "Articles", ""):
        allowed, reason = budget.http_charge(bad_owner, now=FIXED_NOW)
        assert allowed is False, bad_owner
        assert "소유자" in (reason or ""), reason
        assert budget.http_reserve(bad_owner, 5) == 0

    # 거부는 어떤 카운터도 바꾸지 않는다.
    assert budget.api_used == 0
    assert budget.http_shared_used == 0
    assert budget.http_owner_used(HTTP_OWNER_ARTICLES) == 0
    assert budget.http_owner_used(HTTP_OWNER_ODDS) == 0
    assert budget.http_remaining(HTTP_OWNER_ARTICLES) == HTTP_LOCAL_SHARE * 2
    assert budget.http_remaining(HTTP_OWNER_ODDS) == HTTP_LOCAL_SHARE * 2

    # 유효 소유자는 그대로 동작한다(거부가 정상 경로를 막지 않는다).
    assert budget.http_charge(HTTP_OWNER_ARTICLES, now=FIXED_NOW)[0] is True
    assert budget.http_reserve(HTTP_OWNER_ODDS, 1) == 1
