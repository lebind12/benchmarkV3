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
from sqlalchemy.orm import Session, sessionmaker

from app.preview import artifacts as artifact_store
from app.preview import send_ledger
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
    RATE_LIMIT_MAX_SENDS,
    RetryDecision,
    RunBudget,
    bounded_wait_seconds,
    rate_limit_wait_seconds,
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
    "extract_finish_reason",
    "extract_usage",
    "model_configuration_status",
    "replay_result",
    "JournalRequiredForNetworkSend",
    "request_model",
    "sent_attempt_count",
    "transported_live",
    "transported_over_network",
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

    실제 네트워크로 나가는 어댑터다(`uses_network=True`). 장부 없이는 전송하지 않는다.
    `send_func`를 주입할 수 있어 테스트가 실제 네트워크 없이 429→성공을 재현한다.
    """

    is_recorded_transport = False
    uses_network = True
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
    # 실제 Vertex 호출이다. 기록·모의와 구분해 장부 요구 대상으로 표시한다.
    is_recorded_transport = False
    uses_network = True

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
            # google-genai의 APIError는 본문을 `details`, HTTP 응답을 `response`에 둔다.
            # 없는 `response_json`을 읽으면 오류 본문·RetryInfo가 버려진다(2026-11-19 조사).
            payload = _api_error_payload(exc)
            return TransportResult(
                http_status=status or None,
                raw_request=request_body,
                raw_response=payload,
                error_class=_api_error_class(status) if status else "provider_error",
                error_message=_api_error_message(exc, payload)[:2000],
                retry_after_seconds=_retry_after_from_payload(payload)
                or _retry_after_from_response(getattr(exc, "response", None)),
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


def _api_error_payload(exc: Any) -> Any:
    """SDK 오류에서 **오류 본문**을 꺼낸다. 비밀값은 담지 않는다.

    google-genai 3.0 `errors.APIError`는 본문을 `details`, HTTP 응답을 `response`에
    저장하며 `response_json` 속성을 만들지 않는다. 둘 중 실제로 있는 값을 쓴다.
    """
    details = getattr(exc, "details", None)
    if isinstance(details, Mapping):
        return details
    response = getattr(exc, "response", None)
    for value in (
        getattr(response, "json", None),
        getattr(getattr(exc, "body", None), "json", None),
    ):
        if callable(value):
            try:
                parsed = value()
            except Exception:  # noqa: BLE001 - 오류 본문 파싱 실패는 오류 기록을 막지 않는다
                continue
            if isinstance(parsed, Mapping):
                return parsed
    return None


def _api_error_message(exc: Any, payload: Any) -> str:
    """SDK 오류의 사람이 읽을 메시지. 본문의 message가 있으면 그것을 우선한다."""
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping):
            text = error.get("message")
            if isinstance(text, str) and text.strip():
                return text
    return str(getattr(exc, "message", "") or exc)


def _retry_after_from_response(response: Any) -> float | None:
    """HTTP 응답의 `Retry-After` 헤더. 숫자 초 형식만 해석한다."""
    if response is None:
        return None
    headers = getattr(response, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    for key, value in headers.items():
        if str(key).lower() == "retry-after":
            try:
                return float(str(value).strip())
            except (TypeError, ValueError):
                return None
    return None


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

    429 뒤 성공 같은 재시도 흐름을 실제 네트워크 없이 재현하되, 기록에는 `mode`가
    그대로 남는다. 이 기록을 실제 제공자 성공률로 인용하지 않는다.

    `mode=live`로 만들 수 있지만 **네트워크로 나가지 않는다**. 그래서 장부 요구 대상이
    아니다(`is_recorded_transport=True`). 기록 실행에 장부를 요구하면 검사가 막힌다.
    """

    is_recorded_transport = True
    uses_network = False

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

    is_recorded_transport = True
    uses_network = False

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


