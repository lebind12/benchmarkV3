"""수집 종료 → 기존 프리뷰 생성 서비스 연결 (수집 경계).

이 모듈이 책임지는 것:

- 종료된 수집 실행의 **원래 상태를 보존**한 채, DB의 대상 경기로 생성을 시도한다.
- 후보 선택(기존 NS·0<남은시간<=6h 정책), 순서, 회차 한도를 기존 의미 그대로 쓴다.
- 자동 회차 중복을 막고, 경기별 예외를 격리해 다음 경기를 계속 처리한다.
- 생성은 기존 단일 서비스 `generate_match_preview(trigger="collection")`만 호출한다.

책임지지 않는 것:

- 새 생성 엔진·프롬프트·본문 해석·품질 판정. 본문 내용은 이 경계에서 읽지 않는다.
- 수집 상태 변경. 호출자가 넘긴 원래 상태를 덮어쓰지 않는다.

승인 경계: 이 경계는 **워크플로우 승인으로 자동 생성을 허용/불허하지 않는다**(사용자 확정:
승인은 AI 한글 번역·선수 연결의 검수 상태이며 게시 허가가 아니다). 승인 행이 없거나 저장
버전이 달라도 생성은 정상 호출되고, 승인 조회 실패도 생성 실패로 바꾸지 않는다. 승인 행을
새로 만들거나 자동 승인하는 경로도 두지 않는다.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Callable, Mapping, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.preview.contracts import RunStatus
from app.preview.models import PreviewRun
from app.services.match_preview import FixtureResolutionError, generate_match_preview

__all__ = [
    "COLLECTION_LABEL",
    "collect_candidates",
    "run_collection_generation",
]

# 수집 경계가 남기는 실행 label 접두사. 같은 자동 회차의 중복 판정에 쓴다.
COLLECTION_LABEL = "수집 완료 후 자동 생성(시스템 호출)"


def _round_key(kickoff_at) -> str:
    """이 경기의 자동 생성 회차. **기존 회차 의미를 그대로 쓴다.**

    기존 `home_preview_generation.process_fixture`는 `generation_due_at(kickoff)`(킥오프
    직전 마지막 정기 수집 slot)을 회차로 삼아 같은 경기의 재생성을 막는다. 실행 시각의
    bucket(`slot_time(now)`)을 쓰면 경기마다 회차가 실행 시각에 따라 달라져, 같은 경기가
    6시간마다 다시 생성된다. 그래서 회차는 **킥오프에 고정**한다.
    """
    from app.services.home_preview_policy import generation_due_at

    return generation_due_at(kickoff_at).isoformat()


def _test_round_key(test_scope) -> str:
    """시험 실행의 회차 키. **정기 회차 키를 소모하지 않는다.**

    시험은 수집 실행 ID로 구분한다. 정기 회차(`generation_due_at`)를 쓰면 이 시험이 그
    회차를 선점해 이후 정기 생성이 중복으로 건너뛰어질 수 있다.
    """
    return f"preview-test:{getattr(test_scope, 'run_id', '')}"


def _fixture_label(
    external_id: int, home_name: str, away_name: str, *, round_key: str
) -> str:
    """실행 label. **경기 회차 식별자를 포함**해 같은 회차만 중복으로 잡는다.

    label은 수집 경계가 만든 실행에만 붙으므로, 관리자 실행(label이 다르다)은 자동 회차
    중복 판정에 걸리지 않는다.
    """
    return f"{COLLECTION_LABEL} {round_key} {external_id} {home_name} 대 {away_name}"


def _note_skipped(skipped: list | None, fixture_id, reason: str, *, detail=None) -> None:
    """지정 경기 탈락 사유를 한 번만 남긴다(같은 경기 중복 기록 방지)."""
    if skipped is None:
        return
    key = int(fixture_id)
    if any(int(row.get("fixture_id", 0)) == key for row in skipped):
        return
    entry = {"fixture_id": key, "reason": reason}
    if detail is not None:
        entry["detail"] = detail
    skipped.append(entry)


def collect_candidates(
    session: Session,
    *,
    now,
    fixture_ids: Sequence[int] | None = None,
    test_scope=None,
    skipped: list | None = None,
):
    """자동 생성 후보를 기존 정책 그대로 고른다.

    기본은 NS·`now < kickoff <= now+6h`다. `test_scope`가 주어지면 **그 범위가 지목한
    두 경기만** 시간창 조건을 면제한다(사용자 명시 예외). 다른 후보 조건(NS·본문)은
    그대로이며, 일반 경로는 `test_scope=None`이라 예외가 존재하지 않는다.

    시험 범위에서는 **지정 경기별 탈락 사유**를 `skipped`에 남긴다. 수집 후 일정/상태가
    바뀌어 빠진 경기를 사용자가 구분할 수 있어야 하기 때문이다(단순 `no_candidates`만
    남기면 어느 경기가 왜 빠졌는지 알 수 없다).
    """
    from app.services.home_preview import eligible_rows

    wanted = set(fixture_ids) if fixture_ids is not None else None
    rows = [
        row
        for row in eligible_rows(session, start=now, end=now + timedelta(hours=6))
        if row[0].status_short == "NS"
        and now < row[0].kickoff_at
        and (wanted is None or row[0].external_id in wanted)
    ]
    exempt: list = []
    if test_scope is not None:
        # 요청 기간은 **모든 후보**에 적용한다. 6시간 안이면서 기간 밖인 경기도 이 요청의
        # 범위가 아니므로 생성하지 않는다(생성 직전의 기간 존중).
        kept: list = []
        for row in rows:
            if test_scope.is_preview_fixture(row[0].external_id) and not test_scope.in_window(
                row[0].kickoff_at
            ):
                _note_skipped(
                    skipped,
                    row[0].external_id,
                    "outside_requested_period",
                    detail=f"kickoff={row[0].kickoff_at.isoformat()}",
                )
                continue
            kept.append(row)
        rows = kept
    if test_scope is not None:
        # 6시간 밖이어도 이 요청이 지목한 두 경기만 후보에 더한다. 다만 **요청 기간 밖**
        # 경기는 더하지 않는다. 기간은 이 요청이 확인하려는 범위이므로, 일정이 바뀌어
        # 기간을 벗어난 경기를 조용히 생성하면 요청 범위를 넘는다.
        exempt_ids = set(test_scope.preview_fixture_ids)
        known = {row[0].external_id for row in rows}
        found = {row[0].external_id for row in rows}
        for row in eligible_rows(session, start=now, end=now + timedelta(days=365)):
            fixture = row[0]
            if fixture.external_id not in exempt_ids or fixture.external_id in known:
                continue
            found.add(fixture.external_id)
            if not test_scope.in_window(fixture.kickoff_at):
                _note_skipped(
                    skipped,
                    fixture.external_id,
                    "outside_requested_period",
                    detail=f"kickoff={fixture.kickoff_at.isoformat()}",
                )
                continue
            if fixture.status_short != "NS":
                _note_skipped(
                    skipped, fixture.external_id, "not_scheduled", detail=fixture.status_short
                )
                continue
            if not now < fixture.kickoff_at:
                _note_skipped(skipped, fixture.external_id, "kickoff_passed")
                continue
            exempt.append(row)
            known.add(fixture.external_id)
        # DB에서 아예 찾지 못한 지정 경기도 사유로 남긴다.
        for external_id in test_scope.preview_fixture_ids:
            if external_id not in found:
                _note_skipped(skipped, external_id, "fixture_not_found")
    rows = rows + exempt
    rows.sort(key=lambda row: (row[4], row[0].kickoff_at, row[0].external_id))
    if test_scope is not None:
        # 시험은 **지정한 두 경기만** 생성한다. 같은 시각의 다른 경기는 대상이 아니다.
        rows = [row for row in rows if test_scope.is_preview_fixture(row[0].external_id)]
        key = _test_round_key(test_scope)
    else:
        key = None
    return [
        {
            "fixture_id": row[0].external_id,
            "round_key": key or _round_key(row[0].kickoff_at),
            "label": _fixture_label(
                row[0].external_id,
                row[2].name,
                row[3].name,
                round_key=key or _round_key(row[0].kickoff_at),
            ),
            "priority": row[4],
        }
        for row in rows
    ]


def _already_generated(session: Session, *, fixture_id: int, label: str) -> str | None:
    """같은 경기·같은 자동 회차의 **완료·실패 이력**을 찾는다.

    기존 저장 구조(`preview_runs`)만 읽는다. 새 표를 만들지 않는다. 실행 label에 회차
    식별자를 넣으므로 같은 회차의 재실행은 `requested_at`이 달라도 같은 label로 잡힌다.
    진행 중(`queued`/`running`) 실행도 중복으로 본다.
    """
    row = session.scalar(
        select(PreviewRun)
        .where(
            PreviewRun.fixture_id == fixture_id,
            PreviewRun.label == label,
        )
        .order_by(PreviewRun.requested_at.desc())
        .limit(1)
    )
    if row is None:
        return None
    # 상태를 구분하지 않고 **이력 자체**를 중복으로 본다. 성공·실패·진행 중 어느 쪽이든
    # 같은 회차를 다시 시작하지 않는다(새 자동 재시도 정책을 만들지 않는다).
    return str(row.id)


def _fixture_lock(fixture_id: int):
    """이 경기의 자동 생성 구간을 직렬화하는 **최소 잠금**(PostgreSQL 세션 advisory lock).

    왜 필요한가: 중복 조회와 생성 시작 사이에는 창이 있다. 두 수집 종료가 거의 동시에
    같은 경기를 보면 둘 다 "아직 없음"을 읽고 둘 다 생성을 시작할 수 있다. 기존
    `preview_pipeline_runs`의 active 유니크 키는 **진행 중 실행**만 합치고, 이 경계는
    그 표를 쓰지 않으므로(생성 서비스가 소유) 그 키로는 이 창을 닫을 수 없다.

    새 잠금 엔진을 만들지 않고, 이미 이 저장소가 쓰는 `pg_try_advisory_lock` 패턴을
    경기 단위 키로 한 번만 쓴다. 잠금을 못 잡으면 **생성을 시작하지 않고** 건너뛴 사유를
    남긴다(동시 진입에서 중복 생성을 만들지 않는 쪽을 택한다).

    PostgreSQL이 아닌 드라이버(검사 대역 등)에서는 잠금 없이 진행한다. 이 경계가 지원하는
    실제 동시 진입은 PostgreSQL이다.
    """
    return _AdvisoryFixtureLock(fixture_id)


class _AdvisoryFixtureLock:
    """경기별 advisory lock. 획득 실패를 예외가 아니라 `acquired=False`로 알린다."""

    # 자동 생성 잠금 키 공간. 다른 advisory lock과 겹치지 않게 고정 접두부를 쓴다.
    NAMESPACE = 730_001

    def __init__(self, fixture_id: int) -> None:
        self.fixture_id = int(fixture_id)
        self.acquired = False
        self._connection = None
        # 잠금을 못 잡은 이유. `busy`(다른 실행이 보유)와 `unavailable`(연결 불가)를
        # 구분한다. 연결 불가는 "다른 곳에서 진행 중"이 아니라 실행 불가 사유다.
        self.reason: str | None = None
        self._locked = False

    def __enter__(self):
        from app.preview.db import get_engine

        try:
            connection = get_engine().connect()
        except Exception:  # noqa: BLE001 - 연결 불가는 실행 불가 사유로 남긴다
            self.reason = "unavailable"
            return self
        self._connection = connection
        try:
            self.acquired = bool(
                connection.execute(
                    text("SELECT pg_try_advisory_lock(:namespace, :key)"),
                    {"namespace": self.NAMESPACE, "key": self.fixture_id},
                ).scalar()
            )
            self._locked = self.acquired
            if not self.acquired:
                self.reason = "busy"
        except Exception:  # noqa: BLE001 - PostgreSQL이 아니면 잠금 없이 진행
            self.acquired = True
            self._locked = False
        return self

    def __exit__(self, exc_type, exc, tb):
        connection = self._connection
        self._connection = None
        try:
            if self._locked and connection is not None:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :key)"),
                    {"namespace": self.NAMESPACE, "key": self.fixture_id},
                )
        finally:
            if connection is not None:
                connection.close()
        return False


def preview_session_factory():
    """preview_dev 세션을 내는 **호출 가능 팩토리**(공개 계약).

    호출 계약은 하나다. `preview_session_factory()`가 `with`에 쓸 수 있는 `Session`을
    돌려준다. `app.db.SessionLocal`과 같은 단계이며, 그래서 `with preview_factory() as s`가
    성립한다.

    `app.preview.db.get_session_factory()`는 `sessionmaker` **인스턴스**를 돌려주며 그것은
    `__enter__`가 없어 `with`가 `TypeError`를 낸다. 그 값을 그대로 넘기면 후보마다 중복
    조회 단계에서 실패해 생성이 한 번도 시작되지 않는다. 그래서 그 인스턴스를 **부르는**
    얇은 함수로 감싼다(한 단계 차이를 여기서 흡수한다).
    """
    from app.preview.db import get_session_factory

    return get_session_factory()()


# 이전 이름 호환. 같은 계약(호출하면 Session)을 유지한다.
_default_preview_factory = preview_session_factory


def run_collection_generation(
    *,
    session_factory: Callable[[], Any],
    preview_session_factory: Callable[[], Any] | None = None,
    collection_status: str,
    now,
    transport: Any = None,
    reader: Any = None,
    fixture_ids: Sequence[int] | None = None,
    cycle_limit: int | None = None,
    cancelled: Callable[[], bool] | None = None,
    generate: Callable[..., Any] | None = None,
    fixture_lock: Callable[[int], Any] | None = None,
    # 호환용 인자. **더 이상 게이트로 쓰지 않는다**(수집 후 생성은 승인에 의존하지 않는다).
    # 기존 호출부가 넘겨도 생성이 막히지 않도록 시그니처만 유지한다.
    admission: Callable[[Callable[[], Any]], dict[str, Any]] | None = None,
    test_scope=None,
) -> dict[str, Any]:
    """수집 종료 뒤 프리뷰 생성을 시도하고, 수집 상태를 보존한 채 결과를 돌려준다.

    - `collection_status`는 **원래 수집 상태**다. 이 함수는 그것을 바꾸지 않는다.
    - 각 경기는 자기 세션에서 처리된다. 한 경기의 예외가 다음 경기를 막지 않는다.
    - `cancelled()`가 참이면 새 생성을 시작하지 않는다.

    반환은 원래 수집 상태와 별도인 생성 결과다.
    """
    result: dict[str, Any] = {
        "collection_status": collection_status,
        "state": "skipped",
        "reason": None,
        "candidates": 0,
        "generated": [],
        "skipped": [],
        "failed": [],
    }
    if cancelled is not None and cancelled():
        result["reason"] = "cancelled"
        return result

    # 시험 범위에서는 지정 경기별 탈락 사유를 결과에 남긴다.
    scope_skipped: list = []
    try:
        with session_factory() as session:
            candidates = collect_candidates(
                session,
                now=now,
                fixture_ids=fixture_ids,
                test_scope=test_scope,
                skipped=scope_skipped,
            )
    except Exception as exc:  # noqa: BLE001 - DB 후보 조회 실패를 성공으로 감추지 않는다
        result.update(state="failed", reason=f"candidate_query_failed: {type(exc).__name__}")
        return result

    if scope_skipped:
        # 경기별 사유를 결과에 보존한다(생성 후보가 비어도 어느 경기가 왜 빠졌는지 남는다).
        result["skipped"] = list(scope_skipped)
    limit = len(candidates) if cycle_limit is None else max(0, int(cycle_limit))
    selected, deferred = candidates[:limit], candidates[limit:]
    result["candidates"] = len(selected)
    result["deferred"] = [row["fixture_id"] for row in deferred]
    if not selected:
        result["reason"] = "no_candidates"
        return result
    if transport is None:
        # 모델 전송 없이 호출하면 파이프라인이 모의로 저장한다. 수집에서는 그렇게 하지
        # 않는다. 실행 불가 사유를 남기고 생성하지 않는다.
        result.update(state="failed", reason="model_transport_unconfigured")
        result["skipped"] = [row["fixture_id"] for row in selected]
        return result

    generate = generate or generate_match_preview
    # 후보·경기 자료는 공개 스키마 세션으로 읽고, **프리뷰 실행 기록과 생성 쓰기는
    # preview_dev 세션**으로 한다. 생성 파이프라인은 preview_dev 행을 쓴다.
    preview_factory = preview_session_factory or _default_preview_factory

    # 수집 후 자동 생성은 **워크플로우 승인에 의존하지 않는다**(사용자 확정: 승인은 AI 한글
    # 번역·선수 연결의 검수 상태이지 게시 허가가 아니다). 승인 행이 없거나 저장 버전이
    # 달라도 생성은 정상 호출되어야 하며, 승인 조회 실패를 생성 실패로 바꾸지 않는다.
    # 승인 행을 새로 만들거나 자동 승인하는 경로도 두지 않는다(의존 자체를 없앤다).
    for candidate in selected:
        fixture_id = candidate["fixture_id"]
        if cancelled is not None and cancelled():
            result["skipped"].append({"fixture_id": fixture_id, "reason": "cancelled"})
            continue
        # 조회와 생성 시작 사이의 경쟁을 경기 단위 잠금으로 닫는다. 잠금을 못 잡으면
        # 중복 생성을 만들지 않는 쪽을 택하고 사유를 남긴다.
        lock = (fixture_lock or _fixture_lock)(fixture_id)
        with lock:
            if not lock.acquired:
                # 연결 불가는 "다른 곳에서 진행 중"이 아니다. 실행 불가 사유로 남긴다.
                reason = (
                    "generation_lock_unavailable"
                    if getattr(lock, "reason", None) == "unavailable"
                    else "generation_in_progress_elsewhere"
                )
                result["skipped"].append({"fixture_id": fixture_id, "reason": reason})
                continue
            try:
                with preview_factory() as write_session:
                    existing = _already_generated(
                        write_session, fixture_id=fixture_id, label=candidate["label"]
                    )
            except Exception as exc:  # noqa: BLE001
                result["failed"].append(
                    {"fixture_id": fixture_id, "reason": f"dedup_query_failed: {type(exc).__name__}"}
                )
                continue
            if existing is not None:
                result["skipped"].append(
                    {"fixture_id": fixture_id, "reason": "already_generated_this_cycle", "run_id": existing}
                )
                continue
            generated = _generate_one(
                generate,
                preview_factory=preview_factory,
                candidate=candidate,
                reader=reader,
                transport=transport,
                result=result,
            )

    result["state"] = "finished"
    if not result["generated"] and result["failed"]:
        result["state"] = "failed"
    return result


def _generate_one(
    generate,
    *,
    preview_factory,
    candidate,
    reader,
    transport,
    result,
) -> bool:
    """경기 하나를 생성하고 결과를 기록한다. 예외는 그 경기의 실패로만 남긴다."""
    fixture_id = candidate["fixture_id"]
    try:
        with preview_factory() as write_session:
            outcome = generate(
                fixture_id=fixture_id,
                actor_id=None,
                trigger="collection",
                session=write_session,
                transport=transport,
                reader=reader,
                label=candidate["label"],
            )
            write_session.commit()
    except FixtureResolutionError as exc:
        result["failed"].append({"fixture_id": fixture_id, "reason": exc.reason})
        return True
    except Exception as exc:  # noqa: BLE001 - 한 경기 실패를 다음 경기로 넘긴다
        result["failed"].append(
            {"fixture_id": fixture_id, "reason": f"generation_failed: {type(exc).__name__}"}
        )
        return True
    # 예외 없이 돌아왔어도 **상태가 성공이 아니면** 생성 성공으로 세지 않는다.
    # 필수 섹션 본문을 만들지 못한 실행은 `RunStatus.FAILED`로 끝난다(파이프라인 계약).
    status = getattr(outcome, "status", None)
    run_id = str(getattr(outcome, "run_id", ""))
    if status is not None and status != RunStatus.SUCCEEDED:
        entry = {
            "fixture_id": fixture_id,
            "run_id": run_id,
            "reason": f"generation_status_{getattr(status, 'value', status)}",
            "detail": getattr(outcome, "unavailable_reason", None),
        }
        # 공통 수집이 예외로 끝났다면 그 진단을 함께 남긴다. 이 값이 없으면
        # `detail`의 "필수 섹션 없음"만 남아 첫 예외의 원인을 사후에 알 수 없다
        # (2026-11-19 실패에서 실제로 확인이 막혔다).
        collection_failure = getattr(outcome, "collection_failure", None)
        if collection_failure:
            entry["collection_failure"] = dict(collection_failure)
        result["failed"].append(entry)
        return True
    result["generated"].append(
        {
            "fixture_id": fixture_id,
            "run_id": run_id,
            "status": getattr(status, "value", None),
        }
    )
    return True


