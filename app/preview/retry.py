"""MP-04 공통 실행 예산과 재시도 정책.

계획 §5(`docs/superpowers/plans/2026-11-10-match-preview.md`)의 초기 개발 설정을
그대로 옮긴다. 값을 여기저기 복사하지 않고 이 파일 한 곳에서만 정한다.

| 항목 | 값 |
|---|---|
| 전체 프리뷰 모델 요청 예산 | 재시도·출력 수정 포함 8회 |
| 정상 경로 모델 호출 | 조사 3 + 종합 1 = 4회 (그래서 재시도 여유는 4회) |
| D0 외부 API 요청 예산 | 재시도 포함 24회 |
| 논리 호출 최대 시도 | 최초 포함 3회 |
| 모델 동시 요청 | 실행 합계 2 |
| API 동시 요청 | 실행 합계 2 |
| 모델 응답 대기 상한 | 300초 |
| 축구 API 요청 상한 | 30초 |
| 전체 실행 기한 | 접수 후 1,800초 (대기 포함) |
| 대기 | 유효한 Retry-After 우선, 없으면 1초부터 지수 증가, 무작위 지연 포함 60초 상한 |

설계 원칙:

- 재시도와 예산을 소유하는 실행기는 **하나**다. LangGraph 노드 재시도나 제공자
  SDK 재시도를 함께 켜서 실제 호출 수가 배로 늘게 두지 않는다. 그래서 SDK 재시도는
  끄거나(전송 계층) 시도 기록에 포함되는지 확인해야 한다.
- 남은 예산은 "아직 시작하지 않은 필수 단계의 최초 호출 몫"을 먼저 남긴다. 앞 단계의
  재시도가 뒤 단계의 첫 호출을 굶기지 않게 하기 위함이다.
- 기한은 대기 시간까지 포함한다. 대기 후 남은 시간이 없으면 재시도하지 않는다.
- 401·403 같은 영구 오류는 같은 요청을 다시 보내지 않는다. 429는 재시도 대상이며,
  실패한 시도와 성공한 시도를 모두 남긴다(성공만 골라 제출하지 않는다).
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Mapping

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
    "NORMAL_MODEL_CALLS",
    "RETRY_BASE_DELAY_SECONDS",
    "RETRY_MAX_DELAY_SECONDS",
    "RUN_DEADLINE_SECONDS",
    "RetryDecision",
    "RunBudget",
    "bounded_wait_seconds",
    "classify_attempt",
    "plan_limits",
]

# --- 계획 §5 값 ------------------------------------------------------------

MODEL_REQUEST_BUDGET = 8
# 정상 경로 모델 호출 수. 전체 프리뷰는 조사 4(R1·R2·R3·R4) + 종합 1 = 5회다.
# 상한(총 8)은 그대로 두고, 재시도 여유만 3회로 줄어든다. 조용히 늘리지 않는다.
NORMAL_MODEL_CALLS = 5  # 조사 4 + 종합 1
API_REQUEST_BUDGET = 24
MAX_ATTEMPTS_PER_CALL = 3
MODEL_CONCURRENCY = 2
API_CONCURRENCY = 2
MODEL_TIMEOUT_SECONDS = 300
API_TIMEOUT_SECONDS = 30
RUN_DEADLINE_SECONDS = 1800
RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 60.0

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
    attempts_by_call: dict[str, int] = field(default_factory=dict)
    registered_calls: list[str] = field(default_factory=list)
    stopped_reason: str | None = None
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
            "stopped_reason": self.stopped_reason,
        }

    # -- 시간 -------------------------------------------------------------

    @property
    def deadline(self) -> datetime:
        return self.started_at + timedelta(seconds=self.limits.deadline_seconds)

    def elapsed_seconds(self, now: datetime | None = None) -> float:
        return max(0.0, ((now or _utcnow()) - self.started_at).total_seconds())

    def seconds_left(self, now: datetime | None = None) -> float:
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

    def unstarted_calls(self) -> int:
        return max(0, self.limits.normal_model_calls - len(self.registered_calls))

    def reserved_model_requests(self) -> int:
        """아직 시작하지 않은 정상 호출의 첫 시도 몫. 재시도는 이 몫을 침범하지 않는다."""
        return self.unstarted_calls()

    def remaining(self, request_class: str = RequestClass.MODEL.value) -> int:
        if request_class == RequestClass.API.value:
            return max(0, self.limits.api_requests - self.api_used)
        return max(0, self.limits.model_requests - self.model_used)

    def attempts_used(self, logical_call_id: str) -> int:
        return int(self.attempts_by_call.get(logical_call_id, 0))

    # -- 판정 -------------------------------------------------------------

    def can_attempt(
        self,
        logical_call_id: str,
        request_class: str = RequestClass.MODEL.value,
        *,
        now: datetime | None = None,
    ) -> tuple[bool, str | None]:
        """다음 시도를 보낼 수 있는지. 거부 사유는 화면에 그대로 보여줄 수 있는 문장이다."""
        if self.attempts_used(logical_call_id) >= self.limits.attempts_per_call:
            return False, (
                f"논리 호출 {logical_call_id}의 시도 상한"
                f"({self.limits.attempts_per_call}회)에 도달했습니다."
            )
        if self.deadline_passed(now):
            return False, (
                f"전체 실행 기한({self.limits.deadline_seconds}초)이 지나 더 보내지 않습니다."
            )
        if request_class == RequestClass.API.value:
            if self.api_used + 1 > self.limits.api_requests:
                return False, (
                    f"API 요청 예산({self.limits.api_requests}회)을 모두 사용했습니다."
                )
            return True, None
        reserved = self.reserved_model_requests()
        if self.model_used + 1 > self.limits.model_requests - reserved:
            return False, (
                f"모델 요청 예산({self.limits.model_requests}회) 중 아직 시작하지 않은"
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

    def snapshot(self) -> dict[str, Any]:
        """화면·보고서에 쓰는 예산 상태. 남은 값을 0으로 꾸며 채우지 않는다."""
        return {
            "model_requests": self.limits.model_requests,
            "model_used": self.model_used,
            "model_remaining": self.remaining(),
            "model_reserved_for_unstarted_steps": self.reserved_model_requests(),
            "api_requests": self.limits.api_requests,
            "api_used": self.api_used,
            "api_remaining": self.remaining(RequestClass.API.value),
            "attempts_per_call": self.limits.attempts_per_call,
            "deadline_seconds": self.limits.deadline_seconds,
            "seconds_left": round(self.seconds_left(), 3),
            "registered_calls": list(self.registered_calls),
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
