"""Independent localhost-only harness; never uses production DB/Redis/Vertex.

Run from repository root with PYTHONPATH=. python .../fixture_server.py.
Actual news/general routers and services + SQLite SQL. The team squad query's
Postgres ARRAY_AGG is replaced by an empty result (squad is outside card scope).
Auth refresh is a test-only token issuer; /auth/me and manager checks are real.
No current_user/manager_user overrides. No product files are modified.
"""
from __future__ import annotations

from datetime import datetime, timezone
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from sqlalchemy import create_engine, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app import db
from app.api.v1 import auth, general, news_analysis as api
from app.core import sessions
from app.models import (
    AppUser, Coach, CoachTranslation, Fixture, League, LeagueTranslation, NewsArticle,
    Player, PlayerSeasonStat, PlayerTranslation, Team, TeamCoach, TeamSeason,
    TeamTranslation, Venue,
)
from app.services import news_analysis as service

@compiles(JSONB, "sqlite")
def sqlite_json(_type, _compiler, **_kw):
    return "JSON"

engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
for model in (AppUser, Venue, League, LeagueTranslation, Team, TeamTranslation,
              TeamSeason, Player, PlayerTranslation, PlayerSeasonStat, Coach,
              CoachTranslation, TeamCoach, Fixture, NewsArticle):
    model.__table__.create(engine)
with Session(engine) as session:
    session.add_all([
        AppUser(id=i, email=f"test{i}@example.invalid", password_hash="test-only", role=role, is_active=active)
        for i, role, active in [(1,"STREAMER",True),(2,"ADMIN",True),(3,"USER",True),(4,"ADMIN",False)]
    ])
    session.add(Venue(id=1, external_id=1, name="Fixture Stadium", city="London", capacity=60000))
    session.add(NewsArticle(id=1,source="Independent fixture",source_url="https://example.com/existing-news",original_title="Existing saved football news",title_ko="기존 저장 뉴스",published_at=datetime(2026,10,27,12,tzinfo=timezone.utc)))
    session.add_all([
        League(id=1,external_id=39,name="Premier League",type="League",slug="premier-league",current_season=2026,is_active=True),
        League(id=2,external_id=45,name="FA Cup",type="Cup",slug="fa-cup",current_season=2026,is_active=True),
        Team(id=42,external_id=42,name="Arsenal",slug="arsenal",country="England",venue_id=1),
        Team(id=50,external_id=50,name="Manchester City",slug="manchester-city",country="England"),
        TeamTranslation(team_id=42,name_ko="아스널"),
        TeamSeason(team_id=42,league_id=1,season_year=2026),
        Player(id=10,external_id=10,name="B. Saka",firstname="Bukayo Ayoyinka Temidayo",lastname="Saka",slug="bukayo-saka",nationality="England",current_team_id=42),
        PlayerTranslation(player_id=10,name_ko="부카요 사카"),
        Player(id=11,external_id=11,name="José Silva",firstname="José",lastname="Silva",slug="jose-silva",nationality="Portugal",current_team_id=50),
        Player(id=12,external_id=12,name="Alex One",firstname="Alex",lastname="One",slug="alex-one"),
        Player(id=13,external_id=13,name="Alex Two",firstname="Alex",lastname="Two",slug="alex-two"),
        PlayerTranslation(player_id=12,name_ko="김민수"),PlayerTranslation(player_id=13,name_ko="김민수"),
        Player(id=14,external_id=14,name="Chris Test",firstname="Chris Albert",lastname="Test",slug="chris-test-a"),
        Player(id=15,external_id=15,name="Chris Test",firstname="Christopher",lastname="Test",slug="chris-test-b"),
        Fixture(id=1,external_id=101,league_id=1,season_year=2026,home_team_id=42,away_team_id=50,
                kickoff_at=datetime(2026,10,27,12,tzinfo=timezone.utc),status_short="FT",goals_home=0,goals_away=1),
    ])
    for i, league, team, year, appearances, goals, assists in [
        (1,1,42,2026,0,0,None),(2,2,50,2026,2,1,0),(3,1,42,2025,99,88,77),
    ]:
        session.add(PlayerSeasonStat(id=i,player_id=10,team_id=team,league_id=league,season_year=year,
                                    appearances=appearances,goals=goals,assists=assists,raw_stats={}))
    session.commit()

