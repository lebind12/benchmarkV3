"""GET /api/v1/home/standings unit tests.

These tests are intentionally route-level and service-mocked. They should fail in
the Red phase until `app.api.v1.home` is implemented and included in app.main.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


SAMPLE_STANDINGS_RESPONSE = {
    "league": {
        "external_id": 39,
        "slug": "premier-league",
        "name_ko": "프리미어리그",
        "short_name_ko": "EPL",
        "name": "Premier League",
    },
    "season": 2025,
    "rows": [
        {
            "rank": 1,
            "team": {
                "external_id": 40,
                "slug": "liverpool-40",
                "name_ko": None,
                "short_name_ko": None,
                "name": "Liverpool",
                "logo_url": "https://example.test/liverpool.png",
            },
            "points": 72,
            "played": 32,
            "win": 22,
            "draw": 6,
            "loss": 4,
            "goals_for": 75,
            "goals_against": 30,
        }
    ],
}


class FakeHomeService:
    def __init__(self, payload: dict | None = None) -> None:
        self.payload = payload or SAMPLE_STANDINGS_RESPONSE
        self.standings_calls: list[dict[str, int]] = []

    def get_standings(self, *, league_id: int = 39) -> dict:
        self.standings_calls.append({"league_id": league_id})
        return self.payload


@pytest.fixture()
def client_and_service():
    from app.api.v1.home import get_home_service, router

    service = FakeHomeService()
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/home")
    app.dependency_overrides[get_home_service] = lambda: service
    return TestClient(app), service


def test_hs_u01_route_registered_on_main_app():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/home/standings" in paths


def test_hs_u02_public_default_request(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/standings")

    assert response.status_code == 200
    assert service.standings_calls == [{"league_id": 39}]
    assert response.json()["league"]["external_id"] == 39


def test_hs_u03_accepts_explicit_allowed_league(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/standings?league_id=2")

    assert response.status_code == 200
    assert service.standings_calls[-1] == {"league_id": 2}


def test_hs_u03b_accepts_world_cup_league(client_and_service):
    client, service = client_and_service

    response = client.get("/api/v1/home/standings?league_id=1")

    assert response.status_code == 200
    assert service.standings_calls[-1] == {"league_id": 1}


def test_hs_u04_unsupported_league_id_returns_422(client_and_service):
    client, _service = client_and_service

    response = client.get("/api/v1/home/standings?league_id=999")

    assert response.status_code == 422


def test_hs_u05_empty_standings_payload_returns_200():
    from app.api.v1.home import get_home_service, router

    empty_payload = {
        "league": SAMPLE_STANDINGS_RESPONSE["league"],
        "season": 2025,
        "rows": [],
    }
    service = FakeHomeService(payload=empty_payload)
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/home")
    app.dependency_overrides[get_home_service] = lambda: service
    client = TestClient(app)

    response = client.get("/api/v1/home/standings?league_id=48")

    assert response.status_code == 200
    assert response.json() == empty_payload


def test_hs_u06_response_shape_passthrough(client_and_service):
    client, _service = client_and_service

    payload = client.get("/api/v1/home/standings").json()
    row = payload["rows"][0]

    assert payload["league"]["short_name_ko"] == "EPL"
    assert payload["season"] == 2025
    assert row["rank"] == 1
    assert row["team"]["name_ko"] is None
    assert row["team"]["name"] == "Liverpool"
    assert row["points"] == 72
    assert (row["win"], row["draw"], row["loss"]) == (22, 6, 4)
    assert row["goals_for"] == 75
    assert row["goals_against"] == 30
