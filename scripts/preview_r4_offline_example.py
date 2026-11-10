"""R4 오프라인 예시 — 이미 저장된 R1 원문의 선정·이유를 R4 계약으로 옮긴다.

이 스크립트가 하는 일과 하지 않는 일:

- **한다**: 기존에 저장된 R1 live 원문(사용자가 이미 수용한 서술)에서 `hot_players`
  항목을 읽어 R4 출력 계약(`selected_player`/`selection_reason`)으로 **변환**하고,
  주입된 DB 한국어 이름 해석기로 표시 이름을 확인한다. 읽는 곳은 두 가지다.
  ① `--r1-run-id`를 주면 `preview_dev.preview_results`의 저장 payload를 **읽기 전용**으로
  읽고, ② 없으면 `--r1-source` 근거 JSON을 읽는다(저장 payload보다 정보가 적다).
- **하지 않는다**: 모델·API 호출, 새 R4 생성, 문장 품질 평가, 승인 생성, DB 쓰기.
  재사용한 값이므로 결과에는 `origin="reused_r1_selection"`이 붙는다. 이것은 R4 live
  실행이 아니다.

실행(저장소 루트에서, 읽기 전용):

```sh
.venv/bin/python scripts/preview_r4_offline_example.py \
    --r1-run-id 6e59041a-3767-4756-a412-991008873f50 \
    --out docs/implementation/match-preview/evidence/mp-r4-players/offline-example.json
```

이름 해석기는 `PREVIEW_NAMES_DATABASE_URL`(저장소 밖 0600 파일)이 있을 때만 붙는다.
없으면 `mapping_status="resolver_not_injected"`로 남고, 스크립트는 한국어 이름을
만들지 않는다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.preview import provider
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    FixtureIdentity,
    ModuleInput,
    OperationKind,
    RunMode,
    compute_input_hash,
)
from app.preview.modules import players
from app.preview.modules import players_contract as contract
from app.preview.retry import RunBudget

DEFAULT_ENV_FILE = "~/.config/match-preview/preview-dev.env"
NAMES_KEY = "PREVIEW_NAMES_DATABASE_URL"
DEV_DB_KEY = "PREVIEW_DEV_DATABASE_URL"


def _env_value(path: str, key: str) -> str | None:
    """자격 증명 파일에서 키 값만 읽는다. 값은 출력하지 않는다."""
    file = Path(os.path.expanduser(path))
    if not file.exists():
        return None
    for line in file.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{key}="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            return value or None
    return None


def _r1_hot_players(source: Mapping[str, Any], run_key: str) -> tuple[list[dict[str, Any]], dict]:
    """저장된 R1 근거에서 이 실행의 `hot_players`를 읽는다. 없으면 빈 목록."""
    runs = source.get("runs") or {}
    run = runs.get(run_key) or {}
    rows = run.get("hot_players") or []
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        player = str(row.get("player") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if not player or not reason:
            continue
        items.append(
            {
                contract.SELECTED_PLAYER_FIELD: player,
                contract.SELECTION_REASON_FIELD: reason,
                "team": None,
                "player_ref": None,
                "evidence": [],
                "superlative_basis": None,
            }
        )
    fixture = {
        "run_id": run.get("run_id"),
        "stored_section_version": (run.get("stored_section") or {}).get("version"),
        "source_hot_player_count": len(rows),
    }
    return items, fixture


def _r1_hot_players_from_db(env_file: str, run_id: str) -> tuple[list[dict[str, Any]], dict]:
    """저장된 R1 결과 payload에서 선정 항목을 읽는다(읽기 전용, 범위 한정).

    `preview_results.payload`는 `ModuleResult` 사전이고, 모듈 payload는 그 안의
    `payload` 키에 있다. 다시 모듈 payload의 `payload` 키에 R1 조사 결과가 있으므로
    실제 경로는 `payload->'payload'->'payload'->'hot_players'`다.
    """
    url = _env_value(env_file, DEV_DB_KEY)
    if not url:
        raise SystemExit(f"{DEV_DB_KEY} is not configured; pass --r1-source instead")
    from sqlalchemy import text

    from app.auth.identity import build_read_only_engine

    engine = build_read_only_engine(url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SET LOCAL statement_timeout = 5000"))
            row = conn.execute(
                text(
                    """
                    SELECT version, implementation_version, prompt_version,
                           payload->'payload'->'payload'->'hot_players' AS players
                    FROM preview_dev.preview_results
                    WHERE run_id = CAST(:run_id AS uuid) AND module_id = 'R1'
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {"run_id": run_id},
            ).mappings().first()
    finally:
        engine.dispose()
    if row is None or not row["players"]:
        raise SystemExit(f"no stored R1 hot_players for run {run_id}")
    items: list[dict[str, Any]] = []
    for raw in row["players"]:
        if not isinstance(raw, Mapping):
            continue
        player = str(raw.get("player") or "").strip()
        reason = str(raw.get("reason") or "").strip()
        if not player or not reason:
            continue
        items.append(
            {
                contract.SELECTED_PLAYER_FIELD: player,
                contract.SELECTION_REASON_FIELD: reason,
                "team": str(raw.get("team") or "").strip() or None,
                "player_ref": None,
                "evidence": [],
                "superlative_basis": raw.get("superlative_basis"),
            }
        )
    meta = {
        "run_id": run_id,
        "source": "preview_dev.preview_results (read-only)",
        "r1_result_version": row["version"],
        "r1_implementation_version": row["implementation_version"],
        "r1_prompt_version": row["prompt_version"],
        "source_hot_player_count": len(row["players"]),
    }
    return items, meta


