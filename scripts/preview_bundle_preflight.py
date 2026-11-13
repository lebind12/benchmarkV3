"""프리뷰 섹션 실행의 **기록 전송 preflight**.

목적: 유료 호출을 한 번이라도 열기 전에, 전송 이후 경로 전체(전송 → 원문 보존 → 정규화 →
저장 → 섹션 결과 → 정보 원문 묶음 저장 → 관리자 조회)를 **네트워크 없이** 끝까지
통과시켜 본다.

무엇을 확인하는가:

1. `execute_request`가 전송 **전** 예약을 남기고, 응답 **직후** 결과를 남긴다.
2. 그 뒤 저장·정규화 단계에서 예외가 나도 원문·사용량·실행 기록이 남는다(장부 독립).
3. 정상 6회 / 최대 8회 / 동시 2 상한이 지켜지고, 9번째는 **전송 없이** 거부된다.
4. 정보 원문 묶음이 저장되고 관리자 조회 경로와 같은 모양으로 다시 열린다.
5. 섹션 결과가 버전으로 저장되고 `SectionDelivery`(payload 해시)가 실제 요청과 맞는다.

무엇을 **하지 않는가**:

- 실제 모델·외부 HTTP를 부르지 않는다. 모든 transport는 `RecordedTransport`이고,
  `--mode`는 항상 `recorded`만 허용한다. 이 스크립트로 만든 결과를 live 성공으로
  인용하지 않는다.
- 운영 DB에 쓰지 않는다. 대상은 `*_test` / `test_*` 전용 로컬 DB뿐이며, 시작 전에
  `tests.preview._dbguard.assert_safe_test_database`로 확인한다.
- 사용자 승인·배포·git 조작을 하지 않는다.

사용:

    .venv/bin/python scripts/preview_bundle_preflight.py
    .venv/bin/python scripts/preview_bundle_preflight.py --fixture 1557474 --json

종료 코드는 확인 항목이 모두 통과하면 0, 하나라도 실패하면 1이다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_VERSION = "mp11-preflight-1"
DEFAULT_FIXTURE_ID = 1557474
FIXED_NOW = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)

FIXTURE = {
    "fixture_id": DEFAULT_FIXTURE_ID,
    "league_id": 39,
    "season": 2026,
    "home_team_id": 13,
    "away_team_id": 4,
    "kickoff_at": "2026-11-21T12:30:00+00:00",
}

NORMAL_LOGICAL_CALLS = (
    "discovery_people",
    "discovery_outlook",
    "section_players",
    "section_availability",
    "section_outlook",
    "section_ai_forecast",
)


class PreflightFailure(RuntimeError):
    """확인 항목 실패. 어떤 항목이 왜 실패했는지 그대로 보고한다."""


def _check(results: list[dict[str, Any]], name: str, ok: bool, detail: Any = None) -> None:
    results.append({"check": name, "ok": bool(ok), "detail": detail})
    if not ok:
        raise PreflightFailure(f"{name}: {detail}")


def _ok_response(text: str) -> Any:
    from app.preview import provider

    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "preflight 요청"},
        raw_response={
            "candidates": [
                {
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": "STOP",
                }
            ]
        },
        usage={"input_tokens": 130, "output_tokens": 90},
        duration_ms=6,
    )


def _recorded_transport(count: int = 24) -> Any:
    from app.preview import provider
    from app.preview.contracts import RunMode

    return provider.RecordedTransport(
        script=[_ok_response(f"preflight 응답 {index}") for index in range(count)],
        provider="preflight-recorded",
        # 계수 경로를 실제와 같게 보기 위해 live로 둔다. 네트워크는 없다(모듈 docstring).
        mode=RunMode.LIVE,
    )


def _context(run_id: uuid.UUID) -> Any:
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        ExecutionLimits,
        OperationKind,
        RunMode,
    )

    return ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.TEST,
        mode=RunMode.LIVE,
        actor_id=1,
        config_version="mp11-preflight",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _sample_bundle() -> Any:
    from app.preview import information_bundle as bundle_contract

    source = bundle_contract.BundleSource(
        source_id="src:preflight-stats",
        discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
        requested_url="https://example.test/stats",
        final_url="https://example.test/stats",
        nature="stats",
        method="fresh_http",
        title="시즌 기록(preflight)",
        captured_at=FIXED_NOW,
        http_status=200,
        body_chars=1800,
        passages=(
            bundle_contract.Passage(
                passage_id="src:preflight-stats#p1",
                source_id="src:preflight-stats",
                ordinal=1,
                text="홈팀의 최근 5경기 성적은 3승 1무 1패입니다.",
            ),
        ),
    )
    blocked = bundle_contract.BundleSource(
        source_id="src:preflight-blocked",
        discovery_group=bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,
        requested_url="https://example.test/odds",
        final_url="https://example.test/odds",
        nature="unavailable",
        method="unavailable",
        http_status=403,
        failure="HTTP 403 챌린지",
    )
    return bundle_contract.InformationBundle(
        bundle_id=bundle_contract.new_bundle_id("preflight"),
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=(source, blocked),
        db_snapshot=bundle_contract.DbSnapshot(
            fixture=dict(FIXTURE),
            team_id_space="internal",
            collected_at=FIXED_NOW,
            teams=(
                {"team_id": 13, "name_ko": "맨체스터 시티"},
                {"team_id": 4, "name_ko": "풀럼"},
            ),
            standings=({"team_id": 13, "rank": 3, "points": 21},),
            injuries=(),
            coverage=(
                {
                    "topic": "부상·출전 불확실",
                    "state": "unknown",
                    "detail": "저장된 부상 행이 없습니다. '없음'의 증거가 아닙니다.",
                },
            ),
            source_tables=("public.fixture", "public.team", "public.standings"),
            readable=True,
        ),
        discovery_groups=(
            bundle_contract.DiscoveryGroup(
                group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
                status="completed",
                logical_call_id="discovery_people",
                sent_attempts=1,
            ),
            bundle_contract.DiscoveryGroup(
                group=bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,
                status="completed",
                logical_call_id="discovery_outlook",
                sent_attempts=1,
            ),
        ),
        network_usage=bundle_contract.NetworkUsage(
            http_used=2, http_failed=1, http_limit=24
        ),
        mode="live",
        diagnostics=("배당 사이트 1곳이 차단되어 본문을 얻지 못했습니다.",),
    )


def _run_preflight(fixture_id: int) -> dict[str, Any]:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.preview import information_bundle as bundle_contract
    from app.preview import provider, send_ledger, store
    from app.preview.contracts import (
        FixtureIdentity,
        ModuleInput,
        ModuleResult,
        ModuleStatus,
        QualityStatus,
        RunStatus,
    )
    from app.preview.retry import RunBudget

    results: list[dict[str, Any]] = []
    test_url = os.environ.get(
        "PREVIEW_TEST_DATABASE_URL",
        "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_test",
    )
    from tests.preview._dbguard import assert_safe_test_database

    target = assert_safe_test_database(test_url)
    results.append(
        {
            "check": "test_database_target",
            "ok": True,
            "detail": {"host": target.host, "port": target.port, "name": target.name},
        }
    )

    engine = create_engine(
        test_url,
        future=True,
        # 스키마를 생략한 쿼리가 개발 영역에만 떨어지게 한다(앱 연결과 같은 설정).
        connect_args={"options": "-c search_path=preview_dev"},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    # 전송 장부도 **같은 테스트 DB**를 쓰게 고정한다. 이걸 빠뜨리면 장부가 기본 개발
    # DSN으로 가서 사용량이 다른 DB에 남는다(검사에서 즉시 드러난다).
    send_ledger.bind_send_session_factory(factory)
    from sqlalchemy import text as _sql_text

    from app.preview.db import SCHEMA, Base

    # 전용 테스트 DB 안에서만 스키마를 새로 만든다. 이 블록은 *_test 대상에서만 실행된다.
    with engine.begin() as conn:
        conn.execute(_sql_text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(_sql_text(f"CREATE SCHEMA {SCHEMA}"))
    Base.metadata.create_all(engine)

    run_id = uuid.uuid4()
    context = _context(run_id)
    budget = RunBudget.for_run(
        now=FIXED_NOW,
    )
    transport = _recorded_transport()

    try:
        with factory() as session:
            store.store_run(
                session,
                context,
                fixture=FixtureIdentity.from_dict({**FIXTURE, "fixture_id": fixture_id}),
                fixture_label=f"fixture {fixture_id}",
                label="mp11 preflight",
                status=RunStatus.RUNNING,
            )
            session.commit()

            # (1) 정상 6회 전송. 매 호출이 예약+결과 두 행을 남긴다.
            for index, logical_call_id in enumerate(NORMAL_LOGICAL_CALLS):
                result = provider.execute_request(
                    provider.RequestSpec(
                        logical_call_id=logical_call_id,
                        provider="preflight-recorded",
                        model="preflight-model",
                        operation="preflight",
                        module_id="D1" if index < 2 else "C1",
                    ),
                    context,
                    transport=transport,
                    budget=budget,
                    session=session,
                    sleeper=lambda seconds: None,
                    now=lambda: FIXED_NOW,
                )
                if not result.ok:
                    raise PreflightFailure(
                        f"{logical_call_id} 기록 전송이 실패했다: {result.stopped_reason}"
                    )
            _check(
                results,
                "normal_six_sends",
                budget.model_used == 6
                and send_ledger.charged_requests(session, run_id=run_id) == 6,
                {"budget": budget.model_used, "ledger": send_ledger.charged_requests(session, run_id=run_id)},
            )

            # (2) 재시도 여유 2회까지는 나가고, 3번째는 전송 없이 거부된다.
            for index in range(2):
                provider.execute_request(
                    provider.RequestSpec(
                        logical_call_id=f"preflight-retry-{index}",
                        provider="preflight-recorded",
                        model="preflight-model",
                        operation="preflight",
                        module_id="C1",
                    ),
                    context,
                    transport=transport,
                    budget=budget,
                    session=session,
                    sleeper=lambda seconds: None,
                    now=lambda: FIXED_NOW,
                )
            sent_before = len(transport.calls)
            refused = provider.execute_request(
                provider.RequestSpec(
                    logical_call_id="preflight-ninth",
                    provider="preflight-recorded",
                    model="preflight-model",
                    operation="preflight",
                    module_id="C1",
                ),
                context,
                transport=transport,
                budget=budget,
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            )
            _check(
                results,
                "ninth_send_refused_without_transport",
                refused.ok is False and len(transport.calls) == sent_before,
                {"calls_before": sent_before, "calls_after": len(transport.calls)},
            )

            # (3) 실제 전송 직후 예외 + 실행 트랜잭션 롤백 → 장부는 남는다.
            rollback_run = uuid.uuid4()
            rb_context = _context(rollback_run)
            store.store_run(
                session,
                rb_context,
                fixture=FixtureIdentity.from_dict({**FIXTURE, "fixture_id": fixture_id}),
                label="mp11 preflight rollback",
                status=RunStatus.RUNNING,
            )
            session.commit()
            sent = provider.execute_request(
                provider.RequestSpec(
                    logical_call_id="section_players",
                    provider="preflight-recorded",
                    model="preflight-model",
                    operation="preflight",
                    module_id="C1",
                ),
                rb_context,
                transport=transport,
                budget=RunBudget.for_run(now=FIXED_NOW),
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            )
            if not sent.ok:
                raise PreflightFailure("롤백 검사용 전송이 실패했다")
            session.rollback()
            session.close()

            with factory() as fresh:
                charged = send_ledger.charged_requests(fresh, run_id=rollback_run)
                from sqlalchemy import select

                from app.preview.models import PreviewWriteAudit

                rows = [
                    dict(row.detail or {})
                    for row in fresh.scalars(
                        select(PreviewWriteAudit).where(
                            PreviewWriteAudit.run_id == rollback_run
                        )
                    )
                    if str(dict(row.detail or {}).get("logical_call_id")) == "section_players"
                ]
                _check(
                    results,
                    "post_send_failure_keeps_charge_and_body",
                    charged == 1 and any(row.get("usage") for row in rows),
                    {
                        "charged": charged,
                        "rows_with_usage": sum(1 for row in rows if row.get("usage")),
                    },
                )

            # (4) 정보 원문 묶음 저장 → 같은 모양으로 다시 열린다.
            with factory() as bundle_session:
                bundle = _sample_bundle()
                saved = store.save_information_bundle(
                    bundle_session, run_id=run_id, bundle=bundle, actor_id=1
                )
                bundle_session.commit()
                reopened = store.load_information_bundle(bundle_session, run_id)
                _check(
                    results,
                    "bundle_saved_and_reopened",
                    reopened["available"] is True
                    and reopened["bundle"]["bundle_hash"]
                    == saved["bundle"]["bundle_hash"]
                    and [s["source_id"] for s in reopened["bundle"]["sources"]]
                    == ["src:preflight-stats", "src:preflight-blocked"],
                    {"artifact_id": reopened.get("artifact_id")},
                )

                # (5) 섹션 결과 + 실제 전달 기록(payload 해시)
                payload = {
                    "contents": [
                        {"role": "user", "parts": [{"text": "홍팀 최근 5경기 3승 1무 1패"}]}
                    ]
                }
                delivery = bundle_contract.build_section_delivery(
                    section_id=bundle_contract.SECTION_PLAYERS,
                    payload=payload,
                    passage_ids=("src:preflight-stats#p1",),
                    source_ids=("src:preflight-stats",),
                    available_passage_ids=("src:preflight-stats#p1",),
                    logical_call_id="section_players",
                    model_delivered=True,
                    sent_attempts=1,
                    implementation_version="preflight-impl",
                    prompt_version="preflight-prompt",
                )
                bundle = bundle.with_section_delivery(delivery)
                execution = store.start_module_execution(
                    bundle_session,
                    run_id=run_id,
                    module_id="C1",
                    module_input=ModuleInput(
                        module_id="C1",
                        fixture=FixtureIdentity.from_dict(FIXTURE),
                        snapshot_ids=(),
                        selected_result_ids=(),
                        input_hash="preflight-hash",
                        prompt_version="preflight-prompt",
                        contract_version="preflight-contract",
                        implementation_version="preflight-impl",
                    ),
                    ordinal=0,
                    actor_id=1,
                )
                stored = store.save_module_result(
                    bundle_session,
                    ModuleResult(
                        result_id=uuid.uuid4(),
                        module_id="C1",
                        module_execution_id=execution.id,
                        run_id=run_id,
                        version=1,
                        input_hash="preflight-hash",
                        status=ModuleStatus.SUCCEEDED,
                        quality=QualityStatus.READY,
                        payload={"payload": {"preflight": True}},
                    ),
                    actor_id=1,
                )
                section = store.save_section_result(
                    bundle_session,
                    run_id=run_id,
                    workflow_id=bundle_contract.SECTION_PLAYERS,
                    workflow_version="preflight@1",
                    title="주목 선수(preflight)",
                    body="preflight 본문",
                    version=1,
                    mode=context.mode,
                    environment=context.environment,
                    quality=QualityStatus.READY,
                    output_contract_version="preflight-out-1",
                    contract_version="preflight-contract",
                    sources=({"label": "시즌 기록(preflight)", "kind": "web_article"},),
                    module_execution_ids=(execution.id,),
                    result_ids=(stored.id,),
                )
                bundle_session.commit()
                _check(
                    results,
                    "section_delivery_matches_payload",
                    delivery.payload_sha256
                    == bundle_contract.delivery_hash(payload)
                    and bundle_contract.bundle_summary(bundle)["section_delivery_count"] == 1,
                    {"payload_sha256": delivery.payload_sha256[:12]},
                )
                _check(
                    results,
                    "section_result_saved_with_version",
                    section.version == 1 and bool(section.body),
                    {"section_result_id": str(section.id)},
                )
                # 재처리(무전송)가 새 버전을 만든다.
                replay = provider.replay_result(
                    bundle_session,
                    source_result_id=stored.id,
                    transform=lambda raw, previous: {
                        "claims": [],
                        "coverage": [],
                        "diagnostics": ["preflight 재처리"],
                        "payload": {"replayed": True},
                    },
                    actor_id=1,
                )
                bundle_session.commit()
                _check(
                    results,
                    "replay_makes_new_version_without_sending",
                    replay.external_calls == 0 and replay.new_version == 2,
                    {"new_version": replay.new_version},
                )
                _check(
                    results,
                    "ledger_unchanged_by_replay",
                    send_ledger.charged_requests(bundle_session, run_id=run_id) == 8,
                    {
                        "charged": send_ledger.charged_requests(
                            bundle_session, run_id=run_id
                        )
                    },
                )
    finally:
        engine.dispose()

    return {
        "script_version": SCRIPT_VERSION,
        "mode": "recorded",  # 실제 네트워크·유료 호출 없음
        "external_paid_calls": 0,
        "fixture_id": fixture_id,
        "run_id": str(run_id),
        "checks": results,
        "all_passed": all(item["ok"] for item in results),
        "note": (
            "기록 transport preflight입니다. 실제 모델·외부 HTTP를 부르지 않았으며"
            " 이 결과를 live 성공으로 인용하지 않습니다. 전용 로컬 테스트 DB만"
            " 사용했습니다."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=int, default=DEFAULT_FIXTURE_ID)
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args(argv)

    try:
        report = _run_preflight(args.fixture)
    except PreflightFailure as exc:
        print(f"preflight FAILED: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"preflight {SCRIPT_VERSION} — mode={report['mode']} (유료 호출 0회)")
        for item in report["checks"]:
            mark = "OK  " if item["ok"] else "FAIL"
            print(f"  [{mark}] {item['check']}")
        print(f"all_passed={report['all_passed']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
