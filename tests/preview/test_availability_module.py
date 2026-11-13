"""MP-06 R2 부상·결장 영향 조사 검사.

계획 §6 MP-06의 수용 기준:

- `test_questionable_not_confirmed_absence`: 출전 불확실 표기를 결장 확정으로 바꾸지 않는다.
- `test_empty_list_not_no_injuries`: 빈 부상 응답을 '부상자 0명'으로 쓰지 않는다.
- `test_conflicting_reports_preserved`: API와 검색 보도가 다르면 둘 다 보존한다.
- `test_injury_impact_has_basis`: 영향 해석은 근거가 연결된 것만 채택한다.
- `test_api_only_availability_result`: 검색 출처가 없어도 API 사실로 본문을 만든다.

그리고 사용자 테스트 단위인 **섹션 워크플로우 전체**(prepare_data → research →
compose_body → finalize)를 실제 LangGraph 실행기로 돌려, 독자용 본문과 근거가
저장되는지 확인한다.

실제 모델·API 호출은 하지 않는다. `provider.RecordedTransport`로 준비한 응답만 쓰며,
그 기록은 live 성공으로 계산되지 않는다(`mode=mock`). D0 준비 노드는 실제 D0 구현이
아니라 이 검사용 고정 노드이며, live 검증은 MP-05 통합 뒤에 따로 한다.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.preview import provider, runner, store
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    ModuleInput,
    OperationKind,
    QualityStatus,
    RunMode,
    RunStatus,
)
from app.preview.modules import availability as r2
from app.preview.retry import BudgetLimits, RunBudget
from app.preview.sources import api_football as api

FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
# 예산·기한은 실제 시계로 판정되므로 실행 시작 시각도 실제 현재 시각을 쓴다.
RUN_NOW = datetime.now(timezone.utc)
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "availability.json"

# 이 파일은 자기 전용 루프백 테스트 DB만 쓴다(공유 reset 충돌 방지).
# 공통 conftest의 DB를 바꾸지 않고, 이 모듈이 자기 엔진·세션을 직접 만든다.
MP06_TEST_DATABASE_URL = (
    "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_mp06_test"
)


@pytest.fixture(scope="session")
def mp06_engine():
    """MP-06 전용 테스트 DB 엔진. 연결 전에 대상을 검사한다."""
    from sqlalchemy import create_engine

    from app.core.db_target import normalize_driver
    from tests.preview._dbguard import assert_safe_test_database

    assert_safe_test_database(MP06_TEST_DATABASE_URL)
    engine = create_engine(normalize_driver(MP06_TEST_DATABASE_URL), future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(mp06_engine):
    """테스트마다 `preview_dev` 스키마를 새로 만든다(마이그레이션 대신 메타데이터)."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from app.auth import models as _auth_models  # noqa: F401  (모델 등록)
    from app.preview.db import SCHEMA, Base
    from app.preview import models as _preview_models  # noqa: F401  (모델 등록)

    # 스키마 생성과 테이블 생성 사이에 다른 연결이 끼어들지 않도록 한 트랜잭션에서 한다.
    with mp06_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
        Base.metadata.create_all(bind=conn)
    factory = sessionmaker(bind=mp06_engine, autoflush=False, expire_on_commit=False)
    yield factory
    with mp06_engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))


@pytest.fixture()
def recorded() -> Mapping[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 도우미
# --------------------------------------------------------------------------


def _fixture_identity(recorded: Mapping[str, Any]) -> FixtureIdentity:
    return FixtureIdentity.from_dict(dict(recorded["fixture"]))


def _module_input(recorded: Mapping[str, Any]) -> ModuleInput:
    identity = _fixture_identity(recorded)
    from app.preview.contracts import MODULE_INPUT_VERSION, compute_input_hash

    return ModuleInput(
        module_id=r2.AVAILABILITY_MODULE_ID,
        fixture=identity,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash({"fixture": identity.to_dict()}),
        prompt_version=r2.PROMPT_VERSION,
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=r2.IMPLEMENTATION_VERSION,
    )


def _context(run_id: uuid.UUID, *, mode: RunMode = RunMode.MOCK) -> ExecutionContext:
    return ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=mode,
        actor_id=4,
        config_version="mp06-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _body(text: str, grounding: Mapping[str, Any] | None = None) -> dict[str, Any]:
    candidate: dict[str, Any] = {
        "content": {"role": "model", "parts": [{"text": text}]},
        "finishReason": "STOP",
    }
    if grounding is not None:
        candidate["groundingMetadata"] = dict(grounding)
    return {"candidates": [candidate]}


def _ok(text: str, grounding: Mapping[str, Any] | None = None) -> provider.TransportResult:
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response=_body(text, grounding),
        usage={"input_tokens": 1200, "output_tokens": 380, "search_queries": None},
    )


