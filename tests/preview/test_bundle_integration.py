"""PS-05 통합 검사: 정보 원문 → 저장 → 조회 → 섹션 결과 버전 연결.

이 파일이 확인하는 것(계획 PS-05 대표 직접 검사):

- 기록 transport로 정상 6전송 / 최대 8 / 동시 2를 확인한다.
- 부분 자료(웹 없음, DB만)로도 최종 전망 경로가 성립하고, 없는 섹션 본문을 만들지 않는다.
- 저장된 정보 원문 묶음이 관리자 API로 **같은 구간·출처**로 다시 열린다.
- 저장 응답 재처리는 새 결과 버전을 만들고 **전송 0회**다.
- 묶음이 없으면 빈 묶음을 만들지 않고 `available=false`와 사유를 낸다.

실제 모델·외부 HTTP 전송은 하지 않는다. `mode=live` 기록 transport를 쓰되 네트워크가
없다는 사실을 여기 밝힌다. 전용 로컬 테스트 DB만 쓴다.
"""

from __future__ import annotations

import json
import pathlib
import types
import uuid
from datetime import datetime, timezone

from app.preview import information_bundle as bundle_contract
from app.preview import provider, retrieval, send_ledger, store
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
    RunStatus,
)
from app.preview.modules import form as form_module
from app.preview.retry import RunBudget, plan_limits

RUNS = "/api/v1/admin/preview/runs"
LOGIN = "/api/v1/auth/login"
FIXED_NOW = datetime(2026, 11, 11, 4, 0, tzinfo=timezone.utc)

FIXTURE = {
    "fixture_id": 1557474,
    "league_id": 39,
    "season": 2026,
    "home_team_id": 13,
    "away_team_id": 4,
    "kickoff_at": "2026-11-21T12:30:00+00:00",
}


def _ok(text: str) -> provider.TransportResult:
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response={
            "candidates": [
                {"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}
            ]
        },
        usage={"input_tokens": 120, "output_tokens": 80},
        duration_ms=4,
    )


def _live_transport(text: str = "응답") -> provider.RecordedTransport:
    return provider.RecordedTransport(
        script=[_ok(text) for _ in range(16)],
        provider="recorded-live",
        mode=RunMode.LIVE,
    )


def _bundle_transport() -> provider.RecordedTransport:
    """모듈별 정상 응답을 골라 돌려주는 기록 transport(mode=live, 네트워크 없음).

    라우트 통합 검사는 **실제 그래프 전체**를 돌리므로 조사 2 + 작성 3 + 전망 1의
    응답 모양이 각각 맞아야 한다. 값은 `test_bundle_pipeline`의 기록 응답과 같은 축이다.
    """
    answers = {
        "discovery_people": {
            "candidates": [
                {"url": "https://example.test/stats", "title": "시즌 기록", "kind": "stats"},
                # 차단된 출처 하나. 실패해도 다른 본문을 숨기지 않는지 함께 본다.
                {"url": "https://example.test/blocked", "title": "차단된 페이지", "kind": "preview"},
            ]
        },
        "discovery_outlook": {
            "candidates": [
                {"url": "https://example.test/preview", "title": "경기 프리뷰", "kind": "preview"}
            ]
        },
        "section_players": {
            "players": [
                {
                    "selected_player": "엘링 홀란",
                    "selection_reason": "최근 5경기 6골",
                    "team": "맨체스터 시티",
                    "evidence": ["src:stats#p1"],
                },
                {
                    "selected_player": "알렉스 이워비",
                    "selection_reason": "원정 공격의 중심",
                    "team": "풀럼",
                    "evidence": ["src:stats#p1"],
                },
            ]
        },
        "section_availability": {"injuries": []},
        "section_outlook": {
            "media_forecasts": [
                {
                    "publisher": "BBC",
                    "statement": "홈팀 우세 (2-1)",
                    "predicted_score": "2-1",
                    "url": "https://example.test/preview",
                    "evidence": ["src:stats#p1"],
                }
            ]
        },
        "section_ai_forecast": {
            "forecast": "홈팀이 리그 순위 우위를 바탕으로 주도권을 잡을 것으로 보입니다.",
            "predicted_score": {"home": 2, "away": 1},
            "score_reasoning": ["리그 3위", "최근 5경기 3승 1무 1패"],
            "forecast_evidence": ["src:stats#p1"],
        },
    }

    class _BranchTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            logical = str(getattr(spec, "logical_call_id", ""))
            answer = answers.get(logical, {"candidates": []})
            text = json.dumps(answer, ensure_ascii=False)
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}], "role": "model"},
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 150, "output_tokens": 90},
                duration_ms=8,
            )

    return _BranchTransport()


def _context(run_id: uuid.UUID | None = None) -> ExecutionContext:
    return ExecutionContext(
        run_id=run_id or uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=1,
        config_version="mp11-integration-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _bundle(*, with_web: bool = True) -> bundle_contract.InformationBundle:
    sources: tuple[bundle_contract.BundleSource, ...] = ()
    if with_web:
        sources = (
            bundle_contract.BundleSource(
                source_id="src:stats",
                discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
                requested_url="https://example.test/stats",
                final_url="https://example.test/stats",
                nature="stats",
                method="fresh_http",
                title="시즌 기록",
                captured_at=FIXED_NOW,
                http_status=200,
                body_chars=2400,
                passages=(
                    bundle_contract.Passage(
                        passage_id="src:stats#p1",
                        source_id="src:stats",
                        ordinal=1,
                        text="홈팀의 최근 5경기 성적은 3승 1무 1패입니다.",
                    ),
                ),
            ),
            bundle_contract.BundleSource(
                source_id="src:blocked",
                discovery_group=bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,
                requested_url="https://example.test/odds",
                final_url="https://example.test/odds",
                nature="unavailable",
                method="unavailable",
                http_status=403,
                failure="HTTP 403 챌린지",
            ),
        )
    return bundle_contract.InformationBundle(
        bundle_id=bundle_contract.new_bundle_id(),
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=sources,
        db_snapshot=bundle_contract.DbSnapshot(
            fixture=dict(FIXTURE),
            team_id_space="internal",
            collected_at=FIXED_NOW,
            teams=(
                {"team_id": 13, "name_ko": "맨체스터 시티"},
                {"team_id": 4, "name_ko": "풀럼"},
            ),
            standings=({"team_id": 13, "rank": 3, "points": 21},),
            # 재생성 후보가 실제 선수 id를 갖도록 DB 통계 행을 넣는다.
            roster=({"player_id": 533, "team_id": 13, "goals": 9, "appearances": 10},),
            # 부상 행 0건은 '부상자 없음'의 증거가 아니다. coverage로 사유를 남긴다.
            injuries=(),
            coverage=(
                {
                    "topic": "부상·출전 불확실",
                    "state": "unknown",
                    "detail": "저장된 부상 행이 없습니다. '없음'의 증거가 아닙니다.",
                },
            ),
            source_tables=("public.fixture", "public.team", "public.standings"),
            readable=True,
        ),
        discovery_groups=(
            bundle_contract.DiscoveryGroup(
                group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
                status="completed",
                logical_call_id="discovery_people",
                sent_attempts=1,
            ),
            bundle_contract.DiscoveryGroup(
                group=bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,
                status="completed",
                logical_call_id="discovery_outlook",
                sent_attempts=1,
            ),
        ),
        network_usage=bundle_contract.NetworkUsage(
            http_used=2, http_failed=1, http_limit=24
        ),
        mode="live",
        diagnostics=("배당 사이트 1곳이 차단되어 본문을 얻지 못했습니다.",),
    )


def _login_admin(client, make_user) -> dict:
    """원래 benchmark 로그인으로 ADMIN 세션을 얻고 **Bearer 헤더**를 붙인다.

    통합 앱의 프리뷰 관리 API는 원래 JWT access token을 요구한다(별도 preview
    쿠키 세션을 만들지 않는다). 응답 본문의 `access_token`을 이후 요청에 그대로 쓴다.
    """
    user = make_user(role="ADMIN")
    response = client.post(
        LOGIN, json={"email": user["email"], "password": user["password"]}
    )
    assert response.status_code == 200, response.text
    token = response.json().get("access_token")
    assert token, "로그인 응답에 access_token이 없다"
    client.headers["Authorization"] = f"Bearer {token}"
    return user


def _store_context_run(session, context: ExecutionContext) -> None:
    from app.preview.contracts import FixtureIdentity

    store.store_run(
        session,
        context,
        fixture=FixtureIdentity.from_dict(FIXTURE),
        fixture_label="fixture 1557474",
        label="ps05 integration",
        status=RunStatus.RUNNING,
    )


def test_normal_path_six_sends_with_two_concurrent_peak(session_factory):
    """정상 경로는 6전송이고, 동시 모델 요청은 2를 넘지 않는다."""
    context = _context()
    with session_factory() as session:
        _store_context_run(session, context)
        session.commit()

        budget = RunBudget.for_run(
            plan_limits(model_requests=8, normal_model_calls=6), now=FIXED_NOW
        )
        transport = _live_transport()
        logical_ids = (
            "discovery_people",
            "discovery_outlook",
            "section_players",
            "section_availability",
            "section_outlook",
            "section_ai_forecast",
        )
        for logical_call_id in logical_ids:
            result = provider.execute_request(
                provider.RequestSpec(
                    logical_call_id=logical_call_id,
                    provider="recorded-live",
                    model="recorded-model",
                    operation="integration_test",
                    module_id="D1",
                ),
                context,
                transport=transport,
                budget=budget,
                session=session,
                sleeper=lambda seconds: None,
                now=lambda: FIXED_NOW,
            )
            assert result.ok is True, logical_call_id

        assert budget.model_used == 6
        assert send_ledger.charged_requests(session, run_id=context.run_id) == 6
        # 예약은 정상 6회 몫과 같으므로 재시도 여유는 2회다.
        assert budget.limits.model_requests - budget.limits.normal_model_calls == 2

        from app.preview.retry import ConcurrencyLimiter

        limiter = ConcurrencyLimiter(2, label="모델")
        with limiter:
            with limiter:
                pass
        assert limiter.peak <= 2


def test_db_only_bundle_keeps_final_forecast_possible(session_factory):
    """웹 자료가 전혀 없어도 DB 경기력 자료가 있으면 최종 전망 입력이 성립한다."""
    bundle = _bundle(with_web=False)
    assert bundle.usable_sources == ()
    assert bundle.db_snapshot is not None and bundle.db_snapshot.readable is True
    assert bundle_contract.validate_information_bundle(bundle) == ()

    summary = bundle_contract.bundle_summary(bundle)
    assert summary["usable_source_count"] == 0
    assert summary["db_readable"] is True
    # 부상 0건을 "부상자 없음"으로 바꾸지 않는다.
    assert summary["db_injuries"] == 0
    coverage = {row["topic"]: row["state"] for row in bundle.db_snapshot.coverage}
    assert coverage["부상·출전 불확실"] == "unknown"


def test_saved_bundle_reopens_with_same_passages(client, make_user, session_factory):
    """저장한 묶음이 관리자 API에서 같은 출처·구간으로 다시 열린다."""
    bundle = _bundle()
    run_id = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(run_id))
        session.commit()
        saved = store.save_information_bundle(
            session, run_id=run_id, bundle=bundle, actor_id=1
        )
        session.commit()
        assert saved["available"] is True
        artifact_id = saved["artifact_id"]

    _login_admin(client, make_user)
    response = client.get(f"{RUNS}/{run_id}/information-bundle")
    assert response.status_code == 200, response.text
    payload = response.json()
    # 계약(manifest §4): availability는 중첩 객체다. 프론트 파서도 이 모양을 읽는다.
    assert payload["availability"]["available"] is True
    assert payload["availability"]["artifact_id"] == artifact_id
    assert payload["availability"]["reason"] is None
    reopened = payload["bundle"]
    assert reopened["bundle_hash"] == bundle.to_dict()["bundle_hash"]
    assert reopened["bundle_version"] == bundle_contract.INFORMATION_BUNDLE_VERSION
    assert [source["source_id"] for source in reopened["sources"]] == [
        "src:stats",
        "src:blocked",
    ]
    # 실패한 출처는 후보로 남고 구간이 없다.
    blocked = reopened["sources"][1]
    assert blocked["failure"]
    assert blocked["passages"] == []
    # 전달 **후보** 구간이 그대로 보존된다. 실제 전달 기록은 section_deliveries다.
    assert reopened["available_passages"][0]["text"].startswith("홈팀의 최근")
    assert reopened["section_deliveries"] == []
    assert "전달 후보" in reopened["passage_semantics"]
    assert reopened["browser_used"] is False
    assert reopened["cross_checked_with_db"] is False
    assert reopened["requires_grounding_chunks"] is False


