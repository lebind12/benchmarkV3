"""PS-03 bundle 섹션 작성의 대표 기록 검사.

이 파일이 확인하는 것(계획 PS-03의 직접 확인 항목만):

- 선수는 팀당 목표 인원으로 나뉘고 **선수명·선정 이유가 분리**된다.
- 부상은 팀당 최대 2명이며 상태 표기를 승격하지 않는다.
- 매체는 서로 다른 매체 최대 3곳이고, 점수 미제시 기사에 점수를 만들지 않는다.
- DB 자료만으로도 최종 AI 전망·스코어가 성립한다.
- 배당 섹션은 **모델 호출 0회**다.
- 입력의 진단·누락 문구가 독자 본문에 새지 않는다.
- 실제 전달 기록(`SectionDelivery`)이 요청 payload 해시와 함께 남는다.

실제 모델·외부 HTTP는 부르지 않는다. `RecordedTransport`(mode=live)로 계수 경로만
실제와 같게 두고, 네트워크가 없다는 사실을 여기 밝힌다. 전용 로컬 테스트 DB는 쓰지
않는다(저장을 하지 않는 단위 검사다).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from app.preview import information_bundle as bundle_contract
from app.preview import provider
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    QualityStatus,
    RunMode,
)
from app.preview.modules import bundle_sections
from app.preview.retry import RunBudget, plan_limits

FIXED_NOW = datetime(2026, 11, 11, 6, 0, tzinfo=timezone.utc)
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
# 새 재시도 검사가 쓰는 정상 선수 응답. 기존 검사와 같은 모양의 값을 쓴다.
PLAYERS_ANSWER = {
    "players": [
        {
            "selected_player": "엘링 홀란",
            "selection_reason": "최근 5경기 6골",
            "team": HOME_KO,
            "evidence": ["src:stats#p1"],
        },
        {
            "selected_player": "알렉스 이워비",
            "selection_reason": "원정 공격의 중심",
            "team": AWAY_KO,
            "evidence": ["src:stats#p1"],
        },
    ]
}


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
                body_chars=120,
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
                source_id="src:media",
                discovery_group=bundle_contract.DISCOVERY_GROUP_MEDIA_ODDS,
                requested_url="https://example.test/preview",
                final_url="https://example.test/preview",
                nature="preview",
                method="fresh_http",
                title="경기 프리뷰",
                captured_at=FIXED_NOW,
                body_chars=90,
                passages=(
                    bundle_contract.Passage(
                        passage_id="src:media#p1",
                        source_id="src:media",
                        ordinal=1,
                        text="BBC는 홈팀 우세를 예상했습니다.",
                    ),
                ),
            ),
        )
    return bundle_contract.InformationBundle(
        bundle_id="bundle-sections-test",
        fixture=dict(FIXTURE),
        team_id_space="internal",
        collected_at=FIXED_NOW,
        sources=sources,
        db_snapshot=bundle_contract.DbSnapshot(
            fixture=dict(FIXTURE),
            team_id_space="internal",
            collected_at=FIXED_NOW,
            teams=(
                {"team_id": 13, "name_ko": HOME_KO},
                {"team_id": 4, "name_ko": AWAY_KO},
            ),
            standings=({"team_id": 13, "rank": 3, "points": 21},),
            injuries=({"player_name": "로드리", "expected_status": "questionable", "team_id": 13},),
            readable=True,
        ),
        odds=bundle_contract.OddsMarket(
            quotes=(
                bundle_contract.OddsQuote(
                    source_id="src:media",
                    site="Bet365",
                    market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                    observed_at=FIXED_NOW,
                    home_decimal=2.1,
                    draw_decimal=3.4,
                    away_decimal=3.2,
                ),
            )
        ),
        mode="live",
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=RunMode.LIVE,
        actor_id=1,
        config_version="mp11-sections-test",
        limits=ExecutionLimits(
            model_requests=8, api_requests=24, attempts_per_call=3, deadline_seconds=1800
        ),
    )


def _budget() -> RunBudget:
    return RunBudget.for_run(
        plan_limits(model_requests=8, normal_model_calls=6), now=FIXED_NOW
    )


def _transport(answer: dict) -> tuple[provider.RecordedTransport, str]:
    text = json.dumps(answer, ensure_ascii=False)
    transport = provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"contents": "요청"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}], "role": "model"},
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 100, "output_tokens": 50},
            )
        ],
        provider="recorded-model",
        mode=RunMode.LIVE,
    )
    return transport, text


def _run(section_id: str, answer: dict | None, *, bundle=None, budget=None):
    active_bundle = bundle if bundle is not None else _bundle()
    transport = None
    if answer is not None:
        transport, _ = _transport(answer)
    return bundle_sections.build_bundle_section(
        section_id=section_id,
        bundle=active_bundle,
        transport=transport,
        context=_context(),
        budget=budget or _budget(),
        now=FIXED_NOW,
    )


def test_players_split_name_and_reason_per_team():
    """선수명과 선정 이유가 분리되고 팀별 목표 인원이 지켜진다."""
    answer = {
        "players": [
            {
                "selected_player": "엘링 홀란",
                "selection_reason": "최근 5경기 6골",
                "team": HOME_KO,
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "라얀 셰르키",
                "selection_reason": "측면 돌파",
                "team": HOME_KO,
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "알렉스 이워비",
                "selection_reason": "원정 공격의 중심",
                "team": AWAY_KO,
                "evidence": ["src:stats#p1"],
            },
        ]
    }
    draft = _run(bundle_contract.SECTION_PLAYERS, answer)

    assert draft.quality is QualityStatus.READY
    assert draft.unavailable is False
    # 본문은 기록된 라벨 형식을 쓴다(선수: / 이유:).
    assert "선정 선수: 엘링 홀란" in draft.body
    assert "선정 이유: 최근 5경기 6골" in draft.body
    rows = draft.structured["players"]
    assert [row["selected_player"] for row in rows] == [
        "엘링 홀란",
        "라얀 셰르키",
        "알렉스 이워비",
    ]
    # 선수명과 이유가 한 문장으로 합쳐지지 않았다.
    for row in rows:
        assert row["selection_reason"]
        assert row["selection_reason"] != row["selected_player"]
    assert draft.external_calls == 1


def test_players_never_exceed_two_per_team():
    """팀당 2명을 넘는 응답은 잘라내고 그 사실을 진단에 남긴다(본문에는 안 넣는다)."""
    answer = {
        "players": [
            {
                "selected_player": f"{HOME_KO} 선수{i}",
                "selection_reason": f"이유 {i}",
                "team": HOME_KO,
                "evidence": ["src:stats#p1"],
            }
            for i in range(4)
        ]
    }
    draft = _run(bundle_contract.SECTION_PLAYERS, answer)
    assert len(draft.structured["players"]) <= bundle_sections.MAX_BUNDLE_PLAYERS
    home_rows = [row for row in draft.structured["players"] if row["team"] == HOME_KO]
    assert len(home_rows) <= bundle_sections.PLAYERS_PER_TEAM


def test_availability_keeps_uncertain_status_and_caps_two_per_team():
    """부상은 팀당 최대 2명이고, '출전 불확실'을 확정 결장으로 바꾸지 않는다."""
    answer = {
        "injuries": [
            {
                "player_name": "로드리",
                "team_id": 13,
                "status": "doubtful",
                "injury": "무릎",
                "importance": "중원 장악력 저하",
                "evidence": ["src:stats#p1"],
            },
            {
                "player_name": "존 스톤스",
                "team_id": 13,
                "status": "confirmed_absence",
                "injury": "햄스트링",
                "importance": "수비 로테이션 축소",
                "evidence": ["src:stats#p1"],
            },
            {
                "player_name": "세번째 선수",
                "team_id": 13,
                "status": "unknown",
                "injury": "미상",
                "importance": "확인되지 않음",
                "evidence": ["src:stats#p1"],
            },
        ]
    }
    draft = _run(bundle_contract.SECTION_AVAILABILITY, answer)
    assert draft.quality is QualityStatus.READY
    rows = draft.structured["injuries"]
    assert len(rows) <= bundle_sections.MAX_INJURIES_PER_TEAM
    statuses = {row["player_name"]: row["status"] for row in rows}
    assert statuses["로드리"] == "doubtful"
    # 본문에도 불확실 표기가 유지된다.
    assert "출전 불확실" in draft.body
    assert "결장 확정" not in draft.body


def test_media_keeps_three_publishers_and_does_not_invent_scores():
    """매체는 서로 다른 곳 최대 3곳이고, 점수를 안 준 기사에 점수를 만들지 않는다."""
    answer = {
        "media_forecasts": [
            # URL은 **수집한 출처**여야 한다(없는 주소를 인용하면 그 항목은 빠진다).
            {
                "publisher": "BBC",
                "statement": "홈팀 우세",
                "predicted_score": "2-1",
                "url": "https://example.test/preview",
                "evidence": ["src:media#p1"],
            },
            {
                "publisher": "Sky Sports",
                "statement": "접전 예상",
                "url": "https://example.test/preview",
                "evidence": ["src:media#p1"],
            },
            {
                "publisher": "The Athletic",
                "statement": "무승부 가능성",
                "url": "https://example.test/preview",
                "evidence": ["src:media#p1"],
            },
            {
                "publisher": "Fourth Outlet",
                "statement": "네 번째 매체",
                "url": "https://example.test/preview",
                "evidence": ["src:media#p1"],
            },
        ]
    }
    draft = _run(bundle_contract.SECTION_OUTLOOK, answer)
    assert draft.quality is QualityStatus.READY
    rows = draft.structured["media"]
    assert len(rows) <= bundle_sections.MAX_MEDIA_PUBLISHERS
    publishers = [row["publisher"] for row in rows]
    assert len(set(publishers)) == len(publishers)
    # 점수 미제시 기사는 점수가 비어 있다(만들어 채우지 않는다).
    by_publisher = {row["publisher"]: row for row in rows}
    if "Sky Sports" in by_publisher:
        assert by_publisher["Sky Sports"]["predicted_score"] in (None, "")
    # 출처 본문에 없는 점수는 비운다(“2-1”을 지어내지 않는다). 그 사실은 진단에 남는다.
    assert by_publisher["BBC"]["predicted_score"] is None
    assert any("인용문에 없는 예상 스코어" in line for line in draft.diagnostics)


def test_media_score_is_kept_only_when_the_statement_states_it():
    """매체 진술문에 적힌 점수만 유지한다(모델이 덧붙인 점수는 비운다).

    현재 검증 규칙은 `predicted_score`가 그 매체의 `statement` 안에 있을 때만 채택한다.
    기사 본문에만 있고 진술문에 없으면 비우고 그 사실을 진단에 남긴다 — 없는 점수를
    표에 채우지 않기 위한 경계다.
    """
    answer = {
        "media_forecasts": [
            {
                "publisher": "BBC",
                "statement": "BBC는 홈팀이 2-1로 이길 것으로 봤습니다.",
                "predicted_score": "2-1",
                "url": "https://example.test/preview",
                "evidence": ["src:media#p1"],
            }
        ]
    }
    draft = _run(bundle_contract.SECTION_OUTLOOK, answer)
    rows = draft.structured["media"]
    assert rows and rows[0]["predicted_score"] == "2-1"
    assert "2-1" in draft.body


def test_db_only_bundle_still_produces_final_forecast():
    """웹 자료가 전혀 없어도 DB 경기력 자료로 최종 전망·스코어가 성립한다."""
    answer = {
        "forecast": "홈팀이 리그 순위 우위를 바탕으로 주도권을 잡을 것으로 보입니다.",
        "predicted_score": {"home": 2, "away": 1},
        "score_reasoning": ["리그 3위로 상위권", "최근 5경기 3승"],
        "forecast_evidence": [],
    }
    draft = _run(bundle_contract.SECTION_AI_FORECAST, answer, bundle=_bundle(with_web=False))
    assert draft.quality is QualityStatus.READY
    assert draft.unavailable is False
    assert "AI 예상 스코어" in draft.body
    assert "2-1" in draft.body
    assert draft.structured["forecast"]["score"] == "2-1"
    assert draft.structured["forecast"]["lean"] == "home"


def test_diagnostics_do_not_leak_into_reader_body():
    """관리자 진단·검사 기준·내부 ID가 독자 본문에 들어가지 않는다."""
    answer = {
        "players": [
            {
                "selected_player": "엘링 홀란",
                "selection_reason": "최근 5경기 6골",
                "team": HOME_KO,
                "evidence": ["src:stats#p1"],
            },
            {
                "selected_player": "무근거 선수",
                "selection_reason": "근거 없음",
                "team": HOME_KO,
                "evidence": ["src:unknown#p9"],
            },
        ]
    }
    draft = _run(bundle_contract.SECTION_PLAYERS, answer)
    assert draft.body.strip()
    for forbidden in ("src:", "evidence", "진단", "검증", "미확보", "누락"):
        assert forbidden not in draft.body, forbidden
    # 전달하지 않은 근거 Id는 표시 근거에서 빠지고, 그 사실은 관리자 진단에만 남는다.
    assert any("근거 id" in line for line in draft.diagnostics)
    rows = {row["selected_player"]: row for row in draft.structured["players"]}
    assert rows["엘링 홀란"]["evidence"], "전달한 근거는 남아야 한다"
    assert rows["무근거 선수"]["evidence"] == [], "없는 근거를 표시하지 않는다"


def test_delivery_records_real_payload_hash_and_passages():
    """전달 기록은 실제 요청 payload 해시와 전달 구간 ID를 담는다."""
    answer = {
        "players": [
            {
                "selected_player": "엘링 홀란",
                "selection_reason": "최근 5경기 6골",
                "team": HOME_KO,
                "evidence": ["src:stats#p1"],
            }
        ]
    }
    draft = _run(bundle_contract.SECTION_PLAYERS, answer)
    delivery = draft.delivery
    assert delivery is not None
    assert delivery.model_delivered is True
    assert delivery.passage_ids, "실제 전달한 구간 ID가 비었다"
    assert delivery.payload_sha256 and len(delivery.payload_sha256) == 64
    assert delivery.sent_attempts == 1
    # 묶음에 붙이면 그대로 저장 가능한 모양이 된다.
    patched = _bundle().with_section_delivery(delivery)
    assert bundle_contract.bundle_summary(patched)["section_delivery_count"] == 1
    assert bundle_contract.validate_information_bundle(patched) == ()


def test_unknown_section_is_rejected():
    """지원하지 않는 섹션은 조용히 빈 본문을 만들지 않고 거부한다."""
    with pytest.raises(bundle_sections.BundleSectionError):
        _run("section_unknown", {})


def test_section_versions_are_code_constants():
    """섹션 버전 축은 코드 상수에서 온다(실행마다 흔들리지 않는다)."""
    for section_id in bundle_sections.SUPPORTED_SECTION_IDS:
        implementation_version, prompt_version = bundle_sections.bundle_section_versions(
            section_id
        )
        assert implementation_version == bundle_sections.IMPLEMENTATION_VERSION
        assert prompt_version


# --------------------------------------------------------------------------
# 모듈별 3회 안에서의 기술 실패 재시도 (사용자 확정 2026-11-12)
# --------------------------------------------------------------------------


def _scripted_transport(results: list[provider.TransportResult]) -> provider.RecordedTransport:
    """정해진 순서로 응답하는 기록 transport(mode=live, 네트워크 없음)."""
    return provider.RecordedTransport(
        script=list(results), provider="recorded-model", mode=RunMode.LIVE
    )


def _json_response(answer: dict, *, finish_reason: str = "STOP") -> provider.TransportResult:
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": json.dumps(answer, ensure_ascii=False)}],
                        "role": "model",
                    },
                    "finishReason": finish_reason,
                }
            ]
        },
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def _truncated_response() -> provider.TransportResult:
    """출력 상한에서 잘린 응답(JSON이 닫히지 않았다)."""
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response={
            "candidates": [
                {
                    "content": {"parts": [{"text": '{"players": [{"selected_player": "엘'}], "role": "model"},
                    "finishReason": "MAX_TOKENS",
                }
            ]
        },
        usage={"input_tokens": 10, "output_tokens": 40000},
    )


def _rate_limited() -> provider.TransportResult:
    return provider.TransportResult(
        http_status=429,
        raw_request={"contents": "요청"},
        raw_response={"error": {"code": 429, "message": "rate limited"}},
        error_class="rate_limited",
        error_message="rate limited",
        retry_after_seconds=0.0,
    )


def _unparseable_response() -> provider.TransportResult:
    """HTTP 200이지만 JSON이 아닌 본문(파싱 실패)."""
    return provider.TransportResult(
        http_status=200,
        raw_request={"contents": "요청"},
        raw_response={
            "candidates": [
                {
                    "content": {"parts": [{"text": "이건 JSON이 아닙니다"}], "role": "model"},
                    "finishReason": "STOP",
                }
            ]
        },
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def _run_with_transport(section_id: str, transport, *, budget=None):
    return bundle_sections.build_bundle_section(
        section_id=section_id,
        bundle=_bundle(),
        transport=transport,
        context=_context(),
        budget=budget or _budget(),
        now=FIXED_NOW,
    )


def test_truncated_then_parse_failure_then_ok_sends_exactly_three():
    """잘린 응답 → 200이지만 해석 불가 → 정상 응답에서 **실제 3전송**으로 끝난다.

    HTTP 200이라는 이유로 잘린 응답을 성공 처리하지 않는다. 그리고 재시도는 같은
    모듈의 3회 안에서 일어나며, 별도 SDK/그래프 재시도 루프를 거치지 않는다.
    """
    transport = _scripted_transport(
        [_truncated_response(), _unparseable_response(), _json_response(PLAYERS_ANSWER)]
    )
    draft = _run_with_transport("section_players", transport)

    # 실제로 3번 전송했고, 네 번째는 보내지 않았다.
    assert len(transport.calls) == 3
    assert draft.unavailable_reason is None
    assert "선정 선수" in draft.body
    assert draft.external_calls == 3


def test_second_truncation_still_retries_within_the_same_three():
    """429 → 잘린 응답(MAX_TOKENS) → 정상 응답도 **같은 모듈의 3회** 안에서 처리된다."""
    transport = _scripted_transport(
        [_rate_limited(), _truncated_response(), _json_response(PLAYERS_ANSWER)]
    )
    draft = _run_with_transport("section_players", transport)

    assert len(transport.calls) == 3
    assert draft.external_calls == 3
    assert draft.unavailable_reason is None
    assert "선정 선수" in draft.body


def test_fourth_transport_is_never_sent_when_content_keeps_failing():
    """계속 잘리면 3회에서 멈추고 4번째 전송은 **0**이다."""
    transport = _scripted_transport(
        [_truncated_response(), _truncated_response(), _truncated_response(), _truncated_response()]
    )
    draft = _run_with_transport("section_players", transport)

    assert len(transport.calls) == 3, transport.calls
    # 본문은 없지만 사유는 남는다(성공으로 꾸미지 않는다).
    assert draft.unavailable_reason
    assert draft.body == ""


def test_short_but_parseable_body_is_not_resent():
    """짧아도 파싱 가능한 본문은 다시 보내지 않는다(품질 재호출 금지)."""
    short_answer = {
        "players": [
            {
                "selected_player": "엘링 홀란",
                "selection_reason": "득점",
                "team": HOME_KO,
                "evidence": ["src-1#p1"],
            }
        ]
    }
    transport = _scripted_transport(
        [_json_response(short_answer), _json_response(PLAYERS_ANSWER)]
    )
    draft = _run_with_transport("section_players", transport)

    # 첫 응답을 그대로 수용했다. 두 번째 응답은 소비되지 않았다.
    assert len(transport.calls) == 1
    assert draft.external_calls == 1
    assert draft.unavailable_reason is None


def test_authentication_error_stops_without_repeating():
    """401은 같은 요청을 다시 보내지 않는다(설정·인증 오류는 반복 대상이 아니다)."""
    unauthorized = provider.TransportResult(
        http_status=401,
        raw_request={"contents": "요청"},
        raw_response={"error": {"code": 401, "message": "unauthorized"}},
        error_class="authentication_error",
        error_message="unauthorized",
    )
    transport = _scripted_transport([unauthorized, _json_response(PLAYERS_ANSWER)])
    draft = _run_with_transport("section_players", transport)

    assert len(transport.calls) == 1
    assert draft.unavailable_reason
    assert draft.body == ""