def _transport(
    recorded: Mapping[str, Any], key: str, *, grounding: bool = True
) -> provider.RecordedTransport:
    payload = json.dumps(recorded[key], ensure_ascii=False)
    return provider.RecordedTransport(
        script=[_ok(payload, recorded["grounding"] if grounding else None)]
    )


def _store_run(session, context: ExecutionContext) -> None:
    store.store_run(session, context, label="MP-06 R2 검사", status=RunStatus.RUNNING)


def _run_research(
    session,
    recorded: Mapping[str, Any],
    *,
    key: str,
    material_key: str = "material_api_session",
    grounding: bool = True,
    mode: RunMode = RunMode.MOCK,
    stored_loader=None,
) -> r2.AvailabilityOutcome:
    run_id = uuid.uuid4()
    context = _context(run_id, mode=mode)
    _store_run(session, context)
    transport = _transport(recorded, key, grounding=grounding)
    return r2.research_availability(
        session,
        module_input=_module_input(recorded),
        context=context,
        transport=transport,
        budget=RunBudget.for_run(now=RUN_NOW),
        material=recorded[material_key],
        stored_loader=stored_loader,
        now=FIXED_NOW,
    )


def _section_prepare(recorded: Mapping[str, Any]) -> runner.NodeImplementation:
    """검사용 D0 준비 노드. 실제 D0 구현이 아니라 고정 자료를 넘기는 노드다."""

    def run(ctx: runner.SectionNodeContext, state: runner.SectionState) -> runner.NodeOutcome:
        return runner.NodeOutcome(
            payload=dict(recorded["material_api_session"]),
            diagnostics=("검사용 D0 자료입니다. 실제 API 수집이 아닙니다.",),
        )

    return runner.NodeImplementation(
        module_id="D0",
        implementation_version="mp06-test-d0-1",
        prompt_version=None,
        mode=RunMode.MOCK,
        run=run,
    )


# --------------------------------------------------------------------------
# accept criteria 1: 출전 불확실은 결장 확정이 아니다
# --------------------------------------------------------------------------


def test_questionable_not_confirmed_absence(session_factory, recorded):
    """`Questionable` 표기를 결장 확정으로 승격하지 않고 그대로 보존한다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_doubtful")
        session.commit()

    assert outcome.unavailable_reason is None
    research = outcome.research
    assert research is not None
    doubtful = next(update for update in research.player_updates if update.player_id == 7101)
    assert doubtful.status == r2.STATUS_DOUBTFUL
    assert doubtful.api_status == r2.STATUS_DOUBTFUL
    assert doubtful.conflict is False

    # API 원문 표기와 사유가 사라지지 않는다.
    fact = next(item for item in research.facts if item.player_id == 7101)
    assert fact.type_marker == "Questionable"
    assert fact.reason == "Knock - 75% chance of playing"
    assert fact.uncertainty == "uncertain"
    assert fact.adopted is True

    # API가 확정 결장으로 표기한 다른 선수는 확정으로 남는다(같은 필드에서 섞지 않음).
    confirmed = next(update for update in research.player_updates if update.player_id == 7102)
    assert confirmed.status == r2.STATUS_CONFIRMED_ABSENCE

    # 본문도 '결장 확정'이라고 단정하지 않는다.
    composed = r2.compose_availability_body(outcome.payload)
    body = composed.body
    assert "출전 불확실" in body
    doubtful_line = next(line for line in body.splitlines() if "7101" in line or "Doubtful" in line)
    assert "결장 확정" not in doubtful_line
    assert "확정되지 않았습니다" in doubtful_line


def test_unknown_marker_is_not_promoted(session_factory, recorded):
    """표기가 없는 부상 행은 확정 사실로 채택되지 않는다(이름도 만들지 않는다)."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_doubtful")
        session.commit()

    research = outcome.research
    assert research is not None
    unlabelled = next(item for item in research.facts if item.player_id == 7103)
    assert unlabelled.adopted is False
    assert unlabelled.expected_status == r2.STATUS_UNKNOWN
    # 저장 행이 이름을 주지 않으면 식별자만 쓴다.
    assert unlabelled.player_name is None
    assert unlabelled.display_name == "선수 ID 7103"


