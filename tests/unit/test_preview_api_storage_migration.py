"""PA-IMPL API·저장소 일관성 및 legacy 가드 단위 검사(합성 대역).

이 검사는 운영 DB나 실제 모델에 연결하지 않는 합성 대역으로 아래 수용 기준을 확인한다.
- 공개 `/recommendations`와 `/fixtures/{id}/document`가 동일한 `preview_dev` 승인 선택과
  완전성 기준을 따른다(1557474 3섹션 부분 문서, 미승인, 킥오프 이후 저장, 저장소 503 포함).
- `home_preview_document`가 구 MP-10(`mp10-*`)·모의·카탈로그 실행을 제외하면서
  기존 `mp11-bundle-pipeline-*`, `section`, `test-cfg` 실행은 보존한다.
- 관리자 구 실행 엔드포인트(`/resume`, `/module-reruns`, `/synthesis-runs`)가
  새 bundle/section 실행을 legacy 상태조회 404 대신 명시적 409로 거부하고 MP-10만 통과시킨다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import db
from app.api.v1 import home_preview as home_preview_api
from app.api.v1 import preview_admin as preview_admin_api
from app.preview import db as preview_db
from app.preview.access import PreviewPrincipal
from app.schemas.home_preview import structure
from app.services import home_preview, home_preview_document

BASE = datetime(2026, 11, 18, 0, 0, tzinfo=timezone.utc)
KICKOFF = datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc)
RUN_ID = uuid.UUID("4f90e50b-ce55-4beb-8a17-20ef6e9192fb")


def _section_obj(
    workflow_id: str,
    *,
    run_id: uuid.UUID = RUN_ID,
    body: str = "본문",
    workflow_version: str | None = None,
    created_at: datetime = BASE,
    mode: str = "live",
    output_contract_version: str | None = None,
    unavailable_reason: str | None = None,
    sources: list[dict] | None = None,
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_version=workflow_version or f"{workflow_id}@v1",
        version=1,
        title=workflow_id,
        body=body,
        sources=list(sources or []),
        quality="ready",
        mode=mode,
        output_contract_version=output_contract_version,
        unavailable_reason=unavailable_reason,
        created_at=created_at,
        result_ids=[],
    )


def _approval_obj(workflow_id: str, workflow_version: str | None = None):
    return SimpleNamespace(
        workflow_id=workflow_id,
        workflow_version=workflow_version or f"{workflow_id}@v1",
        reviewed_run_id=None,
        section_result_id=None,
        active=True,
    )


def _run_obj(
    *,
    run_id: uuid.UUID = RUN_ID,
    operation_kind: str = "preview",
    config_version: str = "mp11-bundle-pipeline-3",
    mode: str = "live",
    status: str = "succeeded",
    requested_at: datetime = BASE,
):
    return SimpleNamespace(
        id=run_id,
        fixture_id=1557474,
        operation_kind=operation_kind,
        config_version=config_version,
        mode=mode,
        status=status,
        requested_at=requested_at,
        home_team_id=13,
        away_team_id=4,
        fixture_label="맨체스터 시티 vs 풀럼",
    )


class _StoredStub:
    """`home_preview_document`가 읽는 최소 `preview_dev` 세션 대역."""

    def __init__(self, runs, sections_by_run, approvals, *, raise_on_query: bool = False):
        self._runs = list(runs)
        self._sections_by_run = sections_by_run
        self._approvals = list(approvals)
        self._raise_on_query = raise_on_query

    def scalars(self, statement):
        if self._raise_on_query:
            raise OperationalError("SELECT 1", {}, Exception("db down"))
        text = str(statement)
        if "preview_runs" in text:
            return list(self._runs)
        if "preview_section_approvals" in text:
            return list(self._approvals)
        if "preview_section_results" in text:
            run_ids = list(self._sections_by_run)
            if len(run_ids) == 1:
                return list(self._sections_by_run[run_ids[0]])
            compiled = statement.compile()
            for param in compiled.params.values():
                if param in self._sections_by_run:
                    return list(self._sections_by_run[param])
                for key in self._sections_by_run:
                    if str(key) == str(param):
                        return list(self._sections_by_run[key])
            return []
        return []


def _recommendation_fixture_row():
    fixture = SimpleNamespace(
        id=101,
        external_id=1557474,
        kickoff_at=KICKOFF,
        updated_at=BASE,
        status_short="NS",
        round="Regular Season - 12",
        home_team_id=13,
        away_team_id=4,
        league_id=39,
        season_year=2026,
        goals_home=None,
        goals_away=None,
    )
    league = SimpleNamespace(
        id=1,
        external_id=39,
        name="Premier League",
        type="League",
        country_name="England",
        is_active=True,
    )
    home = SimpleNamespace(id=13, external_id=50, name="Manchester City")
    away = SimpleNamespace(id=4, external_id=36, name="Fulham")
    translations = {13: "맨체스터 시티", 4: "풀럼"}
    return (fixture, league, home, away, 1, translations)


def _public_stub():
    return SimpleNamespace(scalars=lambda *_a, **_k: [])


def test_recommendations_and_document_agree_on_1557474_three_section_partial(monkeypatch):
    """1557474 3섹션 저장본은 /document complete=False, /recommendations preview.state='partial'이어야 한다.

    실패 시 사용자 영향: /document는 승인 본문이 있는데 /recommendations가 unavailable을
    표시하거나, 반대로 선수 섹션이 없는데 ready(완료)로 오인시킨다.
    """
    sections = [
        _section_obj("section_outlook"),
        _section_obj("section_odds"),
        _section_obj("section_ai_forecast"),
    ]
    approvals = [
        _approval_obj("section_outlook"),
        _approval_obj("section_odds"),
        _approval_obj("section_ai_forecast"),
    ]
    stored = _StoredStub([_run_obj()], {RUN_ID: sections}, approvals)

    monkeypatch.setattr(home_preview, "eligible_rows", lambda *_a, **_k: [_recommendation_fixture_row()])
    monkeypatch.setattr(home_preview_document.store_module, "load_composition", lambda *_a, **_k: {"available": False})
    data_as_of = BASE - timedelta(hours=2)
    monkeypatch.setattr(
        home_preview_document.store_module,
        "load_information_bundle",
        lambda *_a, **_k: {"available": True, "bundle": {"as_of": data_as_of.isoformat()}, "summary": None},
    )
    monkeypatch.setattr(home_preview_document, "_id_context", lambda *_a, **_k: (None, None))

    doc = home_preview_document.read_document(stored, 1557474, now=BASE + timedelta(hours=1))
    rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=BASE + timedelta(hours=1),
        stored_session=stored,
    )
    structure("recommendations", rec)

    assert doc["status"] == "available"
    assert doc["run_id"] == str(RUN_ID)
    assert doc["complete"] is False
    preview = rec["items"][0]["preview"]
    assert preview == {
        "state": "partial",
        "served": "current",
        "generated_at": BASE.isoformat(),
        "as_of": data_as_of.isoformat(),
    }


def test_recommendations_and_document_agree_on_ready_and_unapproved(monkeypatch):
    """필수 섹션 모두 승인되면 ready, 승인 행이 없으면 unavailable(가리지 않음)이어야 한다.

    실패 시 사용자 영향: 미승인 본문이 추천 카드에 ready/pending으로 노출된다.
    """
    monkeypatch.setattr(home_preview, "eligible_rows", lambda *_a, **_k: [_recommendation_fixture_row()])
    monkeypatch.setattr(home_preview_document.store_module, "load_composition", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(home_preview_document, "_id_context", lambda *_a, **_k: (None, None))

    full_sections = [
        _section_obj("section_players"),
        _section_obj("section_ai_forecast"),
    ]
    full_approvals = [
        _approval_obj("section_players"),
        _approval_obj("section_ai_forecast"),
    ]
    ready_stored = _StoredStub([_run_obj()], {RUN_ID: full_sections}, full_approvals)
    ready_doc = home_preview_document.read_document(ready_stored, 1557474, now=BASE)
    ready_rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=BASE,
        stored_session=ready_stored,
    )
    structure("recommendations", ready_rec)
    assert ready_doc["complete"] is True
    assert ready_rec["items"][0]["preview"]["state"] == "ready"

    unapproved_stored = _StoredStub([_run_obj()], {RUN_ID: full_sections}, [])
    unapproved_doc = home_preview_document.read_document(unapproved_stored, 1557474, now=BASE)
    unapproved_rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=BASE,
        stored_session=unapproved_stored,
    )
    structure("recommendations", unapproved_rec)
    assert unapproved_doc["status"] == "none"
    assert unapproved_doc["reason"] == "no_approved_version"
    assert unapproved_rec["items"][0]["preview"] == {
        "state": "unavailable",
        "served": None,
        "generated_at": None,
        "as_of": None,
    }


def test_recommendations_does_not_fabricate_generated_at_after_kickoff(monkeypatch):
    """킥오프 이후 저장되고 자료 기준 근거가 없으면 generated_at과 as_of를 저장시각으로 지어내지 않는다.

    실패 시 사용자 영향: 저장시각을 자료 기준시각으로 오해하거나 가짜 generated_at으로 스키마 오류가 난다.
    """
    post_kickoff = KICKOFF + timedelta(minutes=15)
    sections = [_section_obj("section_players", created_at=post_kickoff), _section_obj("section_ai_forecast", created_at=post_kickoff)]
    approvals = [_approval_obj("section_players"), _approval_obj("section_ai_forecast")]
    stored = _StoredStub([_run_obj()], {RUN_ID: sections}, approvals)

    monkeypatch.setattr(home_preview, "eligible_rows", lambda *_a, **_k: [_recommendation_fixture_row()])
    monkeypatch.setattr(home_preview_document.store_module, "load_composition", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(
        home_preview_document.store_module,
        "load_information_bundle",
        lambda *_a, **_k: {"available": False, "bundle": None, "summary": None},
    )

    rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=post_kickoff,
        stored_session=stored,
    )
    structure("recommendations", rec)
    assert rec["items"][0]["preview"] == {
        "state": "ready",
        "served": "current",
        "generated_at": None,
        "as_of": None,
    }


def test_recommendations_as_of_aggregates_selected_sources_and_returns_none_when_unrecorded(monkeypatch):
    """다중 실행 구성본은 선택된 표시 섹션의 원천 자료 시각(max)만 집계하고 미선택 실행은 무시한다."""
    run_main = RUN_ID
    run_other = uuid.UUID("11111111-1111-1111-1111-111111111111")
    run_ignored = uuid.UUID("22222222-2222-2222-2222-222222222222")

    saved_at = BASE + timedelta(hours=5)
    t_bundle_main = BASE - timedelta(hours=3)
    t_source_other = BASE - timedelta(hours=1)
    t_bundle_ignored = BASE + timedelta(hours=4)

    sec_players = _section_obj("section_players", run_id=run_main, created_at=saved_at)
    sec_ai_other = _section_obj(
        "section_ai_forecast",
        run_id=run_other,
        created_at=saved_at - timedelta(minutes=30),
        sources=[{"label": "공식 배당", "retrieved_at": t_source_other.isoformat()}],
    )
    sec_ai_unused = _section_obj("section_ai_forecast", run_id=run_ignored, created_at=saved_at)
    approvals = [_approval_obj("section_players"), _approval_obj("section_ai_forecast")]
    stored = _StoredStub(
        [
            _run_obj(run_id=run_main, requested_at=saved_at),
            _run_obj(run_id=run_ignored, requested_at=BASE - timedelta(hours=1)),
        ],
        {run_main: [sec_players], run_ignored: [sec_ai_unused]},
        approvals,
    )

    monkeypatch.setattr(home_preview, "eligible_rows", lambda *_a, **_k: [_recommendation_fixture_row()])
    monkeypatch.setattr(home_preview_document, "_id_context", lambda *_a, **_k: (None, None))
    monkeypatch.setattr(
        home_preview_document.store_module,
        "load_composition",
        lambda _s, rid: (
            {
                "available": True,
                "composition": {
                    "items": [
                        {"result_id": str(sec_players.id)},
                        {"result_id": str(sec_ai_other.id)},
                    ]
                },
            }
            if str(rid) == str(run_main)
            else {"available": False}
        ),
    )
    monkeypatch.setattr(
        home_preview_document.store_module,
        "get_section_result_any_run",
        lambda _s, rid: sec_ai_other if str(rid) == str(sec_ai_other.id) else None,
    )
    bundles = {
        str(run_main): {"available": True, "bundle": {"as_of": t_bundle_main.isoformat()}, "summary": None},
        str(run_ignored): {"available": True, "bundle": {"as_of": t_bundle_ignored.isoformat()}, "summary": None},
    }
    monkeypatch.setattr(
        home_preview_document.store_module,
        "load_information_bundle",
        lambda _s, rid: bundles.get(str(rid), {"available": False, "bundle": None, "summary": None}),
    )

    rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=saved_at,
        stored_session=stored,
    )
    structure("recommendations", rec)
    assert rec["items"][0]["preview"] == {
        "state": "ready",
        "served": "current",
        "generated_at": saved_at.isoformat(),
        "as_of": t_source_other.isoformat(),
    }

    # 근거 시각이 전혀 없으면 generated_at만 남기고 as_of는 None으로 둔다.
    sec_players_bare = _section_obj("section_players", run_id=run_main, created_at=saved_at)
    sec_ai_bare = _section_obj("section_ai_forecast", run_id=run_main, created_at=saved_at)
    bare_stored = _StoredStub([_run_obj(run_id=run_main, requested_at=saved_at)], {run_main: [sec_players_bare, sec_ai_bare]}, approvals)
    monkeypatch.setattr(home_preview_document.store_module, "load_composition", lambda *_a, **_k: {"available": False})
    monkeypatch.setattr(
        home_preview_document.store_module,
        "load_information_bundle",
        lambda *_a, **_k: {"available": False, "bundle": None, "summary": None},
    )
    bare_rec = home_preview.recommendations(
        _public_stub(),
        requested_date=KICKOFF.astimezone(home_preview.KST).date(),
        now=saved_at,
        stored_session=bare_stored,
    )
    structure("recommendations", bare_rec)
    assert bare_rec["items"][0]["preview"] == {
        "state": "ready",
        "served": "current",
        "generated_at": saved_at.isoformat(),
        "as_of": None,
    }


def test_recommendations_route_returns_503_on_stored_db_failure(monkeypatch):
    """`preview_dev` 읽기 실패 시 503을 반환해 '문서 없음(unavailable)'으로 숨기지 않는다.

    실패 시 사용자 영향: DB 연결 장애를 '프리뷰 없음'으로 오해하게 된다.
    """
    failing_stored = _StoredStub([], {}, [], raise_on_query=True)
    monkeypatch.setattr(home_preview, "eligible_rows", lambda *_a, **_k: [_recommendation_fixture_row()])

    app = FastAPI()
    app.include_router(home_preview_api.router)
    app.dependency_overrides[db.get_db_session] = _public_stub
    app.dependency_overrides[preview_db.get_db] = lambda: failing_stored

    client = TestClient(app)
    res = client.get(f"/api/v1/home/recommendations?date={KICKOFF.astimezone(home_preview.KST).date().isoformat()}")
    assert res.status_code == 503
    assert res.json()["detail"] == "home_preview_storage_unavailable"


def test_run_eligibility_excludes_mp10_catalog_mock_and_keeps_bundle_section_and_test_cfg():
    """구 MP-10·카탈로그·모의 실행은 제외하고 역사 bundle·section·test-cfg는 허용해야 한다.

    실패 시 사용자 영향: 구 MP-10 실행이 새 canonical 계약 문서를 밀어내거나 반대로 구 bundle이 사라진다.
    """
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="preview", config_version="mp10-pipeline-1")
    ) is False
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="fixture_catalog", config_version="mp04-fixture-catalog-1")
    ) is False
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="preview", config_version="mp11-bundle-pipeline-3", mode="mock")
    ) is False
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="preview", config_version="mp11-bundle-pipeline-2")
    ) is True
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="section", config_version="mp04-section-1")
    ) is True
    assert home_preview_document._is_eligible_document_run(
        _run_obj(operation_kind="preview", config_version="test-cfg")
    ) is True
    assert home_preview_document._is_eligible_document_run(SimpleNamespace(status="succeeded")) is True


def test_legacy_run_endpoints_reject_bundle_and_section_runs_with_409(monkeypatch):
    """새 bundle/section 실행이 legacy /resume, /module-reruns, /synthesis-runs에 들어가면 409로 거부한다.

    실패 시 사용자 영향: 존재하는 bundle 실행에 대해 'preview run not found' 404가 나거나 구 파이프라인이 오동작한다.
    """
    bundle_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    section_id = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    legacy_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

    runs = {
        bundle_id: _run_obj(run_id=bundle_id, operation_kind="preview", config_version="mp11-bundle-pipeline-3"),
        section_id: _run_obj(run_id=section_id, operation_kind="section", config_version="mp11-bundle-pipeline-3"),
        legacy_id: _run_obj(run_id=legacy_id, operation_kind="preview", config_version="mp10-pipeline-1"),
    }

    class _AdminStubSession:
        def get(self, _model, run_uuid):
            return runs.get(run_uuid)

        def commit(self):
            return None

        def rollback(self):
            return None

    def fake_detail(_session, run_uuid):
        run = runs[run_uuid]
        return {"summary": {"run_id": str(run_uuid), "operation_kind": run.operation_kind, "mode": "live"}}

    legacy_calls = []
    from app.preview import pipeline as pipeline_module

    def fake_legacy_outcome(name):
        def _fn(*_args, **_kwargs):
            legacy_calls.append(name)
            return SimpleNamespace(
                run_id=legacy_id,
                admission="approved",
                mode=SimpleNamespace(value="live"),
                status=SimpleNamespace(value="succeeded"),
                quality=SimpleNamespace(value="ready"),
                stage="completed",
                external_calls=1,
                joined_existing=False,
                waiting_reason=None,
                unavailable_reason=None,
                budget={},
                workflow_versions={},
                section_result_ids={},
                resume_of_run_id=None,
            )

        return _fn

    monkeypatch.setattr(preview_admin_api, "_detail_or_404", fake_detail)
    monkeypatch.setattr(preview_admin_api, "_fixture_reader", lambda: None)
    monkeypatch.setattr(preview_admin_api, "_pipeline_transport", lambda *_a, **_k: None)
    monkeypatch.setattr(pipeline_module, "resume_preview_run", fake_legacy_outcome("resume"))
    monkeypatch.setattr(pipeline_module, "rerun_module", fake_legacy_outcome("module"))
    monkeypatch.setattr(pipeline_module, "resynthesize_preview", fake_legacy_outcome("synthesis"))

    app = FastAPI()
    app.include_router(preview_admin_api.router)
    app.dependency_overrides[preview_admin_api.get_db] = _AdminStubSession
    app.dependency_overrides[preview_admin_api.require_preview_admin] = lambda: PreviewPrincipal(
        user_id=1, email="admin@example.com", role="ADMIN"
    )

    client = TestClient(app)

    for target_id in (bundle_id, section_id):
        r1 = client.post(f"/api/v1/admin/preview/runs/{target_id}/resume")
        r2 = client.post(f"/api/v1/admin/preview/runs/{target_id}/module-reruns", json={"module_id": "R1", "mode": "live"})
        r3 = client.post(
            f"/api/v1/admin/preview/runs/{target_id}/synthesis-runs",
            json={"selected_result_ids": [str(uuid.uuid4())], "mode": "live"},
        )
        for resp in (r1, r2, r3):
            assert resp.status_code == 409
            assert "/bundle-runs" in resp.json()["detail"]

    assert legacy_calls == []

    # 구 MP-10 실행은 기존 호환 경로로 계속 위임된다.
    ok_resume = client.post(f"/api/v1/admin/preview/runs/{legacy_id}/resume")
    assert ok_resume.status_code == 200
    assert legacy_calls == ["resume"]
