"""Copy broadcast momentum Redis keys from one prefix to another.

Usage:
    .venv/bin/python scripts/copy_broadcast_momentum_redis_prefix.py --source-prefix local: --target-prefix prod:
"""
from __future__ import annotations

import argparse
import re
from typing import Any

import httpx

from app.core.config import get_settings


MOMENTUM_KEY_RE = re.compile(r"broadcast:fixture:(\d+):momentum:(last|samples|latest)$")


class UpstashRest:
    def __init__(self, *, rest_url: str, token: str) -> None:
        self.rest_url = rest_url.rstrip("/")
        self.client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=15.0)

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


def _strip_prefix(key: str, prefix: str) -> str:
    return key[len(prefix) :] if prefix and key.startswith(prefix) else key


def _target_key(source_key: str, *, source_prefix: str, target_prefix: str) -> str | None:
    raw_key = _strip_prefix(source_key, source_prefix)
    return f"{target_prefix}{raw_key}" if MOMENTUM_KEY_RE.match(raw_key) else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-prefix", default="local:")
    parser.add_argument("--target-prefix", default="prod:")
    parser.add_argument("--fixture-id", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.upstash_redis_rest_url or not settings.upstash_redis_rest_token:
        raise SystemExit("UPSTASH_REDIS_REST_URL/TOKEN are required")

    redis = UpstashRest(
        rest_url=settings.upstash_redis_rest_url,
        token=settings.upstash_redis_rest_token,
    )
    pattern = (
        f"{args.source_prefix}broadcast:fixture:{args.fixture_id}:momentum:*"
        if args.fixture_id
        else f"{args.source_prefix}broadcast:fixture:*:momentum:*"
    )
    source_keys = sorted(redis.scan(pattern=pattern))
    copied = 0
    skipped = 0

    for source_key in source_keys:
        target_key = _target_key(
            source_key,
            source_prefix=args.source_prefix,
            target_prefix=args.target_prefix,
        )
        if not target_key:
            skipped += 1
            continue
        ttl_ms = redis.command("PTTL", source_key)
        value = redis.command("GET", source_key)
        if value is None:
            skipped += 1
            continue
        if not args.dry_run:
            if isinstance(ttl_ms, int) and ttl_ms > 0:
                redis.command("SET", target_key, value, "PX", ttl_ms)
            else:
                redis.command("SET", target_key, value)
        copied += 1

    print(f"{'would_copy' if args.dry_run else 'copied'} keys={copied} skipped={skipped}")


if __name__ == "__main__":
    main()
