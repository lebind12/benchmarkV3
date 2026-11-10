"""preview_dev 객체·권한 실태 확인 (읽기 전용).

이미 준비된 개발 영역이 앱이 기대하는 모양과 맞는지, 그리고 두 역할의 권한
경계가 실제로 막혀 있는지 확인한다. 객체를 새로 만들거나 고치지 않는다.
`scripts/preview_dev_provision.py`를 다시 실행하지 않아도 상태를 판정할 수 있다.

자격 증명은 저장소 밖 0600 파일에서 읽고 값을 출력하지 않는다.

    .venv/bin/python scripts/preview_dev_status.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import psycopg

EXPECTED_COLUMNS = [
    ("id", "uuid", "NO"),
    ("user_id", "bigint", "NO"),
    ("email", "text", "NO"),
    ("token_hash", "text", "NO"),
    ("created_at", "timestamp with time zone", "NO"),
    ("expires_at", "timestamp with time zone", "NO"),
    ("revoked_at", "timestamp with time zone", "YES"),
]


def _read_credentials(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("PREVIEW_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def _denied(conn: psycopg.Connection, statement: str) -> bool:
    try:
        with conn.transaction():
            conn.execute(statement)
        return False
    except psycopg.errors.InsufficientPrivilege:
        return True


def _check_shape(writer_url: str) -> bool:
    ok = True
    with psycopg.connect(writer_url, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'preview_dev' "
                "AND table_name = 'preview_admin_sessions' "
                "ORDER BY ordinal_position"
            )
            found = [tuple(row) for row in cur.fetchall()]
            if found == EXPECTED_COLUMNS:
                print("shape: preview_dev.preview_admin_sessions matches expectations")
            else:
                ok = False
                print(f"shape: MISMATCH\n  expected {EXPECTED_COLUMNS}\n  found    {found}")

            cur.execute("SELECT count(*) FROM preview_dev.schema_migrations")
            migrations = cur.fetchone()[0]
            print(f"shape: migration rows = {migrations}")

            cur.execute("SELECT count(*) FROM preview_dev.preview_admin_sessions")
            print(f"shape: session rows = {cur.fetchone()[0]}")

        writer_blocks = {
            "write to public.app_user": _denied(
                conn, "UPDATE public.app_user SET role = role WHERE false"
            ),
            "read public.app_user": _denied(conn, "SELECT 1 FROM public.app_user LIMIT 0"),
            "read public.fixture": _denied(conn, "SELECT 1 FROM public.fixture LIMIT 0"),
            "create table in public": _denied(conn, "CREATE TABLE public.probe_denied (a int)"),
        }
    print("writer role (preview_dev_app):")
    for label, denied in writer_blocks.items():
        print(f"  {label}: {'denied' if denied else 'ALLOWED (unexpected)'}")
        ok = ok and denied
    return ok


def _check_identity(identity_url: str) -> bool:
    ok = True
    with psycopg.connect(
        identity_url,
        connect_timeout=15,
        options="-c default_transaction_read_only=on -c statement_timeout=8000",
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM public.app_user")
            print(f"identity: public.app_user rows = {cur.fetchone()[0]}")
            cur.execute("SELECT current_user")
            print(f"identity: connected as {cur.fetchone()[0]}")

        # 기대값: app_user 읽기만 허용, 나머지는 전부 거부.
        identity_blocks = {
            "select public.app_user": (
                _denied(conn, "SELECT 1 FROM public.app_user LIMIT 0"),
                False,
            ),
            "update public.app_user": (
                _denied(conn, "UPDATE public.app_user SET role = role WHERE false"),
                True,
            ),
            "select public.fixture": (
                _denied(conn, "SELECT 1 FROM public.fixture LIMIT 0"),
                True,
            ),
            "select preview_dev sessions": (
                _denied(conn, "SELECT 1 FROM preview_dev.preview_admin_sessions LIMIT 0"),
                True,
            ),
        }
    print("identity role (preview_dev_identity_ro):")
    for label, (denied, expected_denied) in identity_blocks.items():
        matched = denied is expected_denied
        print(
            f"  {label}: {'denied' if denied else 'allowed'}"
            f"{'' if matched else ' (UNEXPECTED)'}"
        )
        ok = ok and matched
    return ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--credentials-file",
        default=str(Path.home() / ".config" / "match-preview" / "preview-dev.env"),
    )
    args = parser.parse_args(argv)

    path = Path(args.credentials_file)
    if not path.exists():
        print(f"missing credentials file: {path}", file=sys.stderr)
        return 2
    if oct(path.stat().st_mode)[-3:] != "600":
        print(f"credentials file must be mode 600: {path}", file=sys.stderr)
        return 2

    values = _read_credentials(path)
    writer_url = values.get("PREVIEW_DEV_DATABASE_URL")
    identity_url = values.get("PREVIEW_IDENTITY_DATABASE_URL")
    if not writer_url or not identity_url:
        print("credentials file lacks the two database URLs", file=sys.stderr)
        return 2

    shape_ok = _check_shape(writer_url)
    identity_ok = _check_identity(identity_url)
    print(f"result: {'PASS' if shape_ok and identity_ok else 'FAIL'}")
    return 0 if shape_ok and identity_ok else 1


if __name__ == "__main__":
    sys.exit(main())
