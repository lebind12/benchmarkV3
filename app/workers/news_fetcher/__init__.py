"""news-fetcher worker.

ESPN Soccer RSS -> ``news_article`` metadata rows. This worker never fetches
article bodies; it stores only title, summary, source URL, publish time, and
keyword tags for downstream short Korean summarisation.
"""
from __future__ import annotations

RSS_URL = "https://www.espn.com/espn/rss/soccer/news"
SOURCE_NAME = "ESPN"
BATCH_LIMIT = 50
HTTP_TIMEOUT_SECONDS = 15.0
RETRY_MAX = 3
RETRY_BACKOFF_BASE_SEC = 1

# Target competitions from AGENTS.md plus World Cup. news_article.tags is JSONB
# and intentionally has no FK, so these IDs can be used before league rows exist.
TARGET_LEAGUE_KEYWORDS: dict[int, tuple[str, ...]] = {
    1: ("FIFA World Cup", "World Cup"),
    2: ("UEFA Champions League", "Champions League"),
    3: ("UEFA Europa League", "Europa League"),
    39: ("Premier League",),
    45: ("FA Cup",),
    48: ("Carabao Cup", "League Cup"),
}
