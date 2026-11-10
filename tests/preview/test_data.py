"""D0 경기 선택·자료 준비 검사 (MP-03).

계획 §6 MP-03의 수용 기준:

- `test_external_fixture_identity`: 외부 경기 ID와 내부 ID를 구분하고 다른 경기를 거부한다.
- `test_empty_injuries_not_zero`: 빈 부상 응답을 '부상자 0명'으로 저장하지 않는다.
- `test_questionable_preserved`: 출전 불확실이 확정 결장으로 바뀌지 않는다.
- `test_wrong_fixture_rejected`: 다른 경기가 오면 D0 자료를 만들지 않는다.
- `test_api_error_not_missing`: API 오류가 '자료 없음'과 다르게 기록된다.
- `test_view_uses_stored_fixtures`: 목록 조회는 저장된 자료만 읽고 수집을 일으키지 않는다.

모든 수집은 주입한 모의 실행기로만 일어난다. 실제 API 전송은 공통 실행기(MP-04)가
준비된 뒤 연결하며, 이 파일은 live 성공을 주장하지 않는다.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.preview import data as preview_data
from app.preview import store
from app.preview.contracts import (
    CONTRACT_VERSION,
    AttemptOutcome,
    CoverageState,
    Environment,
    ExecutionContext,
    ExecutionLimits,
    FixtureCatalogQuery,
    FixtureIdentity,
    ModuleStatus,
    OperationKind,
    ProviderResponse,
    RunMode,
    compute_input_hash,
)
from app.preview.models import (
    PreviewAttempt,
    PreviewModuleExecution,
    PreviewResult,
    PreviewRun,
    PreviewSourceSnapshot,
)
from app.preview.sources import api_football as api
from app.preview.sources.fixtures import FixtureReadAccess

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures" / "api_football.json").read_text(encoding="utf-8")
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


def _response(attempt_id: uuid.UUID | None = None, **overrides) -> ProviderResponse:
    payload = {
        "attempt_id": attempt_id,
        "outcome": AttemptOutcome.OK,
        "http_status": 200,
        "received_at": MOMENT,
    }
    payload.update(overrides)
    return ProviderResponse(**payload)


class RecordingExecutor:
    """호출당 한 번만 응답하는 모의 실행기. 호출 순서와 명세를 그대로 남긴다."""

    def __init__(self, payloads: dict[str, dict], *, failures: dict[str, str] | None = None):
        self.payloads = payloads
        self.failures = failures or {}
        self.calls: list = []

    def __call__(self, spec):
        self.calls.append(spec)
        topic = spec.parameters.get("provider_endpoint")
        failure = self.failures.get(spec.logical_call_id)
        if failure is not None:
            return api.ApiExchange(
                response=_response(
                    outcome=AttemptOutcome.ERROR,
                    http_status=500,
                    error_class="provider_error",
                    error_message=failure,
                ),
                body=None,
            )
        body = self.payloads.get(spec.logical_call_id, {"errors": [], "response": []})
        if isinstance(body, Exception):
            raise body
        return api.ApiExchange(response=_response(), body=body)


def _default_payloads() -> dict[str, dict]:
    return {
        "D0-fixture": FIXTURES["fixture"],
        "D0-form-home": FIXTURES["form_home"],
        "D0-form-away": FIXTURES["form_away"],
        "D0-standings": FIXTURES["standings"],
        "D0-players-home": FIXTURES["players_home"],
        "D0-players-away": FIXTURES["players_away"],
        "D0-injuries": FIXTURES["injuries_sample"],
        "D0-odds": FIXTURES["odds_sample"],
        "D0-predictions": FIXTURES["predictions_sample"],
    }


def _context(*, operation=OperationKind.MODULE, mode=RunMode.LIVE) -> ExecutionContext:
    return ExecutionContext(
        run_id=uuid.uuid4(),
        operation_kind=operation,
        environment=Environment.DEV,
        mode=mode,
        actor_id=11,
        config_version=f"test/{CONTRACT_VERSION}",
        limits=ExecutionLimits(model_requests=0, api_requests=api.D0_API_REQUEST_BUDGET),
    )


def _prepare_run(session, context, fixture=FIXTURE) -> PreviewRun:
    return store.store_run(
        session, context, fixture=fixture, label="D0 검사", status=store.RunStatus.RUNNING
    )


def _run_d0(session, *, payloads=None, failures=None, fixture=FIXTURE, mode=RunMode.LIVE):
    context = _context(mode=mode)
    _prepare_run(session, context, fixture)
    executor = RecordingExecutor(payloads or _default_payloads(), failures=failures)
    result = preview_data.prepare_match_data(
        session, fixture, context, executor=executor, now=MOMENT
    )
    return context, executor, result


# --------------------------------------------------------------------------
# 경기 식별
# --------------------------------------------------------------------------


def test_external_fixture_identity(session_factory):
    """외부 ID와 내부 ID를 섞지 않고, 응답의 경기 ID를 그대로 식별자로 남긴다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session)
        session.commit()

        assert result.fixture.fixture_id == FIXTURE.fixture_id
        assert result.result.module_id == preview_data.D0_MODULE_ID
        assert result.result.version == 1
        assert result.mode is RunMode.LIVE

        # 요청 명세는 외부 ID를 그대로 싣고, 내부 DB ID를 쓰지 않는다.
        identity_spec = executor.calls[0]
        assert identity_spec.logical_call_id == "D0-fixture"
        assert identity_spec.parameters["id"] == 1200001

        # 저장된 실행 행의 fixture_id도 외부 ID다.
        row = session.get(PreviewRun, context.run_id)
        assert row.fixture_id == 1200001
        assert row.operation_kind == OperationKind.MODULE.value

        # 후보 객체는 내부 ID와 외부 ID를 따로 표시한다.
        candidate = preview_data.FixtureCandidate(
            fixture_id=1200001,
            league_id=39,
            league_name="Recorded Premier League",
            season=2026,
            home_team_id=50,
            home_team_name="Recorded Home",
            away_team_id=49,
            away_team_name="Recorded Away",
            kickoff_at=MOMENT,
            status_short="NS",
            origin="stored_db",
            origin_note="검사용",
        )
        assert candidate.identity().fixture_id == 1200001


