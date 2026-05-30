"""Unit tests for GET /api/v1/fixtures/{external_id}/matchup-insights."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


MATCHUP_INSIGHTS_PAYLOAD = {
    "mode": "pre_match",
    "source": "recent_completed_fixtures",
    "title": "매치업 인사이트",
    "subtitle": "최근 완료 경기 최대 10경기 평균",
    "home": {
        "team": {
            "external_id": 50,
            "slug": "manchester-city",
            "name": "Manchester City",
            "name_ko": "맨체스터 시티",
            "short_name_ko": "맨시티",
            "logo_url": None,
        },
        "sample_size": 10,
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
        "sample_size": 8,
    },
    "metrics": [
        {
            "key": "xg",
            "label": "xG",
            "unit": "",
            "precision": 2,
            "better": "higher",
            "home": 1.84,
            "away": 1.42,
        }
    ],
}


class FakeMatchupInsightsService:
    def __init__(self, payload: dict | None = None):
        self.payload = payload or MATCHUP_INSIGHTS_PAYLOAD
        self.calls: list[tuple[int, int]] = []

    def get_matchup_insights(self, external_id: int, limit: int = 10) -> dict:
        self.calls.append((external_id, limit))
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


def test_matchup_insights_u01_default_limit_returns_mode_and_metrics():
    service = FakeMatchupInsightsService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/matchup-insights")

    assert response.status_code == 200
    assert service.calls == [(1379344, 10)]
    payload = response.json()
    assert payload == MATCHUP_INSIGHTS_PAYLOAD
    assert payload["mode"] == "pre_match"
    assert payload["metrics"][0]["key"] == "xg"


def test_matchup_insights_u02_limit_20_is_passed_to_service():
    service = FakeMatchupInsightsService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/matchup-insights?limit=20")

    assert response.status_code == 200
    assert service.calls == [(1379344, 20)]


def test_matchup_insights_u03_limit_above_20_returns_422_without_service_call():
    service = FakeMatchupInsightsService()

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1379344/matchup-insights?limit=21")

    assert response.status_code == 422
    assert service.calls == []


def test_matchup_insights_u04_fixture_not_found_maps_to_404():
    class MissingFixtureService:
        def get_matchup_insights(self, external_id: int, limit: int = 10) -> dict:
            raise analytics.FixtureNotFoundError(external_id)

    with client_with_service(MissingFixtureService()) as (client, analytics):
        response = client.get("/api/v1/fixtures/999999/matchup-insights")

    assert response.status_code == 404
    assert "999999" in response.text
