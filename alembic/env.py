"""Alembic 실행 환경.

DB URL은 앱 설정에서 읽는다. 루프백이 아닌 DB는 기본적으로 거부되지만, 이는
앱 설정과 같은 `PREVIEW_ALLOW_NONLOCAL_DB=1`로 열린다. 마이그레이션에는 테스트
픽스처의 전용 테스트 DB 검사가 적용되지 않으므로, 운영 DB를 향하지 않도록
대상 URL을 직접 확인해야 한다.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    settings = get_settings()
    settings.assert_local_database()
    return settings.database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
