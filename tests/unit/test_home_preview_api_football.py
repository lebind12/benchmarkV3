import copy
import json
from pathlib import Path

from app.schemas.home_preview import clock
from app.services.home_preview_api_football import ApiFootballPreviewEvidence

CAPTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures/api_football/home_preview_1557444.json").read_text()
)


def snapshot():
    from app.services.home_preview import missing

    now = CAPTURE["_capture"]["checked_at"]
    return {
        "schema_version": "1.1",
        "is_mock": False,
        "search_suggestions": None,
        "fixture": {
            "external_id": 1557444,
            "kickoff_at": "2026-10-25T14:00:00+00:00",
            "home": {"external_id": 40, "name": "Liverpool"},
            "away": {"external_id": 51, "name": "Brighton"},
        },
        "generated_at": None,
        "as_of": now,
        "sources": [],
        "facts": {k: missing() for k in ("injuries", "home_form", "away_form")},
        "analysis": {
            k: missing("generation_pending") for k in ("summary", "key_points", "ai_prediction")
        },
        "external": {k: missing() for k in ("predictions", "odds")},
    }


class Client:
    def __init__(self):
        self.values = copy.deepcopy(CAPTURE)
        self.calls = []

    def get(self, path, **params):
        self.calls.append((path, params))
        return self.values[
            {
                "/leagues": "league_coverage",
                "/injuries": "injuries",
                "/odds": "odds",
                "/predictions": "predictions",
            }[path]
        ]


def test_real_capture_preserves_api_numbers_statuses_and_update_clock():
    client = Client()
    provider = ApiFootballPreviewEvidence(client, league_id=39, season_year=2026)
    result, usage = provider(snapshot(), now=clock(CAPTURE["_capture"]["checked_at"]))
    assert len(result["facts"]["injuries"]["data"]) == 30
    assert {r["availability"] for r in result["facts"]["injuries"]["data"]} == {"out", "doubtful"}
    odds = result["external"]["odds"]["data"]
    assert [r["bookmaker"] for r in odds] == ["Bet365", "William Hill", "Marathonbet"]
    assert odds[0]["home"] == 2.10 and odds[0]["draw"] == 3.80 and odds[0]["away"] == 3.20
    assert result["external"]["odds"]["as_of"] == "2026-10-24T21:18:23+00:00"
    assert usage["api_football_requests"] == 4
    assert (
        result["external"]["predictions"]["data"][0]["summary"]
        == CAPTURE["predictions"]["response"][0]["predictions"]["advice"]
    )


def test_no_reported_injuries_is_not_confirmed_zero():
    client = Client()
    client.values["injuries"]["response"] = []
    result, _ = ApiFootballPreviewEvidence(client, league_id=39, season_year=2026)(
        snapshot(), now=clock(CAPTURE["_capture"]["checked_at"])
    )
    assert result["facts"]["injuries"]["status"] == "missing"
    assert result["facts"]["injuries"]["data"] is None


def test_wrong_fixture_stale_odds_and_wrong_market_cannot_publish():
    client = Client()
    client.values["injuries"]["response"][0]["fixture"]["id"] = 99
    client.values["odds"]["response"][0]["update"] = "2026-10-20T00:00:00Z"
    result, _ = ApiFootballPreviewEvidence(client, league_id=39, season_year=2026)(
        snapshot(), now=clock(CAPTURE["_capture"]["checked_at"])
    )
    assert result["facts"]["injuries"]["status"] == "error"
    assert result["external"]["odds"]["data"] is None
    client = Client()
    for book in client.values["odds"]["response"][0]["bookmakers"]:
        book["bets"][0]["id"] = 2
    result, _ = ApiFootballPreviewEvidence(client, league_id=39, season_year=2026)(
        snapshot(), now=clock(CAPTURE["_capture"]["checked_at"])
    )
    assert result["external"]["odds"]["data"] is None


def test_coverage_failure_is_error_not_reported_as_missing_data():
    from app.workers.daily_sync.api import ApiFootballError

    class FailedClient:
        def get(self, *args, **kwargs):
            raise ApiFootballError("private auth diagnostic")

    result, _ = ApiFootballPreviewEvidence(FailedClient(), league_id=39, season_year=2026)(
        snapshot(), now=clock(CAPTURE["_capture"]["checked_at"])
    )
    assert result["facts"]["injuries"]["status"] == "error"
    assert result["external"]["odds"]["reason"] == "upstream_failed"
    assert "private auth diagnostic" not in str(result)


def test_current_fixture_identity_disagreement_cannot_publish_odds_for_wrong_sides():
    import pytest

    client = Client()
    client.values["predictions"]["response"][0]["teams"]["away"]["id"] = 999
    with pytest.raises(ValueError, match="prediction_identity"):
        ApiFootballPreviewEvidence(client, league_id=39, season_year=2026)(
            snapshot(), now=clock(CAPTURE["_capture"]["checked_at"])
        )