def _build_resolver(env_file: str):
    """읽기 전용 이름 해석기를 만든다. 설정이 없으면 `None`(이름을 만들지 않는다)."""
    url = _env_value(env_file, NAMES_KEY)
    if not url:
        return None, None
    from app.preview.localized_names import DbNameLookup, DisplayNames, load_name_index

    lookup = DbNameLookup.from_url(url)
    # 저장 DB 경기(1557474 = Manchester City vs Fulham)의 두 팀 로스터만 읽는다.
    index = load_name_index(lookup, team_ids=[13, 4])
    lookup.close()
    return DisplayNames(index), "db_read_only_bounded"


def _offline_transport(items: Sequence[Mapping[str, Any]]) -> provider.RecordedTransport:
    """재사용한 선정을 **기록 응답**으로 감싼다. 새 생성이 아니라 재생이다."""
    model_text = json.dumps(
        {"players": list(items), "search_note": None, "uncertainties": []},
        ensure_ascii=False,
    )
    return provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"note": "reused saved R1 selection; nothing was sent"},
                raw_response={"candidates": [{"content": {"parts": [{"text": model_text}]}}]},
            )
        ],
        mode=RunMode.REPLAY,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1-source", help="저장된 R1 근거 JSON 경로")
    parser.add_argument("--r1-run", default="baseline", help="근거 안의 실행 키(baseline/candidate)")
    parser.add_argument("--r1-run-id", help="저장된 R1 결과를 읽을 실행 ID(읽기 전용 DB)")
    parser.add_argument("--out", required=True, help="예시 결과 JSON을 쓸 경로")
    parser.add_argument("--env-file", default=DEFAULT_ENV_FILE)
    args = parser.parse_args(argv)

    if not args.r1_run_id and not args.r1_source:
        raise SystemExit("pass --r1-run-id (stored payload) or --r1-source (evidence JSON)")
    if args.r1_run_id:
        items, fixture_meta = _r1_hot_players_from_db(args.env_file, args.r1_run_id)
    else:
        source = json.loads(Path(args.r1_source).read_text(encoding="utf-8"))
        items, fixture_meta = _r1_hot_players(source, args.r1_run)
        fixture_meta = {"path": args.r1_source, "run_key": args.r1_run, **fixture_meta}
    resolver, resolver_note = _build_resolver(args.env_file)

    moment = datetime(2026, 11, 11, tzinfo=timezone.utc)
    fixture = FixtureIdentity(
        fixture_id=1557474,
        league_id=1,
        season=2026,
        home_team_id=13,
        away_team_id=4,
        kickoff_at=datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc),
    )
    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=RunMode.REPLAY,
        actor_id=1,
        config_version="r4-offline-example",
    )
    module_input = ModuleInput(
        module_id=players.PLAYERS_MODULE_ID,
        fixture=fixture,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash({"module": "R4", "origin": "reused_r1_selection"}),
        prompt_version=players.PROMPT_VERSION,
        contract_version="mp02-module-input-1",
        implementation_version=players.IMPLEMENTATION_VERSION,
    )
    research = players.research_players(
        None,
        module_input=module_input,
        context=context,
        transport=_offline_transport(items),
        budget=RunBudget.for_run(now=moment),
        resolver=resolver,
        now=moment,
        origin="reused_r1_selection",
    )
    payload = dict(research.payload())
    composed = players.compose_players_body(payload)

    example = {
        "note": (
            "이미 저장된 R1 선정·이유를 R4 계약으로 변환한 **오프라인 예시**입니다."
            " 새 R4 live 생성이 아니며, 모델·API 호출 0회입니다."
        ),
        "origin": "reused_r1_selection",
        "not_live_r4_generation": True,
        "model_calls": 0,
        "api_calls": 0,
        "external_calls_reported": research.external_calls,
        "r1_source": dict(fixture_meta),
        "name_resolver": resolver_note or "not_injected",
        "output_contract_version": contract.OUTPUT_CONTRACT_VERSION,
        "display_labels": dict(contract.DISPLAY_LABELS),
        "players": payload["players"],
        "unmapped": payload["unmapped"],
        "mapping": payload["mapping"],
        "coverage": payload["coverage"],
        "diagnostics": payload["diagnostics"],
        "composed_body": composed.body,
        "composed_quality": composed.quality.value,
        "contract_summary": contract.contract_summary(),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(example, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {out_path}")
    print(f"players={len(example['players'])} origin={example['origin']} model_calls=0")
    for row in example["players"]:
        print(
            f"- 선정 선수: {row[contract.SELECTED_PLAYER_FIELD]}"
            f" ({row.get('mapping_status')}, {row.get('name_source')})"
        )
        print(f"  선정 이유: {row[contract.SELECTION_REASON_FIELD]}")
    if example["unmapped"]:
        print(f"unmapped={len(example['unmapped'])} (원래 표기 유지, 이름 만들지 않음)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
