"""Unit tests for broadcast momentum scoring."""
from __future__ import annotations

import pytest

from app.services.broadcast_momentum import _calculate, _diff


pytestmark = pytest.mark.unit


def _state(
    *,
    home_score: int = 0,
    away_score: int = 0,
    home_stats: dict[str, float] | None = None,
    away_stats: dict[str, float] | None = None,
) -> dict:
    keys = {
        "xg": 0.0,
        "shots": 0.0,
        "shotsOnGoal": 0.0,
        "insideBoxShots": 0.0,
        "corners": 0.0,
        "possession": 50.0,
        "passes": 0.0,
        "passesAccurate": 0.0,
        "yellowCards": 0.0,
        "redCards": 0.0,
    }
    home = {**keys, **(home_stats or {})}
    away = {**keys, **(away_stats or {})}
    return {
        "elapsed": 63,
        "extra": None,
        "minuteKey": 63,
        "displayMinute": "63'",
        "capturedAt": "2026-06-14T00:00:00Z",
        "score": {"home": home_score, "away": away_score},
        "stats": {"home": home, "away": away},
        "eventCounts": {"home": {"dangerEvents": 0.0}, "away": {"dangerEvents": 0.0}},
    }


def test_momentum_base_prevents_single_corner_from_overstating_flow():
    result = _calculate(
        [{"elapsed": 63, "home": {"corners": 1.0}, "away": {}}],
        updated_at="2026-06-14T00:00:00Z",
    )

    assert result["home"] <= 55
    assert result["away"] >= 45
    assert result["dominance"] == "low"


def test_momentum_separates_balanced_tempo_from_dominance():
    sample = {
        "elapsed": 63,
        "home": {"shots": 5.0, "shotsOnGoal": 3.0, "insideBoxShots": 4.0},
        "away": {"shots": 5.0, "shotsOnGoal": 3.0, "insideBoxShots": 4.0},
    }

    result = _calculate([sample], updated_at="2026-06-14T00:00:00Z")

    assert result["trend"] == "balanced"
    assert result["intensity"] == "low"
    assert result["dominance"] == "low"
    assert result["tempo"] == "high"
    assert result["activity"] >= 15


def test_momentum_uses_score_delta_for_goals():
    previous = _state(home_score=0, away_score=0)
    current = _state(home_score=1, away_score=0)

    sample = _diff(current, previous)

    assert sample["home"]["goals"] == 1
    assert sample["away"]["goals"] == 0


def test_momentum_uses_red_card_state_as_persistent_bias():
    current = _state(away_stats={"redCards": 1.0})
    result = _calculate(
        [{"elapsed": 63, "home": {}, "away": {}}],
        updated_at="2026-06-14T00:00:00Z",
        current=current,
    )

    assert result["home"] > 50
    assert result["home"] < 60


def test_momentum_does_not_use_possession_delta_as_attack_signal():
    result = _calculate(
        [{"elapsed": 63, "home": {"possession": 10.0}, "away": {}}],
        updated_at="2026-06-14T00:00:00Z",
    )

    assert result["home"] == 50
    assert result["away"] == 50