# --------------------------------------------------------------------------
# accept criteria 2: 빈 응답은 '부상자 없음'이 아니다
# --------------------------------------------------------------------------


def test_empty_list_not_no_injuries(session_factory, recorded):
    """빈 부상 응답·API 실패는 '부상자 0명'이 아니라 자료 없음으로 남는다."""
    with session_factory() as session:
        outcome = _run_research(
            session,
            recorded,
            key="model_output_empty_search",
            material_key="material_empty_injuries",
            grounding=False,
        )
        session.commit()

    research = outcome.research
    assert research is not None
    assert research.material_state == r2.STATE_EMPTY_RESPONSE
    assert "부상자 없음" not in (research.material_detail or "") or "증거가 아니" in (
        research.material_detail or ""
    )
    # 빈 목록을 사실 0건으로 승격하지 않는다.
    assert research.facts == ()

    coverage = {entry["topic"]: entry for entry in outcome.payload["coverage"]}
    api_entry = coverage["부상·출전 불확실 API"]
    assert api_entry["state"] == "unknown"
    assert "증거가 아니" in api_entry["detail"]

    # 독자용 본문에는 이 진단이 들어가지 않는다. 근거가 없으면 본문도 만들지 않는다.
    composed = r2.compose_availability_body(outcome.payload)
    assert "부상자 없음" not in composed.body
    assert composed.body == ""
    assert composed.quality is QualityStatus.INSUFFICIENT
    # 진단에는 남는다(관리자 화면용).
    assert any("empty_response" in note or "비어" in note for note in outcome.diagnostics)


def test_api_error_is_not_missing_or_zero(session_factory, recorded):
    """호출 실패와 미제공을 구분해 남기고, 어느 쪽도 '없음'으로 합치지 않는다."""
    with session_factory() as session:
        outcome = _run_research(
            session,
            recorded,
            key="model_output_empty_search",
            material_key="material_api_failed",
            grounding=False,
        )
        session.commit()

    research = outcome.research
    assert research is not None
    # 첫 번째 부상 coverage 항목(호출 실패)이 그대로 상태가 된다.
    assert research.material_state == r2.STATE_CALL_ERROR
    assert research.facts == ()
    assert outcome.quality is QualityStatus.INSUFFICIENT
    assert outcome.unavailable_reason is not None


# --------------------------------------------------------------------------
# accept criteria 3: 상충 보도는 숨기지 않고 둘 다 보존한다
# --------------------------------------------------------------------------


def test_conflicting_reports_preserved(session_factory, recorded):
    """API는 출전 불확실, 검색 보도는 결장 — 상충으로 표시하고 한쪽을 삭제하지 않는다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_conflict")
        session.commit()

    research = outcome.research
    assert research is not None
    update = research.player_updates[0]
    assert update.conflict is True
    assert update.api_status == r2.STATUS_DOUBTFUL
    assert update.status == r2.STATUS_CONFIRMED_ABSENCE
    # API 사실 자체는 그대로 남아 있다.
    fact = next(item for item in research.facts if item.player_id == 7101)
    assert fact.type_marker == "Questionable"

    # 검색 스냅샷이 상충으로 표시되고, source URL도 보존된다.
    claims = outcome.payload["claims"]
    conflict_claims = [claim for claim in claims if claim["decision"] == "conflict"]
    assert conflict_claims, claims
    assert conflict_claims[0]["source_url"] == "https://recorded.example.test/home-team-news"

    coverage = {entry["topic"]: entry for entry in outcome.payload["coverage"]}
    assert coverage["부상 맥락 검색"]["state"] == "source_conflict"

    body = r2.compose_availability_body(outcome.payload).body
    assert "출전 불확실" in body and "결장" in body
    assert "어느 쪽도 확정으로 바꾸지 않았습니다" in body


# --------------------------------------------------------------------------
# accept criteria 4: 영향 해석에는 근거가 붙는다
# --------------------------------------------------------------------------


def test_api_fact_keeps_collection_timestamp(session_factory, recorded):
    """API 사실에 D0가 남긴 수집 시각이 붙고, 시각이 없으면 지어내지 않는다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_doubtful")
        session.commit()

    research = outcome.research
    assert research is not None
    for fact in research.facts:
        assert fact.collected_at == datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)
    composed = r2.compose_availability_body(outcome.payload)
    assert "수집 2026-11-10" in composed.body

    # 시각 정보가 없는 자료에서는 '시각 미상'으로 남고 값을 만들지 않는다.
    without_topics = dict(recorded["material_api_session"])
    without_topics.pop("topics", None)
    facts = r2.injury_facts_from_material(without_topics)
    assert all(fact.collected_at is None for fact in facts.facts)


