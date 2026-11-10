"""운영 지표 집계 (MP-08).

목적은 관리자가 **저장된 기록만으로** 완료율·모듈 성공률·자료 확보율·API 보완·
429·재시도·처리 시간·사용량을 확인하고, 이상한 지표에서 해당 실행의 시도 원문으로
내려가는 것이다. 이 모듈은 조회 전용이며 외부 모델·API를 부르지 않는다. 제공자
클라이언트나 HTTP 전송 계층을 import하지 않는다.

집계 원칙:

1. **운영 실호출과 개발·모의·재생을 섞지 않는다.** 필터가 비어 있으면 기본 조회는
   `environment=prod`·`mode=live`만 집계한다. 다른 축은 관리자가 환경·실행 방식
   필터를 명시해야 나타나고, 걸러낸 건수는 `excluded`에 드러낸다.
2. **논리적 실행과 실제 시도를 구분한다.** 재시도는 실행 성공률의 분모를 늘리지
   않는다. 실패한 시도(429 등)는 성공 뒤에도 오류 빈도에 남는다.
3. **전체 프리뷰와 다른 작업을 섞지 않는다.** `operation_kind=fixture_catalog`는
   지표 대상이 아니고(건수만 드러냄), `operation_kind=module` 단독 실행은
   전체 프리뷰 완료율과 분리된 자기 범위(`module_runs`)로 표시한다.
4. **없는 값을 0으로 채우지 않는다.** 표본이 없는 지표는 `available=False`와
   `표본 없음` 사유로, 제공자가 사용량을 주지 않은 값은 `None`과 누락 건수로
   남긴다. 비용은 가격 기준·적용 시각이 확인되기 전에는 계산하지 않는다(`None`).
5. **중복 수신은 한 번만 센다.** 같은 실행·논리 호출·시도 순번이 두 번 저장되면
   한 번만 집계하고, 버린 건수를 `duplicate_events_dropped`로 드러낸다.
   결과 버전이 여러 개여도 모듈 실행은 하나로 센다(최신 결과를 본다).

지표 행은 `metric`(식별자)·`label`(화면 표시)·`scope`(분모가 무엇인지)·
`numerator`/`denominator`·`sample_size`·`note`·`detail_run_ids`(내려갈 실행)를
가진다. 처리 시간·사용량은 비율이 아니므로 각각 `timings`·`usage`로 따로 내보내고
표본 수와 함께 표시한다. 중앙값·95백분위를 비율의 분자/분모에 끼워 넣지 않는다.
"""

from __future__ import annotations

import math
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.preview.contracts import (
    ClaimDecision,
    CoverageState,
    Environment,
    MetricsQuery,
    MetricsResult,
    OperationKind,
    RunMode,
    RunStatus,
)
from app.preview.models import (
    PreviewAttempt,
    PreviewModuleExecution,
    PreviewResult,
    PreviewRun,
    PreviewSourceSnapshot,
)

__all__ = [
    "DEFAULT_ENVIRONMENTS",
    "DEFAULT_MODES",
    "DEFAULT_WINDOW_DAYS",
    "METRIC_VERSION",
    "MetricRow",
    "MetricsQueryError",
    "MetricsReport",
    "dedupe_attempts",
    "query_metrics",
]

METRIC_VERSION = "mp08-metrics-1"

# 기본 조회는 운영 실호출만 본다. 개발·모의·재생은 명시적 필터로만 등장한다.
DEFAULT_ENVIRONMENTS: tuple[Environment, ...] = (Environment.PROD,)
DEFAULT_MODES: tuple[RunMode, ...] = (RunMode.LIVE,)
DEFAULT_WINDOW_DAYS = 7

TERMINAL_MODULE_STATUSES = frozenset({"succeeded", "failed"})
IN_FLIGHT_RUN_STATUSES = frozenset({"queued", "running", "retry_wait"})

SCOPE_PREVIEW = "preview_runs"
SCOPE_PREVIEW_MODULES = "preview_module_executions"
SCOPE_MODULE_RUNS = "module_runs"
SCOPE_ATTEMPTS = "preview_and_module_attempts"

DEFAULT_VIEW_NOTE = (
    "기본 조회는 운영(prod)·실호출(live) 기록만 집계합니다. "
    "개발·모의·재생 기록은 환경·실행 방식 필터를 지정했을 때만 나타납니다."
)


class MetricsQueryError(ValueError):
    """지표 조회 조건이 성립하지 않는다. 라우터가 422로 돌려준다."""


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    moment = _as_utc(value)
    return moment.isoformat() if moment is not None else None


