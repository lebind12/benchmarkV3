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


def start_run(session, ids, mode, user=None, parent=None):
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
                            if item["status"] == "succeeded":
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
        if payload["status"] == "succeeded" and settings.home_preview_enabled:
            tracker.check_cancelled()
            payload["stage"] = "메인 프리뷰 생성"
            tracker.log("추천 경기 프리뷰 생성을 시작합니다.", code="HOME_PREVIEW_STARTED")
            payload["home_preview"] = run_home_preview_after_sync()
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


def run_home_preview_after_sync():
    """Preserve the collection outcome even when optional preview generation fails."""
    from app.workers.home_preview import run_cycle

    try:
        return run_cycle(db.SessionLocal, execute=True)
    except Exception:
        return {"state": "failed", "reason": "generation_failed"}
