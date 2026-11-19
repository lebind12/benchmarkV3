"""새 기본 경로 전체(묶음→섹션5→저장)의 기록 통합 검사.

이 파일이 확인하는 것(계획 PS-05 통합 항목 중 새 기본 경로):

- 정상 경로가 **모델 6회**(조사 2 + 작성 3 + 최종 1)로 끝나고, 배당은 0회다.
- 전체 실제 전송 상한 8회가 지켜지며 9번째는 전송 없이 거부된다.
- 웹 본문 0 + DB 경기력 자료만으로도 필수 섹션(주목 선수·AI 전망) 판정이 정직하다.
- 부분 자료(수집 실패 출처)가 섹션 본문을 망가뜨리지 않고 진단으로만 남는다.
- 정보 원문 묶음·섹션 결과·전달 기록이 **실제로 저장**되고 다시 열린다.
- 다른 성공 섹션을 다시 부르지 않는다(섹션별 1회).

실제 모델·외부 HTTP는 부르지 않는다. `RecordedTransport`(mode=live)와 가짜 HTTP
클라이언트로 계수 경로만 실제와 같게 두며, 네트워크가 없다는 사실을 여기 밝힌다.
전용 로컬 테스트 DB(`*_test`)만 쓴다.
"""

from __future__ import annotations

import json
import pathlib
import types
import threading
import time
import uuid
from datetime import datetime, timezone

import pytest

from app.preview import (
    bundle_pipeline,
    information_bundle as bundle_contract,
    provider,
    retrieval,
    send_ledger,
    store,
)
from app.preview.contracts import RunMode, RunStatus
from app.preview.retry import BudgetLimits

FIXED_NOW = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)
FIXTURE = {
    "fixture_id": 1557474,
    "league_id": 39,
    "season": 2026,
    "home_team_id": 13,
    "away_team_id": 4,
    "kickoff_at": "2026-11-21T12:30:00+00:00",
}
HOME_KO = "맨체스터 시티"
AWAY_KO = "풀럼"

DISCOVERY_ANSWER = {
    "people": {
        "candidates": [
            {
                "url": "https://example.test/stats",
                "title": "시즌 기록",
                "kind": "stats",
                "note": None,
            },
            {
                "url": "https://example.test/blocked",
                "title": "차단된 페이지",
                "kind": "preview",
                "note": None,
            },
        ]
    },
    "outlook": {
        "candidates": [
            {
                "url": "https://example.test/preview",
                "title": "경기 프리뷰",
                "kind": "preview",
                "note": None,
            }
        ]
    },
}

PLAYERS_ANSWER = {
    "players": [
        {
            "selected_player": "엘링 홀란",
            "selection_reason": "최근 5경기 6골",
            "team": HOME_KO,
            "evidence": ["src-1#p1"],
        },
        {
            "selected_player": "알렉스 이워비",
            "selection_reason": "원정 공격의 중심",
            "team": AWAY_KO,
            "evidence": ["src-1#p1"],
        },
    ]
}
AVAILABILITY_ANSWER = {
    "injuries": [
        {
            "player_name": "로드리",
            "team_id": 13,
            "status": "doubtful",
            "injury": "무릎",
            "importance": "중원 장악력 저하",
            "evidence": ["src-1#p1"],
        }
    ]
}
OUTLOOK_ANSWER = {
    "media_forecasts": [
        {
            "publisher": "BBC",
            "statement": "홈팀 우세 (2-1)",
            "predicted_score": "2-1",
            "url": "https://example.test/preview",
            "evidence": ["src-3#p1"],
        }
    ]
}
FORECAST_ANSWER = {
    "forecast": "홈팀이 리그 순위 우위를 바탕으로 주도권을 잡을 것으로 보입니다.",
    "predicted_score": {"home": 2, "away": 1},
    "score_reasoning": ["리그 3위", "최근 5경기 3승 1무 1패"],
    "forecast_evidence": ["src-1#p1"],
}

ARTICLE_HTML = (
    "<html><head><title>시즌 기록</title></head><body><article>"
    + ("홈팀의 최근 5경기 성적은 3승 1무 1패이며 리그 3위입니다. " * 20)
    + "</article></body></html>"
)
PREVIEW_HTML = (
    "<html><head><title>경기 프리뷰</title></head><body><article>"
    + ("BBC는 홈팀 우세를 예상했고 예상 스코어는 2-1이라고 전했습니다. " * 20)
    + "</article></body></html>"
)


class _FakeFixtureReader:
    """저장 경기 조회기 대역. 읽기 권한·단건 조회만 흉내 낸다(DB 연결 없음)."""

    def __init__(self, record: dict | None = None) -> None:
        self.record = dict(FIXTURE) if record is None else record
        self.queries: list[int] = []
        self.closed = False

    def access(self):
        return types.SimpleNamespace(readable=True, detail=None)

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
            home_team_name=HOME_KO,
            away_team_id=int(self.record["away_team_id"]),
            away_team_name=AWAY_KO,
            kickoff_at=kickoff,
            status_short="NS",
            referee=None,
            updated_at=None,
            label=f"{HOME_KO} vs {AWAY_KO}",
        )

    def close(self) -> None:
        self.closed = True


def _fake_fixture_reader(record: dict | None = None) -> _FakeFixtureReader:
    return _FakeFixtureReader(record)


class _FakeHttp:
    """가짜 수집기. 실제 네트워크를 열지 않고 본문·차단을 재현한다."""

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
        html = PREVIEW_HTML if "preview" in url else ARTICLE_HTML
        return retrieval.HttpFetch(
            requested_url=url,
            final_url=url,
            status_code=200,
            body_text=html,
        )


def _login_admin_with_bearer(client, make_user) -> dict:
    """원래 benchmark 로그인으로 ADMIN 세션을 얻고 **Bearer 헤더**를 붙인다.

    통합 앱의 프리뷰 관리 API는 원래 JWT access token을 요구한다. 응답의
    `access_token`을 이후 요청 헤더로 쓴다(별도 preview 쿠키 세션을 만들지 않는다).
    """
    user = make_user(role="ADMIN")
    login = client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": user["password"]}
    )
    assert login.status_code == 200, login.text
    token = login.json().get("access_token")
    assert token, "로그인 응답에 access_token이 없다"
    client.headers["Authorization"] = f"Bearer {token}"
    return user


