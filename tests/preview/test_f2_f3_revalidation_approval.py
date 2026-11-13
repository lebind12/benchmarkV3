"""독립 검토 F2/F3 회귀 검사.

이 파일이 확인하는 것(범위는 두 결함뿐이다):

- F2: 재검증(`revalidate_section_from_stored_response`)이 덜어낸 사실·사유를 **읽을 수
  있는 문장 목록**으로 남기고, 그 재검증이 만든 R1 검증 결과를 **버전이 붙은 저장 행**과
  출처(provenance)로 남긴다. 섹션 진단이 글자 배열로 저장되면 실패한다.
- F3: 재검증 후보 본문을 승인하면 승인 기록의 버전·구성이 **검토한 섹션 결과 행이 실제로
  가진 스탬프**와 같아야 한다. 옛 모듈 결과 행에서 다시 계산해 다른 버전(`@bf3b…`,
  `@7a18…`)을 남기면, 최신 후보를 승인해도 곧바로 SUPERSEDED가 된다.

검사 DB는 이 파일 전용 `preview_f2f3_test`다. `public` 스키마를 만들거나 지우지 않고
`preview_dev` 스키마만 비운다. 승인 행은 이 전용 DB에만 만들며 실제 승인 기록이 아니다.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.preview import approvals, runner, sections, store, version_manifest
from app.preview.contracts import (
    ApprovalState,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
)
from app.preview.modules import form
from app.preview.registry import get_section_workflow
from tests.preview._dbguard import assert_safe_test_database

TEST_DATABASE_URL = "postgresql+psycopg://preview:preview_local_dev@127.0.0.1:55432/preview_f2f3_test"

FIXED_NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "form.json").read_text(encoding="utf-8")
)
FIXTURE = FIXTURES["fixture"]

# 저장된 D0 사실 2건만 있는 실행을 재현한다(검색 출처 0건).
FACT_IDS = ("api:standings-13", "api:standings-4")

# 덜어낼 사실과, 그 사실을 전제로 삼는 판단 문장을 함께 담은 R1 원문.
STORED_MODEL_TEXT = json.dumps(
    {
        "match_context": {
            "importance": "리그 3위 Manchester City가 하위권 Fulham을 홈으로 불러들이는 경기입니다.",
            "importance_evidence": ["api:standings-13", "api:standings-4"],
        },
        "recent_form": [
            {
                "team": "Manchester City",
                "summary": "10경기 7승 3패로 리그 3위입니다.",
                "evidence": ["api:standings-13"],
            }
        ],
        "watch_points": [
            {
                "title": "최전방 기동력",
                "detail": (
                    "Rodrigo Muniz는 최근 뉴캐슬전에서 동점골을 터뜨렸으며,"
                    " 최근 득점으로 자신감을 얻은 만큼 눈여겨볼 만합니다."
                ),
                "evidence": ["api:standings-4"],
            }
        ],
        "hot_players": [],
        "search_note": None,
        "uncertainties": [],
    },
    ensure_ascii=False,
)


@pytest.fixture(scope="module", autouse=True)
def _environment() -> Iterator[None]:
    """전용 DB를 확인하고 앱 설정을 이 DB로 고정한다."""
    assert_safe_test_database(TEST_DATABASE_URL)
    previous = {
        key: os.environ.get(key)
        for key in (
            "PREVIEW_DATABASE_URL",
            "PREVIEW_IDENTITY_DATABASE_URL",
            "PREVIEW_ENV",
            "PREVIEW_COOKIE_SECURE",
        )
    }
    os.environ["PREVIEW_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_IDENTITY_DATABASE_URL"] = TEST_DATABASE_URL
    os.environ["PREVIEW_ENV"] = "test"
    os.environ["PREVIEW_COOKIE_SECURE"] = "false"
    yield
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture()
def engine(_environment: None):
    from app.auth import models as _auth_models  # noqa: F401  (모델 등록)
    from app.preview.db import SCHEMA, Base
    from app.preview import models as _preview_models  # noqa: F401  (모델 등록)
    from app.preview import store as _store  # noqa: F401

    engine = create_engine(
        TEST_DATABASE_URL,
        future=True,
        connect_args={"options": f"-c search_path={SCHEMA}"},
    )
    with engine.begin() as conn:
        # 이 전용 DB에서 개발 스키마만 비운다. `public`은 만들지도 지우지도 않는다.
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    Base.metadata.create_all(engine)
    yield engine
    with engine.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {SCHEMA}"))
    engine.dispose()


@pytest.fixture()
def session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _facts() -> form.FormFacts:
    return form.FormFacts(
        fixture_id=FIXTURE["fixture_id"],
        league_id=FIXTURE["league_id"],
        season=FIXTURE["season"],
        home_team_id=FIXTURE["home_team_id"],
        away_team_id=FIXTURE["away_team_id"],
        kickoff_at=datetime.fromisoformat(FIXTURE["kickoff_at"]),
        home_team=FIXTURE["home_team"],
        away_team=FIXTURE["away_team"],
        league=FIXTURE["league"],
        facts=tuple(
            form.Fact(
                fact_id=fact_id,
                text=str(item["text"]),
                snapshot_id=str(item["snapshot_id"]),
                collected_at=(
                    datetime.fromisoformat(str(item["collected_at"]))
                    if item.get("collected_at")
                    else None
                ),
                subject_team_id=item.get("subject_team_id"),
            )
            for fact_id, item in zip(FACT_IDS, FIXTURES["facts"], strict=False)
        ),
    )


def _seed_stored_run(session) -> tuple[uuid.UUID, uuid.UUID]:
    """R1 원문·D0 결과·섹션 결과가 저장된 실행 하나를 만든다(외부 호출 0회)."""
    from app.preview import artifacts as artifact_store
    from app.preview.contracts import ModuleResult, ModuleStatus, QualityStatus

    run_id = uuid.uuid4()
    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=11,
        config_version="f2f3-test",
        limits=ExecutionLimits(),
    )
    store.store_run(session, context, fixture=None, fixture_label="Manchester City vs Fulham")

    # D0: 저장 자료 재사용 결과(외부 호출 0회).
    d0_execution = store.start_module_execution(
        session,
        run_id=run_id,
        module_id="D0",
        module_input=_module_input("D0", sections.STORED_DATA_IMPLEMENTATION_VERSION),
        actor_id=11,
    )
    facts = _facts()
    d0_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id="D0",
        module_execution_id=d0_execution.id,
        run_id=run_id,
        version=1,
        input_hash=d0_execution.input_hash,
        status=ModuleStatus.SUCCEEDED,
        quality=QualityStatus.READY,
        implementation_version=sections.STORED_DATA_IMPLEMENTATION_VERSION,
        prompt_version="",
        payload={
            "fixture": {
                "fixture_id": facts.fixture_id,
                "league_id": facts.league_id,
                "season": facts.season,
                "home_team_id": facts.home_team_id,
                "away_team_id": facts.away_team_id,
                "kickoff_at": facts.kickoff_at.isoformat(),
                "home_team": facts.home_team,
                "away_team": facts.away_team,
                "league": facts.league,
            },
            "facts": [fact.to_dict() for fact in facts.facts],
            "api_sources": list(FIXTURES["api_sources"]),
        },
    )
    store.save_module_result(session, d0_result, actor_id=11)

    # R1: 옛 구현 버전으로 저장된 원문 응답·결과. 재검증은 이 원문만 읽는다.
    old_impl, old_prompt = "mp05-form-1-nomime-1", "mp05-form-prompt-1"
    r1_execution = store.start_module_execution(
        session,
        run_id=run_id,
        module_id="R1",
        module_input=_module_input("R1", old_impl, prompt_version=old_prompt),
        actor_id=11,
    )
    artifact = artifact_store.save_artifact(
        session,
        run_id=run_id,
        kind=artifact_store.ArtifactKind.RAW_RESPONSE,
        content={"candidates": [{"content": {"parts": [{"text": STORED_MODEL_TEXT}]}}]},
        actor_id=11,
        now=FIXED_NOW,
    )
    store.append_attempt(
        session,
        run_id=run_id,
        module_execution_id=r1_execution.id,
        module_id="R1",
        logical_call_id="R1-form",
        attempt_ordinal=0,
        provider="recorded-model",
        mode=RunMode.LIVE,
        outcome="succeeded",
        request_spec={"logical_call_id": "R1-form", "prompt_version": old_prompt},
        response_artifact_id=artifact.id,
        actor_id=11,
        started_at=FIXED_NOW,
        finished_at=FIXED_NOW,
    )
    r1_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id="R1",
        module_execution_id=r1_execution.id,
        run_id=run_id,
        version=1,
        input_hash=r1_execution.input_hash,
        status=ModuleStatus.SUCCEEDED,
        quality=QualityStatus.READY,
        implementation_version=old_impl,
        prompt_version=old_prompt,
        payload={"note": "옛 구현이 저장한 R1 결과"},
    )
    store.save_module_result(session, r1_result, actor_id=11)

    # 옛 본문 섹션 결과. 재검증은 이 행을 덮어쓰지 않고 새 버전을 올린다.
    old_stamp = "section_form@9f0d2e9bcb33c26d"
    section_row = store.save_section_result(
        session,
        run_id=run_id,
        workflow_id="section_form",
        workflow_version=old_stamp,
        title="경기력·주목 선수",
        body="Manchester City와 Fulham의 맞대결입니다. 옛 규칙으로 만든 본문입니다.",
        version=1,
        mode=RunMode.LIVE,
        environment=Environment.DEV,
        quality=QualityStatus.READY,
        output_contract_version=get_section_workflow("section_form").output_contract_version,
        contract_version="mp04-section-result-1",
        sources=(),
        module_execution_ids=[d0_execution.id, r1_execution.id],
        result_ids=[d0_result.result_id, r1_result.result_id],
        diagnostics=("옛 규칙으로 저장한 진단입니다.",),
        actor_id=11,
        now=FIXED_NOW,
    )
    session.commit()
    return run_id, section_row.id


def _module_input(module_id: str, implementation: str, *, prompt_version: str = ""):
    from app.preview.contracts import ModuleInput, compute_input_hash

    return ModuleInput(
        module_id=module_id,
        fixture=None,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash(
            {"module_id": module_id, "implementation": implementation}
        ),
        prompt_version=prompt_version,
        contract_version="mp02-1",
        implementation_version=implementation,
    )


def _revalidate(session, run_id: uuid.UUID):
    return sections.revalidate_section_from_stored_response(
        session, run_id=run_id, actor_id=11, now=FIXED_NOW
    )


# --------------------------------------------------------------------------
# F2: 재검증 진단·검증 결과 기록
# --------------------------------------------------------------------------


def test_revalidation_diagnostics_are_readable_complete_messages(session_factory):
    """F2 — 섹션 진단은 글자 배열이 아니라 전체 문장 목록으로 저장된다."""
    with session_factory() as session:
        run_id, _ = _seed_stored_run(session)
        row, research, _composed = _revalidate(session, run_id)
        session.commit()

        assert row.diagnostics, "재검증 진단이 저장되어야 한다"
        # 글자 단위로 쪼개지면 한 항목이 1글자다. 문장이면 2글자보다 길다.
        assert all(
            len(item) > 1 for item in row.diagnostics
        ), f"진단이 글자 배열로 저장됐다: {row.diagnostics[:10]}"
        # 사람이 읽는 문장이 그대로 남는다(재검증 사실 + 버전 표기).
        joined = " ".join(row.diagnostics)
        assert "다시 해석" in joined
        # 원래 있던 옛 진단은 그대로 보존된다.
        stored = store.get_run_detail(session, run_id).section_results
        assert stored[0]["diagnostics"] == ["옛 규칙으로 저장한 진단입니다."]

        # 검증기가 만든 제외 사유(덜어낸 사실 포함)도 읽을 수 있는 문장으로 남는다.
        assert research.diagnostics
        assert all(len(str(item)) > 1 for item in research.diagnostics)


def test_revalidation_persists_versioned_r1_result_with_provenance(session_factory):
    """F2 — 재검증이 만든 R1 검증 결과가 새 버전 행과 출처로 저장된다."""
    from app.preview.models import PreviewAttempt, PreviewResult

    with session_factory() as session:
        run_id, _ = _seed_stored_run(session)
        row, research, _composed = _revalidate(session, run_id)
        session.commit()

        r1_rows = (
            session.query(PreviewResult)
            .filter_by(run_id=run_id, module_id="R1")
            .order_by(PreviewResult.created_at)
            .all()
        )
        assert len(r1_rows) == 2, "재검증 결과가 새 R1 행으로 남아야 한다"
        old_row, new_row = r1_rows[0], r1_rows[1]
        # 실제 새 결과 행이다(옛 행을 고치지 않는다). 버전은 모듈 실행 단위로 올라간다.
        assert new_row.id != old_row.id
        assert new_row.module_execution_id != old_row.module_execution_id
        assert new_row.version == 1 and old_row.version == 1
        assert new_row.supersedes_result_id is None
        # 재검증을 수행한 구현은 지금 코드다. 원문을 만든 프롬프트는 옛 값 그대로 남는다
        # (새 프롬프트를 보냈다고 적지 않는다).
        assert new_row.implementation_version == form.FORM_IMPLEMENTATION_VERSION
        assert new_row.prompt_version == old_row.prompt_version
        assert new_row.prompt_version != form.FORM_PROMPT_VERSION
        assert new_row.status == "succeeded"
        # 저장 행은 `ModuleResult.to_dict()`라 실제 payload가 한 겹 안에 있다.
        payload = new_row.payload.get("payload") or {}
        assert payload.get("diagnostics"), "검증 진단이 R1 결과에 남아야 한다"
        provenance = payload.get("provenance") or {}
        assert provenance.get("kind") == "revalidated_from_stored_response"
        assert provenance.get("source_result_id") == str(old_row.id)
        assert provenance.get("source_prompt_version") == old_row.prompt_version
        assert provenance.get("source_implementation_version") == old_row.implementation_version
        assert provenance.get("external_calls") == 0
        # 원문 응답 정체성은 옛 attempt의 아티팩트를 그대로 가리킨다.
        attempt = session.query(PreviewAttempt).filter_by(run_id=run_id, module_id="R1").one()
        assert provenance.get("source_artifact_id") == str(attempt.response_artifact_id)
        # 섹션 결과는 이 새 R1 결과를 승인·진단 근거로 가리킨다.
        assert str(new_row.id) in row.result_ids
        # 옛 R1 행은 그대로다(backfill 없음).
        assert (old_row.payload.get("payload") or {}).get("note") == "옛 구현이 저장한 R1 결과"


def test_revalidation_keeps_source_generation_versions_separate(session_factory):
    """F2 — 재검증은 원문 생성 프롬프트를 새 프롬프트로 다시 쓰지 않는다."""
    with session_factory() as session:
        run_id, _ = _seed_stored_run(session)
        _row, research, _composed = _revalidate(session, run_id)
        session.commit()

        # 재검증 결과는 "지금 검증 규칙"으로 해석한 결과다.
        assert research.implementation_version == form.FORM_IMPLEMENTATION_VERSION
        # 원문은 옛 프롬프트가 만든 것이므로, 그 사실을 바꾸어 말하지 않는다.
        assert research.sources is not None
        detail = store.get_run_detail(session, run_id)
        assert detail.attempts, "옛 시도 기록이 그대로 남아야 한다"
        assert all(
            str(attempt.get("prompt_version") or "") in ("", "mp05-form-prompt-1")
            for attempt in detail.attempts
            if attempt.get("module_id") == "R1"
        ), "옛 시도에 새 프롬프트 버전을 소급하지 않는다"


# --------------------------------------------------------------------------
# F3: 승인이 검토한 본문/버전/구성을 가리킨다
# --------------------------------------------------------------------------


def test_approval_records_the_reviewed_section_version(session_factory):
    """F3 — 승인 버전은 검토한 섹션 결과 스탬프와 같다(옛 모듈 행 재계산 아님)."""
    with session_factory() as session:
        run_id, _ = _seed_stored_run(session)
        row, _research, _composed = _revalidate(session, run_id)
        session.commit()

        current_version = version_manifest.workflow_version_of("section_form")
        # 재검증 후보는 지금 코드로 만든 결과이므로 현재 후보 버전을 가진다.
        assert row.workflow_version == current_version

        approval = approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=run_id,
            section_result_id=row.id,
            actor_id=11,
            note="F2/F3 회귀 검사용",
            now=FIXED_NOW,
        )
        session.commit()

        # 승인 기록의 버전은 검토한 섹션 결과의 스탬프 그대로다. 값은 지금 manifest에서
        # 유도한다(하드코딩하면 구성이 바뀔 때 검사가 의미를 잃는다).
        assert approval.workflow_version == row.workflow_version
        assert approval.workflow_version == current_version
        # 검토 보고가 실측한 옛 모듈 행 재계산 값과 다르다.
        assert approval.workflow_version not in (
            "section_form@bf3b6e2ba968e123",
            "section_form@7a18bceabdf61629",
        )
        # 구성도 그 스탬프와 같은 이유로 현재 manifest와 일치한다.
        expected = version_manifest.constituents_for_workflow("section_form")
        assert [item.to_dict() for item in approval.constituents] == [
            item.to_dict() for item in expected
        ]

        status = approvals.section_approval_status(session, "section_form")
        # 최신 후보를 승인했으므로 곧바로 SUPERSEDED가 되지 않는다.
        assert status.state is ApprovalState.APPROVED
        assert status.active_approval is not None
        assert status.active_approval.workflow_version == row.workflow_version


def test_approval_of_historical_body_keeps_its_own_version(session_factory):
    """F3 — 옛 본문을 승인하면 그 본문의 옛 스탬프가 남고 현재 후보와 구분된다."""
    from app.preview.models import PreviewSectionResult

    with session_factory() as session:
        run_id, old_section_id = _seed_stored_run(session)
        _revalidate(session, run_id)
        session.commit()

        approval = approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=run_id,
            section_result_id=old_section_id,
            actor_id=11,
            note="옛 본문 승인 경계 확인",
            now=FIXED_NOW,
        )
        session.commit()

        old_row = session.get(PreviewSectionResult, old_section_id)
        # 이 본문은 자기 구성을 남기지 않은 예전 결과다. 승인 기록은 그 본문이 실제로
        # 가리키는 옛 모듈 행에서 계산한 버전이며, 현재 후보 버전을 쓰지 않는다.
        expected_old = approvals.release_version(
            get_section_workflow("section_form"),
            approvals._reviewed_constituents(
                get_section_workflow("section_form"), old_row, approvals._results_of_run(session, run_id)
            )[0],
        )[0]
        assert approval.workflow_version == expected_old
        assert approval.workflow_version != old_row.workflow_version
        # 현재 후보는 여전히 지금 코드로 계산한 값이다(옛 승인이 덮어쓰지 않는다).
        current = version_manifest.workflow_version_of("section_form")
        assert approval.workflow_version != current
        status = approvals.section_approval_status(session, "section_form")
        assert status.state is ApprovalState.SUPERSEDED
        assert status.pinned_approval is not None
        assert status.pinned_approval.workflow_version == approval.workflow_version
        assert status.active_approval is None


def test_current_candidate_stays_derived_from_current_code(session_factory):
    """F3 — 승인 후보 계산은 현재 코드에서 나오고 승인 기록과 섞이지 않는다."""
    with session_factory() as session:
        run_id, old_section_id = _seed_stored_run(session)
        _revalidate(session, run_id)
        session.commit()

        workflow = get_section_workflow("section_form")
        before = approvals.section_approval_status(session, "section_form").current_version
        approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=run_id,
            section_result_id=old_section_id,
            actor_id=11,
            now=FIXED_NOW,
        )
        session.commit()
        after = approvals.section_approval_status(session, "section_form").current_version

        assert before == after == runner.section_workflow_version(workflow)


def test_old_result_rows_do_not_leak_into_the_approval(session_factory):
    """F3 — 승인 구성은 검토한 결과를 만든 구성이고, 옛 모듈 행으로 대체되지 않는다."""
    from app.preview.models import PreviewResult

    with session_factory() as session:
        run_id, _ = _seed_stored_run(session)
        row, _research, _composed = _revalidate(session, run_id)
        session.commit()

        approval = approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=run_id,
            section_result_id=row.id,
            actor_id=11,
            now=FIXED_NOW,
        )
        session.commit()

        by_module = {item.module_id: item for item in approval.constituents}
        # 옛 R1 행에 붙은 옛 버전이 승인 구성으로 새지 않는다.
        old_r1 = (
            session.query(PreviewResult)
            .filter_by(run_id=run_id, module_id="R1")
            .order_by(PreviewResult.version)
            .first()
        )
        assert old_r1 is not None
        assert by_module["R1"].implementation_version != old_r1.implementation_version
        assert by_module["R1"].implementation_version == form.FORM_IMPLEMENTATION_VERSION
        # 승인 근거 섹션 결과를 그대로 가리킨다.
        assert approval.evidence.section_result_id == row.id
