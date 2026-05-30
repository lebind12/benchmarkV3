"""Unit tests for GET /api/v1/fixtures/{external_id}/team-recent."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


TEAM_RECENT_PAYLOAD = {
    "home": {
        "team": {
            "external_id": 50,
            "slug": "manchester-city",
            "name": "Manchester City",
            "name_ko": "맨체스터 시티",
            "short_name_ko": "맨시티",
            "logo_url": None,
        },
        "fixtures": [
            {
                "external_id": 1379001,
                "league": {
                    "external_id": 39,
                    "slug": "premier-league",
                    "name": "Premier League",
                    "name_ko": "프리미어리그",
                    "short_name_ko": "EPL",
                    "logo_url": None,
                },
                "home": {
                    "external_id": 50,
                    "slug": "manchester-city",
                    "name": "Manchester City",
                    "name_ko": "맨체스터 시티",
                    "short_name_ko": "맨시티",
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
                "kickoff_at": "2025-08-19T15:00:00Z",
                "status_short": "FT",
                "goals_home": 2,
                "goals_away": 1,
            }
        ],
    },
    "away": {
        "team": {
            "external_id": 66,
            "slug": "aston-villa",
            "name": "Aston Villa",
            "name_ko": "애스턴 빌라",
            "short_name_ko": "빌라",
            "logo_url": None,
        },
        "fixtures": [],
    },
}


class FakeTeamRecentService:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or TEAM_RECENT_PAYLOAD
        self.calls: list[tuple[int, int]] = []

    def get_team_recent_matches(self, external_id: int, limit: int = 10) -> dict:
        self.calls.append((external_id, limit))
        payload = {
            "home": {
                **self.payload["home"],
                "fixtures": self.payload["home"]["fixtures"][:limit],
            },
            "away": {
                **self.payload["away"],
                "fixtures": self.payload["away"]["fixtures"][:limit],
            },
        }
        return payload


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


def test_team_recent_u01_default_limit_returns_home_and_away_lists():
    service = FakeTeamRecentService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/team-recent")

    assert response.status_code == 200
    assert service.calls == [(1379344, 10)]
    payload = response.json()
    assert payload == TEAM_RECENT_PAYLOAD
    assert payload["home"]["fixtures"][0]["status_short"] == "FT"
    assert payload["home"]["fixtures"][0]["league"]["short_name_ko"] == "EPL"


def test_team_recent_u02_limit_20_is_passed_to_service():
    service = FakeTeamRecentService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/team-recent?limit=20")

    assert response.status_code == 200
    assert service.calls == [(1379344, 20)]


def test_team_recent_u03_limit_above_20_returns_422_without_service_call():
    service = FakeTeamRecentService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/team-recent?limit=21")

    assert response.status_code == 422
    assert service.calls == []


def test_team_recent_u04_fixture_not_found_maps_to_404():
    class MissingFixtureService:
        def get_team_recent_matches(self, external_id: int, limit: int = 10) -> dict:
            raise analytics.FixtureNotFoundError(external_id)

    with client_with_service(MissingFixtureService()) as (client, analytics):
        response = client.get("/api/v1/fixtures/999999/team-recent")

    assert response.status_code == 404
    assert "999999" in response.text
