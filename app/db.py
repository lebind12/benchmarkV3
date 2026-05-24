"""Database session helpers."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url


def make_engine():
    settings = get_settings()
    return create_engine(
        normalize_database_url(settings.database_url),
        **database_engine_kwargs(settings),
    )


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