def test_bundle_endpoint_reports_missing_bundle_honestly(client, make_user, session_factory):
    """묶음이 없으면 빈 묶음을 만들지 않고 available=false와 사유를 낸다."""
    run_id = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(run_id))
        session.commit()

    _login_admin(client, make_user)
    payload = client.get(f"{RUNS}/{run_id}/information-bundle").json()
    assert payload["availability"]["available"] is False
    assert payload["bundle"] is None
    # 사유가 중첩 객체로 전달돼야 화면이 일반 문구로 대체하지 않는다(검토 F6).
    assert "저장되어 있지 않습니다" in (payload["availability"]["reason"] or "")


def test_bundle_endpoint_requires_admin(client, session_factory):
    """비인증·비ADMIN은 묶음을 읽을 수 없다."""
    assert client.get(f"{RUNS}/{uuid.uuid4()}/information-bundle").status_code == 401


def test_stored_response_replay_makes_new_version_without_sending(session_factory):
    """저장 응답 재처리는 새 결과 버전을 만들고 전송 0회다."""
    context = _context()
    with session_factory() as session:
        _store_context_run(session, context)
        session.commit()

        budget = RunBudget.for_run(now=FIXED_NOW)
        transport = _live_transport("모델 원문 응답")
        result = provider.execute_request(
            provider.RequestSpec(
                logical_call_id="discovery_people",
                provider="recorded-live",
                model="recorded-model",
                operation="integration_test",
                module_id="D1",
            ),
            context,
            transport=transport,
            budget=budget,
            session=session,
            sleeper=lambda seconds: None,
            now=lambda: FIXED_NOW,
        )
        assert result.ok is True

        from app.preview.contracts import ModuleResult, ModuleStatus, QualityStatus

        from app.preview.contracts import FixtureIdentity, ModuleInput

        execution = store.start_module_execution(
            session,
            run_id=context.run_id,
            module_id="D1",
            module_input=ModuleInput(
                module_id="D1",
                fixture=FixtureIdentity.from_dict(FIXTURE),
                snapshot_ids=(),
                selected_result_ids=(),
                input_hash="hash-1",
                prompt_version="p1",
                contract_version="c1",
                implementation_version="i1",
                delivered=(),
                parameters={},
            ),
            ordinal=0,
            actor_id=1,
        )
        saved = store.save_module_result(
            session,
            ModuleResult(
                result_id=uuid.uuid4(),
                module_id="D1",
                module_execution_id=execution.id,
                run_id=context.run_id,
                version=1,
                input_hash="hash-1",
                status=ModuleStatus.SUCCEEDED,
                quality=QualityStatus.READY,
                payload={"payload": {"note": "원본"}},
            ),
            actor_id=1,
        )
        session.commit()

    with session_factory() as session:
        replay = provider.replay_result(
            session,
            source_result_id=saved.id,
            transform=lambda raw, previous: {
                "claims": [],
                "coverage": [],
                "diagnostics": ["재처리"],
                "payload": {"replayed": True},
            },
            actor_id=1,
        )
        session.commit()
        assert replay.external_calls == 0
        assert replay.new_version == saved.version + 1
        # 재처리는 새 결과 버전일 뿐, 새 전송이 아니다.
        assert (
            send_ledger.charged_requests(session, run_id=saved.run_id) == 1
        ), "재처리가 전송으로 세어졌다"


def test_partial_bundle_caps_delivered_passages_within_limits():
    """부분 자료에서도 전달 구간은 상한 안에서만 만들어진다(초과 시 거부)."""
    long_text = "가" * (bundle_contract.MAX_PASSAGE_CHARS + 1)
    source = bundle_contract.BundleSource(
        source_id="src:too-long",
        discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
        requested_url="https://example.test/long",
        final_url="https://example.test/long",
        nature="news",
        method="fresh_http",
        passages=(
            bundle_contract.Passage(
                passage_id="src:too-long#p1",
                source_id="src:too-long",
                ordinal=1,
                text=long_text,
            ),
        ),
    )
    bundle = bundle_contract.InformationBundle(
        bundle_id="bundle-long-1",
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=(source,),
    )
    problems = bundle_contract.validate_information_bundle(bundle)
    assert any("상한" in problem for problem in problems), problems


def test_section_prompt_versions_are_stable_constants():
    """섹션 작성 프롬프트/구현 버전은 코드 상수에서 온다(실행마다 흔들리지 않는다)."""
    assert form_module.FORM_IMPLEMENTATION_VERSION
    assert form_module.FORM_PROMPT_VERSION
    # 같은 코드가 같은 값을 낸다.
    again = __import__("importlib").reload(
        __import__("app.preview.modules.form", fromlist=["form"])
    )
    assert again.FORM_IMPLEMENTATION_VERSION == form_module.FORM_IMPLEMENTATION_VERSION
    assert again.FORM_PROMPT_VERSION == form_module.FORM_PROMPT_VERSION


