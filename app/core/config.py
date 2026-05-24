"""Application settings (pydantic-settings).

Loaded once at import; used by FastAPI, alembic, and workers. Values come
from ``.env`` (local) or process env (Koyeb / CI). Real secrets are never
checked in — see ``.env.example``.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralised env-driven configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database ---------------------------------------------------------
    # Supabase Postgres URL (or any libpq URL). alembic also reads this via
    # `app.core.config.get_settings().database_url`.
    database_url: str = Field(
        default="postgresql+psycopg://placeholder:placeholder@localhost:5432/placeholder",
        description="Primary DB URL (Supabase / local).",
    )

    # Integration test DB URL (separate from prod). Conftest skips integration
    # tests if unset.
    test_database_url: str | None = Field(default=None)
    db_pool_size: int = Field(
        default=2,
        ge=1,
        le=10,
        description="SQLAlchemy QueuePool size per process. Keep low for Supabase session pooler.",
    )
    db_max_overflow: int = Field(
        default=0,
        ge=0,
        le=10,
        description="Extra SQLAlchemy connections above db_pool_size.",
    )
    db_pool_timeout: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Seconds to wait for a pooled DB connection before failing.",
    )
    db_pool_recycle: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Seconds before recycling pooled DB connections.",
    )

    # --- External APIs ----------------------------------------------------
    api_football_key: str | None = Field(default=None)
    api_football_host: str = Field(default="v3.football.api-sports.io")
    api_football_concurrency: int = Field(
        default=6,
        ge=1,
        le=6,
        description="Max concurrent API-Football requests. Ultra plan is 450 req/min; keep <= 6.",
    )
    api_football_requests_per_minute: int = Field(
        default=300,
        ge=1,
        le=450,
        description="Paced API-Football request-start limit. Ultra plan hard cap is 450 req/min.",
    )

    # --- Cache / session helpers ------------------------------------------
    upstash_redis_rest_url: str | None = Field(default=None)
    upstash_redis_rest_token: str | None = Field(default=None)

    # --- OpenAI (translation-filler) --------------------------------------
    openai_api_key: str | None = Field(default=None)

    # --- Web clients -------------------------------------------------------
    cors_allow_origins: str = Field(
        default="*",
        description="Comma-separated origins allowed to call the API from browsers.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton accessor. ``lru_cache`` keeps env parsing one-shot per process."""
    return Settings()


def normalize_database_url(database_url: str) -> str:
    """Force libpq-style Postgres URLs onto the psycopg3 SQLAlchemy dialect."""
    if database_url.startswith("postgresql://"):
        return "postgresql+psycopg://" + database_url[len("postgresql://") :]
    if database_url.startswith("postgres://"):
        return "postgresql+psycopg://" + database_url[len("postgres://") :]
    return database_url


def database_engine_kwargs(settings: Settings | None = None) -> dict[str, object]:
    """Return SQLAlchemy engine options tuned for the Supabase session pooler."""
    resolved = settings or get_settings()
    return {
        "future": True,
        "pool_pre_ping": True,
        "pool_size": resolved.db_pool_size,
        "max_overflow": resolved.db_max_overflow,
        "pool_timeout": resolved.db_pool_timeout,
        "pool_recycle": resolved.db_pool_recycle,
    }
