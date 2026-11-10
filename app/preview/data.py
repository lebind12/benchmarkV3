"""D0 경기 선택과 API 자료 (MP-03).

이 파일이 제공하는 것:

- `import_fixtures`: 관리자가 명시한 `FixtureCatalogQuery`로 경기 후보를 **수집해
  저장**한다. `operation_kind=fixture_catalog`로 기록하며 전체 프리뷰 실행과 구분한다.
- `list_fixtures`: **저장된 것만** 읽는다. 외부 API를 부르지 않는다. 화면을 여는 것만으로
  수집이 일어나지 않는다.
- `prepare_match_data`: `FixtureIdentity` + `ExecutionContext`를 받아 D0 `ModuleResult`
  (버전 기록)와 `SourceSnapshot`을 만든다.

경계:

- 전송 계층은 없다. 실행기(`ApiExecutor`, MP-04의 `execute_request`가 붙는 자리)를
  주입받아 **호출당 한 번** 부른다. 숨은 재시도를 만들지 않는다.
- 조회 경로는 제공자 클라이언트를 import하지 않는다. 이 파일은 `httpx`/`requests`를
  쓰지 않는다.
- 실패는 "자료 없음"으로 바꾸지 않는다. 제공자 오류는 `CALL_ERROR`, 응답이 성공했지만
  자료가 없는 경우만 `API_NOT_PROVIDED`다. 빈 부상 응답은 `UNKNOWN`이며 '부상자 0명'이
  아니다.
- 새 테이블·마이그레이션을 만들지 않는다. 저장은 MP-02가 만든 `preview_dev` 표를 그대로
  쓴다(실행·스냅샷·시도·아티팩트·결과 버전).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.preview import artifacts as artifact_store
from app.preview import store
from app.preview.contracts import (
    CONTRACT_VERSION,
    MODULE_INPUT_VERSION,
    AttemptOutcome,
    ClaimDecision,
    ClaimKind,
    ContractError,
    CoverageEntry,
    CoverageState,
    EvidenceClaim,
    ExecutionContext,
    FailureCode,
    FixtureCatalogQuery,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    OperationKind,
    QualityStatus,
    RequestSpec,
    RunMode,
    RunStatus,
    SourceKind,
    SourceSnapshot,
    ValidationStatus,
    compute_input_hash,
)
from app.preview.models import PreviewModuleExecution, PreviewResult, PreviewRun
from app.preview.sources import api_football as api
from app.preview.sources.fixtures import (
    FixtureReadAccess,
    FixtureReadDenied,
    StoredFixture,
    StoredFixtureReader,
)

__all__ = [
    "CATALOG_MODULE_ID",
    "D0_IMPLEMENTATION_VERSION",
    "D0_MODULE_ID",
    "D0Result",
    "FixtureCandidate",
    "FixtureListResult",
    "ImportedFixtures",
    "catalog_candidates",
    "import_fixtures",
    "list_fixtures",
    "prepare_match_data",
    "store_candidates",
]

D0_MODULE_ID = "D0"
CATALOG_MODULE_ID = "fixture_catalog"
D0_IMPLEMENTATION_VERSION = "mp03-d0-1"
MAX_CATALOG_CANDIDATES = 200


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------
# 경기 후보
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FixtureCandidate:
    """선택 화면에 보이는 경기 후보 한 건.

    `fixture_id`는 API-Football 외부 경기 ID이며 동일성 키다. `origin`은 이 후보가
    저장된 기존 DB에서 왔는지, 저장된 목록 수집 기록에서 왔는지 구분한다.
    """

    fixture_id: int
    league_id: int
    league_name: str | None
    season: int
    home_team_id: int | None
    home_team_name: str | None
    away_team_id: int | None
    away_team_name: str | None
    kickoff_at: datetime
    status_short: str | None
    origin: str
    origin_note: str
    run_id: uuid.UUID | None = None
    mode: RunMode | None = None

    @property
    def label(self) -> str:
        home = self.home_team_name or f"team {self.home_team_id}"
        away = self.away_team_name or f"team {self.away_team_id}"
        return f"{home} vs {away}"

    @property
    def selectable(self) -> bool:
        """팀이 확정되지 않은 경기는 D0 대상이 아니다. 0으로 채우지 않는다."""
        return self.home_team_id is not None and self.away_team_id is not None

    def identity(self) -> FixtureIdentity:
        if not self.selectable:
            raise ValueError("home/away team ids are not both confirmed")
        return FixtureIdentity(
            fixture_id=self.fixture_id,
            league_id=self.league_id,
            season=self.season,
            home_team_id=self.home_team_id,  # type: ignore[arg-type]
            away_team_id=self.away_team_id,  # type: ignore[arg-type]
            kickoff_at=self.kickoff_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "league_id": self.league_id,
            "league_name": self.league_name,
            "season": self.season,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "label": self.label,
            "kickoff_at": self.kickoff_at.isoformat(),
            "status_short": self.status_short,
            "origin": self.origin,
            "origin_note": self.origin_note,
            "run_id": str(self.run_id) if self.run_id else None,
            "mode": self.mode.value if self.mode else None,
            "selectable": self.selectable,
        }


def _candidate_from_stored(record: StoredFixture) -> FixtureCandidate:
    return FixtureCandidate(
        fixture_id=record.fixture_id,
        league_id=record.league_id,
        league_name=record.league_name,
        season=record.season,
        home_team_id=record.home_team_id,
        home_team_name=record.home_team_name,
        away_team_id=record.away_team_id,
        away_team_name=record.away_team_name,
        kickoff_at=record.kickoff_at,
        status_short=record.status_short,
        origin="stored_db",
        origin_note=(
            "기존 DB에 저장된 경기 자료를 읽기 전용으로 표시합니다. 새 수집이 아닙니다."
        ),
    )


def _candidate_from_payload(raw: Mapping[str, Any], *, run_id, mode, collected_at):
    kickoff = raw.get("kickoff_at")
    moment = datetime.fromisoformat(str(kickoff)) if kickoff else collected_at
    return FixtureCandidate(
        fixture_id=int(raw["fixture_id"]),
        league_id=int(raw["league_id"]),
        league_name=raw.get("league_name"),
        season=int(raw["season"]),
        home_team_id=(
            int(raw["home_team_id"]) if raw.get("home_team_id") is not None else None
        ),
        home_team_name=raw.get("home_team_name"),
        away_team_id=(
            int(raw["away_team_id"]) if raw.get("away_team_id") is not None else None
        ),
        away_team_name=raw.get("away_team_name"),
        kickoff_at=moment,
        status_short=raw.get("status_short"),
        origin="catalog_import",
        origin_note=(
            f"저장된 목록 수집 기록입니다(실행 방식: {mode.value}). "
            "이 목록을 다시 수집하지 않습니다."
        ),
        run_id=run_id,
        mode=mode,
    )


@dataclass(frozen=True)
class FixtureListResult:
    """저장된 후보 목록과, 어떤 저장 출처를 읽었는지에 대한 설명."""

    candidates: tuple[FixtureCandidate, ...]
    sources: tuple[Mapping[str, Any], ...]
    stored_access: Mapping[str, Any]
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixtures": [candidate.to_dict() for candidate in self.candidates],
            "sources": [dict(source) for source in self.sources],
            "stored_access": dict(self.stored_access),
            "note": self.note,
            "external_calls": 0,
        }


# --------------------------------------------------------------------------
# 목록 수집 (명시적 import)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportedFixtures:
    """목록 수집 결과. 저장된 실행·결과 ID를 함께 돌려준다."""

    run_id: uuid.UUID
    module_execution_id: uuid.UUID
    result_id: uuid.UUID
    candidates: tuple[FixtureCandidate, ...]
    mode: RunMode
    status: ModuleStatus
    # 주입된 실행기를 부른 횟수와, live에서만 세는 외부 호출 횟수를 구분한다.
    provider_calls: int
    coverage: tuple[CoverageEntry, ...]
    diagnostics: tuple[str, ...]

    @property
    def external_calls(self) -> int:
        return self.provider_calls if self.mode is RunMode.LIVE else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "module_execution_id": str(self.module_execution_id),
            "result_id": str(self.result_id),
            "fixtures": [candidate.to_dict() for candidate in self.candidates],
            "mode": self.mode.value,
            "status": self.status.value,
            "provider_calls": self.provider_calls,
            "external_calls": self.external_calls,
            "coverage": [entry.to_dict() for entry in self.coverage],
            "diagnostics": list(self.diagnostics),
        }


def _catalog_season(now: datetime, *, season: int | None) -> int:
    if season is not None:
        return season
    # 유럽 리그 기준 7월 시작. 확인되지 않은 값을 단정하지 않으려고 호출자가 넘기는
    # 값을 우선하고, 없을 때만 이 규칙을 쓴다.
    return now.year if now.month >= 7 else now.year - 1


def import_fixtures(
    session: Session,
    query: FixtureCatalogQuery,
    *,
    context: ExecutionContext,
    executor: api.ApiExecutor,
    season: int | None = None,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> ImportedFixtures:
    """관리자가 명시한 조건으로 경기 후보를 수집해 저장한다.

    `operation_kind=fixture_catalog`만 허용한다. 전체 프리뷰 실행과 섞지 않기 위함이다.
    실행기 호출은 정확히 1회이며, 실패해도 재시도하지 않는다.
    """
    if context.operation_kind is not OperationKind.FIXTURE_CATALOG:
        raise ContractError(
            "import_fixtures requires operation_kind=fixture_catalog; "
            "it must not be mixed with a preview run"
        )
    moment = now or _now()
    actor = actor_id if actor_id is not None else context.actor_id
    resolved_season = _catalog_season(moment, season=season)

    run = store.store_run(
        session,
        context,
        fixture=None,
        fixture_label=f"경기 목록 수집 l={query.league_id} d={query.date} tz={query.timezone}",
        label="경기 목록 수집 (fixture_catalog)",
        status=RunStatus.RUNNING,
    )

    call = api.catalog_call(
        league_id=query.league_id,
        date=query.date,
        timezone_name=query.timezone,
        season=resolved_season,
    )
    spec = api.request_spec(call, module_id=CATALOG_MODULE_ID)
    request_artifact = artifact_store.save_artifact(
        session,
        run_id=run.id,
        kind=artifact_store.ArtifactKind.RAW_REQUEST,
        content=spec.to_dict(),
        actor_id=actor,
        now=moment,
    )
    exchange = executor(spec)
    response = exchange.response
    body = exchange.body
    response_artifact = None
    if body is not None:
        response_artifact = artifact_store.save_artifact(
            session,
            run_id=run.id,
            kind=artifact_store.ArtifactKind.RAW_RESPONSE,
            content=body,
            actor_id=actor,
            now=moment,
        )
    attempt = store.append_attempt(
        session,
        run_id=run.id,
        logical_call_id=call.call_id,
        attempt_ordinal=0,
        provider=spec.provider,
        model=None,
        mode=context.mode,
        operation=call.endpoint,
        outcome=response.outcome.value,
        request_spec=spec.to_dict(),
        http_status=response.http_status,
        error_class=response.error_class,
        error_message=response.error_message,
        request_artifact_id=request_artifact.id,
        response_artifact_id=response_artifact.id if response_artifact else None,
        usage=response.usage.to_dict() if response.usage else None,
        wait_ms=0,
        started_at=moment,
        finished_at=response.received_at or moment,
        actor_id=actor,
    )
    snapshot_row = store.record_source_snapshot(
        session,
        run_id=run.id,
        source_kind=SourceKind.API,
        provider=api.API_PROVIDER,
        collected_at=response.received_at or moment,
        validation_status=(
            ValidationStatus.VERIFIED if exchange.ok else ValidationStatus.UNVERIFIED
        ),
        catalog_query=query.to_dict(),
        attempt_id=attempt.id,
        artifact_id=response_artifact.id if response_artifact else None,
        note=(
            f"경기 목록 수집(실행 방식 {context.mode.value}). "
            "이 자료는 선택 경기의 D0 근거와 구분해 기록합니다."
        ),
        actor_id=actor,
    )

    module_input = ModuleInput(
        module_id=CATALOG_MODULE_ID,
        fixture=None,
        snapshot_ids=(snapshot_row.id,),
        selected_result_ids=(),
        input_hash=compute_input_hash(
            {"catalog_query": query.to_dict(), "season": resolved_season}
        ),
        prompt_version="",
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=D0_IMPLEMENTATION_VERSION,
        parameters={"catalog_query": query.to_dict(), "season": resolved_season},
    )
    execution = store.start_module_execution(
        session,
        run_id=run.id,
        module_id=CATALOG_MODULE_ID,
        module_input=module_input,
        actor_id=actor,
    )

    candidates: tuple[FixtureCandidate, ...] = ()
    coverage: tuple[CoverageEntry, ...]
    diagnostics: list[str] = []
    status = ModuleStatus.SUCCEEDED
    failure_code = None

    if not exchange.ok:
        # 제공자 오류를 '자료 없음'으로 바꾸지 않는다.
        diagnostics.append(
            "경기 목록 수집 호출이 실패했습니다. 빈 목록은 '해당 날짜 경기 없음'의 증거가 아닙니다."
        )
        coverage = (
            CoverageEntry(
                topic="fixture_catalog",
                state=CoverageState.CALL_ERROR,
                detail=response.error_message or response.error_class or "요청 실패",
            ),
        )
        status = ModuleStatus.FAILED
        failure_code = FailureCode.PROVIDER_ERROR
    else:
        try:
            envelope = api.parse_envelope(body)
            envelope.require_ok()
            records = [api.parse_fixture_record(raw) for raw in envelope.records]
        except api.ApiFootballError as exc:
            diagnostics.append(f"경기 목록 응답을 해석하지 못했습니다: {exc}")
            coverage = (
                CoverageEntry(
                    topic="fixture_catalog",
                    state=CoverageState.CALL_ERROR,
                    detail=str(exc),
                ),
            )
            status = ModuleStatus.FAILED
            failure_code = FailureCode.INVALID_OUTPUT
        else:
            candidates = tuple(
                FixtureCandidate(
                    fixture_id=record.fixture_id,
                    league_id=record.league_id,
                    league_name=record.league_name,
                    season=record.season,
                    home_team_id=record.home_team_id,
                    away_team_id=record.away_team_id,
                    home_team_name=record.home_team_name,
                    away_team_name=record.away_team_name,
                    kickoff_at=record.kickoff_at,
                    status_short=record.status_short,
                    origin="catalog_import",
                    origin_note=(
                        f"방금 저장한 목록 수집 결과입니다(실행 방식: {context.mode.value})."
                    ),
                    run_id=run.id,
                    mode=context.mode,
                )
                for record in records[:MAX_CATALOG_CANDIDATES]
            )
            if candidates:
                coverage = (
                    CoverageEntry(
                        topic="fixture_catalog",
                        state=CoverageState.AVAILABLE,
                        detail=f"{len(candidates)}건",
                    ),
                )
            else:
                # 호출은 성공했고 results=0이다. '경기 없음'과 '수집 실패'를 구분한다.
                coverage = (
                    CoverageEntry(
                        topic="fixture_catalog",
                        state=CoverageState.API_NOT_PROVIDED,
                        detail="제공자가 해당 조건의 경기를 반환하지 않았습니다.",
                    ),
                )
                diagnostics.append(
                    "수집은 성공했지만 후보가 0건입니다. 이는 수집 실패와 다른 상태입니다."
                )

    payload = {
        "catalog_query": query.to_dict(),
        "season": resolved_season,
        "snapshot_id": str(snapshot_row.id),
        "response_artifact_id": str(response_artifact.id) if response_artifact else None,
        "mode": context.mode.value,
        "provider": api.API_PROVIDER,
        "collected_at": (response.received_at or moment).isoformat(),
        "candidates": [candidate.to_dict() for candidate in candidates],
    }
    d0_result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=CATALOG_MODULE_ID,
        module_execution_id=execution.id,
        run_id=run.id,
        version=1,
        input_hash=module_input.input_hash,
        status=status,
        quality=QualityStatus.PENDING,
        claims=(),
        coverage=coverage,
        diagnostics=tuple(diagnostics),
        failure_code=failure_code,
        implementation_version=D0_IMPLEMENTATION_VERSION,
        prompt_version="",
        contract_version=CONTRACT_VERSION,
        payload=payload,
    )
    saved = store.save_module_result(session, d0_result, actor_id=actor)
    store.update_module_delivery(
        session,
        execution.id,
        {
            "target_module_id": None,
            "values": [
                {"key": "candidate_count", "value": len(candidates)},
                {"key": "catalog_query", "value": query.to_dict()},
            ],
            "note": (
                "목록 수집은 경기 선택 화면의 입력입니다. 선택한 경기의 D0 근거와"
                " 같은 자료로 취급하지 않습니다."
            ),
        },
        status=status,
        quality=QualityStatus.PENDING,
        failure_code=failure_code,
    )
    store.finish_run(
        session,
        run.id,
        status=RunStatus.SUCCEEDED if status is ModuleStatus.SUCCEEDED else RunStatus.FAILED,
        quality=QualityStatus.PENDING,
        failure_code=failure_code,
        actor_id=actor,
    )

    return ImportedFixtures(
        run_id=run.id,
        module_execution_id=execution.id,
        result_id=saved.id,
        candidates=candidates,
        mode=context.mode,
        status=status,
        provider_calls=1,
        coverage=coverage,
        diagnostics=tuple(diagnostics),
    )


# --------------------------------------------------------------------------
# 저장된 목록 조회 (외부 호출 없음)
# --------------------------------------------------------------------------


def _latest_catalog_results(session: Session, *, limit: int) -> list[PreviewResult]:
    """저장된 목록 수집 결과 중 실행별 최신 버전만 읽는다."""
    rows = session.scalars(
        select(PreviewResult)
        .where(PreviewResult.module_id == CATALOG_MODULE_ID)
        .order_by(PreviewResult.created_at.desc())
        .limit(limit * 4)
    ).all()
    latest: dict[uuid.UUID, PreviewResult] = {}
    for row in rows:
        current = latest.get(row.module_execution_id)
        if current is None or row.version > current.version:
            latest[row.module_execution_id] = row
    return sorted(
        latest.values(), key=lambda row: row.created_at or _now(), reverse=True
    )[:limit]


def _result_payload(row: PreviewResult) -> Mapping[str, Any]:
    """저장된 결과 행에서 모듈이 만든 payload를 꺼낸다.

    `store.save_module_result`는 `ModuleResult.to_dict()`를 그대로 담으므로 실제
    payload는 한 단계 아래에 있다. 두 모양을 모두 받아 화면 조회가 조용히 빈 목록을
    돌려주지 않게 한다.
    """
    outer = row.payload or {}
    inner = outer.get("payload")
    if isinstance(inner, Mapping):
        return inner
    return outer


def store_candidates(
    session: Session, *, query: FixtureCatalogQuery | None = None, limit: int = 50
) -> tuple[FixtureCandidate, ...]:
    """저장된 목록 수집 결과에서 후보를 읽는다. 외부 호출이 없다."""
    candidates: list[FixtureCandidate] = []
    for row in _latest_catalog_results(session, limit=limit):
        payload = _result_payload(row)
        run = session.get(PreviewRun, row.run_id)
        mode = RunMode(payload.get("mode", run.mode if run else RunMode.MOCK.value))
        if query is not None:
            stored_query = payload.get("catalog_query") or {}
            if stored_query and stored_query.get("league_id") != query.league_id:
                continue
            if stored_query and stored_query.get("date") != query.date:
                continue
        collected_at = payload.get("collected_at")
        moment = (
            datetime.fromisoformat(str(collected_at)) if collected_at else (_now())
        )
        for raw in payload.get("candidates") or ():
            if not isinstance(raw, Mapping):
                continue
            candidates.append(
                _candidate_from_payload(
                    raw, run_id=row.run_id, mode=mode, collected_at=moment
                )
            )
    return tuple(candidates)


def list_fixtures(
    session: Session,
    *,
    query: FixtureCatalogQuery | None = None,
    reader: StoredFixtureReader | None = None,
    limit: int = 50,
    now: datetime | None = None,
) -> FixtureListResult:
    """저장된 경기 후보를 읽는다. 수집을 일으키지 않는다.

    두 저장 출처를 함께 본다.

    1. 기존 DB의 경기 자료(읽기 전용). 권한이 없으면 그 사실과 필요한 SELECT 경계를
       응답에 남긴다. 조용히 빈 목록으로 만들지 않는다.
    2. `preview_dev`에 저장된 목록 수집 결과(실행 방식 라벨 유지).

    같은 외부 경기 ID가 양쪽에 있으면 기존 DB 행을 우선한다.
    """
    moment = now or _now()
    sources: list[Mapping[str, Any]] = []
    stored_candidates: tuple[FixtureCandidate, ...] = ()
    access_payload: Mapping[str, Any] = {
        "readable": False,
        "detail": "저장된 경기 자료 조회기가 연결되지 않았습니다.",
        "tables": {},
        "missing": [],
        "required": [],
    }

    if reader is not None:
        try:
            access = reader.access()
        except Exception as exc:  # pragma: no cover - 연결 실패 방어
            access = FixtureReadAccess(
                readable=False,
                tables={},
                detail=f"{type(exc).__name__}: 읽기 연결을 확인하지 못했습니다.",
            )
        access_payload = access.to_dict()
        if access.readable:
            try:
                rows = reader.list_fixtures(
                    league_id=query.league_id if query else None,
                    date=query.date if query else None,
                    limit=limit,
                    upcoming_only=True,
                    now=moment,
                )
            except FixtureReadDenied as exc:  # pragma: no cover - 방어적 경로
                access_payload = {
                    **access_payload,
                    "readable": False,
                    "detail": str(exc),
                }
            else:
                stored_candidates = tuple(_candidate_from_stored(row) for row in rows)
                sources.append(
                    {
                        "origin": "stored_db",
                        "label": "기존 DB 저장 경기 (읽기 전용)",
                        "count": len(stored_candidates),
                        "external_calls": 0,
                    }
                )

    imported = store_candidates(session, query=query, limit=limit)
    if imported:
        sources.append(
            {
                "origin": "catalog_import",
                "label": "저장된 목록 수집 기록",
                "count": len(imported),
                "external_calls": 0,
            }
        )

    merged: dict[int, FixtureCandidate] = {c.fixture_id: c for c in imported}
    for candidate in stored_candidates:
        # 기존 DB 행이 있으면 그쪽이 기준이다(최신 저장 자료).
        merged[candidate.fixture_id] = candidate
    ordered = sorted(merged.values(), key=lambda c: (c.kickoff_at, c.fixture_id))[:limit]

    notes: list[str] = [
        "이 목록은 저장된 자료만 읽습니다. 화면을 열어도 새 외부 수집이 일어나지 않습니다."
    ]
    if reader is not None and not access_payload.get("readable", False):
        notes.append(
            "기존 DB 경기 자료 읽기 권한이 없어 목록 수집 기록만 표시합니다. "
            "필요한 경계: SELECT ON public.fixture, public.team, public.league "
            "(및 부상·순위 조회 시 public.injury, public.standings)."
        )

    return FixtureListResult(
        candidates=tuple(ordered),
        sources=tuple(sources),
        stored_access=access_payload,
        note=" ".join(notes),
    )


# --------------------------------------------------------------------------
# D0 자료 준비
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class D0Result:
    """D0 실행 결과. 결과 버전과 자료 스냅샷을 함께 돌려준다."""

    result: ModuleResult
    snapshots: tuple[SourceSnapshot, ...]
    coverage: tuple[CoverageEntry, ...]
    claims: tuple[EvidenceClaim, ...]
    diagnostics: tuple[str, ...]
    fixture: FixtureIdentity
    mode: RunMode
    # 주입된 실행기를 부른 횟수. 실행기가 실제로 외부에 요청했는지는 실행기가 안다.
    provider_calls: int

    @property
    def external_calls(self) -> int:
        """외부 호출 횟수. live만 센다. mock·replay를 live 성공으로 세지 않는다."""
        return self.provider_calls if self.mode is RunMode.LIVE else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "result": self.result.to_dict(),
            "snapshots": [snapshot.to_dict() for snapshot in self.snapshots],
            "coverage": [entry.to_dict() for entry in self.coverage],
            "claims": [claim.to_dict() for claim in self.claims],
            "diagnostics": list(self.diagnostics),
            "fixture": self.fixture.to_dict(),
            "mode": self.mode.value,
            "provider_calls": self.provider_calls,
            "external_calls": self.external_calls,
            "external_calls_note": (
                "external_calls는 live 실행에서만 셉니다. mock·replay는 실행기를 불러도"
                " 외부 호출로 세지 않습니다."
            ),
        }


_TOPIC_LABELS = {
    "fixture_identity": "경기 식별",
    "recent_form": "최근 성적",
    "standings": "리그 순위",
    "player_stats": "선수 기록",
    "injuries": "부상·출전 불확실",
    "odds": "경기 전 승무패 배당",
    "predictions": "제공자 알고리즘 예측",
}


def _coverage_for(topic: str, state: CoverageState, detail: str | None = None):
    return CoverageEntry(topic=_TOPIC_LABELS.get(topic, topic), state=state, detail=detail)


def _snapshot_of(row, fixture: FixtureIdentity) -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id=row.id,
        source_kind=SourceKind.API,
        provider=row.provider,
        collected_at=row.collected_at,
        provider_updated_at=row.provider_updated_at,
        fixture=fixture,
        catalog_query=None,
        artifact_id=row.artifact_id,
        validation_status=ValidationStatus(row.validation_status),
        note=row.note,
    )


def _claim(
    claim_id: str,
    kind: ClaimKind,
    text: str,
    snapshot_id: uuid.UUID,
    *,
    subject_team_id: int | None = None,
    subject_player_id: int | None = None,
    decision: ClaimDecision = ClaimDecision.ADOPTED,
    reason: str | None = None,
) -> EvidenceClaim:
    return EvidenceClaim(
        claim_id=claim_id,
        kind=kind,
        text=text,
        snapshot_ids=(snapshot_id,),
        decision=decision,
        decision_reason=reason,
        subject_team_id=subject_team_id,
        subject_player_id=subject_player_id,
    )


def prepare_match_data(
    session: Session,
    fixture: FixtureIdentity,
    context: ExecutionContext,
    *,
    executor: api.ApiExecutor,
    actor_id: int | None = None,
    now: datetime | None = None,
) -> D0Result:
    """D0를 한 번 실행하고 결과 버전·스냅샷을 남긴다.

    호출 하나당 실행기 호출 한 번이다. 실패한 호출은 그대로 실패로 남고, 재시도는
    공통 실행기(MP-04)의 몫이다. 제공자 오류는 `CALL_ERROR`이며 '자료 없음'이 아니다.
    """
    if context.operation_kind not in (OperationKind.MODULE, OperationKind.PREVIEW):
        raise ContractError(
            "prepare_match_data runs inside a preview or module execution, "
            f"not {context.operation_kind.value}"
        )
    run = session.get(PreviewRun, context.run_id)
    if run is None:
        raise ContractError(f"run {context.run_id} must exist before D0 runs")

    moment = now or _now()
    actor = actor_id if actor_id is not None else context.actor_id

    calls = api.d0_calls(
        fixture.fixture_id,
        league_id=fixture.league_id,
        season=fixture.season,
        home_team_id=fixture.home_team_id,
        away_team_id=fixture.away_team_id,
    )
    snapshots: list[SourceSnapshot] = []
    coverage: list[CoverageEntry] = []
    claims: list[EvidenceClaim] = []
    diagnostics: list[str] = []
    snapshot_ids: list[uuid.UUID] = []
    payload_topics: dict[str, Any] = {}
    provider_calls = 0
    provider_failures = 0

    module_input = ModuleInput(
        module_id=D0_MODULE_ID,
        fixture=fixture,
        snapshot_ids=(),
        selected_result_ids=(),
        input_hash=compute_input_hash(
            {"fixture": fixture.to_dict(), "implementation": D0_IMPLEMENTATION_VERSION}
        ),
        prompt_version="",
        contract_version=MODULE_INPUT_VERSION,
        implementation_version=D0_IMPLEMENTATION_VERSION,
        parameters={"call_ids": [call.call_id for call in calls]},
    )
    execution_id = context.module_execution_id
    execution_ordinal = 0
    if execution_id is None:
        # 같은 실행에서 D0를 다시 돌리면 새 모듈 실행(다음 ordinal)을 만든다. 이전 모듈
        # 실행의 결과·시도는 그대로 남는다. 재실행을 재시도(attempt_ordinal>0)로
        # 적으면 실제 재시도 통계가 오염된다.
        next_ordinal = int(
            session.scalar(
                select(func.count())
                .select_from(PreviewModuleExecution)
                .where(
                    PreviewModuleExecution.run_id == run.id,
                    PreviewModuleExecution.module_id == D0_MODULE_ID,
                )
            )
            or 0
        )
        execution = store.start_module_execution(
            session,
            run_id=run.id,
            module_id=D0_MODULE_ID,
            module_input=module_input,
            ordinal=next_ordinal,
            actor_id=actor,
        )
        execution_id = execution.id
        execution_ordinal = next_ordinal

    snapshots_by_call: dict[str, SourceSnapshot] = {}

    def _record_call(call):
        """논리 호출 하나를 실행하고 시도·원문·스냅샷을 남긴다.

        D0 재실행은 **새 모듈 실행**이다. 시도 순번은 항상 0으로 두고, 실행 순번이
        0이 아닐 때만 논리 호출 ID에 그 순번을 붙인다. 이렇게 하면 (run, 호출, 순번)
        유일 제약을 재시도로 위장하지 않고 지킬 수 있고, 재시도 집계도 오염되지
        않는다. 실제 재시도는 공통 실행기(MP-04)가 같은 논리 호출에 순번을 올려 남긴다.
        """
        nonlocal provider_calls, provider_failures
        logical_call_id = (
            call.call_id
            if execution_ordinal == 0
            else f"{call.call_id}#re{execution_ordinal}"
        )
        spec = api.request_spec(call, module_id=D0_MODULE_ID)
        request_artifact = artifact_store.save_artifact(
            session,
            run_id=run.id,
            kind=artifact_store.ArtifactKind.RAW_REQUEST,
            content=spec.to_dict(),
            actor_id=actor,
            now=moment,
        )
        exchange = executor(spec)
        provider_calls += 1
        response = exchange.response
        response_artifact = None
        if exchange.body is not None:
            response_artifact = artifact_store.save_artifact(
                session,
                run_id=run.id,
                kind=artifact_store.ArtifactKind.RAW_RESPONSE,
                content=exchange.body,
                actor_id=actor,
                now=moment,
            )
        attempt = store.append_attempt(
            session,
            run_id=run.id,
            module_execution_id=execution_id,
            module_id=D0_MODULE_ID,
            logical_call_id=logical_call_id,
            attempt_ordinal=0,
            provider=spec.provider,
            model=None,
            mode=context.mode,
            operation=call.endpoint,
            outcome=response.outcome.value,
            request_spec=spec.to_dict(),
            http_status=response.http_status,
            error_class=response.error_class,
            error_message=response.error_message,
            request_artifact_id=request_artifact.id,
            response_artifact_id=response_artifact.id if response_artifact else None,
            usage=response.usage.to_dict() if response.usage else None,
            wait_ms=0,
            started_at=moment,
            finished_at=response.received_at or moment,
            actor_id=actor,
        )
        collected_at = response.received_at or moment
        ok = exchange.ok and response.outcome is AttemptOutcome.OK
        if not ok:
            provider_failures += 1
        snapshot_row = store.record_source_snapshot(
            session,
            run_id=run.id,
            source_kind=SourceKind.API,
            provider=api.API_PROVIDER,
            collected_at=collected_at,
            validation_status=(
                ValidationStatus.VERIFIED if ok else ValidationStatus.UNVERIFIED
            ),
            fixture=fixture,
            attempt_id=attempt.id,
            artifact_id=response_artifact.id if response_artifact else None,
            note=f"{call.call_id}: {call.description} (실행 방식 {context.mode.value})",
            actor_id=actor,
        )
        snapshot = _snapshot_of(snapshot_row, fixture)
        snapshots.append(snapshot)
        snapshots_by_call[call.call_id] = snapshot
        snapshot_ids.append(snapshot.snapshot_id)
        payload_topics[call.topic] = {
            "call_id": call.call_id,
            "endpoint": call.endpoint,
            "provider": api.API_PROVIDER,
            "snapshot_id": str(snapshot.snapshot_id),
            "artifact_id": str(response_artifact.id) if response_artifact else None,
            "collected_at": collected_at.isoformat(),
            "provider_updated_at": (
                snapshot.provider_updated_at.isoformat()
                if snapshot.provider_updated_at
                else None
            ),
            "validation_status": snapshot.validation_status.value,
            "mode": context.mode.value,
            "http_status": response.http_status,
        }
        return exchange, snapshot, ok

    # 1) 경기 확인이 먼저다. 다른 경기가 오면 나머지 호출을 하지 않는다.
    identity_exchange, identity_snapshot, identity_ok = _record_call(calls[0])
    identity_error: str | None = None
    if identity_ok:
        try:
            envelope = api.parse_envelope(identity_exchange.body)
            envelope.require_ok()
            if not envelope.records:
                raise api.ApiFootballError("경기 응답이 비어 있습니다.")
            record = api.verify_fixture(
                api.parse_fixture_record(envelope.records[0]),
                fixture_id=fixture.fixture_id,
                home_team_id=fixture.home_team_id,
                away_team_id=fixture.away_team_id,
            )
        except api.WrongFixture as exc:
            identity_error = str(exc)
            coverage.append(
                _coverage_for("fixture_identity", CoverageState.VALIDATION_REJECTED, str(exc))
            )
            diagnostics.append(
                "요청한 경기와 응답의 경기가 달라 D0 자료를 만들지 않았습니다. "
                "다른 경기 자료를 이 경기 근거로 쓰지 않습니다."
            )
        except api.ApiFootballError as exc:
            identity_error = str(exc)
            coverage.append(
                _coverage_for("fixture_identity", CoverageState.CALL_ERROR, str(exc))
            )
        else:
            coverage.append(
                _coverage_for(
                    "fixture_identity",
                    CoverageState.AVAILABLE,
                    f"경기 {record.fixture_id}, 킥오프 {record.kickoff_at.isoformat()}",
                )
            )
            claims.append(
                _claim(
                    "d0-fixture-identity",
                    ClaimKind.FACT,
                    f"{record.home_team_name or fixture.home_team_id} 대 "
                    f"{record.away_team_name or fixture.away_team_id}, "
                    f"킥오프 {record.kickoff_at.isoformat()}, 대회 {fixture.league_id} "
                    f"시즌 {fixture.season}.",
                    identity_snapshot.snapshot_id,
                )
            )
    else:
        coverage.append(
            _coverage_for(
                "fixture_identity",
                CoverageState.CALL_ERROR,
                identity_exchange.response.error_message or "경기 확인 호출 실패",
            )
        )

    if identity_error is not None or not identity_ok:
        # 경기가 확인되지 않으면 나머지 자료를 이 경기로 채우지 않는다.
        result = _save_d0_result(
            session,
            execution_id=execution_id,
            run_id=run.id,
            fixture=fixture,
            module_input=module_input,
            status=ModuleStatus.FAILED,
            quality=QualityStatus.INSUFFICIENT,
            claims=(),
            coverage=tuple(coverage),
            diagnostics=tuple(
                diagnostics
                + ["경기 확인이 실패해 나머지 D0 자료 수집을 중단했습니다."]
            ),
            failure_code=FailureCode.PROVIDER_ERROR,
            payload={"topics": payload_topics, "mode": context.mode.value},
            actor=actor,
        )
        return D0Result(
            result=result,
            snapshots=tuple(snapshots),
            coverage=tuple(coverage),
            claims=(),
            diagnostics=tuple(diagnostics),
            fixture=fixture,
            mode=context.mode,
            provider_calls=provider_calls,
        )

    # 2) 나머지 자료. 한 호출의 실패가 다른 자료를 지우지 않는다.
    odds_adopted = 0
    injury_records: tuple[api.InjuryRecord, ...] = ()
    injuries_ok = False
    for call in calls[1:]:
        exchange, snapshot, ok = _record_call(call)
        if not ok:
            coverage.append(
                _coverage_for(
                    call.topic,
                    CoverageState.CALL_ERROR,
                    exchange.response.error_message
                    or exchange.response.error_class
                    or "호출 실패",
                )
            )
            continue
        try:
            envelope = api.parse_envelope(exchange.body)
            envelope.require_ok()
        except api.ApiFootballError as exc:
            coverage.append(
                _coverage_for(call.topic, CoverageState.CALL_ERROR, str(exc))
            )
            continue

        try:
            if call.topic == "recent_form":
                form = api.parse_team_statistics(envelope.records[0]) if envelope.records else None
                if form is None:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.API_NOT_PROVIDED,
                            f"{call.call_id}: 제공자가 팀 기록을 반환하지 않았습니다.",
                        )
                    )
                    continue
                coverage.append(
                    _coverage_for(
                        call.topic,
                        CoverageState.AVAILABLE,
                        f"팀 {form.team_id} 폼 {form.form or '미제공'}",
                    )
                )
                if form.form:
                    claims.append(
                        _claim(
                            f"d0-form-{form.team_id}",
                            ClaimKind.FACT,
                            f"팀 {form.team_id} 최근 폼 {form.form}, "
                            f"{form.played if form.played is not None else '미상'}경기 "
                            f"{form.wins if form.wins is not None else '?'}승 "
                            f"{form.draws if form.draws is not None else '?'}무 "
                            f"{form.losses if form.losses is not None else '?'}패.",
                            snapshot.snapshot_id,
                            subject_team_id=form.team_id,
                        )
                    )
            elif call.topic == "standings":
                if not envelope.records:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.API_NOT_PROVIDED,
                            "제공자가 순위 자료를 반환하지 않았습니다.",
                        )
                    )
                else:
                    coverage.append(
                        _coverage_for(
                            call.topic, CoverageState.AVAILABLE, f"{len(envelope.records)}건"
                        )
                    )
            elif call.topic == "player_stats":
                players = api.parse_player_statistics(envelope)
                if not players:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.API_NOT_PROVIDED,
                            f"{call.call_id}: 선수 기록이 없습니다.",
                        )
                    )
                else:
                    coverage.append(
                        _coverage_for(
                            call.topic, CoverageState.AVAILABLE, f"{len(players)}명"
                        )
                    )
            elif call.topic == "injuries":
                injury_records = api.parse_injuries(
                    envelope, fixture_id=fixture.fixture_id
                )
                injuries_ok = True
                if not injury_records:
                    # 빈 응답은 '부상자 0명'이 아니다.
                    coverage.append(
                        _coverage_for(
                            call.topic, CoverageState.UNKNOWN, api.EMPTY_INJURIES_MEANING
                        )
                    )
                    diagnostics.append(api.EMPTY_INJURIES_MEANING)
                else:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.AVAILABLE,
                            f"{len(injury_records)}건(불확실 포함)",
                        )
                    )
            elif call.topic == "odds":
                odds = api.parse_odds(envelope, fixture_id=fixture.fixture_id)
                collected_at = snapshot.collected_at
                fresh = [
                    record
                    for record in odds
                    if api.odds_freshness(record, collected_at)[0]
                ]
                for record in odds:
                    accepted, reason = api.odds_freshness(record, collected_at)
                    if accepted and record.home and record.away:
                        odds_adopted += 1
                        claims.append(
                            _claim(
                                f"d0-odds-{record.bookmaker_id or 'x'}-"
                                f"{record.market_id or 'x'}",
                                ClaimKind.EXTERNAL_FORECAST,
                                f"{record.bookmaker or '업체 미상'} 경기 전 승무패 "
                                f"홈 {record.home} / 무 {record.draw or '미제공'} / "
                                f"원정 {record.away}.",
                                snapshot.snapshot_id,
                                reason="경기 전 승무패 시장, 갱신 시각 확인, 수집 6시간 이내.",
                            )
                        )
                if not odds:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.API_NOT_PROVIDED,
                            "제공자가 배당 자료를 반환하지 않았습니다.",
                        )
                    )
                elif not fresh:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.VALIDATION_REJECTED,
                            "갱신 시각이 없거나 오래된 배당만 있어 채택하지 않았습니다.",
                        )
                    )
                else:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.AVAILABLE,
                            f"채택 {odds_adopted}건 / 수신 {len(odds)}건",
                        )
                    )
            elif call.topic == "predictions":
                prediction = api.parse_prediction(
                    envelope, fixture_id=fixture.fixture_id
                )
                if prediction is None:
                    coverage.append(
                        _coverage_for(
                            call.topic,
                            CoverageState.API_NOT_PROVIDED,
                            "제공자가 예측 자료를 반환하지 않았습니다.",
                        )
                    )
                else:
                    coverage.append(
                        _coverage_for(call.topic, CoverageState.AVAILABLE, "1건")
                    )
                    if prediction.advice or prediction.winner_name:
                        claims.append(
                            _claim(
                                "d0-prediction",
                                ClaimKind.API_PREDICTION,
                                "제공자 알고리즘 예측: "
                                + (prediction.advice or prediction.winner_name or "")
                                + (
                                    f" (홈 {prediction.percent_home} / "
                                    f"무 {prediction.percent_draw} / "
                                    f"원정 {prediction.percent_away})"
                                    if prediction.percent_home
                                    else ""
                                ),
                                snapshot.snapshot_id,
                                reason="제공자 알고리즘 예측이며 매체 의견이나 이 서비스의 결론이 아닙니다.",
                            )
                        )
        except api.WrongFixture as exc:
            coverage.append(
                _coverage_for(call.topic, CoverageState.VALIDATION_REJECTED, str(exc))
            )
            diagnostics.append(
                f"{call.call_id}: 응답의 경기가 달라 이 자료를 채택하지 않았습니다."
            )
        except api.ApiFootballError as exc:
            coverage.append(_coverage_for(call.topic, CoverageState.CALL_ERROR, str(exc)))

    # 부상 불확실성은 원문을 유지한 채 근거로 남긴다. 확정으로 승격하지 않는다.
    injury_snapshot = snapshots_by_call.get("D0-injuries")
    injury_snapshot_id = injury_snapshot.snapshot_id if injury_snapshot else None
    if injuries_ok and injury_snapshot_id is not None:
        for record in injury_records:
            uncertainty = record.uncertainty
            claims.append(
                EvidenceClaim(
                    claim_id=f"d0-injury-{record.player_id}",
                    kind=ClaimKind.FACT,
                    text=(
                        f"선수 {record.player_name or record.player_id} 상태: "
                        f"{record.type_marker or '표기 없음'}"
                        + (f", 사유 {record.reason}" if record.reason else "")
                    ),
                    snapshot_ids=(injury_snapshot_id,),
                    decision=(
                        ClaimDecision.ADOPTED
                        if uncertainty != "unknown"
                        else ClaimDecision.EXCLUDED
                    ),
                    decision_reason=(
                        "출전 불확실 표기를 그대로 보존했습니다. 결장 확정이 아닙니다."
                        if uncertainty == "uncertain"
                        else "표기가 없어 확정 사실로 채택하지 않았습니다."
                    ),
                    subject_team_id=record.team_id,
                    subject_player_id=record.player_id,
                )
            )

    if provider_failures and provider_failures == len(snapshots):
        status = ModuleStatus.FAILED
        failure_code = FailureCode.PROVIDER_ERROR
    elif claims:
        status = ModuleStatus.SUCCEEDED
        failure_code = None
    else:
        status = ModuleStatus.SUCCEEDED
        failure_code = None
        diagnostics.append(
            "실행은 끝났지만 채택할 근거가 없습니다. 실행 성공과 근거 확보는 별개입니다."
        )

    quality = QualityStatus.PENDING
    result = _save_d0_result(
        session,
        execution_id=execution_id,
        run_id=run.id,
        fixture=fixture,
        module_input=module_input,
        status=status,
        quality=quality,
        claims=tuple(claims),
        coverage=tuple(coverage),
        diagnostics=tuple(diagnostics),
        failure_code=failure_code,
        payload={
            "topics": payload_topics,
            "mode": context.mode.value,
            "fixture": fixture.to_dict(),
            "implementation_version": D0_IMPLEMENTATION_VERSION,
        },
        actor=actor,
    )

    store.update_module_delivery(
        session,
        execution_id,
        {
            "target_module_id": None,
            "values": [
                {"key": "snapshot_ids", "value": [str(sid) for sid in snapshot_ids]},
                {"key": "adopted_claim_ids", "value": [c.claim_id for c in claims]},
                {"key": "coverage", "value": [e.to_dict() for e in coverage]},
            ],
            "note": (
                "D0 자료 묶음입니다. 후속 조사 모듈이 같은 스냅샷을 입력으로 받습니다."
            ),
        },
        status=status,
        quality=quality,
        failure_code=failure_code,
    )

    return D0Result(
        result=result,
        snapshots=tuple(snapshots),
        coverage=tuple(coverage),
        claims=tuple(claims),
        diagnostics=tuple(diagnostics),
        fixture=fixture,
        mode=context.mode,
        provider_calls=provider_calls,
    )


def _save_d0_result(
    session: Session,
    *,
    execution_id: uuid.UUID,
    run_id: uuid.UUID,
    fixture: FixtureIdentity,
    module_input: ModuleInput,
    status: ModuleStatus,
    quality: QualityStatus,
    claims: tuple[EvidenceClaim, ...],
    coverage: tuple[CoverageEntry, ...],
    diagnostics: tuple[str, ...],
    failure_code,
    payload: Mapping[str, Any],
    actor: int,
) -> ModuleResult:
    previous = session.scalars(
        select(PreviewResult)
        .where(PreviewResult.module_execution_id == execution_id)
        .order_by(PreviewResult.version.desc())
        .limit(1)
    ).first()
    version = (previous.version + 1) if previous is not None else 1
    result = ModuleResult(
        result_id=uuid.uuid4(),
        module_id=D0_MODULE_ID,
        module_execution_id=execution_id,
        run_id=run_id,
        version=version,
        input_hash=module_input.input_hash,
        status=status,
        quality=quality,
        claims=claims,
        coverage=coverage,
        diagnostics=diagnostics,
        failure_code=failure_code,
        implementation_version=D0_IMPLEMENTATION_VERSION,
        prompt_version="",
        contract_version=CONTRACT_VERSION,
        payload=payload,
    )
    store.save_module_result(session, result, actor_id=actor)
    return result
