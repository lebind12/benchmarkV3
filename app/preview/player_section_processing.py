"""NS-02 선수·부상 섹션 생성 후처리 및 진단 조립기.

공통 계약(`app/preview/player_section_contracts.py`)의 Enum·버전·제한을 사용해
원시 모델 JSON을 검사·정규화하고, 팀당 2명 고정 슬롯(`home1`, `home2`, `away1`,
`away2`, `home_etc=None`, `away_etc=None`)과 시도별·제외별 진단을 만든다.

핵심 규칙:
1. 원시 응답의 `player_id`/`player_ref`/`team_id`를 신뢰하지 않고 DB 경기·팀 문맥으로만 검증한다.
2. 누락/중복 검사는 조기 필터링·절단 전에 원시 항목 전체에 대해 수행한다.
3. DB 한글명 우선, 없으면 같은 응답의 AI 한글명 후보(`korean_labels` 등)를 쓴다.
   사용 가능한 한글명이 없으면 영어 원문을 한글로 가장하지 않고 번역 결함으로 남긴다.
4. 본문은 후속 이름 치환으로 재작성하지 않으며, 섹션별 로컬 해석기로 가변 상태를 격리한다.
5. 첫 유효 응답에 설명 누락 또는 중복이 있으면 섹션 단위 1회 재생성 사유를 판정하고,
   최종 채택 응답에서만 설명 누락 제거 -> 중복 중 설명 있는 첫 항목 보존 -> 팀당 앞 2명 배치한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

from app.preview import localized_names
from app.preview import player_section_contracts as psc

_ALLOWED_INJURY_STATUSES = frozenset(
    {"doubtful", "confirmed_absence", "available", "unknown"}
)
_STATUS_LABELS: Mapping[str, str] = {
    "doubtful": "출전 불확실",
    "confirmed_absence": "결장(확정 표기)",
    "available": "출전 가능 표기",
    "unknown": "표기 없음(확정 사실 아님)",
}


def _clean_text(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    return " ".join(str(value).split()).strip()


def _strict_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _has_korean(text: str | None) -> bool:
    return bool(text and localized_names._has_korean(text))


def _surface_key(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def _clean_evidence(value: Any, allowed_ids: frozenset[str] | None = None) -> tuple[tuple[str, ...], int]:
    if not isinstance(value, (list, tuple)):
        return (), 0
    kept: list[str] = []
    dropped = 0
    for item in value:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        if allowed_ids is not None and cleaned not in allowed_ids:
            dropped += 1
            continue
        kept.append(cleaned)
    return tuple(dict.fromkeys(kept)), dropped


def clone_section_resolver(resolver: Any | None) -> Any | None:
    """공유 이름 해석기가 섹션 간 가변 상태를 오염시키지 않도록 로컬 복제본을 반환한다."""
    if resolver is None:
        return None
    fork_fn = getattr(resolver, "fork", None)
    if callable(fork_fn):
        return fork_fn()
    return _SectionScopedResolverProxy(resolver)


class _SectionScopedResolverProxy:
    """`fork()`가 없는 핸들(`_ResolverHandle` 등)을 감싸 섹션 로컬 표기 격리를 보장한다."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._local_model_labels: dict[str, dict[str, Any]] = {}
        self._local_names_cache: dict[tuple[int, ...], Any] = {}

    @property
    def index(self) -> Any:
        return getattr(self._inner, "index", None)

    def _local_names(self, scope_team_ids: Sequence[int] | None = None) -> Any | None:
        effective = tuple(
            int(item) for item in (scope_team_ids or ()) if item is not None
        )
        if not effective:
            effective = tuple(
                int(item)
                for item in (getattr(self._inner, "_default_scope", None) or ())
                if item is not None
            )
        if not effective:
            return None
        if effective in self._local_names_cache:
            return self._local_names_cache[effective]
        names_for = getattr(self._inner, "_names_for", None)
        if callable(names_for):
            base = names_for(effective)
            if base is not None and callable(getattr(base, "fork", None)):
                cloned = base.fork()
                self._local_names_cache[effective] = cloned
                return cloned
        return None

    def resolve_team(
        self,
        value: Any = None,
        *,
        team_id: int | None = None,
        external_id: int | None = None,
        id_space: str = "internal",
        scope_team_ids: Sequence[int] | None = None,
    ) -> Any:
        scope = scope_team_ids
        if not scope and team_id is not None and not isinstance(team_id, bool):
            scope = (int(team_id),)
        local = self._local_names(scope)
        if local is not None:
            return local.resolve_team(
                value, team_id=team_id, external_id=external_id, id_space=id_space
            )
        fn = getattr(self._inner, "resolve_team", None)
        if not callable(fn):
            return None
        try:
            return fn(
                value,
                team_id=team_id,
                external_id=external_id,
                id_space=id_space,
                scope_team_ids=scope_team_ids,
            )
        except TypeError:
            return fn(value, team_id=team_id, external_id=external_id, id_space=id_space)

    def resolve_player(
        self,
        name: Any = "",
        *,
        player_id: int | None = None,
        external_id: int | None = None,
        id_space: str = "internal",
        team_hint: Any = None,
        scope_team_ids: Sequence[int] | None = None,
        id_is_hint: bool = False,
    ) -> Any:
        local = self._local_names(scope_team_ids)
        if local is not None:
            return local.resolve_player(
                name,
                player_id=player_id,
                external_id=external_id,
                id_space=id_space,
                team_hint=team_hint,
                scope_team_ids=scope_team_ids,
                id_is_hint=id_is_hint,
            )
        fn = getattr(self._inner, "resolve_player", None)
        if not callable(fn):
            return None
        return fn(
            name,
            player_id=player_id,
            external_id=external_id,
            id_space=id_space,
            team_hint=team_hint,
            scope_team_ids=scope_team_ids,
            id_is_hint=id_is_hint,
        )

    def register_model_labels(
        self, labels: Any, *, scope_team_ids: Sequence[int] | None = None
    ) -> tuple[dict[str, Any], ...]:
        local = self._local_names(scope_team_ids)
        if local is not None and callable(getattr(local, "register_model_labels", None)):
            return local.register_model_labels(labels)
        return ()

    def rewrite_body(self, text: str) -> str:
        # NS-02 계약: 본문은 생성 시점 원문을 유지하며 후속 이름 치환으로 재작성하지 않는다.
        return text


