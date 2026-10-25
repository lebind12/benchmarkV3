import json
from datetime import UTC, datetime

from app.core.config import Settings
from app.services.home_preview_causes import WebAbsenceCauses, targets_from
from app.services.home_preview_vertex import VertexPreviewProvider
from tests.unit.test_home_preview_causes import URL, candidate, page, payload

NOW = datetime(2026, 10, 25, tzinfo=UTC)


def configured(*, invented=False, future=False):
    calls = []

    def fetch(url):
        calls.append(("fetch", url))
        value = page()
        if future:
            value["dates"] = ["2026-10-26T12:00:00Z"]
        return value

    provider = VertexPreviewProvider(
        Settings(_env_file=None, google_cloud_project="test"),
        source_fetcher=fetch,
        clock=lambda: NOW,
    )

    def request(body):
        if "tools" in body:
            calls.append(("search", None))
            assert body.get("generationConfig", {}).get("responseSchema") is None
            return (
                "Cited original source",
                {
                    "webSearchQueries": ["Scott injury official"],
                    "groundingChunks": [{"web": {"uri": URL}}],
                    "searchEntryPoint": {
                        "renderedContent": "<div>Original Google suggestions</div>"
                    },
                },
                {"totalTokenCount": 10},
            )
        calls.append(("extract", None))
        schema = body["generationConfig"]["responseSchema"]
        assert schema["properties"]["candidates"]["items"]["properties"]["source_id"]["enum"] == ["s1"]
        source_input = json.loads(body["contents"][0]["parts"][0]["text"])
        assert source_input["sources"][0]["url"] == URL
        item = candidate()
        item.pop("url")
        item.pop("occurrence_url", None)
        item["source_id"] = "unknown" if invented else "s1"
        item["occurrence_source_id"] = "s1"
        return json.dumps({"candidates": [item]}), {}, {"totalTokenCount": 20}

    provider.request = request

    def discover(value, *, targets, now):
        return provider.discover_absence_causes(
            value, targets=targets, now=now, aliases={40: "Liverpool", 51: "Brighton"}
        )

    return provider, discover, calls


def test_search_citations_are_fetched_before_json_extraction_and_original_fetch_is_reused():
    provider, discover, calls = configured()
    result, usage = WebAbsenceCauses(
        discover,
        fetcher=provider.fetch_research_page,
        aliases={40: "Liverpool", 51: "Brighton"},
        clock=lambda: NOW,
    )(payload(), now=NOW)
    assert [step for step, _ in calls] == ["search", "fetch", "extract"]
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"]["occurred_on"] == "2026-10-18"
    assert usage["model_requests"] == 2 and usage["cause_extraction_requests"] == 1
    assert result["sources"][-1]["published_on"] == "2026-10-24"


def test_model_cannot_add_a_source_url_that_was_not_fetched():
    provider, discover, calls = configured(invented=True)
    result, usage = WebAbsenceCauses(
        discover, fetcher=provider.fetch_research_page, aliases={40: "Liverpool"}, clock=lambda: NOW
    )(payload(), now=NOW)
    assert usage["cause_verified"] == 0
    assert [url for step, url in calls if step == "fetch"] == [URL]
    assert result["facts"]["injuries"]["data"][0]["cause"]["data"] is None


def test_future_or_unusable_originals_do_not_reach_the_extraction_model():
    _provider, discover, calls = configured(future=True)
    candidates, _, usage = discover(payload(), targets=targets_from(payload()), now=NOW)
    assert candidates == [] and usage["model_requests"] == 1
    assert not any(step == "extract" for step, _ in calls)


def test_related_original_article_is_prioritized_before_source_budget_is_exhausted():
    provider, _discover, calls = configured()
    article = URL + "-scott-official-update"

    def request(body):
        if "tools" in body:
            return "sources", {"groundingChunks": [{"web": {"uri": URL}}] + [
                {"web": {"uri": URL + f"-{i}"}} for i in range(12)
            ]}, {}
        return json.dumps({"candidates": []}), {}, {}

    def fetch(url):
        calls.append(("fetch", url))
        value = page()
        value["url"] = url
        if url == URL:
            value["dates"] = []
            value["links"] = [article]
        return value

    provider.request = request
    provider.source_fetcher = fetch
    # fetch_research_page uses the injected fetcher stored by the provider.
    provider.discover_absence_causes(payload(), targets=targets_from(payload()), now=NOW,
                                    aliases={40: "Liverpool", 51: "Brighton"})
    assert [url for step, url in calls if step == "fetch"][:2] == [URL, article]
