"""NS-01 선수 섹션(주목 선수·부상/결장) 고정 슬롯 저장·재조회 저장소.

호출자의 SQLAlchemy 세션을 그대로 사용하며 내부에서 `commit()`하지 않는다.
부모 `preview_section_results` 및 번역 후보 저장과 같은 트랜잭션 안에서
원자적으로 성공하거나 실패한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.preview import player_name_candidates as candidate_store
from app.preview.contracts import ContractError
from app.preview.models import PreviewRun, PreviewSectionResult, PreviewWriteAudit
from app.preview.player_section_contracts import (
    FIXED_SLOT_KEYS,
    INJURY_PLAYERS_TABLE,
    INJURY_SLOT_COLUMN_SUFFIXES,
    WATCH_PLAYERS_TABLE,
    WATCH_SLOT_COLUMN_SUFFIXES,
    InjuryPlayerSectionInput,
    InjuryPlayerSectionRecord,
    InjuryPlayerSlot,
    PlayerNameCandidateRecord,
    PlayerSectionWorkflowId,
    SlotKey,
    WatchPlayerSectionInput,
    WatchPlayerSectionRecord,
    WatchPlayerSlot,
    _slot_column_dict,
)
from app.preview.player_section_models import (
    PreviewInjuryPlayerSection,
    PreviewPlayerNameCandidate,
    PreviewWatchPlayerSection,
)
from app.preview.store import RunNotFound, WriteConflict

__all__ = [
    "get_injury_player_section",
    "get_player_section",
    "get_watch_player_section",
    "save_injury_player_section",
    "save_player_section",
    "save_watch_player_section",
]


@dataclass(frozen=True)
class _SectionStorageSpec:
    workflow_id: PlayerSectionWorkflowId
    table_name: str
    model_cls: type[PreviewWatchPlayerSection] | type[PreviewInjuryPlayerSection]
    input_cls: type[WatchPlayerSectionInput] | type[InjuryPlayerSectionInput]
    record_cls: type[WatchPlayerSectionRecord] | type[InjuryPlayerSectionRecord]
    slot_cls: type[WatchPlayerSlot] | type[InjuryPlayerSlot]
    slot_suffixes: tuple[str, ...]
    include_injury_fields: bool
    include_etc_fields: bool


_WATCH_SPEC = _SectionStorageSpec(
    workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
    table_name=WATCH_PLAYERS_TABLE,
    model_cls=PreviewWatchPlayerSection,
    input_cls=WatchPlayerSectionInput,
    record_cls=WatchPlayerSectionRecord,
    slot_cls=WatchPlayerSlot,
    slot_suffixes=WATCH_SLOT_COLUMN_SUFFIXES,
    include_injury_fields=False,
    include_etc_fields=True,
)

_INJURY_SPEC = _SectionStorageSpec(
    workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY,
    table_name=INJURY_PLAYERS_TABLE,
    model_cls=PreviewInjuryPlayerSection,
    input_cls=InjuryPlayerSectionInput,
    record_cls=InjuryPlayerSectionRecord,
    slot_cls=InjuryPlayerSlot,
    slot_suffixes=INJURY_SLOT_COLUMN_SUFFIXES,
    include_injury_fields=True,
    include_etc_fields=False,
)

_SPECS_BY_WORKFLOW: dict[PlayerSectionWorkflowId, _SectionStorageSpec] = {
    PlayerSectionWorkflowId.SECTION_PLAYERS: _WATCH_SPEC,
    PlayerSectionWorkflowId.SECTION_AVAILABILITY: _INJURY_SPEC,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _extract_row_slot_columns(
    row: PreviewWatchPlayerSection | PreviewInjuryPlayerSection,
    slot_prefix: str,
    suffixes: tuple[str, ...],
) -> dict[str, Any]:
    return {
        f"{slot_prefix}_{suffix}": getattr(row, f"{slot_prefix}_{suffix}")
        for suffix in suffixes
    }


def _candidate_canonical_dict(cand: PlayerNameCandidateRecord) -> dict[str, Any]:
    return {
        "id": str(cand.id),
        "run_id": str(cand.run_id),
        "section_result_id": str(cand.section_result_id),
        "workflow_id": cand.workflow_id.value,
        "slot_key": cand.slot_key.value,
        "fixture_id": cand.fixture_id,
        "team_id": cand.team_id,
        "player_id": cand.player_id,
        "original_name": cand.original_name,
        "candidate_name_ko": cand.candidate_name_ko,
        "source": cand.source.value,
        "review_status": cand.review_status.value,
    }


def _record_canonical_dict(
    record: WatchPlayerSectionRecord | InjuryPlayerSectionRecord,
    spec: _SectionStorageSpec,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "section_result_id": str(record.section_result_id),
        "run_id": str(record.run_id),
        "fixture_id": record.fixture_id,
        "home_team_id": record.home_team_id,
        "away_team_id": record.away_team_id,
        "output_contract_version": record.output_contract_version,
    }
    if spec.include_etc_fields:
        assert isinstance(record, WatchPlayerSectionRecord)
        payload["home_etc"] = record.home_etc
        payload["away_etc"] = record.away_etc
    for key, slot in record.slots().items():
        payload.update(
            _slot_column_dict(
                key.value, slot, include_injury_fields=spec.include_injury_fields
            )
        )
    payload["candidates"] = [
        _candidate_canonical_dict(c)
        for c in sorted(record.candidates, key=lambda item: item.slot_key.value)
    ]
    return payload


def _row_to_record(
    session: Session,
    row: PreviewWatchPlayerSection | PreviewInjuryPlayerSection,
    spec: _SectionStorageSpec,
) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord:
    slots: dict[str, Any] = {}
    for prefix in FIXED_SLOT_KEYS:
        slot_key = SlotKey(prefix)
        columns = _extract_row_slot_columns(row, prefix, spec.slot_suffixes)
        slots[prefix] = spec.slot_cls.from_columns(slot_key, columns)

    cand_rows = list(
        session.scalars(
            select(PreviewPlayerNameCandidate)
            .where(PreviewPlayerNameCandidate.section_result_id == row.section_result_id)
            .order_by(
                PreviewPlayerNameCandidate.slot_key, PreviewPlayerNameCandidate.id
            )
        )
    )
    candidates = tuple(
        candidate_store.to_candidate_record(
            cand_row,
            unresolved_reason=(
                slots[cand_row.slot_key].unresolved_reason
                if cand_row.slot_key in slots and slots[cand_row.slot_key] is not None
                else None
            ),
        )
        for cand_row in cand_rows
    )

    kwargs: dict[str, Any] = {
        "section_result_id": row.section_result_id,
        "run_id": row.run_id,
        "fixture_id": int(row.fixture_id),
        "home_team_id": int(row.home_team_id) if row.home_team_id is not None else None,
        "away_team_id": int(row.away_team_id) if row.away_team_id is not None else None,
        "output_contract_version": row.output_contract_version,
        "created_at": _ensure_aware(row.created_at),
        "candidates": candidates,
        **slots,
    }
    if spec.include_etc_fields:
        assert isinstance(row, PreviewWatchPlayerSection)
        kwargs["home_etc"] = row.home_etc
        kwargs["away_etc"] = row.away_etc

    return spec.record_cls(**kwargs)


def _validate_parent_ownership(
    session: Session,
    section_input: WatchPlayerSectionInput | InjuryPlayerSectionInput,
    spec: _SectionStorageSpec,
) -> None:
    run = session.get(PreviewRun, section_input.run_id)
    if run is None:
        raise RunNotFound(f"run {section_input.run_id} not found")
    if run.cancelled_at is not None:
        raise WriteConflict("취소된 실행에는 선수 섹션 결과를 저장할 수 없습니다.")
    if run.fixture_id is not None and int(run.fixture_id) != section_input.fixture_id:
        raise WriteConflict(
            f"실행({run.id})의 fixture_id({run.fixture_id})가 "
            f"저장 입력({section_input.fixture_id})과 다릅니다."
        )
    if (
        run.home_team_id is not None
        and section_input.home_team_id is not None
        and int(run.home_team_id) != section_input.home_team_id
    ):
        raise WriteConflict(
            f"실행({run.id})의 home_team_id({run.home_team_id})가 "
            f"저장 입력({section_input.home_team_id})과 다릅니다."
        )
    if (
        run.away_team_id is not None
        and section_input.away_team_id is not None
        and int(run.away_team_id) != section_input.away_team_id
    ):
        raise WriteConflict(
            f"실행({run.id})의 away_team_id({run.away_team_id})가 "
            f"저장 입력({section_input.away_team_id})과 다릅니다."
        )

    section_row = session.get(PreviewSectionResult, section_input.section_result_id)
    if section_row is None:
        raise RunNotFound(
            f"section result {section_input.section_result_id} not found"
        )
    if section_row.run_id != section_input.run_id:
        raise WriteConflict(
            f"섹션 결과({section_row.id})의 소유 실행({section_row.run_id})이 "
            f"저장 입력({section_input.run_id})과 다릅니다."
        )
    if section_row.workflow_id != spec.workflow_id.value:
        raise WriteConflict(
            f"섹션 결과({section_row.id})의 workflow_id({section_row.workflow_id})가 "
            f"{spec.workflow_id.value} 저장 요청과 다릅니다."
        )
    if section_row.output_contract_version != section_input.output_contract_version:
        raise WriteConflict(
            f"섹션 결과({section_row.id})의 output_contract_version"
            f"({section_row.output_contract_version})이 저장 입력"
            f"({section_input.output_contract_version})과 다릅니다."
        )


def _build_section_row(
    section_input: WatchPlayerSectionInput | InjuryPlayerSectionInput,
    spec: _SectionStorageSpec,
    moment: datetime,
) -> PreviewWatchPlayerSection | PreviewInjuryPlayerSection:
    column_values: dict[str, Any] = {
        "section_result_id": section_input.section_result_id,
        "run_id": section_input.run_id,
        "fixture_id": section_input.fixture_id,
        "home_team_id": section_input.home_team_id,
        "away_team_id": section_input.away_team_id,
        "output_contract_version": section_input.output_contract_version,
        "created_at": moment,
    }
    if spec.include_etc_fields:
        column_values["home_etc"] = None
        column_values["away_etc"] = None

    for key, slot in section_input.slots().items():
        slot_cols = _slot_column_dict(
            key.value, slot, include_injury_fields=spec.include_injury_fields
        )
        cand_col = f"{key.value}_translation_candidate_id"
        if slot_cols.get(cand_col) is not None:
            slot_cols[cand_col] = uuid.UUID(str(slot_cols[cand_col]))
        column_values.update(slot_cols)

    return spec.model_cls(**column_values)


def _save_section(
    session: Session,
    section_input: WatchPlayerSectionInput | InjuryPlayerSectionInput,
    spec: _SectionStorageSpec,
    *,
    actor_id: int = 0,
    now: datetime | None = None,
) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord:
    if not isinstance(section_input, spec.input_cls):
        raise ContractError(
            f"{spec.input_cls.__name__} 입력이 필요합니다: {type(section_input).__name__}"
        )

    _validate_parent_ownership(session, section_input, spec)

    existing = session.get(spec.model_cls, section_input.section_result_id)
    if existing is not None:
        existing_record = _row_to_record(session, existing, spec)
        if _record_canonical_dict(existing_record, spec) == section_input.canonical_dict():
            return existing_record
        raise WriteConflict(
            f"section_result_id={section_input.section_result_id}에 이미 다른 값의 "
            f"{spec.table_name} 결과가 저장되어 있습니다."
        )

    moment = _ensure_aware(now or _now())
    candidate_store.save_section_candidates(
        session,
        section_result_id=section_input.section_result_id,
        candidates=section_input.candidates,
        moment=moment,
        actor_id=actor_id,
    )

    row = _build_section_row(section_input, spec, moment)
    session.add(row)
    session.flush()

    filled_slots = [
        key.value
        for key, slot in section_input.slots().items()
        if slot is not None
    ]
    session.add(
        PreviewWriteAudit(
            run_id=row.run_id,
            actor_id=actor_id,
            action="player_section_saved",
            target_table=spec.table_name,
            target_id=str(row.section_result_id),
            detail={
                "workflow_id": spec.workflow_id.value,
                "fixture_id": int(row.fixture_id),
                "output_contract_version": row.output_contract_version,
                "filled_slots": filled_slots,
                "candidate_count": len(section_input.candidates),
            },
        )
    )
    session.flush()
    return _row_to_record(session, row, spec)


def save_watch_player_section(
    session: Session,
    section_input: WatchPlayerSectionInput,
    *,
    actor_id: int = 0,
    now: datetime | None = None,
) -> WatchPlayerSectionRecord:
    """주목 선수 고정 4슬롯과 번역 후보를 호출자 트랜잭션 안에 저장한다."""
    record = _save_section(
        session, section_input, _WATCH_SPEC, actor_id=actor_id, now=now
    )
    assert isinstance(record, WatchPlayerSectionRecord)
    return record


def save_injury_player_section(
    session: Session,
    section_input: InjuryPlayerSectionInput,
    *,
    actor_id: int = 0,
    now: datetime | None = None,
) -> InjuryPlayerSectionRecord:
    """부상·결장 고정 4슬롯과 번역 후보를 호출자 트랜잭션 안에 저장한다."""
    record = _save_section(
        session, section_input, _INJURY_SPEC, actor_id=actor_id, now=now
    )
    assert isinstance(record, InjuryPlayerSectionRecord)
    return record


def save_player_section(
    session: Session,
    section_input: WatchPlayerSectionInput | InjuryPlayerSectionInput,
    *,
    actor_id: int = 0,
    now: datetime | None = None,
) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord:
    """입력 계약 타입에 따라 주목 선수 또는 부상·결장 저장소로 분기한다."""
    if isinstance(section_input, WatchPlayerSectionInput):
        return save_watch_player_section(
            session, section_input, actor_id=actor_id, now=now
        )
    if isinstance(section_input, InjuryPlayerSectionInput):
        return save_injury_player_section(
            session, section_input, actor_id=actor_id, now=now
        )
    raise ContractError(
        "WatchPlayerSectionInput 또는 InjuryPlayerSectionInput이 필요합니다."
    )


def _get_section(
    session: Session,
    section_result_id: uuid.UUID,
    spec: _SectionStorageSpec,
    *,
    run_id: uuid.UUID | None = None,
) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord | None:
    row = session.get(spec.model_cls, section_result_id)
    if row is None:
        return None
    if run_id is not None and row.run_id != run_id:
        return None
    return _row_to_record(session, row, spec)


def get_watch_player_section(
    session: Session,
    section_result_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
) -> WatchPlayerSectionRecord | None:
    """저장된 주목 선수 고정 4슬롯 결과를 재조회한다."""
    record = _get_section(session, section_result_id, _WATCH_SPEC, run_id=run_id)
    assert record is None or isinstance(record, WatchPlayerSectionRecord)
    return record


def get_injury_player_section(
    session: Session,
    section_result_id: uuid.UUID,
    *,
    run_id: uuid.UUID | None = None,
) -> InjuryPlayerSectionRecord | None:
    """저장된 부상·결장 고정 4슬롯 결과를 재조회한다."""
    record = _get_section(session, section_result_id, _INJURY_SPEC, run_id=run_id)
    assert record is None or isinstance(record, InjuryPlayerSectionRecord)
    return record


def get_player_section(
    session: Session,
    section_result_id: uuid.UUID,
    *,
    workflow_id: PlayerSectionWorkflowId | str | None = None,
    run_id: uuid.UUID | None = None,
) -> WatchPlayerSectionRecord | InjuryPlayerSectionRecord | None:
    """결과 ID(및 선택적 workflow_id/run_id)로 선수 섹션 정본을 재조회한다."""
    if workflow_id is not None:
        try:
            wf = PlayerSectionWorkflowId(workflow_id)
        except ValueError as exc:
            raise ContractError(
                f"허용되지 않은 workflow_id입니다: {workflow_id!r}"
            ) from exc
        return _get_section(
            session, section_result_id, _SPECS_BY_WORKFLOW[wf], run_id=run_id
        )
    watch = get_watch_player_section(session, section_result_id, run_id=run_id)
    if watch is not None:
        return watch
    return get_injury_player_section(session, section_result_id, run_id=run_id)
