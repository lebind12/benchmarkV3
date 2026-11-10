"""로컬 개발용 관리자 계정 생성 도구.

비밀번호는 하드코딩하지 않는다. 대화형 입력(또는 파이프)으로만 받고,
실행 후에는 저장소에 남지 않는다. 운영 DB에는 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.auth.models import Role, User  # noqa: E402
from app.auth.service import hash_password  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db import get_session_factory  # noqa: E402

MIN_PASSWORD_LENGTH = 12


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
        description="Create a local development ADMIN account for the match preview app."
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
    settings.assert_local_database()

    password = _read_password(arguments)
    if len(password) < MIN_PASSWORD_LENGTH:
        raise SystemExit(f"password must be at least {MIN_PASSWORD_LENGTH} characters")

    email = arguments.email.strip().lower()
    password_hash = hash_password(password)

    with get_session_factory()() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is not None:
            if not arguments.reset_password:
                print(f"account already exists: {email} (use --reset-password to change it)")
                return 1
            user.password_hash = password_hash
            user.is_active = True
            user.role = Role.ADMIN.value
            session.commit()
            print(f"updated ADMIN account: {email}")
            return 0

        session.add(
            User(
                email=email,
                password_hash=password_hash,
                role=Role.ADMIN.value,
                is_active=True,
            )
        )
        session.commit()
        print(f"created ADMIN account: {email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