@dataclass(frozen=True)
class FixtureTeamContext:
    """경기 홈·원정 팀 검증 기준."""

    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    home_team_name: str | None = None
    away_team_name: str | None = None

    @property
    def scope_team_ids(self) -> tuple[int, ...]:
        ids: list[int] = []
        if self.home_team_id is not None:
            ids.append(self.home_team_id)
        if self.away_team_id is not None:
            ids.append(self.away_team_id)
        return tuple(ids)


@dataclass(frozen=True)
class PlayerSectionSlotDraft:
    """처리 파이프라인의 고정 슬롯('저장 예정 값')."""

    slot_key: psc.SlotKey
    team_side: psc.TeamSide
    team_id: int | None
    team_name: str | None
    player_id: int | None
    external_player_id: int | None
    original_name: str
    name_ko: str
    name_source: psc.NameSource
    body: str
    evidence: tuple[str, ...] = ()
    unresolved_reason: str | None = None
    status: str | None = None
    injury: str | None = None
    importance: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "slot_key": self.slot_key.value,
            "team_side": self.team_side.value,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "player_id": self.player_id,
            "external_player_id": self.external_player_id,
            "resolution_status": (
                psc.SlotResolutionStatus.RESOLVED.value
                if self.player_id is not None
                else psc.SlotResolutionStatus.UNRESOLVED.value
            ),
            "original_name": self.original_name,
            "name_ko": self.name_ko,
            "name_source": self.name_source.value,
            "body": self.body,
            "unresolved_reason": self.unresolved_reason,
            "evidence": list(self.evidence),
        }
        if self.status is not None:
            payload["status"] = self.status
            payload["injury"] = self.injury
            payload["importance"] = self.importance
        return payload


@dataclass(frozen=True)
class ProcessingUnplacedItem:
    """4슬롯에 들어가지 못한 후보 항목과 사유."""

    original_name: str
    reason: psc.UnplacedReason
    team_hint: str | None = None
    team_id: int | None = None
    player_id: int | None = None
    external_player_id: int | None = None
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_name": self.original_name,
            "reason": self.reason.value,
            "team_hint": self.team_hint,
            "team_id": self.team_id,
            "player_id": self.player_id,
            "external_player_id": self.external_player_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ProcessingAttemptRecord:
    """모듈 전송 시도 1회의 생성·재생성 추적 기록(0부터 시작하는 실제 ordinal)."""

    attempt_ordinal: int
    logical_call_id: str
    parsed_valid: bool
    raw_text: str | None = None
    parsed_json: Mapping[str, Any] | None = None
    regeneration_triggered: bool = False
    regeneration_reason: psc.RegenerationReason | None = None
    error_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_ordinal": self.attempt_ordinal,
            "logical_call_id": self.logical_call_id,
            "parsed_valid": self.parsed_valid,
            "raw_text": self.raw_text,
            "parsed_json": dict(self.parsed_json) if self.parsed_json is not None else None,
            "regeneration_triggered": self.regeneration_triggered,
            "regeneration_reason": (
                self.regeneration_reason.value if self.regeneration_reason is not None else None
            ),
            "error_reason": self.error_reason,
        }