def test_b_collection_output_adapts_into_the_contract_bundle():
    """B의 실제 반환(`CollectionOutput.bundle`)이 계약 묶음으로 그대로 이어진다.

    B는 이미 `InformationBundle`을 돌려준다(코디네이터 ACK: CollectionResult 대신 계약
    반환형). A 어댑터는 호출자가 준 DB 스냅샷·조사 기록·시각만 덮어쓰고, 출처·실패·
    배당·네트워크 사용량은 **다시 만들지 않는다**.
    """
    from app.preview import retrieval

    collected_ok = retrieval.CollectedSource(
        source_id="src-1",
        requested_url="https://example.test/stats",
        final_url="https://example.test/stats",
        method="fresh_http",
        collected_at=FIXED_NOW,
        http_status=200,
        title="시즌 기록",
        kind="stats",
        extraction="trafilatura",
        extractor="trafilatura",
        text="홈팀 최근 성적 본문입니다." * 4,
        body_sha256="deadbeef",
        passages=(
            retrieval.Passage(
                passage_id="src-1#p1",
                source_id="src-1",
                ordinal=1,
                text="구간 본문",
            ),
        ),
        search_group="people",
    )
    blocked = retrieval.CollectedSource(
        source_id="src-2",
        requested_url="https://example.test/odds",
        final_url=None,
        method="fresh_http",
        collected_at=FIXED_NOW,
        kind="preview",
        search_group="outlook",
        failure="http_403",
        failure_detail="차단",
    )
    b_bundle = bundle_contract.InformationBundle(
        bundle_id="bundle-from-b",
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=(
            retrieval._to_bundle_source(collected_ok, group_fallback="people"),
            retrieval._to_bundle_source(blocked, group_fallback="outlook"),
        ),
        odds=bundle_contract.OddsMarket(
            quotes=(
                bundle_contract.OddsQuote(
                    source_id="src-1",
                    site="Bet365",
                    market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                    observed_at=FIXED_NOW,
                    home_decimal=2.1,
                    draw_decimal=3.4,
                    away_decimal=3.2,
                ),
            )
        ),
        network_usage=bundle_contract.NetworkUsage(
            http_used=3, http_failed=1, redirects=1, http_limit=24
        ),
        diagnostics=("배당 표 1곳을 읽었습니다.",),
    )
    output = retrieval.CollectionOutput(
        bundle=b_bundle,
        bodies=(),
        diagnostics=({"reason": "http_403", "url": "https://example.test/odds"},),
        network_usage={
            "used": 3,
            "failed": 1,
            "redirects": 1,
            "limit": 24,
            "counted": "redirect hops, failures and direct fetches",
        },
    )

    snapshot = bundle_contract.DbSnapshot(
        fixture=dict(FIXTURE), team_id_space="internal", readable=True
    )
    adapted = bundle_contract.bundle_from_collection(
        collection=output,
        db_snapshot=snapshot,
    )
    data = adapted.to_dict()
    assert data["bundle_id"] == "bundle-from-b"
    assert data["db_snapshot"]["readable"] is True
    assert [source["source_id"] for source in data["sources"]] == ["src-1", "src-2"]
    # B가 만든 표기가 canonical 값으로 유지된다.
    assert data["sources"][0]["discovery_group"] == "players_injury"
    assert data["sources"][1]["discovery_group"] == "media_odds"
    # 실패한 출처는 본문 구간 없이 사유만 남는다(근거로 쓰지 않는다).
    assert data["sources"][1]["failure"] == "http_403"
    assert data["sources"][1]["passages"] == []
    assert data["sources"][1]["nature"] == "unavailable"
    # 배당 채택 1줄, 네트워크 사용량은 B 값을 그대로 쓴다(다시 세지 않는다).
    assert len(bundle_contract.adopted_odds_quotes(adapted)) == 1
    assert data["network_usage"]["http_used"] == 3
    assert data["network_usage"]["http_limit"] == 24
    assert bundle_contract.validate_information_bundle(adapted) == ()
    assert bundle_contract.bundle_summary(adapted)["section_delivery_count"] == 0


def test_legacy_source_list_shape_still_adapts():
    """옛 모양(출처 목록 + network_usage dict)도 같은 계약으로 옮긴다."""
    from app.preview import retrieval

    legacy = type(
        "LegacyCollection",
        (),
        {
            "sources": (
                retrieval.CollectedSource(
                    source_id="src-legacy-1",
                    requested_url="https://example.test/a",
                    final_url="https://example.test/a",
                    method="fresh_http",
                    collected_at=FIXED_NOW,
                    http_status=200,
                    kind="stats",
                    extraction="trafilatura",
                    text="본문 텍스트입니다." * 10,
                    body_sha256="abc",
                    passages=(
                        retrieval.Passage(
                            passage_id="src-legacy-1#p1",
                            source_id="src-legacy-1",
                            ordinal=1,
                            text="구간 본문",
                        ),
                    ),
                    search_group="people",
                ),
            ),
            "diagnostics": ({"reason": "no_usable_sources"},),
            "network_usage": {"used": 2, "limit": 24, "counted": "hops"},
            "odds": None,
        },
    )()
    bundle = bundle_contract.bundle_from_collection(
        collection=legacy,
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
    )
    data = bundle.to_dict()
    assert data["sources"][0]["nature"] == "stats"
    assert data["sources"][0]["passages"][0]["text"] == "구간 본문"
    assert data["network_usage"]["http_used"] == 2
    assert any("no_usable_sources" in note for note in data["diagnostics"])
    assert bundle_contract.validate_information_bundle(bundle) == ()


def test_section_delivery_records_actual_payload_not_candidates():
    """섹션 전달 기록은 실제 payload 해시와 전달 구간 ID만 담는다."""
    payload = {"contents": [{"role": "user", "parts": [{"text": "전달 본문"}]}]}
    delivery = bundle_contract.build_section_delivery(
        section_id=bundle_contract.SECTION_PLAYERS,
        payload=payload,
        passage_ids=("src:stats#p1",),
        source_ids=("src:stats",),
        available_passage_ids=("src:stats#p1", "src:stats#p2"),
        logical_call_id="section_players",
        model_delivered=True,
        input_chars=12,
        sent_attempts=1,
        prompt_version="p1",
        implementation_version="i1",
    )
    assert delivery.payload_sha256 == bundle_contract.delivery_hash(payload)
    assert delivery.passage_ids == ("src:stats#p1",)
    assert delivery.excluded_passage_ids == ("src:stats#p2",)
    assert delivery.model_delivered is True

    bundle = _bundle().with_section_delivery(delivery)
    saved = bundle.to_dict()
    assert saved["section_deliveries"][0]["payload_sha256"] == delivery.payload_sha256
    assert bundle_contract.bundle_summary(bundle)["section_delivery_count"] == 1

    # 모델을 쓰지 않는 배당 섹션은 전달 기록을 만들지 않는다(model_delivered=False).
    odds_delivery = bundle_contract.build_section_delivery(
        section_id=bundle_contract.SECTION_ODDS,
        payload={"quotes": []},
        model_delivered=False,
        available_passage_ids=("src:odds#p1",),
    )
    assert odds_delivery.payload_sha256 is None
    assert odds_delivery.excluded_passage_ids == ("src:odds#p1",)


def test_bodies_are_stored_as_artifacts_and_readable_per_run(
    client, make_user, session_factory
):
    """수집 전문은 아티팩트로 저장되고, 묶음은 `body_artifact_id`로만 가리킨다.

    관리자 화면은 묶음 인라인으로 출처·후보 구간을 보고, 전문은 이 실행 소유 아티팩트
    경로로 연다. 다른 실행 소유 원문은 열리지 않는다(권한 경계).
    """
    from app.preview import retrieval

    run_id = uuid.uuid4()
    source = bundle_contract.BundleSource(
        source_id="src-body-1",
        discovery_group=bundle_contract.DISCOVERY_GROUP_PLAYERS_INJURY,
        requested_url="https://example.test/a",
        final_url="https://example.test/a",
        nature="stats",
        method="fresh_http",
        captured_at=FIXED_NOW,
        body_chars=40,
        passages=(
            bundle_contract.Passage(
                passage_id="src-body-1#p1",
                source_id="src-body-1",
                ordinal=1,
                text="후보 구간 본문",
            ),
        ),
    )
    body = retrieval.SourceBody(
        source_id="src-body-1",
        requested_url="https://example.test/a",
        final_url="https://example.test/a",
        text="전문 본문입니다. " * 5,
        body_sha256="bodyhash",
        extractor="trafilatura",
        extraction="trafilatura",
        html_sha256="htmlhash",
        captured_at=FIXED_NOW,
    )
    collection = retrieval.CollectionOutput(
        bundle=bundle_contract.InformationBundle(
            bundle_id="bundle-bodies",
            fixture=dict(FIXTURE),
            team_id_space="internal",
            collected_at=FIXED_NOW,
            sources=(source,),
            db_snapshot=bundle_contract.DbSnapshot(
                fixture=dict(FIXTURE), team_id_space="internal", readable=True
            ),
        ),
        bodies=(body,),
    )

    with session_factory() as session:
        _store_context_run(session, _context(run_id))
        session.commit()
        saved = store.save_information_bundle_with_bodies(
            session, run_id=run_id, collection=collection, actor_id=1
        )
        session.commit()
        saved_source = saved["bundle"]["sources"][0]
        assert saved_source["body_artifact_id"], saved_source
        # 묶음에는 전문 텍스트가 다시 들어가지 않는다.
        assert "전문 본문입니다." not in str(saved["bundle"])

    _login_admin(client, make_user)
    inline = client.get(f"{RUNS}/{run_id}/information-bundle").json()
    assert inline["bundle"]["sources"][0]["passages"][0]["text"] == "후보 구간 본문"

    detail = client.get(
        f"{RUNS}/{run_id}/information-bundle/sources/src-body-1"
    ).json()
    assert detail["available"] is True
    assert detail["body"]["text"].startswith("전문 본문입니다.")
    assert detail["body"]["body_sha256"] == "bodyhash"

    # 다른 실행에서는 이 전문을 열 수 없다.
    other_run = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(other_run))
        session.commit()
    missing = client.get(
        f"{RUNS}/{other_run}/information-bundle/sources/src-body-1"
    ).json()
    assert missing["available"] is False
    assert missing["body"] is None


