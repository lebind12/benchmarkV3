"""경기 생성의 공통 실행 예산과 재시도 정책 (단일 소유자).

값을 여기저기 복사하지 않고 이 파일 한 곳에서만 정한다.

| 항목 | 값 |
|---|---|
| 한 생성 실행의 **각 논리 AI 모듈** | 최초 포함 최대 3회 |
| 여섯 모듈 합계 | 6 × 3 = 18 (가능한 전송 수의 산술적 설명, 공용 예산 아님) |
| 전체 독립 8회 한도 | **없음**(2026-11-12 사용자 확정으로 제거) |
| 다른 경기·이전 시험 집합 prior 차감 | **없음**(기록만 보존) |
| D0 외부 API 요청 예산 | 재시도 포함 24회 |
| 모델 동시 요청 | 실행 합계 2 |
| API 동시 요청 | 실행 합계 2 |
| 모델 응답 대기 상한 | 300초 |
| 축구 API 요청 상한 | 30초 |
| 모델 출력 상한 | 40,000 토큰 |
| 전체 실행 기한 | 1,800초 — **새 생성 경로의 독립 중단 기준으로 쓰지 않는다** |
| 대기 | 유효한 Retry-After 우선, 없으면 1초부터 지수 증가, 무작위 지연 포함 60초 상한 |

설계 원칙:

- 재시도와 예산을 소유하는 실행기는 **하나**다. LangGraph 노드 재시도나 제공자
  SDK 재시도를 함께 켜서 실제 호출 수가 배로 늘게 두지 않는다. 그래서 SDK 재시도는
  끄거나(전송 계층) 시도 기록에 포함되는지 확인해야 한다.
- 모듈 상한이 선언된 실행(`RunBudget.for_generation`)에서는 **모듈별 3회가 단일
  소유자**다. 전체 상한은 그 합계에서 파생되므로 다른 모듈이 이 모듈의 3회를
  굶기지 못하고, 옛 8회 값도 병목이 되지 않는다.
- 남은 예산 예약(미시작 단계의 첫 호출 몫)은 **모듈 상한이 없는 옛 경로**에서만
  쓴다. 모듈 상한이 있으면 미시작 단계 예약을 다시 빼지 않는다.
- 전역 기한도 모듈 상한이 있는 경로에서는 끈다. 요청별 300초 타임아웃·명시적
  취소·기술 실패 기록은 그대로 유지한다.
- 401·403 같은 영구 오류는 같은 요청을 다시 보내지 않는다. 429·503·타임아웃,
  `finishReason=MAX_TOKENS` 절단, JSON 파싱 실패는 같은 모듈의 남은 횟수로 처리한다.
  실패한 시도와 성공한 시도를 모두 남긴다(성공만 골라 제출하지 않는다).
- 글의 길이·내용·근거 수 부족은 재시도 사유가 아니다. 성공 판단은 사용자가 한다.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from app.preview.contracts import ExecutionLimits, RequestClass

__all__ = [
    "API_CONCURRENCY",
    "API_REQUEST_BUDGET",
    "API_TIMEOUT_SECONDS",
    "BudgetExceeded",
    "BudgetLimits",
    "ConcurrencyGate",
    "DeadlineExceeded",
    "MAX_ATTEMPTS_PER_CALL",
    "MODEL_CONCURRENCY",
    "MODEL_REQUEST_BUDGET",
    "MODEL_TIMEOUT_SECONDS",
    "HTTP_LOCAL_SHARE",
    "HTTP_OWNER_ARTICLES",
    "HTTP_OWNER_ODDS",
    "HTTP_OWNERS",
    "HTTP_SHARED_SHARE",
    "HTTP_TOTAL_LIMIT",
    "MODULE_SEND_CAP",
    "NORMAL_MODEL_CALLS",
    "RETRY_BASE_DELAY_SECONDS",
    "RETRY_MAX_DELAY_SECONDS",
    "RUN_DEADLINE_SECONDS",
    "RetryDecision",
    "RunBudget",
    "RESERVATION_RETURNED",
    "bounded_wait_seconds",
    "rate_limit_wait_seconds",
    "RATE_LIMIT_MAX_SENDS",
    "RATE_LIMIT_WAIT_SECONDS",
    "classify_attempt",
    "plan_limits",
]

# --- 계획 §5 값 ------------------------------------------------------------

MODEL_REQUEST_BUDGET = 8
# 정상 경로 모델 호출 수(2026-11-11 확정 설계). 두 조사 묶음 + 작성 3 + 최종 전망 1 = 6회다.
# 상한(총 8)은 그대로 두고, 재시도 여유만 2회다. 조용히 늘리지 않는다.
# 옛 경로(R1~R4 조사 + S1 종합 = 5회)는 그대로 실행되지만 기본 경로가 아니다.
NORMAL_MODEL_CALLS = 6  # 조사 2 + 작성 3 + 최종 전망 1
# 사용자 확정(2026-11-12): **한 생성 실행의 각 논리 AI 모듈**에 최초 포함 최대 3회.
# 전체 독립 8회·trial 누적 차감은 새 생성 경로에서 쓰지 않는다. 여섯 모듈 × 3 = 18은
# 가능한 전송 수의 산술적 설명이며 공용 여유를 배분하는 정책이 아니다.
MODULE_SEND_CAP = 3
API_REQUEST_BUDGET = 24

# HTTP 로직별 **보호 몫**(사용자 확정 2026-11-19: "기사·배당 각 10회, 공통 30회").
# 보호 몫은 **다른 로직이 쓸 수 없는** 몫이고, 자기 몫을 넘는 요청은 공유 몫에서 뺀다.
# 따라서 기사 20회를 써도 배당 10회가 남고, 역순도 같다. 합계는 30을 넘지 않는다.
# 10은 "사용할 수 있는 몫"이지 성공 10회 보장도, 강제 10회 반복도 아니다.
HTTP_OWNER_ARTICLES = "articles"
HTTP_OWNER_ODDS = "odds"
HTTP_LOCAL_SHARE = 10
HTTP_SHARED_SHARE = 10
HTTP_TOTAL_LIMIT = 30
# 보호 몫이 선언된 실행의 HTTP 소유자 전체. 여기 없으면 공유 몫만 쓴다.
HTTP_OWNERS: tuple[str, ...] = (HTTP_OWNER_ARTICLES, HTTP_OWNER_ODDS)
MAX_ATTEMPTS_PER_CALL = 3
MODEL_CONCURRENCY = 2
API_CONCURRENCY = 2
MODEL_TIMEOUT_SECONDS = 300
API_TIMEOUT_SECONDS = 30
RUN_DEADLINE_SECONDS = 1800
RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0

# 429(요청 제한) 전용 대기 구간(사용자 확정 2026-11-19). **고정 세 구간**이며 초 단위
# 공식이나 60초 상한으로 줄이지 않는다. jitter로도 단축하지 않는다.
RATE_LIMIT_WAIT_SECONDS: tuple[int, ...] = (60, 300, 600)
# 429는 최초 포함 최대 **4회 전송**한다(대기 3회를 모두 쓸 수 있게). 다른 오류나
# 내용 재생성 상한은 이 값으로 늘리지 않는다(모듈 상한 3회는 그대로).
RATE_LIMIT_MAX_SENDS = 4

# 시작하지 않기로 확정된 정상 호출의 예약을 반환했을 때 남기는 표시. 전체 상한은
# 늘지 않고, 그 몫만 재시도가 쓸 수 있게 된다.
RESERVATION_RETURNED = "reservation_returned"

# --- 오류 분류 ------------------------------------------------------------

# 같은 요청을 다시 보내도 결과가 달라지지 않는 영구 오류. 401에 눈먼 재시도를 하지 않는다.
PERMANENT_HTTP_STATUSES = frozenset({400, 401, 403, 404, 422})
# 일시적 오류. 429(요청 제한)는 대기 후 재시도 대상이다.
RETRYABLE_HTTP_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
# 재시도해도 의미가 없는 전송 오류 분류. 설정 오류는 새 시도로 해결되지 않는다.
PERMANENT_ERROR_CLASSES = frozenset(
    {
        "configuration_error",
        "invalid_request",
        "invalid_argument",
        "authentication_error",
        "permission_error",
        "not_found",
    }
)


class RetryDecision(str, Enum):
    """한 시도 뒤에 같은 논리 호출을 다시 보낼지."""

    RETRY = "retry"
    STOP = "stop"


class BudgetExceeded(RuntimeError):
    """실행 예산을 더 쓸 수 없다. 실제 호출을 보내기 전에 중단한다."""


class DeadlineExceeded(RuntimeError):
    """전체 실행 기한이 지났다."""


def classify_attempt(
    *,
    outcome: str,
    http_status: int | None = None,
    error_class: str | None = None,
) -> RetryDecision:
    """시도 결과를 '더 보낼지'로만 분류한다. 성공/실패 판정과 다른 축이다."""
    if outcome == "ok":
        return RetryDecision.STOP
    if error_class and error_class.lower() in PERMANENT_ERROR_CLASSES:
        return RetryDecision.STOP
    if http_status is not None:
        if http_status in PERMANENT_HTTP_STATUSES:
            return RetryDecision.STOP
        if http_status in RETRYABLE_HTTP_STATUSES:
            return RetryDecision.RETRY
        # 4xx는 요청 자체를 고치지 않으면 성공하지 않는다.
        if 400 <= http_status < 500:
            return RetryDecision.STOP
        return RetryDecision.RETRY
    # 응답을 보존하지 못한 경우(시간 초과·전송 오류)는 일시적으로 본다. 다만 그
    # 시도가 제공자에 도달했는지는 알 수 없으므로 결과는 unknown으로 남긴다.
    return RetryDecision.RETRY


def bounded_wait_seconds(
    attempt_ordinal: int,
    *,
    retry_after_seconds: float | None = None,
    rng: Callable[[], float] = random.random,
    base_seconds: float = RETRY_BASE_DELAY_SECONDS,
    max_seconds: float = RETRY_MAX_DELAY_SECONDS,
) -> float:
    """재시도 전 대기 시간.

    유효한 Retry-After가 있으면 그것을 우선한다. 없으면 1초부터 지수 증가시키고
    무작위 지연(0.5~1.0배)을 섞는다. 어느 쪽이든 60초를 넘기지 않는다.
    """
    if retry_after_seconds is not None and retry_after_seconds >= 0:
        return min(float(retry_after_seconds), max_seconds)
    exponent = max(0, int(attempt_ordinal))
    ceiling = min(max_seconds, base_seconds * (2**exponent))
    jitter = 0.5 + 0.5 * float(rng())
    return min(max_seconds, ceiling * jitter)


def rate_limit_wait_seconds(
    attempt_ordinal: int,
    *,
    retry_after_seconds: float | None = None,
) -> float:
    """429 재시도 전 대기 시간. **60 / 300 / 600초 고정 구간**이다.

    - jitter를 섞지 않는다. 지정된 구간을 임의로 단축하지 않는다.
    - 공급자가 더 긴 유효 대기 안내(RetryInfo/Retry-After)를 주면 그것을 **최소 대기**로
      존중한다(짧은 안내로 구간을 깎지 않는다).
    - 구간을 모두 쓴 뒤에는 마지막 구간 값을 유지한다(무한 증가 없음).
    """
    index = max(0, int(attempt_ordinal))
    ladder = RATE_LIMIT_WAIT_SECONDS[min(index, len(RATE_LIMIT_WAIT_SECONDS) - 1)]
    wait = float(ladder)
    if retry_after_seconds is not None and retry_after_seconds >= 0:
        wait = max(wait, float(retry_after_seconds))
    return wait


@dataclass(frozen=True)
class BudgetLimits:
    """한 실행이 쓸 수 있는 상한. 계획 §5 값이 기본이다."""

    model_requests: int = MODEL_REQUEST_BUDGET
    api_requests: int = API_REQUEST_BUDGET
    attempts_per_call: int = MAX_ATTEMPTS_PER_CALL
    deadline_seconds: int = RUN_DEADLINE_SECONDS
    model_concurrency: int = MODEL_CONCURRENCY
    api_concurrency: int = API_CONCURRENCY
    normal_model_calls: int = NORMAL_MODEL_CALLS

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_requests": self.model_requests,
            "api_requests": self.api_requests,
            "attempts_per_call": self.attempts_per_call,
            "deadline_seconds": self.deadline_seconds,
            "model_concurrency": self.model_concurrency,
            "api_concurrency": self.api_concurrency,
            "normal_model_calls": self.normal_model_calls,
        }

    def execution_limits(self) -> ExecutionLimits:
        """MP-02 기록 계약(`preview_runs.limits`)에 넣을 값.

        동시성·정상 호출 수는 `preview_runs.limits`의 네 필드에 없으므로 여기에
        억지로 넣지 않고 `to_dict()`로 API 응답에 따로 낸다.
        """
        return ExecutionLimits(
            model_requests=self.model_requests,
            api_requests=self.api_requests,
            attempts_per_call=self.attempts_per_call,
            deadline_seconds=self.deadline_seconds,
        )


def plan_limits(**overrides: Any) -> BudgetLimits:
    """계획 기본값에 일부만 바꿔 적용한다. 0이나 음수는 거부한다."""
    allowed = set(BudgetLimits.__dataclass_fields__)
    unknown = set(overrides) - allowed
    if unknown:
        raise TypeError(f"unknown budget field(s): {sorted(unknown)}")
    for key, value in overrides.items():
        if value is not None and int(value) < 0:
            raise ValueError(f"budget field {key} cannot be negative")
    return BudgetLimits(**{k: int(v) for k, v in overrides.items() if v is not None})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_moment(value: Any) -> datetime | None:
    """저장된 ISO 문자열을 시각으로 되돌린다. 못 읽으면 `None`(지어내지 않는다)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@dataclass
