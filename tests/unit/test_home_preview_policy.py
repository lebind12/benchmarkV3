from types import SimpleNamespace

from app.schemas.home_preview import clock
from app.services.home_preview_policy import category, priority, slot_time


def league(id, type="Cup", country="England"):
    return SimpleNamespace(external_id=id, type=type, country_name=country, country_code="GB")


def test_all_eight_priority_groups_and_dynamic_cup_identity():
    assert priority(league(39, "League"), 40, 51, "Regular Season - 8") == 1
    assert priority(league(39, "League"), 51, 66, "Regular Season - 8") == 2
    assert priority(league(2), 40, 157, "Quarter-finals") == 3
    assert priority(league(2), 157, 505, "Final") == 4
    assert priority(league(2), 157, 505, "Semi-finals") == 5
    assert priority(league(3), 51, 505, "Final") == 6
    assert priority(league(999), 40, 51, "Round of 16") == 7
    assert priority(league(2), 157, 505, "Quarter-finals") == 8
    assert priority(league(2), 157, 505, "League Stage - 1") is None
    assert category(league(999, country="Scotland")) == "other"
    assert priority(league(999, country="Scotland"), 40, 51, "Final") is None


def test_slot_is_kst_six_hour_bucket():
    assert slot_time(clock("2026-10-25T00:10:00Z")) == clock("2026-10-24T21:00:00Z")
    assert slot_time(clock("2026-10-25T03:00:00Z")) == clock("2026-10-25T03:00:00Z")


def test_fingerprint_ignores_observation_noise_but_refreshes_on_sla_slot():
    from copy import deepcopy

    from app.services.home_preview_generation import snapshot_fingerprint
    from tests.unit.test_home_preview_api_football import snapshot

    value = snapshot()
    later = deepcopy(value)
    later["as_of"] = "2026-10-25T00:01:00Z"
    first = snapshot_fingerprint(value, model="test", now=clock("2026-10-25T00:00:00Z"))
    assert first == snapshot_fingerprint(later, model="test", now=clock("2026-10-25T00:01:00Z"))
    assert first != snapshot_fingerprint(later, model="test", now=clock("2026-10-25T03:00:00Z"))


def test_generation_due_is_last_regular_collection_strictly_before_kickoff():
    from datetime import timedelta

    from app.services.home_preview_policy import generation_due_at, in_generation_window

    for hour in (3, 9, 15, 21):
        kickoff = clock(f"2026-10-25T{hour:02}:00:00Z")
        assert generation_due_at(kickoff) == kickoff - timedelta(hours=6)
        assert generation_due_at(kickoff + timedelta(seconds=1)) == kickoff
        assert in_generation_window(kickoff, kickoff - timedelta(hours=6))
        assert not in_generation_window(kickoff, kickoff - timedelta(hours=6, seconds=1))
        assert not in_generation_window(kickoff, kickoff)
        assert not in_generation_window(kickoff, kickoff + timedelta(seconds=1))