def _transport() -> provider.RecordedTransport:
    """모듈별 응답을 골라 돌려주는 기록 transport(mode=live)."""

    class _BranchTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            logical = str(getattr(spec, "logical_call_id", ""))
            if logical.startswith("discovery_"):
                group = logical.split("_", 1)[1]
                answer = DISCOVERY_ANSWER.get(group, {"candidates": []})
            elif logical == "section_players":
                answer = PLAYERS_ANSWER
            elif logical == "section_availability":
                answer = AVAILABILITY_ANSWER
            elif logical == "section_outlook":
                answer = OUTLOOK_ANSWER
            elif logical == "section_ai_forecast":
                answer = FORECAST_ANSWER
            else:
                answer = {}
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


class _StubReader:
    """저장 DB 읽기 대역. 경기·순위만 있고 부상 행은 0건이다(부상자 없음 아님)."""

    def __init__(self) -> None:
        from app.preview.sources.fixtures import StoredFixture

        self.fixture = StoredFixture(
            internal_id=41125,
            fixture_id=FIXTURE["fixture_id"],
            league_id=FIXTURE["league_id"],
            league_name="Premier League",
            season=FIXTURE["season"],
            home_team_id=FIXTURE["home_team_id"],
            home_team_name=HOME_KO,
            away_team_id=FIXTURE["away_team_id"],
            away_team_name=AWAY_KO,
            kickoff_at=datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc),
            status_short="NS",
            referee=None,
            updated_at=None,
        )

    def get_fixture(self, *, fixture_id=None, internal_id=None):
        return self.fixture

    def standings_for_league(self, *, league_id: int, season: int):
        return [
            {"team_id": FIXTURE["home_team_id"], "rank": 3, "points": 21, "played": 10,
             "win": 7, "draw": 0, "loss": 3, "form": "LLLWW"},
            {"team_id": FIXTURE["away_team_id"], "rank": 15, "points": 10, "played": 10,
             "win": 2, "draw": 4, "loss": 4, "form": "DDWWL"},
        ]

    def injuries_for_fixture(self, fixture_id: int):
        # 저장된 부상 행이 0건이다. "부상자 없음"의 증거가 아니다.
        return []


def _limits() -> BudgetLimits:
    return BudgetLimits(
        model_requests=8,
        api_requests=24,
        attempts_per_call=3,
        deadline_seconds=1800,
        normal_model_calls=6,
    )


def test_bundle_pipeline_normal_path_six_model_calls(session_factory):
    """정상 경로는 모델 6회(조사2+작성3+최종1)이고 배당은 0회다."""
    transport = _transport()
    http = _FakeHttp()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=None,
            http=http,
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        logical = [call.logical_call_id for call in transport.calls]
        assert len(logical) == 6, logical
        assert sorted(logical) == sorted(
            [
                "discovery_people",
                "discovery_outlook",
                "section_players",
                "section_availability",
                "section_outlook",
                "section_ai_forecast",
            ]
        )
        assert outcome.external_calls == 6
        # 전체 상한은 **모듈 수 × 3**에서 파생된다. 옛 8회 상한은 판정에 쓰지 않는다.
        assert outcome.budget["model_requests"] == 18
        assert outcome.budget["module_send_cap"] == 3
        # 배당은 모델 없이 만들어졌고 섹션 결과로 저장됐다.
        assert bundle_contract.SECTION_ODDS in outcome.section_result_ids
        assert outcome.section_quality[bundle_contract.SECTION_ODDS] in {"ready", "insufficient"}

        # 실제 전송 사용량이 장부와 일치한다.
        assert send_ledger.charged_requests(session, run_id=outcome.run_id) == 6

        # 정보 원문 묶음이 저장되고 다시 열린다.
        reopened = store.load_information_bundle(session, outcome.run_id)
        assert reopened["available"] is True
        assert reopened["bundle"]["browser_used"] is False
        assert reopened["bundle"]["cross_checked_with_db"] is False
        # 차단된 출처는 실패로 남고 근거로 쓰이지 않는다.
        failed = [s for s in reopened["bundle"]["sources"] if s.get("failure")]
        assert failed, reopened["bundle"]["sources"]
        # 섹션별 전달 기록이 남는다(모델을 쓴 섹션만 model_delivered=True).
        deliveries = reopened["bundle"]["section_deliveries"]
        assert deliveries
        by_section = {d["section_id"]: d for d in deliveries}
        assert by_section[bundle_contract.SECTION_ODDS]["model_delivered"] is False
        assert by_section[bundle_contract.SECTION_PLAYERS]["model_delivered"] is True
        assert by_section[bundle_contract.SECTION_PLAYERS]["payload_sha256"]


def test_bundle_pipeline_saves_section_results_with_bodies(session_factory):
    """각 섹션 결과가 본문·근거와 함께 저장되고 다시 열린다(실제 작성기 경유)."""
    transport = _transport()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        rows = {
            row["workflow_id"]: row
            for row in store.list_section_results(session, outcome.run_id)
        }
        # 다섯 섹션이 모두 저장되고, 본문이 있는 섹션은 mode=live로 남는다.
        assert set(rows) == set(bundle_contract.SECTION_IDS), rows
        for workflow_id, row in rows.items():
            assert row["mode"] == "live", workflow_id
            if row["body"]:
                # 독자 본문에 내부 ID·진단 문구가 없다.
                for forbidden in ("src-1", "src:", "진단", "미확보"):
                    assert forbidden not in row["body"], (workflow_id, forbidden)
        # 실제 작성기 출력: 선수명과 선정 이유가 분리돼 저장된다.
        players = rows[bundle_contract.SECTION_PLAYERS]
        assert "선정 선수: 엘링 홀란" in players["body"]
        assert "선정 이유: 최근 5경기 6골" in players["body"]
        # 최종 전망: 본문 + 예상 스코어가 함께 저장된다.
        forecast = rows[bundle_contract.SECTION_AI_FORECAST]
        assert "AI 경기 전망" in forecast["body"]
        assert "2-1" in forecast["body"]


