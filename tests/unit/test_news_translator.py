from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def _import_module():
    from app.workers import news_translator  # noqa: F401
    from app.workers.news_translator import openai_client, prompt, queue, runner

    return {
        "news_translator": news_translator,
        "queue": queue,
        "prompt": prompt,
        "openai_client": openai_client,
        "runner": runner,
    }


@pytest.fixture(scope="module")
def mods():
    return _import_module()


def test_nt_u01_queue_sql_targets_pending_news_rows(mods):
    session = MagicMock()
    session.execute.return_value.all.return_value = []
    assert mods["queue"].fetch_queue(session, limit=50) == []
    args, _ = session.execute.call_args
    sql_text = str(getattr(args[0], "text", args[0])).lower()
    assert "from news_article" in sql_text
    assert "title_ko is null or summary_ko is null" in sql_text
    assert "order by published_at desc" in sql_text
    assert "limit 50" in sql_text


def test_nt_u02_prompt_contains_original_title_and_summary(mods):
    messages = mods["prompt"].build_prompt(
        {
            "source": "ESPN",
            "source_url": "https://example.com/a",
            "original_title": "Liverpool edge Arsenal in thriller",
            "original_summary": "Liverpool won after a late goal.",
        }
    )
    blob = json.dumps(messages, ensure_ascii=False)
    assert "Liverpool edge Arsenal" in blob
    assert "Liverpool won after a late goal" in blob
    assert "title_ko" in blob and "summary_ko" in blob
    assert "JSON" in blob


def test_nt_u03_parse_valid_response(mods):
    parsed = mods["openai_client"].parse_response(
        '{"title_ko":"리버풀, 아스널에 극적 승리","summary_ko":"리버풀이 막판 골로 승리했다.","confidence":0.9}'
    )
    assert parsed == {
        "title_ko": "리버풀, 아스널에 극적 승리",
        "summary_ko": "리버풀이 막판 골로 승리했다.",
        "confidence": 0.9,
    }


def test_nt_u03_parse_invalid_response(mods):
    assert mods["openai_client"].parse_response("not json") is None
    assert mods["openai_client"].parse_response('{"title_ko":"제목"}') is None


def test_nt_u04_openai_call_parameters(mods):
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(
        return_value=MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"title_ko":"A","summary_ko":"B","confidence":1}'
                    )
                )
            ]
        )
    )
    asyncio.run(
        mods["openai_client"].call(
            messages=[{"role": "user", "content": "x"}], client=fake_client
        )
    )
    kwargs = fake_client.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-3.5-turbo"
    assert kwargs["temperature"] == 0.3
    assert kwargs["max_tokens"] == 400
    assert kwargs["response_format"] == {"type": "json_object"}


def test_nt_u05_dry_run_generates_preview_without_update(mods):
    queue_mod = mods["queue"]
    rows = [
        {
            "id": 1,
            "source": "ESPN",
            "source_url": "https://example.com/a",
            "original_title": "Title",
            "original_summary": "Summary",
        }
    ]
    session = MagicMock()
    openai_mock = AsyncMock(
        return_value={"title_ko": "제목", "summary_ko": "요약", "confidence": 0.8}
    )
    with patch.object(queue_mod, "fetch_queue", return_value=rows):
        result = asyncio.run(
            mods["runner"].run_cycle(
                session,
                openai_client=openai_mock,
                dry_run=True,
            )
        )
    assert result.succeeded_count == 1
    assert result.previews[0].title_ko == "제목"
    session.execute.assert_not_called()


def test_nt_u06_apply_updates_news_article_without_overwrite(mods):
    queue_mod = mods["queue"]
    rows = [
        {
            "id": 1,
            "source": "ESPN",
            "source_url": "https://example.com/a",
            "original_title": "Title",
            "original_summary": "Summary",
        }
    ]
    session = MagicMock()
    openai_mock = AsyncMock(
        return_value={"title_ko": "제목", "summary_ko": "요약", "confidence": 0.8}
    )
    with patch.object(queue_mod, "fetch_queue", return_value=rows):
        result = asyncio.run(
            mods["runner"].run_cycle(
                session,
                openai_client=openai_mock,
                dry_run=False,
            )
        )
    assert result.succeeded_count == 1
    session.execute.assert_called_once()
    sql_text = str(getattr(session.execute.call_args.args[0], "text", ""))
    assert "COALESCE(title_ko" in sql_text
    assert "COALESCE(summary_ko" in sql_text
    session.commit.assert_called_once()


def test_nt_u07_exponential_backoff_1_2_4(mods):
    fake_client = MagicMock()
    fake_client.chat.completions.create = AsyncMock(side_effect=Exception("OpenAI 5xx"))
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    with patch("asyncio.sleep", side_effect=fake_sleep):
        parsed = asyncio.run(
            mods["openai_client"].call(
                messages=[{"role": "user", "content": "x"}], client=fake_client
            )
        )
    assert parsed is None
    assert sleeps[:3] == [1, 2, 4]
