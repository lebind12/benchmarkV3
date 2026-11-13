"""두 조사 묶음(discovery) — 후보 URL만 찾는다 (PS-02).

설계 §"두 묶음 조사"의 **조사 A/B**를 담당한다.

- 묶음 A(`GROUP_PEOPLE`): 양 팀 주목 선수와 부상·결장 자료.
- 묶음 B(`GROUP_OUTLOOK`): 이 경기 외부 전망·예상 스코어와 공개 배당 출처.

경계(중요):

1. 조사 응답은 **후보 URL**이다. 응답에 적힌 사실 문장은 수집 본문이 아니며, 이 모듈은
   그 문장을 본문으로 승격하는 필드를 만들지 않는다(설계 §3).
2. 모델 호출은 기존 `provider.request_model` 하나뿐이다. 새 검색 도구·새 제공자·
   별도 SDK를 추가하지 않는다. 조사 호출에는 **작성용 검색 도구를 중복해서 넣지 않는다.**
3. 이 모듈은 HTTP를 보내지 않는다. 실제 본문 수집은 `retrieval.collect_information_bundle`
   이 맡는다. 조사 함수가 수집이나 작성을 실행해서는 안 된다(계획 공통 계약).
4. 후보 정규화는 결정적이다. 스킴이 http/https가 아니거나, 호스트가 없거나, 같은 문서를
   가리키는 중복은 후보에서 빼고 **사유와 함께** 남긴다.
5. 응답이 깨졌으면 `DiscoveryParseError`다. 빈 후보 목록과 구분한다.

이 모듈은 `httpx`·`requests`·`socket`을 import하지 않는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from app.preview.contracts import (
    ExecutionContext,
    FixtureIdentity,
    RequestClass,
    RunMode,
)
from app.preview import provider
from app.preview.provider import (
    ContentCheck,
    ExecuteRequestResult,
    ProviderTransport,
    request_model,
)
from app.preview.retry import sleep_seconds as provider_sleep_seconds
from app.preview.retry import RunBudget

__all__ = [
    "GROUP_OUTLOOK",
    "GROUP_PEOPLE",
    "GROUPS",
    "LOGICAL_CALL_IDS",
    "PROMPT_PATHS",
    "PROMPT_VERSIONS",
    "Candidate",
    "DiscoveryParseError",
    "DiscoveryResult",
    "build_prompt",
    "discover_candidates",
    "normalize_candidate_url",
    "parse_candidates",
    "to_discovery_group",
]

GROUP_PEOPLE = "people"
GROUP_OUTLOOK = "outlook"
GROUPS: tuple[str, ...] = (GROUP_PEOPLE, GROUP_OUTLOOK)

# 묶음마다 논리 호출 id가 다르다. 예산·기록에서 두 조사를 같은 호출로 뭉개지 않는다.
LOGICAL_CALL_IDS: dict[str, str] = {
    GROUP_PEOPLE: "discovery_people",
    GROUP_OUTLOOK: "discovery_outlook",
}

MODULE_IDS: dict[str, str] = {
    GROUP_PEOPLE: "D1",
    GROUP_OUTLOOK: "D2",
}

# - v2: URL만이 아니라 **검색을 사용해 정리한 주제별 요약**(`summary`)과 인용 주소를
#   함께 내도록 바꿨다. 같은 요청이라도 결과 의미가 달라지므로 새 버전으로 확인한다.
PROMPT_VERSIONS: dict[str, str] = {
    GROUP_PEOPLE: "discovery_people/v2",
    GROUP_OUTLOOK: "discovery_outlook/v2",
}

PROMPT_PATHS: dict[str, str] = {
    GROUP_PEOPLE: "discovery_people.md",
    GROUP_OUTLOOK: "discovery_outlook.md",
}

STATUS_COMPLETED = "completed"
STATUS_NO_MATERIAL = "no_material"
STATUS_FAILED = "failed"

# 정규화에서 지우는 추적성 쿼리 키. 같은 문서를 가리키는 변형을 합치기 위한 것이다.
TRACKING_QUERY_KEYS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "referrer",
        "source",
        "spm",
        "igshid",
    }
)

ALLOWED_SCHEMES = frozenset({"http", "https"})

# 후보 종류. 수집 단계가 추출 폴백을 고르는 힌트일 뿐, "수집했다"는 뜻이 아니다.
CANDIDATE_KINDS = frozenset(
    {"article", "preview", "list", "stats", "profile", "odds", "other"}
)

# 검색 도구 응답의 grounding 메타데이터에서 읽는 키. snake_case/camelCase를 모두 본다.
_GROUNDING_KEYS = ("grounding_metadata", "groundingMetadata")
_CHUNK_KEYS = ("grounding_chunks", "groundingChunks")
_SUPPORT_KEYS = ("grounding_supports", "groundingSupports")
_QUERY_KEYS = ("web_search_queries", "webSearchQueries")


def _grounding_metadata_for(raw_response: Any) -> Mapping[str, Any] | None:
    """응답에서 grounding 메타데이터 매핑을 꺼낸다. 없으면 `None`(만들지 않는다)."""
    candidate = _first_candidate(raw_response)
    if candidate is None:
        return None
    for key in _GROUNDING_KEYS:
        value = candidate.get(key)
        if isinstance(value, Mapping) and value:
            return value
    return None


def _first_candidate(raw_response: Any) -> Mapping[str, Any] | None:
    if not isinstance(raw_response, Mapping):
        return None
    candidates = raw_response.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return None
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            return candidate
    return None


def _chunk_rows(metadata: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    chunks = None
    for key in _CHUNK_KEYS:
        if key in metadata:
            chunks = metadata.get(key)
            break
    if not isinstance(chunks, Sequence) or isinstance(chunks, (str, bytes)):
        return rows
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            continue
        web = chunk.get("web")
        if isinstance(web, Mapping):
            rows.append(web)
        elif isinstance(web, str) and web.strip():
            # 옛 SDK 모양: web이 URI 문자열이면 주소만 있는 것으로 본다(내용 추정 금지).
            rows.append({"uri": web.strip()})
    return rows


def _quick_match(chunk: Mapping[str, Any], sentence: str) -> bool:
    """인용 문장이 이 청크에서 온 것인지 **관측 가능한 단서로만** 판정한다.

    구글 응답은 청크별 요약문을 주지 않는다. 그래서 문장에 그 청크의 도메인 이름이
    실제로 들어 있는 경우만 연결하고, 그 밖의 경우는 연결하지 않는다(추측 금지).
    """
    domain = str(chunk.get("domain") or "").strip().lower()
    if not domain:
        return False
    bare = domain[4:] if domain.startswith("www.") else domain
    lowered = sentence.lower()
    return bare in lowered or domain in lowered


def extract_search_findings(
    raw_response: Any,
    *,
    group: str,
    captured_at: datetime | None = None,
    response_artifact_id: Any | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """조사 원문 응답에서 **실제로 반환된** 검색 자료만 줄 단위로 꺼낸다.

    돌려주는 값은 `(findings, notes)`이고 각 finding은
    `information_bundle.SearchFinding` 계약과 같은 키를 쓴다.

    경계(사용자 확정 기준):

    - 청크의 `domain`·`title`·`uri`는 **메타데이터**이며 기사 요약문이 아니다.
      `material_type="search_source_meta"`로만 남기고, 그 값을 스니펫으로 승격하지 않는다.
    - 응답에 요약/스니펫 필드가 실제로 있으면(향후 제공자 변화) 그 값만
      `material_type="search_snippet"`이다. 없으면 만들지 않는다.
    - `grounding_supports[].segment.text`는 **모델이 쓴 문장**이다.
      `material_type="model_cited_span"`으로 남기며 검색 요약문이라 부르지 않는다.
    - `web_search_queries`는 검색 질의 목록이다. 자료가 아니므로 finding으로 만들지
      않고 `notes`에 개수만 남긴다.
    """
    notes: list[str] = []
    candidate = _first_candidate(raw_response)
    if candidate is None:
        return [], ["모델 응답에 후보가 없어 검색 반환 필드를 읽지 못했습니다."]
    metadata = None
    for key in _GROUNDING_KEYS:
        if isinstance(candidate.get(key), Mapping):
            metadata = candidate[key]
            break
    if not isinstance(metadata, Mapping) or not metadata:
        return [], [
            "이 응답에는 검색 메타데이터(grounding)가 없습니다. 검색 자료를 만들지"
            " 않았습니다."
        ]

    findings: list[dict[str, Any]] = []
    chunks = _chunk_rows(metadata)
    for index, web in enumerate(chunks, start=1):
        uri = str(web.get("uri") or "").strip() or None
        title = str(web.get("title") or "").strip() or None
        domain = str(web.get("domain") or "").strip() or None
        # 스니펫/요약 필드가 응답에 실제로 있는 경우만 이 값을 쓴다.
        snippet = None
        for key in ("snippet", "summary", "content", "text"):
            value = web.get(key)
            if isinstance(value, str) and value.strip():
                snippet = value.strip()
                break
        content = snippet if snippet else None
        material_type = "search_snippet" if snippet else "search_source_meta"
        findings.append(
            {
                "finding_id": f"{group}-search-{index}",
                "discovery_group": group,
                "material_type": material_type,
                "title": title,
                "url": uri,
                "domain": domain,
                "content": content,
                "captured_at": captured_at,
                "response_artifact_id": response_artifact_id,
                "note": (
                    None
                    if snippet
                    else "검색 도구가 반환한 출처 메타데이터(도메인·주소)입니다."
                    " 요약문이 아닙니다."
                ),
            }
        )
    if findings:
        notes.append(
            f"검색 도구가 출처 {len(findings)}건을 반환했습니다."
            " 요약문 필드가 있는 항목만 search_snippet이며 나머지는 출처 메타입니다."
        )

    supports = None
    for key in _SUPPORT_KEYS:
        if key in metadata:
            supports = metadata.get(key)
            break
    spans = 0
    if isinstance(supports, Sequence) and not isinstance(supports, (str, bytes)):
        for support in supports:
            if not isinstance(support, Mapping):
                continue
            segment = support.get("segment")
            text = segment.get("text") if isinstance(segment, Mapping) else None
            if not isinstance(text, str) or not text.strip():
                continue
            indices = support.get("grounding_chunk_indices") or ()
            linked = [
                chunks[int(item) - 1]
                for item in indices
                if isinstance(item, int) and 0 < int(item) <= len(chunks)
            ]
            domain = None
            url = None
            for chunk in linked:
                if _quick_match(chunk, text):
                    domain = str(chunk.get("domain") or "") or None
                    url = str(chunk.get("uri") or "") or None
                    break
            spans += 1
            findings.append(
                {
                    "finding_id": f"{group}-span-{spans}",
                    "discovery_group": group,
                    "material_type": "model_cited_span",
                    "title": None,
                    "url": url,
                    "domain": domain,
                    "content": text.strip(),
                    "captured_at": captured_at,
                    "response_artifact_id": response_artifact_id,
                    "note": (
                        "모델이 자기 응답에서 쓴 인용 문장입니다. 검색 도구가 반환한"
                        " 요약문이 아니며, 연결 도메인은 문장에 이름이 실제로 나온 경우만"
                        " 표시했습니다."
                    ),
                }
            )
    if spans:
        notes.append(
            f"모델이 인용한 문장 {spans}건을 model_cited_span으로 남겼습니다(검색 요약문 아님)."
        )

    query_count = 0
    for key in _QUERY_KEYS:
        queries = metadata.get(key)
        if isinstance(queries, Sequence) and not isinstance(queries, (str, bytes)):
            query_count = len([item for item in queries if isinstance(item, str)])
            break
    if query_count:
        notes.append(f"검색 질의 {query_count}건이 응답에 기록되어 있습니다(자료 아님).")

    return findings, notes



class DiscoveryParseError(ValueError):
    """조사 응답을 후보로 해석할 수 없다. '자료 없음'과 구분한다."""


# 내부 상태 -> A의 묶음 조사 상태(`DISCOVERY_STATUSES`).
# `no_material`은 호출이 성공했으나 쓸 후보가 없는 경우다. 이것을 `failed`로 세면
# "자료가 없다"와 "조사가 실패했다"가 섞이고, `completed`로 세면 후보 없는 완료가 된다.
# A의 목록에 별도 값이 없으므로 `completed` + 빈 candidate_urls + 진단으로 남긴다.
_BUNDLE_STATUS = {
    STATUS_COMPLETED: "completed",
    STATUS_NO_MATERIAL: "completed",
    STATUS_FAILED: "failed",
}


# --------------------------------------------------------------------------
# 후보
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """조사 단계가 돌려주는 URL 후보.

    `collected`는 항상 False다. 후보는 아직 가져오지 않았고 본문도 없다. 이 값을
    True로 바꾸는 곳은 수집 단계뿐이며, 후보 객체를 수집 결과로 재사용하지 않는다.
    """

    candidate_id: str
    requested_url: str
    canonical_url: str
    title: str | None
    kind: str
    note: str | None
    search_group: str
    collected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "requested_url": self.requested_url,
            "canonical_url": self.canonical_url,
            "title": self.title,
            "kind": self.kind,
            "note": self.note,
            "search_group": self.search_group,
            "collected": self.collected,
        }


@dataclass(frozen=True)
class DiscoveryResult:
    """조사 한 묶음의 결론. 실패와 '자료 없음'과 '완료'를 구분한다."""

    group: str
    status: str
    candidates: tuple[Candidate, ...] = ()
    dropped: tuple[dict[str, Any], ...] = ()
    search_note: str | None = None
    prompt_version: str | None = None
    diagnostics: tuple[str, ...] = ()
    provider: str | None = None
    model: str | None = None
    # 실제로 전송된 시도 수. 기록 transport·모의는 0이며 live 성공으로 세지 않는다.
    sent_attempts: int = 0
    response_artifact_id: Any | None = None
    finished_at: datetime | None = None
    dropped_count: int = 0
    # 검색 도구를 실제로 사용해 모델이 정리한 **주제별 조사 요약**. 작성 입력으로 쓴다.
    # 각 항목은 `topic`·`text`·`sources`를 가지며, 기사 원문 발췌가 아니다.
    research_summary: tuple[dict[str, Any], ...] = ()
    # 검색 도구가 실제로 반환한 자료(출처 메타·요약이 있으면 요약·모델 인용 문장).
    # 각 줄의 `material_type`이 무엇인지 밝힌다. 후보 URL 목록과 섞지 않는다.
    search_findings: tuple[dict[str, Any], ...] = ()
    # 검색 자료에 대한 짧은 진단(질의 수, 스니펫 부재 등). 관리자/로그용이다.
    search_notes: tuple[str, ...] = ()
    model_result: ExecuteRequestResult | None = field(default=None, repr=False, compare=False)

    @property
    def completed(self) -> bool:
        return self.status == STATUS_COMPLETED

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "status": self.status,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "dropped": [dict(item) for item in self.dropped],
            "search_note": self.search_note,
            "prompt_version": self.prompt_version,
            "diagnostics": list(self.diagnostics),
            "provider": self.provider,
            "model": self.model,
            "sent_attempts": self.sent_attempts,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "dropped_count": self.dropped_count,
            "research_summary": [dict(item) for item in self.research_summary],
            "search_findings": [dict(item) for item in self.search_findings],
            "search_notes": list(self.search_notes),
        }


def to_discovery_group(result: DiscoveryResult):
    """조사 결과를 A의 `DiscoveryGroup`으로 옮긴다.

    이름 표기는 `canonical_discovery_group()`을 거쳐 `players_injury`/`media_odds`가 된다.
    후보 URL만 넘기고 응답 텍스트는 넘기지 않는다(응답 문장은 근거가 아니다).
    전송 시도 수는 호출 시점에 transport 기준으로 기록해 둔 값을 그대로 쓴다.
    """
    from app.preview.information_bundle import DiscoveryGroup, canonical_discovery_group

    diagnostics = list(result.diagnostics)
    if result.status == STATUS_NO_MATERIAL:
        diagnostics.append(
            "조사 호출은 성공했지만 쓸 후보 URL이 없습니다(자료 없음, 실패 아님)."
        )
    if result.dropped_count:
        diagnostics.append(f"후보 {result.dropped_count}건을 정규화에서 제외했습니다.")

    return DiscoveryGroup(
        group=canonical_discovery_group(result.group),
        status=_BUNDLE_STATUS.get(result.status, "failed"),
        logical_call_id=LOGICAL_CALL_IDS.get(result.group),
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        response_artifact_id=result.response_artifact_id,
        candidate_urls=tuple(candidate.requested_url for candidate in result.candidates),
        diagnostics=tuple(diagnostics),
        sent_attempts=result.sent_attempts,
        started_at=None,
        finished_at=result.finished_at,
        # 검색 자료는 자료 유형 라벨을 그대로 넘긴다. 여기서 이름을 바꾸지 않는다.
        search_findings=tuple(dict(item) for item in result.search_findings),
        search_notes=tuple(str(item) for item in result.search_notes),
    )


# --------------------------------------------------------------------------
# URL 정규화
# --------------------------------------------------------------------------


def _discovery_content_check(group: str) -> ContentCheck:
    """조사 응답의 내용 수용 기준(잘림·JSON 해석 실패만 다시 보낸다)."""

    label = f"조사({group})"

    def accepts(text: str | None, raw_response: Any) -> str | None:
        truncated = provider.rejection_of_truncated_or_unparseable(
            label=label,
            finish_reason=provider.extract_finish_reason(raw_response),
            text=text,
        )
        if truncated:
            return truncated
        if not text:
            return f"{label} 응답 본문이 비어 있습니다. 다시 보냅니다."
        try:
            _json_payload(text)
        except DiscoveryParseError as exc:
            return f"{exc} 같은 모듈의 남은 횟수 안에서 다시 보냅니다."
        return None

    return provider.ContentCheck(accepts=accepts, label=label)


def normalize_candidate_url(url: str) -> str | None:
    """후보 URL을 비교 가능한 형태로 만든다. 쓸 수 없는 URL은 `None`이다.

    하는 일: 스킴·호스트 소문자화, 기본 포트 제거, fragment 제거, 추적성 쿼리 제거,
    빈 경로를 `/`로, 쿼리 키 정렬. 하지 않는 일: 경로 재작성, 슬래시 추측, 대소문자
    변환(경로는 대소문자를 구분한다).
    """
    if not isinstance(url, str):
        return None
    text = url.strip()
    if not text:
        return None
    parsed = urlparse(text)
    scheme = parsed.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if any(ch in host for ch in " <>\"'`"):
        return None

    port = parsed.port
    netloc = host
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{host}:{port}"

    path = parsed.path or "/"
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    query = urlencode(sorted(query_pairs))
    return urlunparse((scheme, netloc, path, "", query, ""))


# --------------------------------------------------------------------------
# 응답 해석
# --------------------------------------------------------------------------


def _json_payload(text: str) -> Mapping[str, Any]:
    """모델 응답에서 JSON 객체 하나를 꺼낸다. 코드 블록 표시는 허용한다."""
    if not isinstance(text, str) or not text.strip():
        raise DiscoveryParseError("조사 응답이 비어 있습니다.")
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = [line for line in candidate.splitlines() if not line.strip().startswith("```")]
        candidate = "\n".join(lines).strip()
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise DiscoveryParseError("조사 응답에서 JSON 객체를 찾지 못했습니다.") from None
        try:
            payload = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise DiscoveryParseError(f"조사 응답 JSON을 해석하지 못했습니다: {exc}") from None
    if not isinstance(payload, Mapping):
        raise DiscoveryParseError("조사 응답이 JSON 객체가 아닙니다.")
    return payload


def _clean_kind(value: Any) -> str:
    kind = str(value or "").strip().lower()
    return kind if kind in CANDIDATE_KINDS else "other"


def parse_candidates(text: str, *, group: str) -> DiscoveryResult:
    """조사 응답 텍스트를 후보 목록으로 바꾼다. 순수 함수다(네트워크·모델 없음)."""
    if group not in GROUPS:
        raise ValueError(f"unknown discovery group: {group!r}")
    payload = _json_payload(text)

    raw_candidates = payload.get("candidates")
    if raw_candidates is None:
        raw_candidates = []
    if not isinstance(raw_candidates, Sequence) or isinstance(raw_candidates, (str, bytes)):
        raise DiscoveryParseError("조사 응답의 candidates가 목록이 아닙니다.")

    seen: set[str] = set()
    candidates: list[Candidate] = []
    dropped: list[dict[str, Any]] = []

    for index, item in enumerate(raw_candidates, start=1):
        if not isinstance(item, Mapping):
            dropped.append({"index": index, "reason": "not_an_object"})
            continue
        url = item.get("url")
        canonical = normalize_candidate_url(url if isinstance(url, str) else "")
        if canonical is None:
            dropped.append(
                {
                    "index": index,
                    "reason": "unsupported_url",
                    "url": url if isinstance(url, str) else None,
                }
            )
            continue
        if canonical in seen:
            dropped.append({"index": index, "reason": "duplicate", "url": canonical})
            continue
        seen.add(canonical)
        candidates.append(
            Candidate(
                candidate_id=f"{group}-{len(candidates) + 1}",
                requested_url=(url or "").strip() if isinstance(url, str) else canonical,
                canonical_url=canonical,
                title=(str(item["title"]).strip() if item.get("title") else None),
                kind=_clean_kind(item.get("kind")),
                note=(str(item["note"]).strip() if item.get("note") else None),
                search_group=group,
            )
        )

    note = payload.get("search_note")
    return DiscoveryResult(
        group=group,
        status=STATUS_COMPLETED,
        candidates=tuple(candidates),
        dropped=tuple(dropped),
        search_note=(str(note).strip() if isinstance(note, str) and note.strip() else None),
        research_summary=parse_research_summary(payload, group=group),
        prompt_version=PROMPT_VERSIONS[group],
    )


# 주제 표기 정규화. 프롬프트가 제안한 값을 받되, 모르는 표기는 그대로 보존한다.
SUMMARY_TOPICS: tuple[str, ...] = (
    "주목 선수",
    "부상·결장",
    "최근 흐름",
    "외부 전망",
    "예상 스코어",
    "배당 표",
    "기타",
)


def parse_research_summary(payload: Mapping[str, Any], *, group: str) -> tuple[dict[str, Any], ...]:
    """조사 응답의 `summary`를 주제별 요약 항목으로 읽는다(순수 함수).

    - `text`가 비어 있는 항목은 **만들지 않는다**(빈 요약을 자료로 세지 않는다).
    - `sources`는 실제 http/https 주소만 남긴다. 주소가 없으면 그대로 빈 목록이며,
      호출부가 "근거 주소 없음"을 진단으로 남긴다(내용을 지어내지 않는다).
    - `unverified`는 모델이 스스로 낮은 확신을 표시한 값이다. 숨기지 않고 그대로 넘긴다.
    """
    raw = payload.get("summary")
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        sources: list[str] = []
        raw_sources = item.get("sources")
        if isinstance(raw_sources, Sequence) and not isinstance(raw_sources, (str, bytes)):
            for candidate in raw_sources:
                if not isinstance(candidate, str):
                    continue
                canonical = normalize_candidate_url(candidate)
                if canonical and canonical not in sources:
                    sources.append(canonical)
        topic = item.get("topic")
        rows.append(
            {
                "summary_id": f"{group}-summary-{len(rows) + 1}",
                "topic": str(topic).strip() if isinstance(topic, str) and topic.strip() else "기타",
                "text": text.strip(),
                "sources": sources,
                "publisher": (
                    str(item["publisher"]).strip()
                    if isinstance(item.get("publisher"), str) and item.get("publisher").strip()
                    else None
                ),
                "predicted_score": (
                    str(item["predicted_score"]).strip()
                    if isinstance(item.get("predicted_score"), str)
                    and item.get("predicted_score").strip()
                    else None
                ),
                "unverified": bool(item.get("unverified")),
                "index": index,
            }
        )
    return tuple(rows)


# --------------------------------------------------------------------------
# 프롬프트
# --------------------------------------------------------------------------


def _prompt_path(group: str):
    from pathlib import Path

    return Path(__file__).resolve().parent / "prompts" / PROMPT_PATHS[group]


def load_prompt(group: str) -> str:
    """묶음별 프롬프트 전문. 파일이 없으면 조용히 대체하지 않고 실패한다."""
    path = _prompt_path(group)
    if not path.exists():
        raise FileNotFoundError(f"discovery prompt missing: {path}")
    return path.read_text(encoding="utf-8")


def build_prompt(
    group: str,
    *,
    fixture: FixtureIdentity,
    home_team: str,
    away_team: str,
    today: str,
    league: str | None = None,
    kickoff_label: str | None = None,
    db_context: str | None = None,
    max_candidates: int = 8,
) -> str:
    """묶음 프롬프트에 이번 경기 값을 채운다. 값은 지어내지 않고 비면 그대로 표시한다."""
    if group not in GROUPS:
        raise ValueError(f"unknown discovery group: {group!r}")
    template = load_prompt(group)
    replacements = {
        "fixture_id": str(fixture.fixture_id),
        "league_id": str(fixture.league_id),
        "league": league or "리그 미확인",
        "season": str(fixture.season),
        "home_team": home_team,
        "away_team": away_team,
        "home_team_id": str(fixture.home_team_id),
        "away_team_id": str(fixture.away_team_id),
        "kickoff_at": kickoff_label or fixture.kickoff_at.isoformat(),
        "today": today,
        "max_candidates": str(max_candidates),
        "db_context": db_context or "DB 자료 없음",
    }
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace("${" + key + "}", value)
    return prompt


# --------------------------------------------------------------------------
# 조사 실행
# --------------------------------------------------------------------------


def _sent_attempts(model_result: ExecuteRequestResult, transport: ProviderTransport) -> int:
    """실제로 전송된 시도 수. 기록 transport·모의·저장응답 재생은 0이다."""
    from app.preview.provider import sent_attempt_count

    try:
        return int(sent_attempt_count(model_result, getattr(transport, "mode", RunMode.MOCK)))
    except Exception:  # noqa: BLE001 - 계측 실패를 전송으로 세지 않는다
        return 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def discover_candidates(
    *,
    group: str,
    fixture: FixtureIdentity,
    context: ExecutionContext,
    transport: ProviderTransport,
    budget: RunBudget,
    home_team: str,
    away_team: str,
    today: str | None = None,
    league: str | None = None,
    db_context: str | None = None,
    max_candidates: int = 8,
    session: Any | None = None,
    module_execution_id: Any | None = None,
    sleeper: Callable[[float], None] | None = None,
    rng: Callable[[], float] | None = None,
    now: Callable[[], datetime] | None = None,
) -> DiscoveryResult:
    """조사 묶음 하나를 실행해 URL 후보를 얻는다.

    모델 호출은 `provider.request_model` 1회다(예산·기록 공유). 검색 도구는 넣지 않는다.
    실패하면 후보 목록이 아니라 실패 상태를 돌려준다.
    """
    if group not in GROUPS:
        raise ValueError(f"unknown discovery group: {group!r}")

    # `now`는 시각이거나 시각을 돌려주는 함수다. 호출자가 실행 기준 시각을 고정할 때
    # 둘 다 자연스럽게 넘길 수 있어야 한다(수집 모듈과 같은 규약).
    moment = now() if callable(now) else (now or _now())
    prompt_text = build_prompt(
        group,
        fixture=fixture,
        home_team=home_team,
        away_team=away_team,
        today=today or moment.date().isoformat(),
        league=league,
        db_context=db_context,
        max_candidates=max_candidates,
    )

    result = request_model(
        logical_call_id=LOGICAL_CALL_IDS[group],
        contents=[{"role": "user", "parts": [{"text": prompt_text}]}],
        context=context,
        transport=transport,
        budget=budget,
        session=session,
        module_id=MODULE_IDS[group],
        operation=f"discover_{group}",
        prompt_version=PROMPT_VERSIONS[group],
        # 조사 A/B는 DB 문맥 **+ Vertex 검색 도구**를 쓴다(설계 §두 묶음 조사 2항).
        # 도구는 조사에만 있고, 작성 3회·최종 전망 요청에는 넣지 않는다(설계 5항).
        generation_config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
            # 조사 A/B만 검색 도구를 쓴다(설계 §두 묶음 조사 2항·3항). 이 도구가 없으면
            # 모델은 실제 URL을 찾지 못해 후보를 비우고, 그 결과 수집 본문 0건 →
            # 필수 섹션 미작성이 된다(실제 유료 실행에서 관측된 결함).
            # 작성(작성 3회)·최종 전망 요청에는 이 도구를 넣지 않는다(설계 5항).
            "tools": [{"google_search": {}}],
        },
        module_execution_id=module_execution_id,
        sleeper=sleeper or provider_sleep_seconds,
        rng=rng,
        now=lambda: moment,
        # 잘린 JSON·해석 불가 조사 응답은 **같은 모듈의 남은 횟수 안에서** 다시 보낸다.
        # 조사 응답이 JSON이 아니면 쓸 후보를 얻을 수 없으므로 재전송 가치가 있다.
        content_check=_discovery_content_check(group),
    )

    sent = _sent_attempts(result, transport)
    response = getattr(result, "response", None)
    identity = {
        "provider": getattr(transport, "provider", None),
        "model": getattr(transport, "model", None),
        "sent_attempts": sent,
        "response_artifact_id": getattr(response, "raw_artifact_id", None),
        "finished_at": getattr(response, "received_at", None),
    }

    # 검색 도구가 **실제로 돌려준** 자료를 응답 원문에서 읽는다. 이 값은 후보 URL 파싱이
    # 실패해도 남긴다: 원문 수집이 실패해도 검색 내용을 버리지 않는다(사용자 확정 기준).
    findings, finding_notes = extract_search_findings(
        getattr(result, "raw_response", None),
        group=group,
        captured_at=getattr(response, "received_at", None),
        response_artifact_id=getattr(response, "raw_artifact_id", None),
    )

    if not result.ok or not result.text:
        reason = result.stopped_reason or "model_call_failed"
        return DiscoveryResult(
            group=group,
            status=STATUS_FAILED,
            prompt_version=PROMPT_VERSIONS[group],
            diagnostics=(f"조사 모델 호출이 성공하지 않았습니다: {reason}",),
            search_findings=tuple(findings),
            search_notes=tuple(finding_notes),
            model_result=result,
            **identity,
        )

    try:
        parsed = parse_candidates(result.text, group=group)
    except DiscoveryParseError as exc:
        # 후보 URL 해석이 실패해도 검색이 실제로 돌려준 자료는 버리지 않는다.
        return DiscoveryResult(
            group=group,
            status=STATUS_FAILED,
            prompt_version=PROMPT_VERSIONS[group],
            diagnostics=(str(exc),),
            search_findings=tuple(findings),
            search_notes=tuple(finding_notes),
            model_result=result,
            **identity,
        )

    status = STATUS_COMPLETED if parsed.candidates else STATUS_NO_MATERIAL
    diagnostics: list[str] = []
    if parsed.dropped:
        diagnostics.append(f"후보 {len(parsed.dropped)}건을 정규화 단계에서 제외했습니다.")
    if status == STATUS_NO_MATERIAL:
        diagnostics.append("조사 응답에 쓸 수 있는 후보 URL이 없습니다.")
    # 조사 요약 → material_type=search_ai_summary. 검색을 실제로 사용한 응답에서 모델이
    # 주제별로 정리한 요약이며, 기사 원문 발췌도 검색 도구가 직접 반환한 스니펫도 아니다.
    # 라벨로 그 사실을 밝히고 작성 입력에 쓴다(사용자 확정: 요약 활용).
    # 검색 도구가 실제로 반환한 주소(grounding_chunks). 있으면 요약의 인용 주소를 이
    # 집합과 대조해 "도구가 반환한 주소"인지 "모델이 제시한 주소"인지 구분한다.
    # 대조는 **표시 구분**일 뿐이며, 일치하지 않는다고 요약을 버리지 않는다.
    tool_hosts = {
        str(web.get("domain") or "").strip().lower()
        for web in _chunk_rows(
            _grounding_metadata_for(getattr(result, "raw_response", None)) or {}
        )
        if str(web.get("domain") or "").strip()
    }

    def _provenance(urls: list[str]) -> str:
        if not urls:
            return "none"
        first = str(urls[0])
        host = ""
        try:
            from urllib.parse import urlparse

            host = (urlparse(first).hostname or "").lower()
        except ValueError:
            host = ""
        bare = host[4:] if host.startswith("www.") else host
        if host and any(h == host or h == bare or bare.endswith("." + h) for h in tool_hosts):
            return "grounding_chunk"
        return "model_provided"

    summary_findings = [
        {
            "finding_id": str(item["summary_id"]),
            "discovery_group": group,
            "material_type": "search_ai_summary",
            "title": f"조사 요약 · {item['topic']}",
            "url": (item["sources"] or [None])[0],
            "domain": None,
            "content": str(item["text"]),
            "captured_at": identity["finished_at"],
            "response_artifact_id": identity["response_artifact_id"],
            "note": (
                "검색 도구를 사용한 조사 응답에서 모델이 정리한 요약입니다."
                " 기사 원문 발췌나 검색 도구가 직접 반환한 스니펫이 아닙니다."
                + ("" if item["sources"] else " 이 항목에는 근거 주소가 없습니다.")
            ),
            "sources": list(item["sources"]),
            "unverified": bool(item.get("unverified")),
            "url_provenance": _provenance(list(item["sources"])),
        }
        for item in parsed.research_summary
    ]
    # 모델이 쓴 페이지 설명은 후보 `note`에 이미 있고, 검색 요약문과 구분된다.
    model_notes = [
        {
            "finding_id": f"{group}-note-{index}",
            "discovery_group": group,
            "material_type": "model_note",
            "title": candidate.title,
            "url": candidate.requested_url,
            "domain": None,
            "content": candidate.note,
            "captured_at": identity["finished_at"],
            "response_artifact_id": identity["response_artifact_id"],
            "note": "조사 응답에서 모델이 쓴 페이지 설명입니다. 검색 요약문이 아닙니다.",
        }
        for index, candidate in enumerate(parsed.candidates, start=1)
        if candidate.note
    ]

    return DiscoveryResult(
        group=parsed.group,
        status=status,
        candidates=parsed.candidates,
        dropped=parsed.dropped,
        search_note=parsed.search_note,
        prompt_version=parsed.prompt_version,
        diagnostics=tuple(diagnostics),
        dropped_count=len(parsed.dropped),
        research_summary=parsed.research_summary,
        search_findings=tuple(summary_findings) + tuple(findings) + tuple(model_notes),
        search_notes=tuple(
            finding_notes
            + (
                [f"검색 조사 요약 {len(summary_findings)}건을 작성 자료로 남겼습니다."]
                if summary_findings
                else []
            )
        ),
        model_result=result,
        **identity,
    )
