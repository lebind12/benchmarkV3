"""Fixture-detail match endpoint unit tests.

All external dependencies are mocked through the fixture-detail service
dependency. Initial Red state is expected until app.api.fixture_detail exists.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

pytestmark = pytest.mark.unit


def _build_client(service) -> TestClient:
    from app.api.fixture_detail import get_fixture_detail_service, router

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_fixture_detail_service] = lambda: service
    return TestClient(app)


class FakeMatchService:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[int] = []

    def get_match_detail(self, external_id: int):
        self.calls.append(external_id)
        return self.payload


MATCH_PAYLOAD = {
    "external_id": 1000001,
    "league": {
        "external_id": 39,
        "slug": "premier-league",
        "name": "Premier League",
        "name_ko": "프리미어리그",
        "short_name_ko": "EPL",
        "logo_url": "https://cdn.example/leagues/39.png",
    },
    "round": "32라운드",
    "status_short": "FT",
    "status_long": "Match Finished",
    "kickoff_at": "2026-05-13T10:00:00Z",
    "venue": {"name": "Anfield", "city": "Liverpool"},
    "referee": "J. Pratt",
    "home": {
        "external_id": 40,
        "slug": "liverpool-40",
        "name": "Liverpool",
        "name_ko": "리버풀",
        "short_name_ko": "리버풀",
        "logo_url": "https://cdn.example/teams/40.png",
    },
    "away": {
        "external_id": 42,
        "slug": "arsenal-42",
        "name": "Arsenal",
        "name_ko": None,
        "short_name_ko": None,
        "logo_url": "https://cdn.example/teams/42.png",
    },
    "goals_home": 3,
    "goals_away": 1,
    "penalty_home": None,
    "penalty_away": None,
    "goal_events": [
        {
            "minute": 23,
            "extra": None,
            "scorer": {
                "external_id": 1001,
                "slug": "mohamed-salah-1001",
                "name": "Mohamed Salah",
                "name_ko": "모하메드 살라",
                "photo_url": "https://cdn.example/players/1001.png",
            },
            "team_external_id": 40,
            "type": "normal",
        }
    ],
}


def test_match_u01_returns_match_header_payload():
    service = FakeMatchService(MATCH_PAYLOAD)
    client = _build_client(service)

    response = client.get("/api/v1/fixtures/1000001")

    assert response.status_code == 200
    body = response.json()
    assert service.calls == [1000001]
    assert body["external_id"] == 1000001
    assert body["league"]["slug"] == "premier-league"
    assert body["status_short"] == "FT"
    assert body["goals_home"] == 3
    assert body["goals_away"] == 1
    assert body["goal_events"][0]["type"] == "normal"


def test_match_u02_maps_none_to_404():
    client = _build_client(FakeMatchService(None))

    response = client.get("/api/v1/fixtures/1000099")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"


def test_match_u03_rejects_non_integer_external_id():
    client = _build_client(FakeMatchService(MATCH_PAYLOAD))

    response = client.get("/api/v1/fixtures/not-an-int")

    assert response.status_code == 422


def test_match_u04_preserves_nullable_translation_with_english_name():
    client = _build_client(FakeMatchService(MATCH_PAYLOAD))

    response = client.get("/api/v1/fixtures/1000001")

    assert response.status_code == 200
    away = response.json()["away"]
    assert away["name"] == "Arsenal"
    assert away["name_ko"] is None
    assert away["short_name_ko"] is None
