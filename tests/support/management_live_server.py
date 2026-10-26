"""Local UI→FastAPI→Postgres harness with fixture football/refresh storage.

No network calls to API-Football or Upstash. Only the dedicated local test DB
is writable. Production application imports do not include this module.
"""

# ruff: noqa: E402 — environment isolation must precede application imports.
import os
from pathlib import Path
import threading
import time

os.environ.update(
    {
        "DATABASE_URL": "postgresql+psycopg://postgres:benchmark_test_only@127.0.0.1:55439/benchmark_test",
        "JWT_SECRET_KEY": "management-local-e2e-only-signing-key-48-characters",
        "UPSTASH_REDIS_KEY_PREFIX": "local:management-e2e:",
        "AUTH_COOKIE_SECURE": "false",
        "AUTH_COOKIE_NAME": "benchmark_management_test_refresh",
        "WORKER_SCHEDULER_ENABLED": "false",
        "API_FOOTBALL_KEY": "fixture-only",
        "CORS_ALLOW_ORIGINS": "http://127.0.0.1:5187,http://127.0.0.1:5173,http://localhost:5187",
    }
)

import httpx
import uvicorn
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app import db
from app.main import app
from app.core import sessions
from app.core.security import hash_password
from app.models import (
    AppUser,
    ApiFootballLeagueCatalog,
    Player,
    PlayerTranslation,
    League,
    Team,
    TeamTranslation,
    PlayerSeasonStat,
    Coach,
    TeamCoach,
    TeamSeason,
    WorkerSyncLog,
)
from app.services import management
from app.workers.daily_sync.api import ApiFootballClient

if db.engine.url.host != "127.0.0.1" or db.engine.url.port != 55439:
    raise RuntimeError("This harness requires the dedicated local test DB.")

LEAGUES = [
    {
        "league": {
            "id": ident,
            "name": name,
            "type": kind,
            "logo": f"https://media.api-sports.io/football/leagues/{ident}.png",
        },
        "country": {"name": "World" if ident in [7, 23, 803, 897] else "England"},
        "seasons": [
            {"year": year, "current": year == 2026, "coverage": {"standings": False}}
            for year in [2026, 2025]
        ],
    }
    for ident, name, kind in [
        (39, "Premier League", "League"),
        (45, "FA Cup", "Cup"),
        (140, "La Liga", "League"),
        (7, "Asian Cup", "Cup"),
        (23, "EAFF E-1 Football Championship", "Cup"),
        (803, "Asian Games", "Cup"),
        (897, "Asian Cup Women", "Cup"),
    ]
]

_tokens = {}
_token_lock = threading.Lock()


def fixture_redis(*command):
    with _token_lock:
        if command[0] == "SET":
            _tokens[command[1]] = command[2]
            return "OK"
        if command[0] == "DEL":
            return _tokens.pop(command[1], None)
        if command[0] == "EVAL":
            key, old, new = command[3:6]
            if key not in _tokens:
                return 0
            if _tokens[key] != old:
                _tokens.pop(key, None)
                return -1
            _tokens[key] = new
            return 1
        raise AssertionError(command[0])


sessions.redis_command = fixture_redis


def fixture_response(request):
    time.sleep(0.8)
    path = request.url.path
    league_id = int(request.url.params.get("league") or request.url.params.get("id") or 39)
    if path == "/leagues":
        response = [
            entry
            for entry in LEAGUES
            if not request.url.params.get("id") or entry["league"]["id"] == league_id
        ]
    elif path == "/teams":
        if league_id == 45:
            raise httpx.ReadTimeout("Local fixture: timed out fetching teams")
        response = [
            {
                "team": {
                    "id": ident,
                    "name": name,
                    "logo": f"https://media.api-sports.io/football/teams/{ident}.png",
                }
            }
            for ident, name in [(40, "Liverpool"), (42, "Arsenal")]
        ]
    elif path == "/fixtures":
        response = [
            {
                "fixture": {
                    "id": league_id * 1000 + index,
                    "date": date,
                    "status": {"short": "NS"},
                    "venue": {},
                },
                "league": {"id": league_id, "season": 2026, "round": "Round 1"},
                "teams": {
                    "home": {"id": 40, "name": "Liverpool"},
                    "away": {"id": 42, "name": "Arsenal"},
                },
                "goals": {},
                "score": {},
            }
            for index, date in [(1, "2026-01-01T12:00:00+00:00"), (2, "2027-01-01T12:00:00+00:00")]
        ]
    else:
        response = []
    return httpx.Response(200, json={"response": response, "paging": {"total": 1}})


_original_init = ApiFootballClient.__post_init__


def fixture_init(self):
    _original_init(self)
    self._client.close()
    self._client = httpx.Client(
        base_url="https://football.fixture", transport=httpx.MockTransport(fixture_response)
    )
    self.backoff_seconds = 0.1


ApiFootballClient.__post_init__ = fixture_init


