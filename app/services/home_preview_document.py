"""홈 공개 조회용 저장 문서 선택·투영 (읽기 전용).

홈 추천 경기는 지금 옛 publication/version 저장소를 읽고, 새 관리자는 `preview_dev`의
실행·섹션·구성본을 쓴다. 이 모듈이 그 간극을 잇는다. **저장된 행만 읽고** 값을 새로
만들지 않으며, 모델·검색·스크래핑·배당 조회를 시작하지 않는다.

선택 규칙(승인 설계 `2026-11-13-home-stored-preview-design.md`):

- 최신의 기준은 **표시할 문서가 저장된 시각**이다. 요청 시각이나 킥오프가 아니다.
- 구성본이 있으면 그 구성본이 고른 결과 ID가 기준이다. 섹션을 각자 최신으로 바꿔
  관리자가 저장한 조합과 달라지게 하지 않는다. 구성본 항목은 **다른 실행**의 결과를
  가리킬 수 있다.
- 본문이 없는 실행(생성 중·실패)은 이전 문서를 밀어내지 않는다.
- 킥오프까지 6시간이 넘게 남은 저장본도 표시한다. 6시간 문구는 문서가 없을 때의 안내다.
- 공개 가능 여부는 기존 섹션 워크플로우 **버전 승인** 정책을 따른다. 모의 결과와
  승인되지 않은 버전은 저장됐다는 이유만으로 게시하지 않는다.
- 동률은 실행 ID로 일관되게 결정한다.

투영 규칙: 공개 응답에는 본문 표시에 필요한 화이트리스트만 담는다. 실행 진단·프롬프트·
원문·계정·비밀값은 넣지 않는다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.preview import store as store_module
from app.preview.models import (
    PreviewResult,
    PreviewRun,
    PreviewSectionApproval,
    PreviewSectionResult,
)
from app.services.home_preview_policy import utcnow
from app.preview.section_preview import composition_section_blocks
from app.preview.section_structured import structured_row_from_section_result

__all__ = [
    "DOCUMENT_REASONS",
    "PreviewDocumentUnavailable",
    "REQUIRED_READER_SECTIONS",
    "project_document",
    "read_document",
    "recommendation_preview_status",
    "select_document",
]

REQUIRED_READER_SECTIONS = ("section_players", "section_ai_forecast")

# 공개 응답이 쓰는 사유. 문서 없음과 읽기 실패를 같은 문구로 뭉개지 않는다.
DOCUMENT_REASONS = {
    "no_stored_run": "이 경기의 저장 실행이 없습니다.",
    "no_displayable_section": "표시할 본문이 있는 저장 문서가 없습니다.",
    "no_approved_version": "승인된 워크플로우 버전의 저장 문서가 없습니다.",
    "storage_unavailable": "저장 문서를 읽지 못했습니다.",
}

# 모의 실행은 UI 시연이며 게시 근거가 아니다.
_MOCK_MODE = "mock"

# 킥오프 6시간 이내인데 문서가 없는 구간. 기존 생성 일정(6시간)과 같은 값이며 새 생성
# 규칙을 만들지 않는다. 이 경계는 화면 문구를 고르는 데만 쓴다.
ABSENCE_DUE_SECONDS = 6 * 60 * 60


class PreviewDocumentUnavailable(RuntimeError):
    """저장 문서를 읽지 못했다. '문서 없음'과 구분해야 하는 상태다."""


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _text_of(value: Any) -> str | None:
    """UUID 열을 공개 비교용 문자열로. 없으면 `None`(근거 없음으로 본다)."""
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def _version_set(workflow_version: Any) -> str | None:
    return _text(workflow_version)


def approved_versions(approvals: Sequence[Mapping[str, Any]]) -> dict[str, frozenset[str]]:
    """활성 승인에서 (워크플로우 → 승인된 버전들)을 만든다.

    승인 단위는 섹션 워크플로우 버전이다. 승인 행이 없으면 표도 비고, 그 상태에서
    문서는 공개되지 않는다(승인을 만들어 통과시키지 않는다).
    """
    table: dict[str, set[str]] = {}
    for row in approvals:
        if not row.get("active"):
            continue
        workflow_id = _text(row.get("workflow_id"))
        version = _version_set(row.get("workflow_version"))
        if workflow_id is None or version is None:
            continue
        table.setdefault(workflow_id, set()).add(version)
    return {key: frozenset(value) for key, value in table.items()}


def approved_evidence(
    approvals: Sequence[Mapping[str, Any]],
) -> frozenset[tuple[str, str, str]]:
    """활성 승인이 **명시적으로 가리키는** (워크플로우, 실행, 섹션 결과) 근거 집합.

    승인 행은 검토한 실행(`reviewed_run_id`)과 섹션 결과(`section_result_id`)를 함께
    보관한다. 그 값이 승인이 가리키는 정확한 본문이며, 버전 문자열보다 구체적인 증거다.

    왜 버전 비교만으로는 부족한가: 승인 시각의 구성 버전은 승인 서비스가 계산한 값이고,
    저장 행의 버전 스탬프는 그 본문을 만든 실행이 남긴 값이다. 두 값은 같은 본문을
    가리키면서도 문자열이 다를 수 있다(옛 결과의 구성을 승인 시점에 재계산하는 기존
    사양). 그래서 문자열만 비교하면 사용자가 명시 승인한 본문이 공개에서 빠진다.

    이 집합은 "그 저장 결과를 명시 승인했다"는 사실만 담는다. 워크플로우 전체 승인이나
    현재 생성 코드 승인으로 넓히지 않는다. 근거가 비어 있는 승인 행은 넣지 않는다.
    """
    table: set[tuple[str, str, str]] = set()
    for row in approvals:
        if not row.get("active"):
            continue
        workflow_id = _text(row.get("workflow_id"))
        run_id = _text(row.get("reviewed_run_id"))
        result_id = _text(row.get("section_result_id"))
        if workflow_id is None or run_id is None or result_id is None:
            continue
        table.add((workflow_id, run_id, result_id))
    return frozenset(table)


def _displayable(
    row: Mapping[str, Any],
    approved: Mapping[str, frozenset[str]],
    evidence: frozenset[tuple[str, str, str]] = frozenset(),
) -> bool:
    """이 섹션 행을 공개 본문에 넣을 수 있는지.

    본문이 없으면 표시할 것이 없다. 모의 실행은 게시하지 않는다. 공개 근거는 두 갈래다.

    1. 워크플로우 버전이 활성 승인 버전과 일치한다(기존 경로).
    2. 활성 승인이 **이 행 자체**를 근거로 가리킨다(워크플로우·실행·섹션 결과가 모두
       일치). 버전 문자열이 달라도 사용자가 명시 승인한 그 본문이므로 표시한다.

    어느 갈래도 아니면 게시하지 않는다. 근거가 다른 행, 다른 실행, 같은 워크플로우의
    미승인 버전은 이 함수에서 통과하지 못한다.
    """
    if not _text(row.get("body")):
        return False
    if _text(row.get("mode")) == _MOCK_MODE:
        return False
    workflow_id = _text(row.get("workflow_id"))
    version = _version_set(row.get("workflow_version"))
    if workflow_id is None or version is None:
        return False
    if version in approved.get(workflow_id, frozenset()):
        return True
    result_id = _text(row.get("section_result_id"))
    run_id = _text(row.get("run_id"))
    if result_id is None or run_id is None:
        return False
    return (workflow_id, run_id, result_id) in evidence


def _chosen_rows(
    rows: Sequence[Mapping[str, Any]],
    selected_result_ids: Sequence[str],
    approved: Mapping[str, frozenset[str]],
    evidence: frozenset[tuple[str, str, str]] = frozenset(),
) -> list[Mapping[str, Any]]:
    """워크플로우당 한 행. 구성본 선택이 있으면 그 행, 없으면 최신 버전.

    구성본이 고른 행이 승인되지 않았거나 본문이 없으면 **그 섹션을 빼고** 다음 버전을
    대신 넣지 않는다. 선택된 버전이 정본이기 때문이다. 그래서 선택이 걸린 워크플로우는
    공개 불가여도 `claimed`에 남겨 아래 채우기 대상에서 제외한다. 대신 넣으면 관리자가
    저장한 조합과 홈 본문이 달라진다(수용 기준 DOC-PRESENT 위반).
    """
    by_id = {
        str(row.get("section_result_id")): row
        for row in rows
        if row.get("section_result_id")
    }
    chosen: dict[str, Mapping[str, Any]] = {}
    # 구성본이 지목한 워크플로우. 공개 가능 여부와 무관하게 "이 섹션은 선택이 정본"이다.
    claimed: set[str] = set()
    for raw_id in selected_result_ids:
        row = by_id.get(str(raw_id))
        if row is None:
            continue
        workflow_id = _text(row.get("workflow_id"))
        if workflow_id is None or workflow_id in claimed:
            continue
        claimed.add(workflow_id)
        if not _displayable(row, approved, evidence):
            continue
        chosen[workflow_id] = row
    ordered = sorted(
        (row for row in rows if _displayable(row, approved, evidence)),
        key=lambda row: (
            str(row.get("workflow_id") or ""),
            -int(row.get("version") or 0),
            str(row.get("created_at") or ""),
        ),
    )
    for row in ordered:
        workflow_id = _text(row.get("workflow_id"))
        if workflow_id is None or workflow_id in chosen or workflow_id in claimed:
            continue
        chosen[workflow_id] = row
    return list(chosen.values())


def _saved_at(rows: Sequence[Mapping[str, Any]]) -> datetime | None:
    """이 문서가 저장된 시각. 고른 섹션 행이 저장된 시각 중 가장 늦은 값이다.

    저장 열은 시간대를 가진 값이므로 UTC로 맞춰 비교한다. 기준을 요청 시각이나
    킥오프로 바꾸지 않는다.
    """
    moments: list[datetime] = []
    for row in rows:
        created = row.get("created_at")
        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except ValueError:
                continue
        if not isinstance(created, datetime):
            continue
        moments.append(
            created.astimezone(timezone.utc) if created.tzinfo else created.replace(tzinfo=timezone.utc)
        )
    return max(moments) if moments else None


def select_document(
    runs: Sequence[Mapping[str, Any]],
    approved: Mapping[str, frozenset[str]],
    evidence: frozenset[tuple[str, str, str]] = frozenset(),
) -> dict[str, Any] | None:
    """표시 가능한 저장 문서 중 **저장 시각이 가장 늦은** 하나를 고른다.

    `runs`의 각 항목은 `run_id`, `sections`(그 실행의 섹션 행), 선택적으로
    `composition_result_ids`를 갖는다. 표시할 본문이 하나도 없는 실행은 후보에서
    빠지므로, 본문 없는 새 실행이 이전 문서를 밀어내지 않는다.
    """
    best: dict[str, Any] | None = None
    best_key: tuple[datetime, str] | None = None
    for run in runs:
        sections = list(run.get("sections") or ())
        selected = [str(item) for item in (run.get("composition_result_ids") or ())]
        chosen = _chosen_rows(sections, selected, approved, evidence)
        if not chosen:
            continue
        saved_at = _saved_at(chosen)
        if saved_at is None:
            continue
        candidate = {
            "run_id": str(run.get("run_id")),
            "rows": chosen,
            "saved_at": saved_at.isoformat(),
        }
        # 저장 시각이 늦은 쪽이 최신이다. 동률은 실행 ID로 일관되게 결정한다.
        key = (saved_at, candidate["run_id"])
        if best_key is None or key > best_key:
            best, best_key = candidate, key
    return best


def _reason_key(runs: Sequence[Mapping[str, Any]]) -> str:
    if not runs:
        return "no_stored_run"
    for run in runs:
        if any(_text(row.get("body")) for row in run.get("sections") or ()):
            return "no_approved_version"
    return "no_displayable_section"


def _public_row(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """구조 값에서 **공개 가능한 필드만** 남긴다.

    `structured_row_from_section_result`는 내부 기본키(`player_id`, `team_id`)도 함께
    낸다. 그 값은 우리 DB 식별자이며 API-Football 외부 ID와 숫자가 다르다(예: 내부 13 =
    외부 50). 공개 계약에 넣으면 계정·원문 정보는 아니어도 내부 식별자를 노출하고,
    소비자가 사진 주소를 잘못 조립할 위험을 만든다. 그래서 이름·이유·팀 표기와
    **확인된 외부 ID·사진 주소**만 남긴다.
    """
    structured = row.get("structured")
    if not isinstance(structured, Mapping):
        return row

    def keep(values: Any, allowed: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for item in values or ():
            if not isinstance(item, Mapping):
                continue
            rows.append({key: item.get(key) for key in allowed if key in item})
        return rows

    cleaned = {
        "structured_version": structured.get("structured_version"),
        "workflow_id": structured.get("workflow_id"),
        "players": keep(
            structured.get("players"),
            (
                "player",
                "reason",
                "team",
                "external_player_id",
                "team_external_id",
                "photo_url",
                "team_side",
                "slot_key",
                "unresolved",
            ),
        ),
        "injuries": keep(
            structured.get("injuries"),
            (
                "player",
                "team",
                "status",
                "summary",
                "external_player_id",
                "team_external_id",
                "photo_url",
                "team_side",
                "slot_key",
                "unresolved",
            ),
        ),
        "media": keep(
            structured.get("media"), ("publisher", "statement", "predicted_score", "published_at", "url")
        ),
        "odds": keep(
            structured.get("odds"), ("bookmaker", "market", "observedAt", "home", "draw", "away")
        ),
        "forecast": dict(structured["forecast"]) if isinstance(structured.get("forecast"), Mapping) else None,
    }
    return {**row, "structured": cleaned}


def project_document(
    document: Mapping[str, Any],
    *,
    external_id: int,
    fixtures: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """고른 문서를 공개 화이트리스트 응답으로 투영한다.

    `composition_section_blocks`가 본문·근거·부분 표시를 만든다. 여기서는 표시에 필요한
    식별자만 덧붙이고, 진단·원문·계정·비밀값은 넣지 않는다.
    """
    rows = list(document.get("rows") or ())
    blocks, problems = composition_section_blocks(rows, selected_result_ids=())
    for row in rows:
        if row.get("storage_mismatch") and row.get("storage_error"):
            err = str(row["storage_error"])
            if err not in problems:
                problems.append(err)
    by_workflow = {_text(row.get("workflow_id")): row for row in rows}
    structured_by_result = {
        str(row.get("section_result_id")): _public_row(row).get("structured")
        for row in rows
    }
    sections = []
    for block in blocks:
        row = by_workflow.get(str(block.get("section_id"))) or {}
        result_id = str(row.get("section_result_id") or "")
        sections.append(
            {
                "section_result_id": result_id or None,
                "run_id": _text(row.get("run_id")),
                "workflow_id": block.get("section_id"),
                "workflow_version": row.get("workflow_version"),
                "version": block.get("version"),
                "title": block.get("title"),
                "body": block.get("body"),
                "sources": list(block.get("sources") or []),
                "quality": block.get("quality"),
                "partial": bool(block.get("partial")),
                "created_at": block.get("created_at"),
                "structured": structured_by_result.get(result_id),
            }
        )
    present_workflows = {str(item.get("workflow_id") or "") for item in sections}
    for required_workflow in REQUIRED_READER_SECTIONS:
        if required_workflow not in present_workflows:
            msg = f"{required_workflow}: 표시할 수 있는 승인 본문이 없어 필수 섹션이 누락되었습니다."
            if msg not in problems:
                problems.append(msg)
    fixture = dict(fixtures or {})
    return {
        "schema_version": "1.0",
        "fixture_id": external_id,
        "status": "available",
        "reason": None,
        "saved_at": document.get("saved_at"),
        "run_id": str(document.get("run_id")),
        "complete": not problems,
        "fixture": fixture,
        "headline": sections[0]["title"] if sections else None,
        "sections": sections,
    }


def absence_notice(kickoff_at: Any, *, now: datetime) -> dict[str, Any]:
    """문서가 없을 때 화면이 쓸 안내 상태. 시각 근거로만 정한다.

    세 경우를 하나의 값으로 모은다. 화면이 시간 비교를 다시 하면 서버와 클라이언트
    시계가 어긋나 같은 경기가 다른 안내로 보인다(모델 도메인: 분기를 자료 구조 하나로).

    - `upcoming_overdue`: 킥오프 전 남은 시간이 0보다 크고 6시간 이하인데 문서가 없다.
      아직 생성되지 않았다는 문제 안내다. 실제 실패 기록이 없으므로 생성 실패로 단정하지
      않는다.
    - `upcoming`: 그보다 먼 미래(6시간 초과)다. 기본 안내만 보여준다.
    - `past`: 킥오프 시각이 지났거나 이미 시작한 경기다. 앞으로 생성될 예정이라고
      표현하지 않는다.

    경계는 계획의 최소 해석을 따른다. 정확히 6시간은 미생성 문제 안내에 포함하고,
    정확히 킥오프 시각부터는 `past`다.
    """
    if isinstance(kickoff_at, str):
        try:
            kickoff_at = datetime.fromisoformat(kickoff_at)
        except ValueError:
            return {"state": "upcoming", "remaining_seconds": None}
    if not isinstance(kickoff_at, datetime):
        return {"state": "upcoming", "remaining_seconds": None}
    kickoff = kickoff_at if kickoff_at.tzinfo else kickoff_at.replace(tzinfo=timezone.utc)
    remaining = (kickoff - now).total_seconds()
    if remaining <= 0:
        state = "past"
    elif remaining <= ABSENCE_DUE_SECONDS:
        state = "upcoming_overdue"
    else:
        state = "upcoming"
    return {"state": state, "remaining_seconds": int(remaining)}


def empty_document(
    reason: str,
    *,
    external_id: int,
    fixtures: Mapping[str, Any] | None = None,
    now: datetime | None = None,
):
    """문서 없음 응답. 사유를 숨기지 않고, 본문 자리를 만들지 않는다."""
    fixture = dict(fixtures or {})
    return {
        "schema_version": "1.0",
        "fixture_id": external_id,
        "status": "none",
        "reason": reason,
        "reason_text": DOCUMENT_REASONS.get(reason),
        "absence": absence_notice(fixture.get("kickoff_at"), now=now or utcnow()),
        "saved_at": None,
        "run_id": None,
        "complete": None,
        "fixture": fixture,
        "headline": None,
        "sections": [],
    }


def _section_row_view(row: PreviewSectionResult) -> dict[str, Any]:
    """저장 섹션 행 → 선택·투영에 쓰는 평면 값(내부 진단 제외)."""
    created = row.created_at
    return {
        "section_result_id": str(row.id),
        "run_id": str(row.run_id),
        "workflow_id": row.workflow_id,
        "workflow_version": row.workflow_version,
        "version": row.version,
        "title": row.title,
        "body": row.body,
        "sources": list(row.sources or []),
        "quality": row.quality,
        "mode": row.mode,
        "output_contract_version": getattr(row, "output_contract_version", None),
        "unavailable_reason": row.unavailable_reason,
        "created_at": created.isoformat() if created else None,
        "result_ids": list(row.result_ids or []),
    }


def _is_eligible_document_run(run: Any) -> bool:
    """공개 문서 후보로 쓸 수 있는 실행만 남긴다.

    구 MP-10(`mp10-*`)·모의·카탈로그·단일 모듈 실행은 현재 canonical 저장 계약을
    쓰지 않으므로 제외한다. 속성 없는 단위 대역(`_StubRun`)과 test-cfg는 유지한다.
    """
    if getattr(run, "status", None) == "cancelled":
        return False
    if getattr(run, "mode", None) == _MOCK_MODE:
        return False
    op_kind = getattr(run, "operation_kind", None)
    if op_kind is not None and str(op_kind) not in ("preview", "section"):
        return False
    cfg = getattr(run, "config_version", None)
    if cfg is not None:
        cfg_str = str(cfg).strip()
        if (
            cfg_str.startswith("mp10-")
            or cfg_str.startswith("mp02-demo")
            or cfg_str.startswith("mp04-fixture-catalog")
        ):
            return False
    return True


def _read_runs(session: Session, external_id: int, *, limit: int = 50):
    """이 외부 경기 ID의 저장 실행들. 저장된 행만 읽는다."""
    statement = (
        select(PreviewRun)
        .where(
            PreviewRun.fixture_id == external_id,
            PreviewRun.status != "cancelled",
            PreviewRun.mode != _MOCK_MODE,
            PreviewRun.operation_kind.in_(("preview", "section")),
            ~PreviewRun.config_version.startswith("mp10-"),
        )
        .order_by(PreviewRun.requested_at.desc())
        .limit(limit)
    )
    return [run for run in session.scalars(statement) if _is_eligible_document_run(run)]


def _read_approvals(session: Session) -> list[dict[str, Any]]:
    """활성 승인 행을 둘 다의 판정 근거로 읽는다.

    버전 문자열(기존 경로)과 승인이 가리키는 정확한 실행·섹션 결과(증거 경로)를 함께
    넘긴다. 읽기 전용이며 승인 행을 만들거나 고치지 않는다.
    """
    rows = session.scalars(select(PreviewSectionApproval).where(PreviewSectionApproval.active.is_(True)))
    return [
        {
            "workflow_id": row.workflow_id,
            "workflow_version": row.workflow_version,
            "reviewed_run_id": _text_of(getattr(row, "reviewed_run_id", None)),
            "section_result_id": _text_of(getattr(row, "section_result_id", None)),
            "active": True,
        }
        for row in rows
    ]


def _composition_ids(session: Session, run_id: Any) -> list[str]:
    """관리자가 저장한 구성본의 선택 결과 ID. 없으면 빈 목록."""
    try:
        record = store_module.load_composition(session, run_id)
    except Exception:  # noqa: BLE001 - 구성본 조회 실패로 문서를 없애지 않는다
        return []
    if not record.get("available"):
        return []
    composition = record.get("composition") or {}
    return [
        str(item["result_id"])
        for item in composition.get("items") or ()
        if isinstance(item, Mapping) and item.get("result_id")
    ]


def _rows_for(session: Session, run: PreviewRun, cache: dict[str, PreviewSectionResult]):
    """실행의 섹션 행과, 구성본이 다른 실행에서 고른 행까지 모은다."""
    own = list(
        session.scalars(
            select(PreviewSectionResult)
            .where(PreviewSectionResult.run_id == run.id)
            .order_by(PreviewSectionResult.created_at, PreviewSectionResult.workflow_id)
        )
    )
    rows = [_section_row_view(row) for row in own]
    composition_ids = _composition_ids(session, run.id)
    known = {row["section_result_id"] for row in rows}
    for result_id in composition_ids:
        if result_id in known:
            continue
        if result_id not in cache:
            try:
                import uuid as _uuid

                cache[result_id] = store_module.get_section_result_any_run(
                    session, _uuid.UUID(result_id)
                )
            except (ValueError, TypeError):
                cache[result_id] = None
        picked = cache.get(result_id)
        if picked is None:
            continue
        rows.append(_section_row_view(picked))
        known.add(result_id)
    return rows, composition_ids


def _result_payloads(session: Session, rows: Sequence[Mapping[str, Any]]):
    """섹션 행의 `result_ids` → 저장 payload. 구조화 값의 근거다."""
    ids: list[Any] = []
    for row in rows:
        for value in row.get("result_ids") or ():
            try:
                import uuid as _uuid

                ids.append(_uuid.UUID(str(value)))
            except (ValueError, TypeError):
                continue
    if not ids:
        return {}
    payloads: dict[str, Any] = {}
    for result in session.scalars(select(PreviewResult).where(PreviewResult.id.in_(ids))):
        payloads[str(result.id)] = result.payload
    return payloads


def _latest_payload(payloads: Mapping[str, Any], row: Mapping[str, Any]):
    for result_id in row.get("result_ids") or ():
        payload = payloads.get(str(result_id))
        if isinstance(payload, Mapping):
            return payload
    return None


def _id_context(session: Session, run: Any):
    """저장 payload의 **내부** ID를 화면용 **외부** ID로 확인하는 좁은 경계.

    저장 payload의 `player_id`/`team_id`는 우리 DB 기본키이고, 사진·로고 주소는
    API-Football 외부 ID를 요구한다. 두 공간의 숫자가 달라서(내부 13 = 외부 50) 그대로
    쓰면 다른 팀 로고가 나온다. 확인되지 않으면 `None`이고 사진을 만들지 않는다.
    확인기는 기존 표시 이름 파사드를 그대로 재사용하며 새 연결·새 권한을 만들지 않는다.
    """
    from app.preview.config import get_settings
    from app.preview.display_names import open_display_names
    from app.preview.section_structured import StructuredIdContext

    try:
        bridge = open_display_names(
            fixture={
                "home_team_id": getattr(run, "home_team_id", None),
                "away_team_id": getattr(run, "away_team_id", None),
            },
            dsn=get_settings().names_database_url,
            fallback_label=str(getattr(run, "fixture_label", "") or ""),
        )
    except Exception:  # noqa: BLE001 - 확인 실패로 문서를 없애지 않는다
        return None, None
    if not getattr(bridge, "active", False):
        return None, bridge
    scope = tuple(
        int(value)
        for value in (getattr(run, "home_team_id", None), getattr(run, "away_team_id", None))
        if isinstance(value, int)
    )
    try:
        # `StructuredIdContext`는 **해석기**를 요구한다. 파사드(`DisplayNameBridge`)가 아니라
        # 그 안의 `names`(DB 이름 해석기)를 넘긴다. 관리자 `get_section_results` 경로도 같은
        # 값을 넘긴다. 파사드를 그대로 넘기면 `resolve_player`/`resolve_team`이 없어 모든
        # 확인이 조용히 `None`이 되고, 선수·부상 사진과 팀 외부 ID가 공개 응답에서 사라진다.
        return StructuredIdContext(bridge.names, scope_team_ids=scope), bridge
    except Exception:  # noqa: BLE001 - 확인 경계 실패로 표를 없애지 않는다
        return None, bridge


def _parse_utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _decorate_rows(
    session: Session,
    rows: Sequence[Mapping[str, Any]],
    *,
    id_context: Any = None,
    home_name: str | None = None,
    away_name: str | None = None,
) -> list[dict[str, Any]]:
    from app.preview import player_section_read

    payloads = _result_payloads(session, rows)
    decorated: list[dict[str, Any]] = []
    for row in rows:
        if player_section_read.is_new_player_section_contract(row.get("output_contract_version")):
            canonical = player_section_read.read_canonical_player_section(
                session,
                row,
                id_context=id_context,
                home_team_name=home_name,
                away_team_name=away_name,
            )
            if canonical.storage_mismatch:
                row = {
                    **row,
                    "body": "",
                    "unavailable_reason": canonical.storage_error,
                    **canonical.structured_result_fields(),
                }
            else:
                row = {**row, **canonical.structured_result_fields()}
        else:
            payload = _latest_payload(payloads, row)
            row = {
                **row,
                **structured_row_from_section_result(
                    row, payload=payload, id_context=id_context
                ),
            }
        decorated.append(row)
    return decorated


def _load_selection_context(
    session: Session,
    external_id: int,
    *,
    approved: Mapping[str, frozenset[str]] | None = None,
    evidence: frozenset[tuple[str, str, str]] | None = None,
):
    runs = _read_runs(session, external_id)
    if not runs:
        return [], [], None
    if approved is None or evidence is None:
        approval_rows = _read_approvals(session)
        approved = approved_versions(approval_rows)
        evidence = approved_evidence(approval_rows)
    cache: dict[str, PreviewSectionResult] = {}
    candidates = []
    for run in runs:
        rows, composition_ids = _rows_for(session, run, cache)
        candidates.append(
            {
                "run_id": run.id,
                "sections": rows,
                "composition_result_ids": composition_ids,
            }
        )
    chosen = select_document(candidates, approved, evidence)
    return runs, candidates, chosen


def read_document(
    session: Session,
    external_id: int,
    *,
    fixtures: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """홈 공개 조회의 저장 문서. 없으면 사유가 담긴 `status=none` 응답.

    저장 조회만 한다. 모델·검색·배당 갱신·생성·쓰기를 시작하지 않는다.
    """
    try:
        moment = now or utcnow()
        runs, candidates, chosen = _load_selection_context(session, external_id)
        if not runs:
            return empty_document(
                "no_stored_run", external_id=external_id, fixtures=fixtures, now=moment
            )
        if chosen is None:
            return empty_document(
                _reason_key(candidates), external_id=external_id, fixtures=fixtures, now=moment
            )
        rows = list(chosen.get("rows") or ())
        chosen_run = next(
            (run for run in runs if str(run.id) == str(chosen.get("run_id"))), None
        )
        id_context, bridge = (None, None)
        if chosen_run is not None:
            id_context, bridge = _id_context(session, chosen_run)
        home_name = _text((fixtures or {}).get("home", {}).get("name")) if isinstance(fixtures, Mapping) else None
        away_name = _text((fixtures or {}).get("away", {}).get("name")) if isinstance(fixtures, Mapping) else None
        try:
            decorated = _decorate_rows(
                session,
                rows,
                id_context=id_context,
                home_name=home_name,
                away_name=away_name,
            )
        finally:
            # 파사드가 연 읽기 전용 연결을 요청 단위로 닫는다.
            close = getattr(bridge, "close", None)
            if callable(close):
                close()
        return project_document(
            {**chosen, "rows": decorated}, external_id=external_id, fixtures=fixtures
        )
    except SQLAlchemyError as exc:
        raise PreviewDocumentUnavailable(str(exc)) from exc


def recommendation_preview_status(
    session: Session,
    external_id: int,
    *,
    kickoff_at: Any = None,
    status_short: str | None = None,
    now: datetime | None = None,
    approved: Mapping[str, frozenset[str]] | None = None,
    evidence: frozenset[tuple[str, str, str]] | None = None,
) -> dict[str, Any]:
    """홈 추천 카드 `preview` 요약. `/document`와 같은 저장 선택·완전성 기준을 쓴다."""
    try:
        moment = now or utcnow()
        runs, candidates, chosen = _load_selection_context(
            session, external_id, approved=approved, evidence=evidence
        )
        if chosen is not None:
            decorated = _decorate_rows(session, list(chosen.get("rows") or ()))
            projected = project_document(
                {**chosen, "rows": decorated}, external_id=external_id
            )
            if projected.get("sections"):
                saved_at = projected.get("saved_at")
                saved_dt = _parse_utc(saved_at)
                kickoff_dt = _parse_utc(kickoff_at)
                # 추천 스키마는 generated_at < kickoff_at를 강제한다. 킥오프 이후 저장분은
                # 시각을 지어내지 않고 generated_at=None으로 남긴다.
                generated_at = (
                    saved_at
                    if saved_dt is not None
                    and (kickoff_dt is None or saved_dt < kickoff_dt)
                    else None
                )
                return {
                    "state": "ready" if projected.get("complete") else "partial",
                    "served": "current",
                    "generated_at": generated_at,
                    "as_of": saved_at,
                }
        if any(getattr(run, "status", None) in ("queued", "running", "retry_wait") for run in runs):
            state = "pending"
        elif runs and _reason_key(candidates) == "no_approved_version":
            state = "unavailable"
        elif runs and getattr(runs[0], "status", None) == "failed":
            state = "failed"
        elif chosen is not None:
            # 선택된 문서가 저장 불일치로 표시 불가인 경우
            state = "failed"
        else:
            kickoff_dt = _parse_utc(kickoff_at)
            kickoff_passed = (status_short is not None and status_short != "NS") or (
                kickoff_dt is not None and kickoff_dt <= moment
            )
            before_window = kickoff_dt is not None and kickoff_dt > moment + timedelta(hours=6)
            state = "unavailable" if (before_window or kickoff_passed) else "pending"
        return {
            "state": state,
            "served": None,
            "generated_at": None,
            "as_of": None,
        }
    except SQLAlchemyError as exc:
        raise PreviewDocumentUnavailable(str(exc)) from exc
