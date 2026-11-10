"""R4 주목 선수 선정 (section_players).

경기력(R1/section_form)과 **분리된** 별도 모듈이다. 이 파일이 하는 일은 한 경기의
주목 선수를 AI가 **선정**하고, 각 항목을 `selected_player`(선정 선수)·
`selection_reason`(선정 이유) 두 표시 필드로 나눠 돌려주는 것이다.

경계(사용자 확정 2026-11-11):

- R1은 경기력만, R4는 주목 선수만 맡는다. 기존 R1의 합친 저장 결과는 이전 이력이며
  R4가 만든 것으로 바꿔 표시하지 않는다.
- 표시 이름은 **DB 한국어 값**을 쓴다. 모델 음차·임의 번역을 만들지 않는다. 해석기는
  주입받는다(`resolver=` 또는 `name_map=`). 주입이 없으면 원래 표기를 유지하고
  `mapping_status="resolver_not_injected"`로 미해결을 드러낸다. 이름을 지어내지 않는다.
- 모델 호출은 `provider.request_model` **한 번**뿐이다. 두 번째 종합·검증 호출을 두지
  않는다. 재시도·예산은 공통 실행기(`RunBudget`/`execute_request`) 몫이며, 이 모듈은
  넘겨받은 예산을 그대로 쓴다(모듈별 상한을 새로 만들지 않는다).
- 사실/판단 경계는 **기존 공유 판단 API**(`form.validate_response`)를 그대로 쓴다.
  선정 자체는 AI 판단이라 외부 동의 출처를 요구하지 않고, 이유 문장에 섞인 수치·부상
  같은 사실 전제만 제공된 API/검색 근거와 대조한다. 그래서 이 파일은 판단 엔진을
  복사하지 않고 R1이 검증한 경계를 호출한다.
- 원문 응답은 그대로 보존한다(`raw_model_text`, `raw_grounding`). 표시 이름을 바꿔도
  원문과 모델이 고른 표기는 지우지 않는다(`model_selected_player`).

이 파일은 새 파일이며, 공유 등록부·섹션 연결·버전 manifest는 통합 담당(MP-10)이
이어 붙인다. 이 모듈은 자기 빌더(`build_players_implementations`)와 노드만 제공한다.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from sqlalchemy.orm import Session

from app.preview import provider, store
from app.preview.contracts import (
    MODULE_INPUT_VERSION,
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
    compute_input_hash,
)
from app.preview.modules import form
from app.preview.modules import players_contract as contract
from app.preview.runner import (
    COMPOSE_MODULE_ID,
    NodeImplementation,
    NodeOutcome,
    SectionNodeContext,
    SectionState,
    WorkflowImplementations,
)
from app.preview.retry import RunBudget

__all__ = [
    "COMPOSE_IMPLEMENTATION_VERSION",
    "IMPLEMENTATION_VERSION",
    "LOGICAL_CALL_ID",
    "PLAYERS_MODULE_ID",
    "PROMPT_VERSION",
    "ComposedPlayers",
    "NameMapping",
    "PlayersMaterial",
    "PlayersResearch",
    "build_players_implementations",
    "build_prompt",
    "compose_players_body",
    "load_prompt",
    "parse_model_output",
    "players_compose_node",
    "players_research_node",
    "resolve_selection_names",
    "research_players",
]

# 섹션 워크플로우(`section_players`)의 조사 모듈 id.
PLAYERS_MODULE_ID = "R4"
IMPLEMENTATION_VERSION = "mp05p-r4-1"
COMPOSE_IMPLEMENTATION_VERSION = "mp05p-r4-compose-1"
PROMPT_VERSION = "mp05p-r4-prompt-1"

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "players.md"
LOGICAL_CALL_ID = "section_players/research-r4"
SEARCH_PROVIDER = "vertex-google-search"

SECTION_TITLE = "주목 선수"

# 조사 결과 상태 표기. 이 모듈이 만드는 자료의 확보 상태다.
STATE_AVAILABLE = "available"
STATE_API_NOT_PROVIDED = "api_not_provided"
STATE_CALL_ERROR = "call_error"
STATE_NOT_RUN = "not_run"
STATE_VALIDATION_REJECTED = "validation_rejected"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load_prompt(path: Path | None = None) -> str:
    """R4 프롬프트 전문. 없으면 조용히 대체하지 않고 실패한다."""
    return (path or PROMPT_PATH).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 입력 자료 (D0 산출 재사용)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayersMaterial:
    """R4가 쓰는 공유 자료(D0 산출). 새 API 호출 없이 받은 값만 담는다."""

    facts: form.FormFacts
    roster: tuple[Mapping[str, Any], ...] = ()
    note: str | None = None

    @property
    def state(self) -> str:
        return STATE_AVAILABLE if self.facts.facts else STATE_API_NOT_PROVIDED

    @property
    def team_ids(self) -> tuple[int, ...]:
        """이 경기의 두 팀 id. 후보 범위를 좁힐 때만 쓴다(새 권한을 만들지 않는다)."""
        ids = [self.facts.home_team_id, self.facts.away_team_id]
        return tuple(item for item in ids if item)


def _as_datetime(value: Any) -> datetime | None:
    """저장된 시각 표기를 읽는다. 해석하지 못하면 `None`(지금 시각으로 채우지 않음)."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _fixture_identity(fixture: Mapping[str, Any] | None) -> FixtureIdentity | None:
    if not fixture:
        return None
    try:
        return FixtureIdentity.from_dict(dict(fixture))
    except (KeyError, TypeError, ValueError):
        return None


