"""Auth business logic for email signup and login."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, is_strong_password, verify_password
from app.models.app_user import AppUser


class AuthError(ValueError):
    code = "auth_error"


class EmailAlreadyRegistered(AuthError):
    code = "email_already_registered"


class WeakPassword(AuthError):
    code = "weak_password"


class InvalidCredentials(AuthError):
    code = "invalid_credentials"


class InactiveUser(AuthError):
    code = "inactive_user"


@dataclass(frozen=True)
class SignupInput:
    email: str
    password: str
    nickname: str | None = None


@dataclass(frozen=True)
class LoginInput:
    email: str
    password: str


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _clean_nickname(nickname: str | None) -> str | None:
    if nickname is None:
        return None
    value = nickname.strip()
    return value or None


def signup_user(session: Session, payload: SignupInput) -> AppUser:
    email = normalize_email(payload.email)
    if not is_strong_password(payload.password):
        raise WeakPassword("weak_password")

    existing = session.execute(
        select(AppUser.id).where(func.lower(AppUser.email) == email)
    ).first()
    if existing is not None:
        raise EmailAlreadyRegistered("email_already_registered")

    user = AppUser(
        email=email,
        password_hash=hash_password(payload.password),
        nickname=_clean_nickname(payload.nickname),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise EmailAlreadyRegistered("email_already_registered") from exc
    session.refresh(user)
    return user


def login_user(session: Session, payload: LoginInput) -> AppUser:
    email = normalize_email(payload.email)
    user = session.execute(
        select(AppUser).where(func.lower(AppUser.email) == email)
    ).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise InvalidCredentials("invalid_credentials")
    if not user.is_active:
        raise InactiveUser("inactive_user")

    user.last_login_at = datetime.now(UTC)
    session.commit()
    session.refresh(user)
    return user


def user_public_payload(user: AppUser) -> dict[str, object]:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "nickname": user.nickname,
        "is_active": user.is_active,
    }
