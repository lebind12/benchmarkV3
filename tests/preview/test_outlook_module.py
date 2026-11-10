"""MP-07 R3 배당·외부 전망 조사 검사.

계획 §6 MP-07의 대표 검사:

- `test_pre_match_market_not_qualification`: 컵대회 진출·라이브·다른 시장 배당이
  경기 전 승무패 1X2로 둔갑하지 않는다.
- `test_other_fixture_odds_rejected`: 다른 경기의 배당이 이 경기 승무패로 쓰이지 않는다.
- `test_api_prediction_not_media_opinion`: 제공자 알고리즘 예측이 매체 의견과 다른
  claim 종류로 남고, 매체 전망 문단에 섞이지 않는다.
- `test_missing_media_uses_api_without_fabrication`: 검색 근거가 없어도 배당·제공자
  예측으로 본문을 만들며, 없는 매체·스코어·URL을 만들지 않는다.
- `test_grounding_metadata_missing_is_visible_in_admin`: grounding 메타데이터 부재가
  관리자 기록(coverage·diagnostics·payload)에는 보이고 독자 본문에는 없다.

모든 모델 응답은 녹화 자료(`tests/preview/fixtures/outlook.json`)와 모의 transport로
재현한다. 실제 모델·API 호출은 없다. 이 파일은 live 성공을 주장하지 않는다.
"""

from __future__ import annotations

import json
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.preview import artifacts as artifact_store
from app.preview import provider, store
from app.preview.contracts import (
    ClaimKind,
    CoverageState,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    ModuleInput,
    OperationKind,
    QualityStatus,
    RunMode,
    RunStatus,
    compute_input_hash,
)
from app.preview.modules import outlook
from app.preview.retry import BudgetLimits, RunBudget

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "outlook.json").read_text(encoding="utf-8")
)

FIXTURE = FixtureIdentity(
    fixture_id=1200001,
    league_id=39,
    season=2026,
    home_team_id=50,
    away_team_id=49,
    kickoff_at=datetime(2026, 11, 12, 20, 0, tzinfo=timezone.utc),
)
MOMENT = datetime(2026, 11, 10, 16, 0, tzinfo=timezone.utc)


def _context(*, mode: RunMode = RunMode.LIVE) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=mode,
        actor_id=11,
        config_version="mp07-test",
        limits=ExecutionLimits(model_requests=8, attempts_per_call=3),
    )


def _module_input() -> ModuleInput:
    return ModuleInput(
        module_id=outlook.MODULE_ID,
        fixture=FIXTURE,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash(
            {"fixture": FIXTURE.to_dict(), "implementation": outlook.IMPLEMENTATION_VERSION}
        ),
        prompt_version=outlook.PROMPT_VERSION,
        contract_version="mp02-module-input-1",
        implementation_version=outlook.IMPLEMENTATION_VERSION,
    )


def _prepare_run(session, context: ExecutionContext) -> None:
    store.store_run(
        session, context, fixture=FIXTURE, label="R3 검사", status=RunStatus.RUNNING
    )


def _response(
    *,
    text: str,
    grounding: bool,
    attempt_id: uuid.UUID | None = None,
    http_status: int = 200,
) -> provider.TransportResult:
    """녹화 모양의 모델 응답. grounding 유무를 실제 필드 구조로 나눈다."""
    source = (
        FIXTURES["model_response_grounded"]
        if grounding
        else FIXTURES["model_response_without_grounding"]
    )
    raw = json.loads(json.dumps(source))
    raw["candidates"][0]["content"]["parts"] = [{"text": text}]
    if attempt_id is not None:
        raw["recorded_attempt_id"] = str(attempt_id)
    return provider.TransportResult(
        http_status=http_status,
        raw_request={
            "contents": [{"role": "user", "parts": [{"text": "R3 조사"}]}],
            "generation_config": outlook.build_generation_config(),
        },
        raw_response=raw,
        provider_request_id=raw.get("response_id"),
        usage={
            "input_tokens": raw.get("usage_metadata", {}).get("prompt_token_count"),
            "output_tokens": raw.get("usage_metadata", {}).get("candidates_token_count"),
            "search_queries": None,
        },
        duration_ms=1234,
    )


