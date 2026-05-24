"""Unit tests for GET /api/v1/fixtures/{external_id}/league-standings.

The DB/service layer is mocked. The payload follows the live
`LeagueStandingsPayload` consumed by `StandingsTab.vue`.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


LEAGUE_STANDINGS_PAYLOAD = {
    "league": {
        "external_id": 39,
        "slug": "premier-league",
        "name": "Premier League",
        "name_ko": "프리미어 리그",
        "short_name_ko": "EPL",
        "logo_url": None,
    },
    "season": 2025,
    "group_name": None,
    "highlighted_team_ids": [40, 42],
    "rows": [
        {
            "rank": 1,
            "team": {
                "external_id": 40,
                "slug": "liverpool",
                "name": "Liverpool",
                "name_ko": "리버풀",
                "short_name_ko": "리버풀",
                "logo_url": None,
            },
            "played": 32,
            "win": 21,
            "draw": 7,
            "loss": 4,
            "goals_for": 70,
            "goals_against": 30,
            "goal_diff": 40,
            "points": 70,
            "group_name": None,
        },
        {
            "rank": 2,
            "team": {
                "external_id": 42,
                "slug": "arsenal",
                "name": "Arsenal",
                "name_ko": "아스널",
                "short_name_ko": "아스널",
                "logo_url": None,
            },
            "played": 32,
            "win": 20,
            "draw": 8,
            "loss": 4,
            "goals_for": 65,
            "goals_against": 32,
            "goal_diff": 33,
            "points": 68,
            "group_name": None,
        },
    ],
}


EMPTY_STANDINGS_PAYLOAD = {
    "league": {
        "external_id": 48,
        "slug": "carabao-cup",
        "name": "League Cup",
        "name_ko": "카라바오컵",
        "short_name_ko": "카라바오컵",
        "logo_url": None,
    },
    "season": 2025,
    "group_name": None,
    "highlighted_team_ids": [40, 42],
    "rows": [],
}


class FakeLeagueStandingsService:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[int] = []

    def get_league_standings(self, external_id: int) -> dict:
        self.calls.append(external_id)
        return self.payload


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


def test_league_standings_u01_flat_payload_with_highlighted_ids():
    service = FakeLeagueStandingsService(LEAGUE_STANDINGS_PAYLOAD)

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000001/league-standings")

    assert response.status_code == 200
    assert service.calls == [1000001]
    payload = response.json()
    assert payload == LEAGUE_STANDINGS_PAYLOAD
    assert payload["highlighted_team_ids"] == [40, 42]
    assert payload["rows"][0]["rank"] == 1
    assert "groups" not in payload
    assert "format" not in payload


def test_league_standings_u02_tournament_empty_payload_is_200():
    service = FakeLeagueStandingsService(EMPTY_STANDINGS_PAYLOAD)

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000006/league-standings")

    assert response.status_code == 200
    assert response.json()["rows"] == []
    assert response.json()["group_name"] is None
    assert response.json()["highlighted_team_ids"] == [40, 42]


def test_league_standings_u03_fixture_not_found_maps_to_404():
    class MissingFixtureService:
        def get_league_standings(self, external_id: int) -> dict:
            raise analytics.FixtureNotFoundError(external_id)

    with client_with_service(MissingFixtureService()) as (client, analytics):
        response = client.get("/api/v1/fixtures/999999/league-standings")

    assert response.status_code == 404
    assert "999999" in response.text