@dataclass(frozen=True)
class PlayerSectionProcessingBundle:
    """NS-02 선수·부상 섹션 처리 결과('저장 예정 값' 및 진단 묶음)."""

    workflow_id: psc.PlayerSectionWorkflowId
    fixture_id: int
    home_team_id: int | None
    away_team_id: int | None
    output_contract_version: str
    home1: PlayerSectionSlotDraft | None = None
    home2: PlayerSectionSlotDraft | None = None
    away1: PlayerSectionSlotDraft | None = None
    away2: PlayerSectionSlotDraft | None = None
    home_etc: None = None
    away_etc: None = None
    regeneration_count: int = 0
    regeneration_reason: psc.RegenerationReason | None = None
    module_attempt_count: int = 0
    adopted_attempt_ordinal: int | None = None
    attempts: tuple[ProcessingAttemptRecord, ...] = ()
    unplaced_items: tuple[ProcessingUnplacedItem, ...] = ()
    diagnostics: tuple[str, ...] = ()
    translation_defects: tuple[str, ...] = ()
    korean_labels: tuple[dict[str, Any], ...] = ()
    dropped_evidence_count: int = 0
    failed_reason: str | None = None
    persisted: bool = False
    mode: str = "live"

    @property
    def placed_slots(self) -> tuple[PlayerSectionSlotDraft, ...]:
        out: list[PlayerSectionSlotDraft] = []
        for attr in psc.FIXED_SLOT_KEYS:
            slot = getattr(self, attr)
            if slot is not None:
                out.append(slot)
        return tuple(out)

    @property
    def ok(self) -> bool:
        return self.failed_reason is None and bool(self.placed_slots)

    def to_contract_result(self) -> psc.PlayerSectionProcessingResult | None:
        """유효한 처리 결과를 공통 계약 `PlayerSectionProcessingResult`로 변환한다."""
        if not self.ok or self.adopted_attempt_ordinal is None or not self.attempts:
            return None

        def _convert_slot(
            slot: PlayerSectionSlotDraft | None,
        ) -> psc.PendingWatchSlotDraft | psc.PendingInjurySlotDraft | None:
            if slot is None:
                return None
            if self.workflow_id == psc.PlayerSectionWorkflowId.SECTION_PLAYERS:
                return psc.PendingWatchSlotDraft(
                    player_id=slot.player_id,
                    original_name=slot.original_name,
                    name_ko=slot.name_ko,
                    body=slot.body,
                    name_source=slot.name_source,
                    unresolved_reason=slot.unresolved_reason,
                    evidence=slot.evidence,
                )
            return psc.PendingInjurySlotDraft(
                player_id=slot.player_id,
                original_name=slot.original_name,
                name_ko=slot.name_ko,
                body=slot.body,
                name_source=slot.name_source,
                status=slot.status or "unknown",
                injury=slot.injury,
                importance=slot.importance,
                unresolved_reason=slot.unresolved_reason,
                evidence=slot.evidence,
            )

        traces = tuple(
            psc.PlayerSectionAttemptTrace(
                attempt_ordinal=item.attempt_ordinal,
                logical_call_id=item.logical_call_id,
                raw_text=item.raw_text,
                parsed_json=dict(item.parsed_json) if item.parsed_json is not None else None,
                regeneration_triggered=item.regeneration_triggered,
                regeneration_reason=item.regeneration_reason,
            )
            for item in self.attempts
        )
        unplaced = tuple(
            psc.UnplacedPlayerDiagnostic(
                original_name=item.original_name,
                reason=item.reason,
                team_hint=item.team_hint,
                team_id=item.team_id,
                player_id=item.player_id,
                detail=item.detail,
            )
            for item in self.unplaced_items
        )
        return psc.PlayerSectionProcessingResult(
            workflow_id=self.workflow_id,
            fixture_id=self.fixture_id,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            output_contract_version=self.output_contract_version,
            home1=_convert_slot(self.home1),
            home2=_convert_slot(self.home2),
            away1=_convert_slot(self.away1),
            away2=_convert_slot(self.away2),
            home_etc=None,
            away_etc=None,
            regeneration_count=self.regeneration_count,
            module_attempt_count=self.module_attempt_count,
            adopted_attempt_ordinal=self.adopted_attempt_ordinal,
            attempts=traces,
            unplaced_items=unplaced,
            persisted=self.persisted,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id.value,
            "fixture_id": self.fixture_id,
            "home_team_id": self.home_team_id,
            "away_team_id": self.away_team_id,
            "output_contract_version": self.output_contract_version,
            "persisted": self.persisted,
            "storage_status": "저장됨" if self.persisted else "저장 예정 값",
            "mode": self.mode,
            "ok": self.ok,
            "failed_reason": self.failed_reason,
            "home1": self.home1.to_dict() if self.home1 is not None else None,
            "home2": self.home2.to_dict() if self.home2 is not None else None,
            "away1": self.away1.to_dict() if self.away1 is not None else None,
            "away2": self.away2.to_dict() if self.away2 is not None else None,
            "home_etc": None,
            "away_etc": None,
            "regeneration_count": self.regeneration_count,
            "regeneration_reason": (
                self.regeneration_reason.value if self.regeneration_reason is not None else None
            ),
            "module_attempt_count": self.module_attempt_count,
            "adopted_attempt_ordinal": self.adopted_attempt_ordinal,
            "attempts": [item.to_dict() for item in self.attempts],
            "unplaced_items": [item.to_dict() for item in self.unplaced_items],
            "translation_defects": list(self.translation_defects),
            "diagnostics": list(self.diagnostics),
            "korean_labels": [dict(item) for item in self.korean_labels],
            "dropped_evidence_count": self.dropped_evidence_count,
        }


