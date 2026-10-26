"""Opt-in local-only, grounded one-request generation and existing-contract publication."""

import argparse
import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.home_preview import HomePreviewPublication, HomePreviewVersion
from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview import fixture_by_external, read_preview
from app.services.home_preview_policy import identity, utcnow
from app.services.home_preview_single_call import payload_vertex_schema, resolve_existing_response
from app.services.home_preview_single_call_storage import publish_existing_preview
from app.services.home_preview_targets import (
    assert_content_preserved,
    require_section_targets,
    section_target_report,
)
from app.services.home_preview_vertex import VertexPreviewProvider
from app.services.home_preview_web import fetch_page
from scripts.build_home_preview_single_call_request import PROMPTS, build_input


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument(
        "--as-of", help="Explicit historical local replay clock, actual times audited separately"
    )
    parser.add_argument("--publish", action="store_true")
    parser.add_argument(
        "--expectations-file",
        type=Path,
        help="Independently checked source facts for this local regression case",
    )
    parser.add_argument(
        "--repair-from",
        type=Path,
        help="Previously rejected candidate, treated only as an untrusted draft",
    )
    parser.add_argument(
        "--original-pages-file",
        type=Path,
        help="Caller-fetched original articles, never model-authored URLs",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write request only, without provider calls or DB writes",
    )
    args = parser.parse_args()
    url = os.environ.get("TEST_DATABASE_URL", "")
    target = make_url(url)
    if target.host != "127.0.0.1" or target.port != 55441 or target.database != "home_preview_test":
        parser.error("Only the dedicated local main preview test DB at 127.0.0.1:55441 is allowed")
    folder = args.output_dir
    folder.mkdir(parents=True, exist_ok=True)
    actual_start = utcnow()
    reference_time = clock(args.as_of) if args.as_of else actual_start
    engine = create_engine(url)
    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        data = build_input(session, args.fixture_id, now=reference_time)
        fixture = fixture_by_external(session, args.fixture_id)
        if reference_time >= fixture.kickoff_at:
            parser.error(
                "Generation requires a pre-kickoff clock; use --as-of only for an authorized local replay"
            )
        expected_identity = identity(fixture)
        prior_id = session.get(HomePreviewPublication, fixture.id).version_id
    original_sources = []
    if args.original_pages_file:
        from urllib.parse import urlsplit

        publisher_names = {
            "sportsmole.co.uk": "Sports Mole",
            "goal.com": "Goal.com",
            "football365.com": "Football365",
            "si.com": "Sports Illustrated",
            "rotowire.com": "RotoWire",
            "theguardian.com": "The Guardian",
        }
        for i, page in enumerate(json.loads(args.original_pages_file.read_text())):
            host = (urlsplit(page["url"]).hostname or "").removeprefix("www.")
            if host not in publisher_names:
                raise ValueError("unapproved_original_input_host")
            original_sources.append(
                {"id": f"web-original-{i + 1}", "publisher": publisher_names[host], "page": page}
            )
        data["original_sources"] = [
            {
                "id": row["id"],
                "publisher": row["publisher"],
                "title": row["page"]["title"],
                "url": row["page"]["url"],
                "publication_values": row["page"]["dates"],
                "text": "\n".join(
                    p["text"]
                    for p in row["page"].get("passages", [])
                    if 30 <= len(p["text"]) < 2000
                    and re.search(
                        r"United|Bournemouth|Mainoo|Shaw|Scott|Toth|Dorgu|Croatia|Tottenham|prediction|We say",
                        p["text"],
                        re.IGNORECASE,
                    )
                )
                or row["page"]["text"],
            }
            for row in original_sources
        ]
    for row in original_sources:
        data["output_template"]["sources"].append(
            {
                "id": row["id"],
                "fixture_id": args.fixture_id,
                "kind": "web",
                "title": row["publisher"] + " | " + row["page"]["title"],
                "url": None,
                "published_at": None,
                "retrieved_at": data["as_of"],
            }
        )
    expected_incidents = (
        json.loads(args.expectations_file.read_text()).get("incidents", [])
        if args.expectations_file
        else []
    )
    data["acceptance_expectations"] = {"incidents": expected_incidents}
    data["original_source_pages"] = original_sources
    system = (PROMPTS / "system.md").read_text()
    # DB facts/sources already live inside the exact existing output template; avoid duplicate input.
    model_input = {
        k: v
        for k, v in data.items()
        if k not in {"db_facts", "db_sources", "original_source_pages", "acceptance_expectations"}
    }
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [
            {"role": "user", "parts": [{"text": json.dumps(model_input, ensure_ascii=False)}]}
        ],
        "tools": [{"googleSearch": {}}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 24576,
            "thinkingConfig": {"thinkingLevel": "LOW"},
            "responseMimeType": "application/json",
            "responseSchema": payload_vertex_schema(),
        },
    }

    if args.repair_from:
        draft = json.loads(args.repair_from.read_text())
        draft_targets = section_target_report(
            draft,
            source_urls={row["id"]: row["page"]["url"] for row in original_sources},
            expected_incidents=expected_incidents,
        )
        feedback = (
            "다음은 이전 검증에서 거부된 초안이다. 초안 자체를 사실 근거로 사용하지 말고 원래 DB와 원문을 기준으로 목표 미달 부분을 고쳐 전체 기존 JSON을 반환한다. 출처 목록은 새 output_template.sources의 모든 기존 ID를 포함한다. source_ids를 없애거나 정보를 삭제해서 오류만 피하지 않는다. 필요한 선수 reason은3문장 이상, AI에는 실제 선정 결장 변수를 포함한다. 무실점 표현은 허용한다.\n검사 결과: "
            + json.dumps(draft_targets, ensure_ascii=False)
        )
        selected_ids = {
            p["player_id"] for p in (draft["analysis"].get("key_absences") or {}).get("data") or []
        }
        draft_fields = {
            "analysis": draft["analysis"],
            "selected_injuries": [
                r
                for r in draft["facts"]["injuries"]["data"] or []
                if r.get("player_id") in selected_ids
            ],
            "external_predictions": draft["external"]["predictions"],
        }
        body["contents"].append(
            {
                "role": "user",
                "parts": [
                    {
                        "text": "검증에서 거부된 초안 필드(사실 근거가 아님). DB 복사 필드는 원래 output_template만 사용한다. 최종 답은 전체 기존 JSON이다.\n"
                        + json.dumps(draft_fields, ensure_ascii=False)
                    }
                ],
            }
        )
        body["contents"].append({"role": "user", "parts": [{"text": feedback}]})

    def write(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")

    write("db-input.json", data)
    write("request.json", body)
    (folder / "prompt.md").write_text(
        system + "\n\n" + json.dumps(model_input, ensure_ascii=False, indent=2)
    )
    if args.prepare_only:
        print(
            json.dumps(
                {
                    "state": "prepared",
                    "model_requests": 0,
                    "db_writes": 0,
                    "fixture_id": args.fixture_id,
                    "as_of": args.as_of,
                }
            ),
            flush=True,
        )
        return
    values = dotenv_values(args.env_file)
    settings = Settings(
        _env_file=None,
        google_cloud_project=values.get("GOOGLE_CLOUD_PROJECT"),
        google_application_credentials_json=values.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"),
        home_preview_cause_timeout_seconds=300,
    )
    provider = VertexPreviewProvider(settings)
    provider.stage = "causes_single_existing"
    report = {
        "state": "running",
        "fixture_id": args.fixture_id,
        "model": settings.home_preview_vertex_model,
        "actual_started_at": actual_start.isoformat(),
        "replay_as_of": args.as_of,
        "previous_version_id": prior_id,
        "model_requests": 0,
        "api_requests": 0,
        "db_writes": 0,
        "attempts": [],
    }
    write("execution.json", report)
    payload = None
    for attempt in range(1, 4):
        attempt_start = utcnow()
        report["model_requests"] += 1
        print(
            json.dumps(
                {
                    "event": "request_started",
                    "attempt": attempt,
                    "actual_time": attempt_start.isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        try:
            raw, grounding, usage = provider.request(body)
            (folder / f"response-{attempt}.txt").write_text(raw)
            write(f"grounding-{attempt}.json", grounding)
            write(f"usage-{attempt}.json", usage)
            source_urls = {row["id"]: row["page"]["url"] for row in original_sources}
            raw_targets = section_target_report(
                json.loads(raw), source_urls=source_urls, expected_incidents=expected_incidents
            )
            write(f"raw-targets-{attempt}.json", raw_targets)
            (folder / "response.txt").write_text(raw)
            write("response.json", json.loads(raw))
            write("grounding.json", grounding)
            # Report actual call result immediately; publication remains behind contract checks.
            print(
                json.dumps(
                    {
                        "event": "response_received",
                        "attempt": attempt,
                        "ai_prediction": json.loads(raw).get("analysis", {}).get("ai_prediction"),
                        "usage": usage,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            hosts = set()
            for chunk in grounding.get("groundingChunks") or []:
                web = chunk.get("web") or {}
                domain = web.get("domain") or web.get("title", "")
                if re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}", domain):
                    hosts.add(domain.lower())

            def fetch(url, allowed_hosts=frozenset(hosts)):
                return fetch_page(url, allowed_hosts=allowed_hosts)

            finished = utcnow()
            model_clock = reference_time + (finished - actual_start) if args.as_of else finished
            payload, resolution, pages = resolve_existing_response(
                raw,
                grounding,
                data["output_template"],
                fetcher=fetch,
                now=model_clock,
                original_sources=original_sources,
                expected_incidents=expected_incidents,
            )
            write("source-resolution.json", resolution)
            write("original-pages.json", pages)
            write("payload.json", payload)
            report["attempts"].append({"attempt": attempt, "state": "validated", "usage": usage})
            report.update(state="validated", search_queries=grounding.get("webSearchQueries", []))
            break
        except Exception as exc:
            item = {"attempt": attempt, "state": "failed", "error_type": type(exc).__name__}
            if hasattr(exc, "preview_finish_reason"):
                item["finish_reason"] = exc.preview_finish_reason
                item["usage"] = exc.preview_usage
                (folder / f"incomplete-response-{attempt}.txt").write_text(exc.preview_partial_text)
                write(f"incomplete-grounding-{attempt}.json", exc.preview_grounding)
            if isinstance(exc, httpx.HTTPStatusError):
                item["http_status"] = exc.response.status_code
                try:
                    item["message"] = re.sub(
                        r"https?://\S+",
                        "[URL]",
                        exc.response.json().get("error", {}).get("message", ""),
                    )[:2500]
                    item["provider_details"] = (
                        exc.response.json().get("error", {}).get("details", [])
                    )
                except ValueError:
                    pass
            else:
                item["message"] = str(exc)[:2500]
            if hasattr(exc, "preview_resolution"):
                write(f"failed-source-resolution-{attempt}.json", exc.preview_resolution)
                write(f"failed-original-pages-{attempt}.json", exc.preview_pages)
            if hasattr(exc, "preview_candidate"):
                write(f"failed-candidate-{attempt}.json", exc.preview_candidate)
            if hasattr(exc, "target_report"):
                write(f"failed-targets-{attempt}.json", exc.target_report)
                item["targets"] = exc.target_report
            report["attempts"].append(item)
            write("execution.json", report)
            print(json.dumps(item, ensure_ascii=False), flush=True)
            if attempt == 3 or (
                isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 400
            ):
                report.update(state="failed", actual_finished_at=utcnow().isoformat())
                write("execution.json", report)
                raise
            if getattr(exc, "preview_finish_reason", None) == "MAX_TOKENS":
                body["generationConfig"]["maxOutputTokens"] = min(
                    65536, body["generationConfig"]["maxOutputTokens"] * 2
                )
            if not isinstance(exc, httpx.HTTPError):
                details = json.dumps(
                    getattr(exc, "target_report", locals().get("raw_targets", {})),
                    ensure_ascii=False,
                )
                feedback = (
                    "직전 후보는 검증에서 거부되었습니다. 원래 DB 입력을 유일한 사실 기준으로 유지하고 다음 오류만 바로잡아 기존 전체 JSON을 반환하세요. "
                    + item["message"]
                    + "\n목표 검사: "
                    + details
                )
                body["contents"] = [
                    {
                        "role": "user",
                        "parts": [{"text": json.dumps(model_input, ensure_ascii=False)}],
                    }
                ]
                if "raw" in locals():
                    body["contents"].append({"role": "model", "parts": [{"text": raw}]})
                body["contents"].append({"role": "user", "parts": [{"text": feedback}]})
                write(f"request-retry-{attempt + 1}.json", body)
            delay = 60 * (2 ** (attempt - 1)) if item.get("http_status") == 429 else 30
            while delay > 0:
                print(
                    json.dumps(
                        {
                            "event": "retry_wait",
                            "remaining_seconds": delay,
                            "next_attempt": attempt + 1,
                        }
                    ),
                    flush=True,
                )
                time.sleep(min(30, delay))
                delay -= 30
    if payload is not None and args.publish:
        PreviewPayload.model_validate(payload)
        require_section_targets(payload, expected_incidents=expected_incidents)
        assert_content_preserved(json.loads(raw), payload)
        with Session(engine) as session:
            previous = session.get(HomePreviewVersion, prior_id)
            write("previous-payload.json", previous.payload)
            result = publish_existing_preview(
                session,
                payload,
                input_data=data,
                raw_response=json.loads(raw),
                raw_text=raw,
                resolution=resolution,
                grounding=grounding,
                actual_started_at=report["actual_started_at"],
                actual_finished_at=utcnow().isoformat(),
                expected_version_id=prior_id,
                expected_identity=expected_identity,
                replay_as_of=args.as_of,
            )
            report.update(
                state="published",
                version_id=result["version_id"],
                snapshot_id=result["snapshot_id"],
                db_writes=3,
            )
            session.commit()
        with Session(engine) as session:
            response = read_preview(session, args.fixture_id)
        write("api-readback.json", response)
    report["actual_finished_at"] = utcnow().isoformat()
    write("execution.json", report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if payload is not None:
        print(
            json.dumps(
                {
                    "ai_prediction": payload["analysis"]["ai_prediction"],
                    "key_absences": payload["analysis"]["key_absences"],
                    "injuries": [
                        {
                            "player_name": r["player_name"],
                            "detail": r["detail"],
                            "cause": r.get("cause"),
                        }
                        for r in payload["facts"]["injuries"]["data"] or []
                    ],
                    "external_predictions": payload["external"]["predictions"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