def test_wrong_fixture_rejected(session_factory):
    """응답의 경기 ID가 다르면 자료를 채택하지 않는다."""
    other = json.loads(json.dumps(FIXTURES["fixture"]))
    other["response"][0]["fixture"]["id"] = 1300002

    with session_factory() as session:
        payloads = _default_payloads()
        payloads["D0-fixture"] = other
        context, executor, result = _run_d0(session, payloads=payloads)
        session.commit()

        assert result.result.status is ModuleStatus.FAILED
        assert result.claims == ()
        identity_coverage = [entry for entry in result.coverage if entry.topic == "경기 식별"]
        assert identity_coverage
        assert identity_coverage[0].state is CoverageState.VALIDATION_REJECTED
        # 경기가 확인되지 않았으므로 나머지 자료 호출을 하지 않는다.
        assert [call.logical_call_id for call in executor.calls] == ["D0-fixture"]

        # 스냅샷은 남기되 채택 근거는 없다.
        snapshots = session.scalars(
            select(PreviewSourceSnapshot).where(PreviewSourceSnapshot.run_id == context.run_id)
        ).all()
        assert len(snapshots) == 1


def test_api_error_not_missing(session_factory):
    """제공자 오류는 '자료 없음'이 아니라 호출 오류로 기록된다."""
    with session_factory() as session:
        context, executor, result = _run_d0(
            session, failures={"D0-odds": "provider said 500"}
        )
        session.commit()

        odd_state = {e.topic: e for e in result.coverage}["경기 전 승무패 배당"]
        assert odd_state.state is CoverageState.CALL_ERROR
        assert odd_state.state is not CoverageState.API_NOT_PROVIDED

        # 실패한 호출도 시도·스냅샷으로 남는다. 시도는 한 번뿐이다(숨은 재시도 없음).
        attempts = session.scalars(
            select(PreviewAttempt).where(
                PreviewAttempt.run_id == context.run_id,
                PreviewAttempt.logical_call_id == "D0-odds",
            )
        ).all()
        assert len(attempts) == 1
        assert attempts[0].attempt_ordinal == 0
        assert attempts[0].outcome == AttemptOutcome.ERROR.value

        # 다른 자료는 그대로 남는다. 한 호출 실패가 전체를 지우지 않는다.
        assert any(
            e.topic == "최근 성적" and e.state is CoverageState.AVAILABLE
            for e in result.coverage
        )


# --------------------------------------------------------------------------
# 부상 의미
# --------------------------------------------------------------------------