def material_from_state(state: Mapping[str, Any] | None) -> PlayersMaterial:
    """D0 노드 산출(`state["data"]`)에서 R4 입력을 만든다. 없는 값은 비워 둔다."""
    data = state if isinstance(state, Mapping) else {}
    fixture = _fixture_identity(data.get("fixture") if isinstance(data, Mapping) else None)
    moment = _now()
    facts: list[form.Fact] = []
    for row in data.get("facts") or ():
        if not isinstance(row, Mapping):
            continue
        fact_id = str(row.get("fact_id") or "").strip()
        text = str(row.get("text") or "").strip()
        snapshot_id = str(row.get("snapshot_id") or "").strip()
        if not fact_id or not text or not snapshot_id:
            continue
        collected = row.get("collected_at")
        facts.append(
            form.Fact(
                fact_id=fact_id,
                text=text,
                snapshot_id=snapshot_id,
                collected_at=_as_datetime(collected),
                subject_team_id=(
                    int(row["subject_team_id"])
                    if isinstance(row.get("subject_team_id"), int)
                    else None
                ),
            )
        )
    roster = tuple(
        dict(item) for item in data.get("roster") or () if isinstance(item, Mapping)
    )
    fixture_payload = data.get("fixture") if isinstance(data.get("fixture"), Mapping) else {}
    if fixture is None:
        return PlayersMaterial(
            facts=form.FormFacts(
                fixture_id=0,
                league_id=0,
                season=0,
                home_team_id=0,
                away_team_id=0,
                kickoff_at=moment,
                home_team="홈팀",
                away_team="원정팀",
                league=None,
            ),
            roster=roster,
            note="경기 식별자가 없어 공유 자료를 읽지 않았습니다.",
        )
    return PlayersMaterial(
        facts=form.FormFacts(
            fixture_id=fixture.fixture_id,
            league_id=fixture.league_id,
            season=fixture.season,
            home_team_id=fixture.home_team_id,
            away_team_id=fixture.away_team_id,
            kickoff_at=fixture.kickoff_at,
            home_team=str(fixture_payload.get("home_team") or f"team {fixture.home_team_id}"),
            away_team=str(fixture_payload.get("away_team") or f"team {fixture.away_team_id}"),
            league=(
                str(fixture_payload["league"]) if fixture_payload.get("league") else None
            ),
            facts=tuple(facts),
            snapshot_ids=tuple(dict.fromkeys(fact.snapshot_id for fact in facts)),
            collected_at=moment,
            source_note=data.get("note") if isinstance(data.get("note"), str) else None,
        ),
        roster=roster,
    )


# --------------------------------------------------------------------------
# 이름 해석 (주입식)
# --------------------------------------------------------------------------


class PlayerNameResolver(Protocol):
    """이름 해석기가 갖춰야 할 최소 모양(덕 타이핑).

    `app.preview.localized_names.DisplayNames.resolve_player`가 이 모양을 그대로
    만족한다. 이 모듈은 그 클래스를 import하지 않고 **주입받아** 쓴다. 그래야 해석
    구현·DB 권한이 이 파일과 분리되고, 이름 매핑 담당이 인터페이스를 바꿔도 여기서
    복제하지 않는다.
    """

    def resolve_player(
        self,
        name: Any,
        *,
        team_hint: Any = None,
        scope_team_ids: Any = None,
        player_id: int | None = None,
        external_id: int | None = None,
        id_space: str = "internal",
    ) -> Any: ...


@dataclass(frozen=True)
class NameMapping:
    """선수 한 명의 표시 이름 해석 결과. 표시 필드와 내부 진단을 함께 둔다."""

    display_name: str
    player_id: int | None = None
    external_id: int | None = None
    team_display_name: str | None = None
    name_source: str = "original"
    mapping_status: str = "unresolved"
    mapping_reason: str | None = None
    mapping_detail: str | None = None

    @property
    def resolved(self) -> bool:
        return self.mapping_status == "resolved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "display_name": self.display_name,
            "player_id": self.player_id,
            "external_id": self.external_id,
            "team_display_name": self.team_display_name,
            "name_source": self.name_source,
            "mapping_status": self.mapping_status,
            "mapping_reason": self.mapping_reason,
            "mapping_detail": self.mapping_detail,
        }


def _normalize_key(value: Any) -> str:
    """이름 비교 키. 표시 문구를 만들지 않고 같은 표기인지만 본다."""
    raw = str(value or "").strip().casefold()
    for entity, replacement in (("&apos;", "'"), ("&#39;", "'")):
        raw = raw.replace(entity, replacement)
    return " ".join(raw.replace(".", " ").split())


def _unresolved(
    original: str,
    *,
    status: str,
    reason: str,
    detail: str,
) -> NameMapping:
    """해석 실패. 원래 표기를 유지하고 사유를 남긴다(이름을 지어내지 않는다)."""
    return NameMapping(
        display_name=original,
        name_source="original",
        mapping_status=status,
        mapping_reason=reason,
        mapping_detail=detail,
    )


def _from_resolution(original: str, resolution: Any) -> NameMapping:
    """해석기 반환값을 표시 이름·내부 메타데이터로 옮긴다."""
    player = getattr(resolution, "player", None)
    unmapped = getattr(resolution, "unmapped", None)
    reason = getattr(unmapped, "reason", None)
    reason_value = getattr(reason, "value", reason)
    detail = getattr(unmapped, "detail", None)
    if player is None:
        return _unresolved(
            original,
            status="unresolved",
            reason=str(reason_value or "not_found"),
            detail=str(detail or "저장된 DB 한국어 이름과 확실히 일치하는 항목이 없습니다."),
        )
    display = str(getattr(player, "display_name", "") or "").strip() or original
    name_ko = getattr(player, "name_ko", None)
    source = getattr(player, "source", None)
    source_value = getattr(source, "value", source)
    is_resolved = bool(name_ko) or str(source_value or "") in {"db_korean", "db_short_korean"}
    return NameMapping(
        display_name=display if is_resolved else original,
        player_id=getattr(player, "player_id", None),
        external_id=getattr(player, "external_id", None),
        team_display_name=getattr(player, "team_display_name", None),
        name_source=str(source_value or ("db_korean" if name_ko else "original")),
        mapping_status="resolved" if is_resolved else "unresolved",
        mapping_reason=None if is_resolved else str(reason_value or "db_korean_missing"),
        mapping_detail=None if is_resolved else str(detail or ""),
    )


