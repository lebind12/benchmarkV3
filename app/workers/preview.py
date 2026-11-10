"""섹션 워크플로우 로컬 실행 진입점 (애플리케이션 연결 계층).

이 파일은 **애플리케이션 연결 계층**이다. 범용 실행 엔진이나 분산 스케줄러가 아니다.
하는 일은 세 가지뿐이다.

1. 섹션 워크플로우 하나를 골라 실행하고, 그 실행 ID를 출력한다.
2. 저장된 실행을 다시 읽어 본문·근거·시도 수를 사람이 읽을 수 있게 보여준다.
3. 실패하면 0이 아닌 종료 코드로 끝난다(성공처럼 보이게 하지 않는다).

경계:

- 기본은 명시적 모의 시연이다. 실제 조사·생성 구현은 MP-05 이후에 등록되며, 그때도
  이 진입점은 같은 `runner.run_section_workflow`를 부른다.
- 쓰기는 `preview_dev` 스키마뿐이다. 기존 `public` 영역은 읽기만 한다.
- 재시작 후에도 같은 실행을 다시 열 수 있는 것은 저장 행 덕분이지, 이 스크립트가
  상태를 들고 있기 때문이 아니다.
- 운영 배포·스케줄러·자동 재개는 이 파일의 범위가 아니다.

    PREVIEW_CREDENTIALS_FILE=~/.config/match-preview/preview-dev.env \
        .venv/bin/python -m app.workers.preview list-sections
    .venv/bin/python -m app.workers.preview run --workflow section_form
    .venv/bin/python -m app.workers.preview show --run-id <uuid>
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app.core.config import get_settings
from app.db import get_session_factory
from app.preview import runner, store
from app.preview.registry import get_section_workflow, section_workflow_ids

DEFAULT_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"


def _load_credentials(path: Path) -> None:
    """저장소 밖 0600 파일에서 연결 정보를 읽는다. 값을 출력하지 않는다."""
    if not path.exists():
        raise SystemExit(f"missing credentials file: {path}")
    mode = oct(path.stat().st_mode)[-3:]
    if mode != "600":
        raise SystemExit(f"refusing credentials file with mode {mode} (expected 600)")
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PREVIEW_") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)
    if os.environ.get("PREVIEW_DEV_DATABASE_URL"):
        os.environ.setdefault(
            "PREVIEW_DATABASE_URL", os.environ["PREVIEW_DEV_DATABASE_URL"]
        )
    get_settings.cache_clear()


def _implementations(workflow_id: str) -> runner.WorkflowImplementations:
    """지금 실행 가능한 구현. 실제 조사 구현은 MP-05 이후에 등록된다."""
    return runner.mock_section_implementations(workflow_id)


def _cmd_list_sections(_: argparse.Namespace) -> int:
    built = {workflow_id: _implementations(workflow_id) for workflow_id in section_workflow_ids()}
    for workflow_id in section_workflow_ids():
        registration = get_section_workflow(workflow_id)
        availability = runner.section_run_availability(workflow_id, built)
        modes = ",".join(availability["modes"]) or "-"
        state = "실행 가능" if availability["implemented"] else "미구현"
        print(f"{workflow_id:24s} {state:8s} modes={modes}")
        print(f"  구성: {' + '.join(registration.module_ids)}")
        if availability["note"]:
            print(f"  안내: {availability['note']}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    try:
        get_section_workflow(args.workflow)
    except KeyError:
        print(f"unknown section workflow: {args.workflow}", file=sys.stderr)
        return 2
    if args.mode != "mock":
        print(
            "실제 조사·생성 구현이 아직 등록되지 않아 mock 실행만 열려 있습니다.",
            file=sys.stderr,
        )
        return 2

    factory = get_session_factory()
    with factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id=args.workflow,
            implementations=_implementations(args.workflow),
            actor_id=args.actor_id,
            fixture_label=args.fixture_label,
        )
        session.commit()

    print(f"run_id: {result.run_id}")
    print(f"workflow: {result.workflow_id} ({result.workflow_version})")
    print(f"mode: {result.mode.value} / status: {result.status.value} / quality: {result.quality.value}")
    print(f"section_result_id: {result.section_result_id} v{result.section_result_version}")
    print(f"external_calls: {result.external_calls}")
    if result.unavailable_reason:
        print(f"본문 없음: {result.unavailable_reason}")
        return 1
    print()
    print(result.body)
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    import uuid

    factory = get_session_factory()
    with factory() as session:
        try:
            detail = store.get_run_detail(session, uuid.UUID(args.run_id))
        except (store.RunNotFound, ValueError):
            print(f"run not found: {args.run_id}", file=sys.stderr)
            return 2

        summary = detail.summary
        print(f"run: {summary.run_id}")
        print(
            f"mode: {summary.mode.value} / env: {summary.environment.value}"
            f" / status: {summary.status.value} / quality: {summary.quality.value}"
        )
        print(f"modules: {summary.module_count} / attempts: {summary.attempt_count}")
        for row in detail.section_results:
            print()
            print(f"[{row['workflow_id']}] {row['title']} (v{row['version']}, {row['mode']})")
            if row["unavailable"]:
                print(f"  본문 없음: {row['unavailable_reason']}")
                continue
            print(row["body"])
            for source in row["sources"]:
                print(f"  근거: {source.get('label')} {source.get('url') or ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="섹션 워크플로우 로컬 실행 진입점")
    parser.add_argument(
        "--credentials-file",
        default=os.environ.get("PREVIEW_CREDENTIALS_FILE", str(DEFAULT_CREDENTIALS)),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-sections", help="섹션별 실행 가능성 확인").set_defaults(
        func=_cmd_list_sections
    )

    run = sub.add_parser("run", help="섹션 워크플로우 하나 실행")
    run.add_argument("--workflow", required=True, help="섹션 워크플로우 ID")
    run.add_argument("--mode", default="mock", help="실행 방식 (현재 mock만 열려 있음)")
    run.add_argument("--actor-id", type=int, default=0, help="실행 소유 계정 ID")
    run.add_argument("--fixture-label", default=None, help="경기 표시 이름")
    run.set_defaults(func=_cmd_run)

    show = sub.add_parser("show", help="저장된 실행 다시 열기")
    show.add_argument("--run-id", required=True)
    show.set_defaults(func=_cmd_show)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _load_credentials(Path(args.credentials_file))
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - CLI 진입점
    raise SystemExit(main())
