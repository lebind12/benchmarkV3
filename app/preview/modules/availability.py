"""MP-06 R2 부상·결장 영향 조사.

이 모듈이 하는 일은 **한 경기**의 부상·결장 상황을 근거와 함께 정리하는 것이다.
사용자가 보는 단위는 이 모듈이 아니라 `section_availability` 워크플로우이며, 이
파일은 그 워크플로우의 `research` 노드와 `compose_body` 노드를 제공한다.

경계:

- 모델 네트워크는 `provider.request_model` 하나로만 나간다. 정상 경로 호출은 **1회**이고
  재시도·예산은 공통 실행기(`retry.RunBudget`/`execute_request`)가 소유한다.
- 본문은 **검증된 구조화 결과**에서 결정적으로 만든다. 두 번째 숨은 LLM 호출로
  다듬지 않는다.
- API 부상 사실과 검색 근거를 구분해 보존한다. 출전 불확실 표기를 결장 확정으로
  승격하지 않고, 빈 목록·미제공·호출 실패를 "부상자 0명"으로 바꾸지 않는다.
- 자료 누락·검색 미확보·호출 오류는 **관리자 진단**으로 남긴다. 독자용 본문에는
  누락 안내 문단을 넣지 않는다. 근거가 전혀 없으면 본문을 만들지 않고 초안으로 둔다.
- 선수 이름을 만들지 않는다. 저장된 DB 부상 행은 `player_name=None`일 수 있고, 그때는
  식별자만 쓴다. 검색에서 실제 이름을 확인했을 때만 이름을 쓴다.

정직성 규칙:

- 모델이 제시한 URL은 이번 호출의 grounding 결과에 실제로 있는 주소만 인정한다.
  없는 URL·모르는 근거 id가 붙은 항목은 채택하지 않고 진단에 남긴다.
- `mode`는 주입된 transport가 밝힌 값에서만 나온다. mock·replay를 live로 표시하지 않는다.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy.orm import Session

from app.preview import provider, store
from app.preview.contracts import (
    ClaimDecision,
    ClaimKind,
    CoverageEntry,
    CoverageState,
    EvidenceClaim,
    ExecutionContext,
    FixtureIdentity,
    ModuleInput,
    QualityStatus,
    RunMode,
    SourceKind,
    ValidationStatus,
)
from app.preview.runner import (
    COMPOSE_MODULE_ID,
    NodeImplementation,
    NodeOutcome,
    SectionNodeContext,
    SectionState,
    WorkflowImplementations,
)
from app.preview.sources import api_football as api

__all__ = [
    "AVAILABILITY_MODULE_ID",
    "COMPOSE_IMPLEMENTATION_VERSION",
    "IMPLEMENTATION_VERSION",
    "MATERIAL_STATES",
    "PROMPT_VERSION",
    "AvailabilityFacts",
    "AvailabilityOutcome",
    "ComposedAvailability",
    "GroundingInfo",
    "GroundingSource",
    "InjuryFact",
    "ValidatedAvailability",
    "availability_compose_node",
    "availability_research_node",
    "build_availability_implementations",
    "compose_availability_body",
    "extract_grounding",
    "injury_facts_from_material",
    "parse_model_output",
    "research_availability",
    "validate_model_output",
]

# 섹션 워크플로우 등록부(`section_availability`)의 조사 모듈 id.
AVAILABILITY_MODULE_ID = "R2"
IMPLEMENTATION_VERSION = "mp06-r2-1"
COMPOSE_IMPLEMENTATION_VERSION = "mp06-r2-compose-1"
PROMPT_VERSION = "mp06-r2-prompt-1"

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "availability.md"

LOGICAL_CALL_ID = "section_availability/research-r2"
SEARCH_PROVIDER = "vertex-google-search"

# 부상 자료의 상태. 서로 다른 사실이므로 한 값으로 합치지 않는다.
STATE_AVAILABLE = "available"
STATE_EMPTY_RESPONSE = "empty_response"
STATE_API_NOT_PROVIDED = "api_not_provided"
STATE_CALL_ERROR = "call_error"
STATE_NOT_RUN = "not_run"
MATERIAL_STATES = (
    STATE_AVAILABLE,
    STATE_EMPTY_RESPONSE,
    STATE_API_NOT_PROVIDED,
    STATE_CALL_ERROR,
    STATE_NOT_RUN,
)

STATE_LABELS = {
    STATE_AVAILABLE: "API 부상 자료 수신",
    STATE_EMPTY_RESPONSE: "API 응답은 성공했지만 부상 항목이 비어 있음(부상자 0명의 증거가 아님)",
    STATE_API_NOT_PROVIDED: "API가 이 경기의 부상 자료를 제공하지 않음",
    STATE_CALL_ERROR: "부상 자료 API 호출이 실패함",
    STATE_NOT_RUN: "부상 자료 수집이 실행되지 않음",
}

# 모델 출력 status. API 표기를 승격하지 않기 위해 네 값만 인정한다.
STATUS_DOUBTFUL = "doubtful"
STATUS_CONFIRMED_ABSENCE = "confirmed_absence"
STATUS_AVAILABLE = "available"
STATUS_UNKNOWN = "unknown"
STATUSES = (STATUS_DOUBTFUL, STATUS_CONFIRMED_ABSENCE, STATUS_AVAILABLE, STATUS_UNKNOWN)

STATUS_LABELS = {
    STATUS_DOUBTFUL: "출전 불확실",
    STATUS_CONFIRMED_ABSENCE: "결장(확정 표기)",
    STATUS_AVAILABLE: "출전 가능 표기",
    STATUS_UNKNOWN: "표기 없음(확정 사실 아님)",
}

_UNCERTAINTY_TO_STATUS = {
    "uncertain": STATUS_DOUBTFUL,
    "confirmed": STATUS_CONFIRMED_ABSENCE,
    "unknown": STATUS_UNKNOWN,
}

_COVERAGE_TOPIC_API = "부상·출전 불확실 API"
_COVERAGE_TOPIC_SEARCH = "부상 맥락 검색"
_COVERAGE_TOPIC_IMPACT = "결장 영향 해석"

# D0가 남기는 부상 claim 문장 모양(`app/preview/data.py`)을 되읽기 위한 패턴.
_CLAIM_STATUS = re.compile(r"상태:\s*(?P<marker>[^,\n]+)")
_CLAIM_REASON = re.compile(r"사유\s*(?P<reason>.+)$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 근거 자료
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class InjuryFact:
    """이 경기의 부상·출전 불확실 사실 한 건. 원문 표기를 그대로 보존한다."""

    evidence_id: str
    player_id: int
    player_name: str | None
    team_id: int | None
    type_marker: str | None
    reason: str | None
    uncertainty: str
    reported_at: datetime | None = None
    collected_at: datetime | None = None
    snapshot_id: uuid.UUID | None = None
    source: str = "api"
    adopted: bool = True

    @property
    def expected_status(self) -> str:
        """API 표기가 뜻하는 상태. 모델이 이와 다르게 쓰면 상충으로 남긴다."""
        return _UNCERTAINTY_TO_STATUS.get(self.uncertainty, STATUS_UNKNOWN)

    @property
    def display_name(self) -> str:
        """이름을 만들지 않는다. 없으면 식별자만 쓴다."""
        if self.player_name:
            return self.player_name
        return f"선수 ID {self.player_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "team_id": self.team_id,
            "type_marker": self.type_marker,
            "reason": self.reason,
            "uncertainty": self.uncertainty,
            "expected_status": self.expected_status,
            "reported_at": self.reported_at.isoformat() if self.reported_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
            "source": self.source,
            "adopted": self.adopted,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InjuryFact":
        return cls(
            evidence_id=str(data["evidence_id"]),
            player_id=int(data["player_id"]),
            player_name=data.get("player_name"),
            team_id=int(data["team_id"]) if data.get("team_id") is not None else None,
            type_marker=data.get("type_marker"),
            reason=data.get("reason"),
            uncertainty=str(data.get("uncertainty") or "unknown"),
            reported_at=_dt(data.get("reported_at")),
            collected_at=_dt(data.get("collected_at")),
            snapshot_id=uuid.UUID(str(data["snapshot_id"])) if data.get("snapshot_id") else None,
            source=str(data.get("source") or "api"),
            adopted=bool(data.get("adopted", True)),
        )


def _dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


@dataclass(frozen=True)
class AvailabilityFacts:
    """D0가 넘긴 부상 자료 묶음의 해석 결과. 상태와 사실을 함께 둔다."""

    state: str
    detail: str | None
    facts: tuple[InjuryFact, ...]
    team_names: Mapping[int, str] = field(default_factory=dict)
    fixture_label: str | None = None

    @property
    def has_api_facts(self) -> bool:
        return self.state == STATE_AVAILABLE and bool(self.facts)

    def team_label(self, team_id: int | None) -> str | None:
        if team_id is None:
            return None
        return self.team_names.get(team_id)


def _uncertainty_of(marker: str | None) -> str:
    """표기 하나의 확실성. D0와 같은 판정 함수를 쓴다(문구가 어긋나지 않게)."""
    return api.injury_uncertainty(marker)


def _is_injury_topic(topic: Any) -> bool:
    """부상 자료 항목인지. D0는 한글 라벨을 쓰고, 호출 topic은 영문 `injuries`다."""
    lowered = str(topic or "").lower()
    return "부상" in lowered or "injur" in lowered


def _material_state_from_coverage(
    coverage: Sequence[Mapping[str, Any]],
) -> tuple[str, str | None] | None:
    """D0 coverage에서 부상 항목을 찾아 상태를 읽는다.

    항목 이름·라벨 표기에 의존하지 않는다(`부상`/`injur` 둘 다 받는다). 같은 주제가
    여러 번 있으면 `not_run`보다 실제 수집 결과를 먼저 쓴다.
    """
    fallback: tuple[str, str | None] | None = None
    for entry in coverage:
        if not _is_injury_topic(entry.get("topic")):
            continue
        state = str(entry.get("state") or "")
        detail = entry.get("detail")
        if state == CoverageState.AVAILABLE.value:
            return STATE_AVAILABLE, detail
        if state == CoverageState.UNKNOWN.value:
            # 빈 응답은 '없음'이 아니라 자료 없음이다.
            matched = STATE_EMPTY_RESPONSE
        elif state == CoverageState.API_NOT_PROVIDED.value:
            matched = STATE_API_NOT_PROVIDED
        elif state == CoverageState.CALL_ERROR.value:
            matched = STATE_CALL_ERROR
        elif state == CoverageState.SOURCE_CONFLICT.value:
            matched = STATE_AVAILABLE
        else:
            matched = STATE_NOT_RUN
        if fallback is None or (fallback[0] == STATE_NOT_RUN and matched != STATE_NOT_RUN):
            fallback = (matched, detail)
    return fallback


def _team_names(material: Mapping[str, Any]) -> dict[int, str]:
    """D0가 팀 이름을 줬을 때만 이름을 쓴다. 여기서 이름을 만들지 않는다."""
    names: dict[int, str] = {}
    teams = material.get("teams")
    if isinstance(teams, Mapping):
        for key, value in teams.items():
            if isinstance(value, Mapping):
                team_id = value.get("id") or value.get("team_id")
                name = value.get("name")
                if team_id is not None and name:
                    names[int(team_id)] = str(name)
            elif isinstance(key, (int, str)) and isinstance(value, str) and value:
                try:
                    names[int(key)] = value
                except (TypeError, ValueError):
                    continue
    fixtures = material.get("fixture")
    if not isinstance(fixtures, Mapping):
        return names
    # 공통 D0는 `fixture.home`/`fixture.away` 중첩과 `home_team`+`home_team_id` 평면
    # 두 모양을 쓸 수 있다. 둘 다 읽고, 없으면 이름을 만들지 않는다.
    for side in ("home", "away"):
        entry = fixtures.get(side)
        if isinstance(entry, Mapping) and entry.get("id") is not None and entry.get("name"):
            names[int(entry["id"])] = str(entry["name"])
    for name_key, id_key in (
        ("home_team_name", "home_team_id"),
        ("away_team_name", "away_team_id"),
        ("home_team", "home_team_id"),
        ("away_team", "away_team_id"),
    ):
        name = fixtures.get(name_key)
        team_id = fixtures.get(id_key)
        if not name or team_id is None:
            continue
        try:
            names[int(team_id)] = str(name)
        except (TypeError, ValueError):
            continue
    return names


def _material_timestamps(material: Mapping[str, Any]) -> tuple[dict[str, datetime], datetime | None]:
    """D0 자료 묶음의 `topics`에서 스냅샷별 수집 시각을 읽는다.

    D0가 남긴 수집 시각을 API 사실에 붙이기 위한 것이다. 값이 없으면 `None`이고,
    시각을 지어내지 않는다.
    """
    by_snapshot: dict[str, datetime] = {}
    injuries_collected: datetime | None = None
    topics = material.get("topics")
    if not isinstance(topics, Mapping):
        return by_snapshot, injuries_collected
    for topic, entry in topics.items():
        if not isinstance(entry, Mapping):
            continue
        collected = _dt(entry.get("collected_at"))
        snapshot_id = entry.get("snapshot_id")
        if collected is not None and snapshot_id:
            by_snapshot[str(snapshot_id)] = collected
        if collected is not None and _is_injury_topic(topic):
            injuries_collected = collected
    return by_snapshot, injuries_collected


def injury_facts_from_material(
    material: Mapping[str, Any] | None,
    *,
    fixture: FixtureIdentity | None = None,
    stored_loader: Callable[[int], Sequence[Any]] | None = None,
) -> AvailabilityFacts:
    """D0 자료에서 이 경기의 부상 사실과 상태를 읽는다.

    읽는 모양은 세 가지이며, 있는 것을 우선순위대로 쓴다.

    1. `injuries`: 구조화된 부상 레코드 목록(가장 정확한 입력)
    2. `claims`: D0가 남긴 `d0-injury-<player_id>` claim(문장에서 표기·사유를 되읽음)
    3. `stored_loader`: 주입된 읽기 전용 DB 조회기(저장된 부상 행). 이름은 붙이지 않는다.

    빈 배열·미제공·호출 실패를 "부상자 없음"으로 바꾸지 않는다.
    """
    material = material or {}
    state_detail = _material_state_from_coverage(material.get("coverage") or ())
    state, detail = state_detail if state_detail else (STATE_NOT_RUN, None)
    team_names = _team_names(material)
    reasons: list[str] = []

    records: list[Mapping[str, Any]] = []
    raw_records = material.get("injuries")
    if isinstance(raw_records, Sequence) and not isinstance(raw_records, (str, bytes)):
        records = [dict(item) for item in raw_records if isinstance(item, Mapping)]
        if state == STATE_NOT_RUN:
            state = STATE_AVAILABLE if records else STATE_EMPTY_RESPONSE

    facts: list[InjuryFact] = []
    if records:
        for record in records:
            fact = _fact_from_record(record)
            if fact is not None:
                facts.append(fact)
    else:
        # 공통 D0는 `claims`(D0 claim) 또는 `facts`(fact_id/text) 목록으로 넘긴다.
        for source_key in ("claims", "facts"):
            for claim in material.get(source_key) or ():
                if not isinstance(claim, Mapping):
                    continue
                fact = _fact_from_claim(claim)
                if fact is not None:
                    facts.append(fact)
        if state == STATE_NOT_RUN and facts:
            state = STATE_AVAILABLE

    if not facts and stored_loader is not None and fixture is not None:
        try:
            stored = list(stored_loader(fixture.fixture_id))
        except Exception as exc:  # pragma: no cover - 읽기 권한·연결 실패
            reasons.append(f"저장된 부상 자료를 읽지 못했습니다: {type(exc).__name__}")
            stored = []
        stored_snapshot = _material_snapshot(material, facts_state=state)
        for row in stored:
            fact = _fact_from_stored(row)
            if fact is None:
                continue
            facts.append(
                _with_stored_origin(fact, stored_snapshot)
                if stored_snapshot is not None
                else _drop_stored_timestamps(fact)
            )
        if facts:
            state = STATE_AVAILABLE
            detail = detail or "저장된 DB 부상 행(읽기 전용)에서 읽었습니다."
        elif state in (STATE_NOT_RUN, STATE_EMPTY_RESPONSE):
            # 저장된 행도 없고 API 응답도 비었다. '부상자 없음'이 아니다.
            state = STATE_EMPTY_RESPONSE
            detail = detail or "저장된 DB 부상 행이 없습니다. 이는 '부상자 없음'의 증거가 아닙니다."

    if facts:
        # D0가 남긴 수집 시각을 붙인다. 없으면 None으로 두고 지어내지 않는다.
        by_snapshot, injuries_collected = _material_timestamps(material)
        stamped: list[InjuryFact] = []
        for fact in facts:
            if fact.snapshot_id is not None:
                # 스냅샷을 특정할 수 있으면 그 시각을, 없으면 부상 주제의 수집 시각을
                # 쓴다. API 사실은 이번 실행이 수집한 부상 자료이기 때문이다.
                stamped.append(
                    _with_collected_at(
                        fact,
                        by_snapshot.get(str(fact.snapshot_id)) or injuries_collected,
                    )
                )
                continue
            if fact.source == "stored_db":
                # 저장 행의 시각은 부상 보도 시각이다. 어느 스냅샷 자료인지 확정할 수
                # 없으면 D0 수집 시각으로 바꾸지 않는다.
                stamped.append(_drop_stored_timestamps(fact))
                continue
            stamped.append(_with_collected_at(fact, injuries_collected))
        facts = stamped

    if state == STATE_AVAILABLE and not facts:
        detail = detail or "API가 부상 항목 0건을 반환했습니다. 이는 '부상자 없음'의 증거가 아닙니다."
    if reasons:
        detail = " ".join([detail] + reasons) if detail else " ".join(reasons)

    return AvailabilityFacts(
        state=state,
        detail=detail,
        facts=tuple(facts),
        team_names=dict(team_names),
        fixture_label=material.get("fixture_label"),
    )


def _with_team_names(
    facts: AvailabilityFacts, team_names: Mapping[int, str]
) -> AvailabilityFacts:
    """확인된 팀 이름을 덧붙인다. 여기서 이름을 만들지 않고, 있는 값만 합친다."""
    from dataclasses import replace

    merged = {**dict(facts.team_names)}
    for key, value in team_names.items():
        try:
            merged[int(key)] = str(value)
        except (TypeError, ValueError):
            continue
    return replace(facts, team_names=merged)


def _material_snapshot(
    material: Mapping[str, Any], *, facts_state: str
) -> tuple[uuid.UUID, datetime | None] | None:
    """저장 자료를 읽은 D0 스냅샷 하나를 고른다.

    D0가 `snapshot_ids`를 하나만 주면 그 스냅샷이 이번 읽기의 근거다. 여럿이면
    어느 것이 부상 행인지 확정할 수 없으므로 붙이지 않는다(추측 금지).
    """
    if facts_state not in (STATE_AVAILABLE, STATE_EMPTY_RESPONSE):
        return None
    ids = material.get("snapshot_ids")
    if not isinstance(ids, Sequence) or isinstance(ids, (str, bytes)) or len(ids) != 1:
        return None
    try:
        snapshot_id = uuid.UUID(str(ids[0]))
    except (TypeError, ValueError):
        return None
    by_snapshot, injuries_collected = _material_timestamps(material)
    return snapshot_id, by_snapshot.get(str(snapshot_id), injuries_collected)


def _with_stored_origin(
    fact: InjuryFact, origin: tuple[uuid.UUID, datetime | None] | None
) -> InjuryFact:
    """저장 자료에서 읽은 사실에 D0 스냅샷·수집 시각을 붙인다(없으면 그대로 둔다)."""
    if origin is None:
        return fact
    from dataclasses import replace

    snapshot_id, collected_at = origin
    return replace(
        fact,
        snapshot_id=fact.snapshot_id or snapshot_id,
        collected_at=fact.collected_at or collected_at,
    )


def _drop_stored_timestamps(fact: InjuryFact) -> InjuryFact:
    """스냅샷을 특정할 수 없을 때 저장 행의 시각을 승격하지 않는다.

    저장 행의 `reported_at`은 부상 보도 시각이고 D0 수집 시각이 아니다. 어느 스냅샷의
    자료인지 확정할 수 없으면 둘을 섞지 않는다.
    """
    from dataclasses import replace

    return replace(fact, snapshot_id=None, collected_at=None)


def _with_collected_at(fact: InjuryFact, collected_at: datetime | None) -> InjuryFact:
    if collected_at is None or fact.collected_at is not None:
        return fact
    from dataclasses import replace

    return replace(fact, collected_at=collected_at)


def _team_id(record: Mapping[str, Any]) -> int | None:
    candidate = record.get("team_id")
    if candidate is None and isinstance(record.get("team"), Mapping):
        candidate = record["team"].get("id")
    if candidate is None:
        return None
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return None


def _fact_from_record(record: Mapping[str, Any]) -> InjuryFact | None:
    player_id = record.get("player_id", record.get("id"))
    if player_id is None:
        return None
    try:
        player_id = int(player_id)
    except (TypeError, ValueError):
        return None
    marker = record.get("type_marker", record.get("type"))
    uncertainty = str(record.get("uncertainty") or _uncertainty_of(marker))
    return InjuryFact(
        evidence_id=f"api:injury-{player_id}",
        player_id=player_id,
        player_name=record.get("player_name") or record.get("name"),
        team_id=_team_id(record),
        type_marker=str(marker) if marker else None,
        reason=record.get("reason"),
        uncertainty=uncertainty,
        reported_at=_dt(record.get("reported_at")),
        collected_at=_dt(record.get("collected_at")),
        snapshot_id=(
            uuid.UUID(str(record["snapshot_id"])) if record.get("snapshot_id") else None
        ),
        source=str(record.get("source") or "api"),
        adopted=bool(record.get("adopted", uncertainty != "unknown")),
    )


def _fact_from_claim(claim: Mapping[str, Any]) -> InjuryFact | None:
    claim_id = str(claim.get("claim_id") or claim.get("fact_id") or "")
    if not claim_id.startswith("d0-injury-"):
        return None
    try:
        player_id = int(claim_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        # `d0-injury-count` 같은 집계 항목은 선수 사실이 아니다. 이름을 만들지 않는다.
        return None
    text = str(claim.get("text") or "")
    status_match = _CLAIM_STATUS.search(text)
    marker = status_match.group("marker").strip() if status_match else None
    if marker in ("표기 없음", ""):
        marker = None
    reason_match = _CLAIM_REASON.search(text)
    reason = reason_match.group("reason").strip() if reason_match else None
    snapshot_ids = claim.get("snapshot_ids") or ()
    if not snapshot_ids and claim.get("snapshot_id"):
        snapshot_ids = (claim["snapshot_id"],)
    decision = str(claim.get("decision") or ClaimDecision.ADOPTED.value)
    uncertainty = _uncertainty_of(marker)
    return InjuryFact(
        evidence_id=f"api:injury-{player_id}",
        player_id=player_id,
        player_name=None,
        team_id=claim.get("subject_team_id"),
        type_marker=marker,
        reason=reason,
        uncertainty=uncertainty,
        snapshot_id=uuid.UUID(str(snapshot_ids[0])) if snapshot_ids else None,
        collected_at=_dt(claim.get("collected_at")),
        source="api",
        # D0가 제외한 근거(표기 없음)를 여기서 승격하지 않는다.
        adopted=decision == ClaimDecision.ADOPTED.value,
    )


def _fact_from_stored(row: Any) -> InjuryFact | None:
    player_id = getattr(row, "player_id", None)
    if player_id is None:
        return None
    marker = getattr(row, "type_marker", None)
    reason = getattr(row, "reason", None)
    reported_at = getattr(row, "reported_at", None)
    return InjuryFact(
        evidence_id=f"stored:injury-{int(player_id)}",
        player_id=int(player_id),
        # 저장된 DB 조회기는 이름을 주지 않는다(읽기 경계 밖). 만들지 않는다.
        player_name=getattr(row, "player_name", None),
        team_id=(
            int(getattr(row, "team_id")) if getattr(row, "team_id", None) is not None else None
        ),
        type_marker=marker,
        reason=reason,
        uncertainty=_uncertainty_of(marker),
        reported_at=reported_at if isinstance(reported_at, datetime) else None,
        source="stored_db",
        adopted=_uncertainty_of(marker) != "unknown",
    )


# --------------------------------------------------------------------------
# grounding (검색 출처·Search Suggestions)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundingSource:
    """검색 결과가 실제로 인용한 출처 하나."""

    uri: str
    title: str | None = None
    domain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"uri": self.uri, "title": self.title, "domain": self.domain}


@dataclass(frozen=True)
class GroundingInfo:
    """한 응답의 grounding 메타데이터. 없으면 `available=False`다."""

    sources: tuple[GroundingSource, ...] = ()
    queries: tuple[str, ...] = ()
    supports: tuple[Mapping[str, Any], ...] = ()
    search_entry_point: Mapping[str, Any] | None = None

    @property
    def available(self) -> bool:
        return bool(self.sources)

    def uris(self) -> frozenset[str]:
        return frozenset(source.uri for source in self.sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "sources": [source.to_dict() for source in self.sources],
            "queries": list(self.queries),
            "supports": [dict(item) for item in self.supports],
            # Search Suggestions는 제공된 그대로 보존한다(수정·재작성 금지).
            "search_entry_point": dict(self.search_entry_point)
            if self.search_entry_point
            else None,
        }


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _entry_point(value: Any) -> dict[str, Any] | None:
    """Search Suggestions를 제공된 값 그대로 보존한다. 키 이름만 snake_case로 맞춘다."""
    if not isinstance(value, Mapping):
        return None
    normalized = {
        "rendered_content": _first(value, "rendered_content", "renderedContent"),
        "sdk_blob": _first(value, "sdk_blob", "sdkBlob"),
    }
    extra = {
        str(key): item
        for key, item in value.items()
        if str(key) not in ("rendered_content", "renderedContent", "sdk_blob", "sdkBlob")
    }
    return {**normalized, **extra}


def _candidate_payloads(raw_response: Any) -> list[Mapping[str, Any]]:
    if not isinstance(raw_response, Mapping):
        return []
    candidates = raw_response.get("candidates")
    if not isinstance(candidates, Sequence):
        return []
    return [item for item in candidates if isinstance(item, Mapping)]


def extract_grounding(raw_response: Any) -> GroundingInfo:
    """원문 응답에서 grounding 출처·검색어·Search Suggestions를 보존한다.

    SDK 직렬화는 snake_case지만, 다른 경로가 camelCase를 넣어도 읽도록 둘 다 받는다.
    """
    for candidate in _candidate_payloads(raw_response):
        metadata = _first(candidate, "grounding_metadata", "groundingMetadata")
        if not isinstance(metadata, Mapping):
            continue
        sources: list[GroundingSource] = []
        chunks = _first(metadata, "grounding_chunks", "groundingChunks") or ()
        for chunk in chunks:
            if not isinstance(chunk, Mapping):
                continue
            web = _first(chunk, "web")
            if not isinstance(web, Mapping):
                continue
            uri = _first(web, "uri", "url")
            if not uri:
                continue
            sources.append(
                GroundingSource(
                    uri=str(uri),
                    title=_first(web, "title"),
                    domain=_first(web, "domain"),
                )
            )
        queries = _first(metadata, "web_search_queries", "webSearchQueries") or ()
        supports = _first(metadata, "grounding_supports", "groundingSupports") or ()
        entry_point = _first(metadata, "search_entry_point", "searchEntryPoint")
        return GroundingInfo(
            sources=tuple(sources),
            queries=tuple(str(query) for query in queries),
            supports=tuple(dict(item) for item in supports if isinstance(item, Mapping)),
            search_entry_point=_entry_point(entry_point),
        )
    return GroundingInfo()


# --------------------------------------------------------------------------
# 프롬프트
# --------------------------------------------------------------------------


def load_prompt_template(path: Path | None = None) -> str:
    return (path or PROMPT_PATH).read_text(encoding="utf-8")


def _api_fact_lines(facts: Sequence[InjuryFact]) -> str:
    if not facts:
        return "API 부상 사실이 없습니다."
    lines: list[str] = []
    for fact in facts:
        parts = [
            f"- id `{fact.evidence_id}`",
            f"선수 id {fact.player_id}",
        ]
        if fact.player_name:
            parts.append(f"이름 {fact.player_name}")
        parts.append(f"팀 id {fact.team_id if fact.team_id is not None else '미상'}")
        parts.append(f"원문 표기 `{fact.type_marker or '표기 없음'}`")
        if fact.reason:
            parts.append(f"사유 `{fact.reason}`")
        parts.append(f"분류 `{fact.uncertainty}`")
        if fact.reported_at:
            parts.append(f"보고 시각 {fact.reported_at.isoformat()}")
        if fact.collected_at:
            parts.append(f"수집 시각 {fact.collected_at.isoformat()}")
        if not fact.adopted:
            parts.append("D0 판정: 표기가 없어 확정 사실로 채택되지 않음")
        lines.append(" · ".join(parts))
    return "\n".join(lines)


def build_prompt(
    *,
    template: str,
    fixture: FixtureIdentity | None,
    facts: AvailabilityFacts,
    today: datetime,
) -> str:
    """프롬프트 본문을 채운다. 값이 없으면 '미확인'으로 표시하고 만들지 않는다."""
    identity = fixture
    team_names = facts.team_names
    home_name = (team_names.get(identity.home_team_id) if identity else None) or "홈팀"
    away_name = (team_names.get(identity.away_team_id) if identity else None) or "원정팀"
    evidence_ids = "\n".join(
        f"- `{fact.evidence_id}` (선수 id {fact.player_id})" for fact in facts.facts
    ) or "- 인용 가능한 API 사실 id가 없습니다. 검색 URL만 쓸 수 있습니다."
    values = {
        "fixture_label": facts.fixture_label
        or (
            f"{home_name} vs {away_name}" if fixture else "경기 미확인"
        ),
        "fixture_id": str(identity.fixture_id) if identity else "미확인",
        "league_id": str(identity.league_id) if identity else "미확인",
        "season": str(identity.season) if identity else "미확인",
        "kickoff_at": identity.kickoff_at.isoformat() if identity else "미확인",
        "home_team": home_name,
        "home_team_id": str(identity.home_team_id) if identity else "미확인",
        "away_team": away_name,
        "away_team_id": str(identity.away_team_id) if identity else "미확인",
        "today": today.date().isoformat(),
        "injury_state": facts.state,
        "injury_state_detail": facts.detail or STATE_LABELS.get(facts.state, facts.state),
        "api_facts": _api_fact_lines(facts.facts),
        "evidence_ids": evidence_ids,
    }
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


# --------------------------------------------------------------------------
# 모델 출력 해석·검증
# --------------------------------------------------------------------------


def parse_model_output(text: str | None) -> Mapping[str, Any] | None:
    """모델 텍스트에서 JSON 객체 하나를 읽는다. 없으면 `None`(빈 dict로 꾸미지 않음)."""
    if not text:
        return None
    stripped = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fenced:
        stripped = fenced.group(1).strip()
    try:
        parsed = json.loads(stripped)
    except ValueError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(stripped[start : end + 1])
        except ValueError:
            return None
    return parsed if isinstance(parsed, Mapping) else None


@dataclass(frozen=True)
class PlayerUpdate:
    player_id: int | None
    player_name: str | None
    team_id: int | None
    status: str
    summary: str
    evidence: tuple[str, ...]
    conflict: bool = False
    api_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "team_id": self.team_id,
            "status": self.status,
            "summary": self.summary,
            "evidence": list(self.evidence),
            "conflict": self.conflict,
            "api_status": self.api_status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlayerUpdate":
        return cls(
            player_id=int(data["player_id"]) if data.get("player_id") is not None else None,
            player_name=data.get("player_name"),
            team_id=int(data["team_id"]) if data.get("team_id") is not None else None,
            status=str(data.get("status") or STATUS_UNKNOWN),
            summary=str(data.get("summary") or ""),
            evidence=tuple(str(item) for item in data.get("evidence") or ()),
            conflict=bool(data.get("conflict", False)),
            api_status=data.get("api_status"),
        )


@dataclass(frozen=True)
class ReportedAbsence:
    player_name: str
    team_id: int | None
    summary: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_name": self.player_name,
            "team_id": self.team_id,
            "summary": self.summary,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReportedAbsence":
        return cls(
            player_name=str(data.get("player_name") or ""),
            team_id=int(data["team_id"]) if data.get("team_id") is not None else None,
            summary=str(data.get("summary") or ""),
            evidence=tuple(str(item) for item in data.get("evidence") or ()),
        )


@dataclass(frozen=True)
class ImpactNote:
    """근거가 연결된 영향 해석. 근거 없는 해석은 채택하지 않는다."""

    team_id: int | None
    summary: str
    basis: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"team_id": self.team_id, "summary": self.summary, "basis": list(self.basis)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImpactNote":
        return cls(
            team_id=int(data["team_id"]) if data.get("team_id") is not None else None,
            summary=str(data.get("summary") or ""),
            basis=tuple(str(item) for item in data.get("basis") or ()),
        )


@dataclass(frozen=True)
class ValidatedAvailability:
    """검증을 통과한 조사 결과. 본문은 이 값에서만 만든다."""

    material_state: str
    material_detail: str | None
    facts: tuple[InjuryFact, ...]
    player_updates: tuple[PlayerUpdate, ...]
    reported_absences: tuple[ReportedAbsence, ...]
    impacts: tuple[ImpactNote, ...]
    uncertainties: tuple[str, ...]
    search_note: str | None
    rejected: tuple[str, ...]
    grounding: GroundingInfo
    search_snapshot_id: uuid.UUID | None = None
    team_names: Mapping[int, str] = field(default_factory=dict)
    fixture_label: str | None = None

    @property
    def has_reader_facts(self) -> bool:
        return bool(self.player_updates or self.reported_absences)

    @property
    def adopted_fact_count(self) -> int:
        return len(self.player_updates) + len(self.reported_absences)

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_state": self.material_state,
            "material_detail": self.material_detail,
            "facts": [fact.to_dict() for fact in self.facts],
            "player_updates": [update.to_dict() for update in self.player_updates],
            "reported_absences": [absence.to_dict() for absence in self.reported_absences],
            "impacts": [impact.to_dict() for impact in self.impacts],
            "uncertainties": list(self.uncertainties),
            "search_note": self.search_note,
            "rejected": list(self.rejected),
            "grounding": self.grounding.to_dict(),
            "search_snapshot_id": str(self.search_snapshot_id) if self.search_snapshot_id else None,
            "team_names": {str(key): value for key, value in self.team_names.items()},
            "fixture_label": self.fixture_label,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidatedAvailability":
        return cls(
            material_state=str(data.get("material_state") or STATE_NOT_RUN),
            material_detail=data.get("material_detail"),
            facts=tuple(InjuryFact.from_dict(item) for item in data.get("facts") or ()),
            player_updates=tuple(
                PlayerUpdate.from_dict(item) for item in data.get("player_updates") or ()
            ),
            reported_absences=tuple(
                ReportedAbsence.from_dict(item) for item in data.get("reported_absences") or ()
            ),
            impacts=tuple(ImpactNote.from_dict(item) for item in data.get("impacts") or ()),
            uncertainties=tuple(str(item) for item in data.get("uncertainties") or ()),
            search_note=data.get("search_note"),
            rejected=tuple(str(item) for item in data.get("rejected") or ()),
            grounding=_grounding_from_dict(data.get("grounding")),
            search_snapshot_id=(
                uuid.UUID(str(data["search_snapshot_id"]))
                if data.get("search_snapshot_id")
                else None
            ),
            team_names={
                int(key): str(value)
                for key, value in (data.get("team_names") or {}).items()
                if str(key).lstrip("-").isdigit()
            },
            fixture_label=data.get("fixture_label"),
        )


def _grounding_from_dict(data: Any) -> GroundingInfo:
    if not isinstance(data, Mapping):
        return GroundingInfo()
    return GroundingInfo(
        sources=tuple(
            GroundingSource(
                uri=str(item["uri"]),
                title=item.get("title"),
                domain=item.get("domain"),
            )
            for item in data.get("sources") or ()
            if isinstance(item, Mapping) and item.get("uri")
        ),
        queries=tuple(str(item) for item in data.get("queries") or ()),
        supports=tuple(
            dict(item) for item in data.get("supports") or () if isinstance(item, Mapping)
        ),
        search_entry_point=(
            dict(data["search_entry_point"])
            if isinstance(data.get("search_entry_point"), Mapping)
            else None
        ),
    )


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


# 자료 확보 사정을 말하는 문장. 독자용 본문이 아니라 관리자 진단에 남긴다.
_MATERIAL_GAP_MARKERS = (
    "검색 자료",
    "검색 결과",
    "검색으로 확인하지",
    "검색하지 못",
    "미확보",
    "자료를 얻지 못",
    "자료가 없",
    "API 자료가 없",
    "grounding",
    "호출 실패",
    "재시도",
)


def _is_material_gap_note(note: str) -> bool:
    return any(marker in note for marker in _MATERIAL_GAP_MARKERS)


def validate_model_output(
    parsed: Mapping[str, Any] | None,
    *,
    facts: AvailabilityFacts,
    grounding: GroundingInfo,
) -> ValidatedAvailability:
    """모델 출력을 검증한다. 근거가 없는 항목은 채택하지 않고 기록에 남긴다.

    - URL 근거는 **이번 호출의 grounding 결과에 실제로 있는 주소**만 인정한다.
    - API 사실 id는 제공한 목록에 있는 것만 인정한다.
    - API 표기(불확실)를 결장 확정으로 바꾼 항목은 상충으로 표시해 둘 다 보존한다.
    """
    rejected: list[str] = []
    if parsed is None:
        rejected.append("모델 응답에서 JSON 객체를 찾지 못했습니다. 결과를 채택하지 않습니다.")
        return ValidatedAvailability(
            material_state=facts.state,
            material_detail=facts.detail,
            facts=facts.facts,
            player_updates=(),
            reported_absences=(),
            impacts=(),
            uncertainties=(),
            search_note=None,
            rejected=tuple(rejected),
            grounding=grounding,
            team_names=dict(facts.team_names),
            fixture_label=facts.fixture_label,
        )

    fact_by_id = {fact.evidence_id: fact for fact in facts.facts}
    allowed_urls = {uri.rstrip("/") for uri in grounding.uris()}

    def split_evidence(entries: Any, label: str) -> tuple[str, ...]:
        accepted: list[str] = []
        raw = entries if isinstance(entries, Sequence) and not isinstance(entries, (str, bytes)) else ()
        for entry in raw:
            token = str(entry).strip()
            if not token:
                continue
            if token in fact_by_id:
                accepted.append(token)
                continue
            if token.lower().startswith(("http://", "https://")):
                if token.rstrip("/") in allowed_urls:
                    accepted.append(token)
                else:
                    rejected.append(f"{label}: 이번 검색 결과에 없는 URL `{token}`을 근거로 썼습니다.")
                continue
            rejected.append(f"{label}: 알 수 없는 근거 id `{token}`입니다.")
        return tuple(dict.fromkeys(accepted))

    updates: list[PlayerUpdate] = []
    for index, raw in enumerate(parsed.get("player_updates") or ()):
        if not isinstance(raw, Mapping):
            continue
        label = f"player_updates[{index}]"
        evidence = split_evidence(raw.get("evidence"), label)
        summary = _clean_text(raw.get("summary"))
        if not summary:
            rejected.append(f"{label}: 설명이 비어 있어 채택하지 않았습니다.")
            continue
        status = _clean_text(raw.get("status")).lower()
        if status not in STATUSES:
            rejected.append(f"{label}: 알 수 없는 상태 `{raw.get('status')}`를 `unknown`으로 낮췄습니다.")
            status = STATUS_UNKNOWN
        player_id: int | None
        try:
            player_id = int(raw["player_id"]) if raw.get("player_id") is not None else None
        except (TypeError, ValueError):
            player_id = None
        api_fact = fact_by_id.get(f"api:injury-{player_id}") if player_id is not None else None
        if player_id is not None and api_fact is None:
            rejected.append(f"{label}: 제공되지 않은 선수 id {player_id}를 이름 근거 없이 채택하지 않았습니다.")
            player_id = None
        if not evidence:
            rejected.append(f"{label}: 근거가 없어 채택하지 않았습니다.")
            continue
        expected = api_fact.expected_status if api_fact else None
        conflict = bool(
            api_fact
            and expected in (STATUS_DOUBTFUL, STATUS_CONFIRMED_ABSENCE, STATUS_UNKNOWN)
            and status != expected
        )
        if conflict:
            rejected.append(
                f"{label}: API 표기({expected})와 다른 상태({status})를 상충으로 보존했습니다."
            )
        team_id = api_fact.team_id if api_fact else None
        if team_id is None and raw.get("team_id") is not None:
            try:
                team_id = int(raw["team_id"])
            except (TypeError, ValueError):
                team_id = None
        updates.append(
            PlayerUpdate(
                player_id=player_id,
                player_name=(str(raw.get("player_name")).strip() if raw.get("player_name") else None),
                team_id=team_id,
                status=status,
                summary=summary,
                evidence=evidence,
                conflict=conflict,
                api_status=expected,
            )
        )

    absences: list[ReportedAbsence] = []
    for index, raw in enumerate(parsed.get("reported_absences") or ()):
        if not isinstance(raw, Mapping):
            continue
        label = f"reported_absences[{index}]"
        evidence = split_evidence(raw.get("evidence"), label)
        summary = _clean_text(raw.get("summary"))
        name = _clean_text(raw.get("player_name"))
        if not name or not summary:
            rejected.append(f"{label}: 선수 이름이나 설명이 비어 채택하지 않았습니다.")
            continue
        if not evidence:
            rejected.append(f"{label}: 근거가 없어 채택하지 않았습니다.")
            continue
        team_id = None
        if raw.get("team_id") is not None:
            try:
                team_id = int(raw["team_id"])
            except (TypeError, ValueError):
                team_id = None
        absences.append(
            ReportedAbsence(player_name=name, team_id=team_id, summary=summary, evidence=evidence)
        )

    impacts: list[ImpactNote] = []
    seen_teams: dict[int | None, int] = {}
    for index, raw in enumerate(parsed.get("impact") or parsed.get("impacts") or ()):
        if not isinstance(raw, Mapping):
            continue
        label = f"impact[{index}]"
        summary = _clean_text(raw.get("summary"))
        basis = split_evidence(raw.get("basis"), label)
        if not summary:
            rejected.append(f"{label}: 설명이 비어 채택하지 않았습니다.")
            continue
        if not basis:
            # 근거 없는 영향 해석은 채택하지 않는다(사실과 해석의 경계).
            rejected.append(f"{label}: 근거가 연결되지 않은 영향 해석을 채택하지 않았습니다.")
            continue
        team_id = None
        if raw.get("team_id") is not None:
            try:
                team_id = int(raw["team_id"])
            except (TypeError, ValueError):
                team_id = None
        if seen_teams.get(team_id, 0) >= 2:
            continue
        seen_teams[team_id] = seen_teams.get(team_id, 0) + 1
        impacts.append(ImpactNote(team_id=team_id, summary=summary, basis=basis))

    uncertainties: list[str] = []
    for item in parsed.get("uncertainties") or ():
        note = _clean_text(item)
        if not note:
            continue
        if _is_material_gap_note(note):
            # 자료 수집 부족은 관리자 진단이다. 독자용 본문에 넣지 않는다.
            rejected.append(f"uncertainties: 자료 확보 사정 문장을 독자용에서 제외했습니다 — {note}")
            continue
        uncertainties.append(note)
    search_note = _clean_text(parsed.get("search_note")) or None

    return ValidatedAvailability(
        material_state=facts.state,
        material_detail=facts.detail,
        facts=facts.facts,
        player_updates=tuple(updates),
        reported_absences=tuple(absences),
        impacts=tuple(impacts),
        uncertainties=tuple(uncertainties),
        search_note=search_note,
        rejected=tuple(rejected),
        grounding=grounding,
        team_names=dict(facts.team_names),
        fixture_label=facts.fixture_label,
    )


# --------------------------------------------------------------------------
# 조사 실행
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AvailabilityOutcome:
    """R2 조사 노드의 산출. 저장은 호출자(공통 runner)가 한다."""

    mode: RunMode
    quality: QualityStatus
    payload: Mapping[str, Any]
    sources: tuple[Mapping[str, Any], ...]
    diagnostics: tuple[str, ...]
    unavailable_reason: str | None
    external_calls: int
    research: ValidatedAvailability | None = None
    text: str | None = None
    attempts: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "quality": self.quality.value,
            "payload": dict(self.payload),
            "sources": [dict(item) for item in self.sources],
            "diagnostics": list(self.diagnostics),
            "unavailable_reason": self.unavailable_reason,
            "external_calls": self.external_calls,
            "attempts": [dict(item) for item in self.attempts],
        }


def _coverage_entries(research: ValidatedAvailability) -> tuple[CoverageEntry, ...]:
    state_map = {
        STATE_AVAILABLE: CoverageState.AVAILABLE,
        STATE_EMPTY_RESPONSE: CoverageState.UNKNOWN,
        STATE_API_NOT_PROVIDED: CoverageState.API_NOT_PROVIDED,
        STATE_CALL_ERROR: CoverageState.CALL_ERROR,
        STATE_NOT_RUN: CoverageState.NOT_RUN,
    }
    api_detail = research.material_detail or STATE_LABELS.get(
        research.material_state, research.material_state
    )
    if research.facts:
        api_detail = f"{api_detail} (사실 {len(research.facts)}건)"
    search_state = (
        CoverageState.AVAILABLE if research.grounding.available else CoverageState.SEARCH_NOT_FOUND
    )
    search_detail = (
        f"출처 {len(research.grounding.sources)}건 · 검색어 {len(research.grounding.queries)}개"
        if research.grounding.available
        else "이번 호출에서 검색 출처(grounding)가 비어 있습니다. API 사실만으로 구성했습니다."
    )
    if any(update.conflict for update in research.player_updates):
        search_state = CoverageState.SOURCE_CONFLICT
        search_detail = (
            f"{search_detail} API 표기와 다른 보도를 상충으로 보존했습니다."
        )
    impact_state = (
        CoverageState.AVAILABLE if research.impacts else CoverageState.VALIDATION_REJECTED
    )
    impact_detail = (
        f"근거가 연결된 해석 {len(research.impacts)}건"
        if research.impacts
        else "근거가 연결된 영향 해석이 없어 채택하지 않았습니다."
    )
    return (
        CoverageEntry(topic=_COVERAGE_TOPIC_API, state=state_map[research.material_state], detail=api_detail),
        CoverageEntry(topic=_COVERAGE_TOPIC_SEARCH, state=search_state, detail=search_detail),
        CoverageEntry(topic=_COVERAGE_TOPIC_IMPACT, state=impact_state, detail=impact_detail),
    )


def _claims(research: ValidatedAvailability, *, search_snapshot_id: uuid.UUID | None) -> tuple[EvidenceClaim, ...]:
    claims: list[EvidenceClaim] = []
    for fact in research.facts:
        claims.append(
            EvidenceClaim(
                claim_id=f"r2-api-{fact.player_id}",
                kind=ClaimKind.FACT,
                text=(
                    f"API 부상 자료: {fact.display_name} 표기 "
                    f"{fact.type_marker or '표기 없음'}"
                    + (f", 사유 {fact.reason}" if fact.reason else "")
                ),
                snapshot_ids=((fact.snapshot_id,) if fact.snapshot_id else ()),
                decision=ClaimDecision.ADOPTED if fact.adopted else ClaimDecision.EXCLUDED,
                decision_reason=(
                    "출전 불확실 표기를 그대로 보존했습니다. 결장 확정이 아닙니다."
                    if fact.uncertainty == "uncertain"
                    else (
                        "표기가 없어 확정 사실로 채택하지 않았습니다."
                        if not fact.adopted
                        else "API 원문 표기를 그대로 옮겼습니다."
                    )
                ),
                subject_team_id=fact.team_id,
                subject_player_id=fact.player_id,
                claimed_at=fact.reported_at or fact.collected_at,
            )
        )
    for index, update in enumerate(research.player_updates):
        url = _first_url(update.evidence)
        claims.append(
            EvidenceClaim(
                claim_id=f"r2-update-{index}",
                kind=ClaimKind.FACT,
                text=update.summary,
                snapshot_ids=_snapshot_ids(update.evidence, research, search_snapshot_id),
                decision=ClaimDecision.CONFLICT if update.conflict else ClaimDecision.ADOPTED,
                decision_reason=(
                    "검색 보도가 API 표기와 달라 상충으로 보존했습니다. 어느 쪽도 확정으로 바꾸지 않았습니다."
                    if update.conflict
                    else None
                ),
                subject_team_id=update.team_id,
                subject_player_id=update.player_id,
                source_url=url,
            )
        )
    for index, absence in enumerate(research.reported_absences):
        claims.append(
            EvidenceClaim(
                claim_id=f"r2-absence-{index}",
                kind=ClaimKind.FACT,
                text=f"{absence.player_name}: {absence.summary}",
                snapshot_ids=(search_snapshot_id,) if search_snapshot_id else (),
                decision=ClaimDecision.ADOPTED,
                decision_reason="검색 보도 근거입니다. 원문을 직접 확인한 것은 아닙니다.",
                subject_team_id=absence.team_id,
                source_url=_first_url(absence.evidence),
            )
        )
    for index, impact in enumerate(research.impacts):
        claims.append(
            EvidenceClaim(
                claim_id=f"r2-impact-{index}",
                kind=ClaimKind.AI_INTERPRETATION,
                text=impact.summary,
                snapshot_ids=_snapshot_ids(impact.basis, research, search_snapshot_id),
                decision=ClaimDecision.ADOPTED,
                decision_reason="근거가 연결된 해석입니다: " + ", ".join(impact.basis),
                subject_team_id=impact.team_id,
                source_url=_first_url(impact.basis),
            )
        )
    return tuple(claims)


def _first_url(evidence: Sequence[str]) -> str | None:
    for token in evidence:
        if token.lower().startswith(("http://", "https://")):
            return token
    return None


def _snapshot_ids(
    evidence: Sequence[str],
    research: ValidatedAvailability,
    search_snapshot_id: uuid.UUID | None,
) -> tuple[uuid.UUID, ...]:
    fact_by_id = {fact.evidence_id: fact for fact in research.facts}
    ids: list[uuid.UUID] = []
    for token in evidence:
        fact = fact_by_id.get(token)
        if fact is not None and fact.snapshot_id is not None:
            ids.append(fact.snapshot_id)
        elif token.lower().startswith(("http://", "https://")) and search_snapshot_id:
            ids.append(search_snapshot_id)
    return tuple(dict.fromkeys(ids))


def _reader_sources(research: ValidatedAvailability) -> tuple[Mapping[str, Any], ...]:
    sources: list[Mapping[str, Any]] = []
    for fact in research.facts:
        collected = fact.collected_at.isoformat() if fact.collected_at else "시각 미상"
        sources.append(
            {
                "label": f"API-Football 부상 자료 · {fact.display_name}",
                "kind": "api",
                "url": None,
                "note": (
                    f"수집 {collected} · 원문 표기 {fact.type_marker or '표기 없음'}"
                    + (f" · 사유 {fact.reason}" if fact.reason else "")
                ),
            }
        )
    for source in research.grounding.sources:
        sources.append(
            {
                "label": source.title or source.domain or source.uri,
                "kind": "search",
                "url": source.uri,
                "note": "검색 결과가 인용한 출처입니다. 원문 전체를 직접 확인한 것은 아닙니다.",
            }
        )
    return tuple(sources)


def _diagnostics(research: ValidatedAvailability, *, mode: RunMode, stopped_reason: str | None) -> tuple[str, ...]:
    notes: list[str] = []
    if mode is not RunMode.LIVE:
        notes.append(
            f"{mode.value} 실행입니다. 실제 검색·모델 호출 결과가 아니며 승인 근거가 아닙니다."
        )
    if research.material_state != STATE_AVAILABLE:
        notes.append(
            f"부상 API 자료 상태: {research.material_state} — "
            f"{research.material_detail or STATE_LABELS[research.material_state]}"
        )
    if not research.grounding.available:
        notes.append(
            "이번 호출의 grounding 출처가 비어 있습니다. 검색 근거 없이 API 사실만 사용했습니다."
        )
    if research.rejected:
        notes.extend(research.rejected)
    if stopped_reason:
        notes.append(stopped_reason)
    return tuple(notes)


def research_availability(
    session: Session,
    *,
    module_input: ModuleInput,
    context: ExecutionContext,
    transport: Any,
    budget: Any,
    material: Mapping[str, Any] | None = None,
    stored_loader: Callable[[int], Sequence[Any]] | None = None,
    team_names: Mapping[int, str] | None = None,
    prompt_template: str | None = None,
    model_name: str | None = None,
    now: datetime | None = None,
) -> AvailabilityOutcome:
    """R2 조사 한 번. 정상 경로 모델 호출 1회(재시도는 공통 예산).

    Args:
        session: 원문 아티팩트·스냅샷을 읽고 남길 세션.
        module_input: 공통 입력 계약(경기 식별·스냅샷·버전).
        context: 공통 실행 문맥(실행 ID·예산·모드).
        transport: 모델 전송. mock/replay/live는 transport가 밝힌 값을 쓴다.
        budget: 공통 재시도·기한 예산.
        material: D0 자료 묶음(부상 사실·coverage·팀 이름). 없으면 자료 없음이다.
        stored_loader: 저장된 부상 행 읽기(읽기 전용 DB). 주입될 때만 읽는다.
        team_names: 저장된 경기 자료에서 확인한 팀 id→이름. 없으면 `팀 <id>`로 쓴다.
    """
    moment = now or _now()
    mode = getattr(transport, "mode", RunMode.MOCK)
    fixture = module_input.fixture
    facts = injury_facts_from_material(material, fixture=fixture, stored_loader=stored_loader)
    if team_names:
        facts = _with_team_names(facts, team_names)
    template = prompt_template or load_prompt_template()
    prompt_text = build_prompt(template=template, fixture=fixture, facts=facts, today=moment)

    result = provider.request_model(
        logical_call_id=LOGICAL_CALL_ID,
        contents=[{"role": "user", "parts": [{"text": prompt_text}]}],
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=AVAILABILITY_MODULE_ID,
        operation="research_availability",
        prompt_version=PROMPT_VERSION,
        # Google Search grounding을 켠다. JSON 형식 강제는 걸지 않고 응답을 관대하게
        # 파싱한다(검색 도구와 제어된 생성의 조합은 제공자 제약이 있다).
        generation_config={
            "temperature": 0.2,
            "tools": [{"google_search": {}}],
        },
        model_name=model_name,
        module_execution_id=context.module_execution_id,
        actor_id=context.actor_id,
    )

    attempts = tuple(attempt.to_dict() for attempt in result.attempts)
    raw_response = _raw_response(session, result.response.raw_artifact_id)
    grounding = extract_grounding(raw_response)

    search_snapshot_id: uuid.UUID | None = None
    if result.ok:
        try:
            snapshot = store.record_source_snapshot(
                session,
                run_id=context.run_id,
                source_kind=SourceKind.SEARCH,
                provider=SEARCH_PROVIDER,
                collected_at=result.response.received_at or moment,
                validation_status=(
                    ValidationStatus.VERIFIED if grounding.available else ValidationStatus.UNVERIFIED
                ),
                fixture=fixture,
                attempt_id=result.response.attempt_id,
                artifact_id=result.response.raw_artifact_id,
                note=(
                    f"{LOGICAL_CALL_ID}: Google Search grounding으로 확인한 출처"
                    if grounding.available
                    else f"{LOGICAL_CALL_ID}: 이번 호출에 검색 출처가 없습니다."
                ),
                actor_id=context.actor_id,
            )
            search_snapshot_id = snapshot.id
        except Exception:  # pragma: no cover - 실행 행이 없는 단독 호출
            search_snapshot_id = None

    if result.ok:
        research = validate_model_output(
            parse_model_output(result.text), facts=facts, grounding=grounding
        )
    else:
        research = validate_model_output(None, facts=facts, grounding=grounding)

    research = ValidatedAvailability(
        material_state=research.material_state,
        material_detail=research.material_detail,
        facts=research.facts,
        player_updates=research.player_updates,
        reported_absences=research.reported_absences,
        impacts=research.impacts,
        uncertainties=research.uncertainties,
        search_note=research.search_note,
        rejected=research.rejected,
        grounding=research.grounding,
        search_snapshot_id=search_snapshot_id,
        team_names=research.team_names,
        fixture_label=research.fixture_label,
    )

    claims = _claims(research, search_snapshot_id=search_snapshot_id)
    coverage = _coverage_entries(research)
    diagnostics = list(_diagnostics(research, mode=mode, stopped_reason=result.stopped_reason))
    if result.missing_configuration:
        diagnostics.append(f"모델 설정이 없어 호출하지 않았습니다: {result.missing_configuration}")

    has_adopted = any(claim.decision is not ClaimDecision.EXCLUDED for claim in claims)
    if not result.ok:
        quality = QualityStatus.INSUFFICIENT
        unavailable_reason = (
            "R2 조사 모델 호출이 실패해 결장 영향 본문을 만들 수 없습니다."
            + (f" 원인: {result.stopped_reason}" if result.stopped_reason else "")
        )
        if facts.facts:
            unavailable_reason += (
                " API 부상 사실은 보존했지만, 해석·검증 없이 본문으로 확정하지 않았습니다."
            )
    elif not research.has_reader_facts:
        quality = QualityStatus.INSUFFICIENT
        unavailable_reason = (
            "근거가 확인된 부상·결장 항목이 없어 본문을 만들지 않았습니다."
            " 자료 상태는 관리자 기록에 남겼습니다."
        )
    else:
        quality = QualityStatus.READY if has_adopted else QualityStatus.INSUFFICIENT
        unavailable_reason = None

    payload: dict[str, Any] = {
        "module_id": AVAILABILITY_MODULE_ID,
        "implementation_version": IMPLEMENTATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "mode": mode.value,
        "claims": [claim.to_dict() for claim in claims],
        "coverage": [entry.to_dict() for entry in coverage],
        "research": research.to_dict(),
        "raw_grounding": research.grounding.to_dict(),
        "search_snapshot_id": str(search_snapshot_id) if search_snapshot_id else None,
        "model_text": (result.text or "")[:4000] or None,
        "attempt_count": len(attempts),
        "reader_sources": [dict(item) for item in _reader_sources(research)],
    }

    return AvailabilityOutcome(
        mode=mode,
        quality=quality,
        payload=payload,
        sources=_reader_sources(research),
        diagnostics=tuple(diagnostics),
        unavailable_reason=unavailable_reason,
        external_calls=(len(attempts) if mode is RunMode.LIVE and result.ok else 0),
        research=research,
        text=result.text,
        attempts=attempts,
    )


def _raw_response(session: Session, artifact_id: uuid.UUID | None) -> Any:
    """원문 응답 아티팩트 본문을 읽는다. 없거나 만료면 `None`. 여기서 만들지 않는다."""
    if artifact_id is None:
        return None
    from app.preview.models import PreviewArtifact

    row = session.get(PreviewArtifact, artifact_id)
    if row is None or row.body is None:
        return None
    try:
        return json.loads(row.body)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 본문 구성 (결정적, 두 번째 LLM 호출 없음)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ComposedAvailability:
    title: str
    body: str
    sources: tuple[Mapping[str, Any], ...]
    quality: QualityStatus
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "sources": [dict(item) for item in self.sources],
            "quality": self.quality.value,
            "diagnostics": list(self.diagnostics),
        }


def _team_label(team_id: int | None, names: Mapping[int, str]) -> str:
    if team_id is None:
        return "팀 미확인"
    name = names.get(team_id)
    return name if name else f"팀 {team_id}"


def _source_label(fact: InjuryFact) -> str:
    """근거 출처 표기. 저장 자료 재사용을 새 API 수집으로 부르지 않는다."""
    if fact.source == "stored_db":
        return "저장된 API-Football 부상 자료(읽기 전용)"
    return "API-Football 부상 자료"


def _evidence_note(evidence: Sequence[str], facts_by_id: Mapping[str, InjuryFact]) -> str:
    labels: list[str] = []
    for token in evidence:
        fact = facts_by_id.get(token)
        if fact is not None:
            collected = fact.collected_at.date().isoformat() if fact.collected_at else "시각 미상"
            labels.append(f"{_source_label(fact)}(수집 {collected})")
        elif token.lower().startswith(("http://", "https://")):
            labels.append("검색 출처")
    return ", ".join(dict.fromkeys(labels)) or "근거 확인"


def _status_sentence(status: str, *, conflict: bool, api_status: str | None) -> str:
    if conflict:
        return (
            f"API 표기는 {STATUS_LABELS.get(api_status or STATUS_UNKNOWN, '표기 없음')}"
            f"였고, 같은 기간 보도는 {STATUS_LABELS.get(status, status)}을 전합니다"
            " — 어느 쪽도 확정으로 바꾸지 않았습니다"
        )
    sentence = STATUS_LABELS.get(status, status)
    if status == STATUS_DOUBTFUL:
        # '결장 확정'이라는 표현 자체를 쓰지 않는다. 확정으로 읽히지 않게 문장을 만든다.
        return f"{sentence} — 출전 여부가 확정되지 않았습니다"
    return sentence


def _summary_line(research: ValidatedAvailability) -> str:
    """검증된 항목 수만으로 만드는 도입 문장. 없는 수치를 만들지 않는다."""
    doubtful = sum(1 for update in research.player_updates if update.status == STATUS_DOUBTFUL)
    confirmed = sum(
        1 for update in research.player_updates if update.status == STATUS_CONFIRMED_ABSENCE
    )
    reported = len(research.reported_absences)
    conflicts = sum(1 for update in research.player_updates if update.conflict)
    parts: list[str] = []
    if confirmed:
        parts.append(f"결장 표기 {confirmed}명")
    if doubtful:
        parts.append(f"출전 불확실 {doubtful}명")
    if reported:
        parts.append(f"현지 보도 결장 {reported}명")
    if not parts:
        parts.append(f"확인된 항목 {research.adopted_fact_count}건")
    head = "이번 경기의 결장·출전 불확실 상황은 " + ", ".join(parts) + "으로 확인됩니다."
    if conflicts:
        head += " 일부 항목은 API 표기와 보도가 달라 양쪽을 함께 적었습니다."
    return head


def _group_updates(
    updates: Sequence[PlayerUpdate], absences: Sequence[ReportedAbsence]
) -> list[int | None]:
    """본문에 팀을 묶어 보여줄 순서. 등장 순서를 그대로 쓰고 팀을 만들지 않는다."""
    order: list[int | None] = []
    for update in updates:
        if update.team_id not in order:
            order.append(update.team_id)
    for absence in absences:
        if absence.team_id not in order:
            order.append(absence.team_id)
    return order


def compose_availability_body(payload: Mapping[str, Any]) -> ComposedAvailability:
    """검증된 조사 payload로 독자용 한국어 본문을 결정적으로 만든다.

    누락·검색 실패·재시도 문구는 본문에 넣지 않는다. 근거가 없으면 빈 본문을 돌려주고
    호출자가 초안으로 처리한다. 두 번째 모델 호출은 하지 않는다.
    """
    research = ValidatedAvailability.from_dict(payload.get("research") or {})
    names = dict(research.team_names)
    facts_by_id = {fact.evidence_id: fact for fact in research.facts}
    title = "부상·결장 영향"

    if not research.has_reader_facts:
        return ComposedAvailability(
            title=title,
            body="",
            sources=(),
            quality=QualityStatus.INSUFFICIENT,
            diagnostics=("독자용 본문을 만들 근거가 없습니다. 관리자 초안으로 남깁니다.",),
        )

    lines: list[str] = [_summary_line(research), ""]
    lines.append("결장·출전 불확실")
    for team_id in _group_updates(research.player_updates, research.reported_absences):
        team = _team_label(team_id, names)
        lines.append(f"{team}")
        for update in research.player_updates:
            if update.team_id != team_id:
                continue
            who = update.player_name or (
                f"선수 ID {update.player_id}" if update.player_id is not None else "선수 미확인"
            )
            status = _status_sentence(
                update.status, conflict=update.conflict, api_status=update.api_status
            )
            lines.append(f"- {who}: {status}. {update.summary}")
            lines.append(f"  근거: {_evidence_note(update.evidence, facts_by_id)}")
        for absence in research.reported_absences:
            if absence.team_id != team_id:
                continue
            lines.append(f"- {absence.player_name}: 결장 보도. {absence.summary}")
            lines.append(f"  근거: {_evidence_note(absence.evidence, facts_by_id)}")

    if research.impacts:
        lines.append("")
        lines.append("전력 영향 (근거에 기반한 해석)")
        for impact in research.impacts:
            team = _team_label(impact.team_id, names)
            lines.append(f"- {team}: {impact.summary}")
            lines.append(f"  근거: {_evidence_note(impact.basis, facts_by_id)}")

    if research.uncertainties:
        lines.append("")
        lines.append("남은 불확실성")
        for note in research.uncertainties:
            lines.append(f"- {note}")

    sources: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for fact in research.facts:
        if fact.evidence_id in seen:
            continue
        seen.add(fact.evidence_id)
        collected = fact.collected_at.isoformat() if fact.collected_at else "시각 미상"
        team = names.get(fact.team_id) if fact.team_id is not None else None
        sources.append(
            {
                "label": _source_label(fact)
                + (f" · {team}" if team else "")
                + f" · {fact.display_name}",
                "kind": "api",
                "url": None,
                "note": (
                    f"수집 {collected} · 원문 표기 {fact.type_marker or '표기 없음'}"
                    + (f" · 사유 {fact.reason}" if fact.reason else "")
                ),
            }
        )
    for source in research.grounding.sources:
        if source.uri in seen:
            continue
        seen.add(source.uri)
        sources.append(
            {
                "label": source.title or source.domain or source.uri,
                "kind": "search",
                "url": source.uri,
                "note": "검색 결과가 인용한 출처입니다. 원문 전체를 직접 확인한 것은 아닙니다.",
            }
        )

    return ComposedAvailability(
        title=title,
        body="\n".join(lines).strip(),
        sources=tuple(sources),
        quality=QualityStatus.READY,
    )


# --------------------------------------------------------------------------
# 노드 구현 (섹션 워크플로우 주입용)
# --------------------------------------------------------------------------


def _material_from_state(state: SectionState) -> Mapping[str, Any]:
    data = state.get("data")
    return dict(data) if isinstance(data, Mapping) else {}


def _loader_from_reader(reader: Any) -> Callable[[int], Sequence[Any]] | None:
    """읽기 전용 저장 자료 조회기에서 부상 행 로더를 만든다.

    `reader`는 `injuries_for_fixture(fixture_id)`를 가진 객체면 된다(덕 타이핑).
    없으면 `None`이고, 저장된 행을 읽지 않는다. 여기서 새 DB 연결을 만들지 않는다.
    """
    if reader is None:
        return None
    loader = getattr(reader, "injuries_for_fixture", None)
    return loader if callable(loader) else None


def availability_research_node(
    *,
    transport: Any,
    material: Mapping[str, Any] | None = None,
    stored_loader: Callable[[int], Sequence[Any]] | None = None,
    reader: Any = None,
    team_names: Mapping[int, str] | None = None,
    model_name: str | None = None,
    now: datetime | None = None,
    mode: RunMode | None = None,
) -> NodeImplementation:
    """섹션 워크플로우의 `research` 노드로 넣을 R2 구현.

    `state["data"]`(D0 노드 산출)에서 부상 자료를 읽는다. `material`을 주면 그 값을
    우선 쓴다(단독 검증·기록 재생용).
    """

    loader = stored_loader or _loader_from_reader(reader)

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        payload_material = material if material is not None else _material_from_state(state)
        execution_id = ctx.module_execution_id or ctx.context.module_execution_id
        context = (
            _with_execution(ctx.context, execution_id)
            if execution_id and ctx.context.module_execution_id != execution_id
            else ctx.context
        )
        module_input = _module_input_for(ctx, state)
        outcome = research_availability(
            ctx.session,
            module_input=module_input,
            context=context,
            transport=transport,
            budget=ctx.budget,
            material=payload_material,
            stored_loader=loader,
            team_names=team_names,
            model_name=model_name,
            now=now,
        )
        return NodeOutcome(
            payload=dict(outcome.payload),
            # 독자용 근거 목록은 compose 노드가 한 번만 낸다(중복 방지).
            sources=(),
            quality=outcome.quality,
            diagnostics=outcome.diagnostics,
            unavailable_reason=outcome.unavailable_reason,
            external_calls=outcome.external_calls,
        )

    return NodeImplementation(
        module_id=AVAILABILITY_MODULE_ID,
        implementation_version=IMPLEMENTATION_VERSION,
        prompt_version=PROMPT_VERSION,
        mode=mode or getattr(transport, "mode", RunMode.MOCK),
        run=run,
    )


def _with_execution(context: ExecutionContext, module_execution_id: uuid.UUID) -> ExecutionContext:
    from dataclasses import replace

    return replace(context, module_execution_id=module_execution_id)


def _module_input_for(ctx: SectionNodeContext, state: SectionState) -> ModuleInput:
    """공통 runner가 만든 입력 문맥을 그대로 쓴다. 새 해시를 만들지 않는다."""
    from app.preview.contracts import MODULE_INPUT_VERSION, compute_input_hash

    fixture = ctx.fixture or state.get("fixture")
    identity = FixtureIdentity.from_dict(dict(fixture)) if fixture else None
    return ModuleInput(
        module_id=AVAILABILITY_MODULE_ID,
        fixture=identity,
        snapshot_ids=tuple(ctx.snapshot_ids),
        selected_result_ids=tuple(ctx.selected_result_ids),
        input_hash=compute_input_hash(
            {
                "module_id": AVAILABILITY_MODULE_ID,
                "fixture": dict(fixture or {}),
                "snapshot_ids": [str(item) for item in ctx.snapshot_ids],
                "selected_result_ids": [str(item) for item in ctx.selected_result_ids],
            }
        ),
        prompt_version=PROMPT_VERSION,
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=IMPLEMENTATION_VERSION,
        parameters={"node": "research"},
    )


def availability_compose_node(*, now: datetime | None = None, mode: RunMode | None = None) -> NodeImplementation:
    """검증된 R2 결과로 본문을 만드는 `compose_body` 노드."""

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        collected = state.get("research") or {}
        payload = collected.get(AVAILABILITY_MODULE_ID)
        if not isinstance(payload, Mapping):
            return NodeOutcome(
                unavailable_reason=(
                    "R2 조사 결과가 없어 부상·결장 본문을 만들 수 없습니다."
                    " 없는 내용을 만들어 채우지 않았습니다."
                ),
                quality=QualityStatus.INSUFFICIENT,
                diagnostics=("research 상태에 R2 결과가 없습니다.",),
            )
        composed = compose_availability_body(payload)
        if not composed.body.strip():
            return NodeOutcome(
                unavailable_reason=(
                    "근거가 확인된 부상·결장 항목이 없어 섹션 본문을 만들지 않았습니다."
                ),
                quality=QualityStatus.INSUFFICIENT,
                diagnostics=composed.diagnostics,
            )
        return NodeOutcome(
            title=composed.title,
            body=composed.body,
            sources=composed.sources,
            quality=composed.quality,
            diagnostics=composed.diagnostics,
        )

    return NodeImplementation(
        module_id=COMPOSE_MODULE_ID,
        implementation_version=COMPOSE_IMPLEMENTATION_VERSION,
        prompt_version=None,
        mode=mode or RunMode.LIVE,
        run=run,
    )


def build_availability_implementations(
    *,
    prepare_data: NodeImplementation,
    transport: Any,
    material: Mapping[str, Any] | None = None,
    stored_loader: Callable[[int], Sequence[Any]] | None = None,
    reader: Any = None,
    team_names: Mapping[int, str] | None = None,
    model_name: str | None = None,
    now: datetime | None = None,
) -> WorkflowImplementations:
    """`section_availability` 워크플로우 구현 묶음.

    D0 준비 노드는 공통 소유(MP-05 통합)이므로 인자로 받는다. 이 함수는 R2 조사 노드와
    본문 구성 노드만 제공한다.

    Args:
        prepare_data: 공통 D0 준비 노드(저장 자료 재사용).
        transport: 모델 전송. mock/replay/live는 transport가 밝힌 값을 쓴다.
        material: D0 산출을 state 대신 고정값으로 줄 때 쓴다(재생·검증용).
        stored_loader: 저장된 부상 행 로더(읽기 전용 DB).
        reader: `injuries_for_fixture`를 가진 읽기 전용 조회기. 주면 로더로 쓴다.
        team_names: 확인된 팀 id→이름. 없으면 저장 자료의 이름을 쓴다.
        model_name: 모델 이름. 없으면 transport가 밝힌 이름을 쓴다(대체 모델 없음).
    """
    return WorkflowImplementations(
        prepare_data=prepare_data,
        research=(
            availability_research_node(
                transport=transport,
                material=material,
                stored_loader=stored_loader,
                reader=reader,
                team_names=team_names,
                model_name=model_name,
                now=now,
            ),
        ),
        compose_body=availability_compose_node(now=now),
    )
