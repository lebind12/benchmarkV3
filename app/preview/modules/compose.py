"""섹션 본문 조립 (결정적 조합, 추가 모델 호출 없음).

계획 §6 MP-05: "검증된 조사 결과에서 본문을 결정적으로 조립한다. 두 번째 숨은 LLM
호출을 두지 않는다." 그래서 이 모듈은 문자열 조립만 한다. 네트워크·모델 호출이 없다.

독자용 원칙(설계 §8):

- 본문에 자료 누락·호출 실패·재시도·진단 문구를 넣지 않는다. 그것은 관리자 진단으로만
  남는다.
- 채택된 사실·해석만 쓴다. 근거 없는 문장을 채워 넣지 않는다.
- 출처는 근거 목록으로 따로 낸다. 검색 출처는 실제 URL, API 자료는 스냅샷 참조다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from app.preview.contracts import EvidenceClaim, QualityStatus

__all__ = ["ComposedSection", "clean_model_labels", "compose_form_body"]

FORM_SECTION_TITLE = "경기력과 주목 선수"


@dataclass(frozen=True)
class ComposedSection:
    title: str
    body: str
    sources: tuple[Mapping[str, Any], ...]
    quality: QualityStatus
    unavailable_reason: str | None = None

    @property
    def unavailable(self) -> bool:
        return self.unavailable_reason is not None


# 모델이 스스로 붙인 사실/해석 표기. 본문에서는 이 표기를 읽히는 문장으로 바꾼다.
# 표기를 지우지 않고 해석에만 라벨을 남겨, 사실 진술과 해석이 섞이지 않게 한다.
# 콜론까지 표기의 일부로 본다(콜론 없는 자연스러운 "사실"이라는 단어는 건드리지 않음).
_MARKER = re.compile(
    r"(?P<kind>사실|fact|해석|interpretation)"
    r"\s*(?:[(（]\s*(?P<inner>fact|interpretation)\s*[)）])?"
    r"\s*[:：]",
    re.IGNORECASE,
)
_INTERPRETATION_KINDS = frozenset({"해석", "interpretation"})
_INTERPRETATION_PREFIX = "AI 해석으로는, "


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def clean_model_labels(text: Any) -> str:
    """모델이 붙인 `사실(fact):`/`해석(interpretation):` 표기를 읽히는 문장으로 바꾼다.

    표기 뒤 문장은 다음 표기 전까지 그 종류로 본다. 사실 표기는 지우고, 해석 구간에는
    "AI 해석으로는,"을 붙여 해석임을 본문에 남긴다.
    """
    raw = _clean(text)
    if not raw:
        return ""
    pieces: list[str] = []
    mode = "fact"
    cursor = 0
    for match in _MARKER.finditer(raw):
        segment = raw[cursor : match.start()].strip(" :：")
        if segment:
            pieces.append(
                (_INTERPRETATION_PREFIX + segment) if mode == "interpretation" else segment
            )
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
        pieces.append(
            (_INTERPRETATION_PREFIX + tail) if mode == "interpretation" else tail
        )
    return _clean(" ".join(pieces))


def _paragraphs(paragraphs: Sequence[str]) -> str:
    return "\n\n".join(part.strip() for part in paragraphs if part and part.strip())


def _kickoff_text(kickoff_iso: str | None) -> str | None:
    if not kickoff_iso:
        return None
    from datetime import datetime, timezone

    try:
        moment = datetime.fromisoformat(kickoff_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    kst = moment.astimezone(timezone.utc)
    # 독자에게는 날짜와 UTC 시각만 사실로 제시한다. 현지 시각을 지어내지 않는다.
    return f"{kst.date().isoformat()} {kst.strftime('%H:%M')} UTC"


def _source_rows(
    *,
    search_sources: Sequence[Mapping[str, Any]],
    api_rows: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for source in search_sources:
        url = source.get("url")
        if not url:
            continue
        rows.append(
            {
                "label": _clean(source.get("title") or source.get("domain") or url),
                "url": str(url),
                "kind": "search",
                "note": "Google Search grounding 인용 출처",
            }
        )
    for row in api_rows:
        rows.append(dict(row))
    return tuple(rows)


def _api_source_rows(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """API 자료 출처. URL이 없으므로 스냅샷 참조와 수집 시각을 적는다."""
    rows: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in payload.get("api_sources") or ():
        if not isinstance(row, Mapping):
            continue
        snapshot_id = row.get("snapshot_id")
        if not snapshot_id or str(snapshot_id) in seen:
            continue
        seen.add(str(snapshot_id))
        label = _clean(row.get("label") or "API-Football 자료")
        collected = row.get("collected_at")
        rows.append(
            {
                "label": label,
                "url": None,
                "kind": "api",
                "note": (
                    f"수집 {collected}" if collected else "수집 시각 미상"
                )
                + " · API-Football 저장 자료",
            }
        )
    return tuple(rows)


def _claim_texts(claims: Sequence[EvidenceClaim], kind_names: Sequence[str]) -> list[str]:
    wanted = {name for name in kind_names}
    return [
        _clean(claim.text)
        for claim in claims
        if claim.kind.value in wanted and claim.decision.value == "adopted" and claim.text
    ]


def compose_form_body(payload: Mapping[str, Any]) -> ComposedSection:
    """R1 조사 payload에서 독자용 본문을 만든다.

    `payload`는 `FormResearch.payload()`의 결과다. 본문을 만들 근거가 없으면 빈 본문과
    `unavailable_reason`을 돌려준다. 빈 본문을 성공으로 바꾸지 않는다.
    """
    fixture = payload.get("fixture") or {}
    home = _clean(fixture.get("home_team") or "홈팀")
    away = _clean(fixture.get("away_team") or "원정팀")
    league = _clean(fixture.get("league") or "")
    kickoff = _kickoff_text(fixture.get("kickoff_at"))

    watch_points = [item for item in payload.get("watch_points") or () if isinstance(item, Mapping)]
    hot_players = [item for item in payload.get("hot_players") or () if isinstance(item, Mapping)]
    recent_form = [item for item in payload.get("recent_form") or () if isinstance(item, Mapping)]
    importance = clean_model_labels(payload.get("match_importance"))
    claims = tuple(
        EvidenceClaim.from_dict(item)
        for item in payload.get("claims") or ()
        if isinstance(item, Mapping)
    )

    if not watch_points and not recent_form and not hot_players and not importance:
        return ComposedSection(
            title=FORM_SECTION_TITLE,
            body="",
            sources=(),
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "채택된 근거가 없어 경기력·주목 선수 본문을 만들지 않았습니다."
            ),
        )

    opening_bits = [f"{home}와 {away}의 맞대결입니다."]
    if league:
        opening_bits.append(f"{league} 경기이며," if kickoff else f"{league} 경기입니다.")
    if kickoff:
        opening_bits.append(f"킥오프는 {kickoff}입니다.")
    paragraphs: list[str] = [" ".join(opening_bits)]

    if importance:
        paragraphs.append(importance)

    if recent_form:
        form_sentences: list[str] = []
        for item in recent_form:
            team = _clean(item.get("team")) or "해당 팀"
            summary = clean_model_labels(item.get("summary"))
            if not summary:
                continue
            form_sentences.append(f"{team}는 {summary}" if not summary.startswith(team) else summary)
        if form_sentences:
            paragraphs.append(" ".join(form_sentences))

    if watch_points:
        for item in watch_points:
            title = clean_model_labels(item.get("title"))
            detail = clean_model_labels(item.get("detail"))
            if title and detail:
                paragraphs.append(f"{title}. {detail}")
            elif detail or title:
                paragraphs.append(detail or title)

    if hot_players:
        player_bits: list[str] = []
        for item in hot_players:
            player = _clean(item.get("player"))
            team = _clean(item.get("team"))
            reason = clean_model_labels(item.get("reason"))
            if not player or not reason:
                continue
            who = f"{player}({team})" if team else player
            player_bits.append(f"{who}는 {reason}")
        if player_bits:
            paragraphs.append("주목할 선수는 이렇습니다. " + " ".join(player_bits))

    body = _paragraphs(paragraphs)
    if not body.strip():
        return ComposedSection(
            title=FORM_SECTION_TITLE,
            body="",
            sources=(),
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason="본문 문장을 만들지 못했습니다.",
        )

    sources = _source_rows(
        search_sources=[item for item in payload.get("sources") or () if isinstance(item, Mapping)],
        api_rows=_api_source_rows(payload),
    )
    return ComposedSection(
        title=FORM_SECTION_TITLE,
        body=body,
        sources=sources,
        quality=QualityStatus.READY if (watch_points or recent_form) else QualityStatus.PENDING,
    )


def adopted_fact_lines(payload: Mapping[str, Any]) -> list[str]:
    """진단용: 본문에 쓰인 채택 사실 목록. 본문에는 넣지 않는다."""
    claims = [
        EvidenceClaim.from_dict(item)
        for item in payload.get("claims") or ()
        if isinstance(item, Mapping)
    ]
    return _claim_texts(claims, ("fact",))
