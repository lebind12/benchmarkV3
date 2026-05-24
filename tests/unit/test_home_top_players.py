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


def _payload(rows=None, *, league=LEAGUE, metric="goals"):
    return {
        "league": league,
        "season": 2025,
        "metric": metric,
        "rows": rows or [],
    }


def _row(rank=1, value=22):
    return {
        "rank": rank,
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
        "metric_value": value,
    }


@pytest.fixture()
def client():
    return TestClient(app)


def _patch_service(monkeypatch, payload):
    from app.services import home as home_service

    mock = MagicMock(return_value=payload)
    monkeypatch.setattr(home_service, "list_home_top_players", mock, raising=False)
    try:
        from app.api import home as home_router

        monkeypatch.setattr(home_router, "list_home_top_players", mock, raising=False)
    except ImportError:
        pass
    return mock


def test_htp_u01_defaults_are_public_and_call_service(client, monkeypatch):
    service = _patch_service(monkeypatch, _payload([_row()]))

    response = client.get("/api/v1/home/top-players")

    assert response.status_code == 200
    assert response.json()["metric"] == "goals"
    assert response.json()["rows"][0]["rank"] == 1
    assert service.call_count == 1
    assert service.call_args.kwargs["league_id"] == 39
    assert service.call_args.kwargs["metric"] == "goals"


def test_htp_u02_query_overrides_are_passed_to_service(client, monkeypatch):
    service = _patch_service(monkeypatch, _payload([_row(value=11)], metric="assists"))

    response = client.get("/api/v1/home/top-players?league_id=2&metric=assists")

    assert response.status_code == 200
    assert response.json()["metric"] == "assists"
    assert service.call_args.kwargs["league_id"] == 2
    assert service.call_args.kwargs["metric"] == "assists"


def test_htp_u03_empty_rows_and_null_league_are_valid(client, monkeypatch):
    _patch_service(monkeypatch, _payload([], league=None))

    response = client.get("/api/v1/home/top-players?league_id=999")

    assert response.status_code == 200
    assert response.json()["league"] is None
    assert response.json()["rows"] == []


def test_htp_u04_invalid_metric_returns_422_without_service_call(client, monkeypatch):
    service = _patch_service(monkeypatch, _payload([_row()]))

    response = client.get("/api/v1/home/top-players?metric=saves")

    assert response.status_code == 422
    service.assert_not_called()
