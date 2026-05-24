from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

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
    env["PGOPTIONS"] = f"-c search_path={schema} {env.get('PGOPTIONS', '')}".strip()
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=_project_root(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@pytest.fixture()
def migrated_db(isolated_db, test_database_url):
    engine, schema = isolated_db
    result = _run_alembic(["upgrade", "head"], schema=schema, db_url=test_database_url)
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head 실패\n{result.stdout}\n{result.stderr}")
    return engine, schema


def test_hn_i01_returns_latest_five_news_with_field_mapping(migrated_db):
    from app.services.home import list_home_news

    engine, _ = migrated_db
    with engine.begin() as conn:
        for idx in range(6):
            conn.execute(
                text(
                    "INSERT INTO news_article "
                    "(source, source_url, original_title, original_summary, published_at, "
                    "image_url, title_ko, summary_ko, tags) "
                    "VALUES (:source, :url, :title, :summary, :published, :image, :ko, "
                    ":summary_ko, CAST(:tags AS jsonb))"
                ),
                {
                    "source": "bbc.com",
                    "url": f"https://example.com/news/{idx}",
                    "title": f"Title {idx}",
                    "summary": f"Summary {idx}",
                    "published": f"2026-05-14T0{idx}:00:00Z",
                    "image": f"https://example.com/{idx}.jpg",
                    "ko": None if idx == 5 else f"제목 {idx}",
                    "summary_ko": f"요약 {idx}",
                    "tags": '{"teams":[33]}',
                },
            )

    with Session(engine) as session:
        payload = list_home_news(session)

    assert len(payload["items"]) == 5
    assert payload["items"][0]["title"] == "Title 5"
    assert payload["items"][0]["title_ko"] is None
    assert payload["items"][0]["url"] == "https://example.com/news/5"
    assert payload["items"][0]["thumbnail_url"] == "https://example.com/5.jpg"
