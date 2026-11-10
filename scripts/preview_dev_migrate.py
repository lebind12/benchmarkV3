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
MIGRATION_PATH = REPO_ROOT / "alembic" / "versions" / "0002_preview_runs.py"
DEFAULT_CREDENTIALS = Path.home() / ".config" / "match-preview" / "preview-dev.env"
SCHEMA = "preview_dev"


def load_migration():
    spec = importlib.util.spec_from_file_location("mp02_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
    migration = load_migration()

    with psycopg.connect(url, connect_timeout=15) as conn:
        conn.autocommit = True
        applied = _applied(conn)
        if migration.VERSION in applied:
            print(f"{migration.VERSION}: already applied")
            return 0

        print(f"target schema: {SCHEMA}")
        print(f"pending version: {migration.VERSION}")
        if args.dry_run:
            print(f"dry run: {len(migration.UPGRADE_STATEMENTS)} statements pending")
            return 0

        # DDL과 이력 기록을 한 트랜잭션으로 묶는다. 실패하면 테이블도 남지 않는다.
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
