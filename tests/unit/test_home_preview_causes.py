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


def parsed_page(html, url=URL):
    from app.services.home_preview_web import PageText, normalized

    parser = PageText()
    parser.feed(html)
    return {
        "url": url,
        "text": normalized(" ".join(parser.parts)),
        "title": "Official club news",
        "dates": parser.primary_dates or parser.dates,
        "digest": "context-page-hash",
        "passages": parser.passages,
        "links": parser.links,
    }


def test_day_precision_official_release_and_split_incident_paragraph_resolve_october_17():
    value = payload()
    target = value["facts"]["injuries"]["data"][0]
    target.update(player_name="Jeremie Frimpong", detail="Muscle Injury")
    target["importance_evidence"]["recognition_name"] = "Jeremie Frimpong"
    source = parsed_page(
        '<head><meta property="article:published_time" content="2026-10-19"></head><h1>Liverpool: updates on Szoboszlai and Frimpong</h1><p>Szoboszlai was forced off in Saturday’s 2-1 victory at Brentford, while Frimpong had to be substituted shortly after coming on as a half-time substitute.</p><p>Jeremie Frimpong is obviously a new muscle injury and we will wait until he recovers.</p>'
    )
    item = {
        **candidate(),
        "reason_code": "muscle",
        "quote": "a malformed redundant quote",
        "cause_quotes": ["Jeremie Frimpong", "a new muscle injury"],
        "occurred_on": "2026-10-17",
        "occurrence_quote": "Frimpong had to be substituted",
        "occurrence_quotes": ["Saturday’s 2-1 victory at Brentford"],
    }
    from app.services.home_preview_causes import verified_cause

    data, published = verified_cause(
        item, source, value, target, now=NOW, aliases={40: "Liverpool"}
    )
    assert data["occurred_on"] == "2026-10-17" and published is None
    result, _ = evidence(item, source)(value, now=NOW)
    assert result["sources"][-1]["published_on"] == "2026-10-19"
    assert result["sources"][-1]["published_at"] is None


def test_player_heading_binds_multiple_paragraphs_without_requiring_name_in_every_excerpt():
    from app.services.home_preview_causes import verified_cause

    source = parsed_page(
        '<head><meta property="article:published_time" content="2026-10-24"></head><h1>Liverpool injury news</h1><h2>Alex Scott</h2><p>Type of injury: Thigh.</p><p>Scott played against Brentford on October 18.</p><p>Unfortunately, he aggravated the same injury and was forced off.</p>'
    )
    item = {
        **candidate(),
        "quote": "Type of injury: Thigh.",
        "occurrence_quote": "Scott played against Brentford on October 18.",
        "occurrence_quotes": ["he aggravated the same injury and was forced off."],
    }
    value = payload()
    data, _ = verified_cause(
        item,
        source,
        value,
        value["facts"]["injuries"]["data"][0],
        now=NOW,
        aliases={40: "Liverpool"},
    )
    assert data["occurred_on"] == "2026-10-18" and data["label"] == "허벅지 부상 재발"


def test_another_players_heading_cannot_supply_this_players_injury_type():
    import pytest

    from app.services.home_preview_causes import verified_cause

    source = parsed_page(
        '<head><meta property="article:published_time" content="2026-10-24"></head><h1>Liverpool news</h1><h2>Alex Scott</h2><p>Training update.</p><h2>Another Player</h2><p>Type of injury: Thigh.</p>'
    )
    item = {**candidate(), "quote": "Type of injury: Thigh."}
    value = payload()
    with pytest.raises(ValueError, match="cause_player"):
        verified_cause(
            item,
            source,
            value,
            value["facts"]["injuries"]["data"][0],
            now=NOW,
            aliases={40: "Liverpool"},
        )


def test_linked_sources_verify_distinct_cause_and_incident_claims_but_unrelated_sources_do_not():
    from app.services.home_preview_causes import verified_cause

    value = payload()
    target = value["facts"]["injuries"]["data"][0]
    primary = page()
    primary["text"] = "Liverpool: " + QUOTE
    primary["links"] = ["https://www.liverpoolfc.com/news/original-incident"]
    event = {**page(), "url": primary["links"][0]}
    data, _ = verified_cause(
        candidate(),
        primary,
        value,
        target,
        now=NOW,
        aliases={40: "Liverpool"},
        occurrence_page=event,
    )
    assert data["occurred_on"] == "2026-10-18"
    primary["links"] = []
    data, _ = verified_cause(
        candidate(),
        primary,
        value,
        target,
        now=NOW,
        aliases={40: "Liverpool"},
        occurrence_page=event,
    )
    assert data["occurred_on"] is None and data["label"] == "허벅지 부상"


def test_old_wrong_year_report_is_not_treated_as_current_injury_evidence():
    import pytest

    from app.services.home_preview_causes import verified_cause

    source = page()
    source["dates"] = ["2024-04-23"]
    value = payload()
    with pytest.raises(ValueError, match="publication"):
        verified_cause(
            candidate(),
            source,
            value,
            value["facts"]["injuries"]["data"][0],
            now=NOW,
            aliases={40: "Liverpool"},
        )


def test_incident_date_is_not_discarded_merely_because_same_paragraph_also_has_a_return_date():
    from app.services.home_preview_causes import verified_cause

    source = page()
    phrase = "Alex Scott sustained a thigh injury on 18 October 2026 but could return on 24 October 2026."
    source["text"] += " " + phrase
    item = {**candidate(), "occurrence_quote": phrase}
    value = payload()
    target = value["facts"]["injuries"]["data"][0]
    data, _ = verified_cause(item, source, value, target, now=NOW, aliases={40: "Liverpool"})
    assert data["occurred_on"] == "2026-10-18"
    item["occurred_on"] = "2026-10-24"
    data, _ = verified_cause(item, source, value, target, now=NOW, aliases={40: "Liverpool"})
    assert data["occurred_on"] is None
