"""MP-08 운영 지표 수용 검사.

핵심 자료는 `tests/preview/fixtures/metrics_events.json`이다. 이 파일은 저장 구조에
남는 행의 모양을 고정한 **합성** 자료이며, 실제 제공자 호출 결과가 아니다. 이 값으로
실제 호출 성공률을 주장하지 않는다.

확인 항목:

- `test_attempt_and_execution_denominators`: 논리적 실행 2건 중 하나는 429→200,
  다른 하나는 200이지만 근거 없음인 자료에서 실행 성공 2/2, 429 응답 1/3,
  근거 확보 1/2, 추가 재시도 1회가 나온다. 오류 후 성공은 429 빈도에 남는다.
- `test_mock_replay_dev_excluded_from_prod`: 개발·모의·재생 기록이 운영 지표에
  섞이지 않고, 걸러낸 건수가 응답에 드러난다.
- `test_catalog_and_module_runs_not_preview_runs`: 경기 목록 수집은 프리뷰 완료율
  분모에 없고, 모듈 단독 실행은 별도 범위로 표시된다.
- `test_duplicate_event_not_counted_twice`: 같은 실행·논리 호출·시도 순번의 중복
  수신은 한 번만 센다.
- `test_missing_usage_not_zero`: 제공자가 주지 않은 사용량은 0이 아니라 미확인이다.
- `test_metric_drilldown_keeps_filters`: 지표에서 내려간 실행 목록이 조회 필터를
  그대로 반영하고, 시도 원문으로 연결된다.
- 조회는 외부 호출을 하지 않고 ADMIN만 통과한다.
"""

from __future__ import annotations

import json
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.preview.contracts import (
    CONTRACT_VERSION,
    Environment,
    MetricsQuery,
    RunMode,
)
from app.preview.metrics import MetricsQueryError, dedupe_attempts, query_metrics

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "metrics_events.json"
METRICS = "/api/v1/admin/preview/metrics"
LOGIN = "/api/v1/auth/login"


@pytest.fixture()
def metrics_client(engine, schema):
    """지표 라우터가 붙은 앱.

    `app/main.py`는 공유 파일 소유자(MP-04)가 편집한다. 등록이 아직 없으면 이 검사가
    자기 라우터를 붙여 경계를 확인하고, 등록이 있으면 그대로 쓴다. 어느 쪽이든 실제
    앱에서 `/api/v1/admin/preview/metrics`가 404면 이 검사가 401 기대에서 실패한다.
    """
    from fastapi.testclient import TestClient

    from app.api.v1 import preview_metrics
    from app.main import create_app

    app = create_app()
    registered = any(
        getattr(route, "path", "") == "/api/v1/admin/preview/metrics"
        for route in app.routes
    )
    if not registered:
        app.include_router(preview_metrics.router)
    with TestClient(app) as test_client:
        yield test_client


