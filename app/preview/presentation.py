"""MP-09 독자용 표현. 독자에 보낼 필드만 골라 담는다.

이 파일의 규칙:

- **독자용 투영은 허용 목록(allow-list)** 이다. 저장된 값에서 지우는 방식이 아니라,
  넘길 필드만 골라 새 dict를 만든다. 그래서 나중에 내부 필드가 늘어도 독자 응답으로
  새지 않는다.
- 진단·커버리지·스냅샷 ID·결과 ID·시도 정보·내부 토큰은 **독자용에 넣지 않는다**.
  관리자 진단은 `inspection`·`get_run_detail`이 따로 낸다.
- 근거 표시, AI 예측이라는 표시, 자료 기준 시각은 독자 이해를 위한 정보라 남긴다.
- 없다고 판단한 보조 항목은 빈 카드 대신 **키 자체를 넣지 않는다**(빈 배열·플레이스
  홀더 문구 금지).

`to_preview_document`는 계약(`PreviewDocument`)을 만든다. 계약 필드 밖의 표시 정보
(경기 이름·출처 시각·AI 표시)는 저장하는 `payload`와 API 투영에서 별도로 낸다.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.preview.contracts import (
    PREVIEW_DOCUMENT_VERSION,
    ClaimKind,
    EvidenceClaim,
    FixtureIdentity,
    PreviewDocument,
)

__all__ = [
    "AI_FORECAST_LABEL",
    "ReaderPreview",
    "MODE_LABELS",
    "compose_reader_body",
    "fixture_label",
    "mode_label",
    "reader_payload",
    "to_preview_document",
]

# 독자 화면에 그대로 나가는 AI 예측 표시. 이 문구는 버전 축이 아니다(표시 문구).
AI_FORECAST_LABEL = "AI 예측"

# 실행 방식 표시. 모의·재생을 실제 생성으로 읽지 않게 화면이 그대로 보여준다.
MODE_LABELS = {
    "live": "실호출 (live)",
    "replay": "저장 응답 재생 (replay)",
    "mock": "모의 자료 (mock, 외부 호출 없음)",
}


def mode_label(mode: Any) -> str:
    """실행 방식의 사람이 읽는 표기. 모르는 값은 그대로 돌려준다."""
    value = mode.value if hasattr(mode, "value") else str(mode or "")
    return MODE_LABELS.get(value, value)

# 독자용에 남으면 안 되는 내부 토큰. 결과·스냅샷 UUID, 내부 근거 claim ID,
# 대괄호로 노출된 내부 참조.
#
# claim ID는 **소문자**로 만든다(`api:standings-13`, `r1-watch-0`, `r3-media-0`).
# 그래서 대소문자를 구분한다. 구분하지 않으면 "API-Football" 같은 **실제 출처 이름**이
# 내부 ID로 오인되어 지워진다(실제로 그런 손실이 관측돼 구분으로 고쳤다).
_UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
)
_INTERNAL_CLAIM_ID = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:api:[a-z0-9._-]+"
    r"|(?:r1|r2|r3|s1)-[a-z0-9]+(?:-[a-z0-9]+)*"
    r"|rejected-[a-z0-9-]+)"
    r"(?![A-Za-z0-9])"
)
_BRACKETED_INTERNAL = re.compile(r"\[\s*(?:api|fact|claim)[^\[\]]*?\]", re.IGNORECASE)


def _strip_internal(text: str) -> str:
    cleaned = _UUID.sub(" ", text)
    cleaned = _BRACKETED_INTERNAL.sub(" ", cleaned)
    return _INTERNAL_CLAIM_ID.sub(" ", cleaned)
_MARKER = re.compile(
    r"(?P<kind>사실|fact|해석|interpretation)"
    r"\s*(?:[(（]\s*(?P<inner>fact|interpretation)\s*[)）])?\s*[:：]",
    re.IGNORECASE,
)
_INTERPRETATION_KINDS = frozenset({"해석", "interpretation"})
_AI_PREFIX = "AI 해석으로는, "


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _reader_text(text: Any) -> str:
    """모델이 남긴 내부 ID·사실/해석 표기를 독자용 문장으로 정리한다."""
    raw = _clean(_strip_internal(_clean(text)))
    if not raw:
        return ""
    pieces: list[str] = []
    mode = "fact"
    cursor = 0
    for match in _MARKER.finditer(raw):
        segment = raw[cursor : match.start()].strip(" :：")
        if segment:
            pieces.append((_AI_PREFIX + segment) if mode == "interpretation" else segment)
        kind = (match.group("kind") or "").lower()
        inner = (match.group("inner") or "").lower()
        mode = (
            "interpretation"
            if kind in _INTERPRETATION_KINDS or inner == "interpretation"
            else "fact"
        )
        cursor = match.end()
    tail = raw[cursor:].strip(" :：")
    if tail:
        pieces.append((_AI_PREFIX + tail) if mode == "interpretation" else tail)
    return _clean(" ".join(pieces))


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return moment.isoformat()


def _source_row(row: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """독자용 근거 한 행. 내부 ID는 지우고 사람이 읽을 값만 남긴다."""
    url = _clean(row.get("url")) or None
    label = _reader_text(row.get("label")) or (_clean(row.get("domain")) if row.get("domain") else "")
    if not label and url:
        label = url
    if not label:
        return None
    kind = str(row.get("kind") or ("search" if url else "api"))
    note = _reader_text(row.get("note")) if row.get("note") else ""
    result: dict[str, Any] = {"label": label, "kind": kind}
    if url:
        result["url"] = url
    if note:
        result["note"] = note
    observed = row.get("collected_at") or row.get("published_at") or row.get("observed_at")
    if observed:
        result["observed_at"] = str(observed)
    return result


@dataclass(frozen=True)
class ReaderPreview:
    """독자용 프리뷰 하나. 계약 문서와 표시 정보(경기 이름·기준 시각)를 함께 둔다."""

    document: PreviewDocument
    fixture_label: str
    league: str | None = None
    sources: tuple[Mapping[str, Any], ...] = ()
    # 독자 문장에 쓰인 채택 근거. **관리자 진단**에서 문장↔근거를 따라가는 데 쓴다.
    cited_claim_ids: tuple[str, ...] = ()
    attribution: Mapping[str, Any] = field(default_factory=dict)


def fixture_label(
    fixture: FixtureIdentity | None, names: Mapping[str, Any] | None
) -> str:
    """경기 표시 이름. 팀 이름이 없으면 저장된 라벨, 그것도 없으면 경기 ID만 쓴다.

    팀 이름을 지어내지 않는다. `names["label"]`은 저장된 실행 라벨(표시용)이다.
    """
    names = names or {}
    home = _clean(names.get("home_team"))
    away = _clean(names.get("away_team"))
    if home and away:
        return f"{home} vs {away}"
    stored = _clean(names.get("label"))
    if stored:
        return stored
    if fixture is not None:
        return f"경기 {fixture.fixture_id}"
    return "경기 정보 없음"


def to_preview_document(
    *,
    document_id: uuid.UUID,
    run_id: uuid.UUID,
    fixture: FixtureIdentity,
    generated_at: datetime,
    data_as_of: datetime | None,
    headline: str,
    watch_points: Sequence[str] = (),
    players_to_watch: Sequence[Mapping[str, Any]] = (),
    absences_impact: str | None = None,
    external_outlook: Sequence[Mapping[str, Any]] = (),
    ai_prediction: Mapping[str, Any] | None = None,
    sources: Sequence[Mapping[str, Any]] = (),
) -> PreviewDocument:
    """독자용 문서를 만든다. 넘긴 값만 담고 새 값을 만들지 않는다."""
    clean_watch = tuple(text for text in (_reader_text(item) for item in watch_points) if text)
    clean_players: list[Mapping[str, Any]] = []
    for item in players_to_watch:
        player = _reader_text(item.get("player"))
        reason = _reader_text(item.get("reason"))
        if not player or not reason:
            continue
        row: dict[str, Any] = {"player": player, "reason": reason}
        team = _reader_text(item.get("team"))
        if team:
            row["team"] = team
        clean_players.append(row)

    clean_outlook: list[Mapping[str, Any]] = []
    for item in external_outlook:
        statement = _reader_text(item.get("statement") or item.get("text"))
        if not statement:
            continue
        row = {
            "publisher": _reader_text(item.get("publisher")) or "매체 미상",
            "statement": statement,
            "source_kind": str(item.get("source_kind") or ClaimKind.EXTERNAL_FORECAST.value),
        }
        published = item.get("published_at") or item.get("observed_at")
        if published:
            row["published_at"] = str(published)
        if item.get("url"):
            row["url"] = str(item["url"])
        if item.get("source_kind") == ClaimKind.API_PREDICTION.value:
            # 제공자 이름이 이미 있으면 그대로 둔다. 없을 때만 일반 표기로 채운다.
            row["publisher"] = _reader_text(item.get("publisher")) or "제공자 알고리즘"
            row["source_note"] = "제공자 알고리즘 예측이며 매체 의견이 아닙니다."
        clean_outlook.append(row)

    prediction: dict[str, Any] = {}
    if ai_prediction:
        lean = str(ai_prediction.get("lean") or "").strip().lower()
        if lean in {"home", "draw", "away"}:
            prediction["lean"] = lean
        score = _reader_text(ai_prediction.get("score"))
        if score:
            prediction["score"] = score
        reasoning = tuple(
            text
            for text in (_reader_text(item) for item in ai_prediction.get("reasoning") or ())
            if text
        )
        if reasoning:
            prediction["reasoning"] = reasoning
        note = _reader_text(ai_prediction.get("note"))
        if note:
            prediction["note"] = note

    clean_sources: list[Mapping[str, Any]] = []
    for row in sources:
        cleaned = _source_row(row)
        if cleaned is not None:
            clean_sources.append(cleaned)

    absences = _reader_text(absences_impact) if absences_impact else None
    return PreviewDocument(
        document_id=document_id,
        run_id=run_id,
        fixture=fixture,
        generated_at=generated_at,
        data_as_of=data_as_of,
        headline=_reader_text(headline),
        watch_points=clean_watch,
        players_to_watch=tuple(clean_players),
        absences_impact=absences,
        external_outlook=tuple(clean_outlook),
        ai_prediction=prediction,
        sources=tuple(clean_sources),
        contract_version=PREVIEW_DOCUMENT_VERSION,
    )


def compose_reader_body(document: PreviewDocument) -> str:
    """독자용 본문 문단. 보조 항목이 없으면 그 문단 자체를 만들지 않는다."""
    paragraphs: list[str] = []
    if document.headline:
        paragraphs.append(document.headline)
    if document.watch_points:
        paragraphs.append("관전 포인트. " + " ".join(document.watch_points))
    if document.players_to_watch:
        bits: list[str] = []
        for player in document.players_to_watch:
            team = player.get("team")
            who = f"{player['player']}({team})" if team else str(player["player"])
            bits.append(f"{who}는 {player['reason']}")
        paragraphs.append("주목할 선수는 이렇습니다. " + " ".join(bits))
    if document.absences_impact:
        paragraphs.append(document.absences_impact)
    if document.external_outlook:
        bits = []
        for outlook in document.external_outlook:
            publisher = outlook.get("publisher") or "매체 미상"
            published = outlook.get("published_at")
            stamp = f"({published})" if published else ""
            bits.append(f"{publisher}{stamp}: {outlook['statement']}")
        paragraphs.append("외부 전망입니다. " + " ".join(bits))
    prediction = document.ai_prediction or {}
    if prediction:
        bits = []
        lean = prediction.get("lean")
        if lean:
            bits.append({"home": "홈팀 우세", "draw": "무승부", "away": "원정팀 우세"}[lean])
        if prediction.get("score"):
            bits.append(f"예상 스코어 {prediction['score']}")
        lead = ", ".join(bits)
        reasoning = prediction.get("reasoning") or ()
        sentence = f"{AI_FORECAST_LABEL}입니다."
        if lead:
            sentence = f"{AI_FORECAST_LABEL}은 {lead}입니다."
        if reasoning:
            sentence += " " + " ".join(reasoning)
        if prediction.get("note"):
            sentence += f" {prediction['note']}"
        paragraphs.append(sentence)
    return "\n\n".join(part for part in paragraphs if part.strip())


def reader_payload(
    preview: ReaderPreview,
    *,
    generated_at: datetime,
    data_as_of: datetime | None,
) -> dict[str, Any]:
    """독자용 API 응답. **허용 목록**만 담는다.

    실행 ID·워크플로우 ID·노드 이름·커버리지·시도·진단은 넣지 않는다. 그것들은
    관리자 진단 경로(`admin_diagnostics`·`section_preview.build_diagnostics_view`)의
    몫이다. 빈 보조 항목은 키 자체를 넣지 않는다(빈 카드·누락 안내 금지).
    """
    document = preview.document
    fixture = document.fixture
    payload: dict[str, Any] = {
        "fixture": {
            "fixture_id": fixture.fixture_id,
            "home_team_id": fixture.home_team_id,
            "away_team_id": fixture.away_team_id,
            "league_id": fixture.league_id,
            "season": fixture.season,
            "kickoff_at": _iso(fixture.kickoff_at),
            "label": preview.fixture_label,
            "league": preview.league,
        },
        "headline": document.headline,
        "generated_at": _iso(generated_at),
        "data_as_of": _iso(data_as_of),
        "attribution": {
            "ai_forecast_label": AI_FORECAST_LABEL,
            "ai_forecast_note": (
                "관전 포인트와 예상은 확인된 자료를 바탕으로 한 AI 판단이며,"
                " 경기 결과를 보장하지 않습니다."
            ),
            "model": preview.attribution.get("model"),
            "provider": preview.attribution.get("provider"),
            "executed_at": preview.attribution.get("executed_at"),
        },
    }
    if document.watch_points:
        payload["watch_points"] = list(document.watch_points)
    if document.players_to_watch:
        payload["players_to_watch"] = [dict(item) for item in document.players_to_watch]
    if document.absences_impact:
        payload["absences_impact"] = document.absences_impact
    if document.external_outlook:
        payload["external_outlook"] = [dict(item) for item in document.external_outlook]
    if document.ai_prediction:
        payload["ai_prediction"] = dict(document.ai_prediction)
    if preview.sources:
        payload["sources"] = [dict(item) for item in preview.sources]
    payload["body"] = compose_reader_body(document)
    return payload


def admin_diagnostics(
    *,
    gaps: Sequence[Mapping[str, Any]],
    excluded_claims: Sequence[EvidenceClaim],
    diagnostics: Sequence[str],
    selected_inputs: Sequence[Mapping[str, Any]],
    contract_versions: Mapping[str, str],
) -> dict[str, Any]:
    """관리자 전용 진단. 독자용 응답과 **분리**해서 따로 낸다."""
    return {
        "gaps": [dict(item) for item in gaps],
        "excluded_claims": [
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "text": claim.text,
                "reason": claim.decision_reason,
            }
            for claim in excluded_claims
        ],
        "diagnostics": list(diagnostics),
        "selected_inputs": [dict(item) for item in selected_inputs],
        "contract_versions": dict(contract_versions),
    }
