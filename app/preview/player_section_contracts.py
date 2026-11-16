"""NS-00 선수 섹션(주목 선수·부상/결장) 공통 논리 계약.

A(저장/마이그레이션/undo), B(프롬프트/응답 처리/검증), C(파이프라인 저장·조회·투영)가
공통으로 가져다 쓰는 최소 타입·경계 검증·버전 상수를 정의한다.

경계 원칙:
- SQLAlchemy 모델, 마이그레이션 DDL, 저장소 함수, 모델 호출/생성 로직을 넣지 않는다.
- 기존 `app.preview.contracts.SECTION_RESULT_CONTRACT_VERSION`은 변경하지 않고,
  `section_players`와 `section_availability`의 출력 계약 버전만 별도 관리한다.
- 빈 자리(`None`)와 채워진 미확인 자리(`player_id=None`)를 타입과 경계 검증으로 분리한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

from app.preview.contracts import ContractError

PREVIEW_DEV_SCHEMA = "preview_dev"
WATCH_PLAYERS_TABLE = "preview_watch_player_sections"
INJURY_PLAYERS_TABLE = "preview_injury_player_sections"
PLAYER_NAME_CANDIDATES_TABLE = "preview_player_name_candidates"

SECTION_PLAYERS_WORKFLOW_ID = "section_players"
SECTION_AVAILABILITY_WORKFLOW_ID = "section_availability"

WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION = "ns01-watch-players-1"
INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION = "ns01-injury-players-1"
PLAYER_SECTION_STORAGE_CONTRACT_VERSION = "ns00-player-section-1"

MAX_SLOTS_PER_TEAM = 2
MAX_CONTENT_REGENERATIONS = 1
MAX_MODULE_ATTEMPTS = 3
FIXED_SLOT_KEYS = ("home1", "home2", "away1", "away2")

PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS: dict[str, str] = {
    SECTION_PLAYERS_WORKFLOW_ID: WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
    SECTION_AVAILABILITY_WORKFLOW_ID: INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
}

WATCH_SLOT_COLUMN_SUFFIXES = (
    "player_id",
    "original_name",
    "name_ko",
    "body",
    "name_source",
    "unresolved_reason",
    "translation_candidate_id",
    "evidence",
)
INJURY_SLOT_COLUMN_SUFFIXES = WATCH_SLOT_COLUMN_SUFFIXES + (
    "status",
    "injury",
    "importance",
)


class PlayerSectionWorkflowId(str, Enum):
    """선수 구조화 저장을 사용하는 두 섹션 워크플로우 ID."""

    SECTION_PLAYERS = SECTION_PLAYERS_WORKFLOW_ID
    SECTION_AVAILABILITY = SECTION_AVAILABILITY_WORKFLOW_ID


class TeamSide(str, Enum):
    HOME = "home"
    AWAY = "away"


class SlotKey(str, Enum):
    """고정 4슬롯 키. JSON 배열이 아니라 고정 컬럼 접두사와 1:1 대응한다."""

    HOME1 = "home1"
    HOME2 = "home2"
    AWAY1 = "away1"
    AWAY2 = "away2"

    @property
    def team_side(self) -> TeamSide:
        return TeamSide.HOME if self in (SlotKey.HOME1, SlotKey.HOME2) else TeamSide.AWAY

    @property
    def slot_number(self) -> int:
        return 1 if self in (SlotKey.HOME1, SlotKey.AWAY1) else 2

    @classmethod
    def for_team(cls, side: TeamSide, slot_number: int) -> "SlotKey":
        if slot_number not in (1, 2):
            raise ContractError(f"slot_number는 1 또는 2여야 합니다: {slot_number!r}")
        if side == TeamSide.HOME:
            return cls.HOME1 if slot_number == 1 else cls.HOME2
        return cls.AWAY1 if slot_number == 1 else cls.AWAY2


class NameSource(str, Enum):
    """채워진 자리의 표시 이름 출처."""

    DB_KO = "db_ko"
    AI_CANDIDATE = "ai_candidate"


class CandidateSource(str, Enum):
    """한글명 후보 생성 출처."""

    AI_TRANSLATION = "ai_translation"


class CandidateReviewStatus(str, Enum):
    """한글명 후보 검수 상태. NS-00 생성 시 기본값은 pending이다."""

    PENDING = "pending"
    APPROVED = "approved"
    EDITED = "edited"
    REJECTED = "rejected"


class SlotResolutionStatus(str, Enum):
    """조회 투영 시 계산되는 슬롯 연결 상태(별도 DB 컬럼으로 중복 저장하지 않는다)."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    EMPTY = "empty"


class RegenerationReason(str, Enum):
    """첫 유효 응답에 대해 섹션 단위 1회 내용 재생성을 유발한 사유."""

    MISSING_BODY = "missing_body"
    DUPLICATE_PLAYER = "duplicate_player"
    MISSING_AND_DUPLICATE = "missing_and_duplicate"


class UnplacedReason(str, Enum):
    """원시 후보가 최종 4슬롯에 들어가지 못한 사유."""

    MISSING_BODY = "missing_body"
    DUPLICATE_PLAYER = "duplicate_player"
    TEAM_UNRESOLVED = "team_unresolved"
    SLOT_CAPACITY_EXCEEDED = "slot_capacity_exceeded"
    MISSING_NAME = "missing_name"
    MISSING_NAME_KO = "missing_name_ko"


