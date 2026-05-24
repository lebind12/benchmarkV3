"""Small API-Football client with retry and pagination helpers."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

import httpx


class ApiFootballError(RuntimeError):
    """Raised when API-Football returns an unrecoverable response."""


class ApiFootballRetryableError(ApiFootballError):
    """Raised for retryable API-Football responses."""


@dataclass
class ApiFootballRateLimiter:
    """Thread-safe paced limiter shared by all API-Football worker threads."""

    requests_per_minute: int
    time_func: Callable[[], float] = time.monotonic
    sleep_func: Callable[[float], None] = time.sleep
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _next_request_at: float = field(default=0.0, init=False, repr=False)

    def acquire(self) -> None:
        if self.requests_per_minute <= 0:
            return
        min_interval = 60.0 / self.requests_per_minute
        while True:
            with self._lock:
                now = self.time_func()
                wait_seconds = self._next_request_at - now
                if wait_seconds <= 0:
                    self._next_request_at = max(now, self._next_request_at) + min_interval
                    return
            self.sleep_func(wait_seconds)


def _is_rate_limit_error(errors: Any) -> bool:
    if isinstance(errors, dict):
        return any(str(key).lower() == "ratelimit" for key in errors)
    if isinstance(errors, list):
        return any(_is_rate_limit_error(item) for item in errors)
    return "rate limit" in str(errors).lower() or "too many requests" in str(errors).lower()


@dataclass
class ApiFootballClient:
    api_key: str
    host: str = "v3.football.api-sports.io"
    timeout: float = 30.0
    max_retries: int = 3
    backoff_seconds: float = 1.0
    requests_per_minute: int = 300
    rate_limiter: ApiFootballRateLimiter | None = None

    def __post_init__(self) -> None:
        self._client = httpx.Client(
            base_url=f"https://{self.host}",
            headers={
                "x-apisports-key": self.api_key,
                "x-rapidapi-key": self.api_key,
                "x-rapidapi-host": self.host,
            },
            timeout=self.timeout,
        )
        self.calls_total = 0
        self.calls_failed = 0
        self._counter_lock = Lock()
        if self.rate_limiter is None and self.requests_per_minute > 0:
            self.rate_limiter = ApiFootballRateLimiter(self.requests_per_minute)

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        clean_params = {key: value for key, value in params.items() if value is not None}
        for attempt in range(1, self.max_retries + 1):
            if self.rate_limiter is not None:
                self.rate_limiter.acquire()
            with self._counter_lock:
                self.calls_total += 1
            try:
                response = self._client.get(path, params=clean_params)
                if response.status_code == 401:
                    raise ApiFootballError("api_football_auth_failed")
                if response.status_code == 429 or response.status_code >= 500:
                    raise ApiFootballRetryableError(
                        f"api_football_retryable_status={response.status_code}"
                    )
                response.raise_for_status()
                payload = response.json()
                errors = payload.get("errors")
                if errors:
                    if _is_rate_limit_error(errors):
                        raise ApiFootballRetryableError(f"api_football_errors={errors}")
                    raise ApiFootballError(f"api_football_errors={errors}")
                return payload
            except ApiFootballRetryableError as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    with self._counter_lock:
                        self.calls_failed += 1
                    raise ApiFootballError(str(exc)) from exc
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
            except ApiFootballError:
                with self._counter_lock:
                    self.calls_failed += 1
                raise
            except Exception as exc:  # noqa: BLE001 - retry surface is intentionally broad
                last_error = exc
                if attempt >= self.max_retries:
                    with self._counter_lock:
                        self.calls_failed += 1
                    break
                time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise ApiFootballError(f"api_football_request_failed path={path}") from last_error

    def response(self, path: str, **params: Any) -> list[dict[str, Any]]:
        payload = self.get(path, **params)
        response = payload.get("response")
        if isinstance(response, list):
            return response
        return []

    def paginated_response(self, path: str, **params: Any) -> list[dict[str, Any]]:
        first_payload = self.get(path, page=1, **params)
        rows = first_payload.get("response") or []
        paging = first_payload.get("paging") or {}
        total = int(paging.get("total") or 1)
        for page in range(2, total + 1):
            payload = self.get(path, page=page, **params)
            page_rows = payload.get("response") or []
            if isinstance(page_rows, list):
                rows.extend(page_rows)
        return rows if isinstance(rows, list) else []
