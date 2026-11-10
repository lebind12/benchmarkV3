"""R3 배당·외부 전망 조사 (MP-07).

이 모듈이 하는 일은 하나다. **한 경기의 배당과 외부 전망을, 출처가 남은 근거로**
정리해 프리뷰 섹션 본문과 근거를 만든다. 조사 모델 호출은 정상 경로에서 1회이며,
그 호출은 `provider.request_model`만 통과한다.

세 가지 자료를 **끝까지 섞지 않는다.**

| 자료 | 어디서 오나 | 무엇으로 남나 |
|---|---|---|
| 경기 전 승무패 배당 | D0가 수집한 API-Football 원문 | `ClaimKind.EXTERNAL_FORECAST`, 업체·시장·기준 시각 |
| 외부 매체 전망 | 모델의 Google Search grounding 결과 | `ClaimKind.EXTERNAL_FORECAST`, 매체·URL·게시 시각 |
| 제공자 알고리즘 예측 | D0가 수집한 API-Football predictions | `ClaimKind.API_PREDICTION`, 매체 의견이 아님을 명시 |

정직성 규칙:

- **다른 경기의 배당은 이 경기의 승무패가 아니다.** 경기 ID가 다르면 채택하지 않고
  관리자 기록에만 남긴다. 컵대회 진출(qualification)·라이브·핸디캡 같은 다른 시장도
  경기 전 승무패가 아니므로 같은 방식으로 제외한다.
- **검색 결과에 없는 URL은 만들지 않는다.** 모델이 매체 전망을 적어도 그 주소가
  grounding 출처 목록에 없으면 채택하지 않는다. grounding 메타데이터 자체가 없으면
  매체 전망을 채택하지 않고 그 사유를 관리자 기록에 남긴다. 독자 본문에는 이 사유를
  쓰지 않는다.
- **원문에 없는 예상 스코어를 만들지 않는다.** 인용한 기사가 스코어를 적지 않았으면
  예상 스코어 항목은 비어 있다.
- **API 예측 숫자를 매체 의견으로 바꾸지 않는다.** 문단 제목과 claim 종류로 구분한다.
- **베팅 권유를 쓰지 않는다.** 배당은 관전 참고 자료로만 정리한다.
- **독자 본문에 누락·오류·재시도 안내를 넣지 않는다.** 확보한 근거로만 문단을 만들고,
  근거가 없는 항목은 문단 자체를 생략한다. 미확보 사유는 `coverage`·`diagnostics`·
  `payload['grounding']`에만 남는다.

경계:

- 새 테이블·마이그레이션·공통 계약 변경이 없다. 저장은 MP-02·MP-04가 만든
  `preview_dev` 표(실행·스냅샷·시도·아티팩트·결과)를 그대로 쓴다.
- 재시도·예산은 `execute_request` 하나가 소유한다. 이 파일은 재시도 루프를 만들지
  않는다. 모델 호출은 `request_model`을 정확히 한 번 부른다.
- 본문은 확정된 조사 결과에서 **결정적으로** 만든다. 두 번째 숨은 모델 호출이나
  자기 검토(supervisor/reflection) 단계를 두지 않는다.
- `app/preview/registry.py`·`modules/__init__.py`·프런트 공통 라우터·타입은 MP-05
  소유다. 이 파일은 등록에 필요한 값만 내보낸다.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from sqlalchemy import select
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
    compute_input_hash,
)
from app.preview.models import PreviewArtifact, PreviewResult
from app.preview.retry import RunBudget
from app.preview.sources import api_football as api

__all__ = [
    "IMPLEMENTATION_VERSION",
    "MODULE_ID",
    "OUTLOOK_OUTPUT_CONTRACT_VERSION",
    "PROMPT_VERSION",
    "GROUNDING_TOOL",
    "ApiPrediction",
    "GroundingRecord",
    "MediaForecast",
    "OddsObservation",
    "OutlookResearch",
    "ROOT_TITLE",
    "build_generation_config",
    "compose_outlook_body",
    "compose_outlook_section",
    "compose_outlook_sources",
    "outlook_node",
    "outlook_node_implementation",
    "outlook_prompt",
    "parse_media_response",
    "research_outlook",
    "validate_media_forecasts",
]

MODULE_ID = "R3"
IMPLEMENTATION_VERSION = "mp07-r3-1"
PROMPT_VERSION = "r3-outlook-1"
# 섹션 결과에 영향을 주는 출력 계약 축. MP-05가 registry의
# `section_outlook` output_contract_version을 올릴 때 참고할 값이다.
OUTLOOK_OUTPUT_CONTRACT_VERSION = "mp07-outlook-output-1"

ROOT_TITLE = "배당과 외부 전망"
MEDIA_SECTION_TITLE = "외부 매체 전망"
ODDS_SECTION_TITLE = "경기 전 승무패 배당"
API_SECTION_TITLE = "제공자 알고리즘 예측"

# Google Search grounding 도구. 공식 문서의 tools 형식을 그대로 쓰고, 공통 transport가
# `types.GenerateContentConfig(**generation_config)`로 변환한다.
GROUNDING_TOOL: Mapping[str, Any] = {"google_search": {}}

# 이 모듈이 쓰는 조사 주제 키(coverage). D0 주제 라벨과 섞지 않는다.
TOPIC_ODDS = "경기 전 승무패 배당"
TOPIC_MEDIA = "외부 매체 전망"
TOPIC_API_PREDICTION = "제공자 알고리즘 예측"
TOPIC_SEARCH = "검색 근거(Google Search grounding)"

MEDIA_URL_MISSING_REASON = (
    "검색 결과 출처 목록에서 이 주소를 확인하지 못해 매체 전망으로 채택하지 않았습니다."
)
GROUNDING_ABSENT_REASON = (
    "모델 응답에 Google Search grounding 메타데이터가 없어 검색 출처를 확인할 수"
    " 없습니다. 확인되지 않은 매체 전망은 채택하지 않았습니다."
)
NO_SEARCH_QUERY_REASON = (
    "grounding에 검색 질의가 기록되지 않았습니다. 제공자 내부 검색 실행 여부는"
    " 알 수 없으며 추정하지 않습니다."
)
EMPTY_MEDIA_REASON = "검색으로 확인한 매체 전망이 응답에 없습니다."
TRANSPORT_MISSING_REASON = (
    "모델 전송 계층이 주입되지 않아 외부 매체 전망 조사를 실행하지 않았습니다."
)

def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 자료 구조 (이 모듈 전용, 공통 계약은 바꾸지 않는다)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OddsObservation:
    """경기 전 승무패 배당 한 건. 반드시 업체·시장·기준 시각을 함께 둔다."""

    claim_id: str
    bookmaker: str | None
    bookmaker_id: int | None
    market: str | None
    market_id: int | None
    observed_at: datetime | None
    home: str | None
    draw: str | None
    away: str | None
    fixture_id: int | None
    snapshot_id: uuid.UUID | None
    adopted: bool
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "bookmaker": self.bookmaker,
            "bookmaker_id": self.bookmaker_id,
            "market": self.market,
            "market_id": self.market_id,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "home": self.home,
            "draw": self.draw,
            "away": self.away,
            "fixture_id": self.fixture_id,
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
            "adopted": self.adopted,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class MediaForecast:
    """외부 매체 전망 한 건. URL과 게시 시각, grounding 확인 여부를 함께 둔다."""

    claim_id: str
    publisher: str | None
    url: str
    published_at: str | None
    statement: str
    predicted_score: str | None
    grounding_chunk_indices: tuple[int, ...]
    source_confirmed: bool
    adopted: bool
    rejection_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "publisher": self.publisher,
            "url": self.url,
            "published_at": self.published_at,
            "statement": self.statement,
            "predicted_score": self.predicted_score,
            "grounding_chunk_indices": list(self.grounding_chunk_indices),
            "source_confirmed": self.source_confirmed,
            "adopted": self.adopted,
            "rejection_reason": self.rejection_reason,
        }


@dataclass(frozen=True)
class ApiPrediction:
    """제공자(API-Football) 알고리즘 예측. 매체 의견도 이 서비스의 결론도 아니다."""

    claim_id: str
    provider: str
    winner_name: str | None
    winner_comment: str | None
    advice: str | None
    under_over: str | None
    percent_home: str | None
    percent_draw: str | None
    percent_away: str | None
    snapshot_id: uuid.UUID | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "provider": self.provider,
            "winner_name": self.winner_name,
            "winner_comment": self.winner_comment,
            "advice": self.advice,
            "under_over": self.under_over,
            "percent_home": self.percent_home,
            "percent_draw": self.percent_draw,
            "percent_away": self.percent_away,
            "snapshot_id": str(self.snapshot_id) if self.snapshot_id else None,
        }


@dataclass(frozen=True)
class GroundingRecord:
    """Google Search grounding 원문 메타데이터. 관리자 화면 전용이다.

    `present=False`이면 모델 응답에 grounding 메타데이터가 없다는 뜻이다. 그 사실을
    숨기지 않고 `absence_reason`에 남긴다. 이 문장은 독자 본문에 쓰지 않는다.
    """

    present: bool
    web_search_queries: tuple[str, ...] = ()
    chunk_uris: tuple[str, ...] = ()
    chunk_titles: tuple[str, ...] = ()
    supports: tuple[Mapping[str, Any], ...] = ()
    search_suggestions_html: str | None = None
    absence_reason: str | None = None
    missing_queries_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "present": self.present,
            "web_search_queries": list(self.web_search_queries),
            "chunk_uris": list(self.chunk_uris),
            "chunk_titles": list(self.chunk_titles),
            "supports": [dict(item) for item in self.supports],
            "search_suggestions_html": self.search_suggestions_html,
            "absence_reason": self.absence_reason,
            "missing_queries_note": self.missing_queries_note,
        }


@dataclass(frozen=True)
class OutlookResearch:
    """R3 조사 결과. 독자 본문·근거와 관리자 진단을 한 묶음으로 돌려준다."""

    fixture: FixtureIdentity | None
    mode: RunMode
    odds: tuple[OddsObservation, ...] = ()
    rejected_odds: tuple[OddsObservation, ...] = ()
    media: tuple[MediaForecast, ...] = ()
    rejected_media: tuple[MediaForecast, ...] = ()
    api_prediction: ApiPrediction | None = None
    grounding: GroundingRecord = field(default_factory=lambda: GroundingRecord(present=False))
    claims: tuple[EvidenceClaim, ...] = ()
    coverage: tuple[CoverageEntry, ...] = ()
    diagnostics: tuple[str, ...] = ()
    quality: QualityStatus = QualityStatus.INSUFFICIENT
    model_text: str | None = None
    external_calls: int = 0
    model_name: str | None = None
    prompt_version: str = PROMPT_VERSION
    implementation_version: str = IMPLEMENTATION_VERSION
    attempt_summary: Mapping[str, Any] = field(default_factory=dict)
    input_hash: str = ""

    # -- 독자용 ------------------------------------------------------------

    @property
    def reader_body(self) -> str:
        return compose_outlook_body(self)

    @property
    def reader_sources(self) -> tuple[dict[str, Any], ...]:
        return compose_outlook_sources(self)

    @property
    def has_reader_content(self) -> bool:
        return bool(self.reader_body.strip())

    @property
    def adopted_claim_count(self) -> int:
        return len([claim for claim in self.claims if claim.decision is ClaimDecision.ADOPTED])

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": MODULE_ID,
            "implementation_version": self.implementation_version,
            "prompt_version": self.prompt_version,
            "outlook_contract_version": OUTLOOK_OUTPUT_CONTRACT_VERSION,
            "mode": self.mode.value,
            "fixture": self.fixture.to_dict() if self.fixture else None,
            "odds": [item.to_dict() for item in self.odds],
            "rejected_odds": [item.to_dict() for item in self.rejected_odds],
            "media": [item.to_dict() for item in self.media],
            "rejected_media": [item.to_dict() for item in self.rejected_media],
            "api_prediction": self.api_prediction.to_dict() if self.api_prediction else None,
            "grounding": self.grounding.to_dict(),
            "claims": [claim.to_dict() for claim in self.claims],
            "coverage": [entry.to_dict() for entry in self.coverage],
            "diagnostics": list(self.diagnostics),
            "quality": self.quality.value,
            "model_text": self.model_text,
            "external_calls": self.external_calls,
            "model_name": self.model_name,
            "attempt_summary": dict(self.attempt_summary),
            "input_hash": self.input_hash,
            "reader_body": self.reader_body,
            "reader_sources": [dict(item) for item in self.reader_sources],
        }


# --------------------------------------------------------------------------
# 원문 해석 도우미
# --------------------------------------------------------------------------


def _get(mapping: Mapping[str, Any], snake: str, camel: str | None = None) -> Any:
    """SDK는 snake_case, 녹화 원문은 camelCase일 수 있다. 둘 다 읽는다."""
    if snake in mapping:
        return mapping[snake]
    if camel and camel in mapping:
        return mapping[camel]
    return None


def _first_candidate(raw_response: Any) -> Mapping[str, Any] | None:
    if not isinstance(raw_response, Mapping):
        return None
    candidates = raw_response.get("candidates")
    if not isinstance(candidates, Sequence):
        return None
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _normalize_url(url: str) -> tuple[str, str] | None:
    """비교용 (호스트, 경로). 추적 인자·조각은 무시한다. HTTP(S)만 인정한다."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return parts.netloc.lower(), parts.path.rstrip("/").lower()


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "시각 미확인"
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# --------------------------------------------------------------------------
# D0 자료 (배당·제공자 예측) 읽기
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _D0Evidence:
    """D0가 남긴 배당·예측 원문. 네트워크 호출 없이 저장된 아티팩트만 읽는다."""

    odds_raw: Mapping[str, Any] | None = None
    prediction_raw: Mapping[str, Any] | None = None
    odds_snapshot_id: uuid.UUID | None = None
    prediction_snapshot_id: uuid.UUID | None = None
    notes: tuple[str, ...] = ()


