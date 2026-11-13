"""정보 원문 묶음(InformationBundle) 공통 계약.

이 파일은 **PS-01 통합 책임자(A)가 소유하는 공유 계약**이다. B(조사·수집)가 만들고,
C(섹션 작성)가 소비하며, A가 저장·조회·통합한다. 셋이 같은 이름·필드·버전을 쓰게 하려고
이 파일 하나에 모은다. 타입 파일을 서로 고쳐 계약을 맞추지 않는다.

설계 원칙:

- **전문·전달 후보·실제 전달을 구분한다.** `BundleSource.passages`는 수집·정규화되어
  섹션이 **고를 수 있게 된 후보** 구간이고, 전문은 `body_artifact_id`가 가리키는
  아티팩트에 남긴다. "모델에 실제로 보냈다"는 사실은 `SectionDelivery`(섹션 요청
  payload 해시 + 실제 전달 구간 ID)만 주장한다. 본문 전체를 JSONB 묶음에 다시 넣지
  않는다.
- **URL은 후보이고 본문이 근거다.** 조사 묶음이 만든 URL 후보만으로는 근거가 되지
  않는다. 실제로 가져온 본문과 구간만 `sources`에 담는다.
- **없는 값은 `None`이다.** 배당 누락값·미확인 시각·실패 원인을 0이나 빈 문자열로
  채우지 않는다. 실패한 후보는 `failure`에 사유를 남기고 본문을 비운다.
- **비밀값은 계약에 값으로 담지 않는다.** 인증 헤더·쿠키·API 키·DSN은 여기에 오지
  않는다. 저장 직전 `artifacts.save_artifact`가 한 번 더 지운다.
- **자료 성격을 섞지 않는다.** 프리뷰 기사, 지난 경기 보도, 통계, 프로필, 배당을 같은
  종류로 표시하지 않는다(`SourceNature`).
- **기사와 DB를 교차 검증해 탈락시키지 않는다.** 묶음은 자료를 보존할 뿐이고, 별도
  사실 심사 엔진이나 Google `grounding_chunks`/`grounding_supports`를 필수 조건으로
  요구하지 않는다.
- **예산은 이 파일이 정하지 않는다.** 모델 호출 상한·재시도는 `app.preview.retry`
  (`RunBudget`)가, 수집 HTTP 상한은 이 파일의 `DeliveryLimits`가 정한다. 전송 기록은
  `provider.execute_request`가 남긴다.

이 모듈은 외부 호출을 하지 않는다. 순수 자료 구조·검증·요약만 둔다.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

__all__ = [
    "COLLECTION_METHODS",
    "DB_SNAPSHOT_SECTIONS",
    "DISCOVERY_GROUPS",
    "DISCOVERY_GROUP_ALIASES",
    "DISCOVERY_GROUP_MEDIA_ODDS",
    "DISCOVERY_GROUP_PLAYERS_INJURY",
    "DISCOVERY_STATUSES",
    "INFORMATION_BUNDLE_VERSION",
    "MAX_BUNDLE_INPUT_CHARS",
    "MAX_PASSAGES_PER_SOURCE",
    "MAX_PASSAGE_CHARS",
    "MAX_SOURCES_PER_SECTION",
    "MAX_WEB_SECTION_CHARS",
    "ODDS_MARKET_REGULATION_1X2",
    "SECTION_AI_FORECAST",
    "SECTION_AVAILABILITY",
    "SECTION_IDS",
    "SECTION_MATERIAL_KEYS",
    "SECTION_ODDS",
    "SECTION_OUTLOOK",
    "SECTION_PLAYERS",
    "SOURCE_NATURES",
    "BundleBuildError",
    "canonical_discovery_group",
    "BundleSource",
    "DbSnapshot",
    "DeliveryLimits",
    "DiscoveryGroup",
    "InformationBundle",
    "NetworkUsage",
    "OddsMarket",
    "OddsQuote",
    "Passage",
    "bundle_hash",
    "bundle_summary",
    "bundle_to_dict",
    "SectionDelivery",
    "adopted_odds_quotes",
    "build_section_delivery",
    "bundle_from_collection",
    "bundle_source_from_collection",
    "collection_bodies",
    "discovery_group_from_result",
    "network_usage_from_collection",
    "odds_market_from_observation",
    "collect_available_passages",
    "delivery_hash",
    "describe_odds",
    "describe_bundle",
    "ensure_valid_bundle",
    "iter_source_urls",
    "new_bundle_id",
    "passage_char_total",
    "source_index",
    "validate_information_bundle",
]


# --------------------------------------------------------------------------
# 버전·식별자·제한
# --------------------------------------------------------------------------

# 묶음 계약 버전. 필드 의미가 바뀌면 올리고 의존 작업(B/C/D)에 먼저 알린다.
# - 3: 검색 자료(`search_findings`)를 출처 목록과 **분리**해 추가했다. 검색 도구가
#   실제로 돌려준 출처 메타와, 모델이 따로 쓴 문장(스니펫 아님)을 자료 유형으로
#   구분하므로 같은 묶음의 의미가 달라진다.
# - 4: 사용자 확정에 따라 **검색 기반 AI 조사 요약**(`search_ai_summary`)을 실제 작성
#   입력으로 쓴다. 조사 프롬프트가 URL만이 아니라 검색을 사용해 정리한 주제별 요약과
#   인용 URL을 함께 내고, 그 요약을 기사 스니펫으로 위장하지 않고 명시 유형으로 보존한다.
# - 5: 요약의 인용 주소에 **출처 표시**(`url_provenance`: 검색 도구 반환/모델 제시/없음)를
#   더한다. 도구가 반환한 주소와 모델이 적은 주소를 같은 이름으로 부르지 않는다.
INFORMATION_BUNDLE_VERSION = "mp11-information-bundle-5"

# --------------------------------------------------------------------------
# 검색 자료 — 실제 검색 반환과 모델 산문의 경계
# --------------------------------------------------------------------------

# 검색 자료의 **자료 유형**. 같은 목록에 담되 절대 같은 이름으로 부르지 않는다.
# - `search_ai_summary`: 검색 도구를 **실제로 사용한** 조사 응답에서 모델이 주제별로
#   정리한 요약(인용 URL 포함). 사용자 확정으로 작성 근거로 **사용한다**. 다만 이것은
#   기사 원문 발췌도 검색 도구가 직접 반환한 스니펫도 아니므로 그렇게 부르지 않는다.
# - `search_snippet`: 검색 도구 응답에 요약/스니펫 필드가 실제로 있어 그 값을 옮긴 것.
#   현재 확인된 Google Search grounding 응답에는 이 필드가 없다(도메인/제목/URI만 온다).
# - `search_source_meta`: 검색 도구가 실제로 돌려준 출처 **메타데이터**(도메인·URI·제목
#   필드 값). 본문이나 요약이 아니다. 제목 필드가 도메인과 같을 수 있다.
# - `model_cited_span`: 모델이 자기 응답에서 인용한 문장 구간(grounding_supports
#   segment.text). **모델이 쓴 문장**이며 검색 스니펫이 아니다. 공식 문서도 이 필드가
#   모델 답변의 부분임을 밝히므로 기사 원문 발췌로 부르지 않는다.
# - `model_note`: 조사 응답 JSON에서 모델이 쓴 **한 줄 페이지 설명**. 조사 요약
#   (`search_ai_summary`)과 섞지 않는다.
SEARCH_MATERIAL_TYPES: tuple[str, ...] = (
    "search_ai_summary",
    "search_snippet",
    "search_source_meta",
    "model_cited_span",
    "model_note",
)

# 화면·프롬프트에 **그대로** 쓰는 자료 유형 표기. 이 문자열을 바꾸지 않고 재사용한다.
SEARCH_MATERIAL_LABELS: Mapping[str, str] = {
    "search_ai_summary": "검색을 사용한 AI 조사 요약(기사 원문 아님)",
    "search_snippet": "검색 도구가 반환한 요약문",
    "search_source_meta": "검색 도구가 반환한 출처 메타(도메인·주소)",
    "model_cited_span": "모델이 쓴 문장(검색 요약문 아님)",
    "model_note": "모델이 쓴 페이지 설명(검색 요약문 아님)",
}

# 작성 입력으로 넘길 수 있는 자료 유형. 각 줄에는 위 표기의 라벨이 반드시 붙는다.
# 조사 요약과 모델 한 줄 메모를 함께 넣는다. 다만 둘을 같은 유형으로 합치지 않는다.
SEARCH_MATERIAL_DELIVERABLE: tuple[str, ...] = (
    "search_ai_summary",
    "search_snippet",
    "search_source_meta",
    "model_cited_span",
)

# 작성 입력 우선순위가 낮은 유형(같은 상한 안에서 뒤로 밀린다). 내용이 있는 요약·인용을
# 먼저 넣고, 주소만 있는 메타와 한 줄 설명은 남는 자리에만 넣는다.
SEARCH_MATERIAL_LOW_PRIORITY: tuple[str, ...] = ("search_source_meta", "model_note")

# 주소가 **어디서 왔는지**. 사용자 확정: 검색 도구가 준 출처 메타가 있으면 그 연결을
# 보존하고, 없으면 "모델이 제시한 주소"로 정직하게 구분한다(추가 증명 게이트는 만들지 않음).
SEARCH_URL_PROVENANCE: tuple[str, ...] = (
    "grounding_chunk",   # 검색 도구 응답의 grounding_chunks[].web.uri (실제 반환 주소)
    "model_provided",    # 조사 응답 JSON에서 모델이 적은 주소(도구 메타로 확인되지 않음)
    "none",              # 주소 없음
)
SEARCH_URL_PROVENANCE_LABELS: Mapping[str, str] = {
    "grounding_chunk": "검색 도구가 반환한 주소",
    "model_provided": "모델이 제시한 주소(도구 메타 미확인)",
    "none": "주소 없음",
}

# 작성 입력에 넣는 검색 자료 상한. 기사 본문 상한과 별도로 센다.
MAX_SEARCH_FINDINGS_PER_SECTION = 8
MAX_SEARCH_FINDING_CHARS = 600
MAX_SEARCH_MATERIAL_CHARS = 4000

# 두 조사 묶음(설계 ②). A그룹은 선수·부상, B그룹은 외부 전망·배당이다.
DISCOVERY_GROUP_PLAYERS_INJURY = "players_injury"
DISCOVERY_GROUP_MEDIA_ODDS = "media_odds"
DISCOVERY_GROUPS: tuple[str, ...] = (
    DISCOVERY_GROUP_PLAYERS_INJURY,
    DISCOVERY_GROUP_MEDIA_ODDS,
)

# B(`app.preview.discovery`)는 자기 묶음 이름(`people`/`outlook`)을 쓴다. 이름을 서로
# 고치지 않도록 여기서 별칭만 받아 canonical 값으로 맞춘다. 두 표기가 모두 검증을
# 통과하며, 저장은 `discovery_group` 그대로 남겨 어느 쪽이 보냈는지도 확인할 수 있다.
DISCOVERY_GROUP_ALIASES: Mapping[str, str] = {
    "people": DISCOVERY_GROUP_PLAYERS_INJURY,
    "outlook": DISCOVERY_GROUP_MEDIA_ODDS,
}

# 조사 묶음 하나의 종료 상태. '진행 중'을 완료로 세지 않는다.
DISCOVERY_STATUSES: tuple[str, ...] = (
    "completed",
    "not_run",
    "failed",
    "configuration_error",
    "budget_exhausted",
)

# 자료 성격. 기사 프리뷰·지난 경기 보도·통계·프로필·배당을 같은 종류로 합치지 않는다.
SOURCE_NATURES: tuple[str, ...] = (
    "preview",  # 이번 경기의 프리뷰/전망 기사
    "news",  # 팀·선수 뉴스
    "past_match_report",  # 지난 경기 보도 (이번 경기 결과가 아니다)
    "stats",  # 시즌 통계·순위·기록 페이지
    "profile",  # 선수·감독 프로필/백과
    "squad",  # 스쿼드·명단
    "odds",  # 배당 수집 페이지/응답
    "unavailable",  # 후보였으나 본문 미확보
    "unknown",  # 성격을 확정하지 못함
)

# 브라우저 없이 본문을 얻은 방법. `stored_capture`는 이전에 저장한 캡처 재사용이다.
COLLECTION_METHODS: tuple[str, ...] = (
    "fresh_http",  # 이번 실행에서 새 HTTP 요청
    "stored_capture",  # 저장된 HTML/응답 재사용 (새 요청 없음)
    "public_api",  # 공개 본문/JSON API
    "static_json",  # 페이지에 내장된 정적 JSON
    "text_fallback",  # 기사 추출이 목록·표를 버려 텍스트 폴백을 쓴 경우
    "unavailable",  # 본문 미확보
)

# 배당 시장. 정규시간 1X2만 다룬다. 진출/연장/라이브/핸디캡/언더오버를 섞지 않는다.
ODDS_MARKET_REGULATION_1X2 = "1x2_regulation"

# 독자용 섹션 ID. 승인 단위는 이 다섯 개다(설계 §승인 단위).
SECTION_PLAYERS = "section_players"
SECTION_AVAILABILITY = "section_availability"
SECTION_OUTLOOK = "section_outlook"
SECTION_ODDS = "section_odds"
SECTION_AI_FORECAST = "section_ai_forecast"
SECTION_IDS: tuple[str, ...] = (
    SECTION_PLAYERS,
    SECTION_AVAILABILITY,
    SECTION_OUTLOOK,
    SECTION_ODDS,
    SECTION_AI_FORECAST,
)

# 섹션 → 그 섹션이 읽는 자료 축. 작성 단계가 다른 섹션 자료를 끌어다 쓰지 않게 한다.
SECTION_MATERIAL_KEYS: Mapping[str, tuple[str, ...]] = {
    SECTION_PLAYERS: ("db", "web_players"),
    SECTION_AVAILABILITY: ("db", "web_injury"),
    SECTION_OUTLOOK: ("db", "web_outlook"),
    # 배당은 모델 없이 수집·정규화한 완결 결과를 쓴다.
    SECTION_ODDS: ("odds",),
    # 최종 AI 전망·스코어는 확보된 모든 축과 DB 경기력 자료를 읽는다.
    SECTION_AI_FORECAST: ("db", "web_players", "web_injury", "web_outlook", "sections"),
}

# 모델 입력 발췌량 상한(설계 §실행 예산). 결정적 처리이며 요약 모델을 따로 부르지 않는다.
MAX_SOURCES_PER_SECTION = 6
MAX_PASSAGES_PER_SOURCE = 3
MAX_PASSAGE_CHARS = 1500
MAX_WEB_SECTION_CHARS = 16000
MAX_BUNDLE_INPUT_CHARS = 32000  # DB 포함 정보 원문 총량

# DB 스냅샷이 담는 축. 읽지 못한 축은 `None`/`unknown`으로 남고 빈 값을 만들지 않는다.
DB_SNAPSHOT_SECTIONS: tuple[str, ...] = (
    "fixture",
    "teams",
    "standings",
    "injuries",
    "recent_matches",
    "roster",
)


def canonical_discovery_group(value: str) -> str:
    """B의 묶음 이름 표기를 canonical 값으로 맞춘다. 모르는 값은 그대로 돌려준다."""
    text = str(value or "").strip()
    return DISCOVERY_GROUP_ALIASES.get(text, text)


class BundleBuildError(ValueError):
    """묶음이 계약을 어긴다. 저장 전에 호출자가 거부해야 하는 상태다."""


@dataclass(frozen=True)
class DeliveryLimits:
    """섹션별 발췌 상한. 값을 여러 파일에 복사하지 않고 이 한 곳에서 온다."""

    max_sources_per_section: int = MAX_SOURCES_PER_SECTION
    max_passages_per_source: int = MAX_PASSAGES_PER_SOURCE
    max_passage_chars: int = MAX_PASSAGE_CHARS
    max_web_section_chars: int = MAX_WEB_SECTION_CHARS
    max_bundle_input_chars: int = MAX_BUNDLE_INPUT_CHARS

    def to_dict(self) -> dict[str, int]:
        return {
            "max_sources_per_section": self.max_sources_per_section,
            "max_passages_per_source": self.max_passages_per_source,
            "max_passage_chars": self.max_passage_chars,
            "max_web_section_chars": self.max_web_section_chars,
            "max_bundle_input_chars": self.max_bundle_input_chars,
        }


# --------------------------------------------------------------------------
# 직렬화 도우미 (계약은 JSONB에 넣을 수 있는 기본형만 쓴다)
# --------------------------------------------------------------------------


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _moment(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _decimal_or_none(value: Any) -> float | None:
    """배당 소수점 값. 없거나 숫자가 아니면 `None`(추정으로 채우지 않는다)."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    # 1.00 미만·비정상적으로 큰 값은 배당으로 보지 않는다.
    if number < 1.0 or number > 1000.0:
        return None
    return round(number, 3)


