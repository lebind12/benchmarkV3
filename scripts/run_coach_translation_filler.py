"""Run translation-filler cycles until coach_translation is filled."""
from __future__ import annotations

import asyncio
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings, normalize_database_url
from app.workers.translation_filler.runner import run_cycle


def _pending_coaches(session: Session) -> int:
    return int(
        session.execute(
            text(
                """
                SELECT count(*)
                FROM coach_translation
                WHERE name_ko IS NULL OR short_name_ko IS NULL
                """
            )
        ).scalar_one()
    )


async def _run() -> None:
    try:
        from openai import AsyncOpenAI  # type: ignore
    except ImportError as exc:
        raise RuntimeError("openai package is required") from exc

    settings = get_settings()
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    cycles = 0
    with Session(engine) as session:
        while _pending_coaches(session) > 0:
            cycles += 1
            before = _pending_coaches(session)
            result = await run_cycle(session, openai_client=client, limit=50, semaphore=5)
            after = _pending_coaches(session)
            print(
                json.dumps(
                    {
                        "cycle": cycles,
                        "coach_pending_before": before,
                        "coach_pending_after": after,
                        "succeeded_count": result.succeeded_count,
                        "failed_count": result.failed_count,
                    },
                    ensure_ascii=False,
                )
            )
            if result.succeeded_count == 0:
                raise RuntimeError("coach translation did not make progress")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
