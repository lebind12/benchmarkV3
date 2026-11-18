"""새 기본 경로: 정보 원문 묶음 → 섹션 5개 → 저장.

흐름(설계 §목적과 실행 순서):

    D0(저장 DB 읽기, 모델 0회)
      → 조사 A/B(모델 2회, 서로 독립)
      → 공통 수집(브라우저 없는 HTTP, 모델 0회, HTTP 예산 24 공유)
      → 정보 원문 묶음 저장(전문 아티팩트 + 구간)
      → 작성 3회(선수·부상·매체) + 배당(모델 0회)
      → 최종 AI 전망·스코어 1회
      → 섹션 결과 저장(버전)

예산은 **하나의 `RunBudget`** 으로 센다. 정상 6회, 전체 실제 전송 8회, 모델 동시 2회,
비모델 HTTP 24회를 수집이 함께 쓴다. 이 모듈은 새 실행기를 만들지 않고 기존
`discovery`·`retrieval`·`bundle_sections`·`provider`·`store`를 순서대로 부른다.

정직성:

- 한 갈래가 실패해도 다른 갈래의 저장 결과를 지우지 않는다. 실패는 그 섹션의
  `unavailable_reason`과 진단으로 남고, 독자 본문에 진단 문구를 넣지 않는다.
- 자료가 전혀 없으면(웹 본문 0 + DB 경기력 0) 최종 전망 요청을 **보내지 않는다**.
- 시작하지 않기로 확정된 호출은 예약을 반환한다(전체 상한은 늘지 않음).
- 조사 결과의 URL은 후보이며, 그 응답에 적힌 사실 문장을 수집 본문으로 쓰지 않는다.
"""

from __future__ import annotations

import operator
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Annotated, Any, Mapping, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session, sessionmaker

from app.preview import (
    artifacts as artifact_store,
    discovery,
    information_bundle as bundle_contract,
    player_section_contracts,
    player_section_store,
    retrieval,
    send_ledger,
    store,
    version_manifest,
)
from app.preview.contracts import (
    Environment,
    ExecutionContext,
    FixtureIdentity,
    OperationKind,
    QualityStatus,
    RequestClass,
    RunMode,
    RunStatus,
)
from app.preview.modules import bundle_sections
from app.preview.models import PreviewRun
from app.preview.registry import get_section_workflow
from app.preview.retry import BudgetLimits, ConcurrencyLimiter, MODULE_SEND_CAP, RunBudget

__all__ = [
    "BUNDLE_PIPELINE_VERSION",
    "BundlePipelineOutcome",
    "INITIAL_PLAYER_SECTIONS",
    "REGENERABLE_SECTIONS",
    "SectionRegenerationOutcome",
    "SectionRegenerationRefused",
    "build_bundle_graph",
    "build_db_snapshot",
    "build_single_section_bundle_graph",
    "run_bundle_pipeline",
    "run_section_initial",
    "run_section_regeneration",
]

# - 2: 선택 결과 구성본(여러 실행의 섹션 결과 버전)과 마지막 AI 단독 재실행 연결.
# - 3: 조사 응답이 검색 기반 AI 요약을 내고 그 요약이 묶음(search_ai_summary)·작성
#   입력에 실제로 들어간다. 같은 경기라도 작성 입력이 달라지므로 새 버전으로 확인한다.
BUNDLE_PIPELINE_VERSION = "mp11-bundle-pipeline-3"

# 시험 집합(run 집합) 표기. 실행 `label`에 이 태그를 붙여 두면, 재시작·새 run 뒤에도
# 같은 집합의 누적 전송을 **영속 장부에서** 다시 셀 수 있다. 새 테이블·새 schema를 만들지
# 않고 기존 `preview_runs.label`과 `preview_write_audit`(send_charged)를 그대로 쓴다.
TRIAL_TAG_PREFIX = "trial-set:"

# 환경변수 `PREVIEW_TRIAL_SET_ID`가 없을 때 쓰는 **과거 시험 집합** 표기 값.
# 2026-11-12 확정 정책에서 집합 누적은 새 경기 생성을 막지 않는다. 이 상수는 옛
# 실행·시험 스크립트의 label 기록 호환에만 남긴다(상한 판정에 쓰지 않는다).
DEFAULT_TRIAL_SET_ID = "sf-b4-search-fallback"


def trial_tag(trial_set_id: str | None) -> str:
    """label에 붙일 시험 집합 태그. 값이 없으면 빈 문자열이다(태그를 만들지 않는다)."""
    text = str(trial_set_id or "").strip()
    return f"{TRIAL_TAG_PREFIX}{text}" if text else ""


def trial_set_of(label: str | None) -> str | None:
    """label에서 시험 집합 ID를 읽는다. 없으면 `None`(옛 실행·일반 실행)."""
    text = str(label or "")
    marker = text.find(TRIAL_TAG_PREFIX)
    if marker < 0:
        return None
    rest = text[marker + len(TRIAL_TAG_PREFIX) :]
    for stop in (" ", "·", "|"):
        index = rest.find(stop)
        if index >= 0:
            rest = rest[:index]
    value = rest.strip()
    return value or None

# 저장 순서(독자 화면 표시 순서). 최종 전망은 마지막에 만든다.
WRITING_SECTIONS: tuple[str, ...] = (
    bundle_contract.SECTION_PLAYERS,
    bundle_contract.SECTION_AVAILABILITY,
    bundle_contract.SECTION_OUTLOOK,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class BundlePipelineOutcome:
    """실행 한 번의 결론. 화면은 `run_id`로 저장된 결과를 다시 연다."""

    run_id: uuid.UUID
    mode: RunMode
    status: RunStatus
    quality: QualityStatus
    bundle_id: str | None = None
    bundle_hash: str | None = None
    bundle_artifact_id: str | None = None
    section_result_ids: Mapping[str, str] = field(default_factory=dict)
    section_quality: Mapping[str, str] = field(default_factory=dict)
    section_unavailable: Mapping[str, str] = field(default_factory=dict)
    discovery_status: Mapping[str, str] = field(default_factory=dict)
    external_calls: int = 0
    model_calls_after: int = 0
    budget: Mapping[str, Any] = field(default_factory=dict)
    unavailable_reason: str | None = None
    diagnostics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "mode": self.mode.value,
            "status": self.status.value,
            "quality": self.quality.value,
            "bundle_id": self.bundle_id,
            "bundle_hash": self.bundle_hash,
            "bundle_artifact_id": self.bundle_artifact_id,
            "section_result_ids": dict(self.section_result_ids),
            "section_quality": dict(self.section_quality),
            "section_unavailable": dict(self.section_unavailable),
            "discovery_status": dict(self.discovery_status),
            "external_calls": self.external_calls,
            "budget": dict(self.budget),
            "unavailable_reason": self.unavailable_reason,
            "diagnostics": list(self.diagnostics),
            "pipeline_version": BUNDLE_PIPELINE_VERSION,
        }


# --------------------------------------------------------------------------
# D0 — 저장 DB 읽기 (모델 0회)
# --------------------------------------------------------------------------


def build_db_snapshot(
    session: Session,
    *,
    fixture: Mapping[str, Any],
    reader: Any,
    run_id: uuid.UUID,
    actor_id: int,
    now: datetime | None = None,
) -> bundle_contract.DbSnapshot:
    """기존 저장 자료를 읽기 전용으로 옮겨 묶음용 DB 스냅샷을 만든다.

    읽지 못한 축은 `None`/빈 목록이고 `coverage`에 사유가 남는다. 특히 부상 행 0건은
    "부상자 없음"의 증거가 아니므로 `unknown`으로 남긴다.
    """
    from app.preview import sections as sections_module
    from app.preview.modules import form as form_module

    moment = now or _now()
    identity = FixtureIdentity.from_dict(dict(fixture))

    # **ID 공간 먼저 맞춘다.** 외부 경기 식별자의 리그 id(예: 39)는 저장 표의 리그 id
    # (예: 1)와 다르다. 저장 경기 행에서 내부 리그·시즌·팀 id를 먼저 읽어 그 값으로
    # 조회한다. 외부 id로 저장 표를 조회하면 0행이 되어 "자료 없음"처럼 보인다.
    internal: dict[str, Any] | None = None
    id_diagnostics: list[str] = []
    if reader is not None:
        try:
            found = reader.get_fixture(fixture_id=identity.fixture_id)
        except Exception as exc:  # noqa: BLE001
            found = None
            id_diagnostics.append(f"저장 경기 식별자를 읽지 못했습니다: {exc}")
        if found is not None:
            internal = {
                "internal_id": found.internal_id,
                "league_id": found.league_id,
                "season": found.season,
                "home_team_id": found.home_team_id,
                "away_team_id": found.away_team_id,
            }
            if found.league_id != identity.league_id or found.season != identity.season:
                id_diagnostics.append(
                    "리그/시즌 id 공간이 달라 저장 경기 행의 내부 값으로 조회했습니다"
                    f"(요청 league_id={identity.league_id}, season={identity.season};"
                    f" 저장 league_id={found.league_id}, season={found.season})."
                )
        else:
            id_diagnostics.append(
                "저장 경기 행을 찾지 못했습니다. 외부 id로만 조회하며 DB 경기 자료는"
                " 없다고 단정하지 않습니다."
            )

    # 내부 값을 조회 기준으로 쓴다(없으면 요청 값을 그대로 쓰되 0행을 '없음'으로 단정하지 않음).
    db_league_id = int((internal or {}).get("league_id") or identity.league_id)
    db_season = int((internal or {}).get("season") or identity.season)
    db_home_team_id = int((internal or {}).get("home_team_id") or identity.home_team_id)
    db_away_team_id = int((internal or {}).get("away_team_id") or identity.away_team_id)

    stored = sections_module.read_stored_context(
        session,
        # 내부 id로 조회되는 식별자. 외부 id는 표시·동일성 키로만 쓴다.
        fixture={
            **dict(fixture),
            "league_id": db_league_id,
            "season": db_season,
            "home_team_id": db_home_team_id,
            "away_team_id": db_away_team_id,
        },
        reader=reader,
        run_id=run_id,
        actor_id=actor_id,
        now=moment,
    )
    facts = stored.facts
    teams = tuple(
        {
            "team_id": team_id,
            "name": name,
        }
        for team_id, name in (
            (facts.home_team_id, facts.home_team),
            (facts.away_team_id, facts.away_team),
        )
        if team_id
    )
    standings: list[dict[str, Any]] = []
    for fact in facts.facts:
        if str(fact.fact_id).startswith("api:standings-"):
            standings.append(
                {
                    "team_id": fact.subject_team_id,
                    "text": fact.text,
                }
            )
    # 선수 시즌 통계(좁은 읽기 전용 역할). 설정·권한이 없으면 상태를 `unknown`으로 남기고
    # 빈 목록을 "기록 0"으로 바꾸지 않는다. 값은 읽은 것만 옮긴다.
    stats_rows: list[dict[str, Any]] = []
    stats_state = "not_configured"
    stats_note: str | None = None
    stats_reader = None
    try:
        from app.preview.sources import player_stats as stats_module

        stats_reader = stats_module.open_player_stats_from_settings()
        if stats_reader is not None:
            collected = stats_reader.season_stats_with_state(
                team_ids=[db_home_team_id, db_away_team_id],
                league_id=db_league_id,
                season_year=db_season,
                now=moment,
            )
            stats_rows = [row.to_dict() for row in collected.rows or ()]
            stats_state = collected.state
            stats_note = collected.reason or collected.coverage_note
    except Exception as exc:  # noqa: BLE001 - 통계 실패를 축구 자료 성공으로 승격하지 않는다
        stats_state = "unknown"
        stats_note = f"선수 통계 조회가 실패했습니다: {type(exc).__name__}"
    finally:
        close = getattr(stats_reader, "close", None)
        if callable(close):
            close()

    injuries: list[dict[str, Any]] = []
    if reader is not None:
        try:
            for row in reader.injuries_for_fixture(identity.fixture_id) or ():
                injuries.append(
                    {
                        "player_name": getattr(row, "player_name", None),
                        "team_id": getattr(row, "team_id", None),
                        "expected_status": getattr(row, "type_marker", None),
                    }
                )
        except Exception:  # noqa: BLE001 - 읽기 실패를 사실로 바꾸지 않는다
            pass

    artifact = artifact_store.save_artifact(
        session,
        run_id=run_id,
        kind=artifact_store.ArtifactKind.RAW_RESPONSE,
        content={
            "source": "stored_read_only_db",
            "note": "기존 DB에서 읽기 전용으로 재사용한 자료입니다. 새 외부 API 호출이 아닙니다.",
            "fixture": dict(fixture),
            "facts": [fact.to_dict() for fact in facts.facts],
            "coverage": [entry.to_dict() for entry in stored.coverage],
        },
        actor_id=actor_id,
        now=moment,
    )
    coverage_entries = [entry.to_dict() for entry in stored.coverage]
    if id_diagnostics:
        coverage_entries.append(
            {
                "topic": "ID 공간",
                "state": "available" if internal else "unknown",
                "detail": " ".join(id_diagnostics),
            }
        )
    coverage_entries.append(
        {
            "topic": "선수 시즌 통계",
            "state": stats_state,
            "detail": stats_note
            or (
                f"저장된 선수 통계 {len(stats_rows)}행을 읽었습니다."
                if stats_rows
                else "선수 통계를 확인하지 못했습니다(기록 0의 증거가 아닙니다)."
            ),
        }
    )
    return bundle_contract.DbSnapshot(
        fixture=dict(fixture),
        team_id_space="internal",
        collected_at=moment,
        teams=teams,
        standings=tuple(standings),
        injuries=tuple(injuries),
        # 선수 통계는 로스터 축에 그대로 담는다(별도 표를 만들지 않는다).
        roster=tuple(stats_rows),
        source_tables=(
            "public.fixture",
            "public.team",
            "public.standings",
            "public.injury",
        ),
        coverage=tuple(coverage_entries),
        diagnostics=tuple(list(stored.diagnostics) + id_diagnostics),
        artifact_id=artifact.id,
        readable=bool(stored.snapshot_ids),
    )


# --------------------------------------------------------------------------
# 섹션 저장
# --------------------------------------------------------------------------