@dataclass(frozen=True)
class _EvaluatedCandidate:
    """원시 응답 항목 1건의 정규화·검증 중간 결과."""

    index: int
    original_name: str
    team_hint: str | None
    team_side: psc.TeamSide | None
    resolved_team_id: int | None
    resolved_team_name: str | None
    player_id: int | None
    external_player_id: int | None
    name_ko: str | None
    name_source: psc.NameSource | None
    unresolved_reason: str | None
    body: str
    evidence: tuple[str, ...]
    dropped_evidence: int
    status: str | None = None
    injury: str | None = None
    importance: str | None = None
    missing_name: bool = False
    missing_body: bool = False
    missing_name_ko: bool = False

    @property
    def identity_key(self) -> tuple[Any, ...]:
        if self.player_id is not None:
            return ("db", self.player_id)
        if not self.original_name:
            return ("raw_index", self.index)
        side_key = self.team_side.value if self.team_side is not None else "team_unresolved"
        return ("unresolved", side_key, _surface_key(self.original_name))


def extract_korean_labels(payload: Mapping[str, Any] | None) -> tuple[dict[str, Any], ...]:
    """같은 응답이 낸 `korean_labels`를 안전하게 정규화한다(한국어 포함 후보만 유지)."""
    if not isinstance(payload, Mapping):
        return ()
    raw = payload.get("korean_labels")
    if not isinstance(raw, (list, tuple)):
        return ()
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, Mapping):
            continue
        original = _clean_text(entry.get("original"))
        korean = _clean_text(entry.get("korean"))
        kind = _clean_text(entry.get("kind")).lower() or "player"
        if not original or not korean or not _has_korean(korean):
            continue
        if kind not in {"team", "player", "coach"}:
            continue
        out.append({"original": original, "korean": korean, "kind": kind})
    return tuple(out)


def _lookup_ai_korean_label(
    original: str,
    labels: Sequence[Mapping[str, Any]],
    *,
    kind: str,
) -> str | None:
    target = _surface_key(original)
    if not target:
        return None
    for entry in labels:
        entry_kind = _clean_text(entry.get("kind")).lower()
        if entry_kind and entry_kind != kind:
            continue
        if _surface_key(_clean_text(entry.get("original"))) == target:
            korean = _clean_text(entry.get("korean"))
            if _has_korean(korean):
                return korean
    return None


def _resolve_team_side(
    *,
    team_hint: str | None,
    raw_team_id: int | None,
    fixture: FixtureTeamContext,
    resolver: Any | None,
) -> tuple[psc.TeamSide | None, int | None, str | None]:
    """팀 표기를 홈·원정으로 검증한다. 신뢰할 수 없는 숫자는 버린다."""
    home_surfaces = {_surface_key(fixture.home_team_name)} if fixture.home_team_name else set()
    away_surfaces = {_surface_key(fixture.away_team_name)} if fixture.away_team_name else set()

    if resolver is not None and callable(getattr(resolver, "resolve_team", None)):
        if fixture.home_team_id is not None:
            home_row = resolver.resolve_team(
                fixture.home_team_name, team_id=fixture.home_team_id, id_space="internal"
            )
            if home_row is not None:
                for val in (
                    getattr(home_row, "english_name", None),
                    getattr(home_row, "name_ko", None),
                    getattr(home_row, "display_name", None),
                ):
                    cleaned = _clean_text(val)
                    if cleaned:
                        home_surfaces.add(_surface_key(cleaned))
        if fixture.away_team_id is not None:
            away_row = resolver.resolve_team(
                fixture.away_team_name, team_id=fixture.away_team_id, id_space="internal"
            )
            if away_row is not None:
                for val in (
                    getattr(away_row, "english_name", None),
                    getattr(away_row, "name_ko", None),
                    getattr(away_row, "display_name", None),
                ):
                    cleaned = _clean_text(val)
                    if cleaned:
                        away_surfaces.add(_surface_key(cleaned))

    if team_hint:
        hint_key = _surface_key(team_hint)
        if hint_key in home_surfaces:
            return psc.TeamSide.HOME, fixture.home_team_id, fixture.home_team_name or team_hint
        if hint_key in away_surfaces:
            return psc.TeamSide.AWAY, fixture.away_team_id, fixture.away_team_name or team_hint
        if resolver is not None and callable(getattr(resolver, "resolve_team", None)):
            resolved_team = resolver.resolve_team(team_hint)
            team_id = _strict_int(getattr(resolved_team, "team_id", None))
            if team_id is not None:
                display = _clean_text(getattr(resolved_team, "display_name", None)) or team_hint
                if team_id == fixture.home_team_id:
                    return psc.TeamSide.HOME, fixture.home_team_id, display
                if team_id == fixture.away_team_id:
                    return psc.TeamSide.AWAY, fixture.away_team_id, display
                # 경기의 홈·원정 팀과 다른 제3팀을 가리키면 미확인으로 둔다.
                return None, None, None
        return None, None, None

    if raw_team_id is not None:
        if fixture.home_team_id is not None and raw_team_id == fixture.home_team_id:
            return psc.TeamSide.HOME, fixture.home_team_id, fixture.home_team_name
        if fixture.away_team_id is not None and raw_team_id == fixture.away_team_id:
            return psc.TeamSide.AWAY, fixture.away_team_id, fixture.away_team_name
    return None, None, None


