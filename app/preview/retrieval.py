"""공통 수집기(retrieval) — 후보 URL을 실제 본문으로 바꾼다 (PS-02).

설계 §"두 묶음 조사와 작성 연결"3~5와 계획 PS-02를 담당한다.

경계:

1. **모델을 부르지 않는다.** 이 모듈은 `provider`를 import하지 않는다. 수집이 작성을
   실행하면 예산·승인 단위가 섞이기 때문이다(계획 공통 계약). 모델 전송은 0회다.
2. **전송은 공통 예산(RunBudget)으로 센다.** 리다이렉트 홉과 직접 JSON/API 조회도 실제
   전송이다. 상한에 닿으면 요청을 보내기 전에 멈춘다. 실패한 전송도 사용량이다.
3. **private/loopback 대상은 거부한다.** 시작 URL뿐 아니라 리다이렉트 경로의 매 홉을
   검사한다. 요청은 예산을 차감하기 전에 거부한다.
4. **한 번만 가져온다.** 정규화 URL과 본문 해시 두 축으로 중복을 제거한다.
5. **브라우저·프록시·CAPTCHA 우회를 쓰지 않는다.** 차단·JS 셸·빈 본문은 실패로 기록하고
   다른 출처로 넘어간다. 자동 브라우저 전환은 없다.
6. **기사 추출이 비면 목록·표 텍스트로 폴백한다.** 두 경로 모두 없으면 실패다. 실패한
   출처를 "본문 0자 출처"로 성공처럼 세지 않는다.
7. **배당은 결정적이다.** 공개 표의 명시적인 정규시간 1X2 소수점만 옮긴다. 값이 없거나
   구조를 모르면 `available=False`와 사유를 남긴다. AI로 숫자를 만들지 않는다.

전송 구현은 주입한다(`http=`). 기본 구현은 Scrapling 일반 HTTP이고, 없으면 표준
라이브러리로 폴백한다. 테스트는 가짜 http를 넣어 네트워크를 열지 않는다.
"""

from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urljoin, urlparse

from app.preview.contracts import FixtureIdentity, RequestClass
from app.preview.discovery import Candidate, normalize_candidate_url
from app.preview.information_bundle import (
    ODDS_MARKET_REGULATION_1X2,
    BundleSource,
    InformationBundle,
    NetworkUsage,
    OddsMarket,
    OddsQuote,
    Passage,
    canonical_discovery_group,
    new_bundle_id,
    search_findings_from_groups,
)
from app.preview.retry import BudgetExceeded, RunBudget

__all__ = [
    "ARTICLE_MAX_CHARS_PER_PASSAGE",
    "HTTP_CONCURRENCY",
    "HTTP_TIMEOUT_SECONDS",
    "MAX_PASSAGES_PER_SOURCE",
    "MODEL_CALLS_MADE_BY_COLLECTION",
    "MAX_WEB_CHARS",
    "BlockedTarget",
    "CollectionResult",
    "CollectedSource",
    "HttpFetch",
    "OddsObservation",
    "ScraplingHttpClient",
    "StandardHttpClient",
    "collect_information_bundle",
    "extract_article_text",
    "is_public_http_url",
    "parse_odds_table",
]

# --- 상한 (설계 §실행 예산) -------------------------------------------------

MAX_PASSAGES_PER_SOURCE = 3
ARTICLE_MAX_CHARS_PER_PASSAGE = 1500
MAX_WEB_CHARS = 16000
MAX_SOURCES_PER_BUNDLE = 6
HTTP_TIMEOUT_SECONDS = 30
HTTP_CONCURRENCY = 2
MAX_REDIRECT_HOPS = 5
# 수집은 모델을 부르지 않는다. 계약 확인용 상수이며 값은 항상 0이다.
MODEL_CALLS_MADE_BY_COLLECTION = 0
# 이 상한을 넘는 본문은 읽지 않는다(메모리·처리시간 경계).
MAX_BODY_BYTES = 4_000_000
# 본문으로 인정하는 최소 길이. 이보다 짧으면 "본문 확보"로 세지 않는다.
MIN_USABLE_TEXT_CHARS = 200
# 기사 추출이 이보다 짧고, 전체 텍스트가 그 3배 이상 길면 목록·표 폴백을 쓴다.
# 값은 저장된 실제 캡처의 관측 비율(기사형 0.44~0.82, 목록·표형 0.05~0.08)에서 정했다.
ARTICLE_FALLBACK_MAX_CHARS = 500
ARTICLE_FALLBACK_RATIO = 3

BLOCKED_NETWORKS = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)

# 사설/루프백으로 확인 없이 판정할 수 있는 호스트 이름.
BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"}
)


class BlockedTarget(Exception):
    """공개 수집 대상이 아니다(private/loopback/잘못된 스킴). 요청 전에 거부한다."""


# --------------------------------------------------------------------------
# 전송 경계
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpFetch:
    """HTTP 응답의 최소 표현. 요청/최종 URL과 리다이렉트 홉을 구분해 남긴다."""

    requested_url: str
    final_url: str
    status_code: int | None
    body_text: str
    redirects: tuple[str, ...] = ()
    content_type: str = "text/html"
    error: str | None = None
    body_bytes: int | None = None

    @property
    def ok(self) -> bool:
        return (
            self.error is None
            and self.status_code is not None
            and 200 <= self.status_code < 300
            and bool(self.body_text)
        )

    @property
    def hop_count(self) -> int:
        """실제로 보낸 전송 수. 시작 URL 1회 + 리다이렉트 홉 수."""
        return max(1, len(self.redirects))


class HttpClient(Protocol):
    """HTTP 하나를 가져오는 최소 계약. 테스트는 가짜 구현을 주입한다.

    `on_hop`은 **전송 직전에 매 홉마다** 호출되는 게이트다. 예산 계층이 여기에 연결되어
    실제 전송 전에 차감/거부한다. 게이트를 지원하지 않는 클라이언트는 `supports_hop_gate`
    가 False이며, 그 경우 호출자는 예약 방식으로 상한을 지킨다.
    """

    supports_hop_gate: bool

    def fetch(
        self,
        url: str,
        *,
        timeout_seconds: int,
        on_hop: Callable[[str], bool] | None = None,
    ) -> HttpFetch: ...


def _resolves_to_public(hostname: str) -> bool:
    """호스트가 공개 주소로만 풀리는지 확인한다. 확인 실패는 거부다.

    수집 대상은 공개 페이지만이다. DNS 확인이 실패하면 그 주소로 요청하지 않는다
    (프록시·사내망으로 흘러갈 수 있는 경로를 만들지 않는다).
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    if not infos:
        return False
    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        if any(parsed in network for network in BLOCKED_NETWORKS):
            return False
        if parsed.is_loopback or parsed.is_link_local or parsed.is_reserved:
            return False
    return True


def is_public_http_url(url: str, *, resolve_dns: bool = True) -> bool:
    """수집해도 되는 공개 http(s) URL인지 판정한다.

    `resolve_dns=False`는 호스트 이름만 볼 때 쓴다(리다이렉트 경로 검사에서 DNS를
    반복 조회하지 않도록 호출자가 선택한다).
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").strip()
    if not host:
        return False
    if host.lower() in BLOCKED_HOSTNAMES:
        return False

    # IP 리터럴은 DNS 없이 판정한다.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if any(literal in network for network in BLOCKED_NETWORKS):
            return False
        return not (literal.is_loopback or literal.is_reserved or literal.is_link_local)

    if not resolve_dns:
        return True
    return _resolves_to_public(host)


