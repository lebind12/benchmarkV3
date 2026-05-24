"""CLI entrypoint for ESPN news fetcher."""
from __future__ import annotations

import argparse
import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
from app.workers.news_fetcher.runner import result_to_dict, run_cycle


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(
        normalize_database_url(settings.database_url),
        **database_engine_kwargs(settings),
    )
    try:
        with Session(engine) as session:
            result = await run_cycle(session, limit=args.limit, dry_run=args.dry_run)
    finally:
        engine.dispose()
    print(json.dumps(result_to_dict(result), ensure_ascii=False, default=str, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ESPN Soccer RSS into news_article.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
