"""Durable collection execution, cooperative cancellation and full-run log counters."""

from __future__ import annotations
import copy
import re
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import delete, select, text, update
from app import db
from app.core.config import get_settings
from app.models import ManagementRun, LeagueSyncTarget
from app.services.management import ManagementError, allowed_seasons, target_payload
from app.services.worker_runs import _DailySyncAdvisoryLock
from app.services.sync_log_analysis import analyze_logs
from app.workers.daily_sync.api import ApiFootballClient
from app.workers.daily_sync.runner import (
    measure_league_sync_plan,
    backfill_measured_league,
    _is_retryable_db_error,
)

ACTIVE = ("queued", "running", "cancel_requested")
_mutex = threading.Lock()


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


class SyncCancelled(Exception):
    pass


def clean_message(value):
    message = str(value)
    settings = get_settings()
    for secret in (
        settings.api_football_key,
        settings.jwt_secret_key,
        settings.upstash_redis_rest_token,
    ):
        if secret:
            message = message.replace(secret, "[redacted]")
    return re.sub(r"(postgres(?:ql)?(?:\+psycopg)?://)[^@\s]+@", r"\1[redacted]@", message)[:2000]


def _recover_orphans(session):
    stale = session.scalars(
        select(ManagementRun).where(
            ManagementRun.status.in_(ACTIVE),
            ManagementRun.heartbeat_at < now() - timedelta(seconds=45),
        )
    ).all()
    if not stale:
        return
    # A slow live process retains the advisory lock; never mislabel it as interrupted.
    from app.services.worker_runs import DAILY_SYNC_ADVISORY_LOCK_KEY

    locked = session.scalar(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": DAILY_SYNC_ADVISORY_LOCK_KEY}
    )
    if locked:
        for row in stale:
            payload = copy.deepcopy(row.payload)
            payload.update(status="interrupted", finished_at=stamp(), stage="실행 프로세스 중단")
            for item in payload["items"]:
                if item["status"] in ACTIVE:
                    item["status"] = "interrupted"
            payload.setdefault("log_statistics", {})["RUN_INTERRUPTED"] = {
                "code": "RUN_INTERRUPTED",
                "errors": 1,
                "warnings": 0,
                "target_ids": [
                    i["target_id"] for i in payload["items"] if i["status"] == "interrupted"
                ],
            }
            payload["logs"].append(
                {
                    "at": stamp(),
                    "code": "RUN_INTERRUPTED",
                    "level": "error",
                    "message": "실행 프로세스의 연결이 끊어졌습니다. 저장된 데이터는 유지되며 대상 전체를 다시 실행할 수 있습니다.",
                }
            )
            total = payload.get("log_counts", {}).get("total", len(payload["logs"]) - 1) + 1
            payload["logs"] = payload["logs"][-1000:]
            payload["log_counts"] = {
                "total": total,
                "retained": len(payload["logs"]),
                "dropped": total - len(payload["logs"]),
            }
            row.status, row.payload = "interrupted", payload
        session.commit()


def run_list(session):
    _recover_orphans(session)
    session.execute(
        delete(ManagementRun).where(
            ManagementRun.status.not_in(ACTIVE),
            ManagementRun.created_at < now() - timedelta(days=7),
        )
    )
    session.commit()
    rows = session.execute(
        select(
            ManagementRun.status,
            ManagementRun.cancel_requested_at,
            ManagementRun.payload.op("-")("logs").label("payload"),
        )
        .where(ManagementRun.status.not_in(ACTIVE))
        .order_by(ManagementRun.created_at.desc())
        .limit(100)
    ).all()
    payloads = [_payload(r) for r in rows]
    active = session.scalar(select(ManagementRun).where(ManagementRun.status.in_(ACTIVE)).limit(1))
    if active:
        payloads.insert(0, _payload(active))
    return {
        "active": next((r for r in payloads if r["status"] in ACTIVE), None),
        "items": sorted(
            [r for r in payloads if r["status"] not in ACTIVE] + legacy_runs(session),
            key=lambda r: r["created_at"],
            reverse=True,
        )[:100],
        "limit": 100,
    }