def test_empty_injuries_not_zero(session_factory):
    """빈 부상 응답은 '부상자 없음'이 아니라 알 수 없음으로 남는다."""
    with session_factory() as session:
        payloads = _default_payloads()
        payloads["D0-injuries"] = FIXTURES["injuries_empty"]
        context, executor, result = _run_d0(session, payloads=payloads)
        session.commit()

        injuries = {e.topic: e for e in result.coverage}["부상·출전 불확실"]
        assert injuries.state is CoverageState.UNKNOWN
        assert injuries.state is not CoverageState.AVAILABLE
        assert "부상자 없음" in (injuries.detail or "")
        # 부상 관련 claim을 만들지 않는다.
        assert not [c for c in result.claims if c.claim_id.startswith("d0-injury-")]
        assert any("부상자 없음" in note for note in result.diagnostics)


def test_questionable_preserved(session_factory):
    """출전 불확실은 원문 그대로 남고, 결장 확정으로 승격되지 않는다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session)
        session.commit()

        claims = {claim.claim_id: claim for claim in result.claims}
        doubtful = claims["d0-injury-7101"]
        assert "Questionable" in doubtful.text
        assert "결장 확정이 아닙니다" in (doubtful.decision_reason or "")
        assert doubtful.decision.value == "adopted"

        # 표기가 없는 항목은 확정 사실로 채택하지 않는다.
        unknown_marker = claims["d0-injury-7103"]
        assert unknown_marker.decision.value == "excluded"

        # 저장된 결과 본문에도 같은 의미가 남는다.
        saved = session.scalars(
            select(PreviewResult).where(PreviewResult.run_id == context.run_id)
        ).all()
        payload_text = json.dumps([row.payload for row in saved], ensure_ascii=False)
        assert "결장 확정이 아닙니다" in payload_text


# --------------------------------------------------------------------------
# 배당·예측 구분
# --------------------------------------------------------------------------


def test_odds_and_prediction_are_separate_kinds(session_factory):
    """API 예측과 공개 배당을 같은 종류로 합치지 않는다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session)
        session.commit()

        kinds = {claim.claim_id: claim.kind.value for claim in result.claims}
        assert kinds["d0-prediction"] == "api_prediction"
        odds_claims = [key for key in kinds if key.startswith("d0-odds-")]
        assert odds_claims
        assert all(kinds[key] == "external_forecast" for key in odds_claims)

        odds_coverage = {e.topic: e for e in result.coverage}["경기 전 승무패 배당"]
        assert odds_coverage.state is CoverageState.AVAILABLE
        assert "채택 1건" in (odds_coverage.detail or "")


def test_mode_is_recorded_without_upgrading_source(session_factory):
    """실행 방식(mock)과 자료 출처(api)는 다른 축이며, mock을 live로 세지 않는다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session, mode=RunMode.MOCK)
        session.commit()

        assert result.mode is RunMode.MOCK
        assert result.provider_calls == len(executor.calls)
        # mock 실행은 실행기를 불러도 외부 호출로 세지 않는다.
        assert result.external_calls == 0
        # 스냅샷의 출처는 api 그대로다. 재생·모의를 source_kind에 덮어쓰지 않는다.
        assert all(snapshot.source_kind.value == "api" for snapshot in result.snapshots)
        payloads = json.dumps(result.result.payload, ensure_ascii=False)
        assert '"mode": "mock"' in payloads


# --------------------------------------------------------------------------
# 목록 수집과 저장된 목록 조회
# --------------------------------------------------------------------------


def test_mock_run_does_not_count_external_calls(session_factory):
    """mock 문맥에서 실행기를 불러도 외부 호출 0으로 남는다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session, mode=RunMode.MOCK)
        session.commit()

        assert executor.calls, "실행기는 실제로 불렸다"
        assert result.provider_calls == len(executor.calls)
        assert result.external_calls == 0
        assert result.to_dict()["external_calls"] == 0
        assert "mock" in result.to_dict()["external_calls_note"]


def test_live_run_counts_provider_calls_as_external(session_factory):
    """live 문맥에서는 실행기 호출이 외부 호출로 센다. 이 값이 live 근거를 대신하지는 않는다."""
    with session_factory() as session:
        context, executor, result = _run_d0(session, mode=RunMode.LIVE)
        session.commit()

        assert result.provider_calls == len(executor.calls) == 9
        assert result.external_calls == 9