def test_bundle_pipeline_db_only_still_reaches_forecast(session_factory):
    """수집 후보가 하나도 없어도 DB 자료로 필수 섹션 판정이 이뤄진다."""

    class _NoCandidatesTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            self.calls.append(spec)
            logical = str(getattr(spec, "logical_call_id", ""))
            if logical.startswith("discovery_"):
                answer = {"candidates": []}
            elif logical == "section_ai_forecast":
                answer = FORECAST_ANSWER
            else:
                answer = {}
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": json.dumps(answer, ensure_ascii=False)}
                                ],
                                "role": "model",
                            },
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 40},
                duration_ms=5,
            )

    transport = _NoCandidatesTransport()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        # 웹 본문이 없어도 최종 전망 요청은 보내진다(DB 경기력 자료가 있으므로).
        assert "section_ai_forecast" in [call.logical_call_id for call in transport.calls]
        assert bundle_contract.SECTION_AI_FORECAST in outcome.section_result_ids
        # 선수 섹션은 근거가 없어 unavailable로 남고, 그 사실이 정상 완료를 막는다.
        assert outcome.status is RunStatus.FAILED
        assert outcome.quality.value == "insufficient"
        assert bundle_contract.SECTION_PLAYERS in (outcome.unavailable_reason or "")


def test_bundle_pipeline_does_not_refetch_or_repeat_sections(session_factory):
    """같은 섹션을 두 번 부르지 않고, HTTP 수집도 후보당 한 번만 한다."""
    transport = _transport()
    http = _FakeHttp()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            http=http,
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        logical = [call.logical_call_id for call in transport.calls]
        assert len(logical) == len(set(logical)), f"같은 논리 호출이 두 번 나갔다: {logical}"
        # 각 후보 URL은 한 번만 가져온다.
        assert len(http.calls) == len(set(http.calls)), http.calls
        assert len(outcome.section_result_ids) >= 4


def test_bundle_pipeline_ignores_the_removed_pooled_eight_send_cap(session_factory):
    """옛 '전체 8회' 상한은 새 생성 경로의 판정에 쓰이지 않는다.

    `limits.model_requests`에 8(또는 6)을 넘겨도 판정은 **모듈별 3회**가 소유한다.
    정상 경로는 6전송이고, 어느 모듈도 4번째를 보내지 않는다.
    """
    transport = _transport()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=BudgetLimits(
                model_requests=6,
                api_requests=24,
                attempts_per_call=3,
                deadline_seconds=1800,
                normal_model_calls=6,
            ),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        logical = [call.logical_call_id for call in transport.calls]
        # 정상 경로는 모듈당 1회다(성공한 모듈을 다시 보내지 않는다).
        assert len(logical) == len(set(logical)) == 6, logical
        # 파생 상한은 옛 6/8 값에 막히지 않는다(모듈 6 × 3 = 18).
        assert outcome.budget["model_requests"] == 18
        assert outcome.budget["module_send_cap"] == 3
        assert send_ledger.charged_requests(session, run_id=outcome.run_id) == 6


def test_bundle_pipeline_rejects_a_caller_supplied_narrower_cap(session_factory):
    """호출자가 더 좁은 모듈 상한을 다시 걸면 조용히 무시하지 않고 거부한다."""
    with session_factory() as session:
        with pytest.raises(ValueError, match="module_send_cap"):
            bundle_pipeline.run_bundle_pipeline(
                session,
                fixture=dict(FIXTURE),
                actor_id=7,
                transport=_transport(),
                http=_FakeHttp(),
                target_checker=lambda url: True,
                mode=RunMode.LIVE,
                now=FIXED_NOW,
                module_send_cap=1,
            )
        session.rollback()


def test_bundle_pipeline_sends_three_per_module_when_the_model_fails(session_factory):
    """모듈이 계속 실패하면 **그 모듈만** 3회에서 멈추고 4번째는 나가지 않는다.

    같은 실행의 다른 모듈은 자신의 3회를 그대로 쓸 수 있다(전체 8회 병목 없음).
    """
    base = _transport()

    class _FailingPlayers(provider.RecordedTransport):
        """`section_players`만 잘린 응답을 계속 돌려준다."""

        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            if str(getattr(spec, "logical_call_id", "")) == "section_players":
                self.calls.append(spec)
                return provider.TransportResult(
                    http_status=200,
                    raw_request={"contents": "recorded"},
                    raw_response={
                        "candidates": [
                            {
                                "content": {"parts": [{"text": '{"players": ['}], "role": "model"},
                                "finishReason": "MAX_TOKENS",
                            }
                        ]
                    },
                )
            # 나머지 모듈은 정상 응답을 그대로 쓴다. 다만 **이 transport**의 호출
            # 목록에도 남겨야 계수가 이 검사의 관측 대상이 된다(대역 transport에만
            # 남기면 여기서 보이지 않는다).
            result = base.send(spec, timeout_seconds=timeout_seconds, context=context)
            self.calls.append(spec)
            return result

    transport = _FailingPlayers()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        player_sends = [
            call for call in transport.calls if call.logical_call_id == "section_players"
        ]
        assert len(player_sends) == 3, f"선수 모듈 전송 {len(player_sends)}회"
        # 다른 모듈은 자기 1회씩 그대로 나갔다(선수 실패가 다른 갈래를 막지 않는다).
        other = [
            call.logical_call_id
            for call in transport.calls
            if call.logical_call_id != "section_players"
        ]
        assert len(other) == len(set(other)) == 5, other
        # 선수 본문은 없지만 실행·저장 사실과 사유는 남는다(성공으로 꾸미지 않는다).
        assert outcome.section_unavailable.get("section_players")


