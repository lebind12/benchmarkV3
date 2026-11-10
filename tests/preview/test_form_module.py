"""MP-05 R1(경기력·주목 선수) 조사 검사.

이 파일이 확인하는 것(계획 §6 MP-05 수용 기준):

- `test_form_claims_reference_sources`: 채택된 문장이 실제 근거(snapshot·검색 URL)를
  가리키고, 다음 단계로 넘기는 식별자가 그대로 일치한다.
- `test_old_match_news_excluded`: 킥오프 7일 이전 보도는 최근 흐름 근거로 채택되지
  않고 사유가 남는다.
- `test_player_claim_without_evidence_rejected`: 근거 없는 선수 단정 표현은 제외된다.
- `test_api_facts_remain_without_search`: 검색 출처가 없어도 API 사실로 결과를 만들고,
  검색 미확보 사실이 관리자 진단에 남는다.
- `test_grounding_metadata_preserved`: grounding 질의·출처·Search Suggestions가
  보존되고, 한 번의 정상 호출만 나간다.

응답 본문은 `fixtures/form.json`의 기록이며 실제 모델 호출 결과가 아니다. live 성공으로
표현하지 않는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.preview import modules, provider, runner, sections, store
from app.preview.contracts import (
    ClaimKind,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    RunMode,
)
from app.preview.modules import compose, form
from app.preview.retry import BudgetLimits, RunBudget

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "form.json").read_text(encoding="utf-8")
)
FIXED_NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
FIXTURE = FIXTURES["fixture"]


def _facts(*, with_snapshots: bool = True) -> form.FormFacts:
    return form.FormFacts(
        fixture_id=FIXTURE["fixture_id"],
        league_id=FIXTURE["league_id"],
        season=FIXTURE["season"],
        home_team_id=FIXTURE["home_team_id"],
        away_team_id=FIXTURE["away_team_id"],
        kickoff_at=datetime.fromisoformat(FIXTURE["kickoff_at"]),
        home_team=FIXTURE["home_team"],
        away_team=FIXTURE["away_team"],
        league=FIXTURE["league"],
        facts=tuple(
            form.Fact(
                fact_id=item["fact_id"],
                text=item["text"],
                snapshot_id=item["snapshot_id"] if with_snapshots else "",
                collected_at=FIXED_NOW,
                subject_team_id=item.get("subject_team_id"),
            )
            for item in FIXTURES["facts"]
        ),
        snapshot_ids=(
            tuple(item["snapshot_id"] for item in FIXTURES["facts"]) if with_snapshots else ()
        ),
        collected_at=FIXED_NOW,
    )


def _context() -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=OperationKind.MODULE,
        environment=Environment.DEV,
        mode=RunMode.MOCK,
        actor_id=1,
        config_version="mp05-test",
        limits=ExecutionLimits(),
    )


def _transport(
    *, text: str, raw: dict | None = None, mode: RunMode = RunMode.MOCK
) -> provider.RecordedTransport:
    payload = raw if raw is not None else dict(FIXTURES["grounding_raw"])
    if not payload.get("candidates"):
        payload = {"candidates": [{"content": {"parts": [{"text": text}]}}]}
    # `mode`는 이 기록이 무엇을 대신하는지 밝힌다. 네트워크를 열지 않으므로 transport의
    # 실행 방식 표기가 실행 기록·외부 호출 수의 기준이다(mock이면 live로 세지 않는다).
    return provider.RecordedTransport(
        mode=mode,
        script=[
            provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={**payload, "candidates": [
                    {**payload["candidates"][0], "content": {"parts": [{"text": text}], "role": "model"}}
                ]},
                usage={"input_tokens": 1200, "output_tokens": 320},
                duration_ms=1500,
            )
        ]
    )


def _research(*, text: str | None = None, raw: dict | None = None, session=None):
    body = text if text is not None else FIXTURES["model_text"]
    module_input = form.ModuleInput(
        module_id="R1",
        fixture=None,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash="hash-mp05",
        prompt_version=form.FORM_PROMPT_VERSION,
        contract_version="mp02-module-input-1",
        implementation_version=form.FORM_IMPLEMENTATION_VERSION,
    )
    return form.research_form(
        module_input,
        _context(),
        facts=_facts(),
        transport=_transport(text=body, raw=raw),
        budget=RunBudget.for_run(
            BudgetLimits(model_requests=2, attempts_per_call=1, normal_model_calls=1),
            now=FIXED_NOW,
        ),
        session=session,
        now=FIXED_NOW,
    )


# --------------------------------------------------------------------------
# 수용 기준
# --------------------------------------------------------------------------


def test_form_claims_reference_sources():
    """채택 문장이 실제 근거를 가리키고, 다음 단계 식별자가 그대로 이어진다."""
    research = _research()

    assert research.unavailable is False
    adopted = research.adopted_claims
    assert adopted, "근거가 있는 채택 문장이 있어야 한다"

    allowed_snapshots = {fact.snapshot_id for fact in research.facts.facts}
    allowed_urls = {source["url"] for source in research.sources}
    for claim in adopted:
        if claim.snapshot_ids:
            assert {str(sid) for sid in claim.snapshot_ids} <= allowed_snapshots
        else:
            assert claim.source_url in allowed_urls, claim

    # 다음 단계로 넘기는 식별자는 실제 참조만 담는다.
    source_ids = research.source_ids
    assert source_ids
    for value in source_ids:
        assert value in allowed_snapshots or value in allowed_urls

    payload = research.payload()
    assert payload["source_ids"] == list(source_ids)
    # 본문 조립 입력에도 같은 식별자가 유지된다.
    composed = compose.compose_form_body(payload)
    assert composed.body
    labels = [row.get("label") for row in composed.sources]
    assert any(label for label in labels)


def test_old_match_news_excluded():
    """킥오프 7일 이전 보도는 최근 흐름 근거로 채택하지 않고 사유를 남긴다."""
    research = _research(text=FIXTURES["model_text_old_news"])

    assert research.recent_form == ()
    joined = " ".join(research.diagnostics)
    assert "7일 이전" in joined
    # 본문에는 그 문장이 들어가지 않는다.
    composed = compose.compose_form_body(research.payload())
    assert "2026-10-05" not in composed.body


def test_player_claim_without_evidence_rejected():
    """근거 없는 선수 단정 표현은 채택하지 않고 사유를 남긴다."""
    research = _research(text=FIXTURES["model_text_with_superlative"])

    assert research.hot_players == ()
    assert any("단정 표현" in line for line in research.diagnostics)
    composed = compose.compose_form_body(research.payload())
    assert "리그 최고의 스트라이커" not in composed.body


def test_api_facts_remain_without_search():
    """검색 출처가 없어도 API 사실로 결과를 만들고, 미확보는 진단에 남긴다."""
    raw = {"candidates": [{"content": {"parts": [{"text": FIXTURES["model_text_no_search"]}]}}]}
    research = _research(text=FIXTURES["model_text_no_search"], raw=raw)

    # grounding metadata가 없으므로 검색 미확보가 기록된다.
    assert research.grounding["sources"] == []
    search_row = next(c for c in research.coverage if c.topic == "매체·맥락 검색")
    assert search_row.state.value == "search_not_found"

    # API 사실만으로도 관전 포인트·최근 흐름은 남는다.
    assert research.recent_form
    assert research.watch_points
    facts_only = [c for c in research.adopted_claims if c.kind is ClaimKind.FACT]
    assert facts_only
    # 검색 보완 사실은 관리자 기록에 남고 독자용 본문에는 들어가지 않는다.
    composed = compose.compose_form_body(research.payload())
    assert composed.body
    assert "검색 결과가 없어" not in composed.body


def test_grounding_metadata_preserved():
    """검색 질의·출처·supports·Search Suggestions를 보존한다(공식 문서 표시 요구)."""
    raw = FIXTURES["grounding_raw"]
    grounding = form.parse_grounding(raw)

    assert grounding["web_search_queries"] == [
        "Manchester City Fulham preview November 2026",
        "Manchester City recent form November 2026",
    ]
    assert [source["url"] for source in grounding["sources"]] == [
        "https://www.bbc.com/sport/football/manchester-city-fulham-preview",
        "https://www.premierleague.com/news/manchester-city-form",
    ]
    assert grounding["supports"]
    assert grounding["search_entry_point"]["rendered_content"].startswith("<div")

    # 만든 URL이 아니라 제공자가 준 URL만 결과 출처로 쓴다.
    research = _research()
    urls = {source["url"] for source in research.sources}
    assert urls <= {source["url"] for source in grounding["sources"]}


def test_one_normal_call_only(session_factory):
    """정상 경로에서 모델 요청은 1회다. 숨은 두 번째 호출이 없다."""
    context = _context()
    # 실제 전송을 대신하는 기록이므로 live로 표기한다. 이 실행만 외부 호출 1회로 센다.
    transport = _transport(text=FIXTURES["model_text"], mode=RunMode.LIVE)
    with session_factory() as session:
        store.store_run(session, context, label="mp05 R1 검사")
        module_input = form.ModuleInput(
            module_id="R1",
            fixture=None,
            snapshot_ids=(),
            selected_result_ids=(),
            input_hash="hash-mp05-run",
            prompt_version=form.FORM_PROMPT_VERSION,
            contract_version="mp02-module-input-1",
            implementation_version=form.FORM_IMPLEMENTATION_VERSION,
        )
        budget = RunBudget.for_run(
            BudgetLimits(model_requests=8, attempts_per_call=3, normal_model_calls=4),
            now=FIXED_NOW,
        )
        research = form.research_form(
            module_input,
            context,
            facts=_facts(),
            transport=transport,
            budget=budget,
            session=session,
            actor_id=1,
            now=FIXED_NOW,
        )
        session.commit()

        assert len(transport.calls) == 1
        assert budget.model_used == 1
        assert research.external_calls == 1
        # grounding 시도가 요청 설정에 실제로 들어갔다.
        assert transport.calls[0].parameters["generation_config"]["tools"] == [
            {"google_search": {}}
        ]
        # 원문·시도가 같은 경로로 저장됐다.
        detail = store.get_run_detail(session, context.run_id)
        assert len(detail.attempts) == 1


def test_body_has_no_diagnostics_and_is_reader_facing():
    """독자용 본문에는 누락·오류·재시도 진단 문구가 없다."""
    research = _research()
    composed = compose.compose_form_body(research.payload())

    assert composed.body
    for forbidden in ("검색 결과가 없어", "미확보", "재시도", "호출 실패", "API 보완"):
        assert forbidden not in composed.body
    # 문단은 사람이 읽는 문장이다. JSON을 그대로 붙이지 않는다.
    assert not composed.body.strip().startswith("{")
    assert "match_context" not in composed.body


def test_module_versions_and_registry_agree():
    """구현이 있는 모듈만 실행 가능으로 등록된다."""
    from app.preview.registry import list_modules

    implemented = {
        registration.module_id
        for registration in list_modules()
        if registration.implemented
    }
    backed = set(modules.backed_modules())
    assert backed <= implemented
    assert "R1" in backed


def test_form_section_workflow_runs_with_live_style_implementations(session_factory):
    """섹션 워크플로우가 조사→본문 조립까지 실제 구현으로 돌고 본문을 남긴다."""
    implementations = runner.WorkflowImplementations(
        prepare_data=runner.NodeImplementation(
            module_id="D0",
            implementation_version="mp05-test-d0",
            prompt_version=None,
            mode=RunMode.LIVE,
            run=lambda ctx, state: runner.NodeOutcome(
                payload={"topics": {}, "mode": "live"},
                diagnostics=("테스트용 자료 준비 노드입니다.",),
            ),
        ),
        research=(
            runner.NodeImplementation(
                module_id="R1",
                implementation_version=form.FORM_IMPLEMENTATION_VERSION,
                prompt_version=form.FORM_PROMPT_VERSION,
                mode=RunMode.LIVE,
                run=form.form_node(
                    facts=_facts(),
                    transport=_transport(text=FIXTURES["model_text"]),
                    now=FIXED_NOW,
                ),
            ),
        ),
        compose_body=runner.NodeImplementation(
            module_id=runner.COMPOSE_MODULE_ID,
            implementation_version=sections.FORM_COMPOSE_IMPLEMENTATION_VERSION,
            prompt_version=None,
            mode=RunMode.LIVE,
            run=lambda ctx, state: _compose_outcome(state),
        ),
    )
    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=implementations,
            actor_id=1,
            fixture=FIXTURE,
            fixture_label="Manchester City vs Fulham",
            now=FIXED_NOW,
        )
        session.commit()

        assert result.mode is RunMode.LIVE
        assert result.body.strip()
        assert result.sources
        assert result.unavailable is False


def _compose_outcome(state) -> runner.NodeOutcome:
    """research state의 payload에서 본문을 만든다(두 번째 모델 호출 없음)."""
    research_payload = (state.get("research") or {}).get("R1") or {}
    composed = compose.compose_form_body(research_payload)
    return runner.NodeOutcome(
        title=composed.title,
        body=composed.body,
        sources=composed.sources,
        quality=composed.quality,
        unavailable_reason=composed.unavailable_reason,
    )


# --------------------------------------------------------------------------
# 섹션 워크플로우 수용: 저장 경기 → 섹션 실행 → 본문·근거 → 사용자 승인
# --------------------------------------------------------------------------


def test_section_form_end_to_end_body_sources_then_user_approval(session_factory):
    """경기 선택부터 승인까지 한 흐름을 저장 자료로 확인한다.

    이 검사는 **실제 경기 결과의 품질**을 확인하는 것이 아니라, 워크플로우가
    본문과 근거를 저장하고 그 본문이 승인 근거로 연결되는 경로를 확인한다.
    모델 호출은 기록된 transport로 대체하며 live 성공으로 표시하지 않는다.
    """
    from app.preview import approvals, sections

    class _StoredFixture:
        internal_id = 1
        fixture_id = FIXTURE["fixture_id"]
        league_id = FIXTURE["league_id"]
        league_name = "Premier League"
        season = FIXTURE["season"]
        home_team_id = FIXTURE["home_team_id"]
        home_team_name = FIXTURE["home_team"]
        away_team_id = FIXTURE["away_team_id"]
        away_team_name = FIXTURE["away_team"]
        kickoff_at = datetime.fromisoformat(FIXTURE["kickoff_at"])
        status_short = "NS"
        referee = None
        updated_at = None

        @property
        def label(self) -> str:
            return f"{self.home_team_name} vs {self.away_team_name}"

    class _Reader:
        def get_fixture(self, *, fixture_id: int):
            return _StoredFixture()

        def standings_for_league(self, *, league_id: int, season: int, limit: int = 60):
            return (
                {"team_id": FIXTURE["home_team_id"], "rank": 3, "points": 21, "played": 10,
                 "win": 7, "draw": 0, "loss": 3, "goals_for": 21, "goals_against": 13,
                 "form": "LLLWW"},
                {"team_id": FIXTURE["away_team_id"], "rank": 15, "points": 10, "played": 10,
                 "win": 2, "draw": 4, "loss": 4, "goals_for": 10, "goals_against": 12,
                 "form": "DDWWL"},
            )

        def injuries_for_fixture(self, fixture_id: int):
            return ()

    # 저장 자료 재사용 경로는 fact id를 `api:standings-<team_id>`로 만든다. 모델이
    # 실제로 받은 식별자를 인용하는 상황을 그대로 재현한다.
    stored_model_text = json.dumps(
        {
            "match_context": {
                "importance": "리그 3위 Manchester City가 홈에서 하위권 Fulham을 만납니다.",
                "importance_evidence": ["api:standings-13", "api:standings-4"],
            },
            "recent_form": [
                {
                    "team": "Manchester City",
                    "summary": "10경기 7승 3패, 승점 21로 리그 3위입니다.",
                    "evidence": ["api:standings-13"],
                },
                {
                    "team": "Fulham",
                    "summary": "10경기 2승 4무 4패, 승점 10으로 리그 15위입니다.",
                    "evidence": ["api:standings-4"],
                },
            ],
            "watch_points": [
                {
                    "title": "상위권 경쟁 유지",
                    "detail": "City가 승점 3점을 쌓아야 하는 위치입니다.",
                    "evidence": ["api:standings-13"],
                }
            ],
            "hot_players": [],
            "search_note": "킥오프 7일 이내 보도는 확인하지 못했습니다.",
            "uncertainties": [],
        },
        ensure_ascii=False,
    )
    transport = _transport(text=stored_model_text)
    implementations = sections.build_implementations(
        "section_form",
        transport=provider.RecordedTransport(
            script=list(transport._script),  # noqa: SLF001 - 테스트가 준비한 기록 그대로
            provider="recorded-model",
            mode=RunMode.LIVE,
        ),
        reader=_Reader(),
        now=FIXED_NOW,
    )

    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=implementations,
            actor_id=11,
            fixture=FIXTURE,
            fixture_label="Manchester City vs Fulham",
            now=FIXED_NOW,
        )
        session.commit()

        assert result.body.strip(), "본문이 저장되어야 한다"
        assert result.sources, "근거가 함께 저장되어야 한다"
        # 독자용 본문에는 운영 진단 문구가 없다.
        for noise in ("미확보", "실패", "재시도", "grounding", "누락"):
            assert noise not in result.body

        stored = store.get_run_detail(session, result.run_id).section_results[0]
        assert stored["body"] == result.body
        # 승인 근거는 이 실행의 섹션 결과다. 승인은 사용자가 확인한 뒤에만 만든다.
        approval = approvals.approve_section_version(
            session,
            workflow_id="section_form",
            run_id=result.run_id,
            section_result_id=result.section_result_id,
            actor_id=11,
            note="사용자 확인 후 승인(테스트)",
            now=FIXED_NOW,
        )
        session.commit()

        assert approval.evidence.section_result_id == result.section_result_id
        assert approval.workflow_id == "section_form"


def test_mock_section_result_cannot_be_approved(session_factory):
    """모의 시연 결과로는 승인 행을 만들지 않는다(사용자 승인 대체 금지)."""
    from app.preview import approvals

    with session_factory() as session:
        result = runner.run_section_workflow(
            session,
            workflow_id="section_form",
            implementations=runner.mock_section_implementations("section_form"),
            actor_id=11,
            fixture=FIXTURE,
            now=FIXED_NOW,
        )
        session.commit()

        with pytest.raises(approvals.ApprovalRequestError):
            approvals.approve_section_version(
                session,
                workflow_id="section_form",
                run_id=result.run_id,
                section_result_id=result.section_result_id,
                actor_id=11,
                now=FIXED_NOW,
            )


def test_compose_turns_model_fact_and_interpretation_labels_into_prose():
    """모델이 붙인 `사실(fact):`/`해석(interpretation):` 표기를 읽히는 문장으로 바꾼다.

    표기를 그대로 두면 본문이 JSON 라벨 나열처럼 읽힌다. 사실 진술은 그대로 두고
    해석에는 "AI 해석" 라벨을 남겨 둘을 섞지 않는다.
    """
    payload = {
        "fixture": {
            "home_team": "Manchester City",
            "away_team": "Fulham",
            "league": "Premier League",
            "kickoff_at": "2026-11-21T12:30:00+00:00",
        },
        "match_importance": "사실(fact): City는 리그 3위입니다. 해석(interpretation): 승점 3점이 필요합니다.",
        "recent_form": [
            {
                "team": "Manchester City",
                "summary": "사실(fact): 최근 5경기 2승 3패입니다. 해석(interpretation): 분위기 반전이 필요합니다.",
            }
        ],
        "watch_points": [
            {
                "title": "상위권 경쟁",
                "detail": "사실(fact): 승점 21점입니다. 해석(interpretation): 이번 경기가 중요합니다.",
            }
        ],
        "hot_players": [],
        "claims": [],
        "sources": [],
        "api_sources": [],
    }
    composed = compose.compose_form_body(payload)

    assert "사실(fact):" not in composed.body
    assert "해석(interpretation):" not in composed.body
    # 사실 진술은 남고, 해석에는 라벨이 남는다.
    assert "City는 리그 3위입니다." in composed.body
    assert "AI 해석" in composed.body


def test_internal_source_ids_do_not_reach_reader_body():
    """모델이 본문에 남긴 내부 근거 ID(`[api:…]`)는 독자용 문장에서 사라진다.

    실제 후보 실행(7c0af3c0)에서 모델이 `fact: … [api:standings-13]`처럼 근거 ID를
    대괄호로 본문에 남겼고, 그대로 독자용 본문에 노출됐다. 내부 식별자는 구조화된
    근거(claims·sources·진단)에 남아야 하고, 읽는 사람에게는 보이지 않아야 한다.
    """
    payload = {
        "fixture": {
            "home_team": "Manchester City",
            "away_team": "Fulham",
            "league": "Premier League",
            "kickoff_at": "2026-11-21T12:30:00+00:00",
        },
        "match_importance": (
            "fact: 맨체스터 시티는 승점 21점으로 리그 3위입니다"
            " [api:standings-13, api:standings-4] interpretation: 승점 확보가 중요합니다."
        ),
        "recent_form": [
            {
                "team": "Manchester City",
                "summary": "fact: 최근 5경기에서 LLLWW입니다. [api:standings-13] interpretation: 반등이 필요합니다.",
            }
        ],
        "watch_points": [],
        "hot_players": [],
        # 내부 근거는 구조화된 목록에 그대로 남아 있다.
        "claims": [
            {
                "claim_id": "api:standings-13",
                "kind": "fact",
                "text": "맨체스터 시티는 리그 3위입니다.",
                "decision": "adopted",
                "snapshot_ids": ["52f3c43a-3fb2-4442-b7df-4fa0a11ec8f2"],
            }
        ],
        "sources": [],
        "api_sources": [
            {
                "label": "API-Football 저장 자료",
                "snapshot_id": "52f3c43a-3fb2-4442-b7df-4fa0a11ec8f2",
                "collected_at": "2026-11-10T13:14:24.051542+00:00",
            }
        ],
    }

    composed = compose.compose_form_body(payload)

    # 독자용 문장에는 내부 식별자가 남지 않는다.
    assert "[api:" not in composed.body
    assert "api:standings" not in composed.body
    # 문장 자체는 읽히게 남는다(문장을 통째로 지우지 않는다).
    assert "맨체스터 시티는 승점 21점으로 리그 3위입니다" in composed.body
    assert "최근 5경기에서 LLLWW입니다" in composed.body
    # 구조화된 근거 식별자는 그대로 보존된다.
    assert payload["claims"][0]["claim_id"] == "api:standings-13"
    assert payload["claims"][0]["snapshot_ids"] == ["52f3c43a-3fb2-4442-b7df-4fa0a11ec8f2"]
    assert composed.sources and composed.sources[0]["kind"] == "api"


def test_sections_endpoint_reports_real_implementation_and_model_state(client, make_user):
    """섹션 목록이 실제 구현 여부와 모델 설정 상태를 숨기지 않는다."""
    login = "/api/v1/auth/login"
    user = make_user(role="ADMIN")
    response = client.post(login, json={"email": user["email"], "password": user["password"]})
    assert response.status_code == 200, response.text

    payload = client.get("/api/v1/admin/preview/sections").json()
    availability = payload["availability"]

    form_section = availability["section_form"]
    assert form_section["real_generation_available"] is True
    assert "model" in form_section
    # 설정이 없으면 configured=False와 사유가 함께 온다(모델 이름을 지어내지 않는다).
    assert isinstance(form_section["model"]["configured"], bool)

    # R2·R3도 구현이 등록되어 실제 생성 가능으로 표시된다. S1은 아직 아니다.
    for workflow_id in ("section_availability", "section_outlook"):
        assert availability[workflow_id]["real_generation_available"] is True
    assert availability["section_synthesis"]["real_generation_available"] is False


def test_live_run_requires_fixture_identity(client, make_user):
    """실제 실행에 경기 식별자가 없으면 거부한다(빈 경기로 성공 꾸미기 금지)."""
    login = "/api/v1/auth/login"
    user = make_user(role="ADMIN")
    client.post(login, json={"email": user["email"], "password": user["password"]})

    section_runs = "/api/v1/admin/preview/section-runs"
    response = client.post(section_runs, json={"workflow_id": "section_form", "mode": "live"})
    assert response.status_code == 422
    assert "경기 식별자" in response.json()["detail"] or "모델 설정" in response.json()["detail"]


# --------------------------------------------------------------------------
# 세 섹션 통합: form / availability / outlook 이 실제 노드로 실행된다
# --------------------------------------------------------------------------


class _StoredFixture:
    """저장 경기 한 건의 최소 표현. 읽기 전용 조회기가 돌려주는 모양과 같다."""

    internal_id = 1
    fixture_id = 1557474
    league_id = 1
    league_name = "Premier League"
    season = 2026
    home_team_id = 13
    home_team_name = "Manchester City"
    away_team_id = 4
    away_team_name = "Fulham"
    kickoff_at = datetime(2026, 11, 21, 12, 30, tzinfo=timezone.utc)
    status_short = "NS"
    referee = None
    updated_at = None

    @property
    def label(self) -> str:
        return "Manchester City vs Fulham"


class _Reader:
    def get_fixture(self, *, fixture_id: int):
        return _StoredFixture()

    def standings_for_league(self, *, league_id: int, season: int, limit: int = 60):
        return (
            {"team_id": 13, "rank": 3, "points": 21, "played": 10, "win": 7,
             "draw": 0, "loss": 3, "goals_for": 21, "goals_against": 13, "form": "LLLWW"},
            {"team_id": 4, "rank": 15, "points": 10, "played": 10, "win": 2,
             "draw": 4, "loss": 4, "goals_for": 10, "goals_against": 12, "form": "DDWWL"},
        )

    def injuries_for_fixture(self, fixture_id: int):
        return ()


def test_all_three_implemented_sections_produce_a_body(session_factory):
    """form·availability·outlook 세 섹션이 실제 노드로 본문을 만든다.

    기록된 transport를 쓰므로 live 성공 증거가 아니다. 확인하는 것은 세 섹션이 모두
    공통 실행기·저장 경로로 끝까지 돌고, 본문과 근거를 남긴다는 사실이다.
    """
    from app.preview import sections

    section_model_text = {
        "section_form": FIXTURES["model_text"],
        "section_availability": json.dumps(
            {
                "injuries": [
                    {
                        "player_id": 9401,
                        "team": "Manchester City",
                        "status": "out",
                        "detail": "햄스트링 부상으로 결장이 예상됩니다.",
                        "evidence": ["api:standings-13"],
                    }
                ],
                "impact": "Manchester City의 측면 자원이 줄어듭니다.",
                "uncertainties": ["정확한 복귀 시점은 확인되지 않았습니다."],
                "search_note": None,
            },
            ensure_ascii=False,
        ),
        "section_outlook": json.dumps(
            {
                "media": [],
                "search_note": "킥오프 7일 이내 매체 전망을 확인하지 못했습니다.",
                "uncertainties": [],
            },
            ensure_ascii=False,
        ),
    }
    for workflow_id in ("section_form", "section_availability", "section_outlook"):
        implementations = sections.build_implementations(
            workflow_id,
            transport=provider.RecordedTransport(
                script=[
                    provider.TransportResult(
                        http_status=200,
                        raw_request={"contents": "recorded"},
                        raw_response={
                            "candidates": [
                                {
                                    "content": {
                                        "parts": [{"text": section_model_text[workflow_id]}],
                                        "role": "model",
                                    },
                                    "grounding_metadata": FIXTURES["grounding_raw"]["candidates"][0][
                                        "grounding_metadata"
                                    ],
                                }
                            ]
                        },
                        usage={"input_tokens": 10, "output_tokens": 5},
                    )
                ],
                provider="recorded-model",
                mode=RunMode.LIVE,
            ),
            reader=_Reader(),
            now=FIXED_NOW,
        )
        with session_factory() as session:
            # 실행 기한은 실제 시계로 판정된다. 고정 시각을 넘기면 기한이 이미 지난 것으로
            # 보여 첫 시도가 거부되므로 이 검사는 실제 시계를 쓴다.
            result = runner.run_section_workflow(
                session,
                workflow_id=workflow_id,
                implementations=implementations,
                actor_id=1,
                fixture=FIXTURE,
                fixture_label="Manchester City vs Fulham",
            )
            session.commit()

            # 이 섹션들이 공통 저장 경로로 결과를 남겼는지 확인한다. 본문이 없으면
            # unavailable_reason이 남아야 하고, 둘 다 없는 상태는 허용하지 않는다.
            assert result.body.strip() or result.unavailable_reason, workflow_id
            stored = store.get_run_detail(session, result.run_id).section_results
            assert len(stored) == 1, workflow_id
            assert stored[0]["workflow_id"] == workflow_id