def _json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _recorded_transport(script, mode: RunMode = RunMode.LIVE) -> provider.RecordedTransport:
    # 이 기록이 무엇을 대신하는지 밝힌다. 네트워크를 열지 않으므로 transport의 실행
    # 방식이 외부 호출 수의 기준이며, mock으로 표기하면 live로 세지 않는다.
    return provider.RecordedTransport(script=script, mode=mode)


def _research(
    session,
    *,
    transport=None,
    mode: RunMode = RunMode.LIVE,
    d0=None,
    budget: RunBudget | None = None,
):
    context = _context(mode=mode)
    _prepare_run(session, context)
    return outlook.research_outlook(
        session,
        context=context,
        module_input=_module_input(),
        transport=transport,
        budget=budget or RunBudget.for_run(now=MOMENT),
        actor_id=11,
        d0=d0,
        now=MOMENT,
        sleeper=lambda seconds: None,
    )


def _d0(*, odds=None, prediction=None) -> dict:
    return {
        "odds_raw": odds if odds is not None else FIXTURES["odds_sample"],
        "prediction_raw": (
            prediction if prediction is not None else FIXTURES["predictions_sample"]
        ),
    }


# --------------------------------------------------------------------------
# 대표 검사 1: 경기 전 승무패가 아닌 시장
# --------------------------------------------------------------------------


def test_pre_match_market_not_qualification(session_factory):
    """컵대회 진출·라이브·더블찬스 배당은 이 경기의 1X2 배당이 아니다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        # 채택된 배당은 경기 전 승무패 두 건(업체 두 곳)뿐이다.
        assert [item.market for item in result.odds] == ["Match Winner", "Match Winner"]
        assert [item.bookmaker for item in result.odds] == [
            "Recorded Book A",
            "Recorded Book B",
        ]
        # 라이브·진출·더블찬스는 제외 목록에 이유와 함께 남는다.
        rejected_markets = {item.market for item in result.rejected_odds}
        assert "Match Winner (Live)" in rejected_markets
        assert "To Qualify" in rejected_markets
        assert "Double Chance" in rejected_markets
        # 라이브 배당 값이 1X2 배당으로 새지 않는다.
        adopted_home = {item.home for item in result.odds}
        assert "1.10" not in adopted_home
        assert "1.22" not in adopted_home
        # 제외 사유가 관리자 기록에 남는다.
        reasons = " ".join(
            item.rejection_reason or "" for item in result.rejected_odds
        )
        assert "경기 전 승무패" in reasons or "라이브" in reasons
        # 독자 본문에는 제외·누락 안내가 없다.
        body = outlook.compose_outlook_body(result)
        assert "To Qualify" not in body
        assert "제외" not in body


# --------------------------------------------------------------------------
# 대표 검사 2: 다른 경기 배당
# --------------------------------------------------------------------------


def test_other_fixture_odds_rejected(session_factory):
    """다른 경기의 배당은 이 경기 승무패로 쓰이지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(odds=FIXTURES["odds_other_fixture"]),
        )
        session.commit()

        assert result.odds == ()
        assert len(result.rejected_odds) == 1
        assert "999999" in (result.rejected_odds[0].rejection_reason or "")
        # 배당 근거가 없으니 본문에도 배당 문단이 없다.
        body = outlook.compose_outlook_body(result)
        assert outlook.ODDS_SECTION_TITLE not in body
        odds_coverage = next(
            entry for entry in result.coverage if entry.topic == outlook.TOPIC_ODDS
        )
        assert odds_coverage.state is CoverageState.VALIDATION_REJECTED


