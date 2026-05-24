from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.integration


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _run_alembic(args: list[str], schema: str, db_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = db_url
    env["SQLALCHEMY_DATABASE_URL"] = db_url
    existing = env.get("PGOPTIONS", "")
    env["PGOPTIONS"] = f"-c search_path={schema} {existing}".strip()
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture(scope="function")
def migrated_db(isolated_db, test_database_url):
    engine, schema = isolated_db
    result = _run_alembic(["upgrade", "head"], schema=schema, db_url=test_database_url)
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head 실패 (schema={schema})\n{result.stdout}\n{result.stderr}"
        )
    return engine, schema


def _insert_news(conn, *, source_url="https://example.com/a", filled=False):
    return conn.execute(
        text(
            """
            INSERT INTO news_article (
                source, source_url, original_title, original_summary,
                published_at, title_ko, summary_ko
            )
            VALUES (
                'ESPN', :source_url, 'Liverpool edge Arsenal in thriller',
                'Liverpool won after a late goal.', now(), :title_ko, :summary_ko
            )
            RETURNING id
            """
        ),
        {
            "source_url": source_url,
            "title_ko": "기존 제목" if filled else None,
            "summary_ko": "기존 요약" if filled else None,
        },
    ).scalar()


def test_nt_i01_cycle_updates_pending_news_article(migrated_db):
    from app.workers.news_translator.runner import run_cycle

    engine, _ = migrated_db
    with engine.begin() as conn:
        article_id = _insert_news(conn)

    translator = AsyncMock(
        return_value={
            "title_ko": "리버풀, 아스널에 극적 승리",
            "summary_ko": "리버풀이 막판 골로 승리했다.",
            "confidence": 0.9,
        }
    )

    with Session(engine) as session:
        result = asyncio.run(run_cycle(session, openai_client=translator))

    assert result.succeeded_count == 1
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT title_ko, summary_ko, translated_at "
                "FROM news_article WHERE id=:id"
            ),
            {"id": article_id},
        ).first()
    assert row.title_ko == "리버풀, 아스널에 극적 승리"
    assert row.summary_ko == "리버풀이 막판 골로 승리했다."
    assert row.translated_at is not None


def test_nt_i02_dry_run_does_not_update_db(migrated_db):
    from app.workers.news_translator.runner import run_cycle

    engine, _ = migrated_db
    with engine.begin() as conn:
        article_id = _insert_news(conn, source_url="https://example.com/dry")

    translator = AsyncMock(
        return_value={
            "title_ko": "드라이런 제목",
            "summary_ko": "드라이런 요약",
            "confidence": 0.7,
        }
    )

    with Session(engine) as session:
        result = asyncio.run(run_cycle(session, openai_client=translator, dry_run=True))

    assert result.succeeded_count == 1
    assert result.previews[0].title_ko == "드라이런 제목"
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT title_ko, summary_ko, translated_at FROM news_article WHERE id=:id"),
            {"id": article_id},
        ).first()
    assert row.title_ko is None
    assert row.summary_ko is None
    assert row.translated_at is None


def test_nt_i03_filled_row_is_not_reprocessed(migrated_db):
    from app.workers.news_translator.runner import run_cycle

    engine, _ = migrated_db
    with engine.begin() as conn:
        article_id = _insert_news(
            conn,
            source_url="https://example.com/filled",
            filled=True,
        )

    translator = AsyncMock(
        return_value={
            "title_ko": "새 제목",
            "summary_ko": "새 요약",
            "confidence": 1,
        }
    )
    with Session(engine) as session:
        result = asyncio.run(run_cycle(session, openai_client=translator))

    assert result.openai_calls == 0
    translator.assert_not_called()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT title_ko, summary_ko FROM news_article WHERE id=:id"),
            {"id": article_id},
        ).first()
    assert row.title_ko == "기존 제목"
    assert row.summary_ko == "기존 요약"