def test_section_regeneration_reuse_requires_a_stored_bundle(client, make_user, session_factory):
    """source_mode=reuse는 저장된 묶음의 실행을 명시해야 하며, 서버가 임의로 고르지 않는다."""
    _login_admin(client, make_user)

    # base_run_id 없이 reuse를 요청하면 실행 전에 거부된다.
    response = client.post(
        "/api/v1/admin/preview/section-runs",
        json={"workflow_id": "section_players", "mode": "mock", "source_mode": "reuse"},
    )
    assert response.status_code == 422, response.text
    assert "base_run_id" in response.text

    # 묶음이 없는 실행을 가리키면 "없다"고 정직하게 거부한다.
    empty_run = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(empty_run))
        session.commit()
    response = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "mock",
            "source_mode": "reuse",
            "base_run_id": str(empty_run),
        },
    )
    assert response.status_code == 422, response.text
    assert "정보 원문 묶음이 없습니다" in response.text


def test_section_regeneration_reuse_requires_live_and_never_fakes_reuse(
    client, make_user, session_factory
):
    """묶음 재사용 재생성은 **실제 모델 경로**에서만 일어나고, 모의를 재사용으로 꾸미지 않는다.

    검토 F5: 이전에는 `mode=mock` + `source_mode=reuse`가 묶음을 쓰지 않는 옛 노드를 돌리고도
    `bundle_reused=true`를 돌려줬다. 지금은 mock 재생성이 묶음 재사용 실적으로 표시되지
    않는다(422, 정직한 거절).
    """
    base_run = uuid.uuid4()
    bundle = _bundle()
    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        session.commit()
        store.save_information_bundle(
            session, run_id=base_run, bundle=bundle, actor_id=1
        )
        session.commit()

    _login_admin(client, make_user)
    response = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "mock",
            "source_mode": "reuse",
            "base_run_id": str(base_run),
            "bundle_id": bundle.bundle_id,
            "fixture_id": FIXTURE["fixture_id"],
            "league_id": FIXTURE["league_id"],
            "season": FIXTURE["season"],
            "home_team_id": FIXTURE["home_team_id"],
            "away_team_id": FIXTURE["away_team_id"],
            "kickoff_at": FIXTURE["kickoff_at"],
        },
    )
    # 모의 실행을 "묶음 재사용"으로 표시하지 않는다.
    assert response.status_code == 422, response.text
    assert "묶음 재사용으로 표시하지 않습니다" in response.text


def test_bundle_section_regeneration_uses_the_stored_bundle_without_collection(
    session_factory,
):
    """live 재생성은 저장 묶음만 쓰고 **수집·검색 호출 0**으로 작성 호출만 낸다(검토 F5)."""
    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import RunMode
    from app.preview.retry import BudgetLimits

    base_run = uuid.uuid4()
    bundle = _bundle()
    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        session.commit()
        store.save_information_bundle(session, run_id=base_run, bundle=bundle, actor_id=1)
        session.commit()

        transport, _ = _recording_transport_for("section_players")
        outcome = bp.run_section_regeneration(
            session,
            section_id="section_players",
            actor_id=7,
            transport=transport,
            base_run_id=base_run,
            source_mode="reuse",
            limits=BudgetLimits(
                model_requests=6,
                api_requests=24,
                attempts_per_call=1,
                deadline_seconds=1800,
                normal_model_calls=6,
            ),
            now=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc),
        )
        session.commit()

    assert outcome.bundle_reused is True
    assert outcome.bundle_refreshed is False
    assert outcome.bundle_id == bundle.bundle_id
    assert outcome.other_sections_untouched is True
    # 작성 호출 1회만 나갔고, 수집·검색 호출은 없다.
    assert [call.logical_call_id for call in transport.calls] == ["section_players"]
    assert outcome.external_calls == 1
    assert outcome.section_result_id is not None


def _store_base_run_with_selected_sections(
    session_factory, base_run: uuid.UUID
) -> dict:
    """부모 실행: 원문 묶음 + 앞 섹션 결과 3개(+이전 최종 결론) + 그 구성본을 남긴다.

    재생성 대표 사례의 **입력 자료**다. 모두 실제 저장 경로(`store.*`)로 만들고, 값은
    검사가 나중에 "덮어쓰지 않았는지"를 확인할 수 있게 돌려준다.
    """
    from app.preview import bundle_pipeline as bp
    from app.preview import version_manifest
    from app.preview.contracts import QualityStatus

    rows = (
        ("section_players", "주목 선수 본문", 1),
        ("section_availability", "부상·결장 본문", 1),
        ("section_outlook", "외부 전망 본문", 2),
        ("section_ai_forecast", "이전 최종 결론 본문", 1),
    )
    stored: dict[str, dict] = {}
    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        bundle = _bundle()
        store.save_information_bundle(
            session, run_id=base_run, bundle=bundle, actor_id=1
        )
        for section_id, body, version in rows:
            row = store.save_section_result(
                session,
                run_id=base_run,
                workflow_id=section_id,
                workflow_version=version_manifest.workflow_version_of(section_id),
                title=section_id,
                body=body,
                version=version,
                mode=RunMode.LIVE,
                environment=Environment.DEV,
                quality=QualityStatus.READY,
                output_contract_version="mp-test-output-1",
                contract_version="mp-test-contract-1",
                actor_id=1,
                now=FIXED_NOW,
            )
            stored[section_id] = {
                "result_id": str(row.id),
                "version": row.version,
                "body": row.body,
                "quality": row.quality,
            }
        composition = bp.save_composition(
            session,
            run_id=base_run,
            fixture_id=FIXTURE["fixture_id"],
            selected_result_ids=tuple(
                uuid.UUID(stored[section_id]["result_id"])
                for section_id, _body, _version in rows
            ),
            actor_id=1,
            now=FIXED_NOW,
        )["composition"]
        session.commit()
    return {
        "sections": stored,
        "composition_id": composition["composition_id"],
        "composition_items": [
            (item["result_id"], item["version"]) for item in composition["items"]
        ],
        "bundle_id": bundle.bundle_id,
    }