def test_stale_odds_rejected(session_factory):
    """갱신 시각이 오래된 배당은 최신 배당으로 승격하지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(odds=FIXTURES["odds_stale"]),
        )
        session.commit()

        assert result.odds == ()
        assert "시간" in (result.rejected_odds[0].rejection_reason or "")


# --------------------------------------------------------------------------
# 대표 검사 3: API 예측과 매체 의견의 구분
# --------------------------------------------------------------------------


def test_api_prediction_not_media_opinion(session_factory):
    """제공자 알고리즘 예측은 매체 의견과 다른 claim 종류·다른 문단으로 남는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        api_claims = [
            claim for claim in result.claims if claim.kind is ClaimKind.API_PREDICTION
        ]
        media_claims = [
            claim
            for claim in result.claims
            if claim.kind is ClaimKind.EXTERNAL_FORECAST
            and claim.source_url
            and claim.decision.value == "adopted"
        ]
        assert len(api_claims) == 1
        assert media_claims
        # API 예측 claim은 매체 URL을 갖지 않는다.
        assert api_claims[0].source_url is None
        assert "매체 의견" in (api_claims[0].decision_reason or "")
        assert "아닙니다" in (api_claims[0].decision_reason or "")

        body = outlook.compose_outlook_body(result)
        api_index = body.find(outlook.API_SECTION_TITLE)
        media_index = body.find(outlook.MEDIA_SECTION_TITLE)
        assert api_index > 0 and media_index > 0
        # 두 문단이 분리돼 있고, API 문단이 매체 문단 뒤에 온다.
        assert media_index < api_index
        api_block = body[api_index:]
        media_block = body[media_index:api_index]
        assert "55%" in api_block
        assert "55%" not in media_block
        # API 예측 숫자가 매체 보도인 것처럼 쓰이지 않는다.
        assert "매체" not in api_block.split("\n")[0] or "아니라" in api_block

        # 근거 목록에서도 종류가 갈린다.
        kinds = [item["kind"] for item in outlook.compose_outlook_sources(result)]
        assert "media" in kinds and "api_prediction" in kinds and "bookmaker" in kinds


# --------------------------------------------------------------------------
# 대표 검사 4: 검색 근거가 없을 때 API 보완
# --------------------------------------------------------------------------


def test_missing_media_uses_api_without_fabrication(session_factory):
    """검색 근거가 없어도 배당·제공자 예측으로 본문을 만들고, 없는 것을 만들지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        assert result.media == ()
        assert result.odds and result.api_prediction is not None
        assert result.quality is QualityStatus.READY

        body = outlook.compose_outlook_body(result)
        assert outlook.ODDS_SECTION_TITLE in body
        assert outlook.API_SECTION_TITLE in body
        # 매체 전망이 없으면 문단도 만들지 않는다(빈 제목 금지).
        assert outlook.MEDIA_SECTION_TITLE not in body
        # URL·스코어를 만들지 않는다.
        assert "http" not in body
        assert "예상 스코어" not in body

        media_coverage = next(
            entry for entry in result.coverage if entry.topic == outlook.TOPIC_MEDIA
        )
        assert media_coverage.state is CoverageState.SEARCH_NOT_FOUND


def test_transport_absent_still_composes_from_api_only(session_factory):
    """전송 계층이 없으면 호출하지 않고, 확보한 API 근거만으로 본문을 만든다."""
    with session_factory() as session:
        result = _research(session, transport=None, d0=_d0())
        session.commit()

        assert result.external_calls == 0
        assert result.model_text is None
        assert result.odds and result.api_prediction is not None
        body = outlook.compose_outlook_body(result)
        assert body
        assert outlook.MEDIA_SECTION_TITLE not in body
        media_coverage = next(
            entry for entry in result.coverage if entry.topic == outlook.TOPIC_MEDIA
        )
        assert media_coverage.state is CoverageState.NOT_RUN
        assert "주입되지 않아" in (media_coverage.detail or "")


def test_no_sources_at_all_makes_no_body(session_factory):
    """근거가 하나도 없으면 본문을 만들지 않는다. 빈 카드·안내 문장을 만들지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(odds={"errors": [], "response": []}, prediction={"errors": [], "response": []}),
        )
        session.commit()

        assert outlook.compose_outlook_body(result) == ""
        assert outlook.compose_outlook_sources(result) == ()
        assert result.quality is QualityStatus.INSUFFICIENT
        # 진단에는 사유가 남는다.
        assert result.diagnostics


# --------------------------------------------------------------------------
# 대표 검사 5: grounding 메타데이터 부재의 관리자 노출
# --------------------------------------------------------------------------


