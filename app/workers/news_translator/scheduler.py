"""APScheduler registration for news-translator."""
from __future__ import annotations

from app.workers.news_translator import POLL_INTERVAL_SEC
from app.workers.news_translator.runner import run


def register(scheduler) -> None:
    scheduler.add_job(
        run,
        "interval",
        seconds=POLL_INTERVAL_SEC,
        id="news-translator",
        replace_existing=True,
        max_instances=1,
    )
