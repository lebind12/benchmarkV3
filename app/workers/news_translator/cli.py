"""CLI entrypoint for news-translator dry-runs and manual cycles."""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
from app.workers.news_translator.runner import result_to_dict, run_cycle


async def _mock_translator(*, messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic local translator for DB/drift dry-runs without OpenAI."""
    user = next((m for m in messages if m.get("role") == "user"), {})
    content = str(user.get("content") or "")
    marker = "입력:\n"
    payload: dict[str, Any] = {}
    if marker in content:
        raw = content.split(marker, 1)[1].split("\n\n", 1)[0]
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
    title = str(payload.get("original_title") or "축구 뉴스").strip()
    summary = str(payload.get("original_summary") or title).strip()
    return {
        "title_ko": f"[드라이런] {title[:70]}",
        "summary_ko": f"[드라이런] {summary[:140]}",
        "confidence": 0.0,
    }


async def _main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_engine(
        normalize_database_url(settings.database_url),
        **database_engine_kwargs(settings),
    )

    if args.mock:
        client = _mock_translator
    else:
        try:
            from openai import AsyncOpenAI  # type: ignore
        except ImportError as e:
            raise SystemExit("openai package is not installed. Use --mock for dry-run.") from e
        client = AsyncOpenAI(api_key=settings.openai_api_key)

    try:
        with Session(engine) as session:
            result = await run_cycle(
                session,
                openai_client=client,
                limit=args.limit,
                semaphore=args.semaphore,
                dry_run=args.dry_run,
            )
    finally:
        engine.dispose()

    print(json.dumps(result_to_dict(result), ensure_ascii=False, default=str, indent=2))
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the news-translator worker once.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--semaphore", type=int, default=5)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read rows and generate output without updating DB.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic local output instead of calling OpenAI.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_main_async(args)))


if __name__ == "__main__":
    main()