def _enum_or_none(enum_type, raw: Any):
    if raw is None:
        return None
    try:
        return enum_type(raw)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 결과 구조
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricRow:
    """지표 한 줄. 분자·분모와 표본 수, 내려갈 실행을 함께 담는다."""

    metric: str
    label: str
    scope: str
    numerator: int | None
    denominator: int | None
    note: str
    sample_size: int = 0
    available: bool = True
    detail_run_ids: tuple[uuid.UUID, ...] = ()
    breakdown: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ratio(self) -> float | None:
        if not self.available or not self.denominator:
            return None
        if self.numerator is None:
            return None
        return self.numerator / self.denominator

    def to_contract(self, window: Mapping[str, Any], filters: Mapping[str, Any]) -> MetricsResult:
        """MP-02가 고정한 지표 계약으로 같은 값을 표현한다."""
        return MetricsResult(
            metric=self.metric,
            numerator=self.numerator,
            denominator=self.denominator,
            window=dict(window),
            filters=dict(filters),
            detail_run_ids=self.detail_run_ids,
            note=self.note,
        )

    def to_dict(self, window: Mapping[str, Any], filters: Mapping[str, Any]) -> dict[str, Any]:
        contract = self.to_contract(window, filters).to_dict()
        return {
            "metric": contract["metric"],
            "label": self.label,
            "scope": self.scope,
            "numerator": contract["numerator"],
            "denominator": contract["denominator"],
            "window": contract["window"],
            "filters": contract["filters"],
            "detail_run_ids": contract["detail_run_ids"],
            "note": contract["note"],
            "sample_size": self.sample_size,
            "available": self.available,
            "ratio": self.ratio,
            "breakdown": {
                str(k): (v if not isinstance(v, Mapping) else {str(kk): vv for kk, vv in v.items()})
                for k, v in self.breakdown.items()
            },
        }


@dataclass(frozen=True)
class MetricsReport:
    """지표 묶음. 화면과 응답이 같은 값을 보도록 한 곳에서 만든다."""

    window: Mapping[str, Any]
    filters: Mapping[str, Any]
    rows: tuple[MetricRow, ...]
    timings: Mapping[str, Any]
    usage: Mapping[str, Any]
    runs: tuple[Mapping[str, Any], ...]
    excluded: Mapping[str, Any]
    notes: tuple[str, ...]
    empty: bool
    metric_version: str = METRIC_VERSION

    def row(self, metric: str) -> MetricRow | None:
        for row in self.rows:
            if row.metric == metric:
                return row
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_version": self.metric_version,
            "window": dict(self.window),
            "filters": dict(self.filters),
            "rows": [row.to_dict(self.window, self.filters) for row in self.rows],
            "timings": dict(self.timings),
            "usage": dict(self.usage),
            "runs": [dict(run) for run in self.runs],
            "excluded": dict(self.excluded),
            "notes": list(self.notes),
            "empty": self.empty,
        }


# --------------------------------------------------------------------------
# 조회 보조
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Window:
    from_at: datetime
    to_at: datetime
    defaulted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_at": _iso(self.from_at),
            "to_at": _iso(self.to_at),
            "source": "default" if self.defaulted else "explicit",
            "days": round((self.to_at - self.from_at).total_seconds() / 86400, 2),
        }


@dataclass
class _ModuleAgg:
    module_execution_id: uuid.UUID
    module_id: str
    run_id: uuid.UUID
    status: str
    quality: str
    failure_code: str | None
    latest_result: PreviewResult | None
    attempts: list[PreviewAttempt] = field(default_factory=list)

    @property
    def terminated(self) -> bool:
        return self.status in TERMINAL_MODULE_STATUSES

    def payload(self) -> Mapping[str, Any]:
        return (self.latest_result.payload or {}) if self.latest_result else {}

    def claims(self) -> list[Mapping[str, Any]]:
        return [c for c in self.payload().get("claims") or [] if isinstance(c, Mapping)]

    def coverage(self) -> list[Mapping[str, Any]]:
        return [c for c in self.payload().get("coverage") or [] if isinstance(c, Mapping)]

    def adopted_claims(self) -> list[Mapping[str, Any]]:
        return [
            claim
            for claim in self.claims()
            if str(claim.get("decision")) == ClaimDecision.ADOPTED.value
            and claim.get("snapshot_ids")
        ]

    def coverage_states(self) -> set[str]:
        return {str(entry.get("state")) for entry in self.coverage()}

    def search_missed(self) -> bool:
        return CoverageState.SEARCH_NOT_FOUND.value in self.coverage_states()

    def contract_version(self) -> str | None:
        if self.latest_result is not None and self.latest_result.contract_version:
            return self.latest_result.contract_version
        for attempt in self.attempts:
            version = _attempt_contract_version(attempt)
            if version:
                return version
        return None


