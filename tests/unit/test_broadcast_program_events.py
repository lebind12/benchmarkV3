from __future__ import annotations

import pytest

from app.services.broadcast_program import _event_kind, _event_summary

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


def test_goal_detail_exceptions_are_not_broadcast_goals() -> None:
    assert _event_kind({"type": "Goal", "detail": "Missed Penalty"}) == "penalty-missed"
    assert _event_kind({"type": "Goal", "detail": "Goal cancelled"}) == "goal-cancelled"
    assert _event_kind({"type": "Goal", "detail": "Goal disallowed"}) == "goal-cancelled"
    assert _event_kind({"type": "Goal", "detail": "Normal Goal"}) == "goal"

    result = _event_summary(
        [
            {"type": "Goal", "detail": "Missed Penalty", "player": {"id": 12, "name": "Penalty Player"}},
            {"type": "Goal", "detail": "Goal cancelled", "player": {"id": 13, "name": "Cancelled Player"}},
        ],
        {},
    )

    assert result[12]["goals"] == 0
    assert result[12]["ownGoals"] == 0
    assert result[13]["goals"] == 0
    assert result[13]["ownGoals"] == 0
