"""MP-03 전용 읽기 역할 준비 (1회, 좁은 범위).

이 스크립트가 하는 일은 하나뿐이다. 기존 운영 DB의 경기 관련 표 5개에 `SELECT`만
가진 **새** 읽기 전용 역할을 만든다.

하지 않는 일:

- 기존 역할(`preview_dev_identity_ro`, `preview_dev_app`)의 권한을 넓히지 않는다.
- 기존 역할의 비밀번호를 바꾸지 않는다. 다른 자격 증명을 재설정하지 않는다.
- `public` 스키마에 DDL·DML을 실행하지 않는다. 행을 고치지 않는다.
- 앱이 관리자 역할로 접속하게 만들지 않는다. 관리자 DSN은 프로비저닝에만 쓴다.
- `SUPERUSER`·`CREATEDB`·`CREATEROLE`·`BYPASSRLS`를 주지 않는다.

관리자 DSN은 `PREVIEW_PROVISION_ADMIN_URL` 환경변수로만 받고 값을 출력하지 않는다.
새 역할 비밀번호는 실행 시 생성해 0600 자격 증명 파일에만 쓴다.

검증은 권한 introspection과 읽기 전용 트랜잭션으로만 한다. 운영 데이터에 쓰기
탐침(DML probe)을 실제로 실행하지 않는다.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

import psycopg
from psycopg import sql

FIXTURE_ROLE = "preview_dev_fixture_ro"

# 이 역할이 읽는 표. 이름을 넓히지 않는다.
FIXTURE_TABLES: tuple[str, ...] = (
    "public.fixture",
    "public.team",
    "public.league",
    "public.injury",
    "public.standings",
)

CREDENTIALS_KEY = "PREVIEW_FIXTURES_DATABASE_URL"

ROLE_SQL = (
    "CREATE ROLE {} LOGIN PASSWORD {} "
    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
)


def _role_exists(conn: psycopg.Connection, role: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        return cur.fetchone() is not None


def _role_attributes(conn: psycopg.Connection, role: str) -> dict[str, object]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole,"
            " rolbypassrls, rolinherit"
            " FROM pg_roles WHERE rolname = %s",
            (role,),
        )
        row = cur.fetchone()
    if row is None:
        return {}
    keys = (
        "rolcanlogin",
        "rolsuper",
        "rolcreatedb",
        "rolcreaterole",
        "rolbypassrls",
        "rolinherit",
    )
    return dict(zip(keys, row))


def _missing_tables(conn: psycopg.Connection) -> list[str]:
    """부여 전에 표가 실제로 있는지 확인한다. 없는 표에 GRANT하면 실패한다."""
    missing: list[str] = []
    with conn.cursor() as cur:
        for qualified in FIXTURE_TABLES:
            schema, name = qualified.split(".", 1)
            cur.execute(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r','p','v')",
                (schema, name),
            )
            if cur.fetchone() is None:
                missing.append(qualified)
    return missing


def _privileges(conn: psycopg.Connection, role: str) -> dict[str, dict[str, bool]]:
    """역할의 표별 권한 상태를 확인한다. 실제 쓰기 탐침은 하지 않는다."""
    result: dict[str, dict[str, bool]] = {}
    with conn.cursor() as cur:
        for qualified in FIXTURE_TABLES:
            cur.execute(
                "SELECT has_table_privilege(%s, %s, 'SELECT'),"
                " has_table_privilege(%s, %s, 'INSERT'),"
                " has_table_privilege(%s, %s, 'UPDATE'),"
                " has_table_privilege(%s, %s, 'DELETE'),"
                " has_table_privilege(%s, %s, 'TRUNCATE')",
                (role, qualified) * 5,
            )
            sel, ins, upd, dele, trunc = cur.fetchone()
            result[qualified] = {
                "select": bool(sel),
                "insert": bool(ins),
                "update": bool(upd),
                "delete": bool(dele),
                "truncate": bool(trunc),
            }
        cur.execute(
            "SELECT has_schema_privilege(%s, 'public', 'USAGE'),"
            " has_schema_privilege(%s, 'public', 'CREATE'),"
            " has_schema_privilege(%s, 'preview_dev', 'USAGE'),"
            " has_database_privilege(%s, current_database(), 'CONNECT')",
            (role, role, role, role),
        )
        usage, create_public, preview_dev_usage, connect = cur.fetchone()
    result["_schema"] = {
        "public_usage": bool(usage),
        "public_create": bool(create_public),
        "preview_dev_usage": bool(preview_dev_usage),
        "database_connect": bool(connect),
    }
    return result


def _fixture_dsn(admin_url: str, password: str) -> str:
    """풀러 사용자명 접미사를 유지한 새 역할 DSN을 만든다.

    Supabase 풀러는 사용자명에 테넌트 접미사(`.<project-ref>`)를 요구한다. 관리자
    접속 사용자명의 접미사를 그대로 붙인다.
    """
    info = psycopg.conninfo.conninfo_to_dict(admin_url)
    admin_user = info.get("user", "")
    suffix = admin_user.split(".", 1)[1] if "." in admin_user else ""
    user = f"{FIXTURE_ROLE}.{suffix}" if suffix else FIXTURE_ROLE

    host = info.get("host", "")
    port = info.get("port", "5432")
    database = info.get("dbname", "postgres")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


def _write_credentials(path: Path, fixture_url: str) -> None:
    """기존 자격 증명 파일에 키를 하나 더한다. 다른 줄은 그대로 둔다."""
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
    lines = [
        line
        for line in existing.splitlines()
        if not line.startswith(f"{CREDENTIALS_KEY}=")
    ]
    if not any(line.startswith("#") for line in lines):
        lines.insert(0, "# preview_dev 연결 자격 증명. 저장소에 커밋하지 않는다.")
    lines.append(
        "# 경기 자료 읽기 전용 역할. 기존 역할과 별개이며 SELECT만 가진다."
    )
    lines.append(f"{CREDENTIALS_KEY}={fixture_url}")
    body = "\n".join(line for line in lines if line is not None) + "\n"

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--credentials-file",
        default=str(Path.home() / ".config" / "match-preview" / "preview-dev.env"),
        help="새 역할 DSN을 쓸 0600 파일 경로",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="권한 부여 없이 현재 상태만 확인한다",
    )
    args = parser.parse_args(argv)

    admin_url = os.environ.get("PREVIEW_PROVISION_ADMIN_URL")
    if not admin_url:
        raise SystemExit("PREVIEW_PROVISION_ADMIN_URL is required")

    # 검사용 SELECT 뒤에 autocommit을 바꾸면 실패한다. 처음부터 autocommit으로 열고
    # 권한 변경만 명시적 트랜잭션(`conn.transaction()`)으로 묶는다.
    with psycopg.connect(admin_url, connect_timeout=15, autocommit=True) as conn:
        missing = _missing_tables(conn)
        if missing:
            # 이름을 지어내지 않는다. 확인되지 않은 표에 GRANT하지 않는다.
            print("missing tables: " + ", ".join(missing))
            return 2

        existed = _role_exists(conn, FIXTURE_ROLE)
        print(f"role {FIXTURE_ROLE}: {'exists' if existed else 'absent'}")

        if args.dry_run:
            if existed:
                print("attributes:", _role_attributes(conn, FIXTURE_ROLE))
                print("privileges:", _privileges(conn, FIXTURE_ROLE))
            return 0

        password = secrets.token_urlsafe(24)
        with conn.transaction():
            with conn.cursor() as cur:
                if existed:
                    # 이미 있으면 비밀번호만 바꾼다. 다른 역할은 건드리지 않는다.
                    cur.execute(
                        sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                            sql.Identifier(FIXTURE_ROLE), sql.Literal(password)
                        )
                    )
                    print(f"role {FIXTURE_ROLE}: password rotated (existing role)")
                else:
                    cur.execute(
                        sql.SQL(ROLE_SQL).format(
                            sql.Identifier(FIXTURE_ROLE), sql.Literal(password)
                        )
                    )
                    print(f"role {FIXTURE_ROLE}: created")

                # public 스키마 사용은 허용하되 CREATE는 주지 않는다.
                cur.execute(f"GRANT USAGE ON SCHEMA public TO {FIXTURE_ROLE}")
                cur.execute(f"REVOKE CREATE ON SCHEMA public FROM {FIXTURE_ROLE}")
                for qualified in FIXTURE_TABLES:
                    cur.execute(f"GRANT SELECT ON TABLE {qualified} TO {FIXTURE_ROLE}")
                # 개발 스키마에는 아무 권한도 주지 않는다.
                cur.execute(f"REVOKE ALL ON SCHEMA preview_dev FROM {FIXTURE_ROLE}")

        attributes = _role_attributes(conn, FIXTURE_ROLE)
        privileges = _privileges(conn, FIXTURE_ROLE)

        if attributes.get("rolsuper") or attributes.get("rolcreaterole") or attributes.get(
            "rolcreatedb"
        ) or attributes.get("rolbypassrls"):
            print("refusing to write credentials: role has elevated attributes")
            return 3
        for qualified, privs in privileges.items():
            if qualified == "_schema":
                continue
            if not privs["select"]:
                print(f"refusing to write credentials: {qualified} has no SELECT")
                return 3
            for write in ("insert", "update", "delete", "truncate"):
                if privs[write]:
                    print(
                        f"refusing to write credentials: {qualified} has {write}"
                    )
                    return 3
        if privileges["_schema"]["public_create"]:
            print("refusing to write credentials: role can CREATE in public")
            return 3
        if privileges["_schema"]["preview_dev_usage"]:
            print("refusing to write credentials: role has preview_dev access")
            return 3

        fixture_url = _fixture_dsn(admin_url, password)
        _write_credentials(Path(args.credentials_file), fixture_url)

    print("attributes:", attributes)
    print("privileges:", privileges)
    print(f"credentials file written (0600): {args.credentials_file}")
    print(f"key: {CREDENTIALS_KEY}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