def extract_finish_reason(raw_response: Any) -> str | None:
    """후보의 종료 사유(`finish_reason`). 없으면 `None`(추정하지 않는다).

    잘린 응답(MAX_TOKENS)을 성공 본문으로 다루지 않으려면 이 값이 필요하다. 후보가
    여러 개면 첫 후보 값을 쓴다(제공자 응답 순서를 그대로 따른다).
    """
    if not isinstance(raw_response, Mapping):
        return None
    candidates = raw_response.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return None
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        for key in ("finish_reason", "finishReason"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
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
    # 수신 원문(비밀값 제거 전 값이 아니라 transport가 돌려준 그대로). 호출자가 검색
    # 메타데이터 같은 **실제 반환 필드**를 읽어야 할 때 쓴다. 저장된 아티팩트와 같은
    # 내용이며, 여기 담는 것은 사본일 뿐 영속 기록은 아티팩트가 소유한다.
    raw_response: Any = None

    @property
    def ok(self) -> bool:
        return self.response.outcome is AttemptOutcome.OK

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)


@dataclass(frozen=True)
class ContentCheck:
    """응답 **내용**이 이 호출의 목적에 맞는지 보는 계약.

    기술 성공(HTTP 200·본문 있음)과 내용 수용을 구분한다. 잘린 JSON(MAX_TOKENS)이나
    JSON 파싱 실패는 기술 오류가 아니지만 그 본문으로는 결과를 만들 수 없으므로,
    **같은 논리 모듈의 남은 횟수 안에서** 다시 보낸다.

    여기 담는 것은 "다시 보낼 가치가 있는가"뿐이다. 글의 품질·길이·내용 판단은
    넣지 않는다(사용자가 성공을 판단한다). 검사는 **파싱 가능성**까지만 본다.
    """

    # 수용 판정 함수. `(text, raw_response) -> 거부 사유 or None`. None이면 수용.
    accepts: Callable[[str | None, Any], str | None]
    # 기록에 남길 라벨(어느 모듈의 내용 검사인지).
    label: str = "content"


# 응답이 잘렸다고 판정하는 종료 사유. 이 값이면 본문을 성공으로 다루지 않는다.
TRUNCATING_FINISH_REASONS: tuple[str, ...] = ("MAX_TOKENS", "MAX_OUTPUT_TOKENS")

# 응답 내용이 수용 기준을 통과하지 못했을 때 시도 행에 남기는 오류 분류. 재시도
# 대상이지만 `classify_attempt`의 HTTP 분류와 섞지 않는다(기술 오류가 아니다).
CONTENT_REJECTION_ERROR_CLASS = "content_not_accepted"


def rejection_of_truncated_or_unparseable(
    *,
    label: str,
    finish_reason: str | None,
    text: str | None,
) -> str | None:
    """잘림·JSON 미완성 사유. 아니면 `None`.

    종료 사유가 `MAX_TOKENS`/`MAX_OUTPUT_TOKENS`면 잘린 것으로 본다. 종료 사유가
    없어도 JSON이 닫히지 않았으면 같은 사유로 남긴다(추정으로 성공 처리하지 않는다).
    """
    reason = (finish_reason or "").strip().upper()
    if reason in TRUNCATING_FINISH_REASONS:
        return (
            f"{label} 응답이 출력 상한에서 잘렸습니다(finish_reason={finish_reason})."
            " 잘린 JSON을 본문으로 쓰지 않습니다."
        )
    body = (text or "").strip()
    if body and not (body.endswith("}") or body.endswith("```")):
        return (
            f"{label} 응답 JSON이 닫히지 않았습니다(잘린 응답으로 판단)."
            " 잘린 JSON을 본문으로 쓰지 않습니다."
        )
    return None


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


def transported_live(transport: ProviderTransport) -> bool:
    """이 transport가 **실제 네트워크로** 나가는지. 기록의 mode를 추론하지 않는다."""
    mode = getattr(transport, "mode", RunMode.MOCK)
    value = mode.value if isinstance(mode, RunMode) else str(mode)
    return value == RunMode.LIVE.value


# 실제 네트워크로 나가는 transport 클래스. `mode=live`인 **기록** transport(테스트·모의
# 재현)는 여기 없다. 두 경우를 같은 값으로 취급하면 기록 실행에 장부 요구가 걸리거나
# (검사가 깨진다) 반대로 실제 전송이 장부 없이 나가 상한을 잃는다.
_NETWORK_TRANSPORTS: tuple[str, ...] = (
    "GoogleGenAIHttpTransport",
    "HttpApiTransport",
    "HttpClientTransport",
)


