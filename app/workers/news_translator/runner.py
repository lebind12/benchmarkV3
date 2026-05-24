"""Cycle runner for news-translator."""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

from app.workers.news_translator import (
    BATCH_LIMIT,
    SEMAPHORE,
    openai_client as openai_client_module,
    prompt as prompt_module,
    queue as queue_module,
)


@dataclass
class TranslationPreview:
    id: int
    source: str
    source_url: str
    original_title: str
    title_ko: str
    summary_ko: str
    confidence: float = 0.0


@dataclass
class CycleResult:
    cycle_started_at: str = ""
    duration_seconds: float = 0.0
    queue_size_at_start: int = 0
    processed_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0
    openai_calls: int = 0
    openai_errors: int = 0
    dry_run: bool = False
    cost_estimate_usd: float = 0.0
    previews: list[TranslationPreview] = field(default_factory=list)


_COST_PER_CALL_USD = 0.001

_UPDATE_SQL = text(
    """
    UPDATE news_article
    SET title_ko = COALESCE(title_ko, :title_ko),
        summary_ko = COALESCE(summary_ko, :summary_ko),
        translated_at = COALESCE(translated_at, now()),
        updated_at = now()
    WHERE id = :id
    """
)


async def _invoke_openai(openai_client: Any, messages: list[dict[str, str]]):
    if inspect.iscoroutinefunction(openai_client):
        return await openai_client(messages=messages)
    return await openai_client_module.call(messages=messages, client=openai_client)


async def run_cycle(
    session,
    *,
    openai_client: Any,
    limit: int = BATCH_LIMIT,
    semaphore: int = SEMAPHORE,
    dry_run: bool = False,
) -> CycleResult:
    """Run one news translation cycle.

    ``dry_run=True`` still reads rows and calls the supplied translator, but it
    does not update ``news_article``.
    """
    started = time.monotonic()
    result = CycleResult(
        cycle_started_at=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
    )
    raw_rows = queue_module.fetch_queue(session, limit=limit)
    rows = raw_rows[:limit]
    result.queue_size_at_start = len(raw_rows)

    if not rows:
        result.duration_seconds = time.monotonic() - started
        _emit(result)
        return result

    sem = asyncio.Semaphore(max(1, int(semaphore)))

    async def _handle(row: dict[str, Any]) -> None:
        try:
            messages = prompt_module.build_prompt(row)
        except Exception:  # noqa: BLE001 - bad row, retry next cycle
            result.failed_count += 1
            return

        async with sem:
            result.openai_calls += 1
            try:
                parsed = await _invoke_openai(openai_client, messages)
            except Exception:  # noqa: BLE001
                result.openai_errors += 1
                result.failed_count += 1
                return

        if not parsed:
            result.failed_count += 1
            return

        preview = TranslationPreview(
            id=int(row["id"]),
            source=str(row.get("source") or ""),
            source_url=str(row.get("source_url") or ""),
            original_title=str(row.get("original_title") or ""),
            title_ko=parsed["title_ko"],
            summary_ko=parsed["summary_ko"],
            confidence=float(parsed.get("confidence") or 0.0),
        )
        result.previews.append(preview)

        if not dry_run:
            try:
                session.execute(
                    _UPDATE_SQL,
                    {
                        "id": row["id"],
                        "title_ko": parsed["title_ko"],
                        "summary_ko": parsed["summary_ko"],
                    },
                )
                commit = getattr(session, "commit", None)
                if callable(commit):
                    commit()
            except Exception:  # noqa: BLE001 - DB failure, retry next cycle
                result.failed_count += 1
                return

        result.succeeded_count += 1

    await asyncio.gather(*(_handle(row) for row in rows))
    result.processed_count = result.succeeded_count + result.failed_count
    result.duration_seconds = time.monotonic() - started
    result.cost_estimate_usd = round(result.openai_calls * _COST_PER_CALL_USD, 6)
    _emit(result)
    return result


def result_to_dict(result: CycleResult, *, include_previews: bool = True) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cycle_started_at": result.cycle_started_at,
        "duration_seconds": round(result.duration_seconds, 4),
        "queue_size_at_start": result.queue_size_at_start,
        "processed_count": result.processed_count,
        "succeeded_count": result.succeeded_count,
        "failed_count": result.failed_count,
        "openai_calls": result.openai_calls,
        "openai_errors": result.openai_errors,
        "dry_run": result.dry_run,
        "cost_estimate_usd": result.cost_estimate_usd,
    }
    if include_previews:
        payload["previews"] = [preview.__dict__ for preview in result.previews]
    return payload


def _emit(result: CycleResult) -> None:
    try:
        sys.stdout.write(
            json.dumps(result_to_dict(result, include_previews=False), ensure_ascii=False)
            + "\n"
        )
        sys.stdout.flush()
    except Exception:  # noqa: BLE001 - logging must never crash a cycle
        pass


async def run() -> None:  # pragma: no cover - production scheduler path
    from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    try:
        from openai import AsyncOpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError("openai package is not installed - required for prod run().") from e

    settings = get_settings()
    engine = create_engine(
        normalize_database_url(settings.database_url),
        **database_engine_kwargs(settings),
    )
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        with Session(engine) as session:
            await run_cycle(session, openai_client=client)
    finally:
        engine.dispose()
