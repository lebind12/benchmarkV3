import json
from copy import deepcopy

from app.services.home_preview_grounding import claim_grounding, resolve_sources, string_spans

URI = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/provider-link"
URL = "https://www.football365.com/match-preview/man-utd-v-bournemouth-prediction-preview"
QUOTE = "we are not expecting United to take all three points"


def inputs(*, quote=QUOTE, model_url=None):
    source = {"id": "f365", "publisher": "Football365", "title": "Original preview"}
    if model_url:
        source["url"] = model_url
    value = {
        "summary": {"text": "맨유의 승리가 어렵다는 외부 전망입니다.", "evidence_ids": ["f365"]},
        "external_forecasts": {
            "items": [
                {
                    "source_ids": ["f365"],
                    "evidence": [{"source_id": "f365", "claim": "승리가 어렵다", "quote": quote}],
                }
            ]
        },
        "source_catalog": [source],
    }
    raw = json.dumps(value, ensure_ascii=False)
    segment = value["summary"]["text"]
    start = raw.encode().index(segment.encode())
    grounding = {
        "groundingChunks": [{"web": {"uri": URI, "domain": "football365.com"}}],
        "groundingSupports": [
            {
                "segment": {
                    "startIndex": start,
                    "endIndex": start + len(segment.encode()),
                    "text": segment,
                },
                "groundingChunkIndices": [0],
            }
        ],
    }
    return value, raw, grounding


def fetch(url):
    assert url == URI
    return {
        "url": URL,
        "title": "Man Utd v Bournemouth preview",
        "text": QUOTE,
        "dates": ["2026-10-24T14:14:33+00:00"],
    }


def test_korean_byte_offsets_map_to_actual_json_field():
    _, raw, grounding = inputs()
    links, errors = claim_grounding(raw, grounding)
    assert errors == []
    assert [row["path"] for row in links] == [["summary", "text"]]
    assert links[0]["chunk_indices"] == [0]


def test_model_url_is_ignored_and_google_original_url_is_used_without_mutating_response():
    _, raw, grounding = inputs(model_url="https://www.football365.com/news/invented")
    before = json.loads(raw)
    result, report, _ = resolve_sources(raw, grounding, fetcher=fetch)
    assert result["source_catalog"][0]["url"] == URL
    assert result["source_catalog"][0]["published_at"] == "2026-10-24T14:14:33+00:00"
    assert result["source_catalog"][0]["verification"] == "original_quote_matched"
    assert result["summary"] == before["summary"]
    assert report["model_urls_used"] == 0
    assert json.loads(raw) == before


def test_same_publisher_with_wrong_quote_does_not_resolve_an_article():
    _, raw, grounding = inputs(quote="This quote is not present")
    result, report, _ = resolve_sources(raw, grounding, fetcher=fetch)
    assert result["source_catalog"][0]["url"] is None
    assert report["sources"][0]["state"] == "unresolved"


def test_model_url_is_never_fetched_if_no_grounding_exists():
    _, raw, _ = inputs(model_url="https://fake-source.test/123")

    def never(_):
        raise AssertionError("model url was fetched")

    result, report, pages = resolve_sources(raw, {}, fetcher=never)
    assert pages == [] and result["source_catalog"][0]["url"] is None
    assert report["claim_links"] == 0


def test_explicit_user_reference_may_verify_quote_but_is_not_reported_as_google_grounding():
    _, raw, _ = inputs()

    def original(url):
        assert url == URL
        return {**fetch(URI), "url": URL}

    result, report, _ = resolve_sources(raw, {}, fetcher=original, reference_urls=[URL])
    assert result["source_catalog"][0]["url"] == URL
    assert report["sources"][0]["origin"] == "user_reference"
    assert result["grounding_links"] == []


def test_invalid_segment_text_does_not_attach_citation():
    _, raw, grounding = inputs()
    grounding["groundingSupports"][0]["segment"]["text"] = "different"
    links, errors = claim_grounding(raw, grounding)
    assert links == [] and errors == ["segment_text_mismatch"]


def test_nonzero_part_index_is_not_incorrectly_attached_to_joined_text():
    _, raw, grounding = inputs()
    grounding["groundingSupports"][0]["segment"]["partIndex"] = 1
    links, errors = claim_grounding(raw, grounding)
    assert links == [] and errors == ["unsupported_segment"]


def test_quote_match_cannot_assign_a_different_publisher():
    value, _, grounding = inputs()
    value["source_catalog"][0]["publisher"] = "Sports Mole"
    result, _, _ = resolve_sources(json.dumps(value, ensure_ascii=False), grounding, fetcher=fetch)
    assert result["source_catalog"][0]["url"] is None


def test_escaped_strings_and_arrays_have_correct_utf8_spans():
    raw = json.dumps({"array": [{"text": '한글 "인용" 문장'}], "empty": []}, ensure_ascii=False)
    path, start, end = next(row for row in string_spans(raw) if row[0] == ("array", 0, "text"))
    assert path == ("array", 0, "text")
    assert json.loads('"' + raw.encode()[start:end].decode() + '"') == '한글 "인용" 문장'


def test_attribution_uses_provider_url_even_when_original_cannot_be_fetched():
    _, raw, grounding = inputs()

    def unavailable(_):
        raise ValueError("unavailable")

    result, report, _ = resolve_sources(raw, grounding, fetcher=unavailable)
    link = result["grounding_links"][0]
    source = next(s for s in result["source_catalog"] if s["id"] in link["source_ids"])
    assert source["url"] == URI
    assert source["verification"] == "grounding_attribution"
    assert report["fetch_failures"][0]["reason"] == "unavailable"


def test_ambiguous_originals_do_not_silently_choose_a_url():
    _, raw, grounding = inputs()
    grounding = deepcopy(grounding)
    grounding["groundingChunks"].append({"web": {"uri": URI + "-second"}})

    def original(url):
        page = fetch(URI)
        if url.endswith("second"):
            page["url"] = URL + "-different"
        return page

    result, report, _ = resolve_sources(raw, grounding, fetcher=original)
    assert result["source_catalog"][0]["url"] is None
    assert report["sources"][0]["state"] == "ambiguous_original"


def test_sports_illustrated_name_maps_to_si_domain():
    from app.services.home_preview_grounding import publisher_matches

    assert publisher_matches("Sports Illustrated", "https://www.si.com/soccer/preview")
    assert not publisher_matches("Sports Illustrated", URL)


def test_typographic_quote_and_score_dash_normalization_does_not_change_wording():
    from app.services.home_preview_grounding import quote_key

    assert quote_key("Prediction: Man Utd 1–1 Bournemouth") == quote_key(
        "Prediction: Man Utd 1-1 Bournemouth"
    )
    assert quote_key("we’re expecting a draw") == quote_key("we're expecting a draw")
    assert quote_key("Man Utd 1-1 Bournemouth") != quote_key("Man Utd 2-1 Bournemouth")


def test_similar_looking_domain_cannot_impersonate_a_publisher():
    from app.services.home_preview_grounding import publisher_matches

    assert not publisher_matches("Football365", "https://football365.com.evil.test/news")
    assert not publisher_matches("Football365", "https://football365fake.com/news")
    assert publisher_matches("Sports Mole", "https://www.sportsmole.co.uk/football/preview")