def test_catalog_import_is_separate_operation(session_factory):
    """목록 수집은 fixture_catalog로 기록되고 전체 프리뷰 실행과 섞이지 않는다."""
    query = FixtureCatalogQuery(league_id=39, date="2026-11-12", timezone="Asia/Seoul")
    context = _context(operation=OperationKind.FIXTURE_CATALOG, mode=RunMode.LIVE)
    executor = RecordingExecutor({"catalog-fixtures": FIXTURES["catalog"]})

    with session_factory() as session:
        imported = preview_data.import_fixtures(
            session, query, context=context, executor=executor, season=2026, now=MOMENT
        )
        session.commit()

        assert len(executor.calls) == 1
        assert [c.fixture_id for c in imported.candidates] == [1200001, 1200002]
        assert imported.provider_calls == 1
        # live 문맥이므로 외부 호출로 센다. mock이면 0이다.
        assert imported.external_calls == 1

        run = session.get(PreviewRun, context.run_id)
        assert run.operation_kind == OperationKind.FIXTURE_CATALOG.value
        assert run.fixture_id is None, "목록 수집은 아직 한 경기의 식별자를 갖지 않는다"

        result = session.get(PreviewResult, imported.result_id)
        assert result.module_id == preview_data.CATALOG_MODULE_ID


def test_import_requires_catalog_operation_kind(session_factory):
    """전체 프리뷰 실행 문맥으로 목록 수집을 섞지 않는다."""
    query = FixtureCatalogQuery(league_id=39, date="2026-11-12", timezone="Asia/Seoul")
    context = _context(operation=OperationKind.PREVIEW)
    executor = RecordingExecutor({"catalog-fixtures": FIXTURES["catalog"]})

    with session_factory() as session:
        with pytest.raises(Exception) as excinfo:
            preview_data.import_fixtures(
                session, query, context=context, executor=executor, season=2026
            )
        assert "fixture_catalog" in str(excinfo.value)
        assert executor.calls == []


def test_view_uses_stored_fixtures(session_factory, monkeypatch):
    """목록 조회는 저장된 자료만 읽고 외부 호출을 일으키지 않는다."""
    query = FixtureCatalogQuery(league_id=39, date="2026-11-13", timezone="Asia/Seoul")
    context = _context(operation=OperationKind.FIXTURE_CATALOG, mode=RunMode.LIVE)
    catalog_payload = json.loads(json.dumps(FIXTURES["catalog"]))
    for record in catalog_payload["response"]:
        record["fixture"]["date"] = "2026-11-13T18:00:00+00:00"
    executor = RecordingExecutor({"catalog-fixtures": catalog_payload})

    with session_factory() as session:
        preview_data.import_fixtures(
            session, query, context=context, executor=executor, season=2026, now=MOMENT
        )
        session.commit()

        calls_before = len(executor.calls)

        # 조회 중 어떤 실행기도 불리지 않게 만든다.
        def _deny(*args, **kwargs):
            raise AssertionError("저장된 목록 조회가 외부 수집을 일으켰습니다")

        monkeypatch.setattr(preview_data, "prepare_match_data", _deny)
        monkeypatch.setattr(preview_data, "import_fixtures", _deny)

        listed = preview_data.list_fixtures(session, query=query, limit=10)

        assert len(executor.calls) == calls_before
        assert [candidate.fixture_id for candidate in listed.candidates] == [1200001, 1200002]
        assert all(candidate.origin == "catalog_import" for candidate in listed.candidates)
        assert listed.to_dict()["external_calls"] == 0
        # 저장된 목록 수집이 어떤 실행 방식이었는지 화면에 남는다.
        assert listed.candidates[0].mode is RunMode.LIVE
        assert any(source["origin"] == "catalog_import" for source in listed.sources)


def test_stored_reader_reports_missing_permission(session_factory):
    """읽기 권한이 없으면 조용한 빈 목록이 아니라 필요한 SELECT 경계를 알린다."""

    class DeniedReader:
        def __init__(self):
            self.access_calls = 0

        def access(self):
            self.access_calls += 1
            return FixtureReadAccess(
                readable=False,
                tables={
                    "public.fixture": False,
                    "public.team": False,
                    "public.league": False,
                    "public.injury": False,
                    "public.standings": False,
                },
                role="preview_dev_identity_ro",
                detail="권한 없는 표: public.fixture",
            )

    reader = DeniedReader()
    with session_factory() as session:
        listed = preview_data.list_fixtures(session, reader=reader, limit=5)
        payload = listed.to_dict()

        assert reader.access_calls == 1
        assert payload["stored_access"]["readable"] is False
        assert payload["stored_access"]["required"]
        assert "public.fixture" in payload["stored_access"]["missing"]
        assert "읽기 권한이 없어" in payload["note"]
        assert payload["external_calls"] == 0


