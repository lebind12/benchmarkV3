"""R1 인용 실험 **1회** — response_mime_type 제거가 인용 반환을 바꾸는가.

이 스크립트가 확인하는 것:

- 기준 실행(`6e59041a-…`)의 **저장된 원문 요청**에서 프롬프트와 생성 설정을 그대로 읽는다.
- `generation_config`에서 `response_mime_type` **하나만** 뺀 후보 설정을 만든다.
- 같은 모델·같은 경기·같은 저장 D0 자료로 **한 번** 전송하고, 검증·본문 조립은 현재
  코드를 그대로 쓴다.
- 결과를 새 실행으로 `preview_dev`에 남기고 기준 실행과 비교한다.

스스로 지키는 경계:

- 실제 전송은 **최대 1회**. `SendCappedTransport`가 두 번째 전송을 예외로 막는다.
- 재시도 없음(`attempts_per_call=1`). 429·타임아웃·잘못된 JSON이어도 다시 보내지 않고,
  출력을 다른 호출로 고치지 않는다.
- API-Football 0회. 저장 자료만 읽는다.
- 제품 기본값은 바꾸지 않는다. 기본 경로는 `application/json`을 그대로 쓴다.
- 승인 행을 만들지 않는다.

    .venv/bin/python scripts/preview_grounding_one_call.py \
        --baseline-run-id 6e59041a-3767-4756-a412-991008873f50 --dry-run

    .venv/bin/python scripts/preview_grounding_one_call.py \
        --baseline-run-id 6e59041a-3767-4756-a412-991008873f50 --json-out <path>
"""

from __future__ import annotations

import argparse
import hashlib
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

# 이 실험이 바꾸는 단 하나의 축.
REMOVED_SETTING = "response_mime_type"
# 후보 구현 버전. 생성 설정이 다르므로 기본 `mp05-form-1`과 다른 값을 기록한다.
CANDIDATE_IMPLEMENTATION_VERSION = "mp05-form-1-nomime-1"


class SecondSendForbidden(RuntimeError):
    """이 실험은 전송 1회만 허용한다. 두 번째 전송 시도는 상한 위반이다."""


class SendCappedTransport:
    """실제 transport를 감싸 전송 횟수 상한을 강제한다.

    기록·예산·재시도 판단은 안쪽 transport와 공통 경로가 그대로 담당한다.
    """

    def __init__(self, inner, *, max_sends: int = 1) -> None:
        self._inner = inner
        self._max_sends = max_sends
        self.send_count = 0
        self.provider = getattr(inner, "provider", "vertex")
        self.mode = getattr(inner, "mode", None)
        self.request_class = getattr(inner, "request_class", None)
        self.model = getattr(inner, "model", None)

    def configuration_problem(self) -> str | None:
        checker = getattr(self._inner, "configuration_problem", None)
        return checker() if callable(checker) else None

    def send(self, spec, *, timeout_seconds: int, context):
        if self.send_count >= self._max_sends:
            raise SecondSendForbidden(
                f"전송 상한({self._max_sends}회)을 넘는 두 번째 전송 시도가 있었습니다."
                " 요청을 보내지 않고 중단했습니다."
            )
        self.send_count += 1
        return self._inner.send(spec, timeout_seconds=timeout_seconds, context=context)


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
    """기존 도구와 같은 이름 매핑만 한다. 값은 출력하지 않는다."""
    dev = _read_env_file(dev_credentials)
    os.environ.setdefault("PREVIEW_DATABASE_URL", dev.get("PREVIEW_DEV_DATABASE_URL", ""))
    os.environ.setdefault(
        "PREVIEW_IDENTITY_DATABASE_URL", dev.get("PREVIEW_IDENTITY_DATABASE_URL", "")
    )
    os.environ.setdefault(
        "PREVIEW_FIXTURES_DATABASE_URL", dev.get("PREVIEW_FIXTURES_DATABASE_URL", "")
    )
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