def test_injury_impact_has_basis(session_factory, recorded):
    """근거가 연결된 영향 해석만 채택하고, 근거 없는 단정은 버린다."""
    with session_factory() as session:
        with_basis = _run_research(session, recorded, key="model_output_doubtful")
        without_basis = _run_research(session, recorded, key="model_output_impact_without_basis")
        session.commit()

    research = with_basis.research
    assert research is not None
    assert len(research.impacts) == 2
    for impact in research.impacts:
        assert impact.basis, "영향 해석에는 근거가 있어야 한다"
    impact_claims = [
        claim for claim in with_basis.payload["claims"] if claim["kind"] == "ai_interpretation"
    ]
    assert len(impact_claims) == 2
    assert all("근거가 연결된 해석" in (claim["decision_reason"] or "") for claim in impact_claims)

    rejected = without_basis.research
    assert rejected is not None
    assert rejected.impacts == ()
    assert any("근거가 연결되지 않은 영향 해석" in note for note in without_basis.diagnostics)
    # 사실 claim은 남고, 근거 없는 해석만 빠진다.
    assert rejected.player_updates
    body = r2.compose_availability_body(without_basis.payload).body
    assert "리그 최고" not in body
    assert "전력 영향" not in body


def test_invented_source_url_is_rejected(session_factory, recorded):
    """이번 검색 결과에 없는 URL을 근거로 쓴 항목은 채택하지 않는다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_invented_url")
        session.commit()

    research = outcome.research
    assert research is not None
    assert research.player_updates == ()
    assert any("이번 검색 결과에 없는 URL" in note for note in outcome.diagnostics)
    assert outcome.quality is QualityStatus.INSUFFICIENT


# --------------------------------------------------------------------------
# accept criteria 5: 검색이 없어도 API 사실로 결과를 만든다
# --------------------------------------------------------------------------


def test_api_only_availability_result(session_factory, recorded):
    """검색 출처가 비어도 API 사실로 본문·근거를 만든다. 누락 문구는 본문에 없다."""
    with session_factory() as session:
        outcome = _run_research(
            session,
            recorded,
            key="model_output_empty_search",
            grounding=False,
        )
        session.commit()

    research = outcome.research
    assert research is not None
    assert research.grounding.available is False
    assert research.player_updates

    coverage = {entry["topic"]: entry for entry in outcome.payload["coverage"]}
    assert coverage["부상 맥락 검색"]["state"] == "search_not_found"
    assert coverage["부상·출전 불확실 API"]["state"] == "available"
    # 검색 미확보는 진단에만 남는다.
    assert any("grounding 출처가 비어" in note for note in outcome.diagnostics)

    composed = r2.compose_availability_body(outcome.payload)
    assert composed.body.strip()
    assert composed.quality is QualityStatus.READY
    # 독자용 본문에 자료 누락·검색 실패 안내가 없다.
    for banned in ("검색", "미확보", "누락", "API 자료 없음", "grounding"):
        assert banned not in composed.body, composed.body
    # 근거 목록에는 API 출처가 남고, URL은 만들지 않는다.
    assert any(source["kind"] == "api" for source in composed.sources)
    assert all(source["url"] is None for source in composed.sources)


def test_material_topics_do_not_depend_on_korean_label(recorded):
    """D0 coverage 항목 라벨이 한글이 아니어도 같은 상태를 읽는다(공유 계약 가정 금지)."""
    english = {
        "coverage": [{"topic": "injuries", "state": "available", "detail": "3건"}],
        "claims": recorded["material_api_session"]["claims"],
        "topics": recorded["material_api_session"]["topics"],
    }
    facts = r2.injury_facts_from_material(english)
    assert facts.state == r2.STATE_AVAILABLE
    assert len(facts.facts) == 3
    assert facts.facts[0].collected_at is not None

    # 같은 주제가 not_run과 실제 결과로 함께 와도 실제 결과를 쓴다.
    mixed = {
        "coverage": [
            {"topic": "injuries", "state": "not_run", "detail": None},
            {"topic": "부상·출전 불확실", "state": "call_error", "detail": "HTTP 500"},
        ]
    }
    assert r2.injury_facts_from_material(mixed).state == r2.STATE_CALL_ERROR

    # 부상 항목이 아예 없으면 '자료 없음'이 아니라 '수집 미실행'이다.
    assert r2.injury_facts_from_material({"coverage": []}).state == r2.STATE_NOT_RUN


def test_grounding_metadata_and_suggestions_are_preserved(session_factory, recorded):
    """grounding 출처·검색어·Search Suggestions를 원문 그대로 보존한다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_doubtful")
        session.commit()

    research = outcome.research
    assert research is not None
    grounding = research.grounding
    assert [source.uri for source in grounding.sources] == [
        "https://recorded.example.test/home-team-news",
        "https://recorded.example.test/match-preview-notes",
    ]
    assert grounding.queries[0].startswith("Recorded Home Recorded Away team news")
    assert grounding.search_entry_point is not None
    assert "recorded-suggestions" in grounding.search_entry_point["rendered_content"]
    # supports는 수신한 원문 그대로 보존한다(키 이름을 바꾸지 않는다).
    support = grounding.supports[0]
    indices = support.get("grounding_chunk_indices", support.get("groundingChunkIndices"))
    assert indices == [0]
    # 검색 스냅샷이 source_kind=search로 남는다.
    assert research.search_snapshot_id is not None
    # 검색은 모델 호출 안에서 일어난다. 별도 검색 호출을 만들지 않는다.
    assert outcome.external_calls == 0  # mock transport는 live 호출로 세지 않는다


