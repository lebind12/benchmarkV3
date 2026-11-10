"""R1 경기력·주목 선수 조사 (section_form).

이 모듈이 하는 일은 **한 번의 정상 모델 호출**로 경기력·관전 포인트·주목 선수를
조사하는 것이다. 호출은 공통 경로 `provider.request_model` -> `execute_request`를
통해서만 나가므로 예산·시도·원문 기록이 한 곳에 남는다.

정직성 규칙(설계 §5·§8):

- 새 사실을 만들지 않는다. 근거 없는 선수 평가(최고·최다 같은 단정)는 채택하지 않고
  사유와 함께 제외한다.
- 오래된 경기 소식은 최근 흐름 근거로 쓰지 않는다. 기준 시각(킥오프 - 7일)보다 이전
  자료는 제외하고 사유를 남긴다.
- API 자료가 있어도 매체·맥락 검색(Google Search grounding)을 시도한다. 검색 결과가
  없으면 그 사실을 남기고 API 사실만으로 결과를 만든다.
- 출처 URL은 grounding이 준 실제 URL만 쓴다. 만들어 넣지 않는다.
- 결과에는 다음 단계로 넘길 정확한 출처 식별자(snapshot_id, claim_id, URL)를 담는다.

`research_form`은 `FormResearch`를 돌려준다. `FormResearch.to_module_result`가 R1의
`ModuleResult` 계약을 만든다. 노드 어댑터(`form_node`)는 이것을 `NodeOutcome`으로
옮겨 공통 실행기가 `preview_results`에 저장하게 한다.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from string import Template
from typing import Any, Iterable, Mapping, Sequence

from app.preview import artifacts as artifact_store
from app.preview import provider
from app.preview.contracts import (
    CONTRACT_VERSION,
    ClaimDecision,
    ClaimKind,
    CoverageEntry,
    CoverageState,
    EvidenceClaim,
    ExecutionContext,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    QualityStatus,
    compute_input_hash,
)
from app.preview.modules import module_versions
from app.preview.retry import RunBudget

__all__ = [
    "FORM_IMPLEMENTATION_VERSION",
    "FORM_MODULE_ID",
    "FORM_PROMPT_VERSION",
    "FormFacts",
    "FormResearch",
    "form_node",
    "load_prompt",
    "research_form",
]

FORM_MODULE_ID = "R1"
FORM_IMPLEMENTATION_VERSION, FORM_PROMPT_VERSION = module_versions(FORM_MODULE_ID)
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "form.md"

# 최근 맥락 기준. 킥오프 7일 이전 자료는 최근 흐름 근거가 아니다(계획 §5).
RECENT_CONTEXT_WINDOW = timedelta(days=7)

# 근거 없이 쓰면 안 되는 선수 단정 표현. 하나라도 있으면 근거를 요구한다.
SUPERLATIVE_PATTERNS = (
    "세계 최고",
    "리그 최고",
    "최고의",
    "최강",
    "무결점",
    "역대급",
    "압도적",
    "월드클래스",
    "월드 클래스",
)

# 검색 근거가 필요한 매체·맥락 신호. 이 신호가 있는 항목은 URL 근거를 요구한다.
SEARCH_EVIDENCE_HINT = re.compile(r"보도|매체|기사|인터뷰|발언|전망|소식")
DATE_PATTERN = re.compile(r"(20\d{2})-(\d{2})-(\d{2})")

MAX_WATCH_POINTS = 3
MAX_HOT_PLAYERS = 3


class FormResearchError(ValueError):
    """모델 응답을 R1 결과로 해석할 수 없다. 빈 성공으로 바꾸지 않는다."""


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 입력 자료
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Fact:
    """프롬프트에 넣는 API 사실 한 줄. `fact_id`가 다음 단계까지 이어진다."""

    fact_id: str
    text: str
    snapshot_id: str
    collected_at: datetime | None = None
    subject_team_id: int | None = None
    kind: ClaimKind = ClaimKind.FACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "text": self.text,
            "snapshot_id": self.snapshot_id,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "subject_team_id": self.subject_team_id,
            "kind": self.kind.value,
        }


@dataclass(frozen=True)
class FormFacts:
    """R1이 쓰는 공유 자료 묶음(D0 성격). 수집 시각·경기 식별자를 함께 둔다."""

    fixture_id: int
    league_id: int
    season: int
    home_team_id: int
    away_team_id: int
    kickoff_at: datetime
    home_team: str
    away_team: str
    league: str | None
    facts: tuple[Fact, ...] = ()
    snapshot_ids: tuple[str, ...] = ()
    collected_at: datetime | None = None
    source_note: str | None = None

    @property
    def fixture_label(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    def fact_text_block(self) -> str:
        if not self.facts:
            return "API 자료 없음. 확인된 구조화 사실이 없으니 검색 근거만 사용한다."
        lines = []
        for fact in self.facts:
            collected = (
                f" (수집 {fact.collected_at.isoformat()})" if fact.collected_at else ""
            )
            lines.append(f"- {fact.fact_id}: {fact.text}{collected}")
        return "\n".join(lines)

    def allowed_evidence_ids(self) -> set[str]:
        return {fact.fact_id for fact in self.facts}


# --------------------------------------------------------------------------
# 결과
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FormResearch:
    """R1 조사 결과. 사실·해석·불확실성·출처를 분리해 담는다."""

    facts: FormFacts
    claims: tuple[EvidenceClaim, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    watch_points: tuple[Mapping[str, Any], ...] = ()
    hot_players: tuple[Mapping[str, Any], ...] = ()
    recent_form: tuple[Mapping[str, Any], ...] = ()
    match_importance: str | None = None
    sources: tuple[Mapping[str, Any], ...] = ()
    grounding: Mapping[str, Any] = field(default_factory=dict)
    search_note: str | None = None
    unavailable_reason: str | None = None
    quality: QualityStatus = QualityStatus.PENDING
    external_calls: int = 1
    implementation_version: str = FORM_IMPLEMENTATION_VERSION
    prompt_version: str = FORM_PROMPT_VERSION

    @property
    def unavailable(self) -> bool:
        return self.unavailable_reason is not None

    @property
    def adopted_claims(self) -> tuple[EvidenceClaim, ...]:
        return tuple(c for c in self.claims if c.decision is ClaimDecision.ADOPTED)

    @property
    def source_ids(self) -> tuple[str, ...]:
        """다음 단계로 넘기는 정확한 근거 식별자. 만든 값이 아니라 실제 참조다."""
        ids: list[str] = []
        for claim in self.adopted_claims:
            for snapshot_id in claim.snapshot_ids:
                text = str(snapshot_id)
                if text not in ids:
                    ids.append(text)
        for source in self.sources:
            url = source.get("url")
            if isinstance(url, str) and url and url not in ids:
                ids.append(url)
        return tuple(ids)

    def to_module_result(self, *, module_input: ModuleInput, context: ExecutionContext,
                         module_execution_id: uuid.UUID, version: int = 1) -> ModuleResult:
        """R1의 `ModuleResult` 계약. 실행 성공과 근거 확보를 따로 표현한다."""
        return ModuleResult(
            result_id=uuid.uuid4(),
            module_id=FORM_MODULE_ID,
            module_execution_id=module_execution_id,
            run_id=context.run_id,
            version=version,
            input_hash=module_input.input_hash,
            status=(
                ModuleStatus.FAILED if self.unavailable else ModuleStatus.SUCCEEDED
            ),
            quality=self.quality,
            claims=self.claims,
            coverage=self.coverage,
            diagnostics=self.diagnostics,
            implementation_version=self.implementation_version,
            prompt_version=self.prompt_version,
            contract_version=CONTRACT_VERSION,
            payload=dict(self.payload()),
        )

    def api_source_rows(self) -> tuple[Mapping[str, Any], ...]:
        """API 자료 출처 행. URL이 없으므로 스냅샷 참조와 수집 시각을 남긴다."""
        rows: list[Mapping[str, Any]] = []
        seen: set[str] = set()
        for fact in self.facts.facts:
            if not fact.snapshot_id or fact.snapshot_id in seen:
                continue
            seen.add(fact.snapshot_id)
            rows.append(
                {
                    "snapshot_id": fact.snapshot_id,
                    "label": "API-Football 저장 자료",
                    "collected_at": (
                        fact.collected_at.isoformat() if fact.collected_at else None
                    ),
                }
            )
        return tuple(rows)

    def payload(self) -> Mapping[str, Any]:
        return {
            "fixture": {
                "fixture_id": self.facts.fixture_id,
                "league_id": self.facts.league_id,
                "season": self.facts.season,
                "home_team_id": self.facts.home_team_id,
                "away_team_id": self.facts.away_team_id,
                "kickoff_at": self.facts.kickoff_at.isoformat(),
                "home_team": self.facts.home_team,
                "away_team": self.facts.away_team,
                "league": self.facts.league,
            },
            "match_importance": self.match_importance,
            "recent_form": [dict(item) for item in self.recent_form],
            "watch_points": [dict(item) for item in self.watch_points],
            "hot_players": [dict(item) for item in self.hot_players],
            "uncertainties": list(self.uncertainties),
            "search_note": self.search_note,
            "sources": [dict(item) for item in self.sources],
            "api_sources": [dict(item) for item in self.api_source_rows()],
            "grounding": dict(self.grounding),
            "source_ids": list(self.source_ids),
            "claims": [claim.to_dict() for claim in self.claims],
            "coverage": [entry.to_dict() for entry in self.coverage],
            "diagnostics": list(self.diagnostics),
            "implementation_version": self.implementation_version,
            "prompt_version": self.prompt_version,
        }


# --------------------------------------------------------------------------
# 검증 도우미
# --------------------------------------------------------------------------


def _entry_text(item: Mapping[str, Any]) -> str:
    parts = [
        str(item.get(key) or "")
        for key in ("title", "detail", "summary", "reason", "player")
    ]
    return " ".join(part for part in parts if part)


def _parse_date(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _dates_in_text(text: str) -> tuple[datetime, ...]:
    found: list[datetime] = []
    for match in DATE_PATTERN.finditer(text):
        try:
            found.append(
                datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)),
                         tzinfo=timezone.utc)
            )
        except ValueError:
            continue
    return tuple(found)


def _superlative_hits(text: str) -> tuple[str, ...]:
    return tuple(pattern for pattern in SUPERLATIVE_PATTERNS if pattern in text)


def _old_news_reason(
    item: Mapping[str, Any], kickoff_at: datetime
) -> str | None:
    """킥오프 7일 이전 소식을 최근 흐름 근거로 쓰지 않는다.

    날짜가 명시된 과거 맞대결·기록은 배경 자료로 허용한다. 그래서 `background=True`
    인 항목은 제외하지 않는다. 맥락(보도·기사) 신호가 있고 날짜가 오래된 경우만
    최근 흐름 근거로 인정하지 않는다.
    """
    if bool(item.get("background")):
        return None
    text = _entry_text(item)
    if not SEARCH_EVIDENCE_HINT.search(text):
        return None
    threshold = kickoff_at - RECENT_CONTEXT_WINDOW
    dates = list(_dates_in_text(text))
    declared = _parse_date(item.get("claimed_at"))
    if declared is not None:
        dates.append(declared)
    if any(moment < threshold for moment in dates):
        return (
            f"킥오프 7일 이전({threshold.date().isoformat()} 이전) 자료는 최근 흐름"
            " 근거로 쓰지 않습니다."
        )
    return None


def _evidence_ids(item: Mapping[str, Any]) -> tuple[str, ...]:
    raw = item.get("evidence")
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        return ()
    return tuple(str(value) for value in raw if isinstance(value, str) and value.strip())


# --------------------------------------------------------------------------
# 프롬프트 조립
# --------------------------------------------------------------------------


def build_contents(facts: FormFacts, *, now: datetime) -> list[dict[str, Any]]:
    template = load_prompt()
    values = {
        "fixture_label": facts.fixture_label,
        "fixture_id": facts.fixture_id,
        "league_id": facts.league_id,
        "season": facts.season,
        "kickoff_at": facts.kickoff_at.isoformat(),
        "home_team": facts.home_team,
        "home_team_id": facts.home_team_id,
        "away_team": facts.away_team,
        "away_team_id": facts.away_team_id,
        "today": now.date().isoformat(),
        "api_facts": facts.fact_text_block(),
    }
    try:
        prompt = Template(template).substitute(**values)
    except KeyError as exc:  # pragma: no cover - 프롬프트 편집 실수 방지
        raise FormResearchError(f"prompt placeholder missing: {exc}") from None
    return [{"role": "user", "parts": [{"text": prompt}]}]


# --------------------------------------------------------------------------
# grounding 해석
# --------------------------------------------------------------------------


def _candidates(raw: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    candidates = raw.get("candidates")
    return candidates if isinstance(candidates, Sequence) else ()


def parse_grounding(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    """수신 원문에서 검색 질의·출처·support·Search Suggestions를 보존한다.

    제공자의 grounding metadata를 그대로 옮긴다. 여기서 링크가 있다고 기사를 읽은
    것으로 표시하지 않는다(설계 §5).
    """
    result: dict[str, Any] = {
        "attempted": True,
        "web_search_queries": [],
        "sources": [],
        "supports": [],
        "search_entry_point": None,
        "note": None,
    }
    if not isinstance(raw, Mapping):
        result["note"] = "수신 원문이 없어 grounding metadata를 확인하지 못했습니다."
        return result
    metadata: Mapping[str, Any] | None = None
    for candidate in _candidates(raw):
        if not isinstance(candidate, Mapping):
            continue
        found = candidate.get("grounding_metadata") or candidate.get("groundingMetadata")
        if isinstance(found, Mapping):
            metadata = found
            break
    if metadata is None:
        result["note"] = "제공자 응답에 grounding metadata가 없습니다."
        return result

    queries = metadata.get("web_search_queries") or metadata.get("webSearchQueries") or []
    result["web_search_queries"] = [str(q) for q in queries if isinstance(q, str)]

    chunks = metadata.get("grounding_chunks") or metadata.get("groundingChunks") or []
    sources: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            continue
        web = chunk.get("web")
        if isinstance(web, Mapping) and web.get("uri"):
            sources.append(
                {
                    "url": str(web.get("uri")),
                    "title": web.get("title"),
                    "domain": web.get("domain"),
                }
            )
    result["sources"] = sources

    supports = metadata.get("grounding_supports") or metadata.get("groundingSupports") or []
    result["supports"] = [dict(item) for item in supports if isinstance(item, Mapping)]

    entry = metadata.get("search_entry_point") or metadata.get("searchEntryPoint")
    if isinstance(entry, Mapping):
        result["search_entry_point"] = {
            "rendered_content": entry.get("rendered_content")
            or entry.get("renderedContent"),
            "sdk_blob": entry.get("sdk_blob") or entry.get("sdkBlob"),
        }
    if not sources:
        result["note"] = (
            "제공자가 검색 질의는 실행했지만 인용 출처(chunk)를 반환하지 않았습니다."
            " 출처 없는 내용은 사실로 채택하지 않습니다."
            if result["web_search_queries"]
            else "검색 질의가 응답에 없고 인용 출처도 없습니다."
        )
        result["citation_chunks_missing"] = True
    return result


def _grounding_urls(grounding: Mapping[str, Any]) -> set[str]:
    return {
        str(source.get("url"))
        for source in grounding.get("sources") or ()
        if isinstance(source, Mapping) and source.get("url")
    }


# --------------------------------------------------------------------------
# 모델 응답 해석
# --------------------------------------------------------------------------


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return stripped


def parse_model_json(text: str) -> Mapping[str, Any]:
    body = _strip_code_fence(text)
    start = body.find("{")
    end = body.rfind("}")
    if start < 0 or end < start:
        raise FormResearchError("모델 응답에서 JSON 객체를 찾지 못했습니다.")
    try:
        parsed = json.loads(body[start : end + 1])
    except ValueError as exc:
        raise FormResearchError(f"모델 응답 JSON을 해석하지 못했습니다: {exc}") from None
    if not isinstance(parsed, Mapping):
        raise FormResearchError("모델 응답이 JSON 객체가 아닙니다.")
    return parsed


@dataclass
class _Validated:
    claims: list[EvidenceClaim]
    watch_points: list[dict[str, Any]]
    hot_players: list[dict[str, Any]]
    recent_form: list[dict[str, Any]]
    uncertainties: list[str]
    diagnostics: list[str]
    coverage: list[CoverageEntry]


def _claim(
    claim_id: str,
    kind: ClaimKind,
    text: str,
    *,
    snapshot_ids: Iterable[uuid.UUID] = (),
    decision: ClaimDecision = ClaimDecision.ADOPTED,
    reason: str | None = None,
    source_url: str | None = None,
    subject_team_id: int | None = None,
    subject_player_id: int | None = None,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        kind=kind,
        text=text,
        snapshot_ids=tuple(snapshot_ids),
        decision=decision,
        decision_reason=reason,
        subject_team_id=subject_team_id,
        subject_player_id=subject_player_id,
        source_url=source_url,
    )


def _validate_item(
    *,
    index: int,
    item: Mapping[str, Any],
    kind: ClaimKind,
    label: str,
    facts: FormFacts,
    allowed_ids: set[str],
    url_map: Mapping[str, str],
    grounding_urls: set[str],
    kickoff_at: datetime,
    require_search: bool,
) -> tuple[EvidenceClaim | None, str | None]:
    """항목 하나를 검증한다. 채택할 수 없으면 (None, 사유)를 돌려준다."""
    text = _entry_text(item).strip()
    if not text:
        return None, "내용이 비어 있어 채택하지 않았습니다."

    reason = _old_news_reason(item, kickoff_at)
    if reason:
        return None, reason

    evidence = _evidence_ids(item)
    usable = [value for value in evidence if value in allowed_ids or value in grounding_urls]
    # snapshot은 fact마다 붙은 실제 snapshot_id를 그대로 쓴다. 순서로 짝짓지 않는다.
    snapshot_ids = [
        uuid.UUID(fact.snapshot_id)
        for fact in facts.facts
        if fact.fact_id in usable and fact.snapshot_id
    ]
    url = next((value for value in usable if value in grounding_urls), None)
    if url is None:
        for value in usable:
            mapped = url_map.get(value)
            if mapped in grounding_urls:
                url = mapped
                break

    if not snapshot_ids and not url:
        return None, "근거 식별자(snapshot 또는 검색 출처 URL)가 없어 채택하지 않았습니다."
    if require_search and url is None and SEARCH_EVIDENCE_HINT.search(text):
        return None, "매체·맥락 진술인데 검색 출처 URL이 없어 채택하지 않았습니다."

    return (
        _claim(
            f"r1-{label}-{index}",
            kind,
            text,
            snapshot_ids=snapshot_ids,
            source_url=url,
        ),
        None,
    )


def validate_response(
    payload: Mapping[str, Any],
    *,
    facts: FormFacts,
    grounding: Mapping[str, Any],
    now: datetime,
) -> _Validated:
    """모델 JSON을 채택/제외로 나눈다. 제외 사유는 지우지 않고 남긴다."""
    allowed_ids = facts.allowed_evidence_ids()
    grounding_urls = _grounding_urls(grounding)
    url_map = {
        str(source.get("url")): str(source.get("url"))
        for source in grounding.get("sources") or ()
        if isinstance(source, Mapping) and source.get("url")
    }
    kickoff_at = facts.kickoff_at
    warnings: list[str] = []
    claims: list[EvidenceClaim] = []
    watch_points: list[dict[str, Any]] = []
    hot_players: list[dict[str, Any]] = []
    recent_form: list[dict[str, Any]] = []
    uncertainties = [str(item) for item in payload.get("uncertainties") or () if str(item).strip()]
    diagnostics: list[str] = []

    def note_exclusion(label: str, reason: str) -> None:
        diagnostics.append(f"{label}: {reason}")

    ctx = payload.get("match_context") or {}
    if isinstance(ctx, Mapping) and str(ctx.get("importance") or "").strip():
        claim, reason = _validate_item(
            index=0,
            item={"detail": ctx.get("importance"), "evidence": ctx.get("importance_evidence")},
            kind=ClaimKind.AI_INTERPRETATION,
            label="importance",
            facts=facts,
            allowed_ids=allowed_ids,
            url_map=url_map,
            grounding_urls=grounding_urls,
            kickoff_at=kickoff_at,
            require_search=False,
        )
        if claim:
            claims.append(claim)
        elif reason:
            note_exclusion("이번 경기 의미", reason)

    for index, item in enumerate(payload.get("recent_form") or ()):
        if not isinstance(item, Mapping):
            continue
        claim, reason = _validate_item(
            index=index,
            item=item,
            kind=ClaimKind.FACT,
            label="form",
            facts=facts,
            allowed_ids=allowed_ids,
            url_map=url_map,
            grounding_urls=grounding_urls,
            kickoff_at=kickoff_at,
            require_search=True,
        )
        if claim is None:
            note_exclusion(f"최근 흐름 {index + 1}", reason or "채택 근거 없음")
            continue
        claims.append(claim)
        recent_form.append(
            {
                "team": str(item.get("team") or ""),
                "summary": str(item.get("summary") or ""),
                "claim_id": claim.claim_id,
                "evidence": list(claim.snapshot_ids) and [str(s) for s in claim.snapshot_ids]
                or ([claim.source_url] if claim.source_url else []),
                "source_url": claim.source_url,
            }
        )

    for index, item in enumerate(payload.get("watch_points") or ()):
        if not isinstance(item, Mapping):
            continue
        if len(watch_points) >= MAX_WATCH_POINTS:
            break
        claim, reason = _validate_item(
            index=index,
            item=item,
            kind=ClaimKind.AI_INTERPRETATION,
            label="watch",
            facts=facts,
            allowed_ids=allowed_ids,
            url_map=url_map,
            grounding_urls=grounding_urls,
            kickoff_at=kickoff_at,
            require_search=True,
        )
        if claim is None:
            note_exclusion(f"관전 포인트 {index + 1}", reason or "채택 근거 없음")
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        claims.append(
            _claim(
                f"{claim.claim_id}-detail",
                ClaimKind.AI_INTERPRETATION,
                f"{title}: {detail}" if title and detail else claim.text,
                snapshot_ids=claim.snapshot_ids,
                source_url=claim.source_url,
            )
        )
        watch_points.append(
            {
                "title": title or detail[:40],
                "detail": detail,
                "claim_id": claim.claim_id,
                "source_url": claim.source_url,
            }
        )

    for index, item in enumerate(payload.get("hot_players") or ()):
        if not isinstance(item, Mapping):
            continue
        if len(hot_players) >= MAX_HOT_PLAYERS:
            break
        player = str(item.get("player") or "").strip()
        if not player:
            note_exclusion(f"주목 선수 {index + 1}", "선수 이름이 비어 있습니다.")
            continue
        text = f"{player}: {item.get('reason') or ''}".strip()
        hits = _superlative_hits(text)
        basis = str(item.get("superlative_basis") or "").strip()
        if hits and not basis:
            note_exclusion(
                f"주목 선수 {player}",
                f"단정 표현({', '.join(hits)})에 대한 근거가 없어 채택하지 않았습니다.",
            )
            continue
        claim, reason = _validate_item(
            index=index,
            item={"detail": item.get("reason"), "evidence": item.get("evidence")},
            kind=ClaimKind.AI_INTERPRETATION,
            label="player",
            facts=facts,
            allowed_ids=allowed_ids,
            url_map=url_map,
            grounding_urls=grounding_urls,
            kickoff_at=kickoff_at,
            require_search=False,
        )
        if claim is None:
            note_exclusion(f"주목 선수 {player}", reason or "채택 근거 없음")
            continue
        claims.append(
            _claim(
                claim.claim_id,
                ClaimKind.AI_INTERPRETATION,
                text,
                snapshot_ids=claim.snapshot_ids,
                source_url=claim.source_url,
            )
        )
        hot_players.append(
            {
                "player": player,
                "team": str(item.get("team") or "").strip() or None,
                "reason": str(item.get("reason") or "").strip(),
                "claim_id": claim.claim_id,
                "source_url": claim.source_url,
                "superlative_basis": basis or None,
            }
        )

    search_note = payload.get("search_note")
    if isinstance(search_note, str) and search_note.strip():
        warnings.append(search_note.strip())

    coverage: list[CoverageEntry] = []
    if grounding_urls:
        search_state = CoverageState.AVAILABLE
        search_detail = f"검색 출처 {len(grounding_urls)}건"
    elif grounding.get("citation_chunks_missing"):
        # 검색은 수행됐지만 인용 출처가 응답에 없다. '검색 미발견'과 구분해 남긴다.
        search_state = CoverageState.UNKNOWN
        search_detail = grounding.get("note") or "검색 인용 출처를 확인하지 못했습니다."
    else:
        search_state = CoverageState.SEARCH_NOT_FOUND
        search_detail = grounding.get("note") or "검색 출처를 확보하지 못했습니다."
    coverage.append(
        CoverageEntry(topic="매체·맥락 검색", state=search_state, detail=search_detail)
    )
    coverage.append(
        CoverageEntry(
            topic="경기력·관전 포인트",
            state=CoverageState.AVAILABLE if watch_points or recent_form else (
                CoverageState.API_NOT_PROVIDED
            ),
            detail=(
                f"관전 포인트 {len(watch_points)}건, 최근 흐름 {len(recent_form)}건"
                if watch_points or recent_form
                else "채택할 근거가 없어 항목을 만들지 않았습니다."
            ),
        )
    )
    coverage.append(
        CoverageEntry(
            topic="주목 선수",
            state=CoverageState.AVAILABLE if hot_players else CoverageState.API_NOT_PROVIDED,
            detail=(
                f"{len(hot_players)}명"
                if hot_players
                else "근거 있는 선수 평가를 만들지 못했습니다."
            ),
        )
    )
    return _Validated(
        claims=claims,
        watch_points=watch_points,
        hot_players=hot_players,
        recent_form=recent_form,
        uncertainties=uncertainties,
        diagnostics=diagnostics + warnings,
        coverage=coverage,
    )


# --------------------------------------------------------------------------
# 실행
# --------------------------------------------------------------------------


def _api_fact_claims(facts: FormFacts) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for fact in facts.facts:
        if not fact.snapshot_id:
            continue
        claims.append(
            _claim(
                fact.fact_id,
                ClaimKind.FACT,
                fact.text,
                snapshot_ids=[uuid.UUID(fact.snapshot_id)],
                reason="저장된 API 사실입니다. 수집 시각을 함께 보존합니다.",
                subject_team_id=fact.subject_team_id,
            )
        )
    return claims


def _result_sources(grounding: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    sources: list[Mapping[str, Any]] = []
    for source in grounding.get("sources") or ():
        if not isinstance(source, Mapping) or not source.get("url"):
            continue
        label = source.get("title") or source.get("domain") or str(source.get("url"))
        sources.append(
            {
                "label": str(label),
                "url": str(source.get("url")),
                "kind": "search",
                "note": (
                    "Google Search grounding이 제공한 출처입니다."
                    " 링크만으로 원문 전체를 확인한 것으로 표시하지 않습니다."
                ),
            }
        )
    return tuple(sources)


def research_form(
    module_input: ModuleInput,
    context: ExecutionContext,
    *,
    facts: FormFacts,
    transport: provider.ProviderTransport,
    budget: RunBudget,
    session=None,
    actor_id: int | None = None,
    module_execution_id: uuid.UUID | None = None,
    now: datetime | None = None,
    logical_call_id: str = "R1-form",
    generation_config_override: Mapping[str, Any] | None = None,
) -> FormResearch:
    """R1 정상 호출 1회. 모델 호출은 `request_model`만 통과한다.

    `generation_config_override`는 **제품 기본값을 바꾸지 않는 주입 지점**이다. 넘기지
    않으면(기본) 아래 기본 생성 설정을 그대로 쓴다. 한정 실험처럼 기본과 다른 설정을
    한 번만 시험할 때, 같은 요청 경로·예산·기록을 그대로 지나가게 하려고 둔다.
    """
    moment = now or datetime.now(timezone.utc)
    contents = build_contents(facts, now=moment)
    generation = {
        # 매체·맥락 검색을 API 자료 유무와 무관하게 시도한다(설계 §5).
        "temperature": 0.2,
        "response_mime_type": "application/json",
        "tools": [{"google_search": {}}],
    }
    if generation_config_override is not None:
        generation = dict(generation_config_override)
    result = provider.request_model(
        logical_call_id=logical_call_id,
        contents=contents,
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=FORM_MODULE_ID,
        operation="research_form",
        prompt_version=FORM_PROMPT_VERSION,
        generation_config=generation,
        module_execution_id=module_execution_id,
        actor_id=actor_id,
        now=lambda: moment,
    )

    api_claims = _api_fact_claims(facts)
    if not result.ok or not result.text:
        reason = result.stopped_reason or (
            result.response.error_message or "모델 호출이 성공하지 않았습니다."
        )
        return FormResearch(
            facts=facts,
            claims=tuple(api_claims),
            coverage=(
                CoverageEntry(
                    topic="경기력·관전 포인트",
                    state=CoverageState.CALL_ERROR,
                    detail=reason,
                ),
                CoverageEntry(
                    topic="매체·맥락 검색",
                    state=CoverageState.CALL_ERROR,
                    detail="검색 조사를 완료하지 못했습니다.",
                ),
                CoverageEntry(
                    topic="주목 선수",
                    state=CoverageState.NOT_RUN,
                    detail="모델 호출이 성공하지 않아 만들지 않았습니다.",
                ),
            ),
            diagnostics=(f"R1 모델 호출 실패: {reason}",),
            grounding={"attempted": True, "note": "호출 실패로 grounding metadata가 없습니다."},
            unavailable_reason=(
                "경기력 조사 호출이 성공하지 않아 이 섹션의 본문을 만들 수 없습니다."
            ),
            quality=QualityStatus.INSUFFICIENT,
            external_calls=provider.sent_attempt_count(result, transport.mode),
        )

    raw = _load_raw_payload(session, result.response.raw_artifact_id)
    grounding = parse_grounding(raw)
    try:
        payload = parse_model_json(result.text)
    except FormResearchError as exc:
        return FormResearch(
            facts=facts,
            claims=tuple(api_claims),
            coverage=(
                CoverageEntry(
                    topic="경기력·관전 포인트",
                    state=CoverageState.VALIDATION_REJECTED,
                    detail=str(exc),
                ),
            ),
            diagnostics=(str(exc),),
            grounding=grounding,
            sources=_result_sources(grounding),
            unavailable_reason=(
                "모델 응답을 조사 결과로 해석하지 못해 본문을 만들지 않았습니다."
            ),
            quality=QualityStatus.INSUFFICIENT,
            external_calls=provider.sent_attempt_count(result, transport.mode),
        )

    validated = validate_response(payload, facts=facts, grounding=grounding, now=moment)
    claims = tuple(api_claims) + tuple(validated.claims)
    importance = None
    ctx = payload.get("match_context")
    if isinstance(ctx, Mapping):
        text = str(ctx.get("importance") or "").strip()
        importance = text or None

    no_evidence = not validated.watch_points and not validated.recent_form and not validated.hot_players
    return FormResearch(
        facts=facts,
        claims=claims,
        coverage=tuple(validated.coverage),
        diagnostics=tuple(validated.diagnostics),
        uncertainties=tuple(validated.uncertainties),
        watch_points=tuple(validated.watch_points),
        hot_players=tuple(validated.hot_players),
        recent_form=tuple(validated.recent_form),
        match_importance=importance,
        sources=_result_sources(grounding),
        grounding=grounding,
        search_note=payload.get("search_note") if isinstance(payload.get("search_note"), str) else None,
        unavailable_reason=(
            "채택할 근거를 확보하지 못해 이 섹션의 본문을 만들지 않았습니다."
            if no_evidence
            else None
        ),
        quality=QualityStatus.PENDING if no_evidence else QualityStatus.READY,
        external_calls=provider.sent_attempt_count(result, transport.mode),
    )


def _load_raw_payload(session, artifact_id: uuid.UUID | None) -> Mapping[str, Any] | None:
    """저장된 원문 응답을 grounding 해석용으로 다시 읽는다. 새 호출은 없다."""
    if session is None or artifact_id is None:
        return None
    from app.preview.models import PreviewArtifact

    row = session.get(PreviewArtifact, artifact_id)
    if row is None or row.body is None:
        return None
    try:
        parsed = json.loads(row.body)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, Mapping) else None


# --------------------------------------------------------------------------
# 섹션 노드 어댑터
# --------------------------------------------------------------------------


def form_node(
    *,
    facts: FormFacts,
    transport: provider.ProviderTransport,
    now: datetime | None = None,
    generation_config_override: Mapping[str, Any] | None = None,
):
    """runner가 쓰는 노드 어댑터. 노드는 한 번의 정상 호출만 한다.

    `generation_config_override`는 기본 제품 설정을 바꾸지 않기 위한 선택 인자다.
    넘기지 않으면 `research_form`이 정한 기본 생성 설정을 그대로 쓴다.
    """
    from app.preview.runner import NodeOutcome, SectionNodeContext, SectionState

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        fixture = (
            FixtureIdentity(
                fixture_id=facts.fixture_id,
                league_id=facts.league_id,
                season=facts.season,
                home_team_id=facts.home_team_id,
                away_team_id=facts.away_team_id,
                kickoff_at=facts.kickoff_at,
            )
            if facts.fixture_id
            else None
        )
        module_input = ModuleInput(
            module_id=FORM_MODULE_ID,
            fixture=fixture,
            snapshot_ids=tuple(uuid.UUID(sid) for sid in facts.snapshot_ids if sid),
            selected_result_ids=ctx.selected_result_ids,
            input_hash=compute_input_hash(
                {
                    "module_id": FORM_MODULE_ID,
                    "fixture_id": facts.fixture_id,
                    "snapshot_ids": list(facts.snapshot_ids),
                    "implementation": FORM_IMPLEMENTATION_VERSION,
                }
            ),
            prompt_version=FORM_PROMPT_VERSION,
            contract_version=CONTRACT_VERSION,
            implementation_version=FORM_IMPLEMENTATION_VERSION,
        )
        research = research_form(
            module_input,
            ctx.context,
            facts=facts,
            transport=transport,
            budget=ctx.budget,
            session=ctx.session,
            actor_id=ctx.actor_id,
            module_execution_id=ctx.module_execution_id,
            now=now,
            generation_config_override=generation_config_override,
        )
        # runner는 payload의 claims/coverage를 계약 객체로 저장한다. dict를 넣으면
        # ModuleResult 타입과 어긋나므로 여기서 계약 객체를 그대로 넘긴다.
        node_payload = dict(research.payload())
        node_payload["claims"] = list(research.claims)
        node_payload["coverage"] = list(research.coverage)
        return NodeOutcome(
            payload=node_payload,
            sources=research.sources,
            quality=research.quality,
            diagnostics=research.diagnostics,
            unavailable_reason=research.unavailable_reason,
            external_calls=research.external_calls,
        )

    return run
