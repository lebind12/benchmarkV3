"""MP-02 원문 보관 기간 처리 수용 검사.

핵심은 `test_expired_artifact_keeps_summary`다. 만료된 원문은 열 수 없지만 요약과
기간, 해시, 실행·결과 기록은 남아서 "왜 열 수 없는지"가 화면에 남는다. 만료를
읽기 실패와 섞지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.preview import demo_pipeline, store
from app.preview.retention import (
    RAW_ARTIFACT_RETENTION_DAYS,
    STRUCTURED_RECORD_RETENTION_DAYS,
    expire_raw_artifacts,
    retention_policy,
    retention_summary,
)

RUNS = "/api/v1/admin/preview/runs"
LOGIN = "/api/v1/auth/login"


def _login_admin(client, make_user) -> dict:
    user = make_user(role="ADMIN")
    assert (
        client.post(
            LOGIN, json={"email": user["email"], "password": user["password"]}
        ).status_code
        == 200
    )
    return user


def test_expired_artifact_keeps_summary(session_factory):
    """보관 기간이 지나면 본문만 사라지고 요약·해시·기간은 남는다."""
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()

        detail = store.get_run_detail(session, created.run_id)
        before = {a["kind"]: a for a in detail.artifacts}
        original = before["raw_response"]
        assert original["status"] == "available"
        assert original["body"]

        later = datetime.now(timezone.utc) + timedelta(
            days=RAW_ARTIFACT_RETENTION_DAYS + 1
        )
        expired = expire_raw_artifacts(session, now=later)
        session.commit()
        assert len(expired) == len(detail.artifacts)

        after_detail = store.get_run_detail(session, created.run_id)
        after = {a["kind"]: a for a in after_detail.artifacts}
        gone = after["raw_response"]

        assert gone["status"] == "expired"
        assert gone["body"] is None
        assert gone["detail"] and "보관 기간이 지나" in gone["detail"]
        # 요약·해시·기간은 남는다.
        assert gone["sha256"] == original["sha256"]
        assert gone["summary"]
        assert gone["expires_at"] == original["expires_at"]
        assert gone["expired_at"] is not None

        # 실행·결과 기록은 그대로 남는다. 만료된 원문은 읽기 실패가 아니다.
        assert after_detail.summary.status.value == "succeeded"
        assert [row["version"] for row in after_detail.results] == [1, 2]
        assert after_detail.modules[0]["module_id"] == "mock_demo"


def test_expiry_is_idempotent(session_factory):
    """같은 만료 처리를 두 번 해도 이미 지운 본문을 다시 지우지 않는다."""
    with session_factory() as session:
        demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()
        later = datetime.now(timezone.utc) + timedelta(days=RAW_ARTIFACT_RETENTION_DAYS + 5)

        first = expire_raw_artifacts(session, now=later)
        session.commit()
        second = expire_raw_artifacts(session, now=later)
        session.commit()

    assert len(first) == 3
    assert second == []


def test_retention_policy_is_explicit_about_no_automatic_purge():
    policy = retention_policy()
    assert policy["raw_artifact_days"] == RAW_ARTIFACT_RETENTION_DAYS == 30
    assert policy["structured_record_days"] == STRUCTURED_RECORD_RETENTION_DAYS == 180
    assert policy["automatic_purge"] is False
    assert "스케줄러" in policy["note"]


def test_retention_summary_reports_due_and_next_expiry(session_factory):
    with session_factory() as session:
        demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()

        fresh = retention_summary(session)
        assert fresh["artifacts"] == 3
        assert fresh["expired"] == 0
        assert fresh["due_for_expiry"] == 0
        assert fresh["next_expiry_at"]

        later = datetime.now(timezone.utc) + timedelta(days=RAW_ARTIFACT_RETENTION_DAYS + 1)
        due = retention_summary(session, now=later)
        assert due["due_for_expiry"] == 3

        expire_raw_artifacts(session, now=later)
        session.commit()
        after = retention_summary(session, now=later)
        assert after["expired"] == 3
        assert after["due_for_expiry"] == 0


def test_expiry_endpoint_requires_admin_and_expires_only_raw_bodies(
    client, make_user, session_factory
):
    _login_admin(client, make_user)
    created = client.post(f"{RUNS}/mock-demo").json()

    # 아직 만료 대상이 아니다.
    response = client.post("/api/v1/admin/preview/retention/expire")
    assert response.status_code == 200
    assert response.json()["expired"] == 0

    # 실제 만료 시각을 앞당겨 본문만 지워지는지 확인한다.
    with session_factory() as session:
        session.execute(
            text(
                "UPDATE preview_dev.preview_artifacts SET expires_at = now() - interval '1 day'"
            )
        )
        session.commit()

    expired = client.post("/api/v1/admin/preview/retention/expire")
    assert expired.status_code == 200
    assert expired.json()["expired"] == 3

    detail = client.get(f"{RUNS}/{created['run_id']}").json()
    assert all(a["status"] == "expired" for a in detail["artifacts"])
    assert all(a["body"] is None for a in detail["artifacts"])
    assert detail["summary"]["status"] == "succeeded"
    assert len(detail["results"]) == 2


def test_expired_body_never_revives_after_a_second_run(session_factory):
    """만료 뒤에는 몇 번을 다시 열어도 본문이 돌아오지 않는다."""
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()
        later = datetime.now(timezone.utc) + timedelta(days=RAW_ARTIFACT_RETENTION_DAYS + 2)
        expire_raw_artifacts(session, now=later)
        session.commit()

        for _ in range(2):
            detail = store.get_run_detail(session, created.run_id)
            assert detail.artifacts
            for artifact in detail.artifacts:
                assert artifact["body"] is None


def test_artifact_redaction_happens_before_storage(session_factory):
    """저장 전에 지운다. 저장 후 조회에서 가리는 방식이 아니다."""
    with session_factory() as session:
        demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()
        bodies = list(
            session.execute(
                text("SELECT body, redacted FROM preview_dev.preview_artifacts")
            )
        )

    assert bodies
    for body, redacted in bodies:
        assert redacted is True
        assert "mock-token-value-for-redaction-check" not in (body or "")
        assert "mock-api-key-value-for-redaction-check" not in (body or "")


def test_artifact_summary_survives_without_body(session_factory):
    with session_factory() as session:
        created = demo_pipeline.create_recorded_mock_run(session, actor_id=11)
        session.commit()
        later = datetime.now(timezone.utc) + timedelta(days=RAW_ARTIFACT_RETENTION_DAYS + 1)
        expire_raw_artifacts(session, now=later)
        session.commit()

        row = session.execute(
            text(
                "SELECT summary, byte_size FROM preview_dev.preview_artifacts "
                "WHERE run_id = :run AND kind = 'raw_request'"
            ),
            {"run": created.run_id},
        ).one()

    assert row.summary["kind"] == "raw_request"
    assert row.summary["char_count"] > 0
    assert row.byte_size > 0