def _fixture_identity_for_run(session: Session, run_id: uuid.UUID) -> FixtureIdentity | None:
    row = session.get(PreviewRun, run_id)
    if row is None or row.fixture_id is None:
        return None
    try:
        return FixtureIdentity(
            fixture_id=int(row.fixture_id),
            league_id=int(row.league_id or 0),
            season=int(row.season or 0),
            home_team_id=int(row.home_team_id or 0),
            away_team_id=int(row.away_team_id or 0),
            kickoff_at=row.kickoff_at,
        )
    except (TypeError, ValueError):
        return None


def _draft_input_hash(draft: bundle_sections.SectionDraft) -> str:
    from app.preview.contracts import compute_input_hash

    return compute_input_hash(
        {
            "section_id": draft.section_id,
            "implementation_version": draft.implementation_version,
            "prompt_version": draft.prompt_version,
            "delivery": (
                draft.delivery.payload_sha256 if draft.delivery is not None else None
            ),
            "passage_ids": (
                list(draft.delivery.passage_ids) if draft.delivery is not None else []
            ),
        }
    )


def _next_module_ordinal(session: Session, run_id: uuid.UUID, module_id: str) -> int:
    from sqlalchemy import func, select

    from app.preview.models import PreviewModuleExecution

    return int(
        session.scalar(
            select(func.count())
            .select_from(PreviewModuleExecution)
            .where(
                PreviewModuleExecution.run_id == run_id,
                PreviewModuleExecution.module_id == module_id,
            )
        )
        or 0
    )


def _next_section_version(session: Session, run_id: uuid.UUID, workflow_id: str) -> int:
    from sqlalchemy import select

    from app.preview.models import PreviewSectionResult

    current = session.scalar(
        select(PreviewSectionResult.version)
        .where(
            PreviewSectionResult.run_id == run_id,
            PreviewSectionResult.workflow_id == workflow_id,
        )
        .order_by(PreviewSectionResult.version.desc())
        .limit(1)
    )
    return int(current or 0) + 1


def _save_draft(
    session: Session,
    *,
    run_id: uuid.UUID,
    draft: bundle_sections.SectionDraft,
    mode: RunMode,
    actor_id: int,
    now: datetime,
) -> uuid.UUID:
    """섹션 초안을 **모듈 결과 + 섹션 결과**로 저장한다.

    모듈 결과를 함께 남기는 이유: 화면의 구조화 값(선수명/이유 분리·부상 상태·매체·
    1X2 표·AI 예상)과 진단이 그 payload에 있고, 섹션 결과의 `result_ids`가 그 행을
    가리켜야 "무엇으로 이 본문을 만들었는지"가 이어진다. 본문이 없으면 `unavailable`로
    남기고 빈 본문을 성공으로 저장하지 않는다.
    """
    from app.preview.contracts import (
        SECTION_RESULT_CONTRACT_VERSION,
        ModuleInput,
        ModuleResult,
        ModuleStatus,
    )

    workflow = get_section_workflow(draft.section_id)
    payload = draft.as_node_payload()
    module_id = draft.module_id or f"{draft.section_id}-writer"
    identity = _fixture_identity_for_run(session, run_id)
    execution = store.start_module_execution(
        session,
        run_id=run_id,
        module_id=module_id,
        module_input=ModuleInput(
            module_id=module_id,
            fixture=identity,
            snapshot_ids=(),
            selected_result_ids=(),
            input_hash=_draft_input_hash(draft),
            prompt_version=draft.prompt_version or "",
            contract_version=SECTION_RESULT_CONTRACT_VERSION,
            implementation_version=draft.implementation_version,
        ),
        ordinal=_next_module_ordinal(session, run_id, module_id),
        actor_id=actor_id,
    )
    saved = store.save_module_result(
        session,
        ModuleResult(
            result_id=uuid.uuid4(),
            module_id=module_id,
            module_execution_id=execution.id,
            run_id=run_id,
            version=1,
            input_hash=execution.input_hash,
            status=(
                ModuleStatus.FAILED if draft.unavailable else ModuleStatus.SUCCEEDED
            ),
            quality=draft.quality,
            diagnostics=tuple(str(item) for item in draft.diagnostics),
            implementation_version=draft.implementation_version,
            prompt_version=draft.prompt_version or "",
            contract_version=SECTION_RESULT_CONTRACT_VERSION,
            # `ModuleResult.to_dict()`가 한 겹 감싸므로 여기서는 초안 payload를 그대로
            # 넣는다. 두 번 감싸면 화면의 구조화 값 조회가 한 단계 더 들어가야 한다.
            payload=payload,
        ),
        actor_id=actor_id,
    )
    version = _next_section_version(session, run_id, draft.section_id)
    quality = draft.quality
    unavailable = draft.unavailable_reason
    if not draft.body.strip() and unavailable is None:
        unavailable = "섹션 본문을 만들지 못했습니다."
        quality = QualityStatus.INSUFFICIENT
    row = store.save_section_result(
        session,
        run_id=run_id,
        workflow_id=draft.section_id,
        module_execution_ids=(execution.id,),
        result_ids=(saved.id,),
        workflow_version=version_manifest.workflow_version_of(draft.section_id),
        title=draft.title or workflow.display_name,
        body=draft.body,
        version=version,
        mode=mode,
        environment=Environment.DEV,
        quality=quality,
        output_contract_version=workflow.output_contract_version,
        contract_version=SECTION_RESULT_CONTRACT_VERSION,
        sources=tuple(dict(item) for item in draft.sources),
        diagnostics=tuple(str(item) for item in draft.diagnostics),
        unavailable_reason=unavailable,
        actor_id=actor_id,
        now=now,
    )
    if (
        draft.section_id
        in player_section_contracts.PLAYER_SECTION_OUTPUT_CONTRACT_VERSIONS
        and draft.unavailable_reason is None
        and bool((draft.body or "").strip())
    ):
        processing = getattr(draft, "player_processing", None)
        if processing is None:
            raise store.ContractError(
                f"{draft.section_id} 정본 저장에 필요한 player_processing 결과가 없습니다."
            )
        contract_result = processing.to_contract_result()
        if contract_result is None:
            raise store.ContractError(
                f"{draft.section_id} 처리 결과가 정본 저장 계약을 만족하지 않습니다."
            )
        storage_input = contract_result.materialize_storage_input(
            section_result_id=row.id,
            run_id=run_id,
        )
        player_section_store.save_player_section(
            session,
            storage_input,
            actor_id=actor_id,
            now=now,
        )
    return row.id



# --------------------------------------------------------------------------
# LangGraph 실행 계획 (한 실행 안에서만 사는 판단 근거)
# --------------------------------------------------------------------------


class _GraphState(TypedDict, total=False):
    """그래프가 노드 사이로 넘기는 상태.

    병렬 갈래가 같은 키에 쓰므로 리듀서를 붙인다(기존 전체 프리뷰 그래프와 같은 방식).
    값은 JSON 직렬화 가능한 기본형만 넣는다(SQLAlchemy 세션·객체는 상태에 넣지 않는다).
    """

    bundle: dict[str, Any] | None
    db_snapshot: dict[str, Any] | None
    discovery: Annotated[list, operator.add]
    sections: Annotated[list, operator.add]
    diagnostics: Annotated[list, operator.add]
    completed: Annotated[list, operator.add]
    unavailable_reason: str | None
    # 마무리 노드 하나만 쓰는 최종 결론. 상태 스키마에 없으면 LangGraph가 버린다.
    final: dict[str, Any] | None


@dataclass
class _Plan:
    """그래프 노드가 공유하는 실행 문맥. 세션은 갈래마다 새로 연다."""

    run_id: uuid.UUID
    context: ExecutionContext
    mode: RunMode
    identity: FixtureIdentity
    fixture: Mapping[str, Any]
    actor_id: int
    moment: datetime
    budget: RunBudget
    transport: Any
    reader: Any
    http: Any
    target_checker: Any
    session_factory: sessionmaker
    home_team: str
    away_team: str
    league: str | None
    db_context: str | None
    # 동시 모델 요청 상한(설계 §실행 예산: 2). 기록 검사가 겹침을 직접 관측한다.
    model_limiter: Any = field(default=None)
    # DB 한국어 이름 해석기(있으면 작성 단계가 실제 이름을 쓴다). 없으면 원문 표기를 유지한다.
    resolver: Any = field(default=None)
    # 섹션 작성에 넘길 선수 후보(DB 통계의 player_id + 표시 이름). E가 F1/F2에서 소비한다.
    player_candidates: tuple[dict[str, Any], ...] = ()
    # 제공자 배당 읽기를 **실행당 1회**로 제한하는 표시. 없으면 제한하지 않는다.
    provider_odds_guard: Any = field(default=None)


# 작성 어댑터에 A가 **반드시** 넘기는 계약(검토 F1/F2). 이름을 조용히 빠뜨리지 않는다.
REQUIRED_BUILDER_PARAMS: tuple[str, ...] = (
    "section_id",
    "bundle",
    "transport",
    "context",
    "budget",
    "session",
    "fixture_names",
    "resolver",
    "player_candidates",
    "now",
)

# 작성기에 **있으면 쓰고 없으면 넘기지 않는** 인자. 배당 제공자 보충 읽기 결과이며,
# 없으면 공개 표 값만 쓰는 이전 동작과 같다. 기존 검사 대역(받지 않는 spy)을 깨지 않는다.
OPTIONAL_BUILDER_PARAMS: tuple[str, ...] = ("provider_odds",)


class BuilderContractError(RuntimeError):
    """작성 어댑터가 A가 요구하는 인자를 받지 않는다. 조용히 빼지 않고 멈춘다."""


def _call_bundle_builder(**kwargs: Any) -> Any:
    """작성 어댑터를 **명시 계약**으로 호출한다.

    `bundle_sections.build_bundle_section`(E 소유)은 F1/F2에서 `player_candidates`·`resolver`를
    받아야 한다. 이전 구현은 `inspect.signature`로 받는 인자만 넘겨 **선수 후보를 조용히
    빠뜨렸고**, 그 결과 DB 통계가 프롬프트에 들어가지 않았다(검토 F1/F2의 직접 원인).
    지금은 필수 인자가 없으면 `BuilderContractError`로 멈춘다 — 누락을 숨기지 않는다.

    `OPTIONAL_BUILDER_PARAMS`(배당 제공자 보충 읽기 결과)만 예외다. 없으면 공개 표 값만
    쓰는 이전 동작과 같으므로, 받지 않는 구현·검사 대역에는 넘기지 않는다.
    """
    import inspect

    parameters = inspect.signature(bundle_sections.build_bundle_section).parameters
    missing = [
        name
        for name in REQUIRED_BUILDER_PARAMS
        if name not in parameters and name in kwargs
    ]
    if missing:
        raise BuilderContractError(
            "bundle_sections.build_bundle_section이 A의 필수 인자를 받지 않습니다: "
            f"{', '.join(missing)}. E 인계(시그니처 확정) 전에는 실행하지 않습니다."
        )
    optional_unsupported = {
        name
        for name in OPTIONAL_BUILDER_PARAMS
        if name not in parameters and name in kwargs
    }
    if optional_unsupported:
        kwargs = {
            key: value for key, value in kwargs.items() if key not in optional_unsupported
        }
    return bundle_sections.build_bundle_section(**kwargs)


def _section_resolver(resolver: Any) -> Any:
    """병렬 섹션 분기마다 공유 이름 해석기의 가변 상태를 격리한다."""
    if resolver is None:
        return None
    from app.preview import player_section_processing

    return player_section_processing.clone_section_resolver(resolver)


def _open_name_resolver(team_ids: Sequence[int] = ()) -> Any:
    """DB 한국어 이름 해석기(이름 전용 읽기 역할). 설정이 없으면 `None`이다.

    **이 경기의 두 팀 범위를 해석기의 기본 scope로 설정한다**(검토 F2). 작성기는 저장
    `player_id`로 이름을 확인할 때 `resolve_player`를 scope 없이 부르므로, 기본 scope가
    없으면 `_names_for(())` → `None` → 이름이 비어 DB 한국어 값이 쓰이지 않는다.
    범위는 그 경기의 내부 team id 두 개로만 한정한다(전체 표 조회 금지).
    """
    from app.preview import sections as sections_module

    scoped = [int(item) for item in team_ids if item is not None]
    try:
        return sections_module._name_resolver(  # noqa: SLF001 - 같은 해석기 팩토리 재사용
            reader=None, default_scope_team_ids=scoped
        )
    except Exception:  # noqa: BLE001 - 이름 변환 실패로 실행을 깨지 않는다
        return None


def _fixture_names(plan: "_Plan", snapshot_payload: Any = None) -> dict[str, Any]:
    """작성 단계가 쓰는 팀 표시 이름.

    **D0이 읽은 DB 팀 이름을 우선**한다(검토 F1/F2). `plan.home_team`은 DB를 못 읽었을 때만
    쓰는 자리표시자이므로, 그것을 먼저 쓰면 실제 이름이 DB에 있어도 프롬프트가
    "team 13"으로 나간다(실제 유료 실행에서 관측된 결함).
    """
    names = [str(item.get("name")) for item in (snapshot_payload or {}).get("teams") or ()
             if isinstance(item, Mapping) and item.get("name")] if isinstance(snapshot_payload, Mapping) else []
    home = names[0] if len(names) > 0 else plan.home_team
    away = names[1] if len(names) > 1 else plan.away_team
    return {"home_team": home, "away_team": away, "league": plan.league}


def _player_candidates(snapshot_payload: Any) -> tuple[dict[str, Any], ...]:
    """DB 통계에서 선수 후보(player_id + 표시 이름)를 만든다. 값은 읽은 것만 쓴다."""
    if not isinstance(snapshot_payload, Mapping):
        return ()
    rows: list[dict[str, Any]] = []
    for row in snapshot_payload.get("roster") or ():
        if not isinstance(row, Mapping):
            continue
        player_id = row.get("player_id")
        if player_id is None:
            continue
        rows.append(
            {
                "player_id": player_id,
                "team_id": row.get("team_id"),
                "display_name_ko": row.get("display_name_ko"),
                "position": row.get("position"),
                "appearances": row.get("appearances"),
                "goals": row.get("goals"),
                "assists": row.get("assists"),
                "minutes": row.get("minutes"),
                "rating": row.get("rating"),
            }
        )
    return tuple(rows)


def _branch_session(plan: _Plan) -> Session:
    """갈래 하나의 **독립 세션**. Session은 스레드에 안전하지 않다."""
    return plan.session_factory()


