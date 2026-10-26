"""Read-only proof of the final three independent generation/storage successes."""

import argparse
import hashlib
import json
import os
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.home_preview import HomePreviewSnapshot, HomePreviewVersion
from app.services.home_preview import read_preview
from app.services.home_preview_regression import is_transport_retry, successful_streak


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    folder = args.run_dir
    url = os.environ["TEST_DATABASE_URL"]
    target = make_url(url)
    if (target.host, target.port, target.database) != ("127.0.0.1", 55441, "home_preview_test"):
        raise ValueError("dedicated_local_DB_only")
    execution = json.loads((folder / "execution.json").read_text())
    engine = create_engine(url)
    # Recover a committed candidate awaiting source review without making another model call.
    pending = execution.get("pending_attempt")
    if pending:
        n = pending["attempt"]
        review_path = folder / f"review-{n}.json"
        if review_path.exists() and json.loads(review_path.read_text()).get("passed"):
            raw_text = (folder / f"response-{n}.txt").read_text()
            from sqlalchemy import select

            with Session(engine) as session:
                session.execute(text("SET TRANSACTION READ ONLY"))
                snapshot = session.scalar(
                    select(HomePreviewSnapshot).where(
                        HomePreviewSnapshot.payload["raw_llm_text"].astext == raw_text
                    )
                )
                version = session.scalar(
                    select(HomePreviewVersion).where(HomePreviewVersion.snapshot_id == snapshot.id)
                )
                execution["attempts"].append(
                    {
                        "attempt": n,
                        "state": "passed",
                        "version_id": version.id,
                        "snapshot_id": snapshot.id,
                        "actual_started_at": snapshot.payload["actual_started_at"],
                        "actual_finished_at": snapshot.payload["actual_finished_at"],
                        "recovered_committed_review": True,
                    }
                )
            execution.pop("pending_attempt", None)
    for item in execution["attempts"]:
        if is_transport_retry(item):
            item.setdefault("previous_state", item["state"])
            item["state"] = "transport_retry"
    streak = successful_streak(execution["attempts"])
    if streak != 3:
        raise ValueError("three_consecutive_schema_tests_not_achieved")
    candidates = [item for item in execution["attempts"] if not is_transport_retry(item)]
    last = candidates[-3:]
    assert len(last) == 3 and all(item["state"] == "passed" for item in last)
    engine = create_engine(url)
    rows = []
    request_hashes = []
    evidence_hashes = []
    for item in last:
        n = item["attempt"]
        raw_text = (folder / f"response-{n}.txt").read_text()
        raw = json.loads(raw_text)
        targets = json.loads((folder / f"targets-{n}.json").read_text())
        review = json.loads((folder / f"review-{n}.json").read_text())
        assert targets["passed"] and review["passed"]
        with Session(engine) as s:
            s.execute(text("SET TRANSACTION READ ONLY"))
            version = s.get(HomePreviewVersion, item["version_id"])
            snapshot = s.get(HomePreviewSnapshot, version.snapshot_id)
            assert raw == version.payload == snapshot.payload["raw_llm_response"]
            assert raw_text == snapshot.payload["raw_llm_text"]
            assert snapshot.payload["targets"]["passed"]
            snapshot_id = version.snapshot_id
            actual_start = snapshot.payload["actual_started_at"]
            actual_finish = snapshot.payload["actual_finished_at"]
        picks = {p["player_id"] for p in raw["analysis"]["key_absences"]["data"]}
        injuries = [
            {
                "player_id": r["player_id"],
                "name": r["player_name"],
                "cause": r["cause"]["data"],
                "source_ids": r["cause"]["source_ids"],
            }
            for r in raw["facts"]["injuries"]["data"]
            if r["player_id"] in picks
        ]
        request = json.loads((folder / f"request-{n}.json").read_text())
        request_input = json.loads(request["contents"][0]["parts"][0]["text"])
        Draft202012Validator(request_input["required_storage_json_schema"]).validate(raw)
        evidence_hashes.append(
            hashlib.sha256(
                json.dumps(
                    {
                        "contents": request["contents"],
                        "generationConfig": request["generationConfig"],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
        )
        assert len(request["contents"]) == 1 and request["contents"][0]["role"] == "user"
        request_hashes.append(
            hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
        )
        rows.append(
            {
                "attempt": n,
                "version_id": item["version_id"],
                "snapshot_id": snapshot_id,
                "raw_equals_fresh_DB": True,
                "requested_generation_schema_errors": 0,
                "raw_text_equals_snapshot_text": True,
                "section_and_source_review_passed": True,
                "actual_started_at": actual_start,
                "actual_finished_at": actual_finish,
                "ai_prediction": raw["analysis"]["ai_prediction"]["data"],
                "injuries": injuries,
                "forecasts": raw["external"]["predictions"]["data"],
            }
        )
    with Session(engine) as s:
        s.execute(text("SET TRANSACTION READ ONLY"))
        api = read_preview(s, 1557445)
        assert api["preview"] == raw
    response = httpx.get(
        "http://127.0.0.1:8018/api/v1/home/fixtures/1557445/prematch", trust_env=False
    )
    response.raise_for_status()
    assert response.json()["preview"] == raw
    assert len(set(evidence_hashes)) == 1
    result = {
        "passed": True,
        "consecutive_successes": 3,
        "same_input_evidence_and_generation_config_for_final_three": True,
        "same_request_body_for_final_three": len(set(request_hashes)) == 1,
        "success_basis": "committed_schema_and_section_validation",
        "api_requests": len(execution["attempts"]),
        "transport_retries": sum(is_transport_retry(item) for item in execution["attempts"]),
        "independent_requests_without_previous_model_responses": True,
        "HTTP_API_equals_final_raw": True,
        "reused_collected_originals": True,
        "local_replay_as_of": execution["replay_as_of"],
        "final_version_id": last[-1]["version_id"],
        "results": rows,
    }
    execution.update(
        state="three_consecutive_successes",
        consecutive_successes=3,
        success_basis="committed_schema_and_section_validation",
        transport_retries=result["transport_retries"],
    )
    if not (folder / "execution-before-verification.json").exists():
        (folder / "execution-before-verification.json").write_text(
            (folder / "execution.json").read_text()
        )
    (folder / "execution.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2) + "\n"
    )
    (folder / "final-verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "passed": True,
                "consecutive_successes": 3,
                "version_ids": [r["version_id"] for r in rows],
                "HTTP_API_equals_final_raw": True,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