def _from_name_map(
    original: str, name_map: Mapping[str, str]
) -> NameMapping:
    """기록된 이름 맵으로 해석한다. 정확히 하나로 정해질 때만 채택한다.

    대소문자·마침표만 다른 표기는 같은 이름으로 본다. 정규화 키가 같으면서 **서로 다른**
    한국어 값이 둘 이상이면 고르지 않고 미해결로 돌려준다(동명이인 안전장치).
    """
    key = _normalize_key(original)
    if not key:
        return _unresolved(
            original,
            status="unresolved",
            reason="empty",
            detail="선수 이름이 비어 있습니다.",
        )
    exact = name_map.get(original)
    if isinstance(exact, str) and exact.strip():
        return NameMapping(
            display_name=exact.strip(),
            name_source="db_korean",
            mapping_status="resolved",
        )
    matches = {
        str(value).strip()
        for name, value in name_map.items()
        if _normalize_key(name) == key and isinstance(value, str) and value.strip()
    }
    if len(matches) == 1:
        return NameMapping(
            display_name=matches.pop(),
            name_source="db_korean",
            mapping_status="resolved",
        )
    if len(matches) > 1:
        return _unresolved(
            original,
            status="unresolved",
            reason="ambiguous",
            detail=f"같은 표기에 한국어 이름이 {len(matches)}개라 하나를 고르지 않았습니다.",
        )
    return _unresolved(
        original,
        status="unresolved",
        reason="db_korean_missing",
        detail="주입된 이름 맵에 이 선수의 DB 한국어 값이 없습니다.",
    )


def _resolve_one(
    original: str,
    *,
    team_hint: str | None,
    resolver: Any | None,
    name_map: Mapping[str, str] | None,
    scope_team_ids: Sequence[int] | None,
    player_ref: int | None,
    id_space: str,
    id_is_hint: bool = True,
) -> NameMapping:
    if resolver is not None and hasattr(resolver, "resolve_player"):
        resolution = resolver.resolve_player(
            original,
            team_hint=team_hint,
            scope_team_ids=list(scope_team_ids or []) or None,
            player_id=player_ref,
            id_space=id_space,
            # 모델이 적은 `player_ref`는 **검증되지 않은 참조**다. 확실치 않은 숫자 때문에
            # DB에서 확인되는 한국어 이름을 포기하지 않도록 힌트로 표시한다. 반대로
            # 저장 DB/API에서 확인한 신뢰 ID는 호출자가 `id_is_hint=False`로 넘긴다.
            id_is_hint=id_is_hint,
        )
        return _from_resolution(original, resolution)
    if name_map:
        return _from_name_map(original, name_map)
    return _unresolved(
        original,
        status="resolver_not_injected",
        reason="resolver_not_injected",
        detail=(
            "이름 해석기·이름 맵이 주입되지 않아 DB 한국어 이름을 확인하지 못했습니다."
            " 원래 표기를 그대로 두며, 한국어 이름을 만들지 않았습니다."
        ),
    )


def _resolve_team_display(
    original: str | None,
    *,
    resolver: Any | None,
    name_map: Mapping[str, str] | None,
    id_space: str,
) -> tuple[str | None, str | None]:
    """팀 표시 이름을 DB 한국어 값으로 확인한다. 확인 실패 사유를 함께 돌려준다.

    팀 이름은 표시 보조값이라, 해석하지 못해도 선수 표시를 막지 않는다. 대신 사유를
    남겨 관리자 진단에서 확인할 수 있게 한다.
    """
    if not original:
        return None, None
    resolve_team = getattr(resolver, "resolve_team", None)
    if callable(resolve_team):
        resolved = resolve_team(original, id_space=id_space)
        if resolved is None:
            return None, "team_not_found"
        display = str(getattr(resolved, "display_name", "") or "").strip()
        source = getattr(resolved, "source", None)
        source_value = getattr(source, "value", source)
        if display and str(source_value or "") in {"db_korean", "db_short_korean"}:
            return display, None
        return None, str(source_value or "db_korean_missing")
    if name_map:
        mapping = _from_name_map(original, name_map)
        if mapping.resolved:
            return mapping.display_name, None
        return None, mapping.mapping_reason
    return None, "resolver_not_injected"


def resolve_selection_names(
    items: Sequence[Mapping[str, Any]],
    *,
    resolver: Any | None = None,
    name_map: Mapping[str, str] | None = None,
    scope_team_ids: Sequence[int] | None = None,
    id_space: str = "internal",
    id_is_hint: bool = True,
) -> tuple[list[dict[str, Any]], list[Mapping[str, Any]]]:
    """선정 항목의 `selected_player`를 DB 한국어 이름으로 바꾼다.

    두 표시 필드는 그대로 유지하고, 이름 해석 결과만 내부 메타데이터로 덧붙인다.
    해석하지 못한 항목은 원래 표기를 유지한 채 `unmapped`에 사유를 남긴다.

    `id_is_hint`는 항목의 ID 출처를 밝힌다. 기본값 `True`는 **모델이 응답에 적은**
    참조라 검증되지 않았다는 뜻이다. 저장 DB/API에서 확인한 ID를 넘길 때는 `False`로
    지정해, ID와 이름이 다른 선수를 가리키면 해석기가 `conflict`로 멈추게 한다.
    """
    rows: list[dict[str, Any]] = []
    unmapped: list[Mapping[str, Any]] = []
    for item in items:
        original = str(item.get(contract.SELECTED_PLAYER_FIELD) or "").strip()
        team_original = item.get("team") if isinstance(item.get("team"), str) else None
        mapping = _resolve_one(
            original,
            team_hint=team_original,
            resolver=resolver,
            name_map=name_map,
            scope_team_ids=scope_team_ids,
            player_ref=item.get("player_ref") if isinstance(item.get("player_ref"), int) else None,
            id_space=id_space,
            id_is_hint=id_is_hint,
        )
        row = dict(item)
        row[contract.SELECTED_PLAYER_FIELD] = mapping.display_name
        row["model_selected_player"] = original
        row["player_id"] = mapping.player_id
        row["external_id"] = mapping.external_id
        row["id_space"] = id_space
        row["name_source"] = mapping.name_source
        row["mapping_status"] = mapping.mapping_status
        row["mapping_reason"] = mapping.mapping_reason
        row["mapping_detail"] = mapping.mapping_detail
        # 팀 표시도 같은 DB 한국어 값을 쓴다. 확인하지 못하면 원래 표기를 유지한다.
        team_display, team_reason = _resolve_team_display(
            team_original,
            resolver=resolver,
            name_map=name_map,
            id_space=id_space,
        )
        row["model_team"] = team_original
        row["team"] = team_display or team_original
        row["team_display_name"] = team_display or mapping.team_display_name
        row["team_mapping"] = team_reason
        rows.append(row)
        if not mapping.resolved:
            unmapped.append(
                {
                    "kind": "player",
                    "original": original,
                    "display_name": mapping.display_name,
                    "reason": mapping.mapping_reason,
                    "detail": mapping.mapping_detail,
                }
            )
        if team_original and not team_display:
            unmapped.append(
                {
                    "kind": "team",
                    "original": team_original,
                    "display_name": team_display or team_original,
                    "reason": team_reason,
                    "detail": "팀 표시 이름을 DB 한국어 값으로 확인하지 못해 원래 표기를 유지합니다.",
                }
            )

    # 이유 문장 안에 영어로 다시 나온 **같은 인물**도 같은 DB 한국어 값으로 맞춘다.
    # 해석기가 등록한 표기만 바꾸고, 새 이름을 만들지 않는다.
    rewrite = getattr(resolver, "rewrite_body", None)
    if callable(rewrite):
        for row in rows:
            reason = row.get(contract.SELECTION_REASON_FIELD)
            if isinstance(reason, str) and reason.strip():
                row[contract.SELECTION_REASON_FIELD] = rewrite(reason)
    return rows, unmapped


