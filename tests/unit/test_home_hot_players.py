from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.unit


LEAGUE = {
    "external_id": 39,
    "slug": "premier-league",
    "name_ko": "프리미어리그",
    "name": "Premier League",
}


def _item(goals=22, assists=6):
    return {
        "player": {
            "external_id": 1100,
            "slug": "erling-haaland",
            "name_ko": "엘링 홀란드",
            "name": "Erling Haaland",
            "photo_url": None,
            "team": {
                "external_id": 50,
                "slug": "manchester-city",
                "name_ko": "맨체스터 시티",
                "name": "Manchester City",
                "logo_url": None,
            },
            "league": LEAGUE,
        },
        "goals": goals,
        "assists": assists,
        "score": goals + assists,
    }


@pytest.fixture()
def client():
    return TestClient(app)


def _patch_service(monkeypatch, payload):
    from app.services import home as home_service

    mock = MagicMock(return_value=payload)
    monkeypatch.setattr(home_service, "list_home_hot_players", mock, raising=False)
    try:
        from app.api import home as home_router

        monkeypatch.setattr(home_router, "list_home_hot_players", mock, raising=False)
    except ImportError:
        pass
    return mock


def test_hhp_u01_public_endpoint_returns_service_payload(client, monkeypatch):
    service = _patch_service(monkeypatch, {"items": [_item()]})

    response = client.get("/api/v1/home/hot-players")

    assert response.status_code == 200
    assert response.json()["items"][0]["player"]["slug"] == "erling-haaland"
    assert service.call_count == 1


def test_hhp_u02_score_matches_goals_plus_assists(client, monkeypatch):
    _patch_service(monkeypatch, {"items": [_item(goals=18, assists=9)]})

    response = client.get("/api/v1/home/hot-players")

    item = response.json()["items"][0]
    assert response.status_code == 200
    assert item["score"] == item["goals"] + item["assists"]


def test_hhp_u03_empty_items_are_valid(client, monkeypatch):
    _patch_service(monkeypatch, {"items": []})

    response = client.get("/api/v1/home/hot-players")

    assert response.status_code == 200
    assert response.json() == {"items": []}