def test_grounding_metadata_missing_is_visible_in_admin(session_factory):
    """grounding 부재는 관리자 기록에 보이고, 독자 본문에는 나타나지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [
                    _response(
                        text=_json_text(FIXTURES["model_answer_without_grounding"]),
                        grounding=False,
                    )
                ]
            ),
            d0=_d0(),
        )
        session.commit()

        # 매체 전망은 출처를 확인할 수 없어 채택하지 않는다.
        assert result.media == ()
        assert result.rejected_media
        assert "grounding" in (result.rejected_media[0].rejection_reason or "")
        # 관리자 쪽에는 부재 사실이 남는다.
        assert result.grounding.present is False
        assert result.grounding.absence_reason
        search_coverage = next(
            entry for entry in result.coverage if entry.topic == outlook.TOPIC_SEARCH
        )
        assert search_coverage.state is CoverageState.UNKNOWN
        assert result.diagnostics
        # 저장 payload에도 관리자용으로 남는다.
        payload = result.to_dict()
        assert payload["grounding"]["present"] is False
        assert payload["grounding"]["absence_reason"]

        # 독자 본문에는 어떤 누락·오류 안내도 없다.
        body = outlook.compose_outlook_body(result)
        assert "grounding" not in body.lower()
        assert "누락" not in body
        assert "실패" not in body
        assert "미확보" not in body
        assert outlook.MEDIA_SECTION_TITLE not in body
        # 매체 전망을 만들지 않았으므로 URL도 없다.
        assert "http" not in body


def test_grounding_metadata_is_preserved_for_admin(session_factory):
    """실제 grounding 출처·검색 질의·Search Suggestions를 그대로 보존한다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        assert result.grounding.present is True
        assert result.grounding.web_search_queries
        assert "https://recorded-football.test/preview/1200001" in (
            result.grounding.chunk_uris
        )
        assert result.grounding.search_suggestions_html
        assert result.grounding.supports
        stored = result.to_dict()["grounding"]
        assert stored["chunk_uris"]
        assert stored["search_suggestions_html"]


# --------------------------------------------------------------------------
# 매체 전망 검증과 스코어 창작 금지
# --------------------------------------------------------------------------


def test_media_url_must_exist_in_grounding(session_factory):
    """검색 출처에 없는 주소를 매체 전망으로 채택하지 않는다."""
    answer = {
        "media_forecasts": [
            {
                "publisher": "Invented Desk",
                "url": "https://not-in-grounding.test/made-up",
                "published_at": "2026-11-10",
                "statement": "이 기사는 검색 결과에 없다.",
            }
        ],
        "search_note": "없는 주소.",
    }
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport([_response(text=_json_text(answer), grounding=True)]),
            d0=_d0(),
        )
        session.commit()

        assert result.media == ()
        assert result.rejected_media
        assert "확인하지 못해" in (result.rejected_media[0].rejection_reason or "")
        assert "not-in-grounding" not in outlook.compose_outlook_body(result)


def test_predicted_score_without_statement_is_dropped(session_factory):
    """인용문에 없는 예상 스코어는 비운다. 스코어를 만들어 채우지 않는다."""
    answer = {
        "media_forecasts": [
            {
                "publisher": "Recorded Football Desk",
                "url": "https://recorded-football.test/preview/1200001",
                "published_at": "2026-11-10",
                "statement": "홈팀이 우세하다고 봤다.",
                "predicted_score": "3-0",
            }
        ],
        "search_note": "스코어 없이 인용.",
    }
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport([_response(text=_json_text(answer), grounding=True)]),
            d0=_d0(),
        )
        session.commit()

        assert len(result.media) == 1
        assert result.media[0].predicted_score is None
        assert result.media[0].source_confirmed is True
        body = outlook.compose_outlook_body(result)
        assert "3-0" not in body
        assert "예상 스코어" not in body


