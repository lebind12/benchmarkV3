"""Synthetic contract tests; these do not claim live article or football fact verification."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.schemas.home_preview import clock
from app.services.home_preview_production import (
    ProductionPreviewGenerator,
    generation_input,
    validate_direct_result,
)
from app.services.home_preview_web import update_prediction_coverage


def case():
    original = json.loads(
        (Path(__file__).parents[1] / "fixtures/home_preview/section-targets.json").read_text()
    )["payload"]
    now = clock(original["generated_at"])
    input_payload = deepcopy(original)
    input_payload["sources"] = [s for s in input_payload["sources"] if s["kind"] != "web"]
    input_payload["external"]["predictions"] = {
        "status": "missing",
        "reason": "not_collected",
        "as_of": None,
        "source_ids": [],
        "data": None,
    }
    template = generation_input(input_payload, now=now)["output_template"]
    result = deepcopy(template)
    result["sources"] += [s for s in original["sources"] if s["kind"] == "web"]
    result["analysis"] = deepcopy(original["analysis"])
    result["external"]["predictions"] = deepcopy(original["external"]["predictions"])
    update_prediction_coverage(result, candidate_count=3, checked_at=now)
    return now, input_payload, template, result


def test_full_json_is_returned_unchanged_with_original_response_and_redirect_audit():
    now, payload, template, result = case()
    validate_direct_result(template, result)
    urls = [s["url"] for s in result["sources"] if s["kind"] == "web"]
    grounding = {
        "groundingChunks": [
            {"web": {"uri": "https://grounding.test/" + str(i)}} for i in range(len(urls))
        ]
    }
    mapping = {chunk["web"]["uri"]: url for chunk, url in zip(grounding["groundingChunks"], urls)}

    def fetch(url):
        return {"url": mapping.get(url, url), "title": "Synthetic article", "text": "Test evidence"}

    vertex = SimpleNamespace(
        request=lambda body: (
            json.dumps(result, ensure_ascii=False),
            grounding,
            {"totalTokenCount": 10},
        )
    )
    saved, usage = ProductionPreviewGenerator(vertex, clock=lambda: now, fetcher=fetch)(payload)
    assert saved == result
    assert json.loads(usage["_direct_generation"]["raw_llm_text"]) == saved
    assert usage["_direct_generation"]["raw_llm_response"] == saved
    assert len(usage["_direct_generation"]["original_pages"]) == len(urls)


def test_ungrounded_url_is_rejected_and_invalid_json_retries_are_bounded():
    now, payload, _, result = case()
    generator = ProductionPreviewGenerator(
        None, clock=lambda: now, fetcher=lambda url: {"url": url}
    )
    with pytest.raises(ValueError, match="not_in_grounding"):
        generator.verify_sources(result, {})
    calls = []

    def request(body):
        calls.append(deepcopy(body))
        return "{}", {}, {}

    generator.vertex = SimpleNamespace(request=request)
    with pytest.raises(ValueError):
        generator(payload)
    assert len(calls) == 3
    assert "직전 검증 오류" in calls[1]["systemInstruction"]["parts"][0]["text"]


def test_model_cannot_rewrite_database_facts_or_identity():
    _, _, template, result = case()
    result["fixture"]["home"]["name"] = "Invented"
    with pytest.raises(ValueError):
        validate_direct_result(template, result)


def test_api_forecast_counts_once_and_two_web_publishers_complete_target():
    from app.services.home_preview_forecasts import forecast_source_keys

    _, _, _, result = case()
    rows = result["external"]["predictions"]["data"]
    result["external"]["predictions"]["data"] = rows[:2]
    result["sources"].append(
        {
            "id": "api-test",
            "kind": "api",
            "url": "https://v3.football.api-sports.io/predictions?fixture=1",
        }
    )
    rows = result["external"]["predictions"]["data"]
    rows.append({"source_id": "api-test", "outlook": "API view", "summary": "Algorithm"})
    web, api = forecast_source_keys(result)
    assert len(web) == 2 and len(api) == 1
    update_prediction_coverage(result, candidate_count=2, checked_at=clock(result["as_of"]))
    assert result["external"]["predictions"]["status"] == "available"
    assert result["external"]["predictions"]["coverage"]["total_source_count"] == 3
    rows.append(deepcopy(rows[-1]))
    assert forecast_source_keys(result) == (web, api)
