"""GET /api/v1/home/fixtures unit tests.

These tests are intentionally route-level and service-mocked. They should fail in
the Red phase until `app.api.v1.home` is implemented and included in app.main.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


SAMPLE_FIXTURE_RESPONSE = {
    "items": [
        {
            "external_id": 7001,
            "league": {
                "external_id": 39,
                "slug": "premier-league",
                "name_ko": "프리미어리그",
                "short_name_ko": "EPL",
                "name": "Premier League",
            },
            "home": {
                "external_id": 33,
                "slug": "manchester-united-33",
                "name_ko": "맨체스터 유나이티드",
                "short_name_ko": "맨유",
                "name": "Manchester United",
                "logo_url": "https://example.test/manutd.png",
            },
            "away": {
                "external_id": 40,
                "slug": "liverpool-40",
                "name_ko": None,
                "short_name_ko": None,
                "name": "Liverpool",
                "logo_url": None,
            },
            "kickoff_at": "2026-05-13T15:30:00Z",
            "status_short": "1H",
            "goals_home": 1,
            "goals_away": 0,
        }
    ],
    "filters_applied": {"period": "day", "league_id": None},
}


class FakeHomeService:
    def __init__(self) -> None:
        self.fixture_calls: list[dict[str, object]] = []

    def list_fixtures(
        self,
        *,
        league_id: int | None = None,
        period: str = "day",
        date: date | None = None,
    ) -> dict:
        self.fixture_calls.append(
            {"league_id": league_id, "period": period, "date": date}
        )
        payload = dict(SAMPLE_FIXTURE_RESPONSE)
        payload["filters_applied"] = {"period": period, "league_id": league_id}
        return payload


@pytest.fixture()
def client_and_service():
    from app.api.v1.home import get_home_service, router

    service = FakeHomeService()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/home")
    app.dependency_overrides[get_home_service] = lambda: service
    return TestClient(app), service


def test_hf_u01_route_registered_on_main_app():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/home/fixtures" in paths


def test_hf_u02_public_default_request(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/fixtures")

    assert response.status_code == 200
    assert service.fixture_calls == [
        {"league_id": None, "period": "day", "date": None}
    ]
    assert response.json()["filters_applied"] == {"period": "day", "league_id": None}


def test_hf_u03_accepts_league_and_period(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/fixtures?league_id=39&period=week")

    assert response.status_code == 200
    assert service.fixture_calls[-1] == {
        "league_id": 39,
        "period": "week",
        "date": None,
    }


def test_hf_u03b_accepts_world_cup_league(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/fixtures?league_id=1&period=month")

    assert response.status_code == 200
    assert service.fixture_calls[-1] == {
        "league_id": 1,
        "period": "month",
        "date": None,
    }


def test_hf_u04_accepts_date_override(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/fixtures?date=2026-05-14&period=month")

    assert response.status_code == 200
    assert service.fixture_calls[-1] == {
        "league_id": None,
        "period": "month",
        "date": date(2026, 5, 14),
    }


def test_hf_u05_invalid_period_returns_422(client_and_service):
    client, _service = client_and_service

    response = client.get("/api/v1/home/fixtures?period=year")

    assert response.status_code == 422


def test_hf_u06_unsupported_league_id_returns_422(client_and_service):
    client, _service = client_and_service

    response = client.get("/api/v1/home/fixtures?league_id=999")

    assert response.status_code == 422


def test_hf_u07_response_shape_passthrough(client_and_service):
    client, _service = client_and_service

    payload = client.get("/api/v1/home/fixtures").json()
    item = payload["items"][0]

    assert item["external_id"] == 7001
    assert item["league"]["short_name_ko"] == "EPL"
    assert item["home"]["name_ko"] == "맨체스터 유나이티드"
    assert item["away"]["name_ko"] is None
    assert item["away"]["name"] == "Liverpool"
    assert item["status_short"] == "1H"
    assert item["goals_home"] == 1
    assert item["goals_away"] == 0