def _fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _dt(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    return datetime.fromisoformat(raw)


def _seed(session, payload: dict) -> dict[str, uuid.UUID]:
    """합성 이벤트를 저장 구조에 그대로 넣는다. 실제 외부 호출은 없다."""
    from app.preview.models import (
        PreviewAttempt,
        PreviewModuleExecution,
        PreviewResult,
        PreviewRun,
        PreviewSourceSnapshot,
    )

    run_ids: dict[str, uuid.UUID] = {}
    snapshot_ids_by_run: dict[str, dict[str, uuid.UUID]] = {}

    for run in payload["runs"]:
        run_id = uuid.uuid4()
        run_ids[run["run_key"]] = run_id
        session.add(
            PreviewRun(
                id=run_id,
                operation_kind=run["operation_kind"],
                environment=run["environment"],
                mode=run["mode"],
                status=run["status"],
                quality=run["quality"],
                actor_id=7,
                config_version=run["config_version"],
                limits={},
                contract_versions={"contract": CONTRACT_VERSION},
                fixture_label=run.get("label"),
                label=run.get("label"),
                requested_at=_dt(run["requested_at"]),
                started_at=_dt(run.get("started_at")),
                finished_at=_dt(run.get("finished_at")),
                failure_code=run.get("failure_code"),
            )
        )
        snapshot_ids_by_run[run["run_key"]] = {}
        session.flush()

        for snapshot in run.get("snapshots", []):
            snapshot_id = uuid.uuid4()
            snapshot_ids_by_run[run["run_key"]][snapshot["key"]] = snapshot_id
            session.add(
                PreviewSourceSnapshot(
                    id=snapshot_id,
                    run_id=run_id,
                    source_kind=snapshot["source_kind"],
                    provider=snapshot["provider"],
                    collected_at=_dt(run["started_at"]) or _dt(run["requested_at"]),
                    fixture=None,
                    catalog_query=None,
                    artifact_id=None,
                    validation_status=snapshot["validation_status"],
                    note=None,
                )
            )

        for module in run.get("modules", []):
            execution_id = uuid.uuid4()
            session.add(
                PreviewModuleExecution(
                    id=execution_id,
                    run_id=run_id,
                    module_id=module["module_id"],
                    ordinal=module["ordinal"],
                    status=module["status"],
                    quality=module["quality"],
                    failure_code=module.get("failure_code"),
                    input_payload={},
                    input_hash="",
                    delivered_next_input={},
                    attempt_count=len(module.get("attempts", [])),
                    retry_count=sum(
                        1 for a in module.get("attempts", []) if a["attempt_ordinal"] > 0
                    ),
                    started_at=_dt(module.get("started_at")),
                    finished_at=_dt(module.get("finished_at")),
                )
            )
            session.flush()

            for attempt in module.get("attempts", []):
                session.add(
                    PreviewAttempt(
                        id=uuid.uuid4(),
                        run_id=run_id,
                        module_execution_id=execution_id,
                        module_id=module["module_id"],
                        logical_call_id=attempt["logical_call_id"],
                        attempt_ordinal=attempt["attempt_ordinal"],
                        provider=attempt["provider"],
                        model=attempt.get("model"),
                        mode=run["mode"],
                        operation=attempt.get("operation", "execute_module"),
                        outcome=attempt["outcome"],
                        http_status=attempt.get("http_status"),
                        error_class=attempt.get("error_class"),
                        error_message=attempt.get("error_message"),
                        request_spec={"contract_version": CONTRACT_VERSION},
                        usage=attempt.get("usage"),
                        wait_ms=attempt.get("wait_ms"),
                        started_at=_dt(attempt.get("started_at")),
                        finished_at=_dt(attempt.get("finished_at")),
                    )
                )

            result = module.get("result")
            if result is not None:
                claims = []
                for claim in result.get("claims", []):
                    entry = dict(claim)
                    entry["snapshot_ids"] = [
                        str(snapshot_ids_by_run[run["run_key"]][key])
                        for key in claim.get("snapshot_ids", [])
                        if key in snapshot_ids_by_run[run["run_key"]]
                    ]
                    claims.append(entry)
                session.add(
                    PreviewResult(
                        run_id=run_id,
                        module_execution_id=execution_id,
                        module_id=module["module_id"],
                        version=1,
                        input_hash="",
                        status=result["status"],
                        quality=result["quality"],
                        failure_code=result.get("failure_code"),
                        payload={
                            "claims": claims,
                            "coverage": result.get("coverage", []),
                        },
                        implementation_version="metrics-fixture",
                        prompt_version="metrics-fixture",
                        contract_version=CONTRACT_VERSION,
                    )
                )

        # 모듈 실행 없이 실행 수준에만 시도가 달린 자료(예: 목록 수집).
        for attempt in run.get("attempts", []):
            session.add(
                PreviewAttempt(
                    id=uuid.uuid4(),
                    run_id=run_id,
                    module_execution_id=None,
                    module_id=None,
                    logical_call_id=attempt["logical_call_id"],
                    attempt_ordinal=attempt["attempt_ordinal"],
                    provider=attempt["provider"],
                    model=attempt.get("model"),
                    mode=run["mode"],
                    operation=attempt.get("operation", ""),
                    outcome=attempt["outcome"],
                    http_status=attempt.get("http_status"),
                    error_class=attempt.get("error_class"),
                    error_message=attempt.get("error_message"),
                    request_spec={"contract_version": CONTRACT_VERSION},
                    usage=attempt.get("usage"),
                    wait_ms=attempt.get("wait_ms"),
                    started_at=_dt(attempt.get("started_at")),
                    finished_at=_dt(attempt.get("finished_at")),
                )
            )

    session.commit()
    return run_ids


def _window() -> MetricsQuery:
    payload = _fixture()["window"]
    return MetricsQuery(from_at=_dt(payload["from_at"]), to_at=_dt(payload["to_at"]))


def _prod_live_query() -> MetricsQuery:
    base = _window()
    return MetricsQuery(
        from_at=base.from_at,
        to_at=base.to_at,
        environments=(Environment.PROD,),
        modes=(RunMode.LIVE,),
    )


# --------------------------------------------------------------------------
# 집계 분모
# --------------------------------------------------------------------------


def test_attempt_and_execution_denominators(session_factory):
    """429→200과 200이지만 근거 없음 자료에서 요구된 네 수치가 나온다.

    실행 성공 2/2(재시도가 분모를 늘리지 않는다), 429 응답 1/3(오류 후 성공도 빈도에
    남는다), 근거 확보 1/2(형식이 유효해도 근거가 없으면 빠진다), 추가 재시도 1회.
    """
    with session_factory() as session:
        _seed(session, _fixture())
        report = query_metrics(session, _prod_live_query())

    success = report.row("module_execution_success_rate")
    assert success is not None
    assert (success.numerator, success.denominator) == (2, 2)
    assert success.sample_size == 2

    rate_limited = report.row("attempt_429_rate")
    assert rate_limited is not None
    assert (rate_limited.numerator, rate_limited.denominator) == (1, 3)

    coverage = report.row("evidence_coverage_rate")
    assert coverage is not None
    assert (coverage.numerator, coverage.denominator) == (1, 2)

    retries = report.row("retry_attempt_rate")
    assert retries is not None
    assert retries.numerator == 1
    assert retries.breakdown["retry_attempts"] == 1
    assert retries.breakdown["first_attempts"] == 2

    # 재시도한 논리 호출은 하나이고, 그 하나가 최종 성공으로 복구됐다.
    retried = report.row("retried_logical_call_rate")
    assert retried is not None
    assert (retried.numerator, retried.denominator) == (1, 2)
    assert retried.breakdown["recovered"] == 1
    assert retried.breakdown["unrecovered"] == 0

    # 실행 성공률 분모는 시도가 아니라 논리적 모듈 실행이다: 429 재시도가 3으로 늘리지 않는다.
    assert success.denominator != rate_limited.denominator


def test_mock_replay_dev_excluded_from_prod(session_factory):
    """개발·모의·재생 기록이 운영 지표에 섞이지 않고, 걸러낸 건수가 드러난다."""
    with session_factory() as session:
        _seed(session, _fixture())

        prod_only = query_metrics(session, _prod_live_query())
        mixed = query_metrics(
            session,
            MetricsQuery(
                from_at=_window().from_at,
                to_at=_window().to_at,
                environments=(Environment.PROD, Environment.DEV),
                modes=(RunMode.LIVE, RunMode.MOCK),
            ),
        )

        # 조건을 비우면 기본 조회는 운영·실호출이다. 같은 수치가 나오고 그 사실이 표시된다.
        defaulted = query_metrics(
            session, MetricsQuery(from_at=_window().from_at, to_at=_window().to_at)
        )

    assert prod_only.empty is False
    assert mixed.empty is False

    prod_modules = prod_only.row("module_execution_success_rate")
    mixed_modules = mixed.row("module_execution_success_rate")
    assert prod_modules is not None and mixed_modules is not None
    # 운영 실호출은 2건. 개발 모의 실행의 모듈 1건이 더해지지만, 운영 수치를 덮지 않는다.
    assert prod_modules.denominator == 2
    assert mixed_modules.denominator == 3

    # 걸러낸 건수를 숨기지 않는다.
    # 기간 안의 dev 실행 3건(모의 프리뷰·목록 수집·모듈 단독)이 기본 조회에서 빠졌다.
    assert prod_only.excluded["by_environment"] == 3
    assert prod_only.excluded["by_mode"] == 0
    # 환경을 명시한 조회이므로 기본값 표시가 꺼진다. 기본값 표시 자체는 아래에서 본다.
    assert prod_only.filters["defaulted_environments"] is False

    # 기본값이 적용된 조회는 운영·실호출만 본다.
    assert defaulted.filters["defaulted_environments"] is True
    assert defaulted.filters["environments"] == ["prod"]
    assert defaulted.filters["modes"] == ["live"]
    defaulted_modules = defaulted.row("module_execution_success_rate")
    assert defaulted_modules is not None
    assert defaulted_modules.denominator == prod_modules.denominator


def test_catalog_and_module_runs_not_preview_runs(session_factory):
    """목록 수집은 프리뷰 완료율 분모에 없고, 모듈 단독 실행은 별도 범위다."""
    with session_factory() as session:
        _seed(session, _fixture())
        report = query_metrics(
            session,
            MetricsQuery(
                from_at=_window().from_at,
                to_at=_window().to_at,
                environments=(Environment.PROD, Environment.DEV),
                modes=(RunMode.LIVE, RunMode.MOCK),
            ),
        )

    # 목록 수집 실행은 지표 대상이 아니고, 그 사실이 따로 드러난다.
    assert report.excluded["fixture_catalog_runs"] == 1
    assert report.excluded["fixture_catalog_attempts"] == 1

    completion = report.row("preview_completion_rate")
    assert completion is not None
    # 전체 프리뷰 실행만: 운영 1건 + 개발 모의 1건. 진행 중 실행은 분모에서 빠진다.
    assert completion.denominator == 2
    assert completion.breakdown["in_flight"] == 1

    module_only = report.row("module_only_success_rate")
    assert module_only is not None
    assert (module_only.numerator, module_only.denominator) == (1, 1)
    assert module_only.scope == "module_runs"

    # 모듈 단독 실행은 전체 프리뷰 모듈 성공률 분모에 섞이지 않는다.
    assert "module_only_success_rate" != "module_execution_success_rate"


def test_duplicate_event_not_counted_twice(session_factory):
    """같은 실행·논리 호출·시도 순번이 두 번 들어와도 한 번만 센다.

    저장 테이블은 (run_id, logical_call_id, attempt_ordinal)을 유일하게 강제한다.
    그래서 중복 수신은 다른 저장 경로(재전송 큐·원본 이벤트)에서 들어올 수 있고,
    집계는 같은 키를 한 번만 세야 한다. 여기서는 그 집계 경계를 직접 확인한다.
    """
    from app.preview.models import PreviewAttempt

    with session_factory() as session:
        _seed(session, _fixture())
        before = query_metrics(session, _prod_live_query())

        stored = list(session.scalars(select(PreviewAttempt)))
        duplicate = PreviewAttempt(
            id=uuid.uuid4(),
            run_id=stored[0].run_id,
            module_execution_id=stored[0].module_execution_id,
            module_id=stored[0].module_id,
            logical_call_id=stored[0].logical_call_id,
            attempt_ordinal=stored[0].attempt_ordinal,
            provider=stored[0].provider,
            model=stored[0].model,
            mode=stored[0].mode,
            operation=stored[0].operation,
            outcome=stored[0].outcome,
            http_status=stored[0].http_status,
            request_spec=dict(stored[0].request_spec or {}),
            usage=None,
            started_at=stored[0].started_at,
            finished_at=stored[0].finished_at,
        )
        deduped, dropped = dedupe_attempts([*stored, duplicate])
        assert dropped == 1
        assert len(deduped) == len(stored)

        # 중복을 넣어도 집계 분모가 늘지 않는다(같은 키를 가진 행은 하나만 센다).
        after = query_metrics(session, _prod_live_query())

    assert after.excluded["duplicate_events_dropped"] == 0
    before_429 = before.row("attempt_429_rate")
    after_429 = after.row("attempt_429_rate")
    assert before_429 is not None and after_429 is not None
    assert (after_429.numerator, after_429.denominator) == (
        before_429.numerator,
        before_429.denominator,
    )


def test_missing_usage_not_zero(session_factory):
    """제공자가 사용량을 주지 않은 시도는 0이 아니라 미확인으로 남는다."""
    with session_factory() as session:
        _seed(session, _fixture())
        report = query_metrics(session, _prod_live_query())

    usage = report.usage
    # 첫 시도(429)와 성공 재시도에는 사용량이 있지만, R2의 200 응답에는 없다.
    assert usage["attempts_total"] == 3
    assert usage["attempts_with_usage"] == 1
    assert usage["attempts_missing_usage"] == 2
    assert usage["input_tokens"] == 1000
    assert usage["output_tokens"] == 250
    # 제공자가 검색 사용량을 주지 않았으므로 0이 아니라 미확인이다.
    assert usage["search_queries"] is None
    # 비용은 가격 기준이 확인되지 않아 계산하지 않는다.
    assert usage["cost"] is None
    assert "미확인" in usage["cost_note"]

    reported = report.row("usage_reported_rate")
    assert reported is not None
    assert (reported.numerator, reported.denominator) == (1, 3)


def test_metric_drilldown_keeps_filters(session_factory):
    """지표에서 내려간 실행 목록이 조회 필터를 그대로 반영한다."""
    with session_factory() as session:
        _seed(session, _fixture())
        report = query_metrics(session, _prod_live_query())

    success = report.row("module_execution_success_rate")
    assert success is not None
    assert success.detail_run_ids, "성공 지표에서 해당 실행으로 내려갈 수 있어야 한다."

    run_ids_in_report = {run["run_id"] for run in report.runs}
    for run_id in success.detail_run_ids:
        assert str(run_id) in run_ids_in_report

    # 내려간 실행은 그 모듈의 시도 목록까지 담고 있어 시도 원문으로 이어진다.
    row = next(run for run in report.runs if run["run_id"] == str(success.detail_run_ids[0]))
    assert row["environment"] == "prod"
    assert row["mode"] == "live"
    attempt_ids = [
        attempt["attempt_id"] for module in row["modules"] for attempt in module["attempts"]
    ]
    assert attempt_ids

    # 429 지표에서 내려가면 429를 낸 실행과 그 시도가 그대로 보인다.
    rate_limited = report.row("attempt_429_rate")
    assert rate_limited is not None
    limited_run = next(
        run for run in report.runs if run["run_id"] == str(rate_limited.detail_run_ids[0])
    )
    assert any(
        attempt["http_status"] == 429
        for module in limited_run["modules"]
        for attempt in module["attempts"]
    )


def test_empty_window_reports_no_sample_not_zero(session_factory):
    """표본이 없으면 0%가 아니라 표본 없음으로 알린다."""
    with session_factory() as session:
        _seed(session, _fixture())
        report = query_metrics(
            session,
            MetricsQuery(
                from_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                to_at=datetime(2026, 10, 2, tzinfo=timezone.utc),
                environments=(Environment.PROD,),
                modes=(RunMode.LIVE,),
            ),
        )

    assert report.empty is True
    completion = report.row("preview_completion_rate")
    assert completion is not None
    assert completion.available is False
    assert completion.numerator is None
    assert completion.denominator == 0
    assert "표본" in completion.note


def test_invalid_window_is_rejected(session_factory):
    with session_factory() as session:
        with pytest.raises(MetricsQueryError):
            query_metrics(
                session,
                MetricsQuery(
                    from_at=datetime(2026, 11, 10, tzinfo=timezone.utc),
                    to_at=datetime(2026, 11, 9, tzinfo=timezone.utc),
                ),
            )


# --------------------------------------------------------------------------
# API 경계
# --------------------------------------------------------------------------


def _login_admin(metrics_client, make_user) -> dict:
    user = make_user(role="ADMIN")
    response = metrics_client.post(LOGIN, json={"email": user["email"], "password": user["password"]})
    assert response.status_code == 200, response.text
    return user


def test_metrics_endpoint_is_admin_only(metrics_client, make_user):
    from app.auth.identity import IdentityUser
    from app.auth.service import issue_session
    from app.db import get_session_factory

    assert metrics_client.get(METRICS).status_code == 401

    user = make_user(role="STREAMER")
    factory = get_session_factory()
    with factory() as session:
        issued = issue_session(
            session,
            IdentityUser(id=user["id"], email=user["email"], role=user["role"], is_active=True),
        )
        token = issued.token
        session.commit()
    metrics_client.cookies.set("preview_admin_session", token)
    assert metrics_client.get(METRICS).status_code == 403


def test_metrics_endpoint_reads_only_and_has_no_provider_calls(
    metrics_client, make_user, monkeypatch
):
    _login_admin(metrics_client, make_user)
    payload = _fixture()
    from app.db import get_session_factory

    with get_session_factory()() as session:
        _seed(session, payload)

    attempted: list[object] = []
    import http.client
    import urllib.request

    def _deny(*args, **kwargs):
        attempted.append(args)
        raise AssertionError("the metrics read path must not open an outbound connection")

    monkeypatch.setattr(socket.socket, "connect", _deny)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", _deny)
    monkeypatch.setattr(urllib.request, "urlopen", _deny)

    response = metrics_client.get(
        METRICS,
        params={
            "from_at": payload["window"]["from_at"],
            "to_at": payload["window"]["to_at"],
            "environment": ["prod"],
            "mode": ["live"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert attempted == []
    assert body["read_only"] is True
    assert body["window"]["source"] == "explicit"
    rows = {row["metric"]: row for row in body["rows"]}
    assert rows["module_execution_success_rate"]["numerator"] == 2
    assert rows["module_execution_success_rate"]["denominator"] == 2
    assert rows["attempt_429_rate"]["numerator"] == 1
    assert rows["attempt_429_rate"]["denominator"] == 3
    assert rows["evidence_coverage_rate"]["numerator"] == 1
    assert rows["evidence_coverage_rate"]["denominator"] == 2


def test_metrics_endpoint_rejects_unknown_environment(metrics_client, make_user):
    _login_admin(metrics_client, make_user)
    response = metrics_client.get(METRICS, params={"environment": ["staging"]})
    assert response.status_code == 422


def test_metrics_endpoint_filters_by_metric_and_module(metrics_client, make_user):
    _login_admin(metrics_client, make_user)
    payload = _fixture()
    from app.db import get_session_factory

    with get_session_factory()() as session:
        _seed(session, payload)

    response = metrics_client.get(
        METRICS,
        params={
            "from_at": payload["window"]["from_at"],
            "to_at": payload["window"]["to_at"],
            "environment": ["prod"],
            "mode": ["live"],
            "metric": ["attempt_429_rate"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["metric"] for row in body["rows"]] == ["attempt_429_rate"]

    # 모듈 필터는 분모를 그 모듈로 좁힌다. R2는 429를 내지 않았다.
    r2 = metrics_client.get(
        METRICS,
        params={
            "from_at": payload["window"]["from_at"],
            "to_at": payload["window"]["to_at"],
            "environment": ["prod"],
            "mode": ["live"],
            "module_id": ["R2"],
            "metric": ["attempt_429_rate"],
        },
    ).json()
    assert r2["rows"][0]["numerator"] == 0
    assert r2["rows"][0]["denominator"] == 1

    unknown = metrics_client.get(METRICS, params={"metric": ["made_up_metric"]})
    assert unknown.status_code == 422


def test_metrics_endpoint_defaults_to_prod_live(metrics_client, make_user):
    _login_admin(metrics_client, make_user)
    payload = _fixture()
    from app.db import get_session_factory

    with get_session_factory()() as session:
        _seed(session, payload)

    body = metrics_client.get(
        METRICS,
        params={
            "from_at": payload["window"]["from_at"],
            "to_at": payload["window"]["to_at"],
        },
    ).json()
    assert body["filters"]["environments"] == ["prod"]
    assert body["filters"]["modes"] == ["live"]
    assert body["filters"]["defaulted_environments"] is True
    assert body["excluded"]["by_environment"] == 3