def test_live_regeneration_returns_the_saved_result_and_new_composition(
    client, make_user, monkeypatch, session_factory
):
    """live 재생성 응답·새 구성본이 **방금 저장된 새 결과**와 일치한다(E-1/E-2).

    같은 대표 검사의 두 입력으로 두 분기를 함께 본다.

    - `append`: 선택 결과에 최종 결론이 없다 → 이 실행의 새 결론을 **덧붙인다**.
    - `replace`: 선택 결과에 이전 최종 결론이 있다 → 그 항목을 새 결론으로 **교체한다**.

    어느 쪽이든 응답의 실행·버전·품질·사유는 저장행과 같아야 하고, 선택한 다른 섹션의
    결과 ID·버전은 보존되며 부모 구성본·원문·이전 결과는 덮어쓰지 않는다.
    """
    from app.preview import version_manifest

    for replace_existing in (False, True):
        base_run = uuid.uuid4()
        base = _store_base_run_with_selected_sections(session_factory, base_run)
        before = base["sections"]

        selected = ["section_players", "section_availability", "section_outlook"]
        if replace_existing:
            selected.append("section_ai_forecast")
        selected_ids = [before[section]["result_id"] for section in selected]

        transport, _ = _recording_transport_for("section_ai_forecast")
        _patch_admin_route(monkeypatch, reader=_StubReader(), transport=transport)
        _login_admin(client, make_user)

        response = client.post(
            "/api/v1/admin/preview/section-runs",
            json={
                "workflow_id": "section_ai_forecast",
                "mode": "live",
                "source_mode": "reuse",
                "base_run_id": str(base_run),
                "selected_result_ids": selected_ids,
                "base_result_id": (
                    before["section_ai_forecast"]["result_id"]
                    if replace_existing
                    else None
                ),
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()

        new_run_id = uuid.UUID(payload["run_id"])
        new_result_id = uuid.UUID(payload["section_result_id"])
        # E-1: live 재생성 응답의 워크플로우 버전은 실제 저장 계약 값과 같다.
        assert payload["workflow_version"] == version_manifest.workflow_version_of(
            "section_ai_forecast"
        )
        assert payload["status"] == "succeeded", payload
        assert payload["composition_id"], payload

        with session_factory() as session:
            stored = store.get_section_result(session, new_run_id, new_result_id)
            assert stored is not None, "응답이 가리키는 새 섹션 결과가 저장되지 않았다"
            # 응답 메타데이터는 **방금 저장된 행**과 같다(지어낸 값이 아니다).
            assert payload["section_result_version"] == stored.version
            assert payload["new_version"] == stored.version
            assert payload["quality"] == stored.quality
            assert payload["unavailable_reason"] == stored.unavailable_reason
            assert payload["parent_run_id"] == str(base_run)

            record = store.load_composition(session, new_run_id)
            assert record.get("available"), record
            composition = record["composition"]
            by_section = {item["section_id"]: item for item in composition["items"]}

            # E-2: 이 실행이 다시 만든 항목은 새 결과와 정확히 일치한다.
            regenerated = by_section["section_ai_forecast"]
            assert regenerated["result_id"] == str(new_result_id)
            assert regenerated["run_id"] == str(new_run_id)
            assert regenerated["version"] == stored.version
            assert regenerated["quality"] == stored.quality
            assert regenerated["unavailable"] is (stored.unavailable_reason is not None)
            assert regenerated["unavailable_reason"] == stored.unavailable_reason
            assert regenerated["replaced_by_regeneration"] is True
            # 새 결론은 한 번만 실린다(옛 결론이 중복으로 남지 않는다).
            assert len(composition["items"]) == 4, composition["items"]
            assert [
                item["section_id"]
                for item in composition["items"]
                if item["section_id"] == "section_ai_forecast"
            ] == ["section_ai_forecast"]

            # 선택한 다른 섹션은 기존 실행·ID·버전 그대로다.
            for section in selected:
                if section == "section_ai_forecast":
                    continue
                item = by_section[section]
                assert item["result_id"] == before[section]["result_id"], section
                assert item["run_id"] == str(base_run), section
                assert item["version"] == before[section]["version"], section

            # 부모 실행의 이전 결과·구성본·원문은 덮어쓰지 않았다.
            for section, previous in before.items():
                row = store.get_section_result(
                    session, base_run, uuid.UUID(previous["result_id"])
                )
                assert row is not None, section
                assert row.version == previous["version"], section
                assert row.body == previous["body"], section
                assert row.quality == previous["quality"], section
            parent_now = store.load_composition(session, base_run)["composition"]
            assert parent_now["composition_id"] == base["composition_id"]
            assert [
                (item["result_id"], item["version"]) for item in parent_now["items"]
            ] == base["composition_items"]
            parent_bundle = store.load_information_bundle(session, base_run)
            assert parent_bundle.get("available"), parent_bundle
            assert parent_bundle["bundle"]["bundle_id"] == base["bundle_id"]

        if replace_existing:
            assert payload["base_result_id"] == before["section_ai_forecast"]["result_id"]
        else:
            assert payload["base_result_id"] is None


def test_regeneration_budget_covers_the_modules_that_refresh_actually_runs(
    session_factory, monkeypatch
):
    """refresh 재생성의 예산은 **실제 참여 모듈**로 잡아 조사 전송이 작성 3회를 굶기지 않는다.

    검토 B-2: 예전에는 `budget.module_ids`에 선택한 작성 모듈만 넣어 전체 상한이 3이었고,
    refresh가 같은 예산으로 조사 모듈도 호출해 조사 2회 + 작성 1회 뒤 작성의 두 번째가
    "모델 전송 합계(3회)"로 거부됐다. 모듈별 3회 정책이 재생성에서 시험되지 않는 결함이다.
    """
    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import QualityStatus
    from app.preview.retry import BudgetLimits, RunBudget

    # 예산 목록은 실제 실행 계획과 같아야 한다(첫 전송 전에 확정된다).
    assert bp.regeneration_logical_call_ids("section_players", source_mode="refresh") == (
        "discovery_people",
        "section_players",
    )
    # reuse는 검색·수집 없이 선택한 작성 모듈만, 배당은 모델 0회라는 기존 동작을 지킨다.
    assert bp.regeneration_logical_call_ids("section_players", source_mode="reuse") == (
        "section_players",
    )
    assert bp.regeneration_logical_call_ids("section_odds", source_mode="reuse") == ()
    assert bp.regeneration_logical_call_ids("section_odds", source_mode="refresh") == (
        "discovery_outlook",
    )

    # 실제 participant 수에서 합계를 파생해도 모듈별 3회는 줄지 않고, 네 번째는 불가하다.
    budget = RunBudget.for_generation(
        bp.regeneration_logical_call_ids("section_players", source_mode="refresh")
    )
    assert budget.effective_model_requests() == 6
    for _ in range(3):
        for logical in ("discovery_people", "section_players"):
            allowed, reason = budget.can_attempt(logical)
            assert allowed, reason
            budget.charge(logical)
    for logical in ("discovery_people", "section_players"):
        allowed, reason = budget.can_attempt(logical)
        assert not allowed
        assert "이번 생성 전송 상한(3회)" in reason

    base_run = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        session.commit()
        store.save_information_bundle(
            session, run_id=base_run, bundle=_bundle(), actor_id=1
        )
        session.commit()

        transport = _retrying_transport()
        # 수집 대상 판정은 네트워크 경계다. 대역으로 바꾸고 DNS를 조회하지 않는다.
        monkeypatch.setattr(retrieval, "is_public_http_url", lambda url, **_kw: True)
        outcome = bp.run_section_regeneration(
            session,
            section_id="section_players",
            actor_id=7,
            transport=transport,
            base_run_id=base_run,
            source_mode="refresh",
            reader=_StubReader(),
            http=_FakeCollectionHttp(),
            limits=BudgetLimits(
                model_requests=8,
                api_requests=24,
                attempts_per_call=3,
                deadline_seconds=1800,
                normal_model_calls=6,
            ),
            now=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc),
        )
        session.commit()

    # 조사는 기술 오류로 2회 재시도한 뒤 성공하고, 작성은 자기 3회를 모두 쓴다.
    # 예전 예산(3)이면 조사가 3회를 다 쓰는 순간 작성은 한 번도 나가지 못했다.
    assert [call.logical_call_id for call in transport.calls] == [
        "discovery_people",
        "discovery_people",
        "discovery_people",
        "section_players",
        "section_players",
        "section_players",
    ]
    assert outcome.external_calls == 6
    assert outcome.bundle_refreshed is True
    assert outcome.section_result_id is not None
    assert outcome.quality is QualityStatus.READY
    assert any(
        "실제 참여 모듈(refresh): discovery_people, section_players" in item
        for item in outcome.diagnostics
    ), outcome.diagnostics


def _retrying_transport():
    """조사·작성이 각각 2회 기술 오류(503) 뒤 성공하는 기록 transport.

    `retry_after_seconds=0`이라 재시도 대기가 실제로 기다리지 않는다(예산·재시도 규칙은
    제품 경로 그대로다). 네트워크를 열지 않는다.
    """
    discovery_answer = {
        "candidates": [
            {"url": "https://example.test/stats", "title": "시즌 기록", "kind": "stats"}
        ]
    }
    writer_answer = {
        "players": [
            {
                "selected_player": "엘링 홀란",
                "selection_reason": "최근 5경기 6골",
                "team": "맨체스터 시티",
                "evidence": [],
            }
        ]
    }

    class _Transport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)
            self.sent_by_logical: dict[str, int] = {}

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            logical = str(getattr(spec, "logical_call_id", ""))
            ordinal = self.sent_by_logical.get(logical, 0)
            self.sent_by_logical[logical] = ordinal + 1
            if ordinal < 2:
                return provider.TransportResult(
                    http_status=503,
                    raw_request={"contents": "recorded"},
                    raw_response={"error": "temporarily unavailable"},
                    error_message="HTTP 503",
                    retry_after_seconds=0,
                )
            answer = discovery_answer if logical.startswith("discovery_") else writer_answer
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": json.dumps(answer, ensure_ascii=False),
                                        "role": "model",
                                    }
                                ],
                                "role": "model",
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 150, "output_tokens": 90},
                duration_ms=8,
            )

    return _Transport()