def _payload(row):
    result = copy.deepcopy(row.payload)
    result.setdefault("logs", [])
    result["status"] = (
        "cancel_requested" if row.cancel_requested_at and row.status in ACTIVE else row.status
    )
    result["cancel_requested_at"] = (
        row.cancel_requested_at.isoformat() if row.cancel_requested_at else None
    )
    result["logs"], _ = analyze_logs(result["logs"])
    return result


def payload_view(row):
    """저장된 실행 행 하나를 응답 모양으로 만든다. **부작용이 없다.**

    `_payload`와 같은 변환을 그대로 쓰되, `run_list`처럼 오래된 기록을 지우거나 중단
    실행을 복구하지 않는다. 시험 UI의 목록·단건 조회는 정리 동작을 하지 않아야 한다.
    """
    return _payload(row)


def get_run(session, run_id):
    _recover_orphans(session)
    row = session.get(ManagementRun, run_id)
    if not row:
        legacy = next(
            (
                run
                for run in legacy_runs(session, summaries=False, run_id=run_id)
                if run["id"] == run_id
            ),
            None,
        )
        if legacy:
            return legacy
        raise ManagementError("수집 실행을 찾을 수 없습니다.", 404)
    return _payload(row)


def cancel_run(session, run_id):
    row = session.scalar(select(ManagementRun).where(ManagementRun.id == run_id).with_for_update())
    if not row:
        raise ManagementError("수집 실행을 찾을 수 없습니다.", 404)
    if row.status in ACTIVE:
        row.status = "cancel_requested"
        row.cancel_requested_at = row.cancel_requested_at or now()
        session.commit()
    return _payload(row)


class RunTracker:
    def __init__(self, payload):
        self.payload = payload
        self.item = None
        self.lock = threading.RLock()
        self.last_flush = 0.0
        self.last_cancel_check = 0.0
        self.cancelled = False
        self.closed = False
        self.stored_base = 0

    def check_cancelled(self, session=None):
        with self.lock:
            if time.monotonic() - self.last_cancel_check >= 0.3:
                if session is not None:
                    self.cancelled = bool(
                        session.scalar(
                            select(ManagementRun.cancel_requested_at).where(
                                ManagementRun.id == self.payload["id"]
                            )
                        )
                    )
                else:
                    with db.SessionLocal() as check_session:
                        self.cancelled = bool(
                            check_session.scalar(
                                select(ManagementRun.cancel_requested_at).where(
                                    ManagementRun.id == self.payload["id"]
                                )
                            )
                        )
                self.last_cancel_check = time.monotonic()
            if self.cancelled:
                raise SyncCancelled("사용자가 수집 취소를 요청했습니다.")

    def flush(self, force=False):
        with self.lock:
            if not force and time.monotonic() - self.last_flush < 1:
                return
            payload = copy.deepcopy(self.payload)
            total = sum(item["total"] for item in payload["items"])
            completed = sum(item["saved"] + item["failed"] for item in payload["items"])
            payload["progress"] = min(100, round(completed * 100 / total)) if total else 0
            payload["log_counts"] = {
                "total": payload.pop("_log_total", 0),
                "retained": len(payload["logs"]),
            }
            payload["log_counts"]["dropped"] = (
                payload["log_counts"]["total"] - payload["log_counts"]["retained"]
            )
            with db.SessionLocal() as session:
                session.execute(
                    update(ManagementRun)
                    .where(ManagementRun.id == payload["id"])
                    .values(status=payload["status"], payload=payload, heartbeat_at=now())
                )
                session.commit()
            self.last_flush = time.monotonic()

    def log(self, message, *, code="PROGRESS", level="info", **context):
        with self.lock:
            event = {
                "at": stamp(),
                "message": clean_message(message),
                "code": code,
                "level": level,
                **context,
            }
            if self.item:
                event["target_id"] = self.item["target_id"]
            self.payload["logs"].append(event)
            self.payload["_log_total"] += 1
            self.payload["logs"] = self.payload["logs"][-1000:]
            if level in {"error", "warning"}:
                group = self.payload["log_statistics"].setdefault(
                    code, {"code": code, "errors": 0, "warnings": 0, "target_ids": []}
                )
                group["errors" if level == "error" else "warnings"] += 1
                if self.item and self.item["target_id"] not in group["target_ids"]:
                    group["target_ids"].append(self.item["target_id"])
            self.flush()

    def api_event(self, **event):
        self.log(**event)

    def add_total(self, amount):
        if self.item:
            self.item["total"] += amount

    def set_total(self, amount):
        if self.item:
            self.item["total"] = amount

    def advance(self, amount=1, message=None):
        self.check_cancelled()
        with self.lock:
            if self.item:
                self.item["failed" if message and " failed" in message else "saved"] += amount
                self.item["pending"] = max(
                    0, self.item["total"] - self.item["saved"] - self.item["failed"]
                )
            if message:
                self.log(message)
            self.flush()

    def stored(self, counts):
        with self.lock:
            if self.item:
                values = asdict(counts)
                self.item["stored_rows"] = (
                    self.stored_base
                    + sum(value for value in values.values() if isinstance(value, int))
                    + sum(values["translation_rows"].values())
                )
            self.flush()


