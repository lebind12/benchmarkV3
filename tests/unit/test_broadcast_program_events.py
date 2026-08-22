from __future__ import annotations

import pytest

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.broadcast_program import (
    _event_kind,
    _event_summary,
    _lookup_team_colors,
    _normalize_lineups,
)

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


def test_lookup_team_colors_uses_external_team_ids() -> None:
    session = MagicMock()
    session.execute.return_value = [
        SimpleNamespace(
            external_id=40,
            primary_color="#C8102E",
            secondary_color="#F6EB61",
            accent_color="#00B2A9",
            scoreboard_color_mode="PRIMARY_LIGHT",
        ),
        SimpleNamespace(
            external_id=42,
            primary_color="#EF0107",
            secondary_color="#063672",
            accent_color="#9C824A",
            scoreboard_color_mode="PRIMARY_LIGHT",
        ),
    ]

    result = _lookup_team_colors(session, [42, 40, 42, None])

    assert result == {
        40: {
            "primaryColor": "#C8102E",
            "secondaryColor": "#F6EB61",
            "accentColor": "#00B2A9",
            "scoreboardColorMode": "PRIMARY_LIGHT",
        },
        42: {
            "primaryColor": "#EF0107",
            "secondaryColor": "#063672",
            "accentColor": "#9C824A",
            "scoreboardColorMode": "PRIMARY_LIGHT",
        },
    }
    session.execute.assert_called_once()


def test_normalize_lineups_includes_nullable_primary_color() -> None:
    lineups = [
        {
            "team": {"id": 40, "name": "Liverpool"},
            "formation": "4-3-3",
            "startXI": [],
            "substitutes": [],
        },
        {
            "team": {"id": 999_999, "name": "Unseeded FC"},
            "formation": "4-4-2",
            "startXI": [],
            "substitutes": [],
        },
    ]

    result = _normalize_lineups(
        lineups,
        translations={},
        player_stats={},
        summaries={},
        team_colors={
            40: {
                "primaryColor": "#C8102E",
                "secondaryColor": "#F6EB61",
                "accentColor": "#00B2A9",
                "scoreboardColorMode": "PRIMARY_LIGHT",
            }
        },
    )

    assert result[0]["primaryColor"] == "#C8102E"
    assert result[0]["secondaryColor"] == "#F6EB61"
    assert result[0]["accentColor"] == "#00B2A9"
    assert result[0]["scoreboardColorMode"] == "PRIMARY_LIGHT"
    assert result[1]["primaryColor"] is None
    assert result[1]["secondaryColor"] is None
    assert result[1]["accentColor"] is None
    assert result[1]["scoreboardColorMode"] is None