def test_bundle_run_route_runs_the_new_path_and_links_results(client, make_user, monkeypatch):
    """관리자 API가 **경기 번호 하나**로 새 경로를 실행하고 저장 결과 조회로 이어진다.

    서버가 저장된 경기에서 식별자를 해석하므로 화면은 번호만 보낸다. 저장 경기 조회기는
    합성 기록으로 대역해 실제 DB 없이 해석·실행·재조회 연결만 확인한다.
    """
    from app.api.v1 import preview_admin

    transport = _transport()

    def _patched(mode):
        return transport

    monkeypatch.setattr(preview_admin, "_model_transport", _patched)
    monkeypatch.setattr(preview_admin, "_fixture_reader", lambda: _fake_fixture_reader())
    # 네트워크 경계만 대역으로 바꾼다: 수집기와 공개 대상 판정. 제품 코드는 그대로다.
    http = _FakeHttp()
    monkeypatch.setattr(retrieval, "default_http_client", lambda: http)
    monkeypatch.setattr(retrieval, "is_public_http_url", lambda url, **_kw: True)

    _login_admin_with_bearer(client, make_user)

    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={"fixture_id": FIXTURE["fixture_id"], "mode": "live"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["external_calls"] == 6
    assert bundle_contract.SECTION_PLAYERS in payload["section_result_ids"]

    run_id = payload["run_id"]
    sections = client.get(
        f"/api/v1/admin/preview/runs/{run_id}/section-results"
    ).json()["section_results"]
    players = [row for row in sections if row["workflow_id"] == "section_players"]
    assert players and "선정 선수" in players[0]["body"]
    # 구조화 값이 함께 내려온다.
    assert players[0]["structured"]["players"][0]["player"]

    bundle_view = client.get(
        f"/api/v1/admin/preview/runs/{run_id}/information-bundle"
    ).json()
    # 응답 계약(manifest §4): availability는 중첩 객체다(검토 F6).
    assert bundle_view["availability"]["available"] is True
    assert bundle_view["availability"]["reason"] is None
    assert bundle_view["bundle"]["sources"]


def test_bundle_run_route_refuses_mock_mode(client, make_user):
    """새 경로는 모의 응답으로 본문을 채우지 않는다(422)."""
    _login_admin_with_bearer(client, make_user)
    response = client.post(
        "/api/v1/admin/preview/bundle-runs",
        json={
            "fixture_id": FIXTURE["fixture_id"],
            "league_id": FIXTURE["league_id"],
            "season": FIXTURE["season"],
            "home_team_id": FIXTURE["home_team_id"],
            "away_team_id": FIXTURE["away_team_id"],
            "kickoff_at": FIXTURE["kickoff_at"],
            "mode": "mock",
        },
    )
    assert response.status_code == 422, response.text
    assert "실제 모델 호출이 필요합니다" in response.text


class _TimingTransport(provider.RecordedTransport):
    """갈래 병렬 실행을 **직접 관측**하는 기록 transport.

    성능 벤치마크가 아니다. 각 요청이 시작·종료 시각을 남기므로 두 요청의 구간이
    겹치는지(=실제로 동시에 돌았는지)만 확인한다. 장벽(barrier)으로 먼저 온 요청이
    다른 갈래가 시작될 때까지 기다리게 해, 순차 실행이면 교착으로 실패하게 만든다.
    """

    def __init__(self, expected_concurrent: int = 2) -> None:
        super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)
        self.started: list[tuple[str, float]] = []
        self.finished: list[tuple[str, float]] = []
        self.peak = 0
        self._active = 0
        self._lock = threading.Lock()
        self._barrier = threading.Barrier(expected_concurrent, timeout=10)

    def send(self, spec, *, timeout_seconds, context):
        logical = str(getattr(spec, "logical_call_id", ""))
        with self._lock:
            self._active += 1
            self.peak = max(self.peak, self._active)
            self.calls.append(spec)
            self.started.append((logical, time.monotonic()))
        try:
            # 조사 두 갈래는 반드시 서로를 기다린다(순차면 timeout으로 드러난다).
            if logical.startswith("discovery_"):
                try:
                    self._barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            answer = _ANSWER_BY_LOGICAL.get(logical, {})
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
                usage={"input_tokens": 120, "output_tokens": 60},
                duration_ms=3,
            )
        finally:
            with self._lock:
                self._active -= 1
                self.finished.append((logical, time.monotonic()))


_ANSWER_BY_LOGICAL = {
    "discovery_people": DISCOVERY_ANSWER["people"],
    "discovery_outlook": DISCOVERY_ANSWER["outlook"],
    "section_players": PLAYERS_ANSWER,
    "section_availability": AVAILABILITY_ANSWER,
    "section_outlook": OUTLOOK_ANSWER,
    "section_ai_forecast": FORECAST_ANSWER,
}


def test_branches_run_in_parallel_with_one_budget_and_own_sessions(session_factory):
    """조사 2갈래가 실제로 겹쳐 돌고, 예산·상한은 하나를 공유한다.

    - 두 요청의 시간 구간이 겹친다(장벽 때문에 순차 실행은 성립하지 않는다).
    - 논리 호출 6개, 장부 사용량 6, 전체 상한 8 불변.
    - 갈래 세션은 실행 DB에 붙는다(다른 대상으로 새지 않는다).
    """
    transport = _TimingTransport(expected_concurrent=2)
    with session_factory() as session:
        bind = session.get_bind()
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

        discovery_calls = [
            (name, start) for name, start in transport.started if name.startswith("discovery_")
        ]
        assert {name for name, _ in discovery_calls} == {
            "discovery_people",
            "discovery_outlook",
        }
        # 두 조사가 서로를 기다렸다는 사실 자체가 병렬 실행의 증거다(순차면 장벽 timeout).
        assert not transport._barrier.broken

        # 모델 동시 전송은 2를 넘지 않는다.
        assert transport.peak <= 2, transport.peak
        assert outcome.budget["model_requests"] == 18
        assert outcome.external_calls == 6
        assert send_ledger.charged_requests(session, run_id=outcome.run_id) == 6
        # 같은 논리 호출을 두 번 보내지 않는다.
        logical = [call.logical_call_id for call in transport.calls]
        assert len(logical) == len(set(logical)), logical
        # 갈래 세션이 실행 세션과 같은 DB를 썼다(저장 행이 이 엔진에서 조회된다).
        assert bind is not None
        detail = store.get_run_detail(session, outcome.run_id)
        assert len(detail.results) >= 4
        # 다섯 섹션이 모두 저장됐다. 저장 행의 정렬은 `created_at`·workflow_id 기준이며
        # 화면 표시 순서는 계약의 고정 순서(`SECTION_IDS`)를 쓴다(DB 정렬에 의존하지 않음).
        stored_ids = {
            row["workflow_id"] for row in store.list_section_results(session, outcome.run_id)
        }
        assert stored_ids == set(bundle_contract.SECTION_IDS), stored_ids
        assert set(outcome.section_quality) == set(bundle_contract.SECTION_IDS)


