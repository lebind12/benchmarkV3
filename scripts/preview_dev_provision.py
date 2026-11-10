"""Preview 개발 스키마·역할 준비 (명시적, 1회 실행).

운영 DB의 기존 데이터(`public` 스키마)는 읽기 전용으로만 쓴다. 이 스크립트가
만드는 것은 다음 세 가지이며, 기존 테이블·역할·데이터는 변경하지 않는다.

1. 읽기 전용 역할 `preview_dev_identity_ro`: `public.app_user` SELECT만.
2. 개발 쓰기 역할 `preview_dev_app`: `preview_dev` 스키마 소유자. `public` 쓰기 권한 없음.
3. `preview_dev` 스키마와 세션 테이블·마이그레이션 기록.

관리자 DSN은 `PREVIEW_PROVISION_ADMIN_URL` 환경변수로만 받는다. 값은 출력하지
않는다. 새 역할 비밀번호는 실행 시 생성해 지정한 자격 증명 파일(0600)에만 쓴다.
DROP·TRUNCATE·기존 스키마 재생성은 하지 않는다.
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

SCHEMA = "preview_dev"
IDENTITY_ROLE = "preview_dev_identity_ro"
WRITE_ROLE = "preview_dev_app"
MIGRATION_VERSION = "0001_preview_dev_admin_sessions"

ROLE_SQL = (
    "CREATE ROLE {} LOGIN PASSWORD {} "
    "NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT"
)

DDL = [
    # 스키마 소유자는 관리자다. 개발 쓰기 역할에는 이 스키마 안의 권한만 준다.
    # (`AUTHORIZATION preview_dev_app`은 관리자에게 SET ROLE 권한이 없어 실패한다.)
    f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}",
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.preview_admin_sessions (
        id uuid PRIMARY KEY,
        user_id bigint NOT NULL,
        email text NOT NULL,
        token_hash text NOT NULL UNIQUE,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        revoked_at timestamptz
    )
    """,
    f"""
    CREATE INDEX IF NOT EXISTS ix_preview_admin_sessions_user_id
        ON {SCHEMA}.preview_admin_sessions (user_id)
    """,
    f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA}.schema_migrations (
        version text PRIMARY KEY,
        applied_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    f"""
    INSERT INTO {SCHEMA}.schema_migrations (version)
        VALUES ('{MIGRATION_VERSION}') ON CONFLICT (version) DO NOTHING
    """,
    # 개발 쓰기 역할: preview_dev 안에서만 쓰기. public 쪽은 아무 권한도 없다.
    f"GRANT USAGE, CREATE ON SCHEMA {SCHEMA} TO {WRITE_ROLE}",
    f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {SCHEMA} TO {WRITE_ROLE}",
    f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA {SCHEMA} TO {WRITE_ROLE}",
    f"REVOKE ALL ON SCHEMA public FROM {WRITE_ROLE}",
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {WRITE_ROLE}",
    # 읽기 역할: 기존 계정 표 하나만 읽는다. preview_dev에는 아무 권한도 없다.
    f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {IDENTITY_ROLE}",
    f"GRANT USAGE ON SCHEMA public TO {IDENTITY_ROLE}",
    f"GRANT SELECT ON TABLE public.app_user TO {IDENTITY_ROLE}",
    f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {IDENTITY_ROLE}",
    # 두 역할 모두 DB 접속만 허용한다.
    "GRANT CONNECT ON DATABASE {db} TO " + IDENTITY_ROLE,
    "GRANT CONNECT ON DATABASE {db} TO " + WRITE_ROLE,
]


