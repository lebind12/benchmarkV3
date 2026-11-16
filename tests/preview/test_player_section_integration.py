"""NS-03/04 선수·부상 섹션 통합 저장·조회·버전 분리·롤백·카드 투영 검사.

로컬 전용 합성 테스트 DB(`preview_mp01_test`)에서만 실행한다.
"""

from __future__ import annotations

import json
import types
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.api.v1 import preview_admin
from app.preview import (
    approvals,
    bundle_pipeline,
    display_names,
    information_bundle as bundle_contract,
    player_section_contracts as psc,
    player_section_store,
    provider,
    registry,
    retrieval,
    runner,
    section_preview,
    store,
)
from app.preview.contracts import (
    CONTRACT_VERSION,
    SECTION_RESULT_CONTRACT_VERSION,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    OperationKind,
    QualityStatus,
    RunMode,
)
from app.preview.localized_names import (
    DisplayNames,
    LocalizedNameIndex,
    PlayerNameRow,
    TeamNameRow,
)
from app.preview.models import (
    PreviewModuleExecution,
    PreviewResult,
    PreviewSectionResult,
)
from app.preview.player_section_models import (
    PreviewInjuryPlayerSection,
    PreviewPlayerNameCandidate,
    PreviewWatchPlayerSection,
)
from app.preview.retry import BudgetLimits
from app.services import home_preview_document

FIXED_NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)
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

ARTICLE_HTML = (
    "<html><head><title>시즌 기록</title></head><body><article>"
    + ("맨체스터 시티 엘링 홀란드와 풀럼 아카데미 유망주 기록입니다. " * 15)
    + "</article></body></html>"
)
PREVIEW_HTML = (
    "<html><head><title>경기 프리뷰</title></head><body><article>"
    + ("BBC는 맨체스터 시티 2-1 승리를 예상했습니다. " * 15)
    + "</article></body></html>"
)


class _FakeHttp:
    def fetch(self, url: str, *, timeout_seconds: int) -> retrieval.HttpFetch:
        del timeout_seconds
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