def _attempt_contract_version(attempt: PreviewAttempt) -> str | None:
    spec = attempt.request_spec or {}
    version = spec.get("contract_version")
    return str(version) if version else None


def _resolve_window(query: MetricsQuery, now: datetime) -> _Window:
    to_at = _as_utc(query.to_at) or now
    from_at = _as_utc(query.from_at) or (to_at - timedelta(days=DEFAULT_WINDOW_DAYS))
    if from_at >= to_at:
        raise MetricsQueryError("from_at must be earlier than to_at")
    return _Window(from_at=from_at, to_at=to_at, defaulted=query.from_at is None or query.to_at is None)


def _resolve_environments(query: MetricsQuery) -> tuple[Environment, ...]:
    return tuple(query.environments) if query.environments else DEFAULT_ENVIRONMENTS


def _resolve_modes(query: MetricsQuery) -> tuple[RunMode, ...]:
    return tuple(query.modes) if query.modes else DEFAULT_MODES


def dedupe_attempts(rows: Iterable[PreviewAttempt]) -> tuple[list[PreviewAttempt], int]:
    """같은 실행·논리 호출·시도 순번의 중복 수신을 한 번만 남긴다.

    같은 이벤트가 두 번 들어와도 분모가 부풀지 않게 한다. 남길 행은 먼저 시작한
    시도이고, 버린 건수는 응답의 `duplicate_events_dropped`에 드러낸다.
    """
    ordered = sorted(
        rows,
        key=lambda row: (
            _as_utc(row.started_at).isoformat() if _as_utc(row.started_at) else "",
            str(row.id),
        ),
    )
    seen: dict[tuple[str, str, int], PreviewAttempt] = {}
    dropped = 0
    for row in ordered:
        key = (str(row.run_id), row.logical_call_id, int(row.attempt_ordinal))
        if key in seen:
            dropped += 1
            continue
        seen[key] = row
    return list(seen.values()), dropped


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    """가장 가까운 순위 방식. 표본이 적으면 그 사실을 sample_size로 함께 알린다."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(fraction * len(ordered)))
    return float(ordered[rank - 1])


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _duration_ms(started: datetime | None, finished: datetime | None) -> int | None:
    begin = _as_utc(started)
    end = _as_utc(finished)
    if begin is None or end is None:
        return None
    delta = (end - begin).total_seconds() * 1000
    if delta < 0:
        return None
    return int(round(delta))


# --------------------------------------------------------------------------
# 본체
# --------------------------------------------------------------------------


def query_metrics(
    session: Session,
    query: MetricsQuery | None = None,
    *,
    now: datetime | None = None,
) -> MetricsReport:
    """저장된 실행·모듈 실행·시도 행만 읽어 지표를 만든다."""
    query = query or MetricsQuery()
    moment = _as_utc(now) or datetime.now(timezone.utc)
    window = _resolve_window(query, moment)
    environments = _resolve_environments(query)
    modes = _resolve_modes(query)
    environment_values = {env.value for env in environments}
    mode_values = {mode.value for mode in modes}
    module_filter = {m for m in query.module_ids if m}
    model_filter = {m for m in query.models if m}
    version_filter = {v for v in query.contract_versions if v}

    window_runs = list(
        session.scalars(
            select(PreviewRun)
            .where(PreviewRun.requested_at >= window.from_at)
            .where(PreviewRun.requested_at < window.to_at)
            .order_by(PreviewRun.requested_at.desc())
        )
    )

    # 환경·실행 방식으로 걸러낸 건수를 숨기지 않는다.
    excluded_by_environment = sum(
        1 for run in window_runs if run.environment not in environment_values
    )
    remaining = [run for run in window_runs if run.environment in environment_values]
    excluded_by_mode = sum(1 for run in remaining if run.mode not in mode_values)
    selected_runs = [run for run in remaining if run.mode in mode_values]

    catalog_runs = [run for run in selected_runs if run.operation_kind == OperationKind.FIXTURE_CATALOG.value]
    preview_runs = [run for run in selected_runs if run.operation_kind == OperationKind.PREVIEW.value]
    module_runs = [run for run in selected_runs if run.operation_kind == OperationKind.MODULE.value]
    # mock_demo 등 그 밖의 실행 종류는 프리뷰 완료율에 넣지 않는다.
    other_runs = [
        run
        for run in selected_runs
        if run.operation_kind
        not in (
            OperationKind.FIXTURE_CATALOG.value,
            OperationKind.PREVIEW.value,
            OperationKind.MODULE.value,
        )
    ]

    metric_runs = preview_runs + module_runs
    run_ids = [run.id for run in metric_runs]
    catalog_ids = [run.id for run in catalog_runs]

    modules, attempts, results, snapshots = _load_children(session, run_ids + catalog_ids)

    # 실행별 모듈 묶음. 결과 버전은 최신만 본다(버전이 여러 개여도 실행은 하나).
    latest_result: dict[uuid.UUID, PreviewResult] = {}
    for row in results:
        current = latest_result.get(row.module_execution_id)
        if current is None or row.version > current.version:
            latest_result[row.module_execution_id] = row

    module_aggs: dict[uuid.UUID, _ModuleAgg] = {}
    for row in modules:
        module_aggs[row.id] = _ModuleAgg(
            module_execution_id=row.id,
            module_id=row.module_id,
            run_id=row.run_id,
            status=row.status,
            quality=row.quality,
            failure_code=row.failure_code,
            latest_result=latest_result.get(row.id),
        )

    deduped_attempts, duplicates_dropped = dedupe_attempts(attempts)
    for attempt in deduped_attempts:
        if attempt.module_execution_id is not None:
            agg = module_aggs.get(attempt.module_execution_id)
            if agg is not None:
                agg.attempts.append(attempt)

    snapshot_kind: dict[str, str] = {str(row.id): row.source_kind for row in snapshots}

    def module_matches(agg: _ModuleAgg) -> bool:
        if module_filter and agg.module_id not in module_filter:
            return False
        if model_filter and not any(a.model in model_filter for a in agg.attempts):
            return False
        if version_filter and agg.contract_version() not in version_filter:
            return False
        return True

    def run_matches(run: PreviewRun) -> bool:
        if not (module_filter or model_filter or version_filter):
            return True
        return any(
            module_matches(agg) for agg in module_aggs.values() if agg.run_id == run.id
        )

    preview_runs = _only(run_matches, preview_runs)
    module_runs = _only(run_matches, module_runs)
    kept_run_ids = {run.id for run in preview_runs + module_runs}

    def attempts_of(runs: Sequence[PreviewRun]) -> list[PreviewAttempt]:
        ids = {run.id for run in runs}
        selected: list[PreviewAttempt] = []
        for attempt in deduped_attempts:
            if attempt.run_id not in ids:
                continue
            if module_filter:
                module_id = attempt.module_id
                if module_id is None and attempt.module_execution_id is not None:
                    agg = module_aggs.get(attempt.module_execution_id)
                    module_id = agg.module_id if agg else None
                if module_id not in module_filter:
                    continue
            if model_filter and attempt.model not in model_filter:
                continue
            if version_filter and _attempt_contract_version(attempt) not in version_filter:
                continue
            selected.append(attempt)
        return selected

    metric_modules = [
        agg for agg in module_aggs.values() if agg.run_id in kept_run_ids and module_matches(agg)
    ]
    preview_modules = [agg for agg in metric_modules if agg.run_id in {r.id for r in preview_runs}]
    module_run_modules = [agg for agg in metric_modules if agg.run_id in {r.id for r in module_runs}]
    metric_attempts = attempts_of(preview_runs + module_runs)

    filters_echo = {
        "environments": sorted(environment_values),
        "modes": sorted(mode_values),
        "module_ids": sorted(module_filter),
        "models": sorted(model_filter),
        "contract_versions": sorted(version_filter),
        "defaulted_environments": not query.environments,
        "defaulted_modes": not query.modes,
        "note": DEFAULT_VIEW_NOTE if (not query.environments and not query.modes) else (
            "환경·실행 방식을 명시적으로 지정한 조회입니다. 다른 실행 방식과 섞지 마세요."
        ),
    }

    rows: list[MetricRow] = [
        *_preview_rows(preview_runs),
        *_preview_module_rows(preview_modules, snapshot_kind),
        *_module_run_rows(module_run_modules),
        *_attempt_rows(metric_attempts, module_aggs),
    ]

    timings = _timings(preview_runs + module_runs, metric_attempts)
    usage = _usage(metric_attempts)

    notes = [
        "지표는 preview_dev에 저장된 실행·모듈 실행·시도·결과 행만 읽어 계산합니다. "
        "조회가 외부 모델·API를 호출하지 않습니다.",
        DEFAULT_VIEW_NOTE,
        "제공자 내부 검색 호출 수는 저장된 사용량에 없으므로 집계에 포함했다고 주장하지 않습니다.",
        "비용은 가격 기준과 적용 시각이 확인되지 않아 계산하지 않습니다(0이 아니라 미확인).",
    ]
    if module_filter or model_filter or version_filter:
        notes.append(
            "모듈·모델·계약 버전 필터가 걸리면 그 축의 기록이 있는 실행만 분모에 들어갑니다."
        )

    excluded = {
        "by_environment": excluded_by_environment,
        "by_mode": excluded_by_mode,
        "fixture_catalog_runs": len(catalog_runs),
        "fixture_catalog_attempts": sum(1 for a in attempts if a.run_id in set(catalog_ids)),
        "other_operation_runs": len(other_runs),
        "duplicate_events_dropped": duplicates_dropped,
        "note": (
            "경기 목록 수집(fixture_catalog)과 그 밖의 작업 실행은 전체 프리뷰 완료율에 넣지 않습니다. "
            "모듈 단독 실행은 별도 범위로 표시합니다."
        ),
    }

    return MetricsReport(
        window=window.to_dict(),
        filters=filters_echo,
        rows=tuple(rows),
        timings=timings,
        usage=usage,
        runs=_run_rows(preview_runs + module_runs, module_aggs, metric_attempts),
        excluded=excluded,
        notes=tuple(notes),
        empty=not metric_runs,
    )


def _only(predicate, rows: Sequence[PreviewRun]) -> list[PreviewRun]:
    return [row for row in rows if predicate(row)]


def _load_children(
    session: Session, run_ids: Sequence[uuid.UUID]
) -> tuple[
    list[PreviewModuleExecution],
    list[PreviewAttempt],
    list[PreviewResult],
    list[PreviewSourceSnapshot],
]:
    if not run_ids:
        return [], [], [], []
    modules = list(
        session.scalars(
            select(PreviewModuleExecution).where(PreviewModuleExecution.run_id.in_(run_ids))
        )
    )
    attempts = list(
        session.scalars(select(PreviewAttempt).where(PreviewAttempt.run_id.in_(run_ids)))
    )
    results = list(session.scalars(select(PreviewResult).where(PreviewResult.run_id.in_(run_ids))))
    snapshots = list(
        session.scalars(
            select(PreviewSourceSnapshot).where(PreviewSourceSnapshot.run_id.in_(run_ids))
        )
    )
    return modules, attempts, results, snapshots


# --------------------------------------------------------------------------
# 지표 행
# --------------------------------------------------------------------------


def _ratio_row(
    *,
    metric: str,
    label: str,
    scope: str,
    numerator: int | None,
    denominator: int,
    note: str,
    run_ids: Sequence[uuid.UUID] = (),
    breakdown: Mapping[str, Any] | None = None,
    unavailable_note: str = "표본이 없습니다. 0%가 아니라 집계할 기록이 없다는 뜻입니다.",
) -> MetricRow:
    available = denominator > 0
    return MetricRow(
        metric=metric,
        label=label,
        scope=scope,
        numerator=numerator if available else None,
        denominator=denominator,
        note=note if available else unavailable_note,
        sample_size=denominator,
        available=available,
        detail_run_ids=tuple(dict.fromkeys(run_ids)),
        breakdown=dict(breakdown or {}),
    )


def _terminated_preview_runs(runs: Sequence[PreviewRun]) -> list[PreviewRun]:
    terminal = {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}
    return [run for run in runs if run.status in terminal]


def _preview_rows(runs: Sequence[PreviewRun]) -> list[MetricRow]:
    terminated = _terminated_preview_runs(runs)
    ready = [
        run
        for run in terminated
        if run.status == RunStatus.SUCCEEDED.value and run.quality == "ready"
    ]
    drafts = [
        run
        for run in terminated
        if run.status == RunStatus.SUCCEEDED.value and run.quality == "insufficient"
    ]
    pending_quality = [
        run
        for run in terminated
        if run.status == RunStatus.SUCCEEDED.value and run.quality == "pending"
    ]
    failed = [run for run in terminated if run.status == RunStatus.FAILED.value]
    in_flight = [run for run in runs if run.status in IN_FLIGHT_RUN_STATUSES]

    denominator = len(terminated)
    return [
        _ratio_row(
            metric="preview_completion_rate",
            label="프리뷰 완료율",
            scope=SCOPE_PREVIEW,
            numerator=len(ready),
            denominator=denominator,
            note=(
                "종료된 전체 프리뷰 실행 중 품질 ready로 완료된 건입니다. "
                "진행·대기 중인 실행은 종료 분모에 넣지 않습니다."
            ),
            run_ids=[run.id for run in ready],
            breakdown={
                "ready": len(ready),
                "insufficient_draft": len(drafts),
                "quality_pending": len(pending_quality),
                "failed": len(failed),
                "in_flight": len(in_flight),
            },
        ),
        _ratio_row(
            metric="preview_draft_rate",
            label="정보 부족 초안",
            scope=SCOPE_PREVIEW,
            numerator=len(drafts),
            denominator=denominator,
            note="종료된 전체 프리뷰 실행 중 quality=insufficient로 저장된 초안 건입니다.",
            run_ids=[run.id for run in drafts],
        ),
        _ratio_row(
            metric="preview_failure_rate",
            label="프리뷰 실패",
            scope=SCOPE_PREVIEW,
            numerator=len(failed),
            denominator=denominator,
            note="종료된 전체 프리뷰 실행 중 status=failed 건입니다.",
            run_ids=[run.id for run in failed],
            breakdown={
                "failure_codes": {
                    code: sum(1 for run in failed if run.failure_code == code)
                    for code in {run.failure_code for run in failed if run.failure_code}
                }
            },
        ),
        MetricRow(
            metric="preview_in_flight_count",
            label="진행 중 실행 (분모 제외)",
            scope=SCOPE_PREVIEW,
            numerator=len(in_flight),
            denominator=None,
            note="종료되지 않은 실행 수입니다. 완료율 분모에 들어가지 않습니다.",
            sample_size=len(in_flight),
            available=True,
            detail_run_ids=tuple(run.id for run in in_flight),
            breakdown={
                "statuses": {
                    status: sum(1 for run in in_flight if run.status == status)
                    for status in sorted({run.status for run in in_flight})
                }
            },
        ),
    ]


def _preview_module_rows(
    modules: Sequence[_ModuleAgg], snapshot_kind: Mapping[str, str]
) -> list[MetricRow]:
    terminated = [agg for agg in modules if agg.terminated]
    succeeded = [agg for agg in terminated if agg.status == "succeeded"]
    failed = [agg for agg in terminated if agg.status == "failed"]

    def has_stored_evidence(agg: _ModuleAgg) -> bool:
        for claim in agg.adopted_claims():
            if any(str(snapshot_id) in snapshot_kind for snapshot_id in claim["snapshot_ids"]):
                return True
        return False

    def has_api_evidence(agg: _ModuleAgg) -> bool:
        for claim in agg.adopted_claims():
            for snapshot_id in claim["snapshot_ids"]:
                if snapshot_kind.get(str(snapshot_id)) == "api":
                    return True
        return False

    with_evidence = [agg for agg in terminated if has_stored_evidence(agg)]
    search_missed = [agg for agg in terminated if agg.search_missed()]
    supplemented = [agg for agg in search_missed if has_api_evidence(agg)]

    return [
        _ratio_row(
            metric="module_execution_success_rate",
            label="모듈 실행 성공률",
            scope=SCOPE_PREVIEW_MODULES,
            numerator=len(succeeded),
            denominator=len(terminated),
            note=(
                "전체 프리뷰 실행 안의 종료된 논리적 모듈 실행 기준입니다. 재시도는 분모를 늘리지 않고, "
                "형식이 유효한 실패 응답 뒤 성공한 실행도 성공 1건입니다."
            ),
            run_ids=[agg.run_id for agg in succeeded],
            breakdown={
                "succeeded": len(succeeded),
                "failed": len(failed),
                "failure_codes": {
                    code: sum(1 for agg in failed if agg.failure_code == code)
                    for code in {agg.failure_code for agg in failed if agg.failure_code}
                },
            },
        ),
        _ratio_row(
            metric="evidence_coverage_rate",
            label="자료 확보율",
            scope=SCOPE_PREVIEW_MODULES,
            numerator=len(with_evidence),
            denominator=len(terminated),
            note=(
                "종료된 모듈 실행 중 저장된 자료 스냅샷을 참조하는 채택 근거를 얻은 비율입니다. "
                "실행 성공과 별개이며, 근거 없는 성공 응답은 여기서 빠집니다."
            ),
            run_ids=[agg.run_id for agg in with_evidence],
            breakdown={
                "adopted_with_snapshot": len(with_evidence),
                "terminated_without_evidence": len(terminated) - len(with_evidence),
            },
        ),
        _ratio_row(
            metric="api_supplementation_rate",
            label="API 보완 사용",
            scope=SCOPE_PREVIEW_MODULES,
            numerator=len(supplemented),
            denominator=len(search_missed),
            note=(
                "검색 결과를 얻지 못한(SEARCH_NOT_FOUND) 종료 모듈 실행 중, 저장된 API 스냅샷을 근거로 "
                "채택한 실행의 비율입니다. 정상적인 검색+API 결합은 포함하지 않습니다."
            ),
            run_ids=[agg.run_id for agg in supplemented],
            breakdown={
                "search_missed": len(search_missed),
                "api_supplemented": len(supplemented),
            },
            unavailable_note="검색 결과 없음이 기록된 종료 모듈 실행이 없습니다(표본 없음).",
        ),
    ]


def _module_run_rows(modules: Sequence[_ModuleAgg]) -> list[MetricRow]:
    terminated = [agg for agg in modules if agg.terminated]
    succeeded = [agg for agg in terminated if agg.status == "succeeded"]
    return [
        _ratio_row(
            metric="module_only_success_rate",
            label="모듈 단독 실행 성공률",
            scope=SCOPE_MODULE_RUNS,
            numerator=len(succeeded),
            denominator=len(terminated),
            note=(
                "operation_kind=module 단독 실행의 성공률입니다. 전체 프리뷰 완료율과 분리해 표시하며 "
                "프리뷰 실행으로 세지 않습니다."
            ),
            run_ids=[agg.run_id for agg in succeeded],
            breakdown={
                "succeeded": len(succeeded),
                "failed": len(terminated) - len(succeeded),
            },
            unavailable_note="모듈 단독 실행 기록이 없습니다(표본 없음).",
        )
    ]


def _logical_calls(attempts: Sequence[PreviewAttempt]) -> dict[str, list[PreviewAttempt]]:
    calls: dict[str, list[PreviewAttempt]] = {}
    for attempt in attempts:
        key = f"{attempt.module_execution_id or attempt.run_id}:{attempt.logical_call_id}"
        calls.setdefault(key, []).append(attempt)
    return calls


def _attempt_rows(
    attempts: Sequence[PreviewAttempt], module_aggs: Mapping[uuid.UUID, _ModuleAgg]
) -> list[MetricRow]:
    total = len(attempts)
    rate_limited = [a for a in attempts if a.http_status == 429]
    retries = [a for a in attempts if int(a.attempt_ordinal) > 0]
    calls = _logical_calls(attempts)
    retried_calls = {key: value for key, value in calls.items() if len(value) > 1}
    recovered = sum(1 for value in retried_calls.values() if value[-1].outcome == "ok")
    unrecovered = len(retried_calls) - recovered
    with_usage = [a for a in attempts if a.usage]

    run_ids_for = lambda subset: [a.run_id for a in subset]  # noqa: E731 - 짧은 지역 도우미

    return [
        _ratio_row(
            metric="attempt_429_rate",
            label="429 응답",
            scope=SCOPE_ATTEMPTS,
            numerator=len(rate_limited),
            denominator=total,
            note=(
                "실제로 저장된 요청 시도 중 HTTP 429 응답 수입니다. 제공자·모델별 구분은 필터로 확인합니다. "
                "429 뒤 성공해도 이 시도는 남습니다."
            ),
            run_ids=run_ids_for(rate_limited),
            breakdown={
                "by_provider": {
                    provider: sum(1 for a in rate_limited if a.provider == provider)
                    for provider in sorted({a.provider for a in rate_limited})
                }
            },
        ),
        _ratio_row(
            metric="retry_attempt_rate",
            label="추가 재시도 시도",
            scope=SCOPE_ATTEMPTS,
            numerator=len(retries),
            denominator=total,
            note="최초 시도 이후의 실제 요청 시도 수입니다. 논리 호출의 첫 응답을 다시 세지 않습니다.",
            run_ids=run_ids_for(retries),
            breakdown={
                "first_attempts": total - len(retries),
                "retry_attempts": len(retries),
            },
        ),
        _ratio_row(
            metric="retried_logical_call_rate",
            label="재시도한 논리 호출",
            scope=SCOPE_ATTEMPTS,
            numerator=len(retried_calls),
            denominator=len(calls),
            note=(
                "두 번 이상 시도한 논리 호출의 비율입니다. 그중 최종 성공·실패 건수를 함께 표시해 "
                "재시도가 실제로 복구했는지 확인합니다."
            ),
            run_ids=run_ids_for([a for value in retried_calls.values() for a in value]),
            breakdown={
                "logical_calls": len(calls),
                "retried_calls": len(retried_calls),
                "recovered": recovered,
                "unrecovered": unrecovered,
            },
        ),
        _ratio_row(
            metric="usage_reported_rate",
            label="사용량 보고된 시도",
            scope=SCOPE_ATTEMPTS,
            numerator=len(with_usage),
            denominator=total,
            note=(
                "제공자가 사용량을 돌려준 시도의 비율입니다. 보고되지 않은 시도의 토큰은 0으로 채우지 않고 "
                "미확인으로 남깁니다."
            ),
            run_ids=run_ids_for(attempts),
            breakdown={
                "with_usage": len(with_usage),
                "missing_usage": total - len(with_usage),
            },
        ),
    ]


def _timings(runs: Sequence[PreviewRun], attempts: Sequence[PreviewAttempt]) -> dict[str, Any]:
    terminated = [run for run in runs if run.status in {RunStatus.SUCCEEDED.value, RunStatus.FAILED.value}]
    wall = [
        value
        for value in (_duration_ms(run.started_at, run.finished_at) for run in terminated)
        if value is not None
    ]
    attempt_durations = [
        value
        for value in (
            _duration_ms(attempt.started_at, attempt.finished_at) for attempt in attempts
        )
        if value is not None
    ]
    waits = [int(attempt.wait_ms) for attempt in attempts if attempt.wait_ms is not None]

    def block(values: Sequence[float], label: str) -> dict[str, Any]:
        return {
            "label": label,
            "sample_size": len(values),
            "median_ms": _median(values),
            "p95_ms": _percentile(values, 0.95),
            "note": (
                "표본이 없습니다." if not values else "표본이 적으면 중앙값·95백분위를 일반 성능으로 단정하지 마세요."
            ),
        }

    return {
        "run_wall_clock": block(wall, "전체 실행 시간(대기 포함)"),
        "attempt_duration": block(attempt_durations, "요청 시도 소요 시간"),
        "wait_total_ms": sum(waits) if waits else None,
        "wait_samples": len(waits),
        "wait_note": "재시도 대기로 기록된 wait_ms 합계입니다. 값이 없으면 0이 아니라 미확인입니다.",
    }


def _usage(attempts: Sequence[PreviewAttempt]) -> dict[str, Any]:
    def total(key: str) -> int | None:
        values = [
            int(attempt.usage[key])
            for attempt in attempts
            if attempt.usage and attempt.usage.get(key) is not None
        ]
        return sum(values) if values else None

    reported = [a for a in attempts if a.usage]
    return {
        "input_tokens": total("input_tokens"),
        "output_tokens": total("output_tokens"),
        "search_queries": total("search_queries"),
        "attempts_total": len(attempts),
        "attempts_with_usage": len(reported),
        "attempts_missing_usage": len(attempts) - len(reported),
        "cost": None,
        "cost_note": (
            "비용은 가격 기준·적용 시각이 확인되지 않아 계산하지 않았습니다. 0원이 아니라 미확인입니다."
        ),
        "note": (
            "제공자가 돌려준 값만 합산합니다. 값이 없는 시도는 0으로 채우지 않으며, "
            "제공자 내부 검색 호출 수는 저장된 사용량에 없으므로 포함했다고 주장하지 않습니다."
        ),
    }


def _run_rows(
    runs: Sequence[PreviewRun],
    module_aggs: Mapping[uuid.UUID, _ModuleAgg],
    attempts: Sequence[PreviewAttempt],
) -> tuple[Mapping[str, Any], ...]:
    """지표에서 내려갈 실행·모듈 실행·시도 목록. 조회 필터를 그대로 반영한다."""
    attempts_by_module: dict[uuid.UUID, list[PreviewAttempt]] = {}
    for attempt in attempts:
        if attempt.module_execution_id is not None:
            attempts_by_module.setdefault(attempt.module_execution_id, []).append(attempt)

    ordered = sorted(runs, key=lambda run: run.requested_at, reverse=True)
    rows: list[Mapping[str, Any]] = []
    for run in ordered:
        modules = [agg for agg in module_aggs.values() if agg.run_id == run.id]
        rows.append(
            {
                "run_id": str(run.id),
                "operation_kind": run.operation_kind,
                "environment": run.environment,
                "mode": run.mode,
                "status": run.status,
                "quality": run.quality,
                "label": run.label,
                "fixture_label": run.fixture_label,
                "requested_at": _iso(run.requested_at),
                "finished_at": _iso(run.finished_at),
                "failure_code": run.failure_code,
                "modules": [
                    {
                        "module_execution_id": str(agg.module_execution_id),
                        "module_id": agg.module_id,
                        "status": agg.status,
                        "quality": agg.quality,
                        "failure_code": agg.failure_code,
                        "attempt_ids": [
                            str(attempt.id) for attempt in attempts_by_module.get(agg.module_execution_id, [])
                        ],
                        "attempts": [
                            {
                                "attempt_id": str(attempt.id),
                                "logical_call_id": attempt.logical_call_id,
                                "attempt_ordinal": int(attempt.attempt_ordinal),
                                "provider": attempt.provider,
                                "model": attempt.model,
                                "outcome": attempt.outcome,
                                "http_status": attempt.http_status,
                                "error_class": attempt.error_class,
                                "usage_reported": bool(attempt.usage),
                                "duration_ms": _duration_ms(attempt.started_at, attempt.finished_at),
                            }
                            for attempt in attempts_by_module.get(agg.module_execution_id, [])
                        ],
                    }
                    for agg in modules
                ],
            }
        )
    return tuple(rows)