# --------------------------------------------------------------------------
# 사용자 테스트 단위: 섹션 워크플로우 전체
# --------------------------------------------------------------------------


def test_section_workflow_stores_reader_body_and_sources(session_factory, recorded):
    """prepare_data → research → compose_body → finalize 전체가 독자용 본문을 저장한다."""
    with session_factory() as session:
        transport = _transport(recorded, "model_output_doubtful")
        implementations = r2.build_availability_implementations(
            prepare_data=_section_prepare(recorded),
            transport=transport,
            now=FIXED_NOW,
        )
        result = runner.run_section_workflow(
            session,
            workflow_id="section_availability",
            implementations=implementations,
            actor_id=4,
            fixture=dict(recorded["fixture"]),
            fixture_label=str(recorded["fixture_label"]),
            transport=transport,
            limits=BudgetLimits(),
            now=RUN_NOW,
        )
        session.commit()

        assert result.unavailable is False
        assert result.body.strip()
        assert result.sources
        assert [step["node"] for step in result.step_log] == [
            "prepare_data",
            "research",
            "compose_body",
            "finalize",
        ]
        assert result.mode is RunMode.MOCK
        # 모델 호출은 정상 경로 1회다.
        assert len(transport.calls) == 1
        assert transport.calls[0].module_id == "R2"
        assert transport.calls[0].parameters["generation_config"]["tools"] == [
            {"google_search": {}}
        ]

        # 저장된 행만으로 다시 연다(외부 호출 없음).
        detail = store.get_run_detail(session, result.run_id)
        stored = detail.section_results[0]
        assert stored["body"] == result.body
        assert stored["sources"] == [dict(item) for item in result.sources]
        assert stored["mode"] == "mock"
        assert "출전 불확실" in stored["body"]

        # 본문은 한국어 산문이고, 노드 raw JSON을 그대로 붙이지 않는다.
        assert "{" not in stored["body"]
        assert "player_updates" not in stored["body"]
        # 자료 누락·오류 문구는 관리자 진단에만 있다.
        for banned in ("미확보", "호출 실패", "재시도", "부상자 없음"):
            assert banned not in stored["body"]
        assert stored["diagnostics"]


