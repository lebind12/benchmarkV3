"""Persistence helpers for news-fetcher."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.workers.news_fetcher import SOURCE_NAME
from app.workers.news_fetcher.rss import RssItem


@dataclass
class InsertResult:
    inserted: bool
    source_url: str
    title: str


_INSERT_SQL = text(
    """
    INSERT INTO news_article (
        source,
        source_url,
        original_title,
        original_summary,
        published_at,
        image_url,
        tags,
        created_at,
        updated_at
    )
    VALUES (
        :source,
        :source_url,
        :original_title,
        :original_summary,
        :published_at,
        :image_url,
        CAST(:tags AS jsonb),
        now(),
        now()
    )
    ON CONFLICT (source_url) DO NOTHING
    RETURNING id
    """
)


def insert_article(session, *, item: RssItem, tags: dict[str, Any]) -> InsertResult:
    row_id = session.execute(
        _INSERT_SQL,
        {
            "source": SOURCE_NAME,
            "source_url": item.url,
            "original_title": item.title,
            "original_summary": item.summary,
            "published_at": item.published_at,
            "image_url": item.image_url,
            "tags": __import__("json").dumps(tags, ensure_ascii=False),
        },
    ).scalar_one_or_none()
    return InsertResult(inserted=row_id is not None, source_url=item.url, title=item.title)