def _compose_injury_body(injury: str | None, importance: str | None) -> str:
    return " ".join(part for part in (injury, importance) if part)


def _normalize_injury_status(raw_status: Any) -> str:
    cleaned = _clean_text(raw_status).lower()
    if cleaned in _ALLOWED_INJURY_STATUSES:
        return cleaned
    return "unknown"


def _resolve_player_identity_and_name(
    *,
    original_name: str,
    team_hint: str | None,
    resolved_team_id: int | None,
    fixture: FixtureTeamContext,
    resolver: Any | None,
    labels: Sequence[Mapping[str, Any]],
) -> tuple[int | None, int | None, str | None, psc.NameSource | None, str | None, int | None]:
    """DB 문맥으로 player_id·external_player_id·한글명을 검증한다.

    반환: (player_id, external_player_id, name_ko, name_source, unresolved_reason, inferred_team_id)
    """
    if not original_name:
        return None, None, None, None, "선수 이름 누락", None

    scope: tuple[int, ...]
    if resolved_team_id is not None:
        scope = (resolved_team_id,)
    else:
        scope = fixture.scope_team_ids

    verified_player_id: int | None = None
    verified_external_id: int | None = None
    db_korean: str | None = None
    inferred_team_id: int | None = None
    unresolved_reason: str | None = None

    if resolver is not None and callable(getattr(resolver, "resolve_player", None)) and scope:
        # 모델의 숫자/bool player_ref/player_id는 절대 신뢰해 넘기지 않고 이름·팀·경기 문맥으로만 찾는다.
        resolution = resolver.resolve_player(
            original_name,
            team_hint=team_hint,
            scope_team_ids=scope,
            id_is_hint=False,
        )
        resolved_player = getattr(resolution, "player", None)
        if resolved_player is not None:
            cand_player_id = _strict_int(getattr(resolved_player, "player_id", None))
            if cand_player_id is not None:
                verified_player_id = cand_player_id
                verified_external_id = _strict_int(getattr(resolved_player, "external_id", None))
                # DB row의 실제 한국어 값과 current_team_id를 인덱스에서 직접 확인한다.
                index = getattr(resolver, "index", None)
                row = (
                    index.player(player_id=verified_player_id)
                    if index is not None and callable(getattr(index, "player", None))
                    else None
                )
                if row is not None:
                    db_korean = _clean_text(getattr(row, "korean", None)) or None
                    if verified_external_id is None:
                        verified_external_id = _strict_int(getattr(row, "external_id", None))
                    inferred_team_id = _strict_int(getattr(row, "current_team_id", None))
                else:
                    row_ko = _clean_text(getattr(resolved_player, "name_ko", None))
                    db_korean = row_ko if row_ko and _has_korean(row_ko) else None
        else:
            unmapped = getattr(resolution, "unmapped", None)
            reason_val = getattr(getattr(unmapped, "reason", None), "value", None) or "not_found"
            unresolved_reason = f"DB 선수 미확인 ({reason_val})"
    else:
        unresolved_reason = "DB 이름 해석기 없음" if resolver is None else "경기 팀 범위 없음"

    if db_korean:
        return (
            verified_player_id,
            verified_external_id,
            db_korean,
            psc.NameSource.DB_KO,
            None,
            inferred_team_id,
        )

    ai_candidate = _lookup_ai_korean_label(original_name, labels, kind="player")
    if not ai_candidate and _has_korean(original_name):
        ai_candidate = original_name

    if ai_candidate:
        final_unresolved = unresolved_reason if verified_player_id is None else None
        return (
            verified_player_id,
            verified_external_id,
            ai_candidate,
            psc.NameSource.AI_CANDIDATE,
            final_unresolved,
            inferred_team_id,
        )

    return (
        verified_player_id,
        verified_external_id,
        None,
        None,
        unresolved_reason,
        inferred_team_id,
    )


