"""PS-02 공통 수집(retrieval) 검사.

계획 PS-02와 설계 §수집의 **직접 수용 동작**만 본다.

1. 같은 URL은 한 번만 가져온다(정규화·중복 제거, 본문 해시 중복도 한 번만 남긴다).
2. 리다이렉트·직접 요청도 실제 전송으로 세고, 상한에 닿으면 더 보내지 않는다.
3. private/loopback 대상과 그쪽으로 향하는 리다이렉트는 거부한다.
4. 기사 추출이 비면 목록·표 텍스트로 폴백하고, 그래도 비면 실패로 남긴다.
5. 구간은 출처당 3개·구간당 1500자·웹 총 16000자 상한 안에서만 전달된다.
6. 배당은 공개 표의 명시적인 정규시간 1X2 소수점만 옮기고, 값이 없으면 만들지 않는다.
7. 수집 함수는 모델을 부르지 않는다.

네트워크는 열지 않는다. 아래 가짜 fetcher가 이 파일의 고정 캡처만 돌려준다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.preview import retrieval

from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    OperationKind,
    RunMode,
)
from app.preview.retry import BudgetLimits, BudgetExceeded, RunBudget

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ps02"
FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# 가짜 네트워크
# --------------------------------------------------------------------------


class FakeHttp:
    """고정 캡처를 돌려주는 가짜 HTTP 경계.

    실제 소켓을 열지 않는다. `responses`는 요청 URL -> (상태, 본문, 최종 URL,
    리다이렉트 경로) 매핑이며, 호출 순서를 그대로 기록한다.
    """

    def __init__(self, responses: Mapping[str, Mapping[str, object]]) -> None:
        self._responses = dict(responses)
        self.requests: list[str] = []

    def fetch(self, url: str, *, timeout_seconds: int) -> Any:  # noqa: ANN401
        from app.preview.retrieval import HttpFetch

        self.requests.append(url)
        scripted = self._responses.get(url)
        if scripted is None:
            return HttpFetch(
                requested_url=url,
                final_url=url,
                status_code=404,
                body_text="",
                redirects=(),
                error="not_scripted",
            )
        return HttpFetch(
            requested_url=url,
            final_url=str(scripted.get("final_url", url)),
            status_code=int(scripted.get("status", 200)),
            body_text=str(scripted.get("body", "")),
            redirects=tuple(scripted.get("redirects", ())),
            content_type=str(scripted.get("content_type", "text/html")),
        )


def _fixture() -> FixtureIdentity:
    return FixtureIdentity(
        fixture_id=1557474,
        league_id=39,
        season=2026,
        home_team_id=13,
        away_team_id=4,
        kickoff_at=datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc),
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=RunMode.MOCK,
        actor_id=1,
        config_version="ps02-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _budget(api_requests: int = 24) -> RunBudget:
    return RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=api_requests, attempts_per_call=3),
        now=FIXED_NOW,
    )


def _candidates(*urls: str, kind: str = "article"):
    from app.preview.discovery import Candidate

    return tuple(
        Candidate(
            candidate_id=f"c{index}",
            requested_url=url,
            canonical_url=url,
            title=None,
            kind=kind,
            note=None,
            search_group="people",
        )
        for index, url in enumerate(urls, start=1)
    )


def _read(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _collect(candidates, *, http: FakeHttp, budget: RunBudget | None = None, **kwargs):
    from app.preview import retrieval

    return retrieval.collect_with_bodies(
        candidates=candidates,
        fixture=_fixture(),
        budget=budget or _budget(),
        http=http,
        now=FIXED_NOW,
        # 합성 호스트는 DNS가 없으므로 호스트 이름 검사만 한다. IP 리터럴·스킴·localhost
        # 판정은 그대로 실제 검사기를 쓴다(private 대상 거부 검사가 우회되지 않는다).
        target_checker=lambda url: retrieval.is_public_http_url(url, resolve_dns=False),
        **kwargs,
    )


# --------------------------------------------------------------------------
# 1. 한 번만 가져오기 / 중복
# --------------------------------------------------------------------------


def test_same_url_fetched_once_even_with_tracking_variants():
    """추적 파라미터만 다른 같은 문서는 한 번만 가져온다."""
    article = _read("article.html")
    http = FakeHttp(
        {
            "https://www.example-sports.test/city-fulham-preview": {
                "status": 200,
                "body": article,
            }
        }
    )
    result = _collect(
        _candidates(
            "https://www.example-sports.test/city-fulham-preview",
            "https://www.example-sports.test/city-fulham-preview?utm_source=chat",
        ),
        http=http,
    )

    assert http.requests == ["https://www.example-sports.test/city-fulham-preview"]
    assert len(result.sources) == 1
    # 전문은 BundleSource에 없고(계약), 저장 단계로 넘기는 bodies에 있다.
    body = result.body_for(result.sources[0].source_id)
    assert body is not None and body.text
    assert result.sources[0].passages, "전달 후보 구간이 있어야 한다"


def test_identical_body_from_different_urls_kept_once():
    """서로 다른 URL이 완전히 같은 본문을 주면 한 출처만 남고 나머지는 중복으로 기록된다."""
    article = _read("article.html")
    http = FakeHttp(
        {
            "https://a.example.test/story": {"status": 200, "body": article},
            "https://b.example.test/story": {"status": 200, "body": article},
        }
    )
    result = _collect(
        _candidates("https://a.example.test/story", "https://b.example.test/story"),
        http=http,
    )

    assert len(result.bodies) == 1
    assert any(item["reason"] == "duplicate_body" for item in result.diagnostics)


# --------------------------------------------------------------------------
# 2. 전송 예산
# --------------------------------------------------------------------------


def test_budget_charge_counts_redirect_hops_and_stops_at_ceiling():
    """리다이렉트도 실제 전송으로 세고, 상한에 닿으면 호출 전에 멈춘다."""
    budget = _budget(api_requests=2)
    article = _read("article.html")
    http = FakeHttp(
        {
            "https://first.example.test/a": {
                "status": 200,
                "body": article,
                "final_url": "https://first.example.test/a",
                "redirects": (
                    "https://first.example.test/a",
                    "https://second.example.test/b",
                ),
            },
            "https://third.example.test/c": {"status": 200, "body": article},
        }
    )
    result = _collect(
        _candidates("https://first.example.test/a", "https://third.example.test/c"),
        http=http,
        budget=budget,
    )

    # 첫 후보가 리다이렉트 2홉 = 2회를 써서 예산이 소진됐다.
    assert budget.api_used == 2
    assert http.requests == ["https://first.example.test/a"]
    assert any(item["reason"] == "budget_exhausted" for item in result.diagnostics)
    assert result.network_usage["used"] == 2


def test_budget_never_exceeds_ceiling_and_reports_usage():
    budget = _budget(api_requests=1)
    article = _read("article.html")
    http = FakeHttp(
        {
            "https://one.example.test/x": {"status": 200, "body": article},
            "https://two.example.test/y": {"status": 200, "body": article},
        }
    )
    _collect(
        _candidates("https://one.example.test/x", "https://two.example.test/y"),
        http=http,
        budget=budget,
    )
    assert budget.api_used == 1


# --------------------------------------------------------------------------
# 3. private / loopback / redirect 대상
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "http://localhost/internal",
        "http://192.168.0.10/panel",
        "http://10.0.0.5/router",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/v6",
    ],
)
def test_private_and_loopback_targets_are_refused_without_fetching(url: str):
    http = FakeHttp({})
    result = _collect(_candidates(url), http=http)

    assert http.requests == [], "private 대상으로는 요청을 보내지 않는다"
    # 시도조차 하지 않았고, 그 후보는 실패 사유와 함께 진단에 남는다.
    assert result.usable_sources() == ()
    assert any(item["reason"] == "private_target" for item in result.diagnostics)


def test_redirect_to_private_target_is_refused_after_starting_public():
    """공개 URL로 시작해도 리다이렉트가 private로 가면 그 지점에서 멈춘다."""
    http = FakeHttp(
        {
            "https://public.example.test/start": {
                "status": 200,
                "body": "should not be used",
                "final_url": "http://127.0.0.1/admin",
                "redirects": ("https://public.example.test/start", "http://127.0.0.1/admin"),
            }
        }
    )
    result = _collect(_candidates("https://public.example.test/start"), http=http)

    assert result.sources[0].failure == "redirect_blocked"
    assert result.sources[0].passages == ()
    assert result.sources[0].usable is False


# --------------------------------------------------------------------------
# 4. 추출 폴백과 실패 구분
# --------------------------------------------------------------------------


def test_article_extraction_primary_and_list_page_falls_back_to_text():
    """기사형은 기사 추출, 목록·표형은 텍스트 폴백으로 명단을 보존한다."""
    http = FakeHttp(
        {
            "https://www.example-sports.test/article": {
                "status": 200,
                "body": _read("article.html"),
            },
            "https://www.example-sports.test/squad": {
                "status": 200,
                "body": _read("squad_list.html"),
            },
        }
    )
    result = _collect(
        _candidates(
            "https://www.example-sports.test/article",
            "https://www.example-sports.test/squad",
        ),
        http=http,
    )

    by_url = {source.requested_url: source for source in result.sources}
    article = by_url["https://www.example-sports.test/article"]
    squad = by_url["https://www.example-sports.test/squad"]

    article_body = result.body_for(article.source_id)
    squad_body = result.body_for(squad.source_id)
    assert article_body and "fifth successive home victory" in article_body.text
    # 기사 본문에서 내비게이션 잡음이 본문 앞에 붙지 않는다.
    assert not article_body.text.lstrip().startswith("Home")
    assert article_body.extraction == "article"
    assert article.method == "fresh_http"
    # 명단 페이지는 표 내용이 살아 있어야 한다(조용한 대량 손실 금지).
    assert squad_body and "Erling Haaland" in squad_body.text
    assert squad_body.extraction in {"article", "list_text"}
    # 목록 폴백으로 얻은 본문만 계약상 text_fallback이고, 기사 추출은 fresh_http다.
    assert (article.method == "text_fallback") is (article_body.extraction == "list_text")
    assert (squad.method == "text_fallback") is (squad_body.extraction == "list_text")


def test_blocked_and_js_shell_pages_recorded_as_failures_not_empty_sources():
    http = FakeHttp(
        {
            "https://blocked.example.test/p": {
                "status": 403,
                "body": _read("blocked_403.html"),
            },
            "https://shell.example.test/p": {"status": 200, "body": _read("js_shell.html")},
        }
    )
    result = _collect(
        _candidates("https://blocked.example.test/p", "https://shell.example.test/p"),
        http=http,
    )

    failures = {source.requested_url: source.failure for source in result.sources}
    assert failures["https://blocked.example.test/p"] == "blocked_403"
    assert failures["https://shell.example.test/p"] == "js_shell"
    assert result.bodies == ()
    assert all(source.passages == () for source in result.sources)
    assert all(source.nature == "unavailable" for source in result.sources)
    # 실패한 출처를 "본문 0자짜리 출처"로 세지 않는다.
    assert result.usable_sources() == ()


def test_extraction_library_absence_does_not_crash_collection():
    """추출기가 없어도 stdlib 폴백으로 동작하고, 어떤 추출기를 썼는지 남긴다."""
    http = FakeHttp(
        {"https://www.example-sports.test/article": {"status": 200, "body": _read("article.html")}}
    )
    result = _collect(_candidates("https://www.example-sports.test/article"), http=http)

    source = result.sources[0]
    body = result.body_for(source.source_id)
    assert body is not None and body.text
    assert body.extraction in {"article", "list_text"}
    assert body.extractor in {"trafilatura", "stdlib_text", "scrapling_text"}
    # 어떤 추출기를 썼는지 계약 출처에도 남는다.
    assert source.extractor in {"trafilatura", "stdlib_text", "scrapling_text"}
    assert source.body_sha256 and source.body_chars


# --------------------------------------------------------------------------
# 5. 구간 상한
# --------------------------------------------------------------------------


def test_passages_respect_per_source_and_total_limits():
    long_paragraph = "City pressed high and Fulham defended deep. " * 200  # ~9,000자
    html = (
        "<html><body><article><h1>Preview</h1>"
        f"<p>{long_paragraph}</p><p>{long_paragraph}</p><p>{long_paragraph}</p>"
        f"<p>{long_paragraph}</p><p>{long_paragraph}</p><p>{long_paragraph}</p>"
        f"<p>{long_paragraph}</p>"
        "</article></body></html>"
    )
    urls = [f"https://many{i}.example.test/p" for i in range(6)]
    http = FakeHttp({url: {"status": 200, "body": html + f"<!--{i}-->"} for i, url in enumerate(urls)})

    result = _collect(_candidates(*urls), http=http)

    for source in result.sources:
        assert len(source.passages) <= 3
        for passage in source.passages:
            assert len(passage.text) <= 1500

    delivered = result.delivered_web_chars()
    assert delivered <= 16000


# --------------------------------------------------------------------------
# 6. 배당 (결정적, AI 없음)
# --------------------------------------------------------------------------


def test_odds_parser_reads_only_explicit_regulation_1x2_decimal_values():
    from app.preview import retrieval

    text = _read("odds_fixtures.csv")
    table = retrieval.parse_odds_table(
        text,
        source_url="https://www.football-data.co.uk/fixtures.csv",
        home_team="Man City",
        away_team="Fulham",
        observed_at=FIXED_NOW,
    )

    assert table.available is True
    assert table.bookmaker, "어느 열에서 읽었는지 남긴다"
    assert table.home and table.draw and table.away
    assert (table.home, table.draw, table.away) == (1.55, 4.20, 5.50)
    assert table.market == "1X2"
    assert table.observed_at == FIXED_NOW


def test_odds_parser_returns_honest_missing_instead_of_guessing():
    from app.preview import retrieval

    text = _read("odds_fixtures.csv")
    # 이 표에 없는 경기를 요청하면 값을 만들지 않는다.
    table = retrieval.parse_odds_table(
        text,
        source_url="https://www.football-data.co.uk/fixtures.csv",
        home_team="Liverpool",
        away_team="Chelsea",
        observed_at=FIXED_NOW,
    )
    assert table.available is False
    assert table.reason == "fixture_not_in_table"
    assert (table.home, table.draw, table.away) == (None, None, None)


def test_odds_parser_ignores_rows_without_complete_1x2_values():
    from app.preview import retrieval

    text = _read("odds_fixtures.csv")
    table = retrieval.parse_odds_table(
        text,
        source_url="https://www.football-data.co.uk/fixtures.csv",
        home_team="Brighton",
        away_team="Brentford",
        observed_at=FIXED_NOW,
    )
    assert table.available is False
    assert table.reason == "no_decimal_1x2_columns"


# --------------------------------------------------------------------------
# 7. 수집은 모델을 부르지 않는다
# --------------------------------------------------------------------------


def test_collection_does_not_import_or_call_the_model_provider():
    """수집 경계가 모델 작성까지 실행하지 않는다(계획 공통 계약)."""
    from app.preview import retrieval

    assert retrieval.MODEL_CALLS_MADE_BY_COLLECTION == 0


# --------------------------------------------------------------------------
# A의 묶음 계약 (InformationBundle) 연결
# --------------------------------------------------------------------------


def test_bundle_conforms_to_manifest_contract_and_keeps_internal_odds_analysis():
    """수집 반환은 A의 `InformationBundle`이며 계약 검증을 통과한다."""
    from app.preview.information_bundle import (
        BundleSource,
        InformationBundle,
        Passage,
        adopted_odds_quotes,
        ensure_valid_bundle,
        validate_information_bundle,
    )

    csv_body = _read("odds_fixtures.csv")
    http = FakeHttp(
        {
            "https://a.example.test/p": {"status": 200, "body": _read("article.html")},
            "https://a.example.test/odds": {"status": 200, "body": csv_body},
            "https://a.example.test/blocked": {"status": 403, "body": _read("blocked_403.html")},
        }
    )
    result = _collect(
        _candidates(
            "https://a.example.test/p",
            "https://a.example.test/odds",
            "https://a.example.test/blocked",
        ),
        http=http,
        home_team_names=("Man City",),
        away_team_names=("Fulham",),
    )

    bundle = result.bundle
    assert isinstance(bundle, InformationBundle)
    assert all(isinstance(source, BundleSource) for source in bundle.sources)
    # 전문은 묶음에 없다(계약: 아티팩트가 가리킨다). 대신 bodies로 넘긴다.
    assert not hasattr(bundle.sources[0], "text")
    assert result.bodies
    assert validate_information_bundle(bundle) == ()
    ensure_valid_bundle(bundle)

    # 실패한 출처는 passages 없이 unavailable로 남는다.
    blocked = [s for s in bundle.sources if s.failure]
    assert len(blocked) == 1
    assert blocked[0].nature == "unavailable"
    assert blocked[0].passages == ()
    assert all(isinstance(item, Passage) for item in bundle.available_passages())

    # 정직성 필드
    payload = bundle.to_dict()
    assert payload["browser_used"] is False
    assert payload["cross_checked_with_db"] is False
    assert payload["requires_grounding_chunks"] is False
    assert payload["team_id_space"] == "internal"

    # 배당은 정규시간 1X2로만 채택된다.
    quotes = adopted_odds_quotes(bundle)
    assert len(quotes) == 1
    assert quotes[0]["market"] == "1x2_regulation"
    assert (quotes[0]["home_decimal"], quotes[0]["draw_decimal"], quotes[0]["away_decimal"]) == (
        1.55,
        4.2,
        5.5,
    )


def test_network_usage_counts_failures_and_budget_is_shared():
    """리다이렉트·실패도 NetworkUsage에 세고, 예산 상한을 공유한다."""
    budget = _budget(api_requests=5)
    http = FakeHttp(
        {
            "https://n1.example.test/a": {"status": 200, "body": _read("article.html")},
            "https://n2.example.test/b": {
                "status": 200,
                "body": _read("squad_list.html"),
                "redirects": ("https://n2.example.test/b", "https://n2.example.test/c"),
            },
            "https://n3.example.test/d": {"status": 403, "body": _read("blocked_403.html")},
        }
    )
    result = _collect(
        _candidates(
            "https://n1.example.test/a",
            "https://n2.example.test/b",
            "https://n3.example.test/d",
        ),
        http=http,
        budget=budget,
    )
    usage = result.bundle.network_usage
    assert usage.http_used == 4, "요청 3회 + 리다이렉트 1홉"
    assert usage.http_failed == 1
    assert usage.redirects == 1
    assert usage.http_limit == 5
    assert budget.api_used <= 5


def test_missing_trafilatura_is_declared_not_hidden(monkeypatch):
    """필수 추출기가 없으면 진단에 남긴다(보조 경로만으로 성공 주장 금지)."""
    from app.preview import retrieval

    monkeypatch.setattr(
        retrieval, "_extraction_dependency_problem", lambda: "trafilatura 미설치(테스트)"
    )
    http = FakeHttp(
        {"https://dep.example.test/a": {"status": 200, "body": _read("article.html")}}
    )
    result = _collect(_candidates("https://dep.example.test/a"), http=http)
    assert any("trafilatura" in item for item in result.bundle.diagnostics)


def test_redirect_hops_beyond_the_reservation_are_refused_and_counted():
    """예약한 홉보다 많은 실제 전송은 채택하지 않고, 계상도 상한을 넘지 않는다(검토 F7)."""
    from app.preview import retrieval
    from app.preview.contracts import FixtureIdentity
    from app.preview.retry import BudgetLimits

    class _MultiHop:
        """`redirects`는 시작 URL을 포함한다(실제 클라이언트 규약)."""

        def __init__(self, hops: int) -> None:
            self.hops = hops
            self.requests: list[str] = []

        def fetch(self, url, *, timeout_seconds):
            self.requests.append(url)
            return retrieval.HttpFetch(
                requested_url=url,
                final_url=url + "/final",
                status_code=200,
                body_text="<html><body><article>" + ("가" * 400) + "</article></body></html>",
                redirects=tuple(
                    [url]
                    + [f"https://www.example-sports.test/r{i}" for i in range(self.hops - 1)]
                ),
            )

    fixture = FixtureIdentity.from_dict(
        {
            "fixture_id": 1,
            "league_id": 1,
            "season": 2026,
            "home_team_id": 13,
            "away_team_id": 4,
            "kickoff_at": "2026-11-21T12:30:00+00:00",
        }
    )
    candidates = _candidates("https://www.example-sports.test/a")

    # 예산 3, 실제 6홉 → 예약(3)을 넘으므로 채택하지 않고, 계상은 3을 넘지 않는다.
    budget = RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=3, attempts_per_call=3), now=FIXED_NOW
    )
    out = retrieval.collect_with_bodies(
        candidates=candidates,
        fixture=fixture,
        budget=budget,
        http=_MultiHop(6),
        now=FIXED_NOW,
        target_checker=lambda url: True,
    )
    source = out.bundle.sources[0]
    assert source.failure == "redirect_over_budget"
    assert source.usable is False
    assert budget.api_used <= 3
    assert out.bundle.network_usage.http_used <= 3

    # 예산 24, 실제 2홉 → 정확히 2만 계상하고 나머지 예약은 반환한다.
    budget2 = RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=24, attempts_per_call=3), now=FIXED_NOW
    )
    out2 = retrieval.collect_with_bodies(
        candidates=candidates,
        fixture=fixture,
        budget=budget2,
        http=_MultiHop(2),
        now=FIXED_NOW,
        target_checker=lambda url: True,
    )
    assert budget2.api_used == 2
    assert len(out2.bundle.usable_sources) == 1


class _CountingHopClient:
    """실제 네트워크 경계를 흉내 내는 카운터 클라이언트(전송 1회마다 `sent` 증가).

    `on_hop` 게이트를 **전송 직전**에 부르며, 게이트가 False면 그 홉을 보내지 않는다.
    실제 `StandardHttpClient`/`ScraplingHttpClient`와 같은 계약이다.
    """

    supports_hop_gate = True

    def __init__(self, max_hops: int = 10) -> None:
        self.max_hops = max_hops
        self.sent = 0
        self.requests: list[str] = []

    def fetch(self, url, *, timeout_seconds, on_hop=None):
        hops = [url]
        current = url
        for index in range(self.max_hops):
            if on_hop is not None and not on_hop(current):
                return retrieval.HttpFetch(
                    requested_url=url,
                    final_url=current,
                    status_code=None,
                    body_text="",
                    redirects=tuple(hops),
                    error="budget_exhausted",
                )
            self.sent += 1
            self.requests.append(current)
            nxt = f"https://www.example-sports.test/hop{index}"
            hops.append(nxt)
            current = nxt
        return retrieval.HttpFetch(
            requested_url=url,
            final_url=current,
            status_code=200,
            body_text="<html><body><article>" + ("가" * 400) + "</article></body></html>",
            redirects=tuple(hops),
        )


def test_budget_caps_actual_transmissions_not_just_accounting():
    """예산 3이면 **실제 전송도 3회**에서 멈춘다 — 4번째 전송은 나가지 않는다(검토 F7).

    이전 구현은 응답을 받은 뒤에야 추가 홉을 차감해, 예산 3에서 6번 전송하고 3만 계상했다.
    지금은 홉 게이트가 **전송 전에** 차감/거부하므로 상한을 넘는 전송 자체가 없다.
    """
    from app.preview import retrieval
    from app.preview.contracts import FixtureIdentity
    from app.preview.retry import BudgetLimits

    fixture = FixtureIdentity.from_dict(
        {
            "fixture_id": 1,
            "league_id": 1,
            "season": 2026,
            "home_team_id": 13,
            "away_team_id": 4,
            "kickoff_at": "2026-11-21T12:30:00+00:00",
        }
    )
    budget = RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=3, attempts_per_call=3), now=FIXED_NOW
    )
    client = _CountingHopClient(max_hops=10)
    out = retrieval.collect_with_bodies(
        candidates=_candidates("https://www.example-sports.test/a"),
        fixture=fixture,
        budget=budget,
        http=client,
        now=FIXED_NOW,
        target_checker=lambda url: True,
    )

    # 실제 전송이 예산에서 멈췄다(4번째 전송 없음).
    assert client.sent == 3, client.sent
    assert budget.api_used == 3
    # 상한에 걸린 출처는 채택되지 않고 사유가 남는다.
    assert out.bundle.sources[0].failure == "budget_exhausted"
    assert out.bundle.sources[0].usable is False


def test_standard_http_client_does_not_follow_redirects_implicitly():
    """표준 클라이언트가 리다이렉트를 **자동 추종하지 않는다**(숨은 홉 금지, 검토 F7)."""
    from urllib import request as urlrequest

    from app.preview import retrieval

    opener = retrieval._no_redirect_opener()
    handler = next(
        item for item in opener.handlers if isinstance(item, urlrequest.HTTPRedirectHandler)
    )
    # redirect_request가 None을 돌려주면 라이브러리는 3xx를 따라가지 않는다.
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://x/y") is None
    assert retrieval.StandardHttpClient.supports_hop_gate is True


def test_hops_are_capped_by_usage_not_by_model_retry_attempts():
    """`attempts_per_call=1`(승인 실행)에서 리다이렉트 홉이 막히지 않는다(검토 F7).

    홉은 한 fetch 안의 전송이고, `attempts_per_call`은 논리 호출 **재시도** 횟수다. 둘을
    같은 카운터로 묶으면 승인 실행에서 2번째 홉이 거부되어 수집이 통째로 실패한다.
    """
    from app.preview import retrieval
    from app.preview.contracts import FixtureIdentity
    from app.preview.retry import BudgetLimits

    fixture = FixtureIdentity.from_dict(
        {
            "fixture_id": 1,
            "league_id": 1,
            "season": 2026,
            "home_team_id": 13,
            "away_team_id": 4,
            "kickoff_at": "2026-11-21T12:30:00+00:00",
        }
    )

    class _ThreeHop(_CountingHopClient):
        def fetch(self, url, *, timeout_seconds, on_hop=None):
            hops = [url]
            current = url
            for index in range(3):
                if on_hop is not None and not on_hop(current):
                    return retrieval.HttpFetch(
                        requested_url=url,
                        final_url=current,
                        status_code=None,
                        body_text="",
                        redirects=tuple(hops),
                        error="budget_exhausted",
                    )
                self.sent += 1
                current = f"https://www.example-sports.test/h{index}"
                hops.append(current)
            return retrieval.HttpFetch(
                requested_url=url,
                final_url=current,
                status_code=200,
                body_text="<html><body><article>" + ("가" * 400) + "</article></body></html>",
                redirects=tuple(hops),
            )

    # A) 3홉 + API 예산 24 → 성공(시도 상한 1이어도 홉은 통과한다).
    budget = RunBudget.for_run(
        BudgetLimits(model_requests=6, api_requests=24, attempts_per_call=1), now=FIXED_NOW
    )
    client = _ThreeHop()
    out = retrieval.collect_with_bodies(
        candidates=_candidates("https://www.example-sports.test/a"),
        fixture=fixture,
        budget=budget,
        http=client,
        now=FIXED_NOW,
        target_checker=lambda url: True,
    )
    assert client.sent == 3
    assert budget.api_used == 3
    assert out.bundle.usable_sources, out.bundle.sources
    # 홉은 논리 호출의 '시도' 수를 올리지 않는다.
    assert budget.attempts_used("fetch:c1") == 0

    # B) API 예산 2 → 3번째 홉은 나가지 않는다.
    budget2 = RunBudget.for_run(
        BudgetLimits(model_requests=6, api_requests=2, attempts_per_call=1), now=FIXED_NOW
    )
    client2 = _ThreeHop()
    out2 = retrieval.collect_with_bodies(
        candidates=_candidates("https://www.example-sports.test/a"),
        fixture=fixture,
        budget=budget2,
        http=client2,
        now=FIXED_NOW,
        target_checker=lambda url: True,
    )
    assert client2.sent == 2
    assert budget2.api_used == 2
    assert out2.bundle.sources[0].failure == "budget_exhausted"


def test_article_collection_caps_at_its_share_and_leaves_odds_share():
    """기사 수집은 자기 몫(10+공유10)에서 멈추고 배당 몫 10을 건드리지 않는다.

    검사 이유(실패 시 사용자 영향): 2026-11-19 실제 실행에서 기사 수집이 단일 24회
    예산을 모두 쓰자 제공자 배당 읽기가 나가지 못해 배당 섹션이 비었다. 이 검사는
    **실제 collect_with_bodies 경로**가 소유자를 표기해 그 간섭을 막는지 본다.
    """
    from app.preview.retry import HTTP_OWNER_ARTICLES, HTTP_OWNER_ODDS, HTTP_LOCAL_SHARE

    urls = [f"https://example.test/a{index}" for index in range(1, 26)]
    budget = RunBudget.for_generation(("section_odds",), now=FIXED_NOW)
    assert budget.http_owner_quotas is True

    _collect(_candidates(*urls), http=FakeHttp({}), budget=budget)

    # 25개 후보를 줬지만 기사 몫(10+공유10)에서 멈춘다.
    assert budget.http_owner_used(HTTP_OWNER_ARTICLES) == HTTP_LOCAL_SHARE * 2
    # 그리고 배당이 쓸 10회가 그대로 남는다.
    assert budget.http_remaining(HTTP_OWNER_ODDS) == HTTP_LOCAL_SHARE
    allowed, reason = budget.http_charge(HTTP_OWNER_ODDS, now=FIXED_NOW)
    assert allowed is True, reason