def start_run(session, ids, mode, user=None, parent=None, test_scope=None):
    """수집 실행을 만든다. `test_scope`가 있으면 **그 요청에만** 시험 범위가 붙는다.

    시험 범위는 저장 payload에 함께 실려 실행기와 종료 훅까지 전달된다. 일반 호출은
    `test_scope=None`이므로 범위·예외가 존재하지 않는다.
    """
    if not ids or (user is not None and len(ids) > 20):
        raise ManagementError("1~20개의 활성 수집 대상을 선택하세요.")
    ids = list(dict.fromkeys(ids))
    with _mutex:
        _recover_orphans(session)
        if session.scalar(
            select(ManagementRun.id).where(ManagementRun.status.in_(ACTIVE)).limit(1)
        ):
            raise ManagementError("이미 수집 중인 작업이 있습니다.", 409, "already_running")
        if parent:
            old = session.get(ManagementRun, parent)
            if not old or old.status in ACTIVE:
                raise ManagementError("재실행할 종료 작업을 찾지 못했습니다.")
            retryable = {
                i["target_id"]
                for i in old.payload["items"]
                if i["failed"]
                or i["pending"]
                or i["status"] in {"failed", "cancelled", "interrupted", "partial_failed"}
            }
            if not set(ids).issubset(retryable) or mode != old.payload["mode"]:
                raise ManagementError("실패·미처리 대상과 원래 실행 방식만 재실행할 수 있습니다.")
        targets = session.scalars(
            select(LeagueSyncTarget).where(LeagueSyncTarget.id.in_(ids))
        ).all()
        if len(targets) != len(ids) or any(not t.is_active for t in targets):
            raise ManagementError("비활성 또는 제외된 대상을 실행할 수 없습니다.")
        from app.models import League, ApiFootballLeagueCatalog

        items = []
        for target in targets:
            league = session.get(League, target.league_id)
            catalog = session.scalar(
                select(ApiFootballLeagueCatalog).where(
                    ApiFootballLeagueCatalog.external_id == league.external_id
                )
            )
            if (
                not catalog
                or target.season_year not in allowed_seasons(catalog)
                or not league.is_active
            ):
                raise ManagementError("활성 상태와 최신 두 개최 시즌을 확인하세요.")
            item = target_payload(session, target)
            items.append(
                {
                    "target_id": target.id,
                    "league_id": item["league_id"],
                    "name": item["name"],
                    "season": item["season"],
                    "standings_supported": any(
                        s.get("year") == target.season_year
                        and s.get("coverage", {}).get("standings")
                        for s in catalog.seasons
                    ),
                    "status": "queued",
                    "total": 0,
                    "saved": 0,
                    "failed": 0,
                    "pending": 0,
                    "stored_rows": 0,
                    "total_known": False,
                    "options": {
                        k: item[k]
                        for k in (
                            "include_details",
                            "include_players",
                            "include_standings",
                            "fixture_limit",
                        )
                    },
                }
            )
        guard = _DailySyncAdvisoryLock()
        guard.__enter__()
        if not guard.acquired:
            guard.__exit__(None, None, None)
            raise ManagementError("다른 수집 프로세스가 실행 중입니다.", 409, "already_running")
        created = stamp()
        payload = {
            "id": str(uuid4()),
            "mode": mode,
            "status": "queued",
            "created_at": created,
            "started_at": created,
            "finished_at": None,
            "cancel_requested_at": None,
            "actor": user.nickname or user.email if user else "정기 수집",
            "parent_run_id": parent,
            "items": items,
            "logs": [],
            "progress": 0,
            "stage": "실행 준비",
            "log_statistics": {},
            "_log_total": 0,
            "counts_kind": "processing_units",
        }
        if test_scope is not None:
            # 실행 ID를 범위에 붙여 저장한다. 같은 시험의 중복 생성 판정 키가 된다.
            payload["test_scope"] = test_scope.with_run_id(payload["id"]).to_dict()
        try:
            session.add(
                ManagementRun(
                    id=payload["id"],
                    status="queued",
                    actor_id=user.id if user else None,
                    payload=copy.deepcopy(payload),
                )
            )
            session.commit()
            thread = threading.Thread(
                target=execute_run,
                args=(copy.deepcopy(payload), guard),
                daemon=True,
                name=f"management-{payload['id']}",
            )
            thread.start()
        except Exception:
            session.rollback()
            guard.__exit__(None, None, None)
            raise
    return payload


