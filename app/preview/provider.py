"""MP-04 제공자 어댑터와 공통 시도 기록.

이 파일이 책임지는 것:

- `execute_request(RequestSpec, ExecutionContext, ...)` — 요청 하나를 실제로 보내고,
  논리 호출·시도 순번·원문 요청/응답·오류·사용량·버전 링크를 `preview_dev`에 남긴다.
- 모델(Google Gen AI SDK + Vertex)과 축구 API가 **같은** 예산·시도 규칙을 쓴다.
- `request_model(...)` — 모듈이 모델을 부를 때 거치는 유일한 통로.
- `replay_result(...)` — 저장된 응답으로 변환만 다시 한다. 외부 호출 0회.

정직성 규칙:

- 설정이 없으면 호출하지 않는다. `configuration_error`로 남기고 실행을 실패시킨다.
  빈 응답을 성공이나 "자료 없음"으로 바꾸지 않는다.
- 응답을 보존하기 전에 중단된 경우 `outcome='unknown'`이다. 성공으로 세지 않는다.
- 사용량을 제공자가 주지 않으면 `None`이다. 0으로 채우지 않는다.
- 재시도는 이 모듈 **한 곳**에서만 판단한다. SDK 재시도는 명시적으로 끈다
  (`google-genai`의 `HttpRetryOptions(attempts=1)`). 그래야 실제 호출 수와 기록이
  같아진다.
- 모의(mock)·재생(replay) transport는 네트워크를 열지 않는다. 기록의 `mode`도
  그대로 mock/replay로 남아 live 성공과 섞이지 않는다.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.preview import artifacts as artifact_store
from app.preview import store
from app.preview.models import PreviewArtifact, PreviewAttempt, PreviewModuleExecution, PreviewResult
from app.preview.contracts import (
    PROVIDER_CONTRACT_VERSION,
    AttemptOutcome,
    ExecutionContext,
    ModuleResult,
    ModuleStatus,
    ProviderResponse,
    ProviderUsage,
    QualityStatus,
    RequestClass,
    RequestSpec,
    RunMode,
)
from app.preview.retry import (
    RetryDecision,
    RunBudget,
    bounded_wait_seconds,
    classify_attempt,
    sleep_seconds,
)

__all__ = [
    "AttemptRecord",
    "ConfigurationUnavailable",
    "ExecuteRequestResult",
    "GoogleGenAIHttpTransport",
    "HttpApiTransport",
    "HttpResponse",
    "ProviderTransport",
    "RecordedTransport",
    "ReplayOutcome",
    "ReplayTransport",
    "TransportResult",
    "execute_request",
    "extract_text",
    "extract_usage",
    "model_configuration_status",
    "replay_result",
    "request_model",
]

# 원문에 비밀값이 섞여 들어왔을 때 지울 이름. 값은 여기 적지 않는다.
SECRET_REFS = ("google_application_credentials_json", "api_football_key")


class ConfigurationUnavailable(RuntimeError):
    """설정이 없어 호출을 시작할 수 없다. 요청을 실제로 보내지 않았다는 뜻이다.

    화면·보고서에 그대로 보여줄 실제 사유를 담는다. "자료를 못 찾음" 같은 다른
    실패로 바꾸지 않는다.
    """


# --------------------------------------------------------------------------
# 전송 계층
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TransportResult:
    """전송 계층이 돌려주는 원시 결과. 정규화는 `execute_request`가 한다."""

    http_status: int | None
    raw_request: Any
    raw_response: Any
    provider_request_id: str | None = None
    usage: Mapping[str, Any] | None = None
    error_class: str | None = None
    error_message: str | None = None
    # 요청이 제공자에 도달했는지 확신할 수 없으면 True. outcome은 unknown이 된다.
    outcome_unknown: bool = False
    retry_after_seconds: float | None = None
    duration_ms: int | None = None


class ProviderTransport(Protocol):
    """요청 하나를 보내는 최소 계약. 테스트는 가짜 transport를 주입한다."""

    provider: str
    mode: RunMode
    request_class: RequestClass

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout_seconds: int,
        context: ExecutionContext,
    ) -> TransportResult: ...


@dataclass(frozen=True)
class HttpResponse:
    """HTTP 응답의 최소 표현. 원문 본문을 그대로 보존한다."""

    status_code: int
    body: Any
    headers: Mapping[str, str] = field(default_factory=dict)

    @property
    def retry_after_seconds(self) -> float | None:
        raw = self.headers.get("retry-after") or self.headers.get("Retry-After")
        if not raw:
            return None
        try:
            return max(0.0, float(raw))
        except (TypeError, ValueError):
            return None


def _api_error_class(status: int) -> str:
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "authentication_error"
    if 400 <= status < 500:
        return "invalid_request"
    return "provider_error"


class HttpApiTransport:
    """축구 API 같은 일반 HTTP JSON 호출. 숨은 재시도를 하지 않는다.

    `send_func`를 주입할 수 있어 테스트가 실제 네트워크 없이 429→성공을 재현한다.
    """

    request_class = RequestClass.API

    def __init__(
        self,
        *,
        provider: str,
        send_func: Callable[[RequestSpec, int], HttpResponse],
        mode: RunMode = RunMode.LIVE,
        endpoint: str | None = None,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self._send = send_func
        self.endpoint = endpoint

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout_seconds: int,
        context: ExecutionContext,
    ) -> TransportResult:
        request_body = {
            "endpoint": self.endpoint or spec.endpoint,
            "parameters": dict(spec.parameters),
            "timeout_seconds": timeout_seconds,
            "mode": self.mode.value,
        }
        started = time.monotonic()
        try:
            response = self._send(spec, timeout_seconds)
        except TimeoutError as exc:
            return TransportResult(
                http_status=None,
                raw_request=request_body,
                raw_response=None,
                error_class="transport_timeout",
                error_message=str(exc) or "request timed out",
                outcome_unknown=True,
            )
        except OSError as exc:
            return TransportResult(
                http_status=None,
                raw_request=request_body,
                raw_response=None,
                error_class="transport_error",
                error_message=str(exc),
                outcome_unknown=True,
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        ok = 200 <= response.status_code < 300
        return TransportResult(
            http_status=response.status_code,
            raw_request=request_body,
            raw_response=response.body,
            error_class=None if ok else _api_error_class(response.status_code),
            error_message=None if ok else f"HTTP {response.status_code}",
            retry_after_seconds=response.retry_after_seconds,
            duration_ms=duration_ms,
        )


class GoogleGenAIHttpTransport:
    """Google Gen AI SDK + Vertex AI 실제 호출 어댑터.

    확인한 배포 설정(2026-11-10, `koyeb deployments get <active>`의 env 키 이름):
    `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `VERTEX_AI_MODEL`,
    `GOOGLE_APPLICATION_CREDENTIALS_JSON`(secret). 이 앱은 그 값을 복사하지 않고
    `PREVIEW_MODEL_*` 환경에서 읽는다. 값은 출력·기록하지 않는다.

    SDK 재시도는 끈다(`HttpRetryOptions(attempts=1)`). 재시도·예산은
    `execute_request` 하나만 소유한다.
    """

    request_class = RequestClass.MODEL
    provider = "vertex"

    def __init__(
        self,
        *,
        project: str | None,
        location: str | None,
        model: str | None,
        credentials_json: str | None,
        mode: RunMode = RunMode.LIVE,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.mode = mode
        self.project = project
        self.location = location
        self.model = model
        self._credentials_json = credentials_json
        self._client_factory = client_factory
        self._client: Any | None = None

    # -- 설정 확인 --------------------------------------------------------

    def configuration_problem(self) -> str | None:
        """호출 전에 확인하는 설정. 문제가 있으면 화면에 보여줄 문장을 준다."""
        if not self.project:
            return (
                "Google Cloud 프로젝트가 설정되지 않아 실제 모델을 호출할 수 없습니다."
                " PREVIEW_MODEL_PROJECT가 필요합니다."
            )
        if not self.location:
            return (
                "Google Cloud 위치(리전)가 설정되지 않았습니다."
                " PREVIEW_MODEL_LOCATION이 필요합니다."
            )
        if not self.model:
            return (
                "모델 이름이 설정되지 않았습니다. 배포 설정의 VERTEX_AI_MODEL 값을"
                " 확인해 PREVIEW_MODEL_NAME으로 지정해야 합니다."
            )
        if not (self._credentials_json or self._client_factory):
            return (
                "서비스 계정 자격 증명이 없어 실제 모델을 호출할 수 없습니다."
                " GOOGLE_APPLICATION_CREDENTIALS_JSON에 해당하는 값을"
                " PREVIEW_MODEL_CREDENTIALS_JSON으로 제공해야 합니다."
            )
        return None

    def _build_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client

        from google import genai
        from google.genai import types

        credentials = None
        if self._credentials_json:
            from google.oauth2 import service_account

            info = json.loads(self._credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        options = types.HttpOptions(
            # 재시도를 끈다. 이 실행기만 재시도를 소유한다.
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        self._client = genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
            credentials=credentials,
            http_options=options,
        )
        return self._client

    # -- 전송 -------------------------------------------------------------

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout_seconds: int,
        context: ExecutionContext,
    ) -> TransportResult:
        problem = self.configuration_problem()
        if problem:
            raise ConfigurationUnavailable(problem)

        from google.genai import errors, types

        parameters = dict(spec.parameters or {})
        contents = parameters.get("contents")
        generation = dict(parameters.get("generation_config") or {})
        request_body = {
            "provider": self.provider,
            "model": self.model,
            "project": self.project,
            "location": self.location,
            "contents": contents,
            "generation_config": generation,
            "timeout_seconds": timeout_seconds,
            # 인증 값은 본문에 넣지 않는다. 아티팩트에도 남기지 않는다.
            "auth": "service_account(redacted)",
        }

        client = self._build_client()
        config = types.GenerateContentConfig(**generation) if generation else None
        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except errors.APIError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            payload = getattr(exc, "response_json", None)
            return TransportResult(
                http_status=status or None,
                raw_request=request_body,
                raw_response=payload,
                error_class=_api_error_class(status) if status else "provider_error",
                error_message=str(getattr(exc, "message", "") or exc)[:2000],
                retry_after_seconds=_retry_after_from_payload(payload),
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except (TimeoutError, OSError) as exc:
            # 요청은 나갔을 수 있으나 응답을 보존하지 못했다 → unknown.
            return TransportResult(
                http_status=None,
                raw_request=request_body,
                raw_response=None,
                error_class="transport_timeout"
                if isinstance(exc, TimeoutError)
                else "transport_error",
                error_message=str(exc)[:2000],
                outcome_unknown=True,
            )
        return TransportResult(
            http_status=200,
            raw_request=request_body,
            raw_response=json.loads(response.model_dump_json(exclude_none=True)),
            provider_request_id=getattr(response, "response_id", None),
            usage=_usage_from_genai(response),
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _retry_after_from_payload(payload: Any) -> float | None:
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    if not isinstance(error, Mapping):
        return None
    details = error.get("details")
    if not isinstance(details, Sequence):
        return None
    for entry in details:
        if isinstance(entry, Mapping) and str(entry.get("@type", "")).endswith("RetryInfo"):
            delay = str(entry.get("retryDelay", ""))
            if delay.endswith("s"):
                try:
                    return float(delay[:-1])
                except ValueError:
                    return None
    return None


def _usage_from_genai(response: Any) -> dict[str, Any] | None:
    """SDK 응답의 사용량. 없으면 `None`이며 0으로 채우지 않는다."""
    metadata = getattr(response, "usage_metadata", None)
    if metadata is None:
        return None
    return {
        "input_tokens": getattr(metadata, "prompt_token_count", None),
        "output_tokens": getattr(metadata, "candidates_token_count", None),
        # SDK가 검색 질의 수를 따로 주지 않으면 unknown이다.
        "search_queries": None,
    }


class RecordedTransport:
    """모의 transport. 네트워크를 열지 않고 준비된 응답을 순서대로 돌려준다.

    429 뒤 성공 같은 재시도 흐름을 실제 네트워크 없이 재현하되, 기록에는
    `mode='mock'`으로 남는다. 이 기록을 실제 제공자 성공률로 인용하지 않는다.
    """

    def __init__(
        self,
        *,
        script: Sequence[TransportResult],
        provider: str = "mock-transport",
        mode: RunMode = RunMode.MOCK,
        request_class: RequestClass = RequestClass.MODEL,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self.request_class = request_class
        self._script = list(script)
        self.calls: list[RequestSpec] = []

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout_seconds: int,
        context: ExecutionContext,
    ) -> TransportResult:
        self.calls.append(spec)
        if not self._script:
            raise AssertionError("recorded transport ran out of scripted responses")
        return self._script.pop(0)


class ReplayTransport:
    """저장된 응답 재생 transport. 이 객체는 외부 연결을 만들지 않는다."""

    def __init__(
        self,
        *,
        stored: TransportResult,
        provider: str = "stored-response",
        mode: RunMode = RunMode.REPLAY,
        request_class: RequestClass = RequestClass.MODEL,
    ) -> None:
        self.provider = provider
        self.mode = mode
        self.request_class = request_class
        self._stored = stored
        self.calls: list[RequestSpec] = []

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout_seconds: int,
        context: ExecutionContext,
    ) -> TransportResult:
        self.calls.append(spec)
        return self._stored


# --------------------------------------------------------------------------
# 원문 추출
# --------------------------------------------------------------------------


def extract_text(raw_response: Any) -> str | None:
    """수신 원문에서 모델 텍스트만 뽑는다. 없으면 `None`(빈 문자열을 만들지 않는다)."""
    if isinstance(raw_response, str) and raw_response.strip():
        return raw_response.strip()
    if not isinstance(raw_response, Mapping):
        return None
    candidates = raw_response.get("candidates")
    if isinstance(candidates, Sequence):
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            content = candidate.get("content")
            if not isinstance(content, Mapping):
                continue
            parts = content.get("parts")
            if not isinstance(parts, Sequence):
                continue
            texts = [
                str(part.get("text"))
                for part in parts
                if isinstance(part, Mapping) and part.get("text")
            ]
            if texts:
                return "\n".join(texts).strip()
    return None


def extract_usage(usage: Mapping[str, Any] | None) -> ProviderUsage | None:
    """제공자가 준 사용량을 그대로 옮긴다. 없는 값은 `None`으로 남긴다."""
    if not usage:
        return None
    return ProviderUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        search_queries=usage.get("search_queries"),
    )


# --------------------------------------------------------------------------
# 공통 실행
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AttemptRecord:
    """한 시도의 요약. 저장된 행과 같은 값을 갖는다."""

    attempt_id: uuid.UUID
    logical_call_id: str
    attempt_ordinal: int
    outcome: AttemptOutcome
    http_status: int | None
    error_class: str | None
    error_message: str | None
    wait_ms: int | None
    request_artifact_id: uuid.UUID | None
    response_artifact_id: uuid.UUID | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": str(self.attempt_id),
            "logical_call_id": self.logical_call_id,
            "attempt_ordinal": self.attempt_ordinal,
            "outcome": self.outcome.value,
            "http_status": self.http_status,
            "error_class": self.error_class,
            "error_message": self.error_message,
            "wait_ms": self.wait_ms,
            "request_artifact_id": str(self.request_artifact_id)
            if self.request_artifact_id
            else None,
            "response_artifact_id": str(self.response_artifact_id)
            if self.response_artifact_id
            else None,
        }


@dataclass(frozen=True)
class ExecuteRequestResult:
    """논리 호출 하나의 결론과 그 근거."""

    spec: RequestSpec
    response: ProviderResponse
    attempts: tuple[AttemptRecord, ...]
    budget: Mapping[str, Any]
    text: str | None = None
    stopped_reason: str | None = None
    missing_configuration: str | None = None

    @property
    def ok(self) -> bool:
        return self.response.outcome is AttemptOutcome.OK

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _attempt_timeout(
    spec: RequestSpec,
    *,
    request_class: RequestClass,
    budget: RunBudget,
    moment: datetime,
) -> int:
    """실제 요청 제한. 계획 §5 상한과 남은 실행 기한 중 짧은 쪽."""
    from app.preview.retry import API_TIMEOUT_SECONDS, MODEL_TIMEOUT_SECONDS

    ceiling = API_TIMEOUT_SECONDS if request_class is RequestClass.API else MODEL_TIMEOUT_SECONDS
    declared = spec.timeout_seconds
    timeout = min(ceiling, declared) if declared else ceiling
    return max(1, int(min(timeout, max(1.0, budget.seconds_left(moment)))))


def execute_request(
    spec: RequestSpec,
    context: ExecutionContext,
    *,
    transport: ProviderTransport,
    budget: RunBudget,
    session: Session | None = None,
    actor_id: int | None = None,
    max_attempts: int | None = None,
    sleeper: Callable[[float], None] = sleep_seconds,
    rng: Callable[[], float] | None = None,
    now: Callable[[], datetime] = _now,
    secret_values: Sequence[str] = (),
    module_execution_id: uuid.UUID | None = None,
) -> ExecuteRequestResult:
    """요청 하나를 예산·기한·시도 규칙 안에서 보낸다.

    - 실제 시도마다 한 행을 남긴다. 실패한 시도도 지우지 않는다.
    - `attempt_ordinal`은 0부터 시작한다. 0이 아닌 시도가 재시도다.
    - 기한을 넘기는 대기는 하지 않는다.
    - 설정 부족은 요청을 보내지 않았지만 시도 행으로 남겨, 왜 실패했는지 보이게 한다.
    """
    request_class = transport.request_class
    attempt_limit = max_attempts or budget.limits.attempts_per_call
    picks = rng or (lambda: 0.5)
    budget.register_call(spec.logical_call_id)

    attempts: list[AttemptRecord] = []
    final_response: ProviderResponse | None = None
    final_text: str | None = None
    stopped_reason: str | None = None
    missing_configuration: str | None = None
    ordinal = 0
    wait_seconds = 0.0

    while True:
        moment = now()
        allowed, reason = budget.can_attempt(
            spec.logical_call_id, request_class.value, now=moment
        )
        if not allowed:
            stopped_reason = reason
            break
        if ordinal >= attempt_limit:
            stopped_reason = (
                f"논리 호출 {spec.logical_call_id}의 시도 상한({attempt_limit}회)에"
                " 도달했습니다."
            )
            break

        budget.charge(spec.logical_call_id, request_class.value, now=moment)
        timeout_seconds = _attempt_timeout(
            spec, request_class=request_class, budget=budget, moment=moment
        )

        try:
            outcome = transport.send(
                spec, timeout_seconds=timeout_seconds, context=context
            )
        except ConfigurationUnavailable as exc:
            # 요청을 실제로 보내지 않았다. 그러나 시도로 남겨 원인을 보이게 한다.
            missing_configuration = str(exc)
            attempt = _record_attempt(
                session,
                spec=spec,
                context=context,
                ordinal=ordinal,
                provider=transport.provider,
                mode=transport.mode,
                outcome=AttemptOutcome.ERROR,
                http_status=None,
                error_class="configuration_error",
                error_message=str(exc),
                wait_ms=int(wait_seconds * 1000) if wait_seconds else None,
                request_body={
                    "endpoint": spec.endpoint,
                    "provider": transport.provider,
                    "model": spec.model,
                    "parameters": dict(spec.parameters),
                    "not_sent": True,
                    "reason": str(exc),
                },
                response_body=None,
                usage=None,
                started_at=moment,
                finished_at=now(),
                actor_id=actor_id,
                module_execution_id=module_execution_id,
                secret_values=secret_values,
                request_class=request_class,
            )
            attempts.append(attempt)
            final_response = ProviderResponse(
                attempt_id=attempt.attempt_id,
                outcome=AttemptOutcome.ERROR,
                http_status=None,
                error_class="configuration_error",
                error_message=str(exc),
                received_at=now(),
            )
            stopped_reason = str(exc)
            break

        finished = now()
        outcome_value = _outcome_of(outcome)
        attempt = _record_attempt(
            session,
            spec=spec,
            context=context,
            ordinal=ordinal,
            provider=transport.provider,
            mode=transport.mode,
            outcome=outcome_value,
            http_status=outcome.http_status,
            error_class=outcome.error_class,
            error_message=outcome.error_message,
            wait_ms=int(wait_seconds * 1000) if wait_seconds else None,
            request_body=outcome.raw_request,
            response_body=outcome.raw_response,
            usage=outcome.usage,
            started_at=moment,
            finished_at=finished,
            actor_id=actor_id,
            module_execution_id=module_execution_id,
            secret_values=secret_values,
            request_class=request_class,
        )
        attempts.append(attempt)

        final_response = ProviderResponse(
            attempt_id=attempt.attempt_id,
            outcome=outcome_value,
            http_status=outcome.http_status,
            provider_request_id=outcome.provider_request_id,
            raw_artifact_id=attempt.response_artifact_id,
            error_class=outcome.error_class,
            error_message=outcome.error_message,
            usage=extract_usage(outcome.usage),
            duration_ms=outcome.duration_ms
            if outcome.duration_ms is not None
            else max(0, int((finished - moment).total_seconds() * 1000)),
            received_at=finished,
        )
        if outcome_value is AttemptOutcome.OK:
            final_text = extract_text(outcome.raw_response)
            break

        decision = classify_attempt(
            outcome=outcome_value.value,
            http_status=outcome.http_status,
            error_class=outcome.error_class,
        )
        if decision is RetryDecision.STOP:
            stopped_reason = _stop_reason(outcome)
            break
        if ordinal + 1 >= attempt_limit:
            stopped_reason = (
                f"논리 호출 {spec.logical_call_id}의 시도 상한({attempt_limit}회)에"
                " 도달했습니다."
            )
            break

        wait_seconds = bounded_wait_seconds(
            ordinal,
            retry_after_seconds=outcome.retry_after_seconds,
            rng=picks,
        )
        if wait_seconds >= budget.seconds_left(now()):
            stopped_reason = (
                f"재시도 대기({wait_seconds:.1f}초)가 남은 실행 기한보다 길어"
                " 재시도하지 않았습니다."
            )
            break
        sleeper(wait_seconds)
        ordinal += 1

    if final_response is None:  # pragma: no cover - 첫 시도는 항상 기록된다
        raise RuntimeError("execute_request recorded no attempt")

    return ExecuteRequestResult(
        spec=spec,
        response=final_response,
        attempts=tuple(attempts),
        budget=budget.snapshot(),
        text=final_text,
        stopped_reason=stopped_reason,
        missing_configuration=missing_configuration,
    )


def _stop_reason(outcome: TransportResult) -> str:
    if outcome.error_message:
        return outcome.error_message
    if outcome.http_status is not None:
        return f"HTTP {outcome.http_status}"
    return "요청이 거부되어 재시도하지 않았습니다."


def _outcome_of(outcome: TransportResult) -> AttemptOutcome:
    if outcome.outcome_unknown:
        return AttemptOutcome.UNKNOWN
    if outcome.http_status is not None and 200 <= outcome.http_status < 300:
        return AttemptOutcome.OK
    if outcome.http_status is None and outcome.error_class is None:
        return AttemptOutcome.UNKNOWN
    return AttemptOutcome.ERROR


def _record_attempt(
    session: Session | None,
    *,
    spec: RequestSpec,
    context: ExecutionContext,
    ordinal: int,
    provider: str,
    mode: RunMode,
    outcome: AttemptOutcome,
    http_status: int | None,
    error_class: str | None,
    error_message: str | None,
    wait_ms: int | None,
    request_body: Any,
    response_body: Any,
    usage: Mapping[str, Any] | None,
    started_at: datetime,
    finished_at: datetime,
    actor_id: int | None,
    module_execution_id: uuid.UUID | None,
    secret_values: Sequence[str],
    request_class: RequestClass,
) -> AttemptRecord:
    """시도 한 건을 저장한다. 원문 요청·응답은 각각 아티팩트로 남긴다."""
    request_artifact_id: uuid.UUID | None = None
    response_artifact_id: uuid.UUID | None = None
    attempt_id = uuid.uuid4()

    if session is not None:
        request_artifact = artifact_store.save_artifact(
            session,
            run_id=context.run_id,
            kind=artifact_store.ArtifactKind.RAW_REQUEST,
            content=request_body,
            secret_values=secret_values,
            actor_id=actor_id,
            now=started_at,
        )
        request_artifact_id = request_artifact.id
        if response_body is not None:
            response_artifact = artifact_store.save_artifact(
                session,
                run_id=context.run_id,
                kind=artifact_store.ArtifactKind.RAW_RESPONSE,
                content=response_body,
                secret_values=secret_values,
                actor_id=actor_id,
                now=finished_at,
            )
            response_artifact_id = response_artifact.id

        row = store.append_attempt(
            session,
            run_id=context.run_id,
            module_execution_id=module_execution_id or context.module_execution_id,
            module_id=spec.module_id,
            logical_call_id=spec.logical_call_id,
            attempt_ordinal=ordinal,
            provider=provider,
            model=spec.model,
            mode=mode,
            operation=spec.operation or request_class.value,
            outcome=outcome.value,
            request_spec=spec.to_dict(),
            http_status=http_status,
            error_class=error_class,
            error_message=error_message,
            request_artifact_id=request_artifact_id,
            response_artifact_id=response_artifact_id,
            usage=dict(usage) if usage else None,
            wait_ms=wait_ms,
            started_at=started_at,
            finished_at=finished_at,
            actor_id=actor_id or 0,
        )
        attempt_id = row.id

    return AttemptRecord(
        attempt_id=attempt_id,
        logical_call_id=spec.logical_call_id,
        attempt_ordinal=ordinal,
        outcome=outcome,
        http_status=http_status,
        error_class=error_class,
        error_message=error_message,
        wait_ms=wait_ms,
        request_artifact_id=request_artifact_id,
        response_artifact_id=response_artifact_id,
    )


# --------------------------------------------------------------------------
# 모델 요청
# --------------------------------------------------------------------------


def request_model(
    *,
    logical_call_id: str,
    contents: Sequence[Mapping[str, Any]],
    context: ExecutionContext,
    transport: ProviderTransport,
    budget: RunBudget,
    session: Session | None = None,
    module_id: str | None = None,
    operation: str = "request_model",
    prompt_version: str | None = None,
    generation_config: Mapping[str, Any] | None = None,
    model_name: str | None = None,
    timeout_seconds: int | None = None,
    secret_values: Sequence[str] = (),
    module_execution_id: uuid.UUID | None = None,
    actor_id: int | None = None,
    sleeper: Callable[[float], None] = sleep_seconds,
    rng: Callable[[], float] | None = None,
    now: Callable[[], datetime] = _now,
) -> ExecuteRequestResult:
    """모델 요청 하나. `execute_request`를 통해서만 나가므로 예산·기록이 같다."""
    spec = RequestSpec(
        logical_call_id=logical_call_id,
        provider=getattr(transport, "provider", "vertex"),
        model=model_name or getattr(transport, "model", None),
        operation=operation,
        module_id=module_id,
        endpoint=None,
        parameters={
            "contents": [dict(item) for item in contents],
            "generation_config": dict(generation_config or {}),
        },
        prompt_version=prompt_version,
        contract_version=PROVIDER_CONTRACT_VERSION,
        timeout_seconds=timeout_seconds,
        secret_refs=SECRET_REFS,
    )
    return execute_request(
        spec,
        context,
        transport=transport,
        budget=budget,
        session=session,
        actor_id=actor_id,
        sleeper=sleeper,
        rng=rng,
        now=now,
        secret_values=secret_values,
        module_execution_id=module_execution_id,
    )


def model_configuration_status(transport: ProviderTransport) -> dict[str, Any]:
    """화면에 보여줄 실제 모델 설정 상태. 값이 아니라 '설정됨/없음'만 낸다."""
    checker = getattr(transport, "configuration_problem", None)
    problem = checker() if callable(checker) else None
    mode = getattr(transport, "mode", RunMode.MOCK)
    return {
        "provider": getattr(transport, "provider", "unknown"),
        "mode": mode.value if isinstance(mode, RunMode) else str(mode),
        "configured": problem is None,
        "problem": problem,
    }


# --------------------------------------------------------------------------
# 저장 응답 재생 (외부 호출 0회)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayOutcome:
    """저장 응답 재생의 결론. 새 결과 버전 ID와 원본 링크를 남긴다."""

    run_id: uuid.UUID
    source_result_id: uuid.UUID
    new_result_id: uuid.UUID
    new_version: int
    raw_artifact_id: uuid.UUID | None
    external_calls: int = 0


def replay_result(
    session: Session,
    *,
    source_result_id: uuid.UUID,
    transform: Callable[[Any, Mapping[str, Any] | None], Mapping[str, Any]],
    actor_id: int = 0,
    now: datetime | None = None,
) -> ReplayOutcome:
    """저장된 원문으로 변환만 다시 한다. 외부 모델·API를 호출하지 않는다.

    무료 저장 응답 재생(`replay`)은 LangGraph 체크포인트의 재실행(time travel)과
    다른 동작이다. 이 함수는 원본 결과의 시도·아티팩트를 그대로 가리키는 새 결과
    버전을 만들고, 실제 외부 호출은 0회다.

    `transform`은 (저장된 원문, 이전 payload)를 받아 새 payload 조각
    (`claims`/`coverage`/`diagnostics`/`payload`)을 돌려준다.
    """
    previous = session.get(PreviewResult, source_result_id)
    if previous is None:
        raise store.RunNotFound(f"result {source_result_id} not found")
    execution = session.get(PreviewModuleExecution, previous.module_execution_id)
    if execution is None:  # pragma: no cover - 결과는 모듈 실행에 종속된다
        raise store.RunNotFound(
            f"module execution {previous.module_execution_id} not found"
        )

    previous_payload = dict(previous.payload or {})
    artifact_id_raw = previous_payload.get("transform_source_artifact_id") or (
        previous_payload.get("response_artifact_id")
    )
    artifact_id = uuid.UUID(str(artifact_id_raw)) if artifact_id_raw else None
    if artifact_id is None:
        attempt = session.scalars(
            select(PreviewAttempt)
            .where(PreviewAttempt.module_execution_id == previous.module_execution_id)
            .order_by(PreviewAttempt.attempt_ordinal.desc())
            .limit(1)
        ).first()
        artifact_id = attempt.response_artifact_id if attempt is not None else None

    raw_body: Any = None
    if artifact_id is not None:
        row = session.get(PreviewArtifact, artifact_id)
        if row is not None and row.body is not None:
            try:
                raw_body = json.loads(row.body)
            except (TypeError, ValueError):
                raw_body = row.body

    produced = transform(raw_body, previous_payload)
    moment = now or _now()

    payload: dict[str, Any] = {
        "replay_of_result_id": str(previous.id),
        "replay_of_version": previous.version,
        "replay_external_calls": 0,
        "replay_source_attempt_id": previous_payload.get("attempt_id"),
        "transform_source_artifact_id": str(artifact_id) if artifact_id else None,
        **dict(produced.get("payload") or {}),
    }
    module_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=previous.module_id,
        module_execution_id=previous.module_execution_id,
        run_id=previous.run_id,
        version=previous.version + 1,
        input_hash=previous.input_hash,
        status=ModuleStatus(previous.status),
        quality=QualityStatus(previous.quality),
        claims=tuple(produced.get("claims") or ()),
        coverage=tuple(produced.get("coverage") or ()),
        diagnostics=tuple(str(d) for d in produced.get("diagnostics") or ()),
        implementation_version=previous.implementation_version,
        prompt_version=previous.prompt_version,
        contract_version=previous.contract_version,
        created_at=moment,
        payload=payload,
    )
    saved = store.save_module_result(session, module_result, actor_id=actor_id)
    return ReplayOutcome(
        run_id=previous.run_id,
        source_result_id=previous.id,
        new_result_id=saved.id,
        new_version=saved.version,
        raw_artifact_id=artifact_id,
        external_calls=0,
    )


