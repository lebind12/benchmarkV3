"""MP-09 S1 종합·V0 검증 검사.

계획 §6 MP-09의 대표 검사:

- `test_synthesis_has_no_search_call`: S1 모델 요청에 검색 도구가 없고, 요청은
  정상 경로에서 정확히 1회다.
- `test_selected_result_versions_match_input`: 실제로 넘긴 결과 버전과 저장된 기록·
  payload가 같은 값을 가리킨다.
- `test_added_module_claims_reach_synthesis`: 등록된 모듈을 하나 더해도 같은 계약으로
  종합 입력에 들어간다(하드코딩된 문자열 결합이 아니다).
- `test_fact_citation_must_exist`: 사실 문장의 근거 참조가 실제 입력에 없으면 제외된다.
- `test_missing_optional_section_is_omitted`: 배당·매체 전망이 없어도 프리뷰를 만들고
  빈 카드·누락 안내를 넣지 않는다.
- `test_diagnostics_absent_from_preview_payload`: 독자용 투영에 진단·ID·시도가 없다.
- `test_insufficient_core_not_ready`: 핵심 근거가 없으면 완성 프리뷰로 만들지 않는다.

추가로 사용자 확정 기준(사실 vs AI 판단)의 대표 사례를 검사한다.

모든 모델 응답은 `tests/preview/fixtures/synthesis_inputs.json`의 기록이며 실제
모델 호출 결과가 아니다. 이 파일은 live 성공을 증명하지 않는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.preview import presentation, provider, runner, sections, store, version_manifest
from app.preview.contracts import (
    ClaimDecision,
    ClaimKind,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureIdentity,
    OperationKind,
    PreviewDocument,
    QualityStatus,
    RunMode,
    SourceKind,
    SourceSnapshot,
    ValidationStatus,
)
from app.preview.modules import synthesis
from app.preview.registry import get_section_workflow
from app.preview.retry import BudgetLimits, RunBudget
from app.preview.validation import (
    EvidenceGap,
    SelectedResultInput,
    ValidatedEvidence,
    ValidatedModule,
    validate_evidence,
)

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "synthesis_inputs.json").read_text(
        encoding="utf-8"
    )
)
FIXTURE = FixtureIdentity.from_dict(FIXTURES["fixture"])
MOMENT = datetime.fromisoformat(FIXTURES["collected_at"])

SNAPSHOTS = tuple(
    SourceSnapshot(
        snapshot_id=uuid.UUID(row["snapshot_id"]),
        source_kind=row["source_kind"],
        provider=row["provider"],
        collected_at=MOMENT,
        provider_updated_at=None,
        fixture=FIXTURE,
        catalog_query=None,
        artifact_id=None,
        validation_status=ValidationStatus(row["validation_status"]),
        note=row["note"],
    )
    for row in FIXTURES["snapshots"]
)


def _result(module_id: str, **overrides) -> SelectedResultInput:
    raw = dict(FIXTURES["results"][module_id])
    raw.update(overrides)
    claims = tuple(
        SelectedResultInput.from_dict(
            {
                "result_id": raw["result_id"],
                "module_id": module_id,
                "claims": raw.get("claims") or (),
            }
        ).claims
    )
    return SelectedResultInput(
        result_id=uuid.UUID(raw["result_id"]),
        module_id=module_id,
        version=int(raw["version"]),
        status=str(raw.get("status") or "succeeded"),
        quality=str(raw.get("quality") or "ready"),
        implementation_version=str(raw.get("implementation_version") or ""),
        prompt_version=str(raw.get("prompt_version") or ""),
        fixture=FIXTURE,
        claims=claims,
        sources=tuple(raw.get("sources") or ()),
        payload={"coverage": raw.get("coverage") or ()},
    )


def _results() -> tuple[SelectedResultInput, ...]:
    return (_result("R1"), _result("R2"), _result("R3"))


def _evidence(results=None) -> ValidatedEvidence:
    return validate_evidence(
        fixture=FIXTURE,
        results=results if results is not None else _results(),
        snapshots=SNAPSHOTS,
        module_ids=("R1", "R2", "R3"),
        selected_result_ids=[item.result_id for item in (results or _results())],
    )


def _context(*, mode: RunMode = RunMode.MOCK, run_id=None) -> ExecutionContext:
    return ExecutionContext(
        run_id=run_id or uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=mode,
        actor_id=7,
        config_version="mp09-test",
        limits=ExecutionLimits(model_requests=8, attempts_per_call=3),
    )


def _transport(text: str, *, mode: RunMode = RunMode.MOCK) -> provider.RecordedTransport:
    return provider.RecordedTransport(
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": text}], "role": "model"},
                            "finish_reason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 900, "output_tokens": 260},
                duration_ms=1200,
            )
        ],
        provider="recorded-model",
        mode=mode,
    )


def _synthesize(text: str | None = None, *, evidence=None, mode=RunMode.MOCK):
    transport = _transport(
        text if text is not None else FIXTURES["model_text_ok"], mode=mode
    )
    resolved = evidence if evidence is not None else _evidence()
    result = synthesis.synthesize_preview(
        evidence=resolved,
        context=_context(mode=mode),
        transport=transport,
        budget=RunBudget.for_run(BudgetLimits(), now=MOMENT),
        now=MOMENT,
        fixture_names={
            "home_team": FIXTURES["fixture"]["home_team"],
            "away_team": FIXTURES["fixture"]["away_team"],
            "league": FIXTURES["fixture"]["league"],
        },
    )
    return result, transport


# --------------------------------------------------------------------------
# 대표 검사
# --------------------------------------------------------------------------


def test_synthesis_has_no_search_call():
    """S1 요청에는 검색 도구가 없고, 정상 경로의 논리 호출은 1회다."""
    result, transport = _synthesize()
    assert result.unavailable_reason is None
    assert len(transport.calls) == 1

    spec = transport.calls[0]
    generation = dict(spec.parameters.get("generation_config") or {})
    assert not generation.get("tools"), "S1 요청에 검색 도구가 들어가면 안 됩니다."
    assert spec.operation == "synthesize_preview"
    assert spec.module_id == "S1"
    # 호출 횟수를 숨기지 않는다: 시도 1건, 외부 호출 0건(모의 transport).
    assert result.attempt_summary["attempt_count"] == 1
    assert result.attempt_summary["tools"] == []
    assert result.external_calls == 0


def test_selected_result_versions_match_input():
    """선택한 결과 ID·버전이 실제로 넘긴 입력과 그대로 같다."""
    evidence = _evidence()
    result, _transport = _synthesize(evidence=evidence)

    stored = result.payload["validated"]["modules"]
    assert [row["module_id"] for row in stored] == ["R1", "R2", "R3"]
    assert [row["result_id"] for row in stored] == [
        FIXTURES["results"]["R1"]["result_id"],
        FIXTURES["results"]["R2"]["result_id"],
        FIXTURES["results"]["R3"]["result_id"],
    ]
    assert [row["version"] for row in stored] == [2, 1, 1]
    # payload에 남은 선택 ID도 같은 값이다.
    assert result.payload["selected_result_ids"] == [
        FIXTURES["results"]["R1"]["result_id"],
        FIXTURES["results"]["R2"]["result_id"],
        FIXTURES["results"]["R3"]["result_id"],
    ]
    # 실제 프롬프트에 들어간 자료도 같은 버전에서 나온 문장이다.
    context_text = synthesis._evidence_context(evidence)
    assert "R1 조사 결과 (버전 2" in context_text
    assert "R2 조사 결과 (버전 1" in context_text


def test_selected_result_ids_mismatch_is_diagnosed_not_filled():
    """선택했는데 저장본에 없는 결과 ID는 채우지 않고 진단에 남긴다."""
    missing = uuid.uuid4()
    evidence = validate_evidence(
        fixture=FIXTURE,
        results=_results(),
        snapshots=SNAPSHOTS,
        module_ids=("R1", "R2", "R3"),
        selected_result_ids=[item.result_id for item in _results()] + [missing],
    )
    assert any(str(missing) in gap.reason for gap in evidence.gaps)
    # 없는 결과를 만들어 넣지 않는다: 선택된 결과는 실제 저장된 3건 그대로다.
    assert len(evidence.modules) == 3


def test_added_module_claims_reach_synthesis():
    """새 모듈을 등록하면 같은 계약으로 종합 입력에 들어간다(문자열 결합 아님)."""
    from dataclasses import replace

    extra = _result("R1")
    extra = replace(
        extra,
        result_id=uuid.uuid4(),
        module_id="R9",
        version=1,
        claims=(
            *extra.claims,
            SelectedResultInput.from_dict(
                {
                    "result_id": str(extra.result_id),
                    "module_id": "R9",
                    "claims": [
                        {
                            "claim_id": "r9-new-0",
                            "kind": "fact",
                            "text": "새 모듈이 확인한 추가 사실입니다.",
                            "snapshot_ids": [FIXTURES["snapshots"][0]["snapshot_id"]],
                            "decision": "adopted",
                        }
                    ],
                }
            ).claims[-1],
        ),
    )
    evidence = validate_evidence(
        fixture=FIXTURE,
        results=(*_results(), extra),
        snapshots=SNAPSHOTS,
        module_ids=("R1", "R2", "R3", "R9"),
        selected_result_ids=[item.result_id for item in (*_results(), extra)],
    )
    assert "R9" in evidence.module_ids
    assert "r9-new-0" in evidence.claims_by_id()

    prompt = synthesis._evidence_context(evidence)
    assert "R9 조사 결과" in prompt
    assert "새 모듈이 확인한 추가 사실입니다." in prompt


def test_fact_citation_must_exist():
    """사실 문장의 근거 참조가 실제 입력에 없으면 종합에서 제외된다."""
    fabricated = replace_result_claim(
        _result("R1"),
        claim_id="r1-form-fabricated",
        kind=ClaimKind.FACT,
        text="근거 없는 사실 문장입니다.",
        snapshot_ids=(),
        source_url=None,
    )
    evidence = _evidence(results=(fabricated, _result("R2"), _result("R3")))
    assert "r1-form-fabricated" not in evidence.claims_by_id()
    excluded = {claim.claim_id for claim in evidence.excluded_claims}
    assert "r1-form-fabricated" in excluded

    result, _transport = _synthesize(evidence=evidence)
    assert result.unavailable_reason is None
    prompt = synthesis._evidence_context(evidence)
    assert "근거 없는 사실 문장입니다." not in prompt


def replace_result_claim(
    result: SelectedResultInput,
    *,
    claim_id: str,
    kind: ClaimKind,
    text: str,
    snapshot_ids: tuple = (),
    source_url: str | None = None,
):
    from dataclasses import replace

    from app.preview.contracts import EvidenceClaim

    claim = EvidenceClaim(
        claim_id=claim_id,
        kind=kind,
        text=text,
        snapshot_ids=tuple(snapshot_ids),
        decision=ClaimDecision.ADOPTED,
        source_url=source_url,
    )
    return replace(result, claims=(*result.claims, claim))


def test_missing_optional_section_is_omitted():
    """배당·매체 전망이 없어도 프리뷰를 만들고, 빈 항목을 카드로 남기지 않는다."""
    outlook_empty = _result(
        "R3",
        claims=[
            {
                "claim_id": "r3-api-prediction",
                "kind": "api_prediction",
                "text": "제공자 알고리즘 예측: 우세 팀 Manchester City.",
                "snapshot_ids": [FIXTURES["snapshots"][0]["snapshot_id"]],
                "decision": "adopted",
            }
        ],
        sources=[],
        coverage=[
            {"topic": "경기 전 승무패 배당", "state": "api_not_provided", "detail": "미제공"},
            {"topic": "외부 매체 전망", "state": "search_not_found", "detail": "미발견"},
        ],
    )
    evidence = _evidence(results=(_result("R1"), _result("R2"), outlook_empty))
    result, _transport = _synthesize(evidence=evidence)

    assert result.unavailable_reason is None
    reader = result.payload["reader_preview"]
    assert "absences_impact" in reader  # 부상 자료는 있다
    # 매체 전망이 없으면 그 키 자체를 만들지 않는다(빈 카드 금지).
    forecast_rows = [
        row
        for row in reader.get("external_outlook") or ()
        if row.get("source_kind") == ClaimKind.EXTERNAL_FORECAST.value
    ]
    assert forecast_rows == []
    body = reader["body"]
    for forbidden in ("자료 없음", "미확보", "누락", "실패", "재시도"):
        assert forbidden not in body


def test_diagnostics_absent_from_preview_payload():
    """독자용 투영에는 진단·내부 ID·시도·커버리지가 없다."""
    result, _transport = _synthesize()
    reader = result.payload["reader_preview"]
    for key in (
        "diagnostics",
        "coverage",
        "gaps",
        "selected_result_ids",
        "snapshot_ids",
        "result_ids",
        "attempt_summary",
        "model_text",
        "validated",
    ):
        assert key not in reader, key

    serialized = json.dumps(reader, ensure_ascii=False)
    for internal in (
        FIXTURES["results"]["R1"]["result_id"],
        FIXTURES["snapshots"][0]["snapshot_id"],
        "api:standings-13",
        "r1-watch-0",
        "synthesize_preview",
    ):
        assert internal not in serialized, internal
    # 관리자 진단에는 남아 있다(같은 실행의 진단 경로).
    assert result.payload["diagnostics"] or result.payload["validated"]["gaps"]


def test_insufficient_core_not_ready():
    """참조 있는 사실이 하나도 없으면 완성 프리뷰로 만들지 않는다."""
    no_facts = _result(
        "R1",
        claims=[
            {
                "claim_id": "r1-watch-0",
                "kind": "ai_interpretation",
                "text": "근거 없이 만든 관전 포인트입니다.",
                "decision": "adopted",
            }
        ],
        sources=[],
    )
    evidence = _evidence(results=(no_facts,))
    assert evidence.core_evidence_satisfied is False
    result, transport = _synthesize(evidence=evidence)
    assert result.unavailable_reason
    assert result.quality is QualityStatus.INSUFFICIENT
    # 핵심 근거가 없으면 유료 호출을 하지 않는다.
    assert transport.calls == []
    # 독자용 투영 키 자체를 만들지 않는다(빈 카드 금지).
    assert "reader_preview" not in result.payload


# --------------------------------------------------------------------------
# 사용자 확정 기준: 사실 검증 vs AI 판단
# --------------------------------------------------------------------------


def test_ai_score_judgment_allowed_without_outcome_proof():
    """AI 예상 스코어는 결론을 증명하는 외부 보도 없이도 유지된다."""
    result, _transport = _synthesize()
    prediction = result.payload["reader_preview"]["ai_prediction"]
    assert prediction["lean"] == "home"
    assert prediction["score"] == "2-1"
    assert prediction["reasoning"]
    # 예측을 증명하는 외부 출처는 요구하지 않았다.
    assert result.unavailable_reason is None


def test_hot_player_selection_needs_no_external_pick_source():
    """주목 선수 선정은 AI 판단이라 같은 선수를 고른 외부 보도를 요구하지 않는다."""
    evidence = _evidence()
    assert "r1-player-0" in evidence.claims_by_id()
    result, _transport = _synthesize(evidence=evidence)
    players = result.payload["reader_preview"]["players_to_watch"]
    assert players and players[0]["player"] == "Erling Haaland"
    assert result.payload["reader_preview"].get("external_outlook")


def test_new_stat_in_judgment_is_dropped():
    """'AI 해석'으로 새 구체 수치를 통째로 들여보내지 않는다."""
    result, _transport = _synthesize(FIXTURES["model_text_new_stat"])
    reader = result.payload["reader_preview"]
    # 새 수치가 든 판단 문장은 덜어내고, 남는 판단(예상)은 유지한다.
    assert all("12골" not in item["text"] for item in reader.get("watch_points") or ())
    assert reader["ai_prediction"]["lean"] == "home"
    assert any("12골" in note for note in result.payload["diagnostics"])


def test_media_forecast_requires_actual_media_proof():
    """매체가 실제로 말했다는 URL 근거가 없으면 매체 전망을 쓰지 않는다."""
    result, _transport = _synthesize(FIXTURES["model_text_media_without_url"])
    reader = result.payload["reader_preview"]
    assert not [
        row
        for row in reader.get("external_outlook") or ()
        if row.get("source_kind") == ClaimKind.EXTERNAL_FORECAST.value
    ]
    assert any("URL 근거가 없어" in note for note in result.payload["diagnostics"])


def test_reader_sources_hide_internal_provider_identifiers():
    """독자용 근거에 내부 제공자 식별자(`vertex-google-search` 등)가 나가지 않는다."""
    evidence = _evidence()
    rows = synthesis._reader_sources(evidence)
    rendered = json.dumps([dict(row) for row in rows], ensure_ascii=False)
    assert "vertex-google-search" not in rendered
    assert "api-football-stored" not in rendered
    # 검색 URL은 그대로 보인다(독자가 확인할 수 있는 출처).
    assert "https://www.bbc.com/sport/football/manchester-city-fulham-preview" in rendered
    # API 자료도 사람이 읽는 이름으로 남는다.
    assert "API-Football 저장 자료" in rendered


def test_api_prediction_keeps_algorithmic_source_kind():
    """제공자 알고리즘 예측은 매체 의견과 다른 종류로 남는다."""
    result, _transport = _synthesize()
    rows = result.payload["reader_preview"]["external_outlook"]
    api_rows = [row for row in rows if row["source_kind"] == ClaimKind.API_PREDICTION.value]
    media_rows = [
        row for row in rows if row["source_kind"] == ClaimKind.EXTERNAL_FORECAST.value
    ]
    assert api_rows and media_rows
    assert api_rows[0]["source_note"].startswith("제공자 알고리즘 예측")


def test_api_only_facts_still_produce_a_brief():
    """검색 인용 0건·부상 발생일 미확인·배당 미제공이어도 프리뷰를 만든다."""
    api_only = _result(
        "R2",
        claims=[
            {
                "claim_id": "r2-api-9401",
                "kind": "fact",
                "text": "API 부상 자료: Nathan Ake 표기 Out, 사유 Hamstring Injury",
                "snapshot_ids": [FIXTURES["snapshots"][1]["snapshot_id"]],
                "decision": "adopted",
                "decision_reason": "발생 날짜·경기는 확인되지 않았습니다.",
            }
        ],
        sources=[],
        coverage=[
            {"topic": "부상 맥락 검색", "state": "search_not_found", "detail": "미발견"},
            {"topic": "경기 전 승무패 배당", "state": "api_not_provided", "detail": "미제공"},
        ],
    )
    evidence = _evidence(results=(_result("R1"), api_only))
    result, _transport = _synthesize(evidence=evidence)
    assert evidence.core_evidence_satisfied is True
    assert result.unavailable_reason is None
    reader = result.payload["reader_preview"]
    assert reader["absences_impact"]
    # 확인되지 않은 발생 날짜를 지어내지 않는다.
    assert "2026-11" not in json.dumps(reader.get("absences_impact"), ensure_ascii=False)


def test_empty_selection_is_not_ready_and_makes_no_call():
    """선택 입력이 아예 없는 실행은 호출하지 않고 미완성으로 남는다."""
    evidence = validate_evidence(
        fixture=FIXTURE,
        results=(),
        snapshots=SNAPSHOTS,
        module_ids=("R1", "R2", "R3"),
        selected_result_ids=(),
    )
    assert evidence.core_evidence_satisfied is False
    assert evidence.modules == ()
    result, transport = _synthesize(evidence=evidence)
    assert transport.calls == []
    assert result.unavailable_reason
    assert "reader_preview" not in result.payload
    # 공백 사유는 관리자 진단 자리에 남는다.
    assert any("선택된 결과가 없습니다" in gap.reason for gap in evidence.gaps)


def test_invalid_fixture_is_rejected_before_the_call():
    """경기 식별이 없으면 종합 호출을 하지 않는다(빈 경기로 프리뷰를 꾸미지 않는다)."""
    evidence = validate_evidence(
        fixture=None,
        results=_results(),
        snapshots=SNAPSHOTS,
        module_ids=("R1", "R2", "R3"),
        selected_result_ids=[item.result_id for item in _results()],
    )
    assert evidence.fixture is None
    assert evidence.core_evidence_satisfied is False
    result, transport = _synthesize(evidence=evidence)
    assert transport.calls == []
    assert result.unavailable_reason
    assert "reader_preview" not in result.payload


def test_other_fixture_result_is_excluded():
    """다른 경기의 결과는 종합 입력에서 제외되고 사유가 남는다."""
    from dataclasses import replace

    other = FixtureIdentity(
        fixture_id=999001,
        league_id=1,
        season=2026,
        home_team_id=50,
        away_team_id=49,
        kickoff_at=FIXTURE.kickoff_at,
    )
    wrong = replace(_result("R2"), fixture=other)
    evidence = _evidence(results=(_result("R1"), wrong, _result("R3")))
    assert "R2" not in evidence.module_ids
    assert any("다른 경기" in gap.reason for gap in evidence.gaps)


# --------------------------------------------------------------------------
# 섹션 워크플로우 통합 (저장 경로)
# --------------------------------------------------------------------------


def test_section_workflow_synthesis_persists_reader_preview(session_factory):
    """선택 결과 → S1 1회 → 독자용 본문·근거 저장까지 공통 경로로 끝난다."""
    seeds = _seed_selected_results(session_factory)
    implementations = sections.build_implementations(
        "section_synthesis",
        transport=_transport(FIXTURES["model_text_ok"]),
        now=MOMENT,
    )
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_synthesis",
            implementations=implementations,
            actor_id=1,
            fixture=FIXTURES["fixture"],
            fixture_label="Manchester City vs Fulham",
            selected_result_ids=seeds,
        )
        session.commit()

        assert result.body.strip(), result.unavailable_reason
        assert result.external_calls == 0  # 기록된 transport이므로 live가 아니다.
        stored = store.get_run_detail(session, result.run_id)
        assert stored.section_results[0]["workflow_id"] == "section_synthesis"
        assert stored.section_results[0]["mode"] == RunMode.MOCK.value

        from app.preview import section_preview

        s1_rows = [row for row in stored.results if row["module_id"] == "S1"]
        assert len(s1_rows) == 1
        payload = section_preview.synthesis_result_payload(stored)
        assert payload is not None
        # 저장 행은 ModuleResult.to_dict()이라 한 겹 감싸여 있다(nested payload).
        reader = payload["reader_preview"]
        # 실제로 넘긴 선택 결과가 그대로 기록된다.
        assert payload["selected_result_ids"] == [str(item) for item in seeds]
        assert reader["body"] == result.body
        assert reader["attribution"]["ai_forecast_label"] == presentation.AI_FORECAST_LABEL

        # 관리자 진단에는 공백 사유·선택 입력 버전이 남는다.
        diagnostics = section_preview.build_diagnostics_view(session, stored)
        assert diagnostics["selected_inputs"]
        assert {row["module_id"] for row in diagnostics["selected_inputs"]} == {
            "R1",
            "R2",
            "R3",
        }
        reader_view = section_preview.build_reader_view(session, stored)
        assert reader_view is not None
        assert reader_view["body"] == result.body
        assert "diagnostics" not in reader_view


def test_section_run_without_selected_results_is_not_ready(session_factory):
    """섹션 실행에 선택 입력이 없으면 본문 없이 미완성으로 남고 승인 근거가 되지 않는다."""
    transport = _transport(FIXTURES["model_text_ok"])
    implementations = sections.build_implementations(
        "section_synthesis", transport=transport, now=MOMENT
    )
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_synthesis",
            implementations=implementations,
            actor_id=1,
            fixture=FIXTURES["fixture"],
            selected_result_ids=(),
        )
        session.commit()

        assert result.unavailable_reason
        assert result.body.strip() == ""
        assert transport.calls == []
        stored = store.get_run_detail(session, result.run_id).section_results[0]
        assert stored["unavailable"] is True
        assert stored["mode"] == RunMode.MOCK.value
        # 본문이 없으므로 독자용 프리뷰를 만들지 않는다.
        from app.preview import section_preview

        assert section_preview.build_reader_view(
            session, store.get_run_detail(session, result.run_id)
        ) is None


def test_synthesis_section_has_no_extra_research_calls(session_factory):
    """S1 섹션은 R1/R2/R3를 다시 호출하지 않는다(선택 결과만 읽는다)."""
    seeds = _seed_selected_results(session_factory)
    transport = _transport(FIXTURES["model_text_ok"])
    implementations = sections.build_implementations(
        "section_synthesis", transport=transport, now=MOMENT
    )
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_synthesis",
            implementations=implementations,
            actor_id=1,
            fixture=FIXTURES["fixture"],
            selected_result_ids=seeds,
        )
        session.commit()
        # 모델 논리 호출은 S1 하나뿐이다.
        assert [spec.module_id for spec in transport.calls] == ["S1"]
        detail = store.get_run_detail(session, result.run_id)
        module_ids = [row["module_id"] for row in detail.modules]
        assert "S1" in module_ids
        # 모듈 입력에도 선택 결과 ID가 그대로 남는다(무엇을 보냈는지의 근거).
        s1_module = next(row for row in detail.modules if row["module_id"] == "S1")
        assert s1_module["input"]["selected_result_ids"] == [str(item) for item in seeds]
        for research in ("R1", "R2", "R3"):
            assert research not in module_ids


def _seed_selected_results(session_factory) -> tuple[uuid.UUID, ...]:
    """R1/R2/R3 저장 결과를 실제 저장 경로로 만든다(같은 계약 사용)."""
    from app.preview.contracts import (
        CONTRACT_VERSION,
        ExecutionContext as _Ctx,
        ModuleInput,
        ModuleResult,
        ModuleStatus,
        compute_input_hash,
    )

    context = ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=RunMode.MOCK,
        actor_id=1,
        config_version="mp09-seed",
        limits=ExecutionLimits(),
    )
    result_ids: list[uuid.UUID] = []
    with session_factory() as session:
        store.store_run(
            session,
            context,
            fixture=FIXTURE,
            fixture_label="Manchester City vs Fulham",
            label="MP-09 선택 입력 시드",
        )
        snapshot_ids: list[uuid.UUID] = []
        for row in FIXTURES["snapshots"]:
            snapshot = store.record_source_snapshot(
                session,
                run_id=context.run_id,
                source_kind=SourceKind(row["source_kind"]),
                provider=row["provider"],
                collected_at=MOMENT,
                validation_status=ValidationStatus(row["validation_status"]),
                fixture=FIXTURE,
                note=row["note"],
            )
            snapshot_ids.append(snapshot.id)
        # 픽스처의 스냅샷 ID와 저장 행을 맞춘다(참조가 실제 행을 가리키게).
        remap = {
            uuid.UUID(row["snapshot_id"]): stored
            for row, stored in zip(FIXTURES["snapshots"], snapshot_ids, strict=True)
        }
        for module_id in ("R1", "R2", "R3"):
            raw = FIXTURES["results"][module_id]
            module_input = ModuleInput(
                module_id=module_id,
                fixture=FIXTURE,
                snapshot_ids=tuple(snapshot_ids),
                selected_result_ids=(),
                input_hash=compute_input_hash({"module_id": module_id}),
                prompt_version=raw["prompt_version"],
                contract_version=CONTRACT_VERSION,
                implementation_version=raw["implementation_version"],
            )
            execution = store.start_module_execution(
                session,
                run_id=context.run_id,
                module_id=module_id,
                module_input=module_input,
            )
            claims = []
            for item in raw["claims"]:
                from app.preview.contracts import EvidenceClaim

                claim = EvidenceClaim.from_dict(item)
                claims.append(
                    EvidenceClaim(
                        claim_id=claim.claim_id,
                        kind=claim.kind,
                        text=claim.text,
                        snapshot_ids=tuple(
                            remap.get(snapshot_id, snapshot_id)
                            for snapshot_id in claim.snapshot_ids
                        ),
                        decision=claim.decision,
                        decision_reason=claim.decision_reason,
                        subject_team_id=claim.subject_team_id,
                        subject_player_id=claim.subject_player_id,
                        claimed_at=claim.claimed_at,
                        source_url=claim.source_url,
                    )
                )
            saved = store.save_module_result(
                session,
                ModuleResult(
                    result_id=uuid.uuid4(),
                    module_id=module_id,
                    module_execution_id=execution.id,
                    run_id=context.run_id,
                    version=1,
                    input_hash=module_input.input_hash,
                    status=ModuleStatus.SUCCEEDED,
                    quality=QualityStatus.READY,
                    claims=tuple(claims),
                    coverage=(),
                    diagnostics=(),
                    implementation_version=raw["implementation_version"],
                    prompt_version=raw["prompt_version"],
                    contract_version=CONTRACT_VERSION,
                    payload={
                        "claims": [claim.to_dict() for claim in claims],
                        "coverage": raw.get("coverage") or (),
                        "reader_sources": raw.get("sources") or (),
                    },
                ),
            )
            result_ids.append(saved.id)
        session.commit()
    return tuple(result_ids)


# --------------------------------------------------------------------------
# 등록·버전
# --------------------------------------------------------------------------


def test_s1_registered_with_real_versions():
    """S1 등록부·모듈 버전·승인 후보 버전이 실제 구현 버전을 쓴다."""
    from app.preview import modules as module_versions
    from app.preview.registry import get_module

    registration = get_module("S1")
    assert registration.implemented is True
    assert registration.unrunnable_reason is None
    assert registration.prompt_version == synthesis.PROMPT_VERSION
    assert "S1" in module_versions.backed_modules()
    assert module_versions.module_versions("S1") == (
        synthesis.IMPLEMENTATION_VERSION,
        synthesis.PROMPT_VERSION,
    )

    workflow = get_section_workflow("section_synthesis")
    assert workflow.implemented is True
    constituents = version_manifest.constituents_for_workflow("section_synthesis")
    by_module = {item.module_id: item for item in constituents}
    assert by_module["S1"].prompt_version == synthesis.PROMPT_VERSION
    assert by_module["S1"].implementation_version == synthesis.IMPLEMENTATION_VERSION
    assert by_module["compose_body"].implementation_version == (
        synthesis.COMPOSE_IMPLEMENTATION_VERSION
    )
    version = version_manifest.workflow_version_of("section_synthesis")
    assert version.startswith("section_synthesis@")
    # 다른 섹션 버전과 섞이지 않는다.
    assert version != version_manifest.workflow_version_of("section_form")
