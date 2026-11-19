"""MP-04 제공자 어댑터 검사.

이 파일이 확인하는 것:

- 429 → 대기 → 성공에서 **두 시도가 모두** 저장된다(성공만 골라 제출하지 않는다).
- 401은 같은 요청을 다시 보내지 않는다.
- 원문 요청·응답이 각각 보존되고, 비밀값은 저장 전에 제거된다.
- 사용량이 없으면 0이 아니라 null(unknown)이다.
- 응답을 보존하기 전에 중단된 경우 `unknown`이며 성공으로 세지 않는다.
- 모델 설정이 없으면 제공자를 부르지 않고 `configuration_error`로 실패한다.
- 모의(mock) 기록은 live로 표시되지 않는다.

실제 네트워크 호출은 하지 않는다. 모의 transport로 재현하고, 그 사실을 숨기지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.preview import provider, store
from app.preview.contracts import (
    AttemptOutcome,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
    RunStatus,
)
from app.preview.retry import BudgetLimits, RunBudget

FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


def _context(mode: RunMode = RunMode.MOCK) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=mode,
        actor_id=1,
        config_version="mp04-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _store_run(session, context: ExecutionContext) -> None:
    store.store_run(session, context, label="mp04 provider test", status=RunStatus.RUNNING)


def _ok_response(text: str = "정상 응답", usage: dict | None = None) -> provider.TransportResult:
    body = {
        "candidates": [
            {"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}
        ]
    }
    if usage is not None:
        body["usageMetadata"] = usage
    return provider.TransportResult(
        http_status=200, raw_request={"contents": "요청"}, raw_response=body, usage=usage
    )


def _error(status: int, message: str, retry_after: float | None = None):
    return provider.TransportResult(
        http_status=status,
        raw_request={"contents": "요청"},
        raw_response={"error": {"code": status, "message": message}},
        error_class="rate_limited" if status == 429 else "authentication_error",
        error_message=message,
        retry_after_seconds=retry_after,
    )


def test_429_then_success_two_attempts(session_factory):
    """429 → 대기 → 성공에서 실패한 시도와 성공한 시도가 모두 남는다."""
    context = _context()
    slept: list[float] = []

    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(429, "rate limited", retry_after=3.0), _ok_response()]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=slept.append,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert result.ok is True
        assert result.attempt_count == 2
        assert result.text == "정상 응답"
        # 실패한 시도를 지우지 않는다.
        outcomes = [attempt.outcome for attempt in result.attempts]
        assert outcomes == [AttemptOutcome.ERROR, AttemptOutcome.OK]
        assert result.attempts[1].attempt_ordinal == 1
        # 429는 고정 구간(60/300/600초)을 쓴다. 공급자의 **짧은** 안내로 구간을
        # 깎지 않으므로 첫 대기는 60초다(테스트는 실제로 자지 않는다).
        assert slept == [60.0]

        rows = store.get_run_detail(session, context.run_id).attempts
        assert len(rows) == 2
        assert [row["http_status"] for row in rows] == [429, 200]
        assert rows[1]["wait_ms"] == 60000
        # 원문 요청·응답이 각각 다른 아티팩트로 보존된다.
        assert rows[0]["request_artifact_id"] != rows[0]["response_artifact_id"]
        assert rows[1]["response_artifact_id"]


def test_401_no_blind_retry(session_factory):
    """401은 같은 요청을 다시 보내지 않는다. 인증 오류는 재시도로 해결되지 않는다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(401, "unauthorized"), _ok_response()]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert result.ok is False
        assert result.attempt_count == 1
        # 스크립트에 남은 성공 응답은 소비되지 않았다.
        assert len(transport.calls) == 1
        assert result.response.http_status == 401
        assert result.stopped_reason


def test_raw_payload_preserved(session_factory):
    """수신 원문과 정규화 결과를 각각 보관한다. 원문은 요약으로 대체하지 않는다."""
    context = _context()
    raw_text = "경기 100: 홈팀 최근 5경기 2승 2무 1패"
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(script=[_ok_response(text=raw_text)])
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        attempt_id = result.attempts[0].response_artifact_id
        assert attempt_id is not None
        view = next(
            artifact
            for artifact in store.get_run_detail(session, context.run_id).artifacts
            if artifact["artifact_id"] == str(attempt_id)
        )
        # 원문 본문이 그대로 저장돼 있다(추출 텍스트만 남기지 않는다).
        assert raw_text in view["body"]
        assert "candidates" in view["body"]
        assert result.text == raw_text