observations = {"model_calls":0,"sql_reads":0,"writes":0,"posts":0,"detail_gets":{}}
@event.listens_for(engine, "before_cursor_execute")
def readonly(_conn,_cursor,statement,_params,_context,_many):
    if not statement.lstrip().upper().startswith(("SELECT", "PRAGMA")):
        observations["writes"] += 1
        raise AssertionError("runtime DB writes forbidden in independent fixture")
    observations["sql_reads"] += 1

class ReadSession(Session):
    def execute(self, statement, *args, **kwargs):
        if "ARRAY_AGG(" in str(statement):
            return super().execute(text("SELECT 1 WHERE 0"))
        return super().execute(statement,*args,**kwargs)

def isolated_session():
    with ReadSession(engine) as session:
        yield session

sessions._secret = lambda: "independent-news-tests-secret-32-plus-characters"
api.limiter = service.AnalysisLimiter()
service.limiter = api.limiter

def provider_extract(self, article):
    observations["model_calls"] += 1
    if "[FAIL]" in article:
        raise ValueError("PRIVATE_ARTICLE_MUST_NOT_LEAK")
    if "[SLOW]" in article:
        time.sleep(.7)
    if "[TIMEOUT]" in article:
        raise TimeoutError()
    relevance = "not_football" if "[NOT_FOOTBALL]" in article else "uncertain" if "[UNCERTAIN]" in article else "football"
    evidence = "" if "[NO_EVIDENCE]" in article else article[:600]
    mentions = []
    for name, kind in [("Arsenal","team"),("Manchester City","team"),("Bukayo Saka","player"),
                       ("부카요 사카","player"),("José Silva","player"),("김민수","player"),
                       ("Chris Test","player"),("Saka","player"),("사카왕","player"),("Missing Name","player")]:
        if name in article:
            mentions.append({"mention":name,"evidence":article[:600],"entity_type":kind})
    if "[FAKE_EVIDENCE]" in article:
        mentions=[{"mention":"Arsenal","evidence":"fabricated excerpt", "entity_type":"team"}]
    return {"relevance":relevance,"relevance_evidence":evidence,"mentions":mentions}

api.NewsVertexProvider.extract = provider_extract
app = FastAPI()
app.dependency_overrides[db.get_db_session] = isolated_session
app.include_router(api.router)
app.include_router(general.router)
app.include_router(auth.router)

@app.middleware("http")
async def record(request: Request, call_next):
    if request.url.path.endswith("/news/analyze"):
        observations["posts"] += 1
    if request.url.path.startswith(("/api/v1/teams/","/api/v1/players/")):
        key=request.url.path
        observations["detail_gets"][key]=observations["detail_gets"].get(key,0)+1
    return await call_next(request)

# Remove real refresh only; access-token authentication and /me are real.
app.router.routes[:] = [r for r in app.router.routes if getattr(r,"path",None)!="/api/v1/auth/refresh"]
@app.post("/api/v1/auth/refresh")
def fixture_refresh(request: Request):
    user_id=int(request.cookies.get("fixture_user","1"))
    with Session(engine) as session:
        user=session.get(AppUser,user_id)
        if not user or not user.is_active:
            raise HTTPException(401,"fixture inactive")
        return {"access_token":sessions.encode_token(user_id,"access",lifetime=900),
                "user":{"id":user.id,"email":user.email,"nickname":"Independent tester","role":user.role,"is_active":user.is_active}}

@app.get("/health")
def health():
    return {"fixture":"independent-v2","external_services":"none"}

@app.get("/__fixture/observations")
def observed():
    return observations

@app.post("/__fixture/reset")
def reset():
    api.limiter.calls.clear()
    observations.update(model_calls=0,sql_reads=0,writes=0,posts=0,detail_gets={})
    return {"reset":True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=8027,access_log=False)
