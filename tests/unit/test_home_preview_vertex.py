import json
from datetime import UTC, datetime

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


def test_watchpoint_selection_reason_is_required_in_new_model_response():
    data = snapshot()
    data["sources"] = [{"id": "db-source"}]
    data["analysis"]["player_watchpoints"] = {
        "status": "available",
        "reason": None,
        "as_of": data["as_of"],
        "source_ids": ["db-source"],
        "data": [
            {
                "team_id": 40,
                "player_id": 99,
                "focus": "season_contribution",
                "evidence_ids": ["db-source"],
            }
        ],
    }
    candidate = {
        "finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(data["analysis"])}]},
    }
    with pytest.raises(ValueError, match="missing_player_watchpoint_reason"):
        provider(candidate).analysis(data)
    data["analysis"]["player_watchpoints"]["data"][0]["reason"] = (
        "시즌 공격 기록이 돋보여 이번 경기의 공격 기여를 눈여겨볼 선수입니다."
    )
    candidate["content"]["parts"][0]["text"] = json.dumps(data["analysis"])
    analysis, _ = provider(candidate).analysis(data)
    assert (
        analysis["player_watchpoints"]["data"][0]["reason"]
        == data["analysis"]["player_watchpoints"]["data"][0]["reason"]
    )


@pytest.mark.parametrize("unknown", [None, "item", "parent"])
def test_parent_evidence_index_is_completed_only_from_registered_source_ids(unknown):
    payload = snapshot()
    payload["sources"] = [{"id": "real-db-a"}, {"id": "real-db-b"}]
    analysis = payload["analysis"]
    analysis["summary"] = {
        "status": "available",
        "reason": None,
        "as_of": payload["as_of"],
        "source_ids": ["invented" if unknown == "parent" else "real-db-b"],
        "data": {
            "text": "확인된 기록 기반 관찰",
            "evidence_ids": ["invented" if unknown == "item" else "real-db-a"],
        },
    }
    candidate = {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(analysis)}]}}
    if unknown:
        with pytest.raises(ValueError, match="unknown_analysis_source"):
            provider(candidate).analysis(payload)
    else:
        result, usage = provider(candidate).analysis(payload)
        assert result["summary"]["source_ids"] == ["real-db-b", "real-db-a"]
        assert result["summary"]["data"] == analysis["summary"]["data"]
        assert usage["analysis_source_indexes_completed"] == 1


def test_selected_injury_search_uses_individual_surname_official_domain_and_korean_fallback():
    adapter = VertexPreviewProvider(SETTINGS)
    captured = {}

    def request(body):
        captured.update(body)
        return json.dumps({"candidates": []}), {}, {}

    adapter.request = request
    target = {
        "team_id": 40,
        "player_id": 1096,
        "player_name": "D. Szoboszlai",
        "availability": "out",
        "detail": "Muscle Injury",
        "importance_evidence": {"recognition_name": "D. Szoboszlai"},
    }
    adapter.discover_absence_causes(
        snapshot(),
        targets=[target],
        now=datetime(2026, 10, 25, tzinfo=UTC),
        aliases={40: "Liverpool"},
        names_ko={1096: "도미니크 소보슬라이"},
    )
    prompt = json.loads(captured["contents"][0]["parts"][0]["text"])
    assert prompt["preferred_queries"] == ['"Szoboszlai" injury site:liverpoolfc.com']
    assert "도미니크 소보슬라이" in prompt["fallback_queries"][0]
    assert "verbatim" in captured["systemInstruction"]["parts"][0]["text"]