def test_recorded_score_is_kept_when_the_source_states_it(session_factory):
    """출처가 스코어를 적었으면 그대로 쓴다(지어내지 않되 있는 값은 보존)."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        scored = [item for item in result.media if item.predicted_score]
        assert len(scored) == 1
        assert scored[0].predicted_score == "2-1"
        assert "2-1" in scored[0].statement
        assert "2-1" in outlook.compose_outlook_body(result)


# --------------------------------------------------------------------------
# 실행 경계: 호출 수, 예산, 재생, 모의
# --------------------------------------------------------------------------


def test_single_model_call_per_research(session_factory):
    """정상 경로의 모델 호출은 1회이며 공통 예산을 통과한다."""
    transport = _recorded_transport(
        [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
    )
    with session_factory() as session:
        budget = RunBudget.for_run(BudgetLimits(normal_model_calls=1), now=MOMENT)
        result = _research(
            session, transport=transport, d0=_d0(), budget=budget
        )
        session.commit()

        assert len(transport.calls) == 1
        assert result.attempt_summary["attempt_count"] == 1
        assert result.external_calls == 1
        assert budget.snapshot()["model_used"] == 1
        # 요청 설정이 Google Search grounding을 포함한다.
        sent = transport.calls[0]
        assert sent.parameters["generation_config"]["tools"] == [{"google_search": {}}]


def test_mock_mode_is_not_counted_as_live_call(session_factory):
    """모의 실행은 모델을 실제로 부르지 않고 live 호출로 세지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            # 모의 실행은 모의로 표기한 transport를 쓴다. 표기를 live로 두면 기록된
            # 응답이어도 실제 전송으로 세게 되므로, 무엇을 대신하는지 값으로 밝힌다.
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)],
                mode=RunMode.MOCK,
            ),
            mode=RunMode.MOCK,
            d0=_d0(),
        )
        session.commit()

        assert result.external_calls == 0
        assert result.mode is RunMode.MOCK
        # 모의 실행의 본문도 배당·예측 근거로는 만들어진다.
        assert result.odds and result.api_prediction is not None


def test_replay_opens_no_socket(session_factory, monkeypatch):
    """재생 transport는 네트워크를 열지 않는다."""
    def _deny(*args, **kwargs):
        raise AssertionError("R3 research must not open an outbound connection")

    monkeypatch.setattr(socket.socket, "connect", _deny)

    recorded = _response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)
    with session_factory() as session:
        result = _research(
            session,
            transport=provider.ReplayTransport(stored=recorded),
            mode=RunMode.REPLAY,
            d0=_d0(),
        )
        session.commit()

        assert result.external_calls == 0
        assert result.media  # 저장 응답으로 변환은 다시 한다
        assert result.mode is RunMode.REPLAY


def test_model_failure_keeps_api_body_and_records_reason(session_factory):
    """호출이 실패해도 배당·제공자 예측 근거로 본문을 만들고 실패는 관리자에 남긴다."""
    failure = provider.TransportResult(
        http_status=429,
        raw_request={"contents": "요청"},
        raw_response={"error": {"code": 429, "message": "rate limited"}},
        error_class="rate_limited",
        error_message="rate limited",
        retry_after_seconds=1.0,
    )
    with session_factory() as session:
        budget = RunBudget.for_run(BudgetLimits(attempts_per_call=1), now=MOMENT)
        result = _research(
            session,
            transport=_recorded_transport([failure]),
            d0=_d0(),
            budget=budget,
        )
        session.commit()

        assert result.media == ()
        # 429로 끝난 시도도 실제로 전송된 호출이다. 성공 여부로 0으로 만들지 않는다.
        assert result.external_calls == 1
        body = outlook.compose_outlook_body(result)
        assert body and outlook.ODDS_SECTION_TITLE in body
        assert "rate limited" not in body
        media_coverage = next(
            entry for entry in result.coverage if entry.topic == outlook.TOPIC_MEDIA
        )
        assert media_coverage.state is CoverageState.CALL_ERROR
        assert result.attempt_summary["http_status"] == 429