def _artifact_body(session: Session, artifact_id: Any) -> Mapping[str, Any] | None:
    if not artifact_id:
        return None
    try:
        parsed_id = uuid.UUID(str(artifact_id))
    except (TypeError, ValueError):
        return None
    row = session.get(PreviewArtifact, parsed_id)
    if row is None or not row.body:
        return None
    try:
        body = json.loads(row.body)
    except (TypeError, ValueError):
        return None
    return body if isinstance(body, Mapping) else None


def _latest_d0_topics(session: Session, run_id: uuid.UUID) -> Mapping[str, Any] | None:
    row = session.scalars(
        select(PreviewResult)
        .where(PreviewResult.run_id == run_id, PreviewResult.module_id == "D0")
        .order_by(PreviewResult.created_at.desc(), PreviewResult.version.desc())
        .limit(1)
    ).first()
    if row is None or not isinstance(row.payload, Mapping):
        return None
    inner = row.payload.get("payload")
    topics = row.payload.get("topics")
    if isinstance(inner, Mapping) and isinstance(inner.get("topics"), Mapping):
        return inner["topics"]
    return topics if isinstance(topics, Mapping) else None


def _resolve_d0_evidence(
    session: Session | None,
    *,
    run_id: uuid.UUID | None,
    provided: Mapping[str, Any] | None,
) -> _D0Evidence:
    """배당·예측 원문을 찾는다.

    우선순위는 (1) 실행 기록의 D0 결과가 가리키는 저장 아티팩트, (2) 호출자가 넘긴
    `d0` 묶음이다. 둘 다 없으면 배당·예측 없이 진행하고 그 사실을 coverage에 남긴다.
    어떤 경우에도 새 API 호출을 만들지 않는다.
    """
    notes: list[str] = []
    topics: Mapping[str, Any] = {}
    if isinstance(provided, Mapping) and isinstance(provided.get("topics"), Mapping):
        topics = provided["topics"]
    if not topics and session is not None and run_id is not None:
        found = _latest_d0_topics(session, run_id)
        if isinstance(found, Mapping):
            topics = found
        elif provided is None:
            notes.append(
                "이 실행에서 D0 결과를 찾지 못했습니다. 배당·제공자 예측 없이 조사합니다."
            )

    odds_raw = None
    prediction_raw = None
    odds_snapshot_id = None
    prediction_snapshot_id = None

    if session is not None:
        odds_topic = topics.get("odds") if isinstance(topics, Mapping) else None
        prediction_topic = (
            topics.get("predictions") if isinstance(topics, Mapping) else None
        )
        if isinstance(odds_topic, Mapping):
            odds_raw = _artifact_body(session, odds_topic.get("artifact_id"))
            odds_snapshot_id = _as_uuid(odds_topic.get("snapshot_id"))
        if isinstance(prediction_topic, Mapping):
            prediction_raw = _artifact_body(session, prediction_topic.get("artifact_id"))
            prediction_snapshot_id = _as_uuid(prediction_topic.get("snapshot_id"))

    # 호출자가 이미 해석한 원문을 넘기면 그 값을 쓴다(테스트·재생 경로).
    if isinstance(provided, Mapping):
        if odds_raw is None and isinstance(provided.get("odds_raw"), Mapping):
            odds_raw = provided["odds_raw"]
        if prediction_raw is None and isinstance(provided.get("prediction_raw"), Mapping):
            prediction_raw = provided["prediction_raw"]

    return _D0Evidence(
        odds_raw=odds_raw,
        prediction_raw=prediction_raw,
        odds_snapshot_id=odds_snapshot_id,
        prediction_snapshot_id=prediction_snapshot_id,
        notes=tuple(notes),
    )


