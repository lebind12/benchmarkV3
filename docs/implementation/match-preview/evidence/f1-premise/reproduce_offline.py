"""F1 재현: 저장 원문 응답 + 저장 D0로 수정 후 R1 검증/본문 조립을 오프라인 재실행한다.

외부 모델·API-Football 호출은 0회다. DB 연결은 **읽기 전용 트랜잭션**으로 열고,
`preview_dev`의 저장 행만 읽는다(쓰기·승인 생성·fixture 초기화 없음). 자격 증명은
저장소 밖 0600 파일에서 읽으며 값을 출력하지 않는다.

    .venv/bin/python docs/implementation/match-preview/evidence/f1-premise/reproduce_offline.py

출력: 같은 디렉터리의 `evidence.json`(수정 전 저장 본문, 수정 후 문장, 덜어낸 사실,
내려놓은 전제).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import psycopg

REPO = Path(__file__).resolve().parents[5]
CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
OUTPUT = Path(__file__).resolve().parent / "evidence.json"

RUNS = {
    "baseline": "6e59041a-3767-4756-a412-991008873f50",
    "candidate": "7c0af3c0-4f55-4270-9266-be58c65d8f6b",
}

sys.path.insert(0, str(REPO))

from app.preview import sections, version_manifest  # noqa: E402
from app.preview.modules import compose, form  # noqa: E402


def _database_url() -> str:
    values: dict[str, str] = {}
    for line in CREDENTIALS.read_text(encoding="utf-8").splitlines():
        if line.startswith("PREVIEW_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values["PREVIEW_DEV_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")


def _stored(cursor, run_id: str) -> dict:
    """저장 R1/D0 결과·원문·섹션 본문을 읽는다. 읽기만 한다."""
    cursor.execute("set search_path = preview_dev")
    cursor.execute("set statement_timeout = '20s'")
    cursor.execute(
        "select module_id, version, payload from preview_dev.preview_results "
        "where run_id = %s::uuid order by module_id, version",
        (run_id,),
    )
    modules = {module_id: payload for module_id, _version, payload in cursor.fetchall()}
    cursor.execute(
        "select a.body from preview_dev.preview_attempts p "
        "join preview_dev.preview_artifacts a on a.id = p.response_artifact_id "
        "where p.run_id = %s::uuid and p.module_id = 'R1' "
        "order by p.attempt_ordinal desc limit 1",
        (run_id,),
    )
    row = cursor.fetchone()
    cursor.execute(
        "select version, body, workflow_version from preview_dev.preview_section_results "
        "where run_id = %s::uuid order by version desc limit 1",
        (run_id,),
    )
    section_version, section_body, section_stamp = cursor.fetchone()
    return {
        "modules": modules,
        "raw": json.loads(row[0]) if row and row[0] else None,
        "section_version": section_version,
        "section_body": section_body,
        "section_stamp": section_stamp,
    }


def _facts_from_d0(stored_payload: dict) -> form.FormFacts:
    inner = stored_payload.get("payload") or stored_payload
    fixture = inner.get("fixture") or {}
    return form.FormFacts(
        fixture_id=int(fixture.get("fixture_id") or 0),
        league_id=int(fixture.get("league_id") or 0),
        season=int(fixture.get("season") or 0),
        home_team_id=int(fixture.get("home_team_id") or 0),
        away_team_id=int(fixture.get("away_team_id") or 0),
        kickoff_at=dt.datetime.fromisoformat(fixture["kickoff_at"]),
        home_team=str(fixture.get("home_team") or "홈팀"),
        away_team=str(fixture.get("away_team") or "원정팀"),
        league=fixture.get("league"),
        facts=tuple(
            form.Fact(
                fact_id=str(item.get("fact_id")),
                text=str(item.get("text") or ""),
                snapshot_id=str(item.get("snapshot_id") or ""),
                collected_at=None,
                subject_team_id=item.get("subject_team_id"),
            )
            for item in inner.get("facts") or ()
        ),
    )


def main() -> int:
    evidence = {
        "policy": "설계 §5 사실 검증과 AI 판단의 경계 — 사용자 확정",
        "external_calls": 0,
        "api_football_calls": 0,
        "approvals_created": 0,
        "versions": {
            "r1_implementation_after": "mp05-form-3",
            "r1_prompt": form.FORM_PROMPT_VERSION,
            "compose": sections.FORM_COMPOSE_IMPLEMENTATION_VERSION,
            "note": "mp05-form-3은 MP09가 modules/__init__.py에 등록해야 workflow stamp에 반영된다",
        },
        "workflow_version": {"now": version_manifest.workflow_version_of(sections.FORM_SECTION_ID)},
        "runs": {},
    }
    with psycopg.connect(_database_url(), connect_timeout=15) as conn:
        conn.read_only = True
        with conn.cursor() as cursor:
            for name, run_id in RUNS.items():
                stored = _stored(cursor, run_id)
                facts = _facts_from_d0(stored["modules"]["D0"])
                raw = stored["raw"]
                grounding = form.parse_grounding(raw)
                payload = form.parse_model_json(raw["candidates"][0]["content"]["parts"][0]["text"])
                validated = form.validate_response(
                    payload, facts=facts, grounding=grounding, now=dt.datetime.now(dt.timezone.utc)
                )
                api_claims = form._api_fact_claims(facts)
                research = form.FormResearch(
                    facts=facts,
                    claims=tuple(api_claims) + tuple(validated.claims),
                    coverage=tuple(validated.coverage),
                    diagnostics=tuple(validated.diagnostics),
                    uncertainties=tuple(validated.uncertainties),
                    watch_points=tuple(validated.watch_points),
                    hot_players=tuple(validated.hot_players),
                    recent_form=tuple(validated.recent_form),
                    match_importance=(payload.get("match_context") or {}).get("importance") or None,
                    sources=form._result_sources(grounding),
                    grounding=grounding,
                    external_calls=0,
                )
                body_payload = dict(research.payload())
                body_payload["claims"] = [claim.to_dict() for claim in research.claims]
                body_payload["coverage"] = [entry.to_dict() for entry in research.coverage]
                body_payload.setdefault(
                    "api_sources",
                    list((stored["modules"]["D0"].get("payload") or {}).get("api_sources") or ()),
                )
                composed = compose.compose_form_body(body_payload)
                evidence["runs"][name] = {
                    "run_id": run_id,
                    "stored_section": {
                        "version": stored["section_version"],
                        "workflow_version": stored["section_stamp"],
                        "body": stored["section_body"],
                        "chars": len(stored["section_body"] or ""),
                    },
                    "counts": {
                        "watch_points": len(validated.watch_points),
                        "hot_players": len(validated.hot_players),
                        "recent_form": len(validated.recent_form),
                    },
                    "watch_points": [
                        {"title": item["title"], "detail": item["detail"]}
                        for item in validated.watch_points
                    ],
                    "hot_players": [
                        {"player": item["player"], "reason": item["reason"]}
                        for item in validated.hot_players
                    ],
                    "dropped_facts": list(validated.dropped_facts),
                    "unasserted_premises": list(validated.unasserted_premises),
                    "body_after": composed.body,
                    "body_after_chars": len(composed.body),
                    "grounding_sources": len(grounding.get("sources") or ()),
                    "api_fact_count": len(facts.facts),
                }
    OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    for name, run in evidence["runs"].items():
        print(
            f"{name}: saved {run['stored_section']['chars']}자 -> {run['body_after_chars']}자,"
            f" counts={run['counts']}, premises={len(run['unasserted_premises'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
