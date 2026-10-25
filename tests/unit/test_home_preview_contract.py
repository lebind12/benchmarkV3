import json
from pathlib import Path

import pytest

from app.schemas.home_preview import PreviewPayload, PreviewResponse

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "frontend/src/mocks/home-preview"


def test_shared_response_examples():
    for item in json.loads((EXAMPLES / "responses.json").read_text()).values():
        assert PreviewResponse.model_validate(item).model_dump(mode="json") == item


def test_shared_payload_examples_and_rejections():
    item = json.loads((EXAMPLES / "previews.json").read_text())["90001"]
    PreviewPayload.model_validate(item)
    item["facts"]["injuries"]["reason"] = "private provider diagnostic"
    with pytest.raises(ValueError):
        PreviewPayload.model_validate(item)


def test_cross_fixture_and_null_clock_rejected():
    item = json.loads((EXAMPLES / "responses.json").read_text())["ready"]
    item["fixture_id"] = 2
    with pytest.raises(ValueError):
        PreviewResponse.model_validate(item)
    item = json.loads((EXAMPLES / "responses.json").read_text())["pending"]
    item["publication"]["generated_at"] = "2026-10-25T00:00:00Z"
    with pytest.raises(ValueError):
        PreviewResponse.model_validate(item)
