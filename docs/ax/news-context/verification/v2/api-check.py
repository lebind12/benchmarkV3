"""Independent API scenarios against actual router, JWT checks and SQLite SQL."""
from pathlib import Path
import importlib.util
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient

location=Path(__file__).parent
spec=importlib.util.spec_from_file_location("independent_fixture",location/"fixture_server.py")
h=importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
client=TestClient(h.app)
path="/api/v1/admin/management/news/analyze"
body={"article_text":"Arsenal의 Bukayo Saka가 축구 경기에서 뛰었다.","source_url":"https://source.example.invalid/post"}
results=[]
def headers(id=1, lifetime=60):
    return {"Authorization":"Bearer "+h.sessions.encode_token(id,"access",lifetime=lifetime)}
def post(article=None,**overrides):
    h.reset()
    return client.post(path,json={**body,**({"article_text":article} if article is not None else {}),**overrides},headers=headers())
def run(name,criteria,check):
    try:
        check()
        results.append({"name":name,"criteria":criteria,"status":"PASS"})
    except Exception as exc:
        results.append({"name":name,"criteria":criteria,"status":"FAIL","error":repr(exc)})
def expect(condition,message="assertion failed"):
    assert condition,message

def auth():
    for label,hdr,status in [("anonymous",{},401),("invalid",{"Authorization":"Bearer bad"},401),
                             ("expired",headers(lifetime=-60),401),("USER",headers(3),403),
                             ("inactive",headers(4),401),("deleted",headers(999),401),
                             ("STREAMER",headers(1),200),("ADMIN",headers(2),200)]:
        h.reset(); response=client.post(path,json=body,headers=hdr)
        expect(response.status_code==status,f"{label}: expected {status}, got {response.status_code}: {response.text}")
run("signed JWT and real active-account manager dependency",["AC-1"],auth)

def invalid():
    for value in ["", " ", "x"*20001]:
        response=post(value); expect(response.status_code==422,str(response.status_code));expect(h.observations["model_calls"]==0)
    for value in ["", "javascript:alert(1)", "file:///tmp/x", "https://user:pass@example.invalid", "https://example.invalid\n", "https://x:bad", "x"*2049]:
        response=post(source_url=value);expect(response.status_code==422,f"URL {value[:30]} accepted");expect(h.observations["model_calls"]==0)
    response=post("x"*20000);expect(response.status_code==200,response.text)
    response=post(source_url="http://source.example.invalid/"+"x"*(2048-len("http://source.example.invalid/")))
    expect(response.status_code==200,response.text)
run("input rejects before provider; exact limits",["AC-2"],invalid)

def candidates():
    for article,mention,status in [(body["article_text"],"Bukayo Saka","linked"),("부카요 사카는 축구 선수다.","부카요 사카","linked"),
            ("José Silva의 축구 경기", "José Silva","linked"),("김민수는 축구 선수다.","김민수","ambiguous"),
            ("Chris Test는 축구 선수다.","Chris Test","ambiguous"),("Saka 축구", "Saka","unresolved"),
            ("사카왕 축구", "사카왕","unresolved"),("Missing Name football", "Missing Name","unresolved")]:
        response=post(article);expect(response.status_code==200,response.text)
        row=next(item for item in response.json()["mentions"] if item["mention"]==mention)
        expect(row["status"]==status,f"{mention} {row}")
        expect(bool(row["entity"])==(status=="linked"))
    expect(post("[FAKE_EVIDENCE] Arsenal 축구").json()["mentions"]==[])
    for article in ["NotArsenal football","Arsenalized football","José SilvaExtra football"]:
        expect(post(article).json()["mentions"]==[],article)
run("unique exact/derived names; union collision; surname and invented evidence",["AC-3","AC-13"],candidates)

def relevance():
    for marker,expected in [("[NOT_FOOTBALL]","not_football"),("[UNCERTAIN]","uncertain"),("[NO_EVIDENCE]","uncertain")]:
        response=post(marker+" Arsenal football"); data=response.json()
        expect(response.status_code==200,response.text);expect(data["relevance"]==expected);expect(data["mentions"]==[])
    original=h.api.NewsVertexProvider.extract
    try:
        h.api.NewsVertexProvider.extract=lambda self,article:{"relevance":"american_football","relevance_evidence":article,"mentions":[]}
        expect(post().status_code==503)
        h.api.NewsVertexProvider.extract=lambda self,article:{"relevance":"football","relevance_evidence":"not in original","mentions":[]}
        expect(post().json()["relevance"]=="uncertain")
        h.api.NewsVertexProvider.extract=lambda self,article:{"relevance":"football","relevance_evidence":article,"mentions":[{"mention":"Arsenal","evidence":article,"entity_type":"team","id":999,"detail_path":"javascript:bad"}]}
        expect(post().status_code==503)
    finally:h.api.NewsVertexProvider.extract=original
run("non-football/uncertain gating and malformed/ungrounded output",["AC-7","AC-9"],relevance)

def failure_limits():
    expect(post("[FAIL] PRIVATE_ARTICLE_MUST_NOT_LEAK").status_code==503)
    response=post("[FAIL] PRIVATE_ARTICLE_MUST_NOT_LEAK");expect("PRIVATE_ARTICLE" not in response.text)
    expect(post("[TIMEOUT] Arsenal football").status_code==504)
    h.reset()
    for _ in range(3):expect(client.post(path,json=body,headers=headers()).status_code==200)
    response=client.post(path,json=body,headers=headers());expect(response.status_code==429);expect(response.headers["Retry-After"]=="60")
    h.reset();h.api.limiter.slots.acquire();h.api.limiter.slots.acquire()
    try:expect(client.post(path,json=body,headers=headers()).status_code==429)
    finally:h.api.limiter.slots.release();h.api.limiter.slots.release()
    original=h.api.get_settings
    try:
        h.api.get_settings=lambda:SimpleNamespace(news_analysis_timeout_seconds=.01)
        expect(post("[SLOW] Arsenal football").status_code==504)
    finally:h.api.get_settings=original
run("safe failure, real elapsed timeout, per-user and concurrent bounds",["AC-5","AC-7"],failure_limits)

def detail():
    before=client.get("/api/v1/news").json()
    expect(before["items"][0]["title_ko"]=="기존 저장 뉴스")
    expect(post().status_code==200)
    expect(client.get("/api/v1/news").json()==before,"analysis changed existing public news")
    response=client.get("/api/v1/players/bukayo-saka");expect(response.status_code==200,response.text)
    data=response.json();expect(data["profile"]["nationality"]=="England")
    expect(data["season_stats"][0]["season"]==2026)
    expect(any(row["appearances"]==0 and row["goals"]==0 and row["assists"] is None for row in data["season_stats"]))
    response=client.get("/api/v1/teams/arsenal");expect(response.status_code==200,response.text)
    expect(response.json()["venue"]["name"]=="Fixture Stadium")
    expect(response.json()["recent_results"][0]["goals_home"]==0)
    expect(h.observations["writes"]==0)
run("actual team/player GET and read-only SQL",["AC-8","AC-12"],detail)

report={"timestamp":datetime.now(timezone.utc).isoformat(),"environment":"FastAPI TestClient; actual routers/JWT/active-account checks; isolated SQLite; fake model only; team squad PG ARRAY_AGG empty adaptation", "results":results,"observations":h.observations}
(location/"api-results.json").write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps(report,indent=2,ensure_ascii=False))
sys.exit(any(item["status"]=="FAIL" for item in results))