# --------------------------------------------------------------------------
# 프롬프트
# --------------------------------------------------------------------------


def _roster_lines(roster: Sequence[Mapping[str, Any]]) -> str:
    """프롬프트에 넣는 선수 후보 목록. 확인된 값만 적고 없는 값을 만들지 않는다."""
    lines: list[str] = []
    for row in roster:
        player_id = row.get("player_id")
        name = row.get("display_name") or row.get("english_name")
        if not name:
            continue
        team = row.get("team_display_name") or row.get("team_name") or ""
        label = f"- {name}"
        if team:
            label += f" ({team})"
        if player_id is not None:
            label += f" [player_ref={player_id}]"
        lines.append(label)
    return "\n".join(lines) or "- 제공된 선수 후보 목록이 없습니다. 아래 API 자료의 표기만 쓴다."


def build_prompt(
    *,
    template: str,
    facts: form.FormFacts,
    roster: Sequence[Mapping[str, Any]] = (),
    today: datetime,
) -> str:
    """R4 프롬프트를 채운다. 값이 없으면 '없음'으로 표시하고 만들지 않는다."""
    values = {
        "fixture_label": facts.fixture_label,
        "fixture_id": str(facts.fixture_id),
        "league_id": str(facts.league_id),
        "season": str(facts.season),
        "kickoff_at": facts.kickoff_at.isoformat(),
        "home_team": facts.home_team,
        "home_team_id": str(facts.home_team_id),
        "away_team": facts.away_team,
        "away_team_id": str(facts.away_team_id),
        "today": today.date().isoformat(),
        "api_facts": facts.fact_text_block(),
        "evidence_ids": "\n".join(
            f"- `{fact.fact_id}`" for fact in facts.facts
        )
        or "- 인용 가능한 API 사실 id가 없습니다. 검색 URL만 쓸 수 있습니다.",
        "roster": _roster_lines(roster),
        "max_players": str(contract.MAX_SELECTED_PLAYERS),
    }
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


# --------------------------------------------------------------------------
# 모델 출력 해석
# --------------------------------------------------------------------------


def parse_model_output(text: str | None) -> Mapping[str, Any] | None:
    """모델 텍스트에서 JSON 객체 하나를 읽는다. 없으면 `None`.

    기존 공유 파서(`form.parse_model_json`)를 그대로 쓴다. 파싱 규칙을 복제하지 않는다.
    """
    try:
        return form.parse_model_json(text or "")
    except form.FormResearchError:
        return None


