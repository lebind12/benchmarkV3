from __future__ import annotations

import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core import worker_scheduler

pytestmark = pytest.mark.unit


def test_worker_scheduler_registers_daily_sync_and_translation_jobs(monkeypatch):
    fake_scheduler = MagicMock()
    fake_background_scheduler = MagicMock(return_value=fake_scheduler)

    monkeypatch.setattr(
        worker_scheduler,
        "get_settings",
        lambda: SimpleNamespace(worker_scheduler_enabled=True),
    )

    apscheduler_module = ModuleType("apscheduler")
    schedulers_module = ModuleType("apscheduler.schedulers")
    background_module = ModuleType("apscheduler.schedulers.background")
    background_module.BackgroundScheduler = fake_background_scheduler
    monkeypatch.setitem(sys.modules, "apscheduler", apscheduler_module)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", schedulers_module)
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.background", background_module)

    scheduler = worker_scheduler.start_worker_scheduler()

    assert scheduler is fake_scheduler
    job_ids = [call.kwargs["id"] for call in fake_scheduler.add_job.call_args_list]
    assert job_ids == ["daily-sync", "translation-filler", "news-translator"]
    fake_scheduler.start.assert_called_once()
