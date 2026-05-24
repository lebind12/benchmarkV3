"""One-shot ESPN RSS -> news_article cycle runner."""
from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.workers.news_fetcher import BATCH_LIMIT, RSS_URL
from app.workers.news_fetcher.matcher import (
    build_keyword_index,
    match_article,
    tags_json,
)
from app.workers.news_fetcher.rss import fetch_feed, parse_feed
from app.workers.news_fetcher.store import InsertResult, insert_article


@dataclass
class FetchCycleResult:
    cycle_started_at: str = ""
    duration_seconds: float = 0.0
    source_url: str = RSS_URL
    articles_fetched_total: int = 0
    articles_matched: int = 0
    articles_inserted: int = 0
    articles_duplicate: int = 0
    articles_skipped: int = 0
    dry_run: bool = False
    inserted: list[InsertResult] = field(default_factory=list)


async def run_cycle(
    session,
    *,
    limit: int = BATCH_LIMIT,
    dry_run: bool = False,
) -> FetchCycleResult:
    started = time.monotonic()
    result = FetchCycleResult(
        cycle_started_at=datetime.now(timezone.utc).isoformat(),
        dry_run=dry_run,
    )

    xml_text = await fetch_feed()
    items = parse_feed(xml_text)[:limit]
    result.articles_fetched_total = len(items)

    keywords = build_keyword_index(session)
    for item in items:
        matched = match_article(title=item.title, summary=item.summary, keywords=keywords)
        if not matched.matched:
            result.articles_skipped += 1
            continue
        result.articles_matched += 1
        tags = tags_json(matched.tags)

        if dry_run:
            result.inserted.append(InsertResult(True, item.url, item.title))
            continue

        insert_result = insert_article(session, item=item, tags=tags)
        if insert_result.inserted:
            result.articles_inserted += 1
            result.inserted.append(insert_result)
        else:
            result.articles_duplicate += 1

    if not dry_run:
        commit = getattr(session, "commit", None)
        if callable(commit):
            commit()

    result.duration_seconds = time.monotonic() - started
    _emit(result)
    return result


def result_to_dict(result: FetchCycleResult, *, include_items: bool = True) -> dict:
    payload = {
        "cycle_started_at": result.cycle_started_at,
        "duration_seconds": round(result.duration_seconds, 4),
        "source_url": result.source_url,
        "articles_fetched_total": result.articles_fetched_total,
        "articles_matched": result.articles_matched,
        "articles_inserted": result.articles_inserted,
        "articles_duplicate": result.articles_duplicate,
        "articles_skipped": result.articles_skipped,
        "dry_run": result.dry_run,
    }
    if include_items:
        payload["items"] = [item.__dict__ for item in result.inserted]
    return payload


def _emit(result: FetchCycleResult) -> None:
    try:
        sys.stdout.write(json.dumps(result_to_dict(result, include_items=False), ensure_ascii=False) + "\n")
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass
