"""ESPN RSS fetch + parse helpers."""
from __future__ import annotations

import asyncio
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from app.workers.news_fetcher import (
    HTTP_TIMEOUT_SECONDS,
    RETRY_BACKOFF_BASE_SEC,
    RETRY_MAX,
    RSS_URL,
)


@dataclass(frozen=True)
class RssItem:
    title: str
    summary: str | None
    url: str
    published_at: datetime
    image_url: str | None = None


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_feed(xml_text: str) -> list[RssItem]:
    root = ET.fromstring(xml_text)
    items: list[RssItem] = []
    for item in root.findall("./channel/item"):
        title = _clean_text(item.findtext("title"))
        url = _clean_text(item.findtext("link"))
        if not title or not url:
            continue

        image_url = None
        enclosure = item.find("enclosure")
        if enclosure is not None:
            image_url = enclosure.attrib.get("url")

        items.append(
            RssItem(
                title=title,
                summary=_clean_text(item.findtext("description")) or None,
                url=url,
                published_at=_parse_datetime(item.findtext("pubDate")),
                image_url=image_url,
            )
        )
    return items


async def fetch_feed(*, url: str = RSS_URL, client: httpx.AsyncClient | None = None) -> str:
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
    try:
        for attempt in range(RETRY_MAX + 1):
            try:
                response = await http_client.get(
                    url,
                    headers={
                        "User-Agent": "benchmark-news-fetcher/0.1 (+RSS metadata only)",
                    },
                )
                response.raise_for_status()
                return response.text
            except Exception:  # noqa: BLE001 - transient HTTP path
                if attempt >= RETRY_MAX:
                    raise
                await asyncio.sleep(RETRY_BACKOFF_BASE_SEC * (2 ** attempt))
        raise RuntimeError("unreachable feed retry state")
    finally:
        if owns_client:
            await http_client.aclose()
