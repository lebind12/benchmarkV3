"""애플리케이션 설정.

MP-01은 격리된 로컬 개발용 DB만 대상으로 한다. 프로덕션/클라우드 DB 연결은
이 범위가 아니므로, 루프백이 아닌 주소는 명시적 허용 플래그 없이는 거부한다.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "test", "prod"]

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PREVIEW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp01_dev"
    )
    env: Environment = "dev"
    session_ttl_seconds: int = Field(default=8 * 60 * 60, gt=0, le=7 * 24 * 60 * 60)
    cookie_secure: bool = False
    allow_nonlocal_db: bool = False

    @field_validator("database_url")
    @classmethod
    def _require_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError(
                "PREVIEW_DATABASE_URL must be a PostgreSQL URL; SQLite is not a supported substitute"
            )
        return value

    @property
    def database_host(self) -> str:
        return urlparse(self.database_url).hostname or ""

    @property
    def is_loopback_database(self) -> bool:
        return self.database_host in LOOPBACK_HOSTS

    def assert_local_database(self) -> None:
        """로컬 개발 범위를 벗어난 DB 연결을 조용히 허용하지 않는다."""
        if self.is_loopback_database or self.allow_nonlocal_db:
            return
        raise RuntimeError(
            "Refusing to connect to a non-loopback database "
            f"({self.database_host}); MP-01 is limited to isolated local development. "
            "Set PREVIEW_ALLOW_NONLOCAL_DB=1 only if that is deliberate."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
