"""구현된 섹션 워크플로우의 실제 노드 묶음.

이 파일은 "구현이 실제로 있는 섹션"만 만든다. 지금은 `section_form`(경기력·주목 선수)
하나다. R2/R3/S1은 구현이 없으므로 여기서 만들지 않는다. 없는 구현을 흉내 내어 본문을
만들지 않는다.

구성:

| 노드 | 하는 일 | 외부 호출 |
|---|---|---|
| `prepare_data` | 저장된 경기·순위·부상 자료를 읽기 전용으로 재사용해 공유 사실과 스냅샷을 만든다 | 저장 DB 읽기만. 외부 API 호출 없음 |
| `research` | R1 정상 모델 호출 1회(Google Search grounding) | 모델 1회 |
| `compose_body` | 검증된 조사 결과로 독자용 본문을 결정적으로 조립한다 | 없음 |

자료 경계(AGENTS.md 개발·테스트 DB 기준): 기존 경기·순위·부상 행은 **읽기 전용**으로만
읽는다. 쓰기는 `preview_dev`의 실행·스냅샷·결과 행뿐이다. 저장 자료를 읽지 못하면 빈
사실로 진행하되 그 사실을 진단에 남기고, 검색 근거만으로 결과를 만든다.
"""

from __future__ import annotations

import json

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from app.preview import artifacts as artifact_store
from app.preview import version_manifest
from app.preview import provider, store
from app.preview.contracts import (
    CONTRACT_VERSION,
    CoverageEntry,
    CoverageState,
    FixtureIdentity,
    ModuleInput,
    ModuleResult,
    ModuleStatus,
    SourceKind,
    ValidationStatus,
    compute_input_hash,
)
from app.preview.modules import compose, form
from app.preview.runner import (
    COMPOSE_MODULE_ID,
    DATA_MODULE_ID,
    NodeImplementation,
    NodeOutcome,
    SectionNodeContext,
    SectionState,
    WorkflowImplementations,
)
from app.preview.registry import get_section_workflow

__all__ = [
    "FORM_SECTION_ID",
    "revalidate_section_from_stored_response",
    "StoredContext",
    "build_implementations",
    "implemented_section_ids",
    "read_stored_context",
    "recompose_section_body",
]

FORM_SECTION_ID = "section_form"

# R1 본문 조립 구현 버전. 내부 근거 ID(`[api:…]`)를 독자용 문장에서 지우도록
# 조립 규칙이 바뀌었으므로 버전을 올린다. 산출 문장이 달라지는 변경이다.
FORM_COMPOSE_IMPLEMENTATION_VERSION = "mp05-compose-2"

# 공유 자료 준비(D0) 노드 구현 버전. 저장 자료만 읽고 외부 호출이 없다.
STORED_DATA_IMPLEMENTATION_VERSION = "mp05-stored-d0-1"

# R3 본문 조립 구현 버전. 아웃룩 조립기는 모듈 쪽에 있고, sections는 노드 어댑터만 준다.
OUTLOOK_COMPOSE_IMPLEMENTATION_VERSION = "mp07-outlook-compose-1"

# 이 파일이 실제 노드를 제공하는 섹션. 등록부의 implemented와 별개로 여기서 정한다.
_IMPLEMENTED_SECTIONS = (
    FORM_SECTION_ID,
    "section_availability",
    "section_outlook",
    "section_players",
    "section_synthesis",
)

# 저장 자료 출처 표기. 실제 API 호출이 아니라 읽기 전용 재사용임을 드러낸다.
STORED_PROVIDER = "api-football-stored"

# 재검증 결과의 provenance 종류. 새 모델 호출이 아니라 저장 원문의 재해석임을 뜻한다.
REVALIDATION_PROVENANCE_KIND = "revalidated_from_stored_response"


def implemented_section_ids() -> tuple[str, ...]:
    return _IMPLEMENTED_SECTIONS


@dataclass(frozen=True)
class StoredContext:
    """저장 자료에서 만든 공유 사실 묶음. 수집 시각과 경기 식별자를 함께 둔다."""

    facts: form.FormFacts
    snapshot_ids: tuple[str, ...]
    coverage: tuple[CoverageEntry, ...]
    diagnostics: tuple[str, ...]
    note: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fixture_identity(fixture: Mapping[str, Any] | None) -> FixtureIdentity | None:
    if not fixture:
        return None
    try:
        return FixtureIdentity.from_dict(dict(fixture))
    except (KeyError, TypeError, ValueError):
        return None


