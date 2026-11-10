"""이름 표시용 읽기 역할 준비 (1회, 좁은 범위).

팀·선수의 **한국어 표시 이름**만 읽기 위한 새 읽기 전용 역할 하나를 만든다.

이 스크립트가 하는 일:

- 새 역할 `preview_dev_names_ro`를 만든다(`LOGIN`, 관리자 속성 없음).
- 데이터베이스 `CONNECT`, `public` 스키마 `USAGE`만 준다(`CREATE` 없음).
- **열 단위 `SELECT`** 만 준다. 필요한 항목은 다음과 같다.
  - `public.team(id, external_id, name)`
  - `public.team_translation(team_id, name_ko, short_name_ko)`
  - `public.player(id, external_id, name, firstname, lastname, current_team_id)`
  - `public.player_translation(player_id, name_ko, short_name_ko)`
- 새 역할 DSN을 0600 자격 증명 파일의 `PREVIEW_NAMES_DATABASE_URL` 키로만 쓴다.

하지 않는 일:

- 기존 역할(`preview_dev_identity_ro`, `preview_dev_fixture_ro`, `preview_dev_app`)의
  권한을 넓히지 않고 비밀번호를 바꾸지 않는다.
- 선수 통계·계정·연락처 같은 다른 열을 주지 않는다. 표 전체 권한도 주지 않는다.
- `public`에 DDL·DML을 실행하지 않는다. 행을 고치지 않는다. RLS·트리거·스키마를
  바꾸지 않는다.
- `SUPERUSER`·`CREATEDB`·`CREATEROLE`·`REPLICATION`·`BYPASSRLS`를 주지 않는다.
- 앱이 관리자 역할로 접속하게 만들지 않는다. 관리자 DSN은 프로비저닝에만 쓴다.

검증은 권한 introspection으로만 한다. 운영 데이터에 쓰기 탐침(DML probe)을 실제로
실행하지 않는다. 열 단위 부여라서 `has_table_privilege(..., 'SELECT')`는 거짓으로
나온다(설계된 동작). 그래서 `information_schema.column_privileges`로 확인한다.

관리자 DSN은 `PREVIEW_PROVISION_ADMIN_URL` 환경변수로만 받고 값을 출력하지 않는다.
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

NAMES_ROLE = "preview_dev_names_ro"

# 표별로 허용하는 열. 이름을 넓히지 않는다.
NAME_COLUMNS: dict[str, tuple[str, ...]] = {
    "public.team": ("id", "external_id", "name"),
    "public.team_translation": ("team_id", "name_ko", "short_name_ko"),
    "public.player": ("id", "external_id", "name", "firstname", "lastname", "current_team_id"),
    "public.player_translation": ("player_id", "name_ko", "short_name_ko"),
    # 감독 이름(사용자 요청 범위: 신원·이름·한국어 표기만). 경력·통계·계약 열은 없다.
    "public.coach": ("id", "external_id", "name"),
    "public.coach_translation": ("coach_id", "name_ko", "short_name_ko"),
    # 어느 팀의 감독인지 이름을 고르는 데 필요한 최소 연결 열만 읽는다.
    "public.team_coach": ("team_id", "coach_id"),
}

# 이 역할이 절대 가져서는 안 되는 열. 확인용 목록이며 부여하지 않는다.
FORBIDDEN_COLUMNS: dict[str, tuple[str, ...]] = {
    "public.player": ("age", "birth_date", "birth_place", "birth_country", "nationality",
                      "height_cm", "weight_kg", "injured", "photo_url", "slug"),
    "public.team": ("country", "code", "founded", "logo_url", "venue_id", "created_at", "updated_at"),
    "public.team_translation": ("editor_id", "version", "human_modified", "updated_at"),
    "public.player_translation": ("editor_id", "version", "human_modified", "updated_at"),
    "public.coach": ("photo_url", "slug", "created_at", "updated_at"),
    "public.coach_translation": ("editor_id", "version", "human_modified", "updated_at"),
    "public.team_coach": ("league_id", "season_year", "first_seen_at", "last_seen_at", "updated_at"),
}

CREDENTIALS_KEY = "PREVIEW_NAMES_DATABASE_URL"

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


def _missing_tables(conn: psycopg.Connection) -> list[str]:
    """부여 전에 표와 열이 실제로 있는지 확인한다. 없는 열에 GRANT하면 실패한다."""
    missing: list[str] = []
    with conn.cursor() as cur:
        for qualified, columns in NAME_COLUMNS.items():
            schema, name = qualified.split(".", 1)
            cur.execute(
                "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = %s AND c.relkind IN ('r','p','v')",
                (schema, name),
            )
            if cur.fetchone() is None:
                missing.append(qualified)
                continue
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                (schema, name),
            )
            present = {row[0] for row in cur.fetchall()}
            for column in columns:
                if column not in present:
                    missing.append(f"{qualified}.{column}")
    return missing


def _column_privileges(conn: psycopg.Connection, role: str) -> dict[str, set[str]]:
    """역할이 실제로 가진 열 단위 SELECT 목록."""
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


def _table_privileges(conn: psycopg.Connection, role: str) -> dict[str, dict[str, bool]]:
    """표 전체 권한이 실수로 붙지 않았는지 확인한다. 실제 쓰기 탐침은 하지 않는다."""
    result: dict[str, dict[str, bool]] = {}
    with conn.cursor() as cur:
        for qualified in NAME_COLUMNS:
            checks: dict[str, bool] = {}
            for privilege in (
                "SELECT",
                "INSERT",
                "UPDATE",
                "DELETE",
                "TRUNCATE",
                "REFERENCES",
                "TRIGGER",
            ):
                cur.execute(
                    "SELECT has_table_privilege(%s, %s, %s)",
                    (role, qualified, privilege),
                )
                checks[privilege.lower()] = bool(cur.fetchone()[0])
            result[qualified] = checks
        cur.execute(
            "SELECT has_schema_privilege(%s, 'public', 'USAGE'),"
            " has_schema_privilege(%s, 'public', 'CREATE'),"
            " has_schema_privilege(%s, 'preview_dev', 'USAGE'),"
            " has_database_privilege(%s, current_database(), 'CONNECT'),"
            " has_database_privilege(%s, current_database(), 'CREATE'),"
            " has_database_privilege(%s, current_database(), 'TEMP')",
            (role, role, role, role, role, role),
        )
        usage, create_public, preview_dev_usage, connect, db_create, db_temp = cur.fetchone()
    result["_schema"] = {
        "public_usage": bool(usage),
        "public_create": bool(create_public),
        "preview_dev_usage": bool(preview_dev_usage),
        "database_connect": bool(connect),
        "database_create": bool(db_create),
        "database_temp": bool(db_temp),
    }
    return result


def _grant_sql(qualified: str, columns: tuple[str, ...]) -> sql.Composable:
    return sql.SQL("GRANT SELECT ({}) ON TABLE {} TO {}").format(
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
        sql.SQL(qualified),
        sql.Identifier(NAMES_ROLE),
    )


def _names_dsn(admin_url: str, password: str) -> str:
    """풀러 사용자명 접미사를 유지한 새 역할 DSN을 만든다."""
    info = psycopg.conninfo.conninfo_to_dict(admin_url)
    admin_user = info.get("user", "")
    suffix = admin_user.split(".", 1)[1] if "." in admin_user else ""
    user = f"{NAMES_ROLE}.{suffix}" if suffix else NAMES_ROLE

    host = info.get("host", "")
    port = info.get("port", "5432")
    database = info.get("dbname", "postgres")
    return (
        f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{host}:{port}/{database}"
    )


def _write_credentials(path: Path, names_url: str) -> None:
    """자격 증명 파일에 키를 하나 더한다. 다른 줄은 그대로 둔다."""
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = [
        line for line in existing.splitlines() if not line.startswith(f"{CREDENTIALS_KEY}=")
    ]
    if not lines:
        lines.append("# preview_dev 연결 자격 증명. 저장소에 커밋하지 않는다.")
    lines.append(
        "# 팀·선수 이름 표시용 읽기 전용 역할. 열 단위 SELECT만 가진다."
    )
    lines.append(f"{CREDENTIALS_KEY}={names_url}")
    body = "\n".join(line for line in lines if line is not None) + "\n"

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def _verify(conn: psycopg.Connection, role: str) -> list[str]:
    """부여 결과가 의도한 경계와 맞는지 확인한다. 어긋나면 사유를 돌려준다."""
    problems: list[str] = []
    attributes = _role_attributes(conn, role)
    for attribute in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolbypassrls", "rolreplication"):
        if attributes.get(attribute):
            problems.append(f"role has {attribute}")

    granted = _column_privileges(conn, role)
    for qualified, columns in NAME_COLUMNS.items():
        actual = granted.get(qualified, set())
        missing = set(columns) - actual
        if missing:
            problems.append(f"{qualified} missing column SELECT: {sorted(missing)}")
        extra = actual - set(columns)
        if extra:
            problems.append(f"{qualified} has unexpected column SELECT: {sorted(extra)}")
    for table, columns in FORBIDDEN_COLUMNS.items():
        actual = granted.get(table, set())
        leaked = actual & set(columns)
        if leaked:
            problems.append(f"{table} leaked forbidden columns: {sorted(leaked)}")
    for table in granted:
        if table not in NAME_COLUMNS:
            problems.append(f"{table} unexpectedly readable")

    privileges = _table_privileges(conn, role)
    for qualified, checks in privileges.items():
        if qualified == "_schema":
            continue
        for privilege in ("select", "insert", "update", "delete", "truncate", "references", "trigger"):
            if checks.get(privilege):
                problems.append(f"{qualified} has table-wide {privilege}")
    schema = privileges["_schema"]
    if not schema["public_usage"]:
        problems.append("missing USAGE on public")
    if not schema["database_connect"]:
        problems.append("missing CONNECT on database")
    if schema["public_create"]:
        problems.append("has CREATE on public")
    if schema["preview_dev_usage"]:
        problems.append("has USAGE on preview_dev")
    if schema["database_create"]:
        problems.append("has CREATE on database")
    # `TEMP`는 새 데이터베이스 역할이 PUBLIC 기본값으로 가지는 권한이다. 이 역할만
    # 회수해도 PUBLIC 부여가 남아 효력이 없고, PUBLIC에서 회수하면 기존 역할의 권한을
    # 바꾸는 셈이 된다. 그래서 차단 조건이 아니라 관찰값으로만 남긴다. 기존 영역
    # 쓰기와 무관하며(임시 표는 세션 안에서만 산다) 표·스키마 권한은 위에서 따로 본다.
    return problems


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
    parser.add_argument(
        "--issue-password",
        action="store_true",
        help=(
            "이 스크립트가 만드는 역할 자신의 비밀번호만 새로 발급해 자격 증명 파일에 "
            "쓴다. 다른 역할의 비밀번호는 바꾸지 않는다."
        ),
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
            # 이름을 지어내지 않는다. 확인되지 않은 열에 GRANT하지 않는다.
            print("missing tables/columns: " + ", ".join(missing))
            return 2

        existed = _role_exists(conn, NAMES_ROLE)
        print(f"role {NAMES_ROLE}: {'exists' if existed else 'absent'}")

        if args.dry_run:
            if existed:
                print("attributes:", _role_attributes(conn, NAMES_ROLE))
                print("columns:", _column_privileges(conn, NAMES_ROLE))
                print("problems:", _verify(conn, NAMES_ROLE) or "none")
            return 0

        password: str | None = None
        if existed:
            if args.issue_password:
                # 이 스크립트가 만드는 역할 하나의 비밀번호만 새로 발급한다.
                # 기존 다른 역할(identity/fixture/app)은 건드리지 않는다.
                password = secrets.token_urlsafe(24)
                with conn.transaction():
                    with conn.cursor() as cur:
                        cur.execute(
                            sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                                sql.Identifier(NAMES_ROLE), sql.Literal(password)
                            )
                        )
                print(f"role {NAMES_ROLE}: password reissued for this role only")
            else:
                # 자격 증명이 이미 있는 정상 재실행에서는 비밀번호를 회전하지 않는다.
                print(f"role {NAMES_ROLE}: existing role kept (no password rotation)")
        else:
            password = secrets.token_urlsafe(24)
            with conn.transaction():
                with conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(ROLE_SQL).format(
                            sql.Identifier(NAMES_ROLE), sql.Literal(password)
                        )
                    )
            print(f"role {NAMES_ROLE}: created")

        with conn.transaction():
            with conn.cursor() as cur:
                # public 스키마 사용은 허용하되 CREATE는 주지 않는다.
                cur.execute(f"GRANT USAGE ON SCHEMA public TO {NAMES_ROLE}")
                cur.execute(f"REVOKE CREATE ON SCHEMA public FROM {NAMES_ROLE}")
                cur.execute(f"REVOKE ALL ON SCHEMA preview_dev FROM {NAMES_ROLE}")
                cur.execute(
                    f"GRANT CONNECT ON DATABASE {psycopg.conninfo.conninfo_to_dict(admin_url).get('dbname', 'postgres')}"
                    f" TO {NAMES_ROLE}"
                )
                # 표 전체 권한이 남아 있으면 먼저 회수한다. 열 단위로만 준다.
                for qualified in NAME_COLUMNS:
                    cur.execute(f"REVOKE ALL ON TABLE {qualified} FROM {NAMES_ROLE}")
                for qualified, columns in NAME_COLUMNS.items():
                    cur.execute(_grant_sql(qualified, columns))

        problems = _verify(conn, NAMES_ROLE)
        print("attributes:", _role_attributes(conn, NAMES_ROLE))
        print("columns:", {table: sorted(cols) for table, cols in _column_privileges(conn, NAMES_ROLE).items()})
        if problems:
            print("refusing to write credentials:", problems)
            return 3

        if password is not None:
            names_url = _names_dsn(admin_url, password)
            _write_credentials(Path(args.credentials_file), names_url)
            print(f"credentials file written (0600): {args.credentials_file}")
            print(f"key: {CREDENTIALS_KEY}")
        else:
            print("credentials not rewritten: existing role password unchanged")

    print("verify: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