def start_preview_test_run(
    session,
    *,
    target_ids,
    fixture_from,
    fixture_to,
    preview_fixture_ids,
    generate_after_collection=True,
    user=None,
):
    """기간 지정 프리뷰 시험 실행을 만든다(기존 실행 구조 재사용).

    검증은 여기서 끝낸다(경계). 통과하면 불변 범위 값으로 바꿔 `start_run`에 넘기고,
    실행기는 그 값을 수집 계획과 종료 훅에 전달한다. 이 요청의 두 경기만 6시간 조건
    예외를 받으며 일반 수집·정기 실행에는 범위가 전달되지 않는다.

    정기 실행과의 차이는 `test_scope` 하나뿐이다. 새 실행 엔진·모델·테이블을 만들지 않는다.

    `generate_after_collection=False`는 **수집만** 실행하는 요청이다. 범위 값에 그대로
    저장되어 실행기·종료 훅이 복원하며, 어느 종료 경로에서도 생성 호출은 0회다.
    기존 호출부는 이 인자를 넘기지 않으므로 기본값 `True`(기존 동작)가 유지된다.
    """
    from app.services.collection_test_scope import PREVIEW_TEST_MAX_FIXTURES, PreviewTestScope

    if len(preview_fixture_ids) != PREVIEW_TEST_MAX_FIXTURES:
        raise ManagementError("preview_fixture_ids에는 정확히 두 경기를 지정해야 합니다.", 422)
    if len(set(preview_fixture_ids)) != PREVIEW_TEST_MAX_FIXTURES:
        raise ManagementError("preview_fixture_ids의 두 경기는 서로 달라야 합니다.", 422)
    if fixture_from.tzinfo is None or fixture_to.tzinfo is None:
        raise ManagementError("수집 기간에는 시간대가 필요합니다.", 422)
    if fixture_from > fixture_to:
        raise ManagementError("수집 기간의 시작이 끝보다 늦을 수 없습니다.", 422)

    _require_preview_fixtures_in_scope(
        session,
        target_ids=target_ids,
        fixture_from=fixture_from,
        fixture_to=fixture_to,
        preview_fixture_ids=preview_fixture_ids,
    )

    scope = PreviewTestScope(
        fixture_from=fixture_from,
        fixture_to=fixture_to,
        preview_fixture_ids=tuple(preview_fixture_ids),
        generate_after_collection=bool(generate_after_collection),
    )
    # mode는 refresh 고정. 기존 start_run이 대상/시즌 검증·잠금·409를 그대로 처리한다.
    return start_run(session, target_ids, "refresh", user, None, test_scope=scope)


