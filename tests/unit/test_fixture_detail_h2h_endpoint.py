"""Unit tests for GET /api/v1/fixtures/{external_id}/h2h.

These tests mock the endpoint analytics service. They intentionally require
`app.api.v1.fixture_detail_analytics` so the Red phase fails until be-dev wires the
router and dependency hooks described in the endpoint spec.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


H2H_PAYLOAD = {
    "h2h": [
        {
            "external_id": 999002,
            "league": {
                "external_id": 39,
                "slug": "premier-league",
                "short_name_ko": "EPL",
                "name": "Premier League",
            },
            "kickoff_at": "2025-08-19T15:00:00Z",
            "home": {
                "external_id": 40,
                "slug": "liverpool",
                "name": "Liverpool",
                "name_ko": "리버풀",
                "short_name_ko": "리버풀",
                "logo_url": None,
            },
            "away": {
                "external_id": 42,
                "slug": "arsenal",
                "name": "Arsenal",
                "name_ko": "아스널",
                "short_name_ko": "아스널",
                "logo_url": None,
            },
            "goals_home": 1,
            "goals_away": 1,
            "status_short": "FT",
        }
    ]
}


class FakeH2HService:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or H2H_PAYLOAD
        self.calls: list[tuple[int, int]] = []

    def get_h2h(self, external_id: int, limit: int = 5) -> dict:
        self.calls.append((external_id, limit))
        return {"h2h": self.payload["h2h"][:limit]}


@contextmanager
def client_with_service(service):
    from app.api.v1 import fixture_detail_analytics as analytics
    from app.main import app

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[analytics.get_fixture_detail_analytics_service] = lambda: service
    try:
        with TestClient(app) as client:
            yield client, analytics
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_h2h_u01_default_limit_returns_current_fe_shape():
    service = FakeH2HService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000001/h2h")

    assert response.status_code == 200
    assert service.calls == [(1000001, 5)]
    payload = response.json()
    assert payload == H2H_PAYLOAD
    row = payload["h2h"][0]
    assert row["status_short"] == "FT"
    assert row["league"]["short_name_ko"] == "EPL"
    assert row["home"]["name_ko"] == "리버풀"


def test_h2h_u02_limit_10_is_passed_to_service():
    service = FakeH2HService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000001/h2h?limit=10")

    assert response.status_code == 200
    assert service.calls == [(1000001, 10)]


def test_h2h_u03_limit_above_10_returns_422_without_service_call():
    service = FakeH2HService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000001/h2h?limit=11")

    assert response.status_code == 422
    assert service.calls == []


def test_h2h_u04_fixture_not_found_maps_to_404():
    class MissingFixtureService:
        def get_h2h(self, external_id: int, limit: int = 5) -> dict:
            raise analytics.FixtureNotFoundError(external_id)

    with client_with_service(MissingFixtureService()) as (client, analytics):
        response = client.get("/api/v1/fixtures/999999/h2h")

    assert response.status_code == 404
    assert "999999" in response.text