def seed():
    with db.engine.begin() as connection:
        connection.exec_driver_sql(
            next(Path("supabase/migrations").glob("*_streamer_management.sql")).read_text()
        )
    with db.SessionLocal() as session:
        session.execute(
            insert(AppUser)
            .values(
                email="streamer@management.local",
                password_hash=hash_password("Bench1234"),
                role="STREAMER",
                nickname="로컬 검증 스트리머",
            )
            .on_conflict_do_nothing(index_elements=["email"])
        )
        session.execute(
            insert(AppUser)
            .values(
                email="user@management.local", password_hash=hash_password("Bench1234"), role="USER"
            )
            .on_conflict_do_nothing(index_elements=["email"])
        )
        for entry in LEAGUES:
            session.execute(
                insert(ApiFootballLeagueCatalog)
                .values(
                    external_id=entry["league"]["id"],
                    name=entry["league"]["name"],
                    type=entry["league"]["type"],
                    logo_url=entry["league"]["logo"],
                    country_name=entry["country"]["name"],
                    current_season=2026,
                    seasons=entry["seasons"],
                )
                .on_conflict_do_update(
                    index_elements=["external_id"], set_={"logo_url": entry["league"]["logo"]}
                )
            )
        session.execute(
            insert(Player)
            .values(external_id=1460, name="Bukayo Saka", slug="bukayo-saka-1460")
            .on_conflict_do_nothing(index_elements=["external_id"])
        )
        session.flush()
        player = session.scalar(select(Player).where(Player.external_id == 1460))
        session.execute(
            insert(PlayerTranslation).values(player_id=player.id).on_conflict_do_nothing()
        )
        legacy_logs = [
            {
                "ts": "2026-10-25T00:00:00Z",
                "message": "UEFA Champions League (#2) season 2026: teams failed: api_football_errors={'plan': 'Free plans do not have access to this season, try from 2022 to 2024.'}",
            },
            {
                "ts": "2026-10-25T00:00:01Z",
                "message": "Premier League (#39) season 2026: detail: /fixtures/events fixture=123 done",
            },
            {
                "ts": "2026-10-25T00:00:02Z",
                "message": "League Cup (#48) season 2026: players page=67/103 rows=20",
            },
        ]
        session.execute(
            insert(WorkerSyncLog)
            .values(
                run_id="legacy-classification-demo",
                worker_name="daily-sync",
                status="failed",
                logs=legacy_logs,
            )
            .on_conflict_do_update(index_elements=["run_id"], set_={"logs": legacy_logs})
        )
        session.commit()
        management.save_target(
            session,
            dict(
                league_id=39,
                season=2026,
                is_active=True,
                include_details=False,
                include_players=False,
                include_standings=False,
                fixture_limit=None,
            ),
        )
        # Affiliation fixtures live only in the dedicated local test DB.
        session.execute(
            insert(League)
            .values(
                external_id=140,
                name="La Liga",
                type="League",
                slug="la-liga-scope",
                current_season=2026,
            )
            .on_conflict_do_nothing(index_elements=["external_id"])
        )
        session.execute(
            insert(Coach)
            .values(external_id=999001, name="Scope Coach", slug="scope-coach-999001")
            .on_conflict_do_nothing(index_elements=["external_id"])
        )
        for ident, name, korean in [(42, "Arsenal", "아스널"), (529, "Barcelona", "바르셀로나")]:
            session.execute(
                insert(Team)
                .values(
                    external_id=ident,
                    name=name,
                    slug=f"scope-team-{ident}",
                    logo_url=f"https://media.api-sports.io/football/teams/{ident}.png",
                )
                .on_conflict_do_update(
                    index_elements=["external_id"],
                    set_={"logo_url": f"https://media.api-sports.io/football/teams/{ident}.png"},
                )
            )
            team = session.scalar(select(Team).where(Team.external_id == ident))
            session.execute(
                insert(TeamTranslation)
                .values(team_id=team.id, name_ko=korean)
                .on_conflict_do_nothing()
            )
            league = session.scalar(
                select(League).where(League.external_id == (39 if ident == 42 else 140))
            )
            coach = session.scalar(select(Coach).where(Coach.external_id == 999001))
            session.execute(
                insert(PlayerSeasonStat)
                .values(
                    player_id=player.id,
                    team_id=team.id,
                    league_id=league.id,
                    season_year=2026,
                    raw_stats={},
                )
                .on_conflict_do_nothing()
            )
            session.execute(
                insert(TeamSeason)
                .values(team_id=team.id, league_id=league.id, season_year=2026)
                .on_conflict_do_nothing()
            )
            session.execute(
                insert(TeamCoach)
                .values(team_id=team.id, coach_id=coach.id, league_id=league.id, season_year=2026)
                .on_conflict_do_nothing()
            )
        session.commit()


if __name__ == "__main__":
    seed()
    uvicorn.run(app, host="127.0.0.1", port=8016, log_level="warning")
