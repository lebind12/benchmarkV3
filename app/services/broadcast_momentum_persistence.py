"""Persistence helpers for Redis-backed broadcast momentum state."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.broadcast import _cache_get


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _momentum_key(fixture_external_id: int, suffix: str) -> str:
    return f"broadcast:fixture:{fixture_external_id}:momentum:{suffix}"


def momentum_cache_key(fixture_external_id: int, suffix: str) -> str:
    return _momentum_key(fixture_external_id, suffix)


def _sample_count(samples: Any) -> int:
    return len(samples) if isinstance(samples, list) else 0


def _redis_prefix() -> str:
    return get_settings().upstash_redis_key_prefix or ""


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def persist_broadcast_momentum_state(
    session: Session,
    *,
    fixture_external_id: int,
    last_state: Any,
    samples: Any,
    latest: Any,
    redis_key_prefix: str | None = None,
) -> None:
    """Upsert one fixture's momentum state.

    The payload intentionally mirrors Redis JSON. Broadcast live fixtures can be
    outside the curated DB fixture table, so this table stores API-Football's
    fixture id directly and does not use an FK.
    """
    if not isinstance(fixture_external_id, int) or fixture_external_id <= 0:
        return
    if not isinstance(samples, list):
        samples = []
    if not isinstance(last_state, dict):
        last_state = None
    if not isinstance(latest, dict):
        latest = None

    session.execute(
        text(
            """
            INSERT INTO broadcast_momentum_state (
                fixture_external_id,
                redis_key_prefix,
                last_state,
                samples,
                latest,
                sample_count,
                latest_updated_at,
                last_captured_at,
                persisted_at,
                updated_at
            )
            VALUES (
                :fixture_external_id,
                :redis_key_prefix,
                CAST(:last_state AS jsonb),
                CAST(:samples AS jsonb),
                CAST(:latest AS jsonb),
                :sample_count,
                :latest_updated_at,
                :last_captured_at,
                now(),
                now()
            )
            ON CONFLICT (fixture_external_id, redis_key_prefix)
            DO UPDATE SET
                last_state = EXCLUDED.last_state,
                samples = EXCLUDED.samples,
                latest = EXCLUDED.latest,
                sample_count = EXCLUDED.sample_count,
                latest_updated_at = EXCLUDED.latest_updated_at,
                last_captured_at = EXCLUDED.last_captured_at,
                persisted_at = now(),
                updated_at = now()
            """
        ),
        {
            "fixture_external_id": fixture_external_id,
            "redis_key_prefix": redis_key_prefix if redis_key_prefix is not None else _redis_prefix(),
            "last_state": _json(last_state),
            "samples": _json(samples),
            "latest": _json(latest),
            "sample_count": _sample_count(samples),
            "latest_updated_at": _parse_iso(latest.get("updatedAt") if latest else None),
            "last_captured_at": _parse_iso(last_state.get("capturedAt") if last_state else None),
        },
    )


def persist_broadcast_momentum_from_cache(
    session: Session,
    cache: Any,
    *,
    fixture_external_id: int,
    latest: Any | None = None,
    redis_key_prefix: str | None = None,
) -> None:
    """Read Redis momentum keys through the cache adapter and upsert them."""
    last_state = _cache_get(cache, _momentum_key(fixture_external_id, "last"))
    samples = _cache_get(cache, _momentum_key(fixture_external_id, "samples"))
    latest_payload = latest if latest is not None else _cache_get(
        cache,
        _momentum_key(fixture_external_id, "latest"),
    )
    persist_broadcast_momentum_state(
        session,
        fixture_external_id=fixture_external_id,
        last_state=last_state,
        samples=samples,
        latest=latest_payload,
        redis_key_prefix=redis_key_prefix,
    )


def load_persisted_broadcast_momentum_latest(
    session: Session,
    *,
    fixture_external_id: int,
    redis_key_prefix: str | None = None,
) -> dict[str, Any] | None:
    """Return persisted latest momentum payload for a fixture, if available."""
    if not isinstance(fixture_external_id, int) or fixture_external_id <= 0:
        return None
    row = session.execute(
        text(
            """
            SELECT latest
            FROM broadcast_momentum_state
            WHERE fixture_external_id = :fixture_external_id
              AND redis_key_prefix = :redis_key_prefix
              AND latest IS NOT NULL
            ORDER BY persisted_at DESC
            LIMIT 1
            """
        ),
        {
            "fixture_external_id": fixture_external_id,
            "redis_key_prefix": redis_key_prefix if redis_key_prefix is not None else _redis_prefix(),
        },
    ).scalar_one_or_none()
    return row if isinstance(row, dict) else None


def load_persisted_broadcast_momentum_samples(
    session: Session,
    *,
    fixture_external_id: int,
    redis_key_prefix: str | None = None,
) -> list[dict[str, Any]]:
    """Return persisted momentum samples for a fixture."""
    if not isinstance(fixture_external_id, int) or fixture_external_id <= 0:
        return []
    row = session.execute(
        text(
            """
            SELECT samples
            FROM broadcast_momentum_state
            WHERE fixture_external_id = :fixture_external_id
              AND redis_key_prefix = :redis_key_prefix
              AND samples IS NOT NULL
            ORDER BY persisted_at DESC
            LIMIT 1
            """
        ),
        {
            "fixture_external_id": fixture_external_id,
            "redis_key_prefix": redis_key_prefix if redis_key_prefix is not None else _redis_prefix(),
        },
    ).scalar_one_or_none()
    return row if isinstance(row, list) else []
