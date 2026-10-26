import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.services.home_preview_single_call import (
    payload_vertex_schema,
    validate_existing_response,
)
from scripts.resolve_home_preview_single_call import json_schema

ROOT = Path(__file__).resolve().parents[2]


def sample():
    value = json.loads((ROOT / "frontend/src/mocks/home-preview/previews.json").read_text())[
        "90001"
    ]
    value["is_mock"] = False
    value["facts"].setdefault(
        "player_spotlights",
        {
            "status": "missing",
            "reason": "not_collected",
            "as_of": None,
            "source_ids": [],
            "data": None,
        },
    )
    for name in ("key_absences", "player_watchpoints"):
        value["analysis"].setdefault(
            name,
            {
                "status": "missing",
                "reason": "not_collected",
                "as_of": None,
                "source_ids": [],
                "data": None,
            },
        )
    return value


def test_response_schema_preserves_existing_top_level_and_prediction_fields():
    schema = payload_vertex_schema()
    assert set(schema["properties"]) == set(
        json.loads((ROOT / "docs/spec/schemas/home-preview-payload.schema.json").read_text())[
            "properties"
        ]
    )
    prediction = schema["properties"]["analysis"]["properties"]["ai_prediction"]["properties"][
        "data"
    ]
    assert set(prediction["required"]) == {
        "home_goals",
        "away_goals",
        "confidence",
        "reason",
        "evidence_ids",
    }
    Draft202012Validator(json_schema(schema)).validate(sample())


def test_existing_payload_is_accepted_without_an_alternate_shape():
    value = sample()
    assert validate_existing_response(deepcopy(value), value) == value


def test_experimental_shape_and_null_score_cannot_pass():
    original = sample()
    value = deepcopy(original)
    value["analysis"]["ai_prediction"]["data"] = {
        "label": "AI 경기 예측",
        "text": "API 전망",
        "predicted_score": None,
        "evidence_ids": [],
    }
    with pytest.raises(ValueError, match="invalid_payload_structure"):
        validate_existing_response(value, original)


@pytest.mark.parametrize("block", ["home_form", "away_form", "player_spotlights"])
def test_model_cannot_rewrite_db_facts(block):
    original = sample()
    value = deepcopy(original)
    value["facts"].pop(block, None)
    with pytest.raises(ValueError):
        validate_existing_response(value, original)


def test_model_cannot_rewrite_odds():
    original = sample()
    value = deepcopy(original)
    value["external"]["odds"]["data"][0]["home"] = 9.99
    with pytest.raises(ValueError, match="changed_odds"):
        validate_existing_response(value, original)


def test_model_cannot_misrepresent_api_outlook_as_own_prediction():
    original = sample()
    value = deepcopy(original)
    value["analysis"]["ai_prediction"]["data"]["reason"] = (
        "API-Football 자체 알고리즘 전망을 그대로 제시합니다."
    )
    with pytest.raises(ValueError, match="copied_api_prediction"):
        validate_existing_response(value, original)


def test_vertex_numeric_constants_are_not_string_enums():
    schema = payload_vertex_schema()

    def visit(node):
        if isinstance(node, dict):
            assert all(isinstance(v, str) for v in node.get("enum", []))
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)

    visit(schema)
    count = schema["properties"]["facts"]["properties"]["home_form"]["properties"]["data"][
        "properties"
    ]["expected_count"]
    assert count["minimum"] == count["maximum"] == 5


def test_required_target_sections_and_template_order_match_provider_schema():
    from app.services.home_preview_single_call import order_for_schema

    schema = payload_vertex_schema()
    assert "player_spotlights" in schema["properties"]["facts"]["required"]
    assert {"key_absences", "player_watchpoints"} <= set(
        schema["properties"]["analysis"]["required"]
    )
    original = sample()
    ordered = order_for_schema(original, schema)
    assert original == ordered
    assert list(ordered) == [k for k in schema["properties"] if k in original]
    assert next(iter(ordered["facts"])) == "player_spotlights"
