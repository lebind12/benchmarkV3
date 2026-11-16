"""NS-01 선수 섹션 고정 슬롯·한글명 후보 저장소 직접 검사.

로컬 전용 합성 테스트 DB(`tests/preview/conftest.py`)에서만 실행한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select, text

from app.preview import approvals, player_name_candidates, player_section_store, store
from app.preview.contracts import (
    CONTRACT_VERSION,
    SECTION_RESULT_CONTRACT_VERSION,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    OperationKind,
    QualityStatus,
    RunMode,
)
from app.preview.models import (
    PreviewSectionApproval,
    PreviewSectionResult,
    PreviewWriteAudit,
)
from app.preview.player_section_contracts import (
    INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
    INJURY_PLAYERS_TABLE,
    PLAYER_NAME_CANDIDATES_TABLE,
    WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
    WATCH_PLAYERS_TABLE,
    CandidateReviewStatus,
    CandidateSource,
    InjuryPlayerSectionInput,
    InjuryPlayerSlot,
    NameSource,
    PlayerNameCandidateInput,
    PlayerSectionAttemptTrace,
    PlayerSectionProcessingResult,
    PlayerSectionWorkflowId,
    PendingWatchSlotDraft,
    SlotKey,
    WatchPlayerSectionInput,
    WatchPlayerSlot,
)
from app.preview.player_section_models import (
    PreviewInjuryPlayerSection,
    PreviewPlayerNameCandidate,
    PreviewWatchPlayerSection,
)
from app.preview.store import RunNotFound, WriteConflict


def _fixture(fixture_id: int = 9101, home_team_id: int = 10, away_team_id: int = 20) -> FixtureIdentity:
    return FixtureIdentity(
        fixture_id=fixture_id,
        league_id=39,
        season=2026,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        kickoff_at=datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc),
    )


def _create_run(
    session,
    *,
    fixture_id: int = 9101,
    home_team_id: int = 10,
    away_team_id: int = 20,
    mode: RunMode = RunMode.MOCK,
    actor_id: int = 7,
):
    ctx = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=mode,
        actor_id=actor_id,
        config_version=f"test/{CONTRACT_VERSION}",
        limits=ExecutionLimits(model_requests=1, api_requests=0),
    )
    return store.store_run(
        session,
        ctx,
        fixture=_fixture(fixture_id, home_team_id, away_team_id),
        label="ns01-storage-test",
    )


def _create_section_result(
    session,
    *,
    run_id: uuid.UUID,
    workflow_id: str,
    output_contract_version: str,
    mode: RunMode = RunMode.MOCK,
    version: int = 1,
    body: str = "섹션 요약 본문",
    actor_id: int = 7,
) -> PreviewSectionResult:
    return store.save_section_result(
        session,
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_version="wf-test-1",
        title="선수 섹션",
        body=body,
        version=version,
        mode=mode,
        environment=Environment.DEV,
        quality=QualityStatus.PENDING,
        output_contract_version=output_contract_version,
        contract_version=CONTRACT_VERSION,
        actor_id=actor_id,
    )


def _build_watch_input(
    *,
    run_id: uuid.UUID,
    section_result_id: uuid.UUID,
    fixture_id: int = 9101,
    home_team_id: int = 10,
    away_team_id: int = 20,
    cand_id: uuid.UUID | None = None,
    away_body: str = "후반 조커로 투입돼 측면을 흔드는 변수다.",
) -> WatchPlayerSectionInput:
    resolved_cand_id = cand_id or uuid.uuid4()
    home1 = WatchPlayerSlot(
        player_id=101,
        original_name="Son Heung-Min",
        name_ko="손흥민",
        body="최근 홈 3경기 연속 공격포인트를 기록했다.",
        name_source=NameSource.DB_KO,
        evidence=("fact-home1", {"kind": "api", "fact_id": "f-home1"}),
    )
    away1 = WatchPlayerSlot(
        player_id=None,
        original_name="Jhon Duran",
        name_ko="존 두란",
        body=away_body,
        name_source=NameSource.AI_CANDIDATE,
        unresolved_reason="db_player_not_matched",
        translation_candidate_id=resolved_cand_id,
    )
    cand = PlayerNameCandidateInput(
        id=resolved_cand_id,
        run_id=run_id,
        section_result_id=section_result_id,
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        slot_key=SlotKey.AWAY1,
        fixture_id=fixture_id,
        team_id=away_team_id,
        player_id=None,
        original_name="Jhon Duran",
        candidate_name_ko="존 두란",
    )
    return WatchPlayerSectionInput(
        section_result_id=section_result_id,
        run_id=run_id,
        fixture_id=fixture_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home1=home1,
        home2=None,
        away1=away1,
        away2=None,
        home_etc=None,
        away_etc=None,
        candidates=(cand,),
    )


def _build_injury_input(
    *,
    run_id: uuid.UUID,
    section_result_id: uuid.UUID,
    fixture_id: int = 9101,
    home_team_id: int = 10,
    away_team_id: int = 20,
    cand_id: uuid.UUID | None = None,
) -> InjuryPlayerSectionInput:
    resolved_cand_id = cand_id or uuid.uuid4()
    home1 = InjuryPlayerSlot(
        player_id=202,
        original_name="Micky van de Ven",
        name_ko="미키 판 더 펜",
        body="햄스트링 회복 중으로 출전 여부가 미확정이다.",
        name_source=NameSource.AI_CANDIDATE,
        status="unknown",
        injury="Hamstring",
        importance="수비 뒷공간 커버 핵심이다.",
        translation_candidate_id=resolved_cand_id,
        evidence=({"kind": "api", "fact_id": "inj-1"},),
    )
    cand = PlayerNameCandidateInput(
        id=resolved_cand_id,
        run_id=run_id,
        section_result_id=section_result_id,
        workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY,
        slot_key=SlotKey.HOME1,
        fixture_id=fixture_id,
        team_id=home_team_id,
        player_id=202,
        original_name="Micky van de Ven",
        candidate_name_ko="미키 판 더 펜",
    )
    return InjuryPlayerSectionInput(
        section_result_id=section_result_id,
        run_id=run_id,
        fixture_id=fixture_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home1=home1,
        candidates=(cand,),
    )


def test_save_and_reload_watch_section_with_unresolved_empty_and_pending_candidate(
    session_factory,
) -> None:
    """저장된 주목 선수·미확인 선수·빈 자리·pending 번역 후보를 재조회하지 못하면 카드와 검수 목록이 모두 비게 된다."""
    moment = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        run = _create_run(session)
        sec_res = _create_section_result(
            session,
            run_id=run.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        watch_input = _build_watch_input(run_id=run.id, section_result_id=sec_res.id)
        saved = player_section_store.save_watch_player_section(
            session, watch_input, actor_id=7, now=moment
        )

        # 호출자 트랜잭션 commit 전에도 같은 세션에서 pending 후보를 즉시 읽을 수 있어야 한다.
        pending_before_commit = player_name_candidates.list_pending_candidates(
            session, run_id=run.id
        )
        assert len(pending_before_commit) == 1
        assert pending_before_commit[0].unresolved_reason == "db_player_not_matched"
        session.commit()

    assert saved.home_etc is None
    assert saved.away_etc is None

    with session_factory() as session:
        reloaded = player_section_store.get_watch_player_section(
            session, sec_res.id, run_id=run.id
        )
        assert reloaded is not None
        assert reloaded.home1 is not None
        assert reloaded.home1.player_id == 101
        assert reloaded.home1.name_source is NameSource.DB_KO
        assert reloaded.home1.evidence == (
            "fact-home1",
            {"kind": "api", "fact_id": "f-home1"},
        )
        assert reloaded.home2 is None
        assert reloaded.away1 is not None
        assert reloaded.away1.player_id is None
        assert reloaded.away1.name_ko == "존 두란"
        assert reloaded.away1.unresolved_reason == "db_player_not_matched"
        assert reloaded.away1.body == "후반 조커로 투입돼 측면을 흔드는 변수다."
        assert reloaded.away2 is None
        assert reloaded.home_etc is None
        assert reloaded.away_etc is None

        cand_id = reloaded.away1.translation_candidate_id
        assert cand_id is not None
        cand = player_name_candidates.get_candidate(session, cand_id)
        assert cand is not None
        assert cand.review_status is CandidateReviewStatus.PENDING
        assert cand.source is CandidateSource.AI_TRANSLATION
        assert cand.unresolved_reason == "db_player_not_matched"
        assert cand.team_id == 20


def test_injury_section_preserves_unknown_status_and_participates_in_caller_rollback(
    session_factory,
) -> None:
    """부상 섹션 저장이 내부 commit을 해 버리면 부모 결과 실패 시 DB에 고아 행이 남는다."""
    with session_factory() as session:
        run = _create_run(session)
        session.commit()
        run_id = run.id

    section_result_id = uuid.uuid4()
    with session_factory() as session:
        sec_res = store.save_section_result(
            session,
            run_id=run_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY.value,
            workflow_version="wf-test-1",
            title="부상 및 결장",
            body="미키 판 더 펜은 출전 여부가 미확정이다.",
            version=1,
            mode=RunMode.MOCK,
            environment=Environment.DEV,
            quality=QualityStatus.PENDING,
            output_contract_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
            contract_version=CONTRACT_VERSION,
            section_result_id=section_result_id,
            actor_id=7,
        )
        injury_input = _build_injury_input(run_id=run_id, section_result_id=sec_res.id)
        player_section_store.save_player_section(session, injury_input, actor_id=7)
        # 호출자가 commit 전에 롤백하면 부모 결과·후보·부상 행이 모두 남지 않아야 한다.
        session.rollback()

    with session_factory() as session:
        assert session.get(PreviewSectionResult, section_result_id) is None
        assert (
            player_section_store.get_injury_player_section(session, section_result_id)
            is None
        )
        assert (
            player_name_candidates.list_candidates_for_section_result(
                session, section_result_id
            )
            == ()
        )

        # 정상 트랜잭션에서는 commit 후 status="unknown"과 원문·한글명 후보가 보존된다.
        sec_res = store.save_section_result(
            session,
            run_id=run_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY.value,
            workflow_version="wf-test-1",
            title="부상 및 결장",
            body="미키 판 더 펜은 출전 여부가 미확정이다.",
            version=1,
            mode=RunMode.MOCK,
            environment=Environment.DEV,
            quality=QualityStatus.PENDING,
            output_contract_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
            contract_version=CONTRACT_VERSION,
            section_result_id=section_result_id,
            actor_id=7,
        )
        saved = player_section_store.save_injury_player_section(
            session,
            _build_injury_input(run_id=run_id, section_result_id=sec_res.id),
            actor_id=7,
        )
        session.commit()

    assert saved.home1 is not None
    assert saved.home1.status == "unknown"
    assert saved.home1.injury == "Hamstring"
    assert saved.home1.importance == "수비 뒷공간 커버 핵심이다."
    assert saved.candidates[0].player_id == 202
    assert saved.candidates[0].unresolved_reason is None


def test_resave_identical_is_idempotent_and_value_mismatch_conflicts(
    session_factory,
) -> None:
    """동일 결과 재저장이 실패하면 재시도가 깨지고, 다른 값 덮어쓰기를 막지 못하면 기존 본문이 손상된다."""
    with session_factory() as session:
        run = _create_run(session)
        sec_res = _create_section_result(
            session,
            run_id=run.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        cand_id = uuid.uuid4()
        watch_input = _build_watch_input(
            run_id=run.id, section_result_id=sec_res.id, cand_id=cand_id
        )
        first = player_section_store.save_watch_player_section(
            session, watch_input, actor_id=7
        )
        session.commit()

    with session_factory() as session:
        again = player_section_store.save_watch_player_section(
            session, watch_input, actor_id=7
        )
        session.commit()
        assert again == first

        mutated = _build_watch_input(
            run_id=run.id,
            section_result_id=sec_res.id,
            cand_id=cand_id,
            away_body="임의로 바꾼 다른 설명",
        )
        with pytest.raises(WriteConflict):
            player_section_store.save_watch_player_section(
                session, mutated, actor_id=7
            )
        session.rollback()

    with session_factory() as session:
        persisted = player_section_store.get_watch_player_section(session, sec_res.id)
        assert persisted == first


def test_storage_rejects_run_fixture_workflow_and_candidate_slot_conflicts(
    session_factory,
) -> None:
    """소유 실행·경기·섹션이나 다른 슬롯의 후보를 잘못 연결하면 엉뚱한 선수가 다른 경기에 노출된다."""
    with session_factory() as session:
        run_a = _create_run(session, fixture_id=9101, home_team_id=10, away_team_id=20)
        run_b = _create_run(session, fixture_id=9102, home_team_id=30, away_team_id=40)
        sec_a = _create_section_result(
            session,
            run_id=run_a.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        sec_b = _create_section_result(
            session,
            run_id=run_b.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        shared_cand_id = uuid.uuid4()
        player_section_store.save_watch_player_section(
            session,
            _build_watch_input(
                run_id=run_a.id, section_result_id=sec_a.id, cand_id=shared_cand_id
            ),
            actor_id=7,
        )
        session.commit()

    with session_factory() as session:
        # 존재하지 않는 section_result_id
        with pytest.raises(RunNotFound):
            player_section_store.save_watch_player_section(
                session,
                _build_watch_input(run_id=run_a.id, section_result_id=uuid.uuid4()),
            )

        # 소유 run_id 불일치
        with pytest.raises(WriteConflict):
            player_section_store.save_watch_player_section(
                session,
                _build_watch_input(
                    run_id=run_b.id,
                    section_result_id=sec_a.id,
                    fixture_id=9102,
                    home_team_id=30,
                    away_team_id=40,
                ),
            )

        # PreviewRun의 fixture_id 불일치
        with pytest.raises(WriteConflict):
            player_section_store.save_watch_player_section(
                session,
                _build_watch_input(
                    run_id=run_b.id,
                    section_result_id=sec_b.id,
                    fixture_id=9999,
                    home_team_id=30,
                    away_team_id=40,
                ),
            )

        # workflow_id 불일치(section_players 결과 ID에 injury 저장 시도)
        with pytest.raises(WriteConflict):
            player_section_store.save_injury_player_section(
                session,
                _build_injury_input(
                    run_id=run_b.id,
                    section_result_id=sec_b.id,
                    fixture_id=9102,
                    home_team_id=30,
                    away_team_id=40,
                ),
            )

        # 다른 섹션 결과/슬롯에 이미 연결된 후보 ID 재사용 충돌
        with pytest.raises(WriteConflict):
            player_section_store.save_watch_player_section(
                session,
                _build_watch_input(
                    run_id=run_b.id,
                    section_result_id=sec_b.id,
                    fixture_id=9102,
                    home_team_id=30,
                    away_team_id=40,
                    cand_id=shared_cand_id,
                ),
            )
        session.rollback()


def test_undo_removes_only_target_run_player_sections_and_candidates(
    session_factory,
) -> None:
    """실행 취소 시 새 세 테이블의 소유 행이 누락되면 찌꺼기 후보가 남고, 범위를 넘으면 다른 실행과 public 데이터가 지워진다."""
    with session_factory() as session:
        public_user_id = session.execute(
            text(
                "INSERT INTO public.app_user (email, password_hash, role, is_active) "
                "VALUES ('keep-me@example.test', 'hash', 'ADMIN', true) RETURNING id"
            )
        ).scalar_one()
        run_target = _create_run(session, fixture_id=9101)
        run_other = _create_run(session, fixture_id=9102, home_team_id=30, away_team_id=40)

        watch_target = _create_section_result(
            session,
            run_id=run_target.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        injury_target = _create_section_result(
            session,
            run_id=run_target.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY.value,
            output_contract_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        watch_other = _create_section_result(
            session,
            run_id=run_other.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )

        player_section_store.save_watch_player_section(
            session,
            _build_watch_input(run_id=run_target.id, section_result_id=watch_target.id),
            actor_id=7,
        )
        player_section_store.save_injury_player_section(
            session,
            _build_injury_input(run_id=run_target.id, section_result_id=injury_target.id),
            actor_id=7,
        )
        player_section_store.save_watch_player_section(
            session,
            _build_watch_input(
                run_id=run_other.id,
                section_result_id=watch_other.id,
                fixture_id=9102,
                home_team_id=30,
                away_team_id=40,
            ),
            actor_id=7,
        )
        session.commit()

    with session_factory() as session:
        report = store.undo_report(session, run_target.id)
        assert report["undo"]["can_cancel"] is True
        assert report["would_remove"][WATCH_PLAYERS_TABLE] == 1
        assert report["would_remove"][INJURY_PLAYERS_TABLE] == 1
        assert report["would_remove"][PLAYER_NAME_CANDIDATES_TABLE] == 2
        assert report["would_remove"]["preview_section_results"] == 2

        cancelled = store.cancel_run(
            session, run_target.id, actor_id=99, reason="테스트 정리"
        )
        session.commit()

    assert cancelled["removed"][WATCH_PLAYERS_TABLE] == 1
    assert cancelled["removed"][INJURY_PLAYERS_TABLE] == 1
    assert cancelled["removed"][PLAYER_NAME_CANDIDATES_TABLE] == 2
    assert cancelled["removed"]["preview_section_results"] == 2

    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(PreviewWatchPlayerSection)
                .where(PreviewWatchPlayerSection.run_id == run_target.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PreviewInjuryPlayerSection)
                .where(PreviewInjuryPlayerSection.run_id == run_target.id)
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PreviewPlayerNameCandidate)
                .where(PreviewPlayerNameCandidate.run_id == run_target.id)
            )
            == 0
        )
        # 다른 실행 결과와 public 계정은 그대로 보존된다.
        assert (
            player_section_store.get_watch_player_section(
                session, watch_other.id, run_id=run_other.id
            )
            is not None
        )
        user_email = session.execute(
            text("SELECT email FROM public.app_user WHERE id = :id"),
            {"id": public_user_id},
        ).scalar_one()
        assert user_email == "keep-me@example.test"

        audit_actions = [
            row.action
            for row in session.scalars(
                select(PreviewWriteAudit).where(PreviewWriteAudit.run_id == run_target.id)
            )
        ]
        assert "player_section_saved" in audit_actions
        assert "player_name_candidate_saved" in audit_actions
        assert "run_cancelled" in audit_actions


def test_undo_blocks_on_active_approval_and_foreign_composition_reference(
    session_factory,
) -> None:
    """활성 승인이나 다른 실행 구성본이 참조하는 결과를 undo로 지우면 승인 근거와 공개 구성본이 깨진다."""
    with session_factory() as session:
        run_a = _create_run(session, fixture_id=9201, mode=RunMode.LIVE)
        sec_a = _create_section_result(
            session,
            run_id=run_a.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            mode=RunMode.LIVE,
        )
        player_section_store.save_watch_player_section(
            session,
            _build_watch_input(
                run_id=run_a.id, section_result_id=sec_a.id, fixture_id=9201
            ),
            actor_id=7,
        )
        # 동일 실행에 자기 자신을 가리키는 구성본이 있어도 자기 자신의 취소는 막지 않아야 한다.
        store.save_composition(
            session,
            run_id=run_a.id,
            composition={
                "composition_id": "cmp-self",
                "section_result_ids": [str(sec_a.id)],
                "items": [{"result_id": str(sec_a.id), "run_id": str(run_a.id)}],
            },
            actor_id=7,
        )
        approvals.approve_section_version(
            session,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            run_id=run_a.id,
            section_result_id=sec_a.id,
            actor_id=7,
        )
        session.commit()

    with session_factory() as session:
        report = store.undo_report(session, run_a.id)
        assert report["undo"]["can_cancel"] is False
        assert "활성 섹션 승인" in (report["undo"]["blocked_reason"] or "")
        with pytest.raises(WriteConflict):
            store.cancel_run(session, run_a.id, actor_id=7, reason="승인 중 취소 시도")
        session.rollback()

    # 승인이 다른 실행으로 교체되어 비활성화되더라도, 다른 실행의 구성본이 참조 중이면 계속 차단된다.
    with session_factory() as session:
        run_b = _create_run(session, fixture_id=9201, mode=RunMode.LIVE)
        sec_b = _create_section_result(
            session,
            run_id=run_b.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            mode=RunMode.LIVE,
        )
        approvals.approve_section_version(
            session,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            run_id=run_b.id,
            section_result_id=sec_b.id,
            actor_id=7,
        )
        store.save_composition(
            session,
            run_id=run_b.id,
            composition={
                "composition_id": "cmp-foreign",
                "section_result_ids": [str(sec_a.id)],
                "items": [
                    {
                        "section_id": PlayerSectionWorkflowId.SECTION_PLAYERS.value,
                        "result_id": str(sec_a.id),
                        "run_id": str(run_a.id),
                    }
                ],
            },
            actor_id=7,
        )
        session.commit()

    with session_factory() as session:
        report_comp = store.undo_report(session, run_a.id)
        assert report_comp["undo"]["can_cancel"] is False
        assert "구성본" in (report_comp["undo"]["blocked_reason"] or "")
        with pytest.raises(WriteConflict):
            store.cancel_run(session, run_a.id, actor_id=7, reason="구성본 참조 중 취소")
        session.rollback()

    with session_factory() as session:
        assert (
            player_section_store.get_watch_player_section(session, sec_a.id) is not None
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(PreviewSectionApproval)
                .where(PreviewSectionApproval.section_result_id == sec_a.id)
            )
            == 1
        )


def test_legacy_section_results_are_preserved_without_fake_slot_rows(
    session_factory,
) -> None:
    """기존 mp04 섹션 결과를 보존하지 않거나 새 테이블로 덮어쓰면 이미 저장된 프리뷰가 깨진다."""
    with session_factory() as session:
        run = _create_run(session)
        legacy = _create_section_result(
            session,
            run_id=run.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=SECTION_RESULT_CONTRACT_VERSION,
            body="기존 마크다운 본문",
        )
        new_sec = _create_section_result(
            session,
            run_id=run.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            version=2,
            body="새 고정 슬롯 요약",
        )
        player_section_store.save_watch_player_section(
            session,
            _build_watch_input(run_id=run.id, section_result_id=new_sec.id),
            actor_id=7,
        )
        session.commit()

    with session_factory() as session:
        legacy_row = store.get_section_result(session, run.id, legacy.id)
        assert legacy_row is not None
        assert legacy_row.body == "기존 마크다운 본문"
        assert legacy_row.output_contract_version == SECTION_RESULT_CONTRACT_VERSION
        assert player_section_store.get_player_section(session, legacy.id) is None

        new_record = player_section_store.get_player_section(
            session,
            new_sec.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        )
        assert new_record is not None
        assert new_record.section_result_id == new_sec.id


def test_materialize_storage_input_is_idempotent_across_retries(
    session_factory,
) -> None:
    """같은 처리 결과를 두 번 materialize해 재저장할 때 후보 UUID가 흔들리면 재시도가 충돌로 실패한다."""
    processing = PlayerSectionProcessingResult(
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        fixture_id=9301,
        home_team_id=10,
        away_team_id=20,
        output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        home1=PendingWatchSlotDraft(
            player_id=None,
            original_name="Lucas Bergvall",
            name_ko="루카스 베리발",
            body="중원 전진 패스가 강점이다.",
            name_source=NameSource.AI_CANDIDATE,
            unresolved_reason="db_player_not_matched",
            evidence=("fact-bergvall",),
        ),
        attempts=(
            PlayerSectionAttemptTrace(
                attempt_ordinal=0,
                logical_call_id="call-watch-1",
                raw_text='{"items": []}',
            ),
        ),
        adopted_attempt_ordinal=0,
    )

    with session_factory() as session:
        run = _create_run(session, fixture_id=9301)
        sec_res = _create_section_result(
            session,
            run_id=run.id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS.value,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        first_input = processing.materialize_storage_input(
            section_result_id=sec_res.id, run_id=run.id
        )
        second_input = processing.materialize_storage_input(
            section_result_id=sec_res.id, run_id=run.id
        )
        assert isinstance(first_input, WatchPlayerSectionInput)
        assert isinstance(second_input, WatchPlayerSectionInput)

        saved_first = player_section_store.save_watch_player_section(
            session, first_input, actor_id=7
        )
        saved_second = player_section_store.save_watch_player_section(
            session, second_input, actor_id=7
        )
        session.commit()

    assert saved_first == saved_second
    assert saved_first.home1 is not None
    assert saved_first.home1.evidence == ("fact-bergvall",)
