"""APScheduler registration for news-translator."""
from __future__ import annotations

import asyncio

from app.workers.news_translator import POLL_INTERVAL_SEC
from app.workers.news_translator.runner import run

JOB_ID = "news-translator"


def run_scheduled_news_translator() -> None:
    """Run one news-translator cycle from a sync APScheduler executor."""
    asyncio.run(run())


def register(scheduler) -> None:
    scheduler.add_job(
        run_scheduled_news_translator,
        "interval",
        seconds=POLL_INTERVAL_SEC,
        id=JOB_ID,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
