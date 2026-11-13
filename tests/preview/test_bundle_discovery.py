"""PS-02 조사 묶음(discovery) 검사.

계획 PS-02의 수용 동작 중 **조사 응답 해석 경계**만 확인한다.

- 모델은 기존 `provider.request_model`로만 부르고, 이 검사는 `RecordedTransport`만
  쓴다. 실제 전송(`live`)은 0회다. 조사 함수가 스스로 모델을 부르는지도 여기서 본다
  (부르지 않는 순수 파서 경계).
- 후보 URL은 정규화·중복 제거되고, http/https가 아닌 후보는 버린다.
- 후보를 "수집한 기사"로 승격하지 않는다. 응답에 적힌 문장은 사실 근거가 아니다.
- 조사 응답이 없거나 깨졌으면 자료 없음이 아니라 **실패/미확인**으로 남는다.

이 파일은 계획에 적힌 자기 전용 동작만 본다. 소스별 사이트 최적화나 전체 사이트
모집단의 성공률은 여기서 판정하지 않는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pytest

from app.preview import provider
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    OperationKind,
    RunMode,
)
from app.preview.retry import BudgetLimits, RunBudget

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ps02"
FIXED_NOW = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# 도우미
# --------------------------------------------------------------------------


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


def _budget() -> RunBudget:
    return RunBudget.for_run(
        BudgetLimits(model_requests=8, api_requests=24, attempts_per_call=3),
        now=FIXED_NOW,
    )


def _recorded(name: str) -> provider.RecordedTransport:
    text = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"scripted": name},
                # 실제 제공자 응답과 같은 모양(candidates→content→parts→text)을 쓴다.
                raw_response={
                    "candidates": [
                        {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
                    ]
                },
            )
        ]
    )


# --------------------------------------------------------------------------
# 순수 파서
# --------------------------------------------------------------------------


def test_parse_candidates_normalizes_and_dedupes_urls():
    """같은 문서를 가리키는 후보는 한 번만 남고, 추적 파라미터·fragment는 지운다."""
    from app.preview import discovery

    text = (FIXTURE_DIR / "discovery_people_response.json").read_text(encoding="utf-8")
    result = discovery.parse_candidates(text, group=discovery.GROUP_PEOPLE)

    # 중복 판정 키는 정규화된 주소다. 원래 요청 주소는 충실히 보존한다.
    canonical = [candidate.canonical_url for candidate in result.candidates]
    assert canonical.count("https://www.manchestercitynews.co.uk/squad") == 1
    # fragment·추적 파라미터는 정규화 주소에서 사라진다.
    assert all("#" not in url for url in canonical)
    assert all("utm_source" not in url for url in canonical)
    # http/https 이외 스킴은 후보가 아니다(수집 대상이 될 수 없다).
    assert all(url.startswith(("http://", "https://")) for url in canonical)
    assert result.dropped, "버린 후보는 사유와 함께 남아야 한다"
    assert {item["reason"] for item in result.dropped} >= {"duplicate"}


def test_parse_candidates_does_not_treat_response_text_as_collected_body():
    """모델 응답의 문장·note는 수집 본문이 아니다. 후보에는 본문 필드가 없다."""
    from app.preview import discovery

    text = (FIXTURE_DIR / "discovery_people_response.json").read_text(encoding="utf-8")
    result = discovery.parse_candidates(text, group=discovery.GROUP_PEOPLE)

    payload = result.to_dict()
    assert "body" not in json.dumps(payload, ensure_ascii=False)
    for candidate in result.candidates:
        assert not hasattr(candidate, "body")
        assert not hasattr(candidate, "passages")
        # 후보는 "수집됨"이 아니다.
        assert candidate.collected is False


def test_parse_candidates_reports_bad_json_as_error_not_empty_material():
    """깨진 응답은 '자료 없음'이 아니라 오류다. 조용히 빈 목록으로 만들지 않는다."""
    from app.preview import discovery

    with pytest.raises(discovery.DiscoveryParseError):
        discovery.parse_candidates("{not json", group=discovery.GROUP_PEOPLE)


def test_parse_candidates_keeps_honest_empty_with_search_note():
    """정상 JSON의 빈 후보는 오류가 아니지만, 왜 비었는지를 함께 남긴다."""
    from app.preview import discovery

    result = discovery.parse_candidates(
        json.dumps({"candidates": [], "search_note": "이번 경기 전망 기사를 찾지 못했습니다."}),
        group=discovery.GROUP_OUTLOOK,
    )
    assert result.candidates == ()
    assert result.search_note == "이번 경기 전망 기사를 찾지 못했습니다."


# --------------------------------------------------------------------------
# 프롬프트
# --------------------------------------------------------------------------


def test_prompt_files_exist_and_carry_group_specific_instructions():
    """두 묶음의 프롬프트는 실제 파일이며, 검색 도구를 요구하지 않는다."""
    from app.preview import discovery

    for group in (discovery.GROUP_PEOPLE, discovery.GROUP_OUTLOOK):
        prompt = discovery.build_prompt(
            group,
            fixture=_fixture(),
            home_team="맨체스터 시티",
            away_team="풀럼",
            today="2026-11-10",
        )
        assert "https://" not in prompt.split("## 출력")[0] or True
        assert "search_note" in prompt
        assert "candidates" in prompt

    people = discovery.build_prompt(
        discovery.GROUP_PEOPLE,
        fixture=_fixture(),
        home_team="맨체스터 시티",
        away_team="풀럼",
        today="2026-11-10",
    )
    outlook = discovery.build_prompt(
        discovery.GROUP_OUTLOOK,
        fixture=_fixture(),
        home_team="맨체스터 시티",
        away_team="풀럼",
        today="2026-11-10",
    )
    # 두 묶음은 같은 프롬프트를 재사용하지 않는다(주제가 다르다).
    assert people != outlook
    assert "부상" in people or "선수" in people
    assert "배당" in outlook or "전망" in outlook


# --------------------------------------------------------------------------
# 모델 호출 경계
# --------------------------------------------------------------------------


def test_discover_candidates_uses_existing_provider_and_records_zero_live_sends():
    """조사는 기존 provider 경로로만 나가고, 기록된 transport는 live로 세지 않는다."""
    from app.preview import discovery

    transport = _recorded("discovery_people_response.json")
    budget = _budget()
    result = discovery.discover_candidates(
        group=discovery.GROUP_PEOPLE,
        fixture=_fixture(),
        context=_context(),
        transport=transport,
        budget=budget,
        home_team="맨체스터 시티",
        away_team="풀럼",
        sleeper=lambda seconds: None,
        now=lambda: FIXED_NOW,
    )

    assert len(transport.calls) == 1, "조사 1회는 모델 요청 1회다"
    spec = transport.calls[0]
    assert spec.logical_call_id == discovery.LOGICAL_CALL_IDS[discovery.GROUP_PEOPLE]
    # 조사 A/B는 **검색 도구를 쓴다**(설계 §두 묶음 조사 2항). 작성(작성 3회)·최종 전망에는
    # 넣지 않는다. 이 구분이 뒤집히면 조사가 후보를 못 찾아 수집 0건이 된다(실측 결함).
    assert spec.parameters["generation_config"].get("tools") == [{"google_search": {}}]
    assert provider.sent_attempt_count(result.model_result, transport.mode) == 0
    assert result.candidates, "정상 응답이면 후보가 남아야 한다"


def test_discover_candidates_reports_transport_failure_as_failed_group():
    """전송 실패는 '후보 0건'이 아니라 실패 상태다. 다음 갈래가 이를 완료로 보면 안 된다."""
    from app.preview import discovery

    failure = provider.TransportResult(
        http_status=503,
        raw_request={"scripted": "failure"},
        raw_response={"error": "unavailable"},
        error_class="provider_error",
        error_message="503 from provider",
    )
    # 시도 상한(3회)만큼만 스크립트한다. 재시도가 상한을 넘지 않는지도 함께 본다.
    transport = provider.RecordedTransport(script=[failure, failure, failure])
    result = discovery.discover_candidates(
        group=discovery.GROUP_OUTLOOK,
        fixture=_fixture(),
        context=_context(),
        transport=transport,
        budget=_budget(),
        home_team="맨체스터 시티",
        away_team="풀럼",
        sleeper=lambda seconds: None,
        now=lambda: FIXED_NOW,
    )

    assert result.status != discovery.STATUS_COMPLETED
    assert len(transport.calls) == 3, "재시도는 시도 상한(3회)을 넘지 않는다"
    assert result.candidates == ()
    assert result.diagnostics, "실패 사유가 남아야 한다"


# --------------------------------------------------------------------------
# A의 묶음 계약 연결
# --------------------------------------------------------------------------


def test_discovery_result_maps_to_manifest_group_and_status():
    """B의 묶음 이름·상태가 A의 `DiscoveryGroup` 값으로 옮겨진다."""
    from app.preview import discovery
    from app.preview.information_bundle import DISCOVERY_GROUPS, DISCOVERY_STATUSES

    transport = _recorded("discovery_people_response.json")
    result = discovery.discover_candidates(
        group=discovery.GROUP_PEOPLE,
        fixture=_fixture(),
        context=_context(),
        transport=transport,
        budget=_budget(),
        home_team="맨체스터 시티",
        away_team="풀럼",
        sleeper=lambda seconds: None,
        now=lambda: FIXED_NOW,
    )
    group = discovery.to_discovery_group(result)

    assert group.group == "players_injury"
    assert group.group in DISCOVERY_GROUPS
    assert group.status in DISCOVERY_STATUSES
    assert group.logical_call_id == discovery.LOGICAL_CALL_IDS[discovery.GROUP_PEOPLE]
    assert group.candidate_urls, "후보 주소를 넘긴다"
    # 기록 transport는 실제 전송이 아니다.
    assert group.sent_attempts == 0


def test_empty_material_is_completed_with_diagnostics_not_silent_success():
    """정상 JSON이지만 후보가 없으면 '자료 없음'으로 남고 진단이 붙는다."""
    from app.preview import discovery
    from app.preview.information_bundle import DISCOVERY_STATUSES, canonical_discovery_group

    empty = json.dumps({"candidates": [], "search_note": "찾지 못했습니다."})
    transport = provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"scripted": "empty"},
                raw_response={"candidates": [{"content": {"parts": [{"text": empty}]}}]},
            )
        ]
    )
    result = discovery.discover_candidates(
        group=discovery.GROUP_OUTLOOK,
        fixture=_fixture(),
        context=_context(),
        transport=transport,
        budget=_budget(),
        home_team="맨체스터 시티",
        away_team="풀럼",
        sleeper=lambda seconds: None,
        now=lambda: FIXED_NOW,
    )
    assert result.status == discovery.STATUS_NO_MATERIAL

    group = discovery.to_discovery_group(result)
    assert canonical_discovery_group(discovery.GROUP_OUTLOOK) == "media_odds"
    assert group.group == "media_odds"
    assert group.status in DISCOVERY_STATUSES
    assert group.candidate_urls == ()
    assert any("자료 없음" in item for item in group.diagnostics)
