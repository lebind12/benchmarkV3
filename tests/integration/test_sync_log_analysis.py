"""Legacy and current logs are interpreted on read without changing persisted records."""

import pytest
from app.models import WorkerSyncLog, ManagementRun
from tests.integration.test_streamer_management import management_client, login, BASE  # noqa:F401

pytestmark = pytest.mark.integration
PLAN = "UEFA Champions League (#2) season 2026: teams failed: api_football_errors={'plan': 'Free plans do not have access to this season, try from 2022 to 2024.'}"


def test_legacy_list_and_detail_share_classified_retained_statistics(management_client):  # noqa:F811
    client, factory = management_client
    headers = login(client)
    raw = [
        {"ts": "2026-10-25T00:00:00Z", "message": PLAN},
        {
            "ts": "2026-10-25T00:00:01Z",
            "message": "Premier League (#39) season 2026: detail: /fixtures/events fixture=123 done",
        },
        {"ts": "2026-10-25T00:00:02Z", "message": "unrecognised historical text"},
    ]
    with factory() as session:
        session.add(
            WorkerSyncLog(
                run_id="legacy-analysis",
                worker_name="daily-sync",
                status="failed",
                logs=raw,
                error=PLAN,
            )
        )
        session.commit()
    listing = client.get(BASE + "/runs", headers=headers).json()
    summary = next(r for r in listing["items"] if r["id"] == "legacy-analysis")
    assert summary["logs"] == [] and summary["log_statistics_scope"] == "retained"
    assert summary["log_statistics"]["API_PLAN_RESTRICTED"]["errors"] == 1
    assert summary["log_unclassified_count"] == 1
    detail = client.get(BASE + "/runs/legacy-analysis", headers=headers).json()
    assert len(detail["logs"]) == 3  # no duplicate error appended from the run error field
    assert detail["logs"][0]["analysis"]["code"] == "API_PLAN_RESTRICTED"
    assert detail["logs"][1]["analysis"]["title"] == "경기 이벤트 조회 완료 · 경기 #123"
    assert detail["logs"][1]["analysis"]["target"] == "Premier League · 2026 시즌"
    assert detail["counts_kind"] == "legacy_unknown" and detail["items"] == []
    assert detail["log_statistics"] == summary["log_statistics"]
    with factory() as session:
        stored = session.query(WorkerSyncLog).filter_by(run_id="legacy-analysis").one()
        assert stored.logs == raw and stored.status == "failed" and stored.error == PLAN


def test_current_detail_classifies_progress_without_replacing_full_counters(management_client):  # noqa:F811
    client, factory = management_client
    headers = login(client)
    payload = {
        "id": "current-analysis",
        "status": "succeeded",
        "created_at": "2026-10-25T00:00:00Z",
        "items": [],
        "logs": [
            {
                "at": "2026-10-25T00:00:00Z",
                "message": "League Cup (#48) season 2026: players page=67/103 rows=20",
                "code": "PROGRESS",
                "level": "info",
            }
        ],
        "log_statistics": {
            "API_TIMEOUT": {"code": "API_TIMEOUT", "errors": 12, "warnings": 3, "target_ids": [1]}
        },
        "log_counts": {"total": 2000, "retained": 1, "dropped": 1999},
    }
    with factory() as session:
        session.add(ManagementRun(id="current-analysis", status="succeeded", payload=payload))
        session.commit()
    detail = client.get(BASE + "/runs/current-analysis", headers=headers).json()
    assert detail["logs"][0]["analysis"]["title"] == "선수 기록 처리 · 67/103페이지 · 20개"
    assert detail["log_statistics"] == payload["log_statistics"]
    assert detail["log_counts"] == payload["log_counts"]
    with factory() as session:
        assert session.get(ManagementRun, "current-analysis").payload == payload