def _as_uuid(value: Any) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# 배당 검증
# --------------------------------------------------------------------------

ODDS_LIVE_MARKERS = ("live", "in-play", "inplay", "1st half", "2nd half")
ODDS_PREMATCH_MARKERS = ("match winner", "1x2")
# 경기 전 승무패가 아닌 시장. 이름에 이 표시가 있으면 승무패로 쓰지 않는다.
ODDS_OTHER_MARKET_MARKERS = (
    "qualif",
    "to advance",
    "handicap",
    "over/under",
    "correct score",
    "double chance",
    "both teams",
    "draw no bet",
    "asian",
    "corners",
    "cards",
    "goalscorer",
    "winner (live)",
)


def _market_verdict(market_name: Any) -> tuple[bool, str | None]:
    """경기 전 승무패 시장인지 판정한다. 모르는 시장은 채택하지 않는다."""
    if not isinstance(market_name, str) or not market_name.strip():
        return False, "시장 이름이 없어 경기 전 승무패인지 확인할 수 없습니다."
    lowered = market_name.strip().lower()
    if any(marker in lowered for marker in ODDS_LIVE_MARKERS):
        return False, (
            f"'{market_name}'은(는) 라이브·진행 중 시장이라 경기 전 배당이 아닙니다."
        )
    if any(marker in lowered for marker in ODDS_OTHER_MARKET_MARKERS):
        return False, (
            f"'{market_name}' 시장은 경기 전 승무패가 아니어서 이 경기의 1X2 배당으로"
            " 쓰지 않습니다."
        )
    if not any(marker in lowered for marker in ODDS_PREMATCH_MARKERS):
        return False, (
            f"'{market_name}' 시장은 경기 전 승무패로 확인되지 않아 채택하지 않았습니다."
        )
    return True, None


def _odds_records(raw: Mapping[str, Any]) -> tuple[Sequence[Mapping[str, Any]], str | None]:
    records = raw.get("response")
    if isinstance(records, Mapping):
        records = [records]
    if not isinstance(records, (list, tuple)):
        return (), "배당 응답의 response가 목록이 아닙니다."
    return tuple(item for item in records if isinstance(item, Mapping)), None


def _validate_odds(
    raw: Mapping[str, Any] | None,
    *,
    fixture_id: int | None,
    collected_at: datetime,
    snapshot_id: uuid.UUID | None,
) -> tuple[tuple[OddsObservation, ...], tuple[OddsObservation, ...], tuple[str, ...]]:
    """배당 원문을 검증한다. 채택분과 제외분, 진단 문장을 나눠 돌려준다."""
    if raw is None:
        return (), (), ()
    records, shape_error = _odds_records(raw)
    diagnostics: list[str] = []
    if shape_error:
        return (), (), (shape_error,)
    errors = raw.get("errors")
    if isinstance(errors, (list, tuple, Mapping)) and errors:
        return (), (), ("배당 응답에 제공자 오류가 있어 채택하지 않았습니다.",)

    adopted: list[OddsObservation] = []
    rejected: list[OddsObservation] = []
    for record in records:
        record_fixture = record.get("fixture")
        record_fixture_id = None
        if isinstance(record_fixture, Mapping):
            record_fixture_id = record_fixture.get("id")
        record_update = _as_datetime(record.get("update"))
        bookmakers = record.get("bookmakers")
        if not isinstance(bookmakers, (list, tuple)):
            diagnostics.append("배당 응답의 bookmakers가 목록이 아닙니다.")
            continue
        for book in bookmakers:
            if not isinstance(book, Mapping):
                continue
            book_update = _as_datetime(book.get("update")) or record_update
            bets = book.get("bets")
            if not isinstance(bets, (list, tuple)):
                continue
            for bet in bets:
                if not isinstance(bet, Mapping):
                    continue
                market_name = bet.get("name")
                ok, reason = _market_verdict(market_name)
                odds_by_label: dict[str, str] = {}
                values = bet.get("values")
                if isinstance(values, (list, tuple)):
                    for value in values:
                        if not isinstance(value, Mapping):
                            continue
                        label = value.get("value")
                        odd = value.get("odd")
                        if isinstance(label, str) and odd is not None:
                            odds_by_label[label.strip().lower()] = str(odd)
                claim_id = (
                    f"r3-odds-{book.get('id') or 'x'}-{bet.get('id') or 'x'}"
                )
                observation = OddsObservation(
                    claim_id=claim_id,
                    bookmaker=book.get("name") if isinstance(book.get("name"), str) else None,
                    bookmaker_id=_as_int(book.get("id")),
                    market=market_name if isinstance(market_name, str) else None,
                    market_id=_as_int(bet.get("id")),
                    observed_at=book_update,
                    home=odds_by_label.get("home"),
                    draw=odds_by_label.get("draw"),
                    away=odds_by_label.get("away"),
                    fixture_id=_as_int(record_fixture_id),
                    snapshot_id=snapshot_id,
                    adopted=True,
                )
                # 1) 경기 일치. 다른 경기의 배당은 이 경기의 승무패가 아니다.
                if fixture_id is not None and observation.fixture_id is not None:
                    if observation.fixture_id != fixture_id:
                        rejected.append(
                            _reject(
                                observation,
                                f"요청한 경기 {fixture_id}가 아니라 {observation.fixture_id}의"
                                " 배당이라 채택하지 않았습니다.",
                            )
                        )
                        continue
                elif fixture_id is not None and observation.fixture_id is None:
                    rejected.append(
                        _reject(
                            observation,
                            "응답에 경기 ID가 없어 이 경기의 배당인지 확인할 수 없습니다.",
                        )
                    )
                    continue
                # 2) 시장 종류.
                if not ok:
                    rejected.append(_reject(observation, reason))
                    continue
                # 3) 승무패 세 값이 모두 있어야 한다.
                if not (observation.home and observation.away):
                    rejected.append(
                        _reject(
                            observation,
                            "홈·원정 배당이 모두 있지 않아 승무패로 채택하지 않았습니다.",
                        )
                    )
                    continue
                # 4) 기준 시각과 신선도. 시점을 모르면 최신 확정 배당으로 올리지 않는다.
                if observation.observed_at is None:
                    rejected.append(
                        _reject(
                            observation,
                            "제공자 갱신 시각이 없어 최신 배당으로 채택하지 않았습니다.",
                        )
                    )
                    continue
                fresh, freshness_reason = api.odds_freshness(
                    api.OddsRecord(
                        bookmaker_id=observation.bookmaker_id,
                        bookmaker=observation.bookmaker,
                        market_id=observation.market_id,
                        market=observation.market,
                        home=observation.home,
                        draw=observation.draw,
                        away=observation.away,
                        updated_at=observation.observed_at,
                    ),
                    collected_at,
                )
                if not fresh:
                    rejected.append(_reject(observation, freshness_reason))
                    continue
                adopted.append(observation)
    return tuple(adopted), tuple(rejected), tuple(diagnostics)


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None


def _reject(observation: OddsObservation, reason: str | None) -> OddsObservation:
    return OddsObservation(
        claim_id=observation.claim_id,
        bookmaker=observation.bookmaker,
        bookmaker_id=observation.bookmaker_id,
        market=observation.market,
        market_id=observation.market_id,
        observed_at=observation.observed_at,
        home=observation.home,
        draw=observation.draw,
        away=observation.away,
        fixture_id=observation.fixture_id,
        snapshot_id=observation.snapshot_id,
        adopted=False,
        rejection_reason=reason,
    )


# --------------------------------------------------------------------------
# 제공자 알고리즘 예측
# --------------------------------------------------------------------------


