"""Worker-only grounded full-payload generation; never reconstruct returned prose fields."""

import json
from copy import deepcopy
from pathlib import Path

import httpx

from app.schemas.home_preview import PreviewPayload
from app.services.home_preview_generation_input import prepare_template
from app.services.home_preview_targets import form_metrics
from app.services.home_preview_web import ALLOWED_HOSTS, fetch_page

PROMPT = Path(__file__).resolve().parents[2] / "docs/features/home-preview-production-prompt.md"
SCHEMA = Path(__file__).resolve().parents[2] / "docs/spec/schemas/home-preview-payload.schema.json"


def generation_input(payload, *, now):
    data = {"output_template": deepcopy(payload), "as_of": now.isoformat()}
    template = prepare_template(data, [])
    data["storage_schema"] = json.loads(SCHEMA.read_text())
    data["verified_form_metrics"] = form_metrics(template)
    data["incident_fixture_lookup"] = [
        row
        for side in ("home", "away")
        for row in (template["facts"][side + "_form"].get("data") or {}).get("matches", [])
    ]
    data["player_reason_inputs"] = []
    for row in (template["facts"].get("player_spotlights") or {}).get("data") or []:
        recent = row.get("recent_form") or {}
        complete = {
            stat: recent[stat]
            for stat, sample in (("goals", "goal_samples"), ("assists", "assist_samples"))
            if recent.get(sample) and recent[sample] == recent.get("observed_appearances")
        }
        data["player_reason_inputs"].append(
            {
                "team_id": row["team_id"],
                "player_id": row["player_id"],
                "name": row["player_name"],
                "own_team_name": next(
                    template["fixture"][s]["name"]
                    for s in ("home", "away")
                    if template["fixture"][s]["external_id"] == row["team_id"]
                ),
                "opponent_name": next(
                    template["fixture"][s]["name"]
                    for s in ("home", "away")
                    if template["fixture"][s]["external_id"] != row["team_id"]
                ),
                "season": {
                    key: row[key]
                    for key in (
                        "competition_name",
                        "season_year",
                        "appearances",
                        "goals",
                        "assists",
                    )
                },
                "complete_recent_stats_only": complete,
                "recent_observed_appearances": recent.get("observed_appearances"),
                "verified_streaks": {
                    key: row[key]
                    for key in ("scoring_streak", "assist_streak", "involvement_streak")
                },
            }
        )
    return data


def validate_direct_result(template, result):
    PreviewPayload.model_validate(result)
    for key in ("fixture", "as_of", "generated_at", "schema_version", "is_mock"):
        if result[key] != template[key]:
            raise ValueError("direct_metadata_changed:" + key)
    for key in ("home_form", "away_form", "player_spotlights"):
        if result["facts"].get(key) != template["facts"].get(key):
            raise ValueError("direct_DB_facts_changed:" + key)
    if result["external"]["odds"] != template["external"]["odds"]:
        raise ValueError("direct_odds_changed")
    if result["sources"][: len(template["sources"])] != template["sources"]:
        raise ValueError("direct_sources_changed")
    left = deepcopy(template["facts"]["injuries"])
    right = deepcopy(result["facts"]["injuries"])
    selected = {
        (row["team_id"], row["player_id"])
        for row in (result["analysis"].get("key_absences") or {}).get("data") or []
    }
    for block in (left, right):
        for row in block.get("data") or []:
            if (row["team_id"], row.get("player_id")) in selected:
                row.pop("cause", None)
    if left != right:
        raise ValueError("direct_injury_base_or_unselected_cause_changed")
    if any(
        (template["facts"][side + "_form"].get("data") or {}).get("matches")
        for side in ("home", "away")
    ):
        for key in ("summary", "key_points", "ai_prediction"):
            if not result["analysis"][key].get("data"):
                raise ValueError("direct_missing_analysis:" + key)
    predictions = result["external"]["predictions"]
    if not predictions.get("coverage"):
        raise ValueError("direct_missing_forecast_coverage")
    if len(predictions.get("data") or []) > 3:
        raise ValueError("direct_forecast_limit_three")
    for row in template["external"]["predictions"].get("data") or []:
        if row not in (predictions.get("data") or []):
            raise ValueError("direct_API_prediction_changed")


class ProductionPreviewGenerator:
    def __init__(self, vertex, *, clock, aliases=None, fetcher=fetch_page):
        self.vertex, self.clock, self.aliases, self.fetcher = vertex, clock, aliases or {}, fetcher

    def verify_sources(self, result, grounding):
        web = [row for row in result["sources"] if row["kind"] == "web"]
        if not web:
            return []
        chunks = (grounding.get("groundingChunks") or [])[:12]
        pages = {}
        verified = set()
        for chunk in chunks:
            url = (chunk.get("web") or {}).get("uri")
            if not url:
                continue
            try:
                page = self.fetcher(url)
            except (ValueError, OSError, httpx.HTTPError):
                continue
            pages[url] = page
            verified.add(page["url"])
        audit = []
        for source in web:
            page = pages.get(source["url"]) or self.fetcher(source["url"])
            if page["url"] not in verified:
                raise ValueError("direct_source_not_in_grounding:" + source["id"])
            audit.append(
                {"source_id": source["id"], "requested_url": source["url"], "original_page": page}
            )
        return audit

    def __call__(self, payload):
        data = generation_input(payload, now=self.clock())
        data["allowed_source_hosts"] = sorted(ALLOWED_HOSTS)
        data["team_search_names"] = self.aliases
        body = {
            "systemInstruction": {"parts": [{"text": PROMPT.read_text()}]},
            "contents": [
                {"role": "user", "parts": [{"text": json.dumps(data, ensure_ascii=False)}]}
            ],
            "tools": [{"googleSearch": {}}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": 32768,
                "thinkingConfig": {"thinkingLevel": "MEDIUM"},
                "responseMimeType": "application/json",
            },
        }
        self.vertex.stage = "causes_full_preview"
        attempts = []
        for attempt in range(3):
            raw, grounding, usage = self.vertex.request(body)
            audit = {"raw_text": raw, "grounding": grounding, "usage": usage}
            attempts.append(audit)
            try:
                result = json.loads(raw)
                validate_direct_result(data["output_template"], result)
                pages = self.verify_sources(result, grounding)
            except ValueError as exc:
                audit["error"] = str(exc)[:500]
                if attempt == 2:
                    raise
                body["systemInstruction"]["parts"][0]["text"] = (
                    PROMPT.read_text()
                    + "\n직전 검증 오류를 다음 JSON 응답에서 수정한다. 서버가 값을 보정하지 않는다: "
                    + str(exc)[:500]
                )
                continue
            return result, {
                "_direct_generation": {
                    "input": data,
                    "raw_llm_response": result,
                    "raw_llm_text": raw,
                    "grounding": grounding,
                    "original_pages": pages,
                    "attempts": attempts,
                },
                "full_preview_tokens": usage,
                "generation_mode": "direct_json",
            }
        raise ValueError("direct_generation_failed")
