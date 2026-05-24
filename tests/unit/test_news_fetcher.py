from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


RSS_SAMPLE = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title><![CDATA[Sources: City expect Guardiola exit after season]]></title>
  <description><![CDATA[Manchester City are resigned to losing Pep Guardiola.]]></description>
  <link><![CDATA[https://www.espn.com/soccer/story/_/id/1/city]]></link>
  <pubDate>Mon, 18 May 2026 19:19:30 EST</pubDate>
</item>
<item>
  <title><![CDATA[No link item]]></title>
</item>
</channel></rss>
"""


def test_nf_u01_parse_feed_extracts_items():
    from app.workers.news_fetcher.rss import parse_feed

    items = parse_feed(RSS_SAMPLE)
    assert len(items) == 1
    assert items[0].title == "Sources: City expect Guardiola exit after season"
    assert items[0].summary == "Manchester City are resigned to losing Pep Guardiola."
    assert items[0].url.endswith("/city")
    assert items[0].published_at.tzinfo is not None


def test_nf_u02_matcher_builds_tags():
    from app.workers.news_fetcher.matcher import Keyword, match_article

    result = match_article(
        title="Sources: City expect Guardiola exit after season",
        summary="Manchester City are resigned to losing Pep Guardiola.",
        keywords=[
            Keyword("Manchester City", "teams", 50),
            Keyword("Premier League", "leagues", 39),
            Keyword("Guardiola", "players", 1),
        ],
    )
    assert result.matched is True
    assert result.tags["teams"] == [50]
    assert result.tags["players"] == [1]


def test_nf_u03_store_insert_uses_conflict_do_nothing():
    from app.workers.news_fetcher.rss import RssItem
    from app.workers.news_fetcher.store import insert_article

    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = 123
    item = RssItem(
        title="Neymar named in Brazil final World Cup squad",
        summary="Brazil named Neymar.",
        url="https://example.com/neymar",
        published_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    )
    result = insert_article(session, item=item, tags={"leagues": [1]})
    assert result.inserted is True
    sql_text = str(getattr(session.execute.call_args.args[0], "text", ""))
    assert "ON CONFLICT (source_url) DO NOTHING" in sql_text
