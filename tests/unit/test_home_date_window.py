from __future__ import annotations

from datetime import date, datetime, timezone


def test_date_window_week_starts_on_monday_kst():
    from app.services.home import _date_window

    start, end = _date_window(date(2026, 5, 30), "week")

    assert start == datetime(2026, 5, 24, 15, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 31, 15, 0, tzinfo=timezone.utc)


def test_date_window_month_starts_on_first_day_kst():
    from app.services.home import _date_window

    start, end = _date_window(date(2026, 5, 30), "month")

    assert start == datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 31, 15, 0, tzinfo=timezone.utc)