def new_bundle_id(prefix: str = "bundle") -> str:
    """묶음 ID. 실행 안에서 유일하면 되며 경기 결과의 동일성을 주장하지 않는다."""
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


# --------------------------------------------------------------------------
# 전달 후보 구간과 출처
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Passage:
    """섹션 작성이 **고를 수 있는** 후보 구간 하나(전문의 일부).

    이 구간이 묶음에 있다는 사실은 "모델에 보냈다"는 뜻이 **아니다**. 실제 전달은
    `SectionDelivery.passage_ids`와 `payload_sha256`이 밝힌다. `passage_id`는 같은
    묶음 안에서만 유일하며, 작성 단계·검사 화면이 같은 값으로 구간을 가리킨다.
    """

    passage_id: str
    source_id: str
    ordinal: int
    text: str
    char_count: int | None = None
    heading: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = _plain(self)
        data["char_count"] = self.char_count if self.char_count is not None else len(self.text)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Passage":
        text = str(data.get("text") or "")
        return cls(
            passage_id=str(data["passage_id"]),
            source_id=str(data["source_id"]),
            ordinal=int(data.get("ordinal") or 0),
            text=text,
            char_count=_int_or_none(data.get("char_count")),
            heading=data.get("heading"),
        )


@dataclass(frozen=True)
class BundleSource:
    """실제로 가져온 출처 하나.

    - `passages`는 섹션이 고를 수 있는 **후보** 구간이고, 전문은 `body_artifact_id`가
      가리키는 아티팩트에 있다. 실제 전달 여부는 `SectionDelivery`가 밝힌다. 전문을
      여기에 다시 넣지 않는다.
    - `failure`가 있으면 본문을 근거로 쓰지 않는다. 후보로만 남는다.
    - `nature`는 자료 성격이다. 프리뷰 기사와 지난 경기 보도를 같은 종류로 두지 않는다.
    """

    source_id: str
    discovery_group: str
    requested_url: str | None
    final_url: str | None
    nature: str
    method: str
    title: str | None = None
    published_at: datetime | None = None
    captured_at: datetime | None = None
    stored_capture_at: datetime | None = None
    http_status: int | None = None
    redirects: int | None = None
    extractor: str | None = None
    body_chars: int | None = None
    body_sha256: str | None = None
    body_artifact_id: uuid.UUID | None = None
    passages: tuple[Passage, ...] = ()
    failure: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        """본문 구간이 있어 작성 입력으로 쓸 수 있는 출처인지."""
        return bool(self.passages) and self.failure is None

    def to_dict(self) -> dict[str, Any]:
        return {
            **_plain(self),
            "passages": [item.to_dict() for item in self.passages],
            "delivered_chars": sum(
                item.char_count if item.char_count is not None else len(item.text)
                for item in self.passages
            ),
            "usable": self.usable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BundleSource":
        return cls(
            source_id=str(data["source_id"]),
            discovery_group=str(data.get("discovery_group") or DISCOVERY_GROUP_PLAYERS_INJURY),
            requested_url=data.get("requested_url"),
            final_url=data.get("final_url"),
            nature=str(data.get("nature") or "unknown"),
            method=str(data.get("method") or "unavailable"),
            title=data.get("title"),
            published_at=_moment(data.get("published_at")),
            captured_at=_moment(data.get("captured_at")),
            stored_capture_at=_moment(data.get("stored_capture_at")),
            http_status=_int_or_none(data.get("http_status")),
            redirects=_int_or_none(data.get("redirects")),
            extractor=data.get("extractor"),
            body_chars=_int_or_none(data.get("body_chars")),
            body_sha256=data.get("body_sha256"),
            body_artifact_id=(
                uuid.UUID(str(data["body_artifact_id"]))
                if data.get("body_artifact_id")
                else None
            ),
            passages=tuple(
                Passage.from_dict(item) for item in data.get("passages") or ()
            ),
            failure=data.get("failure"),
            notes=tuple(str(item) for item in data.get("notes") or ()),
        )


@dataclass(frozen=True)
class DiscoveryGroup:
    """조사 묶음 하나의 결과. URL 후보와 원문 응답 링크를 남긴다.

    조사 모델 응답의 URL은 **후보**다. 그 응답에 적힌 사실 문장을 수집 본문으로 바꿔
    취급하지 않는다(`status`·`candidate_urls`만 넘긴다).
    """

    group: str
    status: str
    logical_call_id: str | None = None
    provider: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    response_artifact_id: uuid.UUID | None = None
    candidate_urls: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()
    # 실제 모델 전송 시도 수. 저장 응답 재사용·모의는 0이다.
    sent_attempts: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    # 검색 도구가 실제로 반환한 자료(자료 유형 라벨 포함). 후보 URL과 섞지 않는다.
    # `InformationBundle.search_findings`로 합쳐지며, 여기에는 그 그룹 몫만 둔다.
    search_findings: tuple[Mapping[str, Any], ...] = ()
    search_notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **_plain(self),
            "candidate_urls": list(self.candidate_urls),
            "diagnostics": list(self.diagnostics),
            "search_findings": [dict(item) for item in self.search_findings],
            "search_notes": list(self.search_notes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DiscoveryGroup":
        return cls(
            group=str(data["group"]),
            status=str(data.get("status") or "not_run"),
            logical_call_id=data.get("logical_call_id"),
            provider=data.get("provider"),
            model=data.get("model"),
            prompt_version=data.get("prompt_version"),
            response_artifact_id=(
                uuid.UUID(str(data["response_artifact_id"]))
                if data.get("response_artifact_id")
                else None
            ),
            candidate_urls=tuple(str(item) for item in data.get("candidate_urls") or ()),
            diagnostics=tuple(str(item) for item in data.get("diagnostics") or ()),
            sent_attempts=int(data.get("sent_attempts") or 0),
            started_at=_moment(data.get("started_at")),
            finished_at=_moment(data.get("finished_at")),
            search_findings=tuple(
                dict(item)
                for item in data.get("search_findings") or ()
                if isinstance(item, Mapping)
            ),
            search_notes=tuple(str(item) for item in data.get("search_notes") or ()),
        )


@dataclass(frozen=True)
class SearchFinding:
    """검색 단계에서 **실제로 확보한** 자료 한 줄.

    정직성 규칙(설계 최신 확정 절):

    - `material_type`이 이 줄이 무엇인지 밝힌다. `search_snippet`은 검색 도구 응답에
      요약/스니펫 필드가 실제로 있었던 경우만이다. 지금 확인된 Google Search 응답에는
      그 필드가 없으므로 **만들어 넣지 않는다**.
    - `content`는 위 유형의 실제 값이다. `model_cited_span`·`model_note`는 모델이 쓴
      문장이며 검색 요약문이 아니다. 두 값을 같은 필드에 담되 `material_type`과
      `label`로 구분하고, 표시·프롬프트에서도 라벨을 함께 낸다.
    - `url`은 실제 반환 주소다. URL만 있고 내용이 없는 후보는 `content`를 비우고
      `material_type="search_source_meta"`로 남긴다(기사 내용을 추정해 채우지 않는다).
    - `response_artifact_id`는 이 값을 돌려준 원문 응답을 가리킨다. 없으면 `None`이며
      그 사실을 숨기지 않는다.
    - `search_ai_summary`는 **검색 도구를 실제로 사용한 조사 응답**에서 모델이 주제별로
      정리한 요약이다. 사용자 확정으로 작성 근거로 쓰지만, 기사 원문 발췌도 검색 도구가
      직접 반환한 스니펫도 아니다. `sources`에 그 요약이 인용한 주소를 함께 보존하고,
      `unverified`는 모델이 스스로 낮은 확신을 표시한 값이다(숨기지 않는다).
    """

    finding_id: str
    discovery_group: str
    material_type: str
    label: str
    title: str | None = None
    url: str | None = None
    domain: str | None = None
    content: str | None = None
    content_chars: int | None = None
    captured_at: datetime | None = None
    response_artifact_id: uuid.UUID | None = None
    logical_call_id: str | None = None
    note: str | None = None
    # 요약이 인용한 주소들(여러 개). `url`은 그중 첫 번째이며 화면 링크용이다.
    sources: tuple[str, ...] = ()
    # 모델이 스스로 표시한 낮은 확신. 값을 바꾸지 않는다.
    unverified: bool = False
    # `url`/`sources`의 출처(위 `SEARCH_URL_PROVENANCE`). 도구 메타로 확인된 주소와 모델이
    # 적은 주소를 섞지 않는다. 확신할 수 없으면 `model_provided`다.
    url_provenance: str = "none"

    @property
    def deliverable(self) -> bool:
        """작성 입력에 넣어도 되는 줄인지. 모델 산문은 출처 목록에 넣지 않는다.

        출처 메타는 **내용이 없어도** 전달한다. 다만 그 줄은 "주소만 반환됨"으로
        표시되며, 기사 내용 자리로 쓰이지 않는다(URL만으로 내용을 추정하지 않는다).
        """
        if self.material_type not in SEARCH_MATERIAL_DELIVERABLE:
            return False
        if self.material_type == "search_source_meta":
            return bool((self.url or "").strip() or (self.title or "").strip())
        return bool((self.content or "").strip())

    @property
    def is_search_snippet(self) -> bool:
        """검색 도구가 실제로 반환한 요약문인지. 다른 유형과 절대 섞지 않는다."""
        return self.material_type == "search_snippet"

    def to_dict(self) -> dict[str, Any]:
        content = self.content or ""
        return {
            "finding_id": self.finding_id,
            "discovery_group": self.discovery_group,
            "material_type": self.material_type,
            "label": self.label or SEARCH_MATERIAL_LABELS.get(
                self.material_type, "자료 유형 미확인"
            ),
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "content": self.content,
            "content_chars": self.content_chars
            if self.content_chars is not None
            else (len(content) if content else 0),
            "captured_at": _plain(self.captured_at),
            "response_artifact_id": _plain(self.response_artifact_id),
            "logical_call_id": self.logical_call_id,
            "note": self.note,
            "sources": list(self.sources),
            "unverified": self.unverified,
            "url_provenance": self.url_provenance
            if self.url_provenance in SEARCH_URL_PROVENANCE
            else "none",
            "url_provenance_label": SEARCH_URL_PROVENANCE_LABELS.get(
                self.url_provenance, SEARCH_URL_PROVENANCE_LABELS["none"]
            ),
            "is_search_snippet": self.is_search_snippet,
            "is_ai_summary": self.material_type == "search_ai_summary",
            "deliverable": self.deliverable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SearchFinding":
        material_type = str(data.get("material_type") or "search_source_meta")
        if material_type not in SEARCH_MATERIAL_TYPES:
            material_type = "search_source_meta"
        return cls(
            finding_id=str(data.get("finding_id") or ""),
            discovery_group=canonical_discovery_group(
                str(data.get("discovery_group") or DISCOVERY_GROUP_PLAYERS_INJURY)
            ),
            material_type=material_type,
            label=str(
                data.get("label")
                or SEARCH_MATERIAL_LABELS.get(material_type, "자료 유형 미확인")
            ),
            title=data.get("title"),
            url=data.get("url"),
            domain=data.get("domain"),
            content=data.get("content"),
            content_chars=_int_or_none(data.get("content_chars")),
            captured_at=_moment(data.get("captured_at")),
            response_artifact_id=(
                uuid.UUID(str(data["response_artifact_id"]))
                if data.get("response_artifact_id")
                else None
            ),
            logical_call_id=data.get("logical_call_id"),
            note=data.get("note"),
            sources=tuple(str(item) for item in data.get("sources") or ()),
            unverified=bool(data.get("unverified")),
            url_provenance=(
                str(data.get("url_provenance"))
                if str(data.get("url_provenance") or "") in SEARCH_URL_PROVENANCE
                else ("model_provided" if (data.get("url") or data.get("sources")) else "none")
            ),
        )


@dataclass(frozen=True)
class DbSnapshot:
    """기존 DB에서 읽기 전용으로 가져온 경기·팀·순위·부상·최근 경기·선수 자료.

    - 읽지 못한 축은 `None`이고 `coverage`에 사유가 남는다. 빈 목록을 "없음"의 증거로
      쓰지 않는다(특히 부상 행 0건은 '부상자 없음'이 아니다).
    - `team_id_space`를 반드시 남긴다. internal/external ID를 섞으면 선수·경기가 다른
      대상으로 연결된다.
    """

    fixture: Mapping[str, Any] | None
    team_id_space: str
    collected_at: datetime | None = None
    teams: tuple[Mapping[str, Any], ...] = ()
    standings: tuple[Mapping[str, Any], ...] = ()
    injuries: tuple[Mapping[str, Any], ...] = ()
    recent_matches: tuple[Mapping[str, Any], ...] = ()
    roster: tuple[Mapping[str, Any], ...] = ()
    source_tables: tuple[str, ...] = ()
    coverage: tuple[Mapping[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()
    artifact_id: uuid.UUID | None = None
    readable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            **_plain(self),
            "teams": [dict(item) for item in self.teams],
            "standings": [dict(item) for item in self.standings],
            "injuries": [dict(item) for item in self.injuries],
            "recent_matches": [dict(item) for item in self.recent_matches],
            "roster": [dict(item) for item in self.roster],
            "source_tables": list(self.source_tables),
            "coverage": [dict(item) for item in self.coverage],
            "diagnostics": list(self.diagnostics),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "DbSnapshot":
        payload = dict(data or {})
        return cls(
            fixture=(
                dict(payload["fixture"])
                if isinstance(payload.get("fixture"), Mapping)
                else None
            ),
            team_id_space=str(payload.get("team_id_space") or "unknown"),
            collected_at=_moment(payload.get("collected_at")),
            teams=tuple(
                dict(item) for item in payload.get("teams") or () if isinstance(item, Mapping)
            ),
            standings=tuple(
                dict(item)
                for item in payload.get("standings") or ()
                if isinstance(item, Mapping)
            ),
            injuries=tuple(
                dict(item)
                for item in payload.get("injuries") or ()
                if isinstance(item, Mapping)
            ),
            recent_matches=tuple(
                dict(item)
                for item in payload.get("recent_matches") or ()
                if isinstance(item, Mapping)
            ),
            roster=tuple(
                dict(item)
                for item in payload.get("roster") or ()
                if isinstance(item, Mapping)
            ),
            source_tables=tuple(str(item) for item in payload.get("source_tables") or ()),
            coverage=tuple(
                dict(item)
                for item in payload.get("coverage") or ()
                if isinstance(item, Mapping)
            ),
            diagnostics=tuple(str(item) for item in payload.get("diagnostics") or ()),
            artifact_id=(
                uuid.UUID(str(payload["artifact_id"]))
                if payload.get("artifact_id")
                else None
            ),
            readable=bool(payload.get("readable")),
        )


@dataclass(frozen=True)
class OddsQuote:
    """배당 한 줄. 정규시간 1X2만 다루며 누락값을 추정하지 않는다.

    `market`이 `1x2_regulation`이 아니거나 값이 불완전하면 그 줄은 채택하지 않고
    `OddsMarket.diagnostics`에 남긴다.
    """

    source_id: str
    site: str
    market: str
    observed_at: datetime | None
    home_decimal: float | None
    draw_decimal: float | None
    away_decimal: float | None
    note: str | None = None

    @property
    def complete(self) -> bool:
        return (
            self.market == ODDS_MARKET_REGULATION_1X2
            and all(
                value is not None
                for value in (self.home_decimal, self.draw_decimal, self.away_decimal)
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {**_plain(self), "complete": self.complete}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OddsQuote":
        return cls(
            source_id=str(data["source_id"]),
            site=str(data.get("site") or "unknown"),
            market=str(data.get("market") or ODDS_MARKET_REGULATION_1X2),
            observed_at=_moment(data.get("observed_at")),
            home_decimal=_decimal_or_none(data.get("home_decimal")),
            draw_decimal=_decimal_or_none(data.get("draw_decimal")),
            away_decimal=_decimal_or_none(data.get("away_decimal")),
            note=data.get("note"),
        )


@dataclass(frozen=True)
class OddsMarket:
    """배당 섹션의 재료. 모델 호출 없이 결정적으로 정리한 결과다."""

    quotes: tuple[OddsQuote, ...] = ()
    collected_at: datetime | None = None
    diagnostics: tuple[str, ...] = ()
    unsupported_sites: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "quotes": [item.to_dict() for item in self.quotes],
            "collected_at": _plain(self.collected_at),
            "diagnostics": list(self.diagnostics),
            "unsupported_sites": list(self.unsupported_sites),
            "complete_quotes": sum(1 for item in self.quotes if item.complete),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "OddsMarket":
        payload = dict(data or {})
        return cls(
            quotes=tuple(
                OddsQuote.from_dict(item) for item in payload.get("quotes") or ()
            ),
            collected_at=_moment(payload.get("collected_at")),
            diagnostics=tuple(str(item) for item in payload.get("diagnostics") or ()),
            unsupported_sites=tuple(
                str(item) for item in payload.get("unsupported_sites") or ()
            ),
        )


@dataclass(frozen=True)
class NetworkUsage:
    """묶음 하나를 만드는 동안 쓴 외부 요청. 리다이렉트·실패도 실제 전송으로 센다."""

    http_used: int = 0
    http_failed: int = 0
    redirects: int = 0
    api_used: int = 0
    http_limit: int | None = None
    api_limit: int | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> "NetworkUsage":
        payload = dict(data or {})
        return cls(
            http_used=int(payload.get("http_used") or 0),
            http_failed=int(payload.get("http_failed") or 0),
            redirects=int(payload.get("redirects") or 0),
            api_used=int(payload.get("api_used") or 0),
            http_limit=_int_or_none(payload.get("http_limit")),
            api_limit=_int_or_none(payload.get("api_limit")),
            note=payload.get("note"),
        )


@dataclass(frozen=True)
class SectionDelivery:
    """섹션 요청 하나에 **실제로 실린** 구간·근거 기록.

    묶음의 `sources[].passages`는 전달 **후보**다. 이 객체가 "그 중 무엇을 실제로
    보냈는지"를 밝힌다. `payload_sha256`은 섹션 요청 payload를 정규화해 계산한 해시이므로,
    저장된 요청 아티팩트와 대조하면 실제 전달을 확인할 수 있다.

    모델을 쓰지 않는 섹션(배당)은 `model_delivered=False`이고 `passage_ids`가 비어 있으며
    후보 전체가 `excluded_passage_ids`로 남는다.
    """

    section_id: str
    logical_call_id: str | None
    model_delivered: bool
    passage_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    payload_sha256: str | None = None
    input_chars: int = 0
    available_passage_ids: tuple[str, ...] = ()
    excluded_passage_ids: tuple[str, ...] = ()
    sent_attempts: int = 0
    implementation_version: str | None = None
    prompt_version: str | None = None
    created_at: datetime | None = None
    note: str | None = None
    # 실제 payload에 실린 **검색 자료** id. 기사 구간(passage)과 다른 목록이며,
    # 자료 유형 라벨(`search_findings[].material_type`)과 함께 대조한다.
    search_finding_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            **_plain(self),
            "passage_ids": list(self.passage_ids),
            "source_ids": list(self.source_ids),
            "available_passage_ids": list(self.available_passage_ids),
            "excluded_passage_ids": list(self.excluded_passage_ids),
            "search_finding_ids": list(self.search_finding_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SectionDelivery":
        return cls(
            section_id=str(data["section_id"]),
            logical_call_id=data.get("logical_call_id"),
            model_delivered=bool(data.get("model_delivered")),
            passage_ids=tuple(str(item) for item in data.get("passage_ids") or ()),
            source_ids=tuple(str(item) for item in data.get("source_ids") or ()),
            payload_sha256=data.get("payload_sha256"),
            input_chars=int(data.get("input_chars") or 0),
            available_passage_ids=tuple(
                str(item) for item in data.get("available_passage_ids") or ()
            ),
            excluded_passage_ids=tuple(
                str(item) for item in data.get("excluded_passage_ids") or ()
            ),
            sent_attempts=int(data.get("sent_attempts") or 0),
            implementation_version=data.get("implementation_version"),
            prompt_version=data.get("prompt_version"),
            created_at=_moment(data.get("created_at")),
            note=data.get("note"),
            search_finding_ids=tuple(
                str(item) for item in data.get("search_finding_ids") or ()
            ),
        )


def delivery_hash(payload: Any) -> str:
    """실제 전달 payload의 해시. 같은 payload면 같은 값이 나온다."""
    canonical = json.dumps(_plain(payload), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_section_delivery(
    *,
    section_id: str,
    payload: Any,
    passage_ids: Sequence[str] = (),
    source_ids: Sequence[str] = (),
    available_passage_ids: Sequence[str] = (),
    logical_call_id: str | None = None,
    model_delivered: bool = True,
    input_chars: int | None = None,
    sent_attempts: int = 0,
    implementation_version: str | None = None,
    prompt_version: str | None = None,
    created_at: datetime | None = None,
    note: str | None = None,
    search_finding_ids: Sequence[str] = (),
) -> SectionDelivery:
    """섹션 요청 payload에서 전달 기록을 만든다.

    `passage_ids`는 그 payload에 **실제로 들어간** 구간 ID여야 한다. 호출자가 넘긴
    목록과 payload 해시를 함께 남기므로, 나중에 요청 아티팩트와 대조해 검증할 수 있다.
    """
    included = tuple(dict.fromkeys(str(item) for item in passage_ids))
    available = tuple(dict.fromkeys(str(item) for item in available_passage_ids))
    excluded = tuple(item for item in available if item not in set(included))
    if input_chars is not None:
        chars = int(input_chars)
    else:
        # 실제 전달 글자 수. contents만 세지 않고 payload 전체 텍스트 길이를 쓴다.
        chars = len(json.dumps(_plain(payload), ensure_ascii=False, default=str))
    return SectionDelivery(
        section_id=section_id,
        logical_call_id=logical_call_id,
        model_delivered=bool(model_delivered),
        passage_ids=included,
        source_ids=tuple(dict.fromkeys(str(item) for item in source_ids)),
        payload_sha256=delivery_hash(payload) if model_delivered else None,
        input_chars=chars,
        available_passage_ids=available,
        excluded_passage_ids=excluded if model_delivered else available,
        sent_attempts=int(sent_attempts),
        implementation_version=implementation_version,
        prompt_version=prompt_version,
        created_at=created_at,
        note=note,
        search_finding_ids=(
            tuple(dict.fromkeys(str(item) for item in search_finding_ids))
            if model_delivered
            else ()
        ),
    )


@dataclass(frozen=True)
class InformationBundle:
    """한 경기의 정보 원문 묶음. 섹션 작성의 **유일한 웹·DB 입력**이다.

    흐름: 조사 2묶음 → 후보 URL → 공통 수집 → 이 묶음 → 섹션 작성(3) → 최종 AI 전망(1).

    정직성:

    - `bundle_hash`는 이 묶음의 내용 해시다. 같은 입력으로 재처리했는지 판단하는
      근거이며 결과 동일성을 주장하지 않는다.
    - `mode`가 `replay`면 저장된 본문 재사용이고 새 수집이 아니다. `mock`은 시연이다.
    - `diagnostics`는 관리자 전용이다. 독자용 본문에 누락·실패 문구를 넣지 않는다.
    """

    bundle_id: str
    fixture: Mapping[str, Any]
    team_id_space: str
    collected_at: datetime | None
    sources: tuple[BundleSource, ...] = ()
    db_snapshot: DbSnapshot | None = None
    discovery_groups: tuple[DiscoveryGroup, ...] = ()
    # 검색 단계가 실제로 확보한 자료. 출처(`sources`)는 **수집한 본문**만 담고, 검색이
    # 돌려준 메타/요약과 모델 산문은 여기에 자료 유형과 함께 따로 남긴다.
    search_findings: tuple[SearchFinding, ...] = ()
    odds: OddsMarket | None = None
    # 섹션별 실제 전달 기록. 후보 구간과 실제 전달을 구분하는 유일한 근거다.
    section_deliveries: tuple[SectionDelivery, ...] = ()
    diagnostics: tuple[str, ...] = ()
    network_usage: NetworkUsage = field(default_factory=NetworkUsage)
    bundle_version: str = INFORMATION_BUNDLE_VERSION
    mode: str = "live"
    as_of: datetime | None = None
    build_note: str | None = None
    bundle_hash: str | None = None

    # -- 파생값 -----------------------------------------------------------

    @property
    def usable_sources(self) -> tuple[BundleSource, ...]:
        return tuple(source for source in self.sources if source.usable)

    @property
    def deliverable_search_findings(self) -> tuple[SearchFinding, ...]:
        """작성 입력으로 넘길 수 있는 검색 자료(라벨이 붙은 줄만)."""
        return tuple(item for item in self.search_findings if item.deliverable)

    @property
    def search_snippets(self) -> tuple[SearchFinding, ...]:
        """검색 도구가 실제로 반환한 요약문만. 모델 산문은 여기 들어오지 않는다."""
        return tuple(item for item in self.search_findings if item.is_search_snippet)

    def with_section_delivery(self, delivery: SectionDelivery) -> "InformationBundle":
        """섹션 전달 기록을 더한 사본. 같은 섹션의 이전 기록은 남기고 새 기록을 붙인다."""
        return replace(
            self,
            section_deliveries=self.section_deliveries + (delivery,),
        )

    def available_passages(self) -> tuple[Passage, ...]:
        """수집·정규화되어 **전달 후보**가 된 구간 전체(출처 순서 유지).

        이것은 "모델에 실제로 보냈다"는 뜻이 **아니다**. 실제 전달은 섹션 요청을 만들 때
        `SectionDelivery`로 따로 남기며, 그 해시가 실제 payload와 맞는다.
        """
        collected: list[Passage] = []
        for source in self.sources:
            collected.extend(source.passages)
        return tuple(collected)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "bundle_id": self.bundle_id,
            "bundle_version": self.bundle_version,
            "fixture": dict(self.fixture),
            "team_id_space": self.team_id_space,
            "collected_at": _plain(self.collected_at),
            "as_of": _plain(self.as_of),
            "mode": self.mode,
            "sources": [item.to_dict() for item in self.sources],
            "db_snapshot": self.db_snapshot.to_dict() if self.db_snapshot else None,
            "discovery_groups": [item.to_dict() for item in self.discovery_groups],
            # 검색 자료는 출처와 분리해 둔다. 각 줄의 `material_type`·`label`이 실제
            # 검색 반환인지 모델 산문인지 밝히며, 이 값을 합쳐서 부르지 않는다.
            "search_findings": [item.to_dict() for item in self.search_findings],
            # 유형별 건수는 파생값이므로 해시에서 뺀다(아래 `_HASH_EXCLUDED`).
            "search_findings_by_type": _search_material_counts(
                {"search_findings": [item.to_dict() for item in self.search_findings]}
            ),
            "search_material_semantics": (
                "search_findings는 조사 응답에서 실제로 확보한 자료입니다."
                " material_type=search_snippet만 검색 도구가 반환한 요약문이고,"
                " model_cited_span·model_note는 모델이 쓴 문장입니다. url만 있는 줄은"
                " 기사 내용을 뜻하지 않습니다."
            ),
            "odds": self.odds.to_dict() if self.odds else None,
            "section_deliveries": [item.to_dict() for item in self.section_deliveries],
            # 이름을 그대로 둔다: 이것은 **전달 후보**이며 실제 전달 기록이 아니다.
            "available_passages": [
                {**item.to_dict(), "delivered": False}
                for item in self.available_passages()
            ],
            "passage_semantics": (
                "sources[].passages/available_passages는 수집·정규화된 **전달 후보**"
                " 구간입니다. 실제 모델 전달은 section_deliveries(요청 payload 해시)를"
                " 봅니다."
            ),
            "diagnostics": list(self.diagnostics),
            "network_usage": self.network_usage.to_dict(),
            "delivery_limits": DeliveryLimits().to_dict(),
            "build_note": self.build_note,
            "usable_source_count": len(self.usable_sources),
            "available_chars": sum(
                item.char_count if item.char_count is not None else len(item.text)
                for item in self.available_passages()
            ),
            "browser_used": False,
            "cross_checked_with_db": False,
            "requires_grounding_chunks": False,
        }
        # 해시는 **항상 현재 내용으로 다시 계산한다**. `from_dict`로 받은 값을 그대로 쓰면
        # 전달 기록(`section_deliveries`)을 붙인 뒤에도 예전 해시가 남아, 저장된 묶음의
        # 해시가 그 내용을 설명하지 못한다(검토 F8). 저장 값은 참고용으로만 두고 쓰지 않는다.
        payload["bundle_hash"] = bundle_hash(payload)
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InformationBundle":
        payload = dict(data or {})
        return cls(
            bundle_id=str(payload["bundle_id"]),
            fixture=dict(payload.get("fixture") or {}),
            team_id_space=str(payload.get("team_id_space") or "unknown"),
            collected_at=_moment(payload.get("collected_at")),
            sources=tuple(
                BundleSource.from_dict(item) for item in payload.get("sources") or ()
            ),
            db_snapshot=(
                DbSnapshot.from_dict(payload.get("db_snapshot"))
                if payload.get("db_snapshot")
                else None
            ),
            discovery_groups=tuple(
                DiscoveryGroup.from_dict(item)
                for item in payload.get("discovery_groups") or ()
            ),
            search_findings=tuple(
                SearchFinding.from_dict(item)
                for item in payload.get("search_findings") or ()
                if isinstance(item, Mapping)
            ),
            odds=(
                OddsMarket.from_dict(payload.get("odds")) if payload.get("odds") else None
            ),
            section_deliveries=tuple(
                SectionDelivery.from_dict(item)
                for item in payload.get("section_deliveries") or ()
            ),
            diagnostics=tuple(str(item) for item in payload.get("diagnostics") or ()),
            network_usage=NetworkUsage.from_dict(payload.get("network_usage")),
            bundle_version=str(
                payload.get("bundle_version") or INFORMATION_BUNDLE_VERSION
            ),
            mode=str(payload.get("mode") or "live"),
            as_of=_moment(payload.get("as_of")),
            build_note=payload.get("build_note"),
            bundle_hash=payload.get("bundle_hash"),
        )


# --------------------------------------------------------------------------
# 해시·요약·검증
# --------------------------------------------------------------------------

# 해시에서 빼는 값: 자기 자신과 요약 파생값. 내용이 같으면 해시도 같게 하기 위함이다.
_HASH_EXCLUDED = frozenset(
    {
        "bundle_hash",
        "usable_source_count",
        "available_chars",
        "delivered_chars",
        "delivery_limits",
        "passage_semantics",
        "search_material_semantics",
        "search_findings_by_type",
    }
)


def bundle_hash(payload: Mapping[str, Any]) -> str:
    """묶음 내용 해시. 정렬된 JSON으로 계산해 키 순서에 흔들리지 않는다."""
    canonical = {
        str(key): value
        for key, value in _plain(dict(payload)).items()
        if key not in _HASH_EXCLUDED
    }
    serialized = json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def bundle_to_dict(bundle: InformationBundle | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(bundle, InformationBundle):
        return bundle.to_dict()
    payload = dict(bundle)
    payload.setdefault("bundle_hash", bundle_hash(payload))
    return payload


def collect_available_passages(
    bundle: InformationBundle | Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """작성 단계가 **고를 수 있는** 후보 구간 목록. 실제 전달 기록이 아니다."""
    if isinstance(bundle, InformationBundle):
        return tuple(item.to_dict() for item in bundle.available_passages())
    collected: list[dict[str, Any]] = []
    for source in bundle.get("sources") or ():
        if not isinstance(source, Mapping):
            continue
        for passage in source.get("passages") or ():
            if isinstance(passage, Mapping):
                collected.append(dict(passage))
    return tuple(collected)


def source_index(bundle: InformationBundle | Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """`source_id → 출처 요약`. 검사 화면·작성 단계가 같은 값을 본다."""
    if isinstance(bundle, InformationBundle):
        sources = [item.to_dict() for item in bundle.sources]
    else:
        sources = [dict(item) for item in bundle.get("sources") or () if isinstance(item, Mapping)]
    index: dict[str, dict[str, Any]] = {}
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            continue
        index[source_id] = {
            key: source.get(key)
            for key in (
                "source_id",
                "discovery_group",
                "requested_url",
                "final_url",
                "nature",
                "method",
                "title",
                "captured_at",
                "body_chars",
                "failure",
                "usable",
                "delivered_chars",
            )
        }
    return index


def passage_char_total(bundle: InformationBundle | Mapping[str, Any]) -> int:
    total = 0
    for passage in collect_available_passages(bundle):
        total += int(passage.get("char_count") or len(str(passage.get("text") or "")))
    return total


def bundle_summary(bundle: InformationBundle | Mapping[str, Any]) -> dict[str, Any]:
    """실행·인계 보고에 쓰는 짧은 요약. 본문 전체를 다시 싣지 않는다."""
    data = bundle_to_dict(bundle)
    sources = [item for item in data.get("sources") or () if isinstance(item, Mapping)]
    return {
        "bundle_id": data.get("bundle_id"),
        "bundle_version": data.get("bundle_version"),
        "bundle_hash": data.get("bundle_hash"),
        "fixture_id": (data.get("fixture") or {}).get("fixture_id"),
        "team_id_space": data.get("team_id_space"),
        "mode": data.get("mode"),
        "collected_at": data.get("collected_at"),
        "source_count": len(sources),
        "usable_source_count": sum(1 for item in sources if item.get("usable")),
        "failed_source_count": sum(1 for item in sources if item.get("failure")),
        "available_passages": len(data.get("available_passages") or ()),
        "available_chars": int(data.get("available_chars") or 0),
        "section_delivery_count": len(data.get("section_deliveries") or ()),
        "discovery_groups": {
            str(item.get("group")): str(item.get("status"))
            for item in data.get("discovery_groups") or ()
            if isinstance(item, Mapping)
        },
        "db_readable": bool((data.get("db_snapshot") or {}).get("readable")),
        "db_injuries": len((data.get("db_snapshot") or {}).get("injuries") or ()),
        "odds_quotes": len(((data.get("odds") or {}).get("quotes") or ())),
        "odds_adopted_quotes": len(adopted_odds_quotes(data)),
        "network_usage": dict(data.get("network_usage") or {}),
        "diagnostic_count": len(data.get("diagnostics") or ()),
        # 검색 자료는 유형별로 센다. "검색 자료 n건"이라고 뭉뚱그리지 않는다.
        "search_finding_count": len(data.get("search_findings") or ()),
        "search_findings_by_type": _search_material_counts(data),
        "browser_used": False,
    }


def search_findings_from_groups(
    groups: Sequence[Mapping[str, Any] | DiscoveryGroup],
) -> tuple[SearchFinding, ...]:
    """조사 그룹에 담긴 검색 자료를 묶음 자료로 옮긴다(중복 id는 첫 줄만).

    조사 그룹은 자기 실행에서 실제로 받은 줄을 그대로 들고 있다. 여기서 자료 유형을
    바꾸거나 합치지 않으며, 라벨이 없으면 유형 표기에서 채운다.
    """
    rows: list[SearchFinding] = []
    seen: set[str] = set()
    for group in groups:
        data = group.to_dict() if isinstance(group, DiscoveryGroup) else dict(group or {})
        for raw in data.get("search_findings") or ():
            if not isinstance(raw, Mapping):
                continue
            finding = SearchFinding.from_dict(raw)
            if not finding.finding_id or finding.finding_id in seen:
                continue
            seen.add(finding.finding_id)
            rows.append(finding)
    return tuple(rows)


def excerpt_for_delivery(content: str, *, limit: int = MAX_SEARCH_FINDING_CHARS) -> tuple[str, bool]:
    """작성 입력용 발췌. **원문은 손대지 않고**, 한도까지만 잘라 넘긴다.

    반환: (발췌, 잘렸는지). 잘렸다는 사실은 관리자 화면·프롬프트에 표시하며, 독자 본문에는
    넣지 않는다. 문장 중간에서 끊기지 않도록 마지막 문장 경계를 우선한다.
    """
    text = str(content or "")
    if len(text) <= limit:
        return text, False
    head = text[:limit]
    for stop in ("다.", ".", "。", "\n"):
        index = head.rfind(stop)
        if index >= limit // 2:
            return head[: index + len(stop)].strip(), True
    return head.strip(), True


def _search_material_counts(data: Mapping[str, Any]) -> dict[str, int]:
    counts = {key: 0 for key in SEARCH_MATERIAL_TYPES}
    for item in data.get("search_findings") or ():
        if not isinstance(item, Mapping):
            continue
        material_type = str(item.get("material_type") or "")
        if material_type in counts:
            counts[material_type] += 1
    return counts


def describe_bundle(bundle: InformationBundle | Mapping[str, Any]) -> dict[str, Any]:
    """관리자 검사용 설명. 무엇이 근거이고 무엇이 실패였는지 구분한다."""
    data = bundle_to_dict(bundle)
    return {
        "summary": bundle_summary(data),
        "sources": [
            {
                "source_id": item.get("source_id"),
                "discovery_group": item.get("discovery_group"),
                "nature": item.get("nature"),
                "method": item.get("method"),
                "requested_url": item.get("requested_url"),
                "final_url": item.get("final_url"),
                "title": item.get("title"),
                "captured_at": item.get("captured_at"),
                "body_chars": item.get("body_chars"),
                "passage_count": len(item.get("passages") or ()),
                "delivered_chars": item.get("delivered_chars"),
                "failure": item.get("failure"),
                "usable": item.get("usable"),
                "body_artifact_id": item.get("body_artifact_id"),
            }
            for item in data.get("sources") or ()
            if isinstance(item, Mapping)
        ],
        "available_passages": [
            {
                "passage_id": item.get("passage_id"),
                "source_id": item.get("source_id"),
                "ordinal": item.get("ordinal"),
                "char_count": item.get("char_count"),
                "heading": item.get("heading"),
                "text": item.get("text"),
            }
            for item in collect_available_passages(data)
        ],
        "section_deliveries": list(data.get("section_deliveries") or ()),
        # 검색 자료는 원문 필드를 그대로 보여준다(라벨 포함). 여기서 합치거나 이름을
        # 바꾸지 않는다. 화면·로그가 `material_type`으로 구분해 표시한다.
        "search_findings": list(data.get("search_findings") or ()),
        "search_material_counts": _search_material_counts(data),
        "odds_adopted": list(adopted_odds_quotes(data)),
        "db_snapshot": data.get("db_snapshot"),
        "odds": data.get("odds"),
        "discovery_groups": data.get("discovery_groups"),
        "diagnostics": data.get("diagnostics"),
        "delivery_limits": data.get("delivery_limits"),
        "honesty_note": (
            "URL 후보와 실제 수집 본문은 다릅니다. 실패한 출처는 후보로만 남고 근거로"
            " 쓰이지 않습니다. 이 묶음은 기사와 DB를 교차 검증해 탈락시키지 않으며"
            " Google 인용 메타데이터를 필수 조건으로 요구하지 않습니다."
        ),
    }


def validate_information_bundle(
    bundle: InformationBundle | Mapping[str, Any],
    *,
    limits: DeliveryLimits | None = None,
) -> tuple[str, ...]:
    """묶음이 계약을 어긴 지점 목록. 비어 있으면 통과다.

    거부 조건만 본다(보고용 아님):

    - 출처 ID 중복, 구간이 없는 출처 참조
    - 알 수 없는 자료 성격·수집 방법·조사 그룹
    - 완료가 아닌 조사 그룹 (진행 중을 완료로 세지 않음)
    - 발췌 상한 초과 (출처 수·구간 수·구간 길이·웹 총량·DB 포함 총량)
    - 배당 시장/값 혼합 (정규시간 1X2 외, 누락값)
    """
    cap = limits or DeliveryLimits()
    data = bundle_to_dict(bundle)
    problems: list[str] = []

    if not data.get("bundle_id"):
        problems.append("bundle_id가 없습니다.")
    if not isinstance(data.get("fixture"), Mapping) or not data.get("fixture"):
        problems.append("fixture 식별자가 없습니다.")
    if str(data.get("team_id_space") or "unknown") == "unknown":
        problems.append("team_id_space가 unknown입니다. 내부/외부 ID를 섞을 수 없습니다.")

    sources = [item for item in data.get("sources") or () if isinstance(item, Mapping)]
    seen_ids: set[str] = set()
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if not source_id:
            problems.append("source_id가 없는 출처가 있습니다.")
            continue
        if source_id in seen_ids:
            problems.append(f"출처 ID가 중복됩니다: {source_id}")
        seen_ids.add(source_id)
        nature = str(source.get("nature") or "unknown")
        if nature not in SOURCE_NATURES:
            problems.append(f"알 수 없는 자료 성격입니다: {source_id}={nature}")
        method = str(source.get("method") or "")
        if method not in COLLECTION_METHODS:
            problems.append(f"알 수 없는 수집 방법입니다: {source_id}={method}")
        group = canonical_discovery_group(str(source.get("discovery_group") or ""))
        if group not in DISCOVERY_GROUPS:
            problems.append(f"알 수 없는 조사 그룹입니다: {source_id}={group}")
        if source.get("failure") and source.get("passages"):
            problems.append(
                f"실패로 기록된 출처에 후보 구간이 있습니다: {source_id}"
            )
        if nature == "unavailable" and source.get("passages"):
            problems.append(f"미확보 출처에 후보 구간이 있습니다: {source_id}")

    for group in data.get("discovery_groups") or ():
        if not isinstance(group, Mapping):
            continue
        status = str(group.get("status") or "")
        if status not in DISCOVERY_STATUSES:
            problems.append(f"알 수 없는 조사 상태입니다: {group.get('group')}={status}")

    # 검색 자료는 **자료 유형별로만** 통과시킨다. 유형이 없거나 모르는 값이면 거부하고,
    # 검색 스니펫이라고 적혔는데 실제 내용이 없으면(URL만 있는 후보) 그것도 거부한다.
    # 이 검사가 곧 "URL만 있다고 기사 내용을 추정하지 않는다"의 강제 지점이다.
    seen_findings: set[str] = set()
    for item in data.get("search_findings") or ():
        if not isinstance(item, Mapping):
            problems.append("검색 자료 항목이 객체가 아닙니다.")
            continue
        finding_id = str(item.get("finding_id") or "")
        if not finding_id:
            problems.append("검색 자료에 finding_id가 없습니다.")
        elif finding_id in seen_findings:
            problems.append(f"검색 자료 id가 중복됩니다: {finding_id}")
        seen_findings.add(finding_id)
        material_type = str(item.get("material_type") or "")
        if material_type not in SEARCH_MATERIAL_TYPES:
            problems.append(
                f"알 수 없는 검색 자료 유형입니다: {finding_id}={material_type or '없음'}"
            )
            continue
        group = canonical_discovery_group(str(item.get("discovery_group") or ""))
        if group not in DISCOVERY_GROUPS:
            problems.append(f"검색 자료의 조사 그룹이 모릅니다: {finding_id}={group}")
        content = str(item.get("content") or "").strip()
        if material_type in ("search_ai_summary", "search_snippet", "model_cited_span") and not content:
            problems.append(
                f"내용이 없는 검색 자료를 {material_type}으로 표시했습니다: {finding_id}"
            )
        # 길이는 **거부 사유가 아니다**. 원문은 이 묶음(과 원문 응답 아티팩트)에 그대로
        # 보존하고, 작성 입력에 넣을 때만 한도 안으로 줄인다(`excerpt_for_delivery`).
        # 한 요약이 길다는 이유로 다른 자료나 전체 본문을 반려하지 않는다(SF-02 회귀).

    usable_sources = [item for item in sources if item.get("usable")]
    if len(usable_sources) > cap.max_sources_per_section:
        problems.append(
            f"사용 가능 출처가 섹션 상한({cap.max_sources_per_section})을 넘습니다:"
            f" {len(usable_sources)}"
        )

    total_chars = 0
    for source in sources:
        passages = [item for item in source.get("passages") or () if isinstance(item, Mapping)]
        if len(passages) > cap.max_passages_per_source:
            problems.append(
                f"출처 구간이 상한({cap.max_passages_per_source})을 넘습니다:"
                f" {source.get('source_id')}={len(passages)}"
            )
        for passage in passages:
            text = str(passage.get("text") or "")
            if len(text) > cap.max_passage_chars:
                problems.append(
                    f"구간 길이가 상한({cap.max_passage_chars}자)을 넘습니다:"
                    f" {passage.get('passage_id')}={len(text)}"
                )
            total_chars += len(text)
            if str(passage.get("source_id") or "") not in seen_ids:
                problems.append(
                    f"구간이 없는 출처를 가리킵니다: {passage.get('passage_id')}"
                    f" → {passage.get('source_id')}"
                )
    if total_chars > cap.max_bundle_input_chars:
        problems.append(
            f"정보 원문 총량이 상한({cap.max_bundle_input_chars}자)을 넘습니다: {total_chars}"
        )

    # 배당은 **선택** 섹션이다. 불완전·미지원 배당 줄 때문에 묶음 전체나 필수 작성
    # (AI 전망·점수·주목 선수)을 막지 않는다. 그 줄은 채택하지 않고 진단으로만 남긴다
    # (`adopted_odds_quotes`). 여기서 거부하면 자료가 조금 부족한 경기의 필수 섹션까지
    # 막혀 설계의 "부분 자료로도 필수 작성" 요구를 어긴다.
    return tuple(dict.fromkeys(problems))


def ensure_valid_bundle(
    bundle: InformationBundle | Mapping[str, Any],
    *,
    limits: DeliveryLimits | None = None,
) -> None:
    """검증 실패 시 `BundleBuildError`. 저장 직전 한 번 부른다."""
    problems = validate_information_bundle(bundle, limits=limits)
    if problems:
        raise BundleBuildError("; ".join(problems))


def adopted_odds_quotes(
    bundle: InformationBundle | Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """실제로 채택할 수 있는 배당 줄(정규시간 1X2 + 세 값 모두 있음).

    채택되지 않은 줄은 버리지 않고 `describe_odds()`에서 사유와 함께 보여준다.
    """
    odds = bundle_to_dict(bundle).get("odds")
    if not isinstance(odds, Mapping):
        return ()
    adopted: list[dict[str, Any]] = []
    for quote in odds.get("quotes") or ():
        if not isinstance(quote, Mapping):
            continue
        market = str(quote.get("market") or "")
        values = (
            quote.get("home_decimal"),
            quote.get("draw_decimal"),
            quote.get("away_decimal"),
        )
        if market == ODDS_MARKET_REGULATION_1X2 and all(v is not None for v in values):
            adopted.append(dict(quote))
    return tuple(adopted)


def describe_odds(bundle: InformationBundle | Mapping[str, Any]) -> dict[str, Any]:
    """배당 섹션 재료의 채택/미채택 내역. 숫자를 만들어 채우지 않는다."""
    data = bundle_to_dict(bundle)
    odds = data.get("odds")
    if not isinstance(odds, Mapping):
        return {
            "available": False,
            "adopted": [],
            "ignored": [],
            "note": "이 묶음에는 배당 수집 결과가 없습니다.",
        }
    adopted = list(adopted_odds_quotes(data))
    adopted_ids = {str(item.get("source_id")) for item in adopted}
    ignored: list[dict[str, Any]] = []
    for quote in odds.get("quotes") or ():
        if not isinstance(quote, Mapping):
            continue
        if str(quote.get("source_id")) in adopted_ids:
            continue
        reason = (
            "정규시간 1X2 시장이 아닙니다."
            if str(quote.get("market") or "") != ODDS_MARKET_REGULATION_1X2
            else "홈/무/원정 값이 모두 있지 않아 채택하지 않았습니다(추정 금지)."
        )
        ignored.append({**dict(quote), "ignored_reason": reason})
    return {
        "available": bool(adopted),
        "adopted": adopted,
        "ignored": ignored,
        "unsupported_sites": list(odds.get("unsupported_sites") or ()),
        "diagnostics": list(odds.get("diagnostics") or ()),
        "note": (
            "배당은 선택 섹션입니다. 채택 가능한 줄이 없으면 독자 화면에서 생략하고"
            " 관리자에게만 사유를 남깁니다. 빠진 값을 추정해 채우지 않습니다."
        ),
    }



# --------------------------------------------------------------------------
# B(수집) → A(계약) 어댑터
# --------------------------------------------------------------------------
#
# B의 `retrieval.collect_information_bundle`은 자기 `CollectionResult`를 돌려주고,
# A의 계약은 `InformationBundle`이다. 반환형을 서로 고치지 않기 위해 **A가** 이
# 어댑터를 소유한다. B는 자기 모양을 그대로 유지하고, A의 저장·API·섹션 작성은
# `InformationBundle`만 본다. 두 모델을 한 파일에서 섞지 않는다.

# B가 쓰는 후보 종류 → 이 계약의 자료 성격.
_KIND_TO_NATURE: Mapping[str, str] = {
    "preview": "preview",
    "article": "news",
    "list": "unknown",
    "stats": "stats",
    "profile": "profile",
    "odds": "odds",
    "other": "unknown",
}

# B의 추출 방법 표기 → 이 계약의 수집 방법.
_EXTRACTION_TO_METHOD: Mapping[str, str] = {
    "trafilatura": "fresh_http",
    "scrapling": "fresh_http",
    "text_fallback": "text_fallback",
    "article": "fresh_http",
    "stored_capture": "stored_capture",
}


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """dataclass/매핑 양쪽에서 같은 이름을 읽는다. 어댑터가 모양에 덜 민감해진다."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _nature_for_kind(kind: Any, *, nature_hint: Any = None) -> str:
    """후보 종류에서 자료 성격을 정한다. 확정할 수 없으면 `unknown`이다.

    `past_match_report`는 URL/제목 단서가 필요하므로 호출자가 `nature_hint`로 준다.
    근거 없이 "프리뷰 기사"로 승격하지 않는다.
    """
    hint = str(nature_hint or "").strip()
    if hint in SOURCE_NATURES:
        return hint
    return _KIND_TO_NATURE.get(str(kind or "").strip().lower(), "unknown")


def _method_for_source(source: Any) -> str:
    """수집 방법. 실패한 출처는 `unavailable`이다(본문이 없다)."""
    if _attr(source, "failure") and not _attr(source, "text"):
        return "unavailable"
    extraction = str(_attr(source, "extraction") or "").strip().lower()
    if extraction in _EXTRACTION_TO_METHOD:
        return _EXTRACTION_TO_METHOD[extraction]
    method = str(_attr(source, "method") or "").strip().lower()
    if method in COLLECTION_METHODS:
        return method
    return "fresh_http" if _attr(source, "final_url") else "unavailable"


def bundle_source_from_collection(source: Any, *, group: str) -> BundleSource:
    """B의 출처 하나를 계약 출처로 옮긴다. 본문 전문은 여기 넣지 않는다.

    B의 `Passage.to_dict()`는 본문을 빼고 길이·위치만 낸다. 그래서 여기서는 dict가 아니라
    객체 속성을 읽어 실제 구간 텍스트를 옮긴다. 텍스트가 없으면 구간을 만들지 않는다.
    """
    passages: list[Passage] = []
    raw_passages = _attr(source, "passages") or ()
    for ordinal, item in enumerate(raw_passages, start=1):
        if isinstance(item, Mapping) and "text" not in item:
            # dict로 넘어왔는데 본문이 없으면 지어내지 않는다. 구간을 건너뛴다.
            continue
        text = str(_attr(item, "text") or "")
        if not text.strip():
            continue
        passage_id = str(_attr(item, "passage_id") or "")
        if not passage_id:
            continue
        passages.append(
            Passage(
                passage_id=passage_id,
                source_id=str(_attr(source, "source_id") or ""),
                ordinal=int(_attr(item, "ordinal") or _attr(item, "index") or ordinal),
                text=text,
                char_count=len(text),
                heading=_attr(item, "heading"),
            )
        )

    failure = _attr(source, "failure")
    detail = _attr(source, "failure_detail")
    failure_text = None
    if failure:
        failure_text = f"{failure}: {detail}" if detail else str(failure)

    text_body = str(_attr(source, "text") or "")
    collected_at = _attr(source, "collected_at")
    return BundleSource(
        source_id=str(_attr(source, "source_id") or ""),
        discovery_group=canonical_discovery_group(str(_attr(source, "search_group") or group)),
        requested_url=_attr(source, "requested_url"),
        final_url=_attr(source, "final_url"),
        nature=_nature_for_kind(_attr(source, "kind")),
        method=_method_for_source(source),
        title=_attr(source, "title"),
        captured_at=collected_at if isinstance(collected_at, datetime) else None,
        http_status=_attr(source, "http_status"),
        redirects=len(_attr(source, "redirects") or ()) or None,
        extractor=_attr(source, "extractor"),
        body_chars=len(text_body) if text_body else None,
        body_sha256=_attr(source, "body_sha256"),
        passages=tuple(passages),
        failure=failure_text or ("본문 없음" if not text_body else None),
    )


def odds_market_from_observation(observation: Any, *, source_id: str, site: str) -> OddsMarket:
    """B의 배당 관측 하나를 계약 배당 시장으로 옮긴다.

    `available=False`면 빈 시장과 사유만 남긴다(숫자를 만들지 않는다). 값이 일부만 있으면
    그 줄은 `complete=False`이며 `adopted_odds_quotes()`가 채택하지 않는다.
    """
    if observation is None or not _attr(observation, "available"):
        reason = _attr(observation, "reason") if observation is not None else None
        note = _attr(observation, "note") if observation is not None else None
        detail = reason or note or "배당 수집 결과가 없습니다."
        return OddsMarket(diagnostics=(str(detail),), unsupported_sites=(site,))

    market_name = str(_attr(observation, "market") or ODDS_MARKET_REGULATION_1X2)
    quote = OddsQuote(
        source_id=source_id,
        site=str(_attr(observation, "bookmaker") or site),
        market=market_name,
        observed_at=_attr(observation, "observed_at"),
        home_decimal=_attr(observation, "home"),
        draw_decimal=_attr(observation, "draw"),
        away_decimal=_attr(observation, "away"),
        note=_attr(observation, "note"),
    )
    diagnostics: tuple[str, ...] = ()
    unsupported: tuple[str, ...] = ()
    if not quote.complete:
        diagnostics = (
            "배당 값이 일부만 확인되어 이 줄을 채택하지 않았습니다(추정 금지).",
        )
        unsupported = (quote.site,)
    return OddsMarket(
        quotes=(quote,),
        collected_at=quote.observed_at,
        diagnostics=diagnostics,
        unsupported_sites=unsupported,
    )


def discovery_group_from_result(result: Any) -> DiscoveryGroup:
    """B의 `DiscoveryResult`를 계약 조사 기록으로 옮긴다. 후보 URL만 넘긴다."""
    group = canonical_discovery_group(str(_attr(result, "group") or ""))
    status = str(_attr(result, "status") or "not_run")
    if status not in DISCOVERY_STATUSES:
        # B는 "no_material" 같은 표기를 쓸 수 있다. 완료가 아니면 실패/미실행으로 남긴다.
        status = "not_run" if status in ("no_material", "") else "failed"
    candidates = _attr(result, "candidates") or ()
    urls: list[str] = []
    for candidate in candidates:
        url = _attr(candidate, "canonical_url") or _attr(candidate, "requested_url")
        if url:
            urls.append(str(url))
    model_result = _attr(result, "model_result")
    attempts = _attr(model_result, "attempts") or ()
    sent = sum(
        1
        for attempt in attempts
        if str(_attr(attempt, "error_class") or "") != "configuration_error"
    )
    return DiscoveryGroup(
        group=group,
        status=status,
        logical_call_id=_attr(result, "logical_call_id"),
        provider=_attr(getattr(model_result, "spec", None), "provider"),
        model=_attr(getattr(model_result, "spec", None), "model"),
        prompt_version=_attr(result, "prompt_version"),
        candidate_urls=tuple(urls),
        diagnostics=tuple(str(item) for item in (_attr(result, "diagnostics") or ())),
        sent_attempts=sent,
        # 검색이 실제로 돌려준 자료(검색 기반 AI 요약 포함)를 이 경로에서도 버리지 않는다.
        search_findings=tuple(
            dict(item)
            for item in (_attr(result, "search_findings") or ())
            if isinstance(item, Mapping)
        ),
        search_notes=tuple(str(item) for item in (_attr(result, "search_notes") or ())),
    )


def network_usage_from_collection(usage: Mapping[str, Any] | None, *, api_limit: int | None = None) -> NetworkUsage:
    """B의 `network_usage` dict를 계약 값으로 옮긴다. 없는 값은 `None`/0 그대로 둔다."""
    data = dict(usage or {})
    return NetworkUsage(
        http_used=int(data.get("used") or 0),
        http_failed=int(data.get("failed") or 0),
        redirects=int(data.get("redirects") or 0),
        api_used=int(data.get("used") or 0),
        http_limit=_int_or_none(data.get("limit")) or api_limit,
        api_limit=_int_or_none(data.get("limit")) or api_limit,
        note=str(data.get("counted")) if data.get("counted") else None,
    )


def bundle_from_collection(
    *,
    collection: Any,
    fixture: Mapping[str, Any] | None = None,
    team_id_space: str = "internal",
    db_snapshot: DbSnapshot | None = None,
    discovery_groups: Sequence[DiscoveryGroup] = (),
    collected_at: datetime | None = None,
    mode: str = "live",
    diagnostics: Sequence[str] = (),
    odds_source_id: str = "src:odds",
    odds_site: str = "public-table",
    bundle_id: str | None = None,
    build_note: str | None = None,
) -> InformationBundle:
    """B(수집)의 결과를 A의 `InformationBundle`로 맞춘다.

    B는 이미 계약 묶음을 돌려줄 수 있고(`collect_information_bundle`), 전문을 함께
    주는 `CollectionOutput`을 돌려줄 수도 있다. 이 함수는 **세 모양을 모두 받는다**:

    1. `InformationBundle` — 그대로 쓰되 호출자가 준 DB·조사·시각 값만 덮어쓴다.
    2. `.bundle`을 가진 결과(`CollectionOutput`) — 그 묶음을 같은 방식으로 덮어쓴다.
    3. 출처 목록만 가진 옛 모양(`.sources`, `.network_usage`) — 출처를 계약으로 옮긴다.

    어느 경우에도 자료를 더하거나 빼지 않는다. 실패한 출처는 그대로 남는다.
    """
    payload: InformationBundle | None = None
    if isinstance(collection, InformationBundle):
        payload = collection
    else:
        inner = _attr(collection, "bundle")
        if isinstance(inner, InformationBundle):
            payload = inner
        elif isinstance(inner, Mapping):
            payload = InformationBundle.from_dict(inner)

    if payload is not None:
        updates: dict[str, Any] = {}
        if fixture:
            updates["fixture"] = dict(fixture)
        if team_id_space and team_id_space != "unknown":
            updates["team_id_space"] = team_id_space
        if db_snapshot is not None:
            updates["db_snapshot"] = db_snapshot
        if discovery_groups:
            updates["discovery_groups"] = tuple(discovery_groups)
            # 조사 그룹이 실제로 받은 검색 자료를 묶음 자료로 합친다(라벨은 그대로).
            folded = search_findings_from_groups(discovery_groups)
            if folded:
                existing = {item.finding_id: item for item in payload.search_findings}
                for item in folded:
                    existing.setdefault(item.finding_id, item)
                merged = [item for item in payload.search_findings if item.finding_id in existing]
                # payload에 없던 새 줄은 발견 순서대로 뒤에 붙인다(순서 보존).
                known = {item.finding_id for item in merged}
                merged.extend(item for item in folded if item.finding_id not in known)
                updates["search_findings"] = tuple(merged)
        if collected_at is not None:
            updates["collected_at"] = collected_at
            updates["as_of"] = collected_at
        if mode and mode != payload.mode:
            updates["mode"] = mode
        if diagnostics:
            updates["diagnostics"] = tuple(payload.diagnostics) + tuple(
                str(item) for item in diagnostics
            )
        if bundle_id:
            updates["bundle_id"] = bundle_id
        if build_note:
            updates["build_note"] = build_note
        if not updates:
            return payload
        return replace(payload, **updates)

    # 옛 모양(출처 목록 중심) 경로. 이름·필드만 옮긴다.
    group_default = DISCOVERY_GROUP_PLAYERS_INJURY
    sources: list[BundleSource] = []
    for raw in _attr(collection, "sources") or ():
        if isinstance(raw, BundleSource):
            sources.append(raw)
            continue
        if isinstance(raw, Mapping) and "passages" in raw and "nature" in raw:
            sources.append(BundleSource.from_dict(raw))
            continue
        group = str(_attr(raw, "search_group") or group_default)
        sources.append(bundle_source_from_collection(raw, group=group))

    raw_odds = _attr(collection, "odds")
    if isinstance(raw_odds, OddsMarket):
        odds: OddsMarket | None = raw_odds
    elif isinstance(raw_odds, Mapping):
        odds = OddsMarket.from_dict(raw_odds)
    elif raw_odds is not None:
        odds = odds_market_from_observation(
            raw_odds, source_id=odds_source_id, site=odds_site
        )
    else:
        odds = None

    notes: list[str] = [str(item) for item in diagnostics]
    for item in _attr(collection, "diagnostics") or ():
        if isinstance(item, Mapping):
            reason = item.get("reason") or "diagnostic"
            url = item.get("url")
            notes.append(f"{reason}: {url}" if url else str(reason))
        else:
            notes.append(str(item))

    return InformationBundle(
        bundle_id=bundle_id or new_bundle_id(),
        fixture=dict(fixture or {}),
        team_id_space=team_id_space,
        collected_at=collected_at
        or (db_snapshot.collected_at if db_snapshot is not None else None),
        sources=tuple(sources),
        db_snapshot=db_snapshot,
        discovery_groups=tuple(discovery_groups),
        odds=odds,
        diagnostics=tuple(notes),
        network_usage=network_usage_from_collection(
            _attr(collection, "network_usage"),
        ),
        mode=mode,
        as_of=collected_at,
        build_note=build_note
        or (
            "B 수집 결과를 A 계약으로 옮긴 묶음입니다. 이전송·교차검증·모델 호출이"
            " 없습니다."
        ),
    )


def collection_bodies(collection: Any) -> tuple[Any, ...]:
    """B가 함께 넘긴 **전문** 목록. 없으면 빈 튜플이다(지어내지 않는다).

    A는 이 전문을 아티팩트로 저장하고 `BundleSource.body_artifact_id`를 채운다.
    묶음 dict에는 전문을 넣지 않는다.
    """
    bodies = _attr(collection, "bodies")
    if bodies:
        return tuple(bodies)
    return ()


def iter_source_urls(
    bundle: InformationBundle | Mapping[str, Any],
) -> Iterable[str]:
    """묶음이 실제로 가져온 최종 URL. 중복을 제거해 순서를 유지한다."""
    seen: dict[str, None] = {}
    for source in bundle_to_dict(bundle).get("sources") or ():
        if not isinstance(source, Mapping):
            continue
        url = source.get("final_url") or source.get("requested_url")
        if url:
            seen.setdefault(str(url), None)
    return tuple(seen)
