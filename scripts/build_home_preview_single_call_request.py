"""Build one-call preview experiment input from DB only; never call providers or publish."""

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import League, LeagueTranslation, Team
from app.models.home_preview import HomePreviewPublication, HomePreviewSnapshot, HomePreviewVersion
from app.schemas.home_preview import clock
from app.services.home_preview import build_db_snapshot, fixture_by_external, localize_injury_names
from app.services.home_preview_injuries import enrich_importance
from app.services.home_preview_players import enrich_player_spotlights
from app.services.home_preview_policy import utcnow
from app.services.home_preview_single_call import order_for_schema, payload_vertex_schema
from app.services.home_preview_targets import form_metrics

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "docs/features/home-preview-single-call"


def build_input(session, fixture_id, *, now):
    fixture = fixture_by_external(session, fixture_id)
    payload = build_db_snapshot(session, fixture, now=now)
    publication = session.get(HomePreviewPublication, fixture.id)
    version = (
        session.get(HomePreviewVersion, publication.version_id)
        if publication and publication.version_id
        else None
    )
    saved = {"origin": "db_stored_api_collection", "version_id": version.id if version else None}
    # Reuse only collected API facts. Never feed previous LLM prose or web conclusions back in.
    if version:
        old = version.payload
        evidence = session.get(HomePreviewSnapshot, version.snapshot_id)
        if evidence and evidence.payload.get("mode") in {"local_replay", "local_single_call"}:
            # Re-read the original collected API input, not newly generated injury prose.
            old = evidence.payload["input"]["output_template"]
        if old["fixture"] != payload["fixture"]:
            raise ValueError("saved_fixture_identity_mismatch")
        api_sources = [deepcopy(s) for s in old["sources"] if s["kind"] == "api"]
        api_ids = {s["id"] for s in api_sources}
        if any(clock(s["retrieved_at"]) > now for s in api_sources):
            raise ValueError("future_saved_collection")
        injuries = deepcopy(old["facts"]["injuries"])
        if injuries["source_ids"] and set(injuries["source_ids"]) <= api_ids:
            injuries["data"] = [
                r for r in injuries["data"] or [] if set(r["source_ids"]) <= api_ids
            ]
            for row in injuries["data"]:
                row.pop("cause", None)
                row.pop("importance_evidence", None)
            payload["facts"]["injuries"] = injuries
        saved["odds"] = deepcopy(old["external"]["odds"])
        if not set(saved["odds"]["source_ids"]) <= api_ids:
            raise ValueError("non_api_saved_odds")
        predictions = deepcopy(old["external"]["predictions"])
        predictions["data"] = [r for r in predictions["data"] or [] if r["source_id"] in api_ids]
        predictions["source_ids"] = [r["source_id"] for r in predictions["data"]]
        predictions.pop("coverage", None)
        saved["api_algorithm_predictions"] = predictions
        payload["sources"].extend(api_sources)
    enrich_importance(session, payload, now=now)
    enrich_player_spotlights(session, payload, now=now)
    localize_injury_names(session, payload)
    league = session.get(League, fixture.league_id)
    league_tr = session.get(LeagueTranslation, fixture.league_id)
    identity = deepcopy(payload["fixture"])
    identity.update(
        competition_name=league_tr.name_ko if league_tr and league_tr.name_ko else league.name,
        competition_name_en=league.name,
        season_year=fixture.season_year,
    )
    for side, pk in (("home", fixture.home_team_id), ("away", fixture.away_team_id)):
        identity[side]["canonical_name"] = session.get(Team, pk).name
    # Player images are rendered by the server; they provide no analysis evidence.
    facts = deepcopy(payload["facts"])
    for block in ("injuries", "player_spotlights"):
        for row in (facts.get(block) or {}).get("data") or []:
            row.pop("photo_url", None)
    template = deepcopy(payload)
    template["external"]["odds"] = deepcopy(saved.get("odds", template["external"]["odds"]))
    template["external"]["predictions"] = deepcopy(
        saved.get("api_algorithm_predictions", template["external"]["predictions"])
    )
    template = order_for_schema(template, payload_vertex_schema())
    return {
        "output_template": template,
        "verified_form_metrics": form_metrics(template),
        "incident_fixture_lookup": [
            {
                "team_id": template["fixture"][side]["external_id"],
                "fixture_id": m["fixture_id"],
                "opponent": m["opponent"],
                "kickoff_at": m["kickoff_at"],
                "goals_for": m["goals_for"],
                "goals_against": m["goals_against"],
            }
            for side in ("home", "away")
            for m in (template["facts"][side + "_form"].get("data") or {}).get("matches", [])
        ],
        "task": "맨유–본머스 단일 호출 프리뷰 실험"
        if fixture_id == 1557445
        else "단일 호출 프리뷰 실험",
        "fixture": identity,
        "as_of": now.isoformat(),
        "db_facts": facts,
        "db_sources": payload["sources"],
        "db_saved_external": saved,
        "collection_notes": [
            "입력은 DB에서 읽었으며 외부 API/LLM을 호출하지 않았다.",
            "부상·배당·API 알고리즘 예측은 저장된 API 수집본을 읽었고 이전 LLM 분석·웹 전망은 제외했다.",
            "각 block.as_of/source.retrieved_at이 실제 자료 시각이며 요청 as_of를 자료 갱신 시각으로 쓰지 않는다.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--as-of", help="Explicit local replay clock; actual execution time is audited separately"
    )
    args = parser.parse_args()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        parser.error("TEST_DATABASE_URL is required; no default/production DB is selected")
    engine = create_engine(url)
    now = clock(args.as_of) if args.as_of else utcnow()
    with Session(engine, autoflush=False) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        data = build_input(session, args.fixture_id, now=now)
        assert not session.new and not session.dirty and not session.deleted
    engine.dispose()
    config = Settings(_env_file=None)
    system = (PROMPTS / "system.md").read_text()
    schema = payload_vertex_schema()
    user = (
        "다음 DB 입력과 시스템 지침에 따라 웹 검색·판단·JSON 생성을 이 요청 안에서 완료하세요.\n"
        + json.dumps(data, ensure_ascii=False, indent=2)
    )
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 16384,
            "thinkingConfig": {"thinkingLevel": "LOW"},
            "responseMimeType": "application/json",
            "responseSchema": schema,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, value in (("db-input.json", data), ("request.json", body)):
        (args.output_dir / filename).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        )
    (args.output_dir / "prompt.md").write_text(system + "\n\n---\n\n" + user + "\n")
    report = {
        "fixture_id": args.fixture_id,
        "as_of": now.isoformat(),
        "model": config.home_preview_vertex_model,
        "saved_version": data["db_saved_external"]["version_id"],
        "injury_candidates": len(data["db_facts"]["injuries"]["data"] or []),
        "watch_candidates": len(data["db_facts"]["player_spotlights"]["data"] or []),
        "model_requests": 0,
        "api_requests": 0,
        "db_writes": 0,
        "provider_compatibility": "not_executed",
        "request_bytes": len(json.dumps(body, ensure_ascii=False).encode()),
    }
    (args.output_dir / "manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