def transported_over_network(transport: ProviderTransport) -> bool:
    """**실제 네트워크**로 나가는 transport인지. 클래스 이름과 플래그로 판정한다.

    기록 transport는 이름이 다르고 `is_recorded_transport=True`를 갖는다. 실제 호출
    어댑터도 그 플래그를 명시적으로 `False`로 둔다. 그래서 이름만 바꿔 우회하지 못한다.
    """
    if getattr(transport, "is_recorded_transport", False):
        return False
    declared = getattr(transport, "uses_network", None)
    if declared is not None:
        return bool(declared)
    return type(transport).__name__ in _NETWORK_TRANSPORTS


class JournalRequiredForNetworkSend(RuntimeError):
    """실제 네트워크 전송인데 사용량 장부를 쓸 수 없다. **전송하지 않는다.**

    이 예외는 요청을 보내기 전에 발생한다. 예산·장부가 없는데 실제 호출을 허용하면
    전체 상한(8회)이 다시 새는 구조가 되므로, 조용히 진행하지 않고 멈춘다.
    """


def _known_configuration_problem(transport: ProviderTransport) -> str | None:
    """전송 전에 알 수 있는 설정 문제. 있으면 전송을 시작하지 않는다.

    `send`가 같은 검사를 먼저 하므로 결과가 갈리지 않는다. 이 함수가 없으면 설정
    문제를 모르는 transport로 보고 전송 전 장부에 예약을 남긴다.
    """
    checker = getattr(transport, "configuration_problem", None)
    if not callable(checker):
        return None
    try:
        return checker()
    except Exception:  # noqa: BLE001 - 검사 실패를 '설정 없음'으로 단정하지 않는다
        return None


