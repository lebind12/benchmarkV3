"""기존 운영 계정의 비밀번호 해시 검증.

운영 `app_user.password_hash`는 `pbkdf2_sha256$<iterations>$<salt>$<digest>`
형식이다(2026-11-10 읽기 전용 메타데이터로 확인: 8건 모두 260000회). 이 모듈은
그 형식만 다룬다. 지원하지 않는 형식은 예외 대신 `False`로 거부한다.

비밀번호 원문은 어디에도 저장·기록하지 않는다.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os

PASSWORD_SCHEME = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 260_000
_SALT_BYTES = 16

__all__ = [
    "PASSWORD_SCHEME",
    "hash_pbkdf2_sha256",
    "verify_pbkdf2_sha256",
    "DUMMY_PASSWORD_HASH",
]


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("ascii"))


def hash_pbkdf2_sha256(password: str, iterations: int = DEFAULT_ITERATIONS) -> str:
    """합성 테스트 입력용. 운영 계정 해시는 이 앱이 만들지 않는다."""
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"{PASSWORD_SCHEME}${iterations}${_b64encode(salt)}${_b64encode(digest)}"


def verify_pbkdf2_sha256(password: str, stored_hash: str) -> bool:
    """기존 형식만 검증한다. 파싱 실패·미지원 형식은 `False`다."""
    if not isinstance(stored_hash, str):
        return False
    try:
        scheme, iterations_raw, salt_raw, digest_raw = stored_hash.split("$", 3)
    except ValueError:
        return False
    if scheme != PASSWORD_SCHEME:
        return False
    try:
        iterations = int(iterations_raw)
        salt = _b64decode(salt_raw)
        expected = _b64decode(digest_raw)
    except (ValueError, TypeError, binascii.Error):
        return False
    if iterations <= 0 or not salt or not expected:
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


# 없는 계정에도 같은 비용의 검증을 수행해 응답 시간으로 계정 존재 여부를
# 알아내지 못하게 한다. 값은 테스트·타이밍 전용이며 어떤 계정의 해시도 아니다.
DUMMY_PASSWORD_HASH = hash_pbkdf2_sha256("dummy-password-for-timing-equalisation")
