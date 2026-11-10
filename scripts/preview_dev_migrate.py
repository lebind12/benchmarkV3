"""preview_dev 마이그레이션 적용기 (명시적, 멱등).

이 스크립트는 두 가지만 한다.

1. `preview_dev` 스키마에 MP-02 테이블이 없으면 만든다(이미 있으면 그대로 둔다).
2. `preview_dev.schema_migrations`에 적용 이력을 남긴다.

하지 않는 것:

- 공용 Alembic 체인을 실행하지 않는다. 그 체인은 `public` 영역에 객체를 만든다.
- `public` 스키마에 어떤 DDL도 하지 않는다. DROP·TRUNCATE도 하지 않는다.
- 기존 행을 고치지 않는다. 이미 적용된 버전은 다시 실행하지 않는다.

자격 증명은 저장소 밖 0600 파일에서 읽고 값을 출력하지 않는다.

    .venv/bin/python scripts/preview_dev_migrate.py --dry-run
    .venv/bin/python scripts/preview_dev_migrate.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATION_PATHS = (
    REPO_ROOT / "alembic" / "versions" / "0002_preview_runs.py",
    REPO_ROOT / "alembic" / "versions" / "0003_preview_approvals.py",
    REPO_ROOT / "alembic" / "versions" / "0004_section_results.py",
    REPO_ROOT / "alembic" / "versions" / "0005_pipeline_runs.py",
)
DEFAULT_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
SCHEMA = "preview_dev"


def load_migrations() -> list:
    """적용 순서대로 마이그레이션 모듈을 읽는다. 순서는 파일명이 아니라 목록이 정한다."""
    modules = []
    for index, path in enumerate(MIGRATION_PATHS):
        if not path.exists():
            raise SystemExit(f"missing migration file: {path}")
        spec = importlib.util.spec_from_file_location(f"mp02_migration_{index}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def read_dev_url(credentials: Path) -> str:
    if not credentials.exists():
        raise SystemExit(f"missing credentials file: {credentials}")
    mode = oct(credentials.stat().st_mode)[-3:]
    if mode != "600":
        raise SystemExit(f"refusing credentials file with mode {mode} (expected 600)")
    values: dict[str, str] = {}
    for line in credentials.read_text(encoding="utf-8").splitlines():
        if line.startswith("PREVIEW_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    url = values.get("PREVIEW_DEV_DATABASE_URL")
    if not url:
        raise SystemExit("PREVIEW_DEV_DATABASE_URL is not set in the credentials file")
    return url


def _applied(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT to_regclass(%s)",
            (f"{SCHEMA}.schema_migrations",),
        )
        if cur.fetchone()[0] is None:
            return set()
        cur.execute(f"SELECT version FROM {SCHEMA}.schema_migrations")
        return {row[0] for row in cur.fetchall()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--credentials-file", default=str(DEFAULT_CREDENTIALS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    url = os.environ.get("PREVIEW_DEV_DATABASE_URL") or read_dev_url(
        Path(args.credentials_file)
    )
    migrations = load_migrations()

    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.autocommit = True
        applied = _applied(conn)
        pending = [m for m in migrations if m.VERSION not in applied]

        print(f"target schema: {SCHEMA}")
        for migration in migrations:
            state = "already applied" if migration.VERSION in applied else "pending"
            print(f"{migration.VERSION}: {state}")
        if not pending:
            return 0

        if args.dry_run:
            total = sum(len(m.UPGRADE_STATEMENTS) for m in pending)
            print(f"dry run: {total} statements pending")
            return 0

        for migration in pending:
            # DDL과 이력 기록을 한 트랜잭션으로 묶는다. 실패하면 그 마이그레이션의
            # 테이블도 남지 않고 이력도 남지 않는다.
            with conn.transaction():
                with conn.cursor() as cur:
                    for statement in migration.UPGRADE_STATEMENTS:
                        cur.execute(statement)
                    cur.execute(
                        f"CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations ("
                        " version text PRIMARY KEY,"
                        " applied_at timestamptz NOT NULL DEFAULT now())"
                    )
                    cur.execute(
                        f"INSERT INTO {SCHEMA}.schema_migrations (version) VALUES (%s)"
                        " ON CONFLICT (version) DO NOTHING",
                        (migration.VERSION,),
                    )
            print(f"{migration.VERSION}: applied")

    # LangGraph 체크포인트 표도 개발 스키마에만 만든다(MP-10). 공식 saver의 DDL은
    # 스키마를 생략하므로, 어댑터가 search_path를 preview_dev로 고정한 연결로 부른다.
    # 앱 시작 시 자동 DDL은 하지 않고 이 명시적 경로에서만 준비한다.
    if not args.dry_run:
        _ensure_checkpoints(url)

    return 0


def _ensure_checkpoints(url: str) -> None:
    """공식 Postgres saver 표를 preview_dev에 준비한다. 설치가 없으면 건너뛴다."""
    sys.path.insert(0, str(REPO_ROOT))
    from app.preview import checkpoints

    available, problem = checkpoints.checkpointer_available()
    if not available:
        print(f"checkpoints: skipped ({problem})")
        return
    checkpoints.ensure_checkpoint_tables(url)
    print(f"checkpoints: ready in {checkpoints.CHECKPOINT_SCHEMA}")


if __name__ == "__main__":
    sys.exit(main())
