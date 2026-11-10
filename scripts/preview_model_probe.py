"""Vertex 모델 전송 연결 확인 — 아주 작은 호출 **한 번**만.

이 스크립트가 하는 일은 하나다. 실제 앱의 공통 실행 경로(`execute_request` /
`request_model`)로 아주 작은 모델 요청을 **한 번** 보내, 설정된 제공자·모델·자격
증명으로 모델 전송이 실제로 성립하는지 확인한다.

이것이 확인하는 것과 아닌 것:

- 확인: `PREVIEW_MODEL_*` 설정으로 Vertex 호출이 실제로 성립하는가(연결성).
- 아님: 조사 품질, 섹션 본문의 정확성, 사용자 승인 근거. 이 호출은 모델에게 한
  단어만 되돌려 달라고 요청하며 그 응답을 제품 결과로 쓰지 않는다.

경계:

- 시도는 **최대 1회**다. 401/403/404 같은 인증·모델 오류는 재시도하지 않는다.
  같은 이유로 이 스크립트를 반복 실행해 재시도 루프를 만들지 않는다.
- 쓰기는 `preview_dev`의 실행 1건·시도 1건·원문 2건뿐이다. 기존 행은 고치지 않는다.
- 자격 증명 값은 출력·기록하지 않는다. 원문 아티팩트는 `app/preview/artifacts.py`의
  가림(redaction) 경로를 그대로 지난다. 이 스크립트는 응답 요약(상태·사용량·시간)만
  표준출력으로 낸다.
- 모델 이름은 설정에서만 읽는다. 대체 모델을 고르지 않는다.

    .venv/bin/python scripts/preview_model_probe.py --dry-run
    .venv/bin/python scripts/preview_model_probe.py
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

DEFAULT_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
DEFAULT_MODEL_CREDENTIALS = Path.home() / ".config" / "match-preview" / "model-live.env"

PROBE_CALL_ID = "integration-finish-transport-probe"
PROBE_PROMPT = "Reply with the single word: pong"

# 이 경로를 통과하지 않는 값은 환경에 넣지 않는다.
MODEL_ENV_PREFIX = "PREVIEW_MODEL_"


def _unquote(value: str) -> str:
    """env 파일의 인용 부호를 벗긴다. dotenv가 읽는 것과 같은 결과를 만든다."""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _read_env_file(path: Path) -> dict[str, str]:
    """0600 파일에서 `KEY=VALUE`만 읽는다. 값은 출력하지 않는다."""
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
    os.environ.setdefault("PREVIEW_IDENTITY_DATABASE_URL", dev.get("PREVIEW_IDENTITY_DATABASE_URL", ""))
    os.environ.setdefault("PREVIEW_ALLOW_NONLOCAL_DB", dev.get("PREVIEW_ALLOW_NONLOCAL_DB", "0"))
    os.environ.setdefault(
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", dev.get("PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "0")
    )
    os.environ.setdefault("PREVIEW_ENV", "dev")

    model = _read_env_file(model_credentials)
    for key, value in model.items():
        if key.startswith(MODEL_ENV_PREFIX):
            os.environ.setdefault(key, value)


def _build_transport(settings):  # noqa: ANN001 - 설정 객체
    from app.preview.provider import GoogleGenAIHttpTransport
    from app.preview.contracts import RunMode

    return GoogleGenAIHttpTransport(
        project=settings.model_project,
        location=settings.model_location,
        model=settings.model_name,
        credentials_json=settings.model_credentials_json,
        mode=RunMode.LIVE,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--model-credentials",
        type=Path,
        default=DEFAULT_MODEL_CREDENTIALS,
        help="Vertex 설정을 담은 0600 파일(저장소 밖)",
    )
    parser.add_argument(
        "--dev-credentials",
        type=Path,
        default=DEFAULT_CREDENTIALS,
        help="preview_dev 쓰기 연결을 담은 0600 파일(저장소 밖)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="설정 확인만 하고 호출하지 않는다",
    )
    args = parser.parse_args(argv)

    _load_environment(args.model_credentials, args.dev_credentials)

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    transport = _build_transport(settings)
    from app.preview.provider import model_configuration_status

    status = model_configuration_status(transport)
    print(f"provider: {status['provider']}")
    print(f"mode: {status['mode']}")
    print(f"configured: {status['configured']}")
    if status["problem"]:
        print(f"configuration_problem: {status['problem']}")
    print(f"model: {settings.model_name}")
    print(f"location: {settings.model_location}")
    print(f"live_enabled: {settings.model_live_enabled}")

    if not status["configured"]:
        print("probe: skipped (설정이 없어 호출하지 않았습니다)")
        return 1
    if not settings.model_live_enabled:
        print("probe: skipped (PREVIEW_MODEL_LIVE_ENABLED가 꺼져 있습니다)")
        return 1
    if args.dry_run:
        print("probe: dry-run (호출하지 않았습니다)")
        return 0

    from app.db import get_session_factory
    from app.preview import store
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        ExecutionLimits,
        OperationKind,
        QualityStatus,
        RunMode,
        RunStatus,
    )
    from app.preview.provider import request_model
    from app.preview.retry import BudgetLimits, RunBudget

    # 시도 상한을 1로 고정한다. 재시도 루프를 만들지 않는다. 정상 호출 수도 1로
    # 두어야 '아직 시작하지 않은 단계 몫' 예약이 이 한 번을 막지 않는다.
    limits = BudgetLimits(model_requests=1, attempts_per_call=1, normal_model_calls=1)
    budget = RunBudget.for_run(limits)
    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=0,
        config_version="integration-finish-transport-probe",
        limits=limits.execution_limits(),
    )

    factory = get_session_factory()
    with factory() as session:
        store.store_run(
            session,
            context,
            label="integration-finish: Vertex 전송 연결 확인 (1회)",
            quality=QualityStatus.PENDING,
            status=RunStatus.RUNNING,
        )
        result = request_model(
            logical_call_id=PROBE_CALL_ID,
            contents=[{"role": "user", "parts": [{"text": PROBE_PROMPT}]}],
            context=context,
            transport=transport,
            budget=budget,
            session=session,
            module_id="TRANSPORT_PROBE",
            operation="transport_probe",
        )
        response = result.response
        ok = result.ok
        store.finish_run(
            session,
            context.run_id,
            status=RunStatus.SUCCEEDED if ok else RunStatus.FAILED,
            quality=QualityStatus.READY if ok else QualityStatus.INSUFFICIENT,
        )
        session.commit()

        print(f"run_id: {context.run_id}")
        print(f"attempts: {result.attempt_count} (상한 1)")
        print(f"outcome: {response.outcome.value}")
        print(f"http_status: {response.http_status}")
        print(f"duration_ms: {response.duration_ms}")
        usage = response.usage
        if usage is None:
            print("usage: 미확인(제공자가 사용량을 주지 않았습니다)")
        else:
            print(
                "usage: input_tokens="
                f"{usage.input_tokens} output_tokens={usage.output_tokens}"
            )
        if result.text:
            text = result.text.strip().replace("\n", " ")
            print(f"reply_chars: {len(text)}")
            print(f"reply_preview: {text[:40]}")
        if response.error_class:
            print(f"error_class: {response.error_class}")
        if response.error_message:
            print(f"error_message: {response.error_message[:200]}")
        if response.raw_artifact_id:
            print(f"raw_response_artifact: {response.raw_artifact_id}")
        print(f"finished_at: {datetime.now(timezone.utc).isoformat()}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
