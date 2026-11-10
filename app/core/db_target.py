"""DB URL이 실제로 어디에 연결되는지 확정한다.

앱의 로컬 검사와 테스트의 파괴적 준비 가드가 같은 판정을 쓰도록 한 곳에 둔다.
`urlparse`의 호스트·경로만 보면 부족하다. libpq는 쿼리 인자(`host`, `dbname`,
`service` 등)로 목적지를 덮어쓰고, SQLAlchemy psycopg dialect는 그 값을 그대로
연결 인자로 넘긴다. 그래서 목적지를 하나로 확정할 수 없는 URL은 연결 전에
거부한다. 거부는 fail-closed다. 허용 목록에 없는 형태를 통과시키지 않는다.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

# 목적지를 바꾸는 libpq 키워드. 연결 방식(sslmode 등)만 바꾸는 키워드는 여기 없다.
DESTINATION_KEYWORDS = frozenset(
    {"host", "hostaddr", "port", "dbname", "database", "service"}
)


def normalize_driver(url: str) -> str:
    """`postgresql://`를 이 환경에 설치된 psycopg(3) 드라이버로 고정한다.

    운영 설정의 값은 드라이버를 지정하지 않은 `postgresql://` 형식이다. 그대로
    두면 SQLAlchemy가 설치되지 않은 psycopg2를 찾는다. 값을 바꾸지 않고 스킴만
    명시한다. 확정 가능성 판정은 `parse_database_target`이 그대로 담당한다.
    """
    for plain in ("postgresql://", "postgres://"):
        if url.startswith(plain):
            return "postgresql+psycopg://" + url[len(plain):]
    return url


class AmbiguousDatabaseTarget(ValueError):
    """URL만으로 연결 목적지가 하나로 확정되지 않는다."""


@dataclass(frozen=True)
class DatabaseTarget:
    host: str
    port: int | None
    database: str

    @property
    def is_loopback(self) -> bool:
        return self.host in LOOPBACK_HOSTS

    def describe(self) -> str:
        return f"{self.host}:{self.port or 5432}/{self.database}"


def _reject(message: str) -> AmbiguousDatabaseTarget:
    return AmbiguousDatabaseTarget(f"ambiguous database target: {message}")


def parse_database_target(
    url: str, environ: Mapping[str, str] | None = None
) -> DatabaseTarget:
    """확정 가능한 목적지만 돌려준다. 아니면 `AmbiguousDatabaseTarget`."""
    try:
        parsed = make_url(url)
        host = parsed.host or ""
        database = parsed.database or ""
        query = dict(parsed.query)
        port = parsed.port
    except (ArgumentError, ValueError) as exc:
        # 원본 문자열에는 비밀번호가 들어 있다. 오류 메시지에 옮기지 않는다.
        raise _reject("the URL cannot be parsed") from None

    if not parsed.drivername.startswith("postgresql"):
        raise _reject(
            f"scheme {parsed.drivername!r} is not PostgreSQL; SQLite is not a substitute"
        )

    if not host:
        raise _reject("the URL does not name a host")
    if "," in host:
        raise _reject(f"host {host!r} lists several servers; name exactly one")
    if "%" in host:
        raise _reject(f"host {host!r} is percent-encoded; write the host literally")

    if not database:
        raise _reject("the URL does not name a database")
    if "," in database or "/" in database or "%" in database or ";" in database:
        raise _reject(f"database {database!r} is not a single plain name")

    for key, value in query.items():
        if key.lower() in DESTINATION_KEYWORDS:
            raise _reject(
                f"query parameter {key!r} overrides the connection destination; "
                "put the host, port, and database in the URL itself"
            )
        if not isinstance(value, str):
            raise _reject(
                f"query parameter {key!r} is repeated; one value per parameter"
            )

    env = os.environ if environ is None else environ
    if env.get("PGHOSTADDR"):
        raise _reject(
            "libpq PGHOSTADDR is set and replaces the URL host at connect time; "
            "unset it before connecting"
        )

    return DatabaseTarget(host=host, port=port, database=database)
