from __future__ import annotations

from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.workers.daily_sync import scheduler

pytestmark = pytest.mark.unit


def test_daily_sync_scheduler_registers_kst_four_times_daily():
    fake_scheduler = MagicMock()

    scheduler.register(fake_scheduler)

    fake_scheduler.add_job.assert_called_once()
    args, kwargs = fake_scheduler.add_job.call_args
    assert args[0] is scheduler.run_scheduled_daily_sync
    assert args[1] == "cron"
    assert kwargs["id"] == "daily-sync"
    assert kwargs["hour"] == "0,6,12,18"
    assert kwargs["minute"] == 0
    assert kwargs["timezone"] == ZoneInfo("Asia/Seoul")
    assert kwargs["max_instances"] == 1
    assert kwargs["coalesce"] is True


def test_scheduled_daily_sync_skips_when_run_already_active(monkeypatch):
    def fake_start_daily_sync_run():
        raise RuntimeError("already-running-run-id")

    monkeypatch.setattr(scheduler.worker_runs, "start_daily_sync_run", fake_start_daily_sync_run)

    scheduler.run_scheduled_daily_sync()