class _ExternalIdReader(_StubReader):
    """저장 경기 행이 **내부 리그/시즌 id**를 갖는 대역.

    외부 경기 식별자의 league_id(예: 39)와 저장 표의 league_id(예: 1)가 다르다. DB 조회는
    저장 행의 내부 값으로 해야 하며, 외부 값으로 조회하면 0행이 되어 '자료 없음'처럼 보인다.
    """

    def __init__(self) -> None:
        super().__init__()
        from app.preview.sources.fixtures import StoredFixture

        self.fixture = StoredFixture(
            internal_id=41125,
            fixture_id=FIXTURE["fixture_id"],
            league_id=1,          # 저장 표의 내부 리그 id
            league_name="Premier League",
            season=2026,
            home_team_id=13,
            home_team_name=HOME_KO,
            away_team_id=4,
            away_team_name=AWAY_KO,
            kickoff_at=datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc),
            status_short="NS",
            referee=None,
            updated_at=None,
        )
        self.standings_calls: list[dict] = []

    def standings_for_league(self, *, league_id: int, season: int):
        self.standings_calls.append({"league_id": league_id, "season": season})
        return super().standings_for_league(league_id=league_id, season=season)


def test_db_reads_use_internal_ids_from_the_stored_fixture(session_factory):
    """외부 league_id로 저장 표를 조회하지 않는다(0행을 '없음'으로 오인하지 않는다)."""
    from app.preview import store as store_module
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        ExecutionLimits,
        FixtureIdentity,
        OperationKind,
        RunMode,
        RunStatus,
    )

    reader = _ExternalIdReader()
    run_id = uuid.uuid4()
    with session_factory() as session:
        context = ExecutionContext(
            run_id=run_id,
            operation_kind=OperationKind.PREVIEW,
            environment=Environment.DEV,
            mode=RunMode.LIVE,
            actor_id=7,
            config_version="id-space-test",
            limits=ExecutionLimits(
                model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
            ),
        )
        store_module.store_run(
            session,
            context,
            fixture=FixtureIdentity.from_dict(FIXTURE),
            label="id-space",
            status=RunStatus.RUNNING,
        )
        session.commit()

        snapshot = bundle_pipeline.build_db_snapshot(
            session,
            fixture=dict(FIXTURE),
            reader=reader,
            run_id=run_id,
            actor_id=7,
            now=FIXED_NOW,
        )
        session.commit()

    # 조회는 저장 행의 내부 리그/시즌 id로 갔다.
    assert reader.standings_calls, "순위 조회가 실행되지 않았다"
    assert reader.standings_calls[0]["league_id"] == 1
    assert reader.standings_calls[0]["season"] == 2026
    assert len(snapshot.standings) == 2
    # ID 공간 차이가 진단으로 남고, DB 자료 없음으로 단정하지 않는다.
    assert any("ID 공간" == entry.get("topic") for entry in snapshot.coverage)
    assert snapshot.readable is True


def test_discovery_receives_real_db_team_names_and_context(session_factory):
    """조사 프롬프트에 실제 팀 이름·DB 문맥이 들어간다(자리표시자 금지).

    실제 유료 실행에서 "team 13 vs team 4" 자리표시자 때문에 조사 모델이 팀을 식별하지
    못해 후보를 비웠고, 수집 본문 0건 → 필수 섹션 미작성으로 이어졌다. 그 회귀를 막는다.
    """
    captured: dict[str, str] = {}

    import app.preview.bundle_pipeline as bp

    original = bp.discovery.discover_candidates

    def _spy(*, group, fixture, context, transport, budget, home_team, away_team,
             today=None, league=None, db_context=None, **kwargs):
        captured[group] = f"{home_team} vs {away_team} | {db_context or ''}"
        return original(
            group=group, fixture=fixture, context=context, transport=transport,
            budget=budget, home_team=home_team, away_team=away_team, league=league,
            db_context=db_context, **kwargs,
        )

    import pytest as _pytest

    with session_factory() as session, _pytest.MonkeyPatch.context() as mp:
        mp.setattr(bp.discovery, "discover_candidates", _spy)
        from app.preview.contracts import RunMode

        bp.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=_transport(),
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )

    assert captured, "조사가 실행되지 않았다"
    for group, text in captured.items():
        assert "team 13" not in text and "team 4" not in text, (group, text)
        assert HOME_KO in text and AWAY_KO in text, (group, text)
    assert any("순위" in text for text in captured.values()), captured


def _odds_html() -> str:
    """정규시간 1X2 표를 담은 긴 HTML(최소 본문 길이를 넘긴다)."""
    rows = ["Date,Home,Away,B365H,B365D,B365A"]
    for i in range(12):
        rows.append(f"21/11/2026,Team{i},Rival{i},2.{10 + i % 9},3.{20 + i % 9},3.{30 + i % 9}")
    rows.append("21/11/2026,Manchester City,Fulham,2.10,3.40,3.20")
    csv_text = "\n".join(rows) + "\n"
    return f"<html><body><pre>{csv_text}</pre></body></html>"


class _OddsHttp:
    """배당 표를 돌려주는 가짜 수집기. 팀 이름이 전달되어야만 행이 채택된다."""

    def __init__(self) -> None:
        self.requests: list[str] = []

    def fetch(self, url: str, *, timeout_seconds: int) -> retrieval.HttpFetch:
        self.requests.append(url)
        return retrieval.HttpFetch(
            requested_url=url, final_url=url, status_code=200, body_text=_odds_html()
        )


def test_odds_parser_receives_real_team_names_from_the_db_snapshot(session_factory):
    """수집 단계가 DB 팀 이름을 배당 파서에 넘겨, 실제 표가 채택된다(검토 F9).

    이름을 넘기지 않으면 파서가 `team_names_required`로 즉시 미채택해 배당 섹션이
    구조적으로 항상 비어 있었다. 이름이 있으면 같은 표에서 1X2가 채택된다.
    """
    from app.preview import retrieval as retrieval_module

    captured: dict[str, object] = {}
    original = retrieval_module.collect_with_bodies

    def _spy(*, home_team_names=(), away_team_names=(), **kwargs):
        captured["home"] = tuple(home_team_names)
        captured["away"] = tuple(away_team_names)
        return original(home_team_names=home_team_names, away_team_names=away_team_names, **kwargs)

    import pytest as _pytest

    from app.preview.contracts import RunMode

    with _pytest.MonkeyPatch.context() as mp, session_factory() as session:
        mp.setattr(bundle_pipeline, "retrieval", retrieval_module)
        mp.setattr(retrieval_module, "collect_with_bodies", _spy)
        if True:
            bundle_pipeline.run_bundle_pipeline(
                session,
                fixture=dict(FIXTURE),
                actor_id=7,
                transport=_transport(),
                reader=_StubReader(),
                http=_OddsHttp(),
                target_checker=lambda url: True,
                limits=_limits(),
                mode=RunMode.LIVE,
                now=FIXED_NOW,
            )

    # DB 스냅샷이 준 실제 팀 이름이 그대로 전달됐다(자리표시자 아님).
    assert captured["home"] == (HOME_KO,), captured
    assert captured["away"] == (AWAY_KO,), captured