class RunBudget:
    """실행 하나의 예산·기한·시도 수를 세는 상태.

    이 객체는 DB에 저장되는 기록이 아니라 실행 중 판단 근거다. 실제로 보낸 시도는
    `store.append_attempt`가 남기므로, 예산은 "얼마나 더 보낼 수 있는가"만 책임진다.
    """

    limits: BudgetLimits
    started_at: datetime
    model_used: int = 0
    api_used: int = 0
    # HTTP 소유자별 **실제 차감** 수. 보호 몫 판정과 snapshot의 근거다.
    http_used_by_owner: dict[str, int] = field(default_factory=dict)
    # 보호 몫에서 다른 소유자가 대신 쓴 수(=공유 몫 사용분). 반환 시 이 값부터 줄인다.
    http_shared_used: int = 0
    # HTTP 보호 몫 정책을 쓰는 실행인지. legacy 실행은 기존 24 단일 상한을 유지한다.
    http_owner_quotas: bool = False
    attempts_by_call: dict[str, int] = field(default_factory=dict)
    registered_calls: list[str] = field(default_factory=list)
    # 시작하지 않기로 **확정**된 정상 호출. 예약 몫을 반환하되 전체 상한은 늘리지 않는다.
    cancelled_calls: list[str] = field(default_factory=list)
    # 모듈(logical_call_id)별 **실제 전송** 누적 상한. 사용자가 승인한 단위는 전체 합계가
    # 아니라 모듈별 3회다. `prior_module_usage`는 이전 실행(장부)에서 이미 보낸 수이며,
    # 새 run으로 0으로 초기화하지 않는다.
    module_send_cap: int | None = None
    # 이 실행이 실제로 실행하는 논리 모듈 목록. 있으면 전체 모델 상한을
    # `module_send_cap × 모듈 수`로 **파생**한다(추가 병목을 만들지 않는다).
    module_ids: tuple[str, ...] = ()
    # 이전 시험 집합의 전송 이력. 기록·설명용으로만 남기고 **막는 데 쓰지 않는다**
    # (다른 경기·이전 시험이 새 실행을 차단하지 않는다).
    prior_module_usage: dict[str, int] = field(default_factory=dict)
    sent_by_module: dict[str, int] = field(default_factory=dict)
    # 모듈별 **429로 끝난 전송 수**. 기록·진단용이며 상한 판정의 직접 근거는 아래
    # `last_was_rate_limited`다(혼합 흐름에서 4번째가 막히지 않게 하기 위함).
    rate_limited_by_module: dict[str, int] = field(default_factory=dict)
    # 모듈별 **마지막 실패가 429였는지**. 429 직후의 재시도에만 4번째 전송을 연다.
    # 직전이 비429(503·타임아웃)나 내용 실패면 4번째를 열지 않는다(상한 일괄 증가 금지).
    last_was_rate_limited: dict[str, bool] = field(default_factory=dict)
    stopped_reason: str | None = None
    # 전체 실행 기한을 **독립 중단 기준으로 쓸지**. 모듈별 3회가 상한을 소유하는 새
    # 생성 경로에서는 끈다(사용자 확정 2026-11-12). 기한 값 자체는 기록·표시용으로
    # 남기고, 요청별 300초 타임아웃·명시적 취소는 그대로 둔다.
    deadline_enforced: bool = True
    # 병렬 갈래가 같은 예산을 동시에 갱신하므로 계산 구간을 잠근다. 잠금 순서는
    # 항상 "잠금 → 판정 → 차감"이며, 차감 도중 다른 갈래가 끼어들지 않는다.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # -- 생성 -------------------------------------------------------------

    @classmethod
    def for_run(
        cls,
        limits: BudgetLimits | None = None,
        *,
        now: datetime | None = None,
    ) -> "RunBudget":
        return cls(limits=limits or BudgetLimits(), started_at=now or _utcnow())

    @classmethod
    def for_generation(
        cls,
        module_ids: Sequence[str],
        limits: BudgetLimits | None = None,
        *,
        prior_module_usage: Mapping[str, int] | None = None,
        now: datetime | None = None,
    ) -> "RunBudget":
        """경기 생성 한 번의 예산. **모듈별 3회가 상한을 소유한다.**

        사용자 확정(2026-11-12): 한 경기 1생성 실행에서 각 논리 AI 모듈의 최초 포함
        최대 3회다. 전체 8회·다른 경기·시험 집합 prior 차감은 이 경로에서 쓰지 않는다.
        전체 상한은 모듈 상한의 합계에서 파생하고, 전역 기한은 독립 중단 기준으로
        쓰지 않는다(요청별 300초 타임아웃은 provider가 그대로 건다).
        """
        budget = cls(limits=limits or BudgetLimits(), started_at=now or _utcnow())
        budget.module_send_cap = MODULE_SEND_CAP
        budget.module_ids = tuple(str(item) for item in module_ids if str(item))
        budget.prior_module_usage = dict(prior_module_usage or {})
        # 새 생성 실행에서 전역 기한으로 모듈 3회를 잘라내지 않는다.
        budget.deadline_enforced = False
        # bundle 생성 경로는 **HTTP 로직별 보호 몫**(기사·배당 각 10, 공유 10, 총 30)을
        # 쓴다(사용자 확정 2026-11-19). legacy `for_run` 경로는 기존 24 단일 상한 그대로다.
        budget.http_owner_quotas = True
        return budget

    @classmethod
    def restore(
        cls,
        snapshot: Mapping[str, Any] | None,
        *,
        now: datetime | None = None,
    ) -> "RunBudget":
        """저장된 예산 상태에서 이어 쓴다(MP-10 재개).

        재개는 **남은 예산**으로 미완료 단계만 다시 도는 것이다. 그래서 이미 쓴
        횟수와 기한을 새로 0으로 되돌리지 않는다. 기한 값이 없으면 지금부터 새로
        센다(기록이 없는 경우를 성공으로 꾸미지 않는다).
        """
        data = dict(snapshot or {})
        limits = budget_from_limits(data.get("limits"))
        started = _parse_moment(data.get("started_at")) or (now or _utcnow())
        budget = cls(limits=limits, started_at=started)
        budget.model_used = max(0, int(data.get("model_used") or 0))
        budget.api_used = max(0, int(data.get("api_used") or 0))
        budget.attempts_by_call = {
            str(key): int(value)
            for key, value in (data.get("attempts_by_call") or {}).items()
        }
        budget.registered_calls = [str(item) for item in data.get("registered_calls") or ()]
        budget.cancelled_calls = [
            str(item) for item in data.get("cancelled_calls") or ()
        ]
        budget.module_send_cap = data.get("module_send_cap")
        budget.module_ids = tuple(str(item) for item in data.get("module_ids") or ())
        budget.prior_module_usage = {
            str(key): int(value)
            for key, value in (data.get("prior_module_usage") or {}).items()
        }
        budget.sent_by_module = {
            str(key): int(value)
            for key, value in (data.get("sent_by_module") or {}).items()
        }
        stored_enforced = data.get("deadline_enforced")
        if stored_enforced is not None:
            budget.deadline_enforced = bool(stored_enforced)
        return budget

    def persistable(self) -> dict[str, Any]:
        """재개를 위해 DB에 남길 값. 화면용 파생값은 넣지 않는다."""
        return {
            "limits": self.limits.to_dict(),
            "started_at": self.started_at.isoformat(),
            "model_used": self.model_used,
            "api_used": self.api_used,
            "attempts_by_call": dict(self.attempts_by_call),
            "registered_calls": list(self.registered_calls),
            "cancelled_calls": list(self.cancelled_calls),
            "module_send_cap": self.module_send_cap,
            "module_ids": list(self.module_ids),
            "prior_module_usage": dict(self.prior_module_usage),
            "sent_by_module": dict(self.sent_by_module),
            "deadline_enforced": self.deadline_enforced,
            "stopped_reason": self.stopped_reason,
        }

    # -- 시간 -------------------------------------------------------------

    @property
    def deadline(self) -> datetime:
        return self.started_at + timedelta(seconds=self.limits.deadline_seconds)

    def elapsed_seconds(self, now: datetime | None = None) -> float:
        return max(0.0, ((now or _utcnow()) - self.started_at).total_seconds())

    def seconds_left(self, now: datetime | None = None) -> float:
        """남은 기한. 기한을 독립 중단 기준으로 쓰지 않는 실행에서는 `inf`다.

        `inf`를 돌려주는 이유는 호출자가 `min(요청 타임아웃, 남은 기한)`으로 요청별
        타임아웃을 깎지 않게 하기 위해서다. 300초 요청 상한은 그대로 적용된다.
        """
        if not self.deadline_enforced:
            return float("inf")
        return max(0.0, self.limits.deadline_seconds - self.elapsed_seconds(now))

    def deadline_passed(self, now: datetime | None = None) -> bool:
        return self.seconds_left(now) <= 0.0

    # -- 호출 등록과 예약 --------------------------------------------------

    def register_call(self, logical_call_id: str) -> None:
        """논리 호출을 처음 시작한다. 이 호출의 첫 시도 몫은 더 이상 '미시작'이 아니다.

        전체 프리뷰는 갈래 셋이 이 목록을 동시에 갱신하므로 잠그고 넣는다. 등록이
        늦으면 다른 갈래가 남의 첫 호출 몫을 예약으로 세어 예산을 과소평가한다.
        """
        with self.lock:
            if logical_call_id not in self.registered_calls:
                self.registered_calls.append(logical_call_id)

    def cancel_call(self, logical_call_id: str) -> bool:
        """시작하지 않기로 확정된 정상 호출의 **예약을 반환**한다.

        반환은 "그 호출이 쓰지 않기로 한 첫 시도 몫을 재시도가 쓸 수 있게" 하는 것이다.
        전체 실제 전송 상한(`model_requests`)을 늘리지 않는다. 이미 시도를 보낸 호출은
        취소할 수 없다(그 호출은 이미 자기 몫을 썼다).

        반환값이 `False`면 취소가 거부된 것이다(이미 시작했거나 상한 밖 호출).
        """
        with self.lock:
            if self.attempts_used(logical_call_id) > 0:
                return False
            if len(self.registered_calls) >= self.limits.normal_model_calls:
                # 정상 호출 수를 넘는 추가 호출은 예약 몫이 없으므로 반환할 것도 없다.
                return False
            if logical_call_id not in self.cancelled_calls:
                self.cancelled_calls.append(logical_call_id)
            return True

    def cancelled_unstarted(self) -> int:
        """등록되지 않은 채 취소된 호출 수. 예약 계산에서만 뺀다."""
        return sum(
            1 for call in self.cancelled_calls if call not in self.registered_calls
        )

    def unstarted_calls(self) -> int:
        return max(
            0,
            self.limits.normal_model_calls
            - len(self.registered_calls)
            - self.cancelled_unstarted(),
        )

    def reserved_model_requests(self) -> int:
        """아직 시작하지 않은 정상 호출의 첫 시도 몫. 재시도는 이 몫을 침범하지 않는다."""
        return self.unstarted_calls()

    def effective_model_requests(self) -> int:
        """이 실행이 실제로 쓸 수 있는 모델 전송 상한.

        모듈별 3회 상한이 선언되면 전체 값은 **그 합계에서 파생**한다(모듈 6개면 18,
        섹션 재생성 1개면 3). 옛 숫자 필드(`model_requests`)는 기록 호환용으로 남기되
        판정에 쓰지 않는다. 그래야 `8`이라는 옛 상한이 모듈별 3회를 잘라내지 않는다.
        """
        if self.module_send_cap is not None and self.module_ids:
            # 429 직후 열린 추가 전송 몫을 합계에도 반영한다(모듈 상한만 열고 전체
            # 상한이 막으면 4번째 전송이 두 번째 병목에 걸린다). 직전이 429가 아니면
            # 그 모듈의 몫은 열리지 않으므로 다른 오류의 상한은 늘지 않는다.
            extra = sum(
                1
                for logical_call_id in self.module_ids
                if self.last_failure_was_rate_limited(logical_call_id)
            )
            return self.module_send_cap * len(self.module_ids) + extra
        return self.limits.model_requests

    # -- HTTP 소유자별 보호 몫 ---------------------------------------------

    def http_owner_used(self, owner: str | None) -> int:
        """이 소유자가 실제로 쓴 HTTP 전송 수."""
        if owner is None:
            return 0
        return int(self.http_used_by_owner.get(owner, 0))

    def http_total_used(self) -> int:
        """모든 소유자의 HTTP 전송 합계(= `api_used`와 같은 값)."""
        return int(self.api_used)

    def _http_owner_is_known(self, owner: str | None) -> bool:
        """보호 몫 정책에서 **허용된 소유자**인지 판정한다.

        보호 몫이 켜진 실행에서는 `articles`/`odds`만 유효하다. `None`이나 등록되지 않은
        이름을 조용히 받아들이면 (1) 소유자 없이 공유 몫을 잠식해 두 로직의 보호 몫을
        함께 깎고, (2) 오타 하나로 **없는 보호 몫 10**을 새로 받아 실제 로직을 굶긴다
        (2026-11-19 HB-REVIEW 지적). legacy 실행(`http_owner_quotas=False`)은 종전대로
        소유자 개념이 없으므로 그대로 허용한다.
        """
        if not self.http_owner_quotas:
            return True
        return owner in HTTP_OWNERS

    def http_unknown_owner_reason(self, owner: str | None) -> str:
        """유효하지 않은 소유자로 전송을 시도했을 때의 사유(화면·진단용)."""
        return (
            "HTTP 요청 소유자가 지정되지 않았거나 등록되지 않아 전송하지 않았습니다:"
            f" {owner!r} (허용: {', '.join(HTTP_OWNERS)})"
        )

    def _http_owner_allowance(self, owner: str | None) -> int:
        """이 소유자가 **다른 소유자 몫을 건드리지 않고** 쓸 수 있는 남은 수.

        = 자기 보호 몫의 잔여 + 공유 몫의 잔여.
        """
        if not self.http_owner_quotas:
            return max(0, self.limits.api_requests - self.api_used)
        if not self._http_owner_is_known(owner):
            # 유효하지 않은 소유자는 몫이 0이다(우회 불가).
            return 0
        local_left = max(0, HTTP_LOCAL_SHARE - self.http_owner_used(owner))
        shared_left = max(0, HTTP_SHARED_SHARE - self._http_shared_used_for(owner))
        return local_left + shared_left

    def _http_shared_used_for(self, owner: str | None) -> int:
        """공유 몫 중 이 소유자가 쓴 수(자기 보호 몫을 넘긴 부분)."""
        if owner is None:
            return 0
        return max(0, self.http_owner_used(owner) - HTTP_LOCAL_SHARE)

    def http_remaining(self, owner: str | None = None) -> int:
        """이 소유가 앞으로 보낼 수 있는 남은 HTTP 전송 수(총 상한도 함께 본다)."""
        total_left = max(0, self._http_total_limit() - self.api_used)
        return min(total_left, self._http_owner_allowance(owner))

    def _http_total_limit(self) -> int:
        return HTTP_TOTAL_LIMIT if self.http_owner_quotas else self.limits.api_requests

    def http_reserve(self, owner: str | None, count: int) -> int:
        """이 소유자 이름으로 전송 홉을 미리 예약한다(잠금 유지).

        유효하지 않은 소유자는 **0을 돌려준다**(예약 자체가 성립하지 않는다). 차감과
        예약이 같은 판정을 공유하므로 한 곳에서 닫으면 두 경로가 함께 닫힌다.
        """
        with self.lock:
            if not self._http_owner_is_known(owner):
                return 0
            allowed = min(int(count), self.http_remaining(owner))
            if allowed <= 0:
                return 0
            self._http_consume(owner, allowed)
            return allowed

    def http_charge(self, owner: str | None, *, now: datetime | None = None) -> tuple[bool, str | None]:
        """전송 **한 홉**을 이 소유자 이름으로 차감한다."""
        with self.lock:
            if self.deadline_enforced and self.deadline_passed(now):
                return False, (
                    f"전체 실행 기한({self.limits.deadline_seconds}초)이 지나 더 보내지 않습니다."
                )
            if not self._http_owner_is_known(owner):
                return False, self.http_unknown_owner_reason(owner)
            if self.http_remaining(owner) < 1:
                return False, self._http_exhausted_reason(owner)
            self._http_consume(owner, 1)
            return True, None

    def http_release(self, owner: str | None, count: int) -> int:
        """이 소유자 이름으로 예약했지만 **보내지 않은** 몫을 돌려준다.

        반환은 그 소유자의 사용량에서만 줄인다. 다른 소유자의 몫을 늘리지 않는다.
        """
        if count <= 0:
            return 0
        with self.lock:
            used = self.http_owner_used(owner)
            taken = min(int(count), used)
            if taken <= 0:
                return 0
            self.http_used_by_owner[owner] = used - taken
            self.api_used = max(0, self.api_used - taken)
            return taken

    def _http_consume(self, owner: str | None, count: int) -> None:
        """사용량 증가를 한 곳에서만 한다(총·소유자·공유 계산이 어긋나지 않게)."""
        self.api_used += int(count)
        if owner is None:
            return
        self.http_used_by_owner[owner] = self.http_owner_used(owner) + int(count)
        # 자기 보호 몫을 넘긴 부분의 합이 곧 공유 몫 사용분이다.
        self.http_shared_used = sum(
            max(0, self.http_owner_used(each) - HTTP_LOCAL_SHARE) for each in HTTP_OWNERS
        )

    def _http_exhausted_reason(self, owner: str | None) -> str:
        if not self.http_owner_quotas or owner is None:
            return f"API 요청 예산({self.limits.api_requests}회)을 모두 사용했습니다."
        if self.api_used >= HTTP_TOTAL_LIMIT:
            return (
                f"HTTP 총 전송 상한({HTTP_TOTAL_LIMIT}회)에 도달해"
                f" {owner} 요청을 더 보내지 않습니다."
            )
        return (
            f"{owner}가 쓸 수 있는 HTTP 몫(보호 {HTTP_LOCAL_SHARE}회+공유"
            f" {HTTP_SHARED_SHARE}회)을 모두 사용했습니다."
        )

    def remaining(self, request_class: str = RequestClass.MODEL.value) -> int:
        if request_class == RequestClass.API.value:
            return max(0, self.limits.api_requests - self.api_used)
        return max(0, self.effective_model_requests() - self.model_used)

    def module_total(self, logical_call_id: str) -> int:
        """이 모듈이 **이번 생성 실행**에서 실제로 보낸 수.

        이전 시험 집합의 누적(`prior_module_usage`)은 합산하지 않는다. 사용자 확정은
        "한 생성 실행의 각 논리 모듈에 최초 포함 최대3회"이며, 다른 경기·이전 시험의
        사용량이 새 경기 생성을 막지 않는다. 과거 이력은 `prior_module_usage`에 남아
        화면·보고에 쓰인다.
        """
        return int(self.sent_by_module.get(logical_call_id, 0))

    def module_prior_total(self, logical_call_id: str) -> int:
        """이전 시험 집합에서 보낸 수(표시용). 상한 판정에는 쓰지 않는다."""
        return int(self.prior_module_usage.get(logical_call_id, 0))

    def attempts_used(self, logical_call_id: str) -> int:
        return int(self.attempts_by_call.get(logical_call_id, 0))

    # -- 판정 -------------------------------------------------------------

    def rate_limit_sends(self, logical_call_id: str) -> int:
        """이 모듈이 **429로 끝난** 전송 수. 429 전용 추가 허용의 근거다."""
        return int(self.rate_limited_by_module.get(logical_call_id, 0))

    def note_rate_limited(self, logical_call_id: str) -> None:
        """이번 전송이 429였다고 기록한다. 상한 판정만 바꾸고 다른 정책은 건드리지 않는다."""
        self.rate_limited_by_module[logical_call_id] = (
            self.rate_limit_sends(logical_call_id) + 1
        )
        self.last_was_rate_limited[logical_call_id] = True

    def note_non_rate_limit_failure(self, logical_call_id: str) -> None:
        """마지막 실패가 429가 아니었다고 기록한다(503·타임아웃·내용 실패).

        429가 앞서 있었더라도 **직전이 429가 아니면** 4번째 전송을 열지 않는다.
        """
        self.last_was_rate_limited[logical_call_id] = False

    def last_failure_was_rate_limited(self, logical_call_id: str) -> bool:
        """직전 실패가 429였는지. 4번째 전송 허용의 유일한 근거다."""
        return bool(self.last_was_rate_limited.get(logical_call_id, False))

    def can_attempt(
        self,
        logical_call_id: str,
        request_class: str = RequestClass.MODEL.value,
        *,
        now: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """다음 시도를 보낼 수 있는지. 거부 사유는 화면에 그대로 보여줄 수 있는 문장이다.

        **모듈 상한이 선언된 실행에서는 그 상한이 모델 전송의 단일 소유자다.** 전체
        상한은 모듈 상한의 합계에서 파생되므로 다른 모듈이 이 모듈의 3회를 굶기지
        못한다. 반대로 상한이 없으면(옛 경로) 예약 기반 전체 상한을 그대로 쓴다.
        """
        # 모듈 상한이 있으면 그 값이 시도 상한의 단일 근거다. 둘을 함께 걸어 두면
        # 정책을 바꿀 때 한쪽만 고쳐 조용히 다른 상한이 남는다.
        if self.module_send_cap is not None:
            used = self.module_total(logical_call_id)
            # 429로 끝난 전송에 한해 대기 세 구간(60/300/600초)을 모두 쓸 수 있도록
            # 최대 RATE_LIMIT_MAX_SENDS까지 허용한다. 다른 오류·내용 재생성은 기존
            # 모듈 상한 그대로이며, 이 확장은 429 횟수를 근거로만 열린다.
            limit = self.module_send_cap
            # 429 직후에만 4번째를 연다. 중간에 503 등이 끼어도(429→503→429) 마지막이
            # 429면 열리므로 "최초 포함 4전송"이 혼합 흐름에서도 성립한다.
            if self.last_failure_was_rate_limited(logical_call_id):
                limit = max(limit, RATE_LIMIT_MAX_SENDS)
            if used >= limit:
                prior = self.module_prior_total(logical_call_id)
                history = (
                    f". 이전 시험 집합의 {prior}회는 이번 상한에 합산하지 않습니다"
                    if prior
                    else ""
                )
                return False, (
                    f"모듈 {logical_call_id}의 이번 생성 전송 상한"
                    f"({limit}회)에 도달했습니다. 이 모듈은 더 보내지 않습니다"
                    f"{history}."
                )
        elif self.attempts_used(logical_call_id) >= self.limits.attempts_per_call:
            # 모듈 상한이 없는 경로에서도 **429로 끝난 전송**에 한해 같은 4회 허용을
            # 적용한다(같은 정책을 두 상한 체계에 서로 다르게 두지 않는다). 그 밖의
            # 오류는 기존 attempts_per_call 그대로다.
            if not (
                self.last_failure_was_rate_limited(logical_call_id)
                and self.attempts_used(logical_call_id) < RATE_LIMIT_MAX_SENDS
            ):
                return False, (
                    f"논리 호출 {logical_call_id}의 시도 상한"
                    f"({self.limits.attempts_per_call}회)에 도달했습니다."
                )
        if self.deadline_enforced and self.deadline_passed(now):
            return False, (
                f"전체 실행 기한({self.limits.deadline_seconds}초)이 지나 더 보내지 않습니다."
            )
        if request_class == RequestClass.API.value:
            if self.api_used + 1 > self.limits.api_requests:
                return False, (
                    f"API 요청 예산({self.limits.api_requests}회)을 모두 사용했습니다."
                )
            return True, None
        if self.module_send_cap is not None:
            # 파생 상한은 모듈 상한의 합계다. 미시작 단계 예약을 다시 빼면 모듈 상한이
            # 전체 상한에 막히는(사용자가 허용하지 않은) 두 번째 병목이 생긴다.
            if self.model_used + 1 > self.effective_model_requests():
                return False, (
                    f"모델 전송 합계({self.effective_model_requests()}회)에 도달했습니다."
                )
            return True, None
        reserved = self.reserved_model_requests()
        ceiling = self.effective_model_requests() - reserved
        if self.model_used + 1 > ceiling:
            return False, (
                f"모델 요청 예산({self.effective_model_requests()}회) 중 아직 시작하지 않은"
                f" 필수 단계 몫({reserved}회)을 남겨야 합니다."
            )
        return True, None

    def charge(
        self,
        logical_call_id: str,
        request_class: str = RequestClass.MODEL.value,
        *,
        now: datetime | None = None,
    ) -> None:
        """시도 한 건을 예산에서 차감한다. 보낼 수 없으면 호출 전에 예외로 멈춘다.

        판정과 차감을 **한 잠금 안에서** 처리한다. 갈래 셋이 동시에 통과 판정을 받고
        함께 차감하면 예산 상한을 넘길 수 있기 때문이다.
        """
        with self.lock:
            allowed, reason = self.can_attempt(logical_call_id, request_class, now=now)
            if not allowed:
                self.stopped_reason = reason
                if reason and "기한" in reason:
                    raise DeadlineExceeded(reason)
                raise BudgetExceeded(reason or "budget exhausted")
            if request_class == RequestClass.API.value:
                self.api_used += 1
            else:
                self.model_used += 1
            self.attempts_by_call[logical_call_id] = (
                self.attempts_used(logical_call_id) + 1
            )
            self.sent_by_module[logical_call_id] = (
                self.sent_by_module.get(logical_call_id, 0) + 1
            )

    def reserve_transports(self, count: int, request_class: str = RequestClass.API.value) -> int:
        """전송 홉을 **미리** 예약한다. 논리 호출의 '시도' 수는 올리지 않는다.

        리다이렉트 홉은 한 번의 fetch 안에서 일어나는 전송이며, 재시도 상한
        (`attempts_per_call`)은 논리 호출 재시도에 대한 값이다. 그래서 홉 예약은
        사용량만 잡고 시도 수는 건드리지 않는다. 남은 예산까지만 잡는다.
        """
        with self.lock:
            if request_class == RequestClass.API.value:
                free = max(0, self.limits.api_requests - self.api_used)
                taken = min(int(count), free)
                self.api_used += taken
                return taken
            free = max(0, self.effective_model_requests() - self.model_used)
            taken = min(int(count), free)
            self.model_used += taken
            return taken

    def charge_transport(
        self, request_class: str = RequestClass.API.value, *, now: datetime | None = None
    ) -> tuple[bool, str | None]:
        """전송 **한 홉**을 사용량에서 차감한다. 논리 호출의 '시도' 수는 건드리지 않는다.

        리다이렉트 홉은 한 번의 fetch 안에서 일어나는 전송이며, `attempts_per_call`은
        논리 호출 재시도 횟수다. 둘을 같은 카운터로 묶으면 `attempts_per_call=1`인 승인
        실행에서 2번째 홉이 거부되어 수집이 실패한다(검토 F7). 그래서 홉은 사용량(상한
        24/리다이렉트 상한)으로만 제한하고, 모델 재시도 예산과 섞지 않는다.
        """
        with self.lock:
            if self.deadline_enforced and self.deadline_passed(now):
                return False, (
                    f"전체 실행 기한({self.limits.deadline_seconds}초)이 지나 더 보내지 않습니다."
                )
            if request_class == RequestClass.API.value:
                if self.api_used + 1 > self.limits.api_requests:
                    return False, (
                        f"API 요청 예산({self.limits.api_requests}회)을 모두 사용했습니다."
                    )
                self.api_used += 1
                return True, None
            if self.model_used + 1 > self.effective_model_requests():
                return False, (
                    f"모델 요청 예산({self.effective_model_requests()}회)을 모두 사용했습니다."
                )
            self.model_used += 1
            return True, None

    def release_reserved(
        self, count: int, request_class: str = RequestClass.API.value
    ) -> int:
        """예약했지만 실제로 보내지 않은 전송 몫을 반환한다. 시도 수는 건드리지 않는다."""
        if count <= 0:
            return 0
        with self.lock:
            if request_class == RequestClass.API.value:
                taken = min(int(count), self.api_used)
                self.api_used -= taken
                return taken
            taken = min(int(count), self.model_used)
            self.model_used -= taken
            return taken

    def refund(self, logical_call_id: str, request_class: str, count: int) -> int:
        """**예약했지만 보내지 않은** 전송 몫을 되돌린다.

        리다이렉트 홉을 미리 예약하고 실제로 쓴 만큼만 남기는 경로에서 쓴다. 상한을
        늘리지 않으며, 이미 쓴 몫을 되돌리지 않는다(`used`가 0 밑으로 내려가지 않는다).
        """
        if count <= 0:
            return 0
        with self.lock:
            if request_class == RequestClass.API.value:
                taken = min(int(count), self.api_used)
                self.api_used -= taken
            else:
                taken = min(int(count), self.model_used)
                self.model_used -= taken
            used = self.attempts_used(logical_call_id)
            if used:
                self.attempts_by_call[logical_call_id] = max(0, used - taken)
            return taken

    def snapshot(self) -> dict[str, Any]:
        """화면·보고서에 쓰는 예산 상태. 남은 값을 0으로 꾸며 채우지 않는다."""
        return {
            "model_requests": self.effective_model_requests(),
            "model_used": self.model_used,
            "model_remaining": self.remaining(),
            "model_reserved_for_unstarted_steps": self.reserved_model_requests(),
            "api_requests": self.limits.api_requests,
            "api_used": self.api_used,
            "api_remaining": self.remaining(RequestClass.API.value),
            # HTTP 로직별 보호 몫 상태. 보호 몫 정책을 쓰지 않는 실행에서는 비운다.
            "http_owner_quotas": self.http_owner_quotas,
            "http_total_limit": self._http_total_limit(),
            "http_shared_used": self.http_shared_used,
            "http_owners": (
                {
                    owner: {
                        "used": self.http_owner_used(owner),
                        "local_share": HTTP_LOCAL_SHARE,
                        "local_left": max(
                            0, HTTP_LOCAL_SHARE - self.http_owner_used(owner)
                        ),
                        "shared_used": self._http_shared_used_for(owner),
                    }
                    for owner in HTTP_OWNERS
                }
                if self.http_owner_quotas
                else {}
            ),
            "attempts_per_call": self.limits.attempts_per_call,
            "deadline_seconds": self.limits.deadline_seconds,
            "deadline_enforced": self.deadline_enforced,
            "seconds_left": (
                None
                if self.seconds_left() == float("inf")
                else round(self.seconds_left(), 3)
            ),
            "registered_calls": list(self.registered_calls),
            "cancelled_calls": list(self.cancelled_calls),
            "module_send_cap": self.module_send_cap,
            "module_ids": list(self.module_ids),
            "module_quota_total": (
                self.module_send_cap * len(self.module_ids)
                if self.module_send_cap is not None and self.module_ids
                else None
            ),
            "prior_module_usage": dict(self.prior_module_usage),
            "sent_by_module": dict(self.sent_by_module),
            "reservations_returned": len(self.cancelled_calls),
            "normal_model_calls": self.limits.normal_model_calls,
            "stopped_reason": self.stopped_reason,
        }


class ConcurrencyGate:
    """실행 합계 동시 요청 상한(모델 2, API 2).

    MP-04의 실행은 순차이므로 이 게이트는 상한을 넘겨 호출하는 실수를 즉시 드러내는
    용도다. 스레드에서 동시에 쓰더라도 상한을 넘지 않게 잠금을 함께 쓴다.
    """

    def __init__(self, limit: int, *, label: str) -> None:
        if limit <= 0:
            raise ValueError("a concurrency limit must be positive")
        self._limit = limit
        self._label = label
        self._active = 0
        self._lock = threading.Lock()
        self.peak = 0

    @property
    def limit(self) -> int:
        return self._limit

    def __enter__(self) -> "ConcurrencyGate":
        with self._lock:
            if self._active + 1 > self._limit:
                raise BudgetExceeded(
                    f"{self._label} 동시 요청 상한({self._limit})을 넘을 수 없습니다."
                )
            self._active += 1
            self.peak = max(self.peak, self._active)
        return self

    def __exit__(self, *exc_info: object) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)


