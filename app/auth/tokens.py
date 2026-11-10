"""세션 토큰 해시.

원문 토큰은 쿠키에만 있고 DB에는 SHA-256 해시만 남긴다. 로컬 인증과 운영 계정
인증이 같은 규칙을 쓰도록 한 곳에 둔다.
"""

from __future__ import annotations

import hashlib


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


__all__ = ["hash_session_token"]