def test_forecast_without_score_is_not_counted_as_a_complete_run(session_factory):
    """본문은 있어도 예상 스코어가 없으면 정상 완료가 아니다(검토 F4, A측 게이트)."""
    from app.preview.contracts import RunMode

    class _NoScoreTransport(_TimingTransport):
        def send(self, spec, *, timeout_seconds, context):
            logical = str(getattr(spec, "logical_call_id", ""))
            if logical == "section_ai_forecast":
                answer = {
                    "forecast": "전망 본문은 있지만 스코어를 제시하지 않았습니다.",
                    "predicted_score": {},
                    "score_reasoning": [],
                    "forecast_evidence": [],
                }
                with self._lock:
                    self.calls.append(spec)
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
                    usage={"input_tokens": 100, "output_tokens": 40},
                    duration_ms=3,
                )
            return super().send(spec, timeout_seconds=timeout_seconds, context=context)

    transport = _NoScoreTransport(expected_concurrent=1)
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

    # 전망 섹션 행은 저장됐지만, 필수 요건(스코어) 미충족으로 실행은 실패로 남는다.
    assert bundle_contract.SECTION_AI_FORECAST in outcome.section_result_ids
    assert outcome.status is RunStatus.FAILED
    assert outcome.quality.value == "insufficient"
    assert bundle_contract.SECTION_AI_FORECAST in (outcome.unavailable_reason or "")


def test_writer_receives_db_team_names_and_player_candidates(session_factory):
    """작성 단계가 **DB 팀 이름**과 **선수 후보(player_id)**를 실제로 받는다(검토 F1/F2, A측).

    이전에는 자리표시자(`team 13`)와 빈 선수 목록이 전달돼, DB에 실제 이름·통계가 있어도
    프롬프트가 근거 없이 만들어졌다. A는 D0 스냅샷에서 그 값을 꺼내 넘긴다.
    """
    from dataclasses import replace

    from app.preview.contracts import QualityStatus, RunMode
    from app.preview.modules import bundle_sections as sections_module

    captured: dict[str, dict] = {}
    original_build_snapshot = bundle_pipeline.build_db_snapshot

    def _with_stats(session, **kwargs):
        snapshot = original_build_snapshot(session, **kwargs)
        return replace(
            snapshot,
            roster=(
                {"player_id": 533, "team_id": 13, "display_name_ko": "엘링 홀란", "goals": 9},
            ),
        )

    def _spy(*, section_id, bundle, transport, context, budget, session=None,
             upstream=None, fixture_names=None, resolver=None, limits=None, now=None,
             player_candidates=None):
        captured[section_id] = {
            "player_candidates": len(player_candidates or ()),
            "first_player_id": (player_candidates or [{}])[0].get("player_id"),
            "fixture_names": dict(fixture_names or {}),
        }
        return sections_module.SectionDraft(
            section_id=section_id,
            title="t",
            body="",
            quality=QualityStatus.INSUFFICIENT,
            unavailable_reason="spy",
            delivery=None,
            mode="live",
        )

    original_builder = sections_module.build_bundle_section
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp, session_factory() as session:
        mp.setattr(bundle_pipeline, "build_db_snapshot", _with_stats)
        mp.setattr(sections_module, "build_bundle_section", _spy)
        bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=_transport(),
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )

    assert captured, "작성 단계가 호출되지 않았다"
    for section_id in (
        "section_players",
        "section_availability",
        "section_outlook",
        "section_odds",
    ):
        entry = captured[section_id]
        # 자리표시자가 아니라 DB 팀 이름이 전달된다.
        assert entry["fixture_names"]["home_team"] == HOME_KO, (section_id, entry)
        assert entry["fixture_names"]["away_team"] == AWAY_KO, (section_id, entry)
        # 선수 후보(player_id)가 전달된다.
        assert entry["first_player_id"] == 533, (section_id, entry)
    assert sections_module.build_bundle_section is original_builder



def test_db_stats_and_names_reach_the_real_writer_prompt(session_factory):
    """DB 선수 통계·순위·실제 팀 이름이 **실제 작성기 프롬프트**에 들어간다(검토 F1/F2).

    대역이 아니라 E가 소유한 실제 `build_bundle_section`을 기록 transport로 통과시켜,
    요청 payload에 player_id·한국어 이름·순위 문장이 실제로 실리는지 본다. 자리표시자
    (`team 13`)가 들어가면 실패한다.
    """
    from dataclasses import replace

    from app.preview.contracts import RunMode

    original_snapshot = bundle_pipeline.build_db_snapshot

    def _with_stats(session, **kwargs):
        snapshot = original_snapshot(session, **kwargs)
        return replace(
            snapshot,
            roster=(
                {
                    "player_id": 533,
                    "team_id": 13,
                    "display_name_ko": "엘링 홀란",
                    "position": "Forward",
                    "appearances": 10,
                    "goals": 9,
                    "assists": 2,
                    "minutes": 890,
                    "rating": 7.85,
                },
            ),
        )

    transport = _transport()
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as mp, session_factory() as session:
        mp.setattr(bundle_pipeline, "build_db_snapshot", _with_stats)
        bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

    players_call = next(
        call for call in transport.calls if call.logical_call_id == "section_players"
    )
    payload_text = json.dumps(players_call.parameters, ensure_ascii=False)
    # DB 선수 후보(식별자·한국어 이름·기록)가 프롬프트에 실제로 들어간다.
    assert "533" in payload_text
    assert "엘링 홀란" in payload_text
    # 실제 팀 이름과 DB 순위 문장이 들어가고, 자리표시자는 없다.
    assert HOME_KO in payload_text
    assert "team 13" not in payload_text
    assert "3위" in payload_text or "리그 3위" in payload_text


