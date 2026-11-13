"""격리된 UI 확인용 로컬 환경 준비 (MP-02).

용도는 하나다. 사용자의 실제 계정 로그인 세션과 실제 개발 서버(:8000)를 건드리지
않고, 검사 화면이 실제 브라우저에서 어떻게 보이는지 증거를 남기는 것.

경계:

- 대상은 전용 로컬 테스트 DB뿐이다(`_test` 접미사 없으면 거부). 운영·개발 DB 이름은
  거부된다. `scripts/preview_dev_provision.py`와 같은 가드를 쓰지 않고 여기서 더
  좁게 검사한다.
- 합성 관리자 계정 하나를 **그 테스트 DB 안에만** 만든다. 운영 계정 원장은 읽지도
  쓰지도 않는다.
- 비밀번호는 실행 시 생성해 표준출력으로 한 번만 알려준다. 저장소 파일에 쓰지 않는다.
- 모의 실행은 `create_recorded_mock_run`으로 만든다. 외부 호출은 0회다.

    .venv/bin/python scripts/preview_ui_fixture.py
"""

from __future__ import annotations

import argparse
import importlib.util
import secrets
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import text  # noqa: E402

from app.core.db_target import parse_database_target  # noqa: E402
from tests.preview._dbguard import assert_safe_test_database  # noqa: E402

SCHEMA = "preview_dev"
DEFAULT_URL = (
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp02_ui_test"
)
FIXTURE_EMAIL = "mp02-ui-admin@example.test"
IDENTITY_DDL = """
CREATE TABLE IF NOT EXISTS public.app_user (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role text NOT NULL DEFAULT 'USER',
    nickname text,
    is_active boolean NOT NULL DEFAULT true,
    email_verified boolean NOT NULL DEFAULT false,
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT app_user_role_check CHECK (role IN ('USER', 'STREAMER', 'ADMIN'))
)
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--database-url", default=DEFAULT_URL)
    parser.add_argument("--runs", type=int, default=1, help="만들 녹화 mock 실행 수")
    args = parser.parse_args(argv)

    # 연결 전에 대상부터 검사한다. 테스트 DB가 아니면 여기서 끝난다.
    target = assert_safe_test_database(args.database_url)
    parsed = parse_database_target(args.database_url)
    assert parsed.is_loopback, "the UI fixture database must be loopback"
    print(f"target: {target.host}:{target.port}/{target.name} (loopback test database)")

    import os

    os.environ["PREVIEW_DATABASE_URL"] = args.database_url
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = args.database_url
    os.environ["PREVIEW_ENV"] = "dev"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    os.environ.setdefault("PREVIEW_ALLOW_NONLOCAL_DB", "0")
    os.environ.setdefault("PREVIEW_ALLOW_NONLOCAL_IDENTITY_DB", "0")

    from app.auth import identity as identity_module
    from app.auth.passwords import hash_pbkdf2_sha256
    from app.preview.config import get_settings
    from app.preview.db import get_engine, get_session_factory, reset_engine

    reset_engine()
    identity_module.reset_identity_reader()
    get_settings.cache_clear()

    engine = get_engine()
    from app.auth import models as _auth_models  # noqa: F401
    from app.preview.db import Base
    from app.preview import models as _preview_models  # noqa: F401

    password = f"mp02-ui-{secrets.token_urlsafe(9)}"

    # 마이그레이션 파일이 정의한 DDL을 적용 순서대로 모두 실행한다. 목록을 여기에
    # 손으로 적지 않으므로 새 마이그레이션이 생겨도 이 스크립트가 뒤처지지 않는다.
    migration_paths = sorted((REPO_ROOT / "alembic" / "versions").glob("[0-9]*.py"))
    migrations = []
    for path in migration_paths:
        spec = importlib.util.spec_from_file_location(f"mp02_ui_migration_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        migrations.append(module)

    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
        conn.execute(text(IDENTITY_DDL))
        for migration in migrations:
            # 0001은 Alembic op 기반이라 DDL 목록이 없다. 그 표는 Base.metadata가 만든다.
            for statement in getattr(migration, "UPGRADE_STATEMENTS", ()):
                conn.execute(text(statement))
    Base.metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO public.app_user (email, password_hash, role, is_active) "
                "VALUES (:email, :hash, 'ADMIN', true) "
                "ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash"
            ),
            {"email": FIXTURE_EMAIL, "hash": hash_pbkdf2_sha256(password)},
        )
        actor_id = conn.execute(
            text("SELECT id FROM public.app_user WHERE email = :email"),
            {"email": FIXTURE_EMAIL},
        ).scalar_one()

        # 이전 실행의 잔여 기록을 지우지 않는다. 남아 있으면 그대로 두고 새로 만든다.
        existing = conn.execute(
            text(f"SELECT count(*) FROM {SCHEMA}.preview_runs")
        ).scalar_one()

    created: list[str] = []
    if args.runs > 0:
        from app.preview import demo_pipeline

        factory = get_session_factory()
        for _ in range(args.runs):
            with factory() as session:
                result = demo_pipeline.create_recorded_mock_run(
                    session, actor_id=int(actor_id)
                )
                session.commit()
                created.append(str(result.run_id))

    print(f"admin email: {FIXTURE_EMAIL}")
    print(f"admin password: {password}")
    print(f"previous runs kept: {existing}")
    for run_id in created:
        print(f"mock run: {run_id}")
    print("external calls: 0 (recorded mock pipeline only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