def _parse_api_prediction(
    raw: Mapping[str, Any] | None,
    *,
    fixture_id: int | None,
    snapshot_id: uuid.UUID | None,
) -> tuple[ApiPrediction | None, str | None]:
    """API 예측을 읽는다. 다른 경기·빈 응답은 채택하지 않는다."""
    if raw is None:
        return None, None
    try:
        envelope = api.parse_envelope(raw)
        envelope.require_ok()
        record = api.parse_prediction(envelope, fixture_id=fixture_id)
    except api.WrongFixture as exc:
        return None, f"제공자 예측이 다른 경기의 것이라 채택하지 않았습니다: {exc}"
    except api.ApiFootballError as exc:
        return None, f"제공자 예측을 읽지 못했습니다: {exc}"
    if record is None:
        return None, None
    has_value = any(
        (
            record.winner_name,
            record.advice,
            record.percent_home,
            record.percent_draw,
            record.percent_away,
        )
    )
    if not has_value:
        return None, "제공자 예측 응답에 값이 없어 채택하지 않았습니다."
    return (
        ApiPrediction(
            claim_id="r3-api-prediction",
            provider=api.API_PROVIDER,
            winner_name=record.winner_name,
            winner_comment=record.winner_comment,
            advice=record.advice,
            under_over=record.under_over,
            percent_home=record.percent_home,
            percent_draw=record.percent_draw,
            percent_away=record.percent_away,
            snapshot_id=snapshot_id,
        ),
        None,
    )


# --------------------------------------------------------------------------
# grounding 메타데이터
# --------------------------------------------------------------------------


def _extract_grounding(raw_response: Any) -> GroundingRecord:
    candidate = _first_candidate(raw_response)
    if candidate is None:
        return GroundingRecord(
            present=False,
            absence_reason="모델 응답에 후보가 없어 검색 출처를 확인할 수 없습니다.",
        )
    metadata = _get(candidate, "grounding_metadata", "groundingMetadata")
    if not isinstance(metadata, Mapping) or not metadata:
        return GroundingRecord(present=False, absence_reason=GROUNDING_ABSENT_REASON)

    queries = _get(metadata, "web_search_queries", "webSearchQueries") or ()
    query_list = tuple(str(item) for item in queries if str(item).strip())

    chunks = _get(metadata, "grounding_chunks", "groundingChunks") or ()
    uris: list[str] = []
    titles: list[str] = []
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            continue
        web = _get(chunk, "web", "web")
        if isinstance(web, Mapping):
            uri = web.get("uri")
            title = web.get("title")
            if isinstance(uri, str) and uri.strip():
                uris.append(uri.strip())
            if isinstance(title, str) and title.strip():
                titles.append(title.strip())

    supports_raw = _get(metadata, "grounding_supports", "groundingSupports") or ()
    supports: list[Mapping[str, Any]] = []
    for support in supports_raw:
        if not isinstance(support, Mapping):
            continue
        segment = _get(support, "segment", "segment") or {}
        supports.append(
            {
                "grounding_chunk_indices": list(
                    _get(support, "grounding_chunk_indices", "groundingChunkIndices") or ()
                ),
                "confidence_scores": list(
                    _get(support, "confidence_scores", "confidenceScores") or ()
                ),
                "segment_text": (
                    segment.get("text") if isinstance(segment, Mapping) else None
                ),
            }
        )

    entry_point = _get(metadata, "search_entry_point", "searchEntryPoint")
    suggestions = None
    if isinstance(entry_point, Mapping):
        rendered = _get(entry_point, "rendered_content", "renderedContent")
        if isinstance(rendered, str) and rendered.strip():
            suggestions = rendered

    return GroundingRecord(
        present=True,
        web_search_queries=query_list,
        chunk_uris=tuple(dict.fromkeys(uris)),
        chunk_titles=tuple(dict.fromkeys(titles)),
        supports=tuple(supports),
        search_suggestions_html=suggestions,
        absence_reason=None,
        missing_queries_note=None if query_list else NO_SEARCH_QUERY_REASON,
    )


def _match_grounding_indices(
    grounding: GroundingRecord, url: str
) -> tuple[int, ...]:
    target = _normalize_url(url)
    if target is None:
        return ()
    matches: list[int] = []
    for index, uri in enumerate(grounding.chunk_uris):
        if _normalize_url(uri) == target:
            matches.append(index)
    return tuple(matches)


def _published_after_kickoff(published_at: str | None, kickoff_at: datetime | None) -> bool:
    if not published_at or kickoff_at is None:
        return False
    moment = _as_datetime(published_at)
    if moment is None:
        return False
    return moment > kickoff_at


def parse_media_response(text: str | None) -> tuple[list[dict[str, Any]], str | None]:
    """모델 응답에서 매체 전망 후보를 꺼낸다. 실패는 `None` 목록으로 알린다.

    JSON만 요구하지만 모델이 코드 펜스를 붙이는 경우가 있어 첫 `{`부터 마지막 `}`까지만
    읽는다. 그 마저 실패하면 빈 목록과 사유를 돌려준다.
    """
    if not text or not text.strip():
        return [], "모델 응답 본문이 비어 있습니다."
    stripped = text.strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return [], "모델 응답에서 JSON 객체를 찾지 못했습니다."
    try:
        parsed = json.loads(stripped[start : end + 1])
    except (TypeError, ValueError):
        return [], "모델 응답 JSON을 해석하지 못했습니다."
    if not isinstance(parsed, Mapping):
        return [], "모델 응답 JSON이 객체가 아닙니다."
    raw_items = parsed.get("media_forecasts")
    if raw_items is None:
        raw_items = parsed.get("mediaForecasts")
    if raw_items is None:
        return [], "모델 응답에 media_forecasts 항목이 없습니다."
    if not isinstance(raw_items, (list, tuple)):
        return [], "모델 응답의 media_forecasts가 목록이 아닙니다."
    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            items.append(dict(item))
    return items, None


def validate_media_forecasts(
    raw_items: Sequence[Mapping[str, Any]],
    *,
    grounding: GroundingRecord,
    kickoff_at: datetime | None,
) -> tuple[tuple[MediaForecast, ...], tuple[MediaForecast, ...], tuple[str, ...]]:
    """모델이 적은 매체 전망을 grounding과 대조한다.

    - URL이 검색 결과 출처에 없으면 채택하지 않는다(URL 창작 방지).
    - grounding 자체가 없으면 매체 전망을 채택하지 않는다.
    - 게시 시각이 킥오프 이후면 경기 전 자료가 아니므로 채택하지 않는다.
    - 기사가 스코어를 적지 않았으면 예상 스코어를 만들지 않는다.
    """
    adopted: list[MediaForecast] = []
    rejected: list[MediaForecast] = []
    diagnostics: list[str] = []
    for index, item in enumerate(raw_items):
        url = item.get("url")
        statement = item.get("statement")
        publisher = item.get("publisher")
        published_raw = item.get("published_at") or item.get("publishedAt")
        predicted_score = item.get("predicted_score") or item.get("predictedScore")
        url_text = url.strip() if isinstance(url, str) else ""
        statement_text = statement.strip() if isinstance(statement, str) else ""
        forecast_id = f"r3-media-{index + 1}"
        score_text = (
            str(predicted_score).strip() if isinstance(predicted_score, (str, int, float)) else None
        )
        # 스코어를 적었다고 주장하면서 실제 문장에 없으면 만들지 않는다.
        if score_text and score_text not in statement_text:
            diagnostics.append(
                f"매체 전망 {index + 1}: 예상 스코어 '{score_text}'가 인용문에 없어"
                " 스코어를 비웠습니다."
            )
            score_text = None
        forecast = MediaForecast(
            claim_id=forecast_id,
            publisher=publisher.strip() if isinstance(publisher, str) and publisher.strip() else None,
            url=url_text,
            published_at=str(published_raw).strip() if published_raw else None,
            statement=statement_text,
            predicted_score=score_text,
            grounding_chunk_indices=(),
            source_confirmed=False,
            adopted=False,
        )
        if not url_text:
            rejected.append(_reject_media(forecast, MEDIA_URL_MISSING_REASON))
            continue
        if not statement_text:
            rejected.append(
                _reject_media(
                    forecast,
                    "매체가 이 경기를 어떻게 봤는지 적은 문장이 없어 전망으로 채택하지"
                    " 않았습니다.",
                )
            )
            continue
        if not ground_ok(grounding):
            rejected.append(_reject_media(forecast, GROUNDING_ABSENT_REASON))
            continue
        matches = _match_grounding_indices(grounding, url_text)
        if not matches:
            rejected.append(_reject_media(forecast, MEDIA_URL_MISSING_REASON))
            continue
        if _published_after_kickoff(forecast.published_at, kickoff_at):
            rejected.append(
                _reject_media(
                    forecast,
                    "게시 시각이 킥오프 이후라 경기 전 전망으로 채택하지 않았습니다.",
                )
            )
            continue
        adopted.append(
            MediaForecast(
                claim_id=forecast.claim_id,
                publisher=forecast.publisher,
                url=forecast.url,
                published_at=forecast.published_at,
                statement=forecast.statement,
                predicted_score=forecast.predicted_score,
                grounding_chunk_indices=matches,
                source_confirmed=True,
                adopted=True,
            )
        )
    return tuple(adopted), tuple(rejected), tuple(diagnostics)


