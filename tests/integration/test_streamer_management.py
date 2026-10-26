"""Real Postgres + FastAPI management flows; football and Upstash are fixtures."""

import copy
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import sessionmaker

from app import db
from app.main import app
from app.core import sessions
from app.core.config import get_settings
from app.core.security import hash_password
from app.models import (
    Base,
    AppUser,
    ApiFootballLeagueCatalog,
    League,
    LeagueTranslation,
    TranslationAudit,
    ManagementRun,
)
from app.services import management_runs

pytestmark = pytest.mark.integration
BASE = "/api/v1/admin/management"
LEAGUE = {
    "league": {"id": 39, "name": "Premier League", "type": "League"},
    "country": {"name": "England"},
    "seasons": [
        {"year": y, "current": y == 2026, "coverage": {"standings": True}}
        for y in [2027, 2026, 2025, 2024]
    ],
}


@pytest.fixture()
def management_client(isolated_db, monkeypatch):
    baseline, schema = isolated_db
    engine = create_engine(baseline.url, pool_size=4, max_overflow=0)

    @event.listens_for(engine, "connect")
    def search_path(connection, _):
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}"')
        connection.autocommit = False

    Base.metadata.create_all(engine)
    sql = next(Path("supabase/migrations").glob("*_streamer_management.sql")).read_text()
    with engine.begin() as connection:
        connection.exec_driver_sql(sql)
    factory = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", factory)

    def session_dependency():
        with factory() as session:
            yield session

    app.dependency_overrides[db.get_db_session] = session_dependency
    monkeypatch.setenv("JWT_SECRET_KEY", "t" * 48)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("UPSTASH_REDIS_KEY_PREFIX", "local:test:")
    monkeypatch.setenv("API_FOOTBALL_KEY", "fixture-only")
    get_settings.cache_clear()
    # Atomic in-memory substitute verifies the exact Redis rotation protocol.
    tokens = {}
    lock = threading.Lock()

    def redis(*args):
        with lock:
            if args[0] == "SET":
                tokens[args[1]] = args[2]
                return "OK"
            if args[0] == "DEL":
                return tokens.pop(args[1], None)
            if args[0] == "EVAL":
                key, old, new = args[3:6]
                if key not in tokens:
                    return 0
                if tokens[key] != old:
                    tokens.pop(key, None)
                    return -1
                tokens[key] = new
                return 1
            raise AssertionError(args[0])

    monkeypatch.setattr(sessions, "redis_command", redis)
    with factory() as session:
        for role in ["USER", "STREAMER", "ADMIN"]:
            session.add(
                AppUser(
                    email=f"{role.lower()}@example.test",
                    password_hash=hash_password("Bench1234"),
                    role=role,
                    nickname=role,
                )
            )
        session.add(
            ApiFootballLeagueCatalog(
                external_id=39,
                name="Premier League",
                type="League",
                country_name="England",
                current_season=2026,
                seasons=LEAGUE["seasons"],
            )
        )
        session.commit()
    client = TestClient(app)
    yield client, factory
    app.dependency_overrides.clear()
    get_settings.cache_clear()
    engine.dispose()


