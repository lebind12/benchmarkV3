"""Backfill broadcast momentum Redis state into Postgres.

Usage:
    .venv/bin/python scripts/persist_broadcast_momentum_from_redis.py
"""
from __future__ import annotations

import argparse
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.db import SessionLocal
from app.services.broadcast import _decode_cache_value
from app.services.broadcast_momentum_persistence import persist_broadcast_momentum_state


MOMENTUM_KEY_RE = re.compile(r"broadcast:fixture:(\d+):momentum:(last|samples|latest)$")


class UpstashScanner:
    def __init__(self, *, rest_url: str, token: str, key_prefix: str) -> None:
        self.rest_url = rest_url.rstrip("/")
        self.key_prefix = key_prefix
        self.client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=10.0)

    def command(self, *parts: Any) -> Any:
        response = self.client.post(self.rest_url, json=list(parts))
        response.raise_for_status()
        return response.json().get("result")

    def scan(self, *, pattern: str, count: int = 200) -> list[str]:
        cursor = "0"
        keys: list[str] = []
        while True:
            result = self.command("SCAN", cursor, "MATCH", pattern, "COUNT", count)
            if not isinstance(result, list) or len(result) != 2:
                raise RuntimeError(f"unexpected SCAN result: {result!r}")
            cursor = str(result[0])
            batch = result[1] if isinstance(result[1], list) else []
            keys.extend(str(key) for key in batch)
            if cursor == "0":
                return keys

    def get(self, key: str) -> Any:
        return _decode_cache_value(self.command("GET", key))


def _strip_prefix(key: str, prefix: str) -> str:
    if prefix and key.startswith(prefix):
        return key[len(prefix):]
    return key


def _fixture_ids(keys: list[str], prefix: str) -> set[int]:
    fixture_ids: set[int] = set()
    for key in keys:
        raw_key = _strip_prefix(key, prefix)
        match = MOMENTUM_KEY_RE.match(raw_key)
        if match:
            fixture_ids.add(int(match.group(1)))
    return fixture_ids


def _full_key(prefix: str, fixture_id: int, suffix: str) -> str:
    return f"{prefix}broadcast:fixture:{fixture_id}:momentum:{suffix}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture-id", type=int, help="Backfill one fixture only.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
        raise SystemExit("UPSTASH_REDIS_REST_URL/TOKEN are required")

    prefix = settings.upstash_redis_key_prefix or ""
    scanner = UpstashScanner(
        rest_url=settings.upstash_redis_rest_url,
        token=settings.upstash_redis_rest_token,
        key_prefix=prefix,
    )

    if args.fixture_id:
        fixture_ids = {args.fixture_id}
    else:
        pattern = f"{prefix}broadcast:fixture:*:momentum:*"
        fixture_ids = _fixture_ids(scanner.scan(pattern=pattern), prefix)

    persisted = 0
    with SessionLocal() as session:
        for fixture_id in sorted(fixture_ids):
            last_state = scanner.get(_full_key(prefix, fixture_id, "last"))
            samples = scanner.get(_full_key(prefix, fixture_id, "samples"))
            latest = scanner.get(_full_key(prefix, fixture_id, "latest"))
            if last_state is None and samples is None and latest is None:
                continue
            if args.dry_run:
                sample_count = len(samples) if isinstance(samples, list) else 0
                print(f"fixture={fixture_id} samples={sample_count} latest={isinstance(latest, dict)}")
                continue
            persist_broadcast_momentum_state(
                session,
                fixture_external_id=fixture_id,
                last_state=last_state,
                samples=samples,
                latest=latest,
                redis_key_prefix=prefix,
            )
            persisted += 1
        if not args.dry_run:
            session.commit()

    print(f"{'found' if args.dry_run else 'persisted'} fixtures={len(fixture_ids) if args.dry_run else persisted}")


if __name__ == "__main__":
    main()
