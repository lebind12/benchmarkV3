from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.services.home_preview_retry import ModelRun, failure_details

NOW = datetime(2026, 10, 25, 3, tzinfo=UTC)


def runtime(**kwargs):
    sleeps, persisted = [], []
    run = ModelRun(clock=lambda: NOW, sleep=sleeps.append, jitter=lambda: 0)
    run.start(
        usage=kwargs.get("usage", {}),
        deadline=kwargs.get("deadline", NOW + timedelta(seconds=900)),
        guard=kwargs.get("guard", lambda: None),
        persist=persisted.append,
    )
    return run, sleeps, persisted


def status(code, retry_after=None):
    request = httpx.Request("POST", "https://private.example/project/secret")
    response = httpx.Response(
        code,
        request=request,
        headers={"Retry-After": retry_after} if retry_after else {},
        json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "secret must not persist"}},
    )
    return httpx.HTTPStatusError("secret", request=request, response=response)


def test_transient_retry_is_bounded_per_stage_and_diagnostics_are_safe():
    run, sleeps, _ = runtime()
    calls = []

    def operation(timeout):
        calls.append(timeout)
        if len(calls) == 1:
            raise status(429, "12")
        return "ok"

    assert run.request("forecast", operation, timeout=90) == "ok"
    assert run.requests == 2 and run.retries == 1 and sleeps == [12]
    assert run.events[0]["http_status"] == 429
    assert run.events[0]["provider_code"] == "RESOURCE_EXHAUSTED"
    assert "secret" not in str(run.summary())
    with pytest.raises(httpx.HTTPStatusError):
        run.request("analysis", lambda _: (_ for _ in ()).throw(status(503)), timeout=90)
    assert run.requests == 4 and run.retries == 2
    assert run.request("causes", lambda _: "done", timeout=180) == "done"
    assert run.request("causes", lambda _: "done", timeout=180) == "done"
    with pytest.raises(ValueError, match="model_request_budget_exhausted"):
        run.request("causes", lambda _: "bad", timeout=180)


@pytest.mark.parametrize(
    "exc",
    [status(400), status(401), status(403), status(404), ValueError("incomplete_model_response")],
)
def test_permanent_or_invalid_output_is_not_retried(exc):
    run, sleeps, _ = runtime()

    def fail(_):
        raise exc

    with pytest.raises(type(exc)):
        run.request("analysis", fail, timeout=90)
    assert run.requests == 1 and run.retries == 0 and sleeps == []


def test_retry_after_and_deadline_are_respected_without_shortening_server_delay():
    for deadline, delay in [
        (NOW + timedelta(seconds=100), "20"),
        (NOW + timedelta(seconds=900), "600"),
        (NOW + timedelta(seconds=900), "172800"),
    ]:
        run, sleeps, _ = runtime(deadline=deadline)

        def fail(_, current_delay=delay):
            raise status(429, current_delay)

        with pytest.raises(httpx.HTTPStatusError):
            run.request("analysis", fail, timeout=90)
        assert run.requests == 1 and sleeps == []


def test_guard_rechecked_after_wait_and_persisted_budget_survives_restart():
    checks = []

    def guard():
        checks.append(1)
        if len(checks) > 1:
            raise ValueError("generation_ownership_lost")

    run, _, _ = runtime(guard=guard)

    def fail(_):
        raise httpx.ReadTimeout("private")

    with pytest.raises(ValueError, match="ownership"):
        run.request("causes", fail, timeout=180)
    restored, _, _ = runtime(usage=run.summary())
    assert restored.requests == 1 and restored.retries == 1
    with pytest.raises(httpx.ReadTimeout):
        restored.request("causes", fail, timeout=180)
    assert restored.requests == 2 and restored.retries == 1
    with pytest.raises(ValueError, match="model_stage_budget_exhausted"):
        restored.request("causes", fail, timeout=180)


def test_provider_uses_180_second_cause_timeout_and_retries_that_request_only():
    import json

    from app.core.config import Settings
    from app.services.home_preview_vertex import VertexPreviewProvider
    from tests.unit.test_home_preview_causes import payload, targets_from

    calls = []

    def reply(request):
        calls.append(request.extensions["timeout"]["read"])
        if len(calls) == 1:
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {"parts": [{"text": json.dumps({"candidates": []})}]},
                    }
                ]
            },
        )

    provider = VertexPreviewProvider(
        Settings(_env_file=None, google_cloud_project="test"), transport=httpx.MockTransport(reply)
    )
    provider.runtime, _, _ = runtime()
    value = payload()
    candidates, _, _ = provider.discover_absence_causes(value, targets=targets_from(value), now=NOW)
    assert candidates == [] and calls == [180, 180]
    assert provider.runtime.requests == 2


def test_finish_reason_and_http_date_metadata_are_bounded():
    exc = ValueError("incomplete_model_response")
    exc.preview_finish_reason = "MAX_TOKENS"
    assert failure_details(exc, now=NOW)["finish_reason"] == "MAX_TOKENS"
    assert (
        failure_details(status(429, "Sun, 25 Oct 2026 03:00:20 GMT"), now=NOW)[
            "retry_after_seconds"
        ]
        == 20
    )


def test_truncated_model_response_records_finish_reason_without_retry():
    from app.core.config import Settings
    from app.services.home_preview_vertex import VertexPreviewProvider

    def reply(request):
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "partial"}]}}
                ]
            },
        )

    provider = VertexPreviewProvider(
        Settings(_env_file=None, google_cloud_project="test"), transport=httpx.MockTransport(reply)
    )
    provider.runtime, sleeps, _ = runtime()
    with pytest.raises(ValueError, match="incomplete_model_response"):
        provider.request({})
    assert provider.runtime.requests == 1 and sleeps == []
    assert provider.runtime.events[0]["finish_reason"] == "MAX_TOKENS"
    assert provider.runtime.events[0]["retryable"] is False