def test_stored_reader_merges_db_fixtures(session_factory):
    """권한이 있으면 기존 DB 저장 경기를 읽어 후보로 보여준다."""

    class AllowingReader:
        def access(self):
            return FixtureReadAccess(
                readable=True,
                tables={"public.fixture": True},
                role="preview_reader",
            )

        def list_fixtures(self, **kwargs):
            from app.preview.sources.fixtures import StoredFixture

            assert kwargs["upcoming_only"] is True
            return [
                StoredFixture(
                    internal_id=555,
                    fixture_id=1200001,
                    league_id=39,
                    league_name="Recorded Premier League",
                    season=2026,
                    home_team_id=50,
                    home_team_name="Recorded Home",
                    away_team_id=49,
                    away_team_name="Recorded Away",
                    kickoff_at=FIXTURE.kickoff_at,
                    status_short="NS",
                    venue_name="Recorded Stadium",
                    referee="Recorded Referee",
                    updated_at=MOMENT,
                )
            ]

    with session_factory() as session:
        listed = preview_data.list_fixtures(session, reader=AllowingReader(), limit=5)
        payload = listed.to_dict()

        assert payload["stored_access"]["readable"] is True
        assert len(payload["fixtures"]) == 1
        candidate = payload["fixtures"][0]
        assert candidate["origin"] == "stored_db"
        assert candidate["fixture_id"] == 1200001
        assert candidate["selectable"] is True
        assert candidate["label"] == "Recorded Home vs Recorded Away"


def test_d0_result_versions_do_not_overwrite(session_factory):
    """D0를 다시 돌려도 이전 실행·결과가 지워지지 않고 새 실행으로 쌓인다.

    버전 번호는 모듈 실행 단위다. 재실행은 새 모듈 실행이므로 각 실행이 1부터
    시작하고, 이전 실행의 결과·시도는 그대로 남는다. 재실행을 재시도로 적지 않으므로
    시도 순번은 여전히 0이다.
    """
    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        executor = RecordingExecutor(_default_payloads())

        first = preview_data.prepare_match_data(
            session, FIXTURE, context, executor=executor, now=MOMENT
        )
        second = preview_data.prepare_match_data(
            session, FIXTURE, context, executor=executor, now=MOMENT
        )
        session.commit()

        assert first.result.module_execution_id != second.result.module_execution_id
        assert first.result.version == 1
        assert second.result.version == 1

        executions = session.scalars(
            select(PreviewModuleExecution)
            .where(
                PreviewModuleExecution.run_id == context.run_id,
                PreviewModuleExecution.module_id == preview_data.D0_MODULE_ID,
            )
            .order_by(PreviewModuleExecution.ordinal)
        ).all()
        assert [row.ordinal for row in executions] == [0, 1]

        rows = session.scalars(
            select(PreviewResult)
            .where(PreviewResult.run_id == context.run_id)
            .order_by(PreviewResult.created_at)
        ).all()
        assert len(rows) == 2, "재실행이 이전 결과를 덮어쓰지 않는다"

        attempts = session.scalars(
            select(PreviewAttempt).where(PreviewAttempt.run_id == context.run_id)
        ).all()
        assert {attempt.attempt_ordinal for attempt in attempts} == {0}
        assert len(attempts) == 18, "재실행은 재시도가 아니라 별도 시도다"


def test_input_hash_is_stable_for_same_fixture(session_factory):
    """같은 입력이면 같은 hash가 나온다. 경기가 다르면 달라진다."""
    with session_factory() as session:
        context = _context()
        _prepare_run(session, context)
        executor = RecordingExecutor(_default_payloads())
        first = preview_data.prepare_match_data(
            session, FIXTURE, context, executor=executor, now=MOMENT
        )
        second = preview_data.prepare_match_data(
            session, FIXTURE, context, executor=executor, now=MOMENT
        )
        session.commit()

        assert first.result.input_hash == second.result.input_hash

        other = FixtureIdentity(
            fixture_id=1200002,
            league_id=39,
            season=2026,
            home_team_id=51,
            away_team_id=52,
            kickoff_at=FIXTURE.kickoff_at,
        )
        assert compute_input_hash({"fixture": other.to_dict()}) != compute_input_hash(
            {"fixture": FIXTURE.to_dict()}
        )