def _require_preview_fixtures_in_scope(
    session,
    *,
    target_ids,
    fixture_from,
    fixture_to,
    preview_fixture_ids,
):
    """지정한 두 경기가 **선택한 대상·기간·미래 NS 조건**에 속하는지 접수 전에 확인한다.

    잘못된 기간이나 남의 경기 ID를 받아들이면 수집은 정상 수행된 뒤 생성 단계에서 조용히
    빈 결과가 된다. 사용자는 "요청이 틀렸다"는 즉시 피드백 대신 성공한 수집과 빈 프리뷰를
    받게 되므로, 수집·외부 호출 전에 422로 거부하고 **어느 경기의 어떤 조건**이 어긋났는지
    알린다.

    리그 ID 공간을 섞지 않는다. 저장된 `Fixture.league_id`는 내부 기본키이고 선택 대상의
    리그는 외부 API 리그 ID(`League.external_id`)이므로, 대상에서 외부 ID를 꺼내 비교한다.
    """
    from app.models import Fixture, League, LeagueSyncTarget

    targets = list(
        session.scalars(select(LeagueSyncTarget).where(LeagueSyncTarget.id.in_(target_ids)))
    )
    if not targets:
        raise ManagementError("선택한 수집 대상을 찾지 못했습니다.", 422)
    # 대상이 실제 리그/시즌을 가리키는지 확인한다.
    allowed: dict[int, set[int]] = {}
    for target in targets:
        league = session.get(League, target.league_id)
        if league is None:
            raise ManagementError(
                f"수집 대상 {target.id}의 리그를 찾지 못했습니다.", 422
            )
        allowed.setdefault(int(league.external_id), set()).add(int(target.season_year))

    fixtures = list(
        session.scalars(
            select(Fixture).where(Fixture.external_id.in_(list(preview_fixture_ids)))
        )
    )
    by_external = {int(fixture.external_id): fixture for fixture in fixtures}

    for external_id in preview_fixture_ids:
        fixture = by_external.get(int(external_id))
        if fixture is None:
            raise ManagementError(
                f"경기 {external_id}를 저장된 경기에서 찾지 못했습니다."
                " 수집된 경기만 시험 대상으로 지정할 수 있습니다.",
                422,
            )
        league = session.get(League, fixture.league_id)
        league_external = int(league.external_id) if league is not None else None
        if league_external not in allowed or int(fixture.season_year) not in allowed[league_external]:
            raise ManagementError(
                f"경기 {external_id}는 선택한 수집 대상의 리그/시즌에 속하지 않습니다."
                f" (경기 리그 {league_external}, 시즌 {fixture.season_year})",
                422,
            )
        kickoff = fixture.kickoff_at
        if kickoff is None:
            raise ManagementError(f"경기 {external_id}의 킥오프 시각이 없습니다.", 422)
        if not (fixture_from <= kickoff <= fixture_to):
            raise ManagementError(
                f"경기 {external_id}의 킥오프({kickoff.isoformat()})가 요청 기간"
                f"({fixture_from.isoformat()} ~ {fixture_to.isoformat()}) 밖입니다.",
                422,
            )
        if fixture.status_short != "NS":
            raise ManagementError(
                f"경기 {external_id}는 예정(NS) 경기가 아닙니다(현재 {fixture.status_short}).",
                422,
            )


def _wants_home_preview(settings, test_scope) -> bool:
    """이 수집 종료 뒤 프리뷰 생성을 시작할지 판정한다.

    시험 범위가 **수집만 실행**을 뜻하면(`generate_after_collection=False`) 정기 플래그와
    무관하게 생성하지 않는다. 일반 수집과 기존 시험 실행은 원래 규칙 그대로다.
    """
    if test_scope is not None and not test_scope.generate_after_collection:
        return False
    return bool(getattr(settings, "home_preview_enabled", False)) or test_scope is not None