def test_retried_live_call_counts_every_sent_attempt(session_factory):
    """429 뒤 성공하면 두 번 나갔으므로 2회로 센다. 마지막 시도 기준이 아니다."""
    failure = provider.TransportResult(
        http_status=429,
        raw_request={"contents": "요청"},
        raw_response={"error": {"code": 429, "message": "rate limited"}},
        error_class="rate_limited",
        error_message="rate limited",
        retry_after_seconds=0.0,
    )
    success = _response(
        text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True
    )
    with session_factory() as session:
        budget = RunBudget.for_run(BudgetLimits(attempts_per_call=3), now=MOMENT)
        result = _research(
            session,
            transport=_recorded_transport([failure, success]),
            d0=_d0(),
            budget=budget,
        )
        session.commit()

        assert result.attempt_summary["attempt_count"] == 2
        assert result.attempt_summary["outcomes"] == ["error", "ok"]
        # 실제로 나간 호출은 2회다. 성공한 마지막 시도만 세지 않는다.
        assert result.external_calls == 2
        assert result.attempt_summary["sent_attempts"] == 2
        # 재시도 후 성공했으므로 본문에는 매체 전망이 들어간다.
        assert result.media


def test_configuration_error_is_not_counted_as_a_sent_call(session_factory):
    """설정이 없어 보내지 않은 호출은 기록에 남지만 외부 호출로 세지 않는다."""
    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        result = outlook.research_outlook(
            session,
            context=context,
            module_input=_module_input(),
            transport=provider.GoogleGenAIHttpTransport(
                project=None, location=None, model=None, credentials_json=None
            ),
            budget=RunBudget.for_run(now=MOMENT),
            actor_id=11,
            d0=_d0(),
            now=MOMENT,
            sleeper=lambda seconds: None,
        )
        session.commit()

        # 시도 행은 남아 원인을 보여준다.
        assert result.attempt_summary["attempt_count"] == 1
        assert result.attempt_summary["missing_configuration"]
        # 그러나 요청은 나가지 않았다.
        assert result.external_calls == 0
        # 실패해도 배당·예측 근거로 본문은 만들어진다.
        assert outlook.compose_outlook_body(result)


def test_search_snapshot_is_recorded_for_search_sources(session_factory):
    """검색 근거 스냅샷이 실행에 남는다(출처·시각·원문 참조)."""
    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        result = outlook.research_outlook(
            session,
            context=context,
            module_input=_module_input(),
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
            ),
            budget=RunBudget.for_run(now=MOMENT),
            actor_id=11,
            d0=_d0(),
            now=MOMENT,
            sleeper=lambda seconds: None,
        )
        session.commit()

        detail = store.get_run_detail(session, context.run_id)
        search_sources = [
            source for source in detail.sources if source["source_kind"] == "search"
        ]
        assert search_sources
        assert search_sources[0]["provider"] == "vertex-google-search"
        assert search_sources[0]["collected_at"]
        assert result.media and all(item.source_confirmed for item in result.media)


def test_prompt_asks_for_verified_media_only():
    """프롬프트가 검색 결과 밖의 URL·스코어 창작을 금지한다."""
    prompt = outlook.outlook_prompt(FIXTURE)
    assert "{{CONTEXT}}" not in prompt
    assert "fixture_id 1200001" in prompt
    assert "URL은 검색 결과에 나온 주소를 그대로 쓴다" in prompt
    assert "예상 스코어를 만들지 않는다" in prompt
    assert "베팅 권유를 쓰지 않는다" in prompt


# --------------------------------------------------------------------------
# 노드 통합 계약 (MP-05가 runner에 주입한다)
# --------------------------------------------------------------------------


