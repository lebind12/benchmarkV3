"""Worker-only normalizers based on captured official API-Football responses.

No new provider response ORM models. Raw API mappings are verified against
fixture identity before entering the independently defined home JSON contract.
"""

from copy import deepcopy
from datetime import timedelta
from urllib.parse import urlencode

from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview import missing
from app.services.home_preview_policy import utcnow
from app.workers.daily_sync.api import ApiFootballError

BOOKMAKER_IDS = (8, 7, 2)


class ApiFootballPreviewEvidence:
    def __init__(
        self, client, *, league_id, season_year, bookmaker_ids=BOOKMAKER_IDS, clock=utcnow
    ):
        self.clock = clock
        self.client = client
        self.league_id = league_id
        self.season_year = season_year
        self.bookmaker_ids = tuple(bookmaker_ids)
        self.coverage = None
        self.coverage_failed = False

    def __call__(self, snapshot, *, now):
        value = deepcopy(snapshot)
        fixture = value["fixture"]
        fixture_id = fixture["external_id"]
        retrieved = now.isoformat()
        calls = 0
        transport_start = getattr(self.client, "calls_total", None)
        teams = {fixture[side]["external_id"] for side in ("home", "away")}

        def request(path, **params):
            nonlocal calls
            calls += 1
            raw = self.client.get(path, **params)
            if raw.get("errors"):
                raise ValueError("upstream_failed")
            return raw

        def source(kind, title, params, published_at=None):
            nonlocal retrieved
            retrieved = self.clock().isoformat()
            sid = f"api-football-{kind}-{fixture_id}"
            value["sources"].append(
                {
                    "id": sid,
                    "fixture_id": fixture_id,
                    "kind": "api",
                    "title": title,
                    "url": "https://v3.football.api-sports.io/" + kind + "?" + urlencode(params),
                    "published_at": published_at,
                    "retrieved_at": retrieved,
                }
            )
            return sid

        try:
            if self.coverage is None:
                raw = request("/leagues", id=self.league_id, season=self.season_year)
                self.coverage = next(
                    (
                        season["coverage"]
                        for league in raw["response"]
                        if league["league"]["id"] == self.league_id
                        for season in league.get("seasons", [])
                        if season["year"] == self.season_year
                    ),
                    {},
                )
        except (ApiFootballError, ValueError, KeyError, TypeError, OverflowError):
            self.coverage = {}
            self.coverage_failed = True
        if self.coverage_failed:
            for block in (
                value["facts"]["injuries"],
                value["external"]["odds"],
                value["external"]["predictions"],
            ):
                block.update(status="error", reason="upstream_failed")
        if self.coverage.get("injuries"):
            try:
                raw = request("/injuries", fixture=fixture_id)
                injuries = []
                for row in raw["response"]:
                    if (
                        row["fixture"]["id"] != fixture_id
                        or clock(row["fixture"]["date"]) != clock(fixture["kickoff_at"])
                        or row["team"]["id"] not in teams
                        or row["league"]["id"] != self.league_id
                        or row["league"]["season"] != self.season_year
                    ):
                        raise ValueError("injury_identity")
                    availability = {"Missing Fixture": "out", "Questionable": "doubtful"}.get(
                        row["player"]["type"]
                    )
                    if availability is None:
                        raise ValueError("unknown_injury_status")
                    injuries.append(
                        {
                            "team_id": row["team"]["id"],
                            "player_name": row["player"]["name"],
                            "availability": availability,
                            "detail": row["player"].get("reason") or "사유 미제공",
                            "impact": "출전 불가" if availability == "out" else "출전 불확실",
                            "source_ids": [f"api-football-injuries-{fixture_id}"],
                        }
                    )
                if injuries:
                    sid = source("injuries", "API-Football 부상·출전 정보", {"fixture": fixture_id})
                    value["facts"]["injuries"] = {
                        "status": "available",
                        "reason": None,
                        "as_of": retrieved,
                        "source_ids": [sid],
                        "data": injuries,
                    }
                # Empty success is no reported data, not independently confirmed zero absences.
            except (ApiFootballError, ValueError, KeyError, TypeError, OverflowError):
                value["facts"]["injuries"] = {**missing("upstream_failed"), "status": "error"}
        if self.coverage.get("odds"):
            try:
                raw = request("/odds", fixture=fixture_id, bet=1)
                observed = self.clock()
                retrieved = observed.isoformat()
                odds = []
                updates = []
                if int(raw.get("paging", {}).get("total", 1)) != 1:
                    raise ValueError("incomplete_odds_pages")
                for row in raw["response"]:
                    if (
                        row["fixture"]["id"] != fixture_id
                        or clock(row["fixture"]["date"]) != clock(fixture["kickoff_at"])
                        or row["league"]["id"] != self.league_id
                        or row["league"]["season"] != self.season_year
                    ):
                        raise ValueError("odds_identity")
                    update = clock(row["update"])
                    if not observed - timedelta(hours=6) <= update <= observed or update >= clock(
                        fixture["kickoff_at"]
                    ):
                        continue
                    for bookmaker in sorted(
                        row["bookmakers"],
                        key=lambda b: (
                            self.bookmaker_ids.index(b["id"])
                            if b["id"] in self.bookmaker_ids
                            else len(self.bookmaker_ids)
                        ),
                    ):
                        if bookmaker["id"] not in self.bookmaker_ids:
                            continue
                        for bet in bookmaker["bets"]:
                            if bet["id"] != 1 or bet["name"] != "Match Winner":
                                continue
                            prices = {item["value"]: float(item["odd"]) for item in bet["values"]}
                            if set(prices) != {"Home", "Draw", "Away"} or any(
                                not 1 < odd < 10000 for odd in prices.values()
                            ):
                                raise ValueError("odds_market")
                            odds.append(
                                {
                                    "source_id": f"api-football-odds-{fixture_id}",
                                    "bookmaker": bookmaker["name"],
                                    "market": "1x2_90min",
                                    "format": "decimal",
                                    "home": prices["Home"],
                                    "draw": prices["Draw"],
                                    "away": prices["Away"],
                                    "collected_at": retrieved,
                                }
                            )
                            updates.append(update)
                if odds:
                    sid = source(
                        "odds",
                        "API-Football 경기 전 90분 승무패 배당",
                        {"fixture": fixture_id, "bet": 1},
                        max(updates).isoformat(),
                    )
                    value["external"]["odds"] = {
                        "status": "available",
                        "reason": None,
                        "as_of": max(updates).isoformat(),
                        "source_ids": [sid],
                        "data": odds,
                    }
            except (ApiFootballError, ValueError, KeyError, TypeError, OverflowError):
                value["external"]["odds"] = {**missing("upstream_failed"), "status": "error"}
        if self.coverage.get("predictions"):
            try:
                raw = request("/predictions", fixture=fixture_id)
                rows = raw.get("response") or []
                if len(rows) > 1 or str(raw.get("parameters", {}).get("fixture")) != str(
                    fixture_id
                ):
                    raise ValueError("prediction_fixture")
                if rows:
                    row = rows[0]
                    if (
                        row["league"]["id"] != self.league_id
                        or row["league"]["season"] != self.season_year
                        or any(
                            row["teams"][side]["id"] != fixture[side]["external_id"]
                            for side in ("home", "away")
                        )
                    ):
                        raise ValueError("prediction_identity")
                    prediction = row["predictions"]
                    winner = prediction["winner"]
                    if winner.get("id") in teams:
                        side = "home" if winner["id"] == fixture["home"]["external_id"] else "away"
                        outlook = fixture[side]["name"] + (
                            " 승리 또는 무승부 전망"
                            if prediction.get("win_or_draw") is True
                            else " 우세 전망"
                        )
                    elif (
                        winner.get("id") is None
                        and str(winner.get("name", "")).casefold() == "draw"
                    ):
                        outlook = "무승부 전망"
                    else:
                        raise ValueError("prediction_winner")
                    advice = prediction.get("advice")
                    if not isinstance(advice, str) or not advice.strip():
                        raise ValueError("prediction_advice")
                    sid = source(
                        "predictions", "API-Football 자체 알고리즘 전망", {"fixture": fixture_id}
                    )
                    value["external"]["predictions"] = {
                        "status": "available",
                        "reason": None,
                        "as_of": retrieved,
                        "source_ids": [sid],
                        "data": [{"source_id": sid, "outlook": outlook, "summary": advice}],
                    }
            except (ApiFootballError, ValueError, KeyError, TypeError, OverflowError) as exc:
                if isinstance(exc, ValueError) and str(exc) in {
                    "prediction_identity",
                    "prediction_fixture",
                }:
                    raise
                value["external"]["predictions"] = {**missing("upstream_failed"), "status": "error"}
        if len(value["sources"]) > len(snapshot["sources"]):
            value["as_of"] = retrieved
        return PreviewPayload.model_validate(value).root, {
            "api_football_requests": self.client.calls_total - transport_start
            if isinstance(transport_start, int)
            else calls
        }