def _new_provider_odds_guard() -> Any:
    """실행 하나의 제공자 배당 1회 제한 표시. 해석기가 없으면 `None`(제한 없음)."""
    try:
        from app.preview.sources import provider_odds as provider_odds_module

        return provider_odds_module.ReadOnceGuard()
    except Exception:  # noqa: BLE001 - 이 표시가 없어도 배당 섹션은 동작한다
        return None


def _provider_odds_for(
    fixture: Mapping[str, Any],
    *,
    budget: Any,
    moment: datetime,
    guard: Any = None,
) -> Any:
    """표시 상한까지 **남는 자리**가 있을 때 제공자 배당을 한 번 읽는다(명시 실행 전용).

    호출 지점은 **명시적으로 생성·재생성을 시작한 경로**뿐이다. 저장된 결과를 다시
    여는 GET 경로(`section_preview`·`preview_admin` 조회)는 이 함수를 부르지 않는다.
    그래서 조회만으로 외부 호출이 생기지 않는다.

    `guard`(`provider_odds.ReadOnceGuard`)를 넘기면 같은 실행에서 실제 요청이 **최대
    1회**로 제한된다. 두 번째 호출자는 요청 없이 사유만 받는다.

    예산이 없으면 보내지 않고 사유를 남긴다. 실패는 배당 섹션의 진단으로만 남기고
    다른 섹션의 본문·품질을 바꾸지 않는다.
    """
    from app.preview.sources import provider_odds as provider_odds_module

    fixture_id = fixture.get("fixture_id")
    if not isinstance(fixture_id, int) or isinstance(fixture_id, bool):
        return provider_odds_module.ProviderOddsResult(
            sent=0, reason="경기 번호가 없어 제공자 배당 읽기를 시작하지 않았습니다."
        )
    # 1회 제한을 **예산 차감보다 먼저** 확인한다. 이미 읽은 실행이면 요청도, 예산
    # 차감도 하지 않는다(보내지 않은 전송을 사용량으로 세지 않는다).
    if guard is not None and not guard.claim():
        return provider_odds_module.ProviderOddsResult(
            sent=0,
            reason=(
                "이 실행에서 제공자 배당 읽기는 이미 한 번 시도했습니다."
                " 같은 실행에서 다시 보내지 않습니다."
            ),
        )
    allowed, reason = budget.can_attempt(
        provider_odds_module.PROVIDER_ODDS_CALL_ID, RequestClass.API.value
    )
    if not allowed:
        return provider_odds_module.ProviderOddsResult(
            sent=0,
            reason=(
                "API 요청 예산이 없어 제공자 배당 읽기를 보내지 않았습니다:"
                f" {reason or '사유 없음'}"
            ),
        )
    budget.charge(
        provider_odds_module.PROVIDER_ODDS_CALL_ID, RequestClass.API.value
    )
    return provider_odds_module.read_provider_odds(
        fixture_id=int(fixture_id),
        collected_at=moment,
    )


# --------------------------------------------------------------------------
# 노드: D0 (모델 0회)
# --------------------------------------------------------------------------


