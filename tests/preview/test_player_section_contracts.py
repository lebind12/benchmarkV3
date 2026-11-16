"""NS-00 선수 섹션 공통 계약 순수 단위 테스트(DB 픽스처 미사용)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.preview.contracts import ContractError, SECTION_RESULT_CONTRACT_VERSION
from app.preview.player_section_contracts import (
    CandidateReviewStatus,
    CandidateSource,
    INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
    InjuryPlayerSectionInput,
    InjuryPlayerSlot,
    NameSource,
    PendingInjurySlotDraft,
    PendingWatchSlotDraft,
    PlayerNameCandidateInput,
    PlayerSectionAttemptTrace,
    PlayerSectionProcessingResult,
    PlayerSectionWorkflowId,
    RegenerationReason,
    SlotKey,
    SlotResolutionStatus,
    UnplacedPlayerDiagnostic,
    UnplacedReason,
    WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
    WatchPlayerSectionInput,
    WatchPlayerSlot,
    project_slot,
)


def test_watch_section_accepts_resolved_unresolved_and_empty_slots() -> None:
    """실제 경기에서 1팀 1명만 채워진 빈 자리, DB 확인 선수, 미확인 AI 후보를 함께 저장·투영할 수 있어야 한다."""
    run_id = uuid.uuid4()
    section_result_id = uuid.uuid4()
    cand_away1_id = uuid.uuid4()

    home1 = WatchPlayerSlot(
        player_id=101,
        original_name="Son Heung-Min",
        name_ko="손흥민",
        body="직전 3경기 연속 공격포인트로 홈 측 핵심 변수다.",
        name_source=NameSource.DB_KO,
        evidence=({"kind": "api", "fact_id": "f1"},),
    )
    away1 = WatchPlayerSlot(
        player_id=None,
        original_name="Jhon Duran",
        name_ko="존 두란",
        body="교체 투입 빈도가 높아 후반 변수가 될 수 있다.",
        name_source=NameSource.AI_CANDIDATE,
        unresolved_reason="db_player_not_matched",
        translation_candidate_id=cand_away1_id,
    )
    cand_away1 = PlayerNameCandidateInput(
        id=cand_away1_id,
        run_id=run_id,
        section_result_id=section_result_id,
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        slot_key=SlotKey.AWAY1,
        fixture_id=9001,
        team_id=20,
        player_id=None,
        original_name="Jhon Duran",
        candidate_name_ko="존 두란",
    )

    section = WatchPlayerSectionInput(
        section_result_id=section_result_id,
        run_id=run_id,
        fixture_id=9001,
        home_team_id=10,
        away_team_id=20,
        home1=home1,
        home2=None,
        away1=away1,
        away2=None,
        home_etc=None,
        away_etc=None,
        candidates=(cand_away1,),
    )

    columns = {**home1.to_columns(SlotKey.HOME1), **away1.to_columns(SlotKey.AWAY1)}
    columns.update(WatchPlayerSlot.from_columns(SlotKey.HOME2, {}) or {})
    assert WatchPlayerSlot.from_columns(SlotKey.HOME1, columns) == home1
    assert WatchPlayerSlot.from_columns(SlotKey.HOME2, {}) is None

    home1_view = project_slot(
        SlotKey.HOME1,
        section.home1,
        external_player_id=186,
        photo_url="https://media.api-sports.io/football/players/186.png",
    )
    away1_view = project_slot(
        SlotKey.AWAY1,
        section.away1,
        candidate_review_status=CandidateReviewStatus.PENDING,
    )
    empty_view = project_slot(SlotKey.HOME2, section.home2)

    assert home1_view.resolution_status == SlotResolutionStatus.RESOLVED
    assert home1_view.display_name == "손흥민"
    assert away1_view.resolution_status == SlotResolutionStatus.UNRESOLVED
    assert away1_view.external_player_id is None
    assert away1_view.photo_url is None
    assert empty_view.resolution_status == SlotResolutionStatus.EMPTY
    assert section.canonical_dict()["home_etc"] is None
    assert SECTION_RESULT_CONTRACT_VERSION == "mp04-section-result-1"
    assert section.output_contract_version != SECTION_RESULT_CONTRACT_VERSION


def test_processing_result_materializes_injury_storage_preserving_unknown_status() -> None:
    """부상 섹션은 미확정(unknown) 상태를 결장 확정으로 승격하지 않고 그대로 저장·조회 계약으로 구체화해야 한다."""
    run_id = uuid.uuid4()
    section_result_id = uuid.uuid4()
    cand_id = uuid.uuid4()

    processing = PlayerSectionProcessingResult(
        workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY,
        fixture_id=9002,
        home_team_id=11,
        away_team_id=22,
        output_contract_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
        home1=PendingInjurySlotDraft(
            player_id=202,
            original_name="Micky van de Ven",
            name_ko="미키 판 더 펜",
            body="햄스트링 관리 상태로 출전 여부가 불투명하다.",
            name_source=NameSource.AI_CANDIDATE,
            status="unknown",
            injury="Hamstring",
            importance="수비 라인 속도 대응에 핵심이다.",
        ),
        regeneration_count=1,
        module_attempt_count=2,
        adopted_attempt_ordinal=1,
        attempts=(
            PlayerSectionAttemptTrace(
                attempt_ordinal=0,
                logical_call_id="call-avail-1",
                raw_text="{}",
                regeneration_triggered=True,
                regeneration_reason=RegenerationReason.MISSING_BODY,
            ),
            PlayerSectionAttemptTrace(
                attempt_ordinal=1,
                logical_call_id="call-avail-1",
                raw_text='{"items": []}',
                parsed_json={"items": []},
            ),
        ),
        unplaced_items=(
            UnplacedPlayerDiagnostic(
                original_name="Unknown Reserve",
                team_hint=None,
                reason=UnplacedReason.TEAM_UNRESOLVED,
            ),
        ),
    )

    storage_input = processing.materialize_storage_input(
        section_result_id=section_result_id,
        run_id=run_id,
        candidate_id_factory=lambda _slot: cand_id,
    )
    assert isinstance(storage_input, InjuryPlayerSectionInput)
    assert storage_input.home1 is not None
    assert storage_input.home1.status == "unknown"
    assert storage_input.home1.translation_candidate_id == cand_id
    assert len(storage_input.candidates) == 1
    assert storage_input.candidates[0].source == CandidateSource.AI_TRANSLATION
    assert storage_input.candidates[0].team_id == 11


@pytest.mark.parametrize(
    "kwargs",
    [
        # bool을 정수 ID로 오인해 엉뚱한 선수를 연결하면 안 된다.
        dict(
            player_id=True,
            original_name="Son",
            name_ko="손흥민",
            body="핵심 공격수",
            name_source=NameSource.DB_KO,
        ),
        # 미확인 선수인데 미연결 사유가 없으면 관리자가 원인을 파악할 수 없다.
        dict(
            player_id=None,
            original_name="Unknown",
            name_ko="미확인",
            body="본문",
            name_source=NameSource.AI_CANDIDATE,
            unresolved_reason=None,
            translation_candidate_id=uuid.uuid4(),
        ),
        # db_ko는 DB에서 확인된 한글명이므로 AI 후보를 만들면 중복 검수 항목이 생긴다.
        dict(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="본문",
            name_source=NameSource.DB_KO,
            translation_candidate_id=uuid.uuid4(),
        ),
        # 확인된 선수에 unresolved_reason이 남으면 카드 상태 표시가 모순된다.
        dict(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="본문",
            name_source=NameSource.DB_KO,
            unresolved_reason="db_player_not_matched",
        ),
        # 설명 본문이 비어 있으면 독자에게 빈 카드가 노출된다.
        dict(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="   ",
            name_source=NameSource.DB_KO,
        ),
    ],
)
def test_watch_slot_rejects_impossible_combinations(kwargs: dict) -> None:
    """잘못된 ID 타입·출처·미연결 사유·빈 본문 조합은 저장 전에 즉시 거부되어 손상된 카드 저장을 막아야 한다."""
    with pytest.raises(ContractError):
        WatchPlayerSlot(**kwargs)


def test_partial_null_slot_columns_and_non_null_etc_are_rejected() -> None:
    """부분 NULL 슬롯이나 허용되지 않은 ETC 텍스트가 있으면 빈 자리와 미확인 자리가 섞이는 것을 막아야 한다."""
    with pytest.raises(ContractError):
        WatchPlayerSlot.from_columns(
            SlotKey.HOME1,
            {"home1_original_name": "Son", "home1_name_ko": None, "home1_body": None},
        )

    home1 = WatchPlayerSlot(
        player_id=101,
        original_name="Son",
        name_ko="손흥민",
        body="득점 기대",
        name_source=NameSource.DB_KO,
    )
    with pytest.raises(ContractError):
        WatchPlayerSectionInput(
            section_result_id=uuid.uuid4(),
            run_id=uuid.uuid4(),
            fixture_id=9001,
            home_team_id=10,
            away_team_id=20,
            home1=home1,
            home_etc="초과 선수",  # type: ignore[arg-type]
        )


def test_section_rejects_slot_gaps_duplicate_players_and_candidate_ownership_mismatch() -> None:
    """1번 자리를 비운 채 2번만 채우거나 중복 선수·다른 실행의 번역 후보를 연결하면 거부해야 한다."""
    run_id = uuid.uuid4()
    section_result_id = uuid.uuid4()
    cand_id = uuid.uuid4()

    slot_a = WatchPlayerSlot(
        player_id=101,
        original_name="Son",
        name_ko="손흥민",
        body="첫 번째 설명",
        name_source=NameSource.DB_KO,
    )
    slot_b = WatchPlayerSlot(
        player_id=101,
        original_name="Son",
        name_ko="손흥민",
        body="중복 선수 설명",
        name_source=NameSource.DB_KO,
    )
    slot_ai = WatchPlayerSlot(
        player_id=None,
        original_name="Pedro Porro",
        name_ko="페드로 포로",
        body="측면 전개",
        name_source=NameSource.AI_CANDIDATE,
        unresolved_reason="db_player_not_matched",
        translation_candidate_id=cand_id,
    )

    # home1 비어 있고 home2만 채운 경우
    with pytest.raises(ContractError):
        WatchPlayerSectionInput(
            section_result_id=section_result_id,
            run_id=run_id,
            fixture_id=9001,
            home_team_id=10,
            away_team_id=20,
            home1=None,
            home2=slot_a,
        )

    # 동일 player_id 중복
    with pytest.raises(ContractError):
        WatchPlayerSectionInput(
            section_result_id=section_result_id,
            run_id=run_id,
            fixture_id=9001,
            home_team_id=10,
            away_team_id=20,
            home1=slot_a,
            away1=slot_b,
        )

    # 후보 소유 run_id 불일치
    mismatched_cand = PlayerNameCandidateInput(
        id=cand_id,
        run_id=uuid.uuid4(),
        section_result_id=section_result_id,
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        slot_key=SlotKey.HOME1,
        fixture_id=9001,
        team_id=10,
        player_id=None,
        original_name="Pedro Porro",
        candidate_name_ko="페드로 포로",
    )
    with pytest.raises(ContractError):
        WatchPlayerSectionInput(
            section_result_id=section_result_id,
            run_id=run_id,
            fixture_id=9001,
            home_team_id=10,
            away_team_id=20,
            home1=slot_ai,
            candidates=(mismatched_cand,),
        )


def test_injury_slot_budget_and_projection_guards() -> None:
    """부상 설명 누락·재생성 1회 초과·모듈 3회 초과·미확인 선수 사진 투영은 모두 차단되어야 한다."""
    with pytest.raises(ContractError):
        InjuryPlayerSlot(
            player_id=303,
            original_name="Richarlison",
            name_ko="히샤를리송",
            body="출전 불확실",
            name_source=NameSource.DB_KO,
            status="doubtful",
            injury=None,
            importance=None,
        )

    with pytest.raises(ContractError):
        PlayerSectionProcessingResult(
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
            fixture_id=9003,
            home_team_id=10,
            away_team_id=20,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            home1=PendingWatchSlotDraft(
                player_id=101,
                original_name="Son",
                name_ko="손흥민",
                body="설명",
                name_source=NameSource.DB_KO,
            ),
            regeneration_count=2,
            module_attempt_count=3,
            adopted_attempt_ordinal=2,
        )

    with pytest.raises(ContractError):
        PlayerSectionAttemptTrace(
            attempt_ordinal=3,
            logical_call_id="call-over-budget",
        )

    unresolved = WatchPlayerSlot(
        player_id=None,
        original_name="Unmatched Player",
        name_ko="미확인 선수",
        body="후보 설명",
        name_source=NameSource.AI_CANDIDATE,
        unresolved_reason="db_player_not_matched",
        translation_candidate_id=uuid.uuid4(),
    )
    with pytest.raises(ContractError):
        project_slot(
            SlotKey.HOME1,
            unresolved,
            external_player_id=999999,
            photo_url="https://media.api-sports.io/football/players/999999.png",
        )


def test_attempt_ordinal_uses_zero_based_provider_bookkeeping() -> None:
    """실제 provider·PreviewAttempt 장부와 같은 0 기반 시도 번호(0, 1, 2)만 허용돼야 관리자 진단이 저장 장부와 어긋나지 않는다."""
    processing = PlayerSectionProcessingResult(
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        fixture_id=9010,
        home_team_id=10,
        away_team_id=20,
        output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        home1=PendingWatchSlotDraft(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="선제골 후보",
            name_source=NameSource.DB_KO,
        ),
        regeneration_count=1,
        module_attempt_count=3,
        adopted_attempt_ordinal=2,
        attempts=(
            PlayerSectionAttemptTrace(attempt_ordinal=0, logical_call_id="call-p-1"),
            PlayerSectionAttemptTrace(
                attempt_ordinal=1,
                logical_call_id="call-p-1",
                regeneration_triggered=True,
                regeneration_reason=RegenerationReason.DUPLICATE_PLAYER,
            ),
            PlayerSectionAttemptTrace(attempt_ordinal=2, logical_call_id="call-p-1"),
        ),
    )
    assert [t.attempt_ordinal for t in processing.attempts] == [0, 1, 2]
    assert processing.adopted_attempt_ordinal == 2

    with pytest.raises(ContractError):
        PlayerSectionAttemptTrace(attempt_ordinal=-1, logical_call_id="call-p-1")

    with pytest.raises(ContractError):
        PlayerSectionProcessingResult(
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
            fixture_id=9010,
            home_team_id=10,
            away_team_id=20,
            output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            module_attempt_count=3,
            adopted_attempt_ordinal=3,
        )


def test_string_source_id_evidence_is_preserved_without_wrapping() -> None:
    """bundle_sections._clean_evidence가 만든 문자열 출처 ID가 저장·투영 과정에서 거부되거나 임의 dict로 변형되지 않아야 독자/진단 근거가 유지된다."""
    run_id = uuid.uuid4()
    section_result_id = uuid.uuid4()
    processing = PlayerSectionProcessingResult(
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        fixture_id=9011,
        home_team_id=10,
        away_team_id=20,
        output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        home1=PendingWatchSlotDraft(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="최근 득점 페이스가 좋다.",
            name_source=NameSource.DB_KO,
            evidence=("api:fact-1", {"kind": "web", "url": "https://example.com/a"}),
        ),
    )
    stored = processing.materialize_storage_input(
        section_result_id=section_result_id,
        run_id=run_id,
    )
    assert isinstance(stored, WatchPlayerSectionInput)
    assert stored.home1 is not None
    assert stored.home1.evidence == ("api:fact-1", {"kind": "web", "url": "https://example.com/a"})

    cols = stored.home1.to_columns(SlotKey.HOME1)
    assert cols["home1_evidence"] == ["api:fact-1", {"kind": "web", "url": "https://example.com/a"}]
    assert WatchPlayerSlot.from_columns(SlotKey.HOME1, cols) == stored.home1

    projected = project_slot(SlotKey.HOME1, stored.home1)
    assert projected.evidence == ("api:fact-1", {"kind": "web", "url": "https://example.com/a"})

    with pytest.raises(ContractError):
        WatchPlayerSlot(
            player_id=101,
            original_name="Son",
            name_ko="손흥민",
            body="설명",
            name_source=NameSource.DB_KO,
            evidence=("   ",),
        )


def test_materialize_storage_input_is_deterministic_per_result_and_slot() -> None:
    """같은 처리 결과를 같은 run_id·section_result_id로 재구체화할 때 후보 ID와 동등성 키가 달라지면 멱등 재저장이 불필요한 충돌로 실패한다."""
    run_id = uuid.uuid4()
    section_result_id = uuid.uuid4()
    other_section_result_id = uuid.uuid4()

    processing = PlayerSectionProcessingResult(
        workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
        fixture_id=9012,
        home_team_id=10,
        away_team_id=20,
        output_contract_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        home1=PendingWatchSlotDraft(
            player_id=None,
            original_name="Dejan Kulusevski",
            name_ko="데얀 쿨루셉스키",
            body="오른쪽 측면 창의성 공급원이다.",
            name_source=NameSource.AI_CANDIDATE,
            unresolved_reason="db_player_not_matched",
        ),
        away1=PendingWatchSlotDraft(
            player_id=None,
            original_name="Morgan Rogers",
            name_ko="모건 로저스",
            body="전환 속도가 빠른 공격 자원이다.",
            name_source=NameSource.AI_CANDIDATE,
            unresolved_reason="db_player_not_matched",
        ),
    )

    first = processing.materialize_storage_input(
        section_result_id=section_result_id,
        run_id=run_id,
    )
    second = processing.materialize_storage_input(
        section_result_id=section_result_id,
        run_id=run_id,
    )
    different_result = processing.materialize_storage_input(
        section_result_id=other_section_result_id,
        run_id=run_id,
    )

    assert first == second
    assert first.canonical_dict() == second.canonical_dict()
    assert first.home1 is not None and first.away1 is not None
    assert first.home1.translation_candidate_id != first.away1.translation_candidate_id
    assert different_result.home1 is not None
    assert first.home1.translation_candidate_id != different_result.home1.translation_candidate_id

    shared_id = uuid.uuid4()
    with pytest.raises(ContractError):
        processing.materialize_storage_input(
            section_result_id=section_result_id,
            run_id=run_id,
            candidate_id_factory=lambda _slot: shared_id,
        )