def login(client, role="STREAMER"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": f"{role.lower()}@example.test", "password": "Bench1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def target(client, headers, **changes):
    payload = dict(
        league_id=39,
        season=2026,
        include_details=False,
        include_players=False,
        include_standings=False,
        fixture_limit=10,
    )
    response = client.post(BASE + "/targets", headers=headers, json={**payload, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_roles_current_db_role_and_refresh_replay(management_client):
    client, factory = management_client
    assert client.get(BASE + "/targets").status_code == 401
    user = login(client, "USER")
    assert client.get(BASE + "/targets", headers=user).status_code == 403
    streamer = login(client)
    assert client.get(BASE + "/targets", headers=streamer).status_code == 200
    old_cookie = client.cookies.get("benchmark_refresh")
    refreshed = client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.cookies.get("benchmark_refresh") != old_cookie
    client.cookies.set(
        "benchmark_refresh", old_cookie, domain="testserver.local", path="/api/v1/auth"
    )
    assert client.post("/api/v1/auth/refresh").status_code == 401
    with factory() as session:
        person = session.scalar(select(AppUser).where(AppUser.role == "STREAMER"))
        person.role = "USER"
        session.commit()
    assert client.get(BASE + "/targets", headers=streamer).status_code == 403
    assert client.get("/api/v1/admin/sync-targets").status_code == 401
    assert (
        client.post(
            "/api/v1/admin/daily-sync/run", headers=streamer, json={"fallback_defaults": True}
        ).status_code
        == 403
    )


def test_catalog_latest_actual_seasons_target_upsert_null_and_exclusion(management_client):
    client, factory = management_client
    headers = login(client)
    catalog = client.get(BASE + "/catalog", headers=headers).json()
    assert catalog["items"][0]["seasons"] == [2026, 2025]
    assert (
        client.post(
            BASE + "/targets", headers=headers, json={"league_id": 39, "season": 2024}
        ).status_code
        == 422
    )
    first = target(client, headers)
    again = target(client, headers)
    assert first["id"] == again["id"]
    assert (
        client.patch(
            BASE + f"/targets/{first['id']}", headers=headers, json={"fixture_limit": None}
        ).json()["fixture_limit"]
        is None
    )
    assert (
        client.patch(
            BASE + f"/targets/{first['id']}", headers=headers, json={"is_active": None}
        ).status_code
        == 422
    )
    client.patch(BASE + f"/targets/{first['id']}", headers=headers, json={"is_active": False})
    with factory() as session:
        assert session.scalar(select(League.is_active)) is False
    client.patch(BASE + f"/targets/{first['id']}", headers=headers, json={"is_active": True})
    assert client.delete(BASE + f"/targets/{first['id']}", headers=headers).status_code == 200
    with factory() as session:
        assert session.scalar(select(League.id)) is not None
        assert session.scalar(select(League.is_active)) is False


def test_translation_search_edit_conflict_audit_and_worker_import_protection(management_client):
    client, factory = management_client
    headers = login(client)
    target(client, headers)
    row = client.get(BASE + "/translations?query=Premier&type=league", headers=headers).json()[
        "items"
    ][0]
    url = BASE + f"/translations/league/{row['id']}"
    edit = {"name_ko": "프리미어리그", "short_name_ko": None, "expected_version": row["version"]}
    updated = client.patch(url, headers=headers, json=edit)
    assert updated.status_code == 200, updated.text
    assert updated.json()["protected"] is True
    conflict = client.patch(url, headers=headers, json=edit)
    assert conflict.status_code == 409
    assert conflict.json()["current"]["name_ko"] == "프리미어리그"
    cleared = client.patch(
        url,
        headers=headers,
        json={**edit, "name_ko": None, "expected_version": updated.json()["version"]},
    ).json()
    with factory() as session:
        session.execute(
            text("UPDATE league_translation SET name_ko=:v WHERE league_id=:id"),
            {"v": "AUTO OVERWRITE", "id": row["id"]},
        )
        session.commit()
        stored = session.get(LeagueTranslation, row["id"])
        assert stored.name_ko is None and stored.version == cleared["version"]
        assert len(session.scalars(select(TranslationAudit)).all()) == 2
    assert len(client.get(url + "/history", headers=headers).json()["items"]) == 2
    assert (
        client.get(BASE + "/translations?status=untranslated&type=league", headers=headers).json()[
            "total"
        ]
        == 1
    )


def test_durable_run_cancel_overlap_and_history(management_client, monkeypatch):
    client, factory = management_client
    headers = login(client)
    saved = target(client, headers)
    entered = threading.Event()
    release = threading.Event()

    def fake_execute(payload, guard):
        tracker = management_runs.RunTracker(payload)
        payload["status"] = "running"
        payload["items"][0].update(total=10, saved=2, pending=8, status="running", stored_rows=3)
        tracker.flush(force=True)
        entered.set()
        release.wait(5)
        try:
            tracker.check_cancelled()
        except management_runs.SyncCancelled:
            payload["status"] = "cancelled"
            payload["items"][0]["status"] = "cancelled"
            payload["finished_at"] = management_runs.stamp()
        tracker.flush(force=True)
        guard.__exit__(None, None, None)

    monkeypatch.setattr(management_runs, "execute_run", fake_execute)
    created = client.post("/api/v1/admin/daily-sync/run", headers=headers, json={})
    assert created.status_code == 200, created.text
    assert entered.wait(3)
    run_id = created.json()["id"]
    assert (
        client.get(f"/api/v1/admin/daily-sync/runs/{run_id}", headers=headers).json()["id"]
        == run_id
    )
    assert client.get(BASE + "/runs", headers=headers).json()["active"]["id"] == run_id
    assert (
        client.post(
            BASE + "/runs", headers=headers, json={"target_ids": [saved["id"]], "mode": "refresh"}
        ).status_code
        == 409
    )
    cancelled = client.post(BASE + f"/runs/{run_id}/cancel", headers=headers)
    assert cancelled.json()["status"] == "cancel_requested"
    release.set()
    for _ in range(100):
        current = client.get(BASE + f"/runs/{run_id}", headers=headers).json()
        if current["status"] == "cancelled":
            break
        time.sleep(0.02)
    assert current["status"] == "cancelled"
    assert current["items"][0]["stored_rows"] == 3
    assert client.get(BASE + "/runs", headers=headers).json()["active"] is None


def test_log_counters_survive_tail_truncation(management_client):
    client, factory = management_client
    payload = {
        "id": "counter-test",
        "mode": "refresh",
        "status": "running",
        "items": [{"target_id": 1, "total": 0, "saved": 0, "failed": 0}],
        "logs": [],
        "log_statistics": {},
        "_log_total": 0,
    }
    with factory() as session:
        session.add(
            ManagementRun(id=payload["id"], status="running", payload=copy.deepcopy(payload))
        )
        session.commit()
    tracker = management_runs.RunTracker(payload)
    tracker.item = payload["items"][0]
    tracker.last_flush = time.monotonic()
    for _ in range(1100):
        tracker.log("ReadTimeout", code="API_TIMEOUT", level="error")
    tracker.flush(force=True)
    with factory() as session:
        stored = session.get(ManagementRun, payload["id"]).payload
        assert len(stored["logs"]) == 1000
        assert stored["log_counts"] == {"total": 1100, "retained": 1000, "dropped": 100}
        assert stored["log_statistics"]["API_TIMEOUT"]["errors"] == 1100


def wait_run(client, headers, run_id):
    for _ in range(200):
        response = client.get(BASE + f"/runs/{run_id}", headers=headers)
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] not in management_runs.ACTIVE:
            return run
        time.sleep(0.03)
    raise AssertionError("collection did not finish")


def test_real_runner_initial_refresh_and_retry_events(management_client, monkeypatch):
    import httpx
    from app.models import Fixture
    from app.workers.daily_sync.api import ApiFootballClient

    client, factory = management_client
    headers = login(client)
    saved = target(client, headers, fixture_limit=None)
    fail_teams = False

    def respond(request):
        path = request.url.path
        if path == "/leagues":
            body = {"response": [LEAGUE]}
        elif path == "/teams":
            if fail_teams:
                raise httpx.ReadTimeout("fixture timeout")
            body = {
                "response": [
                    {"team": {"id": id, "name": name}}
                    for id, name in [(40, "Liverpool"), (42, "Arsenal")]
                ]
            }
        elif path == "/fixtures":
            body = {
                "response": [
                    {
                        "fixture": {"id": id, "date": date, "status": {"short": "NS"}, "venue": {}},
                        "league": {"id": 39, "season": 2026, "round": "Round 1"},
                        "teams": {
                            "home": {"id": 40, "name": "Liverpool"},
                            "away": {"id": 42, "name": "Arsenal"},
                        },
                        "goals": {},
                        "score": {},
                    }
                    for id, date in [
                        (1001, "2026-01-01T12:00:00+00:00"),
                        (1002, "2027-01-01T12:00:00+00:00"),
                    ]
                ]
            }
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=body)

    original = ApiFootballClient.__post_init__

    def fixture_init(self):
        original(self)
        self._client.close()
        self._client = httpx.Client(
            base_url="https://football.fixture", transport=httpx.MockTransport(respond)
        )
        self.backoff_seconds = 0
        self.rate_limiter = None

    monkeypatch.setattr(ApiFootballClient, "__post_init__", fixture_init)

    def execute(mode):
        response = client.post(
            BASE + "/runs", headers=headers, json={"target_ids": [saved["id"]], "mode": mode}
        )
        assert response.status_code == 200, response.text
        return wait_run(client, headers, response.json()["id"])

    original_backfill = management_runs.backfill_measured_league
    attempts = []

    def one_deadlock(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("deadlock detected")
        return original_backfill(*args, **kwargs)

    monkeypatch.setattr(management_runs, "backfill_measured_league", one_deadlock)
    initial = execute("initial")
    assert initial["status"] == "succeeded", "\n".join(
        log["message"] for log in initial["logs"] if log.get("level") == "error"
    )
    assert initial["items"][0]["stored_rows"] > 0
    assert initial["log_statistics"]["DB_RETRY"]["warnings"] == 1
    with factory() as session:
        assert len(session.scalars(select(Fixture)).all()) == 2
    refresh = execute("refresh")
    assert refresh["status"] == "succeeded", "\n".join(
        log["message"] for log in refresh["logs"] if log.get("level") == "error"
    )
    assert refresh["items"][0]["stored_rows"] < initial["items"][0]["stored_rows"]
    # It is a limited initial data scope, never mislabeled as complete.
    assert (
        client.get(BASE + "/targets", headers=headers).json()["items"][0]["initial_status"]
        == "일부 적재"
    )
    fail_teams = True
    failed = execute("refresh")
    assert failed["status"] == "partial_failed", failed
    assert failed["log_statistics"]["API_TIMEOUT"]["warnings"] == 2
    assert failed["log_statistics"]["API_TIMEOUT"]["errors"] == 1
    assert failed["items"][0]["failed"] > 0
    summaries = client.get(BASE + "/runs", headers=headers).json()["items"]
    assert all(not item["logs"] for item in summaries)
    assert any(item["log_statistics"] for item in summaries)


def test_orphan_recovery_requires_free_advisory_lock(management_client):
    from datetime import timedelta

    client, factory = management_client
    headers = login(client)
    payload = {
        "id": "orphan",
        "mode": "refresh",
        "status": "running",
        "created_at": management_runs.stamp(),
        "started_at": management_runs.stamp(),
        "items": [
            {"target_id": 1, "status": "running", "total": 4, "saved": 2, "pending": 2, "failed": 0}
        ],
        "logs": [],
        "log_statistics": {},
        "actor": "STREAMER",
        "parent_run_id": None,
        "progress": 50,
        "stage": "running",
    }
    with factory() as session:
        session.add(
            ManagementRun(
                id="orphan",
                status="running",
                payload=payload,
                heartbeat_at=management_runs.now() - timedelta(minutes=2),
            )
        )
        session.commit()
    recovered = client.get(BASE + "/runs/orphan", headers=headers).json()
    assert recovered["status"] == "interrupted"
    assert recovered["items"][0]["pending"] == 2
    assert recovered["log_statistics"]["RUN_INTERRUPTED"]["errors"] == 1
    assert recovered["log_counts"] == {"total": 1, "retained": 1, "dropped": 0}