def _read_baseline_request(session, baseline_run_id: uuid.UUID) -> dict:
    """기준 실행의 저장된 R1 요청 원문을 그대로 읽는다. 새로 렌더하지 않는다."""
    from sqlalchemy import text

    row = session.execute(
        text(
            "select a.request_artifact_id, art.body "
            "from preview_dev.preview_attempts a "
            "join preview_dev.preview_artifacts art on art.id = a.request_artifact_id "
            "where a.run_id = :run and a.module_id = 'R1' "
            "order by a.attempt_ordinal limit 1"
        ),
        {"run": str(baseline_run_id)},
    ).first()
    if row is None or not row[1]:
        raise SystemExit("기준 실행의 R1 요청 원문을 찾지 못했습니다. 실험을 중단합니다.")
    return {"artifact_id": str(row[0]), "payload": json.loads(row[1])}


def _prompt_of(payload: dict) -> str:
    contents = payload.get("contents") or []
    parts = (contents[0] or {}).get("parts") or []
    return str((parts[0] or {}).get("text") or "")


def _read_baseline_d0(baseline_run_id: uuid.UUID) -> dict:
    """기준 실행의 D0 payload를 그대로 읽는다(읽기 전용)."""
    from sqlalchemy import text

    from app.db import get_session_factory

    with get_session_factory()() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        row = session.execute(
            text(
                "select payload from preview_dev.preview_results "
                "where run_id = :run and module_id = 'D0'"
            ),
            {"run": str(baseline_run_id)},
        ).scalar_one()
    if isinstance(row, dict) and isinstance(row.get("payload"), dict):
        row = row["payload"]
    return dict(row)


def _facts_from_baseline(baseline_run_id: uuid.UUID):
    """기준 실행의 D0 사실로 R1 입력을 복원한다(읽기 전용, 쓰기 없음).

    드라이런에서 "현재 코드가 같은 프롬프트를 렌더하는가"만 확인할 때 쓴다.
    """
    from sqlalchemy import text

    from app.db import get_session_factory
    from app.preview.modules import form

    with get_session_factory()() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        row = session.execute(
            text(
                "select payload from preview_dev.preview_results "
                "where run_id = :run and module_id = 'D0'"
            ),
            {"run": str(baseline_run_id)},
        ).scalar_one()
    if isinstance(row, dict) and isinstance(row.get("payload"), dict):
        row = row["payload"]
    fixture = row["fixture"]
    return _form_facts(fixture, row.get("facts") or [])


