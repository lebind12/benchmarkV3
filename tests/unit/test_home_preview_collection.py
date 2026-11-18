"""PC-CONNECT 직접 검사 — 수집 종료 경계와 기존 생성 서비스 연결.

검사 이유(실패 시 사용자 영향):

- 수집이 부분 실패·실패하면 지금은 프리뷰를 아예 만들지 않아, DB에 경기 자료가 있어도
  홈에 보여줄 문서가 생기지 않는다(사용자 확정 Q6 위반).
- 한 경기 생성이 실패하면 다음 경기까지 멈추면 표시 가능한 문서 수가 줄고 원인도 가려진다.
- 같은 자동 회차가 중복 실행되면 같은 경기에 실행이 겹쳐 저장된다.
- 관리자 문서가 있다는 이유로 수집 생성을 건너뛰면 사용자가 확인한 최신본 정책(Q7)과 어긋난다.
- 사용자가 취소했는데 생성이 시작되면 사용자가 멈추라고 한 작업이 계속된다.

**합성 검사다.** 생성기는 대역이고 실제 모델·검색·DB·API를 호출하지 않는다. 그래서 이
검사의 통과를 실제 생성 성공이나 저장 성공으로 인용하지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.preview.contracts import RunStatus
from app.services import home_preview_collection as collection

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 13, 3, 0, tzinfo=timezone.utc)


class _Session:
    """후보 조회·중복 조회에 쓰는 최소 세션 대역. 실제 DB에 연결하지 않는다."""

    def __init__(self, existing_runs, by_label=None):
        self._existing = existing_runs
        self._by_label = by_label or {}
        self.committed = 0
        self.closed = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed += 1
        return False

    def scalar(self, statement):
        # 중복 조회는 label을 조건으로 한다. label별 준비 값을 돌려준다.
        text = str(statement)
        for label, run_id in self._by_label.items():
            if label in text:
                return type("Row", (), {"id": run_id, "fixture_id": None})()
        return None

    def commit(self):
        self.committed += 1


def _candidates(ids):
    return [
        {"fixture_id": fixture_id, "label": f"수집 완료 후 자동 생성(시스템 호출) {fixture_id}", "priority": 1}
        for fixture_id in ids
    ]


def _ready_gate(_factory):
    """승인 게이트 대역. 승인된 상태로 준비됐다고 알린다(실제 DB 조회 없음)."""
    return {"state": "ready", "missing_approval": [], "stale_approval": []}


class _StubLock:
    """항상 획득되는 잠금 대역. 실제 advisory lock을 잡지 않는다(DB 미연결)."""

    def __init__(self, fixture_id):
        self.fixture_id = fixture_id
        self.acquired = True

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _Recorder:
    """생성 호출을 기록하는 대역. 실제 파이프라인을 실행하지 않는다."""

    def __init__(self, fail_ids=(), raise_ids=()):
        self.calls: list[dict] = []
        self.fail_ids = set(fail_ids)
        self.raise_ids = set(raise_ids)

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        fixture_id = kwargs["fixture_id"]
        if fixture_id in self.raise_ids:
            raise RuntimeError("pipeline exploded")
        if fixture_id in self.fail_ids:
            from app.services.match_preview import FixtureResolutionError

            raise FixtureResolutionError("bad fixture", reason="fixture_not_found")
        return type("Outcome", (), {"run_id": f"run-{fixture_id}", "status": RunStatus.SUCCEEDED})()


def _run(monkeypatch, *, ids, recorder, cancelled=None, sessions=None, existing_runs=(), cycle_limit=None):
    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates(ids))
    monkeypatch.setattr(collection, "_already_generated", lambda session, *, fixture_id, label: (sessions or {}).get(fixture_id))
    factory = _Session(existing_runs)
    return collection.run_collection_generation(
        session_factory=lambda: factory,
        preview_session_factory=lambda: _Session(existing_runs),
        collection_status="failed",
        now=NOW,
        transport=object(),
        generate=recorder,
        cancelled=cancelled,
        cycle_limit=cycle_limit,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )


def test_collection_failure_still_generates_from_db_and_preserves_collection_status(monkeypatch):
    """수집이 실패해도 DB 후보로 생성하고, 수집 상태를 덮어쓰지 않는다(Q6)."""
    recorder = _Recorder()
    result = _run(monkeypatch, ids=[101, 102], recorder=recorder)

    assert [call["fixture_id"] for call in recorder.calls] == [101, 102]
    # 원래 수집 상태가 보존된다.
    assert result["collection_status"] == "failed"
    # 수집 상태와 생성 결과가 분리되어 남는다.
    assert result["state"] == "finished"
    assert {row["fixture_id"] for row in result["generated"]} == {101, 102}
    # 생성 실행 ID가 연결된다.
    assert {row["run_id"] for row in result["generated"]} == {"run-101", "run-102"}
    # 관리자 ID로 위장하지 않는다.
    assert all(call["actor_id"] is None for call in recorder.calls)
    assert all(call["trigger"] == "collection" for call in recorder.calls)


def test_one_fixture_failure_does_not_stop_the_next_fixture(monkeypatch):
    """A가 실패해도 B를 처리하고, 실패 사유를 경기별로 남긴다."""
    recorder = _Recorder(raise_ids={101}, fail_ids={102})
    result = _run(monkeypatch, ids=[101, 102, 103], recorder=recorder)

    assert [call["fixture_id"] for call in recorder.calls] == [101, 102, 103]
    failed = {row["fixture_id"]: row["reason"] for row in result["failed"]}
    assert failed[101] == "generation_failed: RuntimeError"
    assert failed[102] == "fixture_not_found"
    # 셋째 경기는 정상 처리된다.
    assert [row["fixture_id"] for row in result["generated"]] == [103]


def test_same_automatic_slot_is_not_generated_twice(monkeypatch):
    """같은 자동 회차에서 이미 생성된 경기는 다시 만들지 않는다."""
    recorder = _Recorder()
    result = _run(
        monkeypatch,
        ids=[101, 102],
        recorder=recorder,
        sessions={101: "run-existing"},
    )

    assert [call["fixture_id"] for call in recorder.calls] == [102]
    skipped = {row["fixture_id"]: row["reason"] for row in result["skipped"]}
    assert skipped[101] == "already_generated_this_cycle"
    assert result["generated"][0]["fixture_id"] == 102


def test_existing_admin_document_does_not_block_collection_generation(monkeypatch):
    """관리자 문서가 있어도 수집 생성은 수행한다(Q7). 중복 판정은 자동 회차 기준이다."""
    recorder = _Recorder()
    # 관리자 실행은 다른 label을 쓰므로 자동 회차 중복으로 잡히지 않는다.
    result = _run(monkeypatch, ids=[101], recorder=recorder)

    assert [call["fixture_id"] for call in recorder.calls] == [101]
    assert result["generated"][0]["fixture_id"] == 101


def test_cancellation_does_not_start_generation(monkeypatch):
    """사용자가 취소하면 후속 생성을 시작하지 않는다."""
    recorder = _Recorder()
    result = _run(monkeypatch, ids=[101, 102], recorder=recorder, cancelled=lambda: True)

    assert recorder.calls == []
    assert result["reason"] == "cancelled"
    assert result["state"] == "skipped"


def test_cancellation_mid_cycle_stops_before_the_next_fixture(monkeypatch):
    """처리 중 취소되면 다음 경기를 시작하지 않고 취소 사유를 남긴다."""
    state = {"calls": 0}

    def cancelled():
        state["calls"] += 1
        # 첫 확인(진입) 뒤 첫 경기 처리 시점부터 취소로 본다.
        return state["calls"] > 1

    recorder = _Recorder()
    result = _run(monkeypatch, ids=[101, 102], recorder=recorder, cancelled=cancelled)

    assert recorder.calls == []
    assert all(row["reason"] == "cancelled" for row in result["skipped"])


def test_missing_model_transport_does_not_generate_or_fake_success(monkeypatch):
    """모델 전송 설정이 없으면 모의로 대체하지 않고 실행 불가 사유를 남긴다."""
    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    recorder = _Recorder()
    factory = _Session(existing_runs=())
    result = collection.run_collection_generation(
        session_factory=lambda: factory,
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=None,
        generate=recorder,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )

    assert recorder.calls == []
    assert result["state"] == "failed"
    assert result["reason"] == "model_transport_unconfigured"
    assert result["generated"] == []


def test_cycle_limit_defers_the_rest_without_dropping_them(monkeypatch):
    """회차 한도는 기존 의미대로 나머지를 deferred로 남긴다(후보 유실 없음)."""
    recorder = _Recorder()
    result = _run(monkeypatch, ids=[101, 102, 103], recorder=recorder, cycle_limit=2)

    assert [call["fixture_id"] for call in recorder.calls] == [101, 102]
    assert result["deferred"] == [103]


def test_round_key_uses_the_legacy_kickoff_due_slot_not_wall_clock():
    """회차는 **킥오프 기준 기존 회차**(generation_due_at)를 쓴다.

    검사 이유(실패 시 사용자 영향): 실행 시각이나 킥오프 시각의 bucket(`slot_time`)을
    회차로 쓰면, 정기 수집 시각에 정확히 걸친 경기에서 기존 회차와 값이 달라져 같은
    경기가 다른 회차로 보인다(자동 생성 중복 또는 누락).

    두 helper가 실제로 갈리는 시각으로 확인한다(12:00 KST 킥오프: due=06:00, slot=12:00).
    """
    from app.services.home_preview_policy import KST, generation_due_at, slot_time

    kickoff = datetime(2026, 11, 13, 12, 0, tzinfo=KST)
    # 이 시각에서 두 helper는 서로 다른 값을 낸다(검사가 실제로 구분한다).
    assert generation_due_at(kickoff) != slot_time(kickoff)

    # 우리 회차는 기존 의미인 due 값이어야 한다.
    assert collection._round_key(kickoff) == generation_due_at(kickoff).isoformat()

    # 같은 킥오프면 label이 같아 중복으로 잡힌다.
    a = collection._fixture_label(
        101, "맨체스터 시티", "풀럼", round_key=collection._round_key(kickoff)
    )
    b = collection._fixture_label(
        101, "맨체스터 시티", "풀럼", round_key=collection._round_key(kickoff)
    )
    assert a == b
    assert collection.COLLECTION_LABEL in a


def test_administrator_run_is_not_counted_as_an_automatic_duplicate(monkeypatch):
    """관리자 실행(label이 다르다)은 자동 회차 중복으로 잡히지 않는다.

    검사 이유(실패 시 사용자 영향): 관리자 생성 기록이 자동 중복으로 오인되면 수집이
    해당 경기의 새 자동 생성을 영영 건너뛴다(Q7 위반).
    """
    looked_up: list[str] = []

    def fake_lookup(session, *, fixture_id, label):
        looked_up.append(label)
        # 관리자 실행은 label이 "정보 원문 프리뷰 ..." 형태이므로 이 조회에 걸리지 않는다.
        return None

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    monkeypatch.setattr(collection, "_already_generated", fake_lookup)
    recorder = _Recorder()
    factory = _Session(existing_runs=())
    result = collection.run_collection_generation(
        session_factory=lambda: factory,
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=recorder,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )

    # 자동 생성이 실제로 호출됐다(관리자 기록 때문에 건너뛰지 않았다).
    assert [call["fixture_id"] for call in recorder.calls] == [101]
    # 중복 조회는 자동 회차 label로만 한다.
    assert looked_up and collection.COLLECTION_LABEL in looked_up[0]
    assert result["generated"]


def test_same_cycle_second_call_is_skipped_by_existing_slot_label(monkeypatch):
    """같은 회차에 두 번 호출하면 두 번째는 저장 구조 조회로 건너뛴다."""
    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    recorded_label = {}

    def first_generate(**kwargs):
        recorded_label["label"] = kwargs["label"]
        return type("O", (), {"run_id": "run-101", "status": RunStatus.SUCCEEDED})()

    factory = _Session(existing_runs=())
    collection.run_collection_generation(
        session_factory=lambda: factory,
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=first_generate,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )

    # 저장 구조에 같은 label의 실행이 남았다고 가정하고 같은 회차를 다시 호출한다.
    skipped_recorder = _Recorder()
    monkeypatch.setattr(
        collection, "_already_generated", lambda session, *, fixture_id, label: "run-101"
    )
    second = collection.run_collection_generation(
        session_factory=lambda: _Session(existing_runs=()),
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=skipped_recorder,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )

    assert skipped_recorder.calls == []
    assert second["skipped"][0]["reason"] == "already_generated_this_cycle"


def test_collection_hook_passes_a_preview_session_factory(monkeypatch):
    """수집 훅이 공개 세션과 **다른 preview_dev 세션**을 생성 쓰기에 넘긴다.

    검사 이유(실패 시 사용자 영향): 생성 파이프라인은 preview_dev 행을 쓰므로, 공개
    스키마 세션으로 호출하면 저장이 실패하고 홈에 새 문서가 생기지 않는다. 두 세션을
    섞지 않는지 확인한다.
    """
    from app.services import management_runs

    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"state": "finished"}

    monkeypatch.setattr(collection, "run_collection_generation", fake_run)
    monkeypatch.setattr(management_runs, "_collection_transport", lambda: object())

    result = management_runs.run_home_preview_after_sync(collection_status="partial_failed")

    assert result["state"] == "finished"
    # 원래 수집 상태가 그대로 전달된다.
    assert captured["collection_status"] == "partial_failed"
    # 공개 세션과 preview 세션을 각각 넘긴다(같은 팩토리를 쓰지 않는다).
    assert captured["session_factory"] is not None
    assert captured["preview_session_factory"] is not None
    assert captured["session_factory"] is not captured["preview_session_factory"]


def test_lock_not_acquired_skips_instead_of_double_generating(monkeypatch):
    """동시 진입에서 잠금을 못 잡으면 생성하지 않고 건너뛴다.

    검사 이유(실패 시 사용자 영향): 중복 조회와 생성 시작 사이에 두 수집 종료가 들어오면
    같은 경기에 자동 생성이 두 번 저장된다. 잠금 실패를 생성으로 진행하면 그 창이 열린다.
    """
    class _BusyLock(_StubLock):
        def __init__(self, fixture_id):
            super().__init__(fixture_id)
            self.acquired = False

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    recorder = _Recorder()
    factory = _Session(existing_runs=())
    result = collection.run_collection_generation(
        session_factory=lambda: factory,
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=recorder,
        fixture_lock=_BusyLock,
        admission=_ready_gate,
    )

    assert recorder.calls == []
    assert result["skipped"][0]["reason"] == "generation_in_progress_elsewhere"
    assert result["generated"] == []


def test_generation_happens_while_holding_the_fixture_lock(monkeypatch):
    """실제 생성은 **잠금을 잡은 구간 안에서** 일어난다.

    검사 이유(실패 시 사용자 영향): 잠금을 잡았더라도 생성이 잠금 밖에서 일어나면 조회와
    생성 사이 창이 그대로 남아 동시 중복이 다시 가능해진다.
    """
    events: list[str] = []

    class _TrackingLock(_StubLock):
        def __enter__(self):
            events.append(f"enter:{self.fixture_id}")
            return self

        def __exit__(self, *exc_info):
            events.append(f"exit:{self.fixture_id}")
            return False

    def generate(**kwargs):
        events.append(f"generate:{kwargs['fixture_id']}")
        return type("O", (), {"run_id": "run-101", "status": RunStatus.SUCCEEDED})()

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    collection.run_collection_generation(
        session_factory=lambda: _Session(existing_runs=()),
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=generate,
        fixture_lock=_TrackingLock,
        admission=_ready_gate,
    )

    assert events == ["enter:101", "generate:101", "exit:101"]


# --------------------------------------------------------------------------
# 독립 검토 지적 1~4
# --------------------------------------------------------------------------


def test_preview_session_factory_calls_the_maker_so_with_gets_a_session(monkeypatch):
    """팩토리를 부르면 sessionmaker를 **한 번 더 호출**해 세션을 낸다(계약 확인).

    검사 이유(실패 시 사용자 영향): 팩토리가 sessionmaker를 그대로 돌려주면 중복 조회
    단계에서 TypeError가 나 **모든 후보가 생성 전에 실패**하고, 수집이 끝나도 프리뷰가
    새로 생기지 않는다. 실제 DB 없이 `sessionmaker` 호출 단계만 확인한다.
    """
    import app.preview.db as preview_db
    from sqlalchemy.orm import sessionmaker

    maker = sessionmaker()  # DB에 연결하지 않는 unbound sessionmaker
    sentinel = object()
    calls = []

    class _Maker:
        def __call__(self):
            calls.append(1)
            return sentinel

    monkeypatch.setattr(preview_db, "get_session_factory", lambda: _Maker())

    produced = collection.preview_session_factory()

    # 팩토리는 maker를 **호출**해서 세션을 낸다(그 자체를 반환하지 않는다).
    assert produced is sentinel
    assert calls == [1]
    # 계약상 돌려주는 값은 sessionmaker가 아니라 with에 넣을 수 있는 객체다.
    assert not isinstance(produced, sessionmaker)


def test_default_preview_factory_is_the_same_contract():
    """기본 fallback도 같은 계약을 쓴다(별도 wrapper가 다른 단계를 내지 않는다)."""
    assert collection._default_preview_factory is collection.preview_session_factory


def test_missing_approval_does_not_block_generation(monkeypatch):
    """승인이 없어도(게이트 not_ready) 수집 후 생성은 정상 호출된다.

    검사 이유(실패 시 사용자 영향): 승인은 번역·선수 연결 검수 상태일 뿐 게시 허가가
    아니므로, 승인 행이 없다는 이유로 자동 생성이 막히면 사용자가 요청한
    "수집 → 프리뷰 → 홈" 경로가 끊긴다.
    """
    def gate(_factory):
        return {
            "state": "not_ready",
            "missing_approval": ["section_ai_forecast"],
            "stale_approval": ["section_odds"],
        }

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101, 102]))
    recorder = _Recorder()
    result = collection.run_collection_generation(
        session_factory=lambda: _Session(existing_runs=()),
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=recorder,
        fixture_lock=_StubLock,
        admission=gate,
    )

    assert [call["fixture_id"] for call in recorder.calls] == [101, 102]
    assert result["state"] == "finished"
    assert result["reason"] is None
    assert {row["fixture_id"] for row in result["generated"]} == {101, 102}


def test_approval_query_failure_does_not_block_generation(monkeypatch):
    """승인 조회 장애(unknown)도 생성 실패로 바꾸지 않는다."""
    def gate(_factory):
        return {"state": "unknown"}

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101]))
    recorder = _Recorder()
    result = collection.run_collection_generation(
        session_factory=lambda: _Session(existing_runs=()),
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=recorder,
        fixture_lock=_StubLock,
        admission=gate,
    )

    assert [call["fixture_id"] for call in recorder.calls] == [101]
    assert result["state"] == "finished"
    assert result["reason"] is None


def test_non_exception_failed_outcome_is_recorded_as_failed_not_generated(monkeypatch):
    """예외 없이 FAILED로 끝난 생성은 generated에 넣지 않고 failed에 남긴다.

    검사 이유(실패 시 사용자 영향): 필수 섹션을 만들지 못한 실행을 생성 성공으로 세면
    수집 결과 요약이 실패를 성공으로 보고한다.
    """
    class _FailedOutcome:
        run_id = "run-failed-101"
        status = RunStatus.FAILED
        unavailable_reason = "필수 섹션 본문을 만들지 못했습니다: section_ai_forecast"

    def generate(**kwargs):
        return _FailedOutcome()

    monkeypatch.setattr(collection, "collect_candidates", lambda session, now, fixture_ids=None, test_scope=None, skipped=None: _candidates([101, 102]))
    result = collection.run_collection_generation(
        session_factory=lambda: _Session(existing_runs=()),
        preview_session_factory=lambda: _Session(existing_runs=()),
        collection_status="succeeded",
        now=NOW,
        transport=object(),
        generate=generate,
        fixture_lock=_StubLock,
        admission=_ready_gate,
    )

    # generated에 들어가지 않는다.
    assert result["generated"] == []
    # 두 경기 모두 failed로 남고 사유와 run_id가 보존된다.
    assert [row["fixture_id"] for row in result["failed"]] == [101, 102]
    assert result["failed"][0]["run_id"] == "run-failed-101"
    assert result["failed"][0]["reason"] == "generation_status_failed"
    # 다음 경기도 처리됐다(중단되지 않음).
    assert result["state"] == "failed"


# --------------------------------------------------------------------------
# 상위 예외 경로 실행 근거 (지적 2)
# --------------------------------------------------------------------------


class _NoDbTracker:
    """`RunTracker` 대역. flush가 DB를 열지 않게 해 `execute_run`을 실제로 돌린다.

    로그·상태 갱신은 실제 payload에 그대로 남기므로, 검사는 진짜 payload의 최종 상태를
    확인할 수 있다(내부 로직을 복사하지 않는다).
    """

    def __init__(self, payload):
        self.payload = payload
        self.item = None
        self.cancelled = False

    def log(self, message, *, code="PROGRESS", level="info", **context):
        self.payload["logs"].append({"code": code, "message": message, "level": level})
        self.payload["_log_total"] += 1

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


def _payload():
    """`execute_run`이 받는 실제 payload 모양(최소 필드)."""
    return {
        "id": "run-top-level-1",
        "status": "queued",
        "mode": "refresh",
        "created_at": "2026-11-13T04:00:00+09:00",
        "started_at": "2026-11-13T04:00:00+09:00",
        "finished_at": None,
        "cancel_requested_at": None,
        "actor": "테스트",
        "parent_run_id": None,
        "items": [
            {
                "target_id": 1,
                "name": "프리미어리그",
                "status": "pending",
                "total": 0,
                "saved": 0,
                "failed": 0,
                "pending": 0,
                "stored_rows": 0,
            }
        ],
        "logs": [],
        "progress": 0,
        "stage": "실행 준비",
        "log_statistics": {},
        "_log_total": 0,
        "counts_kind": "processing_units",
    }


def test_execute_run_top_level_exception_still_calls_the_preview_hook(monkeypatch):
    """상위 예외로 끝난 수집도 프리뷰 훅을 한 번 호출하고 원래 실패를 보존한다.

    검사 이유(실패 시 사용자 영향): API 키 미설정처럼 수집이 예외로 끝나면 DB에 대상
    경기가 남아 있어도 프리뷰를 시도하지 않아 홈에 새 문서가 생기지 않는다(Q6).

    이 검사는 `execute_run`을 **실제로 호출**한다. 내부 except 로직을 복사하지 않고,
    외부 경계(`get_settings`, 세션, 훅)만 대역으로 바꾼다.
    """
    from app.services import management_runs as mr

    calls: list[dict] = []

    class _Settings:
        home_preview_enabled = True
        api_football_key = None  # 이 값 때문에 `execute_run`이 상위 예외로 끝난다
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60

    class _Guard:
        def __exit__(self, *exc):
            return False

    # 세션 의존(flush)을 없앤다: heartbeat/flush가 DB를 열지 않게 한다.
    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        mr, "run_home_preview_after_sync", lambda **kwargs: calls.append(kwargs) or {"state": "finished"}
    )

    payload = _payload()
    mr.execute_run(payload, _Guard())

    # 훅이 정확히 한 번 호출되고 원래 수집 실패 상태가 전달된다.
    assert len(calls) == 1
    assert calls[0]["collection_status"] == "failed"
    # 원래 수집 실패 기록이 보존된다(프리뷰 상태로 덮이지 않는다).
    assert payload["status"] == "failed"
    assert payload["stage"] == "수집 실행 실패"
    # 프리뷰 결과는 별도 키에 남는다.
    assert payload["home_preview"] == {"state": "finished"}


def test_execute_run_normal_path_does_not_call_the_hook_twice(monkeypatch):
    """정상 경로에서 프리뷰 훅이 돌아도, 그 뒤 예외 경로가 다시 부르지 않는다.

    검사 이유(실패 시 사용자 영향): 같은 수집 종료에서 프리뷰 생성이 두 번 시작되면
    중복 실행이 쌓인다.

    정상 경로를 **실제로 지나가게** 만든다: 측정된 항목 1건과 성공한 backfill을 대역으로
    주고, 정상 훅이 한 번 돈 뒤 finally 이전에 예외를 넣어 예외 경로가 중복 호출하지
    않는지 본다.
    """
    from app.services import management_runs as mr

    calls: list[dict] = []

    class _Settings:
        home_preview_enabled = True
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Client:
        # 실제 호출은 api_key를 **위치 인자**로 넘긴다. 시그니처를 맞춰야 정상 경로에 닿는다.
        def __init__(self, api_key=None, **kwargs):
            pass

        def close(self):
            pass

    class _Plan:
        def unit_count(self, **kwargs):
            return 0

    class _Result:
        seasons: list = []

        def to_log_payload(self):
            return {}

    item = {
        "target_id": 1,
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

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(mr, "measure_league_sync_plan", lambda *a, **k: _Plan())
    monkeypatch.setattr(mr, "backfill_measured_league", lambda *a, **k: _Result())
    # 정상 경로 뒤 예외를 넣어 예외 경로까지 지나가게 한다.
    import app.services.management as management_module

    monkeypatch.setattr(management_module, "prune_league_seasons", lambda *a, **k: None)
    def _hook(**kwargs):
        calls.append(kwargs)
        # 정상 경로의 첫 호출은 기록한 뒤 예외를 낸다. 그러면 예외 경로로 진입하는데,
        # 가드가 살아 있으면 이 훅이 **다시 불리지 않는다**(calls는 1로 유지).
        raise RuntimeError("hook failed on normal path")

    monkeypatch.setattr(mr, "run_home_preview_after_sync", _hook)
    # 정상 훅 뒤 예외: 성공한 항목의 저장 단계에서 예외를 던진다.
    class _Store:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *a, **k):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class _SessionLocal:
        def __call__(self):
            return _Store()

        def __enter__(self):
            return _Store()

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mr.db, "SessionLocal", _SessionLocal())

    payload = _payload()
    payload["items"] = [item]
    try:
        mr.execute_run(payload, _Guard())
    except Exception:
        pass

    # 정상 경로가 훅을 한 번 불렀고, 예외 경로가 또 부르지 않는다.
    assert len(calls) == 1


def test_daily_sync_top_level_exception_calls_the_preview_hook(monkeypatch):
    """daily-sync 상위 예외에서도 프리뷰 훅이 한 번 호출되고 원래 오류가 보존된다.

    검사 이유(실패 시 사용자 영향): daily-sync 경로는 관리 훅과 배선이 달라, 상위 예외에서
    프리뷰를 시도하지 않으면 이 진입점으로 끝난 수집은 홈 문서를 만들지 못한다.

    실제 진입점 `start_daily_sync_run`을 호출한다. 스레드·분산 잠금·동기화 배치·로그 저장만
    대역으로 바꾸고, 내부 except 로직은 복사하지 않는다.
    """
    from app.services import worker_runs as wr

    hook_calls: list[dict] = []

    class _Lock:
        acquired = True

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _Settings:
        home_preview_enabled = True

    monkeypatch.setattr(wr, "_DailySyncAdvisoryLock", lambda: _Lock())
    monkeypatch.setattr(wr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(wr, "load_configured_sync_specs", lambda **kwargs: [])
    # 동기화 자체가 상위 예외로 끝나는 대표 사례.
    monkeypatch.setattr(
        wr, "run_backfill_batch", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("sync exploded"))
    )
    monkeypatch.setattr(wr, "_try_persist_finished_run", lambda run, tracker: None)
    # 훅은 경계에서 대역으로 바꾼다(실제 수집·모델 없음).
    import app.services.management_runs as mr

    monkeypatch.setattr(
        mr, "run_home_preview_after_sync", lambda **kwargs: hook_calls.append(kwargs) or {"state": "finished"}
    )

    started = wr.start_daily_sync_run()
    run_id = started["id"]

    # 스레드가 끝날 때까지 기다린다(폴링 루프가 아니라 종료 대기).
    run = wr._runs[run_id]
    for _ in range(200):
        if run.status in {"failed", "succeeded"}:
            break
        import time as _t

        _t.sleep(0.01)

    # 상위 예외로 실패했고 원래 오류가 보존된다.
    assert run.status == "failed"
    assert "sync exploded" in (run.error or "")
    # 프리뷰 훅이 정확히 한 번, 실패 상태로 호출됐다.
    assert len(hook_calls) == 1
    assert hook_calls[0]["collection_status"] == "failed"
    # 프리뷰 결과는 수집 결과와 별도 키에 남는다.
    assert isinstance(run.result, dict)
    assert run.result.get("home_preview") == {"state": "finished"}


def test_test_scope_limits_generation_to_the_two_named_fixtures(monkeypatch):
    """시험 범위가 있으면 지목한 두 경기만 생성 후보가 된다.

    검사 이유(실패 시 사용자 영향): 같은 시각의 다른 경기까지 생성 예외를 받으면 요청이
    지정한 범위를 넘어 모델이 호출되고 preview_dev 기록이 쌓인다.
    """
    from app.services.collection_test_scope import PreviewTestScope

    class _FixtureRow:
        def __init__(self, external_id):
            self.external_id = external_id
            self.status_short = "NS"
            self.kickoff_at = NOW + timedelta(hours=40)

    class _Team:
        name = "팀"

    # eligible_rows가 (fixture, league, home, away, rank, translations) 튜플을 낸다.
    def fake_eligible(session, *, start=None, end=None, include_unranked=False):
        rows = []
        for external_id in (9001, 9002, 9003):
            fixture = _FixtureRow(external_id)
            rows.append((fixture, None, _Team(), _Team(), 1, {}))
        return rows

    monkeypatch.setattr("app.services.home_preview.eligible_rows", fake_eligible)

    scope = PreviewTestScope(
        fixture_from=NOW,
        fixture_to=NOW + timedelta(hours=48),
        preview_fixture_ids=(9001, 9003),
        run_id="run-1",
    )
    # 대역 세션: candidates 조회만 한다.
    candidates = collection.collect_candidates(None, now=NOW, test_scope=scope)
    ids = [row["fixture_id"] for row in candidates]

    # 지정한 두 경기만 남는다(9002는 같은 시각대지만 대상이 아니다).
    assert sorted(ids) == [9001, 9003]
    # 시험 회차 키를 쓰고 정기 회차 키를 쓰지 않는다.
    assert all(row["round_key"] == "preview-test:run-1" for row in candidates)


def test_fixture_that_leaves_the_period_is_skipped_with_its_own_reason(monkeypatch):
    """수집 후 일정이 바뀌어 기간을 벗어난 지정 경기는 자기 사유로 건너뛴다.

    검사 이유(실패 시 사용자 영향): 사유가 없으면 `no_candidates`만 남아 어느 경기가 왜
    빠졌는지 알 수 없고, 사용자는 수집이 성공했는데 프리뷰만 없는 상태를 진단할 수 없다.
    """
    from app.services.collection_test_scope import PreviewTestScope

    class _FixtureRow:
        def __init__(self, external_id, kickoff, status="NS"):
            self.external_id = external_id
            self.status_short = status
            self.kickoff_at = kickoff

    class _Team:
        name = "팀"

    # 9001은 기간 밖으로 밀렸고, 9002는 기간 안이다.
    outside = NOW + timedelta(days=30)

    def fake_eligible(session, *, start=None, end=None, include_unranked=False):
        return [
            (_FixtureRow(9001, outside), None, _Team(), _Team(), 1, {}),
            (_FixtureRow(9002, NOW + timedelta(hours=40)), None, _Team(), _Team(), 1, {}),
        ]

    monkeypatch.setattr("app.services.home_preview.eligible_rows", fake_eligible)

    scope = PreviewTestScope(
        fixture_from=NOW,
        fixture_to=NOW + timedelta(hours=48),
        preview_fixture_ids=(9001, 9002),
        run_id="run-1",
    )
    skipped: list = []
    candidates = collection.collect_candidates(
        None, now=NOW, test_scope=scope, skipped=skipped
    )

    # 기간 밖 경기는 후보가 아니고, 자기 사유가 남는다.
    assert [row["fixture_id"] for row in candidates] == [9002]
    reasons = {row["fixture_id"]: row["reason"] for row in skipped}
    assert reasons[9001] == "outside_requested_period"
    assert 9002 not in reasons


# --------------------------------------------------------------------------
# 수집만 실행(generate_after_collection=false) — 생성 0회 보장
# --------------------------------------------------------------------------


def _collection_only_scope():
    """수집만 실행을 뜻하는 시험 범위."""
    from app.services.collection_test_scope import PreviewTestScope

    return PreviewTestScope(
        fixture_from=NOW,
        fixture_to=NOW + timedelta(hours=48),
        preview_fixture_ids=(9001, 9002),
        run_id="run-collection-only",
        generate_after_collection=False,
    )


def test_collection_only_scope_skips_the_hook_on_the_normal_path(monkeypatch):
    """수집만 실행은 정상 종료 경로에서 생성 훅을 **부르지 않는다**.

    검사 이유(실패 시 사용자 영향): 사용자가 "수집만"을 요청했는데 자동 생성이 돌면
    실제 모델 호출이 나가고, 결과 확인 전에 프리뷰가 만들어진다.

    `execute_run`을 실제로 호출하고 외부 경계(설정·클라이언트·수집 계획·세션·훅)만
    대역으로 바꾼다. 전역 `HOME_PREVIEW_ENABLED`가 켜져 있어도 생성하지 않아야 한다.
    """
    from app.services import management_runs as mr

    calls: list[dict] = []

    class _Settings:
        home_preview_enabled = True  # 전역 플래그가 켜져 있어도 이 요청은 생성 0회다.
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1

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

    class _Store:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *args, **kwargs):
            return None

        def commit(self):
            return None

        def rollback(self):
            return None

    class _SessionLocal:
        def __call__(self):
            return _Store()

    item = {
        "target_id": 1,
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

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(mr, "measure_league_sync_plan", lambda *a, **k: _Plan())
    monkeypatch.setattr(mr, "backfill_measured_league", lambda *a, **k: _Result())
    monkeypatch.setattr(mr.db, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(
        mr,
        "run_home_preview_after_sync",
        lambda **kwargs: calls.append(kwargs) or {"state": "finished"},
    )

    payload = _payload()
    payload["items"] = [item]
    payload["test_scope"] = _collection_only_scope().to_dict()
    mr.execute_run(payload, _Guard())

    # 정상 종료했고, 생성 훅은 한 번도 불리지 않았으며, 생성 결과 키도 없다.
    assert payload["status"] == "succeeded"
    assert calls == []
    assert "home_preview" not in payload


def test_collection_only_scope_skips_the_hook_on_the_exception_path(monkeypatch):
    """수집만 실행은 **상위 예외** 경로에서도 생성 훅을 부르지 않는다.

    검사 이유(실패 시 사용자 영향): 예외 경로가 유일한 생성 진입로가 되면, API 키
    미설정 같은 흔한 실패에서 오히려 모델 호출이 나간다.
    """
    from app.services import management_runs as mr

    calls: list[dict] = []

    class _Settings:
        home_preview_enabled = True
        api_football_key = None  # 이 값 때문에 상위 예외로 끝난다.
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60

    class _Guard:
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        mr,
        "run_home_preview_after_sync",
        lambda **kwargs: calls.append(kwargs) or {"state": "finished"},
    )

    payload = _payload()
    payload["test_scope"] = _collection_only_scope().to_dict()
    mr.execute_run(payload, _Guard())

    # 수집 실패는 그대로 보존되고, 생성 시도는 0회다.
    assert payload["status"] == "failed"
    assert calls == []
    assert "home_preview" not in payload


def test_default_scope_still_generates_after_collection(monkeypatch):
    """`generate_after_collection`을 지정하지 않은 범위는 **기존 동작**을 유지한다.

    검사 이유(실패 시 사용자 영향): 기본값이 뒤집히면 기존 자동 수집 경로가 조용히
    생성을 멈춘다.
    """
    from app.services import management_runs as mr
    from app.services.collection_test_scope import PreviewTestScope

    calls: list[dict] = []

    class _Settings:
        home_preview_enabled = False
        api_football_key = None

    class _Guard:
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(
        mr,
        "run_home_preview_after_sync",
        lambda **kwargs: calls.append(kwargs) or {"state": "finished"},
    )

    scope = PreviewTestScope(
        fixture_from=NOW,
        fixture_to=NOW + timedelta(hours=48),
        preview_fixture_ids=(9001, 9002),
        run_id="run-default",
    )
    assert scope.generate_after_collection is True

    payload = _payload()
    payload["test_scope"] = scope.to_dict()
    mr.execute_run(payload, _Guard())

    # 전역 플래그가 꺼져 있어도 시험 범위는 이 요청에 한해 훅을 한 번 부른다(기존 계약).
    assert len(calls) == 1
    assert payload["home_preview"] == {"state": "finished"}


def test_collection_only_flag_survives_the_stored_roundtrip():
    """저장된 범위를 복원해도 수집만 실행 여부가 보존된다.

    검사 이유(실패 시 사용자 영향): 실행기는 payload에 저장된 범위를 다시 읽는다.
    복원에서 이 값이 사라지면 수집만 실행이 생성까지 시작한다.
    """
    from app.services.collection_test_scope import PreviewTestScope

    scope = _collection_only_scope()
    restored = PreviewTestScope.from_dict(scope.with_run_id("run-9").to_dict())

    assert restored is not None
    assert restored.generate_after_collection is False
    assert restored.run_id == "run-9"


def test_stored_scope_without_the_flag_keeps_generating():
    """이 키가 없는 옛 저장 값은 **생성함**으로 복원된다(이미 접수된 실행의 의미 보존)."""
    from app.services.collection_test_scope import PreviewTestScope

    restored = PreviewTestScope.from_dict(
        {
            "fixture_from": NOW.isoformat(),
            "fixture_to": (NOW + timedelta(hours=48)).isoformat(),
            "preview_fixture_ids": [9001, 9002],
            "run_id": "run-legacy",
        }
    )

    assert restored is not None
    assert restored.generate_after_collection is True


# --------------------------------------------------------------------------
# 실제 수집 경기 근거(collection_evidence) — 계획과 저장의 구별
# --------------------------------------------------------------------------


class _SeasonPlanStub:
    def __init__(self, fixture_ids):
        self.fixture_external_ids = list(fixture_ids)


class _PlanStub:
    def __init__(self, fixture_ids):
        self.seasons = [_SeasonPlanStub(fixture_ids)]

    def unit_count(self, **kwargs):
        return len(self.seasons[0].fixture_external_ids) * 4


class _SeasonResultStub:
    def __init__(self, errors=None, stored=(), details=()):
        self.errors = list(errors or [])
        self.fixture_external_ids_stored = list(stored)
        self.detail_fixture_external_ids_stored = list(details)


class _ResultStub:
    def __init__(self, seasons):
        self.seasons = list(seasons)


def _run_with_evidence(monkeypatch, *, plan_ids, result):
    """`execute_run`을 실제로 돌려 payload의 collection_evidence를 돌려준다.

    외부 경계(설정·클라이언트·계획·백필·세션·훅)만 대역으로 바꾼다. 근거 접기는
    실제 코드가 한다.
    """
    from app.services import management_runs as mr

    class _Settings:
        home_preview_enabled = False
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Client:
        def __init__(self, api_key=None, **kwargs):
            pass

        def close(self):
            pass

    class _Target:
        """저장 단계가 읽는 대상 행. 커밋 경로를 실제로 지나가게 한다."""

        last_sync = None
        initial_status = None

    class _Store:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get(self, *args, **kwargs):
            # 대상 행이 없으면 `execute_run`이 커밋하지 않는다. 실제 수집에서는 대상 행이
            # 있으므로 여기서도 있다고 둔다(커밋 확인 규칙을 검사하기 위해서다).
            return _Target()

        def commit(self):
            return None

        def rollback(self):
            return None

    class _SessionLocal:
        def __call__(self):
            return _Store()

    item = {
        "target_id": 1,
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
            "include_details": True,
            "include_players": False,
            "include_standings": False,
            "fixture_limit": None,
        },
    }

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(mr, "measure_league_sync_plan", lambda *a, **k: _PlanStub(plan_ids))
    monkeypatch.setattr(mr, "backfill_measured_league", lambda *a, **k: result)
    monkeypatch.setattr(mr.db, "SessionLocal", _SessionLocal())
    monkeypatch.setattr(mr, "run_home_preview_after_sync", lambda **k: {"state": "finished"})

    payload = _payload()
    payload["items"] = [item]
    payload["test_scope"] = {
        "fixture_from": NOW.isoformat(),
        "fixture_to": (NOW + timedelta(hours=48)).isoformat(),
        "preview_fixture_ids": [9001, 9002],
        "run_id": "run-evidence",
        "generate_after_collection": False,
    }
    mr.execute_run(payload, _Guard())
    return payload


def test_evidence_separates_planned_fixtures_from_actually_stored_ones(monkeypatch):
    """계획에 있던 경기와 **실제로 저장된** 경기를 구별하고, 확인 불가는 따로 남긴다.

    검사 이유(실패 시 사용자 영향): 처리 단위 카운터만 보이면 사용자는 기간 안 어느
    경기가 갱신됐는지 알 수 없고, 계획 목록을 저장 성공으로 오해한다.

    선택한 생성 대상 두 경기는 이 목록과 다르므로 함께 표시하지 않는다.
    """
    result = _ResultStub(
        [
            _SeasonResultStub(
                errors=[], stored=[9001, 9003], details=[9001]
            )
        ]
    )
    payload = _run_with_evidence(monkeypatch, plan_ids=[9001, 9003, 9004], result=result)

    evidence = payload["collection_evidence"]
    # 계획 3건, 저장 2건, 상세 저장 1건, 확인되지 않음 1건.
    assert evidence["planned_fixture_ids"] == [9001, 9003, 9004]
    assert evidence["stored_fixture_ids"] == [9001, 9003]
    assert evidence["detail_stored_fixture_ids"] == [9001]
    assert evidence["unverified_fixture_ids"] == [9004]
    assert evidence["counts"] == {
        "planned": 3,
        "stored": 2,
        "detail_stored": 1,
        "unverified": 1,
    }
    # 확인되지 않은 경기를 실패로 단정하지 않고, 그 사실을 문장으로 남긴다.
    assert evidence["partial"] is False
    assert any("확인되지 않은" in note for note in evidence["notes"])
    # 생성 대상 두 경기는 근거 목록이 아니라 별도 필드에 있다.
    assert evidence["scope_fixture_ids"] == [9001, 9002]


def test_evidence_marks_partial_when_a_collection_step_reported_errors(monkeypatch):
    """수집 단계 오류가 있으면 `partial`로 표시한다(확인된 범위만 신뢰).

    검사 이유(실패 시 사용자 영향): 부분 실패를 정상 수집으로 보여 주면 사용자가
    확인 범위를 전체로 오해한다.
    """
    result = _ResultStub(
        [_SeasonResultStub(errors=["details:9002:timeout"], stored=[9001], details=[])]
    )
    payload = _run_with_evidence(monkeypatch, plan_ids=[9001, 9002], result=result)

    evidence = payload["collection_evidence"]
    assert evidence["partial"] is True
    assert evidence["stored_fixture_ids"] == [9001]
    assert evidence["detail_stored_fixture_ids"] == []
    assert evidence["unverified_fixture_ids"] == [9002]


def test_evidence_is_absent_for_a_normal_collection_run(monkeypatch):
    """일반 수집 실행에는 이 키를 만들지 않는다(기존 응답 모양 보존).

    검사 이유(실패 시 사용자 영향): 모든 실행에 새 키가 붙으면 기존 소비자가 바뀐
    응답 모양을 처리해야 한다.
    """
    result = _ResultStub([_SeasonResultStub(errors=[], stored=[9001])])
    payload = _run_with_evidence(monkeypatch, plan_ids=[9001], result=result)

    # 시험 범위 실행에서는 있다.
    assert "collection_evidence" in payload

    # 시험 범위가 없으면 없다.
    from app.services import management_runs as mr

    plain = _payload()
    plain["items"] = payload["items"]
    plain.pop("test_scope", None)

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Settings:
        home_preview_enabled = False
        api_football_key = None

    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "run_home_preview_after_sync", lambda **k: {"state": "finished"})
    mr.execute_run(plain, _Guard())
    assert "collection_evidence" not in plain


def test_evidence_marks_partial_when_collection_fails_before_any_result(monkeypatch):
    """백필 결과가 하나도 없어도 **대상 실패/예외가 partial로 반영**된다.

    검사 이유(실패 시 사용자 영향): 백필이 예외로 끝나 결과가 없으면, 결과만 보는 판정은
    `partial=false`가 되어 실패한 수집이 정상으로 보인다. 사용자는 확인된 저장이 0건인
    실행을 "이상 없음"으로 읽는다.
    """
    from app.services import management_runs as mr

    class _Settings:
        home_preview_enabled = False
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Client:
        def __init__(self, api_key=None, **kwargs):
            pass

        def close(self):
            pass

    class _Store:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def rollback(self):
            return None

    class _SessionLocal:
        def __call__(self):
            return _Store()

    item = {
        "target_id": 1,
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
            "include_details": True,
            "include_players": False,
            "include_standings": False,
            "fixture_limit": None,
        },
    }

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(mr, "measure_league_sync_plan", lambda *a, **k: _PlanStub([9001, 9002]))
    monkeypatch.setattr(mr.db, "SessionLocal", _SessionLocal())
    # 백필이 예외로 끝난다(결과 객체 없음).
    monkeypatch.setattr(
        mr,
        "backfill_measured_league",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("store exploded")),
    )
    monkeypatch.setattr(mr, "run_home_preview_after_sync", lambda **k: {"state": "finished"})

    payload = _payload()
    payload["items"] = [item]
    payload["test_scope"] = {
        "fixture_from": NOW.isoformat(),
        "fixture_to": (NOW + timedelta(hours=48)).isoformat(),
        "preview_fixture_ids": [9001, 9002],
        "run_id": "run-failed",
        "generate_after_collection": False,
    }
    mr.execute_run(payload, _Guard())

    evidence = payload["collection_evidence"]
    # 결과가 없어도 partial이고, 계획 경기는 저장 성공으로 표시되지 않는다.
    assert evidence["partial"] is True
    assert evidence["stored_fixture_ids"] == []
    assert evidence["unverified_fixture_ids"] == [9001, 9002]
    assert evidence["counts"]["stored"] == 0
    assert payload["items"][0]["status"] == "failed"


def test_evidence_marks_partial_when_the_target_failed_during_measurement(monkeypatch):
    """수집 범위 확인 단계에서 대상이 실패하면 partial이다(계획이 없어도).

    검사 이유(실패 시 사용자 영향): 계획조차 없으면 근거가 비어 보이는데, 그 상태를
    정상으로 표시하면 실패한 수집이 "대상 없음"처럼 보인다.
    """
    from app.services import management_runs as mr

    class _Settings:
        home_preview_enabled = False
        api_football_key = "test-key"
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60
        api_football_concurrency = 1

    class _Guard:
        def __exit__(self, *exc):
            return False

    class _Client:
        def __init__(self, api_key=None, **kwargs):
            pass

        def close(self):
            pass

    item = {
        "target_id": 1,
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
            "include_details": True,
            "include_players": False,
            "include_standings": False,
            "fixture_limit": None,
        },
    }

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())
    monkeypatch.setattr(mr, "ApiFootballClient", _Client)
    monkeypatch.setattr(
        mr,
        "measure_league_sync_plan",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("API-Football returned no league")),
    )
    monkeypatch.setattr(mr, "run_home_preview_after_sync", lambda **k: {"state": "finished"})

    payload = _payload()
    payload["items"] = [item]
    payload["test_scope"] = {
        "fixture_from": NOW.isoformat(),
        "fixture_to": (NOW + timedelta(hours=48)).isoformat(),
        "preview_fixture_ids": [9001, 9002],
        "run_id": "run-measure-failed",
        "generate_after_collection": False,
    }
    mr.execute_run(payload, _Guard())

    evidence = payload["collection_evidence"]
    assert evidence["partial"] is True
    assert evidence["planned_fixture_ids"] == []
    assert evidence["stored_fixture_ids"] == []
    assert payload["status"] == "failed"


def test_evidence_is_written_on_the_top_level_exception_path(monkeypatch):
    """상위 예외로 끝난 시험 실행도 근거를 남기고 `partial`이 true다.

    검사 이유(실패 시 사용자 영향): 예외 경로에 근거 키가 없으면 화면이 "저장 0건"과
    "근거 없음"을 구분하지 못하고, 실패한 실행을 정상 모양으로 표시한다.
    """
    from app.services import management_runs as mr

    class _Settings:
        home_preview_enabled = False
        api_football_key = None  # 이 값 때문에 상위 예외로 끝난다.
        api_football_host = "https://example.test"
        api_football_requests_per_minute = 60

    class _Guard:
        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(mr, "RunTracker", _NoDbTracker)
    monkeypatch.setattr(mr, "get_settings", lambda: _Settings())

    payload = _payload()
    payload["test_scope"] = {
        "fixture_from": NOW.isoformat(),
        "fixture_to": (NOW + timedelta(hours=48)).isoformat(),
        "preview_fixture_ids": [9001, 9002],
        "run_id": "run-exc",
        "generate_after_collection": False,
    }
    mr.execute_run(payload, _Guard())

    evidence = payload["collection_evidence"]
    assert payload["status"] == "failed"
    assert evidence["partial"] is True
    assert evidence["stored_fixture_ids"] == []
    assert evidence["planned_fixture_ids"] == []
