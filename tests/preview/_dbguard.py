"""테스트 DB 대상 검증.

테스트 픽스처는 매 테스트마다 `public` 스키마를 지운다. 그래서 대상을 여기서
먼저 검사한다. 허용 조건은 두 가지를 모두 만족해야 한다.

1. 엔드포인트가 루프백이다. 애플리케이션 설정의 `PREVIEW_ALLOW_NONLOCAL_DB`
   우회는 테스트에서 의도적으로 무시한다.
2. 데이터베이스 이름이 전용 테스트 DB로 보인다(`_test`로 끝나거나 `test_`로
   시작). 개발·운영 DB 이름은 여기서 거부된다.

이 모듈은 연결을 열지 않는다. 순수 문자열 검사만 한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# 공유 PostgreSQL 인스턴스에서 실수로 지우면 안 되는 기본 DB 이름들.
RESERVED_DATABASES = frozenset({"postgres", "template0", "template1", ""})

_TEST_NAME = re.compile(r"^(?:test_.*|.*_test|.*_tests)$")


class UnsafeTestDatabase(RuntimeError):
    """테스트 파괴적 준비 단계에 쓰면 안 되는 DB 대상."""


@dataclass(frozen=True)
class TestDatabase:
    host: str
    port: int
    name: str


def _database_name(url: str) -> str:
    return urlparse(url).path.lstrip("/")


def assert_safe_test_database(url: str) -> TestDatabase:
    """전용 로컬 테스트 DB가 아니면 연결 전에 실패한다."""
    parsed = urlparse(url)
    scheme = parsed.scheme or ""

    if not scheme.startswith("postgresql"):
        raise UnsafeTestDatabase(
            f"tests require a PostgreSQL URL, got scheme {scheme!r}"
        )

    host = parsed.hostname or ""
    if host not in LOOPBACK_HOSTS:
        raise UnsafeTestDatabase(
            f"tests refuse non-loopback database host {host!r}; "
            "PREVIEW_ALLOW_NONLOCAL_DB does not apply to tests"
        )

    name = _database_name(url)
    if name in RESERVED_DATABASES or not _TEST_NAME.match(name):
        raise UnsafeTestDatabase(
            f"tests refuse database {name!r}: destructive test setup requires a "
            "dedicated test database named test_* or *_test"
        )

    return TestDatabase(host=host, port=parsed.port or 5432, name=name)
