from __future__ import annotations

from collections import deque

import pytest

from app.workers.daily_sync.api import ApiFootballClient, ApiFootballRateLimiter

pytestmark = pytest.mark.unit


class _NoopRateLimiter:
    def acquire(self) -> None:
        return None


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = object()

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = deque(responses)
        self.calls: list[tuple[str, dict]] = []

    def get(self, path: str, *, params: dict) -> _FakeResponse:
        self.calls.append((path, params))
        return self.responses.popleft()

    def close(self) -> None:
        return None


def test_api_football_rate_limiter_paces_request_starts():
    now = [100.0]
    sleeps: list[float] = []

    def fake_time() -> float:
        return now[0]

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    limiter = ApiFootballRateLimiter(
        requests_per_minute=60,
        time_func=fake_time,
        sleep_func=fake_sleep,
    )

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()

    assert sleeps == pytest.approx([1.0, 1.0])


def test_api_football_client_retries_payload_rate_limit_errors():
    client = ApiFootballClient(
        api_key="test",
        backoff_seconds=0,
        rate_limiter=_NoopRateLimiter(),  # type: ignore[arg-type]
    )
    fake_http = _FakeHttpClient(
        [
            _FakeResponse({"errors": {"rateLimit": "Too many requests."}}),
            _FakeResponse({"errors": [], "response": [{"ok": True}]}),
        ]
    )
    client._client = fake_http  # type: ignore[assignment]

    assert client.get("/fixtures", league=39)["response"] == [{"ok": True}]
    assert fake_http.calls == [
        ("/fixtures", {"league": 39}),
        ("/fixtures", {"league": 39}),
    ]
    assert client.calls_total == 2
    assert client.calls_failed == 0
