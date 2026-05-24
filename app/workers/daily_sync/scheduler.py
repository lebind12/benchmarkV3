"""APScheduler registration for daily-sync."""
from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from app.services import worker_runs


JOB_ID = "daily-sync"
KST = ZoneInfo("Asia/Seoul")
SCHEDULE_HOURS = "0,6,12,18"
SCHEDULE_MINUTE = 0


def run_scheduled_daily_sync() -> None:
    """Start a scheduled daily-sync run unless one is already active."""
    try:
        worker_runs.start_daily_sync_run()
    except RuntimeError:
        # The ADMIN manual trigger and the scheduler share the same run registry.
        # If a run is active, the next cron tick can safely try again.
        return


def register(scheduler: Any) -> None:
    scheduler.add_job(
        run_scheduled_daily_sync,
        "cron",
        id=JOB_ID,
        replace_existing=True,
        hour=SCHEDULE_HOURS,
        minute=SCHEDULE_MINUTE,
        timezone=KST,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=900,
    )


def add_jobs(scheduler: Any) -> None:  # pragma: no cover - compatibility alias
    register(scheduler)