def _recording_transport_for(section_id: str):
    """섹션별 기록 응답을 돌려주는 transport(mode=live, 네트워크 없음)."""
    answers = {
        "section_players": {
            "players": [
                {
                    "selected_player": "엘링 홀란",
                    "selection_reason": "최근 5경기 6골",
                    "team": "맨체스터 시티",
                    "evidence": ["src:stats#p1"],
                }
            ]
        },
        "section_availability": {"injuries": []},
        "section_outlook": {"media_forecasts": []},
        "section_ai_forecast": {
            "forecast": "전망",
            "predicted_score": {"home": 2, "away": 1},
            "score_reasoning": ["이유"],
            "forecast_evidence": [],
        },
    }

    class _Transport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            text = json.dumps(answers.get(section_id, {}), ensure_ascii=False)
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}], "role": "model"},
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 40},
                duration_ms=3,
            )

    transport = _Transport()
    return transport, None


def test_odds_section_expects_zero_model_calls(client, make_user):
    """배당 섹션은 모델 0회로 표시된다(수집·정규화만)."""
    _login_admin(client, make_user)
    response = client.post(
        "/api/v1/admin/preview/section-runs",
        json={"workflow_id": "section_outlook", "mode": "mock", "source_mode": "refresh"},
    )
    assert response.status_code == 200, response.text
    # 기존 경로(section_outlook)는 모델 1회지만, 배당 전용 섹션은 0회로 선언된다.
    from app.api.v1.preview_admin import _expected_section_model_calls

    assert _expected_section_model_calls("section_odds") == 0
    assert _expected_section_model_calls("section_players") == 1
    assert _expected_section_model_calls("section_ai_forecast") == 1


def test_section_results_expose_stored_structured_values(session_factory):
    """섹션 결과 조회가 저장 payload의 구조 값을 그대로 노출한다(새로 만들지 않는다)."""
    from app.preview.contracts import (
        FixtureIdentity,
        ModuleInput,
        ModuleResult,
        ModuleStatus,
        QualityStatus,
    )

    run_id = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(run_id))
        session.commit()
        execution = store.start_module_execution(
            session,
            run_id=run_id,
            module_id="R4",
            module_input=ModuleInput(
                module_id="R4",
                fixture=FixtureIdentity.from_dict(FIXTURE),
                snapshot_ids=(),
                selected_result_ids=(),
                input_hash="structured-hash",
                prompt_version="p1",
                contract_version="c1",
                implementation_version="i1",
            ),
            ordinal=0,
            actor_id=1,
        )
        payload = {
            "payload": {
                "players": [
                    {
                        "selected_player": "엘링 홀란",
                        "selection_reason": "최근 5경기 6골",
                        "team": "맨체스터 시티",
                    },
                    {
                        "selected_player": "라얀 셰르키",
                        "selection_reason": "측면 돌파",
                        "team": "맨체스터 시티",
                    },
                ],
                "media": [
                    {
                        "publisher": "BBC",
                        "statement": "시티 우세",
                        "predicted_score": "2-1",
                    }
                ],
                "odds": [
                    {
                        "bookmaker": "Bet365",
                        "market": "1x2_regulation",
                        "home": 2.1,
                        "draw": 3.4,
                        "away": 3.2,
                    }
                ],
            }
        }
        stored = store.save_module_result(
            session,
            ModuleResult(
                result_id=uuid.uuid4(),
                module_id="R4",
                module_execution_id=execution.id,
                run_id=run_id,
                version=1,
                input_hash="structured-hash",
                status=ModuleStatus.SUCCEEDED,
                quality=QualityStatus.READY,
                payload=payload,
            ),
            actor_id=1,
        )
        store.save_section_result(
            session,
            run_id=run_id,
            workflow_id="section_players",
            workflow_version="v1",
            title="주목 선수",
            body="본문",
            version=1,
            mode=RunMode.LIVE,
            environment=Environment.DEV,
            quality=QualityStatus.READY,
            output_contract_version="out-1",
            contract_version="c1",
            module_execution_ids=(execution.id,),
            result_ids=(stored.id,),
        )
        session.commit()

    # 라우터를 직접 호출해 구조 값이 저장 payload와 일치하는지 본다(권한은 기존 테스트).
    from app.preview.section_structured import structured_from_payload

    structured = structured_from_payload(payload, workflow_id="section_players")
    assert [row["player"] for row in structured["players"]] == [
        "엘링 홀란",
        "라얀 셰르키",
    ]
    assert structured["players"][0]["reason"] == "최근 5경기 6골"
    # 점수가 있는 매체는 그대로 옮기고, 없는 매체는 점수를 만들지 않는다.
    assert structured["media"][0]["predictedScore"] == "2-1"
    assert structured["odds"][0]["home"] == "2.1"


def test_bundle_regeneration_branch_precedes_the_legacy_gate():
    """새 bundle 재생성 분기가 옛 구현 게이트보다 **앞**에 있어야 한다(검토 F5).

    `_section_implementations`는 옛 노드 목록만 보므로 `section_odds`/`section_ai_forecast`를
    422로 거부한다. 분기가 뒤에 있으면 새 경로의 두 섹션을 화면에서 다시 만들 수 없다.
    """
    import inspect

    from app.api.v1 import preview_admin

    source = inspect.getsource(preview_admin.create_section_run)
    bundle_branch = source.index("REGENERABLE_SECTIONS")
    legacy_gate = source.index("_section_implementations(payload.workflow_id")
    assert bundle_branch < legacy_gate, (
        "bundle 재생성 분기가 legacy 게이트 뒤에 있다 — odds/ai_forecast가 422로 막힌다"
    )


def test_bundle_regeneration_passes_fixture_resolver_and_candidates(session_factory):
    """reuse 재생성도 같은 fixture resolver·player_candidates를 작성기에 넘긴다(검토 F2/F5)."""
    import os

    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import RunMode
    from app.preview.retry import BudgetLimits

    # 승인된 0600 파일의 names DSN을 기존 로더 경로로 읽는다(값 출력 없음).
    # 이 파일이 없으면 resolver가 None이 되어 "전달됨"을 실제로 확인할 수 없다.
    credentials = pathlib.Path.home() / ".config" / "match-preview" / "preview-dev.env"
    if credentials.exists():
        for line in credentials.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'").strip('"'))
    from app.preview.config import get_settings

    get_settings.cache_clear()

    base_run = uuid.uuid4()
    bundle = _bundle()
    captured: dict[str, object] = {}
    original_build = bp.bundle_sections.build_bundle_section

    def _spy(*, section_id, bundle, transport, context, budget, session=None, upstream=None,
             fixture_names=None, resolver=None, limits=None, now=None, player_candidates=None):
        captured["fixture_names"] = dict(fixture_names or {})
        captured["player_candidates"] = tuple(player_candidates or ())
        captured["resolver"] = resolver
        return original_build(
            section_id=section_id, bundle=bundle, transport=transport, context=context,
            budget=budget, session=session, upstream=upstream, fixture_names=fixture_names,
            resolver=resolver, player_candidates=player_candidates, now=now,
        )

    import pytest as _pytest

    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        session.commit()
        store.save_information_bundle(session, run_id=base_run, bundle=bundle, actor_id=1)
        session.commit()

        transport, _ = _recording_transport_for("section_players")
        with _pytest.MonkeyPatch.context() as mp:
            mp.setattr(bp.bundle_sections, "build_bundle_section", _spy)
            bp.run_section_regeneration(
                session,
                section_id="section_players",
                actor_id=7,
                transport=transport,
                base_run_id=base_run,
                source_mode="reuse",
                limits=BudgetLimits(
                    model_requests=6, api_requests=24, attempts_per_call=1,
                    deadline_seconds=1800, normal_model_calls=6,
                ),
                now=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc),
            )
            session.commit()

    # reuse 경로도 DB 팀 이름과 (해석기·후보) 전달 경로를 유지한다.
    assert captured["fixture_names"]["home_team"]
    # 검토 지적: 이름만 보면 resolver/후보 누락을 못 잡는다. 실제로 넘어갔는지 본다.
    assert captured["resolver"] is not None, "재생성이 resolver를 넘기지 않았다"
    assert captured["player_candidates"], "재생성이 player_candidates를 넘기지 않았다"
    # 후보는 저장 묶음의 DB 스냅샷에서 온 실제 선수 id다.
    assert any(
        row.get("player_id") == 533 for row in captured["player_candidates"]
    ), captured["player_candidates"]