class ConcurrencyLimiter:
    """실제 전송 동시 수를 **기다리며** 제한한다(모델 2, API 2).

    `ConcurrencyGate`는 상한 초과를 즉시 드러내는 검사용이고, 이쪽은 전체 프리뷰의
    병렬 갈래가 셋 이상일 때 실제로 줄을 세우는 용도다. 예산은 줄을 서는 동안에도
    그대로 세므로, 대기했다고 호출 수가 늘지 않는다.
    """

    def __init__(self, limit: int, *, label: str) -> None:
        if limit <= 0:
            raise ValueError("a concurrency limit must be positive")
        self._limit = limit
        self._label = label
        self._semaphore = threading.BoundedSemaphore(limit)
        self._lock = threading.Lock()
        self._active = 0
        self.peak = 0

    @property
    def limit(self) -> int:
        return self._limit

    def __enter__(self) -> "ConcurrencyLimiter":
        self._semaphore.acquire()
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
        return self

    def __exit__(self, *exc_info: object) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)
        self._semaphore.release()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"label": self._label, "limit": self._limit, "peak": self.peak}


def sleep_seconds(seconds: float) -> None:  # pragma: no cover - 기본 sleeper
    """기본 대기. 테스트는 sleeper를 주입해 실제로 기다리지 않는다."""
    if seconds > 0:
        time.sleep(seconds)


def budget_from_limits(limits: Mapping[str, Any] | None) -> BudgetLimits:
    """저장된 `preview_runs.limits`에서 예산 상한을 복원한다. 모르는 값은 기본값."""
    data = dict(limits or {})
    overrides = {
        key: data[key]
        for key in (
            "model_requests",
            "api_requests",
            "attempts_per_call",
            "deadline_seconds",
        )
        if isinstance(data.get(key), int) and data[key] >= 0
    }
    return plan_limits(**overrides)