def test_resolver_is_bound_to_the_fixture_team_scope(session_factory):
    """F2: resolver 인젝션이 **이 경기의 두 팀 범위**로 묶여 만들어진다.

    해석기는 범위 없이 `resolve_player`를 부르면 KeyError를 내므로(제품 해석기와 같은
    계약), 범위를 묶지 않으면 DB 한국어 이름 경로가 실제로 쓰이지 않는다. 이름을 미리
    채운 가짜 해석기로 대체하지 않고, 실제 해석기 생성 경계에서 범위를 묶는지만 본다.
    """
    from app.preview import bundle_pipeline as bp

    captured: dict[str, object] = {}
    original = bp._open_name_resolver

    def _spy(team_ids=()):
        captured["team_ids"] = tuple(team_ids)
        return original(team_ids)

    import pytest as _pytest
    from app.preview.contracts import RunMode

    with _pytest.MonkeyPatch.context() as mp, session_factory() as session:
        mp.setattr(bp, "_open_name_resolver", _spy)
        bp.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=_transport(),
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()

    # 이 경기의 두 내부 팀 id가 그대로 전달된다(전체 표 조회 아님).
    assert captured.get("team_ids") == (13, 4), captured

    # 전달만 확인하면 결함을 못 잡는다(검토 지적). 실제 해석기에서 **scope 없는 호출**이
    # DB 한국어 이름으로 해석되는지까지 본다. names DSN이 없는 환경은 건너뛴다.
    import os

    import pytest as _pytest2

    # 이름 자료는 원래 `DATABASE_URL` 하나로 읽는다(별도 names DSN 없음).
    # 그 연결에 이름 표가 없으면(로컬 테스트 DB 등) DB 한국어 이름을 확인할 수 없으므로
    # 이 검사는 건너뛴다. 이름을 지어내지 않는다.
    from app.preview.config import get_settings as _settings

    _settings.cache_clear()
    if not _settings().names_database_url:
        _pytest2.skip("원래 DATABASE_URL이 설정되지 않은 환경")
    from sqlalchemy import create_engine, text as _sql_text

    from app.core.db_target import normalize_driver

    _probe = create_engine(normalize_driver(_settings().names_database_url), future=True)
    try:
        with _probe.connect() as _conn:
            _has_names = _conn.execute(
                _sql_text("SELECT to_regclass('public.team_translation')")
            ).scalar()
    finally:
        _probe.dispose()
    if not _has_names:
        _pytest2.skip("이 환경의 원래 연결에 이름 표(team_translation)가 없다")

    from app.preview.modules.bundle_sections import _resolver_player_name

    real = bp._open_name_resolver((13, 4))
    # 작성기와 같은 scope 없는 호출 형태로 실제 한국어 이름이 나온다.
    assert _resolver_player_name(533, real) == "엘링 홀란드"
    # 확인되지 않는 ID는 이름을 지어내지 않는다.
    assert _resolver_player_name(999999, real) is None


def test_section_save_exception_kind_survives_in_run_failure_detail(
    session_factory, monkeypatch
):
    """섹션 저장 경계에서 난 예외의 **종류**가 실행 기록에 남는다.

    사용자 영향: 갈래가 롤백되면 모듈 실행·섹션 결과·시도 행이 모두 사라져, 홈이 왜
    빈약해졌는지 사후에 알 수 없다(2026-11-18 CE-E2E에서 실제로 확인이 막혔다).
    원문 메시지(비밀값·SQL 포함 가능)는 남기지 않고 종류·단계만 남긴다.
    """
    from app.preview import player_section_processing as psp

    original = psp.place_final_candidates

    def _no_attempts(**kwargs):
        bundle = original(**kwargs)
        object.__setattr__(bundle, "attempts", ())
        return bundle

    monkeypatch.setattr(psp, "place_final_candidates", _no_attempts)
    transport = _transport()
    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=0,
            transport=transport,
            reader=_StubReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()
        from app.preview.models import PreviewRun

        detail = session.get(PreviewRun, outcome.run_id).failure_detail

    assert outcome.status == RunStatus.FAILED
    assert "section_players" in (outcome.unavailable_reason or "")
    # 단계 라벨은 세부 단계를 단정하지 않는 전체 섹션 실행 이름이다.
    assert "ContractError@section_execution" in (detail or "")
    assert "section_write" not in (detail or "")
    # 원문 메시지·자격 증명은 실행 기록에 남기지 않는다.
    assert "postgres" not in (detail or "").lower()
    assert "treat" not in (detail or "")


def test_collection_failure_detail_carries_no_sql_rows_or_credentials():
    """진단은 구조 정보만 남기고 SQL·행 값·자격 증명을 담지 않는다.

    검사 이유(실패 시 사용자 영향): 실제 DB 예외 본문에는 SQL, 바인딩 파라미터, 실패한 행
    값(선수 실명 등)이 여러 줄로 들어 있다. 진단은 관리자 조회로 그대로 노출되므로
    자유 문구를 넣으면 개인정보·테이블 구조가 새고, 첫 줄 절단으로는 막을 수 없다
    (검토 CF-REVIEW 지적 2).
    """
    import json

    class _NotNullViolation(Exception):
        pgcode = "23502"

    exc = _NotNullViolation(
        'null value in column "candidate_name_ko" violates not-null constraint\n'
        "DETAIL:  Failing row contains (7f3a, 2199, 김민재, 2026-11-19).\n"
        "[SQL: INSERT INTO preview_dev.preview_player_name_candidates ...]\n"
        "[parameters: ('7f3a', 2199, '김민재')]"
    )

    detail = bundle_pipeline._collection_failure_detail(exc, stage="save")
    blob = json.dumps(detail, ensure_ascii=False)

    # 누출 금지: 행 값(실명), SQL, 파라미터, DSN 형태.
    assert "김민재" not in blob
    assert "INSERT INTO" not in blob
    assert "parameters:" not in blob
    assert "Failing row" not in blob
    # 원문을 reason에 넣지 않고, 고정 설명만 쓴다.
    assert detail["reason"] == "정보 원문 묶음 검증·저장 중 실패했습니다."
    # 식별에 필요한 구조 정보는 남는다.
    assert detail["error_kind"] == "_NotNullViolation"
    assert detail["sqlstate"] == "23502"
    assert detail["stage"] == "save"
    assert detail["cause_kind"] is None  # SQLAlchemy 계열이 아니므로 분류 없음


