"""GET /api/v1/broadcast/fixtures/{external_id}/overlay unit tests.

These route-level tests are intentionally Red until the broadcast overlay route,
auth hook, and service override hook are implemented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit


@dataclass
class FakeUser:
    role: str
    user_id: int = 1


FULL_OVERLAY_PAYLOAD: dict[str, Any] = {
    "fixture": {
        "external_id": 1000001,
        "league": {
            "external_id": 39,
            "slug": "premier-league",
            "name": "Premier League",
            "name_ko": "Premier League KO",
            "short_name_ko": "EPL",
            "logo_url": "https://example.test/epl.png",
            "theme_slug": "premier-league",
        },
        "status_short": "2H",
        "status_long": "Second Half",
        "elapsed": 63,
        "extra": None,
        "clock_label": "63:10",
        "added_time_label": None,
        "home": {
            "external_id": 40,
            "slug": "liverpool-40",
            "name": "Liverpool",
            "name_ko": "Liverpool KO",
            "short_name_ko": "LIV",
            "logo_url": "https://example.test/liverpool.png",
            "badge_url": "https://example.test/liverpool.png",
            "code": "LIV",
        },
        "away": {
            "external_id": 42,
            "slug": "arsenal-42",
            "name": "Arsenal",
            "name_ko": "Arsenal KO",
            "short_name_ko": "ARS",
            "logo_url": "https://example.test/arsenal.png",
            "badge_url": "https://example.test/arsenal.png",
            "code": "ARS",
        },
        "goals_home": 2,
        "goals_away": 1,
    },
    "lineups": [
        {
            "team_external_id": 40,
            "team_side": "home",
            "team_name": "Liverpool",
            "team_name_ko": "Liverpool KO",
            "team_code": "LIV",
            "team_logo_url": "https://example.test/liverpool.png",
            "formation": "4-3-3",
            "players": [
                {
                    "player_external_id": 1001,
                    "number": 11,
                    "name": "Mohamed Salah",
                    "name_ko": "Mohamed Salah KO",
                    "short_name_ko": "Salah",
                    "position": "F",
                    "grid": "3:3",
                    "rating": 7.8,
                    "goals": 2,
                    "yellow_cards": 1,
                    "red_cards": 0,
                    "substitution": "none",
                }
            ],
        },
        {
            "team_external_id": 42,
            "team_side": "away",
            "team_name": "Arsenal",
            "team_name_ko": "Arsenal KO",
            "team_code": "ARS",
            "team_logo_url": "https://example.test/arsenal.png",
            "formation": None,
            "players": [],
        },
    ],
    "statistics": [
        {
            "type": "possession",
            "label_ko": "possession",
            "home": 61,
            "away": 39,
            "home_display": "61%",
            "away_display": "39%",
            "home_pct": 61,
            "away_pct": 39,
        }
    ],
    "events": [
        {
            "event_id": "1000001:23",
            "kind": "goal",
            "team_external_id": 40,
            "team_side": "home",
            "team_code": "LIV",
            "team_logo_url": "https://example.test/liverpool.png",
            "minute": 23,
            "extra": None,
            "clock_label": "23:00",
            "title_ko": "goal",
            "detail_ko": "Mohamed Salah",
            "score_label": "1 : 0",
            "player": {
                "external_id": 1001,
                "name": "Mohamed Salah",
                "name_ko": "Mohamed Salah KO",
                "short_name_ko": "Salah",
            },
            "assist": None,
            "in_player": None,
            "out_player": None,
            "stat": None,
        }
    ],
    "polling": {
        "interval_seconds": 10,
        "cache_hit": False,
        "cache_ttl_seconds": 0,
        "generated_at": "2026-05-24T00:00:00Z",
    },
}


PARTIAL_OVERLAY_PAYLOAD = {
    **FULL_OVERLAY_PAYLOAD,
    "lineups": [
        {
            "team_external_id": 40,
            "team_side": "home",
            "team_name": "Liverpool",
            "team_name_ko": None,
            "team_code": "LIV",
            "team_logo_url": None,
            "formation": None,
            "players": [],
        },
        {
            "team_external_id": 42,
            "team_side": "away",
            "team_name": "Arsenal",
            "team_name_ko": None,
            "team_code": "ARS",
            "team_logo_url": None,
            "formation": None,
            "players": [],
        },
    ],
    "statistics": [
        {
            "type": "shots_total",
            "label_ko": "shots",
            "home": None,
            "away": None,
            "home_display": "-",
            "away_display": "-",
            "home_pct": 50,
            "away_pct": 50,
        }
    ],
    "events": [],
}


class FakeBroadcastOverlayService:
    def __init__(self, payload: dict[str, Any] | None, *, raises: Exception | None = None) -> None:
        self.payload = payload
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    def get_overlay(
        self,
        external_id: int,
        user: FakeUser,
        league_slug: str | None = None,
    ) -> dict[str, Any] | None:
        self.calls.append(
            {
                "external_id": external_id,
                "role": user.role,
                "league_slug": league_slug,
            }
        )
        if self.raises is not None:
            raise self.raises
        return self.payload


def _broadcast_api_contract():
    from app.api.v1 import broadcast as broadcast_api

    missing = [
        name
        for name in ("get_broadcast_current_user", "get_broadcast_overlay_service")
        if not hasattr(broadcast_api, name)
    ]
    assert not missing, f"broadcast overlay route contract missing: {', '.join(missing)}"
    return broadcast_api


def _build_client(
    service: FakeBroadcastOverlayService,
    *,
    role: str = "ADMIN",
    authenticated: bool = True,
) -> TestClient:
    broadcast_api = _broadcast_api_contract()
    app = FastAPI()
    app.include_router(broadcast_api.router)
    app.dependency_overrides[broadcast_api.get_broadcast_overlay_service] = lambda: service

    if authenticated:
        app.dependency_overrides[broadcast_api.get_broadcast_current_user] = (
            lambda: FakeUser(role=role)
        )
    else:

        def missing_user():
            raise HTTPException(status_code=401, detail="not_authenticated")

        app.dependency_overrides[broadcast_api.get_broadcast_current_user] = missing_user

    return TestClient(app)


def test_bo_u08_route_registered_on_main_app():
    from app.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/broadcast/fixtures/{external_id}/overlay" in paths


def test_bo_u01_admin_access_returns_canonical_payload():
    service = FakeBroadcastOverlayService(FULL_OVERLAY_PAYLOAD)
    client = _build_client(service, role="ADMIN")

    response = client.get(
        "/api/v1/broadcast/fixtures/1000001/overlay?league_slug=premier-league"
    )

    assert response.status_code == 200
    assert service.calls == [
        {
            "external_id": 1000001,
            "role": "ADMIN",
            "league_slug": "premier-league",
        }
    ]
    body = response.json()
    assert set(body) == {"fixture", "lineups", "statistics", "events", "polling"}
    assert body["fixture"]["league"]["theme_slug"] == "premier-league"
    assert body["lineups"][0]["players"][0]["rating"] == 7.8
    assert body["events"][0]["kind"] == "goal"
    assert body["polling"]["interval_seconds"] == 10


def test_bo_u02_streamer_access_forbidden_before_service_call():
    service = FakeBroadcastOverlayService(FULL_OVERLAY_PAYLOAD)
    client = _build_client(service, role="STREAMER")

    response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 403
    assert service.calls == []


def test_bo_u03_user_access_forbidden_before_service_call():
    service = FakeBroadcastOverlayService(FULL_OVERLAY_PAYLOAD)
    client = _build_client(service, role="USER")

    response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 403
    assert service.calls == []


def test_bo_u04_missing_auth_returns_401_before_service_call():
    service = FakeBroadcastOverlayService(FULL_OVERLAY_PAYLOAD)
    client = _build_client(service, authenticated=False)

    response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 401
    assert service.calls == []


def test_bo_u05_unknown_fixture_maps_to_404():
    service = FakeBroadcastOverlayService(None)
    client = _build_client(service, role="ADMIN")

    response = client.get("/api/v1/broadcast/fixtures/9999999/overlay")

    assert response.status_code == 404
    assert response.json()["detail"] == "fixture_not_found"


def test_bo_u09_upstream_failure_without_fallback_maps_to_502():
    from app.services.broadcast import BroadcastOverlayError

    service = FakeBroadcastOverlayService(
        None,
        raises=BroadcastOverlayError("broadcast_upstream_unavailable"),
    )
    client = _build_client(service, role="ADMIN")

    response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 502
    assert response.json()["detail"] == "broadcast_upstream_unavailable"
    assert service.calls[0]["external_id"] == 1000001


def test_bo_u06_invalid_external_id_returns_422():
    service = FakeBroadcastOverlayService(FULL_OVERLAY_PAYLOAD)
    client = _build_client(service, role="ADMIN")

    response = client.get("/api/v1/broadcast/fixtures/not-int/overlay")

    assert response.status_code == 422
    assert service.calls == []


def test_bo_u07_partial_live_data_serializes_empty_and_null_blocks():
    service = FakeBroadcastOverlayService(PARTIAL_OVERLAY_PAYLOAD)
    client = _build_client(service, role="ADMIN")

    response = client.get("/api/v1/broadcast/fixtures/1000001/overlay")

    assert response.status_code == 200
    body = response.json()
    assert body["lineups"][0]["formation"] is None
    assert body["lineups"][0]["players"] == []
    assert body["statistics"][0]["home"] is None
    assert body["statistics"][0]["home_display"] == "-"
    assert body["events"] == []
