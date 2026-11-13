"""실제 개발 영역(preview_dev)에 작업 소유 모의 실행을 만든다 (MP-02).

용도는 하나다. 사용자가 이미 로그인한 관리자 세션에서 검사 화면을 직접 열어볼 수
있게, 실제 개발 DB의 `preview_dev` 스키마에 **명확히 표시된 작업 소유 mock 실행**을
남긴다.

경계:

- 쓰기 대상은 `preview_dev` 스키마뿐이다. 기존 `public` 영역(경기·계정)은 읽지도
  쓰지도 않는다. 개발 연결 역할은 그 권한이 없다.
- 만드는 실행은 `mode=mock`, `operation_kind=mock_demo`, 라벨에 작업 소유 표시가
  붙는다. 외부 모델·API 호출은 0회다.
- 취소는 이 스크립트가 만든 실행에만 한다(실행 ID를 출력해 두고 되돌린다).
- 운영 배포·환경 변수 변경은 하지 않는다.

    .venv/bin/python scripts/preview_dev_mock_runs.py create
    .venv/bin/python scripts/preview_dev_mock_runs.py list
    .venv/bin/python scripts/preview_dev_mock_runs.py cancel --run-id <uuid>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
# 이 작업(MP-02)이 만든 실행임을 알아보기 위한 라벨 접두사. 취소 대상 판별에도 쓴다.
TASK_LABEL_PREFIX = "MP-02 검증 실행 (작업 소유, mock)"
TASK_ACTOR_ID = 0  # 사람 계정이 아닌 작업 실행을 뜻하는 값. 감사 기록에 그대로 남는다.


def _load_env(path: Path) -> None:
    import os

    if not path.exists():
        raise SystemExit(f"missing credentials file: {path}")
    mode = oct(path.stat().st_mode)[-3:]
    if mode != "600":
        raise SystemExit(f"refusing credentials file with mode {mode} (expected 600)")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PREVIEW_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    dev = values.get("PREVIEW_DEV_DATABASE_URL")
    identity = values.get("PREVIEW_IDENTITY_DATABASE_URL")
    if not dev:
        raise SystemExit("PREVIEW_DEV_DATABASE_URL is not in the credentials file")
    os.environ["PREVIEW_DATABASE_URL"] = dev
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = identity or dev
    os.environ["PREVIEW_ALLOW_NONLOCAL_DB"] = values.get("PREVIEW_ALLOW_NONLOCAL_DB", "0")
    os.environ["PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB"] = values.get(
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "0"
    )
    os.environ.setdefault("PREVIEW_ENV", "dev")


def _session():
    from app.preview.config import get_settings
    from app.preview.db import get_session_factory, reset_engine

    reset_engine()
    get_settings.cache_clear()
    return get_session_factory()()


def cmd_create(args) -> int:
    from app.preview import demo_pipeline
    from app.preview.models import PreviewRun

    session = _session()
    try:
        result = demo_pipeline.create_recorded_mock_run(session, actor_id=TASK_ACTOR_ID)
        run = session.get(PreviewRun, result.run_id)
        run.label = f"{TASK_LABEL_PREFIX} · {args.tag}"
        session.commit()
    finally:
        session.close()

    print(f"run_id: {result.run_id}")
    print(f"module_execution_id: {result.module_execution_id}")
    print(f"label: {TASK_LABEL_PREFIX} · {args.tag}")
    print("mode: mock (외부 모델·API 호출 0회)")
    print(f"inspect: http://127.0.0.1:5173/admin/runs → 실행 {str(result.run_id)[:8]} 검사")
    return 0


def cmd_list(args) -> int:
    from sqlalchemy import select

    from app.preview.models import PreviewRun

    session = _session()
    try:
        rows = list(
            session.scalars(select(PreviewRun).order_by(PreviewRun.requested_at.desc()))
        )
        if not rows:
            print("no runs in preview_dev")
        for row in rows:
            print(
                f"{row.id}  {row.mode:>6}  {row.status:>10}  "
                f"{row.cancelled_at and 'cancelled' or 'active':>9}  {row.label}"
            )
    finally:
        session.close()
    return 0


def cmd_cancel(args) -> int:
    import uuid as uuid_module

    from app.preview import store
    from app.preview.models import PreviewRun

    session = _session()
    try:
        run_id = uuid_module.UUID(args.run_id)
        run = session.get(PreviewRun, run_id)
        if run is None:
            print(f"run {run_id} not found")
            return 1
        if not (run.label or "").startswith(TASK_LABEL_PREFIX):
            print("refusing: this run was not created by the MP-02 task script")
            return 2
        result = store.cancel_run(
            session, run_id, actor_id=TASK_ACTOR_ID, reason="MP-02 검증 실행 정리"
        )
        session.commit()
    finally:
        session.close()

    print(f"cancelled: {result['run_id']}")
    for table, count in result["removed"].items():
        print(f"  removed {table}: {count}")
    print(f"  kept: {', '.join(result['kept'])}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials-file", default=str(CREDENTIALS))
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="작업 소유 mock 실행 만들기")
    create.add_argument("--tag", default="inspect", help="라벨에 붙일 짧은 식별자")
    create.set_defaults(func=cmd_create)

    listing = sub.add_parser("list", help="preview_dev 실행 목록 보기")
    listing.set_defaults(func=cmd_list)

    cancel = sub.add_parser("cancel", help="작업 소유 mock 실행 취소")
    cancel.add_argument("--run-id", required=True)
    cancel.set_defaults(func=cmd_cancel)

    args = parser.parse_args(argv)
    _load_env(Path(args.credentials_file))
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