def test_collection_failure_detail_separates_contract_violation_from_write_failure():
    """저장 안의 계약 검증 실패는 쓰기 실패와 다른 원인으로 구분된다."""
    from app.preview.information_bundle import BundleBuildError

    detail = bundle_pipeline._collection_failure_detail(
        BundleBuildError("출처 ID가 중복됩니다: src-1"), stage="save"
    )

    assert detail["cause_kind"] == "contract_violation"
    assert "src-1" not in detail["reason"]
    assert "계약 검증에서 거부" in detail["reason"]


def test_collection_failure_detail_records_real_utc_time_not_the_fixed_moment():
    """발생 시각은 실제 UTC 시각이며 고정 실행 기준시각이 아니다."""
    from datetime import datetime, timezone

    fixed_moment = datetime(2026, 11, 18, 19, 5, 55, tzinfo=timezone.utc)
    detail = bundle_pipeline._collection_failure_detail(
        RuntimeError("x"), stage="collect", at=fixed_moment
    )

    parsed = datetime.fromisoformat(detail["at"])
    assert parsed.tzinfo is not None
    assert parsed.utcoffset() == timezone.utc.utcoffset(None)
    # 기본값은 실제 현재 시각이다(고정 moment가 아니다).
    live = bundle_pipeline._collection_failure_detail(RuntimeError("x"), stage="collect")
    assert datetime.fromisoformat(live["at"]) > datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_commit_stage_is_reported_when_commit_raises(session_factory):
    """commit에서 난 예외는 stage=commit으로 남아 수집 실패와 구분된다.

    검사 이유(실패 시 사용자 영향): 하나의 try가 입력복원·수집·저장·commit을 모두
    감싸므로 단계 표시가 없으면 "네트워크 실패"와 "저장 확정 실패"가 같은 진단으로 보여
    원인을 좁힐 수 없다(검토 CF-REVIEW 지적 1). 노드가 실제로 그 단계를 표시하는지 본다.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.preview import bundle_pipeline as bp
    from app.preview.contracts import (
        Environment,
        ExecutionContext,
        FixtureIdentity,
        OperationKind,
        RunMode,
    )
    from app.preview.retry import RunBudget

    class _CommitBoom:
        """commit에서만 예외를 내는 세션 대역(수집·저장은 통과)."""

        def __init__(self):
            self.committed = False
            self.rolled_back = False

        def commit(self):
            raise RuntimeError("commit failed")

        def rollback(self):
            self.rolled_back = True

        def close(self):
            pass

    session = _CommitBoom()
    moment = datetime(2026, 11, 18, 19, 5, 55, tzinfo=timezone.utc)
    plan = bp._Plan(
        run_id=_uuid.uuid4(),
        context=ExecutionContext(
            run_id=_uuid.uuid4(),
            operation_kind=OperationKind.PREVIEW,
            environment=Environment.DEV,
            mode=RunMode.LIVE,
            actor_id=0,
            config_version="test-config",
        ),
        mode=RunMode.LIVE,
        identity=FixtureIdentity(
            fixture_id=1557474,
            league_id=1,
            season=2026,
            home_team_id=13,
            away_team_id=4,
            kickoff_at=moment,
        ),
        fixture={"fixture_id": 1557474},
        actor_id=0,
        moment=moment,
        budget=RunBudget.for_generation(("section_players",), now=moment),
        transport=object(),
        reader=None,
        http=object(),
        target_checker=None,
        session_factory=lambda: session,
        home_team="Manchester City",
        away_team="Fulham",
        league="Premier League",
        db_context=None,
    )

    # 수집과 저장은 성공하도록 최소 대역을 세운다(이 검사의 관심은 commit 단계 표시).
    original_collect = bp.retrieval.collect_with_bodies
    original_save = bp.store.save_information_bundle_with_bodies
    try:
        bp.retrieval.collect_with_bodies = lambda **kwargs: type(
            "C", (), {"diagnostics": ()}
        )()
        bp.store.save_information_bundle_with_bodies = lambda *a, **k: {"bundle": {"bundle_id": "b"}}
        result = bp._collection_node(plan)(
            {"discovery": [], "db_snapshot": None, "diagnostics": [], "completed": []}
        )
    finally:
        bp.retrieval.collect_with_bodies = original_collect
        bp.store.save_information_bundle_with_bodies = original_save

    assert session.rolled_back is True
    assert result["bundle"] is None
    assert result["collection_failure"]["stage"] == "commit"
    assert "commit" in result["collection_failure"]["reason"]


def test_provider_odds_uses_its_own_share_after_articles_are_exhausted():
    """기사가 자기 몫 20회를 다 써도 제공자 배당 읽기는 예산 때문에 막히지 않는다.

    검사 이유(실패 시 사용자 영향): 이전에는 기사 수집이 단일 예산을 소진하면 배당
    요청이 나가지 못했다. 배당은 자기 보호 몫으로 판정받아야 한다.
    """
    from datetime import datetime, timezone

    from app.preview import bundle_pipeline as bp
    from app.preview.retry import (
        HTTP_OWNER_ARTICLES,
        HTTP_OWNER_ODDS,
        HTTP_LOCAL_SHARE,
        RunBudget,
    )

    moment = datetime(2026, 11, 18, 19, 5, tzinfo=timezone.utc)
    budget = RunBudget.for_generation(("section_odds",), now=moment)
    # 기사가 자기 몫을 모두 쓴다.
    for _ in range(HTTP_LOCAL_SHARE * 2):
        assert budget.http_charge(HTTP_OWNER_ARTICLES, now=moment)[0] is True

    from app.preview.sources import provider_odds as provider_odds_module

    sent_calls: list[int] = []
    original = provider_odds_module.read_provider_odds
    try:
        provider_odds_module.read_provider_odds = lambda *, fixture_id, collected_at: (
            sent_calls.append(fixture_id)
            or provider_odds_module.ProviderOddsResult(sent=1, reason=None)
        )
        bp._provider_odds_for({"fixture_id": 1557474}, budget=budget, moment=moment)
    finally:
        provider_odds_module.read_provider_odds = original

    # 배당 요청이 실제로 나갔고(막히지 않았고) 자기 몫에서 차감됐다.
    assert sent_calls == [1557474]
    assert budget.http_owner_used(HTTP_OWNER_ODDS) == 1
