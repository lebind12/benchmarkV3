"""섹션 워크플로우 **실제(live) 실행 1회** — 사용자 검토용 본문·근거 만들기.

이 스크립트가 하는 일:

1. 저장된 경기 자료를 읽기 전용으로 재사용해 공유 사실(D0 성격)을 만든다.
2. 지정한 섹션의 조사 노드를 공통 모델 경로(`request_model` -> `execute_request`)로
   **한 번** 호출한다. 기본값은 `section_form`(R1)이고 `--workflow section_players`로
   R4(주목 선수)를 고를 수 있다.
3. 검증된 조사 결과로 독자용 본문을 결정적으로 조립하고 섹션 결과를 `preview_dev`에
   저장한다.
4. 저장된 본문·근거와 실행 ID를 표준출력으로 보여준다.

이것이 확인하는 것과 아닌 것:

- 확인: 실제 경기 한 건에서 섹션 워크플로우가 실제 모델·저장 자료로 끝까지 돌고,
  사용자가 읽을 수 있는 본문과 출처가 `preview_dev`에 저장되는가.
- 아님: 사용자 승인. 승인은 관리자 화면에서 사용자가 직접 만든다. 이 스크립트는
  승인 행을 만들지 않는다.

경계:

- 쓰기는 `preview_dev`의 이 실행(run·시도·원문·결과·섹션 결과)뿐이다. 기존 경기·계정
  자료는 읽기만 한다.
- 모델 이름·프로젝트·리전은 설정에서만 읽는다. 실패해도 대체 모델로 다시 시도하지
  않는다. `--one-send`(기본)는 논리 호출당 시도 상한을 1로 고정해, 429·오류가 나도
  두 번째 전송을 만들지 않는다. 실패는 그대로 기록하고 멈춘다.
- 팀·선수 표시 이름은 `PREVIEW_NAMES_DATABASE_URL`이 있을 때만 DB 한국어 값을 쓴다.
  없으면 원래 표기를 유지한다(번역을 지어내지 않는다).
- 비밀값은 출력하지 않는다. 원문 아티팩트는 가림 경로를 지난다.

    .venv/bin/python scripts/preview_section_live_run.py --fixture-id 1557474 --dry-run
    .venv/bin/python scripts/preview_section_live_run.py --fixture-id 1557474 \
        --workflow section_players
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
DEFAULT_MODEL_CREDENTIALS = Path.home() / ".config" / "match-preview" / "model-live.env"
MODEL_ENV_PREFIX = "PREVIEW_MODEL_"


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(f"missing credentials file: {path}")
    mode = oct(path.stat().st_mode)[-3:]
    if mode != "600":
        raise SystemExit(f"refusing credentials file with mode {mode} (expected 600): {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _unquote(value)
    return values


def _load_environment(model_credentials: Path, dev_credentials: Path) -> None:
    dev = _read_env_file(dev_credentials)
    os.environ.setdefault("PREVIEW_DATABASE_URL", dev.get("PREVIEW_DEV_DATABASE_URL", ""))
    os.environ.setdefault(
        "PREVIEW_IDENTITY_DATABASE_URL", dev.get("PREVIEW_IDENTITY_DATABASE_URL", "")
    )
    os.environ.setdefault("PREVIEW_FIXTURES_DATABASE_URL", dev.get("PREVIEW_FIXTURES_DATABASE_URL", ""))
    # 팀·선수 표시 이름용 읽기 전용 연결(별도 좁은 역할). 없으면 원래 표기를 쓴다.
    # 이 키를 넘기지 않으면 R4가 만든 표시 이름이 영어로 남는다.
    os.environ.setdefault("PREVIEW_NAMES_DATABASE_URL", dev.get("PREVIEW_NAMES_DATABASE_URL", ""))
    os.environ.setdefault("PREVIEW_ALLOW_NONLOCAL_DB", dev.get("PREVIEW_ALLOW_NONLOCAL_DB", "0"))
    os.environ.setdefault(
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB",
        dev.get("PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "0"),
    )
    os.environ.setdefault("PREVIEW_ENV", "dev")

    model = _read_env_file(model_credentials)
    for key, value in model.items():
        if key.startswith(MODEL_ENV_PREFIX):
            os.environ.setdefault(key, value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-id", type=int, default=1557474)
    parser.add_argument(
        "--workflow",
        default="section_form",
        choices=("section_form", "section_players"),
        help="실행할 섹션 워크플로우. 기본은 경기력(R1), 주목 선수는 section_players(R4)",
    )
    parser.add_argument(
        "--one-send",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="논리 호출당 시도 상한을 1로 고정한다(기본). 429·오류여도 두 번째 전송 없음",
    )
    parser.add_argument("--model-credentials", type=Path, default=DEFAULT_MODEL_CREDENTIALS)
    parser.add_argument("--dev-credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--actor-id", type=int, default=0, help="관리자 계정 ID(감사 기록)")
    args = parser.parse_args(argv)

    _load_environment(args.model_credentials, args.dev_credentials)

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    print(f"model: {settings.model_name} | location: {settings.model_location}")
    print(f"live_enabled: {settings.model_live_enabled}")
    print(f"fixtures_reader: {'set' if settings.fixtures_database_url else 'missing'}")

    if not settings.model_live_enabled or not settings.model_name:
        print("live: skipped (모델 설정이 없어 실행하지 않았습니다)")
        return 1

    from app.db import get_session_factory
    from app.preview import provider, runner, sections, store
    from app.preview.contracts import Environment, RunMode
    from app.preview.sources.fixtures import StoredFixtureReader

    reader = (
        StoredFixtureReader.from_url(settings.fixtures_database_url)
        if settings.fixtures_database_url
        else None
    )
    stored = reader.get_fixture(fixture_id=args.fixture_id) if reader is not None else None
    if stored is None:
        print(f"stored fixture {args.fixture_id} not found (읽기 권한 또는 저장 여부 확인)")
        return 1
    fixture = stored.identity().to_dict()
    print(f"fixture: {stored.label} | kickoff {stored.kickoff_at.isoformat()}")

    if args.dry_run:
        print("live: dry-run (호출하지 않았습니다)")
        return 0

    transport = provider.GoogleGenAIHttpTransport(
        project=settings.model_project,
        location=settings.model_location,
        model=settings.model_name,
        credentials_json=settings.model_credentials_json,
        mode=RunMode.LIVE,
    )
    implementations = sections.build_implementations(
        args.workflow, transport=transport, reader=reader
    )

    # 예산은 실제 회계를 유지한다. `--one-send`는 시도 상한과 요청 상한을 1로 낮춘다
    # (429·오류에도 두 번째 전송을 만들지 않는다). 대체 모델·프롬프트 수리 루프는 없다.
    # `normal_model_calls`도 함께 1로 두어야 한다. 이 값은 "아직 시작하지 않은 필수
    # 단계의 몫"을 예약하는데, 5로 남겨 두면 총 상한 1과 모순되어 첫 시도가 전송 전에
    # 거부된다(예약 > 상한).
    from app.preview.retry import plan_limits

    limits = plan_limits(
        attempts_per_call=1 if args.one_send else 3,
        model_requests=1 if args.one_send else 8,
        normal_model_calls=1,
    )
    print(
        "send cap:"
        f" attempts_per_call={limits.attempts_per_call}"
        f" model_requests={limits.model_requests}"
    )

    factory = get_session_factory()
    with factory() as session:
        started = datetime.now(timezone.utc)
        result = runner.run_section_workflow(
            session,
            workflow_id=args.workflow,
            implementations=implementations,
            actor_id=args.actor_id,
            environment=Environment.DEV,
            fixture=fixture,
            fixture_label=stored.label,
            transport=transport,
            label=(
                f"{args.workflow} 실제 실행 (사용자 생성물 확인용)"
            ),
            limits=limits,
        )
        session.commit()

        detail = store.get_run_detail(session, result.run_id)
        section_row = detail.section_results[0] if detail.section_results else None
        summary = {
            "run_id": str(result.run_id),
            "workflow_id": result.workflow_id,
            "workflow_version": result.workflow_version,
            "mode": result.mode.value,
            "status": result.status.value,
            "quality": result.quality.value,
            "external_calls": result.external_calls,
            "attempt_count": len(detail.attempts),
            "model_used": detail.attempts[0]["model"] if detail.attempts else None,
            "fixture": stored.label,
            "fixture_id": args.fixture_id,
            "started_at": started.isoformat(),
            "budget": dict(result.budget),
            "unavailable_reason": result.unavailable_reason,
            "section_result_id": str(result.section_result_id) if result.section_result_id else None,
            "body": section_row["body"] if section_row else result.body,
            "sources": section_row["sources"] if section_row else [dict(s) for s in result.sources],
            "diagnostics": list(result.diagnostics),
            "step_log": [dict(step) for step in result.step_log],
        }

    print("\n=== 실행 요약 ===")
    for key in (
        "run_id",
        "workflow_id",
        "workflow_version",
        "mode",
        "status",
        "quality",
        "external_calls",
        "attempt_count",
        "model_used",
        "section_result_id",
    ):
        print(f"{key}: {summary[key]}")
    print(f"attempts: {summary['attempt_count']} | budget: {json.dumps(summary['budget'], ensure_ascii=False)}")

    print("\n=== 본문 ===")
    print(summary["body"] or "(본문 없음)")
    print("\n=== 근거 ===")
    for source in summary["sources"]:
        print(f"- {source.get('label')} | {source.get('url') or '(URL 없음)'} | {source.get('kind')}")
    if summary["diagnostics"]:
        print("\n=== 관리자 진단 ===")
        for line in summary["diagnostics"]:
            print(f"- {line}")
    if summary["unavailable_reason"]:
        print(f"\nunavailable_reason: {summary['unavailable_reason']}")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nsummary written: {args.json_out}")

    return 0 if summary["body"] else 2


if __name__ == "__main__":
    sys.exit(main())