def test_section_without_evidence_stays_draft(session_factory, recorded):
    """근거가 없으면 본문을 만들지 않고 관리자 초안으로 남긴다(오류 문단을 본문에 넣지 않음)."""
    with session_factory() as session:
        transport = _transport(
            recorded, "model_output_empty_search", grounding=False
        )
        implementations = r2.build_availability_implementations(
            prepare_data=_section_prepare(recorded),
            transport=transport,
            now=FIXED_NOW,
        )

        def empty_prepare(ctx, state):  # noqa: ANN001 - 노드 계약
            return runner.NodeOutcome(payload=dict(recorded["material_empty_injuries"]))

        implementations = runner.WorkflowImplementations(
            prepare_data=runner.NodeImplementation(
                module_id="D0",
                implementation_version="mp06-test-d0-1",
                prompt_version=None,
                mode=RunMode.MOCK,
                run=empty_prepare,
            ),
            research=implementations.research,
            compose_body=implementations.compose_body,
        )
        result = runner.run_section_workflow(
            session,
            workflow_id="section_availability",
            implementations=implementations,
            actor_id=4,
            fixture=dict(recorded["fixture"]),
            transport=transport,
            limits=BudgetLimits(),
            now=RUN_NOW,
        )
        session.commit()

        assert result.body == ""
        assert result.unavailable is True
        assert result.quality is QualityStatus.INSUFFICIENT
        assert result.diagnostics
        # 모델 호출은 여전히 1회다. 재작성 호출을 추가하지 않는다.
        assert len(transport.calls) == 1


def test_research_uses_stored_injury_rows_without_inventing_names(session_factory, recorded):
    """저장된 DB 부상 행을 쓸 때도 선수 이름을 만들지 않는다."""
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            player_id=9101,
            player_name=None,
            team_id=50,
            type_marker="Doubtful",
            reason="Knock",
            reported_at=datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc),
            fixture_id=1200001,
        )
    ]
    with session_factory() as session:
        outcome = _run_research(
            session,
            recorded,
            key="model_output_empty_search",
            material_key="material_empty_injuries",
            grounding=False,
            stored_loader=lambda fixture_id: rows,
        )
        session.commit()

    research = outcome.research
    assert research is not None
    assert research.material_state == r2.STATE_AVAILABLE
    fact = research.facts[0]
    assert fact.evidence_id == "stored:injury-9101"
    assert fact.player_name is None
    assert fact.reported_at == datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    assert fact.display_name == "선수 ID 9101"


def test_common_d0_payload_with_aggregate_only_uses_stored_reader(recorded):
    """공통 D0가 집계 사실만 넘기면 저장된 부상 행을 읽어 선수별 사실을 만든다.

    MP-05의 `read_stored_context`는 `api:injury-count` 집계 사실만 만든다. R2는 그
    문장을 선수별 사실로 쪼개지 않고, 주입된 읽기 전용 조회기에서 행을 읽는다.
    """
    from types import SimpleNamespace

    common_payload = {
        "facts": [
            {
                "fact_id": "api:injury-count",
                "text": "저장된 부상·출전 불확실 행 2건이 있습니다(표기: Doubtful, Out).",
                "snapshot_id": "44444444-4444-4444-8444-444444444444",
                "collected_at": "2026-11-10T16:00:00+00:00",
                "subject_team_id": None,
            }
        ],
        "fixture": {
            "fixture_id": 1200001,
            "league_id": 39,
            "season": 2026,
            "home_team_id": 50,
            "away_team_id": 49,
            "kickoff_at": "2026-11-12T20:00:00+00:00",
            "home_team": "Recorded Home",
            "away_team": "Recorded Away",
            "league": "Recorded League",
        },
        "snapshot_ids": ["44444444-4444-4444-8444-444444444444"],
        "coverage": [
            {"topic": "부상·출전 불확실", "state": "available", "detail": "2건(표기 보존)"}
        ],
        "claims": [],
    }
    rows = [
        SimpleNamespace(
            player_id=9201,
            player_name=None,
            team_id=50,
            type_marker="Doubtful",
            reason=None,
            reported_at=None,
            fixture_id=1200001,
        ),
        SimpleNamespace(
            player_id=9202,
            player_name=None,
            team_id=49,
            type_marker="Out",
            reason=None,
            reported_at=None,
            fixture_id=1200001,
        ),
    ]
    facts = r2.injury_facts_from_material(
        common_payload, stored_loader=lambda fixture_id: rows, fixture=_fixture_identity(recorded)
    )
    assert facts.state == r2.STATE_AVAILABLE
    assert [fact.evidence_id for fact in facts.facts] == ["stored:injury-9201", "stored:injury-9202"]
    assert [fact.expected_status for fact in facts.facts] == ["doubtful", "confirmed_absence"]
    # 팀 이름은 D0가 확인한 값만 쓴다.
    assert facts.team_names[50] == "Recorded Home"
    assert facts.team_names[49] == "Recorded Away"


