"""Prompt builder for short Korean football-news summaries."""
from __future__ import annotations

import json
from typing import Any


_SYSTEM = (
    "당신은 영문 축구 뉴스를 한국어로 짧게 옮기는 스포츠 뉴스 편집자입니다. "
    "원문 전문을 재게시하지 말고, 사실 관계를 유지한 짧은 한국어 제목과 요약만 만드세요. "
    "선수/팀 이름은 한국 축구 중계와 기사에서 통용되는 표기를 우선합니다. "
    "응답은 JSON 만 출력하고 키는 title_ko, summary_ko, confidence 만 사용하세요."
)


def build_prompt(row: dict[str, Any]) -> list[dict[str, str]]:
    """Build a JSON-only chat prompt from a ``news_article`` queue row."""
    payload = {
        "source": row.get("source") or "",
        "source_url": row.get("source_url") or "",
        "original_title": row.get("original_title") or "",
        "original_summary": row.get("original_summary") or "",
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                "다음 축구 기사 메타데이터를 한국어로 간략히 정리하세요.\n"
                "- title_ko: 한국어 기사 제목처럼 자연스럽게, 80자 이내\n"
                "- summary_ko: 원문 요지 1문장, 160자 이내\n"
                "- 원문에 없는 사실, 점수, 이적료, 확정 표현을 추가하지 마세요.\n\n"
                f"입력:\n{json.dumps(payload, ensure_ascii=False)}\n\n"
                "출력(JSON):"
            ),
        },
    ]
