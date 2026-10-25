from copy import deepcopy

import pytest

from app.schemas.home_preview import PreviewPayload
from app.services.home_preview_players import record_notes, streaks
from tests.unit.test_home_preview_api_football import snapshot


def game(goals=1, assists=0, pid=99):
    return [
        {"player": {"id": pid}, "statistics": [{"goals": {"total": goals, "assists": assists}}]}
    ]


def test_streaks_stop_at_missing_game_unknown_values_or_zero_not_previous_scores():
    assert streaks([game(), game(), game(0), game()], 99)["scoring_streak"] == 2
    assert streaks([game(), None, game()], 99)["scoring_streak"] == 1
    assert streaks([None, game(), game()], 99)["scoring_streak"] == 0
    assert streaks([game(None, None), game()], 99)["involvement_streak"] == 0
    assert streaks([game(0, 1), game(1, 0)], 99)["involvement_streak"] == 2
    assert streaks([game(pid=98), game()], 99)["scoring_streak"] == 0


def example():
    v = snapshot()
    v["generated_at"] = v["as_of"]
    v["sources"] = [
        {
            "id": "player-db",
            "fixture_id": 1557444,
            "kind": "db",
            "title": "Known records",
            "url": None,
            "published_at": None,
            "retrieved_at": v["as_of"],
        }
    ]
    p = {
        "team_id": 40,
        "player_id": 99,
        "player_name": "선수",
        "canonical_name": "Player",
        "season_year": 2026,
        "appearances": 7,
        "goals": 4,
        "assists": 1,
        "minutes": 500,
        "recent_match_count": 5,
        "scoring_streak": 3,
        "assist_streak": 0,
        "involvement_streak": 3,
        "source_ids": ["player-db"],
    }
    p["record_notes"] = record_notes(p)
    v["facts"]["player_spotlights"] = {
        "status": "available",
        "reason": None,
        "as_of": v["as_of"],
        "source_ids": ["player-db"],
        "data": [p],
    }
    v["analysis"]["player_watchpoints"] = {
        "status": "available",
        "reason": None,
        "as_of": v["as_of"],
        "source_ids": ["player-db"],
        "data": [
            {
                "team_id": 40,
                "player_id": 99,
                "focus": "scoring_streak",
                "evidence_ids": ["player-db"],
            }
        ],
    }
    return v


def test_watchpoint_text_comes_from_verified_stats_not_model():
    v = example()
    PreviewPayload.model_validate(v)
    assert "3경기" in v["facts"]["player_spotlights"]["data"][0]["record_notes"]["scoring_streak"]
    assert v["facts"]["player_spotlights"]["data"][0]["record_notes"]["assist_streak"] is None


@pytest.mark.parametrize(
    "mutation", ["unknown", "duplicate", "unverified_focus", "over_sample", "team_limit"]
)
def test_invalid_player_watchpoint_is_rejected(mutation):
    v = example()
    p = v["facts"]["player_spotlights"]["data"][0]
    pick = v["analysis"]["player_watchpoints"]["data"][0]
    if mutation == "unknown":
        pick["player_id"] = 123
    if mutation == "duplicate":
        v["analysis"]["player_watchpoints"]["data"].append(deepcopy(pick))
    if mutation == "unverified_focus":
        pick["focus"] = "assist_streak"
    if mutation == "over_sample":
        p["scoring_streak"] = 6
    if mutation == "team_limit":
        for pid in [100, 101]:
            v["facts"]["player_spotlights"]["data"].append({**deepcopy(p), "player_id": pid})
            v["analysis"]["player_watchpoints"]["data"].append({**deepcopy(pick), "player_id": pid})
    with pytest.raises(ValueError):
        PreviewPayload.model_validate(v)


def test_recent_form_keeps_field_sample_counts_and_unknown_values():
    from app.services.home_preview_players import recent_form

    played = {
        "player": {"id": 99},
        "statistics": [{"games": {"minutes": 70}, "goals": {"total": 1, "assists": None}}],
    }
    known_zero = {
        "player": {"id": 99},
        "statistics": [{"games": {"minutes": 60}, "goals": {"total": 0, "assists": 1}}],
    }
    bench = {
        "player": {"id": 99},
        "statistics": [{"games": {"minutes": 0}, "goals": {"total": 0, "assists": None}}],
    }
    result = recent_form([[played], None, [known_zero], [bench]], 99)
    assert result == {
        "team_match_count": 4,
        "observed_appearances": 2,
        "goals": 1,
        "assists": 1,
        "minutes": 130,
        "goal_samples": 2,
        "assist_samples": 1,
        "minute_samples": 2,
    }
    missing = recent_form([None, game(None, None)], 99)
    assert (
        missing["goals"] is None
        and missing["minutes"] is None
        and missing["observed_appearances"] == 0
    )