def ground_ok(grounding: GroundingRecord) -> bool:
    """매체 전망을 확인할 수 있는 grounding인지. 출처 목록이 있어야 한다."""
    return grounding.present and bool(grounding.chunk_uris)


def _reject_media(forecast: MediaForecast, reason: str | None) -> MediaForecast:
    return MediaForecast(
        claim_id=forecast.claim_id,
        publisher=forecast.publisher,
        url=forecast.url,
        published_at=forecast.published_at,
        statement=forecast.statement,
        predicted_score=forecast.predicted_score,
        grounding_chunk_indices=forecast.grounding_chunk_indices,
        source_confirmed=False,
        adopted=False,
        rejection_reason=reason,
    )


# --------------------------------------------------------------------------
# 프롬프트와 모델 요청
# --------------------------------------------------------------------------

_PROMPT_PATH = __file__.replace("modules/outlook.py", "prompts/outlook.md")
_PROMPT_FALLBACK = (
    "이 경기의 외부 매체 전망을 Google 검색 결과에서 찾아 JSON으로만 정리하세요."
    ' 출력: {"media_forecasts": [], "search_note": ""}'
)


def _prompt_template() -> str:
    try:
        with open(_PROMPT_PATH, encoding="utf-8") as handle:
            return handle.read()
    except OSError:  # pragma: no cover - 파일이 없는 배포 형태의 안전망
        return _PROMPT_FALLBACK


def _fixture_context(
    fixture: FixtureIdentity | None,
    *,
    kickoff_at: datetime | None,
    odds: Sequence[OddsObservation],
    prediction: ApiPrediction | None,
) -> str:
    lines: list[str] = []
    if fixture is not None:
        lines.append(
            f"- 경기: fixture_id {fixture.fixture_id}, 리그 {fixture.league_id}, "
            f"시즌 {fixture.season}, 홈 팀 {fixture.home_team_id}, 원정 팀"
            f" {fixture.away_team_id}"
        )
        lines.append(f"- 킥오프: {_format_time(kickoff_at or fixture.kickoff_at)}")
    if odds:
        lines.append("- 이미 확보한 경기 전 승무패 배당(참고용, 새로 만들지 마세요):")
        for observation in odds:
            lines.append(
                f"  - {observation.bookmaker or '업체 미상'} · "
                f"{observation.market or '시장 미상'} · "
                f"{_format_time(observation.observed_at)}: "
                f"홈 {observation.home} / 무 {observation.draw or '미제공'} / "
                f"원정 {observation.away}"
            )
    if prediction is not None:
        lines.append(
            "- 제공자(API-Football) 알고리즘 예측(참고용, 매체 의견이 아닙니다): "
            + ", ".join(
                part
                for part in (
                    f"승자 {prediction.winner_name}" if prediction.winner_name else "",
                    f"조언 {prediction.advice}" if prediction.advice else "",
                    (
                        f"확률 홈 {prediction.percent_home} / 무 {prediction.percent_draw}"
                        f" / 원정 {prediction.percent_away}"
                    )
                    if prediction.percent_home
                    else "",
                )
                if part
            )
        )
    return "\n".join(lines) if lines else "- 경기 정보가 전달되지 않았습니다."


def outlook_prompt(
    fixture: FixtureIdentity | None,
    *,
    kickoff_at: datetime | None = None,
    odds: Sequence[OddsObservation] = (),
    prediction: ApiPrediction | None = None,
) -> str:
    """조사 프롬프트 한 장. 파일 `prompts/outlook.md`의 자리표시자를 채운다."""
    context = _fixture_context(
        fixture, kickoff_at=kickoff_at, odds=odds, prediction=prediction
    )
    return _prompt_template().replace("{{CONTEXT}}", context)


def build_generation_config() -> dict[str, Any]:
    """모델 요청 설정. Google Search grounding을 켜고 출력은 JSON으로 제한한다."""
    return {
        "tools": [dict(GROUNDING_TOOL)],
        "temperature": 0.2,
        "max_output_tokens": 2048,
        "response_mime_type": "application/json",
    }


def _model_contents(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "parts": [{"text": prompt}]}]


# --------------------------------------------------------------------------
# 본문·근거 (결정적 구성, 추가 모델 호출 없음)
# --------------------------------------------------------------------------


def compose_outlook_body(research: OutlookResearch) -> str:
    """검증된 조사 결과로 독자용 한국어 본문을 만든다.

    확보하지 못한 항목은 빈 제목도, 누락 안내도 만들지 않고 통째로 생략한다. 이
    문장들은 관리자 진단이 아니라 독자가 읽는 글이다.
    """
    blocks: list[str] = []
    odds_lines = _odds_body_lines(research.odds)
    media_lines = _media_body_lines(research.media)
    api_lines = _api_body_lines(research.api_prediction)
    if not (odds_lines and odds_lines[0]) and not media_lines and not api_lines:
        return ""
    lead = _lead_paragraph(research)
    if lead:
        blocks.append(lead)
    if odds_lines:
        blocks.append("\n".join([f"### {ODDS_SECTION_TITLE}", *odds_lines]))
    if media_lines:
        blocks.append("\n".join([f"### {MEDIA_SECTION_TITLE}", *media_lines]))
    if api_lines:
        blocks.append("\n".join([f"### {API_SECTION_TITLE}", *api_lines]))
    if not blocks:
        return ""
    return "\n\n".join([f"## {ROOT_TITLE}", *blocks])


def _lead_paragraph(research: OutlookResearch) -> str:
    parts: list[str] = []
    notes: list[str] = []
    if research.odds:
        parts.append("경기 전 승무패 배당")
        notes.append("배당은 업체와 기준 시각을 함께 적었습니다.")
    if research.media:
        parts.append("외부 매체 전망")
        notes.append("매체 전망은 게시 시각과 출처를 함께 적었습니다.")
    if research.api_prediction is not None:
        parts.append("제공자 알고리즘 예측")
        notes.append("제공자 예측은 매체 의견과 구분해 표시했습니다.")
    if not parts:
        return ""
    return (
        f"이 경기의 {', '.join(parts)} 자료를 정리했습니다. {' '.join(notes)}"
    )


def _odds_body_lines(odds: Sequence[OddsObservation]) -> list[str]:
    if not odds:
        return []
    lines = [
        "공개된 경기 전 승무패 배당입니다. 업체마다 값이 다를 수 있어 기준 시각을 함께"
        " 적었습니다."
    ]
    for observation in odds:
        values = (
            f"홈 {observation.home} · 무 {observation.draw or '미제공'} · "
            f"원정 {observation.away}"
        )
        lines.append(
            f"- {observation.bookmaker or '업체 미상'} / "
            f"{observation.market or '경기 전 승무패'} / "
            f"기준 {_format_time(observation.observed_at)}: {values}"
        )
    return lines


def _media_body_lines(media: Sequence[MediaForecast]) -> list[str]:
    if not media:
        return []
    lines = [
        "검색으로 확인한 외부 매체의 이 경기 전망입니다. 매체가 쓴 내용을 그대로"
        " 정리했으며 이 서비스의 판단과는 별개입니다."
    ]
    for forecast in media:
        source = forecast.publisher or "매체 미상"
        when = _format_time(_as_datetime(forecast.published_at))
        # 인용문에 이미 스코어가 있으면 같은 값을 한 번 더 붙이지 않는다.
        score = (
            f" 예상 스코어 {forecast.predicted_score}."
            if forecast.predicted_score and forecast.predicted_score not in forecast.statement
            else ""
        )
        lines.append(f"- {source} ({when}): {forecast.statement}{score}")
    return lines


