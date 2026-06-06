"""APScheduler integration — registers the 1-minute polling job.

Kept dependency-free at import: the real ``AsyncIOScheduler`` is created by
the caller (typically the FastAPI startup hook) and passed to ``register``.
That makes the worker boot-time wiring testable with a plain ``MagicMock``.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.workers.translation_filler.runner import run

# How often to invoke `runner.run`. Spec §16 fixes 60 s; we restate in
# minutes too because APScheduler's `interval` trigger accepts either keyword.
_INTERVAL_KWARGS = {"minutes": 1}
JOB_ID = "translation-filler"


def run_scheduled_translation_filler() -> None:
    """Run one translation-filler cycle from a sync APScheduler executor."""
    asyncio.run(run())


def register(scheduler: Any) -> None:
    """Add the polling job to a caller-supplied APScheduler instance."""
    scheduler.add_job(
        run_scheduled_translation_filler,
        "interval",
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        **_INTERVAL_KWARGS,
    )


# Backwards-compatible alternate entry name expected by tests.
def add_jobs(scheduler: Any) -> None:  # pragma: no cover — tested via register
    register(scheduler)
