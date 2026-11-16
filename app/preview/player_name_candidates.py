"""NS-01 실행·섹션 결과·슬롯 소유 AI 한글명 번역 후보 저장·조회 모듈.

후보는 실행 간 자동 병합이나 공유를 하지 않는 섹션 결과/슬롯 단위 스냅샷이다.
조회 시 원래 섹션 슬롯의 `unresolved_reason`을 연결해 반환한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.preview.contracts import ContractError
from app.preview.models import PreviewWriteAudit
from app.preview.player_section_contracts import (
    PLAYER_NAME_CANDIDATES_TABLE,
    CandidateReviewStatus,
    CandidateSource,
    PlayerNameCandidateInput,
    PlayerNameCandidateRecord,
    PlayerSectionWorkflowId,
    SlotKey,
)
from app.preview.player_section_models import (
    PreviewInjuryPlayerSection,
    PreviewPlayerNameCandidate,
    PreviewWatchPlayerSection,
)
from app.preview.store import WriteConflict

__all__ = [
    "get_candidate",
    "list_candidates_for_run",
    "list_candidates_for_section_result",
    "list_pending_candidates",
]


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _load_slot_unresolved_reasons(
    session: Session,
    rows: Sequence[PreviewPlayerNameCandidate],
) -> dict[tuple[uuid.UUID, str], str | None]:
    """후보 행들과 짝지어진 섹션 슬롯의 미연결 사유를 일괄 조회한다."""
    watch_ids = {
        row.section_result_id
        for row in rows
        if row.workflow_id == PlayerSectionWorkflowId.SECTION_PLAYERS.value
    }
    injury_ids = {
        row.section_result_id
        for row in rows
        if row.workflow_id == PlayerSectionWorkflowId.SECTION_AVAILABILITY.value
    }

    sections_by_result: dict[
        uuid.UUID, PreviewWatchPlayerSection | PreviewInjuryPlayerSection
    ] = {}
    if watch_ids:
        for sec in session.scalars(
            select(PreviewWatchPlayerSection).where(
                PreviewWatchPlayerSection.section_result_id.in_(watch_ids)
            )
        ):
            sections_by_result[sec.section_result_id] = sec
    if injury_ids:
        for sec in session.scalars(
            select(PreviewInjuryPlayerSection).where(
                PreviewInjuryPlayerSection.section_result_id.in_(injury_ids)
            )
        ):
            sections_by_result[sec.section_result_id] = sec

    reasons: dict[tuple[uuid.UUID, str], str | None] = {}
    for row in rows:
        sec = sections_by_result.get(row.section_result_id)
        if sec is None:
            reasons[(row.section_result_id, row.slot_key)] = None
            continue
        reasons[(row.section_result_id, row.slot_key)] = getattr(
            sec, f"{row.slot_key}_unresolved_reason", None
        )
    return reasons


def to_candidate_record(
    row: PreviewPlayerNameCandidate,
    *,
    unresolved_reason: str | None = None,
) -> PlayerNameCandidateRecord:
    return PlayerNameCandidateRecord(
        id=row.id,
        run_id=row.run_id,
        section_result_id=row.section_result_id,
        workflow_id=PlayerSectionWorkflowId(row.workflow_id),
        slot_key=SlotKey(row.slot_key),
        fixture_id=int(row.fixture_id),
        team_id=int(row.team_id) if row.team_id is not None else None,
        player_id=int(row.player_id) if row.player_id is not None else None,
        original_name=row.original_name,
        candidate_name_ko=row.candidate_name_ko,
        source=CandidateSource(row.source),
        review_status=CandidateReviewStatus(row.review_status),
        created_at=_ensure_aware(row.created_at),
        unresolved_reason=unresolved_reason,
    )


def _to_candidate_records(
    session: Session,
    rows: Sequence[PreviewPlayerNameCandidate],
) -> tuple[PlayerNameCandidateRecord, ...]:
    if not rows:
        return ()
    reasons = _load_slot_unresolved_reasons(session, rows)
    return tuple(
        to_candidate_record(
            row,
            unresolved_reason=reasons.get((row.section_result_id, row.slot_key)),
        )
        for row in rows
    )


def save_section_candidates(
    session: Session,
    *,
    section_result_id: uuid.UUID,
    candidates: Iterable[PlayerNameCandidateInput],
    moment: datetime,
    actor_id: int,
) -> list[PreviewPlayerNameCandidate]:
    """섹션 저장 트랜잭션 안에서 번역 후보를 검증하고 기록한다. commit하지 않는다."""
    cand_list = list(candidates)

    existing_for_result = list(
        session.scalars(
            select(PreviewPlayerNameCandidate).where(
                PreviewPlayerNameCandidate.section_result_id == section_result_id
            )
        )
    )
    if existing_for_result:
        raise WriteConflict(
            f"section_result_id={section_result_id}에 이미 번역 후보가 존재합니다."
        )

    if not cand_list:
        return []

    candidate_ids = [cand.id for cand in cand_list]
    colliding = list(
        session.scalars(
            select(PreviewPlayerNameCandidate).where(
                PreviewPlayerNameCandidate.id.in_(candidate_ids)
            )
        )
    )
    if colliding:
        first = colliding[0]
        raise WriteConflict(
            f"번역 후보 ID({first.id})가 이미 다른 결과({first.section_result_id})의 "
            f"슬롯({first.slot_key})에 연결되어 있습니다."
        )

    created_rows: list[PreviewPlayerNameCandidate] = []
    for cand in sorted(cand_list, key=lambda item: item.slot_key.value):
        row = PreviewPlayerNameCandidate(
            id=cand.id,
            run_id=cand.run_id,
            section_result_id=cand.section_result_id,
            workflow_id=cand.workflow_id.value,
            slot_key=cand.slot_key.value,
            fixture_id=cand.fixture_id,
            team_id=cand.team_id,
            player_id=cand.player_id,
            original_name=cand.original_name,
            candidate_name_ko=cand.candidate_name_ko,
            source=cand.source.value,
            review_status=cand.review_status.value,
            created_at=moment,
        )
        session.add(row)
        created_rows.append(row)

    session.flush()
    for row in created_rows:
        session.add(
            PreviewWriteAudit(
                run_id=row.run_id,
                actor_id=actor_id,
                action="player_name_candidate_saved",
                target_table=PLAYER_NAME_CANDIDATES_TABLE,
                target_id=str(row.id),
                detail={
                    "section_result_id": str(row.section_result_id),
                    "workflow_id": row.workflow_id,
                    "slot_key": row.slot_key,
                    "player_id": row.player_id,
                    "review_status": row.review_status,
                },
            )
        )
    return created_rows


def get_candidate(
    session: Session,
    candidate_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
) -> PlayerNameCandidateRecord | None:
    """후보 ID로 단건 조회하며, 원래 섹션 슬롯의 미연결 사유를 연결한다."""
    row = session.get(PreviewPlayerNameCandidate, candidate_id)
    if row is None:
        return None
    if run_id is not None and row.run_id != run_id:
        return None
    return _to_candidate_records(session, [row])[0]


def list_candidates_for_section_result(
    session: Session,
    section_result_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
) -> tuple[PlayerNameCandidateRecord, ...]:
    """특정 섹션 결과가 소유한 번역 후보를 슬롯 순으로 반환한다."""
    stmt = (
        select(PreviewPlayerNameCandidate)
        .where(PreviewPlayerNameCandidate.section_result_id == section_result_id)
        .order_by(PreviewPlayerNameCandidate.slot_key, PreviewPlayerNameCandidate.id)
    )
    if run_id is not None:
        stmt = stmt.where(PreviewPlayerNameCandidate.run_id == run_id)
    rows = list(session.scalars(stmt))
    return _to_candidate_records(session, rows)


def list_candidates_for_run(
    session: Session,
    run_id: uuid.UUID,
    *,
    review_status: CandidateReviewStatus | str | None = None,
) -> tuple[PlayerNameCandidateRecord, ...]:
    """한 실행이 소유한 번역 후보 목록을 반환한다."""
    stmt = (
        select(PreviewPlayerNameCandidate)
        .where(PreviewPlayerNameCandidate.run_id == run_id)
        .order_by(
            PreviewPlayerNameCandidate.created_at,
            PreviewPlayerNameCandidate.section_result_id,
            PreviewPlayerNameCandidate.slot_key,
        )
    )
    if review_status is not None:
        try:
            status_enum = CandidateReviewStatus(review_status)
        except ValueError as exc:
            raise ContractError(
                f"허용되지 않은 review_status입니다: {review_status!r}"
            ) from exc
        stmt = stmt.where(PreviewPlayerNameCandidate.review_status == status_enum.value)
    rows = list(session.scalars(stmt))
    return _to_candidate_records(session, rows)


def list_pending_candidates(
    session: Session,
    *,
    run_id: uuid.UUID | None = None,
    fixture_id: int | None = None,
    workflow_id: PlayerSectionWorkflowId | str | None = None,
    limit: int = 100,
) -> tuple[PlayerNameCandidateRecord, ...]:
    """검수 대기(`pending`) 상태의 AI 번역 후보를 즉시 조회한다."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ContractError(f"limit는 양의 정수여야 합니다: {limit!r}")
    stmt = (
        select(PreviewPlayerNameCandidate)
        .where(
            PreviewPlayerNameCandidate.review_status
            == CandidateReviewStatus.PENDING.value
        )
        .order_by(
            PreviewPlayerNameCandidate.created_at.desc(),
            PreviewPlayerNameCandidate.slot_key,
        )
        .limit(limit)
    )
    if run_id is not None:
        stmt = stmt.where(PreviewPlayerNameCandidate.run_id == run_id)
    if fixture_id is not None:
        if isinstance(fixture_id, bool) or not isinstance(fixture_id, int) or fixture_id <= 0:
            raise ContractError(f"fixture_id는 양의 정수여야 합니다: {fixture_id!r}")
        stmt = stmt.where(PreviewPlayerNameCandidate.fixture_id == fixture_id)
    if workflow_id is not None:
        try:
            wf = PlayerSectionWorkflowId(workflow_id)
        except ValueError as exc:
            raise ContractError(
                f"허용되지 않은 workflow_id입니다: {workflow_id!r}"
            ) from exc
        stmt = stmt.where(PreviewPlayerNameCandidate.workflow_id == wf.value)
    rows = list(session.scalars(stmt))
    return _to_candidate_records(session, rows)