def model_players(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """모델 응답의 `players`를 계약 모양으로 정리한다. 값을 만들지 않고 옮기기만 한다."""
    items: list[dict[str, Any]] = []
    for raw in (payload or {}).get("players") or ():
        if not isinstance(raw, Mapping):
            continue
        player = str(raw.get(contract.SELECTED_PLAYER_FIELD) or raw.get("player") or "").strip()
        if not player:
            continue
        reason = str(raw.get(contract.SELECTION_REASON_FIELD) or raw.get("reason") or "").strip()
        ref = raw.get("player_ref")
        items.append(
            {
                contract.SELECTED_PLAYER_FIELD: player,
                contract.SELECTION_REASON_FIELD: reason,
                "team": str(raw.get("team") or "").strip() or None,
                "player_ref": int(ref) if isinstance(ref, int) or str(ref or "").isdigit() else None,
                "evidence": [str(item) for item in raw.get("evidence") or () if str(item).strip()],
                "superlative_basis": (
                    str(raw.get("superlative_basis") or "").strip() or None
                ),
            }
        )
        if len(items) >= contract.MAX_SELECTED_PLAYERS:
            break
    return items


def _shared_judgment_items(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """공유 판단 API(R1 계약)에 넘길 항목을 만든다.

    R1이 검증한 사실/판단 경계를 **호출**하기 위한 어댑터다. 판단 규칙을 복사하지 않기
    위해 필드 이름만 R1 항목 모양(`player`·`reason`)으로 맞춘다.
    """
    return [
        {
            "player": item.get(contract.SELECTED_PLAYER_FIELD),
            "team": item.get("team"),
            "reason": item.get(contract.SELECTION_REASON_FIELD),
            "evidence": list(item.get("evidence") or ()),
            "superlative_basis": item.get("superlative_basis"),
        }
        for item in items
    ]


def _fact_claims(facts: form.FormFacts) -> list[EvidenceClaim]:
    """D0 API 사실을 채택 근거로 남긴다. 문장을 만들지 않고 받은 값을 옮긴다."""
    claims: list[EvidenceClaim] = []
    for fact in facts.facts:
        if not fact.snapshot_id:
            continue
        claims.append(
            EvidenceClaim(
                claim_id=fact.fact_id,
                kind=ClaimKind.FACT,
                text=fact.text,
                snapshot_ids=(uuid.UUID(fact.snapshot_id),),
                decision=ClaimDecision.ADOPTED,
                subject_team_id=fact.subject_team_id,
            )
        )
    return claims


def _search_coverage(grounding: Mapping[str, Any], *, call_ok: bool) -> CoverageEntry:
    """검색 근거 확보 상태. 검색 부재를 '선정 불가'로 바꾸지 않고 그대로 남긴다."""
    urls = {
        str(source.get("url"))
        for source in grounding.get("sources") or ()
        if isinstance(source, Mapping) and source.get("url")
    }
    if not call_ok:
        return CoverageEntry(
            topic="매체·맥락 검색",
            state=CoverageState.CALL_ERROR,
            detail="모델 호출이 성공하지 않아 검색 근거를 확인하지 못했습니다.",
        )
    if urls:
        return CoverageEntry(
            topic="매체·맥락 검색",
            state=CoverageState.AVAILABLE,
            detail=f"검색 출처 {len(urls)}건",
        )
    return CoverageEntry(
        topic="매체·맥락 검색",
        state=CoverageState.SEARCH_NOT_FOUND,
        detail=str(grounding.get("note") or "검색 출처를 확보하지 못했습니다."),
    )


# --------------------------------------------------------------------------
# 결과
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayersResearch:
    """R4 조사 결과. 표시 필드와 내부 진단을 분리해 담는다."""

    material: PlayersMaterial
    mode: RunMode = RunMode.MOCK
    players: tuple[Mapping[str, Any], ...] = ()
    unmapped: tuple[Mapping[str, Any], ...] = ()
    claims: tuple[EvidenceClaim, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    # 공유 판단 API가 덜어낸 사실과 내려놓은 전제. **내부 메타데이터**이며 표시 필드가
    # 아니다. 관리자 진단과 검토에서 "무엇을 왜 뺐는지"를 확인하는 데 쓴다.
    dropped_facts: tuple[str, ...] = ()
    unasserted_premises: tuple[str, ...] = ()
    search_note: str | None = None
    grounding: Mapping[str, Any] = field(default_factory=dict)
    raw_model_text: str | None = None
    reader_sources: tuple[Mapping[str, Any], ...] = ()
    quality: QualityStatus = QualityStatus.PENDING
    unavailable_reason: str | None = None
    external_calls: int = 0
    attempt_count: int = 0
    origin: str = "live"
    implementation_version: str = IMPLEMENTATION_VERSION
    prompt_version: str = PROMPT_VERSION

    @property
    def selected_count(self) -> int:
        return len(self.players)

    @property
    def mapping_summary(self) -> Mapping[str, Any]:
        resolved = sum(1 for row in self.players if row.get("mapping_status") == "resolved")
        return {
            "resolved": resolved,
            "unresolved": len(self.players) - resolved,
            "resolver_injected": all(
                row.get("mapping_status") != "resolver_not_injected" for row in self.players
            )
            if self.players
            else None,
        }

    def payload(self) -> Mapping[str, Any]:
        """`ModuleResult.payload`. 두 표시 필드는 `players` 배열 안에 그대로 둔다."""
        return {
            "module_id": PLAYERS_MODULE_ID,
            "output_contract_version": contract.OUTPUT_CONTRACT_VERSION,
            "implementation_version": self.implementation_version,
            "prompt_version": self.prompt_version,
            "mode": self.mode.value,
            "origin": self.origin,
            "display_labels": dict(contract.DISPLAY_LABELS),
            "fixture": {
                "fixture_id": self.material.facts.fixture_id,
                "league_id": self.material.facts.league_id,
                "season": self.material.facts.season,
                "home_team_id": self.material.facts.home_team_id,
                "away_team_id": self.material.facts.away_team_id,
                "kickoff_at": self.material.facts.kickoff_at.isoformat(),
                "home_team": self.material.facts.home_team,
                "away_team": self.material.facts.away_team,
                "league": self.material.facts.league,
            },
            "players": [dict(row) for row in self.players],
            "unmapped": [dict(row) for row in self.unmapped],
            "mapping": dict(self.mapping_summary),
            "claims": [claim.to_dict() for claim in self.claims],
            "coverage": [entry.to_dict() for entry in self.coverage],
            "diagnostics": list(self.diagnostics),
            "uncertainties": list(self.uncertainties),
            "dropped_facts": list(self.dropped_facts),
            "unasserted_premises": list(self.unasserted_premises),
            "search_note": self.search_note,
            "raw_grounding": dict(self.grounding),
            "raw_model_text": (self.raw_model_text or "")[:8000] or None,
            "reader_sources": [dict(item) for item in self.reader_sources],
            "selection_rule_note": contract.SELECTION_RULE_NOTE,
            "attempt_count": self.attempt_count,
            "external_calls": self.external_calls,
        }


@dataclass(frozen=True)
class ComposedPlayers:
    """독자용 본문. 이름과 이유를 **분리한 줄**로만 쓴다."""

    title: str
    body: str
    sources: tuple[Mapping[str, Any], ...] = ()
    quality: QualityStatus = QualityStatus.PENDING
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "body": self.body,
            "sources": [dict(item) for item in self.sources],
            "quality": self.quality.value,
            "diagnostics": list(self.diagnostics),
        }


def compose_players_body(payload: Mapping[str, Any]) -> ComposedPlayers:
    """검증된 payload로 독자용 본문을 결정적으로 만든다. 두 번째 호출은 없다.

    표시 규칙: 선수 이름과 이유를 **한 문장으로 합치지 않는다**. 항목마다
    `선정 선수:` 줄과 `선정 이유:` 줄을 따로 낸다. 진단·매핑 사유는 본문에 넣지 않는다.
    """
    players = [
        row for row in payload.get("players") or () if isinstance(row, Mapping)
    ]
    if not players:
        return ComposedPlayers(
            title=SECTION_TITLE,
            body="",
            quality=QualityStatus.INSUFFICIENT,
            diagnostics=("선정된 선수가 없어서 독자용 본문을 만들지 않았습니다.",),
        )
    labels = contract.DISPLAY_LABELS
    lines = [f"이번 경기의 주목 선수 {len(players)}명입니다."]
    for row in players:
        name, reason = contract.display_fields(row)
        if not name or not reason:
            continue
        lines.append("")
        lines.append(f"{labels[contract.SELECTED_PLAYER_FIELD]}: {name}")
        lines.append(f"{labels[contract.SELECTION_REASON_FIELD]}: {reason}")
    body = "\n".join(lines).strip()
    if body.count("\n") < 2:
        return ComposedPlayers(
            title=SECTION_TITLE,
            body="",
            quality=QualityStatus.INSUFFICIENT,
            diagnostics=("표시할 선수 이름·이유가 모두 채워진 항목이 없습니다.",),
        )
    sources = tuple(
        dict(item) for item in payload.get("reader_sources") or () if isinstance(item, Mapping)
    )
    return ComposedPlayers(
        title=SECTION_TITLE,
        body=body,
        sources=sources,
        quality=QualityStatus.READY,
    )


def _rename_claim(claim: EvidenceClaim, old_prefix: str, new_prefix: str) -> EvidenceClaim:
    """공유 판단 API가 만든 claim id의 모듈 접두사만 바꾼다. 문장·근거는 그대로 둔다."""
    claim_id = claim.claim_id
    if claim_id.startswith(old_prefix):
        claim_id = new_prefix + claim_id[len(old_prefix):]
    return EvidenceClaim(
        claim_id=claim_id,
        kind=claim.kind,
        text=claim.text,
        snapshot_ids=claim.snapshot_ids,
        decision=claim.decision,
        decision_reason=claim.decision_reason,
        subject_team_id=claim.subject_team_id,
        subject_player_id=claim.subject_player_id,
        claimed_at=claim.claimed_at,
        source_url=claim.source_url,
    )


def _reader_sources(grounding: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """독자용 검색 출처. grounding이 준 실제 URL만 쓴다."""
    rows: list[Mapping[str, Any]] = []
    for source in grounding.get("sources") or ():
        if not isinstance(source, Mapping) or not source.get("url"):
            continue
        rows.append(
            {
                "label": str(source.get("title") or source.get("domain") or source.get("url")),
                "url": str(source.get("url")),
                "kind": "search",
                "note": "검색 결과가 인용한 출처입니다. 원문 전체를 직접 확인한 것은 아닙니다.",
            }
        )
    return tuple(rows)


def _raw_response(session: Session | None, artifact_id: uuid.UUID | None) -> Any:
    """저장된 원문 응답을 읽는다. 없으면 `None`. 여기서 만들지 않는다."""
    if session is None or artifact_id is None:
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
# 실행 (정상 호출 1회)
# --------------------------------------------------------------------------


def research_players(
    session: Session | None,
    *,
    module_input: ModuleInput,
    context: ExecutionContext,
    transport: Any,
    budget: RunBudget,
    material: PlayersMaterial | None = None,
    resolver: Any | None = None,
    name_map: Mapping[str, str] | None = None,
    roster: Sequence[Mapping[str, Any]] = (),
    id_space: str = "internal",
    prompt_template: str | None = None,
    model_name: str | None = None,
    now: datetime | None = None,
    recorded_raw_response: Any | None = None,
    origin: str = "live",
) -> PlayersResearch:
    """R4 조사 한 번. 모델 호출은 `provider.request_model` 한 번뿐이다.

    Args:
        session: 원문 아티팩트·스냅샷을 남길 세션. `None`이면 기록을 남기지 않는다
            (오프라인 재생·검증용).
        module_input: 공통 입력 계약(경기 식별·스냅샷·버전).
        context: 공통 실행 문맥(실행 ID·모드).
        transport: 모델 전송. mock/replay/live는 transport가 밝힌 값을 쓴다.
        budget: **넘겨받은** 공통 예산. 이 모듈은 새 상한을 만들지 않는다.
        material: D0 산출. 없으면 자료 없음으로 진행한다.
        resolver: 이름 해석기(`resolve_player`를 가진 객체). 이름 매핑 담당이 제공한다.
        name_map: 기록된 이름 맵. 해석기가 없을 때만 쓴다.
        roster: 확인된 선수 후보(있으면 프롬프트에 넣고 후보 범위를 좁힌다).
        id_space: 경기·팀·선수 ID가 어느 공간인지. `internal`은 DB 기본키,
            `external`은 API-Football ID다. 호출자가 저장 자료의 출처에 맞춰 정한다
            (저장 DB 경기는 internal, API 수집 경기는 external).
        recorded_raw_response: 재생 검증용 원문 응답. 세션이 없을 때만 쓴다.
        origin: 이 결과의 출처 표기. `live`/`replay`/`reused_r1_selection` 등.
    """
    moment = now or _now()
    mode = getattr(transport, "mode", RunMode.MOCK)
    facts_source = material or PlayersMaterial(
        facts=form.FormFacts(
            fixture_id=(
                module_input.fixture.fixture_id if module_input.fixture else 0
            ),
            league_id=module_input.fixture.league_id if module_input.fixture else 0,
            season=module_input.fixture.season if module_input.fixture else 0,
            home_team_id=module_input.fixture.home_team_id if module_input.fixture else 0,
            away_team_id=module_input.fixture.away_team_id if module_input.fixture else 0,
            kickoff_at=(
                module_input.fixture.kickoff_at if module_input.fixture else moment
            ),
            home_team="홈팀",
            away_team="원정팀",
            league=None,
        )
    )
    roster_rows = tuple(roster) or facts_source.roster
    template = prompt_template or load_prompt()
    prompt_text = build_prompt(
        template=template, facts=facts_source.facts, roster=roster_rows, today=moment
    )

    result = provider.request_model(
        logical_call_id=LOGICAL_CALL_ID,
        contents=[{"role": "user", "parts": [{"text": prompt_text}]}],
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=PLAYERS_MODULE_ID,
        operation="research_players",
        prompt_version=PROMPT_VERSION,
        # 검색은 기존 Google grounding 경로를 그대로 쓴다(새 검색 도구·두 번째 호출 없음).
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
            "tools": [{"google_search": {}}],
        },
        model_name=model_name,
        module_execution_id=context.module_execution_id,
        actor_id=context.actor_id,
        now=lambda: moment,
    )

    raw_response = (
        _raw_response(session, result.response.raw_artifact_id)
        if session is not None
        else recorded_raw_response
    )
    grounding = form.parse_grounding(raw_response)
    attempts = tuple(attempt.to_dict() for attempt in result.attempts)
    search_snapshot_id: uuid.UUID | None = None
    if session is not None and result.ok:
        try:
            snapshot = store.record_source_snapshot(
                session,
                run_id=context.run_id,
                source_kind=SourceKind.SEARCH,
                provider=SEARCH_PROVIDER,
                collected_at=result.response.received_at or moment,
                validation_status=(
                    ValidationStatus.VERIFIED
                    if _reader_sources(grounding)
                    else ValidationStatus.UNVERIFIED
                ),
                fixture=module_input.fixture,
                attempt_id=result.response.attempt_id,
                artifact_id=result.response.raw_artifact_id,
                note=(
                    f"{LOGICAL_CALL_ID}: Google Search grounding으로 확인한 출처"
                    if _reader_sources(grounding)
                    else f"{LOGICAL_CALL_ID}: 이번 호출에 검색 출처가 없습니다."
                ),
                actor_id=context.actor_id,
            )
            search_snapshot_id = snapshot.id
        except Exception:  # pragma: no cover - 실행 행이 없는 단독 호출
            search_snapshot_id = None

    api_claims = _fact_claims(facts_source.facts)
    coverage: list[CoverageEntry] = [
        _search_coverage(grounding, call_ok=result.ok),
    ]
    diagnostics: list[str] = []
    if facts_source.note:
        diagnostics.append(facts_source.note)

    if not result.ok or not result.text:
        reason = result.stopped_reason or (
            result.response.error_message or "모델 호출이 성공하지 않았습니다."
        )
        coverage.append(
            CoverageEntry(
                topic="주목 선수 선정",
                state=CoverageState.CALL_ERROR,
                detail="모델 호출이 성공하지 않아 선정을 만들지 않았습니다.",
            )
        )
        if result.missing_configuration:
            diagnostics.append(f"모델 설정이 없어 호출하지 않았습니다: {result.missing_configuration}")
        return PlayersResearch(
            material=facts_source,
            mode=mode,
            claims=tuple(api_claims),
            coverage=tuple(coverage),
            diagnostics=tuple(diagnostics + [f"R4 모델 호출 실패: {reason}"]),
            raw_model_text=None,
            reader_sources=_reader_sources(grounding),
            grounding=grounding,
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "주목 선수 선정 호출이 성공하지 않아 이 섹션의 본문을 만들 수 없습니다."
            ),
            external_calls=provider.sent_attempt_count(result, mode),
            attempt_count=len(attempts),
            origin=origin,
        )

    payload = parse_model_output(result.text)
    if payload is None:
        coverage.append(
            CoverageEntry(
                topic="주목 선수 선정",
                state=CoverageState.VALIDATION_REJECTED,
                detail="모델 응답을 JSON으로 해석하지 못했습니다.",
            )
        )
        return PlayersResearch(
            material=facts_source,
            mode=mode,
            claims=tuple(api_claims),
            coverage=tuple(coverage),
            diagnostics=tuple(diagnostics + ["R4 응답을 JSON으로 해석하지 못했습니다."]),
            raw_model_text=result.text,
            reader_sources=_reader_sources(grounding),
            grounding=grounding,
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "모델 응답을 선정 결과로 해석하지 못해 본문을 만들지 않았습니다."
            ),
            external_calls=provider.sent_attempt_count(result, mode),
            attempt_count=len(attempts),
            origin=origin,
        )

    raw_items = model_players(payload)
    # 사실/판단 경계는 공유 판단 API를 그대로 호출한다(판단 엔진 복제 없음).
    judged = form.validate_response(
        {"hot_players": _shared_judgment_items(raw_items)},
        facts=facts_source.facts,
        grounding=grounding,
        now=moment,
    )
    validated_rows = list(judged.hot_players)
    # 공유 판단 API가 항목별로 남긴 진단(덜어낸 사실·내려놓은 전제 포함)을 그대로 쓴다.
    # 같은 문장을 여기서 다시 만들지 않는다.
    diagnostics.extend(judged.diagnostics)

    # 검증을 통과한 항목에 이름 해석을 적용한다. 검증이 항목을 떨어뜨렸으므로
    # 모델 이름 표기로 짝을 맞춘다(같은 표기가 여러 번이면 등장 순서대로).
    queued: dict[str, list[Mapping[str, Any]]] = {}
    for row in validated_rows:
        queued.setdefault(str(row.get("player") or ""), []).append(row)
    matched: list[dict[str, Any]] = []
    for item in raw_items:
        original = str(item.get(contract.SELECTED_PLAYER_FIELD) or "")
        bucket = queued.get(original) or []
        if not bucket:
            continue
        validated = bucket.pop(0)
        matched.append(
            {
                contract.SELECTED_PLAYER_FIELD: original,
                contract.SELECTION_REASON_FIELD: str(
                    validated.get("reason")
                    or item.get(contract.SELECTION_REASON_FIELD)
                    or ""
                ).strip(),
                "team": item.get("team"),
                "player_ref": item.get("player_ref"),
                "evidence": list(item.get("evidence") or ()),
                "claim_id": (
                    "r4" + str(validated["claim_id"])[2:]
                    if str(validated.get("claim_id") or "").startswith("r1")
                    else validated.get("claim_id")
                ),
                "source_url": validated.get("source_url"),
            }
        )

    players, unmapped = resolve_selection_names(
        matched,
        resolver=resolver,
        name_map=name_map,
        scope_team_ids=facts_source.team_ids,
        id_space=id_space,
        # 선정 항목의 `player_ref`는 모델이 적은 값이므로 기본값(힌트)을 그대로 쓴다.
        id_is_hint=True,
    )
    for item in unmapped:
        diagnostics.append(
            f"이름 매핑 미해결({item.get('original')}): {item.get('reason')}"
            f" · {item.get('detail')}"
        )

    # 공유 판단 API는 R1 접두사가 붙은 claim id를 만든다. 이 실행의 결과는 R4이므로
    # 접두사만 R4로 바꿔 진단·기록에서 어느 모듈의 선정인지 분명히 한다(판단 규칙은
    # 공유 API가 그대로 수행한다).
    selection_claims = [
        _rename_claim(claim, "r1-player-", "r4-player-")
        for claim in judged.claims
        if claim.kind is ClaimKind.AI_INTERPRETATION
    ]
    claims = tuple(api_claims) + tuple(selection_claims)
    coverage.append(
        CoverageEntry(
            topic="주목 선수 선정",
            state=(
                CoverageState.AVAILABLE
                if players
                else CoverageState.VALIDATION_REJECTED
            ),
            detail=(
                f"{len(players)}명 선정"
                if players
                else "채택할 수 있는 선정 항목이 없습니다(모델 후보 "
                f"{len(raw_items)}건이 검증에서 제외됨)."
            ),
        )
    )
    search_note = payload.get("search_note")
    uncertainties = tuple(
        str(item) for item in payload.get("uncertainties") or () if str(item).strip()
    )
    quality = QualityStatus.READY if players else QualityStatus.INSUFFICIENT
    return PlayersResearch(
        material=facts_source,
        mode=mode,
        players=tuple(players),
        unmapped=tuple(unmapped),
        claims=claims,
        coverage=tuple(coverage),
        diagnostics=tuple(diagnostics),
        uncertainties=uncertainties,
        dropped_facts=tuple(judged.dropped_facts),
        unasserted_premises=tuple(judged.unasserted_premises),
        search_note=search_note if isinstance(search_note, str) and search_note.strip() else None,
        grounding=grounding,
        raw_model_text=result.text,
        reader_sources=_reader_sources(grounding),
        quality=quality,
        unavailable_reason=(
            None
            if players
            else "검증을 통과한 주목 선수 선정이 없어 이 섹션의 본문을 만들지 않았습니다."
        ),
        external_calls=provider.sent_attempt_count(result, mode),
        attempt_count=len(attempts),
        origin=origin,
    )