def test_stored_rows_reference_the_d0_snapshot_and_are_labelled_readonly(recorded):
    """저장 자료에서 읽은 사실은 D0 스냅샷을 참조하고 '읽기 전용'으로 표기한다."""
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            player_id=9401,
            player_name=None,
            team_id=49,
            type_marker="Missing Fixture",
            reason="Hamstring injury",
            reported_at=None,
            fixture_id=1200001,
        )
    ]
    common_payload = {
        "snapshot_ids": ["55555555-5555-4555-8555-555555555555"],
        "topics": {
            "D0-injuries": {
                "snapshot_id": "55555555-5555-4555-8555-555555555555",
                "collected_at": "2026-11-10T15:30:00+00:00",
            }
        },
        "coverage": [{"topic": "부상·출전 불확실", "state": "available", "detail": "1건"}],
        "claims": [],
    }
    facts = r2.injury_facts_from_material(
        common_payload, fixture=_fixture_identity(recorded), stored_loader=lambda _fid: rows
    )
    fact = facts.facts[0]
    assert str(fact.snapshot_id) == "55555555-5555-4555-8555-555555555555"
    assert fact.collected_at == datetime(2026, 11, 10, 15, 30, tzinfo=timezone.utc)
    assert fact.source == "stored_db"

    # 스냅샷이 여럿이면 어느 것인지 확정하지 않고 붙이지 않는다.
    ambiguous = dict(common_payload)
    ambiguous["snapshot_ids"] = [
        "55555555-5555-4555-8555-555555555555",
        "66666666-6666-4666-8666-666666666666",
    ]
    ambiguous_facts = r2.injury_facts_from_material(
        ambiguous, fixture=_fixture_identity(recorded), stored_loader=lambda _fid: rows
    )
    assert ambiguous_facts.facts[0].snapshot_id is None
    assert ambiguous_facts.facts[0].collected_at is None


def test_reader_object_supplies_stored_injury_rows(recorded):
    """읽기 전용 조회기 객체만 넘겨도 저장 부상 행을 읽고 이름을 만들지 않는다."""
    from types import SimpleNamespace

    class Reader:
        def __init__(self) -> None:
            self.calls: list[int] = []

        def get_fixture(self, **kwargs):  # pragma: no cover - 사용하지 않는다
            raise AssertionError("R2는 경기 단건 조회를 하지 않는다")

        def standings_for_league(self, **kwargs):  # pragma: no cover - 사용하지 않는다
            raise AssertionError("R2는 순위 자료를 읽지 않는다")

        def injuries_for_fixture(self, fixture_id: int):
            self.calls.append(fixture_id)
            return [
                SimpleNamespace(
                    player_id=9301,
                    player_name=None,
                    team_id=50,
                    type_marker="Questionable",
                    reason="Knock",
                    reported_at=None,
                    fixture_id=fixture_id,
                )
            ]

    reader = Reader()
    common_payload = {
        "coverage": [{"topic": "부상·출전 불확실", "state": "available", "detail": "1건"}],
        "claims": [],
    }
    facts = r2.injury_facts_from_material(
        common_payload,
        fixture=_fixture_identity(recorded),
        stored_loader=r2._loader_from_reader(reader),
    )
    assert reader.calls == [1200001]
    assert facts.facts[0].evidence_id == "stored:injury-9301"
    assert facts.facts[0].player_name is None
    assert facts.facts[0].expected_status == r2.STATUS_DOUBTFUL


