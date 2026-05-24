"""Queue lookup for news_article rows pending Korean translation."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text


_QUEUE_SQL_TEMPLATE = """
SELECT id,
       source,
       source_url,
       original_title,
       original_summary,
       published_at
FROM news_article
WHERE title_ko IS NULL OR summary_ko IS NULL
ORDER BY published_at DESC, id DESC
LIMIT {limit}
"""


def _build_sql(*, limit: int) -> str:
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"limit must be a positive int, got {limit!r}")
    return _QUEUE_SQL_TEMPLATE.format(limit=limit)


def fetch_queue(session, *, limit: int) -> list[dict[str, Any]]:
    """Return pending news rows as plain dicts."""
    result = session.execute(text(_build_sql(limit=limit)))
    rows = result.all()
    out: list[dict[str, Any]] = []
    for row in rows:
        mapping = getattr(row, "_mapping", None)
        if mapping is not None:
            out.append(dict(mapping))
            continue
        out.append(
            {
                "id": getattr(row, "id", None),
                "source": getattr(row, "source", None),
                "source_url": getattr(row, "source_url", None),
                "original_title": getattr(row, "original_title", None),
                "original_summary": getattr(row, "original_summary", None),
                "published_at": getattr(row, "published_at", None),
            }
        )
    return out