class _FakeFixtureReader:
    def __init__(self) -> None:
        from app.preview.sources.fixtures import StoredFixture

        self.fixture = StoredFixture(
            internal_id=41125,
            fixture_id=FIXTURE["fixture_id"],
            league_id=FIXTURE["league_id"],
            league_name="프리미어리그",
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

    def access(self):
        return types.SimpleNamespace(readable=True, detail=None)

    def get_fixture(self, *, fixture_id=None, internal_id=None):
        del internal_id
        if fixture_id is not None and int(fixture_id) != FIXTURE["fixture_id"]:
            return None
        return self.fixture

    def standings_for_league(self, *, league_id: int, season: int):
        del league_id, season
        return [
            {
                "team_id": 13,
                "rank": 3,
                "points": 21,
                "played": 10,
                "win": 7,
                "draw": 0,
                "loss": 3,
                "form": "LLLWW",
            },
            {
                "team_id": 4,
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
        del fixture_id
        return []

    def close(self) -> None:
        return None


def _canonical_resolver() -> DisplayNames:
    """실제 DB 이름 해석기(DisplayNames)와 동일한 계약으로 홈/원정 선수·팀을 해석한다."""
    return DisplayNames(
        LocalizedNameIndex(
            teams=(
                TeamNameRow(team_id=13, external_id=50, english_name="Manchester City", name_ko=HOME_KO),
                TeamNameRow(team_id=4, external_id=36, english_name="Fulham", name_ko=AWAY_KO),
            ),
            players=(
                PlayerNameRow(
                    player_id=533,
                    external_id=1100,
                    english_name="Erling Haaland",
                    firstname="Erling",
                    lastname="Haaland",
                    current_team_id=13,
                    name_ko="엘링 홀란드",
                ),
                PlayerNameRow(
                    player_id=544,
                    external_id=44,
                    english_name="Rodri",
                    firstname="Rodrigo",
                    lastname="Hernández",
                    current_team_id=13,
                    name_ko="로드리",
                ),
            ),
        ),
    )


class _TrackingBridge:
    def __init__(self, resolver: DisplayNames) -> None:
        self.names = resolver
        self.active = True
        self.closed = False
        self.rewritten: list[str] = []

    def localize_players(self, rows, *, scope_team_ids=()):
        del scope_team_ids
        return list(rows)

    def register_model_labels(self, labels) -> None:
        del labels
        return None

    def rewrite_body(self, text: str) -> str:
        self.rewritten.append(text)
        return f"[REWRITTEN]{text}"

    def close(self) -> None:
        self.closed = True


def _transport() -> provider.RecordedTransport:
    answers = {
        "discovery_people": {
            "candidates": [
                {"url": "https://example.test/stats", "title": "시즌 기록", "kind": "stats"}
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
                    "selected_player": "Erling Haaland",
                    "selection_reason": "최근 5경기 6골",
                    "team": HOME_KO,
                    "evidence": ["src:stats#p1"],
                },
                {
                    "selected_player": "Academy Prospect",
                    "selection_reason": "측면 돌파가 활발합니다.",
                    "team": AWAY_KO,
                    "evidence": ["src:stats#p1"],
                },
            ],
            "korean_labels": [
                {"original": "Academy Prospect", "korean": "아카데미 유망주", "kind": "player"}
            ],
        },
        "section_availability": {
            "injuries": [
                {
                    "player_name": "Rodri",
                    "team_id": 13,
                    "status": "doubtful",
                    "injury": "무릎 점검",
                    "importance": "중원 영향",
                    "evidence": ["src:stats#p1"],
                }
            ]
        },
        "section_outlook": {
            "media_forecasts": [
                {
                    "publisher": "BBC",
                    "statement": "홈팀 우세 (2-1)",
                    "predicted_score": "2-1",
                    "url": "https://example.test/preview",
                    "evidence": ["src:preview#p1"],
                }
            ]
        },
        "section_ai_forecast": {
            "forecast": "맨체스터 시티가 홈 이점을 살릴 가능성이 높습니다.",
            "predicted_score": {"home": 2, "away": 1},
            "score_reasoning": ["홈 5연승", "공격 전개 우위"],
            "forecast_evidence": ["src:stats#p1"],
        },
    }

    class _BranchTransport(provider.RecordedTransport):
        def __init__(self) -> None:
            super().__init__(script=[], provider="recorded-model", mode=RunMode.LIVE)

        def send(self, spec, *, timeout_seconds, context):
            del timeout_seconds, context
            self.calls.append(spec)
            logical = str(getattr(spec, "logical_call_id", ""))
            answer = answers.get(logical, {"candidates": []})
            payload = json.dumps(answer, ensure_ascii=False)
            return provider.TransportResult(
                http_status=200,
                raw_request={"contents": "recorded"},
                raw_response={
                    "candidates": [
                        {
                            "content": {"parts": [{"text": payload}], "role": "model"},
                            "finishReason": "STOP",
                        }
                    ]
                },
                usage={"input_tokens": 120, "output_tokens": 80},
                duration_ms=5,
            )

    return _BranchTransport()


def _limits() -> BudgetLimits:
    return BudgetLimits(
        model_requests=18,
        api_requests=24,
        attempts_per_call=3,
        deadline_seconds=1800,
        normal_model_calls=6,
    )


def _login_admin(client, make_user) -> int:
    user = make_user(role="ADMIN")
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    assert resp.status_code == 200, resp.text
    return int(user["id"])


_PUBLIC_FIXTURE = {
    "external_id": FIXTURE["fixture_id"],
    "kickoff_at": FIXTURE["kickoff_at"],
    "league": "프리미어리그",
    "home": {"external_id": 50, "name": HOME_KO, "logo_url": None},
    "away": {"external_id": 36, "name": AWAY_KO, "logo_url": None},
}


def test_bundle_pipeline_saves_canonical_tables_and_rereads_every_surface(
    client, make_user, session_factory, monkeypatch
):
    resolver = _canonical_resolver()
    bridge = _TrackingBridge(resolver)
    admin_id = _login_admin(client, make_user)

    monkeypatch.setattr(bundle_pipeline, "_open_name_resolver", lambda team_ids=(): resolver)
    monkeypatch.setattr(display_names, "open_display_names", lambda **kw: bridge)
    monkeypatch.setattr(preview_admin, "_fixture_reader", lambda: _FakeFixtureReader())

    with session_factory() as session:
        outcome = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=admin_id,
            transport=_transport(),
            reader=_FakeFixtureReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()
        run_id = outcome.run_id
        players_sr_id = outcome.section_result_ids["section_players"]
        avail_sr_id = outcome.section_result_ids["section_availability"]

    # 1. DB 3표에 원자 저장 확인
    with session_factory() as session:
        watch = player_section_store.get_watch_player_section(session, players_sr_id)
        orm_watch = session.get(PreviewWatchPlayerSection, players_sr_id)
        assert watch is not None and orm_watch is not None
        assert watch.run_id == run_id
        assert watch.home1 is not None and watch.home1.player_id == 533
        assert watch.home1.name_ko == "엘링 홀란드"
        assert watch.home2 is None
        assert watch.away1 is not None and watch.away1.player_id is None
        assert watch.away1.name_ko == "아카데미 유망주"
        assert watch.away1.translation_candidate_id is not None
        assert watch.away2 is None
        assert orm_watch.home_etc is None
        assert orm_watch.away_etc is None

        injury = player_section_store.get_injury_player_section(session, avail_sr_id)
        orm_injury = session.get(PreviewInjuryPlayerSection, avail_sr_id)
        assert injury is not None and orm_injury is not None
        assert injury.home1 is not None and injury.home1.player_id == 544
        assert injury.home1.name_ko == "로드리"
        assert injury.home1.status == "doubtful"
        assert injury.home2 is None
        assert injury.away1 is None
        assert not hasattr(orm_injury, "home_etc")
        assert not hasattr(orm_injury, "away_etc")

        cand = session.get(PreviewPlayerNameCandidate, watch.away1.translation_candidate_id)
        assert cand is not None
        assert cand.original_name == "Academy Prospect"
        assert cand.candidate_name_ko == "아카데미 유망주"
        assert cand.review_status == "pending"

    # 2. Admin runs/{run_id} & /section-results 정본 재조회 확인(persisted=True, 호출 0회)
    detail_resp = client.get(f"/api/v1/admin/preview/runs/{run_id}")
    assert detail_resp.status_code == 200, detail_resp.text
    detail_json = detail_resp.json()
    players_proc = detail_json["player_section_processing"]["section_players"]
    assert players_proc["persisted"] is True
    assert players_proc["storage_mismatch"] is False
    assert players_proc["output_contract_version"] == psc.WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION
    assert players_proc["home_etc"] is None
    assert players_proc["away_etc"] is None
    assert players_proc["home1"]["external_player_id"] == 1100
    assert (
        players_proc["home1"]["photo_url"]
        == "https://media.api-sports.io/football/players/1100.png"
    )
    assert players_proc["away1"]["player_id"] is None
    assert players_proc["away1"]["external_player_id"] is None
    assert players_proc["away1"]["photo_url"] is None
    assert players_proc["away1"]["candidate_review_status"] == "pending"
    assert players_proc["home2"] is None
    assert players_proc["away2"] is None

    sr_resp = client.get(f"/api/v1/admin/preview/runs/{run_id}/section-results")
    assert sr_resp.status_code == 200, sr_resp.text
    by_wf = {row["workflow_id"]: row for row in sr_resp.json()["section_results"]}
    players_row = by_wf["section_players"]
    assert players_row["persisted"] is True
    assert players_row["storage_mismatch"] is False
    assert players_row["output_contract_version"] == psc.WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION
    assert "아카데미 유망주" in players_row["body"]
    assert not any("[REWRITTEN]" in block["body"] for block in [players_row])
    assert len(players_row["structured"]["players"]) == 2
    assert players_row["structured"]["players"][0]["team_side"] == "home"
    assert (
        players_row["structured"]["players"][0]["photo_url"]
        == "https://media.api-sports.io/football/players/1100.png"
    )
    assert players_row["structured"]["players"][1]["team_side"] == "away"
    assert players_row["structured"]["players"][1]["photo_url"] is None
    assert players_row["structured"]["players"][1]["external_player_id"] is None
    assert players_row["structured"]["players"][1]["unresolved"] is True

    avail_row = by_wf["section_availability"]
    assert avail_row["persisted"] is True
    assert len(avail_row["structured"]["injuries"]) == 1
    assert avail_row["structured"]["injuries"][0]["status"] == "doubtful"
    assert (
        avail_row["structured"]["injuries"][0]["photo_url"]
        == "https://media.api-sports.io/football/players/44.png"
    )

    # 3. section_preview.build_bundle_reader_view 는 신규 선수/부상 본문에 rewrite_body 미실행
    with session_factory() as session:
        run_detail = store.get_run_detail(session, run_id)
        reader = section_preview.build_bundle_reader_view(session, run_detail, names=bridge)
    assert reader is not None
    assert not any("아카데미 유망주" in txt for txt in bridge.rewritten)
    reader_players = next(
        b for b in reader["sections"] if b["section_id"] == "section_players"
    )
    assert "아카데미 유망주" in reader_players["body"]
    assert "[REWRITTEN]" not in reader_players["body"]

    # 4. 섹션 승인 후 홈 공개 문서 read_document 확인(내부 ID 비노출 + 빈 슬롯 생략)
    for wf_id, row in by_wf.items():
        if row["unavailable"]:
            continue
        approve = client.post(
            f"/api/v1/admin/preview/sections/{wf_id}/approvals",
            json={
                "run_id": str(run_id),
                "section_result_id": str(row["section_result_id"]),
                "note": "통합 검증 승인",
            },
        )
        assert approve.status_code == 200, (wf_id, approve.text)

    with session_factory() as session:
        doc = home_preview_document.read_document(
            session, FIXTURE["fixture_id"], fixtures=_PUBLIC_FIXTURE
        )
    assert doc["status"] == "available"
    doc_by_wf = {sec["workflow_id"]: sec for sec in doc["sections"]}
    pub_players = doc_by_wf["section_players"]["structured"]["players"]
    assert len(pub_players) == 2
    assert pub_players[0]["team_side"] == "home"
    assert pub_players[0]["external_player_id"] == 1100
    assert "player_id" not in pub_players[0]
    assert "team_id" not in pub_players[0]
    assert pub_players[1]["team_side"] == "away"
    assert pub_players[1]["photo_url"] is None
    assert pub_players[1]["unresolved"] is True
    assert "player_id" not in pub_players[1]
    assert "team_id" not in pub_players[1]


def test_regeneration_persists_canonical_rows_without_mutating_parent_run(
    session_factory, monkeypatch
):
    resolver = _canonical_resolver()
    monkeypatch.setattr(bundle_pipeline, "_open_name_resolver", lambda team_ids=(): resolver)

    with session_factory() as session:
        base = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=_transport(),
            reader=_FakeFixtureReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()
        base_sr_id = base.section_result_ids["section_players"]
        base_watch_before = player_section_store.get_watch_player_section(session, base_sr_id)
        assert base_watch_before is not None

        regen = bundle_pipeline.run_section_regeneration(
            session,
            section_id="section_players",
            actor_id=8,
            transport=_transport(),
            base_run_id=base.run_id,
            source_mode="reuse",
            reader=_FakeFixtureReader(),
            http=_FakeHttp(),
            limits=_limits(),
            now=FIXED_NOW,
        )
        session.commit()

        assert regen.section_result_id is not None
        assert regen.section_result_id != base_sr_id
        regen_watch = player_section_store.get_watch_player_section(
            session, regen.section_result_id
        )
        orm_regen_watch = session.get(PreviewWatchPlayerSection, regen.section_result_id)
        assert regen_watch is not None and orm_regen_watch is not None
        assert regen_watch.run_id == regen.run_id
        assert regen_watch.home1 is not None and regen_watch.home1.player_id == 533
        assert orm_regen_watch.home_etc is None

        # 부모 실행 정본 행은 그대로 보존된다.
        base_watch_after = player_section_store.get_watch_player_section(session, base_sr_id)
        assert base_watch_after is not None
        assert base_watch_after.section_result_id == base_watch_before.section_result_id


def test_save_player_section_failure_rolls_back_section_result_atomically(
    session_factory, monkeypatch
):
    resolver = _canonical_resolver()
    monkeypatch.setattr(bundle_pipeline, "_open_name_resolver", lambda team_ids=(): resolver)

    with session_factory() as session:
        base = bundle_pipeline.run_bundle_pipeline(
            session,
            fixture=dict(FIXTURE),
            actor_id=7,
            transport=_transport(),
            reader=_FakeFixtureReader(),
            http=_FakeHttp(),
            target_checker=lambda url: True,
            limits=_limits(),
            mode=RunMode.LIVE,
            now=FIXED_NOW,
        )
        session.commit()
        before_sr_count = session.scalar(
            select(func.count()).select_from(PreviewSectionResult)
        )
        before_watch_count = session.scalar(
            select(func.count()).select_from(PreviewWatchPlayerSection)
        )

    def _fail_save(*args, **kwargs):
        raise RuntimeError("boom canonical write")

    monkeypatch.setattr(player_section_store, "save_player_section", _fail_save)

    with session_factory() as session:
        with pytest.raises(RuntimeError, match="boom canonical write"):
            bundle_pipeline.run_section_regeneration(
                session,
                section_id="section_players",
                actor_id=8,
                transport=_transport(),
                base_run_id=base.run_id,
                source_mode="reuse",
                reader=_FakeFixtureReader(),
                http=_FakeHttp(),
                limits=_limits(),
                now=FIXED_NOW,
            )

    with session_factory() as session:
        after_sr_count = session.scalar(
            select(func.count()).select_from(PreviewSectionResult)
        )
        after_watch_count = session.scalar(
            select(func.count()).select_from(PreviewWatchPlayerSection)
        )
        assert after_sr_count == before_sr_count
        assert after_watch_count == before_watch_count


def test_missing_canonical_row_surfaces_explicit_storage_mismatch_without_legacy_fallback(
    client, make_user, session_factory, monkeypatch
):
    resolver = _canonical_resolver()
    bridge = _TrackingBridge(resolver)
    admin_id = _login_admin(client, make_user)

    monkeypatch.setattr(display_names, "open_display_names", lambda **kw: bridge)
    monkeypatch.setattr(preview_admin, "_fixture_reader", lambda: _FakeFixtureReader())

    with session_factory() as session:
        run_id = uuid.uuid4()
        ctx = ExecutionContext(
            run_id=run_id,
            operation_kind=OperationKind.PREVIEW,
            environment=Environment.DEV,
            mode=RunMode.LIVE,
            actor_id=admin_id,
            config_version="test-cfg",
            limits=ExecutionLimits(),
        )
        store.store_run(
            session,
            ctx,
            fixture=store.FixtureIdentity(
                fixture_id=FIXTURE["fixture_id"],
                league_id=FIXTURE["league_id"],
                season=FIXTURE["season"],
                home_team_id=FIXTURE["home_team_id"],
                away_team_id=FIXTURE["away_team_id"],
                kickoff_at=datetime.fromisoformat(FIXTURE["kickoff_at"]),
            ),
            label="mismatch-test",
        )
        exec_row = PreviewModuleExecution(
            id=uuid.uuid4(),
            run_id=run_id,
            module_id="bundle_section_players",
            ordinal=0,
            status="success",
            quality="ready",
            input_payload={},
            input_hash="ih",
            delivered_next_input={},
            started_at=FIXED_NOW,
        )
        session.add(exec_row)
        session.flush()
        res_row = PreviewResult(
            id=uuid.uuid4(),
            run_id=run_id,
            module_execution_id=exec_row.id,
            module_id="bundle_section_players",
            version=1,
            input_hash="ih",
            status="success",
            quality="ready",
            contract_version=CONTRACT_VERSION,
            prompt_version="p-1",
            implementation_version=bundle_pipeline.bundle_sections.PLAYER_SECTION_IMPLEMENTATION_VERSION,
            payload={
                "structured": {
                    "players": [
                        {
                            "selected_player": "Fake Legacy Player",
                            "selection_reason": "숨겨진 대체 표시 금지",
                            "team": HOME_KO,
                        }
                    ]
                }
            },
            created_at=FIXED_NOW,
        )
        session.add(res_row)
        session.flush()

        wf_manifest = registry.get_section_workflow("section_players")
        assert wf_manifest is not None
        sr_row = store.save_section_result(
            session,
            run_id=run_id,
            workflow_id="section_players",
            workflow_version=runner.section_workflow_version(wf_manifest),
            version=1,
            title="주목 선수",
            body="선정 선수: 엘링 홀란드\n선정 이유: 테스트",
            sources=[{"label": "stats", "kind": "stats"}],
            mode=RunMode.LIVE,
            environment=Environment.DEV,
            quality=QualityStatus.READY,
            module_execution_ids=[str(exec_row.id)],
            result_ids=[str(res_row.id)],
            output_contract_version=psc.WATCH_PLAYERS_OUTPUT_CONTRACT_VERSION,
            contract_version=SECTION_RESULT_CONTRACT_VERSION,
            actor_id=admin_id,
            now=FIXED_NOW,
        )
        sr_id = sr_row.id
        wf_forecast = registry.get_section_workflow("section_ai_forecast")
        assert wf_forecast is not None
        forecast_sr = store.save_section_result(
            session,
            run_id=run_id,
            workflow_id="section_ai_forecast",
            workflow_version=runner.section_workflow_version(wf_forecast),
            version=1,
            title="AI 경기 전망",
            body="홈팀 우세가 예상됩니다.\n예상 스코어: 2-1",
            sources=[{"label": "stats", "kind": "stats"}],
            mode=RunMode.LIVE,
            environment=Environment.DEV,
            quality=QualityStatus.READY,
            module_execution_ids=[],
            result_ids=[],
            output_contract_version=wf_forecast.output_contract_version,
            contract_version=SECTION_RESULT_CONTRACT_VERSION,
            actor_id=admin_id,
            now=FIXED_NOW,
        )
        forecast_sr_id = forecast_sr.id
        session.commit()

    # 1. Admin routes report explicit storage_mismatch and never leak "Fake Legacy Player"
    detail = client.get(f"/api/v1/admin/preview/runs/{run_id}").json()
    proc = detail["player_section_processing"]["section_players"]
    assert proc["persisted"] is False
    assert proc["storage_mismatch"] is True
    assert proc["storage_status"] == "storage_mismatch"
    assert "Fake Legacy Player" not in json.dumps(
        detail["player_section_processing"], ensure_ascii=False
    )
    assert "Fake Legacy Player" not in json.dumps(
        detail["section_results"], ensure_ascii=False
    )

    sr_json = client.get(f"/api/v1/admin/preview/runs/{run_id}/section-results").json()
    row = next(r for r in sr_json["section_results"] if r["workflow_id"] == "section_players")
    assert row["persisted"] is False
    assert row["storage_mismatch"] is True
    assert row["structured"]["players"] == []
    assert "Fake Legacy Player" not in json.dumps(sr_json, ensure_ascii=False)

    # 2. Reader preview & public document flag mismatch explicitly
    with session_factory() as session:
        run_detail = store.get_run_detail(session, run_id)
        reader = section_preview.build_bundle_reader_view(session, run_detail, names=bridge)
    assert reader is not None
    assert reader["complete"] is False
    assert all(b["section_id"] != "section_players" for b in reader["sections"])
    assert "정본 저장 행" in str(reader.get("unavailable_reason") or "")

    for wf_target, target_sr in (
        ("section_players", sr_id),
        ("section_ai_forecast", forecast_sr_id),
    ):
        approve = client.post(
            f"/api/v1/admin/preview/sections/{wf_target}/approvals",
            json={
                "run_id": str(run_id),
                "section_result_id": str(target_sr),
                "note": "불일치 확인용 승인",
            },
        )
        assert approve.status_code == 200, (wf_target, approve.text)

    with session_factory() as session:
        doc = home_preview_document.read_document(
            session, FIXTURE["fixture_id"], fixtures=_PUBLIC_FIXTURE
        )
    assert doc["status"] == "available"
    assert doc["complete"] is False
    assert all(s["workflow_id"] != "section_players" for s in doc["sections"])
    assert "Fake Legacy Player" not in json.dumps(doc, ensure_ascii=False)


def test_legacy_contract_still_reads_legacy_payload_and_workflow_versions_isolated(
    client, make_user, session_factory
):
    admin_id = _login_admin(client, make_user)

    with session_factory() as session:
        run_id = uuid.uuid4()
        ctx = ExecutionContext(
            run_id=run_id,
            operation_kind=OperationKind.PREVIEW,
            environment=Environment.DEV,
            mode=RunMode.LIVE,
            actor_id=admin_id,
            config_version="test-cfg",
            limits=ExecutionLimits(),
        )
        store.store_run(
            session,
            ctx,
            fixture=store.FixtureIdentity(
                fixture_id=FIXTURE["fixture_id"],
                league_id=FIXTURE["league_id"],
                season=FIXTURE["season"],
                home_team_id=FIXTURE["home_team_id"],
                away_team_id=FIXTURE["away_team_id"],
                kickoff_at=datetime.fromisoformat(FIXTURE["kickoff_at"]),
            ),
            label="legacy-test",
        )
        exec_row = PreviewModuleExecution(
            id=uuid.uuid4(),
            run_id=run_id,
            module_id="bundle_section_players",
            ordinal=0,
            status="success",
            quality="ready",
            input_payload={},
            input_hash="ih",
            delivered_next_input={},
            started_at=FIXED_NOW,
        )
        session.add(exec_row)
        session.flush()
        res_row = PreviewResult(
            id=uuid.uuid4(),
            run_id=run_id,
            module_execution_id=exec_row.id,
            module_id="bundle_section_players",
            version=1,
            input_hash="ih",
            status="success",
            quality="ready",
            contract_version=CONTRACT_VERSION,
            prompt_version="p-old",
            implementation_version="mp11-bundle-sections-7",
            payload={
                "structured": {
                    "players": [
                        {
                            "selected_player": "레거시 선수",
                            "selection_reason": "기존 계약 호환",
                            "team": HOME_KO,
                        }
                    ]
                }
            },
            created_at=FIXED_NOW,
        )
        session.add(res_row)
        session.flush()
        store.save_section_result(
            session,
            run_id=run_id,
            workflow_id="section_players",
            workflow_version="section_players@legacy0000",
            version=1,
            title="주목 선수",
            body="선정 선수: 레거시 선수\n선정 이유: 기존 계약 호환",
            sources=[],
            mode=RunMode.LIVE,
            environment=Environment.DEV,
            quality=QualityStatus.READY,
            module_execution_ids=[str(exec_row.id)],
            result_ids=[str(res_row.id)],
            output_contract_version="mp11-player-picks-1",
            contract_version=SECTION_RESULT_CONTRACT_VERSION,
            actor_id=admin_id,
            now=FIXED_NOW,
        )
        session.commit()

    sr_json = client.get(f"/api/v1/admin/preview/runs/{run_id}/section-results").json()
    row = sr_json["section_results"][0]
    assert row["persisted"] is False
    assert row["storage_mismatch"] is False
    assert row["structured"]["players"][0]["player"] == "레거시 선수"

    # 워크플로우 버전 분리 확인: section_players / section_availability만 변경, 나머지 불변
    assert SECTION_RESULT_CONTRACT_VERSION == "mp04-section-result-1"
    wf_players = registry.get_section_workflow("section_players")
    wf_avail = registry.get_section_workflow("section_availability")
    wf_odds = registry.get_section_workflow("section_odds")
    wf_outlook = registry.get_section_workflow("section_outlook")
    wf_forecast = registry.get_section_workflow("section_ai_forecast")
    assert wf_players.output_contract_version == "ns01-watch-players-1"
    assert wf_avail.output_contract_version == "ns01-injury-players-1"
    assert runner.section_workflow_version(wf_odds) == "section_odds@49923b1c5dcb467a"
    assert wf_outlook.output_contract_version == "section_outlook-output-1"
    assert wf_forecast.output_contract_version == "mp11-ai-forecast-output-1"


def _patch_initial_section_runtime(monkeypatch, *, transport, reader):
    resolver = _canonical_resolver()
    monkeypatch.setattr(preview_admin, "_model_transport", lambda mode: transport)
    monkeypatch.setattr(preview_admin, "_fixture_reader", lambda: reader)
    monkeypatch.setattr(
        bundle_pipeline,
        "_open_name_resolver",
        lambda team_ids=(): resolver,
    )

    orig_collect = retrieval.collect_with_bodies

    def _collect_with_fake_http(*args, **kwargs):
        kwargs["http"] = _FakeHttp()
        kwargs["target_checker"] = lambda url: True
        return orig_collect(*args, **kwargs)

    monkeypatch.setattr(retrieval, "collect_with_bodies", _collect_with_fake_http)


def test_initial_live_section_run_without_base_run_uses_bundle_graph_and_persists_canonical_tables(
    client, make_user, session_factory, monkeypatch
):
    """base_run_id 없는 최초 LIVE 섹션 실행은 해당 선수/부상 섹션만 LangGraph로 생성하고 정본 3표에 저장한다."""
    _login_admin(client, make_user)

    for workflow_id in ("section_players", "section_availability"):
        transport = _transport()
        reader = _FakeFixtureReader()
        _patch_initial_section_runtime(monkeypatch, transport=transport, reader=reader)

        resp = client.post(
            "/api/v1/admin/preview/section-runs",
            json={
                "workflow_id": workflow_id,
                "mode": "live",
                "fixture_id": FIXTURE["fixture_id"],
                "league_id": FIXTURE["league_id"],
                "season": FIXTURE["season"],
                "home_team_id": FIXTURE["home_team_id"],
                "away_team_id": FIXTURE["away_team_id"],
                "kickoff_at": FIXTURE["kickoff_at"],
                "fixture_label": "Manchester City vs Fulham",
            },
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        run_id = uuid.UUID(data["run_id"])
        result_id = uuid.UUID(data["section_result_id"])

        assert data["workflow_id"] == workflow_id
        assert data["status"] == "succeeded"
        assert data["parent_run_id"] is None
        assert data["base_result_id"] is None
        assert data["bundle_reused"] is False
        assert data["bundle_id"]
        assert data["expected_model_calls"] == 2
        assert data["no_model_call"] is False
        assert data["other_sections_reused"] is False
        assert data["workflow_version"] == runner.section_workflow_version(
            registry.get_section_workflow(workflow_id)
        )

        # 선택한 섹션(1개) + 필요한 인물 조사(discovery_people)만 호출한다.
        called_ids = {str(getattr(spec, "logical_call_id", "")) for spec in transport.calls}
        assert called_ids == {"discovery_people", workflow_id}, called_ids

        with session_factory() as session:
            section_rows = list(
                session.scalars(
                    select(PreviewSectionResult).where(PreviewSectionResult.run_id == run_id)
                )
            )
            assert len(section_rows) == 1
            assert section_rows[0].id == result_id
            assert section_rows[0].workflow_id == workflow_id

            if workflow_id == "section_players":
                watch = player_section_store.get_watch_player_section(session, result_id)
                orm_watch = session.get(PreviewWatchPlayerSection, result_id)
                assert watch is not None and orm_watch is not None
                assert orm_watch.home_etc is None
                assert orm_watch.away_etc is None
                assert watch.home1 is not None and watch.home1.name_ko == "엘링 홀란드"
                assert watch.away1 is not None and watch.away1.translation_candidate_id is not None
                cand = session.get(PreviewPlayerNameCandidate, watch.away1.translation_candidate_id)
                assert cand is not None
                assert cand.candidate_name_ko == "아카데미 유망주"
            else:
                injury = player_section_store.get_injury_player_section(session, result_id)
                orm_injury = session.get(PreviewInjuryPlayerSection, result_id)
                assert injury is not None and orm_injury is not None
                assert injury.home1 is not None and injury.home1.name_ko == "로드리"
                assert injury.home1.status == "doubtful"

        detail_json = client.get(f"/api/v1/admin/preview/runs/{run_id}").json()
        proc = detail_json["player_section_processing"][workflow_id]
        assert proc["persisted"] is True
        assert proc["storage_status"] == "persisted"
        assert proc["storage_mismatch"] is False
        assert detail_json["section_results"][0]["storage_mismatch"] is False

        sr_json = client.get(f"/api/v1/admin/preview/runs/{run_id}/section-results").json()
        assert sr_json["section_results"][0]["persisted"] is True
        assert sr_json["section_results"][0]["storage_status"] == "persisted"
        assert sr_json["section_results"][0]["storage_mismatch"] is False


def test_initial_section_run_boundary_guards_and_regeneration_preserved(
    client, make_user, session_factory, monkeypatch
):
    """최초 실행 범위 제한(주목·부상 외 422, reuse/fixture 누락 422)과 기존 base_run_id 재생성 경로를 보존한다."""
    _login_admin(client, make_user)
    transport = _transport()
    reader = _FakeFixtureReader()
    _patch_initial_section_runtime(monkeypatch, transport=transport, reader=reader)

    # 1) base_run_id 없는 타 섹션 최초 단독 실행은 422로 거부 (범위 확대·가짜 base ID 금지)
    for forbidden_wf in ("section_outlook", "section_odds", "section_ai_forecast"):
        resp = client.post(
            "/api/v1/admin/preview/section-runs",
            json={
                "workflow_id": forbidden_wf,
                "mode": "live",
                "fixture_id": FIXTURE["fixture_id"],
                "league_id": FIXTURE["league_id"],
                "season": FIXTURE["season"],
                "home_team_id": FIXTURE["home_team_id"],
                "away_team_id": FIXTURE["away_team_id"],
                "kickoff_at": FIXTURE["kickoff_at"],
            },
        )
        assert resp.status_code == 422, (forbidden_wf, resp.text)

    # 2) base_run_id 없는 source_mode=reuse 거부(422) & 경기 식별자 누락 거부(422)
    resp_reuse = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "live",
            "source_mode": "reuse",
            "fixture_id": FIXTURE["fixture_id"],
            "kickoff_at": FIXTURE["kickoff_at"],
        },
    )
    assert resp_reuse.status_code == 422, resp_reuse.text

    resp_no_fixture = client.post(
        "/api/v1/admin/preview/section-runs",
        json={"workflow_id": "section_players", "mode": "live"},
    )
    assert resp_no_fixture.status_code == 422, resp_no_fixture.text
    assert transport.calls == []

    # 3) 존재하지 않는 명시적 base_run_id 재생성은 기존대로 404 base run not found
    resp_missing_base = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "live",
            "source_mode": "refresh",
            "base_run_id": str(uuid.uuid4()),
        },
    )
    assert resp_missing_base.status_code == 404, resp_missing_base.text
    assert resp_missing_base.json()["detail"] == "base run not found"

    # 4) 최초 실행으로 만든 run을 base_run_id로 넘겨 source_mode=reuse 재생성 보존 확인
    initial_resp = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "live",
            "fixture_id": FIXTURE["fixture_id"],
            "league_id": FIXTURE["league_id"],
            "season": FIXTURE["season"],
            "home_team_id": FIXTURE["home_team_id"],
            "away_team_id": FIXTURE["away_team_id"],
            "kickoff_at": FIXTURE["kickoff_at"],
            "fixture_label": "Manchester City vs Fulham",
        },
    )
    assert initial_resp.status_code == 200, initial_resp.text
    initial_data = initial_resp.json()
    initial_run_id = initial_data["run_id"]

    regen_resp = client.post(
        "/api/v1/admin/preview/section-runs",
        json={
            "workflow_id": "section_players",
            "mode": "live",
            "source_mode": "reuse",
            "base_run_id": initial_run_id,
            "base_result_id": initial_data["section_result_id"],
        },
    )
    assert regen_resp.status_code == 200, regen_resp.text
    regen_data = regen_resp.json()
    assert regen_data["parent_run_id"] == initial_run_id
    assert regen_data["bundle_reused"] is True
    assert regen_data["expected_model_calls"] == 1
    assert regen_data["other_sections_reused"] is True

    with session_factory() as session:
        regen_watch = session.scalar(
            select(PreviewWatchPlayerSection).where(
                PreviewWatchPlayerSection.section_result_id
                == uuid.UUID(regen_data["section_result_id"])
            )
        )
        assert regen_watch is not None