def evaluate_raw_candidates(
    *,
    workflow_id: psc.PlayerSectionWorkflowId,
    payload: Mapping[str, Any],
    fixture: FixtureTeamContext,
    resolver: Any | None,
    allowed_evidence: frozenset[str] | None = None,
) -> tuple[tuple[_EvaluatedCandidate, ...], tuple[dict[str, Any], ...]]:
    """원시 응답의 모든 항목을 조기 탈락·절단 없이 평가한다."""
    labels = extract_korean_labels(payload)
    if workflow_id == psc.PlayerSectionWorkflowId.SECTION_PLAYERS:
        raw_items = payload.get("players")
    else:
        raw_items = payload.get("injuries")

    if not isinstance(raw_items, (list, tuple)):
        return (), labels

    evaluated: list[_EvaluatedCandidate] = []
    for idx, raw in enumerate(raw_items):
        if not isinstance(raw, Mapping):
            continue
        if workflow_id == psc.PlayerSectionWorkflowId.SECTION_PLAYERS:
            original_name = _clean_text(
                raw.get("selected_player") or raw.get("player")
            )
            team_hint = _clean_text(raw.get("team")) or None
            body = _clean_text(
                raw.get("selection_reason") or raw.get("reason")
            )
            status = None
            injury = None
            importance = None
            missing_body = not body
        else:
            original_name = _clean_text(raw.get("player_name") or raw.get("player"))
            team_hint = _clean_text(raw.get("team")) or None
            injury = _clean_text(raw.get("injury")) or None
            importance = _clean_text(raw.get("importance")) or None
            status = _normalize_injury_status(raw.get("status"))
            body = _compose_injury_body(injury, importance)
            missing_body = injury is None and importance is None

        evidence, dropped = _clean_evidence(raw.get("evidence"), allowed_evidence)
        raw_team_id = _strict_int(raw.get("team_id"))
        team_side, resolved_team_id, resolved_team_name = _resolve_team_side(
            team_hint=team_hint,
            raw_team_id=raw_team_id,
            fixture=fixture,
            resolver=resolver,
        )

        (
            player_id,
            external_player_id,
            name_ko,
            name_source,
            unresolved_reason,
            inferred_team_id,
        ) = _resolve_player_identity_and_name(
            original_name=original_name,
            team_hint=team_hint,
            resolved_team_id=resolved_team_id,
            fixture=fixture,
            resolver=resolver,
            labels=labels,
        )

        # 팀 힌트가 비었을 때도 DB에서 검증된 소속 팀이 경기 팀이면 홈·원정을 확정한다.
        if team_side is None and team_hint is None and inferred_team_id is not None:
            if inferred_team_id == fixture.home_team_id:
                team_side = psc.TeamSide.HOME
                resolved_team_id = fixture.home_team_id
                resolved_team_name = fixture.home_team_name
            elif inferred_team_id == fixture.away_team_id:
                team_side = psc.TeamSide.AWAY
                resolved_team_id = fixture.away_team_id
                resolved_team_name = fixture.away_team_name

        # 팀 한국어 표기가 있으면 슬롯 팀 표시에도 반영한다.
        if resolved_team_name and not _has_korean(resolved_team_name):
            ai_team_ko = _lookup_ai_korean_label(resolved_team_name, labels, kind="team")
            if ai_team_ko:
                resolved_team_name = ai_team_ko

        missing_name = not original_name
        missing_name_ko = (not missing_name) and (name_ko is None)
        evaluated.append(
            _EvaluatedCandidate(
                index=idx,
                original_name=original_name,
                team_hint=team_hint,
                team_side=team_side,
                resolved_team_id=resolved_team_id,
                resolved_team_name=resolved_team_name,
                player_id=player_id,
                external_player_id=external_player_id,
                name_ko=name_ko,
                name_source=name_source,
                unresolved_reason=unresolved_reason,
                body=body,
                evidence=evidence,
                dropped_evidence=dropped,
                status=status,
                injury=injury,
                importance=importance,
                missing_name=missing_name,
                missing_body=missing_body,
                missing_name_ko=missing_name_ko,
            )
        )
    return tuple(evaluated), labels


def detect_regeneration_reason(
    candidates: Sequence[_EvaluatedCandidate],
) -> psc.RegenerationReason | None:
    """조기 필터링·팀당 2명 절단 전에 원시 응답의 설명 누락·중복 여부를 판정한다."""
    if not candidates:
        return None

    has_missing_body = any(c.missing_body for c in candidates)
    seen_identities: set[tuple[Any, ...]] = set()
    has_duplicate = False
    for cand in candidates:
        if cand.missing_name:
            continue
        key = cand.identity_key
        if key in seen_identities:
            has_duplicate = True
            break
        seen_identities.add(key)

    if has_missing_body and has_duplicate:
        return psc.RegenerationReason.MISSING_AND_DUPLICATE
    if has_missing_body:
        return psc.RegenerationReason.MISSING_BODY
    if has_duplicate:
        return psc.RegenerationReason.DUPLICATE_PLAYER
    return None


