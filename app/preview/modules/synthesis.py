"""MP-09 S1 프리뷰 종합.

입력은 **선택된 R1/R2/R3 결과 버전 + 그 결과가 참조하는 D0 스냅샷**뿐이다
(`validation.validate_evidence`가 만든 `ValidatedEvidence`). 이 모듈은 새 검색을
하지 않는다. 정상 경로의 모델 요청은 정확히 1회이며, 모든 호출은
`app.preview.provider.request_model`을 통과한다.

정직성 규칙(사용자 확정 기준):

- 관전 포인트·주목 선수 선정·예상 스코어는 **AI 판단**이다. 그 결론을 증명하는
  외부 보도를 요구하지 않는다.
- 판단 문장에 섞인 **새 수치·기록·부상 발생일**은 확인된 사실에 없으면 덜어낸다.
  "AI 해석"이라는 이름으로 새 사실을 들여보내지 않는다.
- 매체의 예상 스코어는 **그 매체가 실제로 그렇게 말했다는 근거(URL)** 가 있을 때만
  쓴다. 제공자(API-Football) 알고리즘 예측은 `api_prediction` 종류로 구분한다.
- 자료가 없는 보조 항목은 만들지 않는다. 독자용 응답에는 진단·ID·운영 안내가 없다.
- 근거 없는 핵심(경기 식별 또는 참조 있는 사실)이 없으면 완성 프리뷰로 만들지 않는다.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

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
    ModuleResult,
    ModuleStatus,
    PreviewDocument,
    QualityStatus,
    SourceSnapshot,
    compute_input_hash,
)
from app.preview import presentation
from app.preview.retry import RunBudget
from app.preview.validation import (
    EvidenceGap,
    SelectedResultInput,
    ValidatedEvidence,
    validate_evidence,
)

__all__ = [
    "COMPOSE_IMPLEMENTATION_VERSION",
    "IMPLEMENTATION_VERSION",
    "MODULE_ID",
    "OUTPUT_CONTRACT_VERSION",
    "PROMPT_VERSION",
    "SELECTED_INPUT_IMPLEMENTATION_VERSION",
    "S1Result",
    "SECTION_WORKFLOW_ID",
    "build_synthesis_implementations",
    "load_selected_results",
    "load_snapshots",
    "preview_payload_from_result",
    "synthesize_preview",
    "synthesis_prompt",
]

MODULE_ID = "S1"
# 결과 의미를 바꾸는 버전 축이다. 프롬프트·구현이 바뀌면 승인 후보 버전도 바뀐다.
IMPLEMENTATION_VERSION = "mp09-s1-1"
PROMPT_VERSION = "mp09-s1-prompt-1"
OUTPUT_CONTRACT_VERSION = "mp09-synthesis-output-1"
COMPOSE_IMPLEMENTATION_VERSION = "mp09-compose-1"
# 선택 결과 읽기·검증 노드 구현 버전. version_manifest가 같은 값을 승인 후보에 쓴다.
SELECTED_INPUT_IMPLEMENTATION_VERSION = "mp09-selected-inputs-1"

SECTION_WORKFLOW_ID = "section_synthesis"
LOGICAL_CALL_ID = "section_synthesis/research-s1"

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "synthesis.md"

MAX_WATCH_POINTS = 3
MAX_PLAYERS = 3

# 판단 문장에 새로 들어오면 안 되는 구체 수치·기록. 단위가 붙은 숫자만 본다.
_STAT_WITH_UNIT = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:골|도움|경기|승|패|무|위|득점|실점|개|회|장|분|%|명|점)"
)
_EXPLICIT_DATE = re.compile(r"20\d{2}\s*[-./]\s*\d{1,2}")
# 부상 발생 서술. 확인된 사실에 없으면 판단 문장에서 덜어낸다.
_INJURY_EVENT = re.compile(r"(?:부상|결장|이탈|수술)[^.!?]{0,20}(?:했다|했습니다|당했다|당했습니다)")

_JUDGMENT_LEAN = frozenset({"home", "draw", "away"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def synthesis_prompt(evidence: ValidatedEvidence, *, names: Mapping[str, Any] | None = None) -> str:
    """프롬프트 한 장. 자료는 검증된 모듈 결과의 채택 문장만 넣는다."""
    return _prompt_template().replace("{{CONTEXT}}", _evidence_context(evidence, names=names))


def _prompt_template() -> str:
    try:
        return _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:  # pragma: no cover - 파일이 없는 배포 사고
        return "조사 자료만으로 프리뷰를 종합하세요.\n\n{{CONTEXT}}"


def _evidence_context(
    evidence: ValidatedEvidence, *, names: Mapping[str, Any] | None = None
) -> str:
    lines: list[str] = []
    fixture = evidence.fixture
    if fixture is not None:
        names = names or {}
        home = _clean(names.get("home_team")) or f"team {fixture.home_team_id}"
        away = _clean(names.get("away_team")) or f"team {fixture.away_team_id}"
        lines.append(
            f"- 경기: {home} vs {away} (fixture {fixture.fixture_id}, 리그"
            f" {fixture.league_id}, 시즌 {fixture.season})"
        )
        lines.append(f"- 킥오프(UTC): {fixture.kickoff_at.isoformat()}")
    else:
        lines.append("- 경기 식별 정보가 없습니다.")

    for module in evidence.modules:
        lines.append("")
        lines.append(
            f"### {module.module_id} 조사 결과 (버전 {module.version},"
            f" 구현 {module.implementation_version})"
        )
        if not module.adopted:
            lines.append("- 채택된 근거 문장이 없습니다.")
            continue
        for claim in module.adopted:
            label = {
                ClaimKind.FACT: "사실",
                ClaimKind.AI_INTERPRETATION: "AI 해석",
                ClaimKind.EXTERNAL_FORECAST: "외부 전망",
                ClaimKind.API_PREDICTION: "제공자 알고리즘 예측",
            }.get(claim.kind, claim.kind.value)
            suffix = f" (출처 URL {claim.source_url})" if claim.source_url else ""
            lines.append(f"- [{claim.claim_id}] ({label}) {_clean(claim.text)}{suffix}")

    if evidence.gaps:
        # 자료 공백은 프롬프트에 넣지 않는다. 모델이 누락 안내 문장을 쓰지 않게 하기 위함이다.
        lines.append("")
        lines.append("- 일부 조사 자료는 이 입력에 포함되지 않았습니다. 없는 항목은 비우세요.")
    return "\n".join(lines)


def build_contents(evidence: ValidatedEvidence, *, names: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": synthesis_prompt(evidence, names=names)}]}]


def build_generation_config() -> dict[str, Any]:
    """S1 생성 설정. **검색 도구를 넣지 않는다**(새 조사·숨은 검색 금지)."""
    return {
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "response_mime_type": "application/json",
    }


# --------------------------------------------------------------------------
# 저장된 선택 결과 읽기 (외부 호출 없음)
# --------------------------------------------------------------------------


def _payload_claims(row_payload: Mapping[str, Any]) -> tuple[EvidenceClaim, ...]:
    claims: list[EvidenceClaim] = []
    for item in row_payload.get("claims") or ():
        if isinstance(item, EvidenceClaim):
            claims.append(item)
            continue
        if isinstance(item, Mapping) and item.get("claim_id") and item.get("kind"):
            try:
                claims.append(EvidenceClaim.from_dict(item))
            except (KeyError, TypeError, ValueError):
                continue
    return tuple(claims)


def _payload_sources(row_payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """결과 payload의 근거 행. 모듈별 키 이름 차이를 흡수한다(공통 계약 필드만)."""
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for key in ("sources", "reader_sources", "api_sources"):
        for item in row_payload.get(key) or ():
            if not isinstance(item, Mapping):
                continue
            marker = json.dumps(dict(item), ensure_ascii=False, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            rows.append(dict(item))
    return tuple(rows)


def load_snapshots(
    session, *, snapshot_ids: Sequence[uuid.UUID], run_id: uuid.UUID | None = None
) -> tuple[SourceSnapshot, ...]:
    """참조된 스냅샷 행을 **ID로** 읽는다. 없는 ID는 만들지 않는다.

    선택한 결과가 다른 실행에서 만들어졌을 수 있으므로 실행 ID로 거르지 않는다.
    조회는 읽기 전용이며, 없는 참조는 그대로 실패(사실 제외)로 이어진다.
    `run_id`는 호출부 호환을 위해 남긴 표시 값이고 필터로 쓰지 않는다.
    """
    from sqlalchemy import select

    from app.preview.models import PreviewSourceSnapshot

    wanted = {str(snapshot_id) for snapshot_id in snapshot_ids}
    if not wanted:
        return ()
    rows = session.scalars(
        select(PreviewSourceSnapshot).where(PreviewSourceSnapshot.id.in_(list(wanted)))
    ).all()
    found: list[SourceSnapshot] = []
    for row in rows:
        found.append(
            SourceSnapshot(
                snapshot_id=row.id,
                source_kind=_source_kind(row.source_kind),
                provider=row.provider,
                collected_at=row.collected_at,
                provider_updated_at=row.provider_updated_at,
                fixture=FixtureIdentity.from_dict(row.fixture) if row.fixture else None,
                catalog_query=None,
                artifact_id=row.artifact_id,
                validation_status=_validation_status(row.validation_status),
                note=row.note,
            )
        )
    return tuple(found)


def _source_kind(value: Any):
    from app.preview.contracts import SourceKind

    try:
        return SourceKind(str(value))
    except ValueError:  # pragma: no cover - 저장값이 손상된 경우
        return SourceKind.API


def _validation_status(value: Any):
    from app.preview.contracts import ValidationStatus

    try:
        return ValidationStatus(str(value))
    except ValueError:  # pragma: no cover
        return ValidationStatus.UNVERIFIED


def load_selected_results(
    session,
    *,
    run_id: uuid.UUID,
    selected_result_ids: Sequence[uuid.UUID],
) -> tuple[tuple[SelectedResultInput, ...], tuple[SourceSnapshot, ...], dict[str, Any]]:
    """선택된 결과 버전을 읽는다. **선택 ID와 실제 입력이 같은지** 호출자가 검사한다.

    반환: (선택된 결과들, 참조된 스냅샷들, 경기 표시 이름).
    """
    from sqlalchemy import select

    from app.preview.models import PreviewResult

    wanted = [uuid.UUID(str(result_id)) for result_id in selected_result_ids]
    if not wanted:
        return (), (), {}
    rows = (
        session.scalars(select(PreviewResult).where(PreviewResult.id.in_(wanted))).all()
    )
    by_id = {row.id: row for row in rows}
    ordered = [by_id[result_id] for result_id in wanted if result_id in by_id]

    results: list[SelectedResultInput] = []
    names: dict[str, Any] = {}
    snapshot_ids: list[uuid.UUID] = []
    for row in ordered:
        payload = dict(row.payload or {})
        inner = payload.get("payload")
        body = dict(inner) if isinstance(inner, Mapping) else payload
        claims = _payload_claims(payload)
        results.append(
            SelectedResultInput(
                result_id=row.id,
                module_id=row.module_id,
                version=row.version,
                status=row.status,
                quality=row.quality,
                implementation_version=row.implementation_version,
                prompt_version=row.prompt_version,
                fixture=_payload_fixture(body, payload) or _run_fixture(session, row.run_id),
                claims=claims,
                # 근거 행은 안쪽 payload(`reader_sources`/`sources`)에 있다. 바깥(감싼
                # ModuleResult)에도 있을 수 있으므로 둘 다 읽고 중복만 지운다.
                sources=_merge_sources(_payload_sources(body), _payload_sources(payload)),
                payload={
                    "coverage": body.get("coverage") or payload.get("coverage") or (),
                },
            )
        )
        for claim in claims:
            for snapshot_id in claim.snapshot_ids:
                if snapshot_id not in snapshot_ids:
                    snapshot_ids.append(snapshot_id)
        stored_fixture = body.get("fixture")
        if isinstance(stored_fixture, Mapping):
            for key in ("home_team", "away_team", "league"):
                value = stored_fixture.get(key)
                if value and key not in names:
                    names[key] = value
    if not names:
        # 결과 payload에 경기 이름이 없으면 **저장된 실행 라벨**만 표시용으로 쓴다.
        # 값은 저장된 것이고, 없으면 아래에서 `경기 <id>`로 남긴다(지어내지 않는다).
        label = _run_fixture_label(session, ordered[0].run_id) if ordered else None
        if label:
            names["label"] = label
    snapshots = load_snapshots(session, snapshot_ids=snapshot_ids, run_id=run_id)
    return tuple(results), snapshots, names


def _run_fixture_label(session, run_id: uuid.UUID) -> str | None:
    from app.preview.models import PreviewRun

    row = session.get(PreviewRun, run_id)
    label = getattr(row, "fixture_label", None) if row is not None else None
    return str(label) if label else None


def _merge_sources(
    *groups: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    """근거 행을 합치되 같은 행을 두 번 세지 않는다."""
    merged: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for row in group:
            marker = json.dumps(dict(row), ensure_ascii=False, sort_keys=True, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(dict(row))
    return tuple(merged)


def _run_fixture(session, run_id: uuid.UUID) -> FixtureIdentity | None:
    """결과가 속한 실행의 저장된 경기 식별자. payload에 없을 때만 쓰는 대체 출처다.

    새 값을 만들지 않고 **이미 저장된 행**을 읽는다. 결과가 어느 경기의 것인지
    확인할 수 없으면 `None`을 돌려주고, 검증이 그 결과를 제외한다.
    """
    from app.preview.models import PreviewRun

    row = session.get(PreviewRun, run_id)
    if row is None:
        return None
    data = {
        key: getattr(row, key, None)
        for key in ("fixture_id", "league_id", "season", "home_team_id", "away_team_id")
    }
    if not data.get("fixture_id"):
        return None
    kickoff = getattr(row, "kickoff_at", None)
    if kickoff is None:
        return None
    try:
        return FixtureIdentity.from_dict(
            {**data, "kickoff_at": kickoff.isoformat() if hasattr(kickoff, "isoformat") else kickoff}
        )
    except (KeyError, TypeError, ValueError):
        return None


def _payload_fixture(
    body: Mapping[str, Any], payload: Mapping[str, Any]
) -> FixtureIdentity | None:
    for candidate in (body.get("fixture"), payload.get("fixture")):
        if isinstance(candidate, Mapping):
            try:
                return FixtureIdentity.from_dict(candidate)
            except (KeyError, TypeError, ValueError):
                continue
    return None


# --------------------------------------------------------------------------
# 결과
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class S1Result:
    """S1 종합의 산출. 저장은 공통 runner가 한다."""

    document: PreviewDocument
    reader: presentation.ReaderPreview
    module_result: ModuleResult
    claims: tuple[EvidenceClaim, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()
    unavailable_reason: str | None = None
    quality: QualityStatus = QualityStatus.PENDING
    external_calls: int = 0
    model_text: str | None = None
    model_name: str | None = None
    attempt_summary: Mapping[str, Any] = field(default_factory=dict)
    payload: Mapping[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 출력 해석·검증
# --------------------------------------------------------------------------


class SynthesisFormatError(ValueError):
    """모델 출력이 요구한 JSON 구조가 아니다."""


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"```$", "", stripped).strip()
    return stripped


def parse_model_json(text: str) -> Mapping[str, Any]:
    payload = _strip_code_fence(text or "")
    if not payload:
        raise SynthesisFormatError("모델 응답이 비어 있습니다.")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SynthesisFormatError(f"모델 응답이 JSON이 아닙니다: {exc.msg}") from None
    if not isinstance(parsed, Mapping):
        raise SynthesisFormatError("모델 응답이 JSON 객체가 아닙니다.")
    return parsed


def _evidence_text(claims: Sequence[EvidenceClaim]) -> str:
    return " ".join(claim.text for claim in claims)


def _unsupported_pieces(
    text: str, *, cited: Sequence[EvidenceClaim], fixture: FixtureIdentity | None
) -> tuple[str, ...]:
    """판단 문장에 섞인 **새 구체 수치·날짜·부상 사건**을 찾는다.

    판단(선정·예측) 자체는 검사하지 않는다. 다만 판단 문장이 새 사실을 사실처럼
    끌어오면 그 조각을 덜어낸다("AI 해석"으로 새 사실을 통과시키지 않는다).
    """
    allowed = _evidence_text(cited)
    found: list[str] = []
    for match in _STAT_WITH_UNIT.finditer(text):
        token = match.group(0).replace(" ", "")
        if token.replace(" ", "") not in allowed.replace(" ", ""):
            found.append(match.group(0))
    for match in _EXPLICIT_DATE.finditer(text):
        token = match.group(0)
        if token in allowed:
            continue
        if fixture is not None and token in fixture.kickoff_at.date().isoformat():
            continue
        found.append(match.group(0))
    if _INJURY_EVENT.search(text) and not re.search(
        r"부상|결장|이탈|수술", allowed
    ):
        found.append("부상·결장 발생 서술")
    return tuple(dict.fromkeys(found))


def _resolve_citations(
    raw_ids: Any, known: Mapping[str, EvidenceClaim]
) -> tuple[list[EvidenceClaim], list[str]]:
    cited: list[EvidenceClaim] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for value in raw_ids or ():
        claim_id = str(value)
        if claim_id in seen:
            continue
        seen.add(claim_id)
        claim = known.get(claim_id)
        if claim is None:
            unknown.append(claim_id)
            continue
        cited.append(claim)
    return cited, unknown


def _judgment_claim(index: int, label: str, text: str, cited: Sequence[EvidenceClaim]) -> EvidenceClaim:
    refs = ", ".join(claim.claim_id for claim in cited) or "없음"
    return EvidenceClaim(
        claim_id=f"s1-{label}-{index}",
        kind=ClaimKind.AI_INTERPRETATION,
        text=text,
        snapshot_ids=tuple(
            dict.fromkeys(
                snapshot_id for claim in cited for snapshot_id in claim.snapshot_ids
            )
        ),
        decision=ClaimDecision.ADOPTED,
        decision_reason=f"AI 판단입니다. 판단 근거로 쓴 사실: {refs}.",
        source_url=next((claim.source_url for claim in cited if claim.source_url), None),
    )


@dataclass(frozen=True)
class _Synthesis:
    headline: str
    watch_points: tuple[dict[str, Any], ...]
    players: tuple[dict[str, Any], ...]
    absences_impact: str | None
    outlook: tuple[dict[str, Any], ...]
    prediction: dict[str, Any]
    claims: tuple[EvidenceClaim, ...]
    used_claim_ids: tuple[str, ...]
    diagnostics: tuple[str, ...]
    rejected: tuple[str, ...]


def _validated_outlook(
    raw_items: Sequence[Any],
    *,
    known: Mapping[str, EvidenceClaim],
    evidence: ValidatedEvidence,
) -> tuple[tuple[dict[str, Any], ...], list[str]]:
    """매체 전망·제공자 예측을 **실제 근거와 대조**한다.

    매체 예상 스코어는 그 매체가 실제로 말했다는 URL이 있어야 한다. 제공자 예측은
    알고리즘 출처 종류를 유지한다. 어느 쪽도 확인되지 않으면 문장을 만들지 않는다.
    """
    media_by_url = {
        claim.source_url: claim
        for claim in evidence.adopted_claims
        if claim.kind is ClaimKind.EXTERNAL_FORECAST and claim.source_url
    }
    api_claims = [c for c in evidence.adopted_claims if c.kind is ClaimKind.API_PREDICTION]
    kept: list[dict[str, Any]] = []
    rejected: list[str] = []
    for item in raw_items:
        if not isinstance(item, Mapping):
            continue
        statement = _clean(item.get("statement"))
        if not statement:
            continue
        kind = _clean(item.get("source_kind")) or "external_forecast"
        url = _clean(item.get("url")) or None
        if kind == ClaimKind.API_PREDICTION.value:
            if not api_claims:
                rejected.append(
                    f"제공자 알고리즘 예측 근거가 없어 전망을 제외했습니다: {statement[:40]}"
                )
                continue
            source = api_claims[0]
            kept.append(
                {
                    "publisher": _clean(item.get("publisher")) or "제공자 알고리즘",
                    "statement": statement,
                    "source_kind": ClaimKind.API_PREDICTION.value,
                    "published_at": item.get("published_at") or None,
                    "claim_id": source.claim_id,
                }
            )
            continue
        if not url or url not in media_by_url:
            rejected.append(
                "매체가 실제로 그렇게 말했다는 URL 근거가 없어 외부 전망을"
                f" 제외했습니다: {statement[:40]}"
            )
            continue
        source = media_by_url[url]
        kept.append(
            {
                "publisher": _clean(item.get("publisher")) or "매체 미상",
                "statement": statement,
                "source_kind": ClaimKind.EXTERNAL_FORECAST.value,
                "published_at": item.get("published_at") or None,
                "url": url,
                "claim_id": source.claim_id,
            }
        )
    return tuple(kept), rejected


def validate_synthesis(
    payload: Mapping[str, Any],
    *,
    evidence: ValidatedEvidence,
) -> _Synthesis:
    """모델 출력을 검증한다. 통과한 판단만 남기고 이유는 진단에 남긴다."""
    known = evidence.claims_by_id()
    diagnostics: list[str] = []
    rejected: list[str] = []

    headline = _clean(payload.get("headline"))
    if not headline:
        raise SynthesisFormatError("headline이 비어 있습니다.")

    watch_points: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("watch_points") or ()):
        if len(watch_points) >= MAX_WATCH_POINTS:
            break
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, Mapping):
            continue
        text = _clean(item.get("text"))
        if not text:
            continue
        cited, unknown = _resolve_citations(item.get("evidence"), known)
        unsupported = _unsupported_pieces(text, cited=cited, fixture=evidence.fixture)
        if unsupported:
            rejected.append(
                "관전 포인트에서 확인되지 않은 사실 조각을 덜어냈습니다: "
                + ", ".join(unsupported)
            )
            text = _drop_sentences(text, unsupported)
            if not text:
                continue
        claim = _judgment_claim(index, "watch", text, cited)
        watch_points.append(
            {
                "text": text,
                "evidence": [c.claim_id for c in cited],
                "claim_id": claim.claim_id,
            }
        )
        diagnostics.extend(
            f"관전 포인트 근거로 알 수 없는 claim_id를 무시했습니다: {value}"
            for value in unknown
        )

    players: list[dict[str, Any]] = []
    for index, item in enumerate(payload.get("players_to_watch") or ()):
        if len(players) >= MAX_PLAYERS:
            break
        if not isinstance(item, Mapping):
            continue
        player = _clean(item.get("player"))
        reason = _clean(item.get("reason"))
        if not player or not reason:
            continue
        cited, unknown = _resolve_citations(item.get("evidence"), known)
        unsupported = _unsupported_pieces(reason, cited=cited, fixture=evidence.fixture)
        if unsupported:
            rejected.append(
                f"주목 선수 {player}의 이유에서 확인되지 않은 사실 조각을 덜어냈습니다: "
                + ", ".join(unsupported)
            )
            reason = _drop_sentences(reason, unsupported)
            if not reason:
                continue
        claim = _judgment_claim(index, "player", f"{player}: {reason}", cited)
        players.append(
            {
                "player": player,
                "team": _clean(item.get("team")) or None,
                "reason": reason,
                "evidence": [c.claim_id for c in cited],
                "claim_id": claim.claim_id,
            }
        )
        diagnostics.extend(
            f"주목 선수 근거로 알 수 없는 claim_id를 무시했습니다: {value}"
            for value in unknown
        )

    absences_raw = _clean(payload.get("absences_impact"))
    absences: str | None = None
    if absences_raw:
        cited, _unknown = _resolve_citations(payload.get("absences_evidence"), known)
        unsupported = _unsupported_pieces(
            absences_raw, cited=cited, fixture=evidence.fixture
        )
        if unsupported:
            rejected.append(
                "결장·전력 영향 문단에서 확인되지 않은 사실 조각을 덜어냈습니다: "
                + ", ".join(unsupported)
            )
            absences_raw = _drop_sentences(absences_raw, unsupported)
        absences = absences_raw or None

    outlook, outlook_rejected = _validated_outlook(
        payload.get("external_outlook") or (), known=known, evidence=evidence
    )
    rejected.extend(outlook_rejected)

    prediction_raw = payload.get("ai_prediction") or {}
    prediction: dict[str, Any] = {}
    if isinstance(prediction_raw, Mapping):
        lean = _clean(prediction_raw.get("lean")).lower()
        if lean in _JUDGMENT_LEAN:
            prediction["lean"] = lean
        elif lean:
            diagnostics.append(f"예상 승무패 값 {lean!r}는 home/draw/away가 아니어서 비웁니다.")
        score = _clean(prediction_raw.get("score")) or None
        if score and not re.fullmatch(r"\d{1,2}\s*[-:]\s*\d{1,2}", score):
            diagnostics.append(
                f"예상 스코어 표기 {score!r}가 스코어 형식이 아니어서 비웁니다."
            )
            score = None
        if score:
            prediction["score"] = score.replace(" ", "")
        reasoning: list[str] = []
        for item in prediction_raw.get("reasoning") or ():
            text = _clean(item)
            if not text:
                continue
            unsupported = _unsupported_pieces(
                text, cited=evidence.adopted_claims, fixture=evidence.fixture
            )
            if unsupported:
                rejected.append(
                    "AI 예상 이유에서 확인되지 않은 사실 조각을 덜어냈습니다: "
                    + ", ".join(unsupported)
                )
                text = _drop_sentences(text, unsupported)
                if not text:
                    continue
            reasoning.append(text)
        if reasoning:
            prediction["reasoning"] = tuple(reasoning)
        note = _clean(prediction_raw.get("note")) or None
        if note:
            prediction["note"] = note

    claims = tuple(claim for claim in _judgment_claims(watch_points, players))
    used: list[str] = []
    for claim_id in payload.get("used_claim_ids") or ():
        value = str(claim_id)
        if value in known and value not in used:
            used.append(value)

    if not watch_points and not prediction and not players:
        raise SynthesisFormatError(
            "채택할 관전 포인트·주목 선수·AI 예상을 하나도 만들지 못했습니다."
        )

    return _Synthesis(
        headline=headline,
        watch_points=tuple(watch_points),
        players=tuple(players),
        absences_impact=absences,
        outlook=outlook,
        prediction=prediction,
        claims=claims,
        used_claim_ids=tuple(used),
        diagnostics=tuple(diagnostics),
        rejected=tuple(rejected),
    )


def _judgment_claims(
    watch_points: Sequence[Mapping[str, Any]], players: Sequence[Mapping[str, Any]]
) -> list[EvidenceClaim]:
    claims: list[EvidenceClaim] = []
    for item in watch_points:
        claims.append(
            EvidenceClaim(
                claim_id=str(item["claim_id"]),
                kind=ClaimKind.AI_INTERPRETATION,
                text=str(item["text"]),
                decision=ClaimDecision.ADOPTED,
                decision_reason="AI 관전 포인트입니다. 근거: " + ", ".join(item["evidence"]),
            )
        )
    for item in players:
        claims.append(
            EvidenceClaim(
                claim_id=str(item["claim_id"]),
                kind=ClaimKind.AI_INTERPRETATION,
                text=f"{item['player']}: {item['reason']}",
                decision=ClaimDecision.ADOPTED,
                decision_reason="AI 주목 선수 선정입니다. 근거: " + ", ".join(item["evidence"]),
            )
        )
    return claims


def _drop_sentences(text: str, pieces: Sequence[str]) -> str:
    """확인되지 않은 조각이 들어간 문장만 덜어낸다. 나머지 판단은 남긴다."""
    sentences = re.split(r"(?<=[.!?。])\s+", text)
    kept = [
        sentence
        for sentence in sentences
        if sentence.strip() and not any(piece in sentence for piece in pieces)
    ]
    return _clean(" ".join(kept))


# --------------------------------------------------------------------------
# 종합 실행
# --------------------------------------------------------------------------

def synthesize_preview(
    *,
    evidence: ValidatedEvidence,
    context: ExecutionContext,
    transport: provider.ProviderTransport | None,
    budget: RunBudget | None = None,
    session=None,
    actor_id: int | None = None,
    module_execution_id: uuid.UUID | None = None,
    fixture_names: Mapping[str, Any] | None = None,
    now: datetime | None = None,
    logical_call_id: str = LOGICAL_CALL_ID,
    response_text: str | None = None,
) -> S1Result:
    """검증된 조사 결과로 S1 ModuleResult와 PreviewDocument를 만든다.

    정상 경로의 모델 요청은 **1회**다(`response_text`를 주면 그 저장 텍스트를 재사용해
    호출 0회로 같은 변환을 재현한다 — 무료 재생 경로이며 live 성공이 아니다).
    """
    moment = now or _now()
    names = dict(fixture_names or {})
    resolved_actor = actor_id if actor_id is not None else context.actor_id
    run_budget = budget or RunBudget.for_run(now=moment)
    execution_id = module_execution_id or context.module_execution_id

    diagnostics: list[str] = [gap.to_text() for gap in evidence.gaps]
    coverage: list[CoverageEntry] = []
    external_calls = 0
    attempt_summary: dict[str, Any] = {}
    model_name: str | None = None
    model_text = response_text

    fixture = evidence.fixture
    if fixture is None:
        coverage.append(
            CoverageEntry(
                topic="경기 식별",
                state=CoverageState.API_NOT_PROVIDED,
                detail="경기 식별자가 없어 종합하지 않았습니다.",
            )
        )
        return _unavailable(
            evidence=evidence,
            context=context,
            moment=moment,
            diagnostics=diagnostics,
            coverage=coverage,
            reason="경기 식별자가 없어 독자용 프리뷰를 만들지 않았습니다.",
            names=names,
        )
    if not evidence.core_evidence_satisfied:
        coverage.append(
            CoverageEntry(
                topic="핵심 근거",
                state=CoverageState.VALIDATION_REJECTED,
                detail="참조가 붙은 채택 사실이 없어 완성 프리뷰로 만들지 않았습니다.",
            )
        )
        return _unavailable(
            evidence=evidence,
            context=context,
            moment=moment,
            diagnostics=diagnostics,
            coverage=coverage,
            reason=(
                "핵심 근거가 부족해 완성된 프리뷰로 저장하지 않았습니다."
                " 확보된 판단과 공백은 관리자 기록에 남겼습니다."
            ),
            names=names,
        )

    if model_text is None:
        if transport is None:
            diagnostics.append(
                "모델 전송 계층이 없어 S1 종합 호출을 하지 않았습니다. 본문을 만들지 않습니다."
            )
            coverage.append(
                CoverageEntry(
                    topic="S1 종합",
                    state=CoverageState.NOT_RUN,
                    detail="모델 전송 계층이 없습니다.",
                )
            )
            return _unavailable(
                evidence=evidence,
                context=context,
                moment=moment,
                diagnostics=diagnostics,
                coverage=coverage,
                reason="S1 종합 호출을 하지 않아 본문을 만들지 않았습니다.",
                names=names,
            )
        result = provider.request_model(
            logical_call_id=logical_call_id,
            contents=build_contents(evidence, names=names),
            context=context,
            transport=transport,
            budget=run_budget,
            session=session,
            module_id=MODULE_ID,
            operation="synthesize_preview",
            prompt_version=PROMPT_VERSION,
            generation_config=build_generation_config(),
            module_execution_id=execution_id,
            actor_id=resolved_actor,
            # 예산 기한 판정과 시도 기록 시각을 같은 시계로 맞춘다. 테스트는 고정
            # 시각을 넘기므로 실제 시계와 섞이면 첫 시도가 기한 초과로 거부된다.
            now=lambda: moment,
        )
        model_name = result.spec.model
        external_calls = provider.sent_attempt_count(result, transport.mode)
        attempt_summary = {
            "logical_call_id": logical_call_id,
            "attempt_count": result.attempt_count,
            "sent_attempts": external_calls,
            "outcomes": [attempt.outcome.value for attempt in result.attempts],
            "http_status": result.response.http_status,
            "error_class": result.response.error_class,
            "stopped_reason": result.stopped_reason,
            "missing_configuration": result.missing_configuration,
            "mode": transport.mode.value,
            "model": model_name,
            "tools": list((build_generation_config().get("tools") or [])),
            "usage": result.response.usage.to_dict() if result.response.usage else None,
            "response_artifact_id": (
                str(result.response.raw_artifact_id)
                if result.response.raw_artifact_id
                else None
            ),
        }
        if not result.ok or not result.text:
            reason = result.stopped_reason or (
                result.response.error_message or "S1 모델 호출이 성공하지 않았습니다."
            )
            diagnostics.append(f"S1 종합 호출이 실패했습니다: {reason}")
            coverage.append(
                CoverageEntry(topic="S1 종합", state=CoverageState.CALL_ERROR, detail=reason)
            )
            return _unavailable(
                evidence=evidence,
                context=context,
                moment=moment,
                diagnostics=diagnostics,
                coverage=coverage,
                reason="S1 종합 호출이 성공하지 않아 독자용 본문을 만들지 않았습니다.",
                names=names,
                external_calls=external_calls,
                attempt_summary=attempt_summary,
                model_name=model_name,
            )
        model_text = result.text

    try:
        parsed = parse_model_json(model_text)
    except SynthesisFormatError as exc:
        diagnostics.append(str(exc))
        coverage.append(
            CoverageEntry(
                topic="S1 종합", state=CoverageState.VALIDATION_REJECTED, detail=str(exc)
            )
        )
        return _unavailable(
            evidence=evidence,
            context=context,
            moment=moment,
            diagnostics=diagnostics,
            coverage=coverage,
            reason="S1 모델 응답을 프리뷰로 해석하지 못해 본문을 만들지 않았습니다.",
            names=names,
            external_calls=external_calls,
            attempt_summary=attempt_summary,
            model_name=model_name,
            model_text=model_text,
        )

    try:
        synthesis = validate_synthesis(parsed, evidence=evidence)
    except SynthesisFormatError as exc:
        diagnostics.append(str(exc))
        coverage.append(
            CoverageEntry(
                topic="S1 종합", state=CoverageState.VALIDATION_REJECTED, detail=str(exc)
            )
        )
        return _unavailable(
            evidence=evidence,
            context=context,
            moment=moment,
            diagnostics=diagnostics,
            coverage=coverage,
            reason="S1 출력에서 쓸 수 있는 판단을 만들지 못해 본문을 만들지 않았습니다.",
            names=names,
            external_calls=external_calls,
            attempt_summary=attempt_summary,
            model_name=model_name,
            model_text=model_text,
        )

    diagnostics.extend(synthesis.diagnostics)
    diagnostics.extend(synthesis.rejected)
    coverage.append(
        CoverageEntry(
            topic="S1 종합",
            state=CoverageState.AVAILABLE,
            detail=(
                f"관전 포인트 {len(synthesis.watch_points)}건, 주목 선수"
                f" {len(synthesis.players)}명, AI 예상 {'있음' if synthesis.prediction else '없음'}"
            ),
        )
    )

    sources = _reader_sources(evidence)
    data_as_of = _data_as_of(evidence)

    document = presentation.to_preview_document(
        document_id=uuid.uuid4(),
        run_id=context.run_id,
        fixture=fixture,
        generated_at=moment,
        data_as_of=data_as_of,
        headline=synthesis.headline,
        watch_points=[item["text"] for item in synthesis.watch_points],
        players_to_watch=synthesis.players,
        absences_impact=synthesis.absences_impact,
        external_outlook=synthesis.outlook,
        ai_prediction=synthesis.prediction,
        sources=sources,
    )
    attribution = {
        "model": model_name,
        "provider": getattr(transport, "provider", None),
        "mode": context.mode.value,
        "mode_label": presentation.mode_label(context.mode),
        "executed_at": moment.isoformat(),
        "external_calls": external_calls,
    }
    reader = presentation.ReaderPreview(
        document=document,
        fixture_label=presentation.fixture_label(fixture, names),
        league=names.get("league") or None,
        sources=sources,
        cited_claim_ids=tuple(
            dict.fromkeys(
                claim_id
                for item in (*synthesis.watch_points, *synthesis.players)
                for claim_id in item["evidence"]
            )
        ),
        attribution=attribution,
    )

    payload = _success_payload(
        evidence=evidence,
        synthesis=synthesis,
        document=document,
        reader=reader,
        attribution=attribution,
        names=names,
        model_text=model_text,
    )
    quality = QualityStatus.READY
    module_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=MODULE_ID,
        module_execution_id=execution_id,  # type: ignore[arg-type]
        run_id=context.run_id,
        version=1,
        input_hash=compute_input_hash(
            {
                "module_id": MODULE_ID,
                "fixture": fixture.to_dict(),
                "selected_result_ids": [str(r) for r in evidence.selected_result_ids],
                "snapshot_ids": [str(s) for s in evidence.snapshot_ids],
                "implementation": IMPLEMENTATION_VERSION,
            }
        ),
        status=ModuleStatus.SUCCEEDED,
        quality=quality,
        claims=synthesis.claims,
        coverage=tuple(coverage),
        diagnostics=tuple(diagnostics),
        implementation_version=IMPLEMENTATION_VERSION,
        prompt_version=PROMPT_VERSION,
        contract_version=CONTRACT_VERSION,
        payload=payload,
    )
    return S1Result(
        document=document,
        reader=reader,
        module_result=module_result,
        claims=synthesis.claims,
        coverage=tuple(coverage),
        diagnostics=tuple(diagnostics),
        quality=quality,
        external_calls=external_calls,
        model_text=model_text,
        model_name=model_name,
        attempt_summary=attempt_summary,
        payload=payload,
    )


def _unavailable(
    *,
    evidence: ValidatedEvidence,
    context: ExecutionContext,
    moment: datetime,
    diagnostics: Sequence[str],
    coverage: Sequence[CoverageEntry],
    reason: str,
    names: Mapping[str, Any],
    external_calls: int = 0,
    attempt_summary: Mapping[str, Any] | None = None,
    model_name: str | None = None,
    model_text: str | None = None,
) -> S1Result:
    """본문을 만들지 못한 결과. 빈 본문을 성공으로 만들지 않는다."""
    fixture = evidence.fixture
    document = presentation.to_preview_document(
        document_id=uuid.uuid4(),
        run_id=context.run_id,
        fixture=fixture,  # type: ignore[arg-type]
        generated_at=moment,
        data_as_of=None,
        headline="",
    )
    payload = {
        "module_id": MODULE_ID,
        "implementation_version": IMPLEMENTATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "mode": context.mode.value,
        "fixture": fixture.to_dict() if fixture else None,
        "fixture_names": dict(names),
        "validated": evidence.to_dict(),
        "claims": [claim.to_dict() for claim in evidence.adopted_claims],
        "coverage": [entry.to_dict() for entry in coverage],
        "diagnostics": [str(item) for item in diagnostics],
        "unavailable_reason": reason,
        "model_text": model_text,
        "model_name": model_name,
        "attempt_summary": dict(attempt_summary or {}),
        "external_calls": external_calls,
    }
    module_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=MODULE_ID,
        module_execution_id=context.module_execution_id,  # type: ignore[arg-type]
        run_id=context.run_id,
        version=1,
        input_hash=compute_input_hash({"module_id": MODULE_ID, "unavailable": reason}),
        status=ModuleStatus.FAILED,
        quality=QualityStatus.INSUFFICIENT,
        claims=(),
        coverage=tuple(coverage),
        diagnostics=tuple(str(item) for item in diagnostics),
        implementation_version=IMPLEMENTATION_VERSION,
        prompt_version=PROMPT_VERSION,
        contract_version=CONTRACT_VERSION,
        payload=payload,
    )
    return S1Result(
        document=document,
        reader=presentation.ReaderPreview(
            document=document,
            fixture_label=presentation.fixture_label(fixture, names),
            league=names.get("league") or None,
        ),
        module_result=module_result,
        coverage=tuple(coverage),
        diagnostics=tuple(str(item) for item in diagnostics),
        unavailable_reason=reason,
        quality=QualityStatus.INSUFFICIENT,
        external_calls=external_calls,
        model_text=model_text,
        model_name=model_name,
        attempt_summary=attempt_summary or {},
        payload=payload,
    )


def _data_as_of(evidence: ValidatedEvidence) -> datetime | None:
    moments = [snapshot.collected_at for snapshot in evidence.snapshots]
    moments.extend(
        claim.claimed_at for claim in evidence.adopted_claims if claim.claimed_at is not None
    )
    if not moments:
        return None
    return max(moment for moment in moments if moment is not None)


def _reader_sources(evidence: ValidatedEvidence) -> tuple[Mapping[str, Any], ...]:
    """독자용 근거. 검색 URL은 그대로, API 자료는 스냅샷 참조 라벨과 시각을 쓴다."""
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for module in evidence.modules:
        for source in module.sources:
            url = source.get("url")
            marker = str(url or source.get("label") or "")
            if not marker or marker in seen:
                continue
            seen.add(marker)
            rows.append(dict(source))
    for snapshot in evidence.snapshots:
        is_search = str(getattr(snapshot.source_kind, "value", snapshot.source_kind)) == "search"
        if is_search:
            # 검색 스냅샷은 위에서 URL 행으로 이미 표시했다. 내부 제공자 이름
            # (`vertex-google-search` 등)은 독자용에 내보내지 않는다.
            if any(row.get("kind") == "search" for row in rows):
                continue
            label = "검색 자료"
        else:
            # 내부 제공자 식별자는 그대로 쓰지 않고 사람이 읽는 이름으로 바꾼다.
            label = (
                "API-Football 저장 자료"
                if snapshot.provider.startswith("api-football")
                else "저장된 API 자료"
            )
        marker = f"snapshot:{snapshot.source_kind}:{snapshot.collected_at.date().isoformat()}:{label}"
        if marker in seen:
            continue
        seen.add(marker)
        rows.append(
            {
                "label": label,
                "kind": "search" if is_search else "api",
                "url": None,
                "note": f"수집 {snapshot.collected_at.date().isoformat()} · 저장 자료",
                "collected_at": snapshot.collected_at.isoformat(),
            }
        )
    return tuple(rows)


def _success_payload(
    *,
    evidence: ValidatedEvidence,
    synthesis: _Synthesis,
    document: PreviewDocument,
    reader: presentation.ReaderPreview,
    attribution: Mapping[str, Any],
    names: Mapping[str, Any],
    model_text: str | None,
) -> dict[str, Any]:
    """저장 payload. 독자용 투영과 관리자 진단을 **분리**해 담는다."""
    reader_payload = presentation.reader_payload(
        reader, generated_at=document.generated_at, data_as_of=document.data_as_of
    )
    return {
        "module_id": MODULE_ID,
        "implementation_version": IMPLEMENTATION_VERSION,
        "prompt_version": PROMPT_VERSION,
        "output_contract_version": OUTPUT_CONTRACT_VERSION,
        "fixture": evidence.fixture.to_dict() if evidence.fixture else None,
        "fixture_names": dict(names),
        "validated": evidence.to_dict(),
        "selected_result_ids": [str(item) for item in evidence.selected_result_ids],
        "snapshot_ids": [str(item) for item in evidence.snapshot_ids],
        "synthesis": {
            "headline": synthesis.headline,
            "watch_points": [dict(item) for item in synthesis.watch_points],
            "players_to_watch": [dict(item) for item in synthesis.players],
            "absences_impact": synthesis.absences_impact,
            "external_outlook": [dict(item) for item in synthesis.outlook],
            "ai_prediction": dict(synthesis.prediction),
            "used_claim_ids": list(synthesis.used_claim_ids),
        },
        "preview_document": document.to_dict(),
        "reader_preview": reader_payload,
        "attribution": dict(attribution),
        "claims": [claim.to_dict() for claim in synthesis.claims],
        "coverage": [],
        "diagnostics": list(synthesis.diagnostics) + list(synthesis.rejected),
        "model_text": model_text,
        "external_calls": attribution.get("external_calls", 0),
    }


# --------------------------------------------------------------------------
# 저장 결과에서 독자용 투영 다시 만들기 (외부 호출 0회)
# --------------------------------------------------------------------------


def preview_payload_from_result(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """저장된 S1 결과 payload에서 독자용 투영을 다시 만든다. 없으면 `None`.

    저장된 payload의 `reader_preview`를 그대로 믿지 않고 **허용 목록으로 다시
    투영**한다. 나중에 저장 구조가 바뀌어도 진단 필드가 독자 응답으로 새지 않는다.
    """
    document_raw = payload.get("preview_document")
    if not isinstance(document_raw, Mapping):
        return None
    try:
        fixture = FixtureIdentity.from_dict(document_raw["fixture"])
    except (KeyError, TypeError, ValueError):
        return None
    from app.preview.contracts import PREVIEW_DOCUMENT_VERSION

    document = PreviewDocument(
        document_id=uuid.UUID(str(document_raw["document_id"])),
        run_id=uuid.UUID(str(document_raw["run_id"])),
        fixture=fixture,
        generated_at=datetime.fromisoformat(str(document_raw["generated_at"])),
        data_as_of=(
            datetime.fromisoformat(str(document_raw["data_as_of"]))
            if document_raw.get("data_as_of")
            else None
        ),
        headline=str(document_raw.get("headline") or ""),
        watch_points=tuple(str(item) for item in document_raw.get("watch_points") or ()),
        players_to_watch=tuple(
            dict(item) for item in document_raw.get("players_to_watch") or ()
        ),
        absences_impact=document_raw.get("absences_impact") or None,
        external_outlook=tuple(
            dict(item) for item in document_raw.get("external_outlook") or ()
        ),
        ai_prediction=dict(document_raw.get("ai_prediction") or {}),
        sources=tuple(dict(item) for item in document_raw.get("sources") or ()),
        contract_version=str(
            document_raw.get("contract_version") or PREVIEW_DOCUMENT_VERSION
        ),
    )
    attribution = dict(payload.get("attribution") or {})
    names = dict(payload.get("fixture_names") or {})
    reader = presentation.ReaderPreview(
        document=document,
        fixture_label=presentation.fixture_label(fixture, names),
        league=names.get("league") or None,
        sources=document.sources,
        attribution=attribution,
    )
    return presentation.reader_payload(
        reader, generated_at=document.generated_at, data_as_of=document.data_as_of
    )


# --------------------------------------------------------------------------
# 섹션 노드 (prepare → S1 research → compose)
# --------------------------------------------------------------------------


def _initial_evidence(
    module_execution_id: uuid.UUID | None = None,
) -> ValidatedEvidence:
    return ValidatedEvidence(
        fixture=None,
        modules=(),
        snapshots=(),
        gaps=(EvidenceGap(module_id="selection", reason="선택된 결과가 없습니다."),),
        core_evidence_satisfied=False,
    )


def prepare_node(*, now: datetime | None = None):
    """선택 결과를 읽어 V0 검증까지 끝낸다. 외부 호출은 0회다."""
    from app.preview import runner

    def run(ctx: runner.SectionNodeContext, state: runner.SectionState) -> runner.NodeOutcome:
        fixture_raw = state.get("fixture") or ctx.fixture
        fixture = None
        if isinstance(fixture_raw, Mapping):
            try:
                fixture = FixtureIdentity.from_dict(dict(fixture_raw))
            except (KeyError, TypeError, ValueError):
                fixture = None
        results, snapshots, names = load_selected_results(
            ctx.session,
            run_id=ctx.context.run_id,
            selected_result_ids=ctx.selected_result_ids,
        )
        evidence = validate_evidence(
            fixture=fixture,
            results=results,
            snapshots=snapshots,
            # R4(주목 선수)도 종합 입력이다. R1은 경기력 전용으로 분리됐다.
            module_ids=("R1", "R2", "R3", "R4"),
            selected_result_ids=ctx.selected_result_ids,
            now=now,
        )
        return runner.NodeOutcome(
            payload={
                "validated": evidence.to_dict(),
                "fixture": (evidence.fixture.to_dict() if evidence.fixture else None),
                "fixture_names": names,
                "selected_result_ids": [str(item) for item in ctx.selected_result_ids],
                "snapshot_ids": [str(item) for item in evidence.snapshot_ids],
                "claims": [],
                "coverage": [],
            },
            diagnostics=tuple(gap.to_text() for gap in evidence.gaps),
            external_calls=0,
        )

    return run


def research_node(
    *,
    transport: provider.ProviderTransport | None,
    now: datetime | None = None,
):
    """S1 종합 노드. 검증된 입력으로 **정상 호출 1회**만 한다."""
    from app.preview import runner

    def run(ctx: runner.SectionNodeContext, state: runner.SectionState) -> runner.NodeOutcome:
        data = state.get("data") or {}
        evidence = _evidence_from_state(data)
        fixture_names = dict(data.get("fixture_names") or {})
        precheck_reason = _precheck_reason(evidence)
        if precheck_reason:
            return runner.NodeOutcome(
                payload={
                    "module_id": MODULE_ID,
                    "validated": evidence.to_dict(),
                    "unavailable_reason": precheck_reason,
                    "claims": [],
                    "coverage": [],
                    "diagnostics": [gap.to_text() for gap in evidence.gaps],
                },
                unavailable_reason=precheck_reason,
                quality=QualityStatus.INSUFFICIENT,
                external_calls=0,
            )
        result = synthesize_preview(
            evidence=evidence,
            context=ctx.context,
            transport=transport or ctx.transport,
            budget=ctx.budget,
            session=ctx.session,
            actor_id=ctx.actor_id,
            module_execution_id=ctx.module_execution_id,
            fixture_names=fixture_names,
            now=now,
        )
        return runner.NodeOutcome(
            payload=dict(result.payload),
            quality=result.quality,
            diagnostics=result.diagnostics,
            unavailable_reason=result.unavailable_reason,
            external_calls=result.external_calls,
        )

    return run


def _precheck_reason(evidence: ValidatedEvidence) -> str | None:
    """호출 전에 거부해야 하는 경우. 유료 호출을 낭비하지 않는다."""
    if evidence.fixture is None:
        return "경기 식별자가 없어 S1 종합을 실행하지 않았습니다."
    if not evidence.core_evidence_satisfied:
        return (
            "참조가 붙은 채택 사실이 없어 S1 종합을 호출하지 않았습니다."
            " 확보된 자료와 공백은 관리자 기록에 남겼습니다."
        )
    return None


def _evidence_from_state(data: Mapping[str, Any]) -> ValidatedEvidence:
    raw = data.get("validated")
    if isinstance(raw, Mapping) and raw:
        return ValidatedEvidence.from_dict(raw)
    return _initial_evidence()


def compose_node(*, now: datetime | None = None):
    """S1 payload로 독자용 본문·근거를 조립한다. 외부 호출 0회."""
    from app.preview import runner

    def run(ctx: runner.SectionNodeContext, state: runner.SectionState) -> runner.NodeOutcome:
        payload = (state.get("research") or {}).get(MODULE_ID) or {}
        if not payload:
            return runner.NodeOutcome(
                unavailable_reason=(
                    "S1 종합 결과가 없어 독자용 프리뷰를 만들지 않았습니다."
                ),
                quality=QualityStatus.INSUFFICIENT,
            )
        reader_payload = payload.get("reader_preview") or {}
        body = str(reader_payload.get("body") or "")
        if not body.strip():
            return runner.NodeOutcome(
                unavailable_reason=str(
                    payload.get("unavailable_reason")
                    or "S1 종합 결과에 독자용 본문이 없습니다."
                ),
                quality=QualityStatus.INSUFFICIENT,
                diagnostics=payload.get("diagnostics") or (),
            )
        headline = str(reader_payload.get("headline") or "")
        return runner.NodeOutcome(
            title=headline or "경기 프리뷰",
            body=body,
            sources=tuple(
                dict(item) for item in reader_payload.get("sources") or ()
            ),
            quality=QualityStatus.READY,
            diagnostics=(),
        )

    return run


def build_synthesis_implementations(
    *,
    transport: provider.ProviderTransport | None,
    reader=None,
    now: datetime | None = None,
    mode=None,
):
    """`section_synthesis` 섹션의 노드 묶음.

    prepare(선택 결과 읽기·검증) → research(S1 1회) → compose(독자용 조립) 순서다.
    D0 같은 추가 자료 준비 노드를 새로 만들지 않는다. 입력은 **선택된 결과**뿐이다.
    """
    from app.preview import runner
    from app.preview.contracts import RunMode

    resolved_mode = mode or (
        transport.mode if transport is not None else RunMode.MOCK
    )
    return runner.WorkflowImplementations(
        prepare_data=runner.NodeImplementation(
            module_id="D0",
            implementation_version=SELECTED_INPUT_IMPLEMENTATION_VERSION,
            prompt_version=None,
            mode=resolved_mode,
            run=prepare_node(now=now),
        ),
        research=(
            runner.NodeImplementation(
                module_id=MODULE_ID,
                implementation_version=IMPLEMENTATION_VERSION,
                prompt_version=PROMPT_VERSION,
                mode=resolved_mode,
                run=research_node(transport=transport, now=now),
            ),
        ),
        compose_body=runner.NodeImplementation(
            module_id="compose_body",
            implementation_version=COMPOSE_IMPLEMENTATION_VERSION,
            prompt_version=None,
            mode=resolved_mode,
            run=compose_node(now=now),
        ),
    )