def test_node_implementation_returns_reader_body_and_claims(session_factory):
    """노드 결과가 runner가 읽는 claims/coverage와 독자 본문을 함께 준다."""
    from app.preview import runner

    implementation = outlook.outlook_node_implementation(
        mode=RunMode.LIVE,
        transport=_recorded_transport(
            [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
        ),
    )
    assert implementation.module_id == outlook.MODULE_ID
    assert implementation.prompt_version == outlook.PROMPT_VERSION
    assert implementation.mode is RunMode.LIVE

    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        module_run = store.start_module_execution(
            session,
            run_id=context.run_id,
            module_id=outlook.MODULE_ID,
            module_input=_module_input(),
            actor_id=11,
        )
        ctx = runner.SectionNodeContext(
            session=session,
            context=context,
            budget=RunBudget.for_run(now=MOMENT),
            workflow_id="section_outlook",
            workflow_version="v1",
            fixture=FIXTURE.to_dict(),
            mode=RunMode.LIVE,
            transport=None,
            actor_id=11,
            module_execution_id=module_run.id,
        )
        outcome = implementation.run(ctx, {"fixture": FIXTURE.to_dict(), "data": _d0()})
        session.commit()

        assert outcome.body and outlook.ROOT_TITLE in outcome.body
        assert outcome.payload["claims"]
        assert outcome.payload["coverage"]
        assert outcome.payload["reader_body"] == outcome.body
        assert outcome.payload["reader_sources"]
        assert outcome.payload["outlook"]["odds"]
        assert outcome.external_calls == 1
        # 본문은 관리자 진단 문장을 담지 않는다.
        assert "grounding" not in outcome.body.lower()
        assert "미확보" not in outcome.body


def test_node_implementation_reports_unavailable_without_evidence(session_factory):
    """근거가 없으면 본문을 만들지 않고 사용할 수 없음을 그대로 알린다."""
    from app.preview import runner

    implementation = outlook.outlook_node_implementation(
        mode=RunMode.LIVE,
        transport=_recorded_transport(
            [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
        ),
    )
    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        module_run = store.start_module_execution(
            session,
            run_id=context.run_id,
            module_id=outlook.MODULE_ID,
            module_input=_module_input(),
            actor_id=11,
        )
        ctx = runner.SectionNodeContext(
            session=session,
            context=context,
            budget=RunBudget.for_run(now=MOMENT),
            workflow_id="section_outlook",
            workflow_version="v1",
            fixture=FIXTURE.to_dict(),
            mode=RunMode.LIVE,
            transport=None,
            actor_id=11,
            module_execution_id=module_run.id,
        )
        outcome = implementation.run(
            ctx,
            {
                "fixture": FIXTURE.to_dict(),
                "data": {"odds_raw": {"errors": [], "response": []},
                         "prediction_raw": {"errors": [], "response": []}},
            },
        )
        session.commit()

        assert outcome.body is None
        assert outcome.unavailable_reason
        assert outcome.quality is QualityStatus.INSUFFICIENT


def test_reader_body_does_not_mention_absent_parts(session_factory):
    """매체 전망이 없으면 소개 문장도 매체 전망을 언급하지 않는다."""
    with session_factory() as session:
        result = _research(
            session,
            transport=_recorded_transport(
                [_response(text=_json_text(FIXTURES["model_answer_empty"]), grounding=True)]
            ),
            d0=_d0(),
        )
        session.commit()

        body = outlook.compose_outlook_body(result)
        lead = body.split("\n\n")[1]
        # 없는 자료를 소개하지 않는다. 제공자 예측이 매체 의견과 다르다는 설명은 남는다.
        assert "외부 매체 전망" not in lead
        assert "배당" in lead
        # 본문 전체에서도 매체 전망 문단 자체가 없다.
        assert outlook.MEDIA_SECTION_TITLE not in body


def test_compose_outlook_section_returns_body_and_sources(session_factory):
    """compose_body 노드가 부를 진입점이 본문·근거·품질을 그대로 돌려준다."""
    from app.preview.modules import outlook as outlook_module

    transport = _recorded_transport(
        [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
    )
    with session_factory() as session:
        result = _research(session, transport=transport, d0=_d0())
        session.commit()

        payload = {
            "claims": [claim.to_dict() for claim in result.claims],
            "coverage": [entry.to_dict() for entry in result.coverage],
            "outlook": result.to_dict(),
            "reader_body": result.reader_body,
            "reader_sources": [dict(item) for item in result.reader_sources],
        }
        section = outlook_module.compose_outlook_section(payload)
        assert section.body == result.reader_body
        assert section.sources == result.reader_sources
        assert section.quality is QualityStatus.READY
        assert section.unavailable is False

        # 근거가 없는 결과는 빈 본문과 사유를 돌려준다(빈 본문을 성공으로 만들지 않음).
        empty = outlook_module.compose_outlook_section({"reader_body": "", "outlook": {}})
        assert empty.body == ""
        assert empty.quality is QualityStatus.INSUFFICIENT
        assert empty.unavailable_reason


# --------------------------------------------------------------------------
# 섹션 워크플로우 전체 (사용자 테스트 단위)
# --------------------------------------------------------------------------


def test_section_workflow_produces_reader_body_and_sources(session_factory):
    """prepare→research→compose→finalize 전체가 실제 본문·근거를 만든다.

    이 검사는 사용자 테스트 단위가 **섹션 워크플로우**임을 코드로 확인한다. R3 노드는
    그 안의 조사 단계 하나이며, 승인 근거는 이 실행이 남기는 섹션 결과다. 모델 응답은
    녹화 자료라 실제 생성 증거가 아니다.
    """
    from app.preview import runner
    from app.preview.contracts import QualityStatus as RunnerQuality

    implementation = outlook.outlook_node_implementation(
        mode=RunMode.LIVE,
        transport=_recorded_transport(
            [_response(text=_json_text(FIXTURES["model_answer_grounded"]), grounding=True)]
        ),
    )

    def prepare(ctx, state):
        # D0 대신 저장된 배당·예측 원문을 넘긴다. 새 API 호출은 없다.
        return runner.NodeOutcome(
            payload={
                "claims": [],
                "coverage": [],
                "odds_raw": FIXTURES["odds_sample"],
                "prediction_raw": FIXTURES["predictions_sample"],
            }
        )

    def compose(ctx, state):
        research = (state.get("research") or {}).get(outlook.MODULE_ID) or {}
        body = research.get("reader_body") or ""
        # research 단계가 이미 state["sources"]에 근거를 넣었다. compose에서 또 넣으면
        # 같은 근거가 두 번 저장된다. 그래서 여기서는 비운다.
        return runner.NodeOutcome(
            title=outlook.ROOT_TITLE,
            body=body,
            sources=(),
            quality=RunnerQuality(
                research.get("outlook", {}).get("quality", "insufficient")
            ),
        )

    implementations = runner.WorkflowImplementations(
        prepare_data=runner.NodeImplementation(
            module_id="D0",
            implementation_version="test-d0",
            prompt_version=None,
            mode=RunMode.LIVE,
            run=prepare,
        ),
        research=(implementation,),
        compose_body=runner.NodeImplementation(
            module_id=runner.COMPOSE_MODULE_ID,
            implementation_version="test-compose",
            prompt_version="test-compose-p1",
            mode=RunMode.LIVE,
            run=compose,
        ),
    )

    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_outlook",
            implementations=implementations,
            actor_id=11,
            fixture=FIXTURE.to_dict(),
            fixture_label="R3 검사 경기",
            now=MOMENT,
        )
        session.commit()

        # 본문이 있고, 노드 진단이 아니라 읽을 수 있는 문장이다.
        assert result.body.strip()
        assert outlook.ROOT_TITLE in result.body
        assert outlook.ODDS_SECTION_TITLE in result.body
        assert outlook.MEDIA_SECTION_TITLE in result.body
        assert outlook.API_SECTION_TITLE in result.body
        # 독자 본문에 운영 메시지가 없다.
        for noise in ("누락", "미확보", "실패", "재시도", "grounding"):
            assert noise not in result.body
        # 근거가 세 종류로 함께 남는다.
        kinds = {item["kind"] for item in result.sources}
        assert {"bookmaker", "media", "api_prediction"} <= kinds
        # 승인 근거는 이 섹션 결과다.
        assert result.section_result_id is not None
        assert result.quality is QualityStatus.READY
        assert result.mode is RunMode.LIVE
        # 노드 순서와 저장 결과를 실행 ID로 다시 연다.
        assert [step["node"] for step in result.step_log] == list(runner.NODE_ORDER)
        stored = store.get_run_detail(session, result.run_id).section_results[0]
        assert stored["body"] == result.body
        assert stored["sources"] == [dict(item) for item in result.sources]
        assert stored["workflow_id"] == "section_outlook"