# --------------------------------------------------------------------------
# 섹션 노드 구현 (shared integration은 MP-10이 연결)
# --------------------------------------------------------------------------


def _module_input_for(ctx: SectionNodeContext, state: SectionState) -> ModuleInput:
    """공통 runner가 만든 문맥을 그대로 쓴다. 새 해시 규칙을 만들지 않는다."""
    fixture = ctx.fixture or state.get("fixture")
    identity = FixtureIdentity.from_dict(dict(fixture)) if fixture else None
    return ModuleInput(
        module_id=PLAYERS_MODULE_ID,
        fixture=identity,
        snapshot_ids=tuple(ctx.snapshot_ids),
        selected_result_ids=tuple(ctx.selected_result_ids),
        input_hash=compute_input_hash(
            {
                "module_id": PLAYERS_MODULE_ID,
                "fixture": dict(fixture or {}),
                "snapshot_ids": [str(item) for item in ctx.snapshot_ids],
                "selected_result_ids": [str(item) for item in ctx.selected_result_ids],
                "output_contract": contract.OUTPUT_CONTRACT_VERSION,
            }
        ),
        prompt_version=PROMPT_VERSION,
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=IMPLEMENTATION_VERSION,
        parameters={"node": "research"},
    )


def players_research_node(
    *,
    transport: Any,
    resolver: Any | None = None,
    name_map: Mapping[str, str] | None = None,
    material: PlayersMaterial | Mapping[str, Any] | None = None,
    roster: Sequence[Mapping[str, Any]] = (),
    id_space: str = "internal",
    model_name: str | None = None,
    now: datetime | None = None,
    mode: RunMode | None = None,
    origin: str | None = None,
) -> NodeImplementation:
    """`section_players` 워크플로우의 `research` 노드.

    `state["data"]`(D0 산출)를 입력으로 쓴다. `material`을 주면 그 값을 우선 쓴다
    (오프라인 재생·검증용). 예산은 runner가 넘긴 `ctx.budget` 하나만 쓴다.
    """

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        source = material if material is not None else state.get("data")
        if isinstance(source, PlayersMaterial):
            prepared = source
        else:
            prepared = material_from_state(source if isinstance(source, Mapping) else None)
        node_mode = mode or getattr(transport, "mode", RunMode.MOCK)
        research = research_players(
            ctx.session,
            module_input=_module_input_for(ctx, state),
            context=ctx.context,
            transport=transport,
            budget=ctx.budget,
            material=prepared,
            resolver=resolver,
            name_map=name_map,
            roster=roster or prepared.roster,
            id_space=id_space,
            model_name=model_name,
            now=now,
            origin=origin or node_mode.value,
        )
        return NodeOutcome(
            payload=dict(research.payload()),
            quality=research.quality,
            diagnostics=research.diagnostics,
            unavailable_reason=research.unavailable_reason,
            external_calls=research.external_calls,
        )

    return NodeImplementation(
        module_id=PLAYERS_MODULE_ID,
        implementation_version=IMPLEMENTATION_VERSION,
        prompt_version=PROMPT_VERSION,
        mode=mode or getattr(transport, "mode", RunMode.MOCK),
        run=run,
    )