class StandardHttpClient:
    """표준 라이브러리 기반 HTTP.

    제품 기본 경로는 Scrapling 일반 HTTP(`ScraplingHttpClient`)이고, 이 구현은
    Scrapling이 설치되지 않은 환경이나 테스트용 폴백이다. 브라우저를 쓰지 않으며,
    리다이렉트는 직접 따라가며 매 홉을 검사한다(자동 추종 금지).
    """

    def __init__(self, *, user_agent: str | None = None) -> None:
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
        )

    # `urlopen`은 리다이렉트를 **자동으로 따라간다**. 그러면 실제 전송 수를 셀 수 없어
    # 예산 상한이 새므로, 자동 추종을 끄고 이 루프가 직접 홉을 넘긴다(검토 F7).
    supports_hop_gate = True

    def fetch(
        self,
        url: str,
        *,
        timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
        on_hop: Callable[[str], bool] | None = None,
    ) -> HttpFetch:
        from urllib import error as urlerror
        from urllib import request as urlrequest

        hops: list[str] = [url]
        current = url
        for _ in range(MAX_REDIRECT_HOPS + 1):
            # **전송 직전**에 게이트를 부른다. 거부되면 그 홉은 나가지 않는다.
            if on_hop is not None and not on_hop(current):
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error="budget_exhausted",
                )
            if not is_public_http_url(current):
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error="blocked_target",
                )
            request = urlrequest.Request(
                current,
                headers={"User-Agent": self.user_agent, "Accept": "text/html,*/*"},
                method="GET",
            )
            try:
                with _no_redirect_opener().open(
                    request, timeout=timeout_seconds
                ) as response:
                    status = int(getattr(response, "status", 0) or 0)
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location") or response.headers.get(
                            "Location"
                        )
                        if location:
                            nxt = urljoin(current, str(location))
                            hops.append(nxt)
                            current = nxt
                            continue
                    raw = response.read(MAX_BODY_BYTES)
                    charset = response.headers.get_content_charset() or "utf-8"
                    return HttpFetch(
                        requested_url=url,
                        final_url=response.geturl(),
                        status_code=response.status,
                        body_text=raw.decode(charset, errors="replace"),
                        redirects=tuple(hops),
                        content_type=response.headers.get_content_type() or "text/html",
                        body_bytes=len(raw),
                    )
            except urlerror.HTTPError as exc:
                # `_no_redirect_opener`는 3xx에서 추종하지 않고 `redirect_request`가
                # `None`을 돌려준다. 그 결과 표준 라이브러리는 **3xx를 HTTPError로**
                # 올린다. 여기서 분기하지 않으면 301/302/307/308이 "수집 본문 없음"으로
                # 잘못 분류되어 실제 리다이렉트를 따라가지 못한다(실제 3xx 경로 수정).
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location") or exc.headers.get("location")
                    exc.close()
                    if location:
                        nxt = urljoin(current, str(location))
                        # 같은 홉을 다시 세지 않도록 이미 방문한 URL이면 중단한다.
                        if nxt not in hops:
                            hops.append(nxt)
                            current = nxt
                            continue
                        return HttpFetch(
                            requested_url=url,
                            final_url=current,
                            status_code=exc.code,
                            body_text="",
                            redirects=tuple(hops),
                            error="redirect_loop",
                        )
                    return HttpFetch(
                        requested_url=url,
                        final_url=current,
                        status_code=exc.code,
                        body_text="",
                        redirects=tuple(hops),
                        error="redirect_without_location",
                    )
                body = b""
                try:
                    body = exc.read(MAX_BODY_BYTES)
                except Exception:  # noqa: BLE001 - 오류 본문 없음
                    body = b""
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=exc.code,
                    body_text=body.decode("utf-8", errors="replace"),
                    redirects=tuple(hops),
                    error=None,
                )
            except (urlerror.URLError, TimeoutError, OSError) as exc:
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error=f"{type(exc).__name__}: {exc}",
                )
        return HttpFetch(
            requested_url=url,
            final_url=current,
            status_code=None,
            body_text="",
            redirects=tuple(hops),
            error="too_many_redirects",
        )


class ScraplingHttpClient:
    """Scrapling 일반 HTTP(브라우저 아님).

    `scrapling[fetchers]`의 `Fetcher`를 쓰되 **브라우저 렌더를 쓰지 않는다.** 리다이렉트는
    직접 따라가며 매 홉을 검사한다(자동 추종·사설망 도달 금지). 라이브러리가 없으면
    `available()`가 False이고 호출자가 표준 라이브러리로 폴백한다.
    """

    # 리다이렉트를 직접 다루기 위해 자동 추종을 끈다.
    def __init__(self, *, impersonate: str = "chrome", user_agent: str | None = None) -> None:
        self._impersonate = impersonate
        self._user_agent = user_agent

    @staticmethod
    def available() -> bool:
        try:
            from scrapling.fetchers import Fetcher  # noqa: PLC0415,F401 - 선택 의존성
        except Exception:  # noqa: BLE001 - 미설치
            return False
        return True

    supports_hop_gate = True

    def fetch(
        self,
        url: str,
        *,
        timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
        on_hop: Callable[[str], bool] | None = None,
    ) -> HttpFetch:
        from scrapling.fetchers import Fetcher  # noqa: PLC0415

        hops: list[str] = [url]
        current = url
        for _ in range(MAX_REDIRECT_HOPS + 1):
            # **전송 직전** 게이트. 거부되면 이 홉은 나가지 않는다.
            if on_hop is not None and not on_hop(current):
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error="budget_exhausted",
                )
            if not is_public_http_url(current):
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error="blocked_target",
                )
            try:
                response = Fetcher.get(
                    current,
                    timeout=timeout_seconds,
                    follow_redirects=False,
                    stealthy_headers=True,
                    impersonate=self._impersonate,
                    retries=0,  # 재시도는 공통 예산 계층이 소유한다(숨은 재시도 금지).
                )
            except Exception as exc:  # noqa: BLE001 - 전송 실패는 실패로 기록한다
                return HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error=f"{type(exc).__name__}: {exc}",
                )

            status = int(getattr(response, "status", 0) or 0)
            body = getattr(response, "body", b"") or b""
            if isinstance(body, bytes):
                html = body.decode("utf-8", errors="replace")
            else:
                html = str(body)
            headers = getattr(response, "headers", {}) or {}
            location = headers.get("location") or headers.get("Location")
            if status in (301, 302, 303, 307, 308) and location:
                nxt = urljoin(current, str(location))
                hops.append(nxt)
                current = nxt
                continue
            return HttpFetch(
                requested_url=url,
                final_url=current,
                status_code=status or None,
                body_text=html,
                redirects=tuple(hops),
                content_type=str(headers.get("content-type", "text/html")),
                body_bytes=len(body) if isinstance(body, bytes) else None,
            )
        return HttpFetch(
            requested_url=url,
            final_url=current,
            status_code=None,
            body_text="",
            redirects=tuple(hops),
            error="too_many_redirects",
        )