def execute_run(payload, guard):
    tracker = RunTracker(payload)
    done = threading.Event()

    def heartbeat():
        while not done.wait(5):
            try:
                tracker.flush(force=True)
            except Exception:
                pass  # Worker checks persistence again at each processing boundary.

    threading.Thread(target=heartbeat, daemon=True).start()
    client = None
    # 요청별 시험 범위. 일반 실행에는 없다(그래서 6시간 예외도 없다).
    from app.services.collection_test_scope import PreviewTestScope

    test_scope = PreviewTestScope.from_dict(payload.get("test_scope"))
    # 정상 경로에서 프리뷰 훅이 이미 돌았는지. 상위 예외 경로가 **중복 호출하지 않게** 한다.
    preview_started = False
    try:
        settings = get_settings()
        if not settings.api_football_key:
            raise ManagementError("API-Football 키가 설정되지 않았습니다.")
        client = ApiFootballClient(
            settings.api_football_key,
            host=settings.api_football_host,
            requests_per_minute=settings.api_football_requests_per_minute,
            cancellation_check=tracker.check_cancelled,
            on_event=tracker.api_event,
        )
        payload["status"] = "running"
        tracker.log("수집을 시작했습니다.", code="RUN_STARTED")
        measured = []
        for item in payload["items"]:
            tracker.item = item
            tracker.check_cancelled()
            payload["stage"] = f"{item['name']} 수집 범위 확인"
            options = item["options"]
            try:
                plan = measure_league_sync_plan(
                    client,
                    league_external_id=item["league_id"],
                    seasons=[item["season"]],
                    max_workers=settings.api_football_concurrency,
                    progress=tracker,
                    mode=payload["mode"],
                    enforce_latest=True,
                    test_scope=test_scope,
                    **options,
                )
                item["total"] = item["pending"] = plan.unit_count(
                    include_details=options["include_details"],
                    include_players=options["include_players"],
                )
                item["total_known"] = True
                measured.append((item, plan))
            except SyncCancelled:
                raise
            except Exception as exc:
                item.update(status="failed", total=1, failed=1, total_known=True)
                tracker.log(str(exc), code="TARGET_FAILED", level="error", stage="수집 범위 확인")
        for item, plan in measured:
            tracker.item = item
            tracker.check_cancelled()
            item["status"] = "running"
            payload["stage"] = f"{item['name']} {item['season']} 데이터 수집"
            options = item["options"]
            for attempt in range(1, 4):
                tracker.stored_base = item["stored_rows"]
                with db.SessionLocal() as store:
                    try:
                        result = backfill_measured_league(
                            store,
                            client,
                            plan=plan,
                            progress=tracker,
                            max_workers=settings.api_football_concurrency,
                            **{k: v for k, v in options.items() if k != "fixture_limit"},
                        )
                        item["status"] = (
                            "partial_failed"
                            if any(s.errors for s in result.seasons)
                            else "succeeded"
                        )
                        target = store.get(LeagueSyncTarget, item["target_id"])
                        if target:
                            target.last_sync = now()
                            if payload["mode"] == "initial" and item["status"] == "succeeded":
                                # Coverage-limited initial runs stay visibly partial.
                                partial = (
                                    options["fixture_limit"] is not None
                                    or not options["include_details"]
                                    or not options["include_players"]
                                    or item["standings_supported"]
                                    and not options["include_standings"]
                                )
                                target.initial_status = "일부 적재" if partial else "최초 수집 완료"
                            # 시험 범위가 있으면 시즌 정리를 하지 않는다. 정리는 수집한
                            # 리그의 오래된 시즌 행(Fixture/Injury/Standings 등)을 DELETE하므로,
                            # 기간만 좁혀 확인하는 시험이 그 부작용을 일으키면 안 된다.
                            # 기존 일반 수집의 정리 정책은 그대로 유지한다.
                            if item["status"] == "succeeded" and test_scope is None:
                                from app.services.management import prune_league_seasons

                                prune_league_seasons(store, target.league_id, plan.detected_seasons)
                            tracker.check_cancelled(session=store)
                            store.commit()
                    except SyncCancelled:
                        store.rollback()
                        raise
                    except Exception as exc:
                        store.rollback()
                        if _is_retryable_db_error(exc) and attempt < 3:
                            tracker.log(
                                str(exc),
                                code="DB_RETRY",
                                level="warning",
                                stage="데이터 저장",
                                attempt=attempt,
                                max_attempts=3,
                            )
                            item["total"] = (
                                item["saved"]
                                + item["failed"]
                                + plan.unit_count(
                                    include_details=options["include_details"],
                                    include_players=options["include_players"],
                                )
                            )
                            until = time.monotonic() + 2**attempt
                            while time.monotonic() < until:
                                tracker.check_cancelled()
                                time.sleep(0.1)
                            continue
                        item["status"] = "failed"
                        item["failed"] += 1
                        item["total"] = max(item["total"], item["saved"] + item["failed"])
                        item["pending"] = max(0, item["total"] - item["saved"] - item["failed"])
                        tracker.log(
                            str(exc), code="DB_WRITE_FAILED", level="error", stage="데이터 저장"
                        )
                break
            tracker.flush(force=True)
        failed = any(i["status"] in {"failed", "partial_failed"} for i in payload["items"])
        payload["status"] = (
            (
                "partial_failed"
                if any(i["saved"] or i["stored_rows"] for i in payload["items"])
                else "failed"
            )
            if failed
            else "succeeded"
        )
        # The regular scheduler and authenticated manual runs now share this path.
        # Preview errors must not roll back or relabel successfully committed football data.
        # API 최신화가 부분 실패·실패해도 DB의 대상 경기로 생성한다(사용자 확정 Q6).
        # 성공한 리그만으로 후보를 제한하지 않는다.
        # 정기 경로는 전역 플래그를 존중하고, 명시적 시험 요청(검증된 test_scope)은
        # 플래그가 꺼져 있어도 이 요청에 한해 훅을 한 번 호출한다. 전역 설정은 켜지 않는다.
        # 수집만 실행을 뜻하는 test_scope는 어느 경로에서도 훅을 부르지 않는다.
        if _wants_home_preview(settings, test_scope):
            preview_started = True
            tracker.check_cancelled()
            payload["stage"] = "메인 프리뷰 생성"
            tracker.log("추천 경기 프리뷰 생성을 시작합니다.", code="HOME_PREVIEW_STARTED")
            # `check_cancelled()`는 취소일 때 예외를 던진다. 그대로 넘기면 취소가
            # 프리뷰 생성 실패처럼 기록되므로, 비예외 플래그를 먼저 갱신하고 그 값을 넘긴다.
            tracker.check_cancelled()
            payload["home_preview"] = run_home_preview_after_sync(
                collection_status=payload["status"],
                cancelled=lambda: _cancel_requested(tracker),
                test_scope=test_scope,
            )
            tracker.check_cancelled()
        payload["stage"] = "수집 결과 확인"
        tracker.log(
            "수집 실행을 종료했습니다.",
            code="RUN_COMPLETED" if payload["status"] == "succeeded" else "RUN_FINISHED",
        )
    except SyncCancelled:
        payload.update(status="cancelled", stage="취소 완료")
        for item in payload["items"]:
            if item["status"] in ACTIVE:
                item["status"] = "cancelled"
        tracker.log(
            "현재 처리 단위를 중단했습니다. 이미 저장한 데이터는 유지되며 선택 대상 전체를 안전하게 재실행할 수 있습니다.",
            code="RUN_CANCELLED",
        )
    except Exception as exc:
        payload.update(status="failed", stage="수집 실행 실패")
        for item in payload["items"]:
            if item["status"] in ACTIVE:
                item["status"] = "failed"
                item["failed"] += 1
        tracker.log(str(exc), code="RUN_FAILED", level="error")
        # API 키 미설정·클라이언트 생성 실패처럼 **수집 자체가 예외로 끝난** 경우에도
        # DB에 대상 경기가 남아 있으면 생성을 시도한다(Q6). 정상 경로에서 이미 돌았으면
        # 다시 호출하지 않는다. 훅은 자체 예외를 흡수하므로 수집 실패 기록을 덮지 않는다.
        # 수집만 실행 요청은 이 경로에서도 생성하지 않는다(생성 0회 보장).
        if not preview_started and _wants_home_preview(get_settings(), test_scope):
            try:
                payload["home_preview"] = run_home_preview_after_sync(
                    collection_status="failed",
                    test_scope=test_scope,
                )
            except Exception:  # noqa: BLE001 - 프리뷰 실패가 수집 오류를 덮지 않는다
                payload["home_preview"] = {"state": "failed", "reason": "generation_failed"}
    finally:
        done.set()
        if client:
            client.close()
        payload["finished_at"] = stamp()
        try:
            tracker.flush(force=True)
        finally:
            guard.__exit__(None, None, None)