def _api_body_lines(prediction: ApiPrediction | None) -> list[str]:
    if prediction is None:
        return []
    pieces: list[str] = []
    if prediction.winner_name:
        pieces.append(f"우세 팀 {prediction.winner_name}")
    if prediction.percent_home or prediction.percent_draw or prediction.percent_away:
        pieces.append(
            "확률 홈 "
            f"{prediction.percent_home or '미제공'} / 무 "
            f"{prediction.percent_draw or '미제공'} / 원정 "
            f"{prediction.percent_away or '미제공'}"
        )
    if prediction.advice:
        pieces.append(f"조언 {prediction.advice}")
    if prediction.under_over:
        pieces.append(f"언더오버 기준 {prediction.under_over}")
    if not pieces:
        return []
    return [
        "제공자(API-Football)의 알고리즘 예측입니다. 언론 보도나 이 서비스의 결론이"
        " 아니라 제공자가 계산한 값입니다.",
        "- " + ", ".join(pieces) + ".",
    ]


def compose_outlook_section(payload: Mapping[str, Any]) -> "ComposedSection":
    """R3 노드가 저장한 payload에서 독자용 섹션 본문·근거를 만든다.

    `compose_body` 노드가 이 함수 하나만 부르면 된다. `payload`는
    `outlook_node_implementation`이 만든 `NodeOutcome.payload`(=`OutlookResearch`의
    일부 + `outlook` 전체 사전)이다. 조사 결과가 이미 본문 문자열을 갖고 있으면 그 값을
    그대로 쓰고, 없으면 저장된 사전에서 다시 조립한다. 두 경우 모두 같은 규칙(누락
    안내 없음, 근거 없는 항목 생략)을 지킨다.
    """
    from app.preview.modules.compose import ComposedSection

    reader_body = str(payload.get("reader_body") or "").strip()
    reader_sources = tuple(
        dict(item) for item in payload.get("reader_sources") or () if isinstance(item, Mapping)
    )
    outlook_payload = payload.get("outlook")
    if not reader_body and isinstance(outlook_payload, Mapping):
        reader_body, reader_sources = _compose_from_stored(outlook_payload)
    if not reader_body:
        return ComposedSection(
            title=ROOT_TITLE,
            body="",
            sources=(),
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason=(
                "배당·외부 매체 전망·제공자 예측 근거를 확보하지 못해 이 섹션의 본문을"
                " 만들지 않았습니다."
            ),
        )
    quality = QualityStatus.READY
    if isinstance(outlook_payload, Mapping) and outlook_payload.get("quality"):
        try:
            quality = QualityStatus(str(outlook_payload["quality"]))
        except ValueError:
            quality = QualityStatus.PENDING
    return ComposedSection(
        title=ROOT_TITLE, body=reader_body, sources=reader_sources, quality=quality
    )


def _compose_from_stored(
    stored: Mapping[str, Any],
) -> tuple[str, tuple[dict[str, Any], ...]]:
    """저장된 `OutlookResearch.to_dict()`에서 본문·근거를 다시 만든다.

    원문 아티팩트가 만료돼도 저장된 구조화 결과로 본문을 재현할 수 있게 하려는 경로다.
    새 사실을 더하지 않고 저장된 값만 쓴다.
    """
    body = str(stored.get("reader_body") or "").strip()
    sources = tuple(
        dict(item) for item in stored.get("reader_sources") or () if isinstance(item, Mapping)
    )
    return body, sources


def compose_outlook_sources(research: OutlookResearch) -> tuple[dict[str, Any], ...]:
    """본문에 실제로 쓰인 근거 목록. 없는 항목은 만들지 않는다."""
    sources: list[dict[str, Any]] = []
    for observation in research.odds:
        sources.append(
            {
                "label": f"{observation.bookmaker or '업체 미상'} 경기 전 승무패 배당",
                "kind": "bookmaker",
                "url": None,
                "publisher": observation.bookmaker,
                "published_at": _iso_or_none(observation.observed_at),
                "note": (
                    "API-Football 배당 자료입니다. 업체·시장·갱신 시각을 함께 보존했습니다."
                ),
            }
        )
    for forecast in research.media:
        sources.append(
            {
                "label": forecast.publisher or forecast.url,
                "kind": "media",
                "url": forecast.url,
                "publisher": forecast.publisher,
                "published_at": forecast.published_at,
                "note": (
                    "검색 결과 출처 목록에서 주소를 확인했습니다. 기사 원문 전체를 읽은"
                    " 것은 아닙니다."
                ),
            }
        )
    if research.api_prediction is not None:
        sources.append(
            {
                "label": "API-Football 알고리즘 예측",
                "kind": "api_prediction",
                "url": None,
                "publisher": api.API_PROVIDER,
                "published_at": None,
                "note": "제공자 알고리즘 예측이며 매체 의견이 아닙니다.",
            }
        )
    return tuple(sources)


# --------------------------------------------------------------------------
# 결과 조립
# --------------------------------------------------------------------------


def _coverage(topic: str, state: CoverageState, detail: str | None = None) -> CoverageEntry:
    return CoverageEntry(topic=topic, state=state, detail=detail)


def _claims_from(
    odds: Sequence[OddsObservation],
    media: Sequence[MediaForecast],
    prediction: ApiPrediction | None,
) -> tuple[EvidenceClaim, ...]:
    claims: list[EvidenceClaim] = []
    for observation in odds:
        claims.append(
            EvidenceClaim(
                claim_id=observation.claim_id,
                kind=ClaimKind.EXTERNAL_FORECAST,
                text=(
                    f"{observation.bookmaker or '업체 미상'} 경기 전 승무패 "
                    f"{observation.market or '시장 미상'}: 홈 {observation.home} / "
                    f"무 {observation.draw or '미제공'} / 원정 {observation.away}"
                    f" (기준 {_format_time(observation.observed_at)})"
                ),
                snapshot_ids=(observation.snapshot_id,) if observation.snapshot_id else (),
                decision=ClaimDecision.ADOPTED,
                decision_reason=(
                    "경기 전 승무패 시장, 경기 일치, 갱신 시각 확인, 수집 6시간 이내."
                ),
                claimed_at=observation.observed_at,
            )
        )
    for forecast in media:
        claims.append(
            EvidenceClaim(
                claim_id=forecast.claim_id,
                kind=ClaimKind.EXTERNAL_FORECAST,
                text=(
                    f"{forecast.publisher or '매체 미상'}"
                    f"({forecast.published_at or '게시 시각 미확인'}): {forecast.statement}"
                ),
                decision=ClaimDecision.ADOPTED,
                decision_reason=(
                    "검색 결과 출처 목록에서 주소를 확인한 매체 전망입니다. 원문 전체를"
                    " 읽은 것은 아닙니다."
                ),
                source_url=forecast.url,
                claimed_at=_as_datetime(forecast.published_at),
            )
        )
    if prediction is not None:
        pieces = [
            part
            for part in (
                f"우세 팀 {prediction.winner_name}" if prediction.winner_name else "",
                f"조언 {prediction.advice}" if prediction.advice else "",
                (
                    f"홈 {prediction.percent_home} / 무 {prediction.percent_draw} /"
                    f" 원정 {prediction.percent_away}"
                )
                if prediction.percent_home
                else "",
            )
            if part
        ]
        claims.append(
            EvidenceClaim(
                claim_id=prediction.claim_id,
                kind=ClaimKind.API_PREDICTION,
                text="제공자 알고리즘 예측: " + ", ".join(pieces) + ".",
                snapshot_ids=(prediction.snapshot_id,) if prediction.snapshot_id else (),
                decision=ClaimDecision.ADOPTED,
                decision_reason=(
                    "제공자 알고리즘 예측이며 매체 의견이나 이 서비스의 결론이 아닙니다."
                ),
            )
        )
    return tuple(claims)


def _rejected_claim_view(
    rejected_odds: Sequence[OddsObservation], rejected_media: Sequence[MediaForecast]
) -> tuple[EvidenceClaim, ...]:
    claims: list[EvidenceClaim] = []
    for observation in rejected_odds:
        claims.append(
            EvidenceClaim(
                claim_id=f"rejected-{observation.claim_id}",
                kind=ClaimKind.EXTERNAL_FORECAST,
                text=(
                    f"{observation.bookmaker or '업체 미상'} "
                    f"{observation.market or '시장 미상'} 배당 후보"
                ),
                decision=ClaimDecision.EXCLUDED,
                decision_reason=observation.rejection_reason,
                claimed_at=observation.observed_at,
            )
        )
    for forecast in rejected_media:
        claims.append(
            EvidenceClaim(
                claim_id=f"rejected-{forecast.claim_id}",
                kind=ClaimKind.EXTERNAL_FORECAST,
                text=f"{forecast.publisher or '매체 미상'}: {forecast.statement}",
                decision=ClaimDecision.EXCLUDED,
                decision_reason=forecast.rejection_reason,
                source_url=forecast.url or None,
            )
        )
    return tuple(claims)


