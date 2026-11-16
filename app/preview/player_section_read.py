"""NS-03/04 선수·부상 섹션 정본 저장소 읽기 및 투영 경계.

새 출력 계약(`ns01-watch-players-1`, `ns01-injury-players-1`)으로 저장된 섹션 결과는
`preview_watch_player_sections` · `preview_injury_player_sections` ·
`preview_player_name_candidates`를 정본으로 읽는다.

- 정본 행 재조회가 성공한 경우에만 `persisted=True`를 부여한다.
- 정본 행이 있어야 하는 새 계약 결과인데 행이 없으면 구 `PreviewResult.payload`로
  대체해 숨기지 않고 명시적 저장 불일치(`storage_mismatch=True`)를 드러낸다.
- 구 계약(`output_contract_version`이 새 계약이 아닌 경우)과 실패·미확보로 본문이
  비어 있는 결과는 기존 읽기 경로·표시를 보존한다.
- `player_id is None` 슬롯에는 `external_player_id`/`photo_url`을 절대 붙이지 않으며,
  `home_etc`/`away_etc`는 항상 `None`이다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy.orm import Session

from app.preview import player_section_contracts as psc
from app.preview import player_section_store
from app.preview.section_structured import (
    STRUCTURED_VERSION,
    StructuredIdContext,
    player_photo_url,
)

__all__ = [
    "CanonicalPlayerSectionRead",
    "is_new_player_section_contract",
    "read_canonical_player_section",
    "section_expects_canonical_storage",
]

_CANONICAL_OUTPUT_VERSIONS = frozenset(psc.PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS.values())


def is_new_player_section_contract(output_contract_version: Any) -> bool:
    """출력 계약 버전이 NS-01 정본 3표 대상인지 판정한다."""
    return str(output_contract_version or "").strip() in _CANONICAL_OUTPUT_VERSIONS


def section_expects_canonical_storage(row: Mapping[str, Any]) -> bool:
    """이 섹션 결과 행이 정본 3표 행을 반드시 가져야 하는지 판정한다."""
    if not is_new_player_section_contract(row.get("output_contract_version")):
        return False
    unavailable = row.get("unavailable_reason")
    has_body = bool(str(row.get("body") or "").strip())
    return unavailable is None or has_body


def _parse_uuid(value: Any) -> uuid.UUID | None:
    if isinstance(value, uuid.UUID):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def _empty_structured(workflow_id: str) -> dict[str, Any]:
    return {
        "structured_version": STRUCTURED_VERSION,
        "workflow_id": workflow_id,
        "players": [],
        "injuries": [],
        "media": [],
        "odds": [],
        "forecast": None,
    }


def _serialize_evidence(items: Any) -> list[str | dict[str, Any]]:
    """공통 계약의 문자열/매핑 근거 항목을 직렬화 가능 값으로 보존한다."""
    serialized: list[str | dict[str, Any]] = []
    for item in items or ():
        if isinstance(item, str):
            serialized.append(item)
        elif isinstance(item, Mapping):
            serialized.append(dict(item))
        elif hasattr(item, "value"):
            serialized.append(item.value)
    return serialized


def _slot_processing_dict(
    projection: psc.SlotReadProjection,
    *,
    team_id: int | None,
    team_name: str | None,
) -> dict[str, Any] | None:
    if projection.resolution_status == psc.SlotResolutionStatus.EMPTY:
        return None
    payload: dict[str, Any] = {
        "slot_key": projection.slot_key.value,
        "team_side": projection.team_side.value,
        "team_id": team_id,
        "team_name": team_name,
        "player_id": projection.player_id,
        "external_player_id": projection.external_player_id,
        "photo_url": projection.photo_url,
        "resolution_status": projection.resolution_status.value,
        "original_name": projection.original_name,
        "name_ko": projection.display_name,
        "name_source": projection.name_source.value if projection.name_source else None,
        "body": projection.body,
        "unresolved_reason": projection.unresolved_reason,
        "translation_candidate_id": (
            str(projection.translation_candidate_id)
            if projection.translation_candidate_id is not None
            else None
        ),
        "candidate_review_status": (
            projection.candidate_review_status.value
            if projection.candidate_review_status is not None
            else None
        ),
        "evidence": _serialize_evidence(projection.evidence),
    }
    if projection.status is not None or projection.injury is not None or projection.importance is not None:
        payload["status"] = projection.status
        payload["injury"] = projection.injury
        payload["importance"] = projection.importance
    return payload


def _build_processing_view(
    *,
    workflow_id: str,
    row: Mapping[str, Any],
    raw_processing: Mapping[str, Any] | None,
    slot_drafts: Mapping[str, dict[str, Any] | None],
    persisted: bool,
    storage_status: str,
    storage_mismatch: bool,
    storage_error: str | None,
    fixture_id: int | None = None,
    home_team_id: int | None = None,
    away_team_id: int | None = None,
    ok_override: bool | None = None,
    failed_reason_override: str | None = None,
) -> dict[str, Any]:
    raw = dict(raw_processing or {})
    output_version = str(
        row.get("output_contract_version")
        or raw.get("output_contract_version")
        or psc.PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS.get(workflow_id, "")
    )
    resolved_fixture_id = fixture_id if fixture_id is not None else int(raw.get("fixture_id") or 0)
    resolved_home_id = home_team_id if home_team_id is not None else raw.get("home_team_id")
    resolved_away_id = away_team_id if away_team_id is not None else raw.get("away_team_id")
    ok_val = (
        ok_override
        if ok_override is not None
        else (persisted and not storage_mismatch and any(v is not None for v in slot_drafts.values()))
    )
    failed_reason = (
        failed_reason_override
        if failed_reason_override is not None
        else (storage_error if storage_mismatch else raw.get("failed_reason"))
    )
    return {
        "workflow_id": workflow_id,
        "fixture_id": resolved_fixture_id,
        "home_team_id": resolved_home_id,
        "away_team_id": resolved_away_id,
        "output_contract_version": output_version,
        "persisted": persisted,
        "storage_status": storage_status,
        "storage_mismatch": storage_mismatch,
        "storage_error": storage_error,
        "mode": str(row.get("mode") or raw.get("mode") or "live"),
        "ok": ok_val,
        "failed_reason": failed_reason,
        "home1": slot_drafts.get("home1"),
        "home2": slot_drafts.get("home2"),
        "away1": slot_drafts.get("away1"),
        "away2": slot_drafts.get("away2"),
        "home_etc": None,
        "away_etc": None,
        "regeneration_count": int(raw.get("regeneration_count") or 0),
        "regeneration_reason": raw.get("regeneration_reason"),
        "module_attempt_count": int(raw.get("module_attempt_count") or 0),
        "adopted_attempt_ordinal": raw.get("adopted_attempt_ordinal"),
        "attempts": list(raw.get("attempts") or ()),
        "unplaced_items": list(raw.get("unplaced_items") or ()),
        "translation_defects": list(raw.get("translation_defects") or ()),
        "diagnostics": list(raw.get("diagnostics") or ()),
        "korean_labels": list(raw.get("korean_labels") or ()),
        "dropped_evidence_count": int(raw.get("dropped_evidence_count") or 0),
    }


@dataclass(frozen=True)
class CanonicalPlayerSectionRead:
    """새 계약 선수/부상 섹션의 정본 DB 재조회 및 투영 결과."""

    section_result_id: str | None
    workflow_id: str
    persisted: bool
    storage_mismatch: bool
    storage_error: str | None
    structured: dict[str, Any]
    available: bool
    processing: dict[str, Any]

    def structured_result_fields(self) -> dict[str, Any]:
        return {
            "section_result_id": self.section_result_id,
            "workflow_id": self.workflow_id,
            "structured": self.structured,
            "available": self.available,
            "persisted": self.persisted,
            "storage_status": self.processing.get("storage_status"),
            "storage_mismatch": self.storage_mismatch,
            "storage_error": self.storage_error,
        }


def read_canonical_player_section(
    session: Session,
    row: Mapping[str, Any],
    *,
    raw_processing: Mapping[str, Any] | None = None,
    id_context: StructuredIdContext | None = None,
    home_team_name: str | None = None,
    away_team_name: str | None = None,
) -> CanonicalPlayerSectionRead:
    """새 계약 섹션 결과 행을 정본 3표에서 재조회해 구조 값과 처리 진단을 만든다."""
    workflow_id = str(row.get("workflow_id") or "")
    sec_result_id_str = str(row.get("section_result_id") or "").strip() or None
    sec_uuid = _parse_uuid(sec_result_id_str)
    run_uuid = _parse_uuid(row.get("run_id"))
    expects_storage = section_expects_canonical_storage(row)

    record = None
    lookup_error: str | None = None
    if sec_uuid is not None and workflow_id in psc.PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS:
        try:
            record = player_section_store.get_player_section(
                session,
                sec_uuid,
                workflow_id=workflow_id,
                run_id=run_uuid,
            )
        except Exception as exc:  # noqa: BLE001 - 저장 불일치로 명확히 드러낸다
            lookup_error = f"정본 선수/부상 저장소 조회 실패 ({sec_uuid}): {exc}"
            record = None

    if record is None:
        empty = _empty_structured(workflow_id)
        empty_slots = {key: None for key in psc.FIXED_SLOT_KEYS}
        if expects_storage:
            error_msg = lookup_error or (
                f"새 계약 섹션 결과({sec_result_id_str or 'unknown'})의 정본 저장 행을"
                f" 찾지 못했습니다(output_contract_version={row.get('output_contract_version')!r})."
            )
            processing = _build_processing_view(
                workflow_id=workflow_id,
                row=row,
                raw_processing=raw_processing,
                slot_drafts=empty_slots,
                persisted=False,
                storage_status="storage_mismatch",
                storage_mismatch=True,
                storage_error=error_msg,
                ok_override=False,
                failed_reason_override=error_msg,
            )
            return CanonicalPlayerSectionRead(
                section_result_id=sec_result_id_str,
                workflow_id=workflow_id,
                persisted=False,
                storage_mismatch=True,
                storage_error=error_msg,
                structured=empty,
                available=False,
                processing=processing,
            )
        processing = _build_processing_view(
            workflow_id=workflow_id,
            row=row,
            raw_processing=raw_processing,
            slot_drafts=empty_slots,
            persisted=False,
            storage_status="unavailable_not_persisted",
            storage_mismatch=False,
            storage_error=None,
            ok_override=False,
            failed_reason_override=(
                str(row.get("unavailable_reason"))
                if row.get("unavailable_reason") is not None
                else None
            ),
        )
        return CanonicalPlayerSectionRead(
            section_result_id=sec_result_id_str,
            workflow_id=workflow_id,
            persisted=False,
            storage_mismatch=False,
            storage_error=None,
            structured=empty,
            available=False,
            processing=processing,
        )

    candidates_by_id = {cand.id: cand for cand in record.candidates}
    home_team_id = record.home_team_id
    away_team_id = record.away_team_id
    home_team_ext = (
        id_context.team_external_id(home_team_id)
        if id_context is not None and home_team_id is not None
        else None
    )
    away_team_ext = (
        id_context.team_external_id(away_team_id)
        if id_context is not None and away_team_id is not None
        else None
    )
    home_label = (
        (id_context.team_display_name(home_team_id) if id_context is not None and home_team_id is not None else None)
        or home_team_name
    )
    away_label = (
        (id_context.team_display_name(away_team_id) if id_context is not None and away_team_id is not None else None)
        or away_team_name
    )

    structured = _empty_structured(workflow_id)
    slot_drafts: dict[str, dict[str, Any] | None] = {}
    slots_map = record.slots()
    is_watch = workflow_id == psc.PlayerSectionWorkflowId.SECTION_PLAYERS.value

    for key_name in psc.FIXED_SLOT_KEYS:
        slot_key = psc.SlotKey(key_name)
        slot = slots_map[slot_key]
        if slot is None:
            projection = psc.project_slot(slot_key, None)
            slot_drafts[key_name] = None
            continue

        ext_player_id = (
            id_context.player_external_id(slot.player_id)
            if id_context is not None and slot.player_id is not None
            else None
        )
        photo_url = player_photo_url(ext_player_id) if ext_player_id is not None else None
        candidate = (
            candidates_by_id.get(slot.translation_candidate_id)
            if slot.translation_candidate_id is not None
            else None
        )
        review_status = candidate.review_status if candidate is not None else None
        projection = psc.project_slot(
            slot_key,
            slot,
            external_player_id=ext_player_id,
            photo_url=photo_url,
            candidate_review_status=review_status,
        )

        is_home = slot_key.team_side == psc.TeamSide.HOME
        team_id_for = home_team_id if is_home else away_team_id
        team_name_for = home_label if is_home else away_label
        team_ext_for = home_team_ext if is_home else away_team_ext

        slot_drafts[key_name] = _slot_processing_dict(
            projection, team_id=team_id_for, team_name=team_name_for
        )

        common_row = {
            "slot_key": slot_key.value,
            "team_side": slot_key.team_side.value,
            "player": projection.display_name,
            "team": team_name_for,
            "team_id": team_id_for,
            "team_external_id": team_ext_for,
            "player_id": projection.player_id,
            "external_player_id": projection.external_player_id,
            "photo_url": projection.photo_url,
            "unresolved": projection.player_id is None,
            "original_name": projection.original_name,
            "name_source": projection.name_source.value if projection.name_source else None,
            "unresolved_reason": projection.unresolved_reason,
            "translation_candidate_id": (
                str(projection.translation_candidate_id)
                if projection.translation_candidate_id is not None
                else None
            ),
            "candidate_review_status": (
                projection.candidate_review_status.value
                if projection.candidate_review_status is not None
                else None
            ),
            "evidence": _serialize_evidence(projection.evidence),
        }
        if is_watch:
            structured["players"].append({**common_row, "reason": projection.body})
        else:
            structured["injuries"].append(
                {
                    **common_row,
                    "status": projection.status,
                    "summary": projection.body or None,
                    "detail": projection.body or None,
                    "body": projection.body,
                    "injury": projection.injury,
                    "importance": projection.importance,
                }
            )

    target_key = "players" if is_watch else "injuries"
    available = bool(structured[target_key])
    processing = _build_processing_view(
        workflow_id=workflow_id,
        row=row,
        raw_processing=raw_processing,
        slot_drafts=slot_drafts,
        persisted=True,
        storage_status="persisted",
        storage_mismatch=False,
        storage_error=None,
        fixture_id=record.fixture_id,
        home_team_id=record.home_team_id,
        away_team_id=record.away_team_id,
        ok_override=available,
        failed_reason_override=None,
    )
    return CanonicalPlayerSectionRead(
        section_result_id=sec_result_id_str,
        workflow_id=workflow_id,
        persisted=True,
        storage_mismatch=False,
        storage_error=None,
        structured=structured,
        available=available,
        processing=processing,
    )
