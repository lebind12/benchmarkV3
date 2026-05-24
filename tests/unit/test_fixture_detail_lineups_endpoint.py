"""Fixture-detail lineups endpoint unit tests."""

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


class FakeLineupsService:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[int] = []

    def get_fixture_lineups(self, external_id: int):
        self.calls.append(external_id)
        return self.payload


def _team(external_id: int, name: str, name_ko: str | None):
    return {
        "external_id": external_id,
        "slug": f"{name.lower()}-{external_id}",
        "name": name,
        "name_ko": name_ko,
        "short_name_ko": name_ko,
        "logo_url": f"https://cdn.example/teams/{external_id}.png",
    }


def _player(index: int):
    return {
        "player": {
            "external_id": 2000 + index,
            "slug": f"player-{2000 + index}",
            "name": f"Player {index}",
            "name_ko": f"선수 {index}",
            "photo_url": None,
        },
        "number": index,
        "position": "GK" if index == 1 else "MF",
        "grid": f"{index}:1",
        "rating": 7.4 if index == 1 else None,
        "minutes": 90 if index == 1 else None,
    }


LINEUPS_PAYLOAD = {
    "home": {
        "team": _team(40, "Liverpool", "리버풀"),
        "formation": "4-3-3",
        "coach": {"name": "Arne Slot", "name_ko": None},
        "start_xi": [_player(index) for index in range(1, 12)],
        "bench": [_player(20)],
    },
    "away": {
        "team": _team(42, "Arsenal", "아스널"),
        "formation": "4-2-3-1",
        "coach": {"name": "Mikel Arteta", "name_ko": None},
        "start_xi": [_player(index) for index in range(12, 23)],
        "bench": [],
    },
}


EMPTY_LINEUPS_PAYLOAD = {
    "home": {
        "team": _team(40, "Liverpool", "리버풀"),
        "formation": None,
        "coach": None,
        "start_xi": [],
        "bench": [],
    },
    "away": {
        "team": _team(42, "Arsenal", "아스널"),
        "formation": None,
        "coach": None,
        "start_xi": [],
        "bench": [],
    },
}


def test_lineups_u01_returns_home_away_lineups():
    service = FakeLineupsService(LINEUPS_PAYLOAD)
    client = _build_client(service)

    response = client.get("/api/v1/fixtures/1000001/lineups")

    assert response.status_code == 200
    body = response.json()
    assert service.calls == [1000001]
    assert body["home"]["formation"] == "4-3-3"
    assert body["away"]["formation"] == "4-2-3-1"
    assert len(body["home"]["start_xi"]) == 11
    assert body["home"]["start_xi"][0]["rating"] == 7.4
    assert body["home"]["start_xi"][0]["minutes"] == 90
    assert body["home"]["bench"][0]["player"]["external_id"] == 2020


def test_lineups_u02_existing_fixture_can_return_empty_lineups():
    client = _build_client(FakeLineupsService(EMPTY_LINEUPS_PAYLOAD))

    response = client.get("/api/v1/fixtures/1000002/lineups")

    assert response.status_code == 200
    body = response.json()
    assert body["home"]["formation"] is None
    assert body["home"]["start_xi"] == []
    assert body["away"]["bench"] == []


def test_lineups_u03_maps_none_to_404():
    client = _build_client(FakeLineupsService(None))

    response = client.get("/api/v1/fixtures/1000099/lineups")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"


def test_lineups_u04_rejects_non_integer_external_id():
    client = _build_client(FakeLineupsService(LINEUPS_PAYLOAD))

    response = client.get("/api/v1/fixtures/not-an-int/lineups")

    assert response.status_code == 422