def place_final_candidates(
    *,
    workflow_id: psc.PlayerSectionWorkflowId,
    fixture: FixtureTeamContext,
    candidates: Sequence[_EvaluatedCandidate],
    labels: Sequence[Mapping[str, Any]],
    attempts: Sequence[ProcessingAttemptRecord],
    regeneration_count: int,
    regeneration_reason: psc.RegenerationReason | None,
    adopted_attempt_ordinal: int,
    mode: str = "live",
) -> PlayerSectionProcessingBundle:
    """최종 응답에서 설명 누락 제거 -> 중복 중 설명 있는 첫 항목 보존 -> 팀당 앞 2명 배치."""
    unplaced: list[ProcessingUnplacedItem] = []
    diagnostics: list[str] = []
    translation_defects: list[str] = []
    dropped_total = sum(c.dropped_evidence for c in candidates)

    # 1. 이름·설명 누락 항목 먼저 제외
    with_body: list[_EvaluatedCandidate] = []
    for cand in candidates:
        if cand.missing_name:
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name="(이름 누락)",
                    reason=psc.UnplacedReason.MISSING_NAME,
                    team_hint=cand.team_hint,
                    team_id=cand.resolved_team_id,
                    detail="원시 JSON 항목에 선수 이름이 비어 제외했습니다.",
                )
            )
            continue
        if cand.missing_body:
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name=cand.original_name,
                    reason=psc.UnplacedReason.MISSING_BODY,
                    team_hint=cand.team_hint,
                    team_id=cand.resolved_team_id,
                    player_id=cand.player_id,
                    external_player_id=cand.external_player_id,
                    detail="설명(selection_reason 또는 injury/importance)이 비어 제외했습니다.",
                )
            )
            continue
        with_body.append(cand)

    # 2. 설명이 있는 첫 항목을 보존하고 이후 중복 항목 제외
    deduped: list[_EvaluatedCandidate] = []
    seen: set[tuple[Any, ...]] = set()
    for cand in with_body:
        key = cand.identity_key
        if key in seen:
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name=cand.original_name,
                    reason=psc.UnplacedReason.DUPLICATE_PLAYER,
                    team_hint=cand.team_hint,
                    team_id=cand.resolved_team_id,
                    player_id=cand.player_id,
                    external_player_id=cand.external_player_id,
                    detail="동일 선수 중복으로 첫 번째 유효 설명 항목만 유지하고 제외했습니다.",
                )
            )
            continue
        seen.add(key)
        deduped.append(cand)

    # 3. 팀 미확인 및 사용 가능한 한글명 누락 제외 후 팀당 앞 2명 배치
    by_side: dict[psc.TeamSide, list[_EvaluatedCandidate]] = {
        psc.TeamSide.HOME: [],
        psc.TeamSide.AWAY: [],
    }
    for cand in deduped:
        if cand.team_side is None:
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name=cand.original_name,
                    reason=psc.UnplacedReason.TEAM_UNRESOLVED,
                    team_hint=cand.team_hint,
                    player_id=cand.player_id,
                    external_player_id=cand.external_player_id,
                    detail="홈·원정 팀을 검증할 수 없어 임의 배치하지 않았습니다.",
                )
            )
            continue
        if cand.missing_name_ko or cand.name_ko is None or cand.name_source is None:
            msg = (
                f"번역 결함: {cand.original_name}"
                f"{f' (player_id={cand.player_id})' if cand.player_id is not None else ''}"
                "의 DB 한글명과 같은 응답 AI 한글명 후보가 모두 없어 영어 원문으로 채우지 않았습니다."
            )
            translation_defects.append(msg)
            diagnostics.append(msg)
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name=cand.original_name,
                    reason=psc.UnplacedReason.MISSING_NAME_KO,
                    team_hint=cand.team_hint,
                    team_id=cand.resolved_team_id,
                    player_id=cand.player_id,
                    external_player_id=cand.external_player_id,
                    detail=msg,
                )
            )
            continue
        bucket = by_side[cand.team_side]
        if len(bucket) >= psc.MAX_SLOTS_PER_TEAM:
            unplaced.append(
                ProcessingUnplacedItem(
                    original_name=cand.original_name,
                    reason=psc.UnplacedReason.SLOT_CAPACITY_EXCEEDED,
                    team_hint=cand.team_hint,
                    team_id=cand.resolved_team_id,
                    player_id=cand.player_id,
                    external_player_id=cand.external_player_id,
                    detail=f"팀당 최대 {psc.MAX_SLOTS_PER_TEAM}명 슬롯 상한을 넘어 제외했습니다.",
                )
            )
            continue
        bucket.append(cand)

    slots: dict[str, PlayerSectionSlotDraft | None] = {
        key: None for key in psc.FIXED_SLOT_KEYS
    }
    for side in (psc.TeamSide.HOME, psc.TeamSide.AWAY):
        for idx, cand in enumerate(by_side[side], start=1):
            slot_key = psc.SlotKey.for_team(side, idx)
            assert cand.name_ko is not None and cand.name_source is not None
            slots[slot_key.value] = PlayerSectionSlotDraft(
                slot_key=slot_key,
                team_side=side,
                team_id=cand.resolved_team_id,
                team_name=cand.resolved_team_name or cand.team_hint,
                player_id=cand.player_id,
                external_player_id=cand.external_player_id,
                original_name=cand.original_name,
                name_ko=cand.name_ko,
                name_source=cand.name_source,
                body=cand.body,
                evidence=cand.evidence,
                unresolved_reason=cand.unresolved_reason,
                status=cand.status,
                injury=cand.injury,
                importance=cand.importance,
            )

    if dropped_total:
        diagnostics.append(
            f"전달하지 않은 근거 id 인용 {dropped_total}건을 표시 근거에서 뺐습니다."
        )

    has_any_slot = any(slots[k] is not None for k in psc.FIXED_SLOT_KEYS)
    failed_reason: str | None = None
    if not has_any_slot:
        if translation_defects:
            failed_reason = (
                "사용 가능한 한글명(DB 또는 AI 후보)이 있는 선수가 없어 정상 결과를 만들지 않았습니다."
            )
        else:
            failed_reason = (
                "고정 4슬롯에 배치 가능한 유효 선수 항목이 없어 본문을 만들지 않았습니다."
            )

    return PlayerSectionProcessingBundle(
        workflow_id=workflow_id,
        fixture_id=fixture.fixture_id,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
        output_contract_version=psc.output_contract_version_for(workflow_id),
        home1=slots["home1"],
        home2=slots["home2"],
        away1=slots["away1"],
        away2=slots["away2"],
        home_etc=None,
        away_etc=None,
        regeneration_count=regeneration_count,
        regeneration_reason=regeneration_reason,
        module_attempt_count=len(attempts),
        adopted_attempt_ordinal=adopted_attempt_ordinal,
        attempts=tuple(attempts),
        unplaced_items=tuple(unplaced),
        diagnostics=tuple(diagnostics),
        translation_defects=tuple(translation_defects),
        korean_labels=tuple(dict(item) for item in labels),
        dropped_evidence_count=dropped_total,
        failed_reason=failed_reason,
        persisted=False,
        mode=mode,
    )