def test_unknown_usage_is_null_not_zero(session_factory):
    """제공자가 사용량을 주지 않으면 0이 아니라 null이다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(script=[_ok_response()])
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert result.response.usage is None
        row = store.get_run_detail(session, context.run_id).attempts[0]
        assert row["usage"] is None


def test_unknown_outcome_is_not_a_success(session_factory):
    """응답을 보존하기 전에 중단되면 unknown이며 성공으로 세지 않는다."""
    context = _context()
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                provider.TransportResult(
                    http_status=None,
                    raw_request={"contents": "요청"},
                    raw_response=None,
                    error_class="transport_timeout",
                    error_message="read timeout",
                    outcome_unknown=True,
                )
            ]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            max_attempts=1,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert result.ok is False
        assert result.attempts[0].outcome is AttemptOutcome.UNKNOWN
        row = store.get_run_detail(session, context.run_id).attempts[0]
        assert row["outcome"] == "unknown"
        assert row["http_status"] is None


def test_secrets_are_redacted_before_storage(session_factory):
    """원문에 섞여 들어온 인증 값은 저장 전에 제거된다."""
    context = _context()
    canary = "canary-secret-value-1234567890"
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                provider.TransportResult(
                    http_status=200,
                    raw_request={
                        "contents": "요청",
                        "headers": {"authorization": f"Bearer {canary}"},
                    },
                    raw_response={"candidates": [], "echo": f"token={canary}"},
                )
            ]
        )
        provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            secret_values=(canary,),
            now=lambda: FIXED_NOW,
        )
        session.commit()

        detail = store.get_run_detail(session, context.run_id)
        bodies = " ".join(str(artifact["body"]) for artifact in detail.artifacts)
        assert canary not in bodies
        assert "[REDACTED]" in bodies


def test_model_configuration_missing_does_not_call_provider(session_factory):
    """설정이 없으면 제공자를 부르지 않고 configuration_error로 끝난다."""
    context = _context()
    calls: list[object] = []

    def _factory():  # pragma: no cover - 설정이 없으면 호출되지 않는다
        calls.append("client")
        raise AssertionError("no client should be built without configuration")

    transport = provider.GoogleGenAIHttpTransport(
        project=None,
        location="global",
        model="gemini-observed-model",
        credentials_json=None,
        client_factory=_factory,
    )
    status = provider.model_configuration_status(transport)
    assert status["configured"] is False
    assert "프로젝트" in (status["problem"] or "")

    with session_factory() as session:
        _store_run(session, context)
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="vertex",
                model="gemini-observed-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert calls == []
        assert result.ok is False
        assert result.missing_configuration
        assert result.attempts[0].outcome is AttemptOutcome.ERROR
        row = store.get_run_detail(session, context.run_id).attempts[0]
        assert row["error_class"] == "configuration_error"


def test_mock_attempts_are_not_recorded_as_live(session_factory):
    """모의 transport로 만든 기록은 live로 표시되지 않는다."""
    context = _context(mode=RunMode.MOCK)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(script=[_ok_response()])
        provider.execute_request(
            provider.RequestSpec(
                logical_call_id="research-1",
                provider="mock-transport",
                model="mock-model",
                operation="research",
                module_id="R1",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        detail = store.get_run_detail(session, context.run_id)
        assert detail.summary.mode is RunMode.MOCK
        assert all(attempt["mode"] == "mock" for attempt in detail.attempts)


def test_api_budget_is_used_for_api_transport(session_factory):
    """축구 API transport는 모델 예산이 아니라 API 예산을 쓴다."""
    context = _context(mode=RunMode.LIVE)
    budget = RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=1, attempts_per_call=3),
        now=FIXED_NOW,
    )
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.HttpApiTransport(
            provider="api-football",
            mode=RunMode.LIVE,
            send_func=lambda spec, timeout: provider.HttpResponse(
                status_code=429, body={"errors": {"rate": "limited"}},
                headers={"retry-after": "1"},
            ),
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="d0-fixtures",
                provider="api-football",
                model=None,
                operation="fixtures",
                module_id="D0",
            ),
            context,
            transport=transport,
            budget=budget,
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        session.commit()

        assert result.ok is False
        # API 예산 1회이므로 429 한 번에서 멈춘다.
        assert result.attempt_count == 1
        assert result.budget["api_used"] == 1
        assert result.budget["model_used"] == 0


def test_extract_text_returns_none_for_empty_response():
    """빈 응답에서 빈 문자열을 만들지 않는다."""
    assert provider.extract_text({"candidates": []}) is None
    assert provider.extract_text(None) is None
    assert provider.extract_text({"candidates": [{"content": {"parts": []}}]}) is None


def test_missing_retry_after_falls_back_to_bounded_backoff():
    """Retry-After가 없으면 1초부터 지수 증가한다. 상한은 60초."""
    from app.preview.retry import bounded_wait_seconds

    assert bounded_wait_seconds(0, rng=lambda: 1.0) == pytest.approx(1.0)
    assert bounded_wait_seconds(1, rng=lambda: 1.0) == pytest.approx(2.0)
    assert bounded_wait_seconds(99, rng=lambda: 1.0) == pytest.approx(60.0)


def test_google_transport_disables_sdk_retries(monkeypatch):
    """SDK 재시도를 끈다. 실제 호출 수와 기록이 같아야 예산이 두 배가 되지 않는다.

    이 검사는 `_build_client`가 실제로 만드는 `HttpOptions.retry_options.attempts`를
    확인한다. 클라이언트 객체 생성만 가로채고 네트워크 호출은 하지 않는다.
    """
    import google.genai as genai_module
    import google.genai.types as genai_types
    import google.oauth2.service_account as service_account_module

    captured: dict[str, object] = {}

    class _FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            captured["retry_options"] = kwargs["http_options"].retry_options

    monkeypatch.setattr(
        service_account_module.Credentials,
        "from_service_account_info",
        staticmethod(lambda info, scopes=None: "fake-service-account-credentials"),
    )
    monkeypatch.setattr(genai_module, "Client", _FakeClient)

    transport = provider.GoogleGenAIHttpTransport(
        project="project-from-deployment",
        location="global",
        model="model-from-deployment",
        credentials_json='{"type": "service_account", "client_email": "x@example.test"}',
    )
    assert transport.configuration_problem() is None

    client = transport._build_client()
    assert isinstance(client, _FakeClient)
    retry_options = captured["retry_options"]
    # 최초 요청 한 번만 보낸다(재시도 없음).
    assert retry_options is not None
    assert retry_options.attempts == 1
    # Vertex 경로로 만들고, 인증 값은 원문 그대로 넘기지 않는다.
    assert captured["vertexai"] is True
    assert captured["project"] == "project-from-deployment"
    assert captured["location"] == "global"
    assert genai_types.HttpOptions is not None


def test_live_settings_are_read_from_environment_without_printing_secrets(monkeypatch):
    """배포 설정에서 확인한 축(project/location/model)을 환경으로만 받는다.

    비밀값(서비스 계정 JSON)은 `Settings` 표현에 나타나지 않아야 한다.
    """
    from app.preview.config import PreviewSettings

    monkeypatch.setenv("PREVIEW_MODEL_PROJECT", "project-from-deployment")
    monkeypatch.setenv("PREVIEW_MODEL_LOCATION", "global")
    monkeypatch.setenv("PREVIEW_MODEL_NAME", "model-from-deployment")
    monkeypatch.setenv(
        "PREVIEW_MODEL_CREDENTIALS_JSON",
        '{"type": "service_account", "private_key": "canary-private-key-value"}',
    )
    settings = PreviewSettings()
    assert settings.model_project == "project-from-deployment"
    assert settings.model_location == "global"
    assert settings.model_name == "model-from-deployment"
    # 실제 유료 호출은 명시적 플래그가 있어야 열린다.
    assert settings.model_live_enabled is False
    # 비밀값이 표현·로그에 남지 않는다.
    assert "canary-private-key-value" not in repr(settings)
    assert "canary-private-key-value" not in str(settings)


# --------------------------------------------------------------------------
# 응답 내용 수용과 재시도 (사용자 확정 2026-11-12)
# --------------------------------------------------------------------------


def _content_check(label: str = "선수", *, parse_ok: bool = True):
    """간단한 내용 검사. 실제 섹션 파서 대신 'JSON으로 읽히는가'만 본다."""
    import json as _json

    def accepts(text, raw_response):
        truncated = provider.rejection_of_truncated_or_unparseable(
            label=label,
            finish_reason=provider.extract_finish_reason(raw_response),
            text=text,
        )
        if truncated:
            return truncated
        if not text:
            return f"{label} 응답이 비었습니다."
        try:
            _json.loads(text)
        except ValueError:
            return f"{label} 응답을 JSON으로 해석하지 못했습니다."
        return None

    return provider.ContentCheck(accepts=accepts, label=label)


def _reply(text: str, *, finish_reason: str = "STOP") -> provider.TransportResult:
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response={
            "candidates": [
                {
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": finish_reason,
                }
            ]
        },
    )


def _spec() -> provider.RequestSpec:
    return provider.RequestSpec(
        logical_call_id="section_players",
        provider="mock-transport",
        model="mock-model",
        operation="build_players",
        module_id="R4",
    )


def test_max_tokens_is_not_a_success_and_is_retried_then_stops_at_three(session_factory):
    """잘린 응답(MAX_TOKENS)은 성공이 아니다. 같은 모듈의 3회 안에서 다시 보낸다."""
    context = _context(mode=RunMode.LIVE)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                _reply('{"players": [', finish_reason="MAX_TOKENS"),
                _reply('{"players": [', finish_reason="MAX_TOKENS"),
                _reply('{"players": [{"selected_player": "엘링 홀란"}]}'),
            ]
        )
        result = provider.execute_request(
            _spec(),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
            content_check=_content_check(),
        )
        session.commit()

        # 실제 전송 3회, 네 번째 없음.
        assert len(transport.calls) == 3
        assert result.ok is True
        assert result.text and "엘링 홀란" in result.text
        # 실패한 두 시도도 지우지 않는다.
        assert [attempt.outcome for attempt in result.attempts] == [
            AttemptOutcome.ERROR,
            AttemptOutcome.ERROR,
            AttemptOutcome.OK,
        ]
        assert result.attempts[0].error_class == provider.CONTENT_REJECTION_ERROR_CLASS
        # 원문은 보존된다(잘린 본문도 잃지 않는다).
        rows = store.get_run_detail(session, context.run_id).attempts
        assert len(rows) == 3
        assert rows[0]["response_artifact_id"]


def test_fourth_content_rejection_is_never_sent(session_factory):
    """내용이 계속 거부되면 3회에서 멈추고 4번째 전송은 0이다."""
    context = _context(mode=RunMode.LIVE)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                _reply('{"players": [', finish_reason="MAX_TOKENS"),
                _reply("not json"),
                _reply("still not json"),
                _reply('{"players": []}'),
            ]
        )
        result = provider.execute_request(
            _spec(),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
            content_check=_content_check(),
        )
        session.commit()

        assert len(transport.calls) == 3, "4번째 전송이 나갔다"
        assert result.ok is False
        assert result.stopped_reason


def test_short_parseable_body_is_accepted_without_another_send(session_factory):
    """짧아도 파싱되는 본문은 재전송하지 않는다(품질 재호출 금지)."""
    context = _context(mode=RunMode.LIVE)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_reply("{}"), _reply('{"players": [{"selected_player": "x"}]}')]
        )
        result = provider.execute_request(
            _spec(),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
            content_check=_content_check(),
        )
        session.commit()

        assert len(transport.calls) == 1
        assert result.ok is True
        assert result.text == "{}"


def test_authentication_error_is_not_retried_even_with_a_content_check(session_factory):
    """401은 내용 검사와 무관하게 재전송하지 않는다(설정·인증 오류 반복 0)."""
    context = _context(mode=RunMode.LIVE)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(401, "unauthorized"), _reply("{}")]
        )
        result = provider.execute_request(
            _spec(),
            context,
            transport=transport,
            budget=RunBudget.for_run(now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
            content_check=_content_check(),
        )
        session.commit()

        assert len(transport.calls) == 1
        assert result.ok is False


def test_429_exhaustion_uses_60_300_600_and_allows_fourth_send(session_factory):
    """429는 60·300·600초를 기다리고 최초 포함 **4회**까지 보낸다.

    검사 이유(실패 시 사용자 영향): 2026-11-19 실제 실행에서 Vertex 429가 3회 연속
    나자 시도 상한(3회)에 걸려 부상·매체 섹션이 통째로 비었다. 사용자 확정은 세 번의
    대기(1/5/10분)를 모두 쓸 수 있도록 4회 전송을 허용하는 것이다.
    """
    context = _context(RunMode.LIVE)
    slept: list[float] = []
    # 대기한 시간만큼 시계가 실제로 진행한다(대기 16분이 실제 실행 기한 안에 들어온다).
    elapsed = {"seconds": 0.0}

    def _clock():
        return FIXED_NOW + timedelta(seconds=elapsed["seconds"])

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        elapsed["seconds"] += seconds

    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(429, "rate limited") for _ in range(4)]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_availability",
                provider="mock-transport",
                model="mock-model",
                operation="section",
                module_id="R2",
            ),
            context,
            transport=transport,
            # 실제 생성 경로와 같은 예산(모듈 상한이 상한의 소유자)으로 검증한다.
            budget=RunBudget.for_generation(
                ("section_availability", "section_players"), now=FIXED_NOW
            ),
            session=session,
            sleeper=_sleep,
            now=_clock,
        )
        session.commit()

    # 네 번 전송하고 세 번 대기한다(마지막 실패 뒤에는 더 보낼 수 없으므로 대기 없음).
    assert len(transport.calls) == 4
    assert slept == [60.0, 300.0, 600.0]
    assert result.ok is False
    assert len(result.attempts) == 4


def test_non_429_errors_keep_the_three_attempt_cap(session_factory):
    """429가 아닌 오류는 기존 상한(3회)을 넘지 않는다(일괄 증가 금지)."""
    context = _context(RunMode.LIVE)
    slept: list[float] = []
    with session_factory() as session:
        _store_run(session, context)
        retryable_503 = provider.TransportResult(
            http_status=503,
            raw_request={"contents": "요청"},
            raw_response={"error": {"code": 503, "message": "service unavailable"}},
            error_class="provider_error",
            error_message="service unavailable",
        )
        transport = provider.RecordedTransport(script=[retryable_503 for _ in range(5)])
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_players",
                provider="mock-transport",
                model="mock-model",
                operation="section",
                module_id="R4",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_generation(
                ("section_players", "section_availability"), now=FIXED_NOW
            ),
            session=session,
            sleeper=slept.append,
            now=lambda: FIXED_NOW,
        )
        session.commit()

    assert len(transport.calls) == 3
    assert len(result.attempts) == 3


def test_sdk_api_error_keeps_body_and_retry_hint():
    """SDK `APIError`의 `details`/`response`에서 오류 본문과 재시도 안내를 보존한다.

    검사 이유(실패 시 사용자 영향): google-genai 3.0은 `response_json` 속성을 만들지
    않아 기존 코드가 오류 본문과 RetryInfo를 버렸다. 그러면 재시도 안내를 존중할 수
    없고 원인 진단도 사라진다.
    """
    class _Resp:
        headers = {"retry-after": "120"}

    class _SdkError(Exception):
        code = 429
        message = "429 RESOURCE_EXHAUSTED. Resource exhausted"
        details = {
            "error": {
                "code": 429,
                "message": "Resource exhausted. Please try again later.",
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "180s",
                    }
                ],
            }
        }
        response = _Resp()

    payload = provider._api_error_payload(_SdkError())
    assert payload["error"]["status"] == "RESOURCE_EXHAUSTED"
    assert provider._retry_after_from_payload(payload) == 180.0
    assert provider._retry_after_from_response(_Resp()) == 120.0
    assert "Resource exhausted" in provider._api_error_message(_SdkError(), payload)


def test_attempt_timestamps_come_from_the_timestamp_clock(session_factory):
    """attempt의 시작/종료 시각은 실제 시계(주입)에서 오고, 예산 판정 시각과 분리된다.

    검사 이유(실패 시 사용자 영향): 이전 구현은 모든 시도가 `plan.moment` 한 값으로
    기록돼, 429 재시도가 실제로 언제 시작·종료됐는지 사후에 알 수 없었다.
    """
    context = _context(RunMode.LIVE)
    budget_time = FIXED_NOW
    ticks = {"n": 0}

    def _stamp() -> datetime:
        ticks["n"] += 1
        return FIXED_NOW + timedelta(seconds=ticks["n"] * 10)

    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(429, "rate limited"), _ok_response()]
        )
        provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_players",
                provider="mock-transport",
                model="mock-model",
                operation="section",
                module_id="R4",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_generation(("section_players",), now=FIXED_NOW),
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: budget_time,
            timestamp_clock=_stamp,
        )
        session.commit()

        rows = store.get_run_detail(session, context.run_id).attempts
        starts = [row["started_at"] for row in rows]
        # 두 시도의 시작 시각이 서로 다르다(모든 시도가 같은 시각으로 남지 않는다).
        assert len(starts) == 2
        assert starts[0] != starts[1]
        # 주입한 timestamp clock이 실제로 쓰였는지 값으로 확인한다(문자열 형식에 의존하지
        # 않는다). 첫 두 호출은 10초·20초이고 예산 시각(FIXED_NOW)과 다르다.
        parsed = sorted(
            datetime.fromisoformat(str(value).replace("Z", "+00:00")) for value in starts
        )
        assert all(value > FIXED_NOW for value in parsed)


def test_mixed_429_and_other_errors_still_reach_four_sends(session_factory):
    """429가 섞인 흐름(429→503→429→429)에서도 4번째 전송이 열린다.

    검사 이유(실패 시 사용자 영향): 이전 구현은 `429로 끝난 수 >= 전송수-1`을 요구해
    중간에 503이 끼면 3번째에서 막혔다. 사용자가 확정한 "최초 포함 최대 4전송"과
    60/300/600 대기 세 구간이 혼합 흐름에서 줄어들면 안 된다.
    """
    context = _context(RunMode.LIVE)
    slept: list[float] = []
    elapsed = {"seconds": 0.0}

    def _clock():
        return FIXED_NOW + timedelta(seconds=elapsed["seconds"])

    def _sleep(seconds: float) -> None:
        slept.append(seconds)
        elapsed["seconds"] += seconds

    def _retryable_503():
        return provider.TransportResult(
            http_status=503,
            raw_request={"contents": "요청"},
            raw_response={"error": {"code": 503, "message": "service unavailable"}},
            error_class="provider_error",
            error_message="service unavailable",
        )

    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                _error(429, "rate limited"),
                _retryable_503(),
                _error(429, "rate limited"),
                _error(429, "rate limited"),
            ]
        )
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_outlook",
                provider="mock-transport",
                model="mock-model",
                operation="section",
                module_id="R3",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_generation(("section_outlook",), now=FIXED_NOW),
            session=session,
            sleeper=_sleep,
            now=_clock,
        )
        session.commit()

    # 4번 전송까지 나갔다(혼합 흐름에서 3번째에 막히지 않는다).
    assert len(transport.calls) == 4
    # 429 대기는 **시도 서수 기준** 구간(ordinal 0→60, ordinal 2→600)이고, 직전이
    # 429가 아닌 시도(ordinal 1)의 대기는 기존 정책(짧은 지수 대기) 그대로다.
    assert slept[0] == 60.0
    assert slept[1] < 60.0
    assert slept[2] == 600.0
    assert result.ok is False


def test_non_429_failure_after_429_does_not_open_a_fourth_send(session_factory):
    """429 뒤에 비429로 끝나면 4번째를 열지 않는다(상한 일괄 증가 금지)."""
    context = _context(RunMode.LIVE)
    slept: list[float] = []

    def _retryable_503():
        return provider.TransportResult(
            http_status=503,
            raw_request={"contents": "요청"},
            raw_response={"error": {"code": 503, "message": "unavailable"}},
            error_class="provider_error",
            error_message="unavailable",
        )

    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[_error(429, "rate limited"), _retryable_503(), _retryable_503(), _retryable_503()]
        )
        provider.execute_request(
            provider.RequestSpec(
                logical_call_id="section_players",
                provider="mock-transport",
                model="mock-model",
                operation="section",
                module_id="R4",
            ),
            context,
            transport=transport,
            budget=RunBudget.for_generation(("section_players",), now=FIXED_NOW),
            session=session,
            sleeper=slept.append,
            now=lambda: FIXED_NOW,
        )
        session.commit()

    # 429(1) + 503(2,3) = 3전송에서 멈춘다. 4번째는 열리지 않는다.
    assert len(transport.calls) == 3
