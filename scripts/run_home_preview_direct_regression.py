"""Local replay: unmodified model JSON -> commit -> fresh readback. Stop at 3 successes."""

import argparse
import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.home_preview import HomePreviewPublication, HomePreviewSnapshot, HomePreviewVersion
from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview import fixture_by_external, read_preview
from app.services.home_preview_generation_input import prepare_template
from app.services.home_preview_policy import identity, utcnow
from app.services.home_preview_regression import is_transport_retry
from app.services.home_preview_single_call_storage import publish_existing_preview
from app.services.home_preview_targets import assert_content_preserved, section_target_report
from app.services.home_preview_vertex import VertexPreviewProvider
from scripts.build_home_preview_single_call_request import build_input

PROMPT = (
    Path(__file__).resolve().parents[1] / "docs/features/home-preview-single-call/system.md"
).read_text()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--env-file", required=True)
    p.add_argument("--original-pages-file", type=Path, required=True)
    p.add_argument("--expectations-file", type=Path, required=True)
    p.add_argument("--source-excerpts-file", type=Path)
    p.add_argument("--prepare-only", action="store_true")
    args = p.parse_args()
    url = os.environ["TEST_DATABASE_URL"]
    u = make_url(url)
    if (u.host, u.port, u.database) != ("127.0.0.1", 55441, "home_preview_test"):
        raise ValueError("dedicated_local_DB_only")
    folder = args.output_dir
    if (folder / "execution.json").exists():
        raise ValueError("fresh_run_directory_required")
    folder.mkdir(parents=True, exist_ok=True)

    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    engine = create_engine(url)
    asof = "2026-10-25T11:45:00+00:00"
    fixture_id = 1557445
    with Session(engine) as s:
        data = build_input(s, fixture_id, now=clock(asof))
        f = fixture_by_external(s, fixture_id)
        expected_identity = identity(f)
        prior = s.get(HomePreviewPublication, f.id).version_id
    publishers = {
        "sportsmole.co.uk": "Sports Mole",
        "goal.com": "Goal.com",
        "football365.com": "Football365",
        "rotowire.com": "RotoWire",
        "theguardian.com": "The Guardian",
    }
    originals = [
        {
            "id": f"web-original-{i + 1}",
            "publisher": publishers[urlsplit(page["url"]).hostname.removeprefix("www.")],
            "page": page,
        }
        for i, page in enumerate(json.loads(args.original_pages_file.read_text()))
    ]
    template = prepare_template(data, originals)
    data["original_sources"] = [
        {
            "id": r["id"],
            "publisher": r["publisher"],
            "url": r["page"]["url"],
            "publication_values": r["page"]["dates"],
            "text": r["page"]["text"],
        }
        for r in originals
    ]
    if args.source_excerpts_file:
        excerpts = json.loads(args.source_excerpts_file.read_text())
        lookup = {r["source_id"]: r for r in excerpts}
        for source in data["original_sources"]:
            pieces = lookup[source["id"]]["excerpts"]
            if not all(piece in source["text"] for piece in pieces):
                raise ValueError("excerpt_not_in_original")
            source["text"] = "\n\n".join(pieces)
        data["source_excerpt_manifest"] = excerpts
    data["original_source_pages"] = originals
    model_input = {
        k: v
        for k, v in data.items()
        if k
        not in {
            "db_facts",
            "db_sources",
            "original_source_pages",
            "acceptance_expectations",
            "source_excerpt_manifest",
        }
    }
    kinds = {
        kind: [r["id"] for r in template["sources"] if r["kind"] == kind]
        for kind in ("db", "web", "api")
    }
    model_input["source_field_policies"] = {
        "facts.injuries[].cause.source_ids": {
            "allowed_ids": kinds["web"],
            "forbidden": "API 및 DB ID는 이 필드에 넣지 않는다.",
        },
        "analysis.player_watchpoints.data[].evidence_ids": {"allowed_ids": kinds["db"]},
        "analysis.key_absences.data[].evidence_ids": {
            "required": "해당 후보 source_ids(API)와 importance_evidence.source_ids(DB)를 모두 포함"
        },
    }
    model_input["player_reason_inputs"] = []
    for player in template["facts"]["player_spotlights"]["data"] or []:
        recent = player.get("recent_form") or {}
        complete = {
            stat: recent.get(stat)
            for stat, sample in (("goals", "goal_samples"), ("assists", "assist_samples"))
            if recent.get(sample) == recent.get("observed_appearances") and recent.get(sample)
        }
        model_input["player_reason_inputs"].append(
            {
                "team_id": player["team_id"],
                "player_id": player["player_id"],
                "name": player["player_name"],
                "own_team_name": next(
                    template["fixture"][side]["name"]
                    for side in ("home", "away")
                    if template["fixture"][side]["external_id"] == player["team_id"]
                ),
                "opponent_name": next(
                    template["fixture"][side]["name"]
                    for side in ("home", "away")
                    if template["fixture"][side]["external_id"] != player["team_id"]
                ),
                "may_state_recent_goal_total": "goals" in complete,
                "may_state_recent_assist_total": "assists" in complete,
                "season": {
                    k: player[k]
                    for k in ("competition_name", "season_year", "appearances", "goals", "assists")
                },
                "recent_complete_stats_only": complete,
                "recent_observed_appearances": recent.get("observed_appearances"),
                "verified_streaks": {
                    k: player[k] for k in ("scoring_streak", "assist_streak", "involvement_streak")
                },
                "team_form": data["verified_form_metrics"][str(player["team_id"])],
                "source_ids": player["source_ids"],
            }
        )
    model_input["required_storage_json_schema"] = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/spec/schemas/home-preview-payload.schema.json"
        ).read_text()
    )
    generation_contract = model_input["required_storage_json_schema"]
    generation_contract["properties"]["analysis"]["required"] = list(
        generation_contract["properties"]["analysis"]["properties"]
    )
    generation_contract["properties"]["facts"]["required"] = list(
        generation_contract["properties"]["facts"]["properties"]
    )
    for key, block in generation_contract["properties"]["analysis"]["properties"].items():
        block["properties"]["source_ids"]["const"] = template["analysis"][key]["source_ids"]
    spotlight_data = next(
        v
        for v in generation_contract["properties"]["facts"]["properties"]["player_spotlights"][
            "properties"
        ]["data"]["anyOf"]
        if v.get("type") != "null"
    )
    spotlight_data["items"]["required"] = list(spotlight_data["items"]["properties"])
    watch_data = next(
        v
        for v in generation_contract["properties"]["analysis"]["properties"]["player_watchpoints"][
            "properties"
        ]["data"]["anyOf"]
        if v.get("type") != "null"
    )
    watch_data["minItems"] = watch_data["maxItems"] = 2
    model_input = {
        "required_storage_json_schema": model_input.pop("required_storage_json_schema"),
        **model_input,
    }
    safe_players = model_input.pop("player_reason_inputs")
    model_input["player_reason_inputs"] = safe_players
    model_input["final_editorial_checks"] = [
        "이번 프리뷰의 눈여겨볼 선수는 홈대표1명, 원정대표1명으로 총2명이다. 어느 선수를 고르든 own_team_name과opponent_name을 뒤집지 않는다.",
        "player_reason_inputs의 may_state_recent_goal_total=false인 선수는 최근골 합계를 본문에 쓰지 않는다. 원본facts의 불완전한 recent_form.goals는 원본 복사용이며 선정이유에서 전체최근득점으로 해석하지 않는다.",
        "선정이유에는 시즌 기록, 완전한 최근 도움, 실제 연속 기록, 팀폼 중 서로 다른 확인 근거를 연결한다. 문장 장식으로 없는 기록을 추가하지 않는다.",
    ]
    body = {
        "systemInstruction": {"parts": [{"text": PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(model_input, ensure_ascii=False)}]}
        ],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 32768,
            "thinkingConfig": {"thinkingLevel": "MEDIUM"},
            "responseMimeType": "application/json",
        },
    }
    write("db-input.json", data)
    write("request.json", body)
    (folder / "prompt.md").write_text(PROMPT)
    if args.prepare_only:
        print("prepared", flush=True)
        return
    v = dotenv_values(args.env_file)
    settings = Settings(
        _env_file=None,
        google_cloud_project=v.get("GOOGLE_CLOUD_PROJECT"),
        google_application_credentials_json=v.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"),
        home_preview_cause_timeout_seconds=300,
    )
    provider = VertexPreviewProvider(settings)
    provider.stage = "causes_direct_storage"
    expected = json.loads(args.expectations_file.read_text())["incidents"]
    state = {
        "state": "running",
        "consecutive_successes": 0,
        "required_consecutive_successes": 3,
        "attempts": [],
        "model": settings.home_preview_vertex_model,
        "previous_version_id": prior,
        "replay_as_of": asof,
    }
    write("execution.json", state)
    feedback_history = []
    n = 0
    while state["consecutive_successes"] < 3:
        n += 1
        started = utcnow().isoformat()
        saved_ids = {}
        obj = None
        state["pending_attempt"] = {"attempt": n, "actual_started_at": started}
        write("execution.json", state)
        print(
            json.dumps(
                {
                    "event": "request_started",
                    "attempt": n,
                    "consecutive": state["consecutive_successes"],
                }
            ),
            flush=True,
        )
        write(f"request-{n}.json", body)
        try:
            raw, grounding, usage = provider.request(body)
            (folder / f"response-{n}.txt").write_text(raw)
            obj = json.loads(raw)
            write(f"response-{n}.json", obj)
            write(f"usage-{n}.json", usage)
            PreviewPayload.model_validate(obj)
            with Session(engine) as s:
                result = publish_existing_preview(
                    s,
                    obj,
                    input_data=data,
                    raw_response=obj,
                    raw_text=raw,
                    resolution={"mode": "none_direct_json"},
                    grounding=grounding,
                    actual_started_at=started,
                    actual_finished_at=utcnow().isoformat(),
                    expected_version_id=prior,
                    expected_identity=expected_identity,
                    replay_as_of=asof,
                )
                s.commit()
                prior = result["version_id"]
                saved_ids = {"version_id": prior, "snapshot_id": result["snapshot_id"]}
            # Test the committed input using a fresh DB session, not an ORM identity-map value.
            with Session(engine) as s:
                stored = s.get(HomePreviewVersion, prior).payload
                response = read_preview(s, fixture_id)
                assert_content_preserved(obj, stored)
                assert_content_preserved(obj, response["preview"])
            write(f"db-readback-{n}.json", stored)
            write(f"api-readback-{n}.json", response)
            targets = section_target_report(stored, expected_incidents=expected)
            immutable = {
                k: stored[k] == template[k]
                for k in (
                    "fixture",
                    "sources",
                    "as_of",
                    "generated_at",
                    "schema_version",
                    "is_mock",
                    "search_suggestions",
                )
            }
            immutable.update(
                {
                    key: stored["facts"][key] == template["facts"][key]
                    for key in ("home_form", "away_form", "player_spotlights")
                }
            )
            immutable["odds"] = stored["external"]["odds"] == template["external"]["odds"]
            from copy import deepcopy

            actual_injuries = deepcopy(stored["facts"]["injuries"])
            original_injuries = deepcopy(template["facts"]["injuries"])
            for block in (actual_injuries, original_injuries):
                for row in block.get("data") or []:
                    row.pop("cause", None)
            immutable["injury_base"] = actual_injuries == original_injuries
            targets["immutable_input_checks"] = immutable
            targets["passed"] = targets["passed"] and all(immutable.values())
            write(f"targets-{n}.json", targets)
            if not targets["passed"]:
                exc = ValueError("post_commit_section_targets_failed")
                exc.target_report = targets
                raise exc
            # The assistant reviews natural-language meaning against the supplied originals.
            review_file = folder / f"review-{n}.json"
            print(
                json.dumps(
                    {
                        "event": "awaiting_source_review",
                        "attempt": n,
                        "version_id": prior,
                        "review_file": str(review_file),
                    }
                ),
                flush=True,
            )
            while not review_file.exists():
                time.sleep(5)
            review = json.loads(review_file.read_text())
            if not review.get("passed"):
                exc = ValueError(
                    "source_review_failed:"
                    + json.dumps(review.get("findings", []), ensure_ascii=False)
                )
                exc.target_report = {**targets, "passed": False, "source_review": review}
                raise exc
            targets["source_review"] = review
            write(f"targets-{n}.json", targets)
            with Session(engine) as audit_session:
                snapshot = audit_session.get(
                    HomePreviewSnapshot, result["snapshot_id"], with_for_update=True
                )
                audit = dict(snapshot.payload)
                audit["targets"] = targets
                audit["verified_at"] = utcnow().isoformat()
                snapshot.payload = audit
                audit_session.commit()
            state["consecutive_successes"] += 1
            item = {
                "attempt": n,
                "state": "passed",
                "version_id": prior,
                "snapshot_id": result["snapshot_id"],
                "raw_equals_committed_db": True,
                "raw_equals_api": True,
                "usage": usage,
                "consecutive_successes": state["consecutive_successes"],
            }
            # Independent requests use the same inputs/prompt, without recycling a previous response.
            print(
                json.dumps(
                    {
                        "event": "stored_result",
                        "attempt": n,
                        "version_id": prior,
                        "ai": stored["analysis"]["ai_prediction"],
                        "selected_absences": stored["analysis"]["key_absences"],
                        "forecasts": stored["external"]["predictions"],
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - audit each attempt and reset the streak
            retry_transport = isinstance(exc, httpx.RequestError) or (
                isinstance(exc, httpx.HTTPStatusError)
                and is_transport_retry({"http_status": exc.response.status_code})
            )
            if not retry_transport:
                state["consecutive_successes"] = 0
            item = {
                "attempt": n,
                "state": "transport_retry" if retry_transport else "failed",
                "type": type(exc).__name__,
                "error": str(exc)[:4000],
            }
            item.update(saved_ids)
            if isinstance(exc, httpx.HTTPStatusError):
                item["http_status"] = exc.response.status_code
                item["provider_error"] = exc.response.text[:4000]
            if hasattr(exc, "preview_finish_reason"):
                item["finish_reason"] = exc.preview_finish_reason
                item["usage"] = exc.preview_usage
                if exc.preview_finish_reason == "MAX_TOKENS":
                    body["generationConfig"]["maxOutputTokens"] = min(
                        65536, body["generationConfig"]["maxOutputTokens"] * 2
                    )
            if hasattr(exc, "preview_partial_text"):
                (folder / f"incomplete-{n}.txt").write_text(exc.preview_partial_text)
            if not isinstance(exc, httpx.HTTPError):
                failure = {"error": str(exc)}
                if isinstance(obj, dict):
                    ref_errors = []
                    for key, block in (obj.get("analysis") or {}).items():
                        data_value = block.get("data")
                        rows = (
                            data_value
                            if isinstance(data_value, list)
                            else [data_value]
                            if isinstance(data_value, dict)
                            else []
                        )
                        for row in rows:
                            missing = set(row.get("evidence_ids", [])) - set(
                                block.get("source_ids", [])
                            )
                            if missing:
                                ref_errors.append(
                                    {
                                        "field": f"analysis.{key}.source_ids",
                                        "missing_child_evidence_ids": sorted(missing),
                                        "action": "템플릿의 상위 source_ids를 그대로 반환하고 하위 ID를 삭제해 회피하지 않는다.",
                                    }
                                )
                    failure["reference_errors"] = ref_errors
                    from jsonschema import Draft202012Validator

                    failure["schema_errors"] = [
                        {"path": list(e.absolute_path), "error": e.message}
                        for e in Draft202012Validator(
                            model_input["required_storage_json_schema"]
                        ).iter_errors(obj)
                    ][:20]
                body["systemInstruction"]["parts"][0]["text"] = (
                    PROMPT
                    + "\n직전 실패를 다음 응답에서 수정. 값을 서버에서 보정하지 않는다: "
                    + json.dumps(failure, ensure_ascii=False)
                )
            if hasattr(exc, "target_report"):
                write(f"targets-{n}.json", exc.target_report)
                # Prompt correction, not output mutation. Successful streak restarts at zero.
                body["systemInstruction"]["parts"][0]["text"] = (
                    PROMPT
                    + "\n직전 저장 후 검사에서 미달한 필드를 다음 응답에서 수정: "
                    + json.dumps(exc.target_report, ensure_ascii=False)
                )
            if not retry_transport:
                feedback_history.append(
                    {
                        "attempt": n,
                        "error": str(exc),
                        "targets": getattr(exc, "target_report", None),
                    }
                )
                body["systemInstruction"]["parts"][0]["text"] = (
                    PROMPT
                    + "\n누적 수정 지시(이전 교정을 유지하면서 모두 해결): "
                    + json.dumps(feedback_history, ensure_ascii=False)
                )
            write("request.json", body)
        item["actual_started_at"] = started
        item["actual_finished_at"] = utcnow().isoformat()
        state.pop("pending_attempt", None)
        state["attempts"].append(item)
        write("execution.json", state)
        print(json.dumps(item, ensure_ascii=False), flush=True)
        if item["state"] != "passed":
            recent_throttles = sum(a.get("http_status") == 429 for a in state["attempts"][-3:])
            delay = (
                min(240, 60 * (2 ** max(0, recent_throttles - 1)))
                if item.get("http_status") == 429
                else 10
            )
            for remaining in range(delay, 0, -10):
                time.sleep(min(10, remaining))
    state["state"] = "three_consecutive_successes"
    write("execution.json", state)
    print(json.dumps(state, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