def _standings_facts(
    rows: Sequence[Mapping[str, Any]],
    *,
    team_ids: dict[int, str],
) -> list[tuple[str, str, int]]:
    """순위 행에서 팀별 사실 문장을 만든다. 없는 값은 건너뛴다."""
    found: list[tuple[str, str, int]] = []
    for row in rows:
        try:
            team_id = int(row["team_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if team_id not in team_ids:
            continue
        name = team_ids[team_id]
        rank = row.get("rank")
        points = row.get("points")
        played = row.get("played")
        wins = row.get("win")
        draws = row.get("draw")
        losses = row.get("loss")
        form_text = row.get("form")
        parts: list[str] = []
        if played is not None and wins is not None and draws is not None and losses is not None:
            parts.append(f"{played}경기 {wins}승 {draws}무 {losses}패")
        if points is not None:
            parts.append(f"승점 {points}")
        if rank is not None:
            parts.append(f"리그 {rank}위")
        sentence = f"{name}는 " + ", ".join(parts) + "입니다." if parts else ""
        if form_text:
            sentence = (
                f"{sentence} 최근 5경기 폼은 {form_text}입니다."
                if sentence
                else f"{name}의 최근 5경기 폼은 {form_text}입니다."
            )
        if sentence:
            found.append((f"api:standings-{team_id}", sentence, team_id))
    return found


def read_stored_context(
    session,
    *,
    fixture: Mapping[str, Any] | None,
    reader,
    run_id: uuid.UUID,
    actor_id: int,
    now: datetime | None = None,
) -> StoredContext:
    """저장된 경기·순위·부상 자료를 읽기 전용으로 재사용한다.

    외부 API를 호출하지 않는다. 읽지 못한 자료는 `NOT_RUN`/`API_NOT_PROVIDED`로 남기고
    빈 사실을 만들지 않는다.
    """
    moment = now or _now()
    identity = _fixture_identity(fixture)
    if identity is None:
        return StoredContext(
            facts=form.FormFacts(
                fixture_id=0,
                league_id=0,
                season=0,
                home_team_id=0,
                away_team_id=0,
                kickoff_at=moment,
                home_team="홈팀",
                away_team="원정팀",
                league=None,
            ),
            snapshot_ids=(),
            coverage=(
                CoverageEntry(
                    topic="경기 식별",
                    state=CoverageState.API_NOT_PROVIDED,
                    detail="경기 식별자가 없어 저장 자료를 읽지 않았습니다.",
                ),
            ),
            diagnostics=("경기 식별자가 없어 공유 자료 준비를 건너뛰었습니다.",),
        )

    home_name = f"team {identity.home_team_id}"
    away_name = f"team {identity.away_team_id}"
    league_name: str | None = None
    stored_fixture = None
    diagnostics: list[str] = []
    coverage: list[CoverageEntry] = []

    if reader is not None:
        try:
            stored_fixture = reader.get_fixture(fixture_id=identity.fixture_id)
        except Exception as exc:  # noqa: BLE001 - 읽기 실패를 사실로 바꾸지 않는다
            diagnostics.append(f"저장된 경기 자료를 읽지 못했습니다: {exc}")
            coverage.append(
                CoverageEntry(
                    topic="경기 식별",
                    state=CoverageState.CALL_ERROR,
                    detail=str(exc),
                )
            )
    else:
        coverage.append(
            CoverageEntry(
                topic="경기 식별",
                state=CoverageState.NOT_RUN,
                detail="저장 경기 자료 읽기 연결이 설정되지 않았습니다.",
            )
        )

    if stored_fixture is not None:
        home_name = stored_fixture.home_team_name or home_name
        away_name = stored_fixture.away_team_name or away_name
        league_name = stored_fixture.league_name
        coverage.append(
            CoverageEntry(
                topic="경기 식별",
                state=CoverageState.AVAILABLE,
                detail=f"{stored_fixture.label} · 킥오프 {stored_fixture.kickoff_at.isoformat()}",
            )
        )

    fact_rows: list[tuple[str, str, int | None]] = []
    team_ids = {identity.home_team_id: home_name, identity.away_team_id: away_name}

    standings_rows: Sequence[Mapping[str, Any]] = ()
    if reader is not None:
        try:
            standings_rows = reader.standings_for_league(
                league_id=identity.league_id, season=identity.season
            )
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(f"저장된 순위 자료를 읽지 못했습니다: {exc}")
            coverage.append(
                CoverageEntry(
                    topic="리그 순위",
                    state=CoverageState.CALL_ERROR,
                    detail=str(exc),
                )
            )
    for fact_id, text, team_id in _standings_facts(standings_rows, team_ids=team_ids):
        fact_rows.append((fact_id, text, team_id))
    coverage.append(
        CoverageEntry(
            topic="리그 순위",
            state=CoverageState.AVAILABLE if standings_rows else CoverageState.NOT_RUN,
            detail=(
                f"저장된 순위 {len(standings_rows)}행을 읽었습니다."
                if standings_rows
                else "저장된 순위 자료가 없습니다."
            ),
        )
    )

    injury_rows: Sequence[Any] = ()
    if reader is not None:
        try:
            injury_rows = reader.injuries_for_fixture(identity.fixture_id)
        except Exception as exc:  # noqa: BLE001
            diagnostics.append(f"저장된 부상 자료를 읽지 못했습니다: {exc}")
    if injury_rows:
        # 빈 결과를 '부상자 없음'으로 단정하지 않는다. 있는 행만 사실로 적는다.
        markers = ", ".join(
            sorted({str(getattr(row, "type_marker", "") or "표기 없음") for row in injury_rows})
        )
        fact_rows.append(
            (
                "api:injury-count",
                f"저장된 부상·출전 불확실 행 {len(injury_rows)}건이 있습니다(표기: {markers}).",
                None,
            )
        )
        coverage.append(
            CoverageEntry(
                topic="부상·출전 불확실",
                state=CoverageState.AVAILABLE,
                detail=f"{len(injury_rows)}건(표기 보존, 결장 확정으로 승격하지 않음)",
            )
        )
    else:
        coverage.append(
            CoverageEntry(
                topic="부상·출전 불확실",
                state=CoverageState.UNKNOWN,
                detail=(
                    "저장된 부상 행이 없습니다. 이것은 '부상자 없음'의 증거가"
                    " 아닙니다."
                ),
            )
        )

    if not fact_rows:
        diagnostics.append(
            "저장 자료에서 채택할 구조화 사실을 얻지 못했습니다. 검색 근거만 사용합니다."
        )
        return StoredContext(
            facts=form.FormFacts(
                fixture_id=identity.fixture_id,
                league_id=identity.league_id,
                season=identity.season,
                home_team_id=identity.home_team_id,
                away_team_id=identity.away_team_id,
                kickoff_at=identity.kickoff_at,
                home_team=home_name,
                away_team=away_name,
                league=league_name,
                facts=(),
                snapshot_ids=(),
                collected_at=moment,
                source_note="저장 자료에서 사실을 얻지 못했습니다.",
            ),
            snapshot_ids=(),
            coverage=tuple(coverage),
            diagnostics=tuple(diagnostics),
        )

    # 사실 묶음을 한 스냅샷으로 남긴다. 스냅샷 ID가 다음 단계까지 이어진다.
    payload_rows = [
        {"fact_id": fact_id, "text": text, "subject_team_id": team_id}
        for fact_id, text, team_id in fact_rows
    ]
    artifact = artifact_store.save_artifact(
        session,
        run_id=run_id,
        kind=artifact_store.ArtifactKind.RAW_RESPONSE,
        content={
            "source": "stored_read_only_db",
            "note": (
                "기존 DB에서 읽기 전용으로 재사용한 경기·순위·부상 자료입니다."
                " 새 외부 API 호출이 아닙니다."
            ),
            "fixture": identity.to_dict(),
            "facts": payload_rows,
        },
        actor_id=actor_id,
        now=moment,
    )
    snapshot = store.record_source_snapshot(
        session,
        run_id=run_id,
        source_kind=SourceKind.API,
        provider=STORED_PROVIDER,
        collected_at=moment,
        validation_status=ValidationStatus.VERIFIED,
        fixture=identity,
        artifact_id=artifact.id,
        note=(
            "저장된 API-Football 자료를 읽기 전용으로 재사용했습니다."
            " 이 실행에서 새 API 요청을 보내지 않았습니다."
        ),
        actor_id=actor_id,
    )
    snapshot_id = str(snapshot.id)
    facts = tuple(
        form.Fact(
            fact_id=fact_id,
            text=text,
            snapshot_id=snapshot_id,
            collected_at=moment,
            subject_team_id=team_id,
        )
        for fact_id, text, team_id in fact_rows
    )
    return StoredContext(
        facts=form.FormFacts(
            fixture_id=identity.fixture_id,
            league_id=identity.league_id,
            season=identity.season,
            home_team_id=identity.home_team_id,
            away_team_id=identity.away_team_id,
            kickoff_at=identity.kickoff_at,
            home_team=home_name,
            away_team=away_name,
            league=league_name,
            facts=facts,
            snapshot_ids=(snapshot_id,),
            collected_at=moment,
        ),
        snapshot_ids=(snapshot_id,),
        coverage=tuple(coverage),
        diagnostics=tuple(diagnostics),
    )


def _compose_node(now: datetime | None = None):
    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        research_payload = (state.get("research") or {}).get("R1") or {}
        if not research_payload:
            return NodeOutcome(
                title=compose.FORM_SECTION_TITLE,
                unavailable_reason=(
                    "경기력 조사 결과가 없어 섹션 본문을 만들지 않았습니다."
                ),
            )
        composed = compose.compose_form_body(research_payload)
        return NodeOutcome(
            title=composed.title,
            body=composed.body,
            # 검색 출처는 조사 노드가 이미 넘겼다. 여기서는 API 자료 출처만 더한다.
            sources=tuple(
                row for row in composed.sources if row.get("kind") == "api"
            ),
            quality=composed.quality,
            unavailable_reason=composed.unavailable_reason,
        )

    return run


def _prepare_node(
    *,
    reader,
    now: datetime | None = None,
):
    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        moment = now or _now()
        stored = read_stored_context(
            ctx.session,
            fixture=state.get("fixture") or ctx.fixture,
            reader=reader,
            run_id=ctx.context.run_id,
            actor_id=ctx.actor_id,
            now=moment,
        )
        return NodeOutcome(
            payload={
                "facts": [fact.to_dict() for fact in stored.facts.facts],
                "fixture": {
                    "fixture_id": stored.facts.fixture_id,
                    "league_id": stored.facts.league_id,
                    "season": stored.facts.season,
                    "home_team_id": stored.facts.home_team_id,
                    "away_team_id": stored.facts.away_team_id,
                    "kickoff_at": stored.facts.kickoff_at.isoformat(),
                    "home_team": stored.facts.home_team,
                    "away_team": stored.facts.away_team,
                    "league": stored.facts.league,
                },
                "snapshot_ids": list(stored.snapshot_ids),
                "coverage": [entry.to_dict() for entry in stored.coverage],
                "claims": [],
            },
            diagnostics=stored.diagnostics,
            # 저장 자료 재사용은 외부 호출이 아니다.
            external_calls=0,
        )

    return run


def _facts_from_state(
    state: SectionState, *, now: datetime | None = None
) -> form.FormFacts:
    """`prepare_data`가 남긴 payload에서 R1 입력을 복원한다."""
    data = state.get("data") or {}
    raw_fixture = data.get("fixture") or state.get("fixture") or {}
    kickoff_raw = raw_fixture.get("kickoff_at")
    kickoff = _now() if now is None else now
    if isinstance(kickoff_raw, str) and kickoff_raw:
        from datetime import datetime as _dt

        try:
            kickoff = _dt.fromisoformat(kickoff_raw.replace("Z", "+00:00"))
        except ValueError:
            kickoff = now or _now()
    facts = tuple(
        form.Fact(
            fact_id=str(item.get("fact_id")),
            text=str(item.get("text") or ""),
            snapshot_id=str(item.get("snapshot_id") or ""),
            collected_at=(
                datetime.fromisoformat(str(item["collected_at"]).replace("Z", "+00:00"))
                if item.get("collected_at")
                else None
            ),
            subject_team_id=item.get("subject_team_id"),
        )
        for item in data.get("facts") or ()
        if isinstance(item, Mapping)
    )
    return form.FormFacts(
        fixture_id=int(raw_fixture.get("fixture_id") or 0),
        league_id=int(raw_fixture.get("league_id") or 0),
        season=int(raw_fixture.get("season") or 0),
        home_team_id=int(raw_fixture.get("home_team_id") or 0),
        away_team_id=int(raw_fixture.get("away_team_id") or 0),
        kickoff_at=kickoff,
        home_team=str(raw_fixture.get("home_team") or "홈팀"),
        away_team=str(raw_fixture.get("away_team") or "원정팀"),
        league=raw_fixture.get("league"),
        facts=facts,
        snapshot_ids=tuple(str(sid) for sid in data.get("snapshot_ids") or ()),
        collected_at=now,
    )


def _research_node(
    *,
    transport: provider.ProviderTransport,
    now: datetime | None = None,
) -> NodeImplementation:
    """R1 노드. `prepare_data`가 만든 사실을 입력으로 쓴다."""
    from app.preview.runner import NodeOutcome as _Outcome

    def adapt(facts: form.FormFacts) -> Callable[[SectionNodeContext, SectionState], _Outcome]:
        return form.form_node(facts=facts, transport=transport, now=now)

    def run(ctx: SectionNodeContext, state: SectionState) -> _Outcome:
        return adapt(_facts_from_state(state, now=now))(ctx, state)

    return NodeImplementation(
        module_id="R1",
        implementation_version=form.FORM_IMPLEMENTATION_VERSION,
        prompt_version=form.FORM_PROMPT_VERSION,
        mode=transport.mode,
        run=run,
    )


def _prepare_implementation(*, transport, reader, now: datetime | None) -> NodeImplementation:
    return NodeImplementation(
        module_id=DATA_MODULE_ID,
        implementation_version="mp05-stored-d0-1",
        prompt_version=None,
        mode=transport.mode,
        run=_prepare_node(reader=reader, now=now),
    )


def build_implementations(
    workflow_id: str,
    *,
    transport: provider.ProviderTransport,
    reader=None,
    now: datetime | None = None,
) -> WorkflowImplementations:
    """구현이 실제로 있는 섹션의 노드 묶음을 만든다.

    지금 실제 노드가 있는 섹션은 `section_form`·`section_availability`·
    `section_outlook` 셋이다. 그 밖의 섹션은 KeyError로 거부한다(없는 구현을 흉내 내지
    않는다). 모의 시연이 필요하면 `runner.mock_section_implementations`를 쓴다.
    """
    get_section_workflow(workflow_id)  # 등록되지 않은 ID는 KeyError로 거부한다.
    if workflow_id == FORM_SECTION_ID:
        return WorkflowImplementations(
            prepare_data=_prepare_implementation(transport=transport, reader=reader, now=now),
            research=(_research_node(transport=transport, now=now),),
            compose_body=NodeImplementation(
                module_id=COMPOSE_MODULE_ID,
                implementation_version=FORM_COMPOSE_IMPLEMENTATION_VERSION,
                prompt_version=None,
                mode=transport.mode,
                run=_compose_node(now=now),
            ),
        )

    if workflow_id == "section_players":
        from app.preview.modules import players as players_module

        prepare = _prepare_implementation(transport=transport, reader=reader, now=now)
        # R4는 이름 해석기를 **주입받아** 쓴다(자체 조회·번역 없음). 해석기가 없으면
        # 저장된 원래 표기를 그대로 쓴다.
        return players_module.build_players_implementations(
            prepare_data=prepare,
            transport=transport,
            resolver=_name_resolver(reader=reader),
            material=None,
            roster=(),
            id_space="internal",
            now=now,
        )

    if workflow_id == "section_availability":
        from app.preview.modules import availability as availability_module

        prepare = _prepare_implementation(transport=transport, reader=reader, now=now)
        return availability_module.build_availability_implementations(
            prepare_data=prepare,
            transport=transport,
            reader=reader,
            now=now,
        )

    if workflow_id == "section_synthesis":
        from app.preview.modules import synthesis as synthesis_module

        # 합성 섹션은 새 자료 수집(D0) 대신 **선택된 결과 읽기·검증** 노드를 쓴다.
        return synthesis_module.build_synthesis_implementations(
            transport=transport, reader=reader, now=now
        )

    if workflow_id == "section_outlook":
        from app.preview.modules import outlook as outlook_module

        prepare = _prepare_implementation(transport=transport, reader=reader, now=now)
        composed = outlook_module.compose_outlook_section
        return WorkflowImplementations(
            prepare_data=prepare,
            research=(
                outlook_module.outlook_node_implementation(
                    mode=transport.mode, transport=transport
                ),
            ),
            compose_body=NodeImplementation(
                module_id=COMPOSE_MODULE_ID,
                implementation_version=OUTLOOK_COMPOSE_IMPLEMENTATION_VERSION,
                prompt_version=None,
                mode=transport.mode,
                run=_outlook_compose_node(composed),
            ),
        )

    raise KeyError(f"section workflow {workflow_id!r} has no implemented nodes yet")


def _outlook_compose_node(composed_fn):
    """R3 본문 조립 노드.

    R3 조사 노드가 이미 근거(sources)를 넘겼으므로, 본문 조립 노드는 **근거를 다시
    넘기지 않는다**. 같은 근거를 두 번 붙이면 화면에 중복으로 나온다.
    """

    def run(ctx: SectionNodeContext, state: SectionState) -> NodeOutcome:
        payload = (state.get("research") or {}).get("R3") or {}
        if not payload:
            return NodeOutcome(
                unavailable_reason="배당·전망 조사 결과가 없어 섹션 본문을 만들지 않았습니다."
            )
        composed = composed_fn(payload)
        body = getattr(composed, "body", "") or ""
        return NodeOutcome(
            title=getattr(composed, "title", None),
            body=body,
            sources=(),
            quality=getattr(composed, "quality", None),
            unavailable_reason=getattr(composed, "unavailable_reason", None),
        )

    return run


def recompose_section_body(
    session,
    *,
    run_id: uuid.UUID,
    actor_id: int = 0,
    now: datetime | None = None,
):
    """저장된 조사 결과로 섹션 본문을 **다시 조립**한다. 외부 호출은 0회다.

    본문 조립 규칙(문장 다듬기)만 바뀐 경우에 쓴다. 새 조사·새 모델 호출이 아니며,
    저장된 채택 근거를 그대로 입력으로 쓴다. 그래서 근거에 없는 문장이 새로 생기지
    않는다. 이전 섹션 결과는 지우지 않고 새 버전으로 올린다.
    """
    from sqlalchemy import select

    from app.preview.contracts import (
        SECTION_RESULT_CONTRACT_VERSION,
        Environment,
        QualityStatus,
        RunMode,
    )
    from app.preview.models import PreviewResult, PreviewSectionResult

    moment = now or _now()
    run = store.get_run_detail(session, run_id)
    if not run.section_results:
        raise ValueError(f"run {run_id} has no stored section result to recompose")

    latest_section = run.section_results[-1]
    workflow_id = latest_section["workflow_id"]
    if workflow_id != FORM_SECTION_ID:
        raise ValueError(f"recompose is only implemented for {FORM_SECTION_ID}")

    rows = session.scalars(
        select(PreviewResult).where(
            PreviewResult.run_id == run_id, PreviewResult.module_id == "R1"
        ).order_by(PreviewResult.version.desc())
    ).all()
    if not rows:
        raise ValueError(f"run {run_id} has no stored R1 result")
    # 저장된 결과는 `ModuleResult.to_dict()`이므로 실제 조사 payload는 `payload` 키 안에
    # 있다. 그 값을 그대로 본문 조립 입력으로 쓴다.
    stored = dict(rows[0].payload or {})
    inner = stored.get("payload")
    payload = dict(inner) if isinstance(inner, Mapping) else stored
    composed = compose.compose_form_body(payload)
    if not composed.body:
        raise ValueError("stored research did not yield a body; leaving result untouched")

    next_version = int(latest_section["version"]) + 1
    row = store.save_section_result(
        session,
        run_id=run_id,
        workflow_id=workflow_id,
        workflow_version=latest_section["workflow_version"],
        title=composed.title,
        body=composed.body,
        version=next_version,
        mode=RunMode(latest_section["mode"]),
        environment=Environment(latest_section["environment"]),
        quality=composed.quality,
        output_contract_version=latest_section["output_contract_version"],
        contract_version=SECTION_RESULT_CONTRACT_VERSION,
        sources=composed.sources,
        module_execution_ids=[uuid.UUID(x) for x in latest_section["module_execution_ids"]],
        result_ids=[uuid.UUID(x) for x in latest_section["result_ids"]],
        diagnostics=(
            "본문 조립 규칙만 다시 적용했습니다(외부 호출 0회). 저장된 조사·검증 결과를"
            " 그대로 입력으로 썼고 새 근거를 추가하지 않았습니다."
            f" 조립 구현 버전: {FORM_COMPOSE_IMPLEMENTATION_VERSION}.",
        ),
        actor_id=actor_id,
        now=moment,
    )
    return row, composed


def revalidate_section_from_stored_response(
    session,
    *,
    run_id: uuid.UUID,
    actor_id: int = 0,
    now: datetime | None = None,
):
    """저장된 원문 응답을 **새 검증 규칙으로 다시 해석**하고 본문 버전을 추가한다.

    외부 호출은 0회다. 원문 응답·이전 섹션 결과·승인은 건드리지 않고 새 버전만 올린다.

    `recompose_section_body`와의 차이: 그쪽은 **이미 검증된** 조사 결과로 본문만 다시
    조립한다. 이쪽은 검증 규칙 자체가 바뀌었을 때(사실/판단 경계 조정) 저장 원문을
    다시 해석하므로, 이전 실행에서 부당하게 버려진 판단 항목이 되살아날 수 있다.
    새 사실을 만들지는 않는다(원문·같은 facts만 쓴다).

    반환: (새 섹션 결과 행, 새 검증 결과, 조립 결과)
    """
    from sqlalchemy import select

    from app.preview.contracts import (
        SECTION_RESULT_CONTRACT_VERSION,
        Environment,
        QualityStatus,
        RunMode,
    )
    from app.preview.models import PreviewArtifact, PreviewAttempt, PreviewResult, PreviewSourceSnapshot

    moment = now or _now()
    run = store.get_run_detail(session, run_id)
    if not run.section_results:
        raise ValueError(f"run {run_id} has no stored section result to revalidate")

    latest_section = run.section_results[-1]
    if latest_section["workflow_id"] != FORM_SECTION_ID:
        raise ValueError(f"revalidate is only implemented for {FORM_SECTION_ID}")

    # 1) 저장된 R1 원문 응답을 찾는다(재호출 없음).
    attempt = session.scalars(
        select(PreviewAttempt)
        .where(PreviewAttempt.run_id == run_id, PreviewAttempt.module_id == "R1")
        .order_by(PreviewAttempt.attempt_ordinal.desc())
    ).first()
    if attempt is None or attempt.response_artifact_id is None:
        raise ValueError(f"run {run_id} has no stored R1 response artifact")
    artifact = session.get(PreviewArtifact, attempt.response_artifact_id)
    if artifact is None or not artifact.body:
        raise ValueError("stored R1 response artifact is missing or expired")
    raw = json.loads(artifact.body)

    # 2) 그 실행이 쓴 D0 사실을 그대로 복원한다(새 자료 수집 없음).
    d0_rows = session.scalars(
        select(PreviewResult)
        .where(PreviewResult.run_id == run_id, PreviewResult.module_id == DATA_MODULE_ID)
        .order_by(PreviewResult.version.desc())
    ).all()
    if not d0_rows:
        raise ValueError(f"run {run_id} has no stored D0 result")
    stored_d0 = dict(d0_rows[0].payload or {})
    d0_inner = stored_d0.get("payload")
    d0_payload = dict(d0_inner) if isinstance(d0_inner, Mapping) else stored_d0

    fixture = d0_payload.get("fixture") or {}
    facts = form.FormFacts(
        fixture_id=int(fixture.get("fixture_id") or 0),
        league_id=int(fixture.get("league_id") or 0),
        season=int(fixture.get("season") or 0),
        home_team_id=int(fixture.get("home_team_id") or 0),
        away_team_id=int(fixture.get("away_team_id") or 0),
        kickoff_at=_parse_iso(fixture.get("kickoff_at")) or moment,
        home_team=str(fixture.get("home_team") or "홈팀"),
        away_team=str(fixture.get("away_team") or "원정팀"),
        league=fixture.get("league"),
        facts=tuple(
            form.Fact(
                fact_id=str(item.get("fact_id")),
                text=str(item.get("text") or ""),
                snapshot_id=str(item.get("snapshot_id") or ""),
                collected_at=_parse_iso(item.get("collected_at")),
                subject_team_id=item.get("subject_team_id"),
            )
            for item in d0_payload.get("facts") or ()
            if isinstance(item, Mapping)
        ),
    )

    # 3) 같은 원문·같은 facts로 **새 검증 규칙**을 적용한다.
    grounding = form.parse_grounding(raw)
    try:
        model_payload = form.parse_model_json(provider.extract_text(raw) or "")
    except form.FormResearchError as exc:
        raise ValueError(f"stored response is not valid JSON any more: {exc}") from None
    validated = form.validate_response(model_payload, facts=facts, grounding=grounding, now=moment)

    api_claims = form._api_fact_claims(facts)
    claims = tuple(api_claims) + tuple(validated.claims)
    importance = None
    match_ctx = model_payload.get("match_context")
    if isinstance(match_ctx, Mapping):
        importance_text = str(match_ctx.get("importance") or "").strip()
        importance = importance_text or None
    no_evidence = not validated.watch_points and not validated.recent_form and not validated.hot_players
    research = form.FormResearch(
        facts=facts,
        claims=claims,
        coverage=tuple(validated.coverage),
        diagnostics=tuple(validated.diagnostics),
        uncertainties=tuple(validated.uncertainties),
        watch_points=tuple(validated.watch_points),
        hot_players=tuple(validated.hot_players),
        recent_form=tuple(validated.recent_form),
        match_importance=importance,
        sources=form._result_sources(grounding),
        grounding=grounding,
        search_note=model_payload.get("search_note") if isinstance(model_payload.get("search_note"), str) else None,
        unavailable_reason=(
            "채택할 근거를 확보하지 못해 이 섹션의 본문을 만들지 않았습니다." if no_evidence else None
        ),
        quality=QualityStatus.PENDING if no_evidence else QualityStatus.READY,
        external_calls=0,
        implementation_version=form.FORM_IMPLEMENTATION_VERSION,
        prompt_version=form.FORM_PROMPT_VERSION,
    )

    payload_for_body = dict(research.payload())
    payload_for_body["claims"] = [claim.to_dict() for claim in research.claims]
    payload_for_body["coverage"] = [entry.to_dict() for entry in research.coverage]
    # API 출처 표시는 저장 D0 결과에서 그대로 가져온다.
    if not payload_for_body.get("api_sources"):
        payload_for_body["api_sources"] = list(d0_payload.get("api_sources") or ())
    composed = compose.compose_form_body(payload_for_body)
    if not composed.body:
        raise ValueError("stored response did not yield a body under the new rules")

    # 4) 재검증이 만든 검증 결과를 **새 버전 행**으로 남긴다. 진단(덜어낸 사실·사유)을
    # 메모리에만 두면 실행 기록에서 "무엇을 왜 뺐는지"를 볼 수 없다.
    old_r1 = session.scalars(
        select(PreviewResult)
        .where(PreviewResult.run_id == run_id, PreviewResult.module_id == "R1")
        .order_by(PreviewResult.version.desc())
    ).first()
    # 이 후보를 만든 구성 집합은 **지금 코드**다. 채택/제외 판정과 본문 조립을 현재
    # 구현이 수행했으므로, 승인 화면이 보는 현재 후보와 같은 버전을 가진다. 원문 문장을
    # 만든 옛 프롬프트는 숨기지 않고 R1 결과 행의 `prompt_version`과 provenance에
    # 따로 남긴다(새 프롬프트를 보낸 것처럼 꾸미지 않는다).
    manifest = version_manifest.constituents_for_workflow(latest_section["workflow_id"])
    section_version = version_manifest.workflow_version_of(latest_section["workflow_id"])
    provenance = {
        "kind": REVALIDATION_PROVENANCE_KIND,
        # 원문 응답은 **이 실행이 실제로 받은 것**을 그대로 가리킨다(새 호출 없음).
        "source_artifact_id": str(attempt.response_artifact_id),
        "source_attempt_id": str(attempt.id),
        "source_result_id": str(old_r1.id) if old_r1 is not None else None,
        # 원문을 만든 프롬프트/구현과, 지금 다시 해석한 구현을 분리해 남긴다.
        "source_prompt_version": str(old_r1.prompt_version or "") if old_r1 is not None else "",
        "source_implementation_version": (
            str(old_r1.implementation_version or "") if old_r1 is not None else ""
        ),
        "validated_by_implementation_version": form.FORM_IMPLEMENTATION_VERSION,
        "validated_by_prompt_version": form.FORM_PROMPT_VERSION,
        "external_calls": 0,
        "note": (
            "모델 응답을 새로 받은 것이 아니라, 저장된 원문을 새 검증 규칙으로 다시"
            " 해석한 결과입니다. 문장 생성에 쓰인 프롬프트는 원문을 만든 옛 프롬프트이며,"
            " 여기의 검증 구현 버전과 다릅니다."
        ),
    }
    validation_messages = _revalidation_diagnostics(validated, research)

    r1_execution = store.start_module_execution(
        session,
        run_id=run_id,
        module_id="R1",
        ordinal=_next_execution_ordinal(session, run_id, "R1"),
        module_input=ModuleInput(
            module_id="R1",
            fixture=_fixture_from_payload(d0_payload.get("fixture")),
            snapshot_ids=tuple(
                uuid.UUID(str(item.get("snapshot_id")))
                for item in d0_payload.get("facts") or ()
                if isinstance(item, Mapping) and item.get("snapshot_id")
            ),
            selected_result_ids=(),
            input_hash=compute_input_hash(
                {
                    "module_id": "R1",
                    "run_id": str(run_id),
                    "source_artifact_id": str(attempt.response_artifact_id),
                    "implementation": form.FORM_IMPLEMENTATION_VERSION,
                }
            ),
            # 원문은 옛 프롬프트가 만들었다. 새 프롬프트를 보낸 것처럼 적지 않는다.
            prompt_version=provenance["source_prompt_version"],
            contract_version=CONTRACT_VERSION,
            implementation_version=form.FORM_IMPLEMENTATION_VERSION,
            parameters={"node": "revalidate"},
        ),
        actor_id=actor_id,
    )
    revalidated_result = store.save_module_result(
        session,
        ModuleResult(
            result_id=uuid.uuid4(),
            module_id="R1",
            module_execution_id=r1_execution.id,
            run_id=run_id,
            version=1,
            input_hash=r1_execution.input_hash,
            status=ModuleStatus.SUCCEEDED,
            quality=research.quality,
            claims=tuple(research.claims),
            coverage=tuple(research.coverage),
            diagnostics=tuple(validation_messages),
            implementation_version=form.FORM_IMPLEMENTATION_VERSION,
            prompt_version=provenance["source_prompt_version"],
            contract_version=CONTRACT_VERSION,
            payload={
                "payload": dict(payload_for_body),
                "diagnostics": list(validation_messages),
                "provenance": provenance,
                "manifest": [entry.to_dict() for entry in manifest],
                "workflow_version": section_version,
            },
        ),
        actor_id=actor_id,
    )

    compose_execution = store.start_module_execution(
        session,
        run_id=run_id,
        module_id=COMPOSE_MODULE_ID,
        ordinal=_next_execution_ordinal(session, run_id, COMPOSE_MODULE_ID),
        module_input=ModuleInput(
            module_id=COMPOSE_MODULE_ID,
            fixture=_fixture_from_payload(d0_payload.get("fixture")),
            snapshot_ids=(),
            selected_result_ids=(revalidated_result.id,),
            input_hash=compute_input_hash(
                {
                    "module_id": COMPOSE_MODULE_ID,
                    "body_source": str(revalidated_result.id),
                    "implementation": FORM_COMPOSE_IMPLEMENTATION_VERSION,
                }
            ),
            prompt_version="",
            contract_version=CONTRACT_VERSION,
            implementation_version=FORM_COMPOSE_IMPLEMENTATION_VERSION,
            parameters={"node": "revalidate_compose"},
        ),
        actor_id=actor_id,
    )
    composed_result = store.save_module_result(
        session,
        ModuleResult(
            result_id=uuid.uuid4(),
            module_id=COMPOSE_MODULE_ID,
            module_execution_id=compose_execution.id,
            run_id=run_id,
            version=1,
            input_hash=compose_execution.input_hash,
            status=ModuleStatus.SUCCEEDED,
            quality=composed.quality,
            implementation_version=FORM_COMPOSE_IMPLEMENTATION_VERSION,
            prompt_version="",
            contract_version=CONTRACT_VERSION,
            payload={
                "title": composed.title,
                "body": composed.body,
                "sources": [dict(item) for item in composed.sources],
                "revalidated_from_result_id": str(revalidated_result.id),
                "manifest": [entry.to_dict() for entry in manifest],
                "workflow_version": section_version,
            },
        ),
        actor_id=actor_id,
    )

    next_version = int(latest_section["version"]) + 1
    row = store.save_section_result(
        session,
        run_id=run_id,
        workflow_id=latest_section["workflow_id"],
        # 이 결과는 **지금 코드**로 다시 검증한 후보이므로, 옛 실행이 남긴 버전을
        # 물려받지 않고 현재 구성으로 계산한 버전을 쓴다. 그래야 승인 화면이 보는
        # 후보 버전과 저장된 후보가 같아지고, 옛 결과를 새 코드로 표시하지 않는다.
        workflow_version=section_version,
        title=composed.title,
        body=composed.body,
        version=next_version,
        mode=RunMode(latest_section["mode"]),
        environment=Environment(latest_section["environment"]),
        quality=composed.quality,
        output_contract_version=latest_section["output_contract_version"],
        contract_version=SECTION_RESULT_CONTRACT_VERSION,
        sources=composed.sources,
        # 이 결과를 만든 모듈 결과 행을 정확히 가리킨다. 승인의 구성 근거가 여기서 나온다.
        module_execution_ids=[
            uuid.UUID(x) for x in latest_section["module_execution_ids"]
        ]
        + [r1_execution.id, compose_execution.id],
        result_ids=[uuid.UUID(x) for x in latest_section["result_ids"]]
        + [revalidated_result.id, composed_result.id],
        diagnostics=_section_revalidation_diagnostics(
            validation_messages, form.FORM_IMPLEMENTATION_VERSION
        ),
        actor_id=actor_id,
        now=moment,
    )
    return row, research, composed


def _next_execution_ordinal(session, run_id: uuid.UUID, module_id: str) -> int:
    """같은 실행·모듈의 다음 순번. 재검증도 실행 기록의 순서를 이어 간다."""
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


def _fixture_from_payload(payload: Mapping[str, Any] | None) -> FixtureIdentity | None:
    """저장된 D0 payload의 경기 식별자를 그대로 복원한다. 없는 값은 만들지 않는다."""
    if not isinstance(payload, Mapping) or not payload:
        return None
    try:
        return FixtureIdentity.from_dict(dict(payload))
    except (KeyError, TypeError, ValueError):
        return None


def _revalidation_diagnostics(validated, research) -> tuple[str, ...]:
    """재검증 진단을 **사람이 읽는 전체 문장 목록**으로 만든다.

    `validated.diagnostics`는 제외 사유 문장이고, `dropped_facts`·`unasserted_premises`는
    덜어낸 사실과 내려놓은 전제다. 둘을 합쳐 항목마다 한 문장으로 남긴다. 호출자가
    튜플로 받으므로 `save_section_result`가 글자 단위로 펼치지 않는다.
    """
    messages: list[str] = []

    def add(text: Any) -> None:
        cleaned = str(text or "").strip()
        if cleaned and cleaned not in messages:
            messages.append(cleaned)

    for item in tuple(getattr(validated, "diagnostics", ()) or ()):
        add(item)
    dropped = tuple(getattr(validated, "dropped_facts", ()) or ())
    if dropped:
        add(
            f"확인되지 않은 사실 조각 {len(dropped)}개를 덜어냈습니다: "
            + " / ".join(str(item) for item in dropped)
        )
    premises = tuple(getattr(validated, "unasserted_premises", ()) or ())
    if premises:
        add(
            "덜어낸 사실을 전제로 삼던 부분을 주장하지 않고 내려놓았습니다: "
            + " / ".join(str(item) for item in premises)
        )
    for item in tuple(getattr(research, "uncertainties", ()) or ()):
        add(item)
    return tuple(messages)


def _section_revalidation_diagnostics(
    messages: Sequence[str], implementation_version: str
) -> tuple[str, ...]:
    """섹션 결과에 남길 진단. 재검증 사실 문장 + 검증기가 남긴 제외·덜어냄 사유."""
    header = (
        "저장된 원문 응답을 새 사실/판단 검증 규칙으로 다시 해석했습니다(외부 호출 0회)."
        " 새 근거를 추가하지 않았고, 이전 버전과 원문은 그대로 보존합니다."
        f" 검증 구현 버전: {implementation_version}."
    )
    return (header, *messages)


def _parse_iso(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _name_resolver(*, reader) -> Any | None:
    """R4에 주입할 이름 해석기(덕 타이핑). 없으면 `None`이고 원문 표기를 쓴다.

    해석기는 DB 한국어 값만 쓰며 번역하지 않는다. 설정이 없으면 만들어지지 않는다.
    """
    from app.preview.display_names import open_display_names

    try:
        from app.core.config import get_settings

        dsn = get_settings().names_database_url
    except Exception:  # noqa: BLE001 - 설정을 못 읽으면 이름 변환만 건너뛴다
        return None
    if not dsn:
        return None
    return _ResolverHandle(dsn)


class _ResolverHandle:
    """실행 단위 해석기 핸들. 연산마다 그 실행 범위 인덱스를 만든다.

    R4는 `resolve_player`/`resolve_team`/`rewrite_body`만 쓴다. 필요한 팀·선수 범위는
    호출 때 넘어오므로, 범위를 넘기지 않은 요청은 해석하지 않는다(전체 표 조회 금지).
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._cache: dict[tuple[int, ...], Any] = {}

    def _names_for(self, scope_team_ids: Sequence[int]):
        key = tuple(sorted({int(item) for item in scope_team_ids if item is not None}))
        if not key:
            return None
        if key not in self._cache:
            from app.preview.localized_names import (
                DbNameLookup,
                DisplayNames,
                load_name_index,
            )

            lookup = DbNameLookup.from_url(self._dsn)
            try:
                index = load_name_index(lookup, team_ids=list(key), include_rosters=True)
            finally:
                lookup.close()
            self._cache[key] = DisplayNames(index)
        return self._cache[key]

    def resolve_player(self, name, *, scope_team_ids=None, **kwargs):
        names = self._names_for(scope_team_ids or ())
        if names is None:
            raise KeyError("player name resolution needs an explicit team scope")
        return names.resolve_player(name, scope_team_ids=scope_team_ids, **kwargs)

    def resolve_team(self, value=None, **kwargs):
        team_id = kwargs.get("team_id")
        names = self._names_for([team_id] if team_id is not None else ())
        if names is None:
            raise KeyError("team name resolution needs an explicit team id")
        return names.resolve_team(value, **kwargs)

    def rewrite_body(self, text):
        # 본문 치환은 이미 확정된 표기만 쓰므로 범위 캐시 중 하나를 재사용한다.
        for names in self._cache.values():
            return names.rewrite_body(text)
        return text
