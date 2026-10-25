from copy import deepcopy
from datetime import UTC, datetime

from app.services.home_preview_causes import WebAbsenceCauses, targets_from
from tests.unit.test_home_preview_injuries import selection_payload

NOW = datetime(2026, 10, 25, tzinfo=UTC)
URL = "https://www.liverpoolfc.com/news/team-news"
QUOTE = "Alex Scott remains out with a thigh injury."
INCIDENT = "Alex Scott sustained a thigh injury on 18 October 2026."


def payload():
    v = selection_payload()
    row = v["facts"]["injuries"]["data"][0]
    row.update(player_name="Alex Scott", detail="Thigh Injury")
    row["importance_evidence"]["recognition_name"] = "Alex Scott"
    return v


def candidate():
    return {
        "team_id": 40,
        "player_id": 1,
        "url": URL,
        "reason_code": "thigh",
        "quote": QUOTE,
        "occurred_on": "2026-10-18",
        "occurred_month": None,
        "occurrence_quote": INCIDENT,
    }


def page():
    return {
        "url": URL,
        "text": "Liverpool Brighton 25 October 2026. " + QUOTE + " " + INCIDENT,
        "title": "Team news",
        "dates": ["2026-10-24T12:00:00Z"],
        "digest": "page-hash",
    }


def evidence(item=None, source=None):
    items = [item or candidate()]

    def discover(_payload, *, targets, now):
        assert len(targets) == 1 and targets[0]["player_id"] == 1
        return (
            items,
            {
                "webSearchQueries": ["Alex Scott injury when"],
                "groundingChunks": [{"web": {"uri": URL}}],
                "searchEntryPoint": {"renderedContent": "<div>Search suggestion</div>"},
            },
            {"totalTokenCount": 10},
        )

    return WebAbsenceCauses(
        discover,
        fetcher=lambda _: source or page(),
        aliases={40: "Liverpool", 51: "Brighton"},
        clock=lambda: NOW,
    )


def test_only_selected_players_receive_short_causes_and_incident_date_is_not_publication():
    original = payload()
    before = deepcopy(original)
    result, usage = evidence()(original, now=NOW)
    row = result["facts"]["injuries"]["data"][0]
    assert row["cause"]["data"] == {
        "code": "thigh",
        "label": "허벅지 부상",
        "occurred_on": "2026-10-18",
        "occurred_month": None,
    }
    assert all("cause" not in row for row in result["facts"]["injuries"]["data"][1:])
    assert result["analysis"] == before["analysis"] and original == before
    assert (
        usage["cause_targets"] == 1
        and usage["cause_verified"] == 1
        and usage["model_requests"] == 1
    )
    assert result["sources"][-1]["published_at"].startswith("2026-10-24")


def test_unknown_return_or_unverified_incident_dates_are_not_invented():
    item = candidate()
    item.update(
        occurred_on="2026-11-10",
        occurrence_quote="Alex Scott is expected to return on 10 November 2026.",
    )
    source = page()
    source["text"] += " " + item["occurrence_quote"]
    result, _ = evidence(item, source)(payload(), now=NOW)
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"]["occurred_on"] is None
    item = candidate()
    item.update(
        occurred_on=None,
        occurred_month="2026-09",
        occurrence_quote="Alex Scott has been out since September 2026 with a thigh injury.",
    )
    source = page()
    source["text"] += " " + item["occurrence_quote"]
    result, _ = evidence(item, source)(payload(), now=NOW)
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"]["occurred_month"] == "2026-09"


def test_relative_incident_day_requires_exact_publication_anchor():
    item = candidate()
    item.update(
        occurred_on="2026-10-22",
        occurrence_quote="Alex Scott sustained a thigh injury on Thursday.",
    )
    source = page()
    source["text"] += " " + item["occurrence_quote"]
    result, _ = evidence(item, source)(payload(), now=NOW)
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"]["occurred_on"] == "2026-10-22"


def test_conflicting_api_reason_and_unselected_candidates_cannot_replace_absence():
    item = candidate()
    item.update(reason_code="hamstring", quote="Alex Scott remains out with a hamstring injury.")
    source = page()
    source["text"] += " " + item["quote"]
    original = payload()
    original["facts"]["injuries"]["data"][0]["detail"] = "Knee Injury"
    result, _ = evidence(item, source)(original, now=NOW)
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"] is None
    item = candidate()
    item["player_id"] = 999
    result, usage = evidence(item)(payload(), now=NOW)
    assert (
        usage["cause_verified"] == 0
        and result["facts"]["injuries"]["data"][0]["availability"] == "out"
    )


def test_no_selection_means_no_discovery_and_target_limit_is_two_per_team():
    value = payload()
    value["analysis"]["key_absences"]["data"] = []

    def trap(*args, **kwargs):
        raise AssertionError("unselected injury search")

    result, usage = WebAbsenceCauses(trap)(value, now=NOW)
    assert usage["model_requests"] == 0 and result == value
    value = payload()
    value["analysis"]["key_absences"]["data"] = [{"team_id": 40, "player_id": i} for i in (1, 2, 3)]
    assert len(targets_from(value)) == 2