def start_scheduled_run():
    with db.SessionLocal() as session:
        ids = list(
            session.scalars(select(LeagueSyncTarget.id).where(LeagueSyncTarget.is_active)).all()
        )
        if ids:
            try:
                start_run(session, ids, "refresh")
            except ManagementError:
                return


def legacy_runs(session, summaries=True, run_id=None):
    """Expose existing completed worker_sync_log history without inventing row counts."""
    from app.models import WorkerSyncLog

    statement = select(WorkerSyncLog)
    if run_id:
        statement = statement.where(WorkerSyncLog.run_id == run_id)
    rows = session.scalars(
        statement.where(
            WorkerSyncLog.worker_name == "daily-sync",
            WorkerSyncLog.created_at >= now() - timedelta(days=7),
        )
        .order_by(WorkerSyncLog.created_at.desc())
        .limit(100)
    ).all()
    result = []
    for row in rows:
        logs = [
            {
                "at": log.get("at") or log.get("ts") or row.created_at.isoformat(),
                "message": clean_message(log.get("message", "")),
            }
            for log in row.logs
        ]
        if row.error and not any(clean_message(row.error) in log["message"] for log in logs):
            logs.append(
                {
                    "at": (row.finished_at or row.created_at).isoformat(),
                    "message": clean_message(row.error),
                    "level": "error",
                    "code": "LEGACY_FAILURE",
                }
            )
        logs, statistics = analyze_logs(logs)
        result.append(
            {
                "id": row.run_id,
                "mode": "refresh",
                "status": row.status,
                "actor": "기존 수집 실행",
                "items": [],
                "logs": [] if summaries else logs,
                "log_statistics": statistics,
                "log_statistics_scope": "retained",
                "log_unclassified_count": sum(
                    not log["analysis"]["classified"] and not log.get("level") for log in logs
                ),
                "created_at": row.created_at.isoformat(),
                "started_at": (row.started_at or row.created_at).isoformat(),
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "cancel_requested_at": None,
                "parent_run_id": None,
                "progress": row.progress_percent,
                "stage": "기존 실행 기록 · 대상별 처리 수 미기록",
                "counts_kind": "legacy_unknown",
            }
        )
    return result


