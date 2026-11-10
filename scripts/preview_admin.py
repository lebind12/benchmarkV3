"""로컬 개발용 합성 관리자 계정 생성 도구.

기존 운영 계정 원장(`public.app_user`)과 같은 형태의 행을 **루프백 DB에만**
만든다. 비밀번호는 하드코딩하지 않는다. 대화형 입력(또는 파이프)으로만 받고,
실행 후에는 저장소에 남지 않는다.

이 도구는 운영 DB에 쓰지 않는다. `PREVIEW_ALLOW_NONLOCAL_DB=1`이 켜져 있어도
비루프백 대상은 거부한다.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.auth.passwords import hash_pbkdf2_sha256  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import get_engine, reset_engine  # noqa: E402

MIN_PASSWORD_LENGTH = 12

LOCAL_ACCOUNT_DDL = """
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


def _read_password(arguments: argparse.Namespace) -> str:
    if arguments.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
        if not password:
            raise SystemExit("no password on stdin")
        return password

    first = getpass.getpass("admin password: ")
    second = getpass.getpass("repeat password: ")
    if first != second:
        raise SystemExit("passwords do not match")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a local synthetic ADMIN account for the match preview app."
    )
    parser.add_argument("--email", required=True, help="admin login email")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from the first stdin line instead of prompting",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="replace the password hash of an existing account",
    )
    arguments = parser.parse_args(argv)

    settings = get_settings()
    if settings.env == "prod":
        raise SystemExit("refusing to create development accounts with PREVIEW_ENV=prod")
    target = settings.database_target
    # 이 도구는 로컬 합성 계정 전용이다. 우회 플래그와 무관하게 루프백만 허용한다.
    if not target.is_loopback:
        raise SystemExit(
            f"refusing to seed accounts on non-loopback host {target.host!r}"
        )

    password = _read_password(arguments)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    email = arguments.email.strip().lower()
    password_hash = hash_pbkdf2_sha256(password)

    reset_engine()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text(LOCAL_ACCOUNT_DDL))
        existing = conn.execute(
            text("SELECT id FROM public.app_user WHERE lower(email) = :email"),
            {"email": email},
        ).first()
        if existing is not None:
            if not arguments.reset_password:
                print(f"account already exists: {email} (use --reset-password to change it)")
                return 1
            conn.execute(
                text(
                    "UPDATE public.app_user SET password_hash = :h, role = 'ADMIN', "
                    "is_active = true, updated_at = now() WHERE id = :id"
                ),
                {"h": password_hash, "id": existing.id},
            )
            print(f"updated ADMIN account: {email}")
            return 0

        conn.execute(
            text(
                "INSERT INTO public.app_user (email, password_hash, role, is_active) "
                "VALUES (:email, :h, 'ADMIN', true)"
            ),
            {"email": email, "h": password_hash},
        )
        print(f"created ADMIN account: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