def _coverage_entries(
    *,
    odds: Sequence[OddsObservation],
    rejected_odds: Sequence[OddsObservation],
    media: Sequence[MediaForecast],
    rejected_media: Sequence[MediaForecast],
    prediction: ApiPrediction | None,
    grounding: GroundingRecord,
    searched: bool,
    search_error: str | None,
) -> tuple[CoverageEntry, ...]:
    entries: list[CoverageEntry] = []
    if odds:
        entries.append(
            _coverage(TOPIC_ODDS, CoverageState.AVAILABLE, f"채택 {len(odds)}건")
        )
    elif rejected_odds:
        entries.append(
            _coverage(
                TOPIC_ODDS,
                CoverageState.VALIDATION_REJECTED,
                f"{len(rejected_odds)}건이 검증에서 제외되었습니다: "
                + (rejected_odds[0].rejection_reason or "사유 미상"),
            )
        )
    else:
        entries.append(
            _coverage(
                TOPIC_ODDS,
                CoverageState.API_NOT_PROVIDED,
                "D0 배당 자료가 없거나 비어 있습니다.",
            )
        )

    if prediction is not None:
        entries.append(_coverage(TOPIC_API_PREDICTION, CoverageState.AVAILABLE, "1건"))
    else:
        entries.append(
            _coverage(
                TOPIC_API_PREDICTION,
                CoverageState.API_NOT_PROVIDED,
                "D0 제공자 예측 자료가 없습니다.",
            )
        )

    if media:
        entries.append(
            _coverage(TOPIC_MEDIA, CoverageState.AVAILABLE, f"채택 {len(media)}건")
        )
    elif search_error is not None:
        entries.append(_coverage(TOPIC_MEDIA, CoverageState.CALL_ERROR, search_error))
    elif rejected_media:
        entries.append(
            _coverage(
                TOPIC_MEDIA,
                CoverageState.VALIDATION_REJECTED,
                f"{len(rejected_media)}건이 검증에서 제외되었습니다: "
                + (rejected_media[0].rejection_reason or "사유 미상"),
            )
        )
    elif not searched:
        entries.append(
            _coverage(TOPIC_MEDIA, CoverageState.NOT_RUN, TRANSPORT_MISSING_REASON)
        )
    else:
        entries.append(_coverage(TOPIC_MEDIA, CoverageState.SEARCH_NOT_FOUND, EMPTY_MEDIA_REASON))

    if grounding.present and grounding.chunk_uris:
        entries.append(
            _coverage(
                TOPIC_SEARCH,
                CoverageState.AVAILABLE,
                f"검색 질의 {len(grounding.web_search_queries)}건, 출처"
                f" {len(grounding.chunk_uris)}건",
            )
        )
    elif grounding.present:
        entries.append(
            _coverage(
                TOPIC_SEARCH,
                CoverageState.UNKNOWN,
                "grounding 메타데이터는 있으나 출처 목록이 비어 있습니다.",
            )
        )
    else:
        entries.append(
            _coverage(
                TOPIC_SEARCH,
                CoverageState.UNKNOWN,
                grounding.absence_reason or GROUNDING_ABSENT_REASON,
            )
        )
    return tuple(entries)


def _quality_of(
    *, odds: Sequence[OddsObservation], media: Sequence[MediaForecast], prediction: ApiPrediction | None
) -> QualityStatus:
    """섹션 본문을 만들 근거가 있는지. 실행 성공과 다른 축이다."""
    if odds or media or prediction is not None:
        return QualityStatus.READY
    return QualityStatus.INSUFFICIENT


# --------------------------------------------------------------------------
# 조사 실행
# --------------------------------------------------------------------------


def research_outlook(
    session: Session,
    *,
    context: ExecutionContext,
    module_input: ModuleInput | None = None,
    transport: Any | None = None,
    budget: RunBudget | None = None,
    actor_id: int | None = None,
    d0: Mapping[str, Any] | None = None,
    fixture: FixtureIdentity | Mapping[str, Any] | None = None,
    module_execution_id: uuid.UUID | None = None,
    now: datetime | None = None,
    sleeper: Any | None = None,
) -> OutlookResearch:
    """R3 조사를 한 번 실행한다. 모델 호출은 정상 경로에서 1회다.

    `module_input`이 있으면 그 경기·스냅샷·해시를 쓴다. 노드 문맥처럼 경기만 있는
    경우에는 `fixture`를 넘긴다. 모델 전송 계층이 없으면 호출하지 않고, 배당·제공자
    예측만으로 본문을 만든다(그 사실은 진단에 남는다).
    """
    moment = now or _now()
    identity = _resolve_fixture(module_input, fixture)
    resolved_actor = actor_id if actor_id is not None else context.actor_id
    mode = context.mode
    run_budget = budget or RunBudget.for_run(now=moment)
    execution_id = module_execution_id or context.module_execution_id

    evidence = _resolve_d0_evidence(
        session, run_id=context.run_id, provided=d0
    )
    collected_at = moment
    odds, rejected_odds, odds_diagnostics = _validate_odds(
        evidence.odds_raw,
        fixture_id=identity.fixture_id if identity else None,
        collected_at=collected_at,
        snapshot_id=evidence.odds_snapshot_id,
    )
    prediction, prediction_note = _parse_api_prediction(
        evidence.prediction_raw,
        fixture_id=identity.fixture_id if identity else None,
        snapshot_id=evidence.prediction_snapshot_id,
    )

    diagnostics: list[str] = list(evidence.notes) + list(odds_diagnostics)
    if prediction_note:
        diagnostics.append(prediction_note)

    grounding = GroundingRecord(present=False)
    media: tuple[MediaForecast, ...] = ()
    rejected_media: tuple[MediaForecast, ...] = ()
    model_text: str | None = None
    model_name: str | None = None
    external_calls = 0
    searched = False
    search_error: str | None = None
    attempt_summary: dict[str, Any] = {}

    if transport is None:
        diagnostics.append(TRANSPORT_MISSING_REASON)
    else:
        prompt = outlook_prompt(
            identity,
            kickoff_at=identity.kickoff_at if identity else None,
            odds=odds,
            prediction=prediction,
        )
        searched = True
        logical_call_id = f"{MODULE_ID}-outlook"
        result = provider.request_model(
            logical_call_id=logical_call_id,
            contents=_model_contents(prompt),
            context=context,
            transport=transport,
            budget=run_budget,
            session=session,
            module_id=MODULE_ID,
            operation="research_outlook",
            prompt_version=PROMPT_VERSION,
            generation_config=build_generation_config(),
            module_execution_id=execution_id,
            actor_id=resolved_actor,
            sleeper=sleeper or provider.sleep_seconds,
        )
        model_name = result.spec.model
        model_text = result.text
        # 실제로 나간 시도를 센다. 성공 여부로 세지 않는다: 429 뒤 재시도까지 하면 요청은
        # 두 번 나갔고, 마지막 시도가 실패해도 첫 시도는 실제 외부 호출이다. 설정
        # 오류(`configuration_error`)는 전송이 아니므로 공통 도우미가 빼고 센다.
        external_calls = provider.sent_attempt_count(result, transport.mode)
        attempt_summary = {
            "logical_call_id": logical_call_id,
            "attempt_count": result.attempt_count,
            # 실제로 나간 시도 수. 성공/실패와 다른 축이라 따로 남긴다.
            "sent_attempts": external_calls,
            "outcomes": [attempt.outcome.value for attempt in result.attempts],
            "final_outcome": result.response.outcome.value,
            "http_statuses": [attempt.http_status for attempt in result.attempts],
            "error_classes": [attempt.error_class for attempt in result.attempts],
            "http_status": result.response.http_status,
            "error_class": result.response.error_class,
            "stopped_reason": result.stopped_reason,
            "missing_configuration": result.missing_configuration,
            "mode": mode.value,
            "usage": result.response.usage.to_dict() if result.response.usage else None,
            "response_artifact_id": (
                str(result.response.raw_artifact_id)
                if result.response.raw_artifact_id
                else None
            ),
        }

        raw_response = _load_raw_response(
            session, artifact_id=result.response.raw_artifact_id, fallback=result.text
        )
        grounding = _extract_grounding(raw_response)
        if result.ok:
            _record_search_snapshot(
                session,
                context=context,
                identity=identity,
                grounding=grounding,
                artifact_id=result.response.raw_artifact_id,
                attempt_id=result.response.attempt_id,
                actor_id=resolved_actor,
                moment=moment,
                mode=mode,
            )
        else:
            search_error = (
                result.missing_configuration
                or result.stopped_reason
                or result.response.error_message
                or "모델 호출이 실패했습니다."
            )
            diagnostics.append(f"외부 매체 전망 조사 호출이 실패했습니다: {search_error}")

        if result.ok:
            raw_items, parse_error = parse_media_response(model_text)
            if parse_error:
                diagnostics.append(parse_error)
            media, rejected_media, media_diagnostics = validate_media_forecasts(
                raw_items,
                grounding=grounding,
                kickoff_at=identity.kickoff_at if identity else None,
            )
            diagnostics.extend(media_diagnostics)
            if not grounding.present and grounding.absence_reason:
                diagnostics.append(grounding.absence_reason)
            elif grounding.present and grounding.missing_queries_note:
                diagnostics.append(grounding.missing_queries_note)
            if rejected_media:
                diagnostics.append(
                    f"검증되지 않은 매체 전망 {len(rejected_media)}건을 본문에서"
                    " 제외했습니다. 사유는 관리자 기록에 있습니다."
                )

    claims = _claims_from(odds, media, prediction) + _rejected_claim_view(
        rejected_odds, rejected_media
    )
    coverage = _coverage_entries(
        odds=odds,
        rejected_odds=rejected_odds,
        media=media,
        rejected_media=rejected_media,
        prediction=prediction,
        grounding=grounding,
        searched=searched,
        search_error=search_error,
    )
    quality = _quality_of(odds=odds, media=media, prediction=prediction)
    if quality is QualityStatus.INSUFFICIENT:
        diagnostics.append(
            "채택할 배당·매체 전망·제공자 예측 근거가 없습니다. 실행 성공과 근거 확보는"
            " 별개이며, 이 섹션의 독자용 본문은 만들어지지 않았습니다."
        )

    return OutlookResearch(
        fixture=identity,
        mode=mode,
        odds=odds,
        rejected_odds=rejected_odds,
        media=media,
        rejected_media=rejected_media,
        api_prediction=prediction,
        grounding=grounding,
        claims=claims,
        coverage=coverage,
        diagnostics=tuple(diagnostics),
        quality=quality,
        model_text=model_text,
        external_calls=external_calls,
        model_name=model_name,
        attempt_summary=attempt_summary,
        input_hash=_input_hash(module_input, identity),
    )


