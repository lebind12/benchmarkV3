"""Privileged manual news extraction, with no persistence or URL retrieval."""
import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app import db
from app.core.config import get_settings
from app.core.sessions import manager_user
from app.models import AppUser
from app.services.news_analysis import limiter, link_mentions, validate_source_url
from app.services.news_analysis_vertex import NewsVertexProvider

router = APIRouter(prefix="/api/v1/admin/management/news", tags=["news-analysis"])


class AnalyzeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    article_text: str = Field(min_length=1, max_length=20000)
    source_url: str = Field(min_length=1, max_length=2048)

    @field_validator("article_text")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("기사 텍스트를 입력하세요.")
        return value

    @field_validator("source_url")
    @classmethod
    def source(cls, value):
        return validate_source_url(value)


def extract_bounded(article):
    # The worker retains its slot even if the waiting HTTP request times out.
    if not limiter.slots.acquire(blocking=False):
        raise HTTPException(429, "다른 분석이 진행 중입니다. 잠시 후 다시 시도하세요.", headers={"Retry-After": "60"})
    try:
        return NewsVertexProvider().extract(article)
    finally:
        limiter.slots.release()


@router.post("/analyze")
async def analyze(
    body: AnalyzeInput,
    user: Annotated[AppUser, Depends(manager_user)],
    session: Annotated[Session, Depends(db.get_db_session)],
):
    if not limiter.admit(user.id):
        raise HTTPException(429, "분당 3회까지 분석할 수 있습니다. 잠시 후 다시 시도하세요.", headers={"Retry-After": "60"})
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(extract_bounded, body.article_text),
            timeout=get_settings().news_analysis_timeout_seconds,
        )
        return link_mentions(session, body.article_text, body.source_url, payload)
    except (TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "분석 시간이 초과되었습니다. 입력을 유지하고 다시 시도하세요.") from None
    except HTTPException:
        raise
    except Exception:
        # Do not expose provider responses, article text, credentials or SQL details.
        raise HTTPException(503, "분석을 완료하지 못했습니다. 잠시 후 다시 시도하세요.") from None
