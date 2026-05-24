"""OpenAI client wrapper for news-translator."""
from __future__ import annotations

import asyncio
import json
from typing import Any

from app.workers.news_translator import (
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    RETRY_BACKOFF_BASE_SEC,
    RETRY_MAX,
)


def parse_response(content: str | None) -> dict[str, Any] | None:
    """Parse and validate the JSON object returned by the model."""
    if not content:
        return None
    try:
        data = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    title_ko = data.get("title_ko")
    summary_ko = data.get("summary_ko")
    if not isinstance(title_ko, str) or not title_ko.strip():
        return None
    if not isinstance(summary_ko, str) or not summary_ko.strip():
        return None

    confidence = data.get("confidence", 0.0)
    try:
        confidence_float = float(confidence)
    except (TypeError, ValueError):
        confidence_float = 0.0
    confidence_float = max(0.0, min(1.0, confidence_float))

    return {
        "title_ko": title_ko.strip(),
        "summary_ko": summary_ko.strip(),
        "confidence": confidence_float,
    }


async def call(
    messages: list[dict[str, Any]],
    *,
    client: Any,
) -> dict[str, Any] | None:
    """Call chat completions with retry/backoff and strict JSON parsing."""
    api_messages = [m for m in messages if isinstance(m, dict) and "role" in m]
    for attempt in range(RETRY_MAX + 1):
        try:
            response = await client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=OPENAI_TEMPERATURE,
                max_tokens=OPENAI_MAX_TOKENS,
                response_format={"type": "json_object"},
                messages=api_messages,
            )
        except Exception:  # noqa: BLE001 - transient API/client failure
            if attempt >= RETRY_MAX:
                return None
            await asyncio.sleep(RETRY_BACKOFF_BASE_SEC * (2 ** attempt))
            continue

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            return None
        return parse_response(content)

    return None