def run_home_preview_after_sync(*, collection_status="succeeded", cancelled=None, test_scope=None):
    """수집 종료 뒤 기존 단일 생성 서비스로 프리뷰 생성을 시도한다.

    수집 결과(성공/부분 실패/실패)와 무관하게 **DB의 대상 경기**로 시도한다(사용자 확정
    Q6). 이 함수는 원래 수집 상태를 바꾸지 않고, 생성 결과를 별도로 돌려준다. 명시 취소는
    `cancelled`로 전달되어 새 생성을 시작하지 않는다.

    생성은 기존 `generate_match_preview(trigger="collection")`만 쓴다. 옛
    ProductionPreviewGenerator 경로를 새로 호출하지 않는다.
    """
    from app.services.home_preview_collection import (
        preview_session_factory,
        run_collection_generation,
    )
    from app.services.home_preview_policy import utcnow as _now

    settings = get_settings()
    try:
        transport = _collection_transport()
        return run_collection_generation(
            session_factory=db.SessionLocal,
            # 프리뷰 실행 기록·본문 쓰기는 preview_dev 세션으로 한다(공개 스키마에 쓰지 않음).
            # 계약: `preview_session_factory()`가 `with`에 쓸 Session을 낸다(단일 정의 재사용).
            preview_session_factory=preview_session_factory,
            collection_status=collection_status,
            now=_now(),
            transport=transport,
            cycle_limit=settings.home_preview_cycle_limit,
            cancelled=cancelled,
            test_scope=test_scope,
        )
    except Exception as exc:  # noqa: BLE001 - 프리뷰 실패는 수집 결과를 덮지 않는다
        return {
            "collection_status": collection_status,
            "state": "failed",
            "reason": f"generation_failed: {type(exc).__name__}",
        }


def _cancel_requested(tracker) -> bool:
    """취소 요청 여부를 예외 없이 확인한다. 취소를 실패로 바꾸지 않는다."""
    try:
        tracker.check_cancelled()
    except SyncCancelled:
        return True
    return bool(getattr(tracker, "cancelled", False))


def _collection_transport():
    """수집 생성용 모델 transport. 관리자 경로와 **같은 설정**에서 만든다.

    설정이 없거나 live가 꺼져 있으면 `None`이며, 호출 경계가 그 사실을 사유로 남기고
    모의 실행으로 대체하지 않는다.
    """
    from app.preview import config as preview_config
    from app.preview import provider

    preview_settings = preview_config.get_settings()
    if not preview_settings.model_live_enabled:
        return None
    return provider.GoogleGenAIHttpTransport(
        project=preview_settings.model_project,
        location=preview_settings.model_location,
        model=preview_settings.model_name,
        credentials_json=preview_settings.model_credentials_json,
    )
