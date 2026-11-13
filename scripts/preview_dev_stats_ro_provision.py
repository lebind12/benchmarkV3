"""선수 시즌 통계 읽기 역할 준비 (1회, 좁은 범위).

`public.player_season_stat`의 **필요한 열만** 읽는 새 읽기 전용 역할 하나를 준비한다.

이 스크립트가 하는 일:

- 새 역할 `preview_dev_stats_ro`를 만든다(`LOGIN`, 관리자 속성 없음, `NOINHERIT`).
- 데이터베이스 `CONNECT`, `public` 스키마 `USAGE`만 준다(`CREATE` 없음).
- **열 단위 `SELECT`만** 준다: `public.player_season_stat`의 13개 열.
  (`player_id`, `team_id`, `league_id`, `season_year`, `position`, `appearances`,
   `minutes`, `rating`, `goals`, `assists`, `updated_at`)
- 새 역할 DSN을 0600 자격 증명 파일의 `PREVIEW_STATS_DATABASE_URL` 키로만 쓴다.

하지 않는 일:

- 기존 역할(`preview_dev_identity_ro`, `preview_dev_fixture_ro`, `preview_dev_names_ro`,
  `preview_dev_app`)의 권한을 넓히지 않고 비밀번호를 바꾸지 않는다.
- `raw_stats`(jsonb 원본), `shirt_number`, `id`를 주지 않는다. 표 전체 권한도 주지 않는다.
- `public`에 DDL·DML을 실행하지 않는다. 행을 고치지 않는다. RLS·트리거·스키마를 바꾸지 않는다.
- 앱이 관리자 역할로 접속하게 만들지 않는다. 관리자 DSN은 프로비저닝에만 쓴다.

기본 동작은 **dry-run**이다. 권한을 실제로 바꾸려면 `--apply`를 명시해야 한다.
관리자 DSN은 `PREVIEW_PROVISION_ADMIN_URL` 환경변수로만 받고 값을 출력하지 않는다.

검증은 권한 introspection으로만 한다. 운영 데이터에 쓰기 탐침(DML probe)을 실행하지
않는다. 열 단위 부여라서 `has_table_privilege(..., 'SELECT')`는 거짓으로 나오므로
`information_schema.column_privileges`로 확인한다.
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

STATS_ROLE = "preview_dev_stats_ro"
STATS_TABLE = "public.player_season_stat"

# 이 역할이 읽는 열. 이름을 넓히지 않는다.
STATS_COLUMNS: tuple[str, ...] = (
    "player_id",
    "team_id",
    "league_id",
    "season_year",
    "position",
    "appearances",
    "minutes",
    "rating",
    "goals",
    "assists",
    "updated_at",
)

# 이 역할이 절대 가져서는 안 되는 열(존재 확인용 목록이며 부여하지 않는다).
FORBIDDEN_COLUMNS: dict[str, tuple[str, ...]] = {
    STATS_TABLE: ("raw_stats", "shirt_number", "id"),
}

CREDENTIALS_KEY = "PREVIEW_STATS_DATABASE_URL"

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
            " rolbypassrls, rolreplication, rolinherit"
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
        "rolreplication",
        "rolinherit",
    )
    return dict(zip(keys, row))


def _missing_columns(conn: psycopg.Connection) -> list[str]:
    """부여 전에 표와 열이 실제로 있는지 확인한다. 없는 열에 GRANT하면 실패한다."""
    schema, name = STATS_TABLE.split(".", 1)
    missing: list[str] = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r','p')",
            (schema, name),
        )
        if cur.fetchone() is None:
            return [STATS_TABLE]
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s",
            (schema, name),
        )
        present = {row[0] for row in cur.fetchall()}
    for column in STATS_COLUMNS:
        if column not in present:
            missing.append(f"{STATS_TABLE}.{column}")
    return missing


def _column_privileges(conn: psycopg.Connection, role: str) -> dict[str, set[str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_schema || '.' || table_name, column_name"
            " FROM information_schema.column_privileges"
            " WHERE grantee = %s AND privilege_type = 'SELECT'",
            (role,),
        )
        result: dict[str, set[str]] = {}
        for table, column in cur.fetchall():
            result.setdefault(table, set()).add(column)
    return result


def _scope_privileges(conn: psycopg.Connection, role: str, database: str) -> dict[str, bool]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT has_schema_privilege(%s, 'public', 'USAGE'),"
            " has_schema_privilege(%s, 'public', 'CREATE'),"
            " has_schema_privilege(%s, 'preview_dev', 'USAGE'),"
            " has_database_privilege(%s, %s, 'CONNECT'),"
            " has_database_privilege(%s, %s, 'CREATE')",
            (role, role, role, role, database, role, database),
        )
        usage, create_public, preview_dev_usage, connect, db_create = cur.fetchone()
    return {
        "public_usage": bool(usage),
        "public_create": bool(create_public),
        "preview_dev_usage": bool(preview_dev_usage),
        "database_connect": bool(connect),
        "database_create": bool(db_create),
    }


def _table_wide_privileges(conn: psycopg.Connection, role: str) -> dict[str, bool]:
    """표 전체 권한이 실수로 붙지 않았는지 확인한다. 실제 쓰기 탐침은 하지 않는다."""
    result: dict[str, bool] = {}
    with conn.cursor() as cur:
        for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            cur.execute("SELECT has_table_privilege(%s, %s, %s)", (role, STATS_TABLE, privilege))
            result[privilege.lower()] = bool(cur.fetchone()[0])
    return result


def _verify(conn: psycopg.Connection, role: str, database: str) -> list[str]:
    problems: list[str] = []
    attributes = _role_attributes(conn, role)
    for attribute in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls", "rolreplication"):
        if attributes.get(attribute):
            problems.append(f"role has {attribute}")

    granted = _column_privileges(conn, role)
    actual = granted.get(STATS_TABLE, set())
    missing = set(STATS_COLUMNS) - actual
    if missing:
        problems.append(f"{STATS_TABLE} missing column SELECT: {sorted(missing)}")
    extra = actual - set(STATS_COLUMNS)
    if extra:
        problems.append(f"{STATS_TABLE} has unexpected column SELECT: {sorted(extra)}")
    for table, columns in FORBIDDEN_COLUMNS.items():
        leaked = granted.get(table, set()) & set(columns)
        if leaked:
            problems.append(f"{table} leaked forbidden columns: {sorted(leaked)}")
    for table in granted:
        if table != STATS_TABLE:
            problems.append(f"{table} unexpectedly readable")

    for privilege, granted_flag in _table_wide_privileges(conn, role).items():
        if granted_flag:
            problems.append(f"{STATS_TABLE} has table-wide {privilege}")

    scope = _scope_privileges(conn, role, database)
    if not scope["public_usage"]:
        problems.append("missing USAGE on public")
    if not scope["database_connect"]:
        problems.append("missing CONNECT on database")
    if scope["public_create"]:
        problems.append("has CREATE on public")
    if scope["preview_dev_usage"]:
        problems.append("has USAGE on preview_dev")
    if scope["database_create"]:
        problems.append("has CREATE on database")
    return problems


def _stats_dsn(admin_url: str, password: str) -> str:
    """풀러 사용자명 접미사를 유지한 새 역할 DSN을 만든다."""
    info = psycopg.conninfo.conninfo_to_dict(admin_url)
    admin_user = info.get("user", "")
    suffix = admin_user.split(".", 1)[1] if "." in admin_user else ""
    user = f"{STATS_ROLE}.{suffix}" if suffix else STATS_ROLE

    host = info.get("host", "")
    port = info.get("port", "5432")
    database = info.get("dbname", "postgres")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


def _write_credentials(path: Path, stats_url: str) -> None:
    """자격 증명 파일에 키를 하나 더한다. 다른 줄은 그대로 둔다."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [
        line for line in existing.splitlines() if not line.startswith(f"{CREDENTIALS_KEY}=")
    ]
    if not lines:
        lines.append("# preview_dev 연결 자격 증명. 저장소에 커밋하지 않는다.")
    lines.append("# 선수 시즌 통계 읽기 전용 역할. 열 단위 SELECT만 가진다.")
    lines.append(f"{CREDENTIALS_KEY}={stats_url}")
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
        "--apply",
        action="store_true",
        help="역할 생성과 GRANT를 실제로 적용한다. 기본은 dry-run이다.",
    )
    parser.add_argument(
        "--issue-password",
        action="store_true",
        help=(
            "이 스크립트가 만드는 역할 자신의 비밀번호만 새로 발급해 자격 증명 파일에 쓴다. "
            "다른 역할의 비밀번호는 바꾸지 않는다."
        ),
    )
    args = parser.parse_args(argv)

    admin_url = os.environ.get("PREVIEW_PROVISION_ADMIN_URL")
    if not admin_url:
        raise SystemExit(
            "PREVIEW_PROVISION_ADMIN_URL is required (관리자 DSN은 환경변수로만 받는다)"
        )

    database = psycopg.conninfo.conninfo_to_dict(admin_url).get("dbname", "postgres")

    # 검사용 SELECT 뒤에 autocommit을 바꾸면 실패한다. 처음부터 autocommit으로 열고
    # 권한 변경만 명시적 트랜잭션으로 묶는다.
    with psycopg.connect(admin_url, connect_timeout=15, autocommit=True) as conn:
        missing = _missing_columns(conn)
        if missing:
            # 이름을 지어내지 않는다. 확인되지 않은 열에 GRANT하지 않는다.
            print("missing tables/columns: " + ", ".join(missing))
            return 2

        existed = _role_exists(conn, STATS_ROLE)
        print(f"role {STATS_ROLE}: {'exists' if existed else 'absent'}")

        if not args.apply:
            print("mode: dry-run (no grants applied). re-run with --apply to apply.")
            if existed:
                print("attributes:", _role_attributes(conn, STATS_ROLE))
                print(
                    "columns:",
                    {table: sorted(cols) for table, cols in _column_privileges(conn, STATS_ROLE).items()},
                )
                print("problems:", _verify(conn, STATS_ROLE, database) or "none")
            else:
                print("would grant column SELECT:", ", ".join(STATS_COLUMNS))
            return 0

        password: str | None = None
        if existed:
            if args.issue_password:
                password = secrets.token_urlsafe(24)
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                                sql.Identifier(STATS_ROLE), sql.Literal(password)
                            )
                        )
                print(f"role {STATS_ROLE}: password reissued for this role only")
            else:
                print(f"role {STATS_ROLE}: existing role kept (no password rotation)")
        else:
            password = secrets.token_urlsafe(24)
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(ROLE_SQL).format(
                            sql.Identifier(STATS_ROLE), sql.Literal(password)
                        )
                    )
            print(f"role {STATS_ROLE}: created")

        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute(f"GRANT USAGE ON SCHEMA public TO {STATS_ROLE}")
                cur.execute(f"REVOKE CREATE ON SCHEMA public FROM {STATS_ROLE}")
                cur.execute(f"REVOKE ALL ON SCHEMA preview_dev FROM {STATS_ROLE}")
                cur.execute(f"GRANT CONNECT ON DATABASE {database} TO {STATS_ROLE}")
                # 표 전체 권한이 남아 있으면 먼저 회수한다. 열 단위로만 준다.
                cur.execute(f"REVOKE ALL ON TABLE {STATS_TABLE} FROM {STATS_ROLE}")
                cur.execute(
                    sql.SQL("GRANT SELECT ({}) ON TABLE {} TO {}").format(
                        sql.SQL(", ").join(sql.Identifier(column) for column in STATS_COLUMNS),
                        sql.SQL(STATS_TABLE),
                        sql.Identifier(STATS_ROLE),
                    )
                )

        problems = _verify(conn, STATS_ROLE, database)
        print("attributes:", _role_attributes(conn, STATS_ROLE))
        print(
            "columns:",
            {table: sorted(cols) for table, cols in _column_privileges(conn, STATS_ROLE).items()},
        )
        if problems:
            print("refusing to write credentials:", problems)
            return 3

        if password is not None:
            _write_credentials(Path(args.credentials_file), _stats_dsn(admin_url, password))
            print(f"credentials file written (0600): {args.credentials_file}")
            print(f"key: {CREDENTIALS_KEY}")
        else:
            print("credentials not rewritten: existing role password unchanged")

    print("verify: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