def _role_exists(conn: psycopg.Connection, role: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        return cur.fetchone() is not None


def _write_credentials(path: Path, identity_url: str, dev_url: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    body = (
        "# preview_dev 연결 자격 증명. 저장소에 커밋하지 않는다.\n"
        "# 아래 두 플래그는 이 대상이 의도된 원격 DB라는 명시적 동의다.\n"
        f"PREVIEW_IDENTITY_DATABASE_URL={identity_url}\n"
        f"PREVIEW_DEV_DATABASE_URL={dev_url}\n"
        "PREVIEW_ALLOW_NONLOCAL_DB=1\n"
        "PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB=1\n"
    )
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
    args = parser.parse_args(argv)

    admin_url = os.environ.get("PREVIEW_PROVISION_ADMIN_URL")
    if not admin_url:
        raise SystemExit("PREVIEW_PROVISION_ADMIN_URL is required")

    password_ro = secrets.token_urlsafe(24)
    password_app = secrets.token_urlsafe(24)

    with psycopg.connect(admin_url, connect_timeout=15) as conn:
        conn.autocommit = False
        created = []
        with conn.transaction():
            with conn.cursor() as cur:
                cur.execute("SELECT current_database()")
                database = cur.fetchone()[0]
                for role, password in (
                    (IDENTITY_ROLE, password_ro),
                    (WRITE_ROLE, password_app),
                ):
                    if _role_exists(conn, role):
                        cur.execute(
                            # 기존 역할은 비밀번호만 바꾼다. SUPERUSER 등 속성을
                            # 다시 지정하면 관리자에게 없는 권한을 요구한다.
                            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                                sql.Identifier(role), sql.Literal(password)
                            )
                        )
                        created.append(f"role {role}: password rotated (existing role)")
                    else:
                        cur.execute(
                            sql.SQL(ROLE_SQL).format(
                                sql.Identifier(role), sql.Literal(password)
                            )
                        )
                        created.append(f"role {role}: created")

                for statement in DDL:
                    cur.execute(
                        statement.format(
                            db=sql.Identifier(database).as_string(conn)
                        )
                        if "{db}" in statement
                        else statement
                    )

        with conn.cursor() as cur:
            cur.execute(
                "SELECT has_schema_privilege(%s, 'public', 'CREATE'),"
                " has_table_privilege(%s, 'public.app_user', 'INSERT'),"
                " has_table_privilege(%s, 'public.app_user', 'UPDATE'),"
                " has_table_privilege(%s, 'public.app_user', 'DELETE'),"
                " has_table_privilege(%s, 'public.app_user', 'SELECT'),"
                " has_schema_privilege(%s, %s, 'CREATE'),"
                " has_schema_privilege(%s, 'public', 'USAGE')",
                (
                    WRITE_ROLE, WRITE_ROLE, WRITE_ROLE, WRITE_ROLE,
                    IDENTITY_ROLE, WRITE_ROLE, SCHEMA, IDENTITY_ROLE,
                ),
            )
            writer = cur.fetchone()
            cur.execute(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relkind = 'r'",
                (SCHEMA,),
            )
            table_count = cur.fetchone()[0]

    for line in created:
        print(line)
    print(f"database: {database}")
    print(
        "write role public[CREATE/INSERT/UPDATE/DELETE]="
        f"{writer[0]}/{writer[1]}/{writer[2]}/{writer[3]} "
        f"identity SELECT on public.app_user={writer[4]} "
        f"write role CREATE on {SCHEMA}={writer[5]} "
        f"identity USAGE on public={writer[6]}"
    )
    print(f"{SCHEMA} tables: {table_count}")

    info = psycopg.conninfo.conninfo_to_dict(admin_url)
    host = info.get("host", "")
    port = info.get("port", "5432")
    database = info.get("dbname", "postgres")
    # Supabase pooler는 사용자 이름에 테넌트 식별자를 요구한다. 관리자 접속
    # 사용자명(`postgres.<project-ref>`)의 접미사를 그대로 붙인다.
    admin_user = info.get("user", "")
    tenant = admin_user.split(".", 1)[1] if "." in admin_user else ""
    suffix = f".{tenant}" if tenant else ""
    identity_url = (
        f"postgresql://{IDENTITY_ROLE}{suffix}:{quote(password_ro)}@{host}:{port}/{database}"
    )
    dev_url = (
        f"postgresql://{WRITE_ROLE}{suffix}:{quote(password_app)}@{host}:{port}/{database}"
    )
    target = Path(args.credentials_file)
    _write_credentials(target, identity_url, dev_url)
    print(f"credentials written: {target} (mode 600)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
