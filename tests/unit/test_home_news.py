from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.unit


def _item(*, title_ko="리버풀, 막판 동점골로 무승부"):
    return {
        "id": "n1",
        "title_ko": title_ko,
        "title": "Liverpool snatch late equalizer",
        "summary_ko": "리버풀이 후반 추가시간 동점골로 1-1 무승부를 거뒀다.",
        "source": "bbc.com",
        "url": "https://example.com/news/1",
        "thumbnail_url": None,
        "published_at": "2026-05-14T08:00:00Z",
    }


@pytest.fixture()
def client():
    return TestClient(app)


def _patch_service(monkeypatch, payload):
    from app.services import home as home_service

    mock = MagicMock(return_value=payload)
    monkeypatch.setattr(home_service, "list_home_news", mock, raising=False)
    try:
        from app.api import home as home_router

        monkeypatch.setattr(home_router, "list_home_news", mock, raising=False)
    except ImportError:
        pass
    return mock


def test_hn_u01_public_endpoint_returns_news_shape(client, monkeypatch):
    service = _patch_service(monkeypatch, {"items": [_item()]})

    response = client.get("/api/v1/home/news")

    assert response.status_code == 200
    assert response.json()["items"][0]["source"] == "bbc.com"
    assert response.json()["items"][0]["url"].startswith("https://")
    assert service.call_count == 1


def test_hn_u02_title_ko_null_is_allowed_for_fe_fallback(client, monkeypatch):
    _patch_service(monkeypatch, {"items": [_item(title_ko=None)]})

    response = client.get("/api/v1/home/news")

    assert response.status_code == 200
    assert response.json()["items"][0]["title_ko"] is None
    assert response.json()["items"][0]["title"] == "Liverpool snatch late equalizer"


def test_hn_u03_empty_items_are_valid(client, monkeypatch):
    _patch_service(monkeypatch, {"items": []})

    response = client.get("/api/v1/home/news")

    assert response.status_code == 200
    assert response.json() == {"items": []}
