import json

import httpx
import pytest

from app.core.config import Settings
from app.services.home_preview_vertex import VertexPreviewProvider
from tests.unit.test_home_preview_api_football import snapshot

SETTINGS = Settings(_env_file=None, google_cloud_project="test-project")


def provider(candidate):
    def reply(request):
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseSchema" in body["generationConfig"]
        assert "tools" not in body
        assert "/gemini-3.5-flash:" in str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [candidate],
                "usageMetadata": {
                    "totalTokenCount": 321,
                    "secretDiagnostic": "must not be preserved",
                },
            },
        )

    return VertexPreviewProvider(SETTINGS, transport=httpx.MockTransport(reply))


def test_strict_structured_output_and_sanitized_usage():
    data = snapshot()
    candidate = {
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(data["analysis"])}]},
    }
    analysis, usage = provider(candidate).analysis(data)
    assert analysis == data["analysis"]
    assert usage == {"analysis_tokens": {"totalTokenCount": 321}}


@pytest.mark.parametrize(
    "candidate",
    [
        {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": "{}"}]}},
        {"finishReason": "SAFETY", "content": {"parts": [{"text": "{}"}]}},
        {"finishReason": "STOP", "content": {"parts": []}},
        {"finishReason": "STOP", "content": {"parts": [{"text": "```json {} ```"}]}},
        {"finishReason": "STOP", "content": {"parts": [{"text": '{"invented":true}'}]}},
    ],
)
def test_incomplete_blocked_empty_markdown_and_extra_fields_rejected(candidate):
    with pytest.raises(ValueError):
        provider(candidate).analysis(snapshot())