def players_compose_node(*, mode: RunMode | None = None) -> NodeImplementation:
    """검증된 R4 결과로 본문을 만드는 `compose_body` 노드. 외부 호출은 없다."""

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        collected = state.get("research") or {}
        payload = collected.get(PLAYERS_MODULE_ID)
        if not isinstance(payload, Mapping):
            return NodeOutcome(
                unavailable_reason=(
                    "R4 선정 결과가 없어 주목 선수 본문을 만들 수 없습니다."
                    " 없는 내용을 만들어 채우지 않았습니다."
                ),
                quality=QualityStatus.INSUFFICIENT,
                diagnostics=("research 상태에 R4 결과가 없습니다.",),
            )
        composed = compose_players_body(payload)
        if not composed.body.strip():
            return NodeOutcome(
                unavailable_reason=(
                    "표시할 주목 선수 이름·이유가 없어 섹션 본문을 만들지 않았습니다."
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


def build_players_implementations(
    *,
    prepare_data: NodeImplementation,
    transport: Any,
    resolver: Any | None = None,
    name_map: Mapping[str, str] | None = None,
    material: PlayersMaterial | Mapping[str, Any] | None = None,
    roster: Sequence[Mapping[str, Any]] = (),
    id_space: str = "internal",
    model_name: str | None = None,
    now: datetime | None = None,
) -> WorkflowImplementations:
    """`section_players` 워크플로우 구현 묶음.

    D0 준비 노드는 공통 소유이므로 인자로 받는다(`build_availability_implementations`와
    같은 방식). 이 함수는 R4 조사 노드와 본문 조립 노드만 제공한다.
    """
    return WorkflowImplementations(
        prepare_data=prepare_data,
        research=(
            players_research_node(
                transport=transport,
                resolver=resolver,
                name_map=name_map,
                material=material,
                roster=roster,
                id_space=id_space,
                model_name=model_name,
                now=now,
            ),
        ),
        compose_body=players_compose_node(),
    )
