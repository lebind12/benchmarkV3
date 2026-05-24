"""Unit tests for GET /api/v1/fixtures/{external_id}/statistics.

The DB/service layer is mocked. The response shape follows the live fixture-detail FE
type, not the older aliases in the generated request JSON.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


STATISTICS_PAYLOAD = {
    "home": {
        "team_external_id": 40,
        "possession": 58,
        "shots_total": 16,
        "shots_on_target": 7,
        "passes_total": 540,
        "passes_accuracy": 88,
        "corners": 8,
        "fouls": 9,
        "yellow": 1,
        "red": 1,
        "offsides": 2,
    },
    "away": {
        "team_external_id": 42,
        "possession": 42,
        "shots_total": 11,
        "shots_on_target": 4,
        "passes_total": 392,
        "passes_accuracy": 82,
        "corners": 5,
        "fouls": 12,
        "yellow": 2,
        "red": 0,
        "offsides": 3,
    },
}


EMPTY_STATISTICS_PAYLOAD = {
    "home": {
        "team_external_id": 40,
        "possession": None,
        "shots_total": None,
        "shots_on_target": None,
        "passes_total": None,
        "passes_accuracy": None,
        "corners": None,
        "fouls": None,
        "yellow": None,
        "red": None,
        "offsides": None,
    },
    "away": {
        "team_external_id": 42,
        "possession": None,
        "shots_total": None,
        "shots_on_target": None,
        "passes_total": None,
        "passes_accuracy": None,
        "corners": None,
        "fouls": None,
        "yellow": None,
        "red": None,
        "offsides": None,
    },
}


class FakeStatisticsService:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls: list[int] = []

    def get_statistics(self, external_id: int) -> dict:
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


def test_statistics_u01_normal_payload_uses_current_fe_field_names():
    service = FakeStatisticsService(STATISTICS_PAYLOAD)

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000001/statistics")

    assert response.status_code == 200
    assert service.calls == [1000001]
    payload = response.json()
    assert payload == STATISTICS_PAYLOAD
    assert "possession_pct" not in payload["home"]
    assert "shots_on" not in payload["home"]
    assert "passes_accurate_pct" not in payload["home"]
    assert payload["home"]["shots_on_target"] == 7
    assert payload["away"]["red"] == 0


def test_statistics_u02_empty_payload_keeps_team_ids_and_null_metrics():
    service = FakeStatisticsService(EMPTY_STATISTICS_PAYLOAD)

    with client_with_service(service) as (client, _analytics):
        response = client.get("/api/v1/fixtures/1000002/statistics")

    assert response.status_code == 200
    assert response.json() == EMPTY_STATISTICS_PAYLOAD
    assert response.json()["home"]["team_external_id"] == 40
    metric_values = [
        value
        for key, value in response.json()["home"].items()
        if key != "team_external_id"
    ]
    assert metric_values and all(value is None for value in metric_values)


def test_statistics_u03_fixture_not_found_maps_to_404():
    class MissingFixtureService:
        def get_statistics(self, external_id: int) -> dict:
            raise analytics.FixtureNotFoundError(external_id)

    with client_with_service(MissingFixtureService()) as (client, analytics):
        response = client.get("/api/v1/fixtures/999999/statistics")

    assert response.status_code == 404
    assert "999999" in response.text