def require_positive_int(value: Any, field_name: str) -> int:
    """bool·문자열·0·음수를 거부하고 양의 정수만 허용한다."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{field_name}는 bool이 아닌 정수여야 합니다: {value!r}")
    if value <= 0:
        raise ContractError(f"{field_name}는 양의 정수여야 합니다: {value!r}")
    return value


def optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return require_positive_int(value, field_name)


def require_uuid(value: Any, field_name: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value.strip())
        except ValueError as exc:
            raise ContractError(f"{field_name}는 유효한 UUID여야 합니다: {value!r}") from exc
    raise ContractError(f"{field_name}는 UUID여야 합니다: {value!r}")


def optional_uuid(value: Any, field_name: str) -> uuid.UUID | None:
    if value is None:
        return None
    return require_uuid(value, field_name)


def require_non_empty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field_name}는 문자열이어야 합니다: {value!r}")
    stripped = value.strip()
    if not stripped:
        raise ContractError(f"{field_name}는 비어 있을 수 없습니다.")
    return stripped


def optional_non_empty_text(value: Any, field_name: str) -> str | None:
    """None은 허용하되 공백 문자열('')은 NULL과 혼동되지 않게 거부한다."""
    if value is None:
        return None
    return require_non_empty_text(value, field_name)


def require_aware_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ContractError(f"{field_name}는 ISO datetime이어야 합니다: {value!r}") from exc
        value = parsed
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ContractError(f"{field_name}는 시간대(tzinfo)가 포함된 datetime이어야 합니다.")
    return value


def normalize_evidence(value: Any, field_name: str = "evidence") -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        raise ContractError(f"{field_name}는 근거 객체의 시퀀스여야 합니다.")
    normalized: list[dict[str, Any]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ContractError(f"{field_name}[{idx}]는 매핑 객체여야 합니다.")
        normalized.append(dict(item))
    return tuple(normalized)


def _require_enum(enum_cls: type[Enum], value: Any, field_name: str) -> Any:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(value)
    except ValueError as exc:
        raise ContractError(f"{field_name}에 허용되지 않은 값입니다: {value!r}") from exc


def output_contract_version_for(workflow_id: PlayerSectionWorkflowId | str) -> str:
    wf = _require_enum(PlayerSectionWorkflowId, workflow_id, "workflow_id")
    return PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS[wf.value]


def team_id_for_slot(
    slot_key: SlotKey | str,
    *,
    home_team_id: int | None,
    away_team_id: int | None,
) -> int | None:
    key = _require_enum(SlotKey, slot_key, "slot_key")
    return home_team_id if key.team_side == TeamSide.HOME else away_team_id


def _validate_filled_slot_fields(
    *,
    player_id: int | None,
    original_name: str,
    name_ko: str,
    body: str,
    name_source: NameSource,
    unresolved_reason: str | None,
    translation_candidate_id: uuid.UUID | None,
    require_candidate_id_for_ai: bool,
) -> tuple[
    int | None,
    str,
    str,
    str,
    NameSource,
    str | None,
    uuid.UUID | None,
]:
    validated_player_id = optional_positive_int(player_id, "player_id")
    validated_original = require_non_empty_text(original_name, "original_name")
    validated_name_ko = require_non_empty_text(name_ko, "name_ko")
    validated_body = require_non_empty_text(body, "body")
    validated_source: NameSource = _require_enum(NameSource, name_source, "name_source")
    validated_reason = optional_non_empty_text(unresolved_reason, "unresolved_reason")
    validated_candidate_id = optional_uuid(
        translation_candidate_id, "translation_candidate_id"
    )

    if validated_player_id is None:
        if validated_reason is None:
            raise ContractError(
                "player_id가 NULL인 채워진 자리는 unresolved_reason이 필수입니다."
            )
        if validated_source != NameSource.AI_CANDIDATE:
            raise ContractError(
                "미확인 선수(player_id=None)의 name_source는 ai_candidate여야 합니다."
            )
    else:
        if validated_reason is not None:
            raise ContractError(
                "player_id가 확인된 자리에는 unresolved_reason을 둘 수 없습니다."
            )

    if validated_source == NameSource.DB_KO:
        if validated_player_id is None:
            raise ContractError("db_ko 출처는 확인된 player_id가 필수입니다.")
        if validated_candidate_id is not None:
            raise ContractError(
                "db_ko 출처 자리에는 translation_candidate_id를 둘 수 없습니다."
            )
    elif require_candidate_id_for_ai and validated_candidate_id is None:
        raise ContractError(
            "ai_candidate 저장 자리에는 translation_candidate_id가 필수입니다."
        )

    return (
        validated_player_id,
        validated_original,
        validated_name_ko,
        validated_body,
        validated_source,
        validated_reason,
        validated_candidate_id,
    )


def _slot_column_dict(
    prefix: str,
    slot: "WatchPlayerSlot | InjuryPlayerSlot | None",
    *,
    include_injury_fields: bool,
) -> dict[str, Any]:
    if slot is None:
        suffixes = (
            INJURY_SLOT_COLUMN_SUFFIXES if include_injury_fields else WATCH_SLOT_COLUMN_SUFFIXES
        )
        return {
            f"{prefix}_{suffix}": ([] if suffix == "evidence" else None)
            for suffix in suffixes
        }
    data = {
        f"{prefix}_player_id": slot.player_id,
        f"{prefix}_original_name": slot.original_name,
        f"{prefix}_name_ko": slot.name_ko,
        f"{prefix}_body": slot.body,
        f"{prefix}_name_source": slot.name_source.value,
        f"{prefix}_unresolved_reason": slot.unresolved_reason,
        f"{prefix}_translation_candidate_id": (
            str(slot.translation_candidate_id)
            if slot.translation_candidate_id is not None
            else None
        ),
        f"{prefix}_evidence": [dict(item) for item in slot.evidence],
    }
    if include_injury_fields:
        assert isinstance(slot, InjuryPlayerSlot)
        data[f"{prefix}_status"] = slot.status
        data[f"{prefix}_injury"] = slot.injury
        data[f"{prefix}_importance"] = slot.importance
    return data


def _extract_raw_slot_columns(
    slot_key: SlotKey | str,
    columns: Mapping[str, Any],
    *,
    suffixes: Sequence[str],
) -> tuple[str, dict[str, Any]] | None:
    key = _require_enum(SlotKey, slot_key, "slot_key")
    prefix = key.value
    raw = {suffix: columns.get(f"{prefix}_{suffix}") for suffix in suffixes}
    non_empty_evidence = bool(raw.get("evidence"))
    non_null_scalars = [
        suffix
        for suffix, val in raw.items()
        if suffix != "evidence" and val is not None
    ]
    if not non_null_scalars and not non_empty_evidence:
        return None
    if not non_null_scalars and non_empty_evidence:
        raise ContractError(f"{prefix} 빈 자리에 evidence만 존재할 수 없습니다.")
    return prefix, raw


@dataclass(frozen=True)
class PlayerNameCandidateInput:
    """개발 영역 `preview_player_name_candidates` 저장 입력 계약."""

    id: uuid.UUID
    run_id: uuid.UUID
    section_result_id: uuid.UUID
    workflow_id: PlayerSectionWorkflowId
    slot_key: SlotKey
    fixture_id: int
    team_id: int | None
    player_id: int | None
    original_name: str
    candidate_name_ko: str
    source: CandidateSource = CandidateSource.AI_TRANSLATION
    review_status: CandidateReviewStatus = CandidateReviewStatus.PENDING

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_uuid(self.id, "candidate.id"))
        object.__setattr__(self, "run_id", require_uuid(self.run_id, "candidate.run_id"))
        object.__setattr__(
            self,
            "section_result_id",
            require_uuid(self.section_result_id, "candidate.section_result_id"),
        )
        object.__setattr__(
            self,
            "workflow_id",
            _require_enum(PlayerSectionWorkflowId, self.workflow_id, "candidate.workflow_id"),
        )
        object.__setattr__(
            self,
            "slot_key",
            _require_enum(SlotKey, self.slot_key, "candidate.slot_key"),
        )
        object.__setattr__(
            self, "fixture_id", require_positive_int(self.fixture_id, "candidate.fixture_id")
        )
        object.__setattr__(
            self, "team_id", optional_positive_int(self.team_id, "candidate.team_id")
        )
        object.__setattr__(
            self, "player_id", optional_positive_int(self.player_id, "candidate.player_id")
        )
        object.__setattr__(
            self,
            "original_name",
            require_non_empty_text(self.original_name, "candidate.original_name"),
        )
        object.__setattr__(
            self,
            "candidate_name_ko",
            require_non_empty_text(self.candidate_name_ko, "candidate.candidate_name_ko"),
        )
        source = _require_enum(CandidateSource, self.source, "candidate.source")
        if source != CandidateSource.AI_TRANSLATION:
            raise ContractError(f"후보 source는 ai_translation이어야 합니다: {source!r}")
        object.__setattr__(self, "source", source)
        review_status = _require_enum(
            CandidateReviewStatus, self.review_status, "candidate.review_status"
        )
        if review_status != CandidateReviewStatus.PENDING:
            raise ContractError(
                f"NS-00 신규 후보 review_status는 pending이어야 합니다: {review_status!r}"
            )
        object.__setattr__(self, "review_status", review_status)

    def canonical_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "run_id": str(self.run_id),
            "section_result_id": str(self.section_result_id),
            "workflow_id": self.workflow_id.value,
            "slot_key": self.slot_key.value,
            "fixture_id": self.fixture_id,
            "team_id": self.team_id,
            "player_id": self.player_id,
            "original_name": self.original_name,
            "candidate_name_ko": self.candidate_name_ko,
            "source": self.source.value,
            "review_status": self.review_status.value,
        }


@dataclass(frozen=True)
class PlayerNameCandidateRecord:
    """저장된 `preview_player_name_candidates` 조회 레코드."""

    id: uuid.UUID
    run_id: uuid.UUID
    section_result_id: uuid.UUID
    workflow_id: PlayerSectionWorkflowId
    slot_key: SlotKey
    fixture_id: int
    team_id: int | None
    player_id: int | None
    original_name: str
    candidate_name_ko: str
    source: CandidateSource
    review_status: CandidateReviewStatus
    created_at: datetime
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", require_uuid(self.id, "candidate.id"))
        object.__setattr__(self, "run_id", require_uuid(self.run_id, "candidate.run_id"))
        object.__setattr__(
            self,
            "section_result_id",
            require_uuid(self.section_result_id, "candidate.section_result_id"),
        )
        object.__setattr__(
            self,
            "workflow_id",
            _require_enum(PlayerSectionWorkflowId, self.workflow_id, "candidate.workflow_id"),
        )
        object.__setattr__(
            self,
            "slot_key",
            _require_enum(SlotKey, self.slot_key, "candidate.slot_key"),
        )
        object.__setattr__(
            self, "fixture_id", require_positive_int(self.fixture_id, "candidate.fixture_id")
        )
        object.__setattr__(
            self, "team_id", optional_positive_int(self.team_id, "candidate.team_id")
        )
        object.__setattr__(
            self, "player_id", optional_positive_int(self.player_id, "candidate.player_id")
        )
        object.__setattr__(
            self,
            "original_name",
            require_non_empty_text(self.original_name, "candidate.original_name"),
        )
        object.__setattr__(
            self,
            "candidate_name_ko",
            require_non_empty_text(self.candidate_name_ko, "candidate.candidate_name_ko"),
        )
        object.__setattr__(
            self,
            "source",
            _require_enum(CandidateSource, self.source, "candidate.source"),
        )
        object.__setattr__(
            self,
            "review_status",
            _require_enum(CandidateReviewStatus, self.review_status, "candidate.review_status"),
        )
        object.__setattr__(
            self, "created_at", require_aware_datetime(self.created_at, "candidate.created_at")
        )
        validated_reason = optional_non_empty_text(
            self.unresolved_reason, "candidate.unresolved_reason"
        )
        if self.player_id is not None and validated_reason is not None:
            raise ContractError(
                "확인된 선수의 번역 후보 조회에는 unresolved_reason이 없어야 합니다."
            )
        object.__setattr__(self, "unresolved_reason", validated_reason)


@dataclass(frozen=True)
class WatchPlayerSlot:
    """주목 선수 섹션의 채워진 고정 슬롯 저장 계약."""

    player_id: int | None
    original_name: str
    name_ko: str
    body: str
    name_source: NameSource
    unresolved_reason: str | None = None
    translation_candidate_id: uuid.UUID | None = None
    evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        (
            player_id,
            original_name,
            name_ko,
            body,
            name_source,
            unresolved_reason,
            translation_candidate_id,
        ) = _validate_filled_slot_fields(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=self.translation_candidate_id,
            require_candidate_id_for_ai=True,
        )
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "original_name", original_name)
        object.__setattr__(self, "name_ko", name_ko)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "name_source", name_source)
        object.__setattr__(self, "unresolved_reason", unresolved_reason)
        object.__setattr__(self, "translation_candidate_id", translation_candidate_id)
        object.__setattr__(self, "evidence", normalize_evidence(self.evidence))

    @property
    def display_name(self) -> str:
        return self.name_ko

    @property
    def resolution_status(self) -> SlotResolutionStatus:
        return (
            SlotResolutionStatus.RESOLVED
            if self.player_id is not None
            else SlotResolutionStatus.UNRESOLVED
        )

    def to_columns(self, slot_key: SlotKey | str) -> dict[str, Any]:
        key = _require_enum(SlotKey, slot_key, "slot_key")
        return _slot_column_dict(key.value, self, include_injury_fields=False)

    @classmethod
    def from_columns(
        cls, slot_key: SlotKey | str, columns: Mapping[str, Any]
    ) -> "WatchPlayerSlot | None":
        extracted = _extract_raw_slot_columns(
            slot_key, columns, suffixes=WATCH_SLOT_COLUMN_SUFFIXES
        )
        if extracted is None:
            return None
        _, raw = extracted
        return cls(
            player_id=raw["player_id"],
            original_name=raw["original_name"],
            name_ko=raw["name_ko"],
            body=raw["body"],
            name_source=raw["name_source"],
            unresolved_reason=raw["unresolved_reason"],
            translation_candidate_id=raw["translation_candidate_id"],
            evidence=raw["evidence"],
        )


@dataclass(frozen=True)
class InjuryPlayerSlot:
    """부상·결장 섹션의 채워진 고정 슬롯 저장 계약."""

    player_id: int | None
    original_name: str
    name_ko: str
    body: str
    name_source: NameSource
    status: str
    injury: str | None = None
    importance: str | None = None
    unresolved_reason: str | None = None
    translation_candidate_id: uuid.UUID | None = None
    evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        (
            player_id,
            original_name,
            name_ko,
            body,
            name_source,
            unresolved_reason,
            translation_candidate_id,
        ) = _validate_filled_slot_fields(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=self.translation_candidate_id,
            require_candidate_id_for_ai=True,
        )
        validated_status = require_non_empty_text(self.status, "status")
        validated_injury = optional_non_empty_text(self.injury, "injury")
        validated_importance = optional_non_empty_text(self.importance, "importance")
        if validated_injury is None and validated_importance is None:
            raise ContractError(
                "부상 슬롯에는 injury 또는 importance 설명 원문이 하나 이상 필요합니다."
            )
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "original_name", original_name)
        object.__setattr__(self, "name_ko", name_ko)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "name_source", name_source)
        object.__setattr__(self, "status", validated_status)
        object.__setattr__(self, "injury", validated_injury)
        object.__setattr__(self, "importance", validated_importance)
        object.__setattr__(self, "unresolved_reason", unresolved_reason)
        object.__setattr__(self, "translation_candidate_id", translation_candidate_id)
        object.__setattr__(self, "evidence", normalize_evidence(self.evidence))

    @property
    def display_name(self) -> str:
        return self.name_ko

    @property
    def resolution_status(self) -> SlotResolutionStatus:
        return (
            SlotResolutionStatus.RESOLVED
            if self.player_id is not None
            else SlotResolutionStatus.UNRESOLVED
        )

    def to_columns(self, slot_key: SlotKey | str) -> dict[str, Any]:
        key = _require_enum(SlotKey, slot_key, "slot_key")
        return _slot_column_dict(key.value, self, include_injury_fields=True)

    @classmethod
    def from_columns(
        cls, slot_key: SlotKey | str, columns: Mapping[str, Any]
    ) -> "InjuryPlayerSlot | None":
        extracted = _extract_raw_slot_columns(
            slot_key, columns, suffixes=INJURY_SLOT_COLUMN_SUFFIXES
        )
        if extracted is None:
            return None
        _, raw = extracted
        return cls(
            player_id=raw["player_id"],
            original_name=raw["original_name"],
            name_ko=raw["name_ko"],
            body=raw["body"],
            name_source=raw["name_source"],
            status=raw["status"],
            injury=raw["injury"],
            importance=raw["importance"],
            unresolved_reason=raw["unresolved_reason"],
            translation_candidate_id=raw["translation_candidate_id"],
            evidence=raw["evidence"],
        )


def _validate_section_slots_and_candidates(
    *,
    section_result_id: uuid.UUID,
    run_id: uuid.UUID,
    fixture_id: int,
    home_team_id: int | None,
    away_team_id: int | None,
    workflow_id: PlayerSectionWorkflowId,
    slots: Mapping[SlotKey, WatchPlayerSlot | InjuryPlayerSlot | None],
    candidates: Sequence[PlayerNameCandidateInput | PlayerNameCandidateRecord],
) -> None:
    if slots[SlotKey.HOME1] is None and slots[SlotKey.HOME2] is not None:
        raise ContractError("home1이 비어 있을 때 home2를 채울 수 없습니다.")
    if slots[SlotKey.AWAY1] is None and slots[SlotKey.AWAY2] is not None:
        raise ContractError("away1이 비어 있을 때 away2를 채울 수 없습니다.")

    seen_player_ids: dict[int, SlotKey] = {}
    expected_candidates: dict[SlotKey, tuple[uuid.UUID, WatchPlayerSlot | InjuryPlayerSlot]] = {}

    for key in (SlotKey.HOME1, SlotKey.HOME2, SlotKey.AWAY1, SlotKey.AWAY2):
        slot = slots[key]
        if slot is None:
            continue
        if slot.player_id is not None:
            prior_slot = seen_player_ids.get(slot.player_id)
            if prior_slot is not None:
                raise ContractError(
                    f"동일 player_id({slot.player_id})가 {prior_slot.value}와 {key.value}에 중복 배치되었습니다."
                )
            seen_player_ids[slot.player_id] = key
        if slot.name_source == NameSource.AI_CANDIDATE:
            assert slot.translation_candidate_id is not None
            expected_candidates[key] = (slot.translation_candidate_id, slot)

    seen_candidate_slots: set[SlotKey] = set()
    for candidate in candidates:
        if candidate.slot_key in seen_candidate_slots:
            raise ContractError(
                f"동일 슬롯({candidate.slot_key.value})에 번역 후보가 중복되었습니다."
            )
        seen_candidate_slots.add(candidate.slot_key)

        if candidate.run_id != run_id or candidate.section_result_id != section_result_id:
            raise ContractError(
                f"번역 후보({candidate.slot_key.value})의 run_id/section_result_id가 섹션과 다릅니다."
            )
        if candidate.workflow_id != workflow_id or candidate.fixture_id != fixture_id:
            raise ContractError(
                f"번역 후보({candidate.slot_key.value})의 workflow_id/fixture_id가 섹션과 다릅니다."
            )

        expected_team_id = team_id_for_slot(
            candidate.slot_key,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
        )
        if candidate.team_id != expected_team_id:
            raise ContractError(
                f"번역 후보({candidate.slot_key.value})의 team_id가 슬롯 팀({expected_team_id})과 다릅니다."
            )

        expected = expected_candidates.get(candidate.slot_key)
        if expected is None:
            raise ContractError(
                f"db_ko 또는 빈 슬롯({candidate.slot_key.value})에 번역 후보를 둘 수 없습니다."
            )
        expected_id, slot = expected
        if candidate.id != expected_id:
            raise ContractError(
                f"번역 후보 ID({candidate.id})가 슬롯 translation_candidate_id({expected_id})와 다릅니다."
            )
        if (
            candidate.player_id != slot.player_id
            or candidate.original_name != slot.original_name
            or candidate.candidate_name_ko != slot.name_ko
        ):
            raise ContractError(
                f"번역 후보({candidate.slot_key.value})의 선수/이름 필드가 슬롯과 일치하지 않습니다."
            )

    missing_slots = set(expected_candidates) - seen_candidate_slots
    if missing_slots:
        names = ", ".join(sorted(k.value for k in missing_slots))
        raise ContractError(f"ai_candidate 슬롯({names})에 대응하는 번역 후보가 누락되었습니다.")


def _validate_section_header(
    *,
    section_result_id: Any,
    run_id: Any,
    fixture_id: Any,
    home_team_id: Any,
    away_team_id: Any,
    output_contract_version: Any,
    expected_version: str,
) -> tuple[uuid.UUID, uuid.UUID, int, int | None, int | None, str]:
    s_id = require_uuid(section_result_id, "section_result_id")
    r_id = require_uuid(run_id, "run_id")
    f_id = require_positive_int(fixture_id, "fixture_id")
    h_id = optional_positive_int(home_team_id, "home_team_id")
    a_id = optional_positive_int(away_team_id, "away_team_id")
    ver = require_non_empty_text(output_contract_version, "output_contract_version")
    if ver != expected_version:
        raise ContractError(
            f"output_contract_version은 {expected_version!r}이어야 합니다: {ver!r}"
        )
    return s_id, r_id, f_id, h_id, a_id, ver


@dataclass(frozen=True)
class WatchPlayerSectionInput:
    """`preview_watch_player_sections` + `preview_player_name_candidates` 저장 입력 계약."""

    section_result_id: uuid.UUID
    run_id: uuid.UUID
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str = WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION
    home1: WatchPlayerSlot | None = None
    home2: WatchPlayerSlot | None = None
    away1: WatchPlayerSlot | None = None
    away2: WatchPlayerSlot | None = None
    home_etc: None = None
    away_etc: None = None
    candidates: tuple[PlayerNameCandidateInput, ...] = ()

    def __post_init__(self) -> None:
        s_id, r_id, f_id, h_id, a_id, ver = _validate_section_header(
            section_result_id=self.section_result_id,
            run_id=self.run_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            expected_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        if self.home_etc is not None or self.away_etc is not None:
            raise ContractError("NS-00 v1에서 home_etc/away_etc는 반드시 None이어야 합니다.")

        for attr in FIXED_SLOT_KEYS:
            val = getattr(self, attr)
            if val is not None and not isinstance(val, WatchPlayerSlot):
                raise ContractError(f"{attr}는 WatchPlayerSlot 또는 None이어야 합니다.")

        cands = tuple(self.candidates)
        for cand in cands:
            if not isinstance(cand, PlayerNameCandidateInput):
                raise ContractError("candidates 항목은 PlayerNameCandidateInput이어야 합니다.")

        _validate_section_slots_and_candidates(
            section_result_id=s_id,
            run_id=r_id,
            fixture_id=f_id,
            home_team_id=h_id,
            away_team_id=a_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
            slots={
                SlotKey.HOME1: self.home1,
                SlotKey.HOME2: self.home2,
                SlotKey.AWAY1: self.away1,
                SlotKey.AWAY2: self.away2,
            },
            candidates=cands,
        )
        object.__setattr__(self, "section_result_id", s_id)
        object.__setattr__(self, "run_id", r_id)
        object.__setattr__(self, "fixture_id", f_id)
        object.__setattr__(self, "home_team_id", h_id)
        object.__setattr__(self, "away_team_id", a_id)
        object.__setattr__(self, "output_contract_version", ver)
        object.__setattr__(self, "candidates", cands)

    def slots(self) -> dict[SlotKey, WatchPlayerSlot | None]:
        return {
            SlotKey.HOME1: self.home1,
            SlotKey.HOME2: self.home2,
            SlotKey.AWAY1: self.away1,
            SlotKey.AWAY2: self.away2,
        }

    def canonical_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section_result_id": str(self.section_result_id),
            "run_id": str(self.run_id),
            "fixture_id": self.fixture_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "output_contract_version": self.output_contract_version,
            "home_etc": None,
            "away_etc": None,
        }
        for key, slot in self.slots().items():
            payload.update(_slot_column_dict(key.value, slot, include_injury_fields=False))
        payload["candidates"] = [
            c.canonical_dict()
            for c in sorted(self.candidates, key=lambda item: item.slot_key.value)
        ]
        return payload


@dataclass(frozen=True)
class WatchPlayerSectionRecord:
    """저장된 `preview_watch_player_sections` 조회 레코드."""

    section_result_id: uuid.UUID
    run_id: uuid.UUID
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str
    created_at: datetime
    home1: WatchPlayerSlot | None = None
    home2: WatchPlayerSlot | None = None
    away1: WatchPlayerSlot | None = None
    away2: WatchPlayerSlot | None = None
    home_etc: None = None
    away_etc: None = None
    candidates: tuple[PlayerNameCandidateRecord, ...] = ()

    def __post_init__(self) -> None:
        s_id, r_id, f_id, h_id, a_id, ver = _validate_section_header(
            section_result_id=self.section_result_id,
            run_id=self.run_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            expected_version=WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        if self.home_etc is not None or self.away_etc is not None:
            raise ContractError("NS-00 v1에서 home_etc/away_etc는 반드시 None이어야 합니다.")
        created_at = require_aware_datetime(self.created_at, "created_at")
        cands = tuple(self.candidates)
        _validate_section_slots_and_candidates(
            section_result_id=s_id,
            run_id=r_id,
            fixture_id=f_id,
            home_team_id=h_id,
            away_team_id=a_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_PLAYERS,
            slots={
                SlotKey.HOME1: self.home1,
                SlotKey.HOME2: self.home2,
                SlotKey.AWAY1: self.away1,
                SlotKey.AWAY2: self.away2,
            },
            candidates=cands,
        )
        object.__setattr__(self, "section_result_id", s_id)
        object.__setattr__(self, "run_id", r_id)
        object.__setattr__(self, "fixture_id", f_id)
        object.__setattr__(self, "home_team_id", h_id)
        object.__setattr__(self, "away_team_id", a_id)
        object.__setattr__(self, "output_contract_version", ver)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "candidates", cands)

    def slots(self) -> dict[SlotKey, WatchPlayerSlot | None]:
        return {
            SlotKey.HOME1: self.home1,
            SlotKey.HOME2: self.home2,
            SlotKey.AWAY1: self.away1,
            SlotKey.AWAY2: self.away2,
        }


@dataclass(frozen=True)
class InjuryPlayerSectionInput:
    """`preview_injury_player_sections` + `preview_player_name_candidates` 저장 입력 계약."""

    section_result_id: uuid.UUID
    run_id: uuid.UUID
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str = INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION
    home1: InjuryPlayerSlot | None = None
    home2: InjuryPlayerSlot | None = None
    away1: InjuryPlayerSlot | None = None
    away2: InjuryPlayerSlot | None = None
    candidates: tuple[PlayerNameCandidateInput, ...] = ()

    def __post_init__(self) -> None:
        s_id, r_id, f_id, h_id, a_id, ver = _validate_section_header(
            section_result_id=self.section_result_id,
            run_id=self.run_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            expected_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        for attr in FIXED_SLOT_KEYS:
            val = getattr(self, attr)
            if val is not None and not isinstance(val, InjuryPlayerSlot):
                raise ContractError(f"{attr}는 InjuryPlayerSlot 또는 None이어야 합니다.")

        cands = tuple(self.candidates)
        for cand in cands:
            if not isinstance(cand, PlayerNameCandidateInput):
                raise ContractError("candidates 항목은 PlayerNameCandidateInput이어야 합니다.")

        _validate_section_slots_and_candidates(
            section_result_id=s_id,
            run_id=r_id,
            fixture_id=f_id,
            home_team_id=h_id,
            away_team_id=a_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY,
            slots={
                SlotKey.HOME1: self.home1,
                SlotKey.HOME2: self.home2,
                SlotKey.AWAY1: self.away1,
                SlotKey.AWAY2: self.away2,
            },
            candidates=cands,
        )
        object.__setattr__(self, "section_result_id", s_id)
        object.__setattr__(self, "run_id", r_id)
        object.__setattr__(self, "fixture_id", f_id)
        object.__setattr__(self, "home_team_id", h_id)
        object.__setattr__(self, "away_team_id", a_id)
        object.__setattr__(self, "output_contract_version", ver)
        object.__setattr__(self, "candidates", cands)

    def slots(self) -> dict[SlotKey, InjuryPlayerSlot | None]:
        return {
            SlotKey.HOME1: self.home1,
            SlotKey.HOME2: self.home2,
            SlotKey.AWAY1: self.away1,
            SlotKey.AWAY2: self.away2,
        }

    def canonical_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "section_result_id": str(self.section_result_id),
            "run_id": str(self.run_id),
            "fixture_id": self.fixture_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "output_contract_version": self.output_contract_version,
        }
        for key, slot in self.slots().items():
            payload.update(_slot_column_dict(key.value, slot, include_injury_fields=True))
        payload["candidates"] = [
            c.canonical_dict()
            for c in sorted(self.candidates, key=lambda item: item.slot_key.value)
        ]
        return payload


@dataclass(frozen=True)
class InjuryPlayerSectionRecord:
    """저장된 `preview_injury_player_sections` 조회 레코드."""

    section_result_id: uuid.UUID
    run_id: uuid.UUID
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str
    created_at: datetime
    home1: InjuryPlayerSlot | None = None
    home2: InjuryPlayerSlot | None = None
    away1: InjuryPlayerSlot | None = None
    away2: InjuryPlayerSlot | None = None
    candidates: tuple[PlayerNameCandidateRecord, ...] = ()

    def __post_init__(self) -> None:
        s_id, r_id, f_id, h_id, a_id, ver = _validate_section_header(
            section_result_id=self.section_result_id,
            run_id=self.run_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            expected_version=INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION,
        )
        created_at = require_aware_datetime(self.created_at, "created_at")
        cands = tuple(self.candidates)
        _validate_section_slots_and_candidates(
            section_result_id=s_id,
            run_id=r_id,
            fixture_id=f_id,
            home_team_id=h_id,
            away_team_id=a_id,
            workflow_id=PlayerSectionWorkflowId.SECTION_AVAILABILITY,
            slots={
                SlotKey.HOME1: self.home1,
                SlotKey.HOME2: self.home2,
                SlotKey.AWAY1: self.away1,
                SlotKey.AWAY2: self.away2,
            },
            candidates=cands,
        )
        object.__setattr__(self, "section_result_id", s_id)
        object.__setattr__(self, "run_id", r_id)
        object.__setattr__(self, "fixture_id", f_id)
        object.__setattr__(self, "home_team_id", h_id)
        object.__setattr__(self, "away_team_id", a_id)
        object.__setattr__(self, "output_contract_version", ver)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "candidates", cands)

    def slots(self) -> dict[SlotKey, InjuryPlayerSlot | None]:
        return {
            SlotKey.HOME1: self.home1,
            SlotKey.HOME2: self.home2,
            SlotKey.AWAY1: self.away1,
            SlotKey.AWAY2: self.away2,
        }


# --------------------------------------------------------------------------
# B 처리 결과('저장 예정 값') -> C `_save_draft` 구체화 경계
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingWatchSlotDraft:
    """저장 ID 부여 전 B 주목 선수 처리 결과 슬롯('저장 예정 값')."""

    player_id: int | None
    original_name: str
    name_ko: str
    body: str
    name_source: NameSource
    unresolved_reason: str | None = None
    evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        (
            player_id,
            original_name,
            name_ko,
            body,
            name_source,
            unresolved_reason,
            _,
        ) = _validate_filled_slot_fields(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=None,
            require_candidate_id_for_ai=False,
        )
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "original_name", original_name)
        object.__setattr__(self, "name_ko", name_ko)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "name_source", name_source)
        object.__setattr__(self, "unresolved_reason", unresolved_reason)
        object.__setattr__(self, "evidence", normalize_evidence(self.evidence))

    def to_storage_slot(
        self, translation_candidate_id: uuid.UUID | None = None
    ) -> WatchPlayerSlot:
        return WatchPlayerSlot(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=translation_candidate_id,
            evidence=self.evidence,
        )


@dataclass(frozen=True)
class PendingInjurySlotDraft:
    """저장 ID 부여 전 B 부상·결장 처리 결과 슬롯('저장 예정 값')."""

    player_id: int | None
    original_name: str
    name_ko: str
    body: str
    name_source: NameSource
    status: str
    injury: str | None = None
    importance: str | None = None
    unresolved_reason: str | None = None
    evidence: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        (
            player_id,
            original_name,
            name_ko,
            body,
            name_source,
            unresolved_reason,
            _,
        ) = _validate_filled_slot_fields(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=None,
            require_candidate_id_for_ai=False,
        )
        validated_status = require_non_empty_text(self.status, "status")
        validated_injury = optional_non_empty_text(self.injury, "injury")
        validated_importance = optional_non_empty_text(self.importance, "importance")
        if validated_injury is None and validated_importance is None:
            raise ContractError(
                "부상 슬롯에는 injury 또는 importance 설명 원문이 하나 이상 필요합니다."
            )
        object.__setattr__(self, "player_id", player_id)
        object.__setattr__(self, "original_name", original_name)
        object.__setattr__(self, "name_ko", name_ko)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "name_source", name_source)
        object.__setattr__(self, "status", validated_status)
        object.__setattr__(self, "injury", validated_injury)
        object.__setattr__(self, "importance", validated_importance)
        object.__setattr__(self, "unresolved_reason", unresolved_reason)
        object.__setattr__(self, "evidence", normalize_evidence(self.evidence))

    def to_storage_slot(
        self, translation_candidate_id: uuid.UUID | None = None
    ) -> InjuryPlayerSlot:
        return InjuryPlayerSlot(
            player_id=self.player_id,
            original_name=self.original_name,
            name_ko=self.name_ko,
            body=self.body,
            name_source=self.name_source,
            status=self.status,
            injury=self.injury,
            importance=self.importance,
            unresolved_reason=self.unresolved_reason,
            translation_candidate_id=translation_candidate_id,
            evidence=self.evidence,
        )


@dataclass(frozen=True)
class UnplacedPlayerDiagnostic:
    """최종 4슬롯에 들어가지 못한 항목과 제외 사유 진단."""

    original_name: str
    reason: UnplacedReason
    team_hint: str | None = None
    team_id: int | None = None
    player_id: int | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "original_name", require_non_empty_text(self.original_name, "original_name")
        )
        object.__setattr__(
            self, "reason", _require_enum(UnplacedReason, self.reason, "reason")
        )
        object.__setattr__(
            self, "team_hint", optional_non_empty_text(self.team_hint, "team_hint")
        )
        object.__setattr__(
            self, "team_id", optional_positive_int(self.team_id, "team_id")
        )
        object.__setattr__(
            self, "player_id", optional_positive_int(self.player_id, "player_id")
        )
        object.__setattr__(self, "detail", optional_non_empty_text(self.detail, "detail"))


@dataclass(frozen=True)
class PlayerSectionAttemptTrace:
    """재시도·재생성 포함 모듈 전송 시도 1회의 추적 정보."""

    attempt_ordinal: int
    logical_call_id: str
    raw_text: str | None = None
    parsed_json: dict[str, Any] | None = None
    regeneration_triggered: bool = False
    regeneration_reason: RegenerationReason | None = None

    def __post_init__(self) -> None:
        ordinal = require_positive_int(self.attempt_ordinal, "attempt_ordinal")
        if ordinal > MAX_MODULE_ATTEMPTS:
            raise ContractError(
                f"모듈 실제 전송 시도는 최대 {MAX_MODULE_ATTEMPTS}회입니다: {ordinal}"
            )
        object.__setattr__(self, "attempt_ordinal", ordinal)
        object.__setattr__(
            self, "logical_call_id", require_non_empty_text(self.logical_call_id, "logical_call_id")
        )
        if self.raw_text is not None and not isinstance(self.raw_text, str):
            raise ContractError("raw_text는 문자열 또는 None이어야 합니다.")
        if self.parsed_json is not None and not isinstance(self.parsed_json, Mapping):
            raise ContractError("parsed_json은 dict 또는 None이어야 합니다.")
        if self.parsed_json is not None:
            object.__setattr__(self, "parsed_json", dict(self.parsed_json))
        reason = (
            _require_enum(RegenerationReason, self.regeneration_reason, "regeneration_reason")
            if self.regeneration_reason is not None
            else None
        )
        if self.regeneration_triggered and reason is None:
            raise ContractError("내용 재생성을 유발한 경우 regeneration_reason이 필수입니다.")
        if not self.regeneration_triggered and reason is not None:
            raise ContractError(
                "regeneration_triggered=False일 때 regeneration_reason을 둘 수 없습니다."
            )
        object.__setattr__(self, "regeneration_reason", reason)


@dataclass(frozen=True)
class PlayerSectionProcessingResult:
    """B의 선수/부상 섹션 처리 결과('저장 예정 값' 및 검사 진단)."""

    workflow_id: PlayerSectionWorkflowId
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str
    home1: PendingWatchSlotDraft | PendingInjurySlotDraft | None = None
    home2: PendingWatchSlotDraft | PendingInjurySlotDraft | None = None
    away1: PendingWatchSlotDraft | PendingInjurySlotDraft | None = None
    away2: PendingWatchSlotDraft | PendingInjurySlotDraft | None = None
    home_etc: None = None
    away_etc: None = None
    regeneration_count: int = 0
    module_attempt_count: int = 1
    adopted_attempt_ordinal: int = 1
    attempts: tuple[PlayerSectionAttemptTrace, ...] = ()
    unplaced_items: tuple[UnplacedPlayerDiagnostic, ...] = ()
    persisted: bool = False

    def __post_init__(self) -> None:
        wf = _require_enum(PlayerSectionWorkflowId, self.workflow_id, "workflow_id")
        expected_version = output_contract_version_for(wf)
        ver = require_non_empty_text(self.output_contract_version, "output_contract_version")
        if ver != expected_version:
            raise ContractError(
                f"{wf.value}의 output_contract_version은 {expected_version!r}이어야 합니다: {ver!r}"
            )
        f_id = require_positive_int(self.fixture_id, "fixture_id")
        h_id = optional_positive_int(self.home_team_id, "home_team_id")
        a_id = optional_positive_int(self.away_team_id, "away_team_id")
        if self.home_etc is not None or self.away_etc is not None:
            raise ContractError("NS-00 v1에서 home_etc/away_etc는 반드시 None이어야 합니다.")

        expected_slot_cls = (
            PendingWatchSlotDraft
            if wf == PlayerSectionWorkflowId.SECTION_PLAYERS
            else PendingInjurySlotDraft
        )
        for attr in FIXED_SLOT_KEYS:
            slot = getattr(self, attr)
            if slot is not None and not isinstance(slot, expected_slot_cls):
                raise ContractError(
                    f"{wf.value}의 {attr}는 {expected_slot_cls.__name__} 또는 None이어야 합니다."
                )

        if self.home1 is None and self.home2 is not None:
            raise ContractError("home1이 비어 있을 때 home2를 채울 수 없습니다.")
        if self.away1 is None and self.away2 is not None:
            raise ContractError("away1이 비어 있을 때 away2를 채울 수 없습니다.")

        seen_player_ids: set[int] = set()
        for attr in FIXED_SLOT_KEYS:
            slot = getattr(self, attr)
            if slot is not None and slot.player_id is not None:
                if slot.player_id in seen_player_ids:
                    raise ContractError(
                        f"처리 결과에 동일 player_id({slot.player_id})가 중복되었습니다."
                    )
                seen_player_ids.add(slot.player_id)

        if isinstance(self.regeneration_count, bool) or not isinstance(
            self.regeneration_count, int
        ):
            raise ContractError("regeneration_count는 정수여야 합니다.")
        if not 0 <= self.regeneration_count <= MAX_CONTENT_REGENERATIONS:
            raise ContractError(
                f"내용 재생성 횟수는 최대 {MAX_CONTENT_REGENERATIONS}회입니다: {self.regeneration_count}"
            )

        attempts_count = require_positive_int(self.module_attempt_count, "module_attempt_count")
        if attempts_count > MAX_MODULE_ATTEMPTS:
            raise ContractError(
                f"모듈 실제 전송 횟수는 최대 {MAX_MODULE_ATTEMPTS}회입니다: {attempts_count}"
            )
        adopted = require_positive_int(
            self.adopted_attempt_ordinal, "adopted_attempt_ordinal"
        )
        if adopted > attempts_count:
            raise ContractError(
                f"adopted_attempt_ordinal({adopted})는 module_attempt_count({attempts_count})를 넘을 수 없습니다."
            )

        traces = tuple(self.attempts)
        if traces:
            ordinals = [t.attempt_ordinal for t in traces]
            if len(ordinals) != len(set(ordinals)) or ordinals != sorted(ordinals):
                raise ContractError("attempts의 attempt_ordinal은 중복 없이 순증가해야 합니다.")
            if max(ordinals) > attempts_count:
                raise ContractError("attempts에 module_attempt_count를 초과하는 시도가 있습니다.")
            if adopted not in ordinals:
                raise ContractError("adopted_attempt_ordinal에 해당하는 시도 추적이 없습니다.")
            regen_traces = sum(1 for t in traces if t.regeneration_triggered)
            if regen_traces > MAX_CONTENT_REGENERATIONS:
                raise ContractError("내용 재생성 유발 시도는 1회를 넘을 수 없습니다.")

        object.__setattr__(self, "workflow_id", wf)
        object.__setattr__(self, "fixture_id", f_id)
        object.__setattr__(self, "home_team_id", h_id)
        object.__setattr__(self, "away_team_id", a_id)
        object.__setattr__(self, "output_contract_version", ver)
        object.__setattr__(self, "attempts", traces)
        object.__setattr__(self, "unplaced_items", tuple(self.unplaced_items))

    def materialize_storage_input(
        self,
        *,
        section_result_id: uuid.UUID,
        run_id: uuid.UUID,
        candidate_id_factory: Callable[[SlotKey], uuid.UUID] | None = None,
    ) -> WatchPlayerSectionInput | InjuryPlayerSectionInput:
        """C의 `_save_draft`에서 저장 ID를 부여해 정본 저장 입력 계약으로 변환한다."""
        s_id = require_uuid(section_result_id, "section_result_id")
        r_id = require_uuid(run_id, "run_id")
        make_id = candidate_id_factory or (lambda _slot: uuid.uuid4())

        materialized_slots: dict[str, Any] = {}
        candidates: list[PlayerNameCandidateInput] = []

        for key in (SlotKey.HOME1, SlotKey.HOME2, SlotKey.AWAY1, SlotKey.AWAY2):
            draft_slot = getattr(self, key.value)
            if draft_slot is None:
                materialized_slots[key.value] = None
                continue
            cand_id: uuid.UUID | None = None
            if draft_slot.name_source == NameSource.AI_CANDIDATE:
                cand_id = require_uuid(make_id(key), "candidate_id")
                candidates.append(
                    PlayerNameCandidateInput(
                        id=cand_id,
                        run_id=r_id,
                        section_result_id=s_id,
                        workflow_id=self.workflow_id,
                        slot_key=key,
                        fixture_id=self.fixture_id,
                        team_id=team_id_for_slot(
                            key,
                            home_team_id=self.home_team_id,
                            away_team_id=self.away_team_id,
                        ),
                        player_id=draft_slot.player_id,
                        original_name=draft_slot.original_name,
                        candidate_name_ko=draft_slot.name_ko,
                    )
                )
            materialized_slots[key.value] = draft_slot.to_storage_slot(cand_id)

        if self.workflow_id == PlayerSectionWorkflowId.SECTION_PLAYERS:
            return WatchPlayerSectionInput(
                section_result_id=s_id,
                run_id=r_id,
                fixture_id=self.fixture_id,
                home_team_id=self.home_team_id,
                away_team_id=self.away_team_id,
                output_contract_version=self.output_contract_version,
                candidates=tuple(candidates),
                **materialized_slots,
            )
        return InjuryPlayerSectionInput(
            section_result_id=s_id,
            run_id=r_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            candidates=tuple(candidates),
            **materialized_slots,
        )


# --------------------------------------------------------------------------
# C 조회 투영 경계(표시 이름·해석 상태·확인된 외부 ID 기반 사진 URL 분리)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SlotReadProjection:
    """API/화면으로 내보내는 슬롯 읽기 투영."""

    slot_key: SlotKey
    team_side: TeamSide
    resolution_status: SlotResolutionStatus
    display_name: str | None = None
    original_name: str | None = None
    name_source: NameSource | None = None
    player_id: int | None = None
    external_player_id: int | None = None
    photo_url: str | None = None
    body: str | None = None
    unresolved_reason: str | None = None
    translation_candidate_id: uuid.UUID | None = None
    candidate_review_status: CandidateReviewStatus | None = None
    status: str | None = None
    injury: str | None = None
    importance: str | None = None
    evidence: tuple[dict[str, Any], ...] = ()


def project_slot(
    slot_key: SlotKey | str,
    slot: WatchPlayerSlot | InjuryPlayerSlot | None,
    *,
    external_player_id: int | None = None,
    photo_url: str | None = None,
    candidate_review_status: CandidateReviewStatus | None = None,
) -> SlotReadProjection:
    """저장 슬롯을 읽기 투영으로 변환한다. 미확인 선수에게 외부 ID/사진을 붙이지 않는다."""
    key = _require_enum(SlotKey, slot_key, "slot_key")
    ext_id = optional_positive_int(external_player_id, "external_player_id")
    clean_photo = optional_non_empty_text(photo_url, "photo_url")

    if slot is None:
        if ext_id is not None or clean_photo is not None or candidate_review_status is not None:
            raise ContractError("빈 슬롯에는 외부 ID·사진·후보 검수 상태를 둘 수 없습니다.")
        return SlotReadProjection(
            slot_key=key,
            team_side=key.team_side,
            resolution_status=SlotResolutionStatus.EMPTY,
        )

    if slot.player_id is None and (ext_id is not None or clean_photo is not None):
        raise ContractError(
            "player_id가 NULL인 미확인 슬롯에 external_player_id 또는 photo_url을 투영할 수 없습니다."
        )
    if ext_id is None and clean_photo is not None:
        raise ContractError("확인된 external_player_id 없이 photo_url을 만들 수 없습니다.")

    review_status = (
        _require_enum(CandidateReviewStatus, candidate_review_status, "candidate_review_status")
        if candidate_review_status is not None
        else None
    )
    if slot.name_source == NameSource.DB_KO and review_status is not None:
        raise ContractError("db_ko 슬롯에는 candidate_review_status가 없어야 합니다.")

    is_injury = isinstance(slot, InjuryPlayerSlot)
    return SlotReadProjection(
        slot_key=key,
        team_side=key.team_side,
        resolution_status=slot.resolution_status,
        display_name=slot.display_name,
        original_name=slot.original_name,
        name_source=slot.name_source,
        player_id=slot.player_id,
        external_player_id=ext_id,
        photo_url=clean_photo,
        body=slot.body,
        unresolved_reason=slot.unresolved_reason,
        translation_candidate_id=slot.translation_candidate_id,
        candidate_review_status=review_status,
        status=slot.status if is_injury else None,
        injury=slot.injury if is_injury else None,
        importance=slot.importance if is_injury else None,
        evidence=slot.evidence,
    )


__all__ = [
    "CandidateReviewStatus",
    "CandidateSource",
    "FIXED_SLOT_KEYS",
    "INJURY_PLAYERS_OUTPUT_CONTRACT_VERSION",
    "INJURY_PLAYERS_TABLE",
    "INJURY_SLOT_COLUMN_SUFFIXES",
    "InjuryPlayerSectionInput",
    "InjuryPlayerSectionRecord",
    "InjuryPlayerSlot",
    "MAX_CONTENT_REGENERATIONS",
    "MAX_MODULE_ATTEMPTS",
    "MAX_SLOTS_PER_TEAM",
    "NameSource",
    "PLAYER_NAME_CANDIDATES_TABLE",
    "PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS",
    "PLAYER_SECTION_STORAGE_CONTRACT_VERSION",
    "PREVIEW_DEV_SCHEMA",
    "PendingInjurySlotDraft",
    "PendingWatchSlotDraft",
    "PlayerNameCandidateInput",
    "PlayerNameCandidateRecord",
    "PlayerSectionAttemptTrace",
    "PlayerSectionProcessingResult",
    "PlayerSectionWorkflowId",
    "RegenerationReason",
    "SECTION_AVAILABILITY_WORKFLOW_ID",
    "SECTION_PLAYERS_WORKFLOW_ID",
    "SlotKey",
    "SlotReadProjection",
    "SlotResolutionStatus",
    "TeamSide",
    "UnplacedPlayerDiagnostic",
    "UnplacedReason",
    "WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION",
    "WATCH_PLAYERS_TABLE",
    "WATCH_SLOT_COLUMN_SUFFIXES",
    "WatchPlayerSectionInput",
    "WatchPlayerSectionRecord",
    "WatchPlayerSlot",
    "normalize_evidence",
    "optional_non_empty_text",
    "optional_positive_int",
    "optional_uuid",
    "output_contract_version_for",
    "project_slot",
    "require_aware_datetime",
    "require_non_empty_text",
    "require_positive_int",
    "require_uuid",
    "team_id_for_slot",
]