def test_reuse_regeneration_resolves_db_korean_names_without_scope_from_the_builder():
    """재생성도 **같은 fixture-scoped 해석기**로 DB 한국어 이름을 확인한다(검토 F2·F5-b).

    작성기는 저장 `player_id`로 이름을 확인할 때 `resolve_player`를 **scope 없이** 부른다.
    범위를 보장하지 않으면 DB에 한국어 이름이 있어도 표시 이름이 비고, 영어 표기가 그대로
    남는다. A의 주입 경계가 범위를 채워 실제 제품 해석기 경로로 이름이 확인되는지 본다.
    """
    import os

    import pytest as _pytest

    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import RunMode
    from app.preview.retry import BudgetLimits

    # 승인된 0600 파일의 names DSN을 기존 로더 경로로 읽는다(값 출력 없음).
    # 이름 자료는 원래 `DATABASE_URL` 하나로 읽는다(별도 names DSN 없음).
    from app.preview.config import get_settings

    get_settings.cache_clear()
    if not get_settings().names_database_url:
        _pytest.skip("원래 DATABASE_URL이 설정되지 않은 환경")
    from sqlalchemy import create_engine, text as _sql_text

    from app.core.db_target import normalize_driver

    _probe = create_engine(normalize_driver(get_settings().names_database_url), future=True)
    try:
        with _probe.connect() as _conn:
            _has_names = _conn.execute(
                _sql_text("SELECT to_regclass('public.team_translation')")
            ).scalar()
    finally:
        _probe.dispose()
    if not _has_names:
        _pytest.skip("이 환경의 원래 연결에 이름 표(team_translation)가 없다")

    resolver = bp._open_name_resolver((13, 4))
    assert hasattr(resolver, "resolve_player"), resolver

    # 작성기와 **같은 호출 형태**(scope 없이 player_id만)로 한국어 이름이 나온다.
    from app.preview.modules.bundle_sections import _resolver_player_name

    assert _resolver_player_name(533, resolver) == "엘링 홀란드"
    # 확인되지 않는 ID는 이름을 지어내지 않는다.
    assert _resolver_player_name(999999, resolver) is None


# --------------------------------------------------------------------------
# 경기 번호 해석·동일성·DB 재조회 (BI-02 수용 기준)
# --------------------------------------------------------------------------
#
# 확인하는 것:
#
# - 외부 경기 번호 하나를 저장 경기에서 해석해 같은 LangGraph로 실행한다(모델 6회).
# - 이전 전체 식별자 입력이 저장 경기와 **충돌하면 422**이고 모델 전송은 0회다.
# - 저장 자료에 없는 번호는 404, 저장소를 못 읽으면 503이며 둘 다 전송 0회다.
# - 부분 결과를 저장한 뒤 GET으로 같은 결과를 읽는다. GET은 **전송 0회**다.
#
# 실제 모델·외부 HTTP·운영 DB는 쓰지 않는다. 저장 경기 조회기는 조회 계약만 갖는
# 합성 객체이고, transport는 `RecordedTransport`(mode=live, 네트워크 없음)다.
# 전용 로컬 테스트 DB(`*_test`)만 쓴다.


class _StubReader:
    """저장 경기 조회기 대역. 읽기 권한·단건 조회 계약만 만족한다."""

    def __init__(self, *, record: dict | None = None, readable: bool = True) -> None:
        self.record = dict(FIXTURE) if record is None else record
        self.readable = readable
        self.queries: list[int] = []
        self.closed = False

    def access(self):
        return types.SimpleNamespace(
            readable=self.readable,
            detail=None if self.readable else "fixture SELECT 권한이 없습니다(test 대역).",
        )

    def get_fixture(self, *, fixture_id: int):
        self.queries.append(int(fixture_id))
        if self.record is None or int(fixture_id) != int(self.record["fixture_id"]):
            return None
        kickoff = datetime.fromisoformat(str(self.record["kickoff_at"]))
        return types.SimpleNamespace(
            internal_id=1,
            fixture_id=int(self.record["fixture_id"]),
            league_id=int(self.record["league_id"]),
            league_name="프리미어리그",
            season=int(self.record["season"]),
            home_team_id=int(self.record["home_team_id"]),
            home_team_name="맨체스터 시티",
            away_team_id=int(self.record["away_team_id"]),
            away_team_name="풀럼",
            kickoff_at=kickoff,
            status_short="NS",
            referee=None,
            updated_at=None,
            label="맨체스터 시티 vs 풀럼",
        )

    def standings_for_league(self, *, league_id: int, season: int):
        """저장된 순위 자료. D0가 DB 근거로 쓰는 최소 축이다."""
        record = self.record or FIXTURE
        return [
            {
                "team_id": int(record["home_team_id"]),
                "rank": 3,
                "points": 21,
                "played": 10,
                "win": 7,
                "draw": 0,
                "loss": 3,
                "form": "LLLWW",
            },
            {
                "team_id": int(record["away_team_id"]),
                "rank": 15,
                "points": 10,
                "played": 10,
                "win": 2,
                "draw": 4,
                "loss": 4,
                "form": "DDWWL",
            },
        ]

    def injuries_for_fixture(self, fixture_id: int):
        """저장된 부상 행 0건. '부상자 없음'의 증거가 아니다(coverage가 unknown)."""
        return []

    def close(self) -> None:
        self.closed = True


def _patch_admin_route(monkeypatch, *, reader, transport):
    """관리자 라우트의 **네트워크 경계만** 대역으로 바꾼다(제품 코드는 그대로)."""
    from app.api.v1 import preview_admin

    monkeypatch.setattr(preview_admin, "_model_transport", lambda mode: transport)
    monkeypatch.setattr(preview_admin, "_fixture_reader", lambda: reader)
    http = _FakeCollectionHttp()
    monkeypatch.setattr(retrieval, "default_http_client", lambda: http)
    monkeypatch.setattr(retrieval, "is_public_http_url", lambda url, **_kw: True)
    return http


