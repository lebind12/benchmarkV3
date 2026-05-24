"""Fixture-detail events endpoint unit tests."""

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


class FakeEventsService:
    def __init__(self, payload):
        self.payload = payload
        self.calls: list[int] = []

    def get_fixture_events(self, external_id: int):
        self.calls.append(external_id)
        return self.payload


PLAYER = {
    "external_id": 1001,
    "slug": "mohamed-salah-1001",
    "name": "Mohamed Salah",
    "name_ko": "모하메드 살라",
    "photo_url": "https://cdn.example/players/1001.png",
}

EVENTS_PAYLOAD = {
    "events": [
        {
            "id": f"1000001:{index}",
            "minute": 10 + index,
            "extra": None,
            "team_external_id": 40,
            "type": event_type,
            "player": PLAYER,
            "assist": None,
            "player_out": PLAYER if event_type == "substitution" else None,
            "detail": "detail",
        }
        for index, event_type in enumerate(
            [
                "goal",
                "goal_penalty",
                "goal_own",
                "yellow_card",
                "red_card",
                "yellow_red",
                "substitution",
                "var",
            ]
        )
    ]
}


def test_events_u01_returns_canonical_timeline_payload():
    service = FakeEventsService(EVENTS_PAYLOAD)
    client = _build_client(service)

    response = client.get("/api/v1/fixtures/1000001/events")

    assert response.status_code == 200
    body = response.json()
    assert service.calls == [1000001]
    assert [event["type"] for event in body["events"]] == [
        "goal",
        "goal_penalty",
        "goal_own",
        "yellow_card",
        "red_card",
        "yellow_red",
        "substitution",
        "var",
    ]
    assert body["events"][0]["player"]["name"] == "Mohamed Salah"


def test_events_u02_existing_fixture_can_return_empty_events():
    client = _build_client(FakeEventsService({"events": []}))

    response = client.get("/api/v1/fixtures/1000002/events")

    assert response.status_code == 200
    assert response.json() == {"events": []}


def test_events_u03_maps_none_to_404():
    client = _build_client(FakeEventsService(None))

    response = client.get("/api/v1/fixtures/1000099/events")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"


def test_events_u04_rejects_non_integer_external_id():
    client = _build_client(FakeEventsService(EVENTS_PAYLOAD))

    response = client.get("/api/v1/fixtures/not-an-int/events")

    assert response.status_code == 422
