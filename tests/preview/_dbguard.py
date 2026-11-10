"""테스트 DB 대상 검증.

테스트 픽스처는 매 테스트마다 `public` 스키마를 지운다. 그래서 대상을 여기서
먼저 검사한다. 허용 조건은 세 가지를 모두 만족해야 한다.

1. URL이 하나의 목적지를 확정한다. 쿼리 인자(`host`, `dbname`, `service` 등)로
   목적지를 덮어쓰거나, 여러 호스트를 나열하거나, 인코딩으로 값을 숨긴 URL은
   거부한다(`app/core/db_target.py`가 앱 설정과 같은 판정을 한다).
2. 엔드포인트가 루프백이다. 애플리케이션 설정의 `PREVIEW_ALLOW_NONLOCAL_DB`
   우회는 테스트에서 의도적으로 무시한다.
3. 데이터베이스 이름이 전용 테스트 DB로 보인다(`_test`로 끝나거나 `test_`로
   시작). 개발·운영 DB 이름은 여기서 거부된다.

이 모듈은 연결을 열지 않는다. URL 문자열과 지정한 환경변수만 검사한다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.core.db_target import AmbiguousDatabaseTarget, parse_database_target

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


def assert_safe_test_database(
    url: str, environ: Mapping[str, str] | None = None
) -> TestDatabase:
    """전용 로컬 테스트 DB가 아니면 연결 전에 실패한다."""
    try:
        target = parse_database_target(url, environ=environ)
    except AmbiguousDatabaseTarget as exc:
        raise UnsafeTestDatabase(f"tests refuse this database URL: {exc}") from None

    if not target.is_loopback:
        raise UnsafeTestDatabase(
            f"tests refuse non-loopback database host {target.host!r}; "
            "PREVIEW_ALLOW_NONLOCAL_DB does not apply to tests"
        )

    name = target.database
    if name in RESERVED_DATABASES or not _TEST_NAME.match(name):
        raise UnsafeTestDatabase(
            f"tests refuse database {name!r}: destructive test setup requires a "
            "dedicated test database named test_* or *_test"
        )

    return TestDatabase(host=target.host, port=target.port or 5432, name=name)
