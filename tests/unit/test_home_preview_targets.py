"""Synthetic field-level regressions; natural-language meaning requires source review."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.schemas.home_preview import PreviewPayload
from app.services.home_preview_targets import (
    assert_content_preserved,
    form_metrics,
    section_target_report,
)


def payload():
    p = json.loads(
        (Path(__file__).parents[1] / "fixtures/home_preview/section-targets.json").read_text()
    )["payload"]
    row = p["facts"]["injuries"]["data"][0]
    row["cause"] = {
        "status": "available",
        "reason": None,
        "as_of": p["as_of"],
        "source_ids": ["web-sportsmole"],
        "data": {
            "code": None,
            "label": "부위 미공개 부상",
            "occurred_on": "2026-10-10",
            "occurred_month": None,
        },
    }
    return p


def test_fields_meet_goals_and_unknown_anatomy_keeps_date():
    p = payload()
    PreviewPayload.model_validate(p)
    assert section_target_report(p)["passed"]
    assert p["facts"]["injuries"]["data"][0]["cause"]["data"]["code"] is None


def test_natural_wording_is_not_a_keyword_or_sentence_gate():
    p = payload()
    p["analysis"]["player_watchpoints"]["data"][0]["reason"] = (
        "시즌 득점 기여와 직전 두 경기의 공격포인트가 이번 경기의 기대를 높입니다."
    )
    p["analysis"]["ai_prediction"]["data"]["reason"] = (
        "득점력 차이를 고려해 예상했으며, 수비진의 공백이 결과를 바꿀 여지도 있습니다."
    )
    assert section_target_report(p)["passed"]


def test_date_in_prose_cannot_replace_the_typed_date_field():
    p = payload()
    r = p["facts"]["injuries"]["data"][0]
    r["cause"]["data"]["occurred_on"] = None
    r["detail"] = "2026-10-10 부상 발생"
    expected = [
        {"player_id": r["player_id"], "occurred_on": "2026-10-10", "source_id": "web-sportsmole"}
    ]
    report = section_target_report(p, expected_incidents=expected)
    assert not report["passed"]
    assert report["occurrence_checks"][0]["actual"] is None


@pytest.mark.parametrize("section", ["analysis", "facts", "sources", "external"])
def test_any_response_field_mutation_is_detected(section):
    raw = payload()
    stored = deepcopy(raw)
    stored[section] = None
    with pytest.raises(ValueError, match="llm_json_changed"):
        assert_content_preserved(raw, stored)


def test_missing_forecast_outlet_is_detected():
    p = payload()
    p["external"]["predictions"]["data"].pop()
    assert not section_target_report(p)["sections"]["external_forecasts"]["passed"]


def test_form_arithmetic_uses_structured_values():
    p = payload()
    assert form_metrics(p)[str(p["fixture"]["home"]["external_id"])]["at_most_one_goal_games"] == 5