def _resolve_fixture(
    module_input: ModuleInput | None,
    fixture: FixtureIdentity | Mapping[str, Any] | None,
) -> FixtureIdentity | None:
    if module_input is not None and module_input.fixture is not None:
        return module_input.fixture
    if isinstance(fixture, FixtureIdentity):
        return fixture
    if isinstance(fixture, Mapping):
        try:
            return FixtureIdentity.from_dict(fixture)
        except (KeyError, TypeError, ValueError):
            return None
    return None


def _input_hash(module_input: ModuleInput | None, identity: FixtureIdentity | None) -> str:
    if module_input is not None:
        return module_input.input_hash
    return compute_input_hash(
        {
            "module_id": MODULE_ID,
            "fixture": identity.to_dict() if identity else None,
            "implementation": IMPLEMENTATION_VERSION,
        }
    )


def _load_raw_response(
    session: Session, *, artifact_id: uuid.UUID | None, fallback: Any
) -> Any:
    """응답 원문을 찾는다. 저장 아티팩트가 우선이고, 없으면 넘어온 값을 쓴다."""
    if artifact_id is not None:
        body = _artifact_body(session, artifact_id)
        if body is not None:
            return body
    return fallback


def _record_search_snapshot(
    session: Session,
    *,
    context: ExecutionContext,
    identity: FixtureIdentity | None,
    grounding: GroundingRecord,
    artifact_id: uuid.UUID | None,
    attempt_id: uuid.UUID | None,
    actor_id: int,
    moment: datetime,
    mode: RunMode,
) -> None:
    """검색 근거 스냅샷을 남긴다. 출처가 확인된 경우에만 근거로 쓴다."""
    if not grounding.present:
        return
    try:
        store.record_source_snapshot(
            session,
            run_id=context.run_id,
            source_kind=SourceKind.SEARCH,
            provider="vertex-google-search",
            collected_at=moment,
            provider_updated_at=None,
            validation_status=(
                ValidationStatus.VERIFIED
                if grounding.chunk_uris
                else ValidationStatus.UNVERIFIED
            ),
            fixture=identity,
            attempt_id=attempt_id,
            artifact_id=artifact_id,
            note=(
                f"{MODULE_ID}-outlook: Google Search grounding 응답 (실행 방식 {mode.value})."
                " 출처 목록은 원문 아티팩트에 보존했습니다."
            ),
            actor_id=actor_id,
        )
    except store.RunNotFound:  # pragma: no cover - 실행 행이 없으면 남길 곳도 없다
        return


# --------------------------------------------------------------------------
# 노드 통합 (MP-05가 주입한다)
# --------------------------------------------------------------------------


def outlook_node(
    *,
    transport: Any | None = None,
    d0: Mapping[str, Any] | None = None,
    now: datetime | None = None,
):
    """`runner`가 부를 노드 함수 하나. MP-05의 `form_node`와 같은 모양이다.

    `NodeImplementation(run=outlook_node(...))`로 쓰거나, 아래
    `outlook_node_implementation(...)`을 그대로 등록해도 된다.
    """
    from app.preview import runner

    def run(ctx: runner.SectionNodeContext, state: runner.SectionState) -> runner.NodeOutcome:
        provided = d0
        if provided is None and isinstance(state, Mapping):
            candidate = state.get("data")
            provided = candidate if isinstance(candidate, Mapping) else None
        research = research_outlook(
            ctx.session,
            context=ctx.context,
            transport=transport or ctx.transport,
            budget=ctx.budget,
            actor_id=ctx.actor_id,
            d0=provided,
            fixture=ctx.fixture,
            module_execution_id=ctx.module_execution_id,
            now=now,
        )
        body = research.reader_body
        return runner.NodeOutcome(
            payload={
                "claims": [claim.to_dict() for claim in research.claims],
                "coverage": [entry.to_dict() for entry in research.coverage],
                "outlook": research.to_dict(),
                "reader_body": body,
                "reader_sources": [dict(item) for item in research.reader_sources],
                "grounding": research.grounding.to_dict(),
                "outlook_contract_version": OUTLOOK_OUTPUT_CONTRACT_VERSION,
            },
            title=ROOT_TITLE,
            body=body or None,
            # 연구 단계가 본문 근거를 state["sources"]에 넣는다. compose 단계는 여기에
            # 다시 넣지 않는다(같은 근거가 두 번 저장되는 것을 막는다).
            sources=research.reader_sources,
            quality=research.quality,
            diagnostics=research.diagnostics,
            unavailable_reason=(
                None
                if body
                else "배당·외부 전망 근거를 확보하지 못해 이 섹션의 본문을 만들지 못했습니다."
            ),
            external_calls=research.external_calls,
        )

    return run


def outlook_node_implementation(
    *,
    mode: RunMode = RunMode.LIVE,
    transport: Any | None = None,
    implementation_version: str = IMPLEMENTATION_VERSION,
    prompt_version: str = PROMPT_VERSION,
):
    """`runner.NodeImplementation`에 바로 넣을 수 있는 R3 노드.

    노드는 `SectionNodeContext`가 준 실행 문맥을 그대로 쓰고, 조사 결과를
    `NodeOutcome`으로 돌려준다. 결과 저장·버전 기록은 runner가 한다(모듈이 직접 결과
    행을 만들지 않는다). `mode`는 이 구현이 무엇을 근거로 결과를 만드는지 밝히는 값이며
    모의·재생 실행을 live로 세지 않는다.
    """
    from app.preview import runner

    return runner.NodeImplementation(
        module_id=MODULE_ID,
        implementation_version=implementation_version,
        prompt_version=prompt_version,
        mode=mode,
        run=outlook_node(transport=transport),
    )
