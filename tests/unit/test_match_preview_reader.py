"""공통 생성 서비스의 저장 경기 조회기 전달·수명 검사.

검사 이유(실패 시 사용자 영향): 수집 종료 훅은 조회기를 넘기지 않는다. 서비스가 설정으로
조회기를 열어 경기 ID만 해석하고 곧바로 닫은 뒤 파이프라인에는 `None`을 넘기면, 본문 자료
준비(경기 식별 coverage·부상·순위)가 "저장 경기 자료 읽기 연결이 설정되지 않았습니다"로
비어 실제 생성 본문에서 수집된 순위·부상 자료가 빠진다. 실제로 이번 수집 실행에서
`db_snapshot.readable=false`·`not_run`·`standings=[]`가 관측됐다.

**합성 검사다.** 실제 DB·HTTP·모델을 호출하지 않는다. 조회기·세션·파이프라인 경계를
대역으로 바꾸고, 서비스가 **실제로 조회기를 넘기는지**와 **닫힘 순서**를 확인한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.services import match_preview as service

pytestmark = pytest.mark.unit


class _Record:
    """저장 경기 행 대역. `resolve_stored_fixture`가 읽는 필드만 갖는다."""

    fixture_id = 1557470
    league_id = 1
    season = 2026
    home_team_id = 13
    away_team_id = 36
    kickoff_at = datetime(2026, 11, 22, 0, 0, tzinfo=timezone.utc)
    label = "첼시 대 리즈"
    internal_id = 501


class _Access:
    readable = True
    detail = None


class _Reader:
    """조회기 대역. 열림/닫힘과 사용 시점을 기록한다.

    핵심: **닫힌 뒤에 쓰이면 실패**하도록 만든다. 이렇게 해야 "넘겼지만 이미 닫힌 조회기"를
    잡을 수 있다(단순 kwargs 비교로는 잡히지 않는다).
    """

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    def access(self):
        self._require_open("access")
        self.events.append("reader.access")
        return _Access()

    def get_fixture(self, *, fixture_id):
        self._require_open("get_fixture")
        self.events.append("reader.get_fixture")
        return _Record()

    def injuries_for_fixture(self, fixture_id):
        self._require_open("injuries_for_fixture")
        self.events.append("reader.injuries_for_fixture")
        return []

    def close(self):
        self.closed = True
        self.events.append("reader.close")

    def _require_open(self, where: str) -> None:
        if self.closed:
            raise AssertionError(
                f"이미 닫힌 조회기를 {where}에서 사용했다(닫힘 순서 결함)"
            )


class _Session:
    def commit(self):
        return None

    def rollback(self):
        return None


def _run(monkeypatch, *, reader=None, events=None, pipeline_uses_reader=True):
    """서비스 한 번 호출. 파이프라인 대역이 실제로 조회기를 쓰는지 확인할 수 있게 한다."""
    events = events if events is not None else []
    captured: dict = {}

    opened = reader if reader is not None else _Reader(events)

    def fake_from_settings(_settings=None):
        if reader is not None:
            raise AssertionError("호출자 주입 조회기가 있는데 새로 열었다")
        events.append("reader.open")
        return opened

    monkeypatch.setattr(service, "_resolver_from_settings", fake_from_settings)

    class _Outcome:
        run_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
        mode = None
        status = None
        quality = None

    def fake_pipeline(_session, **kwargs):
        captured.update(kwargs)
        passed = kwargs.get("reader")
        if pipeline_uses_reader:
            # 실제 파이프라인이 하는 일을 흉내 낸다: 같은 조회기로 부상 자료를 읽는다.
            assert passed is not None, "파이프라인에 조회기가 전달되지 않았다"
            passed.injuries_for_fixture(1557470)
        events.append("pipeline.run")
        return _Outcome()

    monkeypatch.setattr(service.bundle_pipeline, "run_bundle_pipeline", fake_pipeline)

    outcome = service.generate_match_preview(
        fixture_id=1557470,
        actor_id=None,
        trigger="collection",
        session=_Session(),
        transport=object(),
        reader=reader,
    )
    return outcome, captured, events, opened


def test_collection_call_without_reader_uses_one_open_reader_for_both_stages(monkeypatch):
    """조회기를 생략한 수집 호출이 해석과 생성에 **같은 열린 조회기**를 쓴다.

    검사 이유: 이 연결이 끊기면 수집된 순위·부상 자료가 생성 입력에서 빠진다.
    """
    _outcome, captured, events, opened = _run(monkeypatch)

    # 파이프라인에 실제 조회기가 전달됐다.
    assert captured["reader"] is opened
    # 해석 단계와 파이프라인 단계가 같은 조회기를 사용했다.
    assert events.index("reader.get_fixture") < events.index("pipeline.run")
    assert events.index("reader.injuries_for_fixture") < events.index("pipeline.run")
    # 조회기는 한 번만 열렸다.
    assert events.count("reader.open") == 1


def test_service_owned_reader_is_closed_after_success(monkeypatch):
    """서비스가 연 조회기는 성공 경로에서 닫힌다(연결 누수 없음)."""
    _outcome, _captured, events, opened = _run(monkeypatch)
    assert "reader.close" in events
    # 닫힘은 파이프라인 **뒤**다(사용 중에 닫지 않는다).
    assert events.index("pipeline.run") < events.index("reader.close")
    # 정확히 한 번만 닫는다. 해석 단계의 대여(borrow) 정리와 이 서비스의 정리가
    # 겹쳐 두 번 닫히면 커넥션이 조기 반환되어 다음 단계가 닫힌 조회기를 볼 수 있다.
    assert events.count("reader.close") == 1, events
    assert opened.closed is True


def test_caller_supplied_reader_is_not_closed(monkeypatch):
    """호출자가 주입한 조회기는 호출자 소유이므로 서비스가 닫지 않는다."""
    events: list[str] = []
    injected = _Reader(events)
    _outcome, captured, events, _opened = _run(monkeypatch, reader=injected, events=events)

    assert captured["reader"] is injected
    assert "reader.close" not in events
    assert injected.closed is False


def test_reader_is_closed_when_generation_raises(monkeypatch):
    """생성 단계가 예외로 끝나도 서비스가 연 조회기는 정리된다."""
    events: list[str] = []

    def fake_from_settings(_settings=None):
        events.append("reader.open")
        return opened

    opened = _Reader(events)
    monkeypatch.setattr(service, "_resolver_from_settings", fake_from_settings)

    def exploding_pipeline(_session, **kwargs):
        events.append("pipeline.run")
        raise RuntimeError("모델 전송 실패")

    monkeypatch.setattr(service.bundle_pipeline, "run_bundle_pipeline", exploding_pipeline)

    with pytest.raises(RuntimeError):
        service.generate_match_preview(
            fixture_id=1557470,
            actor_id=None,
            trigger="collection",
            session=_Session(),
            transport=object(),
        )

    assert events.index("pipeline.run") < events.index("reader.close")
    assert opened.closed is True


def test_reader_is_closed_when_resolution_fails(monkeypatch):
    """해석 단계가 실패해도 서비스가 연 조회기는 정리된다."""
    events: list[str] = []

    class _Missing(_Reader):
        def get_fixture(self, *, fixture_id):
            self._require_open("get_fixture")
            events.append("reader.get_fixture")
            return None  # 경기를 찾지 못함

    opened = _Missing(events)

    monkeypatch.setattr(
        service, "_resolver_from_settings", lambda _settings=None: (
            events.append("reader.open") or opened
        )
    )

    with pytest.raises(service.FixtureResolutionError):
        service.generate_match_preview(
            fixture_id=1557470,
            actor_id=None,
            trigger="collection",
            session=_Session(),
            transport=object(),
        )

    assert opened.closed is True
    # 해석 실패이므로 파이프라인은 실행되지 않았다(모델 전송 없음).
    assert "pipeline.run" not in events


def test_unreadable_stored_data_still_fails_before_any_model_call(monkeypatch):
    """저장 자료를 읽을 수 없으면 기존 명확한 오류를 유지하고 모델을 보내지 않는다.

    검사 이유: 이 경계가 느슨해지면 자료 없이 생성이 진행돼 빈 본문이 만들어진다.
    """
    events: list[str] = []

    class _Denied(_Reader):
        def access(self):
            self._require_open("access")
            events.append("reader.access")
            return type("A", (), {"readable": False, "detail": "권한 없음"})()

    opened = _Denied(events)
    monkeypatch.setattr(
        service, "_resolver_from_settings", lambda _settings=None: opened
    )

    with pytest.raises(service.FixtureResolutionError) as excinfo:
        service.generate_match_preview(
            fixture_id=1557470,
            actor_id=None,
            trigger="collection",
            session=_Session(),
            transport=object(),
        )

    assert excinfo.value.reason == "reader_denied"
    assert "pipeline.run" not in events
    assert opened.closed is True


def test_unconfigured_reader_keeps_its_clear_error(monkeypatch):
    """조회기가 설정되지 않았으면 기존 사유를 유지한다(모의로 대체하지 않음)."""
    monkeypatch.setattr(service, "_resolver_from_settings", lambda _settings=None: None)

    with pytest.raises(service.FixtureResolutionError) as excinfo:
        service.generate_match_preview(
            fixture_id=1557470,
            actor_id=None,
            trigger="collection",
            session=_Session(),
            transport=object(),
        )

    assert excinfo.value.reason == "reader_unconfigured"


def test_collection_trigger_still_rejects_a_manage_actor(monkeypatch):
    """시스템 호출 표식과 관리자 위장 금지는 그대로다(정책 보존)."""
    events: list[str] = []
    opened = _Reader(events)
    monkeypatch.setattr(
        service, "_resolver_from_settings", lambda _settings=None: opened
    )

    with pytest.raises(ValueError):
        service.generate_match_preview(
            fixture_id=1557470,
            actor_id=7,  # 수집 호출에 관리자 ID를 넘기면 거부
            trigger="collection",
            session=_Session(),
            transport=object(),
        )
    assert "pipeline.run" not in events
    assert opened.closed is True
