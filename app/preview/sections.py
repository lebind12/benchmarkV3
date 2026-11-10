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

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

from app.preview import artifacts as artifact_store
from app.preview import provider, store
from app.preview.contracts import (
    CoverageEntry,
    CoverageState,
    FixtureIdentity,
    SourceKind,
    ValidationStatus,
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
    "StoredContext",
    "build_implementations",
    "implemented_section_ids",
    "read_stored_context",
    "recompose_section_body",
]

FORM_SECTION_ID = "section_form"

# 이 파일이 실제 노드를 제공하는 섹션. 등록부의 implemented와 별개로 여기서 정한다.
_IMPLEMENTED_SECTIONS = (FORM_SECTION_ID, "section_availability", "section_outlook")

# 저장 자료 출처 표기. 실제 API 호출이 아니라 읽기 전용 재사용임을 드러낸다.
STORED_PROVIDER = "api-football-stored"


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
                implementation_version="mp05-compose-1",
                prompt_version=None,
                mode=transport.mode,
                run=_compose_node(now=now),
            ),
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
                implementation_version="mp07-outlook-compose-1",
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
            " 그대로 입력으로 썼고 새 근거를 추가하지 않았습니다.",
        ),
        actor_id=actor_id,
        now=moment,
    )
    return row, composed
