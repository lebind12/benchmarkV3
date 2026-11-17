"""bundle 실행 요청 식별자 중복 경계 직접 검사.

검사 이유(실패 시 사용자 영향): 화면에서 같은 요청이 두 번 나가면(더블클릭, 응답 유실
뒤 재전달, 새로고침 뒤 재시도) 실제 모델 호출이 두 번 결제되고 결과가 두 벌 저장된다.
사용자는 한 번 눌렀는데 실행이 두 개 생기는 것을 보게 된다.

**합성·단위 검사다.** 실제 모델·실제 공급자를 호출하지 않는다. 저장된 실행 행과 요청
표기 계산만 확인한다. PostgreSQL 동시 잠금은 단위 검사 대상이 아니며(연결 필요),
잠금을 잡지 못한 경우의 판정만 대역으로 확인한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.unit

FIXTURE_IN_SCOPE = 1557474


class _Run:
    """`PreviewRun` 중 이 검사가 읽는 값만 가진 행 대역."""

    def __init__(self, *, fixture_id=FIXTURE_IN_SCOPE, run_id=None, label=None):
        self.id = run_id or uuid.uuid4()
        self.fixture_id = fixture_id
        self.label = label
        self.mode = "live"
        self.status = "succeeded"
        self.quality = "ready"
        self.failure_detail = None


def test_marker_is_embedded_in_the_run_label_without_duplication():
    """요청 표기는 label에 **한 번만** 붙는다.

    사용자 영향: 같은 요청을 재전달할 때마다 표기가 쌓이면, 재전달이 새 실행으로
    오인되어 중복 호출을 막지 못한다.
    """
    from app.preview import preview_test_requests as requests

    request_id = uuid.uuid4()
    once = requests.label_with_request(
        "정보 원문 프리뷰 · live", request_id, default="정보 원문 프리뷰 · live"
    )
    twice = requests.label_with_request(once, request_id, default="정보 원문 프리뷰 · live")

    assert once == twice
    assert str(request_id) in once
    assert once.count(requests.request_marker(request_id)) == 1


def test_label_without_a_user_label_uses_the_default_then_marks_the_request():
    """label을 보내지 않은 요청도 표기를 남긴다(재전달 판정의 유일한 근거)."""
    from app.preview import preview_test_requests as requests

    request_id = uuid.uuid4()
    label = requests.label_with_request(None, request_id, default="정보 원문 프리뷰 · live")

    assert label.startswith("정보 원문 프리뷰 · live")
    assert requests.request_marker(request_id) in label


class _Session:
    """`find_requested_run`이 쓰는 조회만 흉내 내는 세션.

    실제 저장소는 `label LIKE '%request=<id>%'`로 찾는다. 여기서도 **문장에 바인딩된
    요청 표기**로 걸러야 한다. 저장된 행에서 표기를 꺼내 쓰면 어떤 요청 ID를 넣어도
    같은 행을 돌려주는 대역이 되어, 다른 UUID가 기존 실행에 붙는지 판별하지 못한다.
    """

    def __init__(self, rows):
        self.rows = list(rows)

    def scalar(self, statement):
        params = dict(statement.compile().params)
        marker = next(
            (str(value) for value in params.values() if str(value).startswith("request=")),
            None,
        )
        if marker is None:
            return None
        return next(
            (row for row in self.rows if row.label and marker in row.label),
            None,
        )


def test_same_request_id_finds_the_stored_run_instead_of_a_new_one():
    """같은 request_id는 저장된 실행을 찾는다(새 실행을 만들 근거가 없다)."""
    from app.preview import preview_test_requests as requests

    request_id = uuid.uuid4()
    stored = _Run(label=f"정보 원문 프리뷰 · live · {requests.request_marker(request_id)}")
    session = _Session([stored])

    found = requests.find_requested_run(session, request_id)

    assert found is not None
    assert found.id == stored.id


def test_a_different_request_id_does_not_match_the_stored_run():
    """새 UUID(명시적 재생성)는 기존 실행에 붙지 않는다.

    사용자 영향: 사용자가 명시적으로 다시 생성했는데 이전 실행이 돌아오면, 새로
    만들어 달라는 요청이 조용히 무시된다.
    """
    from app.preview import preview_test_requests as requests

    first = uuid.uuid4()
    stored = _Run(label=f"정보 원문 프리뷰 · live · {requests.request_marker(first)}")
    session = _Session([stored])

    assert requests.find_requested_run(session, uuid.uuid4()) is None


def test_same_request_id_for_another_fixture_is_a_conflict():
    """같은 request_id를 다른 경기에 쓰면 409 사유가 되는 충돌이다.

    사용자 영향: 경기 A의 실행이 경기 B의 요청 응답으로 돌아가면 화면이 다른 경기의
    문서를 A의 결과로 표시한다.
    """
    from app.preview import preview_test_requests as requests

    stored = _Run(fixture_id=1557470)

    with pytest.raises(requests.RequestConflict):
        requests.ensure_same_fixture(stored, fixture_id=FIXTURE_IN_SCOPE)


def test_same_request_id_for_the_same_fixture_is_not_a_conflict():
    """같은 경기·같은 request_id는 충돌이 아니다(정상 재전달)."""
    from app.preview import preview_test_requests as requests

    requests.ensure_same_fixture(_Run(), fixture_id=FIXTURE_IN_SCOPE)


def test_losing_the_request_lock_raises_instead_of_generating_twice(monkeypatch):
    """동시 요청이 잠금을 못 잡으면 **생성하지 않고** 409 사유를 낸다.

    사용자 영향: 잠금 없이 진행하면 같은 요청 두 개가 동시에 모델을 부른다.

    실제 PostgreSQL 잠금은 이 단위 검사 범위가 아니므로 잠금 결과만 대역으로 바꾼다.
    """
    from app.preview import preview_test_requests as requests

    class _Connection:
        def execute(self, statement, params=None):
            return type("R", (), {"scalar": staticmethod(lambda: False)})()

        def close(self):
            return None

    class _Engine:
        def connect(self):
            return _Connection()

    monkeypatch.setattr(
        "app.preview.db.get_engine", lambda: _Engine(), raising=True
    )

    with pytest.raises(requests.RequestInFlight):
        with requests.request_lock(uuid.uuid4()):
            pytest.fail("잠금을 잡지 못했으면 본문이 실행되면 안 된다")


def test_replay_response_returns_stored_status_without_calling_the_model(monkeypatch):
    """재전달 응답은 **저장된 행**으로 만든다. 모델 생성 서비스를 부르지 않는다.

    사용자 영향: 재전달이 생성 서비스를 다시 부르면 응답 유실 뒤 재시도가 곧 중복
    과금이 된다.
    """
    from app.preview import preview_test_requests as requests

    run = _Run(run_id=uuid.uuid4())

    class _Session:
        def get(self, model, key):
            return run

    def _boom(*args, **kwargs):
        raise AssertionError("재전달은 생성 서비스를 호출하면 안 됩니다")

    monkeypatch.setattr("app.services.match_preview.generate_match_preview", _boom)
    monkeypatch.setattr(
        "app.preview.store.load_information_bundle",
        lambda session, run_id: {
            "available": True,
            "artifact_id": "artifact-1",
            "summary": {"bundle_id": "bundle-1", "bundle_hash": "hash-1"},
        },
    )
    monkeypatch.setattr(
        "app.preview.store.list_section_results",
        lambda session, run_id: [
            {
                "workflow_id": "section_ai_forecast",
                "section_result_id": "result-1",
                "quality": "ready",
                "unavailable_reason": None,
            }
        ],
    )
    monkeypatch.setattr(
        "app.preview.store.run_send_ledger_summary",
        lambda session, run_id: {"charged_requests": 3},
    )

    replay = requests.replay_response(_Session(), run.id)

    assert replay is not None
    assert replay["run_id"] == str(run.id)
    assert replay["status"] == "succeeded"
    assert replay["bundle_id"] == "bundle-1"
    assert replay["bundle_artifact_id"] == "artifact-1"
    assert replay["section_result_ids"] == {"section_ai_forecast": "result-1"}
    # 실제 전송 수는 장부에서 읽은 값이며, 재전달 자체가 늘리지 않는다.
    assert replay["external_calls"] == 3
    assert replay["note"] == requests.REPLAY_NOTE


def test_replay_of_an_unknown_run_is_none_instead_of_an_invented_response():
    """저장 행이 없으면 응답을 지어내지 않는다(`None`)."""
    from app.preview import preview_test_requests as requests

    class _Session:
        def get(self, model, key):
            return None

    assert requests.replay_response(_Session(), uuid.uuid4()) is None


def test_request_id_is_optional_in_the_existing_request_contract():
    """`request_id`는 선택이다. 기존 요청 본문은 그대로 유효하다.

    사용자 영향: 이 필드를 강제하면 기존 관리자 호출부가 422로 깨진다.
    """
    from app.api.v1.preview_admin import BundlePreviewRunRequest

    without = BundlePreviewRunRequest(fixture_id=FIXTURE_IN_SCOPE, mode="live")
    with_id = BundlePreviewRunRequest(
        fixture_id=FIXTURE_IN_SCOPE, mode="live", request_id=uuid.uuid4()
    )

    assert without.request_id is None
    assert isinstance(with_id.request_id, uuid.UUID)


class _StoredRun:
    """저장된 실행 행 대역. 핸들러가 쓰는 열만 있다."""

    def __init__(self, *, run_id, fixture_id, label):
        self.id = run_id
        self.fixture_id = fixture_id
        self.label = label
        self.mode = "live"
        self.status = "succeeded"
        self.quality = "ready"
        self.failure_detail = None


class _StoringSession:
    """실행 저장을 흉내 내는 세션(`bundle-runs` 핸들러용).

    중복 조회(`label LIKE`)와 재전달 조회(`get`)를 **같은 저장 행**에서 처리한다.
    실제 DB를 쓰지 않으므로 공유 테스트 DB 초기화도 하지 않는다.
    """

    def __init__(self):
        self.runs = []
        self.commits = 0

    def scalar(self, statement):
        params = dict(statement.compile().params)
        marker = next(
            (str(value) for value in params.values() if str(value).startswith("request=")),
            None,
        )
        if marker is None:
            return None
        return next((run for run in self.runs if run.label and marker in run.label), None)

    def get(self, model, key):
        return next((run for run in self.runs if run.id == key), None)

    def add(self, row):  # 실행 저장 서비스가 쓰는 경로(이 검사에서는 쓰지 않는다)
        return None

    def commit(self):
        self.commits += 1


def test_repeating_the_same_request_id_sends_the_model_once(monkeypatch):
    """같은 `request_id`의 재전달은 모델을 **한 번만** 부른다.

    검사 이유(실패 시 사용자 영향): 버튼 더블클릭이나 새로고침 뒤 재전송이 실제 생성
    호출을 두 번 만들면 응답이 두 벌 저장되고, 사용자는 같은 경기의 실행 두 개를 본다.

    실제 핸들러 `create_bundle_preview_run`을 호출한다. 생성 서비스는 호출 횟수를 세는
    대역이고, 저장은 실행 행을 기억하는 세션 대역이다.
    """
    from app.api.v1 import preview_admin
    from app.preview import preview_test_requests as requests
    from app.preview.access import PreviewPrincipal

    generated: list = []
    run_id = uuid.uuid4()

    class _Transport:
        mode = None

    class _Outcome:
        def __init__(self):
            self.run_id = run_id
            self.mode = type("M", (), {"value": "live"})()
            self.status = type("S", (), {"value": "succeeded"})()
            self.quality = type("Q", (), {"value": "ready"})()
            self.bundle_id = "bundle-1"
            self.bundle_hash = "hash-1"
            self.bundle_artifact_id = "artifact-1"
            self.section_result_ids = {"section_ai_forecast": "result-1"}
            self.section_quality = {"section_ai_forecast": "ready"}
            self.section_unavailable = {}
            self.discovery_status = {}
            self.external_calls = 2
            self.budget = {}
            self.unavailable_reason = None

    session = _StoringSession()

    def _generate(**kwargs):
        generated.append(kwargs)
        session.runs.append(
            _StoredRun(
                run_id=run_id, fixture_id=kwargs["fixture_id"], label=kwargs.get("label")
            )
        )
        return _Outcome()

    monkeypatch.setattr(
        "app.api.v1.preview_admin._model_transport", lambda mode: _Transport()
    )
    monkeypatch.setattr("app.api.v1.preview_admin._fixture_reader", lambda: None)
    monkeypatch.setattr(
        "app.api.v1.preview_admin._refuse_conflicting_fixture_identifiers",
        lambda payload, reader=None: None,
    )
    monkeypatch.setattr("app.services.match_preview.generate_match_preview", _generate)
    monkeypatch.setattr(
        "app.preview.store.load_information_bundle",
        lambda s, rid: {"available": True, "artifact_id": "artifact-1", "summary": {}},
    )
    monkeypatch.setattr("app.preview.store.list_section_results", lambda s, rid: [])
    monkeypatch.setattr(
        "app.preview.store.run_send_ledger_summary",
        lambda s, rid: {"charged_requests": 2},
    )

    principal = PreviewPrincipal(user_id=7, email="admin@example.test", role="ADMIN")
    payload = preview_admin.BundlePreviewRunRequest(
        fixture_id=FIXTURE_IN_SCOPE, mode="live", request_id=uuid.uuid4()
    )

    first = preview_admin.create_bundle_preview_run(payload, session=session, principal=principal)
    # 응답이 유실된 상황을 흉내 낸다: 같은 본문을 그대로 다시 보낸다.
    second = preview_admin.create_bundle_preview_run(payload, session=session, principal=principal)

    # 모델 생성은 정확히 한 번, 두 응답은 같은 실행을 가리키고, 재전달임을 알린다.
    assert len(generated) == 1
    assert first.run_id == second.run_id == run_id
    assert second.note == requests.REPLAY_NOTE


def test_a_new_request_id_creates_a_new_run(monkeypatch):
    """새 UUID(명시적 재생성)는 **새 실행**을 만든다.

    검사 이유(실패 시 사용자 영향): 재생성을 눌렀는데 이전 실행이 돌아오면 사용자는
    새로 만들 수단을 잃는다.
    """
    from app.api.v1 import preview_admin
    from app.preview.access import PreviewPrincipal

    generated: list = []
    session = _StoringSession()

    class _Transport:
        mode = None

    def _generate(**kwargs):
        new_id = uuid.uuid4()
        generated.append(kwargs)
        session.runs.append(
            _StoredRun(
                run_id=new_id, fixture_id=kwargs["fixture_id"], label=kwargs.get("label")
            )
        )

        class _Outcome:
            run_id = new_id
            mode = type("M", (), {"value": "live"})()
            status = type("S", (), {"value": "succeeded"})()
            quality = type("Q", (), {"value": "ready"})()
            bundle_id = None
            bundle_hash = None
            bundle_artifact_id = None
            section_result_ids: dict = {}
            section_quality: dict = {}
            section_unavailable: dict = {}
            discovery_status: dict = {}
            external_calls = 1
            budget: dict = {}
            unavailable_reason = None

        return _Outcome()

    monkeypatch.setattr(
        "app.api.v1.preview_admin._model_transport", lambda mode: _Transport()
    )
    monkeypatch.setattr("app.api.v1.preview_admin._fixture_reader", lambda: None)
    monkeypatch.setattr(
        "app.api.v1.preview_admin._refuse_conflicting_fixture_identifiers",
        lambda payload, reader=None: None,
    )
    monkeypatch.setattr("app.services.match_preview.generate_match_preview", _generate)

    principal = PreviewPrincipal(user_id=7, email="admin@example.test", role="ADMIN")
    first = preview_admin.create_bundle_preview_run(
        preview_admin.BundlePreviewRunRequest(
            fixture_id=FIXTURE_IN_SCOPE, mode="live", request_id=uuid.uuid4()
        ),
        session=session,
        principal=principal,
    )
    second = preview_admin.create_bundle_preview_run(
        preview_admin.BundlePreviewRunRequest(
            fixture_id=FIXTURE_IN_SCOPE, mode="live", request_id=uuid.uuid4()
        ),
        session=session,
        principal=principal,
    )

    assert len(generated) == 2
    assert first.run_id != second.run_id


def test_reusing_a_request_id_for_another_fixture_is_409(monkeypatch):
    """같은 `request_id`를 다른 경기에 다시 쓰면 409로 거부한다.

    검사 이유(실패 시 사용자 영향): 그대로 두면 경기 A의 실행 응답이 경기 B의 생성
    요청 응답으로 돌아가, 화면이 다른 경기의 문서를 B의 결과로 표시한다.
    """
    from fastapi import HTTPException

    from app.api.v1 import preview_admin
    from app.preview.access import PreviewPrincipal

    session = _StoringSession()
    request_id = uuid.uuid4()
    session.runs.append(
        _StoredRun(
            run_id=uuid.uuid4(),
            fixture_id=1557470,
            label=f"정보 원문 프리뷰 · live · request={request_id}",
        )
    )
    principal = PreviewPrincipal(user_id=7, email="admin@example.test", role="ADMIN")

    with pytest.raises(HTTPException) as excinfo:
        preview_admin.create_bundle_preview_run(
            preview_admin.BundlePreviewRunRequest(
                fixture_id=FIXTURE_IN_SCOPE, mode="live", request_id=request_id
            ),
            session=session,
            principal=principal,
        )

    assert excinfo.value.status_code == 409


def _create_management_run_table(engine):
    """합성 로컬 테스트 DB에 수집 실행 표를 만든다.

    공유 테스트 DB의 `public` 스키마는 테스트마다 새로 만들어지며 원래 앱의 전체 표를
    만들지 않는다. 이 검사가 쓰는 표 하나만 모델 정의로 만든다(운영 DB 아님).
    """
    from app.models.management import ManagementRun

    from sqlalchemy import text

    # 이 엔진의 search_path는 `preview_dev`다. 스키마를 적지 않으면 그 스키마에 만들어진다
    # (`management_run`도 같은 규칙으로 떨어진다). 테스트마다 스키마가 새로 만들어지므로
    # 남는 객체가 없다.
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS app_user ("
                " id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                " email text NOT NULL UNIQUE, password_hash text NOT NULL,"
                " role text NOT NULL DEFAULT 'USER', nickname text,"
                " is_active boolean NOT NULL DEFAULT true,"
                " email_verified boolean NOT NULL DEFAULT false,"
                " last_login_at timestamptz,"
                " created_at timestamptz NOT NULL DEFAULT now(),"
                " updated_at timestamptz NOT NULL DEFAULT now())"
            )
        )
    ManagementRun.__table__.create(bind=engine, checkfirst=True)


def test_test_run_list_does_not_delete_or_recover_anything(engine, session_factory):
    """시험 실행 목록 조회는 **아무것도 지우거나 복구하지 않는다**.

    검사 이유(실패 시 사용자 영향): 기존 관리 목록(`run_list`)은 7일 지난 종료 실행을
    지우고 중단 실행을 복구한다. 시험 UI가 그 함수를 쓰면 화면을 열어 보는 것만으로
    다른 실행의 기록이 사라진다.

    합성 로컬 테스트 DB(`preview_mp01_test`)에 실행 행 두 건을 넣고 목록을 읽는다.
    오래된 종료 실행이 그대로 남아 있는지, 진행 중 실행의 상태가 바뀌지 않았는지 본다.
    """
    from datetime import datetime, timedelta, timezone

    from app.models.management import ManagementRun
    from app.services import preview_test

    _create_management_run_table(engine)
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=30)

    def _payload(run_id, status, created, *, scope=True):
        value = {
            "id": run_id,
            "mode": "refresh",
            "status": status,
            "created_at": created.isoformat(),
            "started_at": created.isoformat(),
            "finished_at": None,
            "cancel_requested_at": None,
            "actor": "시험",
            "parent_run_id": None,
            "items": [],
            "logs": [],
            "progress": 0,
            "stage": "실행 준비",
            "log_statistics": {},
            "counts_kind": "processing_units",
        }
        if scope:
            value["test_scope"] = {
                "fixture_from": now.isoformat(),
                "fixture_to": now.isoformat(),
                "preview_fixture_ids": [1557474, 1557470],
                "run_id": run_id,
                "generate_after_collection": False,
            }
        return value

    with session_factory() as session:
        session.add(
            ManagementRun(
                id="old-finished-run",
                status="succeeded",
                payload=_payload("old-finished-run", "succeeded", old),
                created_at=old,
                heartbeat_at=now,
            )
        )
        session.add(
            ManagementRun(
                id="stale-running-run",
                status="running",
                payload=_payload("stale-running-run", "running", old),
                created_at=old,
                heartbeat_at=old,
            )
        )
        session.add(
            ManagementRun(
                id="unrelated-run",
                status="succeeded",
                payload=_payload("unrelated-run", "succeeded", now, scope=False),
                created_at=now,
                heartbeat_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        listed = preview_test.list_test_runs(session)

    ids = [item["id"] for item in listed["items"]]
    # 시험 범위가 있는 실행만 나온다(일반 수집 실행은 섞이지 않는다).
    assert "unrelated-run" not in ids
    # 종료 실행만 items에 있고, 진행 중 실행은 active에 따로 있다(중복 표시 없음).
    assert set(ids) == {"old-finished-run"}
    assert listed["active"]["id"] == "stale-running-run"

    with session_factory() as session:
        rows = {row.id: row for row in session.query(ManagementRun).filter(
            ManagementRun.id.in_(ids + ["stale-running-run"])
        )}
        # 오래된 종료 실행은 삭제되지 않았고, 미완료 실행은 복구되지 않았다.
        assert set(rows) == {"old-finished-run", "stale-running-run"}
        assert rows["stale-running-run"].status == "running"
        assert rows["old-finished-run"].status == "succeeded"
        # 저장된 범위가 응답에 그대로 남는다(생성 0회 의미 보존).
        assert rows["old-finished-run"].payload["test_scope"]["generate_after_collection"] is False


def test_test_run_detail_returns_404_for_a_non_test_run(engine, session_factory):
    """다른 종류의 실행 ID로 시험 실행을 조회하면 404다(내용을 돌려주지 않는다)."""
    from datetime import datetime, timezone

    from app.models.management import ManagementRun
    from app.services import preview_test
    from app.services.management import ManagementError

    _create_management_run_table(engine)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        session.add(
            ManagementRun(
                id="regular-run",
                status="succeeded",
                payload={
                    "id": "regular-run",
                    "status": "succeeded",
                    "created_at": now.isoformat(),
                    "items": [],
                    "logs": [],
                    "log_statistics": {},
                    "counts_kind": "processing_units",
                },
                created_at=now,
                heartbeat_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        with pytest.raises(ManagementError) as excinfo:
            preview_test.test_run(session, "regular-run")

    assert excinfo.value.status == 404


def test_streamer_is_rejected_on_the_collection_test_routes(client, make_user):
    """STREAMER는 수집 시험 조회·실행 경로에서 **403**이다.

    검사 이유(실패 시 사용자 영향): 이 경로는 실제 공급자 호출과 공개 자료 갱신을
    일으킨다. 스트리머 역할로 실행되면 권한 밖에서 경기 자료가 바뀐다. 기존 일반
    관리 API의 STREAMER 정책은 이 시험 경로와 별개로 유지된다.

    실제 앱·실제 JWT 인증을 쓴다(경계를 우회하지 않는다). 핸들러 본문까지 가지 않도록
    인증 실패만 확인한다.
    """
    user = make_user(role="STREAMER")
    login = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    for path in (
        "/api/v1/admin/management/preview-test/candidates",
        "/api/v1/admin/management/preview-test/plan?fixture_ids=1557474&fixture_ids=1557470",
        "/api/v1/admin/management/preview-test/runs",
    ):
        response = client.get(path, headers=headers)
        assert response.status_code == 403, (path, response.text)


def test_anonymous_is_rejected_on_the_collection_test_routes(client):
    """비인증 요청은 401이다."""
    response = client.get("/api/v1/admin/management/preview-test/candidates")
    assert response.status_code == 401, response.text


def test_admin_gets_the_documented_candidate_contract(client, make_user):
    """ADMIN은 후보 조회에서 **B가 읽을 키 모양**을 그대로 받는다.

    검사 이유(실패 시 사용자 영향): 응답 키가 없거나 이름이 다르면 프론트가 후보 목록을
    표시하지 못하고, 기본 두 경기 선택이 비어 실행 버튼이 눌리지 않는다.

    실제 라우터·인증·응답 직렬화를 지난다. 후보 판정만 후보 없음으로 바꿔(공유 테스트
    DB에 경기·대상 표를 만들지 않는다) 응답 계약을 확인한다.
    """
    from app.services import preview_test

    user = make_user(role="ADMIN")
    login = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    original = preview_test.eligible_rows
    preview_test.eligible_rows = lambda *a, **k: []
    try:
        response = client.get(
            "/api/v1/admin/management/preview-test/candidates", headers=headers
        )
    finally:
        preview_test.eligible_rows = original

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"as_of", "timezone", "candidates", "reason"}
    assert body["timezone"] == "Asia/Seoul"
    assert body["candidates"] == []
    # 후보가 없으면 실행을 막는 사유가 문장으로 온다(빈 목록만 오지 않는다).
    assert body["reason"]


def test_test_run_list_uses_the_existing_envelope_and_reports_the_active_run(engine, session_factory):
    """목록 envelope는 기존 관리 목록과 같은 `active`/`items`/`limit`이다.

    검사 이유(실패 시 사용자 영향): envelope가 다르면 재사용하는 화면·클라이언트가
    진행 중 실행을 찾지 못해 "수집 중" 표시가 사라진다. 기존 목록 의미대로 진행 중
    실행은 `active`에만 두고 `items`에는 넣지 않아야 같은 실행이 두 번 표시되지 않는다.
    진행 중 판정도 저장된 상태만 읽어야 하며, 조회가 상태를 바꾸면 안 된다.
    """
    from datetime import datetime, timezone

    from app.models.management import ManagementRun
    from app.services import preview_test

    _create_management_run_table(engine)
    now = datetime.now(timezone.utc)

    def _payload(run_id, status):
        return {
            "id": run_id,
            "mode": "refresh",
            "status": status,
            "created_at": now.isoformat(),
            "started_at": now.isoformat(),
            "finished_at": None,
            "cancel_requested_at": None,
            "actor": "시험",
            "parent_run_id": None,
            "items": [],
            "logs": [],
            "progress": 0,
            "stage": "실행 준비",
            "log_statistics": {},
            "counts_kind": "processing_units",
            "test_scope": {
                "fixture_from": now.isoformat(),
                "fixture_to": now.isoformat(),
                "preview_fixture_ids": [1557474, 1557470],
                "run_id": run_id,
                "generate_after_collection": False,
            },
        }

    with session_factory() as session:
        session.add(
            ManagementRun(
                id="finished-test-run",
                status="succeeded",
                payload=_payload("finished-test-run", "succeeded"),
                created_at=now,
                heartbeat_at=now,
            )
        )
        session.add(
            ManagementRun(
                id="active-test-run",
                status="running",
                payload=_payload("active-test-run", "running"),
                created_at=now,
                heartbeat_at=now,
            )
        )
        session.commit()

    with session_factory() as session:
        listed = preview_test.list_test_runs(session)

    assert set(listed) == {"active", "items", "limit"}
    assert listed["limit"] == preview_test.RUN_LIST_LIMIT
    assert listed["active"] is not None
    assert listed["active"]["id"] == "active-test-run"
    # active와 items는 서로 다른 집합이다(기존 목록 의미). 진행 중 실행은 active에만 있다.
    assert {item["id"] for item in listed["items"]} == {"finished-test-run"}

    with session_factory() as session:
        # 조회가 진행 중 실행의 상태를 바꾸지 않았다(복구·중단 표시 없음).
        assert session.get(ManagementRun, "active-test-run").status == "running"
