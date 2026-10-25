"""Per-slot model budget, safe diagnostics and bounded per-stage transient retries."""

import math
import random
import time
from copy import deepcopy
from email.utils import parsedate_to_datetime

import httpx

from app.services.home_preview_policy import utcnow

TRANSIENT = {408, 429, 500, 502, 503, 504}
PROVIDER_CODES = {
    "RESOURCE_EXHAUSTED",
    "UNAVAILABLE",
    "INTERNAL",
    "DEADLINE_EXCEEDED",
    "INVALID_ARGUMENT",
    "PERMISSION_DENIED",
    "UNAUTHENTICATED",
    "NOT_FOUND",
}


def failure_details(exc, *, now):
    detail = {"failure_type": type(exc).__name__, "retryable": False}
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail.update(http_status=response.status_code, retryable=response.status_code in TRANSIENT)
        try:
            code = response.json().get("error", {}).get("status")
            if code in PROVIDER_CODES:
                detail["provider_code"] = code
        except (ValueError, AttributeError, TypeError):
            pass
        value = response.headers.get("Retry-After")
        if value:
            try:
                delay = max(0, float(value))
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(value) - now).total_seconds())
                except (ValueError, TypeError, OverflowError):
                    delay = None
            if delay is not None and not math.isnan(delay):
                detail["retry_after_seconds"] = min(delay, 86401)
    elif isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        detail["retryable"] = True
    if isinstance(exc, ValueError) and str(exc) in {
        "incomplete_model_response",
        "empty_model_response",
        "unknown_analysis_source",
        "model_request_budget_exhausted",
        "model_retry_budget_exhausted",
        "model_stage_budget_exhausted",
        "generation_deadline",
    }:
        detail["failure_code"] = str(exc)
    finish = getattr(exc, "preview_finish_reason", None)
    if finish in {
        "MAX_TOKENS",
        "SAFETY",
        "RECITATION",
        "OTHER",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
    }:
        detail["finish_reason"] = finish
    return detail


class ModelRun:
    def __init__(self, *, clock=utcnow, sleep=time.sleep, jitter=None):
        self.clock, self.sleep = clock, sleep
        self.jitter = jitter or (lambda: random.uniform(0, 5))
        self.started = False
        self.requests, self.retries = 0, 0
        self.events = []

    def start(self, *, usage, deadline, guard, persist):
        self.requests = usage.get("model_requests", 0)
        self.retries = usage.get("model_retries", 0)
        self.events = deepcopy(usage.get("model_events", []))
        self.deadline, self.guard, self.persist = deadline, guard, persist
        self.started = True

    def summary(self):
        return {
            "model_requests": self.requests,
            "model_retries": self.retries,
            "model_events": deepcopy(self.events),
        }

    def request(self, stage, operation, *, timeout):
        if not self.started:
            return operation(timeout)
        while True:
            self.guard()
            if self.requests >= 6:
                raise ValueError("model_request_budget_exhausted")
            stage_requests = sum(event["stage"] == stage for event in self.events)
            if stage_requests >= 2:
                raise ValueError("model_stage_budget_exhausted")
            remaining = (self.deadline - self.clock()).total_seconds()
            if remaining < 5:
                raise ValueError("generation_deadline")
            effective_timeout = min(timeout, remaining - 2)
            self.requests += 1
            event = {
                "request": self.requests,
                "stage": stage,
                "state": "running",
                "started_at": self.clock().isoformat(),
                "timeout_seconds": effective_timeout,
            }
            self.events.append(event)
            self.persist(self.summary())
            started = time.monotonic()
            try:
                result = operation(effective_timeout)
            except Exception as exc:
                event.update(
                    state="failed",
                    elapsed_ms=round((time.monotonic() - started) * 1000),
                    **failure_details(exc, now=self.clock()),
                )
                self.persist(self.summary())
                delay = event.get(
                    "retry_after_seconds",
                    (30 if event.get("http_status") == 429 else 10) + self.jitter(),
                )
                remaining = (self.deadline - self.clock()).total_seconds()
                if (
                    not event["retryable"]
                    or self.retries >= 3
                    or self.requests >= 6
                    or stage_requests >= 1
                    or delay > 60
                    or remaining < delay + timeout + 5
                ):
                    raise
                self.retries += 1
                event["retry_delay_seconds"] = delay
                self.persist(self.summary())
                self.sleep(delay)
                continue
            event.update(state="succeeded", elapsed_ms=round((time.monotonic() - started) * 1000))
            self.persist(self.summary())
            return result
