"""기간 지정 프리뷰 시험 엔드포인트 직접 검사.

검사 이유(실패 시 사용자 영향): 새 엔드포인트로 기간과 두 경기를 지정했는데
(1) 기간이 실제 저장·상세 수집을 제한하지 않으면 기간 밖 경기 자료가 갱신되고,
(2) 두 지정 경기만 6시간 예외를 받지 못하면 정작 시험 대상의 프리뷰가 만들어지지 않으며,
(3) 예외가 일반 수집 경로로 새면 정기 정책이 조용히 완화된다.

**합성 검사다.** 실제 API·모델·DB를 호출하지 않는다. 라우터·실행기·수집 계획·종료 훅은
실제 진입점을 호출하고, 외부 연결(세션·클라이언트·모델·훅)만 대역으로 바꾼다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.preview.contracts import RunStatus as _RunStatus
from app.services.collection_test_scope import PreviewTestScope, PREVIEW_TEST_MAX_FIXTURES

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
WINDOW_START = datetime(2026, 11, 21, 21, 30, tzinfo=KST)
WINDOW_END = datetime(2026, 11, 22, 0, 0, tzinfo=KST)
FIXTURE_A = 1557470
FIXTURE_B = 1557476


def _scope(run_id="run-test-1"):
    return PreviewTestScope(
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
        preview_fixture_ids=(FIXTURE_A, FIXTURE_B),
        run_id=run_id,
    )


# --------------------------------------------------------------------------
# 1. 요청 계약과 인증 경계
# --------------------------------------------------------------------------


def test_request_model_rejects_timezone_free_range():
    """시간대 없는 기간은 거부된다.

    사용자 영향: 시간대를 잃으면 21:30이 UTC로 해석돼 기간이 9시간 밀리고, 지정 경기가
    엉뚱한 시각으로 판정된다.
    """
    from app.api.v1.management import PreviewTestRunCreate

    with pytest.raises(Exception):
        PreviewTestRunCreate(
            target_ids=[13],
            fixture_from="2026-11-21T21:30:00",
            fixture_to="2026-11-22T00:00:00",
            preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
        )


def test_request_model_rejects_reversed_range_and_duplicate_fixtures():
    """기간 역전과 중복/개수 위반을 거부한다."""
    from app.api.v1.management import PreviewTestRunCreate

    with pytest.raises(Exception):
        PreviewTestRunCreate(
            target_ids=[13],
            fixture_from=WINDOW_END,
            fixture_to=WINDOW_START,
            preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
        )
    with pytest.raises(Exception):
        PreviewTestRunCreate(
            target_ids=[13],
            fixture_from=WINDOW_START,
            fixture_to=WINDOW_END,
            preview_fixture_ids=[FIXTURE_A, FIXTURE_A],
        )


def test_request_model_accepts_the_specified_request():
    """현재 지정 값(target13, 11-21 21:30~11-22 00:00 KST, 두 경기)을 그대로 받는다."""
    from app.api.v1.management import PreviewTestRunCreate

    model = PreviewTestRunCreate(
        target_ids=[13],
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
        preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
    )
    assert model.preview_fixture_ids == [FIXTURE_A, FIXTURE_B]
    assert model.fixture_from.tzinfo is not None


def test_route_uses_the_existing_manager_dependency():
    """새 라우트가 기존 관리 인증 의존성을 그대로 쓴다(권한 완화 없음).

    사용자 영향: 인증이 빠지면 누구나 수집·모델 호출을 유발할 수 있다.
    """
    from app.api.v1.management import router

    # 라우터에 prefix가 걸려 있으므로 실제 경로로 확인한다.
    paths = {route.path: route for route in router.routes}
    assert "/api/v1/admin/management/runs/preview-test" in paths
    # 라우터 전체에 manager_user 의존성이 걸려 있고, 핸들러도 Manager를 받는다.
    dependency_names = [
        getattr(getattr(dep, "dependency", None), "__name__", "") for dep in router.dependencies
    ]
    assert "manager_user" in dependency_names
    handler = paths["/api/v1/admin/management/runs/preview-test"].endpoint
    assert "user" in handler.__code__.co_varnames


# --------------------------------------------------------------------------
# 2. 기간이 실제 저장·상세 대상를 제한한다
# --------------------------------------------------------------------------


def test_date_range_filters_fixture_storage_targets_not_just_display(monkeypatch):
    """기간 밖 경기는 **저장·상세 대상 목록**에서 빠진다(표시 필터가 아님).

    사용자 영향: 응답만 걸러도 저장은 기간 밖 경기까지 갱신되어, 시험이 지정 범위를
    넘어 자료를 바꾼다.

    실제 `measure_league_sync_plan`을 호출해 `season_plan.fixture_external_ids`(저장 게이트)를
    확인한다. 외부 API 응답만 대역으로 바꾼다.
    """
    from app.workers.daily_sync import runner

    inside = {"fixture": {"id": FIXTURE_A, "date": "2026-11-22T00:00:00+09:00"}}
    outside = {"fixture": {"id": 999, "date": "2026-11-25T00:00:00+09:00"}}

    class _Client:
        def response(self, path, **params):
            if path == "/leagues":
                return [
                    {
                        "league": {"id": 39, "name": "Premier League"},
                        "seasons": [{"year": 2026}, {"year": 2025}],
                    }
                ]
            return []

        def get(self, path, **params):
            # 병렬 수집은 `client.get`을 쓰고 결과를 endpoint.payload에 넣는다.
            # payload는 API 응답 모양(`{"response": [...]}`)이어야 한다.
            if path == "/fixtures":
                return {"response": [inside, outside]}
            return {"response": []}

    plan = runner.measure_league_sync_plan(
        _Client(),
        league_external_id=39,
        seasons=[2026],
        include_players=False,
        include_standings=False,
        include_details=True,
        fixture_limit=None,
        max_workers=1,
        mode="refresh",
        test_scope=_scope(),
    )
    ids = [i for season in plan.seasons for i in season.fixture_external_ids]
    # 기간 안 경기만 저장·상세 대상이다.
    assert FIXTURE_A in ids
    assert 999 not in ids


# --------------------------------------------------------------------------
# 3. 종료 훅이 범위를 받아 두 경기만 생성한다
# --------------------------------------------------------------------------


def test_scope_restricts_preview_candidates_to_the_two_fixtures():
    """시험 범위가 있으면 후보를 지정 두 경기로만 제한한다.

    사용자 영향: 같은 시각의 다른 경기까지 생성 예외를 받으면 요청 범위를 넘어 모델이
    호출된다.
    """
    scope = _scope()
    assert scope.is_preview_fixture(FIXTURE_A)
    assert scope.is_preview_fixture(FIXTURE_B)
    assert not scope.is_preview_fixture(1557474)  # 같은 시각의 다른 경기
    assert not scope.is_preview_fixture("bad")


def test_test_round_key_does_not_consume_the_regular_slot():
    """시험 회차 키는 수집 실행 ID 기반이라 정기 회차를 선점하지 않는다.

    사용자 영향: 시험이 정기 회차 키를 쓰면 이후 정기 생성이 중복으로 건너뛰어져
    홈 문서가 갱신되지 않는다.
    """
    from app.services.home_preview_collection import _round_key, _test_round_key

    kickoff = datetime(2026, 11, 22, 0, 0, tzinfo=KST)
    scope = _scope(run_id="run-abc")
    test_key = _test_round_key(scope)
    regular_key = _round_key(kickoff)

    assert test_key == "preview-test:run-abc"
    assert test_key != regular_key
    # 다른 시험 실행은 다른 키를 쓴다(같은 시험끼리만 중복).
    assert _test_round_key(_scope(run_id="run-xyz")) != test_key


def test_scope_roundtrip_preserves_timezone_and_ids():
    """저장·복원이 시간대와 두 경기 ID를 보존한다(종료 훅까지 전달되는 근거)."""
    scope = _scope()
    restored = PreviewTestScope.from_dict(scope.to_dict())
    assert restored is not None
    assert restored.fixture_from == scope.fixture_from
    assert restored.fixture_to == scope.fixture_to
    assert restored.preview_fixture_ids == scope.preview_fixture_ids
    assert restored.run_id == scope.run_id
    # 오프셋이 보존된다.
    assert restored.fixture_from.utcoffset() == timedelta(hours=9)


def test_scope_rejects_malformed_stored_value():
    """형식이 아닌 저장 값은 시험 범위 없음으로 본다(일반 경로로 승격되지 않음)."""
    assert PreviewTestScope.from_dict(None) is None
    assert PreviewTestScope.from_dict({}) is None
    assert PreviewTestScope.from_dict({"fixture_from": "x"}) is None
    # 경기 ID가 둘이 아니면 거부.
    bad = _scope().to_dict()
    bad["preview_fixture_ids"] = [FIXTURE_A]
    assert PreviewTestScope.from_dict(bad) is None


def test_regular_path_has_no_scope_so_the_six_hour_rule_is_unchanged():
    """일반 실행 payload에는 시험 범위가 없다(6시간 정책 보존의 근거).

    사용자 영향: 정기 수집이 시험 예외를 물려받으면 6시간 밖 경기까지 자동 생성된다.
    """
    from app.services import management_runs as mr

    assert PreviewTestScope.from_dict(None) is None
    # start_run의 기본 인자가 None이라 일반 호출은 범위를 만들지 않는다.
    import inspect

    signature = inspect.signature(mr.start_run)
    assert signature.parameters["test_scope"].default is None


def test_start_preview_test_run_rejects_wrong_fixture_count():
    """경기 수가 둘이 아니면 실행을 만들지 않고 거부한다."""
    from app.services import management_runs as mr

    class _Session:
        def add(self, *a, **k):
            raise AssertionError("검증 실패 요청은 실행을 만들면 안 된다")

    with pytest.raises(mr.ManagementError):
        mr.start_preview_test_run(
            _Session(),
            target_ids=[13],
            fixture_from=WINDOW_START,
            fixture_to=WINDOW_END,
            preview_fixture_ids=[FIXTURE_A],
        )
    assert PREVIEW_TEST_MAX_FIXTURES == 2


# --------------------------------------------------------------------------
# 4. 실제 관리 실행 → 종료 훅 → 수집 생성 경계 (종단 연결)
# --------------------------------------------------------------------------


def test_management_run_with_test_scope_reaches_two_fixtures_through_the_real_hook(monkeypatch):
    """실제 `execute_run`이 종료 훅을 거쳐 **두 경기와 수집 ID**를 생성 경계까지 전달한다.

    검사 이유(실패 시 사용자 영향): 시험 요청의 두 경기가 생성 경계까지 이어지지 않으면
    사용자가 승인한 시험 엔드포인트가 실제로 두 문서를 만들지 못한다.

    훅을 대체해 호출 횟수만 세지 않는다. `execute_run` → 실제 `run_home_preview_after_sync`
    → 실제 `run_collection_generation` → `collect_candidates`까지 통과시키고, 모델·DB 외부
    경계만 대역으로 바꾼다.
    """
    from app.services import management_runs as mr
    from app.services import home_preview_collection as hpc

    captured: dict = {}

    class _Settings:
        home_preview_enabled = False  # 전역 플래그가 꺼져 있어도 시험은 진행해야 한다
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1
        home_preview_cycle_limit = 10

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Client:
        def __init__(self, api_key=None, **kwargs):
            pass

        def close(self):
            pass

    class _Plan:
        def unit_count(self, **kwargs):
            return 0

    class _Result:
        seasons: list = []

    class _Fixture:
        def __init__(self, external_id):
            self.external_id = external_id
            self.status_short = "NS"
            self.kickoff_at = WINDOW_END

    class _Team:
        name = "팀"

    item = {
        "target_id": 13,
        "name": "프리미어리그",
        "league_id": 39,
        "season": 2026,
        "status": "pending",
        "total": 0,
        "saved": 0,
        "failed": 0,
        "pending": 0,
        "stored_rows": 0,
        "options": {
            "include_details": False,
            "include_players": False,
            "include_standings": False,
            "fixture_limit": None,
        },
    }

    monkeypatch.setattr(mr, "RunTracker", _NoDbTrackerFactory)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(mr, "measure_league_sync_plan", lambda *a, **k: _Plan())
    monkeypatch.setattr(mr, "backfill_measured_league", lambda *a, **k: _Result())

    # 수집 저장 세션을 대역으로 바꿔 **정상(succeeded) 경로**와 정리 분기에 닿게 한다.
    pruned: list = []

    class _Target:
        target_id = 13
        league_id = 7
        last_sync = None
        initial_status = None

    class _Store:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, model, key):
            return _Target()

        def commit(self):
            return None

        def rollback(self):
            return None

        def execute(self, *a, **k):
            return None

    class _SessionLocal:
        def __call__(self):
            return _Store()

        def __enter__(self):
            return _Store()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mr.db, "SessionLocal", _SessionLocal())
    import app.services.management as management_module

    monkeypatch.setattr(
        management_module, "prune_league_seasons", lambda *a, **k: pruned.append(a)
    )

    # 실제 훅이 부르는 생성 경계에서 후보 조회만 대역으로 바꾼다(모델·DB 미접촉).
    def fake_eligible(session, *, start=None, end=None, include_unranked=False):
        return [
            (_Fixture(FIXTURE_A), None, _Team(), _Team(), 1, {}),
            (_Fixture(FIXTURE_B), None, _Team(), _Team(), 1, {}),
        ]

    monkeypatch.setattr("app.services.home_preview.eligible_rows", fake_eligible)

    def fake_generate(**kwargs):
        captured.setdefault("fixtures", []).append(kwargs["fixture_id"])
        captured.setdefault("scopes", []).append(kwargs["label"])
        return type(
            "O", (), {"run_id": f"run-{kwargs['fixture_id']}", "status": _RunStatus.SUCCEEDED}
        )()

    class _Session:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def commit(self):
            return None

        def scalar(self, *a, **k):
            return None

    monkeypatch.setattr(hpc, "preview_session_factory", lambda: _Session())
    monkeypatch.setattr(hpc, "generate_match_preview", fake_generate)
    # 모델 전송은 설정이 필요하므로 대역으로 바꾼다(실제 모델 호출 없음).
    monkeypatch.setattr(mr, "_collection_transport", lambda: object())

    # 경기 잠금은 PostgreSQL advisory lock이므로 DB 없이 대역으로 바꾼다.
    class _Lock:
        acquired = True
        reason = None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(hpc, "_fixture_lock", lambda _fixture_id: _Lock())
    # 승인 게이트는 실제 DB를 읽으므로 대역으로 바꾼다(승인 준비 상태 가정).
    monkeypatch.setattr(
        hpc, "_admission", lambda _factory: {"state": "ready", "missing_approval": [], "stale_approval": []}
    )

    payload = _run_payload()
    payload["items"] = [item]
    payload["test_scope"] = _scope(run_id="run-top").to_dict()
    mr.execute_run(payload, _Guard())

    # 두 지정 경기만 생성되었고, 수집 실행 ID가 회차 키로 이어졌다.
    import json as _json

    assert sorted(captured.get("fixtures") or []) == sorted([FIXTURE_A, FIXTURE_B]), _json.dumps(payload.get("home_preview"), ensure_ascii=False)
    assert all("preview-test:run-top" in label for label in captured.get("scopes") or [])
    # 결과가 별도 키에 남고, 수집 상태가 원래 값으로 전달된다.
    assert payload["home_preview"]["collection_status"] == "succeeded"
    assert len(payload["home_preview"]["generated"]) == 2
    # 시험 범위에서는 시즌 정리를 호출하지 않는다(대상 객체가 있어도).
    assert pruned == []


def _run_payload():
    """`execute_run`이 받는 최소 payload 모양."""
    return {
        "id": "run-scope-1",
        "status": "queued",
        "mode": "refresh",
        "created_at": "2026-11-13T05:00:00+09:00",
        "started_at": "2026-11-13T05:00:00+09:00",
        "finished_at": None,
        "cancel_requested_at": None,
        "actor": "테스트",
        "parent_run_id": None,
        "items": [],
        "logs": [],
        "progress": 0,
        "stage": "실행 준비",
        "log_statistics": {},
        "_log_total": 0,
        "counts_kind": "processing_units",
    }


class _NoDbTrackerFactory:
    """`RunTracker(payload)` 자리를 대신하는 DB 없는 트래커."""

    def __init__(self, payload):
        self.payload = payload
        self.item = None
        self.cancelled = False

    def log(self, message, *, code="PROGRESS", level="info", **context):
        self.payload["logs"].append({"code": code, "message": message})

    def api_event(self, **event):
        return None

    def check_cancelled(self, session=None):
        return None

    def flush(self, force=False):
        return None

    def add_total(self, amount):
        return None

    def set_total(self, amount):
        return None

    def advance(self, amount=1, message=None):
        return None

    def stored(self, counts):
        return None


# --------------------------------------------------------------------------
# 접수 전 소속 확인 (요구 1)
# --------------------------------------------------------------------------


class _ScopeSession:
    """`_require_preview_fixtures_in_scope`가 쓰는 조회만 흉내 내는 세션."""

    def __init__(self, *, targets=(), fixtures=(), leagues=()):
        self._targets = list(targets)
        self._fixtures = list(fixtures)
        self._leagues = {league.id: league for league in leagues}

    def scalars(self, statement):
        text = str(statement)
        if "league_sync_target" in text:
            return iter(self._targets)
        if "fixture" in text:
            return iter(self._fixtures)
        return iter([])

    def get(self, model, key):
        return self._leagues.get(key)


def _target(target_id=13, league_id=7, season=2026):
    row = type("T", (), {})()
    row.id = target_id
    row.league_id = league_id
    row.season_year = season
    return row


def _league(league_id=7, external_id=39):
    row = type("L", (), {})()
    row.id = league_id
    row.external_id = external_id
    return row


def _fixture(external_id, *, league_id=7, season=2026, kickoff=None, status="NS"):
    row = type("F", (), {})()
    row.external_id = external_id
    row.league_id = league_id
    row.season_year = season
    row.kickoff_at = kickoff or WINDOW_END
    row.status_short = status
    return row


def test_accepts_the_current_request_when_both_fixtures_are_in_scope():
    """현재 지정 값(둘 다 기간 안·같은 리그/시즌·NS)은 접수된다."""
    from app.services import management_runs as mr

    session = _ScopeSession(
        targets=[_target()],
        fixtures=[_fixture(FIXTURE_A), _fixture(FIXTURE_B)],
        leagues=[_league()],
    )
    # 예외가 나지 않으면 통과.
    mr._require_preview_fixtures_in_scope(
        session,
        target_ids=[13],
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
        preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
    )


def test_rejects_a_fixture_outside_the_requested_period_before_collection():
    """기간 밖 경기 ID는 수집·외부 호출 전에 422로 거부된다.

    사용자 영향: 거부되지 않으면 수집은 성공하고 생성만 조용히 비어, 사용자가 "요청이
    틀렸다"는 피드백을 받지 못한다.
    """
    from app.services import management_runs as mr

    early = WINDOW_START - timedelta(days=3)
    session = _ScopeSession(
        targets=[_target()],
        fixtures=[_fixture(FIXTURE_A, kickoff=early), _fixture(FIXTURE_B)],
        leagues=[_league()],
    )
    with pytest.raises(mr.ManagementError) as excinfo:
        mr._require_preview_fixtures_in_scope(
            session,
            target_ids=[13],
            fixture_from=WINDOW_START,
            fixture_to=WINDOW_END,
            preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
        )
    # 어느 경기의 어떤 조건인지 알린다.
    assert str(FIXTURE_A) in str(excinfo.value)
    assert "기간" in str(excinfo.value)


def test_rejects_a_fixture_from_another_league_without_confusing_id_spaces():
    """다른 리그 경기는 거부되고, 내부/외부 리그 ID를 섞지 않는다.

    사용자 영향: 내부 기본키(7)를 외부 리그 ID(39)로 착각하면 남의 경기가 통과한다.
    """
    from app.services import management_runs as mr

    # 경기의 league_id는 내부 7이지만, 대상 리그의 외부 ID는 39다. 둘을 섞으면 통과한다.
    other_league = _league(league_id=99, external_id=140)
    session = _ScopeSession(
        targets=[_target(league_id=7)],
        fixtures=[_fixture(FIXTURE_A, league_id=99), _fixture(FIXTURE_B)],
        leagues=[_league(), other_league],
    )
    with pytest.raises(mr.ManagementError) as excinfo:
        mr._require_preview_fixtures_in_scope(
            session,
            target_ids=[13],
            fixture_from=WINDOW_START,
            fixture_to=WINDOW_END,
            preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
        )
    assert str(FIXTURE_A) in str(excinfo.value)
    assert "리그/시즌" in str(excinfo.value)


def test_rejects_a_fixture_that_is_not_scheduled():
    """이미 시작했거나 취소된 경기는 거부된다."""
    from app.services import management_runs as mr

    session = _ScopeSession(
        targets=[_target()],
        fixtures=[_fixture(FIXTURE_A, status="FT"), _fixture(FIXTURE_B)],
        leagues=[_league()],
    )
    with pytest.raises(mr.ManagementError) as excinfo:
        mr._require_preview_fixtures_in_scope(
            session,
            target_ids=[13],
            fixture_from=WINDOW_START,
            fixture_to=WINDOW_END,
            preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
        )
    assert "NS" in str(excinfo.value)


def test_inclusion_is_inclusive_at_both_ends():
    """기간 **양 끝을 포함**한다(킥오프가 정확히 fixture_to인 현재 두 경기)."""
    from app.services import management_runs as mr

    assert WINDOW_END == datetime(2026, 11, 22, 0, 0, tzinfo=KST)
    session = _ScopeSession(
        targets=[_target()],
        fixtures=[
            _fixture(FIXTURE_A, kickoff=WINDOW_START),
            _fixture(FIXTURE_B, kickoff=WINDOW_END),
        ],
        leagues=[_league()],
    )
    mr._require_preview_fixtures_in_scope(
        session,
        target_ids=[13],
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
        preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
    )


# --------------------------------------------------------------------------
# 수집 시험 조회 API — 후보 정렬, 대상 해석, ADMIN 경계
# --------------------------------------------------------------------------


class _Row:
    """`eligible_rows`가 돌려주는 튜플의 각 자리 대역."""

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _candidate_row(*, external_id, kickoff, priority, status="NS", league_id=7, season=2026):
    fixture = _Row(
        external_id=external_id,
        kickoff_at=kickoff,
        status_short=status,
        league_id=league_id,
        season_year=season,
        updated_at=kickoff,
    )
    league = _Row(id=league_id, name="Premier League", external_id=39)
    home = _Row(id=external_id * 10, name="Home", external_id=1)
    away = _Row(id=external_id * 10 + 1, name="Away", external_id=2)
    return (fixture, league, home, away, priority, {})


def _plan_session(*, targets=(), fixtures=(), leagues=()):
    """`build_plan`이 쓰는 조회만 흉내 내는 세션.

    `target_payload`는 리그 행과 그 한국어 이름 행을 **다른 모델로** 조회하므로, 모델별로
    다른 값을 돌려줘야 한다. 같은 값을 돌려주면 이름 조회가 리그 행에서 `name_ko`를
    찾다가 실패한다(그 실패는 실제 코드 결함이 아니다).
    """

    class _Session:
        def __init__(self):
            self.targets = list(targets)
            self.fixtures = list(fixtures)
            self.leagues = {league.id: league for league in leagues}

        def scalars(self, statement):
            text = str(statement)
            if "fixture" in text:
                return iter(self.fixtures)
            if "league_sync_target" in text:
                return iter(self.targets)
            return iter([])

        def scalar(self, statement):
            text = str(statement)
            if "league_sync_target" in text:
                return self.targets[0] if self.targets else None
            return None

        def get(self, model, key):
            if getattr(model, "__name__", "") == "LeagueTranslation":
                # 한국어 이름이 없는 상태를 그대로 재현한다(원래 이름을 쓰는 경로).
                return None
            return self.leagues.get(key)

    return _Session()


def _league_row(*, id=7, external_id=39, is_active=True, name="Premier League"):
    """`target_payload`가 읽는 리그 열. 없는 값을 흉내 내지 않고 채워 둔다."""
    return _Row(
        id=id,
        external_id=external_id,
        is_active=is_active,
        name=name,
        logo_url=None,
        country_name="England",
        current_season=2026,
    )


class _CandidateSession:
    """후보 조회가 리그 한국어 이름을 읽는 경로만 흉내 내는 세션."""

    def scalars(self, statement):
        return iter([])


def _target_row(*, id=13, league_id=7, season=2026, is_active=True, include_details=True):
    return _Row(
        id=id,
        league_id=league_id,
        season_year=season,
        is_active=is_active,
        include_details=include_details,
        include_players=True,
        include_standings=True,
        fixture_limit=None,
        initial_status=None,
        last_sync=None,
    )


def _fixture_row(*, external_id, kickoff, status="NS", league_id=7, season=2026):
    return _Row(
        external_id=external_id,
        kickoff_at=kickoff,
        status_short=status,
        league_id=league_id,
        season_year=season,
        updated_at=kickoff,
    )


NOW = datetime(2026, 11, 17, 19, 0, tzinfo=KST)


def test_candidates_are_ordered_by_kickoff_then_priority_then_fixture_id(monkeypatch):
    """후보는 킥오프→추천 순위→외부 경기 ID 순으로 정렬된다.

    사용자 영향: 정렬이 흔들리면 실행마다 기본 선택 두 경기가 달라지고, 사용자가
    확인한 기간과 대상이 다음 실행에서 조용히 바뀐다.
    """
    from app.services import preview_test

    same_time = datetime(2026, 11, 21, 21, 30, tzinfo=KST)
    later = datetime(2026, 11, 22, 0, 0, tzinfo=KST)
    rows = [
        _candidate_row(external_id=1557476, kickoff=same_time, priority=1),
        _candidate_row(external_id=1557474, kickoff=same_time, priority=1),
        _candidate_row(external_id=1557470, kickoff=later, priority=1),
        _candidate_row(external_id=1557472, kickoff=same_time, priority=2),
    ]
    monkeypatch.setattr(preview_test, "eligible_rows", lambda *a, **k: rows)

    result = preview_test.candidates(_CandidateSession(), now=NOW)

    assert [item["fixture_id"] for item in result["candidates"]] == [
        1557474,
        1557476,
        1557472,
        1557470,
    ]
    assert result["timezone"] == "Asia/Seoul"
    assert result["reason"] is None


def test_candidates_exclude_started_and_unranked_fixtures(monkeypatch):
    """이미 시작한 경기와 추천 순위 없는 경기는 후보가 아니다.

    사용자 영향: 시작한 경기를 후보로 내면 수집 기간이 과거로 늘어나고, 생성 대상으로
    고를 수 없는 경기를 사용자가 선택하게 된다.
    """
    from app.services import preview_test

    rows = [
        _candidate_row(
            external_id=1, kickoff=datetime(2026, 11, 17, 12, 0, tzinfo=KST), priority=1
        ),
        _candidate_row(
            external_id=2, kickoff=datetime(2026, 11, 21, 21, 30, tzinfo=KST), priority=None
        ),
        _candidate_row(
            external_id=3,
            kickoff=datetime(2026, 11, 21, 21, 30, tzinfo=KST),
            priority=1,
            status="FT",
        ),
        _candidate_row(external_id=4, kickoff=datetime(2026, 11, 21, 21, 30, tzinfo=KST), priority=1),
    ]
    monkeypatch.setattr(preview_test, "eligible_rows", lambda *a, **k: rows)

    result = preview_test.candidates(_CandidateSession(), now=NOW)

    assert [item["fixture_id"] for item in result["candidates"]] == [4]


def test_candidates_explain_why_two_are_not_available(monkeypatch):
    """후보가 두 개 미만이면 **부족 사유**를 돌려주고 시각을 지어내지 않는다.

    사용자 영향: 사유가 없으면 화면이 빈 목록만 보여 주고 사용자는 원인을 알 수 없다.
    """
    from app.services import preview_test

    rows = [
        _candidate_row(
            external_id=1557474, kickoff=datetime(2026, 11, 21, 21, 30, tzinfo=KST), priority=1
        )
    ]
    monkeypatch.setattr(preview_test, "eligible_rows", lambda *a, **k: rows)

    result = preview_test.candidates(_CandidateSession(), now=NOW)

    assert len(result["candidates"]) == 1
    assert result["reason"] and "두 경기" in result["reason"]


def test_plan_uses_kst_day_start_and_the_last_kickoff():
    """기간은 **당일 KST 00:00**부터 두 경기 중 마지막 킥오프까지다(양 끝 포함).

    사용자 영향: 시작을 실행 시각으로 잡으면 그날 이미 시작한 경기 자료가 빠지고,
    끝을 첫 경기로 잡으면 두 번째 경기의 수집 창이 잘린다.
    """
    from app.services import preview_test

    first = datetime(2026, 11, 21, 21, 30, tzinfo=KST)
    second = datetime(2026, 11, 22, 0, 0, tzinfo=KST)
    session = _plan_session(
        targets=[_target_row()],
        fixtures=[
            _fixture_row(external_id=1557474, kickoff=first),
            _fixture_row(external_id=1557470, kickoff=second),
        ],
        leagues=[_league_row()],
    )

    plan = preview_test.build_plan(session, [1557474, 1557470], now=NOW)

    assert plan["fixture_from"] == datetime(2026, 11, 17, 0, 0, tzinfo=KST).isoformat()
    assert plan["fixture_to"] == second.isoformat()
    assert plan["can_collect"] is True
    assert plan["blocking_reasons"] == []
    assert plan["target_ids"] == [13]
    assert plan["targets"][0]["season"] == 2026


def test_plan_rejects_an_unknown_fixture_before_any_collection():
    """저장된 경기에 없는 ID는 422로 거부된다(수집 전).

    사용자 영향: 통과시키면 수집은 성공하고 생성 대상만 조용히 비어, 사용자는 잘못된
    요청을 알 수 없다.
    """
    from app.services import preview_test
    from app.services.management import ManagementError

    session = _plan_session(
        targets=[_target_row()],
        fixtures=[_fixture_row(external_id=1557474, kickoff=NOW + timedelta(hours=48))],
        leagues=[_league_row()],
    )

    with pytest.raises(ManagementError) as excinfo:
        preview_test.build_plan(session, [1557474, 999999], now=NOW)

    assert "999999" in str(excinfo.value)
    assert excinfo.value.status == 422


def test_plan_reports_a_missing_active_target_instead_of_inventing_one():
    """활성 대상이 없으면 **실행 불가 사유**를 돌려준다(대상을 만들지 않는다).

    사용자 영향: 대상을 지어내면 엉뚱한 리그/시즌이 수집된다.
    """
    from app.services import preview_test

    session = _plan_session(
        targets=[],
        fixtures=[
            _fixture_row(external_id=1557474, kickoff=NOW + timedelta(hours=48)),
            _fixture_row(external_id=1557470, kickoff=NOW + timedelta(hours=52)),
        ],
        leagues=[_league_row()],
    )

    plan = preview_test.build_plan(session, [1557474, 1557470], now=NOW)

    assert plan["can_collect"] is False
    assert plan["targets"] == []
    assert [reason["code"] for reason in plan["blocking_reasons"]] == [
        "target_not_found",
        "target_not_found",
    ]


def test_plan_marks_an_already_started_fixture_as_blocked():
    """이미 시작한 경기는 실행 불가 사유로 표시된다."""
    from app.services import preview_test

    started = NOW - timedelta(minutes=30)
    session = _plan_session(
        targets=[_target_row()],
        fixtures=[
            _fixture_row(external_id=1557474, kickoff=started),
            _fixture_row(external_id=1557470, kickoff=NOW + timedelta(hours=5)),
        ],
        leagues=[_league_row()],
    )

    plan = preview_test.build_plan(session, [1557474, 1557470], now=NOW)

    assert plan["can_collect"] is False
    codes = [reason["code"] for reason in plan["blocking_reasons"]]
    assert "fixture_started" in codes


def test_plan_rejects_wrong_fixture_count_and_duplicates():
    """정확히 두 개·서로 다른 두 개가 아니면 422다."""
    from app.services import preview_test
    from app.services.management import ManagementError

    session = _plan_session(targets=[_target_row()])

    for ids in ([1], [1, 1], [1, 2, 3]):
        with pytest.raises(ManagementError):
            preview_test.build_plan(session, ids, now=NOW)


def test_collection_test_routes_require_admin_on_top_of_the_manager_dependency():
    """수집 시험 경로는 라우터의 관리 인증 위에 **ADMIN**을 더 요구한다.

    사용자 영향: STREAMER가 수집 시험을 실행하면 실제 공급자 호출과 자료 갱신이
    권한 밖에서 일어난다. 기존 일반 관리 API의 STREAMER 정책은 그대로여야 한다.
    """
    from app.api.v1.management import router

    paths = {route.path for route in router.routes}
    for path in (
        "/api/v1/admin/management/preview-test/candidates",
        "/api/v1/admin/management/preview-test/plan",
        "/api/v1/admin/management/preview-test/runs",
        "/api/v1/admin/management/preview-test/runs/{run_id}",
    ):
        assert path in paths

    # 라우터 기본 의존성은 기존 관리 인증 그대로다(완화·교체 없음).
    dependency_names = [
        getattr(getattr(dep, "dependency", None), "__name__", "") for dep in router.dependencies
    ]
    assert "manager_user" in dependency_names

    from app.api.v1 import management

    # ADMIN 판정은 시험 경로 전용 의존성이며 STREAMER를 통과시키지 않는다.
    streamer = _Row(role="STREAMER")
    admin = _Row(role="ADMIN")
    with pytest.raises(Exception):
        management.require_admin(streamer)
    assert management.require_admin(admin) is admin


def test_existing_preview_test_request_defaults_to_auto_generation():
    """기존 `POST /runs/preview-test` 본문은 **자동 생성이 기본**이다.

    사용자 영향: 기본값이 뒤집히면 기존 호출 경로가 조용히 생성을 멈춘다.
    """
    from app.api.v1.management import PreviewTestRunCreate
    from app.api.v1.management import PreviewTestCollectionRunCreate

    existing = PreviewTestRunCreate(
        target_ids=[13],
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
        preview_fixture_ids=[FIXTURE_A, FIXTURE_B],
    )

    assert existing.generate_after_collection is True

    # 전용 수집 경로는 이 필드를 받지 않는다(의미를 한 경로에만 둔다).
    collection_only = PreviewTestCollectionRunCreate(
        fixture_ids=[FIXTURE_A, FIXTURE_B],
        fixture_from=WINDOW_START,
        fixture_to=WINDOW_END,
    )
    assert not hasattr(collection_only, "generate_after_collection")