class _FakeCollectionHttp:
    """가짜 수집기. 실제 네트워크를 열지 않고 URL마다 **다른** 본문을 돌려준다.

    본문이 같으면 수집기가 중복으로 보고 한 출처만 남긴다. 그래서 URL을 본문에 넣어
    서로 다른 문서임을 드러낸다(그 동작을 우회하는 옵션은 제품 코드에 없다).
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def fetch(self, url: str, *, timeout_seconds: int) -> retrieval.HttpFetch:
        self.calls.append(url)
        if "blocked" in url:
            return retrieval.HttpFetch(
                requested_url=url,
                final_url=url,
                status_code=403,
                body_text="Enable JavaScript and cookies to continue",
            )
        if "preview" in url:
            article = (
                "BBC는 홈팀 우세를 예상했고 예상 스코어는 2-1이라고 전했습니다. "
                f"(출처 {url}) "
            ) * 30
        else:
            article = (
                "홈팀의 최근 5경기 성적은 3승 1무 1패이며 리그 3위입니다. "
                f"(출처 {url}) "
            ) * 30
        html = (
            "<html><head><title>경기 자료</title></head><body><article>"
            + article
            + "</article></body></html>"
        )
        return retrieval.HttpFetch(
            requested_url=url, final_url=url, status_code=200, body_text=html
        )


def test_bundle_route_resolves_the_external_fixture_number_and_stores_results(
    client, make_user, monkeypatch
):
    """외부 번호 하나로 실행하고, 저장된 결과를 GET으로 다시 읽는다(GET 전송 0)."""
    reader = _StubReader()
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={"fixture_id": FIXTURE["fixture_id"], "mode": "live"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["external_calls"] == 6
    # 번호는 **같은 외부 경기 번호로만** 해석됐다(다른 경기를 만들지 않는다).
    # LangGraph 실행은 한 번이며, 같은 경기의 스냅샷 조회가 그 안에서 여러 번 일어날
    # 수 있다. 그래서 "같은 번호만 조회했다"를 단언하고 횟수에 결합하지 않는다.
    assert set(reader.queries) == {FIXTURE["fixture_id"]}, reader.queries

    run_id = payload["run_id"]
    sends_after_run = len(transport.calls)

    # 저장 결과를 GET으로 다시 읽는다. 여기서 새 전송이 나가면 안 된다.
    sections = client.get(f"/api/v1/admin/preview/runs/{run_id}/section-results")
    assert sections.status_code == 200, sections.text
    rows = sections.json()["section_results"]
    assert any(row["workflow_id"] == "section_players" and row["body"] for row in rows)

    preview = client.get(f"/api/v1/admin/preview/runs/{run_id}/preview")
    assert preview.status_code == 200, preview.text

    bundle_view = client.get(f"/api/v1/admin/preview/runs/{run_id}/information-bundle")
    assert bundle_view.status_code == 200, bundle_view.text

    detail = client.get(f"/api/v1/admin/preview/runs/{run_id}")
    assert detail.status_code == 200, detail.text

    # GET 4회 뒤에도 전송 수는 그대로다.
    assert len(transport.calls) == sends_after_run == 6, (
        f"GET이 모델 전송을 일으켰다: {[c.logical_call_id for c in transport.calls]}"
    )


def test_bundle_route_refuses_conflicting_identifiers_without_sending(
    client, make_user, monkeypatch
):
    """이전 전체 식별자 입력이 저장 경기와 다르면 422이고 모델 전송은 0회다."""
    reader = _StubReader()
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={
            "fixture_id": FIXTURE["fixture_id"],
            # 저장된 경기와 다른 리그·팀을 보낸다 → 다른 경기를 만들지 않는다.
            "league_id": 999,
            "home_team_id": 777,
            "mode": "live",
        },
    )
    assert response.status_code == 422, response.text
    assert "다른 경기를 만들지 않습니다" in response.text
    assert transport.calls == [], "충돌인데 모델 전송이 나갔다"


def test_bundle_route_accepts_matching_legacy_identifiers(
    client, make_user, monkeypatch
):
    """과거 전체 식별자 입력도 **저장 경기와 같으면** 정상 실행된다."""
    reader = _StubReader()
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={
            "fixture_id": FIXTURE["fixture_id"],
            "league_id": FIXTURE["league_id"],
            "season": FIXTURE["season"],
            "home_team_id": FIXTURE["home_team_id"],
            "away_team_id": FIXTURE["away_team_id"],
            "kickoff_at": FIXTURE["kickoff_at"],
            "mode": "live",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["external_calls"] == 6


def test_bundle_route_reports_missing_fixture_without_sending(
    client, make_user, monkeypatch
):
    """저장 자료에 없는 번호는 404이고 모델 전송은 0회다."""
    reader = _StubReader()
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={"fixture_id": 999999999, "mode": "live"},
    )
    assert response.status_code == 404, response.text
    assert transport.calls == []


def test_bundle_route_reports_unreadable_store_without_sending(
    client, make_user, monkeypatch
):
    """저장 자료를 읽을 수 없으면 503이고 모델 전송은 0회다."""
    reader = _StubReader(readable=False)
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={"fixture_id": FIXTURE["fixture_id"], "mode": "live"},
    )
    assert response.status_code == 503, response.text
    assert transport.calls == []


def test_fixture_get_returns_the_candidate_and_never_sends(
    client, make_user, monkeypatch
):
    """`GET /fixtures/{fixture_id}`는 기존 FixtureCandidate 단건이며 모델 전송 0회다."""
    reader = _StubReader()
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.get(
        f"/api/v1/admin/preview/fixtures/{FIXTURE['fixture_id']}"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    # 목록의 항목과 같은 모양(단건 객체)이며 번호·팀·시각이 그대로 온다.
    assert payload["fixture_id"] == FIXTURE["fixture_id"]
    assert payload["home_team_id"] == FIXTURE["home_team_id"]
    assert payload["away_team_id"] == FIXTURE["away_team_id"]
    assert payload["kickoff_at"]
    assert payload["origin"] == "stored_db"
    assert transport.calls == []

    missing = client.get("/api/v1/admin/preview/fixtures/999999999")
    assert missing.status_code == 404, missing.text
    assert transport.calls == []


def test_fixture_get_reports_unreadable_store_as_503(client, make_user, monkeypatch):
    """저장 자료를 읽을 수 없으면 빈 성공 대신 503으로 알린다."""
    reader = _StubReader(readable=False)
    transport = _bundle_transport()
    _patch_admin_route(monkeypatch, reader=reader, transport=transport)
    _login_admin(client, make_user)

    response = client.get(
        f"/api/v1/admin/preview/fixtures/{FIXTURE['fixture_id']}"
    )
    assert response.status_code == 503, response.text
    assert transport.calls == []


def test_odds_regeneration_reports_planned_modules_not_just_zero(
    client, make_user, monkeypatch, session_factory
):
    """배당 재생성의 `expected_model_calls`가 **계획상 모듈 수**와 같다(W-3).

    이전 구현은 `(0 if section_odds else 1)`로 고정돼, 배당 **refresh**가 조사 모듈
    (`discovery_outlook`)을 실제로 1회 부르는데도 기대값이 0 → API `no_model_call=true`
    → 화면 "모델 0회"로 표시됐다(사용자 화면 결함). 계약은 다음과 같다.

    - `expected_model_calls`: **계획상** 모듈 수(첫 전송 전 확정된 `participating_module_ids`).
    - `external_calls`: **실제** 모델 전송 수(재시도 포함, `budget.model_used`).
    - API `no_model_call`: 새 기대값이 0인지.

    배당 **reuse**는 계획이 빈 튜플이라 기대 0·실제 0·`no_model_call=true`가 유지되고,
    **refresh**는 기대 1·실제 모델 호출 존재·`no_model_call=false`다.
    모델·HTTP 실제 호출은 없다(기록 transport·가짜 HTTP 대역).

    실패하면 사용자는 배당 "재생성"에서 모델 호출·과금이 실제로 발생했는지 화면으로 알 수 없다.
    """
    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import QualityStatus
    from app.preview.retry import BudgetLimits

    def _limits() -> BudgetLimits:
        return BudgetLimits(
            model_requests=6,
            api_requests=24,
            attempts_per_call=1,
            deadline_seconds=1800,
            normal_model_calls=6,
        )

    # 계획 자체는 이 검사의 전제다(바뀌면 기대값 계약도 함께 바뀐다).
    assert bp.regeneration_logical_call_ids("section_odds", source_mode="reuse") == ()
    assert bp.regeneration_logical_call_ids("section_odds", source_mode="refresh") == (
        "discovery_outlook",
    )

    # --- reuse: 계획 0 → 기대 0, 실제 전송 0 -------------------------------
    base_run = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(base_run))
        session.commit()
        store.save_information_bundle(session, run_id=base_run, bundle=_bundle(), actor_id=1)
        session.commit()
        transport, _ = _recording_transport_for("section_odds")
        reuse = bp.run_section_regeneration(
            session,
            section_id="section_odds",
            actor_id=7,
            transport=transport,
            base_run_id=base_run,
            source_mode="reuse",
            limits=_limits(),
            now=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc),
        )
        session.commit()
    assert reuse.expected_model_calls == 0, reuse.expected_model_calls
    assert reuse.external_calls == 0, reuse.external_calls
    # 배당은 모델을 부르지 않는다(기록 transport 호출 0).
    assert transport.calls == []

    # --- refresh: 계획 1(조사) → 기대 1, 실제 모델 호출 존재 ---------------
    base_run2 = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(base_run2))
        session.commit()
        store.save_information_bundle(session, run_id=base_run2, bundle=_bundle(), actor_id=1)
        session.commit()
        transport2, _ = _recording_transport_for("section_odds")
        refresh = bp.run_section_regeneration(
            session,
            section_id="section_odds",
            actor_id=7,
            transport=transport2,
            base_run_id=base_run2,
            source_mode="refresh",
            reader=_StubReader(),
            http=_FakeCollectionHttp(),
            limits=_limits(),
            now=datetime(2026, 11, 11, 8, 0, tzinfo=timezone.utc),
        )
        session.commit()
    # 계획상 모듈 수는 1이고, 실제로도 조사 모델 전송이 있었다.
    assert refresh.expected_model_calls == 1, refresh.expected_model_calls
    assert refresh.external_calls >= 1, refresh.external_calls
    assert [call.logical_call_id for call in transport2.calls] == ["discovery_outlook"]

    # --- API 연결: no_model_call은 **새 기대값이 0인지**로 판정된다 ---------
    # 응답의 `no_model_call`이 기대값에서 파생되는지 관리자 라우트로 확인한다.
    base_run3 = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(base_run3))
        session.commit()
        store.save_information_bundle(session, run_id=base_run3, bundle=_bundle(), actor_id=1)
        session.commit()

    transport3, _ = _recording_transport_for("section_odds")
    _patch_admin_route(monkeypatch, reader=_StubReader(), transport=transport3)
    _login_admin(client, make_user)
    api_reuse = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_odds",
            "mode": "live",
            "source_mode": "reuse",
            "base_run_id": str(base_run3),
        },
    )
    assert api_reuse.status_code == 200, api_reuse.text
    reuse_payload = api_reuse.json()
    # 배당 reuse: 기대 0 → no_model_call=true(모델을 부르지 않는다).
    assert reuse_payload["expected_model_calls"] == 0, reuse_payload
    assert reuse_payload["no_model_call"] is True, reuse_payload

    base_run4 = uuid.uuid4()
    with session_factory() as session:
        _store_context_run(session, _context(base_run4))
        session.commit()
        store.save_information_bundle(session, run_id=base_run4, bundle=_bundle(), actor_id=1)
        session.commit()

    transport4, _ = _recording_transport_for("section_odds")
    _patch_admin_route(monkeypatch, reader=_StubReader(), transport=transport4)
    api_refresh = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_odds",
            "mode": "live",
            "source_mode": "refresh",
            "base_run_id": str(base_run4),
        },
    )
    assert api_refresh.status_code == 200, api_refresh.text
    refresh_payload = api_refresh.json()
    # 배당 refresh: 기대 1(조사 모듈) → no_model_call=false(모델을 실제로 부른다).
    assert refresh_payload["expected_model_calls"] == 1, refresh_payload
    assert refresh_payload["no_model_call"] is False, refresh_payload