def _journal(
    *,
    spec: RequestSpec,
    context: ExecutionContext,
    transport: ProviderTransport,
    ordinal: int,
    actor_id: int | None,
    request_body: Any,
    response_body: Any = None,
    http_status: int | None = None,
    outcome: str = "pending",
    error_class: str | None = None,
    error_message: str | None = None,
    usage: Mapping[str, Any] | None = None,
    not_sent: bool = False,
    counts_toward_cap: bool = True,
    note: str | None = None,
    secret_values: Sequence[str] = (),
    moment: datetime | None = None,
    enabled: bool = True,
    run_session: Session | None = None,
) -> send_ledger.JournalOutcome | None:
    """전송 사용량을 **독립 트랜잭션**으로 남긴다.

    - mock/replay는 네트워크로 나가지 않으므로 장부를 쓰지 않는다(0회).
    - `enabled=False`는 **저장 대상 실행이 없는** 호출(단위 검사처럼 세션을 넘기지 않는
      경우)이다. 기록할 run이 없으므로 장부도 쓰지 않는다. 이때는 상한이 걸리지 않는
      검사 경로이므로 전송을 막지 않는다.
    - live + 실행 기록이 있는 호출은 장부를 쓰지 못하면 전송하지 않는다
      (`SendJournalUnavailable`). 사용량이 새는 전송을 허용하지 않기 위해서다.
    """
    if not enabled or not transported_live(transport):
        return None
    return send_ledger.journal_send(
        run_id=context.run_id,
        actor_id=actor_id or 0,
        logical_call_id=spec.logical_call_id,
        attempt_ordinal=ordinal,
        request_class=transport.request_class,
        provider=transport.provider,
        model=spec.model,
        mode=(
            transport.mode.value
            if isinstance(transport.mode, RunMode)
            else str(transport.mode)
        ),
        request_body=request_body,
        response_body=response_body,
        http_status=http_status,
        outcome=outcome,
        error_class=error_class,
        error_message=error_message,
        usage=usage,
        not_sent=not_sent,
        counts_toward_cap=counts_toward_cap,
        note=note,
        secret_values=secret_values,
        now=moment,
        # 실행 세션과 같은 DB로 장부를 쓴다(전역 팩토리에 의존하지 않는다).
        session_factory=(
            sessionmaker(bind=run_session.get_bind(), autoflush=False, expire_on_commit=False)
            if run_session is not None
            else None
        ),
    )


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
    content_check: ContentCheck | None = None,
    starting_ordinal: int = 0,
    timestamp_clock: Callable[[], datetime] | None = None,
) -> ExecuteRequestResult:
    """요청 하나를 예산·기한·시도 규칙 안에서 보낸다.

    - 실제 시도마다 한 행을 남긴다. 실패한 시도도 지우지 않는다.
    - `attempt_ordinal`은 0부터 시작한다. 0이 아닌 시도가 재시도다.
    - 기한을 넘기는 대기는 하지 않는다.
    - 설정 부족은 요청을 보내지 않았지만 시도 행으로 남겨, 왜 실패했는지 보이게 한다.
    - `content_check`가 거부한 응답(잘린 JSON·JSON 파싱 실패)은 **같은 논리 모듈의
      남은 횟수 안에서** 다시 보낸다. 재시도 루프를 하나 더 만들지 않고 여기서 처리한다.
    """
    if starting_ordinal < 0:
        raise ValueError(f"starting_ordinal must be >= 0, got {starting_ordinal}")
    request_class = transport.request_class
    # 장부는 "실행 기록이 있는 live 호출"에만 쓴다. 세션이 없으면 기록할 run도 없다.
    journal_enabled = session is not None and transported_live(transport)

    # 실제 네트워크 전송은 **장부가 없으면 시작하지 않는다**. 기록 transport(mode=live
    # 포함)는 네트워크를 열지 않으므로 이 요구에서 제외한다. 테스트 환경 플래그로
    # 우회할 수 있는 경로를 두지 않는다.
    if transported_over_network(transport) and not journal_enabled:
        raise JournalRequiredForNetworkSend(
            "실제 네트워크 전송에는 실행 기록 세션과 사용량 장부가 필요합니다."
            " 장부 없이 보내면 전체 전송 상한(8회)이 사라지므로 요청을 보내지 않습니다."
        )
    # attempt·장부에 남길 **실제 시각**의 출처. 넘기지 않으면 `now`와 같다(기존 동작).
    stamps = timestamp_clock or now
    attempt_limit = max_attempts or budget.limits.attempts_per_call
    picks = rng or (lambda: 0.5)
    budget.register_call(spec.logical_call_id)

    # 재시작·재개로 인메모리 예산이 장부보다 적게 세고 있으면 장부 값을 채택한다.
    # 8회 상한은 새로 주지 않고, 이미 보낸 전송을 다시 셀 수 있게 맞춘다.
    if journal_enabled:
        try:
            send_ledger.reconcile_budget_from_journal(
                budget, session, run_id=context.run_id
            )
        except Exception:  # noqa: BLE001 - 장부 조회 실패로 전송을 막지는 않는다
            pass

    attempts: list[AttemptRecord] = []
    final_response: ProviderResponse | None = None
    final_text: str | None = None
    # 검색 메타데이터처럼 **실제로 돌려받은 필드**를 호출자가 읽을 수 있게 보존한다.
    # 영속 기록은 아티팩트가 소유하며, 이 값은 그 사본이다.
    final_raw_response: Any = None
    stopped_reason: str | None = None
    missing_configuration: str | None = None
    ordinal = starting_ordinal
    wait_seconds = 0.0

    while True:
        moment = now()
        allowed, reason = budget.can_attempt(
            spec.logical_call_id, request_class.value, now=moment
        )
        if not allowed:
            stopped_reason = reason
            break
        # 429로만 연장된 여유는 **직전 실패가 429**인 모듈에 한해 적용한다. 그래야
        # 혼합 흐름(429→503→429)에서도 4번째가 열리고, 직전이 비429면 3회에서 멈춘다.
        loop_ceiling = (
            max(attempt_limit, RATE_LIMIT_MAX_SENDS)
            if budget.last_failure_was_rate_limited(spec.logical_call_id)
            else attempt_limit
        )
        if ordinal >= loop_ceiling:
            stopped_reason = (
                f"논리 호출 {spec.logical_call_id}의 시도 상한({loop_ceiling}회)에"
                " 도달했습니다."
            )
            break

        budget.charge(spec.logical_call_id, request_class.value, now=moment)
        attempt_started = stamps()
        timeout_seconds = _attempt_timeout(
            spec, request_class=request_class, budget=budget, moment=moment
        )

        # 전송 **전**에 사용량·redacted 요청을 독립 트랜잭션으로 남긴다. 이 장부가
        # 없으면 전송하지 않는다(장부를 못 쓰는 전송은 상한을 다시 새게 만든다).
        # 설정 부족은 실제 전송이 아니므로 예약을 남기지 않고 아래 경로에서 기록한다.
        configuration_problem = _known_configuration_problem(transport)
        if configuration_problem is None:
            _journal(
                spec=spec,
                context=context,
                transport=transport,
                ordinal=ordinal,
                actor_id=actor_id,
                request_body={
                    "endpoint": spec.endpoint,
                    "provider": transport.provider,
                    "model": spec.model,
                    "parameters": dict(spec.parameters),
                    "timeout_seconds": timeout_seconds,
                },
                outcome="pending",
                note="전송 전 예약. 후처리·롤백과 무관하게 남는다.",
                secret_values=secret_values,
                moment=moment,
                enabled=journal_enabled,
                run_session=session,
            )

        try:
            outcome = transport.send(
                spec, timeout_seconds=timeout_seconds, context=context
            )
        except ConfigurationUnavailable as exc:
            # 요청을 실제로 보내지 않았다. 그러나 시도로 남겨 원인을 보이게 한다.
            # 장부에도 `not_sent`로 남겨 사용량(8회 상한)에 세지 않는다.
            missing_configuration = str(exc)
            _journal(
                spec=spec,
                context=context,
                transport=transport,
                ordinal=ordinal,
                actor_id=actor_id,
                request_body={
                    "endpoint": spec.endpoint,
                    "provider": transport.provider,
                    "model": spec.model,
                    "not_sent": True,
                    "reason": str(exc),
                },
                outcome="error",
                error_class="configuration_error",
                error_message=str(exc),
                not_sent=True,
                counts_toward_cap=False,
                note="설정 부족으로 전송하지 않았다. 사용량으로 세지 않는다.",
                enabled=journal_enabled,
                secret_values=secret_values,
                moment=moment,
            )
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
                started_at=stamps(),
                finished_at=stamps(),
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

        except Exception as exc:  # noqa: BLE001 - 예상 밖 전송 예외도 장부에 남긴다
            # 전송이 나갔는지 확신할 수 없다. 예약 행은 이미 사용량으로 세었으므로
            # 상한은 잃지 않고, 결과는 unknown으로 남겨 원인을 보이게 한다.
            _journal(
                spec=spec,
                context=context,
                transport=transport,
                ordinal=ordinal,
                actor_id=actor_id,
                request_body={
                    "endpoint": spec.endpoint,
                    "provider": transport.provider,
                    "model": spec.model,
                    "exception": type(exc).__name__,
                },
                outcome="unknown",
                error_class=type(exc).__name__,
                error_message=str(exc)[:500],
                not_sent=False,
                counts_toward_cap=False,
                note=(
                    "전송 호출이 예외로 끝났습니다. 실제 전송 여부를 확정할 수 없어"
                    " unknown으로 남깁니다. 예약 시점에 이미 사용량으로 세었습니다."
                ),
                secret_values=secret_values,
                moment=now(),
                enabled=journal_enabled,
                run_session=session,
            )
            raise

        finished = stamps()
        outcome_value = _outcome_of(outcome)
        received_text = extract_text(outcome.raw_response)
        # 내용 수용 검사(잘린 JSON·JSON 파싱 실패). 기술 성공이어도 그 본문으로 결과를
        # 만들 수 없으면 **같은 모듈의 남은 횟수 안에서** 다시 보낸다. 판정은 이 함수
        # 하나에서만 하며, SDK·그래프·모듈에 별도 재시도 루프를 두지 않는다.
        rejection = (
            content_check.accepts(received_text, outcome.raw_response)
            if (content_check is not None and outcome_value is AttemptOutcome.OK)
            else None
        )
        attempt_outcome = AttemptOutcome.ERROR if rejection else outcome_value
        attempt_error_class = CONTENT_REJECTION_ERROR_CLASS if rejection else outcome.error_class
        attempt_error_message = rejection if rejection else outcome.error_message

        # 응답을 받은 **직후** 결과를 독립 트랜잭션으로 남긴다. 이후 후처리·정규화·
        # 커밋에서 예외가 나도 redacted 원문과 사용량은 남는다.
        _journal(
            spec=spec,
            context=context,
            transport=transport,
            ordinal=ordinal,
            actor_id=actor_id,
            request_body=outcome.raw_request,
            response_body=outcome.raw_response,
            http_status=outcome.http_status,
            outcome=attempt_outcome.value,
            error_class=attempt_error_class,
            error_message=attempt_error_message,
            usage=outcome.usage,
            not_sent=False,
            counts_toward_cap=False,
            note=(
                "응답은 보존했지만 내용이 수용 기준을 통과하지 못했습니다"
                f"({content_check.label}, 원문은 response_body에 남김)."
                if rejection
                else "응답 수신 직후 보존. 실행 트랜잭션 롤백과 무관하다."
            ),
            enabled=journal_enabled,
            secret_values=secret_values,
            moment=finished,
        )
        attempt = _record_attempt(
            session,
            spec=spec,
            context=context,
            ordinal=ordinal,
            provider=transport.provider,
            mode=transport.mode,
            outcome=attempt_outcome,
            http_status=outcome.http_status,
            error_class=attempt_error_class,
            error_message=attempt_error_message,
            wait_ms=int(wait_seconds * 1000) if wait_seconds else None,
            request_body=outcome.raw_request,
            response_body=outcome.raw_response,
            usage=outcome.usage,
            started_at=attempt_started,
            finished_at=finished,
            actor_id=actor_id,
            module_execution_id=module_execution_id,
            secret_values=secret_values,
            request_class=request_class,
        )
        attempts.append(attempt)

        final_response = ProviderResponse(
            attempt_id=attempt.attempt_id,
            outcome=attempt_outcome,
            http_status=outcome.http_status,
            provider_request_id=outcome.provider_request_id,
            raw_artifact_id=attempt.response_artifact_id,
            error_class=attempt_error_class,
            error_message=attempt_error_message,
            usage=extract_usage(outcome.usage),
            duration_ms=outcome.duration_ms
            if outcome.duration_ms is not None
            else max(0, int((finished - moment).total_seconds() * 1000)),
            received_at=finished,
        )
        if rejection:
            # 본문은 보존됐지만 그 내용으로는 결과를 만들 수 없다. 같은 모듈의 남은
            # 횟수가 있으면 다시 보내고, 없으면 사유를 남기고 멈춘다.
            if ordinal + 1 >= attempt_limit:
                stopped_reason = (
                    f"{content_check.label} 응답이 수용 기준을 통과하지 못했고"
                    f" 시도 상한({attempt_limit}회)에 도달했습니다: {rejection}"
                )
                break
            wait_seconds = bounded_wait_seconds(ordinal, rng=picks)
            if wait_seconds >= budget.seconds_left(now()):
                stopped_reason = (
                    f"{content_check.label} 응답 재시도 대기({wait_seconds:.1f}초)가"
                    f" 남은 실행 기한보다 길어 재시도하지 않았습니다: {rejection}"
                )
                break
            sleeper(wait_seconds)
            ordinal += 1
            continue

        if attempt_outcome is AttemptOutcome.OK:
            final_text = received_text
            final_raw_response = outcome.raw_response
            break

        decision = classify_attempt(
            outcome=outcome_value.value,
            http_status=outcome.http_status,
            error_class=outcome.error_class,
        )
        if decision is RetryDecision.STOP:
            stopped_reason = _stop_reason(outcome)
            break
        # 429는 사용자 확정 대기 구간(60/300/600초)을 쓰고 최대 4회까지 보낸다.
        # 그 밖의 오류는 기존 시도 상한을 그대로 유지한다.
        is_rate_limited = (
            outcome.http_status == 429
            or str(outcome.error_class or "") == "rate_limited"
        )
        if is_rate_limited:
            budget.note_rate_limited(spec.logical_call_id)
        else:
            # 직전 실패가 429가 아니면 4번째 전송을 열지 않는다(상한 일괄 증가 금지).
            budget.note_non_rate_limit_failure(spec.logical_call_id)
        send_ceiling = (
            max(attempt_limit, RATE_LIMIT_MAX_SENDS) if is_rate_limited else attempt_limit
        )
        if ordinal + 1 >= send_ceiling:
            # R1: 소진 사유에 **마지막 실패의 실제 HTTP 상태/분류**를 남긴다. 그래야
            # 운영자가 429 소진인지 다른 오류인지 문구만으로 알 수 있다. 원문 본문·
            # 비밀값은 넣지 않는다(상태 코드와 분류 이름만).
            status_text = outcome.http_status if outcome.http_status is not None else "unknown"
            class_text = str(outcome.error_class or "unknown")
            stopped_reason = (
                f"논리 호출 {spec.logical_call_id}의 시도 상한({send_ceiling}회)에"
                f" 도달했습니다(마지막 실패: HTTP {status_text} {class_text})."
            )
            break

        wait_seconds = (
            rate_limit_wait_seconds(
                ordinal, retry_after_seconds=outcome.retry_after_seconds
            )
            if is_rate_limited
            else bounded_wait_seconds(
                ordinal,
                retry_after_seconds=outcome.retry_after_seconds,
                rng=picks,
            )
        )
        if wait_seconds >= budget.seconds_left(now()):
            stopped_reason = (
                f"재시도 대기({wait_seconds:.1f}초)가 남은 실행 기한보다 길어"
                " 재시도하지 않았습니다."
            )
            break
        sleeper(wait_seconds)
        ordinal += 1

    if final_response is None:
        # 첫 시도가 예산·기한에서 거부됐다. 실제 전송은 없었다. 예외로 터뜨리지 않고
        # "전송하지 못한 이유"를 결과로 돌려줘 호출자가 그대로 보고하게 한다.
        final_response = ProviderResponse(
            attempt_id=None,
            outcome=AttemptOutcome.ERROR,
            http_status=None,
            error_class="budget_exhausted"
            if not (stopped_reason and "기한" in stopped_reason)
            else "deadline_exceeded",
            error_message=stopped_reason
            or "요청을 시작하지 못했습니다(첫 시도 거부).",
            received_at=now(),
        )

    return ExecuteRequestResult(
        spec=spec,
        response=final_response,
        attempts=tuple(attempts),
        budget=budget.snapshot(),
        text=final_text,
        stopped_reason=stopped_reason,
        missing_configuration=missing_configuration,
        raw_response=final_raw_response,
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
    sleeper: Callable[[float], None] | None = None,
    rng: Callable[[], float] | None = None,
    now: Callable[[], datetime] = _now,
    content_check: ContentCheck | None = None,
    starting_ordinal: int = 0,
    timestamp_clock: Callable[[], datetime] | None = None,
) -> ExecuteRequestResult:
    """모델 요청 하나. `execute_request`를 통해서만 나가므로 예산·기록이 같다.

    `content_check`를 넘기면 잘린 JSON·JSON 파싱 실패가 **같은 논리 모듈의 남은
    횟수 안에서** 자동 재시도된다. 재시도 루프는 `execute_request` 하나뿐이다.
    """
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
        # 기본 대기는 모듈 속성을 그때 읽는다(검사가 sleep_seconds를 바꿔 실제 대기를
        # 건너뛸 수 있어야 한다. 정의 시점 바인딩은 monkeypatch를 무시한다).
        sleeper=sleeper or sleep_seconds,
        rng=rng,
        now=now,
        secret_values=secret_values,
        module_execution_id=module_execution_id,
        content_check=content_check,
        starting_ordinal=starting_ordinal,
        timestamp_clock=timestamp_clock,
    )


def sent_attempt_count(result: ExecuteRequestResult, transport_mode: Any) -> int:
    """실제로 **전송된** 시도 수.

    기준은 두 가지다.

    1. 실행 방식이 `live`여야 한다. 저장 응답 재생·모의 transport는 네트워크로 나가지
       않으므로, 컨텍스트 모드가 live여도 외부 호출로 세지 않는다.
    2. 설정 부족(`configuration_error`) 시도는 기록에는 남지만 전송이 아니므로 뺀다.

    실패·재시도한 시도는 그대로 센다. 성공 여부로 세면 실패한 live 실행이 0회로 보여
    지표가 틀어진다.
    """
    mode = transport_mode
    value = mode.value if isinstance(mode, RunMode) else str(mode)
    if value != RunMode.LIVE.value:
        return 0
    return sum(
        1 for attempt in result.attempts if attempt.error_class != "configuration_error"
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


