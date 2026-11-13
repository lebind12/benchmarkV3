"""fixture 1557474 전체 프리뷰 **실제 1회** 실행 스크립트 (새 기본 경로).

이 스크립트가 하는 일:

1. `~/.config/match-preview/{preview-dev.env, model-live.env}`(0600)에서 자격 증명을
   읽어 **프로세스 환경으로만** 넣는다. 값은 출력하지 않는다.
2. 새 기본 경로(`bundle_pipeline.run_bundle_pipeline`)를 **정확히 한 번** 실행한다.
   재시도는 **각 논리 모듈의 최초 포함 최대 3회**이며, 전체 8회 제한은 두지 않는다.
   모델 동시 2회·요청당 300초·출력 40,000은 제품 설정을 그대로 쓴다.
3. 실행 뒤 저장된 **섹션 결과 5개**(본문·근거·구조화)와 **정보 원문 묶음**(출처·구간·
   DB·배당·전달 기록)을 읽어 요약을 출력하고, 민감값 없는 결과 JSON을 저장한다.

하지 않는 것:

- 재시도 루프, 새 실행 ID로 상한 초기화, pong/preparation 호출, 숨은 모델 호출.
- 8000/5173 서버 종료·재시작. git stage/commit.
- 사용자 승인 생성. 승인은 관리자가 본문을 보고 만든다.

사용:

    .venv/bin/python scripts/preview_bundle_live_once.py --confirm-live

`--confirm-live` 없이는 실행하지 않는다(실수로 유료 호출이 나가지 않게).
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import uuid
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_VERSION = "mp11-live-once-1"
FIXTURE_ID = 1557474
FIXTURE = {
    "fixture_id": FIXTURE_ID,
    "league_id": 39,
    "season": 2026,
    "home_team_id": 13,
    "away_team_id": 4,
    "kickoff_at": "2026-11-21T12:30:00+00:00",
}
CREDENTIALS = pathlib.Path.home() / ".config" / "match-preview" / "preview-dev.env"
MODEL_CREDENTIALS = pathlib.Path.home() / ".config" / "match-preview" / "model-live.env"
EVIDENCE_DIR = REPO_ROOT / "docs" / "implementation" / "match-preview" / "evidence" / "ps05-live"


def _load_env_file(path: pathlib.Path) -> dict[str, str]:
    """0600 파일에서 KEY=VALUE만 읽는다. 파일 권한이 0600이 아니면 거부한다."""
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise SystemExit(f"refusing {path.name} with mode {oct(mode)} (expected 0o600)")
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _prepare_environment() -> dict[str, object]:
    """자격 증명을 환경에 넣고, **값이 아닌** 준비 상태만 돌려준다."""
    dev = _load_env_file(CREDENTIALS)
    model = _load_env_file(MODEL_CREDENTIALS)

    # 조회·쓰기 연결은 앱 설정 키로 매핑한다.
    mapping = {
        "PREVIEW_DATABASE_URL": dev.get("PREVIEW_DEV_DATABASE_URL"),
        "PREVIEW_IDENTITY_DATABASE_URL": dev.get("PREVIEW_IDENTITY_DATABASE_URL"),
        "PREVIEW_FIXTURES_DATABASE_URL": dev.get("PREVIEW_FIXTURES_DATABASE_URL"),
        "PREVIEW_NAMES_DATABASE_URL": dev.get("PREVIEW_NAMES_DATABASE_URL"),
        "PREVIEW_STATS_DATABASE_URL": dev.get("PREVIEW_STATS_DATABASE_URL"),
        "PREVIEW_ALLOW_NONLOCAL_DB": dev.get("PREVIEW_ALLOW_NONLOCAL_DB", "1"),
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB": dev.get(
            "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "1"
        ),
        "PREVIEW_ENV": "dev",
        "PREVIEW_MODEL_PROVIDER": model.get("PREVIEW_MODEL_PROVIDER", "vertex"),
        "PREVIEW_MODEL_PROJECT": model.get("PREVIEW_MODEL_PROJECT"),
        "PREVIEW_MODEL_LOCATION": model.get("PREVIEW_MODEL_LOCATION", "global"),
        "PREVIEW_MODEL_NAME": model.get("PREVIEW_MODEL_NAME"),
        "PREVIEW_MODEL_CREDENTIALS_JSON": model.get("PREVIEW_MODEL_CREDENTIALS_JSON"),
        "PREVIEW_MODEL_LIVE_ENABLED": model.get("PREVIEW_MODEL_LIVE_ENABLED", "1"),
    }
    present = {}
    for key, value in mapping.items():
        if value:
            os.environ[key] = str(value)
        present[key] = bool(value)
    return {
        "database_url_set": present["PREVIEW_DATABASE_URL"],
        "identity_url_set": present["PREVIEW_IDENTITY_DATABASE_URL"],
        "fixtures_url_set": present["PREVIEW_FIXTURES_DATABASE_URL"],
        "names_url_set": present["PREVIEW_NAMES_DATABASE_URL"],
        "stats_url_set": present["PREVIEW_STATS_DATABASE_URL"],
        "model_name": os.environ.get("PREVIEW_MODEL_NAME"),
        "model_location": os.environ.get("PREVIEW_MODEL_LOCATION"),
        "model_project_set": bool(os.environ.get("PREVIEW_MODEL_PROJECT")),
        "model_credentials_set": bool(os.environ.get("PREVIEW_MODEL_CREDENTIALS_JSON")),
        "model_live_enabled": os.environ.get("PREVIEW_MODEL_LIVE_ENABLED"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="실제 유료 호출을 승인한다. 이 플래그가 없으면 실행하지 않는다.",
    )
    parser.add_argument("--json", action="store_true", help="결과를 JSON으로 출력")
    args = parser.parse_args(argv)
    if not args.confirm_live:
        print(
            "refusing to run: 실제 모델 호출입니다. 승인된 1회 실행은 --confirm-live로 시작하세요.",
            file=sys.stderr,
        )
        return 2

    readiness = _prepare_environment()
    print("environment ready:", json.dumps(readiness, ensure_ascii=False))

    from app.preview.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    if not settings.model_live_enabled:
        print("PREVIEW_MODEL_LIVE_ENABLED is off; refusing to run", file=sys.stderr)
        return 2

    from app.preview.db import get_session_factory
    from app.preview import bundle_pipeline, provider
    from app.preview.contracts import RunMode
    from app.preview.sources.fixtures import StoredFixtureReader

    transport = provider.GoogleGenAIHttpTransport(
        project=settings.model_project,
        location=settings.model_location,
        model=settings.model_name,
        credentials_json=settings.model_credentials_json,
        mode=RunMode.LIVE,
    )
    problem = transport.configuration_problem()
    if problem:
        print(f"model configuration problem: {problem}", file=sys.stderr)
        return 2

    reader = (
        StoredFixtureReader.from_url(settings.fixtures_database_url)
        if settings.fixtures_database_url
        else None
    )
    # 예산은 **제품 정책**을 그대로 쓴다. 스크립트가 호출 횟수를 다시 제한하지 않는다
    # (호출자가 더 낮은 상한을 걸면 사용자가 정한 "모듈별 3회"가 실제로 시험되지 않는다).
    # 그래서 `limits=None`으로 두고 `run_bundle_pipeline`이 `RunBudget.for_generation`으로
    # 모듈별 3회 상한을 세우게 한다.
    limits = None
    # --- 이전 시험 집합의 장부 읽기 (표시·기록용) -------------------------
    # 상한 단위는 **모듈(logical_call_id)별 3회**이며, 계수는 이번 실행 안에서만 센다.
    # 아래 장부 읽기는 과거 사용량을 **보고**하기 위한 것이고, 새 실행을 막는 근거가
    # 아니다(2026-11-12 확정: 다른 경기·이전 시험의 누적은 차감하지 않는다).
    started = datetime.now(timezone.utc)
    factory = get_session_factory()
    from app.preview import send_ledger as ledger_module
    from sqlalchemy import select
    from app.preview.contracts import RequestClass
    from app.preview.models import PreviewWriteAudit

    # --- 이번 변경 시험의 **run 집합** -------------------------------------
    # 사용자 승인 단위는 모듈별 3회이며, 그 계수는 **이번 시험 집합** 안에서 누적된다.
    # 옛 고정 목록(0d938572·216d11ca)은 과거 시험이므로 더 이상 이 집합의 근거가 아니다.
    # 과거 3개 run의 전송 기록은 지우지 않고 그대로 보존한다(집합만 다르다).
    # 집합은 label의 `trial-set:<id>` 태그로 찾으므로, 스크립트를 다시 실행하거나 새 run이
    # 생겨도 자동으로 이 집합의 누적만 세고 0으로 초기화되지 않는다.
    TRIAL_SET_ID = os.environ.get("PREVIEW_TRIAL_SET_ID", "sf-b4-search-fallback").strip()
    # 집합이 시작되기 전에 이미 전송한 실행이 같은 집합으로 이어져야 하면 여기에 적는다.
    # 이번 집합은 **아직 전송 0회**이므로 비어 있다(값을 채우면 그 실행의 장부도 함께 센다).
    SEED_RUN_IDS: tuple[uuid.UUID, ...] = ()
    MODULES = (
        "discovery_people",
        "discovery_outlook",
        "section_players",
        "section_availability",
        "section_outlook",
        "section_ai_forecast",
    )
    # 상한 값은 제품 코드가 소유한다. 스크립트가 같은 숫자를 복제하지 않는다.
    MODULE_SEND_CAP = bundle_pipeline.MODULE_SEND_CAP
    prior_module_usage: dict[str, int] = {}
    with factory() as probe:
        # 1) 이 시험 집합에 속한 실행들을 label 태그로 찾는다(새 run/재시작에도 유지).
        trial_run_ids = list(SEED_RUN_IDS)
        try:
            from app.preview.models import PreviewRun

            tagged = probe.execute(
                select(PreviewRun.id, PreviewRun.label).where(
                    PreviewRun.label.contains(f"{bundle_pipeline.TRIAL_TAG_PREFIX}{TRIAL_SET_ID}")
                )
            ).all()
            for row in tagged:
                if bundle_pipeline.trial_set_of(row[1]) == TRIAL_SET_ID:
                    trial_run_ids.append(row[0])
        except Exception as exc:  # noqa: BLE001 - 집합을 못 읽으면 실행하지 않는다
            print(
                f"refusing to run: 시험 집합 실행 목록을 읽지 못했습니다({type(exc).__name__}).",
                file=sys.stderr,
            )
            return 2
        print(f"trial set {TRIAL_SET_ID}: 기존 실행 {len(trial_run_ids)}건")
        for prior_run_id in trial_run_ids:
            try:
                rows = probe.scalars(
                    select(PreviewWriteAudit).where(
                        PreviewWriteAudit.run_id == prior_run_id,
                        PreviewWriteAudit.action == ledger_module.CHARGE_ACTION,
                    )
                ).all()
            except Exception as exc:  # noqa: BLE001 - 기록 불명확이면 실행하지 않는다
                print(
                    f"refusing to run: 이전 run 장부를 읽지 못했습니다({type(exc).__name__}).",
                    file=sys.stderr,
                )
                return 2
            for row in rows:
                detail = dict(row.detail or {})
                if not detail.get("counted"):
                    continue
                if detail.get("request_class") != RequestClass.MODEL.value:
                    continue
                module_id = str(detail.get("logical_call_id"))
                prior_module_usage[module_id] = prior_module_usage.get(module_id, 0) + 1

    unexpected = [m for m in prior_module_usage if m not in MODULES]
    if unexpected:
        print(
            f"refusing to run: 장부에 예상 밖 모듈 id가 있습니다: {unexpected}",
            file=sys.stderr,
        )
        return 2
    print("per-module prior sends (from durable ledger):")
    for module_id in MODULES:
        used = prior_module_usage.get(module_id, 0)
        print(
            f"  {module_id:24} prior={used} cap={MODULE_SEND_CAP}"
            f" remaining={max(0, MODULE_SEND_CAP - used)}"
        )
    # 이전 시험 집합의 사용량은 **표시용**이다. 사용자 확정 정책은 "한 생성 실행의
    # 각 논리 모듈 최초 포함 3회"이므로, 과거 누적이 새 실행을 막지 않는다. 그래서
    # 여기서 실행을 거부하지 않고, 상한에 가까운 모듈만 참고로 알린다.
    near_cap = [
        m for m in MODULES if prior_module_usage.get(m, 0) >= MODULE_SEND_CAP
    ]
    if near_cap:
        print(
            f"note: 이전 시험 집합에서 상한에 도달한 모듈: {near_cap}."
            " 이번 실행에는 차감하지 않습니다(이력은 보존).",
            file=sys.stderr,
        )
    try:
        with factory() as session:
            outcome = bundle_pipeline.run_bundle_pipeline(
                session,
                fixture=dict(FIXTURE),
                actor_id=1,
                transport=transport,
                reader=reader,
                limits=limits,
                # 상한은 `run_bundle_pipeline`이 모듈별 3회로 세운다. 스크립트는
                # 상한 인자를 다시 넘기지 않는다(제품 정책을 우회하거나 좁히지 않는다).
                prior_module_usage=prior_module_usage,
                label="fixture 1557474 전체 프리뷰 (실제 1회)",
                # 이 실행을 **이번 시험 집합**에 넣는다. 이후 재시작·재실행에서도 같은
                # 집합의 누적 전송만 세고, 새 run으로 계수를 초기화하지 않는다.
                trial_set_id=TRIAL_SET_ID,
                mode=RunMode.LIVE,
                now=started,
            )
            session.commit()
            sections = bundle_pipeline.store.list_section_results(
                session, outcome.run_id
            )
            bundle_record = bundle_pipeline.store.load_information_bundle(
                session, outcome.run_id
            )
            detail = bundle_pipeline.store.get_run_detail(session, outcome.run_id)
            attempts = [
                {
                    "logical_call_id": row.get("logical_call_id"),
                    "attempt_ordinal": row.get("attempt_ordinal"),
                    "outcome": row.get("outcome"),
                    "http_status": row.get("http_status"),
                    "usage": row.get("usage"),
                    "started_at": row.get("started_at"),
                    "finished_at": row.get("finished_at"),
                }
                for row in detail.attempts
            ]
    finally:
        if reader is not None:
            reader.close()

    finished = datetime.now(timezone.utc)
    bundle = bundle_record.get("bundle") or {}
    summary = bundle_record.get("summary") or {}
    result = {
        "script_version": SCRIPT_VERSION,
        "fixture_id": FIXTURE_ID,
        "run_id": str(outcome.run_id),
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 1),
        "mode": outcome.mode.value,
        "status": outcome.status.value,
        "quality": outcome.quality.value,
        "external_calls": outcome.external_calls,
        "budget": dict(outcome.budget),
        "unavailable_reason": outcome.unavailable_reason,
        "bundle": {
            "available": bundle_record.get("available"),
            "bundle_id": summary.get("bundle_id"),
            "bundle_hash": summary.get("bundle_hash"),
            "source_count": summary.get("source_count"),
            "usable_source_count": summary.get("usable_source_count"),
            "failed_source_count": summary.get("failed_source_count"),
            "available_passages": summary.get("available_passages"),
            "available_chars": summary.get("available_chars"),
            "network_usage": summary.get("network_usage"),
            "db_readable": summary.get("db_readable"),
            "db_injuries": summary.get("db_injuries"),
            "odds_quotes": summary.get("odds_quotes"),
            "odds_adopted_quotes": summary.get("odds_adopted_quotes"),
            "section_delivery_count": summary.get("section_delivery_count"),
            "sources": [
                {
                    "source_id": source.get("source_id"),
                    "final_url": source.get("final_url"),
                    "nature": source.get("nature"),
                    "method": source.get("method"),
                    "http_status": source.get("http_status"),
                    "body_chars": source.get("body_chars"),
                    "passages": len(source.get("passages") or ()),
                    "failure": source.get("failure"),
                    "usable": source.get("usable"),
                }
                for source in bundle.get("sources") or ()
            ],
            "section_deliveries": [
                {
                    "section_id": item.get("section_id"),
                    "model_delivered": item.get("model_delivered"),
                    "passage_ids": item.get("passage_ids"),
                    "payload_sha256": item.get("payload_sha256"),
                    "sent_attempts": item.get("sent_attempts"),
                }
                for item in bundle.get("section_deliveries") or ()
            ],
            "diagnostics": list(bundle.get("diagnostics") or ()),
        },
        "sections": [
            {
                "workflow_id": row["workflow_id"],
                "version": row["version"],
                "mode": row["mode"],
                "quality": row["quality"],
                "unavailable": row["unavailable"],
                "unavailable_reason": row["unavailable_reason"],
                "title": row["title"],
                "body_chars": len(row["body"] or ""),
                "body_excerpt": (row["body"] or "")[:600],
                "source_count": len(row["sources"] or ()),
                "diagnostics": list(row["diagnostics"] or ()),
            }
            for row in sections
        ],
        "attempts": attempts,
    }

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    path = EVIDENCE_DIR / f"live-{stamp}-{outcome.run_id}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    path.chmod(0o600)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"run_id={outcome.run_id}")
        print(
            f"status={outcome.status.value} quality={outcome.quality.value}"
            f" external_calls={outcome.external_calls} duration={result['duration_seconds']}s"
        )
        print(
            "bundle:"
            f" sources={result['bundle']['source_count']}"
            f" usable={result['bundle']['usable_source_count']}"
            f" failed={result['bundle']['failed_source_count']}"
            f" passages={result['bundle']['available_passages']}"
            f" db_readable={result['bundle']['db_readable']}"
            f" odds={result['bundle']['odds_adopted_quotes']}"
        )
        for section in result["sections"]:
            mark = "OK  " if not section["unavailable"] else "MISS"
            print(
                f"  [{mark}] {section['workflow_id']:22} v{section['version']}"
                f" {section['quality']:12} chars={section['body_chars']}"
            )
        print(f"evidence: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
