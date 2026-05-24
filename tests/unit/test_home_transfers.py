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


def _team(external_id=40, slug="liverpool", name="Liverpool", name_ko="리버풀"):
    return {
        "external_id": external_id,
        "slug": slug,
        "name_ko": name_ko,
        "short_name_ko": name_ko,
        "name": name,
        "logo_url": None,
    }


def _item(*, fee="€120m"):
    team = _team()
    return {
        "id": "t1",
        "player": {
            "external_id": 2002,
            "slug": "florian-wirtz",
            "name_ko": "플로리안 비르츠",
            "name": "Florian Wirtz",
            "photo_url": None,
            "team": team,
            "league": LEAGUE,
        },
        "from_team": _team(168, "leverkusen", "Bayer Leverkusen", "레버쿠젠"),
        "to_team": team,
        "transfer_date": "2026-05-08",
        "fee": fee,
    }


@pytest.fixture()
def client():
    return TestClient(app)


def _patch_service(monkeypatch, payload):
    from app.services import home as home_service

    mock = MagicMock(return_value=payload)
    monkeypatch.setattr(home_service, "list_home_transfers", mock, raising=False)
    try:
        from app.api import home as home_router

        monkeypatch.setattr(home_router, "list_home_transfers", mock, raising=False)
    except ImportError:
        pass
    return mock


def test_ht_u01_public_endpoint_returns_transfer_shape(client, monkeypatch):
    service = _patch_service(monkeypatch, {"items": [_item()]})

    response = client.get("/api/v1/home/transfers")

    assert response.status_code == 200
    assert response.json()["items"][0]["from_team"]["slug"] == "leverkusen"
    assert response.json()["items"][0]["to_team"]["slug"] == "liverpool"
    assert service.call_count == 1


def test_ht_u02_fee_null_is_allowed(client, monkeypatch):
    _patch_service(monkeypatch, {"items": [_item(fee=None)]})

    response = client.get("/api/v1/home/transfers")

    assert response.status_code == 200
    assert response.json()["items"][0]["fee"] is None


def test_ht_u03_empty_items_are_valid(client, monkeypatch):
    _patch_service(monkeypatch, {"items": []})

    response = client.get("/api/v1/home/transfers")

    assert response.status_code == 200
    assert response.json() == {"items": []}
