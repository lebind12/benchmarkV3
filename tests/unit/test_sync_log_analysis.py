"""Known historical formats and strict negative cases for read-only interpretation."""

import pytest
from app.services.sync_log_analysis import classify_log, analyze_logs

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("message", "category", "title"),
    [
        (
            "Premier League (#39) season 2026: details fixture=1557443",
            "details",
            "경기 상세 처리 · 경기 #1557443",
        ),
        (
            "Premier League (#39) season 2026: detail: /fixtures/players fixture=1557643 done",
            "fixture_players",
            "경기 선수 기록 조회 완료 · 경기 #1557643",
        ),
        (
            "Premier League (#39) season 2026: detail: /fixtures/lineups fixture=1557637 done",
            "lineups",
            "라인업 조회 완료 · 경기 #1557637",
        ),
        (
            "Premier League (#39) season 2026: detail: /fixtures/statistics fixture=1557641 done",
            "statistics",
            "경기 통계 조회 완료 · 경기 #1557641",
        ),
        (
            "Premier League (#39) season 2026: detail: /fixtures/events fixture=1557641 done",
            "events",
            "경기 이벤트 조회 완료 · 경기 #1557641",
        ),
        (
            "League Cup (#48) season 2026: players page=67/103 rows=20",
            "players",
            "선수 기록 처리 · 67/103페이지 · 20개",
        ),
        (
            "League Cup (#48) season 2026: players: /players page=2 done",
            "players",
            "선수 기록 조회 완료 · 2페이지",
        ),
        (
            "League Cup (#48) season 2026: players page=1/103 fetched",
            "players",
            "선수 기록 조회 완료 · 1/103페이지",
        ),
        ("League Cup (#48) season 2026: teams=92", "teams", "팀 데이터 처리 · 92개"),
        ("League Cup (#48) season 2026: fixtures=8", "fixtures", "경기 목록 데이터 처리 · 8개"),
        ("League Cup (#48) season 2026: standings=0", "standings", "순위 데이터 처리 · 0개"),
        ("League Cup (#48): catalog synced, seasons=[2026]", "catalog", "리그·시즌 카탈로그 반영"),
        ("League Cup (#48) season 2026: start", "run", "대상 시즌 수집 시작"),
        ("League Cup (#48) season 2026: complete", "run", "대상 시즌 수집 완료"),
        (
            "daily-sync: skipped because distributed lock is held",
            "run",
            "다른 수집이 실행 중이어서 이번 실행을 건너뜀",
        ),
        ("daily-sync: run started origin=[runtime metadata]", "run", "수집 실행 시작"),
        (
            "daily-sync: start League Cup (#48) seasons=[2026]",
            "run",
            "대상 수집 시작 · 시즌 [2026]",
        ),
        ("daily-sync: complete Premier League (#39)", "run", "대상 리그 수집 완료"),
        (
            "daily-sync: acquired advisory lock key=202605240001",
            "run",
            "중복 실행 방지 확인 · 수집 실행 허용",
        ),
        ("daily-sync: loaded 4 configured specs", "preparation", "수집 대상 설정 불러옴 · 4개"),
        ("daily-sync: measuring update size", "preparation", "수집할 처리 범위 확인 중"),
        (
            "daily-sync: measuring Premier League (#39) seasons=[2026]",
            "preparation",
            "수집 범위 확인 중 · 시즌 [2026]",
        ),
        (
            "daily-sync: measured Premier League (#39) units=1271",
            "preparation",
            "수집 범위 확인 · 1271개 처리 단계",
        ),
        (
            "daily-sync: measured total_units=20 leagues=4 concurrency=6 requests_per_minute=300",
            "preparation",
            "전체 수집 범위 확인 · 4개 리그 · 20개 처리 단계",
        ),
        (
            "daily-sync: run finished status=failed duration=8.21s",
            "run",
            "수집 실행 종료 · 실패 · 8.21초",
        ),
    ],
)
def test_observed_progress_formats(message, category, title):
    raw = {"message": message}
    view = classify_log(raw)
    assert view["title"] == title and view["category"] == category and view["classified"]
    assert view["level"] == "info"
    assert raw == {"message": message}


@pytest.mark.parametrize(
    ("reason", "code"),
    [
        (
            "api_football_errors={'plan': 'Free plans do not have access to this season, try from 2022 to 2024.'}",
            "API_PLAN_RESTRICTED",
        ),
        ("ReadTimeout: timed out", "API_TIMEOUT"),
        ("HTTP 429: Too Many Requests", "API_RATE_LIMIT"),
        ("HTTP 401: Unauthorized", "API_AUTH_FAILED"),
        ("HTTP 503: upstream failed", "API_UPSTREAM_ERROR"),
        ("IntegrityError: violates foreign key constraint", "DB_WRITE_FAILED"),
        ("something unfamiliar", "UNCLASSIFIED"),
    ],
)
def test_failure_causes_require_failure_context(reason, code):
    log = {"message": f"UEFA Champions League (#2) season 2026: players page=1/1 failed: {reason}"}
    view = classify_log(log)
    assert view["code"] == code and view["level"] == "error" and view["category"] == "players"
    assert view["target"] == "UEFA Champions League · 2026 시즌"
    # Current runner progress summaries must not become duplicate failures.
    assert classify_log({**log, "code": "PROGRESS", "level": "info"})["level"] == "info"


@pytest.mark.parametrize(
    "message",
    [
        "unknown response 429 failure",
        "timeout happened somewhere",
        "normal fixture=123",
        "EPL: arbitrary status 500",
    ],
)
def test_unknown_messages_are_not_guessed(message):
    assert classify_log({"message": message})["classified"] is False
    assert classify_log({"message": message})["level"] == "info"


def test_endpoint_failure_is_unknown_cause_and_summary_is_not_double_counted():
    raw = [
        {
            "message": "Premier League (#39) season 2026: detail: /fixtures/events fixture=123 failed"
        },
        {"message": "daily-sync: run finished status=failed duration=3.2s"},
        {"message": "daily-sync: skipped because distributed lock is held"},
    ]
    logs, stats = analyze_logs(raw)
    assert logs[0]["analysis"]["level"] == "error"
    assert stats["UNCLASSIFIED"]["errors"] == 1 and len(stats) == 1
    assert "analysis" not in raw[0]