def build_failed_processing_bundle(
    *,
    workflow_id: psc.PlayerSectionWorkflowId,
    fixture: FixtureTeamContext,
    attempts: Sequence[ProcessingAttemptRecord],
    regeneration_count: int,
    regeneration_reason: psc.RegenerationReason | None,
    failed_reason: str,
    mode: str = "live",
) -> PlayerSectionProcessingBundle:
    """재생성·전송 실패 시 첫 응답으로 대체하지 않고 실패 진단 묶음을 만든다."""
    return PlayerSectionProcessingBundle(
        workflow_id=workflow_id,
        fixture_id=fixture.fixture_id,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
        output_contract_version=psc.output_contract_version_for(workflow_id),
        regeneration_count=regeneration_count,
        regeneration_reason=regeneration_reason,
        module_attempt_count=len(attempts),
        adopted_attempt_ordinal=None,
        attempts=tuple(attempts),
        diagnostics=(failed_reason,),
        failed_reason=failed_reason,
        persisted=False,
        mode=mode,
    )


def compose_availability_body(slots: Sequence[PlayerSectionSlotDraft]) -> str:
    """부상·결장 고정 슬롯으로부터 본문을 결정적으로 조립한다."""
    if not slots:
        return ""
    blocks: list[str] = []
    current: str | None = None
    lines: list[str] = []
    for slot in slots:
        team = slot.team_name or "팀 미확인"
        if current != team:
            if lines:
                blocks.append("\n".join(lines))
            lines = [f"### {team}"]
            current = team
        status_label = _STATUS_LABELS.get(slot.status or "unknown", _STATUS_LABELS["unknown"])
        lines.append(f"- {slot.name_ko}: {status_label}")
        if slot.injury:
            lines.append(f"  부상 내용: {slot.injury}")
        if slot.importance:
            lines.append(f"  영향: {slot.importance}")
    if lines:
        blocks.append("\n".join(lines))
    return "\n\n".join(
        ["## 부상·결장 영향", "확인된 부상·결장 상황만 정리했습니다.", *blocks]
    )


def build_regeneration_instruction(
    *,
    workflow_id: psc.PlayerSectionWorkflowId,
    reason: psc.RegenerationReason,
) -> str:
    """첫 유효 응답의 누락/중복 결함에 대해 섹션 전체 1회 재생성 지시문을 만든다."""
    if workflow_id == psc.PlayerSectionWorkflowId.SECTION_PLAYERS:
        body_desc = "선정 이유(selection_reason)"
        item_desc = "각 팀 최대 2명의 서로 다른 선수"
    else:
        body_desc = "부상 내용(injury)과 중요도 영향(importance)"
        item_desc = "각 팀 최대 2명의 서로 다른 부상·결장 선수"

    problems: list[str] = []
    if reason in (psc.RegenerationReason.MISSING_BODY, psc.RegenerationReason.MISSING_AND_DUPLICATE):
        problems.append(f"{body_desc}이 비어 있는 항목이 포함되었습니다.")
    if reason in (psc.RegenerationReason.DUPLICATE_PLAYER, psc.RegenerationReason.MISSING_AND_DUPLICATE):
        problems.append("동일 선수가 중복 포함되었습니다.")

    return (
        "\n\n[재생성 요청] 직전 응답에 다음 문제가 있었습니다: "
        + " ".join(problems)
        + f" 전체 섹션을 다시 작성해 {item_desc}를 중복 없이 빠짐없이 "
        + f"구체적인 {body_desc} 및 korean_labels와 함께 JSON으로만 출력하세요."
    )