def _no_redirect_opener():
    """리다이렉트를 **따라가지 않는** opener. 각 홉을 우리가 세고 넘긴다."""
    global _NO_REDIRECT_OPENER
    if _NO_REDIRECT_OPENER is None:
        from urllib import request as urlrequest

        class _NoRedirect(urlrequest.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
                # None을 돌려주면 추종하지 않고 원래 응답(3xx)을 그대로 준다.
                return None

        _NO_REDIRECT_OPENER = urlrequest.build_opener(_NoRedirect)
    return _NO_REDIRECT_OPENER


_NO_REDIRECT_OPENER = None


def default_http_client() -> HttpClient:
    """기본 전송기. Scrapling 일반 HTTP가 있으면 그것을, 없으면 표준 라이브러리를 쓴다."""
    if ScraplingHttpClient.available():
        try:
            return ScraplingHttpClient()
        except Exception:  # noqa: BLE001 - 초기화 실패는 폴백 사유다
            pass
    return StandardHttpClient()


# --------------------------------------------------------------------------
# 텍스트 추출
# --------------------------------------------------------------------------


_NOISE_TAGS = ("script", "style", "noscript", "nav", "footer", "aside", "form", "svg")


def _strip_noise(html: str) -> str:
    text = re.sub(r"(?is)<!--.*?-->", " ", html)
    for tag in _NOISE_TAGS:
        text = re.sub(rf"(?is)<{tag}\b.*?</{tag}>", " ", text)
    return text


def _html_to_text(html: str) -> str:
    """표준 라이브러리 HTML 파서 폴백. 블록 경계를 줄바꿈으로 남긴다."""
    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.chunks: list[str] = []
            self._skip = 0

        def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
            if tag in _NOISE_TAGS:
                self._skip += 1
            elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "td", "th"):
                self.chunks.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if tag in _NOISE_TAGS and self._skip:
                self._skip -= 1
            elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
                self.chunks.append("\n")

        def handle_data(self, data: str) -> None:
            if self._skip:
                return
            self.chunks.append(data)

    collector = _Collector()
    collector.feed(html)
    raw = "".join(collector.chunks)
    lines = [re.sub(r"[ \t\u00a0]+", " ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)


def _trafilatura_text(html: str, *, url: str | None) -> str | None:
    try:
        import trafilatura  # noqa: PLC0415 - 선택 의존성
    except Exception:  # noqa: BLE001 - 미설치 환경
        return None
    try:
        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            include_links=False,
            favor_precision=False,
        )
    except Exception:  # noqa: BLE001 - 추출기 내부 오류는 폴백 사유다
        return None
    return extracted.strip() if extracted and extracted.strip() else None


def _scrapling_text(html: str) -> str | None:
    """Scrapling 파서의 전체 텍스트 경로(브라우저 렌더 없음)."""
    try:
        from scrapling.parser import Adaptor  # noqa: PLC0415 - 선택 의존성
    except Exception:  # noqa: BLE001 - 미설치 환경
        return None
    try:
        adaptor = Adaptor(html)
        text = adaptor.get_all_text(separator="\n", strip=True)
    except Exception:  # noqa: BLE001
        return None
    cleaned = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    return cleaned or None


@dataclass(frozen=True)
class Extracted:
    """추출 결과와 그 방법. `method`는 `article` 또는 `list_text`다."""

    text: str
    method: str
    extractor: str


def _text_fallback(html: str) -> tuple[str, str] | None:
    """기사 추출이 부실할 때 쓰는 전체 텍스트 경로. (텍스트, 추출기 이름)을 돌려준다."""
    for extractor, producer in (
        ("scrapling_text", lambda: _scrapling_text(html)),
        ("stdlib_text", lambda: _html_to_text(_strip_noise(html))),
    ):
        text = producer()
        if text and text.strip():
            return text, extractor
    return None


def extract_article_text(html: str, *, url: str | None = None) -> Extracted | None:
    """기사 본문을 뽑는다. 기사 추출이 부실하면 목록·표 텍스트로 폴백한다.

    폴백 조건은 **관측된 손실**이다(측정 근거: `tests/preview/fixtures/ps02`와 저장된
    실제 캡처). 기사형 페이지에서는 기사 추출이 전체 텍스트의 0.44~0.82를 남겼지만,
    스쿼드 명단 페이지에서는 0.08(163자/2,096자), 배당 목록 페이지에서는 0.05
    (225자/4,483자)만 남겼다. 즉 "기사 추출 결과가 매우 짧고 텍스트 경로가 훨씬 길다"가
    목록·표 내용을 버린 신호다.

    규칙: 기사 추출이 `ARTICLE_FALLBACK_MAX_CHARS` 미만이고, 텍스트 경로가 그보다
    `ARTICLE_FALLBACK_RATIO`배 이상 길면 텍스트 경로를 `list_text`로 채택한다.
    애매하면 기사 추출을 그대로 쓴다(추측으로 바꾸지 않는다).
    """
    if not html or not html.strip():
        return None

    article = _trafilatura_text(html, url=url)
    fallback = _text_fallback(html)

    if article:
        if fallback is not None:
            fallback_text, fallback_extractor = fallback
            long_enough_fallback = len(fallback_text) >= len(article) * ARTICLE_FALLBACK_RATIO
            article_too_short = len(article) < ARTICLE_FALLBACK_MAX_CHARS
            if article_too_short and long_enough_fallback:
                return Extracted(
                    text=fallback_text,
                    method="list_text",
                    extractor=fallback_extractor,
                )
        return Extracted(text=article, method="article", extractor="trafilatura")

    if fallback is None:
        return None
    text, extractor = fallback
    method = "article" if _looks_like_prose(text) else "list_text"
    return Extracted(text=text, method=method, extractor=extractor)


def _looks_like_prose(text: str) -> bool:
    """문단형 텍스트인지 대략 판정한다. 새 사실 판정이 아니라 폴백 라벨용 휴리스틱이다."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    long_lines = sum(1 for line in lines if len(line) >= 120)
    return long_lines >= 2 and len(text) >= 400


# --------------------------------------------------------------------------
# 출처와 묶음
# --------------------------------------------------------------------------


@dataclass
class CollectedSource:
    """수집한(또는 실패한) 출처 하나. 실패도 같은 목록에 사유와 함께 남는다."""

    source_id: str
    requested_url: str
    final_url: str | None
    method: str
    collected_at: datetime
    http_status: int | None = None
    title: str | None = None
    kind: str = "other"
    extraction: str | None = None
    extractor: str | None = None
    text: str | None = None
    body_sha256: str | None = None
    html_sha256: str | None = None
    passages: tuple[Passage, ...] = ()
    failure: str | None = None
    failure_detail: str | None = None
    candidate_id: str | None = None
    search_group: str | None = None
    redirects: tuple[str, ...] = ()
    # 실패한 출처도 리다이렉트 홉 수를 남긴다(URL 목록이 없을 때 사용).
    redirect_count: int = 0

    @property
    def redirect_hops(self) -> int:
        return max(len(self.redirects), self.redirect_count)

    @property
    def usable(self) -> bool:
        return bool(self.text) and self.failure is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "candidate_id": self.candidate_id,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "method": self.method,
            "collected_at": self.collected_at.isoformat(),
            "http_status": self.http_status,
            "title": self.title,
            "kind": self.kind,
            "extraction": self.extraction,
            "extractor": self.extractor,
            "text_chars": len(self.text or ""),
            "body_sha256": self.body_sha256,
            "html_sha256": self.html_sha256,
            "passages": [passage.to_dict() for passage in self.passages],
            "failure": self.failure,
            "failure_detail": self.failure_detail,
            "search_group": self.search_group,
            "redirects": list(self.redirects),
            "redirect_count": self.redirect_hops,
            # 본문 전문은 여기 넣지 않는다. 저장 단계가 아티팩트로 남긴다.
        }


@dataclass(frozen=True)
class SourceBody:
    """수집한 전문. 저장(아티팩트)은 A가 하므로 여기서는 넘겨주기만 한다.

    `BundleSource`에는 본문 텍스트가 없다(계약: 전문은 `body_artifact_id`가 가리키는
    아티팩트에 있다). 그래서 본문이 필요한 호출자(A의 저장 단계)에게 이 값으로 건넨다.
    """

    source_id: str
    requested_url: str | None
    final_url: str | None
    text: str
    body_sha256: str
    extractor: str | None
    extraction: str | None
    html_sha256: str | None
    captured_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "body_chars": len(self.text),
            "body_sha256": self.body_sha256,
            "extractor": self.extractor,
            "extraction": self.extraction,
            "html_sha256": self.html_sha256,
            "captured_at": self.captured_at.isoformat(),
        }


@dataclass
class CollectionOutput:
    """수집 한 번의 결론.

    `bundle`이 A가 저장·검사하는 계약(`InformationBundle`)이다. 나머지 필드는 이 함수를
    부른 쪽이 저장·진단에 쓰는 보조값이며, 계약 이름(`InformationBundle`/`BundleSource`/
    `Passage`/`OddsQuote`/`OddsMarket`/`NetworkUsage`)을 다시 쓰지 않는다.
    """

    bundle: InformationBundle
    bodies: tuple[SourceBody, ...] = ()
    odds: "OddsObservation | None" = None
    diagnostics: tuple[dict[str, Any], ...] = ()
    network_usage: dict[str, Any] = field(default_factory=dict)
    budget_snapshot: dict[str, Any] = field(default_factory=dict)

    @property
    def sources(self) -> tuple[BundleSource, ...]:
        return self.bundle.sources

    def usable_sources(self) -> tuple[BundleSource, ...]:
        return self.bundle.usable_sources

    def delivered_web_chars(self) -> int:
        return sum(
            len(passage.text)
            for source in self.bundle.sources
            for passage in source.passages
        )

    def body_for(self, source_id: str) -> SourceBody | None:
        return next((body for body in self.bodies if body.source_id == source_id), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle": self.bundle.to_dict(),
            "bodies": [body.to_dict() for body in self.bodies],
            "odds": self.odds.to_dict() if self.odds else None,
            "diagnostics": [dict(item) for item in self.diagnostics],
            "network_usage": dict(self.network_usage),
            "budget": dict(self.budget_snapshot),
        }


# --------------------------------------------------------------------------
# 실패 분류
# --------------------------------------------------------------------------

_BLOCK_MARKERS = (
    "just a moment",
    "enable javascript and cookies",
    "cloudflare",
    "attention required",
    "access denied",
    "captcha",
    "cf-browser-verification",
)


def _classify_failure(fetch: HttpFetch) -> tuple[str, str | None]:
    """응답을 실패 사유로 분류한다. 성공은 여기로 오지 않는다."""
    if fetch.error == "blocked_target":
        return "redirect_blocked", "리다이렉트가 private/loopback 대상으로 향했습니다."
    if fetch.error == "too_many_redirects":
        return "too_many_redirects", f"리다이렉트가 {MAX_REDIRECT_HOPS}회를 넘었습니다."
    if fetch.error:
        return "fetch_error", fetch.error
    status = fetch.status_code
    if status in (401, 403, 429):
        return f"blocked_{status}", f"HTTP {status}로 차단되었습니다."
    if status is not None and 400 <= status < 500:
        return f"http_{status}", f"HTTP {status}"
    if status is not None and status >= 500:
        return f"http_{status}", f"HTTP {status}"
    body = (fetch.body_text or "").strip()
    if not body:
        return "empty_body", "응답 본문이 비어 있습니다."
    lowered = body.lower()
    if any(marker in lowered for marker in _BLOCK_MARKERS):
        return "blocked_challenge", "차단/챌린지 페이지로 보입니다."
    return "no_content", None


def _looks_like_js_shell(html: str, text: str | None = None) -> bool:
    """정적 HTML에 렌더 결과가 없는 JS 셸인지 본다.

    근거는 마커뿐이다(추정으로 실패 처리하지 않는다). 브라우저로 자동 전환하지 않고
    실패로 기록한 뒤 다른 출처로 넘어간다.
    """
    lowered = (html or "").lower()
    markers = (
        "serverrendered\":2",
        "prerenderedat",
        'id="__nuxt"',
        "id='__nuxt'",
        "id=\"app\"",
        "<app-root",
    )
    if not any(marker in lowered for marker in markers):
        return False
    # 마커가 있어도 본문이 충분히 있으면 셸이 아니다.
    return not (text and len(text.strip()) >= MIN_USABLE_TEXT_CHARS)


# --------------------------------------------------------------------------
# 구간 선택
# --------------------------------------------------------------------------


def _split_passages(source_id: str, text: str) -> tuple[Passage, ...]:
    """본문에서 **전달 후보** 구간을 고른다. 문단 경계를 우선하고 1500자에서 자른다.

    `Passage`는 A의 계약 타입이다. `ordinal`은 1부터 시작하며 같은 출처 안에서 유일하다.
    """
    paragraphs: list[tuple[int, str]] = []
    cursor = 0
    for chunk in re.split(r"\n{1,}", text):
        stripped = chunk.strip()
        if stripped:
            offset = text.find(stripped, cursor)
            if offset < 0:
                offset = cursor
            paragraphs.append((offset, stripped))
            cursor = offset + len(stripped)

    passages: list[Passage] = []
    for _offset, paragraph in paragraphs:
        if len(passages) >= MAX_PASSAGES_PER_SOURCE:
            break
        # 너무 짧은 줄(내비게이션 잔여)은 앞 구간으로 쓰지 않는다.
        if len(paragraph) < 40 and passages:
            continue
        window = paragraph[:ARTICLE_MAX_CHARS_PER_PASSAGE]
        passage = Passage(
            passage_id=f"{source_id}-p{len(passages) + 1}",
            source_id=source_id,
            ordinal=len(passages) + 1,
            text=window,
            char_count=len(window),
        )
        passages.append(passage)
    return tuple(passages)


def _trim_to_total_limit(
    sources: list[CollectedSource], *, limit: int = MAX_WEB_CHARS
) -> list[CollectedSource]:
    """웹 전달 총량 상한을 넘지 않게 뒤쪽 출처의 구간을 줄이거나 떼어낸다."""
    budget_left = limit
    for source in sources:
        kept: list[Passage] = []
        for passage in source.passages:
            if budget_left <= 0:
                break
            if len(passage.text) <= budget_left:
                kept.append(passage)
                budget_left -= len(passage.text)
            else:
                truncated = passage.text[:budget_left]
                kept.append(
                    Passage(
                        passage_id=passage.passage_id,
                        source_id=passage.source_id,
                        ordinal=passage.ordinal,
                        text=truncated,
                        char_count=len(truncated),
                    )
                )
                budget_left = 0
        source.passages = tuple(kept)
    return sources


# --------------------------------------------------------------------------
# 계약 변환 도우미
# --------------------------------------------------------------------------

# 자료 성격 라벨. 수집 단계가 정하고, 기사↔DB 교차 검증으로 바꾸지 않는다.
_NATURE_BY_CANDIDATE_KIND = {
    "preview": "preview",
    "article": "news",
    "list": "squad",
    "stats": "stats",
    "profile": "profile",
    "odds": "odds",
    "other": "unknown",
}

# 수집 방법 라벨(A 계약 값). 텍스트 폴백으로 얻은 본문은 `text_fallback`이다.
_METHOD_LIST_TEXT = "text_fallback"


def _collection_method(extracted: "Extracted") -> str:
    """본문을 어떤 경로로 얻었는지 A 계약 값으로 표기한다.

    목록·표 폴백으로 얻은 본문은 `text_fallback`이다. 기사 추출이면 수집 자체가
    HTTP였으므로 `fresh_http`이고, 어떤 추출기를 썼는지는 `extractor`에 따로 남는다.
    """
    if extracted.method == "list_text":
        return _METHOD_LIST_TEXT
    return "fresh_http"


def _extraction_dependency_problem() -> str | None:
    """필수 추출기(trafilatura)가 없으면 사유를 돌려준다.

    stdlib 경로만으로 제품 검증을 통과했다고 말하지 않기 위해, 수집 실행에 이 사유를
    남긴다. 설치 여부는 import 한 번으로만 확인한다(네트워크 없음).
    """
    try:
        import trafilatura  # noqa: PLC0415,F401 - 설치 확인
    except Exception:  # noqa: BLE001 - 미설치
        return (
            "trafilatura가 설치되지 않아 기사 본문 추출을 표준 라이브러리 폴백으로만"
            " 수행했습니다. 이 결과를 제품 본문 추출 검증으로 인용하지 않습니다."
        )
    return None


def _failed_source(
    *,
    source_id: str,
    candidate: Candidate,
    group: str,
    fetched_at: datetime,
    failure: str,
    detail: str | None = None,
    final_url: str | None = None,
    http_status: int | None = None,
    redirects: int = 0,
    html_sha256: str | None = None,
) -> CollectedSource:
    """실패한 후보 하나. `passages`는 비우고 사유를 남긴다(실패를 성공처럼 세지 않는다)."""
    return CollectedSource(
        source_id=source_id,
        requested_url=candidate.requested_url,
        final_url=final_url,
        method="fresh_http",
        collected_at=fetched_at,
        http_status=http_status,
        kind=candidate.kind,
        title=candidate.title,
        html_sha256=html_sha256,
        candidate_id=candidate.candidate_id,
        search_group=group,
        redirect_count=redirects,
        failure=failure,
        failure_detail=detail,
    )


def _to_bundle_source(source: CollectedSource, *, group_fallback: str | None) -> BundleSource:
    """내부 수집 기록을 A의 `BundleSource`로 옮긴다. 본문 텍스트는 넣지 않는다."""
    group = canonical_discovery_group(source.search_group or group_fallback or "")
    redirect_count = source.redirect_hops or None
    notes: list[str] = []
    if source.extraction:
        notes.append(f"extraction={source.extraction}")
    if source.failure_detail:
        notes.append(source.failure_detail)
    if source.kind:
        notes.append(f"candidate_kind={source.kind}")
    return BundleSource(
        source_id=source.source_id,
        discovery_group=group,
        requested_url=source.requested_url or None,
        final_url=source.final_url,
        nature=(
            "unavailable"
            if source.failure
            else _NATURE_BY_CANDIDATE_KIND.get(source.kind or "other", "unknown")
        ),
        method=source.method,
        title=source.title,
        captured_at=source.collected_at,
        http_status=source.http_status,
        redirects=redirect_count,
        extractor=source.extractor,
        body_chars=len(source.text) if source.text else None,
        body_sha256=source.body_sha256,
        passages=source.passages,
        failure=source.failure,
        notes=tuple(notes),
    )


def _to_odds_market(
    odds: "OddsObservation | None",
    *,
    sources: Sequence[CollectedSource],
    moment: datetime,
) -> OddsMarket | None:
    """내부 배당 관측을 A의 `OddsMarket`으로 옮긴다. 불완전 줄은 채택하지 않는다."""
    if odds is None:
        return None
    if not odds.available or odds.home is None or odds.draw is None or odds.away is None:
        return OddsMarket(
            quotes=(),
            collected_at=moment,
            diagnostics=(odds.note or odds.reason or "배당 값을 확인하지 못했습니다.",),
            unsupported_sites=(),
        )
    source_id = next(
        (
            source.source_id
            for source in sources
            if source.final_url
            and odds.source_url
            and source.final_url.rstrip("/") == odds.source_url.rstrip("/")
        ),
        odds.source_url or "odds-unknown",
    )
    quote = OddsQuote(
        source_id=source_id,
        site=odds.bookmaker or "unknown",
        market=ODDS_MARKET_REGULATION_1X2,
        observed_at=odds.observed_at or moment,
        home_decimal=odds.home,
        draw_decimal=odds.draw,
        away_decimal=odds.away,
        note=odds.note,
    )
    return OddsMarket(
        quotes=(quote,),
        collected_at=moment,
        diagnostics=() if quote.complete else ("정규시간 1X2 값이 완전하지 않아 채택하지 않았습니다.",),
        unsupported_sites=(),
    )


def _diagnostic_sentence(item: Mapping[str, Any]) -> str:
    """진단 dict를 관리자 화면 문장으로. 누락 문구를 독자 본문에 넣지 않는다."""
    reason = str(item.get("reason") or "unknown")
    url = item.get("url") or item.get("duplicate_of")
    detail = item.get("detail")
    parts = [reason]
    if url:
        parts.append(str(url))
    if detail:
        parts.append(str(detail))
    return " · ".join(parts)


# --------------------------------------------------------------------------
# 수집 실행
# --------------------------------------------------------------------------


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_now(value: datetime | Callable[[], datetime] | None) -> datetime:
    """시각 인자는 값과 함수 둘 다 받는다. 둘 다 UTC 기준이다."""
    if value is None:
        return _now()
    if callable(value):
        return value()
    return value


def _title_from_html(html: str) -> str | None:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return None
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    return title or None


def collect_information_bundle(
    *,
    candidates: Sequence[Candidate],
    fixture: FixtureIdentity,
    budget: RunBudget,
    http: HttpClient | None = None,
    now: datetime | Callable[[], datetime] | None = None,
    max_sources: int = MAX_SOURCES_PER_BUNDLE,
    include_odds: bool = True,
    home_team_names: Sequence[str] = (),
    away_team_names: Sequence[str] = (),
    target_checker: Callable[[str], bool] | None = None,
    team_id_space: str = "internal",
    db_snapshot: Any | None = None,
    discovery_groups: Sequence[Any] = (),
    bundle_id: str | None = None,
    mode: str = "live",
    build_note: str | None = None,
) -> InformationBundle:
    """후보 URL을 실제 본문으로 바꿔 `InformationBundle`을 만든다 (계약 반환형).

    모델을 부르지 않는다. 예산·중복·대상 검사·추출 폴백·실패 기록을 이 함수 하나가
    책임진다. 실패한 후보도 `BundleSource(failure=..., passages=())`로 남으므로 "자료
    없음"과 "가져오지 못함"이 구분된다. 전문은 이 묶음에 넣지 않는다(A가 아티팩트로
    저장). 전문이 필요한 호출자는 `collect_with_bodies()`를 쓴다.
    """
    output = collect_with_bodies(
        candidates=candidates,
        fixture=fixture,
        budget=budget,
        http=http,
        now=now,
        max_sources=max_sources,
        include_odds=include_odds,
        home_team_names=home_team_names,
        away_team_names=away_team_names,
        target_checker=target_checker,
        team_id_space=team_id_space,
        db_snapshot=db_snapshot,
        discovery_groups=discovery_groups,
        bundle_id=bundle_id,
        mode=mode,
        build_note=build_note,
    )
    return output.bundle


def collect_with_bodies(
    *,
    candidates: Sequence[Candidate],
    fixture: FixtureIdentity,
    budget: RunBudget,
    http: HttpClient | None = None,
    now: datetime | Callable[[], datetime] | None = None,
    max_sources: int = MAX_SOURCES_PER_BUNDLE,
    include_odds: bool = True,
    home_team_names: Sequence[str] = (),
    away_team_names: Sequence[str] = (),
    target_checker: Callable[[str], bool] | None = None,
    team_id_space: str = "internal",
    db_snapshot: Any | None = None,
    discovery_groups: Sequence[Any] = (),
    bundle_id: str | None = None,
    mode: str = "live",
    build_note: str | None = None,
) -> CollectionOutput:
    """묶음과 **수집 전문**을 함께 돌려준다. 저장(아티팩트)은 호출자(A)가 한다."""
    client = http or default_http_client()
    moment = _resolve_now(now)
    extraction_problem = _extraction_dependency_problem()

    # 기본은 실제 DNS까지 확인한다. 테스트는 합성 호스트를 쓰므로 검사기를 주입한다.
    def _public(url: str) -> bool:
        if target_checker is not None:
            return bool(target_checker(url))
        return is_public_http_url(url)

    sources: list[CollectedSource] = []
    bodies: list[SourceBody] = []
    diagnostics: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    seen_bodies: dict[str, str] = {}
    used_hops = 0
    failed_hops = 0
    redirect_hops = 0
    stopped = False

    if extraction_problem:
        # 필수 추출기가 없으면 그 사실을 먼저 남긴다. stdlib 경로만으로 제품 검증을
        # 통과했다고 말하지 않기 위한 표시다.
        diagnostics.append({"reason": "extraction_dependency_missing", "detail": extraction_problem})

    for candidate in candidates:
        if len([s for s in sources if s.usable]) >= max_sources:
            diagnostics.append(
                {"reason": "max_sources_reached", "limit": max_sources, "url": candidate.requested_url}
            )
            continue

        canonical = normalize_candidate_url(candidate.requested_url) or candidate.canonical_url
        if canonical in seen_urls:
            diagnostics.append(
                {"reason": "duplicate_url", "url": canonical, "candidate_id": candidate.candidate_id}
            )
            continue
        seen_urls.add(canonical)

        source_id = f"src-{len(sources) + 1}"
        group = canonical_discovery_group(candidate.search_group)

        if not _public(canonical):
            sources.append(
                _failed_source(
                    source_id=source_id,
                    candidate=candidate,
                    group=group,
                    fetched_at=moment,
                    failure="private_target",
                    detail="공개 http(s) 대상이 아니어서 요청하지 않았습니다.",
                )
            )
            diagnostics.append(
                {"reason": "private_target", "url": canonical, "candidate_id": candidate.candidate_id}
            )
            continue

        # 예산 확인: 최소 1홉이 남아야 보낸다. 상한이면 더 보내지 않는다(자동 재전송 없음).
        if budget.remaining(RequestClass.API.value) < 1:
            stopped = True
            diagnostics.append(
                {"reason": "budget_exhausted", "url": canonical, "candidate_id": candidate.candidate_id}
            )
            continue

        logical_call_id = f"fetch:{candidate.candidate_id}"
        # **매 홉 전에** 차감한다(검토 F7). 클라이언트가 홉 게이트를 지원하면 실제 전송
        # 직전에 이 게이트가 불리므로, 상한을 넘는 전송은 애초에 나가지 않는다.
        gate_denied = {"value": False}

        def _hop_gate(hop_url: str) -> bool:
            # 홉은 **사용량**으로만 제한한다(모델 논리 재시도 횟수와 분리, 검토 F7).
            allowed, reason = budget.charge_transport(
                RequestClass.API.value, now=moment
            )
            if not allowed:
                gate_denied["value"] = True
                diagnostics.append(
                    {
                        "reason": "budget_exhausted",
                        "url": hop_url,
                        "candidate_id": candidate.candidate_id,
                        "hop": "blocked_before_send",
                        "detail": reason,
                    }
                )
                return False
            nonlocal_used[0] += 1
            return True

        nonlocal_used = [0]
        supports_gate = bool(getattr(client, "supports_hop_gate", False))
        if not supports_gate:
            # 게이트를 지원하지 않는 클라이언트는 **전송 전에 상한 전체를 예약**하고, 실제
            # 홉 수를 알게 된 뒤 남은 몫을 반환한다. 예약을 넘는 홉이 보고되면 그 출처는
            # 채택하지 않는다(이미 나간 전송은 되돌릴 수 없으므로 사실대로 남긴다).
            reserve_now = budget.reserve_transports(
                1 + MAX_REDIRECT_HOPS, RequestClass.API.value
            )
            if reserve_now < 1:
                stopped = True
                diagnostics.append(
                    {
                        "reason": "budget_exhausted",
                        "url": canonical,
                        "candidate_id": candidate.candidate_id,
                    }
                )
                continue
        else:
            reserve_now = 0

        try:
            fetch = client.fetch(
                canonical,
                timeout_seconds=HTTP_TIMEOUT_SECONDS,
                **({"on_hop": _hop_gate} if supports_gate else {}),
            )
        except BudgetExceeded:
            if not supports_gate:
                budget.release_reserved(reserve_now, RequestClass.API.value)
            stopped = True
            diagnostics.append({"reason": "budget_exhausted", "url": canonical})
            continue
        except Exception:
            if not supports_gate:
                budget.release_reserved(reserve_now, RequestClass.API.value)
            raise

        actual_hops = max(1, int(getattr(fetch, "hop_count", 1) or 1))
        if supports_gate:
            used_hops += nonlocal_used[0]
            extra_hops = max(0, nonlocal_used[0] - 1)
            if extra_hops:
                redirect_hops += extra_hops
            if gate_denied["value"]:
                stopped = True
                failed_hops += 1
                sources.append(
                    _failed_source(
                        source_id=source_id,
                        candidate=candidate,
                        group=group,
                        fetched_at=moment,
                        failure="budget_exhausted",
                        detail=(
                            "다음 홉을 보내기 전에 API 예산이 소진되어 전송을 중단했습니다."
                        ),
                        final_url=fetch.final_url,
                        http_status=fetch.status_code,
                        redirects=max(0, nonlocal_used[0] - 1),
                    )
                )
                continue
        else:
            budget.release_reserved(
                max(0, reserve_now - actual_hops), RequestClass.API.value
            )
            used_hops += min(actual_hops, reserve_now)
            extra_hops = max(0, actual_hops - 1)
            if extra_hops:
                redirect_hops += extra_hops
            if actual_hops > reserve_now:
                # 게이트 없는 클라이언트가 예약보다 많이 전송했다. 사실대로 남기고 채택하지 않는다.
                failed_hops += 1
                diagnostics.append(
                    {
                        "reason": "redirect_over_budget",
                        "url": canonical,
                        "hops": actual_hops,
                        "reserved": reserve_now,
                    }
                )
                sources.append(
                    _failed_source(
                        source_id=source_id,
                        candidate=candidate,
                        group=group,
                        fetched_at=moment,
                        failure="redirect_over_budget",
                        detail=(
                            f"리다이렉트 홉 {actual_hops}회가 예산 예약({reserve_now}회)을"
                            " 넘어 이 출처를 채택하지 않았습니다."
                        ),
                        final_url=fetch.final_url,
                        http_status=fetch.status_code,
                        redirects=actual_hops - 1,
                    )
                )
                continue

        redirects = tuple(fetch.redirects or ())
        # 리다이렉트 경로의 매 홉을 다시 검사한다(도중에 private로 갈 수 있다).
        blocked_hop = next(
            (
                hop
                for hop in redirects
                if not (
                    target_checker(hop)
                    if target_checker is not None
                    else is_public_http_url(hop, resolve_dns=False)
                )
            ),
            None,
        )
        if blocked_hop is not None or fetch.error == "blocked_target":
            failed_hops += 1
            sources.append(
                _failed_source(
                    source_id=source_id,
                    candidate=candidate,
                    group=group,
                    fetched_at=moment,
                    failure="redirect_blocked",
                    detail=(
                        f"리다이렉트 홉 {blocked_hop}이 공개 대상이 아닙니다."
                        if blocked_hop
                        else "요청 대상이 공개 대상이 아닙니다."
                    ),
                    final_url=fetch.final_url,
                    http_status=fetch.status_code,
                    redirects=len(redirects),
                )
            )
            diagnostics.append(
                {"reason": "redirect_blocked", "url": canonical, "hop": blocked_hop}
            )
            continue

        html = fetch.body_text or ""
        if not fetch.ok:
            failed_hops += 1
            failure, detail = _classify_failure(fetch)
            extracted_preview = extract_article_text(html, url=fetch.final_url) if html else None
            preview_text = extracted_preview.text if extracted_preview else None
            if failure == "no_content" and _looks_like_js_shell(html, preview_text):
                failure, detail = "js_shell", "정적 HTML에 본문이 없고 JS 셸로 보입니다."
            sources.append(
                _failed_source(
                    source_id=source_id,
                    candidate=candidate,
                    group=group,
                    fetched_at=moment,
                    failure=failure,
                    detail=detail,
                    final_url=fetch.final_url,
                    http_status=fetch.status_code,
                    redirects=len(redirects),
                    html_sha256=_sha256(html) if html else None,
                )
            )
            diagnostics.append(
                {"reason": failure, "url": canonical, "http_status": fetch.status_code}
            )
            continue

        extracted = extract_article_text(html, url=fetch.final_url)
        if extracted is None or len(extracted.text.strip()) < MIN_USABLE_TEXT_CHARS:
            failed_hops += 1
            # 너무 짧은 추출은 본문 확보로 세지 않는다. JS 셸 마커가 있으면 그 사유,
            # 없으면 빈 본문/부족이다. 어느 쪽도 성공으로 꾸미지 않는다.
            if _looks_like_js_shell(html, extracted.text if extracted else None):
                failure, detail = "js_shell", "정적 HTML에 본문이 없고 JS 셸로 보입니다."
            elif extracted is None or not extracted.text.strip():
                failure, detail = "empty_body", "본문 추출 결과가 비어 있습니다."
            else:
                failure = "insufficient_text"
                detail = (
                    f"추출 본문이 {len(extracted.text.strip())}자로 최소"
                    f" {MIN_USABLE_TEXT_CHARS}자에 미달합니다."
                )
            sources.append(
                _failed_source(
                    source_id=source_id,
                    candidate=candidate,
                    group=group,
                    fetched_at=moment,
                    failure=failure,
                    detail=detail,
                    final_url=fetch.final_url,
                    http_status=fetch.status_code,
                    redirects=len(redirects),
                    html_sha256=_sha256(html) if html else None,
                )
            )
            diagnostics.append({"reason": failure, "url": canonical})
            continue

        body_hash = _sha256(extracted.text)
        if body_hash in seen_bodies:
            diagnostics.append(
                {
                    "reason": "duplicate_body",
                    "url": canonical,
                    "duplicate_of": seen_bodies[body_hash],
                }
            )
            continue
        seen_bodies[body_hash] = canonical

        passages = _split_passages(source_id, extracted.text)
        sources.append(
            CollectedSource(
                source_id=source_id,
                requested_url=candidate.requested_url,
                final_url=fetch.final_url,
                method=_collection_method(extracted),
                collected_at=moment,
                http_status=fetch.status_code,
                kind=candidate.kind,
                title=candidate.title or _title_from_html(html),
                extraction=extracted.method,
                extractor=extracted.extractor,
                text=extracted.text,
                body_sha256=body_hash,
                html_sha256=_sha256(html),
                passages=passages,
                candidate_id=candidate.candidate_id,
                search_group=group,
                redirects=redirects,
                redirect_count=len(redirects),
            )
        )
        bodies.append(
            SourceBody(
                source_id=source_id,
                requested_url=candidate.requested_url,
                final_url=fetch.final_url,
                text=extracted.text,
                body_sha256=body_hash,
                extractor=extracted.extractor,
                extraction=extracted.method,
                html_sha256=_sha256(html),
                captured_at=moment,
            )
        )

    sources = _trim_to_total_limit(sources)

    odds: OddsObservation | None = None
    if include_odds:
        odds = _collect_odds(
            sources=sources,
            home_team_names=home_team_names,
            away_team_names=away_team_names,
            diagnostics=diagnostics,
        )

    if not any(source.usable for source in sources) and not stopped:
        diagnostics.append({"reason": "no_usable_sources"})

    network_usage = NetworkUsage(
        http_used=used_hops,
        http_failed=failed_hops,
        redirects=redirect_hops,
        api_used=0,
        http_limit=budget.limits.api_requests,
        note=(
            "비모델 HTTP 상한을 수집이 공유한다. 리다이렉트와 실패도 전송으로 센다."
            " 이 함수는 모델을 호출하지 않는다."
        ),
    )

    bundle = InformationBundle(
        bundle_id=bundle_id or new_bundle_id(),
        fixture=fixture.to_dict(),
        team_id_space=team_id_space,
        collected_at=moment,
        sources=tuple(_to_bundle_source(source, group_fallback=source.search_group) for source in sources),
        db_snapshot=db_snapshot,
        discovery_groups=tuple(discovery_groups),
        # 조사 그룹이 실제로 확보한 검색 자료(검색 기반 AI 요약 포함)를 묶음 최상위로 접는다.
        # 이 줄이 없으면 요약이 `discovery_groups` 안에만 남고 작성 입력에는 0줄이 전달되어,
        # 본문 0·메타 0인 실행에서 "자료 없음"으로 끝난다(SF-02 차단 1).
        search_findings=search_findings_from_groups(tuple(discovery_groups)),
        odds=_to_odds_market(odds, sources=sources, moment=moment),
        diagnostics=tuple(_diagnostic_sentence(item) for item in diagnostics),
        network_usage=network_usage,
        mode=mode,
        as_of=moment,
        build_note=build_note or (
            "브라우저 없는 HTTP 수집. 기사↔DB 교차 검증 없음, grounding chunks 필수 아님."
        ),
    )

    return CollectionOutput(
        bundle=bundle,
        bodies=tuple(bodies),
        odds=odds,
        diagnostics=tuple(diagnostics),
        network_usage={
            "used": used_hops,
            "failed": failed_hops,
            "redirects": redirect_hops,
            "limit": budget.limits.api_requests,
            "remaining": budget.remaining(RequestClass.API.value),
            "counted": "redirect hops, failures and direct fetches",
        },
        budget_snapshot=budget.snapshot(),
    )


# --------------------------------------------------------------------------
# 배당 (결정적)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class OddsObservation:
    """공개 표에서 읽은 정규시간 1X2 배당. 값이 없으면 `available=False`다."""

    available: bool
    source_url: str | None = None
    bookmaker: str | None = None
    market: str | None = None
    observed_at: datetime | None = None
    home: float | None = None
    draw: float | None = None
    away: float | None = None
    reason: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "source_url": self.source_url,
            "bookmaker": self.bookmaker,
            "market": self.market,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "home": self.home,
            "draw": self.draw,
            "away": self.away,
            "reason": self.reason,
            "note": self.note,
        }


# football-data.co.uk 형식: 업체 접두 + H/D/A. 정규시간 1X2만 해당한다.
_ODDS_TRIPLE = re.compile(r"^(?P<book>[A-Za-z][A-Za-z0-9_.]*)(?P<leg>[HDA])$")
_ODDS_BOOK_LABELS = {
    "B365": "Bet365",
    "PS": "Pinnacle",
    "BW": "Bet&Win",
    "IW": "Interwetten",
    "WH": "William Hill",
    "VC": "VC Bet",
    "BF": "Betfair",
    "PSCH": "Pinnacle (closing)",
}
# 라이브·핸디캡·언더오버 등 1X2가 아닌 열은 채택하지 않는다.
_NON_1X2_TOKENS = ("AH", "OU", "O/U", "BTS", "LIVE", "HT", "FT", "EX", "HANDICAP")


def _to_decimal(value: str) -> float | None:
    """소수점 배당만 인정한다. 확률·정수·범위 밖 값은 `None`이다."""
    text = (value or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    # 정규시간 1X2 소수 배당의 통상 범위. 범위 밖은 형식이 다른 열로 본다.
    if not (1.01 <= number <= 100.0):
        return None
    return number


def _normalize_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_odds_table(
    text: str,
    *,
    source_url: str,
    home_team: str,
    away_team: str,
    observed_at: datetime,
) -> OddsObservation:
    """공개 CSV/표에서 이 경기의 정규시간 1X2 소수 배당을 읽는다.

    모르는 구조는 `available=False`다. 값을 추정하거나 다른 시장으로 대체하지 않는다.
    """
    if not text or not text.strip():
        return OddsObservation(
            available=False, source_url=source_url, reason="empty_table",
            note="배당 표 본문이 비어 있습니다.",
        )

    try:
        rows = list(csv.DictReader(io.StringIO(text.strip())))
        fieldnames = rows[0].keys() if rows else []
    except csv.Error:
        return OddsObservation(
            available=False, source_url=source_url, reason="unreadable_table",
            note="CSV로 해석하지 못했습니다.",
        )
    if not rows:
        return OddsObservation(
            available=False, source_url=source_url, reason="empty_table",
            note="표에 경기 행이 없습니다.",
        )

    columns = [str(name or "").strip() for name in fieldnames]
    home_key = next((name for name in ("HomeTeam", "Home", "home_team") if name in columns), None)
    away_key = next((name for name in ("AwayTeam", "Away", "away_team") if name in columns), None)
    if not home_key or not away_key:
        return OddsObservation(
            available=False, source_url=source_url, reason="unknown_table_structure",
            note="홈/원정 팀 열을 찾지 못했습니다.",
        )

    wanted_home = _normalize_team(home_team)
    wanted_away = _normalize_team(away_team)
    target = None
    for row in rows:
        if _normalize_team(str(row.get(home_key) or "")) == wanted_home and (
            _normalize_team(str(row.get(away_key) or "")) == wanted_away
        ):
            target = row
            break
    if target is None:
        return OddsObservation(
            available=False, source_url=source_url, reason="fixture_not_in_table",
            note="이 경기 행이 표에 없습니다.",
        )

    # 업체별 H/D/A 세 열을 찾는다. 1X2가 아닌 열은 제외한다.
    books: dict[str, dict[str, str]] = {}
    for name in columns:
        upper = name.upper()
        if any(token in upper for token in _NON_1X2_TOKENS):
            continue
        match = _ODDS_TRIPLE.match(name)
        if not match:
            continue
        books.setdefault(match.group("book"), {})[match.group("leg")] = name

    preferred = ["B365", "PS", "BW", "WH", "VC", "BF", "PSCH"]
    ordered = [book for book in preferred if book in books] + [
        book for book in books if book not in preferred
    ]
    for book in ordered:
        legs = books[book]
        if not {"H", "D", "A"} <= set(legs):
            continue
        home = _to_decimal(str(target.get(legs["H"]) or ""))
        draw = _to_decimal(str(target.get(legs["D"]) or ""))
        away = _to_decimal(str(target.get(legs["A"]) or ""))
        if home is None or draw is None or away is None:
            continue
        return OddsObservation(
            available=True,
            source_url=source_url,
            bookmaker=_ODDS_BOOK_LABELS.get(book, book),
            market="1X2",
            observed_at=observed_at,
            home=home,
            draw=draw,
            away=away,
            note="공개 표의 정규시간 1X2 소수 배당을 그대로 옮겼습니다.",
        )

    return OddsObservation(
        available=False, source_url=source_url, reason="no_decimal_1x2_columns",
        note="이 경기 행에 완전한 정규시간 1X2 소수 배당 열이 없습니다.",
    )


def _collect_odds(
    *,
    sources: Sequence[CollectedSource],
    home_team_names: Sequence[str],
    away_team_names: Sequence[str],
    diagnostics: list[dict[str, Any]],
) -> OddsObservation | None:
    """이미 수집한 출처 중 배당 표로 읽을 수 있는 것만 결정적으로 정규화한다.

    새 요청을 보내지 않는다(수집 HTTP 예산을 배당 때문에 추가로 쓰지 않는다).
    값을 못 읽으면 `available=False`와 사유를 남긴다. 숫자를 만들어 채우지 않는다.
    """
    if not home_team_names or not away_team_names:
        return OddsObservation(
            available=False,
            reason="team_names_required",
            note="팀 이름이 없어 배당 표에서 이 경기 행을 찾지 못합니다.",
        )

    candidates = [source for source in sources if source.usable and source.text]
    reasons: list[str] = []
    for source in candidates:
        for home_name in home_team_names:
            for away_name in away_team_names:
                observation = parse_odds_table(
                    source.text or "",
                    source_url=source.final_url or source.requested_url,
                    home_team=home_name,
                    away_team=away_name,
                    observed_at=source.collected_at,
                )
                if observation.available:
                    return observation
                if observation.reason:
                    reasons.append(f"{source.source_id}:{observation.reason}")

    diagnostics.append(
        {
            "reason": "odds_not_available",
            "detail": (
                "수집한 공개 자료에서 정규시간 1X2 배당을 읽지 못했습니다."
                + (f" (사유: {', '.join(dict.fromkeys(reasons))})" if reasons else "")
            ),
        }
    )
    return OddsObservation(
        available=False,
        reason="no_accessible_public_odds_source",
        note="접근 가능한 공개 배당 표에서 이 경기의 1X2 값을 확인하지 못했습니다.",
    )