def _form_facts(fixture: dict, facts: list):
    from app.preview.modules import form

    return form.FormFacts(
        fixture_id=fixture["fixture_id"],
        league_id=fixture["league_id"],
        season=fixture["season"],
        home_team_id=fixture["home_team_id"],
        away_team_id=fixture["away_team_id"],
        kickoff_at=datetime.fromisoformat(fixture["kickoff_at"]),
        home_team=fixture["home_team"],
        away_team=fixture["away_team"],
        league=fixture.get("league"),
        facts=tuple(
            form.Fact(
                fact_id=str(item["fact_id"]),
                text=str(item.get("text") or ""),
                snapshot_id=str(item.get("snapshot_id") or ""),
                collected_at=(
                    datetime.fromisoformat(str(item["collected_at"]).replace("Z", "+00:00"))
                    if item.get("collected_at")
                    else None
                ),
                subject_team_id=item.get("subject_team_id"),
            )
            for item in facts
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fixture-id", type=int, default=1557474)
    parser.add_argument("--baseline-run-id", type=str, required=True)
    parser.add_argument("--model-credentials", type=Path, default=DEFAULT_MODEL_CREDENTIALS)
    parser.add_argument("--dev-credentials", type=Path, default=DEFAULT_CREDENTIALS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--actor-id", type=int, default=0)
    args = parser.parse_args(argv)

    _load_environment(args.model_credentials, args.dev_credentials)

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    print(f"model: {settings.model_name} | location: {settings.model_location}")
    print(f"live_enabled: {settings.model_live_enabled}")

    from app.db import get_session_factory
    from app.preview import provider, runner, sections
    from app.preview.contracts import Environment, RunMode
    from app.preview.modules import form
    from app.preview.retry import plan_limits
    from app.preview.sources.fixtures import StoredFixtureReader

    baseline_run_id = uuid.UUID(args.baseline_run_id)
    factory = get_session_factory()

    with factory() as session:
        baseline = _read_baseline_request(session, baseline_run_id)
    baseline_payload = baseline["payload"]
    baseline_generation = dict(baseline_payload.get("generation_config") or {})
    baseline_prompt = _prompt_of(baseline_payload)
    candidate_generation = {k: v for k, v in baseline_generation.items() if k != REMOVED_SETTING}

    print()
    print("=== 요청 차이(전송 전) ===")
    print("baseline generation :", json.dumps(baseline_generation, sort_keys=True, ensure_ascii=False))
    print("candidate generation:", json.dumps(candidate_generation, sort_keys=True, ensure_ascii=False))
    symmetric_diff = set(baseline_generation) ^ set(candidate_generation)
    print("차이 키:", sorted(symmetric_diff))
    if symmetric_diff != {REMOVED_SETTING}:
        print(f"거부: 이 실험은 {REMOVED_SETTING} 하나만 바꿔야 합니다.")
        return 3
    if any(baseline_generation[k] != candidate_generation[k] for k in candidate_generation):
        print("거부: 남은 설정 값이 기준과 다릅니다.")
        return 3
    print(f"프롬프트 글자수: {len(baseline_prompt)} | sha256: "
          f"{hashlib.sha256(baseline_prompt.encode()).hexdigest()[:16]}")
    print(f"모델: {baseline_payload.get('model')} | 리전: {baseline_payload.get('location')}")

    reader = (
        StoredFixtureReader.from_url(settings.fixtures_database_url)
        if settings.fixtures_database_url
        else None
    )
    stored = reader.get_fixture(fixture_id=args.fixture_id) if reader is not None else None
    if stored is None:
        print(f"stored fixture {args.fixture_id} not found")
        return 1
    fixture = stored.identity().to_dict()
    print(f"fixture: {stored.label} | kickoff {stored.kickoff_at.isoformat()}")

    # 입력 동등성: 현재 코드가 지금 렌더한 프롬프트가 기준 원문과 같은지 먼저 확인한다.
    # (전송 전 검사이며, 다르면 아래 research 노드가 전송하지 않고 중단한다.)
    if args.dry_run:
        # 드라이런은 DB에 아무것도 쓰지 않는다. 기준 실행의 D0 사실로만 비교한다.
        facts = _facts_from_baseline(baseline_run_id)
        rendered = form.build_contents(facts, now=datetime.now(timezone.utc))[0]["parts"][0]["text"]
        print("프롬프트 동등성(현재 코드 렌더 vs 기준 원문):", rendered == baseline_prompt)
        print("전송 예정: 1회 | 재시도 0 | API 0 | 실제 전송: 0회(드라이런)")
        return 0 if rendered == baseline_prompt else 3

    real_transport = provider.GoogleGenAIHttpTransport(
        project=settings.model_project,
        location=settings.model_location,
        model=settings.model_name,
        credentials_json=settings.model_credentials_json,
        mode=RunMode.LIVE,
    )
    transport = SendCappedTransport(real_transport, max_sends=1)

    # 입력 동등성: 이번 실험은 **기준 실행의 D0 산출을 그대로** 쓴다.
    # 새로 읽으면 스냅샷 ID·수집 시각이 달라져 프롬프트가 기준 원문과 달라진다
    # (수집 시각이 프롬프트 본문에 들어간다). 그래서 D0은 재수집하지 않고 재생한다.
    baseline_d0 = _read_baseline_d0(baseline_run_id)

    def prepare_replay(ctx, state):
        from app.preview.runner import NodeOutcome

        return NodeOutcome(payload=dict(baseline_d0), external_calls=0)

    prepare = runner.NodeImplementation(
        module_id=sections.DATA_MODULE_ID,
        implementation_version="mp05-stored-d0-1",
        prompt_version=None,
        mode=RunMode.LIVE,
        run=prepare_replay,
    )

    def research_run(ctx, state):
        from app.preview.sections import _facts_from_state

        facts = _facts_from_state(state)
        rendered = form.build_contents(facts, now=datetime.now(timezone.utc))[0]["parts"][0]["text"]
        if rendered != baseline_prompt:
            raise SystemExit(
                "현재 코드 렌더 프롬프트가 기준 원문과 다릅니다. 입력 동등성이 깨져 전송하지 않습니다."
            )
        # 기준 원문 텍스트를 그대로 쓰고, 생성 설정만 후보(마임 타입 제거)로 바꾼다.
        return form.form_node(
            facts=facts,
            transport=transport,
            generation_config_override=candidate_generation,
        )(ctx, state)

    implementations = runner.WorkflowImplementations(
        prepare_data=prepare,
        research=(
            runner.NodeImplementation(
                module_id="R1",
                implementation_version=CANDIDATE_IMPLEMENTATION_VERSION,
                prompt_version=form.FORM_PROMPT_VERSION,
                mode=RunMode.LIVE,
                run=research_run,
            ),
        ),
        compose_body=runner.NodeImplementation(
            module_id=sections.COMPOSE_MODULE_ID,
            implementation_version="mp05-compose-1",
            prompt_version=None,
            mode=RunMode.LIVE,
            run=sections._compose_node(now=None),
        ),
    )

    limits = plan_limits(
        model_requests=1, api_requests=0, attempts_per_call=1, normal_model_calls=1
    )
    print()
    print("전송 예정: 1회 (재시도 0, API 0)")

    with factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=implementations,
            actor_id=args.actor_id,
            environment=Environment.DEV,
            fixture=fixture,
            fixture_label=stored.label,
            transport=transport,
            label="MP05 인용 실험: response_mime_type 제거 1회",
            limits=limits,
            configuration_version="mp05-grounding-one-call-1",
        )
        session.commit()
        run_id = str(result.run_id)

    summary = {
        "experiment": "response_mime_type 제거 1회",
        "baseline_run_id": str(baseline_run_id),
        "baseline_request_artifact_id": baseline["artifact_id"],
        "candidate_run_id": run_id,
        "candidate_implementation_version": CANDIDATE_IMPLEMENTATION_VERSION,
        "model": baseline_payload.get("model"),
        "location": baseline_payload.get("location"),
        "fixture_id": args.fixture_id,
        "fixture": stored.label,
        "baseline_generation": baseline_generation,
        "candidate_generation": candidate_generation,
        "setting_removed": REMOVED_SETTING,
        "prompt_sha256": hashlib.sha256(baseline_prompt.encode()).hexdigest(),
        "prompt_chars": len(baseline_prompt),
        "actual_sends": transport.send_count,
        "send_cap": transport._max_sends,
        "attempts_per_call_limit": 1,
        "workflow_version": result.workflow_version,
        "status": result.status.value,
        "quality": result.quality.value,
        "external_calls": result.external_calls,
        "section_result_id": str(result.section_result_id) if result.section_result_id else None,
        "body": result.body,
        "sources": [dict(s) for s in result.sources],
        "diagnostics": list(result.diagnostics),
        "unavailable_reason": result.unavailable_reason,
        "step_log": [dict(step) for step in result.step_log],
    }

    print("\n=== 결과 ===")
    for key in ("candidate_run_id", "status", "quality", "external_calls", "actual_sends",
                "workflow_version", "section_result_id"):
        print(f"{key}: {summary[key]}")
    print(f"unavailable_reason: {summary['unavailable_reason']}")
    print("\n=== 본문 ===")
    print(summary["body"] or "(본문 없음)")

    if args.json_out:
        args.json_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"summary written: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