def _prepare_node(plan: _Plan):
    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = _branch_session(plan)
        try:
            snapshot = build_db_snapshot(
                session,
                fixture=dict(plan.fixture),
                reader=plan.reader,
                run_id=plan.run_id,
                actor_id=plan.actor_id,
                now=plan.moment,
            )
            session.commit()
            return {
                "db_snapshot": snapshot.to_dict(),
                "diagnostics": [str(item) for item in snapshot.diagnostics],
                "completed": ["D0"],
            }
        except Exception as exc:  # noqa: BLE001 - 실패를 상태로 남기고 다음 단계로 간다
            session.rollback()
            reason = f"저장 자료 준비에 실패했습니다: {exc}"
            return {
                "db_snapshot": None,
                "diagnostics": [reason],
                "completed": ["D0"],
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# 노드: 조사 A/B (모델 각 1회, 서로 독립 병렬)
# --------------------------------------------------------------------------


def _db_team_names(snapshot_payload: Any) -> tuple[str | None, str | None]:
    """D0이 읽은 저장 자료에서 팀 표시 이름을 꺼낸다. 없으면 `None`(이름을 만들지 않음)."""
    if not isinstance(snapshot_payload, Mapping):
        return None, None
    teams = [dict(item) for item in snapshot_payload.get("teams") or () if isinstance(item, Mapping)]
    names = [str(item.get("name")) for item in teams if item.get("name")]
    if len(names) >= 2:
        return names[0], names[1]
    return None, None


def _db_context_text(snapshot_payload: Any, *, limit: int = 12) -> str | None:
    """조사 프롬프트에 넣을 저장 DB 사실 문장. 없으면 `None`.

    조사 모델은 **이 문맥만** 쓴다(검색 도구 없음). DB 순위·부상·통계를 넣어 주지 않으면
    모델이 "팀을 식별할 수 없다"며 후보를 비우게 된다(실제 실행에서 관측된 결함).
    """
    if not isinstance(snapshot_payload, Mapping):
        return None
    lines: list[str] = []
    teams = [dict(item) for item in snapshot_payload.get("teams") or () if isinstance(item, Mapping)]
    for team in teams:
        name = team.get("name")
        if name:
            lines.append(f"- 팀: {name} (내부 id {team.get('team_id')})")
    for row in (snapshot_payload.get("standings") or ())[:limit]:
        if isinstance(row, Mapping):
            text = row.get("text") or (
                f"내부 리그 순위 {row.get('rank')}위, 승점 {row.get('points')}"
                if row.get("rank") is not None
                else None
            )
            if text:
                lines.append(f"- 순위: {text}")
    injuries = list(snapshot_payload.get("injuries") or ())
    if injuries:
        for row in injuries[:limit]:
            if isinstance(row, Mapping):
                lines.append(
                    f"- 부상/결장 표기: {row.get('player_name')}"
                    f" (상태 표기 {row.get('expected_status')}, 팀 {row.get('team_id')})"
                )
    else:
        lines.append("- 저장된 부상 행이 없습니다(부상자 없음의 증거가 아닙니다).")
    roster = list(snapshot_payload.get("roster") or ())
    if roster:
        lines.append(f"- 선수 시즌 통계 {len(roster)}행이 저장되어 있습니다.")
    return "\n".join(lines) or None


def _discovery_node(group: str, plan: _Plan):
    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = _branch_session(plan)
        # D0이 읽은 저장 자료에서 **실제 팀 이름과 DB 문맥**을 꺼내 조사에 넘긴다.
        # 자리표시자("team 13")로 조사하면 모델이 팀을 식별하지 못해 후보가 비고,
        # 수집할 본문이 0건이 되어 필수 섹션이 통째로 비는 결함이 실제 실행에서 관측됐다.
        snapshot_payload = state.get("db_snapshot")
        db_home, db_away = _db_team_names(snapshot_payload)
        home_team = db_home or plan.home_team
        away_team = db_away or plan.away_team
        db_context = plan.db_context or _db_context_text(snapshot_payload)
        try:
            with plan.model_limiter if plan.model_limiter is not None else _nullcontext():
                result = discovery.discover_candidates(
                    group=group,
                    fixture=plan.identity,
                    context=plan.context,
                    transport=plan.transport,
                    budget=plan.budget,
                    home_team=home_team,
                    away_team=away_team,
                    league=plan.league,
                    db_context=db_context,
                    session=session,
                    now=plan.moment,
                )
            session.commit()
            group_record = bundle_contract.discovery_group_from_result(result)
            return {
                "discovery": [
                    {
                        "group": group,
                        "status": result.status,
                        "candidates": [candidate.to_dict() for candidate in result.candidates],
                        "record": group_record.to_dict(),
                        "diagnostics": [str(item) for item in result.diagnostics],
                    }
                ],
                "diagnostics": [str(item) for item in result.diagnostics],
                "completed": [f"discovery_{group}"],
            }
        except Exception as exc:  # noqa: BLE001 - 한 조사 실패가 다른 갈래를 지우지 않는다
            session.rollback()
            reason = f"{group} 조사가 실패했습니다: {exc}"
            return {
                "discovery": [
                    {
                        "group": group,
                        "status": "failed",
                        "candidates": [],
                        "record": None,
                        "diagnostics": [reason],
                    }
                ],
                "diagnostics": [reason],
                "completed": [f"discovery_{group}"],
            }
        finally:
            session.close()

    return run


class _nullcontext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> None:
        return None


# --------------------------------------------------------------------------
# 노드: 수집 합류 (모델 0회, HTTP 예산 공유)
# --------------------------------------------------------------------------


def _collection_node(plan: _Plan):
    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = _branch_session(plan)
        try:
            entries = [dict(item) for item in state.get("discovery") or ()]
            candidates: list[Any] = []
            groups: list[bundle_contract.DiscoveryGroup] = []
            for entry in entries:
                for raw in entry.get("candidates") or ():
                    candidates.append(_candidate_from_dict(raw))
                if entry.get("record"):
                    groups.append(
                        bundle_contract.DiscoveryGroup.from_dict(entry["record"])
                    )
            snapshot_payload = state.get("db_snapshot")
            snapshot = (
                bundle_contract.DbSnapshot.from_dict(snapshot_payload)
                if isinstance(snapshot_payload, Mapping)
                else None
            )
            # 배당 정규화에는 **실제 팀 이름**이 필요하다. 전달하지 않으면 파서가
            # `team_names_required`로 즉시 미채택해 배당 섹션이 항상 비어 버린다(검토 F9).
            snapshot_teams = [dict(item) for item in (state.get("db_snapshot") or {}).get("teams") or ()
                              if isinstance(item, Mapping)]
            team_names = [str(item.get("name")) for item in snapshot_teams if item.get("name")]
            home_name = team_names[0] if len(team_names) > 0 else plan.home_team
            away_name = team_names[1] if len(team_names) > 1 else plan.away_team
            collection = retrieval.collect_with_bodies(
                candidates=candidates,
                fixture=plan.identity,
                budget=plan.budget,
                http=plan.http,
                now=plan.moment,
                team_id_space="internal",
                db_snapshot=snapshot,
                discovery_groups=tuple(groups),
                mode=plan.mode.value,
                target_checker=plan.target_checker,
                home_team_names=(home_name,) if home_name else (),
                away_team_names=(away_name,) if away_name else (),
            )
            saved = store.save_information_bundle_with_bodies(
                session,
                run_id=plan.run_id,
                collection=collection,
                actor_id=plan.actor_id,
                now=plan.moment,
            )
            session.commit()
            diagnostics = [
                str(item) for item in collection.diagnostics if isinstance(item, str)
            ]
            return {
                "bundle": dict(saved["bundle"]),
                "diagnostics": diagnostics,
                "completed": ["collection"],
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"공통 수집이 실패했습니다: {exc}"
            return {
                "bundle": None,
                "diagnostics": [reason],
                "unavailable_reason": reason,
                "completed": ["collection"],
            }
        finally:
            session.close()

    return run


def _candidate_from_dict(raw: Mapping[str, Any]) -> Any:
    """상태에 담긴 후보 dict를 `discovery.Candidate`로 되돌린다."""
    return discovery.Candidate(
        candidate_id=str(raw.get("candidate_id") or ""),
        requested_url=str(raw.get("requested_url") or ""),
        canonical_url=str(raw.get("canonical_url") or raw.get("requested_url") or ""),
        title=raw.get("title"),
        kind=str(raw.get("kind") or "other"),
        note=raw.get("note"),
        search_group=str(raw.get("search_group") or ""),
        collected=bool(raw.get("collected") or False),
    )


# --------------------------------------------------------------------------
# 노드: 섹션 작성 (모델 3회 병렬, 배당 0회)
# --------------------------------------------------------------------------


def _section_node(section_id: str, plan: _Plan):
    """섹션 하나를 자기 세션에서 작성·저장한다. 반환은 요약뿐이다."""

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        bundle_payload = state.get("bundle")
        if not isinstance(bundle_payload, Mapping) or not bundle_payload:
            reason = (
                "정보 원문 묶음이 없어 이 섹션을 작성하지 않았습니다."
            )
            if section_id in _MODEL_SECTIONS:
                plan.budget.cancel_call(section_id)
            return {
                "sections": [
                    {
                        "section_id": section_id,
                        "result_id": None,
                        "status": "skipped",
                        "quality": QualityStatus.INSUFFICIENT.value,
                        "unavailable_reason": reason,
                        "delivery": None,
                        "structured": {},
                    }
                ],
                "diagnostics": [f"{section_id}: {reason}"],
                "completed": [section_id],
            }
        bundle = bundle_contract.InformationBundle.from_dict(dict(bundle_payload))
        # F1/F2: D0이 읽은 선수 후보를 상태에서 꺼내 작성 단계로 넘긴다.
        player_candidates = _player_candidates(state.get("db_snapshot"))
        # 배당 섹션은 **남는 자리**가 있을 때만 제공자 `/odds`를 보충 읽기한다(기획:
        # 공개 사이트 우선, API-Football은 남는 자리 보완, 최대 3개 고유 업체).
        # 공개 표가 1~2행이어도 3행까지 채워야 하므로 "0행일 때만"이 아니라
        # "채택된 서로 다른 업체가 3개 미만"일 때 호출한다. 실제 요청은 실행당 1회다.
        provider_odds = None
        if section_id == bundle_contract.SECTION_ODDS:
            from app.preview.sources import provider_odds as provider_odds_module

            if provider_odds_module.has_remaining_slots(bundle.odds):
                # 1회 제한은 `_provider_odds_for`가 소유한다(예산 차감보다 먼저 판정).
                provider_odds = _provider_odds_for(
                    plan.fixture,
                    budget=plan.budget,
                    moment=plan.moment,
                    guard=plan.provider_odds_guard,
                )
        session = _branch_session(plan)
        try:
            with plan.model_limiter if plan.model_limiter is not None else _nullcontext():
                draft = _call_bundle_builder(
                    section_id=section_id,
                    bundle=bundle,
                    transport=plan.transport,
                    context=plan.context,
                    budget=plan.budget,
                    session=session,
                    # F1/F2: DB에서 읽은 선수 후보(player_id·표시 이름)와 한국어 이름 해석기를
                    # 작성 단계에 그대로 넘긴다. 넘기지 않으면 프롬프트에 선수 후보가 비어
                    # 주목 선수 섹션이 근거 없이 비게 된다.
                    fixture_names=_fixture_names(plan, state.get("db_snapshot")),
                    resolver=_section_resolver(plan.resolver),
                    player_candidates=player_candidates,
                    now=plan.moment,
                    provider_odds=provider_odds,
                )
            result_id = _save_draft(
                session,
                run_id=plan.run_id,
                draft=draft,
                mode=plan.mode,
                actor_id=plan.actor_id,
                now=plan.moment,
            )
            session.commit()
            return {
                "sections": [
                    {
                        "section_id": section_id,
                        "result_id": str(result_id),
                        "status": "saved",
                        "quality": draft.quality.value,
                        "unavailable_reason": draft.unavailable_reason,
                        "delivery": draft.delivery.to_dict() if draft.delivery else None,
                        "structured": dict(draft.structured or {}),
                        "processing": (
                            dict(draft.structured["processing"])
                            if isinstance(draft.structured, Mapping)
                            and isinstance(draft.structured.get("processing"), Mapping)
                            else None
                        ),
                        "module_id": draft.module_id,
                        "external_calls": draft.external_calls,
                    }
                ],
                "diagnostics": [str(item) for item in draft.diagnostics],
                "completed": [section_id],
            }
        except Exception as exc:  # noqa: BLE001 - 한 섹션 실패를 다른 섹션에 옮기지 않는다
            session.rollback()
            reason = f"{section_id} 작성이 실패했습니다: {exc}"
            # 예외 **종류**만 남긴다. 원문 메시지에는 SQL·DSN·비밀값이 섞일 수 있으므로
            # 실행 기록(failure_detail)에는 옮기지 않는다. 롤백으로 이 갈래의 행이 모두
            # 사라져도 "무슨 예외였는지"는 남아야 원인을 좁힐 수 있다(2026-11-18 CE-E2E에서
            # 이 정보가 사라져 원인 확정이 막혔다).
            #
            # 단계 라벨은 **중립적인 전체 섹션 실행 이름**이다. 이 `try`는 작성기 호출,
            # 모델 전송, 응답 후처리, 정본 저장을 **모두** 감싸므로, 어느 한 단계에서
            # 났는지 이 경계에서 알 수 없다. 그래서 저장 단계로 단정하는 이름을 쓰지
            # 않는다(세부 단계 계측은 이번 범위가 아니다).
            return {
                "sections": [
                    {
                        "section_id": section_id,
                        "result_id": None,
                        "status": "failed",
                        "quality": QualityStatus.INSUFFICIENT.value,
                        "unavailable_reason": reason,
                        "delivery": None,
                        "structured": {},
                        "failure_kind": type(exc).__name__,
                        "failure_stage": _SECTION_FAILURE_STAGE,
                    }
                ],
                "diagnostics": [reason],
                "completed": [section_id],
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# 노드: 최종 AI 전망 (모델 1회, 앞 섹션 합류 뒤)
# --------------------------------------------------------------------------


def _forecast_node(plan: _Plan):
    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        bundle_payload = state.get("bundle")
        entries = [dict(item) for item in state.get("sections") or ()]
        upstream = {
            str(entry.get("section_id")): entry.get("structured") or {}
            for entry in entries
            if entry.get("structured")
        }
        if not isinstance(bundle_payload, Mapping) or not bundle_payload:
            plan.budget.cancel_call(bundle_contract.SECTION_AI_FORECAST)
            reason = (
                "정보 원문 묶음이 없어 최종 전망 요청을 보내지 않았습니다."
                " 예약 몫을 반환했습니다."
            )
            return {
                "sections": [
                    {
                        "section_id": bundle_contract.SECTION_AI_FORECAST,
                        "result_id": None,
                        "status": "skipped",
                        "quality": QualityStatus.INSUFFICIENT.value,
                        "unavailable_reason": reason,
                        "delivery": None,
                        "structured": {},
                    }
                ],
                "diagnostics": [reason],
                "completed": ["forecast"],
            }

        bundle = bundle_contract.InformationBundle.from_dict(dict(bundle_payload))
        # 자료가 전혀 없으면 요청을 보내지 않고 예약을 반환한다.
        has_db = bool(
            bundle.db_snapshot is not None
            and (
                bundle.db_snapshot.standings
                or bundle.db_snapshot.injuries
                or bundle.db_snapshot.teams
            )
        )
        # 검색 단계가 실제로 확보한 자료(검색 기반 AI 요약 포함)도 작성 입력이다. 이 값을
        # 빼면 본문·DB가 없는 경기에서 요약만 있어도 최종 전망이 건너뛰어진다(SF-02 §3 참고).
        has_search = bool(bundle.deliverable_search_findings)
        if not bundle.usable_sources and not has_db and not has_search and not any(upstream.values()):
            plan.budget.cancel_call(bundle_contract.SECTION_AI_FORECAST)
            reason = (
                "작성 가능한 웹 본문·검색 자료·DB 경기력 자료·앞 섹션 결과가 모두 없어"
                " 최종 전망 요청을 보내지 않았습니다. 예약 몫을 반환했습니다."
            )
            return {
                "sections": [
                    {
                        "section_id": bundle_contract.SECTION_AI_FORECAST,
                        "result_id": None,
                        "status": "skipped",
                        "quality": QualityStatus.INSUFFICIENT.value,
                        "unavailable_reason": reason,
                        "delivery": None,
                        "structured": {},
                    }
                ],
                "diagnostics": [reason],
                "completed": ["forecast"],
            }

        session = _branch_session(plan)
        try:
            with plan.model_limiter if plan.model_limiter is not None else _nullcontext():
                draft = _call_bundle_builder(
                    section_id=bundle_contract.SECTION_AI_FORECAST,
                    bundle=bundle,
                    transport=plan.transport,
                    context=plan.context,
                    budget=plan.budget,
                    session=session,
                    upstream=upstream,
                    fixture_names=_fixture_names(plan, state.get("db_snapshot")),
                    resolver=plan.resolver,
                    now=plan.moment,
                )
            result_id = _save_draft(
                session,
                run_id=plan.run_id,
                draft=draft,
                mode=plan.mode,
                actor_id=plan.actor_id,
                now=plan.moment,
            )
            session.commit()
            return {
                "sections": [
                    {
                        "section_id": bundle_contract.SECTION_AI_FORECAST,
                        "result_id": str(result_id),
                        "status": "saved",
                        "quality": draft.quality.value,
                        "unavailable_reason": draft.unavailable_reason,
                        "delivery": draft.delivery.to_dict() if draft.delivery else None,
                        "structured": dict(draft.structured or {}),
                        "processing": (
                            dict(draft.structured["processing"])
                            if isinstance(draft.structured, Mapping)
                            and isinstance(draft.structured.get("processing"), Mapping)
                            else None
                        ),
                        "module_id": draft.module_id,
                        "external_calls": draft.external_calls,
                    }
                ],
                "diagnostics": [str(item) for item in draft.diagnostics],
                "completed": ["forecast"],
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"최종 전망 작성이 실패했습니다: {exc}"
            return {
                "sections": [
                    {
                        "section_id": bundle_contract.SECTION_AI_FORECAST,
                        "result_id": None,
                        "status": "failed",
                        "quality": QualityStatus.INSUFFICIENT.value,
                        "unavailable_reason": reason,
                        "delivery": None,
                        "structured": {},
                    }
                ],
                "diagnostics": [reason],
                "completed": ["forecast"],
            }
        finally:
            session.close()

    return run


# --------------------------------------------------------------------------
# 노드: 마무리 (전달 기록 반영·필수 섹션 판정·실행 종료)
# --------------------------------------------------------------------------


def _finalize_node(plan: _Plan):
    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = _branch_session(plan)
        try:
            entries = [dict(item) for item in state.get("sections") or ()]
            bundle_payload = state.get("bundle")
            if isinstance(bundle_payload, Mapping) and bundle_payload:
                bundle = bundle_contract.InformationBundle.from_dict(
                    dict(bundle_payload)
                )
                # 저장된 순서(작성 → 배당 → 전망)로 전달 기록을 붙인다.
                ordered = sorted(
                    entries,
                    key=lambda item: _SECTION_ORDER.get(
                        str(item.get("section_id")), 99
                    ),
                )
                for entry in ordered:
                    delivery = entry.get("delivery")
                    if isinstance(delivery, Mapping):
                        bundle = bundle.with_section_delivery(
                            bundle_contract.SectionDelivery.from_dict(delivery)
                        )
                saved = store.save_information_bundle(
                    session,
                    run_id=plan.run_id,
                    bundle=bundle,
                    actor_id=plan.actor_id,
                    now=plan.moment,
                )
                session.commit()
                bundle_id = (saved.get("bundle") or {}).get("bundle_id")
                bundle_hash = (saved.get("bundle") or {}).get("bundle_hash")
                bundle_artifact_id = saved.get("artifact_id")
            else:
                bundle_id = bundle_hash = bundle_artifact_id = None

            section_result_ids = {
                str(entry["section_id"]): str(entry["result_id"])
                for entry in entries
                if entry.get("section_id") and entry.get("result_id")
            }
            section_quality = {
                str(entry["section_id"]): str(entry.get("quality"))
                for entry in entries
                if entry.get("section_id")
            }
            section_unavailable = {
                str(entry["section_id"]): str(entry["unavailable_reason"])
                for entry in entries
                if entry.get("section_id") and entry.get("unavailable_reason")
            }
            # 필수 섹션 = AI 전망·예상 스코어·주목 선수. 하나라도 없으면 정상 완료가 아니다.
            # 필수 섹션은 **본문만** 보지 않는다. 저장 품질이 `ready`여야 하고, AI 전망은
            # 예상 스코어까지 있어야 한다(검토 F4). 스코어가 없으면 정상 완료가 아니다.
            forecast_score_present = False
            for entry in entries:
                if str(entry.get("section_id")) != bundle_contract.SECTION_AI_FORECAST:
                    continue
                structured = entry.get("structured") or {}
                forecast = structured.get("forecast") if isinstance(structured, Mapping) else None
                forecast_score_present = bool(
                    isinstance(forecast, Mapping) and forecast.get("score")
                )
            required_missing = [
                section_id
                for section_id in (
                    bundle_contract.SECTION_AI_FORECAST,
                    bundle_contract.SECTION_PLAYERS,
                )
                if section_id not in section_result_ids
                or section_unavailable.get(section_id)
                or section_quality.get(section_id) != QualityStatus.READY.value
            ]
            if (
                bundle_contract.SECTION_AI_FORECAST in section_result_ids
                and bundle_contract.SECTION_AI_FORECAST not in required_missing
                and not forecast_score_present
            ):
                # 본문은 있어도 예상 스코어가 없으면 필수 요건 미충족이다.
                required_missing.append(bundle_contract.SECTION_AI_FORECAST)
                section_unavailable[bundle_contract.SECTION_AI_FORECAST] = (
                    "AI 예상 스코어가 없어 필수 요건을 충족하지 못했습니다."
                )
            unavailable_reason = (
                "필수 섹션 본문을 만들지 못했습니다: " + ", ".join(required_missing)
                if required_missing
                else None
            )
            # 갈래가 예외로 끝나 행이 남지 않은 섹션은 **예외 종류**를 실행 기록에 남긴다.
            # 원문 메시지·SQL·DSN은 넣지 않는다. 이 값이 없으면 "무슨 예외로 행이
            # 비었는지"를 사후에 알 수 없다(실제로 확인이 막혔다). 라벨은 세부 단계를
            # 특정하지 않는 전체 섹션 실행 이름이다.
            failed_kinds = {
                str(entry.get("section_id")): str(entry.get("failure_kind"))
                for entry in entries
                if entry.get("failure_kind")
            }
            if failed_kinds and unavailable_reason:
                unavailable_reason = (
                    unavailable_reason
                    + " (섹션 작성 예외: "
                    + ", ".join(
                        f"{name}={kind}@{_SECTION_FAILURE_STAGE}"
                        for name, kind in sorted(failed_kinds.items())
                    )
                    + ")"
                )
            quality = (
                QualityStatus.INSUFFICIENT if required_missing else QualityStatus.READY
            )
            store.finish_run(
                session,
                plan.run_id,
                status=(
                    RunStatus.FAILED if required_missing else RunStatus.SUCCEEDED
                ),
                quality=quality,
                failure_detail=unavailable_reason,
                actor_id=plan.actor_id,
            )
            session.commit()
            return {
                "diagnostics": [],
                "unavailable_reason": unavailable_reason,
                "completed": ["finalize"],
                "final": {
                    "section_result_ids": section_result_ids,
                    "section_quality": section_quality,
                    "section_unavailable": section_unavailable,
                    "bundle_id": bundle_id,
                    "bundle_hash": bundle_hash,
                    "bundle_artifact_id": bundle_artifact_id,
                    "quality": quality.value,
                    "status": (
                        RunStatus.FAILED if required_missing else RunStatus.SUCCEEDED
                    ).value,
                    "unavailable_reason": unavailable_reason,
                    "required_missing": required_missing,
                },
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"마무리 저장에 실패했습니다: {exc}"
            return {
                "diagnostics": [reason],
                "unavailable_reason": reason,
                "completed": ["finalize"],
                "final": {
                    "section_result_ids": {},
                    "section_quality": {},
                    "section_unavailable": {},
                    "bundle_id": None,
                    "bundle_hash": None,
                    "bundle_artifact_id": None,
                    "quality": QualityStatus.INSUFFICIENT.value,
                    "status": RunStatus.FAILED.value,
                    "unavailable_reason": reason,
                    "required_missing": [],
                },
            }
        finally:
            session.close()

    return run


# 저장·표시 순서. 갈래는 동시에 돌지만 결과 순서는 고정한다.
_SECTION_ORDER: Mapping[str, int] = {
    bundle_contract.SECTION_PLAYERS: 0,
    bundle_contract.SECTION_AVAILABILITY: 1,
    bundle_contract.SECTION_OUTLOOK: 2,
    bundle_contract.SECTION_ODDS: 3,
    bundle_contract.SECTION_AI_FORECAST: 4,
}

# 섹션 갈래가 예외로 끝났을 때 실행 기록에 남기는 **전체 섹션 실행** 라벨. 이 경계의
# `try`는 작성기 호출·모델 전송·응답 후처리·정본 저장을 한꺼번에 감싸므로, 어느 세부
# 단계였는지 여기서 구분할 수 없다. 그래서 특정 단계(예: 저장)로 단정하지 않는 이름을 쓴다.
_SECTION_FAILURE_STAGE = "section_execution"

# 모델을 쓰는 섹션. 자료가 없어 시작하지 않으면 예약을 반환한다.
_MODEL_SECTIONS: frozenset[str] = frozenset(
    {
        bundle_contract.SECTION_PLAYERS,
        bundle_contract.SECTION_AVAILABILITY,
        bundle_contract.SECTION_OUTLOOK,
        bundle_contract.SECTION_AI_FORECAST,
    }
)


# --------------------------------------------------------------------------
# 그래프 조립 — 분기·합류는 LangGraph가 판정한다
# --------------------------------------------------------------------------


def build_bundle_graph(*, plan: _Plan, checkpointer: Any | None = None):
    """새 기본 경로 그래프.

        START → D0 → (discovery_people ‖ discovery_outlook) → collection
              → (players ‖ availability ‖ outlook ‖ odds) → forecast → finalize → END

    갈래는 서로 다른 스레드에서 돌고 각자 자기 DB 세션을 연다. 예산은 하나의
    `RunBudget`이며 상한·예약·장부는 갈래가 공유한다.
    """
    graph: StateGraph = StateGraph(_GraphState)

    graph.add_node("D0", _prepare_node(plan))
    for group in _DISCOVERY_GROUPS:
        graph.add_node(f"discovery_{group}", _discovery_node(group, plan))
    graph.add_node("collection", _collection_node(plan))
    for section_id in _WRITER_SECTIONS:
        graph.add_node(section_id, _section_node(section_id, plan))
    graph.add_node("forecast", _forecast_node(plan))
    graph.add_node("finalize", _finalize_node(plan))

    graph.add_edge(START, "D0")
    for group in _DISCOVERY_GROUPS:
        graph.add_edge("D0", f"discovery_{group}")
        graph.add_edge(f"discovery_{group}", "collection")
    for section_id in _WRITER_SECTIONS:
        graph.add_edge("collection", section_id)
        graph.add_edge(section_id, "forecast")
    graph.add_edge("forecast", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


_DISCOVERY_GROUPS: tuple[str, ...] = (discovery.GROUP_PEOPLE, discovery.GROUP_OUTLOOK)

# 작성 갈래(모델 3 + 배당 0). 동시에 돌지만 모델 동시 전송은 2로 제한된다.
_WRITER_SECTIONS: tuple[str, ...] = (
    bundle_contract.SECTION_PLAYERS,
    bundle_contract.SECTION_AVAILABILITY,
    bundle_contract.SECTION_OUTLOOK,
    bundle_contract.SECTION_ODDS,
)


# --------------------------------------------------------------------------
# 진입점
# --------------------------------------------------------------------------


def run_bundle_pipeline(
    session: Session,
    *,
    fixture: Mapping[str, Any],
    actor_id: int,
    transport: Any,
    reader: Any = None,
    http: Any = None,
    limits: BudgetLimits | None = None,
    label: str | None = None,
    mode: RunMode | None = None,
    now: datetime | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    league: str | None = None,
    db_context: str | None = None,
    target_checker: Any = None,
    checkpointer: Any | None = None,
    module_send_cap: int | None = None,
    prior_module_usage: Mapping[str, int] | None = None,
    trial_set_id: str | None = None,
) -> BundlePipelineOutcome:
    """정보 원문 묶음 기반 전체 프리뷰를 **LangGraph 그래프**로 한 번 실행한다.

    `module_send_cap`이 주어지면 **모듈(logical_call_id)별 실제 전송**을 그 수로 제한한다.
    `prior_module_usage`는 이전 실행에서 이미 보낸 수이며, 새 실행이 이 카운터를 0으로
    초기화하지 않는다(사용자 승인 단위는 전체 합계가 아니라 모듈별 상한이다).

    실제 모델 전송은 `transport`가 live일 때만 나간다. 갈래마다 자기 세션을 쓰되
    실행 DB(bind)는 같고, 예산·전송 상한·장부는 하나를 공유한다.
    """
    moment = now or _now()
    run_mode = mode or getattr(transport, "mode", RunMode.MOCK)
    budget_limits = limits or BudgetLimits()
    identity = FixtureIdentity.from_dict(dict(fixture))
    run_id = uuid.uuid4()

    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.PREVIEW,
        environment=Environment.DEV,
        mode=run_mode,
        actor_id=actor_id,
        config_version=BUNDLE_PIPELINE_VERSION,
        limits=budget_limits.execution_limits(),
    )
    store.store_run(
        session,
        context,
        fixture=identity,
        fixture_label=f"fixture {identity.fixture_id}",
        label=_with_trial_tag(label or f"정보 원문 프리뷰 · {run_mode.value}", trial_set_id),
        status=RunStatus.RUNNING,
    )
    session.commit()

    # 예산의 **단일 소유자**는 이 생성 경로다. 사용자 확정 정책(모든 논리 모듈에
    # 최초 포함 최대 3회, 전체 8회·trial prior 차감 없음)을 여기서 한 번만 세운다.
    # 호출자가 더 좁은 상한을 다시 걸면 사용자가 정한 의미가 실제로 시험되지 않으므로,
    # `module_send_cap`은 **정책 값과 같은 경우에만** 받아들인다.
    if module_send_cap is not None and int(module_send_cap) != MODULE_SEND_CAP:
        raise ValueError(
            f"module_send_cap={module_send_cap}은 이 생성 정책({MODULE_SEND_CAP}회)과"
            " 다릅니다. 호출자가 상한을 다시 정하지 않습니다."
        )
    budget = RunBudget.for_generation(
        bundle_logical_call_ids(),
        budget_limits,
        prior_module_usage=prior_module_usage,
        now=moment,
    )
    plan = _Plan(
        run_id=run_id,
        context=context,
        mode=run_mode,
        identity=identity,
        fixture=dict(fixture),
        actor_id=actor_id,
        moment=moment,
        budget=budget,
        transport=transport,
        reader=reader,
        http=http,
        target_checker=target_checker,
        # 갈래 세션은 **이 실행 세션과 같은 DB**에 붙는다(다른 대상으로 새지 않는다).
        session_factory=sessionmaker(
            bind=session.get_bind(), autoflush=False, expire_on_commit=False
        ),
        home_team=home_team or f"team {identity.home_team_id}",
        away_team=away_team or f"team {identity.away_team_id}",
        # DB 한국어 이름 해석기. **이 경기의 두 팀 범위**로 묶어 만든다(검토 F2).
        # 설정이 없으면 None이고, 작성 단계는 같은 응답의 한글 표기를 쓴다.
        resolver=_open_name_resolver((identity.home_team_id, identity.away_team_id)),
        player_candidates=(),
        # 제공자 배당 읽기는 이 생성 실행 전체에서 **한 번**이다(배당 갈래 단일).
        provider_odds_guard=_new_provider_odds_guard(),
        league=league,
        db_context=db_context,
        model_limiter=ConcurrencyLimiter(
            budget_limits.model_concurrency, label="모델"
        ),
    )

    graph = build_bundle_graph(plan=plan, checkpointer=checkpointer)
    final_state: Mapping[str, Any] = graph.invoke(
        {
            "bundle": None,
            "db_snapshot": None,
            "discovery": [],
            "sections": [],
            "diagnostics": [],
            "completed": [],
            "unavailable_reason": None,
        },
        {"configurable": {"thread_id": str(run_id)}},
    )

    final = dict(final_state.get("final") or {})
    return BundlePipelineOutcome(
        run_id=run_id,
        mode=run_mode,
        status=RunStatus(final.get("status") or RunStatus.FAILED.value),
        quality=QualityStatus(final.get("quality") or QualityStatus.INSUFFICIENT.value),
        bundle_id=final.get("bundle_id"),
        bundle_hash=final.get("bundle_hash"),
        bundle_artifact_id=final.get("bundle_artifact_id"),
        section_result_ids=dict(final.get("section_result_ids") or {}),
        section_quality=dict(final.get("section_quality") or {}),
        section_unavailable=dict(final.get("section_unavailable") or {}),
        discovery_status={
            str(entry.get("group")): str(entry.get("status"))
            for entry in final_state.get("discovery") or ()
        },
        external_calls=int(budget.model_used),
        model_calls_after=int(budget.model_used),
        budget=budget.snapshot(),
        unavailable_reason=final.get("unavailable_reason"),
        diagnostics=tuple(str(item) for item in final_state.get("diagnostics") or ()),
    )


# 최초 단독 실행 허용 범위: 주목 선수·부상/결장 두 섹션만 해당한다(타 섹션 확장 금지).
INITIAL_PLAYER_SECTIONS: tuple[str, ...] = (
    bundle_contract.SECTION_PLAYERS,
    bundle_contract.SECTION_AVAILABILITY,
)


def _finalize_single_section_node(section_id: str, plan: _Plan):
    """단일 섹션 최초 실행의 묶음 전달 기록·실행 종료 상태를 정본 행 기준으로 닫는다."""

    def run(state: Mapping[str, Any]) -> dict[str, Any]:
        session = _branch_session(plan)
        try:
            entries = [dict(item) for item in state.get("sections") or ()]
            target_entry = next(
                (entry for entry in entries if str(entry.get("section_id")) == section_id),
                None,
            )
            bundle_id: str | None = None
            bundle_hash: str | None = None
            bundle_artifact_id: Any = None
            bundle_payload = state.get("bundle")
            if isinstance(bundle_payload, Mapping) and bundle_payload:
                bundle = bundle_contract.InformationBundle.from_dict(
                    dict(bundle_payload)
                )
                delivery = target_entry.get("delivery") if target_entry else None
                if isinstance(delivery, Mapping):
                    bundle = bundle.with_section_delivery(
                        bundle_contract.SectionDelivery.from_dict(delivery)
                    )
                saved = store.save_information_bundle(
                    session,
                    run_id=plan.run_id,
                    bundle=bundle,
                    actor_id=plan.actor_id,
                    now=plan.moment,
                )
                session.commit()
                bundle_id = (saved.get("bundle") or {}).get("bundle_id")
                bundle_hash = (saved.get("bundle") or {}).get("bundle_hash")
                bundle_artifact_id = saved.get("artifact_id")

            raw_result_id = target_entry.get("result_id") if target_entry else None
            result_id = uuid.UUID(str(raw_result_id)) if raw_result_id else None
            saved_row = (
                store.get_section_result(session, plan.run_id, result_id)
                if result_id is not None
                else None
            )
            if saved_row is not None:
                quality = QualityStatus(saved_row.quality)
                unavailable_reason = saved_row.unavailable_reason
                saved_version = saved_row.version
            else:
                quality = QualityStatus.INSUFFICIENT
                unavailable_reason = (
                    (target_entry or {}).get("unavailable_reason")
                    or state.get("unavailable_reason")
                    or f"{section_id} 섹션 결과를 저장하지 못했습니다."
                )
                saved_version = None

            status = (
                RunStatus.SUCCEEDED if not unavailable_reason else RunStatus.FAILED
            )
            store.finish_run(
                session,
                plan.run_id,
                status=status,
                quality=quality,
                failure_detail=unavailable_reason,
                actor_id=plan.actor_id,
            )
            session.commit()
            return {
                "diagnostics": [],
                "unavailable_reason": unavailable_reason,
                "completed": ["finalize"],
                "final": {
                    "section_result_id": str(result_id) if result_id else None,
                    "section_result_version": saved_version,
                    "bundle_id": bundle_id,
                    "bundle_hash": bundle_hash,
                    "bundle_artifact_id": bundle_artifact_id,
                    "quality": quality.value,
                    "status": status.value,
                    "unavailable_reason": unavailable_reason,
                },
            }
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            reason = f"마무리 저장에 실패했습니다: {exc}"
            return {
                "diagnostics": [reason],
                "unavailable_reason": reason,
                "completed": ["finalize"],
                "final": {
                    "section_result_id": None,
                    "section_result_version": None,
                    "bundle_id": None,
                    "bundle_hash": None,
                    "bundle_artifact_id": None,
                    "quality": QualityStatus.INSUFFICIENT.value,
                    "status": RunStatus.FAILED.value,
                    "unavailable_reason": reason,
                },
            }
        finally:
            session.close()

    return run


def build_single_section_bundle_graph(
    *,
    section_id: str,
    plan: _Plan,
    checkpointer: Any | None = None,
):
    """단일 선수·부상 섹션 최초 실행 LangGraph:

        START → D0 → discovery_people → collection → <section_id> → finalize → END

    선택한 섹션 1개와 그에 필요한 공유 자료 준비(D0·인물 조사·수집)만 실행한다.
    """
    if section_id not in INITIAL_PLAYER_SECTIONS:
        raise SectionRegenerationRefused(
            f"{section_id} 섹션은 최초 단독 실행 대상이 아닙니다."
            " 주목 선수·부상 섹션만 최초 단독 실행을 지원합니다."
        )

    group = regeneration_discovery_group(section_id)
    discovery_node_name = f"discovery_{group}"
    graph: StateGraph = StateGraph(_GraphState)
    graph.add_node("D0", _prepare_node(plan))
    graph.add_node(discovery_node_name, _discovery_node(group, plan))
    graph.add_node("collection", _collection_node(plan))
    graph.add_node(section_id, _section_node(section_id, plan))
    graph.add_node("finalize", _finalize_single_section_node(section_id, plan))

    graph.add_edge(START, "D0")
    graph.add_edge("D0", discovery_node_name)
    graph.add_edge(discovery_node_name, "collection")
    graph.add_edge("collection", section_id)
    graph.add_edge(section_id, "finalize")
    graph.add_edge("finalize", END)
    return graph.compile(checkpointer=checkpointer)


def run_section_initial(
    session: Session,
    *,
    section_id: str,
    fixture: Mapping[str, Any],
    actor_id: int,
    transport: Any,
    reader: Any = None,
    http: Any = None,
    limits: BudgetLimits | None = None,
    label: str | None = None,
    fixture_label: str | None = None,
    mode: RunMode | None = None,
    now: datetime | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
    league: str | None = None,
    db_context: str | None = None,
    target_checker: Any = None,
    checkpointer: Any | None = None,
) -> "SectionRegenerationOutcome":
    """기준 실행(`base_run_id`) 없이 선택한 선수·부상 섹션 1개만 처음 생성·저장한다.

    기존 `build_bundle_graph`와 같은 LangGraph 노드(`D0` → `discovery_people`
    → `collection` → `_section_node` → `_save_draft`)를 사용하며, 다른 섹션은
    실행하지 않고 `_save_draft`로 정본 3표까지 같은 트랜잭션에 저장한다.
    """
    if section_id not in INITIAL_PLAYER_SECTIONS:
        raise SectionRegenerationRefused(
            f"{section_id} 섹션은 최초 단독 실행 대상이 아닙니다."
            " 주목 선수·부상 섹션만 최초 단독 실행을 지원합니다."
        )

    moment = now or _now()
    run_mode = mode or getattr(transport, "mode", RunMode.MOCK)
    budget_limits = limits or BudgetLimits()
    identity = FixtureIdentity.from_dict(dict(fixture))
    run_id = uuid.uuid4()

    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=run_mode,
        actor_id=actor_id,
        config_version=BUNDLE_PIPELINE_VERSION,
        limits=budget_limits.execution_limits(),
    )
    store.store_run(
        session,
        context,
        fixture=identity,
        fixture_label=fixture_label or f"fixture {identity.fixture_id}",
        label=label or f"섹션 최초 실행 · {section_id}",
        status=RunStatus.RUNNING,
    )
    session.commit()

    participating_module_ids = regeneration_logical_call_ids(
        section_id, source_mode="refresh"
    )
    budget = RunBudget.for_generation(
        participating_module_ids,
        budget_limits,
        now=moment,
    )
    plan = _Plan(
        run_id=run_id,
        context=context,
        mode=run_mode,
        identity=identity,
        fixture=dict(fixture),
        actor_id=actor_id,
        moment=moment,
        budget=budget,
        transport=transport,
        reader=reader,
        http=http,
        target_checker=target_checker,
        session_factory=sessionmaker(
            bind=session.get_bind(), autoflush=False, expire_on_commit=False
        ),
        home_team=home_team or f"team {identity.home_team_id}",
        away_team=away_team or f"team {identity.away_team_id}",
        resolver=_open_name_resolver((identity.home_team_id, identity.away_team_id)),
        player_candidates=(),
        provider_odds_guard=_new_provider_odds_guard(),
        league=league,
        db_context=db_context,
        model_limiter=ConcurrencyLimiter(
            budget_limits.model_concurrency, label="모델"
        ),
    )

    graph = build_single_section_bundle_graph(
        section_id=section_id, plan=plan, checkpointer=checkpointer
    )
    final_state: Mapping[str, Any] = graph.invoke(
        {
            "bundle": None,
            "db_snapshot": None,
            "discovery": [],
            "sections": [],
            "diagnostics": [],
            "completed": [],
            "unavailable_reason": None,
        },
        {"configurable": {"thread_id": str(run_id)}},
    )

    final = dict(final_state.get("final") or {})
    raw_result_id = final.get("section_result_id")
    result_id = uuid.UUID(str(raw_result_id)) if raw_result_id else None
    return SectionRegenerationOutcome(
        run_id=run_id,
        section_id=section_id,
        mode=run_mode,
        quality=QualityStatus(final.get("quality") or QualityStatus.INSUFFICIENT.value),
        section_result_id=result_id,
        section_result_version=final.get("section_result_version"),
        source_mode="refresh",
        bundle_id=final.get("bundle_id"),
        bundle_reused=False,
        bundle_refreshed=bool(final.get("bundle_id")),
        external_calls=int(budget.model_used),
        expected_model_calls=len(participating_module_ids),
        unavailable_reason=final.get("unavailable_reason"),
        diagnostics=tuple(str(item) for item in final_state.get("diagnostics") or ()),
        other_sections_untouched=True,
        base_run_id=None,
        base_result_id=None,
        composition_id=None,
    )


# --------------------------------------------------------------------------
# 구성본(여러 실행의 섹션 결과 버전을 골라 묶은 것)
# --------------------------------------------------------------------------

# 구성본이 필요로 하는 섹션. 최종 AI 전망은 이 결과들을 입력으로 쓴다.
COMPOSITION_SECTION_IDS: tuple[str, ...] = bundle_contract.SECTION_IDS


class CompositionRefused(RuntimeError):
    """구성본을 만들 수 없다(범위 밖 경기·다른 섹션·없는 결과 등).

    거부는 **정직하게** 알린다. 선택되지 않은 최신 결과를 몰래 채우지 않는다.
    """


@dataclass(frozen=True)
class CompositionResult:
    """구성본 검증·저장 결과. 관리자 화면이 그대로 낼 수 있는 값만 담는다."""

    composition_id: str
    fixture_id: int
    items: tuple[dict[str, Any], ...]
    refused: tuple[dict[str, Any], ...] = ()
    diagnostics: tuple[str, ...] = ()
    composition: Mapping[str, Any] = field(default_factory=dict)

    @property
    def section_result_ids(self) -> tuple[uuid.UUID, ...]:
        return tuple(
            uuid.UUID(str(item["result_id"]))
            for item in self.items
            if item.get("result_id")
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "composition_id": self.composition_id,
            "fixture_id": self.fixture_id,
            "items": [dict(item) for item in self.items],
            "refused": [dict(item) for item in self.refused],
            "diagnostics": list(self.diagnostics),
            "composition": dict(self.composition),
        }


def _with_trial_tag(label: str, trial_set_id: str | None) -> str:
    """label에 시험 집합 태그를 한 번만 붙인다(이미 있으면 그대로)."""
    tag = trial_tag(trial_set_id)
    if not tag or TRIAL_TAG_PREFIX in label:
        return label
    return f"{label} · {tag}"


# 사용자 승인 단위: **한 생성 실행**의 각 논리 모듈에 최초 포함 실제 전송 최대 3회.
# 다른 경기·이전 시험 집합의 사용량은 이 상한에서 차감하지 않는다(2026-11-12 확정).
# 독립적인 전체 8회 제한은 두지 않으며, 전체 모델 상한은 이 모듈 상한 합계에서 파생한다.
# 값은 `retry.MODULE_SEND_CAP`이 소유한다(위 import). 여기서 다시 정의하지 않는다.


def bundle_logical_call_ids() -> tuple[str, ...]:
    """한 생성 실행이 실제로 실행하는 논리 모듈 id 목록.

    조사 2(discovery_people·discovery_outlook) + 작성 3(players·availability·outlook)
    + 최종 전망 1 = 6개다. 배당은 모델을 쓰지 않는다. 전체 모델 상한을 이 목록의
    모듈 수 × 3으로 파생해, 모듈 상한이 전체 상한에 막히지 않게 한다.
    """
    from app.preview import discovery as discovery_module
    from app.preview.modules import bundle_sections as sections_module

    section_calls = [
        call_id
        for call_id in sections_module.LOGICAL_CALL_IDS.values()
        if call_id is not None
    ]
    return tuple(discovery_module.LOGICAL_CALL_IDS.values()) + tuple(section_calls)


def trial_module_usage(
    session: Session, trial_set_id: str | None
) -> tuple[dict[str, int], tuple[str, ...]]:
    """이번 시험 집합에 속한 **모든 실행**의 모듈별 실제 전송 수.

    반환: (모듈별 누적, 읽지 못한 실행의 사유). 새 run으로 0이 되지 않는다: 집합은 실행
    `label`의 태그로 찾고, 계수는 `send_charged` 장부에서 다시 센다. 집합 표기가 없으면
    `({}, ("집합 표기 없음",))`이며, 호출자는 **상한 없이 실제 전송하지 않는다**.
    """
    text = str(trial_set_id or "").strip()
    if not text:
        return {}, ("시험 집합 표기가 없어 모듈별 상한을 계산할 수 없습니다.",)
    from sqlalchemy import select as _select

    from app.preview import send_ledger as ledger_module
    from app.preview.contracts import RequestClass as _RequestClass
    from app.preview.models import PreviewRun, PreviewWriteAudit

    run_ids: list[uuid.UUID] = []
    errors: list[str] = []
    for row in session.execute(_select(PreviewRun.id, PreviewRun.label)).all():
        if trial_set_of(row[1]) == text:
            run_ids.append(row[0])
    usage: dict[str, int] = {}
    for run_id in run_ids:
        try:
            rows = session.execute(
                _select(PreviewWriteAudit.detail).where(
                    PreviewWriteAudit.run_id == run_id,
                    PreviewWriteAudit.action == ledger_module.CHARGE_ACTION,
                )
            ).all()
        except Exception as exc:  # noqa: BLE001 - 읽기 실패는 실행 거부 사유다
            errors.append(f"{run_id}: {type(exc).__name__}")
            continue
        for (detail,) in rows:
            data = dict(detail or {})
            if not data.get("counted"):
                continue
            if data.get("request_class") != _RequestClass.MODEL.value:
                continue
            module_id = str(data.get("logical_call_id"))
            usage[module_id] = usage.get(module_id, 0) + 1
    return usage, tuple(errors)


def _fixture_id_of_run(session: Session, run_id: uuid.UUID) -> int | None:
    row = session.get(PreviewRun, run_id)
    return None if row is None else row.fixture_id


def resolve_selected_results(
    session: Session,
    *,
    selected_result_ids: Sequence[uuid.UUID],
    expected_fixture_id: int | None,
    allowed_sections: Sequence[str] = COMPOSITION_SECTION_IDS,
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], tuple[str, ...]]:
    """선택한 섹션 결과 버전을 **그 결과가 저장된 실행에서** 확인한다.

    이 함수가 해결하는 두 결함:

    1. 선택 ID가 API에서 받아도 조회할 때 `base_run_id`(한 실행)만 뒤지던 문제.
       여기서는 결과 ID마다 **자기 실행**을 찾아 읽는다. 그래서 서로 다른 실행의 같은
       경기 결과를 함께 고를 수 있고, 기존 결과 행은 그대로 둔다.
    2. 다른 경기 결과가 섞이는 문제. 경기 ID가 다르면 그 항목은 **거부**하고 사유를
       남긴다. 선택되지 않은 최신 결과로 대체하지 않는다.

    반환: (items, refused, diagnostics)
    """
    items: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    seen_sections: set[str] = set()
    allowed = set(allowed_sections)
    for raw in selected_result_ids:
        result_id = uuid.UUID(str(raw))
        row = store.get_section_result_any_run(session, result_id)
        if row is None:
            refused.append(
                {
                    "result_id": str(result_id),
                    "reason": "저장된 섹션 결과를 찾지 못했습니다.",
                }
            )
            continue
        fixture_id = _fixture_id_of_run(session, row.run_id)
        if expected_fixture_id is not None and fixture_id != expected_fixture_id:
            refused.append(
                {
                    "result_id": str(result_id),
                    "section_id": row.workflow_id,
                    "reason": (
                        "다른 경기의 결과입니다."
                        f" 요청 경기 {expected_fixture_id}, 결과 경기 {fixture_id}."
                    ),
                }
            )
            continue
        if row.workflow_id not in allowed:
            refused.append(
                {
                    "result_id": str(result_id),
                    "section_id": row.workflow_id,
                    "reason": "이 구성본이 쓰지 않는 섹션입니다.",
                }
            )
            continue
        if row.workflow_id in seen_sections:
            refused.append(
                {
                    "result_id": str(result_id),
                    "section_id": row.workflow_id,
                    "reason": "같은 섹션의 결과를 두 번 골랐습니다.",
                }
            )
            continue
        seen_sections.add(row.workflow_id)
        items.append(
            {
                "section_id": row.workflow_id,
                "result_id": str(row.id),
                "run_id": str(row.run_id),
                "fixture_id": fixture_id,
                "version": row.version,
                "workflow_version": row.workflow_version,
                "quality": row.quality,
                "unavailable": row.unavailable_reason is not None,
                "unavailable_reason": row.unavailable_reason,
                "body_chars": len(row.body or ""),
                "mode": row.mode,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "output_contract_version": row.output_contract_version,
            }
        )
    if refused:
        diagnostics.append(
            f"선택한 결과 {len(refused)}건을 쓰지 않았습니다(사유는 refused에 적었습니다)."
        )
    return tuple(items), tuple(refused), tuple(diagnostics)


def save_composition(
    session: Session,
    *,
    run_id: uuid.UUID,
    fixture_id: int | None,
    selected_result_ids: Sequence[uuid.UUID],
    actor_id: int,
    now: datetime | None = None,
) -> dict[str, Any]:
    """선택 ID 집합을 검증해 **저장 구성본**으로 남긴다.

    구성본은 최종 AI 재실행에 그대로 넘길 수 있는 형태다(선택 ID + 각 항목의 실행·버전).
    선택되지 않은 결과를 더하거나 최신 버전으로 바꾸지 않는다.
    """
    items, refused, diagnostics = resolve_selected_results(
        session,
        selected_result_ids=selected_result_ids,
        expected_fixture_id=fixture_id,
    )
    if not items:
        raise CompositionRefused(
            "구성본에 넣을 수 있는 섹션 결과가 없습니다: "
            + (refused[0]["reason"] if refused else "선택한 결과가 없습니다.")
        )
    composition = {
        "composition_id": f"cmp-{uuid.uuid4().hex[:12]}",
        "fixture_id": fixture_id,
        "selected_result_ids": [str(item) for item in selected_result_ids],
        "items": [dict(item) for item in items],
        "refused": [dict(item) for item in refused],
        "diagnostics": list(diagnostics),
        "section_result_ids": [item["result_id"] for item in items],
        "created_at": (now or _now()).isoformat(),
    }
    saved = store.save_composition(
        session,
        run_id=run_id,
        composition=composition,
        actor_id=actor_id,
        now=now,
    )
    return {
        "artifact_id": saved.get("artifact_id"),
        "composition": composition,
        "items": [dict(item) for item in items],
        "refused": [dict(item) for item in refused],
        "diagnostics": list(diagnostics),
    }


def composition_upstream(
    session: Session, composition: Mapping[str, Any]
) -> dict[str, Any]:
    """저장된 구성본을 최종 AI가 읽는 `upstream` 모양으로 바꾼다.

    각 항목은 **구성본에 적힌 결과 ID 하나**만 읽는다(그 실행의 최신 결과가 아니다).
    그래서 선택하지 않은 버전이 조용히 섞이지 않는다.
    """
    upstream: dict[str, Any] = {}
    for item in composition.get("items") or ():
        if not isinstance(item, Mapping):
            continue
        result_id = item.get("result_id")
        if not result_id:
            continue
        row = store.get_section_result_any_run(session, uuid.UUID(str(result_id)))
        if row is None:
            continue
        payload = _section_payload(session, row)
        if payload:
            upstream[str(item.get("section_id") or row.workflow_id)] = payload
    return upstream


def _section_payload(session: Session, row: Any) -> dict[str, Any]:
    """섹션 결과 행 → 최종 AI 입력(구조화 값 + 본문). 값을 만들지 않는다.

    `store.save_module_result`는 `ModuleResult.to_dict()`를 저장하므로 실제 구조화 값은
    `payload → structured` 두 겹 아래에 있다. 한 겹만 읽으면 최종 AI가 선수·부상·매체
    행을 찾지 못해 "결과가 없다"로 작성한다(그래서 두 모양 모두 읽는다).
    """
    payload: dict[str, Any] = {}
    for result_id in row.result_ids or ():
        result = session.get(_PreviewResultModel(), uuid.UUID(str(result_id)))
        if result is None:
            continue
        stored = dict(result.payload or {})
        # 두 겹(`payload.structured`)을 먼저 읽고, 없으면 한 겹 구조를 쓴다.
        candidate = stored.get("payload")
        for source in (candidate if isinstance(candidate, Mapping) else None, stored):
            if not isinstance(source, Mapping):
                continue
            structured = source.get("structured")
            if isinstance(structured, Mapping):
                payload.update(dict(structured))
                break
            if any(
                key in source
                for key in ("players", "injuries", "media", "odds", "forecast")
            ):
                payload.update(dict(source))
                break
    payload.setdefault("body", row.body or "")
    return payload


def _PreviewResultModel():
    from app.preview.models import PreviewResult

    return PreviewResult


# --------------------------------------------------------------------------
# 섹션 단독 재생성 — 실제 묶음 재사용/갱신 (검토 F5)
# --------------------------------------------------------------------------

# 재생성에서 실제로 지원하는 섹션. 새 작성 어댑터로 만드는 섹션이며, 옛 노드 경로를
# "묶음 재사용"으로 표시하지 않는다.
REGENERABLE_SECTIONS: tuple[str, ...] = (
    bundle_contract.SECTION_PLAYERS,
    bundle_contract.SECTION_AVAILABILITY,
    bundle_contract.SECTION_OUTLOOK,
    bundle_contract.SECTION_ODDS,
    bundle_contract.SECTION_AI_FORECAST,
)


def regeneration_discovery_group(section_id: str) -> str:
    """재생성 refresh가 그 섹션에 실제로 실행하는 조사 묶음.

    최종 전망·배당은 전망 쪽 자료를, 나머지 작성 섹션은 선수·부상 쪽 자료를 쓴다.
    `run_section_regeneration`의 refresh 분기와 예산 구성이 **같은 함수**를 보게 해서
    "예산에 넣은 모듈"과 "실제로 호출하는 모듈"이 어긋나지 않게 한다.
    """
    if section_id in (bundle_contract.SECTION_OUTLOOK, bundle_contract.SECTION_ODDS):
        return discovery.GROUP_OUTLOOK
    return discovery.GROUP_PEOPLE


def regeneration_logical_call_ids(
    section_id: str, *, source_mode: str
) -> tuple[str, ...]:
    """재생성 한 번이 실제로 실행하는 논리 AI 모듈 id 목록(첫 전송 전에 확정한다).

    모듈별 3회 상한은 `effective_model_requests()`에서 **이 목록의 길이 × 3**으로
    파생된다. 그래서 이 목록이 실제 실행 계획보다 좁으면 조사 모듈이 쓴 전송이
    작성 모듈의 3회를 굶긴다(검토 B-2). 반대로 넓으면 이번에 부르지도 않는 모듈의
    몫이 상한에 더해져 실제로는 쓸 수 없는 여유가 생긴다. 두 경우를 모두 피한다.

    - `reuse`: 저장 묶음을 그대로 쓰고 수집·검색 호출이 0이다. 선택한 작성 모듈만
      넣는다(배당은 모델 0회이므로 목록이 비고, 상한 판정은 옛 전체 상한 경로를 쓴다).
    - `refresh`: 그 섹션에 필요한 조사 1개 + 선택한 작성 모듈. 새 조사 그룹·새 모듈을
      추가하지 않는다.
    """
    section_call = bundle_sections.LOGICAL_CALL_IDS.get(section_id)
    calls: list[str] = []
    if source_mode == "refresh":
        group_call = discovery.LOGICAL_CALL_IDS.get(
            regeneration_discovery_group(section_id)
        )
        if group_call:
            calls.append(group_call)
    if section_call:
        calls.append(section_call)
    # 같은 모듈을 두 번 세면 상한이 부풀려지므로 순서를 지키며 한 번만 남긴다.
    return tuple(dict.fromkeys(calls))


@dataclass(frozen=True)
class SectionRegenerationOutcome:
    """섹션 하나를 다시 만든 결과. 어떤 묶음을 썼고 무엇을 다시 수집했는지 밝힌다."""

    run_id: uuid.UUID
    section_id: str
    mode: RunMode
    quality: QualityStatus
    section_result_id: uuid.UUID | None
    section_result_version: int | None
    source_mode: str
    bundle_id: str | None
    bundle_reused: bool
    bundle_refreshed: bool
    external_calls: int
    expected_model_calls: int | None
    unavailable_reason: str | None
    diagnostics: tuple[str, ...] = ()
    other_sections_untouched: bool = True
    base_run_id: uuid.UUID | None = None
    base_result_id: uuid.UUID | None = None
    # 이 실행이 실제로 쓴 구성본 ID(안 썼으면 None). 화면·로그가 그대로 표시한다.
    composition_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": str(self.run_id),
            "section_id": self.section_id,
            "mode": self.mode.value,
            "quality": self.quality.value,
            "section_result_id": str(self.section_result_id)
            if self.section_result_id
            else None,
            "section_result_version": self.section_result_version,
            "source_mode": self.source_mode,
            "bundle_id": self.bundle_id,
            "bundle_reused": self.bundle_reused,
            "bundle_refreshed": self.bundle_refreshed,
            "external_calls": self.external_calls,
            "expected_model_calls": self.expected_model_calls,
            "unavailable_reason": self.unavailable_reason,
            "diagnostics": list(self.diagnostics),
            "other_sections_untouched": self.other_sections_untouched,
            "base_run_id": str(self.base_run_id) if self.base_run_id else None,
            "base_result_id": str(self.base_result_id) if self.base_result_id else None,
            "composition_id": self.composition_id,
        }


class SectionRegenerationRefused(RuntimeError):
    """이 섹션은 새 경로로 재생성할 수 없다. 옛 경로로 대신 만들지 않는다."""


def run_section_regeneration(
    session: Session,
    *,
    section_id: str,
    actor_id: int,
    transport: Any,
    base_run_id: uuid.UUID,
    source_mode: str = "reuse",
    base_result_id: uuid.UUID | None = None,
    reader: Any = None,
    http: Any = None,
    limits: BudgetLimits | None = None,
    now: datetime | None = None,
    upstream_result_ids: Sequence[uuid.UUID] = (),
    composition_id: str | None = None,
) -> SectionRegenerationOutcome:
    """저장된 정보 원문 묶음으로 **섹션 하나만** 다시 만든다.

    - `source_mode="reuse"`: 저장 묶음을 그대로 쓰고 **수집·검색 호출 0**이다. 작성 호출만
      발생한다(배당은 모델 0회).
    - `source_mode="refresh"`: 그 섹션에 필요한 자료만 새로 모은다(조사·수집). 다른 성공
      섹션의 결과는 건드리지 않는다.
    - 최종 전망은 앞 섹션 결과 버전을 **명시**해 재사용한다(`upstream_result_ids`).
    - 관리자가 저장한 **구성본**(`/runs/{id}/composition`)이 있으면 그 선택 ID 집합을
      우선 쓴다(`composition_id`로 특정 구성본을 지정할 수도 있다). 구성본을 통해 서로
      다른 실행의 같은 경기 결과를 조합할 수 있고, 다른 경기 결과는 거부된다.

    새 실행을 만들고 그 안에 섹션 결과 버전을 남긴다. 부모 실행은 덮어쓰지 않는다.
    """
    from app.preview import discovery as discovery_module
    from app.preview import retrieval as retrieval_module

    if section_id not in REGENERABLE_SECTIONS:
        raise SectionRegenerationRefused(
            f"{section_id} 섹션은 정보 원문 묶음 경로로 재생성할 수 없습니다."
            " 옛 조사 경로로 대신 만들지 않습니다."
        )
    if source_mode not in ("reuse", "refresh"):
        raise ValueError(f"unknown source_mode {source_mode!r}")

    moment = now or _now()
    run_mode = getattr(transport, "mode", RunMode.MOCK)
    budget_limits = limits or BudgetLimits()

    record = store.load_information_bundle(session, base_run_id)
    if source_mode == "reuse" and not record.get("available"):
        raise SectionRegenerationRefused(
            "재사용할 정보 원문 묶음이 없습니다: "
            f"{record.get('reason') or '사유 없음'}"
        )
    stored_bundle = (
        bundle_contract.InformationBundle.from_dict(record["bundle"])
        if record.get("bundle")
        else None
    )

    base_detail = store.get_run_detail(session, base_run_id)
    fixture_row = base_detail.fixture
    if fixture_row is None:
        raise SectionRegenerationRefused("부모 실행에 경기 식별자가 없습니다.")
    fixture = fixture_row.to_dict()

    # 시험 집합(trial-set) 표기는 **과거 실행의 기록**으로만 보존한다. 사용자 확정
    # 정책은 "한 생성 실행의 각 논리 모듈 최초 포함 3회"이므로, 다른 경기·이전 시험의
    # 누적을 상한 계산에서 차감하지 않는다. 그래서 부모에 집합 표기가 없어도 재생성을
    # 막지 않는다(과거 게이트는 새 정책과 모순이었다). 장부는 읽되 차단에 쓰지 않는다.
    regeneration_trial = trial_set_of(getattr(base_detail.summary, "label", None))
    prior_usage: dict[str, int] = {}
    usage_problems: tuple[str, ...] = ()
    if regeneration_trial:
        prior_usage, usage_problems = trial_module_usage(session, regeneration_trial)

    run_id = uuid.uuid4()
    context = ExecutionContext(
        run_id=run_id,
        operation_kind=OperationKind.SECTION,
        environment=Environment.DEV,
        mode=run_mode,
        actor_id=actor_id,
        config_version=BUNDLE_PIPELINE_VERSION,
        limits=budget_limits.execution_limits(),
    )
    store.store_run(
        session,
        context,
        fixture=fixture_row,
        fixture_label=base_detail.summary.fixture_label,
        # 부모 실행이 시험 집합에 속해 있으면 재생성 실행도 같은 표기를 이어 받아
        # **기록**에 남긴다(정책 판정에는 쓰지 않는다). 표기가 없으면 새로 만들지 않는다.
        label=_with_trial_tag(
            f"섹션 재생성 · {section_id} · {source_mode}",
            regeneration_trial,
        ),
        status=RunStatus.RUNNING,
    )
    session.commit()

    budget = RunBudget.for_run(budget_limits, now=moment)
    # 모듈별 3회 상한을 **재생성에도** 똑같이 건다. 이 주입이 없으면 반복 재생성이
    # 같은 모듈을 계속 보낼 수 있다(SF-02 직접 회귀). 상한은 이번 재생성 실행 안에서만
    # 세고, 이전 실행 누적은 표시용(`prior_module_usage`)으로만 남긴다.
    #
    # 참여 모듈 집합은 **첫 전송 전에** 이 실행의 실제 계획으로 정한다(검토 B-2).
    # 예전에는 선택한 작성 모듈 1개만 넣었는데, refresh는 같은 예산으로 조사 모듈도
    # 호출해서 조사 2회 + 작성 1회 뒤 작성의 두 번째가 "합계 3회"로 거부됐다. 그 조사
    # 전송이 작성 모듈의 3회를 굶기면 안 되므로, refresh는 실제로 호출하는 조사 모듈도
    # 이 목록에 넣는다(새 모듈·새 조사 그룹·추가 호출은 만들지 않는다).
    participating_module_ids = regeneration_logical_call_ids(
        section_id, source_mode=source_mode
    )
    budget.module_send_cap = MODULE_SEND_CAP
    budget.module_ids = participating_module_ids
    budget.prior_module_usage = dict(prior_usage)
    # 재생성도 전역 1800초가 모듈 3회를 잘라내지 않게 한다(요청별 300초는 유지).
    budget.deadline_enforced = False
    participating_text = (
        ", ".join(participating_module_ids) if participating_module_ids else "없음(모델 0회)"
    )
    diagnostics: list[str] = [
        f"이번 재생성 실행의 모듈 상한 {MODULE_SEND_CAP}회를 적용했습니다. 실제 참여"
        f" 모듈({source_mode}): {participating_text}. 이전 시험 집합 누적은 차단에 쓰지"
        f" 않고 표시만 합니다: {dict(sorted(prior_usage.items()))}"
    ]
    if usage_problems:
        # 과거 장부를 읽지 못한 사실은 기술 진단으로 남긴다. 새 정책에서는 이 이력이
        # 상한 판정에 쓰이지 않으므로 재생성을 막지 않는다.
        diagnostics.append(
            "이전 시험 집합 장부 일부를 읽지 못했습니다(차단에는 쓰지 않음): "
            + "; ".join(str(item) for item in usage_problems)
        )
    refreshed = False
    bundle = stored_bundle
    # 화면·프롬프트에 쓸 팀 이름. reuse 경로는 저장 묶음의 DB 스냅샷에서 가져온다.
    home_name = f"team {fixture_row.home_team_id}"
    away_name = f"team {fixture_row.away_team_id}"
    if stored_bundle is not None and stored_bundle.db_snapshot is not None:
        stored_teams = [
            str(item.get("name"))
            for item in (stored_bundle.db_snapshot.teams or ())
            if isinstance(item, Mapping) and item.get("name")
        ]
        if len(stored_teams) > 0:
            home_name = stored_teams[0]
        if len(stored_teams) > 1:
            away_name = stored_teams[1]

    if source_mode == "refresh":
        # 그 섹션에 필요한 조사/수집만 새로 한다(다른 섹션 결과는 그대로 둔다).
        db_snapshot = build_db_snapshot(
            session,
            fixture=fixture,
            reader=reader,
            run_id=run_id,
            actor_id=actor_id,
            now=moment,
        )
        session.commit()
        diagnostics.extend(db_snapshot.diagnostics)
        # 예산에 넣은 조사 모듈과 **같은 함수**로 고른다(검토 B-2). 두 곳에서 따로
        # 판단하면 예산 목록과 실제 호출이 다시 어긋날 수 있다.
        group = regeneration_discovery_group(section_id)
        teams = [str(item.get("name")) for item in db_snapshot.teams if item.get("name")]
        home_name = teams[0] if teams else f"team {fixture_row.home_team_id}"
        away_name = teams[1] if len(teams) > 1 else f"team {fixture_row.away_team_id}"
        discovery_groups: list[bundle_contract.DiscoveryGroup] = []
        candidates: list[Any] = []
        try:
            result = discovery_module.discover_candidates(
                group=group,
                fixture=fixture_row,
                context=context,
                transport=transport,
                budget=budget,
                home_team=home_name,
                away_team=away_name,
                league=str(fixture.get("league") or "") or None,
                db_context=_db_context_text(db_snapshot.to_dict()),
                session=session,
                now=moment,
            )
            candidates.extend(result.candidates or ())
            discovery_groups.append(bundle_contract.discovery_group_from_result(result))
            session.commit()
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(f"{group} 조사가 실패했습니다: {exc}")
        collection = retrieval_module.collect_with_bodies(
            candidates=candidates,
            fixture=fixture_row,
            budget=budget,
            http=http,
            now=moment,
            team_id_space="internal",
            db_snapshot=db_snapshot,
            discovery_groups=tuple(discovery_groups),
            mode=run_mode.value,
            home_team_names=(home_name,),
            away_team_names=(away_name,),
        )
        saved = store.save_information_bundle_with_bodies(
            session, run_id=run_id, collection=collection, actor_id=actor_id, now=moment
        )
        session.commit()
        bundle = bundle_contract.InformationBundle.from_dict(saved["bundle"])
        refreshed = True
    elif bundle is None:  # pragma: no cover - reuse 경로는 위에서 걸러진다
        raise SectionRegenerationRefused("재사용할 묶음이 없습니다.")

    upstream: dict[str, Any] = {}
    # 이 실행이 실제로 쓴 선택 결과(구성본 복사 저장에 쓴다). 두 분기 모두에서 채운다.
    upstream_items: tuple[dict[str, Any], ...] = ()
    upstream_refused: tuple[dict[str, Any], ...] = ()
    # 저장된 구성본을 **실제 실행 경로에서** 읽는다. 이 연결이 없으면 구성본은 저장·조회만
    # 되고 마지막 AI 입력으로 이어지지 않는다(SF-02 차단 2).
    stored_composition: Mapping[str, Any] | None = None
    composition_record = store.load_composition(session, base_run_id)
    if composition_record.get("available"):
        candidate = composition_record.get("composition") or {}
        saved_id = str(candidate.get("composition_id") or "")
        if composition_id and str(composition_id) != saved_id:
            raise SectionRegenerationRefused(
                f"저장된 구성본과 요청한 composition_id가 다릅니다. 저장 값: {saved_id}"
            )
        stored_composition = candidate
    elif composition_id:
        raise SectionRegenerationRefused(
            "이 실행에는 저장된 구성본이 없습니다. 먼저 섹션 결과를 골라 구성본을"
            " 저장하세요."
        )

    if stored_composition and not upstream_result_ids:
        # 구성본이 기준이다. 선택 ID를 다시 검증해(다른 경기·없는 결과·중복 섹션 거부)
        # 통과한 항목만 upstream으로 넘긴다. 선택되지 않은 최신 결과는 섞지 않는다.
        composition_ids = [
            uuid.UUID(str(item["result_id"]))
            for item in stored_composition.get("items") or ()
            if isinstance(item, Mapping) and item.get("result_id")
        ]
        items, refused, resolve_diagnostics = resolve_selected_results(
            session,
            selected_result_ids=composition_ids,
            expected_fixture_id=fixture_row.fixture_id,
        )
        diagnostics.extend(resolve_diagnostics)
        for refusal in refused:
            diagnostics.append(
                f"구성본 항목 {refusal.get('result_id')}를 쓰지 않았습니다:"
                f" {refusal.get('reason')}"
            )
        upstream_items = tuple(dict(item) for item in items)
        upstream_refused = tuple(dict(item) for item in refused)
        if items:
            upstream = composition_upstream(
                session, {"items": [dict(item) for item in items]}
            )
            diagnostics.append(
                f"저장된 구성본({stored_composition.get('composition_id')})의 결과"
                f" {len(upstream)}건을 최종 입력으로 사용했습니다."
            )
    elif upstream_result_ids:
        # 최종 전망은 **관리자가 고른** 앞 섹션 결과 버전을 입력으로 쓴다. 각 ID는
        # **자기 실행**에서 찾는다(서로 다른 실행의 결과를 섞어 고를 수 있어야 한다).
        # 이전 구현은 base_run_id 하나만 뒤져 다른 실행에서 고른 결과를 조용히 버렸다.
        items, refused, resolve_diagnostics = resolve_selected_results(
            session,
            selected_result_ids=upstream_result_ids,
            expected_fixture_id=fixture_row.fixture_id,
        )
        diagnostics.extend(resolve_diagnostics)
        for refusal in refused:
            diagnostics.append(
                f"선택 결과 {refusal.get('result_id')}를 쓰지 않았습니다:"
                f" {refusal.get('reason')}"
            )
        upstream_items = tuple(dict(item) for item in items)
        upstream_refused = tuple(dict(item) for item in refused)
        for item in items:
            row = store.get_section_result_any_run(
                session, uuid.UUID(str(item["result_id"]))
            )
            if row is None:  # pragma: no cover - 방금 확인한 행이다
                continue
            payload = _section_payload(session, row)
            if payload:
                upstream[str(item["section_id"])] = payload

    # F5-b: 재생성도 **같은 fixture-scoped 해석기와 선수 후보**를 넘긴다. 넘기지 않으면
    # 재생성 본문에서만 DB 한국어 이름·통계가 빠져, 같은 섹션을 다시 만들 때 결과가 달라진다.
    regen_team_ids = [
        value
        for value in (fixture_row.home_team_id, fixture_row.away_team_id)
        if value is not None
    ]
    regen_snapshot = (
        bundle.db_snapshot.to_dict() if bundle is not None and bundle.db_snapshot else None
    )
    # 배당 섹션을 **명시적으로 다시 만들 때만** 제공자 `/odds` 보충 읽기를 붙인다.
    # 공개 표가 3개 미만 업체면 남는 자리를 채운다(사이트 우선·최대3·호출 1회 유지).
    regen_provider_odds = None
    if section_id == bundle_contract.SECTION_ODDS:
        from app.preview.sources import provider_odds as provider_odds_module

        if provider_odds_module.has_remaining_slots(bundle.odds):
            # 재생성도 **같은 헬퍼**를 쓴다(1회 제한 → 예산 판정 → 차감 → 1회 읽기).
            # 순서를 여기서 다시 구현하지 않는다(차감·전송 장부가 어긋나는 원인).
            regen_provider_odds = _provider_odds_for(
                {"fixture_id": int(fixture_row.fixture_id)},
                budget=budget,
                moment=moment,
                guard=_new_provider_odds_guard(),
            )
    draft = _call_bundle_builder(
        section_id=section_id,
        bundle=bundle,
        transport=transport,
        context=context,
        budget=budget,
        session=session,
        upstream=upstream,
        fixture_names={"home_team": home_name, "away_team": away_name, "league": None},
        resolver=_section_resolver(_open_name_resolver(regen_team_ids)),
        player_candidates=_player_candidates(regen_snapshot),
        now=moment,
        provider_odds=regen_provider_odds,
    )
    try:
        result_id = _save_draft(
            session,
            run_id=run_id,
            draft=draft,
            mode=run_mode,
            actor_id=actor_id,
            now=moment,
        )
    except Exception:
        session.rollback()
        raise
    # 방금 저장된 결과 행을 **지금** 읽는다. 구성본 복사와 응답 메타데이터가 같은 행을
    # 근거로 삼아야 "이 실행이 다시 만든 결과"와 값이 어긋나지 않는다. 이 조회가 없으면
    # 아래 구성본 블록이 아직 없는 변수를 읽거나, 앞 선택 항목의 `row`(다른 결과)를 쓴다.
    saved_row = store.get_section_result(session, run_id, result_id)
    saved_quality = (
        QualityStatus(saved_row.quality) if saved_row is not None else draft.quality
    )
    saved_unavailable = (
        saved_row.unavailable_reason
        if saved_row is not None
        else draft.unavailable_reason
    )
    saved_version = saved_row.version if saved_row is not None else None
    if draft.delivery is not None:
        store.save_information_bundle(
            session,
            run_id=run_id,
            bundle=bundle.with_section_delivery(draft.delivery),
            actor_id=actor_id,
            now=moment,
        )
    # 이 실행이 **쓴 구성본**을 새 run에도 남긴다. 그래야 그 run의 독자 preview가 "선택한
    # 모듈 본문 + 이 run의 새 결론"을 함께 보여준다(부모 구성본만 가리키면 다른 run의
    # 결과라 선택이 비고, 최신 버전이 섞인다). 선택 ID와 버전은 **그대로 복사**하며
    # 값을 바꾸지 않는다. 이 run이 만든 새 결론만 이 run 소유 결과로 덧붙인다.
    if upstream_items:
        # 이 실행이 다시 만든 섹션은 **이 run의 새 결과**로 바꾸고, 나머지 섹션의 선택
        # 버전은 그대로 둔다. 그래야 독자 preview가 "선택한 모듈 본문 + 새 결론"이면서
        # 옛 결론이 중복으로 실리지 않는다.
        copied_items: list[dict[str, Any]] = []
        replaced = False
        for item in upstream_items:
            if str(item.get("section_id")) == section_id:
                copied_items.append(
                    {
                        **dict(item),
                        "result_id": str(result_id),
                        "run_id": str(run_id),
                        "version": saved_version,
                        "quality": saved_quality.value,
                        "unavailable": saved_unavailable is not None,
                        "unavailable_reason": saved_unavailable,
                        "body_chars": len(draft.body or ""),
                        "replaced_by_regeneration": True,
                    }
                )
                replaced = True
            else:
                copied_items.append(dict(item))
        if not replaced:
            copied_items.append(
                {
                    "section_id": section_id,
                    "result_id": str(result_id),
                    "run_id": str(run_id),
                    "fixture_id": fixture_row.fixture_id,
                    "version": saved_version,
                    "quality": saved_quality.value,
                    "unavailable": saved_unavailable is not None,
                    "unavailable_reason": saved_unavailable,
                    "body_chars": len(draft.body or ""),
                    "replaced_by_regeneration": True,
                }
            )
        copied = {
            "composition_id": f"cmp-{uuid.uuid4().hex[:12]}",
            "fixture_id": fixture_row.fixture_id,
            "selected_result_ids": [str(item["result_id"]) for item in copied_items],
            "items": copied_items,
            "refused": [dict(item) for item in upstream_refused],
            "diagnostics": [
                f"부모 실행 {base_run_id}의 구성본을 복사해 이 실행에 기록했습니다."
            ],
            "section_result_ids": [str(item["result_id"]) for item in copied_items],
            "copied_from_composition_id": (
                str(stored_composition.get("composition_id"))
                if stored_composition
                else None
            ),
            "created_at": moment.isoformat(),
        }
        store.save_composition(
            session,
            run_id=run_id,
            composition=copied,
            actor_id=actor_id,
            now=moment,
        )
        diagnostics.append(
            f"이 실행에도 구성본을 기록했습니다({copied['composition_id']}): 선택 결과"
            f" {len(upstream_items)}건 + 이 실행의 새 결론."
        )
    diagnostics.extend(str(item) for item in draft.diagnostics)

    # 응답·실행 상태도 **저장된 행**을 근거로 쓴다. 초안 값만 쓰면 본문이 비어 저장
    # 단계에서 `unavailable`로 바뀐 경우(=_save_draft의 보정) 응답이 저장행과 어긋나
    # 관리자가 화면에서 본 값과 저장본이 달라진다.
    quality = saved_quality
    unavailable = saved_unavailable
    store.finish_run(
        session,
        run_id,
        status=RunStatus.SUCCEEDED if not unavailable else RunStatus.FAILED,
        quality=quality,
        failure_detail=unavailable,
        actor_id=actor_id,
    )
    session.commit()
    row = store.get_section_result(session, run_id, result_id)

    return SectionRegenerationOutcome(
        run_id=run_id,
        section_id=section_id,
        mode=run_mode,
        quality=quality,
        section_result_id=result_id,
        section_result_version=row.version if row is not None else saved_version,
        source_mode=source_mode,
        bundle_id=bundle.bundle_id,
        bundle_reused=source_mode == "reuse",
        bundle_refreshed=refreshed,
        external_calls=int(budget.model_used),
        # **계획상** 모델 모듈 수. `budget.model_used`(external_calls)는 실제 전송 수이며
        # 재시도를 포함하므로 둘은 다른 값이다.
        #
        # 이전에는 `(0 if section_odds else 1)`로 고정했다. 그래서 배당 **refresh**가 조사
        # 모듈(`discovery_outlook`)을 실제로 1회 부르는데도 기대값이 0으로 나가고,
        # `preview_admin`의 `no_model_call = (expected_model_calls == 0)`이 true가 되어
        # 화면이 "모델 0회"로 표시했다(사용자 화면 결함 W-3). 계획은 이미 첫 전송 전에
        # `participating_module_ids`로 확정돼 있으므로 그 길이를 그대로 쓴다.
        # 배당 reuse는 계획이 빈 튜플이라 0이 유지되고, 다른 섹션의 기대값도 같은 계획을
        # 참조한다(새 계산 체계·새 모듈·새 예산을 만들지 않는다).
        expected_model_calls=len(participating_module_ids),
        unavailable_reason=unavailable,
        diagnostics=tuple(diagnostics),
        other_sections_untouched=True,
        base_run_id=base_run_id,
        base_result_id=base_result_id,
        composition_id=(
            str(stored_composition.get("composition_id"))
            if stored_composition and upstream
            else None
        ),
    )
