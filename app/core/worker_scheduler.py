"""Backend worker scheduler lifecycle."""
from __future__ import annotations

import logging
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.workers.daily_sync import scheduler as daily_sync_scheduler


LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


def start_worker_scheduler() -> Any | None:
    """Start the in-process APScheduler worker scheduler."""
    settings = get_settings()
    if not settings.worker_scheduler_enabled:
        LOGGER.info("worker scheduler disabled by WORKER_SCHEDULER_ENABLED")
        return None

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ModuleNotFoundError:
        LOGGER.warning("APScheduler is not installed; worker scheduler was not started")
        return None

    scheduler = BackgroundScheduler(timezone=KST)
    daily_sync_scheduler.register(scheduler)
    scheduler.start()
    LOGGER.info("worker scheduler started")
    return scheduler


def shutdown_worker_scheduler(scheduler: Any | None) -> None:
    if scheduler is None:
        return
    scheduler.shutdown(wait=False)
