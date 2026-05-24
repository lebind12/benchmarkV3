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


def _item(*, expected_return="2026-06-01"):
    return {
        "id": "i1",
        "player": {
            "external_id": 3001,
            "slug": "rodri",
            "name_ko": "로드리",
            "name": "Rodri",
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
        "injury_type": "햄스트링",
        "expected_return": expected_return,
        "reported_at": "2026-05-12",
    }


@pytest.fixture()
def client():
    return TestClient(app)


def _patch_service(monkeypatch, payload):
    from app.services import home as home_service

    mock = MagicMock(return_value=payload)
    monkeypatch.setattr(home_service, "list_home_injuries", mock, raising=False)
    try:
        from app.api import home as home_router

        monkeypatch.setattr(home_router, "list_home_injuries", mock, raising=False)
    except ImportError:
        pass
    return mock


def test_hi_u01_public_endpoint_returns_injury_shape(client, monkeypatch):
    service = _patch_service(monkeypatch, {"items": [_item()]})

    response = client.get("/api/v1/home/injuries")

    assert response.status_code == 200
    assert response.json()["items"][0]["injury_type"] == "햄스트링"
    assert response.json()["items"][0]["player"]["team"]["slug"] == "manchester-city"
    assert service.call_count == 1


def test_hi_u02_expected_return_null_is_allowed(client, monkeypatch):
    _patch_service(monkeypatch, {"items": [_item(expected_return=None)]})

    response = client.get("/api/v1/home/injuries")

    assert response.status_code == 200
    assert response.json()["items"][0]["expected_return"] is None


def test_hi_u03_empty_items_are_valid(client, monkeypatch):
    _patch_service(monkeypatch, {"items": []})

    response = client.get("/api/v1/home/injuries")

    assert response.status_code == 200
    assert response.json() == {"items": []}