def test_research_prompt_has_no_available_fixture_leak(recorded):
    """프롬프트는 경기 식별·자료 상태·인용 가능 id를 담고, 자리표시자를 남기지 않는다."""
    facts = r2.injury_facts_from_material(recorded["material_api_session"])
    text = r2.build_prompt(
        template=r2.load_prompt_template(),
        fixture=_fixture_identity(recorded),
        facts=facts,
        today=FIXED_NOW,
    )
    assert "1200001" in text
    assert "api:injury-7101" in text
    assert "available" in text
    for placeholder in ("{fixture_id}", "{api_facts}", "{evidence_ids}", "{injury_state}"):
        assert placeholder not in text


def test_claims_reference_api_snapshots(session_factory, recorded):
    """API 사실 claim이 D0 스냅샷을 참조하고, 실행 결과가 저장된다."""
    with session_factory() as session:
        outcome = _run_research(session, recorded, key="model_output_doubtful")
        session.commit()

    api_claims = [claim for claim in outcome.payload["claims"] if claim["claim_id"].startswith("r2-api-")]
    assert api_claims
    for claim in api_claims:
        assert claim["snapshot_ids"], claim
        assert claim["kind"] == "fact"
    # 모듈 결과 저장 경로도 그대로 쓸 수 있다(공통 계약).
    assert outcome.payload["module_id"] == "R2"
    assert outcome.payload["mode"] == "mock"


def test_transport_failure_keeps_api_facts_and_reports_failure(session_factory, recorded):
    """모델 호출이 실패하면 API 사실은 보존하고, 본문 대신 실패로 남긴다."""
    run_id = uuid.uuid4()
    context = _context(run_id)
    with session_factory() as session:
        _store_run(session, context)
        transport = provider.RecordedTransport(
            script=[
                provider.TransportResult(
                    http_status=401,
                    raw_request={"contents": "요청"},
                    raw_response={"error": {"code": 401, "message": "unauthorized"}},
                    error_class="authentication_error",
                    error_message="unauthorized",
                )
            ]
        )
        outcome = r2.research_availability(
            session,
            module_input=_module_input(recorded),
            context=context,
            transport=transport,
            budget=RunBudget.for_run(now=RUN_NOW),
            material=recorded["material_api_session"],
            now=FIXED_NOW,
        )
        session.commit()

    # 401은 같은 요청을 다시 보내지 않는다.
    assert len(transport.calls) == 1
    assert outcome.unavailable_reason is not None
    assert outcome.quality is QualityStatus.INSUFFICIENT
    api_claims = [claim for claim in outcome.payload["claims"] if claim["claim_id"].startswith("r2-api-")]
    assert api_claims, "실패해도 보존된 API 사실은 남아야 한다"
    assert r2.compose_availability_body(outcome.payload).body == ""


def test_module_input_contract_is_respected(recorded):
    """모듈 입력 계약(ModuleInput)을 그대로 받고 필요한 값만 읽는다."""
    module_input = _module_input(recorded)
    assert module_input.module_id == "R2"
    assert module_input.prompt_version == r2.PROMPT_VERSION
    assert module_input.fixture is not None
    assert module_input.fixture.fixture_id == 1200001


def test_unlabelled_api_type_mapping(recorded):
    """API 표기 → 상태 매핑이 D0와 같은 판정을 쓴다(문구가 어긋나지 않게)."""
    assert api.injury_uncertainty("Questionable") == "uncertain"
    assert api.injury_uncertainty("Missing Fixture") == "confirmed"
    assert api.injury_uncertainty(None) == "unknown"
    facts = r2.injury_facts_from_material(recorded["material_api_session"])
    by_id = {fact.player_id: fact for fact in facts.facts}
    assert by_id[7101].expected_status == r2.STATUS_DOUBTFUL
    assert by_id[7102].expected_status == r2.STATUS_CONFIRMED_ABSENCE
    assert by_id[7103].expected_status == r2.STATUS_UNKNOWN


def test_parsed_output_tolerates_code_fence():
    """모델이 코드 블록으로 감싸도 JSON을 읽는다. 못 읽으면 None(빈 dict 아님)."""
    assert r2.parse_model_output('```json\n{"a": 1}\n```') == {"a": 1}
    assert r2.parse_model_output("설명만 있는 응답") is None
    assert r2.parse_model_output(None) is None
    validated = r2.validate_model_output(None, facts=r2.AvailabilityFacts(
        state=r2.STATE_NOT_RUN, detail=None, facts=()
    ), grounding=r2.GroundingInfo())
    assert validated.player_updates == ()
    assert validated.rejected
