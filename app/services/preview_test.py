"""프리뷰 수집 시험 UI의 관리자용 조회·대상 해석.

이 모듈이 책임지는 것:

- **후보 조회**: 기존 추천 판정(`eligible_rows`·`priority`)을 그대로 써서, 지금 이후
  예정(NS)이고 추천 순위가 있는 경기를 킥오프→추천 순위→외부 경기 ID 순으로 낸다.
- **대상·기간 해석**: 선택한 두 경기의 리그/시즌에서 **활성 수집 대상**을 찾고, 수집
  기간(당일 KST 00:00부터 두 경기 중 마지막 킥오프까지, 양 끝 포함)을 낸다.
- **부작용 없는 실행 조회**: 수집 시험 실행 기록을 읽기만 한다.

책임지지 않는 것:

- 수집 실행 시작. 그것은 기존 `management_runs.start_preview_test_run`이 한다.
- 새 수집기·새 표·새 스케줄러. 이 모듈은 쓰기를 하지 않는다(`session.commit()` 없음).
- 기존 관리 실행 목록(`run_list`)의 오래된 기록 정리. 그 함수는 DELETE를 하므로
  시험 UI 조회에 쓰지 않는다. 여기 조회는 정리·복구를 호출하지 않는다.

조회 규칙:

- GET은 모델·외부 API를 호출하지 않는다.
- 후보·기간·대상은 **저장된 행만** 읽어 만든다. 없는 제공자 건수나 갱신 시각을
  추측해 채우지 않고, 모르는 값은 `None`으로 둔다.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fixture, League, LeagueSyncTarget, LeagueTranslation
from app.services.collection_test_scope import PREVIEW_TEST_MAX_FIXTURES
from app.services.home_preview import eligible_rows
from app.services.home_preview_policy import KST, utcnow
from app.services.management import ManagementError, target_payload

__all__ = [
    "CANDIDATE_LIMIT",
    "RUN_LIST_LIMIT",
    "build_plan",
    "candidates",
    "list_test_runs",
    "test_run",
]

# 후보로 내보내는 최대 수. UI는 앞의 두 개를 기본 선택하지만 사용자가 더 볼 수 있다.
CANDIDATE_LIMIT = 20
# 실행 목록 상한. 기존 관리 목록(100)과 같은 규모를 넘지 않는다.
RUN_LIST_LIMIT = 50


def _iso(moment: Any) -> str | None:
    return moment.isoformat() if isinstance(moment, datetime) else None


def _kst_day_start(moment: datetime) -> datetime:
    """그 시각이 속한 KST 날짜의 00:00(시간대 포함)."""
    return datetime.combine(moment.astimezone(KST).date(), time.min, tzinfo=KST)


def candidates(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """지금 이후 예정 경기 중 추천 순위가 있는 후보를 정해진 순서로 낸다.

    순서는 **킥오프 → 추천 순위 → 외부 경기 ID**다. 같은 시각의 두 경기를 추천 순위로
    가르고, 순위까지 같으면 외부 ID로 확정해 실행마다 같은 두 경기가 선택되게 한다.

    `as_of`는 후보 행들의 `updated_at` 최댓값이다. 후보가 없으면 `None`이며, 그때
    `reason`이 부족 사유를 말한다. 없는 시각을 지어내지 않는다.
    """
    moment = now or utcnow()
    rows = [
        row
        for row in eligible_rows(session, start=moment)
        if row[0].status_short == "NS" and row[0].kickoff_at > moment and row[4] is not None
    ]
    rows.sort(key=lambda row: (row[0].kickoff_at, row[4], row[0].external_id))
    selected = rows[:CANDIDATE_LIMIT]

    league_names = _league_names(session, {row[0].league_id for row in selected})
    items = [
        {
            "fixture_id": row[0].external_id,
            "kickoff_at": _iso(row[0].kickoff_at),
            "home_name": _team_name(row[2], row[5]),
            "away_name": _team_name(row[3], row[5]),
            "league_name": league_names.get(row[0].league_id) or row[1].name,
            "season": row[0].season_year,
            "priority": row[4],
        }
        for row in selected
    ]
    needed = PREVIEW_TEST_MAX_FIXTURES
    return {
        "as_of": _iso(max((row[0].updated_at for row in selected), default=None)),
        "timezone": "Asia/Seoul",
        "candidates": items,
        "reason": (
            None
            if len(items) >= needed
            else (
                f"예정(NS)이고 추천 순위가 있는 경기가 {len(items)}건입니다."
                f" 이 시험은 서로 다른 두 경기가 필요합니다."
            )
        ),
    }


def _team_name(team: Any, translations: dict) -> str:
    return translations.get(team.id) or team.name


def _league_names(session: Session, league_ids: set[int]) -> dict[int, str]:
    """리그 한국어 이름. 한 번에 읽고, 없으면 호출부가 원래 이름을 쓴다."""
    if not league_ids:
        return {}
    return {
        row.league_id: row.name_ko
        for row in session.scalars(
            select(LeagueTranslation).where(LeagueTranslation.league_id.in_(league_ids))
        )
        if row.name_ko
    }


def build_plan(
    session: Session,
    fixture_ids: list[int] | tuple[int, ...],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """선택한 두 경기의 수집 기간·활성 대상을 해석한다.

    구조적 위반(개수·중복·없는 경기)은 422로 거부한다. 그 값으로는 요청 자체가 성립하지
    않기 때문이다. 반면 **지금 수집할 수 없는 이유**(이미 시작·예정 아님·활성 대상 없음)는
    `can_collect=false`와 `blocking_reasons`로 돌려준다. 화면이 사유를 보여주고 사용자가
    다른 경기를 고를 수 있어야 하므로, 조회를 오류로 끊지 않는다.

    기간은 **당일 KST 00:00부터 두 경기 중 마지막 킥오프까지**, 양 끝을 포함한다.
    """
    moment = now or utcnow()
    needed = PREVIEW_TEST_MAX_FIXTURES
    fixture_ids = list(fixture_ids)
    if len(fixture_ids) != needed:
        raise ManagementError(f"fixture_ids에는 정확히 {needed}개 경기를 지정해야 합니다.", 422)
    if len(set(fixture_ids)) != needed:
        raise ManagementError("fixture_ids의 두 경기는 서로 달라야 합니다.", 422)
    if any(int(value) <= 0 for value in fixture_ids):
        raise ManagementError("fixture_ids는 양의 외부 경기 ID여야 합니다.", 422)

    fixtures = list(
        session.scalars(select(Fixture).where(Fixture.external_id.in_(fixture_ids)))
    )
    by_external = {int(fixture.external_id): fixture for fixture in fixtures}
    missing = [value for value in fixture_ids if int(value) not in by_external]
    if missing:
        raise ManagementError(
            f"경기 {', '.join(str(value) for value in missing)}를 저장된 경기에서 찾지 못했습니다."
            " 수집된 경기만 시험 대상으로 지정할 수 있습니다.",
            422,
        )

    blocking: list[dict[str, str]] = []
    ordered = [by_external[int(value)] for value in fixture_ids]
    kickoffs = []
    for fixture in ordered:
        if fixture.status_short != "NS":
            blocking.append(
                {
                    "code": "fixture_not_scheduled",
                    "message": (
                        f"경기 {fixture.external_id}는 예정(NS) 경기가 아닙니다"
                        f"(현재 {fixture.status_short})."
                    ),
                }
            )
        if fixture.kickoff_at is None:
            blocking.append(
                {
                    "code": "kickoff_unknown",
                    "message": f"경기 {fixture.external_id}의 킥오프 시각이 없습니다.",
                }
            )
            continue
        kickoffs.append(fixture.kickoff_at)
        if fixture.kickoff_at <= moment:
            blocking.append(
                {
                    "code": "fixture_started",
                    "message": (
                        f"경기 {fixture.external_id}의 킥오프"
                        f"({fixture.kickoff_at.isoformat()})가 이미 지났습니다."
                    ),
                }
            )

    targets: list[dict[str, Any]] = []
    seen_targets: set[int] = set()
    for fixture in ordered:
        target = session.scalar(
            select(LeagueSyncTarget).where(
                LeagueSyncTarget.league_id == fixture.league_id,
                LeagueSyncTarget.season_year == fixture.season_year,
            )
        )
        if target is None:
            blocking.append(
                {
                    "code": "target_not_found",
                    "message": (
                        f"경기 {fixture.external_id}의 리그/시즌"
                        f"({fixture.league_id}/{fixture.season_year})에 수집 대상이 없습니다."
                    ),
                }
            )
            continue
        if not target.is_active:
            blocking.append(
                {
                    "code": "target_inactive",
                    "message": (
                        f"수집 대상 {target.id}(시즌 {target.season_year})이 비활성 상태입니다."
                    ),
                }
            )
            continue
        league = session.get(League, target.league_id)
        if league is not None and not league.is_active:
            blocking.append(
                {
                    "code": "target_league_inactive",
                    "message": f"수집 대상 {target.id}의 리그가 비활성 상태입니다.",
                }
            )
            continue
        if target.id in seen_targets:
            continue
        seen_targets.add(target.id)
        payload = target_payload(session, target)
        targets.append(
            {
                "id": target.id,
                "league_name": payload["name"],
                "season": target.season_year,
                "include_details": bool(target.include_details),
            }
        )

    fixture_from = _kst_day_start(moment)
    fixture_to = max(kickoffs) if kickoffs else None
    notes = [
        "수집은 기간 안의 경기 자료를 갱신합니다. 선택한 두 경기만 생성 대상입니다.",
        "상세 수집 항목은 events/statistics/lineups/players이며 /injuries는 이번 수집에서"
        " 갱신되지 않습니다.",
        "수집이 끝나도 프리뷰 생성은 자동으로 시작하지 않습니다. 화면에서 직접 실행합니다.",
    ]
    return {
        "fixture_ids": [int(value) for value in fixture_ids],
        "fixture_from": _iso(fixture_from),
        "fixture_to": _iso(fixture_to),
        "target_ids": [target["id"] for target in targets],
        "targets": targets,
        "can_collect": not blocking and bool(targets) and fixture_to is not None,
        "blocking_reasons": blocking,
        "scope_notes": notes,
    }


def _test_run_rows(session: Session, *, run_id: str | None = None, limit: int):
    """저장된 수집 시험 실행 행. `test_scope`가 있는 행만 대상이다.

    DELETE·복구를 하지 않는다. 진행 중 표시는 저장된 `status`와 `cancel_requested_at`을
    그대로 반영한다(`payload_view`가 그 일을 한다).
    """
    from app.models import ManagementRun

    statement = select(ManagementRun).where(ManagementRun.payload.has_key("test_scope"))
    if run_id is not None:
        statement = statement.where(ManagementRun.id == run_id)
    else:
        statement = statement.order_by(ManagementRun.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def list_test_runs(session: Session, *, limit: int = RUN_LIST_LIMIT) -> dict[str, Any]:
    """수집 시험 실행 목록(부작용 없음). envelope는 기존 관리 목록과 같다.

    `active`와 `items`는 **서로 다른 집합**이다(기존 `run_list`와 같은 의미).

    - `active`: 진행 중인 시험 실행 **한 건** 또는 `null`.
    - `items`: 진행 중이 **아닌** 실행만. 같은 실행이 양쪽에 중복되지 않는다.

    판정은 저장된 `status`·`cancel_requested_at`만 읽으므로 조회가 상태를 바꾸지 않는다.
    `_recover_orphans`처럼 중단 실행을 복구하거나 `run_list`처럼 오래된 기록을 지우지
    않는다.
    """
    from app.services.management_runs import ACTIVE, payload_view

    rows = sorted(_test_run_rows(session, limit=limit), key=_created_at, reverse=True)
    views = [payload_view(row) for row in rows]
    active = next((run for run in views if run.get("status") in ACTIVE), None)
    return {
        "active": active,
        "items": [run for run in views if run is not active],
        "limit": limit,
    }


def test_run(session: Session, run_id: str) -> dict[str, Any]:
    """수집 시험 실행 하나. 없으면 404다(다른 실행의 내용을 돌려주지 않는다)."""
    from app.services.management_runs import payload_view

    rows = _test_run_rows(session, run_id=run_id, limit=1)
    if not rows:
        raise ManagementError("수집 시험 실행을 찾을 수 없습니다.", 404)
    return payload_view(rows[0])


def _created_at(row) -> str:
    return str((row.payload or {}).get("created_at") or "")
