"""정보 원문 묶음(`InformationBundle`)에서 프리뷰 섹션을 작성한다 (PS-03).

이 모듈은 **작성(어댑터)** 만 소유한다. 수집·조사·저장·라우팅은 다른 소유자가 맡는다.

흐름(설계 §목적과 실행 순서):

    InformationBundle  →  프롬프트(구간·DB 자료)  →  provider.request_model 1회
                       →  모델 JSON 검증·이름 해석  →  결정적 본문 조립  →  SectionDraft

정직성 규칙(설계·계획 고정):

- 작성 3회(선수·부상·매체)와 최종 전망 1회는 **모두** `provider.request_model`만 쓴다.
  검색 도구를 넣지 않는다(조사는 앞 단계가 끝냈다).
- 배당(`section_odds`)은 **모델 호출 0회**다. 묶음의 정규시간 1X2 소수점만 옮긴다.
- 기사와 DB를 교차 대조해 탈락시키지 않는다. Google `grounding_chunks`/`supports`가
  없다는 이유로 기사를 버리지 않는다. 그 메타데이터를 만들어 붙이지도 않는다.
- 구간 id는 **묶음이 준 값 그대로** 쓴다(`src:x#p0`, `src:x-p1` 모두 허용). 없는 id를
  지어내지 않고, 모델이 목록에 없는 id를 적으면 그 인용만 버린다.
- 누락·실패·재시도 진단 문장은 본문에 넣지 않는다. 진단은 `SectionDraft.diagnostics`에만
  남긴다.
- 없는 선수·점수·배당을 채우지 않는다. 출전 불확실 표기를 결장 확정으로 바꾸지 않는다.
- 이름은 DB 한국어 값을 우선한다(주입된 해석기 사용). 해석기가 없으면 원래 표기를
  유지하고 한국어 이름을 만들지 않는다.

버전 축: 이 파일이 새 기본 경로의 구현·프롬프트 버전을 소유한다. 옛 R1~S1 모듈의 버전
상수는 바꾸지 않는다(옛 실행·승인 보존). A(통합 책임자)는 `bundle_section_versions()` /
`bundle_module_versions()`로 이 값을 워크플로우 버전 축에 연결한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy.orm import Session

from app.preview import information_bundle as bundle_contract
from app.preview import player_section_contracts as psc
from app.preview import player_section_processing as player_processing
from app.preview import provider
from app.preview.contracts import ExecutionContext, QualityStatus, RunMode
from app.preview.modules import outlook as outlook_module
from app.preview.modules import players as players_module
from app.preview.modules import players_contract as player_contract
from app.preview.modules import synthesis as synthesis_module
from app.preview.retry import RunBudget

__all__ = [
    "BUNDLE_MODULE_VERSIONS",
    "BUNDLE_SECTION_VERSIONS",
    "IMPLEMENTATION_VERSION",
    "LOGICAL_CALL_IDS",
    "MAX_BUNDLE_PLAYERS",
    "MAX_INJURIES_PER_TEAM",
    "MAX_MEDIA_PUBLISHERS",
    "PLAYERS_PER_TEAM",
    "PROMPT_VERSION_AVAILABILITY",
    "PROMPT_VERSION_FORECAST",
    "PROMPT_VERSION_OUTLOOK",
    "PROMPT_VERSION_ODDS",
    "PROMPT_VERSION_PLAYERS",
    "SectionDraft",
    "SUPPORTED_SECTION_IDS",
    "build_bundle_section",
    "bundle_module_versions",
    "bundle_section_versions",
    "load_prompt",
]

# --------------------------------------------------------------------------
# 버전·상한 (이 파일이 소유하는 새 기본 경로의 축)
# --------------------------------------------------------------------------

# 구현 버전: 작성 어댑터 전체의 축. 프롬프트·검증 규칙·본문 조립이 바뀌면 올린다.
# - 2: PS-06 검토 수정(DB 사실 `text`/`expected_status`·선수 통계 후보·한글 표기·예상
#   스코어 필수 판정).
# - 3: 출력 상한 상향(max_output_tokens 2048 → 40000). 2048에서 추론 토큰이 예산을
#   소비해 JSON이 절단됐으므로 결과 의미가 달라진다. 기존 승인 버전은 덮어쓰지 않는다.
# - 4: 검색 단계가 실제로 반환한 자료(자료 유형 라벨)를 작성 입력에 넣고, 기사 본문이
#   없어도 그 자료로 작성한다. 잘린 응답(finish_reason=MAX_TOKENS)을 ready로 표시하지
#   않는다. 같은 자료로도 결과가 달라지므로 새 버전으로 확인해야 한다.
# - 5: 검색 기반 AI 조사 요약(search_ai_summary)을 작성 입력으로 받고, 요약의 근거 주소·
#   미확인 표시를 함께 전달한다. 조사 요약이 기사 원문이 아님을 프롬프트가 지시한다.
# - 6: 자료 우선순위(수집 본문 → 검색 자료 → DB)를 프롬프트에 명시하고, 요약의 인용 주소가
#   검색 도구가 반환한 주소인지 모델이 제시한 주소인지 구분해 전달한다.
# - 7: 응답 **수용 기준**을 바꿨다(2026-11-12). 잘린 응답(MAX_TOKENS)·JSON 파싱 실패는
#   같은 모듈의 남은 횟수 안에서 다시 보내고, 짧아도 파싱되는 본문은 그대로 쓴다. 어떤
#   응답이 본문이 되는지가 달라지므로 결과 의미가 바뀐다 → 새 버전으로 확인한다.
#
# 주의: 이 상수는 **다섯 섹션 전체**의 축이다. 배당 공급 경로처럼 한 섹션만의 변경은
# 여기서 올리지 않고 그 섹션이 소유한 별도 축으로 기록한다
# (`provider_odds.PROVIDER_ODDS_IMPLEMENTATION_VERSION`, `version_manifest._compose_manifest`).
# 여기서 올리면 관계없는 네 섹션의 승인 버전까지 바뀌어 불필요한 재승인을 만든다.
IMPLEMENTATION_VERSION = "mp11-bundle-sections-7"
# NS-02 선수/부상 섹션 전용 구현 버전 축(outlook·odds·ai_forecast의 승인 버전은 보존한다).
PLAYER_SECTION_IMPLEMENTATION_VERSION = "mp11-bundle-sections-8"

PROMPT_VERSION_PLAYERS = "mp11-bundle-players-prompt-4"
PROMPT_VERSION_AVAILABILITY = "mp11-bundle-availability-prompt-4"
PROMPT_VERSION_OUTLOOK = "mp11-bundle-outlook-prompt-2"
# 프롬프트 버전: 섹션 프롬프트 파일의 지시가 바뀌면 올린다.
# - 4: 최종 전망 프롬프트가 `forecast`·`score_reasoning`의 팀/선수 이름을 Markdown
#   `**이름**`으로 감싸도록 지시한다(굵게 표시 전용). JSON 문자열 스키마·수치·근거 id는
#   그대로이고, 사실·선정·품질 정책은 바꾸지 않는다. 출력 형식이 달라지므로 새 버전이다.
PROMPT_VERSION_FORECAST = "mp11-bundle-forecast-prompt-4"
# 배당은 프롬프트가 없다(모델 호출 0회). 승인 축에는 "모델 없음"을 남긴다.
PROMPT_VERSION_ODDS = "mp11-bundle-odds-no-model-1"

_PLAYER_SECTION_IDS = frozenset(
    {bundle_contract.SECTION_PLAYERS, bundle_contract.SECTION_AVAILABILITY}
)


def implementation_version_for(section_id: str) -> str:
    """섹션 ID별 구현 버전을 돌려준다(선수·부상 섹션 변경을 다른 섹션에 번지지 않는다)."""
    if section_id in _PLAYER_SECTION_IDS:
        return PLAYER_SECTION_IMPLEMENTATION_VERSION
    return IMPLEMENTATION_VERSION

# 작성 3회 + 최종 1회. 배당은 이 표에 없다(모델 호출 없음).
_LOGICAL_CALL_IDS: Mapping[str, str] = {
    bundle_contract.SECTION_PLAYERS: "section_players",
    bundle_contract.SECTION_AVAILABILITY: "section_availability",
    bundle_contract.SECTION_OUTLOOK: "section_outlook",
    bundle_contract.SECTION_AI_FORECAST: "section_ai_forecast",
}
# 모든 섹션의 논리 호출 id. 배당은 모델 호출이 없으므로 값이 `None`이다.
LOGICAL_CALL_IDS: Mapping[str, str | None] = {
    **dict(_LOGICAL_CALL_IDS),
    bundle_contract.SECTION_ODDS: None,
}

SUPPORTED_SECTION_IDS: tuple[str, ...] = tuple(LOGICAL_CALL_IDS)

_PROMPTS: Mapping[str, tuple[str, str]] = {
    bundle_contract.SECTION_PLAYERS: ("bundle_players.md", PROMPT_VERSION_PLAYERS),
    bundle_contract.SECTION_AVAILABILITY: (
        "bundle_availability.md",
        PROMPT_VERSION_AVAILABILITY,
    ),
    bundle_contract.SECTION_OUTLOOK: ("bundle_outlook.md", PROMPT_VERSION_OUTLOOK),
    bundle_contract.SECTION_AI_FORECAST: ("bundle_forecast.md", PROMPT_VERSION_FORECAST),
    bundle_contract.SECTION_ODDS: ("", PROMPT_VERSION_ODDS),
}

# A가 워크플로우 버전 축에 연결할 표: 섹션 → (구현 버전, 프롬프트 버전).
BUNDLE_SECTION_VERSIONS: Mapping[str, tuple[str, str]] = {
    section_id: (implementation_version_for(section_id), prompt_version)
    for section_id, (_file, prompt_version) in _PROMPTS.items()
}

# 같은 값을 옛 모듈 축 이름으로도 읽을 수 있게 둔다(등록부 module_id 기준).
BUNDLE_MODULE_VERSIONS: Mapping[str, tuple[str, str]] = {
    "R4": BUNDLE_SECTION_VERSIONS[bundle_contract.SECTION_PLAYERS],
    "R2": BUNDLE_SECTION_VERSIONS[bundle_contract.SECTION_AVAILABILITY],
    "R3": BUNDLE_SECTION_VERSIONS[bundle_contract.SECTION_OUTLOOK],
    "S1": BUNDLE_SECTION_VERSIONS[bundle_contract.SECTION_AI_FORECAST],
}

PLAYERS_PER_TEAM = 2
MAX_BUNDLE_PLAYERS = 4
MAX_INJURIES_PER_TEAM = 2
MAX_MEDIA_PUBLISHERS = 3

# 섹션별로 읽는 출처 묶음. 작성이 다른 섹션 자료를 끌어다 쓰지 않게 한다.
_SECTION_GROUPS: Mapping[str, tuple[str, ...]] = {
    bundle_contract.SECTION_PLAYERS: (bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,),
    bundle_contract.SECTION_AVAILABILITY: (
        bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
    ),
    bundle_contract.SECTION_OUTLOOK: (bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,),
    bundle_contract.SECTION_ODDS: (bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,),
    bundle_contract.SECTION_AI_FORECAST: bundle_contract.DISCOVERY_GROUPS,
}

# DB 자료가 없을 때 프롬프트에 넣는 문장. 값을 만들지 않는다는 사실을 모델에 알린다.
_NO_PASSAGE_NOTE = "- 전달할 수집 본문 구간이 없습니다. 아래 DB 자료로만 작성한다."
_NO_DB_NOTE = "- DB 경기 자료가 제공되지 않았습니다. 없는 값을 만들지 않는다."
_NO_EVIDENCE_NOTE = "- 인용 가능한 근거 id가 없습니다. 판단만 쓰고 인용을 만들지 않는다."

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_PROMPT_CACHE: dict[str, str] = {}


class BundleSectionError(ValueError):
    """섹션 작성 입력이 계약을 만족하지 않는다. 값을 만들어 통과시키지 않는다."""


def load_prompt(name: str) -> str:
    """프롬프트 파일 하나를 읽는다. 없으면 예외(빈 프롬프트로 호출하지 않는다)."""
    if name in _PROMPT_CACHE:
        return _PROMPT_CACHE[name]
    path = _PROMPT_DIR / name
    if not path.is_file():
        raise BundleSectionError(f"prompt file {name!r} is missing")
    text = path.read_text(encoding="utf-8")
    _PROMPT_CACHE[name] = text
    return text


def bundle_section_versions(section_id: str) -> tuple[str, str]:
    """(구현 버전, 프롬프트 버전). 모르는 섹션은 예외."""
    try:
        return BUNDLE_SECTION_VERSIONS[section_id]
    except KeyError:
        raise KeyError(f"section {section_id!r} has no bundle implementation") from None


def bundle_module_versions(module_id: str) -> tuple[str, str]:
    """등록부 module_id(R4·R2·R3·S1) 기준 (구현 버전, 프롬프트 버전)."""
    try:
        return BUNDLE_MODULE_VERSIONS[module_id]
    except KeyError:
        raise KeyError(f"module {module_id!r} has no bundle implementation") from None


# --------------------------------------------------------------------------
# 결과 모양 (A가 NodeOutcome/save_section_result로 옮긴다)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SectionDraft:
    """섹션 하나의 작성 결과. 화면에 보일 본문·근거와 관리자 진단을 분리한다."""

    section_id: str
    title: str
    body: str
    sources: tuple[Mapping[str, Any], ...] = ()
    structured: Mapping[str, Any] = field(default_factory=dict)
    quality: QualityStatus = QualityStatus.PENDING
    unavailable_reason: str | None = None
    prompt_version: str | None = None
    implementation_version: str | None = None
    diagnostics: tuple[str, ...] = ()
    # 실제로 요청에 실린 구간·payload 기록(A가 묶음에 그대로 붙인다).
    delivery: bundle_contract.SectionDelivery | None = None
    mode: str = "mock"
    # 이 초안을 만든 실제 모델 전송 수(0이면 무전송).
    external_calls: int = 0
    module_id: str | None = None
    # NS-02 선수/부상 섹션의 타입 보존 처리 결과(정본 저장 입력 구체화용, to_dict 제외).
    player_processing: player_processing.PlayerSectionProcessingBundle | None = None

    def __post_init__(self) -> None:
        if self.implementation_version is None:
            object.__setattr__(
                self, "implementation_version", implementation_version_for(self.section_id)
            )

    @property
    def unavailable(self) -> bool:
        return self.unavailable_reason is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "module_id": self.module_id,
            "title": self.title,
            "body": self.body,
            "sources": [dict(item) for item in self.sources],
            "structured": dict(self.structured),
            "quality": self.quality.value,
            "unavailable_reason": self.unavailable_reason,
            "prompt_version": self.prompt_version,
            "implementation_version": self.implementation_version,
            "diagnostics": list(self.diagnostics),
            "delivery": self.delivery.to_dict() if self.delivery else None,
            "mode": self.mode,
            "external_calls": self.external_calls,
        }

    def as_node_payload(self) -> dict[str, Any]:
        """`runner.NodeOutcome.payload`에 그대로 넣을 수 있는 값."""
        return self.to_dict()


# --------------------------------------------------------------------------
# 묶음 읽기 (객체·저장된 매핑 모두 허용)
# --------------------------------------------------------------------------


def _as_payload(bundle: Any) -> dict[str, Any]:
    """묶음을 사전으로 본다. 저장된 매핑이면 그대로, 객체면 `to_dict()`."""
    if isinstance(bundle, Mapping):
        payload = dict(bundle)
    else:
        to_dict = getattr(bundle, "to_dict", None)
        if not callable(to_dict):
            raise BundleSectionError("bundle must be an InformationBundle or a mapping")
        payload = dict(to_dict())
    # 저장된 옛 모양(출처 목록 대신 후보 구간만 있는 경우)도 읽는다.
    if not payload.get("sources") and payload.get("available_passages"):
        payload["sources"] = _sources_from_passages(payload.get("available_passages") or ())
    return payload


def _sources_from_passages(passages: Sequence[Any]) -> list[dict[str, Any]]:
    """후보 구간 목록만 있는 저장본에서 출처 묶음을 되살린다(값을 만들지 않는다)."""
    grouped: dict[str, dict[str, Any]] = {}
    for item in passages:
        if not isinstance(item, Mapping):
            continue
        source_id = str(item.get("source_id") or "")
        passage_id = str(item.get("passage_id") or "")
        text = str(item.get("text") or "")
        if not source_id or not passage_id or not text.strip():
            continue
        source = grouped.setdefault(
            source_id,
            {
                "source_id": source_id,
                "discovery_group": bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
                "nature": "unknown",
                "method": "unavailable",
                "passages": [],
            },
        )
        source["passages"].append(dict(item))
    return list(grouped.values())


def _canonical_group(value: Any) -> str:
    try:
        return bundle_contract.canonical_discovery_group(str(value or ""))
    except Exception:  # noqa: BLE001 - 모르는 표기는 unknown으로 격리한다
        return "unknown"


def _passage_id(item: Mapping[str, Any]) -> str:
    return str(item.get("passage_id") or "").strip()


def _passages_of(source: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in source.get("passages") or ():
        if not isinstance(item, Mapping):
            continue
        text = str(item.get("text") or "").strip()
        if not text or not _passage_id(item):
            continue
        rows.append(dict(item))
    return rows


def _section_scope(payload: Mapping[str, Any], section_id: str) -> list[dict[str, Any]]:
    """그 섹션이 읽을 수 있는 출처 목록(성공한 출처만)."""
    wanted = set(_SECTION_GROUPS.get(section_id, bundle_contract.DISCOVERY_GROUPS))
    scoped: list[dict[str, Any]] = []
    for source in payload.get("sources") or ():
        if not isinstance(source, Mapping):
            continue
        if source.get("failure"):
            # 실패한 출처는 근거로 쓰지 않는다. 후보 id만 남긴다.
            continue
        if _canonical_group(source.get("discovery_group")) not in wanted:
            continue
        if not _passages_of(source):
            continue
        scoped.append(dict(source))
    return scoped


@dataclass(frozen=True)
class _Selection:
    """섹션 하나에 전달할 구간 선택 결과."""

    passages: tuple[dict[str, Any], ...] = ()
    available_ids: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def passage_ids(self) -> tuple[str, ...]:
        return tuple(_passage_id(item) for item in self.passages)

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(str(item.get("source_id") or "") for item in self.passages))

    @property
    def chars(self) -> int:
        return sum(len(str(item.get("text") or "")) for item in self.passages)


def _select_passages(
    payload: Mapping[str, Any],
    section_id: str,
    *,
    limits: Mapping[str, Any] | None = None,
) -> _Selection:
    """섹션 입력 구간을 상한 안에서 고른다(출처 순서·구간 순서 유지).

    상한(설계 §예산): 섹션당 출처 6개·출처당 구간 3개·구간 1500자·웹 총 16000자.
    후보 전체 id는 `available_ids`로 따로 남겨 "고를 수 있었던 것"과 "실제로 넣은 것"을
    구분한다.
    """
    data = dict(limits or {})
    max_sources = int(data.get("max_sources_per_section", bundle_contract.MAX_SOURCES_PER_SECTION))
    max_passages = int(data.get("max_passages_per_source", bundle_contract.MAX_PASSAGES_PER_SOURCE))
    max_chars = int(data.get("max_passage_chars", bundle_contract.MAX_PASSAGE_CHARS))
    max_web = int(data.get("max_web_section_chars", bundle_contract.MAX_WEB_SECTION_CHARS))

    scoped = _section_scope(payload, section_id)
    available_ids = tuple(
        dict.fromkeys(
            _passage_id(item) for source in scoped for item in _passages_of(source)
        )
    )

    diagnostics: list[str] = []
    chosen: list[dict[str, Any]] = []
    used_chars = 0
    used_sources = 0
    web_full = False
    for source in scoped:
        if used_sources >= max_sources:
            diagnostics.append(
                f"출처 상한({max_sources}개)에 닿아 나머지 출처 구간은 전달하지 않았습니다."
            )
            break
        rows: list[dict[str, Any]] = []
        for item in _passages_of(source)[:max_passages]:
            text = str(item.get("text") or "")
            if len(text) > max_chars:
                text = text[:max_chars]
                diagnostics.append(
                    f"구간 {_passage_id(item)}이 {max_chars}자를 넘어 잘라서 전달했습니다."
                )
            if used_chars + len(text) > max_web:
                diagnostics.append(
                    f"웹 입력 상한({max_web}자)에 닿아 남은 구간은 전달하지 않았습니다."
                )
                web_full = True
                break
            used_chars += len(text)
            rows.append(
                {
                    "passage_id": _passage_id(item),
                    "source_id": str(item.get("source_id") or ""),
                    "ordinal": item.get("ordinal"),
                    "text": text,
                    "heading": item.get("heading"),
                    "url": source.get("final_url") or source.get("requested_url"),
                    "title": source.get("title"),
                    "nature": str(source.get("nature") or "unknown"),
                    "published_at": source.get("published_at") or source.get("captured_at"),
                }
            )
        if rows:
            chosen.extend(rows)
            used_sources += 1
        if web_full:
            break
    return _Selection(
        passages=tuple(chosen),
        available_ids=available_ids,
        diagnostics=tuple(diagnostics),
    )


def _render_passages(passages: Sequence[Mapping[str, Any]]) -> str:
    """프롬프트에 넣는 구간 블록. 구간 id를 그대로 적어 인용 근거로 쓴다."""
    if not passages:
        return _NO_PASSAGE_NOTE
    blocks: list[str] = []
    for item in passages:
        head = f"[{item['passage_id']}]"
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        meta = " · ".join(part for part in (title, url) if part)
        if meta:
            head += f" {meta}"
        nature = str(item.get("nature") or "")
        if nature and nature != "unknown":
            head += f" ({nature})"
        blocks.append(f"{head}\n{str(item.get('text') or '').strip()}")
    return "\n\n".join(blocks)


_SEARCH_SCOPE_NOTE = (
    "- 검색 도구가 반환한 자료가 없습니다. 검색 결과를 추정해 쓰지 않는다."
)


@dataclass(frozen=True)
class _SearchMaterial:
    """섹션 하나에 전달할 검색 자료 묶음.

    자료 유형(`material_type`)마다 **다른 이름**으로 보여준다. 검색 도구가 반환한
    요약문이 없는데 모델 산문을 스니펫이라고 부르지 않기 위해, 각 줄에 라벨을 붙이고
    `finding_id`를 인용 근거로 쓸 수 있게 한다.
    """

    rows: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()

    @property
    def finding_ids(self) -> tuple[str, ...]:
        return tuple(str(item.get("finding_id") or "") for item in self.rows)

    @property
    def has_snippet(self) -> bool:
        return any(item.get("material_type") == "search_snippet" for item in self.rows)

    @property
    def chars(self) -> int:
        return sum(len(str(item.get("content") or "")) for item in self.rows)


def _search_material(
    payload: Mapping[str, Any],
    section_id: str,
    *,
    limits: Mapping[str, Any] | None = None,
) -> _SearchMaterial:
    """그 섹션이 읽을 수 있는 검색 자료를 상한 안에서 고른다.

    - 섹션의 조사 그룹 범위만 본다(`_SECTION_GROUPS`). 다른 섹션 자료를 끌어오지 않는다.
    - `deliverable=False`(모델이 쓴 페이지 설명 등)는 전달하지 않는다.
    - 섹션당 최대 `MAX_SEARCH_FINDINGS_PER_SECTION`줄, 줄당 `MAX_SEARCH_FINDING_CHARS`자,
      전체 `MAX_SEARCH_MATERIAL_CHARS`자를 넘기지 않는다.
    """
    data = dict(limits or {})
    max_rows = int(
        data.get("max_search_findings_per_section", bundle_contract.MAX_SEARCH_FINDINGS_PER_SECTION)
    )
    max_chars_each = int(
        data.get("max_search_finding_chars", bundle_contract.MAX_SEARCH_FINDING_CHARS)
    )
    max_total = int(
        data.get("max_search_material_chars", bundle_contract.MAX_SEARCH_MATERIAL_CHARS)
    )
    wanted = set(_SECTION_GROUPS.get(section_id, bundle_contract.DISCOVERY_GROUPS))
    rows: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    used = 0
    # **내용이 있는 줄을 먼저** 넣는다. 주소만 있는 출처 메타가 상한을 다 차지하면, 실제
    # 내용이 있는 인용 문장이 빠져 작성 근거가 비어 버린다(원래 순서는 그 안에서 유지).
    # 우선순위: 기사 본문 대체로 가장 쓸모 있는 검색 AI 요약 → 내용 있는 다른 줄 →
    # 주소만 있는 메타/한 줄 메모. 같은 순위 안에서는 저장 순서를 유지한다(안정 정렬).
    priority = {
        "search_ai_summary": 0,
        "model_cited_span": 1,
        "search_snippet": 1,
    }
    def _rank(row: Mapping[str, Any]) -> tuple[int, int]:
        material = str(row.get("material_type") or "")
        has_content = bool(str(row.get("content") or "").strip())
        if not has_content:
            return (4, 0)
        base = priority.get(material, 3)
        # 같은 유형 안에서는 **근거 주소가 있는 요약을 먼저** 넣는다. 주소 없는 요약은
        # 남는 자리에 넣고 라벨에서 "근거 주소 없음"을 함께 밝힌다.
        has_source = bool(row.get("sources") or row.get("url"))
        return (base, 0 if has_source else 1)

    ordered = sorted(
        (row for row in payload.get("search_findings") or () if isinstance(row, Mapping)),
        key=_rank,
    )
    for raw in ordered:
        if not isinstance(raw, Mapping):
            continue
        # `deliverable`이 저장되지 않은 옛 묶음도 있다. 그때는 자료 유형으로 직접 판정한다
        # (모델 산문은 전달하지 않고, 주소만 있는 메타는 "내용 없음"으로 표시해 전달한다).
        deliverable = raw.get("deliverable")
        if deliverable is None:
            material_type = str(raw.get("material_type") or "")
            if material_type not in bundle_contract.SEARCH_MATERIAL_DELIVERABLE:
                continue
            if material_type == "search_source_meta":
                deliverable = bool(raw.get("url") or raw.get("title"))
            else:
                deliverable = bool(str(raw.get("content") or "").strip())
        if not deliverable:
            continue
        if _canonical_group(raw.get("discovery_group")) not in wanted:
            continue
        if len(rows) >= max_rows:
            diagnostics.append(
                f"검색 자료 상한({max_rows}건)에 닿아 남은 줄은 전달하지 않았습니다."
            )
            break
        content = str(raw.get("content") or "").strip()
        if not content and not (raw.get("url") or raw.get("title")):
            # 내용도 주소도 없으면 근거로 쓸 것이 없다. 빈 줄을 만들지 않는다.
            continue
        # 긴 요약은 **원문을 보존한 채** 전달분만 줄인다. 이 줄이 잘렸다는 사실은
        # 관리자 진단과 프롬프트 라벨에 표시하고, 독자 본문에는 넣지 않는다.
        excerpted = False
        if len(content) > max_chars_each:
            content, excerpted = bundle_contract.excerpt_for_delivery(
                content, limit=max_chars_each
            )
            diagnostics.append(
                f"검색 자료 {raw.get('finding_id')} 원문 {len(str(raw.get('content') or ''))}자 중"
                f" {len(content)}자만 전달했습니다(원문은 묶음에 그대로 보존)."
            )
        if used + len(content) > max_total:
            diagnostics.append(
                f"검색 자료 전체 상한({max_total}자)에 닿아 남은 줄은 전달하지 않았습니다."
            )
            break
        used += len(content)
        material_type = str(raw.get("material_type") or "")
        rows.append(
            {
                "finding_id": str(raw.get("finding_id") or ""),
                "material_type": material_type,
                "label": str(
                    raw.get("label")
                    or bundle_contract.SEARCH_MATERIAL_LABELS.get(material_type, "자료 유형 미확인")
                ),
                "title": raw.get("title"),
                "url": raw.get("url"),
                "domain": raw.get("domain"),
                "content": content,
                "captured_at": raw.get("captured_at"),
                # 요약이 인용한 주소들. 기사 본문이 아니라 "어디를 보고 쓴 요약인지"다.
                "sources": [str(item) for item in raw.get("sources") or ()],
                "unverified": bool(raw.get("unverified")),
                # 이 줄이 원문 일부만 전달된 발췌인지. 관리자·프롬프트 표시용이다.
                "excerpted": excerpted,
                "original_chars": len(str(raw.get("content") or "")),
                # 주소 출처(도구 반환 vs 모델 제시). 프롬프트에 라벨로 함께 적는다.
                "url_provenance": str(raw.get("url_provenance") or "none"),
            }
        )
    return _SearchMaterial(rows=tuple(rows), diagnostics=tuple(diagnostics))


def _render_search_material(material: _SearchMaterial) -> str:
    """검색 자료 블록. **자료 유형 라벨을 그대로** 적어 모델이 무엇을 읽는지 알게 한다."""
    if not material.rows:
        return _SEARCH_SCOPE_NOTE
    blocks: list[str] = []
    for item in material.rows:
        head = f"[{item['finding_id']}] {item['label']}"
        extra = " · ".join(
            part
            for part in (
                str(item.get("domain") or "").strip(),
                str(item.get("title") or "").strip(),
            )
            if part
        )
        if extra:
            head += f" · {extra}"
        if item.get("unverified"):
            head += " · (모델이 확인 불충분으로 표시)"
        url = str(item.get("url") or "").strip()
        sources = [str(one) for one in item.get("sources") or () if str(one).strip()]
        # 링크용 `url`과 겹치는 주소는 한 번만 적는다(같은 주소 중복 금지).
        extra_sources = [one for one in sources if one != url]
        if extra_sources:
            head += " · 근거 주소: " + ", ".join(extra_sources)
        if item.get("excerpted"):
            head += " · (원문 일부 발췌 — 전체는 저장된 원문 참조)"
        provenance = str(item.get("url_provenance") or "none")
        if url:
            head += f"\n{url}"
            label = bundle_contract.SEARCH_URL_PROVENANCE_LABELS.get(provenance)
            if label and provenance != "grounding_chunk":
                # 검색 도구가 반환한 주소가 아니면 그 사실을 함께 적는다(위장 금지).
                head += f" · ({label})"
        elif item["material_type"] == "search_ai_summary":
            # 요약인데 인용 주소가 없다. 그 사실을 숨기지 않고 프롬프트에 함께 적는다.
            head += " · 근거 주소 없음"
        body = str(item.get("content") or "").strip()
        if not body:
            # 내용 없이 주소만 반환된 줄. 기사 내용 자리를 채우지 않는다는 점을 명시한다.
            body = "(주소만 반환됨 — 기사 내용은 이 자료에 없음)"
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def _evidence_lines(passage_ids: Sequence[str], db_ids: Sequence[str]) -> str:
    lines = [f"- `{passage_id}`" for passage_id in passage_ids]
    lines.extend(f"- `{db_id}`" for db_id in db_ids)
    return "\n".join(lines) or _NO_EVIDENCE_NOTE


# --------------------------------------------------------------------------
# DB 자료 → 프롬프트 줄 (없는 값은 만들지 않는다)
# --------------------------------------------------------------------------

_STANDING_KEYS = ("rank", "position", "points", "played", "goals_diff")
_RECENT_KEYS = ("date", "kickoff_at", "opponent", "opponent_name", "home_away", "score", "result")
# D0의 부상 행은 `expected_status` 키를 쓴다(레거시 R2 표기와 같은 값). 이 키를 빼면
# 부상 행이 1건 있어도 인용 가능한 사실이 0건이 된다(검토 F1).
_INJURY_KEYS = (
    "expected_status",
    "status",
    "type",
    "type_marker",
    "injury",
    "reason",
    "detail",
    "expected_return",
)
# D0이 순위 사실을 **완성된 문장**으로 `text`에 담는다(`sections._standings_facts`).
# 이 값을 구조 키로 다시 쪼개지 않고 그대로 프롬프트에 쓴다.
_TEXT_KEYS = ("text", "sentence", "statement")


def _db_snapshot(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = payload.get("db_snapshot")
    return snapshot if isinstance(snapshot, Mapping) else {}


def _team_names(snapshot: Mapping[str, Any]) -> dict[int, str]:
    """DB가 준 팀 한국어 이름만 쓴다. 없으면 비운다."""
    names: dict[int, str] = {}
    for row in snapshot.get("teams") or ():
        if not isinstance(row, Mapping):
            continue
        team_id = row.get("team_id")
        name = row.get("name_ko") or row.get("team_name") or row.get("name")
        if isinstance(team_id, int) and isinstance(name, str) and name.strip():
            names[team_id] = name.strip()
    return names


def _team_label(team_id: Any, names: Mapping[int, str]) -> str | None:
    if isinstance(team_id, int) and team_id in names:
        return names[team_id]
    return None


@dataclass(frozen=True)
class _DbMaterial:
    lines: tuple[str, ...] = ()
    ids: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    teams: Mapping[int, str] = field(default_factory=dict)
    roster: tuple[Mapping[str, Any], ...] = ()
    injuries: tuple[Mapping[str, Any], ...] = ()
    # 부상 행 중 **실제 근거 줄로 옮긴** 사실 id와 그 줄. 행이 있어도 직렬화한 값이 없으면
    # 비어 있다(그때 "전달했습니다"라고 쓰지 않는다).
    injury_ids: tuple[str, ...] = ()
    injury_lines: tuple[str, ...] = ()
    readable: bool = False

    @property
    def has_material(self) -> bool:
        return bool(self.lines) or bool(self.roster)


def _row_line(prefix: str, row: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    parts: list[str] = []
    for key in keys:
        value = row.get(key)
        if value in (None, "", []):
            continue
        parts.append(f"{key}={value}")
    return f"{prefix}: " + ", ".join(parts) if parts else None


def _row_text(row: Mapping[str, Any]) -> str | None:
    """D0이 이미 완성한 사실 문장. 있으면 쪼개지 않고 그대로 쓴다."""
    for key in _TEXT_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolver_player_name(player_id: Any, resolver: Any) -> str | None:
    """신뢰 ID(저장 DB에서 읽은 값)로 DB 한국어 이름을 확인한다.

    이 함수는 **주입된 해석기만** 쓴다(여기서 DB를 조회하지 않는다). ID가 확인되지
    않으면 `None`이며, 호출자는 이름을 지어내지 않는다.
    """
    if not isinstance(player_id, int) or resolver is None:
        return None
    resolve = getattr(resolver, "resolve_player", None)
    if not callable(resolve):
        return None
    try:
        resolved = resolve(
            "",
            player_id=player_id,
            id_space="internal",
            # 저장 DB에서 읽은 값이므로 모델이 적은 힌트가 아니다.
            id_is_hint=False,
        )
    except Exception:  # noqa: BLE001 - 이름 확인 실패로 근거 줄을 없애지 않는다
        return None
    display = getattr(resolved, "display_name", None)
    if isinstance(display, str) and display.strip():
        return display.strip()
    return None


def _db_material(payload: Mapping[str, Any], *, resolver: Any = None) -> _DbMaterial:
    """DB 스냅샷의 행을 인용 가능한 사실 줄로 옮긴다.

    실제 D0 행 모양을 그대로 읽는다. 순위·최근 경기는 `text`, 부상은 `expected_status`를
    쓴다. 행 모양을 모르면 **그 행을 건너뛰고 사유만 센다**(임의 필드를 사실처럼 쓰지
    않는다). 부상 선수 이름이 `None`이면 이름을 만들지 않고, 저장 DB에서 읽은
    `player_id`와 주입된 해석기가 있을 때만 그 DB 이름을 쓴다.
    `api:` id는 이 함수가 만든 결정적 행 참조이며, 프롬프트의 인용 목록과 같은 값이다.
    """
    snapshot = _db_snapshot(payload)
    if not snapshot:
        return _DbMaterial(diagnostics=("정보 원문 묶음에 DB 스냅샷이 없습니다.",))
    names = _team_names(snapshot)
    lines: list[str] = []
    ids: list[str] = []
    diagnostics: list[str] = []
    skipped = 0

    for row in snapshot.get("standings") or ():
        if not isinstance(row, Mapping):
            continue
        text = _row_text(row)
        line = _row_line("리그 순위", row, _STANDING_KEYS)
        team = _team_label(row.get("team_id"), names)
        body = text or line
        if body is None and not team:
            skipped += 1
            continue
        fact_id = f"api:standings-{row.get('team_id') or 'unknown'}"
        # `text`는 팀 이름까지 담은 완성 문장이다. 팀 라벨을 다시 붙이지 않는다.
        if text is not None:
            lines.append(f"- {fact_id}: {text}")
        else:
            lines.append(f"- {fact_id}: {(team + ' — ') if team else ''}{line or '순위 값 없음'}")
        ids.append(fact_id)

    for index, row in enumerate(snapshot.get("recent_matches") or (), start=1):
        if not isinstance(row, Mapping):
            continue
        text = _row_text(row)
        line = _row_line("최근 경기", row, _RECENT_KEYS)
        if text is None and line is None:
            skipped += 1
            continue
        fact_id = f"api:recent-{index}"
        lines.append(f"- {fact_id}: {text or line}")
        ids.append(fact_id)

    injury_ids: list[str] = []
    injury_lines: list[str] = []
    for index, row in enumerate(snapshot.get("injuries") or (), start=1):
        if not isinstance(row, Mapping):
            continue
        player_id = row.get("player_id")
        name = (
            row.get("player_name")
            or row.get("display_name")
            or row.get("name")
            or _resolver_player_name(player_id, resolver)
        )
        # id가 없으면 순번으로 구분한다. 없는 선수 id를 지어내지 않는다.
        fact_id = (
            f"api:injury-{player_id}"
            if player_id is not None
            else f"api:injury-row{index}"
        )
        detail = _row_line("부상", row, _INJURY_KEYS)
        if not name and detail is None:
            skipped += 1
            continue
        team = _team_label(row.get("team_id"), names)
        head = " · ".join(part for part in (str(name or ""), team or "") if part)
        injury_line = f"- {fact_id}: {head}{' — ' if head else ''}{detail or '상세 없음'}"
        lines.append(injury_line)
        ids.append(fact_id)
        injury_ids.append(fact_id)
        injury_lines.append(injury_line)

    roster = tuple(
        dict(row) for row in snapshot.get("roster") or () if isinstance(row, Mapping)
    )
    if skipped:
        diagnostics.append(
            f"DB 행 {skipped}건은 필요한 열을 찾지 못해 근거 줄로 만들지 않았습니다."
        )
    if not snapshot.get("readable"):
        diagnostics.append("DB 스냅샷이 읽기 불가로 표시되어 있습니다(자료 없음과 다름).")
    return _DbMaterial(
        lines=tuple(lines),
        ids=tuple(dict.fromkeys(ids)),
        diagnostics=tuple(diagnostics),
        teams=names,
        roster=roster,
        injuries=tuple(
            dict(row) for row in snapshot.get("injuries") or () if isinstance(row, Mapping)
        ),
        injury_ids=tuple(injury_ids),
        injury_lines=tuple(injury_lines),
        readable=bool(snapshot.get("readable")),
    )


def _db_block(material: _DbMaterial, *, limit: int = 24) -> str:
    if not material.lines:
        return _NO_DB_NOTE
    lines = list(material.lines[:limit])
    if len(material.lines) > limit:
        lines.append(f"- (DB 근거 줄이 {len(material.lines) - limit}건 더 있으나 상한까지만 넣었습니다.)")
    return "\n".join(lines)


# 선수 통계 행에서 후보 줄에 함께 적는 **기록 값**. 없는 값은 생략하고 0으로 채우지 않는다.
_ROSTER_STAT_KEYS = (
    ("출전", "appearances"),
    ("분", "minutes"),
    ("골", "goals"),
    ("도움", "assists"),
    ("평점", "rating"),
)
# 통계 조회기가 실제로 쓰는 한국어 이름 키. `display_name`·`name_ko`가 아니다(검토 F2).
_ROSTER_NAME_KEYS = ("display_name_ko", "display_name", "name_ko", "english_name")


def _roster_name(
    row: Mapping[str, Any],
    *,
    resolver: Any,
) -> str | None:
    """후보의 표시 이름. 저장된 이름 → (없으면) 신뢰 ID로 주입된 해석기 조회 순서.

    저장 DB에서 읽은 `player_id`만 해석기에 넘긴다(모델이 적은 값이 아니다).
    둘 다 없으면 `None`이며 이름을 만들지 않는다.
    """
    for key in _ROSTER_NAME_KEYS:
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return _resolver_player_name(row.get("player_id"), resolver)


def _roster_lines(
    roster: Sequence[Mapping[str, Any]],
    *,
    names: Mapping[int, str] | None = None,
    resolver: Any = None,
) -> str:
    """프롬프트에 넣는 선수 후보. 이름이 확인된 행과 **실제 기록 값**만 적는다.

    이름이 없으면 그 행은 후보 줄로 만들지 않는다(이름을 지어내지 않는다). 대신 몇 행이
    이름 없이 남았는지 밝혀, 읽은 행 수와 후보 수를 혼동하지 않게 한다.
    """
    team_names = names or {}
    lines: list[str] = []
    unnamed = 0
    for row in roster:
        name = _roster_name(row, resolver=resolver)
        if not name:
            unnamed += 1
            continue
        team_id = row.get("team_id")
        team = _team_label(team_id, team_names) or ""
        label = f"- {name}"
        if team:
            label += f" ({team})"
        player_id = row.get("player_id")
        if isinstance(player_id, int) and not isinstance(player_id, bool):
            label += f" [player_ref={player_id}]"
        stats: list[str] = []
        if isinstance(row.get("position"), str) and row["position"].strip():
            stats.append(f"포지션={row['position'].strip()}")
        for text, key in _ROSTER_STAT_KEYS:
            value = row.get(key)
            if value is None or isinstance(value, bool):
                continue
            stats.append(f"{text}={value}")
        if stats:
            label += " " + ", ".join(stats)
        lines.append(label)
    body = "\n".join(lines)
    if not roster:
        return "- 제공된 선수 후보 목록이 없습니다. 자료에 적힌 표기만 쓴다."
    if not body:
        return (
            f"- 선수 통계 {len(roster)}행을 읽었으나 이름이 확인된 후보가 없습니다."
            " 이름을 만들지 않는다."
        )
    if unnamed:
        return body + f"\n- (이름이 확인되지 않은 통계 {unnamed}행은 후보로 쓰지 않았습니다.)"
    return body


def _db_injury_block(material: _DbMaterial) -> str:
    """부상 프롬프트에 넣는 DB 근거 줄. **실제로 직렬화한 부상 사실만** 적는다."""
    if material.injury_lines:
        return "\n".join(material.injury_lines)
    if material.injuries:
        return (
            "- 저장된 부상 행은 있으나 근거로 쓸 값이 직렬화되지 않아 전달할 사실이"
            " 없습니다. 부상 사실을 단정하지 않는다."
        )
    return _NO_DB_NOTE


def _injury_state(material: _DbMaterial) -> tuple[str, str]:
    """부상 자료 상태 문장. **실제로 전달한 사실 건수**로 계산한다(검토 F1)."""
    if material.injury_ids:
        return "available", f"저장된 부상 사실 {len(material.injury_ids)}건을 전달했습니다."
    if material.injuries:
        return (
            "available",
            f"저장된 부상 행 {len(material.injuries)}건이 있으나 근거로 쓸 값이"
            " 직렬화되지 않았습니다. 전달된 부상 사실은 0건이다.",
        )
    if material.readable:
        return (
            "empty_response",
            "DB 부상 행이 0건입니다. '부상자 없음'의 증거가 아니므로 부상이 없다고 쓰지 않는다.",
        )
    return "not_run", "부상 자료를 읽지 못했습니다. 부상자 유무를 단정하지 않는다."


# --------------------------------------------------------------------------
# 프롬프트 렌더링
# --------------------------------------------------------------------------


def _render(template: str, values: Mapping[str, Any]) -> str:
    text = template
    for key, value in values.items():
        text = text.replace("{" + key + "}", str(value))
    leftovers = sorted(set(_PLACEHOLDER.findall(text)))
    if leftovers:
        raise BundleSectionError(
            "prompt placeholders left unfilled: " + ", ".join(leftovers)
        )
    return text


def _fixture_values(payload: Mapping[str, Any], fixture_names: Mapping[str, Any] | None) -> dict[str, str]:
    fixture = payload.get("fixture") if isinstance(payload.get("fixture"), Mapping) else {}
    snapshot = _db_snapshot(payload)
    names = _team_names(snapshot)
    extra = dict(fixture_names or {})

    def team(value: Any, team_id: Any) -> str:
        label = extra.get(value) if isinstance(value, str) else None
        if isinstance(label, str) and label.strip():
            return label.strip()
        known = _team_label(team_id, names)
        if known:
            return known
        return f"team {team_id}" if team_id is not None else "팀 미확인"

    home_id = fixture.get("home_team_id")
    away_id = fixture.get("away_team_id")
    home = team("home_team", home_id)
    away = team("away_team", away_id)
    league = extra.get("league")
    return {
        "fixture_label": (
            f"{home} vs {away}"
            + (f" ({league})" if isinstance(league, str) and league.strip() else "")
        ),
        "fixture_id": str(fixture.get("fixture_id", "미확인")),
        "league_id": str(fixture.get("league_id", "미확인")),
        "season": str(fixture.get("season", "미확인")),
        "kickoff_at": str(fixture.get("kickoff_at") or "미확인"),
        "home_team": home,
        "home_team_id": str(home_id if home_id is not None else "미확인"),
        "away_team": away,
        "away_team_id": str(away_id if away_id is not None else "미확인"),
    }


def _today(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


# --------------------------------------------------------------------------
# 모델 호출 (provider 하나만 통과, 검색 도구 없음)
# --------------------------------------------------------------------------


def build_generation_config() -> dict[str, Any]:
    """작성 요청 설정. **검색 도구를 넣지 않는다**(조사는 앞 단계의 몫이다)."""
    return {
        "temperature": 0.2,
        # 2048에서는 추론(thoughts) 토큰이 출력 예산을 대부분 소비해 JSON이 절단됐다
        # (실측: thoughts 1964 + candidates 68 = 2032). 사용자 지시로 40000으로 올린다.
        # 이 값은 **출력 토큰 상한**이며 모델 호출 횟수 상한과 무관하다.
        "max_output_tokens": 40000,
        "response_mime_type": "application/json",
    }


def _contents(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": prompt}]}]


@dataclass(frozen=True)
class _Call:
    text: str | None
    result: Any
    contents: Sequence[Mapping[str, Any]]
    attempts: int


def _content_accepts_for(
    section_id: str,
    *,
    label: str,
    parse: Callable[[str | None], object],
) -> provider.ContentCheck:
    """이 섹션 응답의 **내용 수용 기준**. 기술 성공과 구분해 다시 보낼지 판단한다.

    다시 보내는 조건은 두 가지뿐이다(사용자 확정 2026-11-12).

    1. 응답이 출력 상한에서 잘렸다(`finishReason=MAX_TOKENS`).
    2. 받은 본문을 그 섹션 파서로 읽을 수 없다(JSON 파싱 실패).

    글의 길이·내용·근거 수는 여기서 판단하지 않는다. 짧아도 파싱되는 본문은 그대로
    수용하고, 좋고 나쁨은 사용자가 본문을 보고 정한다.
    """

    def accepts(text: str | None, raw_response: Any) -> str | None:
        truncated = provider.rejection_of_truncated_or_unparseable(
            label=label,
            finish_reason=provider.extract_finish_reason(raw_response),
            text=text,
        )
        if truncated:
            return truncated
        if not text:
            # 빈 본문은 파싱 이전의 실패다. 재전송으로 해결될 수 있으므로 같은 판정에 넣는다.
            return f"{label} 응답 본문이 비어 있습니다. 다시 보냅니다."
        if parse(text) is None:
            return (
                f"{label} 응답을 JSON으로 해석하지 못했습니다."
                " 같은 모듈의 남은 횟수 안에서 다시 보냅니다."
            )
        return None

    return provider.ContentCheck(accepts=accepts, label=label)


def _media_parse_or_none(text: str | None) -> object | None:
    """매체 전망 응답을 JSON으로 읽는다. 실패하면 `None`(사유는 호출자가 진단에 남김)."""
    rows, reason = outlook_module.parse_media_response(text)
    return None if reason else rows


def _forecast_parse_or_none(text: str | None) -> object | None:
    """최종 전망 응답을 JSON으로 읽는다. 실패하면 `None`(빈 dict로 꾸미지 않는다)."""
    try:
        return synthesis_module.parse_model_json(text or "")
    except synthesis_module.SynthesisFormatError:
        return None


def _call_model(
    *,
    section_id: str,
    prompt: str,
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    module_id: str,
    prompt_version: str,
    now: datetime | None,
    content_check: provider.ContentCheck | None = None,
    starting_ordinal: int = 0,
    sleeper: "Callable[[float], None] | None" = None,
) -> _Call:
    logical_call_id = LOGICAL_CALL_IDS[section_id]
    if logical_call_id is None:  # pragma: no cover - 배당은 이 함수를 부르지 않는다
        raise BundleSectionError(f"section {section_id!r} must not call the model")
    moment = now or datetime.now(timezone.utc)
    contents = _contents(prompt)
    result = provider.request_model(
        logical_call_id=logical_call_id,
        contents=contents,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=module_id,
        operation=f"build_{section_id}",
        prompt_version=prompt_version,
        generation_config=build_generation_config(),
        module_execution_id=getattr(context, "module_execution_id", None),
        actor_id=getattr(context, "actor_id", None),
        now=lambda: moment,
        # 예산·기한 판정은 위 `now`(실행 기준시각)를 그대로 쓰고, attempt·장부에 남는
        # **실제 호출/응답 시각**만 이 시계로 기록한다. 모든 시도가 같은 시각으로
        # 남던 결함만 고치고 예산 판정의 시간축은 바꾸지 않는다.
        timestamp_clock=_wall_clock,
        content_check=content_check,
        starting_ordinal=starting_ordinal,
        sleeper=sleeper,
    )
    return _Call(
        text=result.text if result.ok else None,
        result=result,
        contents=contents,
        attempts=provider.sent_attempt_count(result, transport.mode),
    )


def _wall_clock() -> datetime:
    """현재 UTC 시각. attempt·장부 기록용(내용 기준시각과 분리)."""
    return datetime.now(timezone.utc)


def _mode_value(transport: provider.ProviderTransport) -> str:
    mode = getattr(transport, "mode", RunMode.MOCK)
    return mode.value if isinstance(mode, RunMode) else str(mode)


# 응답이 잘렸다고 판정하는 종료 사유. 이 값이면 본문을 ready로 표시하지 않는다.
_TRUNCATING_FINISH_REASONS = ("MAX_TOKENS", "MAX_OUTPUT_TOKENS")


def _finish_reason(call: _Call) -> str | None:
    return provider.extract_finish_reason(getattr(call.result, "raw_response", None))


def _truncation_reason(call: _Call, *, label: str) -> str | None:
    """응답이 잘려 JSON이 완성되지 않은 경우의 사유. 아니면 `None`.

    빈 본문·잘린 JSON을 `ready`로 위장하지 않기 위한 검사다. 종료 사유가
    MAX_TOKENS이면 잘린 것으로 판정하고, 종료 사유가 없더라도 JSON이 닫히지 않았으면
    같은 사유로 남긴다(추정으로 성공 처리하지 않는다).
    """
    reason = _finish_reason(call)
    if reason and reason.upper() in _TRUNCATING_FINISH_REASONS:
        return (
            f"{label} 응답이 출력 상한에서 잘렸습니다(finish_reason={reason})."
            " 잘린 JSON을 본문으로 쓰지 않습니다."
        )
    text = (call.text or "").strip()
    if text and not (text.endswith("}") or text.endswith("```")):
        return (
            f"{label} 응답 JSON이 닫히지 않았습니다(잘린 응답으로 판단)."
            " 잘린 JSON을 본문으로 쓰지 않습니다."
        )
    return None


def _failure_reason(call: _Call, *, label: str) -> str:
    result = call.result
    return result.stopped_reason or (
        getattr(result.response, "error_message", None) or f"{label} 모델 호출이 성공하지 않았습니다."
    )


# --------------------------------------------------------------------------
# 이름 해석 (주입식 — 해석기가 없으면 원래 표기를 유지한다)
# --------------------------------------------------------------------------


def _resolve_player_rows(
    items: Sequence[Mapping[str, Any]],
    *,
    resolver: Any,
    scope_team_ids: Sequence[int],
) -> tuple[list[dict[str, Any]], list[Mapping[str, Any]]]:
    """기존 R4 이름 해석기를 그대로 쓴다.

    모델이 응답에 적은 `player_ref`는 **검증되지 않은 참조**이므로 `id_is_hint=True`로
    넘긴다(숫자가 틀렸다고 확인된 한국어 이름을 포기하지 않는다).
    """
    return players_module.resolve_selection_names(
        items,
        resolver=resolver,
        name_map=None,
        scope_team_ids=list(scope_team_ids) or None,
        id_space="internal",
        id_is_hint=True,
    )


def _team_display(
    *,
    team_id: Any,
    label: Any,
    names: Mapping[int, str],
    resolver: Any,
) -> str | None:
    """팀 표시 이름. DB 한국어 값 → (없으면) 해석기 이름 조회 → 원래 표기 순서."""
    known = _team_label(team_id, names)
    if known:
        return known
    original = label.strip() if isinstance(label, str) and label.strip() else None
    if original and resolver is not None:
        resolve_team = getattr(resolver, "resolve_team", None)
        if callable(resolve_team):
            # 이름만으로 확인한다(다른 팀 id를 추측해 붙이지 않는다).
            resolved = resolve_team(original)
            display = str(getattr(resolved, "display_name", "") or "").strip()
            if display:
                return display
    return original


def _scope_team_ids(fixture_values: Mapping[str, str]) -> tuple[int, ...]:
    """이 경기의 두 팀 내부 id. 이름 확인 범위를 경기 밖으로 넓히지 않는다."""
    ids: list[int] = []
    for key in ("home_team_id", "away_team_id"):
        value = str(fixture_values.get(key) or "").strip()
        if value.isdigit():
            ids.append(int(value))
    return tuple(dict.fromkeys(ids))


# --------------------------------------------------------------------------
# 공통 결과 조립
# --------------------------------------------------------------------------


def _allowed_evidence(selection: _Selection, material: _DbMaterial) -> set[str]:
    return set(selection.passage_ids) | set(material.ids)


def _clean_evidence(values: Any, allowed: set[str]) -> tuple[list[str], int]:
    """인용 id를 실제로 전달한 목록과 대조한다. 목록에 없으면 그 인용만 버린다."""
    kept: list[str] = []
    dropped = 0
    for item in values or ():
        text = str(item or "").strip()
        if not text:
            continue
        if text in allowed:
            if text not in kept:
                kept.append(text)
        else:
            dropped += 1
    return kept, dropped


def _reader_sources(selection: _Selection) -> tuple[Mapping[str, Any], ...]:
    """독자용 근거 목록. 실제로 전달한 수집 출처만 넣는다."""
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for item in selection.passages:
        source_id = str(item.get("source_id") or "")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        rows.append(
            {
                "label": str(item.get("title") or item.get("url") or source_id),
                "url": item.get("url"),
                "kind": "web",
                "note": "브라우저 없이 수집한 기사 본문입니다.",
            }
        )
    return tuple(rows)


def _delivery(
    *,
    section_id: str,
    call: _Call | None,
    selection: _Selection,
    model_delivered: bool,
    prompt_version: str,
    note: str | None = None,
    search_finding_ids: Sequence[str] = (),
    sent_attempts_override: int | None = None,
) -> bundle_contract.SectionDelivery:
    """실제 전달 기록. payload는 그 요청에 넣은 contents 그대로다."""
    payload = {"contents": [dict(item) for item in call.contents]} if call is not None else {}
    sent_attempts = (
        sent_attempts_override
        if sent_attempts_override is not None
        else (call.attempts if call is not None else 0)
    )
    return bundle_contract.build_section_delivery(
        section_id=section_id,
        payload=payload,
        passage_ids=selection.passage_ids if model_delivered else (),
        source_ids=selection.source_ids if model_delivered else (),
        available_passage_ids=selection.available_ids,
        logical_call_id=LOGICAL_CALL_IDS[section_id],
        model_delivered=model_delivered,
        sent_attempts=sent_attempts,
        implementation_version=implementation_version_for(section_id),
        prompt_version=prompt_version,
        note=note,
        # 실제 payload에 들어간 검색 자료 id만 남긴다(자료 유형은 묶음에서 대조).
        search_finding_ids=tuple(search_finding_ids) if model_delivered else (),
    )


# --------------------------------------------------------------------------
# 섹션: 주목 선수 · 부상·결장 공통 생성/재생성 실행기
# --------------------------------------------------------------------------


def _fixture_team_context(
    payload: Mapping[str, Any], fixture_values: Mapping[str, str]
) -> player_processing.FixtureTeamContext:
    fixture = payload.get("fixture") if isinstance(payload.get("fixture"), Mapping) else {}

    def _pos_int(val: Any) -> int | None:
        if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
            return None
        return val

    raw_fid = _pos_int(fixture.get("fixture_id"))
    if raw_fid is None:
        text_fid = str(fixture_values.get("fixture_id") or "")
        raw_fid = int(text_fid) if text_fid.isdigit() and int(text_fid) > 0 else 1

    home_id = _pos_int(fixture.get("home_team_id"))
    if home_id is None:
        text_hid = str(fixture_values.get("home_team_id") or "")
        home_id = int(text_hid) if text_hid.isdigit() and int(text_hid) > 0 else None

    away_id = _pos_int(fixture.get("away_team_id"))
    if away_id is None:
        text_aid = str(fixture_values.get("away_team_id") or "")
        away_id = int(text_aid) if text_aid.isdigit() and int(text_aid) > 0 else None

    return player_processing.FixtureTeamContext(
        fixture_id=raw_fid,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name=fixture_values.get("home_team"),
        away_team_name=fixture_values.get("away_team"),
    )


def _trace_call_attempts(
    call: _Call,
    *,
    logical_call_id: str,
    accepted_parsed: Mapping[str, Any] | None,
    accepted_raw_text: str | None,
    regeneration_reason: psc.RegenerationReason | None = None,
) -> list[player_processing.ProcessingAttemptRecord]:
    attempts = list(getattr(call.result, "attempts", ()) or ())
    records: list[player_processing.ProcessingAttemptRecord] = []
    last_idx = len(attempts) - 1
    for idx, att in enumerate(attempts):
        is_accepted = accepted_parsed is not None and idx == last_idx
        records.append(
            player_processing.ProcessingAttemptRecord(
                attempt_ordinal=att.attempt_ordinal,
                logical_call_id=att.logical_call_id or logical_call_id,
                parsed_valid=is_accepted,
                raw_text=accepted_raw_text if is_accepted else None,
                parsed_json=dict(accepted_parsed) if is_accepted else None,
                regeneration_triggered=bool(is_accepted and regeneration_reason is not None),
                regeneration_reason=regeneration_reason if is_accepted else None,
                error_reason=(
                    None
                    if is_accepted
                    else (att.error_message or getattr(att.outcome, "value", "failed"))
                ),
            )
        )
    return records


def _execute_player_section_with_regeneration(
    *,
    workflow_id: psc.PlayerSectionWorkflowId,
    section_id: str,
    module_id: str,
    label: str,
    prompt: str,
    prompt_version: str,
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    fixture_ctx: player_processing.FixtureTeamContext,
    local_resolver: Any,
    allowed_evidence: frozenset[str],
    now: datetime | None,
) -> tuple[_Call, int, player_processing.PlayerSectionProcessingBundle, str | None]:
    """첫 유효 응답에 설명 누락·중복이 있으면 같은 장부·예산으로 섹션 전체를 최대 1회 재생성한다."""
    logical_call_id = LOGICAL_CALL_IDS[section_id] or section_id
    content_check = _content_accepts_for(
        section_id, label=label, parse=players_module.parse_model_output
    )
    call1 = _call_model(
        section_id=section_id,
        prompt=prompt,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=module_id,
        prompt_version=prompt_version,
        now=now,
        content_check=content_check,
        starting_ordinal=0,
    )
    mode = _mode_value(transport)
    truncated1 = _truncation_reason(call1, label=label)
    parsed1 = None if truncated1 else players_module.parse_model_output(call1.text)
    if parsed1 is None:
        fail_msg = (
            truncated1
            if truncated1
            else (
                _failure_reason(call1, label=label)
                if call1.text is None
                else f"{label} 응답을 JSON으로 해석하지 못했습니다."
            )
        )
        traces1 = _trace_call_attempts(
            call1,
            logical_call_id=logical_call_id,
            accepted_parsed=None,
            accepted_raw_text=None,
        )
        failed_bundle = player_processing.build_failed_processing_bundle(
            workflow_id=workflow_id,
            fixture=fixture_ctx,
            attempts=traces1,
            regeneration_count=0,
            regeneration_reason=None,
            failed_reason=fail_msg,
            mode=mode,
        )
        return call1, call1.attempts, failed_bundle, fail_msg

    candidates1, labels1 = player_processing.evaluate_raw_candidates(
        workflow_id=workflow_id,
        payload=parsed1,
        fixture=fixture_ctx,
        resolver=local_resolver,
        allowed_evidence=allowed_evidence,
    )
    regen_reason = player_processing.detect_regeneration_reason(candidates1)
    traces1 = _trace_call_attempts(
        call1,
        logical_call_id=logical_call_id,
        accepted_parsed=parsed1,
        accepted_raw_text=call1.text,
        regeneration_reason=regen_reason,
    )
    if regen_reason is None:
        adopted_ordinal = traces1[-1].attempt_ordinal if traces1 else 0
        processing = player_processing.place_final_candidates(
            workflow_id=workflow_id,
            fixture=fixture_ctx,
            candidates=candidates1,
            labels=labels1,
            attempts=traces1,
            regeneration_count=0,
            regeneration_reason=None,
            adopted_attempt_ordinal=adopted_ordinal,
            mode=mode,
        )
        return call1, call1.attempts, processing, None

    # 첫 유효 응답에 누락·중복 결함이 있다: 같은 논리 호출 상한(최대 3회) 안에서만 최대 1회 재생성한다.
    attempts1_raw = list(getattr(call1.result, "attempts", ()) or ())
    next_ordinal = (attempts1_raw[-1].attempt_ordinal + 1) if attempts1_raw else 0
    if next_ordinal >= psc.MAX_MODULE_ATTEMPTS:
        fail_msg = (
            f"첫 유효 응답({regen_reason.value})의 내용 재생성이 필요했으나 "
            f"모듈 전송 상한({psc.MAX_MODULE_ATTEMPTS}회)에 도달해 실패했습니다. 첫 응답으로 대체하지 않습니다."
        )
        failed_bundle = player_processing.build_failed_processing_bundle(
            workflow_id=workflow_id,
            fixture=fixture_ctx,
            attempts=traces1,
            regeneration_count=0,
            regeneration_reason=regen_reason,
            failed_reason=fail_msg,
            mode=mode,
        )
        return call1, call1.attempts, failed_bundle, fail_msg

    regen_prompt = prompt + player_processing.build_regeneration_instruction(
        workflow_id=workflow_id, reason=regen_reason
    )
    call2 = _call_model(
        section_id=section_id,
        prompt=regen_prompt,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=module_id,
        prompt_version=prompt_version,
        now=now,
        content_check=content_check,
        starting_ordinal=next_ordinal,
    )
    total_calls = call1.attempts + call2.attempts
    truncated2 = _truncation_reason(call2, label=label)
    parsed2 = None if truncated2 else players_module.parse_model_output(call2.text)
    if parsed2 is None:
        reason2 = (
            truncated2
            if truncated2
            else (
                _failure_reason(call2, label=label)
                if call2.text is None
                else f"{label} 재생성 응답을 JSON으로 해석하지 못했습니다."
            )
        )
        fail_msg = f"내용 재생성 실패({reason2}). 첫 응답으로 대체하지 않습니다."
        traces2 = _trace_call_attempts(
            call2,
            logical_call_id=logical_call_id,
            accepted_parsed=None,
            accepted_raw_text=None,
        )
        failed_bundle = player_processing.build_failed_processing_bundle(
            workflow_id=workflow_id,
            fixture=fixture_ctx,
            attempts=traces1 + traces2,
            regeneration_count=1,
            regeneration_reason=regen_reason,
            failed_reason=fail_msg,
            mode=mode,
        )
        return call2, total_calls, failed_bundle, fail_msg

    candidates2, labels2 = player_processing.evaluate_raw_candidates(
        workflow_id=workflow_id,
        payload=parsed2,
        fixture=fixture_ctx,
        resolver=local_resolver,
        allowed_evidence=allowed_evidence,
    )
    traces2 = _trace_call_attempts(
        call2,
        logical_call_id=logical_call_id,
        accepted_parsed=parsed2,
        accepted_raw_text=call2.text,
    )
    combined_traces = traces1 + traces2
    adopted_ordinal = traces2[-1].attempt_ordinal if traces2 else next_ordinal
    processing = player_processing.place_final_candidates(
        workflow_id=workflow_id,
        fixture=fixture_ctx,
        candidates=candidates2,
        labels=labels2,
        attempts=combined_traces,
        regeneration_count=1,
        regeneration_reason=regen_reason,
        adopted_attempt_ordinal=adopted_ordinal,
        mode=mode,
    )
    return call2, total_calls, processing, None


# --------------------------------------------------------------------------
# 섹션: 주목 선수
# --------------------------------------------------------------------------


def _player_rows(
    payload: Mapping[str, Any] | None,
    *,
    resolver: Any,
    scope_team_ids: Sequence[int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """모델 응답의 선수를 계약 모양으로 옮기고 팀당 2명으로 제한한다."""
    diagnostics: list[str] = []
    raw_items: list[dict[str, Any]] = []
    for raw in (payload or {}).get("players") or ():
        if not isinstance(raw, Mapping):
            continue
        name = str(
            raw.get(player_contract.SELECTED_PLAYER_FIELD) or raw.get("player") or ""
        ).strip()
        reason = str(
            raw.get(player_contract.SELECTION_REASON_FIELD) or raw.get("reason") or ""
        ).strip()
        if not name or not reason:
            diagnostics.append("이름이나 선정 이유가 비어 있는 선수 항목은 표시하지 않았습니다.")
            continue
        ref = raw.get("player_ref")
        raw_items.append(
            {
                player_contract.SELECTED_PLAYER_FIELD: name,
                player_contract.SELECTION_REASON_FIELD: reason,
                "team": str(raw.get("team") or "").strip() or None,
                "player_ref": (
                    int(ref)
                    if isinstance(ref, int) or str(ref or "").isdigit()
                    else None
                ),
                "evidence": [str(item) for item in raw.get("evidence") or ()],
                "superlative_basis": str(raw.get("superlative_basis") or "").strip() or None,
            }
        )
    if not raw_items:
        return [], diagnostics

    rows, _unmapped = _resolve_player_rows(
        raw_items, resolver=resolver, scope_team_ids=scope_team_ids
    )

    kept: list[dict[str, Any]] = []
    per_team: dict[str, int] = {}
    for row in rows:
        team_key = str(row.get("team") or row.get("team_display_name") or "")
        if team_key and per_team.get(team_key, 0) >= PLAYERS_PER_TEAM:
            diagnostics.append(
                f"{team_key}에서 팀당 상한({PLAYERS_PER_TEAM}명)을 넘는 선수는 표시하지 않았습니다."
            )
            continue
        if len(kept) >= MAX_BUNDLE_PLAYERS:
            diagnostics.append(
                f"전체 상한({MAX_BUNDLE_PLAYERS}명)을 넘는 선수는 표시하지 않았습니다."
            )
            break
        if team_key:
            per_team[team_key] = per_team.get(team_key, 0) + 1
        kept.append(row)
    return kept, diagnostics


def _apply_model_labels(
    rows: Sequence[Mapping[str, Any]],
    labels: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """DB에서 확인되지 않은 표시 이름만 같은 응답의 한글 표기로 바꾼다.

    대소문자·앞뒤 공백만 다른 표기를 같은 이름으로 본다(그 외 유사 일치는 하지 않는다).
    DB에서 확인된 이름(`mapping_status=resolved`)은 **덮어쓰지 않는다**(DB가 이긴다).
    """
    diagnostics: list[str] = []
    by_original: dict[str, str] = {}
    for entry in labels or ():
        if not isinstance(entry, Mapping):
            continue
        kind = str(entry.get("kind") or "").strip().lower()
        if kind and kind != "player":
            continue
        original = str(entry.get("original") or "").strip()
        korean = str(entry.get("korean") or "").strip()
        if original and korean:
            by_original[original.casefold()] = korean
    if not by_original:
        return [dict(row) for row in rows], diagnostics
    kept: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if str(item.get("mapping_status") or "") != "resolved":
            source_name = str(
                item.get("model_selected_player")
                or item.get(player_contract.SELECTED_PLAYER_FIELD)
                or ""
            ).strip()
            label = by_original.get(source_name.casefold())
            if label:
                item[player_contract.SELECTED_PLAYER_FIELD] = label
                item["name_source"] = "model_same_response"
                diagnostics.append(
                    f"{source_name}: DB 한국어 이름이 없어 같은 응답의 표기 '{label}'를"
                    " 표시에 썼습니다."
                )
        kept.append(item)
    return kept, diagnostics


def _players_section(
    *,
    payload: Mapping[str, Any],
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    resolver: Any,
    fixture_values: dict[str, str],
    material: _DbMaterial,
    now: datetime | None,
) -> SectionDraft:
    section_id = bundle_contract.SECTION_PLAYERS
    module_id = "R4"
    prompt_version = PROMPT_VERSION_PLAYERS
    local_resolver = player_processing.clone_section_resolver(resolver)
    fixture_ctx = _fixture_team_context(payload, fixture_values)
    selection = _select_passages(payload, section_id)
    search = _search_material(payload, section_id)
    diagnostics: list[str] = (
        list(selection.diagnostics) + list(material.diagnostics) + list(search.diagnostics)
    )

    # 기사 본문이 없어도 DB 후보나 **검색이 실제로 돌려준 자료**가 있으면 작성을 중단하지
    # 않는다(사용자 확정 기준: 본문 → 검색 자료 → DB 순 사용).
    if not selection.passages and not material.roster and not search.rows:
        budget.cancel_call(LOGICAL_CALL_IDS[section_id] or section_id)
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="주목 선수",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "이 경기의 수집 본문과 선수 후보 자료가 모두 없어 주목 선수 요청을"
                " 보내지 않았습니다."
            ),
            prompt_version=prompt_version,
            diagnostics=tuple(
                diagnostics
                + ["모델 호출을 시작하지 않아 예약 몫을 반환했습니다(새 호출 없음)."]
            ),
            delivery=_delivery(
                section_id=section_id,
                call=None,
                selection=selection,
                model_delivered=False,
                prompt_version=prompt_version,
                note="호출하지 않음(자료 없음).",
            ),
            mode=_mode_value(transport),
        )

    prompt = _render(
        load_prompt(_PROMPTS[section_id][0]),
        {
            **fixture_values,
            "today": _today(now),
            "per_team": str(PLAYERS_PER_TEAM),
            "max_players": str(MAX_BUNDLE_PLAYERS),
            "roster": _roster_lines(
                material.roster, names=material.teams, resolver=local_resolver
            ),
            "db_facts": _db_block(material),
            "evidence_ids": _evidence_lines(
                tuple(selection.passage_ids) + search.finding_ids, material.ids
            ),
            "passages": _render_passages(selection.passages),
            "search_material": _render_search_material(search),
        },
    )
    allowed = frozenset(_allowed_evidence(selection, material) | set(search.finding_ids))
    final_call, total_calls, processing, exec_error = _execute_player_section_with_regeneration(
        workflow_id=psc.PlayerSectionWorkflowId.SECTION_PLAYERS,
        section_id=section_id,
        module_id=module_id,
        label="주목 선수",
        prompt=prompt,
        prompt_version=prompt_version,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        fixture_ctx=fixture_ctx,
        local_resolver=local_resolver,
        allowed_evidence=allowed,
        now=now,
    )
    delivery = _delivery(
        section_id=section_id,
        call=final_call,
        selection=selection,
        model_delivered=True,
        prompt_version=prompt_version,
        note=(
            f"구간 {len(selection.passages)}개·출처 {len(selection.source_ids)}개·"
            f"검색 자료 {len(search.rows)}건을 전달했습니다."
        ),
        search_finding_ids=search.finding_ids,
        sent_attempts_override=total_calls,
    )
    diagnostics.extend(processing.diagnostics)

    if exec_error is not None:
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="주목 선수",
            body="",
            structured={
                "korean_labels": [dict(item) for item in processing.korean_labels],
                "players": [],
                "processing": processing.to_dict(),
            },
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=exec_error,
            prompt_version=prompt_version,
            diagnostics=tuple(diagnostics),
            delivery=delivery,
            mode=_mode_value(transport),
            external_calls=total_calls,
        )

    register_labels = getattr(local_resolver, "register_model_labels", None)
    if callable(register_labels) and processing.korean_labels:
        try:
            register_labels(processing.korean_labels)
        except Exception:  # noqa: BLE001
            pass

    rows = [
        {
            player_contract.SELECTED_PLAYER_FIELD: slot.name_ko,
            player_contract.SELECTION_REASON_FIELD: slot.body,
            "team": slot.team_name,
            "team_side": slot.team_side.value,
            "team_id": slot.team_id,
            "player_id": slot.player_id,
            "external_player_id": slot.external_player_id,
            "original_name": slot.original_name,
            "name_source": slot.name_source.value,
            "unresolved_reason": slot.unresolved_reason,
            "evidence": list(slot.evidence),
        }
        for slot in processing.placed_slots
    ]
    composed = players_module.compose_players_body(
        {"players": rows, "reader_sources": list(_reader_sources(selection))}
    )
    body = composed.body if rows else ""
    unavailable_reason = None
    if not body:
        unavailable_reason = processing.failed_reason or (
            "표시할 수 있는 주목 선수(이름·한글명·선정 이유)가 없어 본문을 만들지 않았습니다."
        )
        diagnostics.extend(composed.diagnostics)

    structured = {
        "korean_labels": [dict(item) for item in processing.korean_labels],
        "players": rows,
        "processing": processing.to_dict(),
    }
    return SectionDraft(
        section_id=section_id,
        module_id=module_id,
        title=composed.title or "주목 선수",
        body=body,
        sources=_reader_sources(selection),
        structured=structured,
        quality=QualityStatus.READY if body else QualityStatus.INSUFFICIENT,
        unavailable_reason=unavailable_reason,
        prompt_version=prompt_version,
        diagnostics=tuple(diagnostics),
        delivery=delivery,
        mode=_mode_value(transport),
        external_calls=total_calls,
        player_processing=processing,
    )


# --------------------------------------------------------------------------
# 섹션: 부상·결장
# --------------------------------------------------------------------------


def _verified_injury_player(
    name: str,
    *,
    team_hint: Any,
    resolver: Any,
    scope_team_ids: Sequence[int],
) -> tuple[int, str] | None:
    """모델이 적은 부상 선수 **이름**을 DB 범위 안에서 결정적으로 확인한다.

    왜 필요한가: 모델은 이름만 적고 `player_id`를 `null`로 두는 경우가 있다. 그러면
    화면 구조 값이 내부↔외부 ID를 확인하지 못해 사진이 비고, 본문에는 영어 표기가 남는다.
    같은 경기 두 팀 로스터 범위에서 **유일하게 확인된** 선수만 ID로 굳힌다.

    반환은 `(player_id, display_name)`이며 확인되지 않으면 `None`이다.
    동명이인·모호한 일치는 ID를 만들지 않는다(추측 금지).

    모델이 준 숫자는 신뢰 ID가 아니므로 쓰지 않는다(`id_is_hint=True`를 쓰지 않는다).
    확인된 범위 안의 이름 일치만 근거로 삼는다.
    """
    if not isinstance(name, str) or not name.strip() or resolver is None:
        return None
    scope = [int(item) for item in scope_team_ids if item is not None]
    resolve = getattr(resolver, "resolve_player", None)
    if not callable(resolve):
        return None
    try:
        resolution = resolve(
            name,
            team_hint=team_hint if isinstance(team_hint, str) else None,
            scope_team_ids=scope or None,
        )
    except Exception:  # noqa: BLE001 - 확인 실패로 부상 행을 없애지 않는다
        return None
    player = getattr(resolution, "player", None)
    if player is None:
        return None
    player_id = getattr(player, "player_id", None)
    if not isinstance(player_id, int) or isinstance(player_id, bool):
        return None
    display = str(getattr(player, "display_name", "") or "").strip()
    if not display:
        return None
    return int(player_id), display


def _injury_rows(
    payload: Mapping[str, Any] | None,
    *,
    allowed: set[str],
    names: Mapping[int, str],
    resolver: Any,
    scope_team_ids: Sequence[int] = (),
) -> tuple[list[dict[str, Any]], list[str], int]:
    """모델 응답의 부상 항목을 정리한다. 상태 표기를 승격하지 않는다."""
    diagnostics: list[str] = []
    rows: list[dict[str, Any]] = []
    dropped_evidence = 0
    per_team: dict[str, int] = {}
    for raw in (payload or {}).get("injuries") or ():
        if not isinstance(raw, Mapping):
            continue
        name = str(raw.get("player_name") or raw.get("player") or "").strip()
        if not name:
            diagnostics.append("이름이 없는 부상 항목은 표시하지 않았습니다.")
            continue
        evidence, dropped = _clean_evidence(raw.get("evidence"), allowed)
        dropped_evidence += dropped
        if not evidence:
            diagnostics.append(
                f"{name}: 전달한 자료로 확인되지 않아 부상 항목에서 뺐습니다."
            )
            continue
        status = str(raw.get("status") or "").strip().lower()
        if status not in {
            "doubtful",
            "confirmed_absence",
            "available",
            "unknown",
        }:
            if status:
                diagnostics.append(
                    f"{name}: 알 수 없는 상태 표기 '{status}'를 'unknown'으로 두었습니다."
                )
            status = "unknown"
        team = _team_display(
            team_id=raw.get("team_id"),
            label=raw.get("team"),
            names=names,
            resolver=resolver,
        )
        if team:
            if per_team.get(team, 0) >= MAX_INJURIES_PER_TEAM:
                diagnostics.append(
                    f"{team}: 팀당 상한({MAX_INJURIES_PER_TEAM}명)을 넘는 부상 항목은"
                    " 표시하지 않았습니다."
                )
                continue
            per_team[team] = per_team.get(team, 0) + 1
        player_id = raw.get("player_id")
        verified = _verified_injury_player(
            name,
            team_hint=raw.get("team"),
            resolver=resolver,
            scope_team_ids=scope_team_ids,
        )
        display_name = name
        if verified is not None:
            verified_id, verified_display = verified
            if isinstance(player_id, int) and not isinstance(player_id, bool):
                if player_id != verified_id:
                    # 모델이 적은 숫자와 이름이 다른 선수를 가리킨다. 어느 쪽도 고르지 않는다.
                    diagnostics.append(
                        f"{name}: 모델이 적은 player_id {player_id}가 이름으로 확인된"
                        f" 선수 {verified_id}와 달라 ID를 비웠습니다."
                    )
                    player_id = None
                else:
                    display_name = verified_display
            else:
                player_id = verified_id
                display_name = verified_display
                diagnostics.append(
                    f"{name}: 저장 자료에서 같은 이름의 선수(player_id {verified_id})를"
                    " 확인해 ID와 표시 이름을 연결했습니다."
                )
        rows.append(
            {
                "player_name": display_name,
                "player_id": player_id if isinstance(player_id, int) else None,
                "team": team,
                "team_id": (
                    raw.get("team_id") if isinstance(raw.get("team_id"), int) else None
                ),
                "status": status,
                "injury": str(raw.get("injury") or "").strip() or None,
                "importance": str(raw.get("importance") or "").strip() or None,
                "evidence": evidence,
            }
        )
    return rows, diagnostics, dropped_evidence


_STATUS_LABELS = {
    "doubtful": "출전 불확실",
    "confirmed_absence": "결장(확정 표기)",
    "available": "출전 가능 표기",
    "unknown": "표기 없음(확정 사실 아님)",
}


def _compose_injuries_body(rows: Sequence[Mapping[str, Any]]) -> str:
    """부상 섹션 본문(결정적). 진단·누락 안내를 넣지 않는다."""
    if not rows:
        return ""
    blocks: list[str] = []
    current: str | None = None
    lines: list[str] = []
    for row in rows:
        team = str(row.get("team") or "팀 미확인")
        if current != team:
            if lines:
                blocks.append("\n".join(lines))
            lines = [f"### {team}"]
            current = team
        lines.append(f"- {row['player_name']}: {_STATUS_LABELS[row['status']]}")
        if row.get("injury"):
            lines.append(f"  부상 내용: {row['injury']}")
        if row.get("importance"):
            lines.append(f"  영향: {row['importance']}")
    if lines:
        blocks.append("\n".join(lines))
    return "\n\n".join(["## 부상·결장 영향", "확인된 부상·결장 상황만 정리했습니다.", *blocks])


def _availability_section(
    *,
    payload: Mapping[str, Any],
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    resolver: Any,
    fixture_values: dict[str, str],
    material: _DbMaterial,
    now: datetime | None,
) -> SectionDraft:
    section_id = bundle_contract.SECTION_AVAILABILITY
    module_id = "R2"
    prompt_version = PROMPT_VERSION_AVAILABILITY
    local_resolver = player_processing.clone_section_resolver(resolver)
    fixture_ctx = _fixture_team_context(payload, fixture_values)
    selection = _select_passages(payload, section_id)
    search = _search_material(payload, section_id)
    diagnostics: list[str] = (
        list(selection.diagnostics) + list(material.diagnostics) + list(search.diagnostics)
    )

    if not selection.passages and not material.injury_ids and not search.rows:
        budget.cancel_call(LOGICAL_CALL_IDS[section_id] or section_id)
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="부상·결장 영향",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "이 경기의 부상 관련 수집 본문과 DB 부상 행이 모두 없어 요청을 보내지"
                " 않았습니다. 부상자가 없다는 뜻은 아닙니다."
            ),
            prompt_version=prompt_version,
            diagnostics=tuple(
                diagnostics + ["모델 호출을 시작하지 않아 예약 몫을 반환했습니다(새 호출 없음)."]
            ),
            delivery=_delivery(
                section_id=section_id,
                call=None,
                selection=selection,
                model_delivered=False,
                prompt_version=prompt_version,
                note="호출하지 않음(자료 없음).",
            ),
            mode=_mode_value(transport),
        )

    state, detail = _injury_state(material)
    prompt = _render(
        load_prompt(_PROMPTS[section_id][0]),
        {
            **fixture_values,
            "today": _today(now),
            "injury_state": state,
            "injury_state_detail": detail,
            "max_players": str(MAX_INJURIES_PER_TEAM),
            "db_injuries": _db_injury_block(material),
            "evidence_ids": _evidence_lines(
                tuple(selection.passage_ids) + search.finding_ids, material.ids
            ),
            "passages": _render_passages(selection.passages),
            "search_material": _render_search_material(search),
        },
    )
    allowed = frozenset(_allowed_evidence(selection, material) | set(search.finding_ids))
    final_call, total_calls, processing, exec_error = _execute_player_section_with_regeneration(
        workflow_id=psc.PlayerSectionWorkflowId.SECTION_AVAILABILITY,
        section_id=section_id,
        module_id=module_id,
        label="부상",
        prompt=prompt,
        prompt_version=prompt_version,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        fixture_ctx=fixture_ctx,
        local_resolver=local_resolver,
        allowed_evidence=allowed,
        now=now,
    )
    delivery = _delivery(
        section_id=section_id,
        call=final_call,
        selection=selection,
        model_delivered=True,
        prompt_version=prompt_version,
        note=(
            f"구간 {len(selection.passages)}개·출처 {len(selection.source_ids)}개·"
            f"검색 자료 {len(search.rows)}건을 전달했습니다."
        ),
        search_finding_ids=search.finding_ids,
        sent_attempts_override=total_calls,
    )
    diagnostics.extend(processing.diagnostics)

    if exec_error is not None:
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="부상·결장 영향",
            body="",
            structured={
                "korean_labels": [dict(item) for item in processing.korean_labels],
                "injuries": [],
                "processing": processing.to_dict(),
            },
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=exec_error,
            prompt_version=prompt_version,
            diagnostics=tuple(diagnostics),
            delivery=delivery,
            mode=_mode_value(transport),
            external_calls=total_calls,
        )

    register_labels = getattr(local_resolver, "register_model_labels", None)
    if callable(register_labels) and processing.korean_labels:
        try:
            register_labels(processing.korean_labels)
        except Exception:  # noqa: BLE001
            pass

    body = player_processing.compose_availability_body(processing.placed_slots)
    structured = {
        "korean_labels": [dict(item) for item in processing.korean_labels],
        "injuries": [
            {
                "player_name": slot.name_ko,
                "team": slot.team_name,
                "team_side": slot.team_side.value,
                "player_id": slot.player_id,
                "external_player_id": slot.external_player_id,
                "team_id": slot.team_id,
                "original_name": slot.original_name,
                "name_source": slot.name_source.value,
                "unresolved_reason": slot.unresolved_reason,
                "status": slot.status,
                "injury": slot.injury,
                "importance": slot.importance,
                "body": slot.body,
                "summary": slot.body or None,
                "detail": slot.body or None,
                "evidence": list(slot.evidence),
            }
            for slot in processing.placed_slots
        ],
        "processing": processing.to_dict(),
    }
    return SectionDraft(
        section_id=section_id,
        module_id=module_id,
        title="부상·결장 영향",
        body=body,
        sources=_reader_sources(selection),
        structured=structured,
        quality=QualityStatus.READY if body else QualityStatus.INSUFFICIENT,
        unavailable_reason=(
            None
            if body
            else (
                processing.failed_reason
                or "근거가 확인된 부상·결장 항목이 없어 이 선택 섹션의 본문을 만들지 않았습니다."
            )
        ),
        prompt_version=prompt_version,
        diagnostics=tuple(diagnostics),
        delivery=delivery,
        mode=_mode_value(transport),
        external_calls=total_calls,
        player_processing=processing,
    )


# --------------------------------------------------------------------------
# 섹션: 외부 매체 전망
# --------------------------------------------------------------------------


def _source_urls(
    payload: Mapping[str, Any],
    section_id: str,
    *,
    search_material: "_SearchMaterial | None" = None,
) -> set[str]:
    """매체 항목이 가리켜도 되는 주소.

    - 실제로 수집한 출처의 최종/요청 주소
    - **이 섹션에 실제로 전달한 검색 자료의 주소**(`finding.sources`·`url`)

    두 번째를 빼면, 검색 도구가 반환한 주소를 근거로 쓴 매체 항목이 "수집 출처 목록에
    없다"는 이유로 버려진다. 그것은 사용자가 승인한 "검색 AI 요약 활용"과 어긋난다.
    주소만 있고 내용이 없는 항목을 채우는 것은 아니며, 이 함수는 **주소 허용 범위**만 넓힌다.
    """
    urls: set[str] = set()
    for source in _section_scope(payload, section_id):
        for key in ("final_url", "requested_url"):
            url = source.get(key)
            if isinstance(url, str) and url.strip():
                urls.add(url.strip())
    for row in (search_material.rows if search_material is not None else ()):
        for value in [row.get("url"), *(row.get("sources") or ())]:
            if isinstance(value, str) and value.strip():
                urls.add(value.strip())
    return urls


def _media_rows(
    parsed_rows: Sequence[Mapping[str, Any]],
    *,
    allowed_urls: set[str],
    allowed_evidence: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """매체 전망을 최대 3곳으로 정리한다. 점수는 인용문에 있을 때만 남긴다."""
    diagnostics: list[str] = []
    rows: list[dict[str, Any]] = []
    seen_media: set[str] = set()
    for raw in parsed_rows:
        statement = str(raw.get("statement") or "").strip()
        if not statement:
            diagnostics.append("전망 문장이 비어 있는 매체 항목은 표시하지 않았습니다.")
            continue
        url = str(raw.get("url") or "").strip()
        if url and url not in allowed_urls:
            diagnostics.append(
                f"수집한 출처 목록에 없는 주소({url})를 가리킨 매체 항목은 표시하지 않았습니다."
            )
            continue
        evidence, _dropped = _clean_evidence(raw.get("evidence"), allowed_evidence)
        if not url and not evidence:
            diagnostics.append(
                "출처 주소와 전달 구간 근거가 모두 없는 매체 항목은 표시하지 않았습니다."
            )
            continue
        if not url:
            diagnostics.append(
                "출처 주소가 비어 있는 매체 항목이 있습니다(주소를 만들지 않았습니다)."
            )
        publisher = str(raw.get("publisher") or "").strip() or None
        key = publisher.casefold() if publisher else "__unknown__"
        if key in seen_media:
            diagnostics.append(
                f"같은 매체({publisher or '매체 미상'})의 항목은 한 곳으로 묶어 표시했습니다."
            )
            continue
        if len(seen_media) >= MAX_MEDIA_PUBLISHERS:
            diagnostics.append(
                f"서로 다른 매체 상한({MAX_MEDIA_PUBLISHERS}곳)을 넘는 항목은 표시하지 않았습니다."
            )
            continue
        seen_media.add(key)

        score = str(raw.get("predicted_score") or "").strip() or None
        if score and score not in statement:
            diagnostics.append(
                f"{publisher or '매체 미상'}: 인용문에 없는 예상 스코어 '{score}'를 비웠습니다."
            )
            score = None
        published = raw.get("published_at")
        rows.append(
            {
                "publisher": publisher,
                "url": url or None,
                "published_at": str(published).strip() if published else None,
                "statement": statement,
                "predicted_score": score,
                "evidence": evidence,
            }
        )
    return rows, diagnostics


def _compose_media_body(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    lines = [
        "## 외부 매체 전망",
        "수집한 기사에서 확인한 외부 매체의 이 경기 전망입니다. 이 서비스의 판단과는 별개입니다.",
    ]
    for row in rows:
        when = f" ({row['published_at']})" if row.get("published_at") else ""
        score = row.get("predicted_score")
        suffix = (
            f" 예상 스코어 {score}."
            if score and score not in row["statement"]
            else ""
        )
        lines.append(f"- {row.get('publisher') or '매체 미상'}{when}: {row['statement']}{suffix}")
    return "\n".join(lines)


def _outlook_section(
    *,
    payload: Mapping[str, Any],
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    material: _DbMaterial,
    fixture_values: dict[str, str],
    now: datetime | None,
) -> SectionDraft:
    section_id = bundle_contract.SECTION_OUTLOOK
    module_id = "R3"
    prompt_version = PROMPT_VERSION_OUTLOOK
    selection = _select_passages(payload, section_id)
    search = _search_material(payload, section_id)
    diagnostics: list[str] = list(selection.diagnostics) + list(search.diagnostics)

    # 검색 도구가 실제로 돌려준 출처 메타/요약이 있으면 본문이 없어도 요청을 보낸다.
    # 그 자료로 매체 전망을 **만들지** 않는다는 경계는 프롬프트가 지시한다.
    if not selection.passages and not search.rows:
        budget.cancel_call(LOGICAL_CALL_IDS[section_id] or section_id)
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="외부 매체 전망",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "외부 전망을 확인할 수집 기사 본문이 없어 매체 전망 요청을 보내지"
                " 않았습니다."
            ),
            prompt_version=prompt_version,
            diagnostics=tuple(
                diagnostics + ["모델 호출을 시작하지 않아 예약 몫을 반환했습니다(새 호출 없음)."]
            ),
            delivery=_delivery(
                section_id=section_id,
                call=None,
                selection=selection,
                model_delivered=False,
                prompt_version=prompt_version,
                note="호출하지 않음(자료 없음).",
            ),
            mode=_mode_value(transport),
        )

    prompt = _render(
        load_prompt(_PROMPTS[section_id][0]),
        {
            **fixture_values,
            "today": _today(now),
            "max_publishers": str(MAX_MEDIA_PUBLISHERS),
            "passages": _render_passages(selection.passages),
            "evidence_ids": _evidence_lines(
                tuple(selection.passage_ids) + search.finding_ids, ()
            ),
            "search_material": _render_search_material(search),
        },
    )
    call = _call_model(
        section_id=section_id,
        prompt=prompt,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=module_id,
        prompt_version=prompt_version,
        now=now,
        # 잘린 JSON·해석 불가 본문은 같은 모듈의 남은 횟수 안에서 다시 보낸다.
        content_check=_content_accepts_for(
            section_id,
            label="외부 매체 전망",
            parse=lambda text: _media_parse_or_none(text),
        ),
    )
    delivery = _delivery(
        section_id=section_id,
        call=call,
        selection=selection,
        model_delivered=True,
        prompt_version=prompt_version,
        note=(
            f"구간 {len(selection.passages)}개·출처 {len(selection.source_ids)}개·"
            f"검색 자료 {len(search.rows)}건을 전달했습니다."
        ),
        search_finding_ids=search.finding_ids,
    )

    truncated = _truncation_reason(call, label="외부 매체 전망")
    if truncated:
        diagnostics.append(truncated)
        parsed_rows, parse_reason = [], truncated
    else:
        parsed_rows, parse_reason = outlook_module.parse_media_response(call.text)
        if parse_reason:
            diagnostics.append(parse_reason)
    # 검색 자료 id도 인용 근거로 쓸 수 있다(그 자료를 실제로 전달했으므로).
    allowed = _allowed_evidence(selection, material) | set(search.finding_ids)
    rows, row_diagnostics = _media_rows(
        parsed_rows,
        allowed_urls=_source_urls(payload, section_id, search_material=search),
        allowed_evidence=allowed,
    )
    diagnostics.extend(row_diagnostics)
    body = _compose_media_body(rows)
    structured = {
        "media": [
            {
                "publisher": row.get("publisher"),
                "url": row.get("url"),
                "published_at": row.get("published_at"),
                "statement": row["statement"],
                "predicted_score": row.get("predicted_score"),
                "evidence": list(row["evidence"]),
            }
            for row in rows
        ]
    }
    unavailable_reason = None
    if not body:
        # 사유를 세 갈래로 구분한다. 모델 전송이 실패했는데 '기사 근거 없음'으로 쓰면
        # 자료 부족으로 오해된다(2026-11-19 관측: R3는 429로 3회 소진, 입력 자료는 3출처
        # 7구간·검색 8건 8071자였다).
        call_failed = call.text is None
        if call_failed:
            unavailable_reason = (
                "외부 매체 전망 모델 호출이 성공하지 않아 본문을 만들지 않았습니다"
                f"({_failure_reason(call, label='외부 매체 전망')})."
            )
        elif not selection.passages and not search.rows:
            unavailable_reason = (
                "이 경기의 수집 기사 본문과 검색 자료가 모두 없어 외부 매체 전망 요청을"
                " 보내지 않았습니다."
            )
        else:
            unavailable_reason = (
                "모델 응답에 채택 가능한 외부 매체 전망 항목이 없어 이 선택 섹션의 본문을"
                " 만들지 않았습니다."
            )
    return SectionDraft(
        section_id=section_id,
        module_id=module_id,
        title="외부 매체 전망",
        body=body,
        sources=_reader_sources(selection),
        structured=structured,
        quality=QualityStatus.READY if body else QualityStatus.INSUFFICIENT,
        unavailable_reason=unavailable_reason,
        prompt_version=prompt_version,
        diagnostics=tuple(diagnostics),
        delivery=delivery,
        mode=_mode_value(transport),
        external_calls=call.attempts,
    )


# --------------------------------------------------------------------------
# 섹션: 배당 (모델 호출 0회)
# --------------------------------------------------------------------------


def _fmt_decimal(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None


def _odds_section(
    *,
    payload: Mapping[str, Any],
    transport: provider.ProviderTransport,
    provider_odds: Any = None,
) -> SectionDraft:
    """배당 섹션. 모델을 부르지 않고 묶음의 채택 가능한 줄만 옮긴다.

    `provider_odds`가 주어지면 그 결과(`provider_odds.ProviderOddsResult`)를 **공개 표
    다음 자리**에 최대 3행까지 채운다. 주지 않으면 저장 묶음의 공개 표 값만 쓴다.
    이 인자는 **명시적 생성·배당 섹션 실행**에서만 넘긴다. 일반 GET 조회는 넘기지
    않으므로 저장된 결과를 다시 여는 것만으로 외부 호출이 생기지 않는다.
    """
    section_id = bundle_contract.SECTION_ODDS
    selection = _select_passages(payload, section_id)
    described = bundle_contract.describe_odds(payload)
    adopted = bundle_contract.adopted_odds_quotes(payload)
    diagnostics = list(selection.diagnostics)
    diagnostics.extend(str(item) for item in described.get("diagnostics") or ())

    rows: list[dict[str, Any]] = []
    for quote in adopted:
        home = _fmt_decimal(quote.get("home_decimal"))
        draw = _fmt_decimal(quote.get("draw_decimal"))
        away = _fmt_decimal(quote.get("away_decimal"))
        if not (home and draw and away):
            diagnostics.append("소수점 값을 읽지 못한 배당 줄은 표시하지 않았습니다.")
            continue
        rows.append(
            {
                "bookmaker": str(quote.get("site") or "사이트 미상"),
                "site": quote.get("site"),
                "market": str(quote.get("market") or bundle_contract.ODDS_MARKET_REGULATION_1X2),
                "observed_at": quote.get("observed_at"),
                "home": home,
                "draw": draw,
                "away": away,
                "source_id": quote.get("source_id"),
            }
        )

    provider_sent = 0
    if provider_odds is not None:
        # 공개 표 값이 1행 있으면 그 값을 유지하고 남는 자리만 제공자 줄로 채운다.
        provider_sent = int(getattr(provider_odds, "sent", 0) or 0)
        diagnostics.extend(str(item) for item in (getattr(provider_odds, "diagnostics", ()) or ()))
        reason = getattr(provider_odds, "reason", None)
        if reason:
            diagnostics.append(str(reason))
        taken = {str(row["bookmaker"]).casefold() for row in rows}
        for quote in getattr(provider_odds, "quotes", ()) or ():
            if len(rows) >= 3:
                break
            site = str(getattr(quote, "site", "") or "사이트 미상")
            if site.casefold() in taken:
                continue
            home = _fmt_decimal(getattr(quote, "home_decimal", None))
            draw = _fmt_decimal(getattr(quote, "draw_decimal", None))
            away = _fmt_decimal(getattr(quote, "away_decimal", None))
            if not (home and draw and away):
                continue
            taken.add(site.casefold())
            observed = getattr(quote, "observed_at", None)
            rows.append(
                {
                    "bookmaker": site,
                    "site": site,
                    "market": bundle_contract.ODDS_MARKET_REGULATION_1X2,
                    "observed_at": observed.isoformat() if hasattr(observed, "isoformat") else observed,
                    "home": home,
                    "draw": draw,
                    "away": away,
                    "source_id": getattr(quote, "source_id", None),
                }
            )

    body = ""
    if rows:
        lines = [
            "## 배당 현황",
            # 출처를 특정하지 않는다. 공개 표와 제공자(API-Football) 줄이 함께 실릴 수
            # 있고, 기준 시각은 **제공자가 준 갱신 시각**이다(수집 시각이 아니다).
            "정규시간 1X2 소수점 배당입니다. 기준 시각은 제공된 갱신 시각입니다.",
        ]
        for row in rows:
            when = str(row["observed_at"] or "시각 미상")
            lines.append(
                f"- {row['bookmaker']} / 정규시간 1X2 / 기준 {when}:"
                f" 홈 {row['home']} · 무 {row['draw']} · 원정 {row['away']}"
            )
        body = "\n".join(lines)

    if not rows and not described.get("available"):
        diagnostics.append(str(described.get("note") or "채택 가능한 배당 줄이 없습니다."))

    return SectionDraft(
        section_id=section_id,
        module_id=None,
        title="배당 현황",
        body=body,
        sources=tuple(
            {
                "label": f"{row['bookmaker']} 정규시간 1X2",
                "url": None,
                "kind": "bookmaker",
                "note": "모델 없이 공개 표·제공자 배당을 정규화한 값입니다.",
            }
            for row in rows
        ),
        structured={"odds": rows},
        quality=QualityStatus.READY if body else QualityStatus.INSUFFICIENT,
        unavailable_reason=(
            None
            if body
            else "정규시간 1X2 값이 모두 있는 배당 줄이 없어 이 선택 섹션을 표시하지 않습니다."
        ),
        prompt_version=PROMPT_VERSION_ODDS,
        diagnostics=tuple(diagnostics),
        delivery=_delivery(
            section_id=section_id,
            call=None,
            selection=selection,
            model_delivered=False,
            prompt_version=PROMPT_VERSION_ODDS,
            note=(
                "모델 호출 없음. 후보 구간은 전달하지 않았습니다."
                + (
                    f" 제공자 배당 읽기 {provider_sent}회."
                    if provider_odds is not None
                    else ""
                )
            ),
        ),
        mode=_mode_value(transport),
        # 모델 호출은 0회다. 제공자 읽기는 API 사용량이며 이 값(external_calls)에 넣지 않는다.
        external_calls=0,
    )


# --------------------------------------------------------------------------
# 섹션: 최종 AI 전망·예상 스코어
# --------------------------------------------------------------------------

_UPSTREAM_ALIASES: Mapping[str, tuple[str, ...]] = {
    bundle_contract.SECTION_PLAYERS: ("players",),
    bundle_contract.SECTION_AVAILABILITY: ("injuries", "availability"),
    bundle_contract.SECTION_OUTLOOK: ("media",),
    bundle_contract.SECTION_ODDS: ("odds",),
}


def _upstream_has_material(upstream: Mapping[str, Any] | None) -> bool:
    """앞 섹션 선택 결과에 **실제 작성 자료**가 있는지.

    본문이 비어 있고 구조화 행도 없는 항목은 자료로 세지 않는다. 그래야 "선택은 했지만
    쓸 내용이 없는" 경우에 최종 요청을 보내지 않는다(빈 입력으로 유료 호출 금지).
    """
    for value in (upstream or {}).values():
        if not isinstance(value, Mapping):
            continue
        if str(value.get("body") or "").strip():
            return True
        for key in ("players", "injuries", "availability", "media", "odds", "forecast"):
            rows = value.get(key)
            if isinstance(rows, (list, tuple)) and rows:
                return True
            if isinstance(rows, Mapping) and rows:
                return True
            if isinstance(rows, str) and rows.strip():
                return True
    return False


def _upstream_value(upstream: Mapping[str, Any] | None, section_id: str) -> Any:
    """앞 섹션 결과를 여러 저장 모양에서 읽는다(값을 만들지 않는다)."""
    if not upstream:
        return None
    for key in (section_id, *_UPSTREAM_ALIASES.get(section_id, ())):
        if key in upstream:
            return upstream[key]
    for key in _UPSTREAM_ALIASES.get(section_id, ()):
        row = upstream.get(key)
        if row is not None:
            return row
    return None


def _upstream_rows(value: Any, *, kind: str) -> list[Mapping[str, Any]]:
    """SectionDraft·저장 payload·구조화 dict 어느 쪽이어도 행 목록으로 읽는다."""
    if value is None:
        return []
    if isinstance(value, SectionDraft):
        value = value.structured
    if isinstance(value, Mapping):
        structured = value.get("structured")
        scope = structured if isinstance(structured, Mapping) else value
        for key in (kind, *_UPSTREAM_ALIASES_KEY_ALIASES.get(kind, ())):
            rows = scope.get(key)
            if isinstance(rows, (list, tuple)):
                return [row for row in rows if isinstance(row, Mapping)]
        return []
    if isinstance(value, (list, tuple)):
        return [row for row in value if isinstance(row, Mapping)]
    return []


_UPSTREAM_ALIASES_KEY_ALIASES: Mapping[str, tuple[str, ...]] = {
    "players": ("players_to_watch",),
    "injuries": ("availability", "absences"),
    "media": ("external_outlook",),
    "odds": (),
}


def _upstream_body(value: Any) -> str:
    if isinstance(value, SectionDraft):
        return value.body
    if isinstance(value, Mapping):
        body = value.get("body")
        return body if isinstance(body, str) else ""
    return ""


def _render_upstream(
    upstream: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[str], list[str]]:
    """앞 섹션 결과를 프롬프트 블록으로 만든다. 반환: (블록, 인용 id, 진단)."""
    diagnostics: list[str] = []
    evidence: list[str] = []
    blocks: dict[str, str] = {}

    players = _upstream_rows(
        _upstream_value(upstream, bundle_contract.SECTION_PLAYERS), kind="players"
    )
    if players:
        lines = []
        for row in players[:MAX_BUNDLE_PLAYERS]:
            name = row.get("selected_player") or row.get("player") or ""
            reason = row.get("selection_reason") or row.get("reason") or ""
            team = row.get("team") or ""
            lines.append(f"- {team + ' · ' if team else ''}{name}: {reason}")
            evidence.extend(str(item) for item in row.get("evidence") or ())
        blocks["players"] = "\n".join(lines)
    else:
        body = _upstream_body(_upstream_value(upstream, bundle_contract.SECTION_PLAYERS))
        blocks["players"] = body.strip() or "- 주목 선수 결과가 없습니다."
        if not body.strip():
            diagnostics.append("주목 선수 섹션 결과가 입력에 없습니다.")

    injuries = _upstream_rows(
        _upstream_value(upstream, bundle_contract.SECTION_AVAILABILITY), kind="injuries"
    )
    if injuries:
        lines = []
        for row in injuries:
            name = row.get("player_name") or row.get("player") or ""
            team = row.get("team") or ""
            status = _STATUS_LABELS.get(str(row.get("status") or ""), "표기 없음")
            detail = " ".join(
                str(part)
                for part in (row.get("injury"), row.get("summary"), row.get("importance"))
                if part
            )
            lines.append(
                f"- {team + ' · ' if team else ''}{name}: {status}"
                + (f" — {detail}" if detail else "")
            )
            evidence.extend(str(item) for item in row.get("evidence") or ())
        blocks["availability"] = "\n".join(lines)
    else:
        body = _upstream_body(_upstream_value(upstream, bundle_contract.SECTION_AVAILABILITY))
        blocks["availability"] = body.strip() or "- 부상·결장 결과가 없습니다(부상자 없음의 증거가 아님)."

    media = _upstream_rows(
        _upstream_value(upstream, bundle_contract.SECTION_OUTLOOK), kind="media"
    )
    if media:
        lines = []
        for row in media[:MAX_MEDIA_PUBLISHERS]:
            publisher = row.get("publisher") or "매체 미상"
            statement = row.get("statement") or ""
            score = row.get("predicted_score")
            lines.append(
                f"- {publisher}: {statement}" + (f" (예상 스코어 {score})" if score else "")
            )
            evidence.extend(str(item) for item in row.get("evidence") or ())
        blocks["media"] = "\n".join(lines)
    else:
        blocks["media"] = "- 확인된 외부 매체 전망이 없습니다."

    odds = _upstream_rows(
        _upstream_value(upstream, bundle_contract.SECTION_ODDS), kind="odds"
    )
    if odds:
        lines = []
        for row in odds:
            site = row.get("bookmaker") or row.get("site") or "사이트 미상"
            when = row.get("observed_at") or "시각 미상"
            lines.append(
                f"- {site} / 기준 {when}: 홈 {row.get('home') or '미제공'} ·"
                f" 무 {row.get('draw') or '미제공'} · 원정 {row.get('away') or '미제공'}"
            )
        blocks["odds"] = "\n".join(lines)
    else:
        blocks["odds"] = "- 확인된 배당이 없습니다. 배당을 언급하지 않는다."

    return blocks, list(dict.fromkeys(evidence)), diagnostics


def _forecast_section(
    *,
    payload: Mapping[str, Any],
    upstream: Mapping[str, Any] | None,
    context: ExecutionContext,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session: Session | None,
    fixture_values: dict[str, str],
    material: _DbMaterial,
    now: datetime | None,
) -> SectionDraft:
    section_id = bundle_contract.SECTION_AI_FORECAST
    module_id = "S1"
    prompt_version = PROMPT_VERSION_FORECAST
    selection = _select_passages(payload, section_id)
    search = _search_material(payload, section_id)
    diagnostics: list[str] = (
        list(selection.diagnostics) + list(material.diagnostics) + list(search.diagnostics)
    )
    blocks, upstream_evidence, upstream_diagnostics = _render_upstream(upstream)
    diagnostics.extend(upstream_diagnostics)

    # 설계 §86: 경기 식별 외에 작성 가능한 자료가 **하나도** 없을 때만 보내지 않는다.
    # 사용자가 고른 앞 섹션 결과(upstream)도 작성 자료다. 이 값을 빼면 "선택 결과를
    # 입력으로 마지막 AI가 결론을 쓴다"는 요구가 게이트에서 막힌다.
    upstream_has_rows = bool(upstream_evidence) or _upstream_has_material(upstream)
    if (
        not selection.passages
        and not material.has_material
        and not search.rows
        and not upstream_has_rows
    ):
        budget.cancel_call(LOGICAL_CALL_IDS[section_id] or section_id)
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="AI 경기 전망",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "작성에 쓸 수 있는 웹 본문과 DB 경기력 자료가 모두 없어 최종 전망 요청을"
                " 보내지 않았습니다."
            ),
            prompt_version=prompt_version,
            diagnostics=tuple(
                diagnostics + ["모델 호출을 시작하지 않아 예약 몫을 반환했습니다(새 호출 없음)."]
            ),
            delivery=_delivery(
                section_id=section_id,
                call=None,
                selection=selection,
                model_delivered=False,
                prompt_version=prompt_version,
                note="호출하지 않음(자료 없음).",
            ),
            mode=_mode_value(transport),
        )

    allowed = (
        set(selection.passage_ids)
        | set(material.ids)
        | set(upstream_evidence)
        | set(search.finding_ids)
    )
    prompt = _render(
        load_prompt(_PROMPTS[section_id][0]),
        {
            **fixture_values,
            "today": _today(now),
            "db_facts": _db_block(material),
            "players": blocks["players"],
            "availability": blocks["availability"],
            "media": blocks["media"],
            "odds": blocks["odds"],
            "search_material": _render_search_material(search),
            "evidence_ids": _evidence_lines(sorted(allowed), ()),
        },
    )
    call = _call_model(
        section_id=section_id,
        prompt=prompt,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=module_id,
        prompt_version=prompt_version,
        now=now,
        # 잘린 JSON·해석 불가 본문은 같은 모듈의 남은 횟수 안에서 다시 보낸다.
        content_check=_content_accepts_for(
            section_id, label="최종 전망", parse=_forecast_parse_or_none
        ),
    )
    delivery = _delivery(
        section_id=section_id,
        call=call,
        selection=selection,
        model_delivered=True,
        prompt_version=prompt_version,
        note=(
            f"구간 {len(selection.passages)}개·DB 근거 {len(material.ids)}건·앞 섹션 인용"
            f" {len(upstream_evidence)}건·검색 자료 {len(search.rows)}건을 전달했습니다."
        ),
        search_finding_ids=search.finding_ids,
    )

    truncated = _truncation_reason(call, label="최종 전망")
    if truncated:
        diagnostics.append(truncated)
    parsed: Mapping[str, Any] | None = None
    if call.text is not None and not truncated:
        try:
            parsed = synthesis_module.parse_model_json(call.text)
        except synthesis_module.SynthesisFormatError:
            parsed = None
            diagnostics.append("최종 전망 응답을 JSON으로 해석하지 못했습니다.")
    if parsed is None:
        if truncated:
            reason = truncated
        elif call.text is None:
            reason = _failure_reason(call, label="최종 전망")
        else:
            reason = "최종 전망 응답을 해석하지 못해 본문을 만들지 않았습니다."
        return SectionDraft(
            section_id=section_id,
            module_id=module_id,
            title="AI 경기 전망",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=reason,
            prompt_version=prompt_version,
            diagnostics=tuple(diagnostics),
            delivery=delivery,
            mode=_mode_value(transport),
            external_calls=call.attempts,
        )

    forecast = str(parsed.get("forecast") or "").strip()
    score, score_diagnostics = _score_of(parsed.get("predicted_score"))
    diagnostics.extend(score_diagnostics)
    reasoning = [
        str(item).strip()
        for item in parsed.get("score_reasoning") or ()
        if str(item).strip()
    ][:3]
    forecast_evidence, dropped = _clean_evidence(parsed.get("forecast_evidence"), allowed)
    if dropped:
        diagnostics.append(
            f"전달하지 않은 근거 id 인용 {dropped}건을 표시 근거에서 뺐습니다."
        )

    lines: list[str] = []
    if forecast:
        lines.extend(["## AI 경기 전망", forecast])
    if score is not None:
        if lines:
            lines.append("")
        lines.extend(["### AI 예상 스코어", f"{score['home']}-{score['away']}"])
        if reasoning:
            lines.append("")
            lines.extend(f"- {item}" for item in reasoning)
    elif forecast:
        diagnostics.append("예상 스코어를 제시하지 않았습니다(값을 만들지 않음).")

    body = "\n".join(lines).strip()
    structured: dict[str, Any] = {
        "forecast": {
            "lean": (
                None
                if score is None
                else (
                    "home"
                    if score["home"] > score["away"]
                    else ("away" if score["away"] > score["home"] else "draw")
                )
            ),
            "score": None if score is None else f"{score['home']}-{score['away']}",
            "reasoning": reasoning,
        },
        "forecast_evidence": forecast_evidence,
    }
    # 설계 §78의 필수 본문은 "경기 전망 + AI 예상 스코어"다. 전망 문장만 있고 스코어가
    # 없으면 **이 섹션은 아직 준비되지 않은 초안**이다(검토 F4). 스코어를 만들지 않고,
    # 부분 본문은 보존하되 `insufficient`·사유를 남겨 정상 완료로 표시되지 않게 한다.
    missing_score = score is None
    if not forecast:
        unavailable_reason = "AI 전망 문장이 응답에 없어 본문을 만들지 않았습니다."
    elif missing_score:
        unavailable_reason = (
            "AI 예상 스코어가 응답에 없어 필수 본문(경기 전망·예상 스코어)을 채우지"
            " 못했습니다. 값을 만들지 않았고, 전망 문장만 보존합니다."
        )
        diagnostics.append(
            "필수 항목(AI 예상 스코어)이 없어 이 섹션을 ready로 표시하지 않았습니다."
        )
    else:
        unavailable_reason = None
    quality = (
        QualityStatus.READY if (forecast and not missing_score) else QualityStatus.INSUFFICIENT
    )
    return SectionDraft(
        section_id=section_id,
        module_id=module_id,
        title="AI 경기 전망",
        body=body,
        sources=(),
        structured=structured,
        quality=quality,
        unavailable_reason=unavailable_reason,
        prompt_version=prompt_version,
        diagnostics=tuple(diagnostics),
        delivery=delivery,
        mode=_mode_value(transport),
        external_calls=call.attempts,
    )


def _score_of(value: Any) -> tuple[dict[str, int] | None, list[str]]:
    """예상 스코어를 홈·원정 정수로 읽는다. 숫자를 만들지 않는다."""
    if not isinstance(value, Mapping):
        if value not in (None, ""):
            return None, ["예상 스코어 형식이 객체가 아니어서 비웠습니다."]
        return None, []
    home = value.get("home")
    away = value.get("away")
    if isinstance(home, bool) or isinstance(away, bool):
        return None, ["예상 스코어에 정수가 아닌 값이 있어 비웠습니다."]
    if not isinstance(home, int) or not isinstance(away, int):
        return None, ["예상 스코어 홈·원정 정수가 모두 있지 않아 비웠습니다."]
    if home < 0 or away < 0:
        return None, ["예상 스코어에 음수가 있어 비웠습니다."]
    return {"home": home, "away": away}, []


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------


def build_bundle_section(
    *,
    section_id: str,
    bundle: Any,
    transport: provider.ProviderTransport | None,
    context: ExecutionContext,
    budget: RunBudget,
    session: Session | None = None,
    upstream: Mapping[str, Any] | None = None,
    fixture_names: Mapping[str, Any] | None = None,
    resolver: Any = None,
    player_candidates: Sequence[Mapping[str, Any]] | None = None,
    limits: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    provider_odds: Any = None,
) -> SectionDraft:
    """정보 원문 묶음에서 섹션 하나를 만든다(계획 PS-03의 유일한 진입점).

    - `section_id`는 `SECTION_IDS` 중 하나다. 모르면 `BundleSectionError`.
    - 모델을 쓰는 섹션은 `provider.request_model`만 통과한다(검색 도구 없음).
    - 배당(`section_odds`)은 모델을 부르지 않는다.
    - `resolver`는 기존 DB 한국어 이름 해석기(`DisplayNames`)를 그대로 넣는다.
      없으면 원래 표기를 유지한다(번역·음차를 만들지 않는다).
    - `fixture_names`는 팀 표시 이름 주입값이다(없으면 묶음의 DB 팀 이름을 쓴다).
    - `player_candidates`는 호출자가 DB 통계에서 이미 만든 선수 후보
      (`player_id`·`team_id`·`display_name_ko`·기록 값)다. 주면 묶음의 `roster`보다
      **우선**한다. 주지 않으면 묶음의 `roster`를 쓴다. 어느 쪽이든 없는 값을 만들지 않는다.
    - `upstream`은 최종 전망이 읽는 앞 섹션 결과다(`SectionDraft`/저장 payload/구조화 dict).
    - 호출하지 않기로 확정된 섹션은 예산 예약을 반환하고(새 상한 없음) 사유를 남긴다.
    """
    if section_id not in SUPPORTED_SECTION_IDS:
        raise BundleSectionError(f"section {section_id!r} has no bundle implementation")
    if section_id == bundle_contract.SECTION_ODDS:
        return _odds_section(
            payload=_as_payload(bundle),
            transport=transport,
            provider_odds=provider_odds,
        )

    if transport is None:
        return SectionDraft(
            section_id=section_id,
            module_id=_MODULE_IDS[section_id],
            title=_TITLES[section_id],
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "모델 전송 계층이 없어 이 섹션의 모델 요청을 보내지 않았습니다."
            ),
            prompt_version=_PROMPTS[section_id][1],
            diagnostics=("model transport is missing",),
            mode="none",
        )

    payload = _as_payload(bundle)
    material = _db_material(payload, resolver=resolver)
    if player_candidates:
        # 호출자가 이미 만든 후보를 그대로 쓴다(여기서 DB를 다시 조회하지 않는다).
        material = replace(
            material,
            roster=tuple(
                dict(row) for row in player_candidates if isinstance(row, Mapping)
            ),
        )
    fixture_values = _fixture_values(payload, fixture_names)
    common = {
        "payload": payload,
        "context": context,
        "transport": transport,
        "budget": budget,
        "session": session,
        "fixture_values": fixture_values,
        "material": material,
        "now": now,
    }
    if section_id == bundle_contract.SECTION_PLAYERS:
        return _players_section(**common, resolver=resolver)
    if section_id == bundle_contract.SECTION_AVAILABILITY:
        return _availability_section(**common, resolver=resolver)
    if section_id == bundle_contract.SECTION_OUTLOOK:
        return _outlook_section(**common)
    return _forecast_section(**common, upstream=upstream)


_MODULE_IDS: Mapping[str, str | None] = {
    bundle_contract.SECTION_PLAYERS: "R4",
    bundle_contract.SECTION_AVAILABILITY: "R2",
    bundle_contract.SECTION_OUTLOOK: "R3",
    bundle_contract.SECTION_ODDS: None,
    bundle_contract.SECTION_AI_FORECAST: "S1",
}

_TITLES: Mapping[str, str] = {
    bundle_contract.SECTION_PLAYERS: "주목 선수",
    bundle_contract.SECTION_AVAILABILITY: "부상·결장 영향",
    bundle_contract.SECTION_OUTLOOK: "외부 매체 전망",
    bundle_contract.SECTION_ODDS: "배당 현황",
    bundle_contract.SECTION_AI_FORECAST: "AI 경기 전망",
}

# `limits` 인자는 구간 선택 상한을 실행별로 좁힐 때만 쓴다(기본은 계약 상수).
# `_select_passages`에 전달되도록 각 섹션 빌더가 같은 값을 쓴다.
