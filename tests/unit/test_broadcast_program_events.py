from __future__ import annotations

import pytest

from app.services.broadcast_program import _event_summary

pytestmark = pytest.mark.unit


def test_event_summary_counts_own_goals_separately_from_goals() -> None:
    events = [
        {
            "type": "Goal",
            "detail": "Own Goal",
            "player": {"id": 10, "name": "Own Goal Player"},
        },
        {
            "type": "Goal",
            "detail": "Normal Goal",
            "player": {"id": 11, "name": "Goal Player"},
        },
    ]

    result = _event_summary(events, {})

    assert result[10]["ownGoals"] == 1
    assert result[10]["goals"] == 0
    assert result[11]["ownGoals"] == 0
    assert result[11]["goals"] == 1
