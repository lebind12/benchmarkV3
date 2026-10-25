from datetime import UTC, datetime

import pytest

from app.services.home_preview_web import WebPreviewEvidence, allowed_url, verified_candidate
from tests.unit.test_home_preview_api_football import snapshot

NOW = datetime(2026, 10, 25, tzinfo=UTC)
URL = "https://www.sportsmole.co.uk/test-fixture"
QUOTE = "We say: Liverpool 1-2 Brighton"


def candidate():
    return {
        "kind": "prediction",
        "url": URL,
        "fixture_id": 1557444,
        "home_id": 40,
        "away_id": 51,
        "match_date": "2026-10-25",
        "home_goals": 1,
        "away_goals": 2,
        "quote": QUOTE,
    }


def page():
    return {
        "url": URL,
        "text": "Liverpool Brighton match 25 October 2026. " + QUOTE,
        "title": "Test source",
        "dates": ["2026-10-24T12:00:00Z"],
        "digest": "test-page-sha256",
    }


def discovery(payload, *, now):
    return (
        [candidate()],
        {
            "webSearchQueries": ["Liverpool Brighton prediction"],
            "searchEntryPoint": {
                "renderedContent": "<div>Provider supplied search suggestion</div>"
            },
            "groundingChunks": [{"web": {"uri": URL}}],
        },
        {"totalTokenCount": 50},
    )


def test_only_original_verified_score_is_published_with_suggestions_and_registry():
    result, usage = WebPreviewEvidence(discovery, fetcher=lambda _: page(), clock=lambda: NOW)(
        snapshot(), now=NOW
    )
    assert result["external"]["predictions"]["data"][0]["outlook"] == "Brighton 우세 전망"
    assert (
        result["search_suggestions"]["rendered_content"]
        == "<div>Provider supplied search suggestion</div>"
    )
    assert usage["_evidence"][0]["quote"] == QUOTE
    assert usage["model_requests"] == 1


@pytest.mark.parametrize("mutation", ["quote", "fixture", "future", "reversed", "unknown_url"])
def test_generated_claims_without_original_confirmation_stay_unverified(mutation):
    value = candidate()
    source = page()
    if mutation == "quote":
        value["quote"] = "Invented quotation"
    if mutation == "fixture":
        value["fixture_id"] = 22
    if mutation == "future":
        source["dates"] = ["2026-10-25T15:00:00Z"]
    if mutation == "reversed":
        value["home_goals"] = 2
        value["away_goals"] = 1
    if mutation == "unknown_url":
        value["url"] = "https://example.test/invented"

    def lookup(payload, *, now):
        _, grounding, tokens = discovery(payload, now=now)
        return [value], grounding, tokens

    result, _ = WebPreviewEvidence(lookup, fetcher=lambda _: source, clock=lambda: NOW)(
        snapshot(), now=NOW
    )
    assert result["external"]["predictions"]["data"] is None
    assert result["external"]["predictions"]["status"] == "unverified"
    assert result["search_suggestions"] is None


def test_unambiguous_fractional_odds_are_converted_and_reversed_labels_rejected():
    quote = "90 minute Liverpool 11/10 Draw 11/4 Brighton 21/10 Betfair"
    value = {
        **candidate(),
        "kind": "odds",
        "bookmaker": "Betfair",
        "market": "1x2_90min",
        "original_values": {"home": "11/10", "draw": "11/4", "away": "21/10"},
        "quote": quote,
    }
    source = {**page(), "text": page()["text"] + " " + quote}
    data, _, _ = verified_candidate(value, source, snapshot(), now=NOW)
    assert data["home"] == 2.1 and data["draw"] == 3.75 and data["away"] == 3.1
    value["original_values"]["home"] = "21/10"
    with pytest.raises(ValueError):
        verified_candidate(value, source, snapshot(), now=NOW)


def test_private_destinations_and_unapproved_hosts_rejected_before_fetch(monkeypatch):
    with pytest.raises(ValueError):
        allowed_url("http://localhost/internal")
    with pytest.raises(ValueError):
        allowed_url("https://example.test/internal")
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(ValueError):
        allowed_url("https://www.liverpoolfc.com/news")


def test_verified_editorial_excerpt_is_appended_even_with_api_prediction():
    payload = snapshot()
    payload["sources"].append(
        {
            "id": "api-prediction",
            "fixture_id": 1557444,
            "kind": "api",
            "title": "API-Football",
            "url": "https://v3.football.api-sports.io/predictions?fixture=1557444",
            "published_at": None,
            "retrieved_at": NOW.isoformat(),
        }
    )
    payload["as_of"] = NOW.isoformat()
    payload["external"]["predictions"] = {
        "status": "available",
        "reason": None,
        "as_of": NOW.isoformat(),
        "source_ids": ["api-prediction"],
        "data": [
            {"source_id": "api-prediction", "outlook": "API outlook", "summary": "API advice"}
        ],
    }
    quote = "We expect Liverpool to have the edge against Brighton."
    item = {**candidate(), "opinion_excerpt": True, "quote": quote}
    source = {**page(), "text": "Liverpool Brighton 25 October 2026. " + quote}

    def discover(payload, *, now):
        _, grounding, tokens = discovery(payload, now=now)
        return [item], grounding, tokens

    result, usage = WebPreviewEvidence(discover, fetcher=lambda _: source, clock=lambda: NOW)(
        payload, now=NOW
    )
    rows = result["external"]["predictions"]["data"]
    assert len(rows) == 2 and rows[0]["summary"] == "API advice"
    assert rows[1]["summary"] == quote and rows[1]["outlook"] == "외부 기사·칼럼 의견"
    assert usage["model_requests"] == 1
    item["quote"] = "We expect an invented claim about Liverpool."
    result, _ = WebPreviewEvidence(discover, fetcher=lambda _: source, clock=lambda: NOW)(
        payload, now=NOW
    )
    assert result["external"]["predictions"]["data"] == payload["external"]["predictions"]["data"]
