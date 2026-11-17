"""bundle 실행 요청 식별자(`request_id`)의 중복 경계.

왜 필요한가:

- 화면이 같은 생성 요청을 두 번 보내면(더블클릭, 새로고침 뒤 재전송, 응답 유실 뒤
  사용자의 재시도) 모델 호출이 두 번 나가고 결과가 두 벌 저장된다.
- `request_id`는 **사용자 요청 한 건**의 식별자다. 같은 값의 재전달은 새 실행을 만들지
  않고 이미 접수된 실행을 그대로 돌려주며, 같은 값을 다른 경기에 쓰면 409다.

저장 구조(새 표·마이그레이션 없음):

- 실행마다 붙는 기존 `preview_dev.preview_runs.label`에 요청 표기를 넣는다. label은
  **실행 행과 같은 트랜잭션**에서 저장되므로(`store.store_run` → `session.commit()`),
  "실행은 저장됐는데 요청 장부는 없는" 창이 생기지 않는다. 그래서 응답이 유실된 뒤의
  재전달도 새 모델 호출을 만들지 않는다.
- 지금 처리 중인 같은 요청은 이 저장소가 이미 쓰는 `pg_try_advisory_lock` 패턴으로
  막는다. 두 번째 동시 요청은 기다리지 않고 409다(중복 호출을 만들지 않는 쪽을 택한다).

경계:

- 이 모듈은 `request_id`가 있을 때만 쓰인다. 없으면 기존 호출 경로가 그대로 동작한다.
- 재전달 응답은 **저장된 행만** 읽어 만든다. 재전송은 모델 호출 0회다.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.preview.models import PreviewRun

__all__ = [
    "MARKER_PREFIX",
    "REPLAY_NOTE",
    "RequestConflict",
    "RequestInFlight",
    "find_requested_run",
    "label_with_request",
    "replay_response",
    "request_lock",
    "request_marker",
]

# 실행 label에 붙는 요청 표기. 형식이 바뀌면 과거 요청과 이어지지 않으므로 고정한다.
MARKER_PREFIX = "request="

REPLAY_NOTE = (
    "이미 접수된 요청입니다. 새 실행·모델 호출 없이 저장된 실행 결과를 돌려줍니다."
    " 새로 만들려면 새 request_id로 요청하세요."
)

# 잠금 키 공간. 다른 advisory lock과 겹치지 않게 고정 접두부를 쓴다.
_LOCK_NAMESPACE = 730_002


class RequestConflict(RuntimeError):
    """같은 request_id가 다른 경기·다른 실행 문맥으로 다시 쓰였다."""


class RequestInFlight(RuntimeError):
    """같은 request_id의 요청이 지금 처리 중이다."""


def request_marker(request_id: Any) -> str:
    return f"{MARKER_PREFIX}{request_id}"


def label_with_request(label: str | None, request_id: Any, *, default: str) -> str:
    """실행 label에 요청 표기를 붙인 사본. 이미 있으면 다시 붙이지 않는다."""
    base = label or default
    marker = request_marker(request_id)
    if marker in base:
        return base
    return f"{base} · {marker}"


def find_requested_run(session: Session, request_id: Any) -> PreviewRun | None:
    """이 request_id로 이미 만들어진 실행. 없으면 `None`. 저장된 행만 읽는다."""
    return session.scalar(
        select(PreviewRun)
        .where(PreviewRun.label.contains(request_marker(request_id), autoescape=True))
        .order_by(PreviewRun.requested_at.desc())
        .limit(1)
    )


def ensure_same_fixture(run: PreviewRun, *, fixture_id: int) -> None:
    """같은 request_id가 같은 경기의 실행인지 확인한다. 다르면 `RequestConflict`."""
    if run.fixture_id is None or int(run.fixture_id) != int(fixture_id):
        raise RequestConflict(
            f"같은 request_id가 다른 경기({run.fixture_id})로 이미 사용되었습니다."
            f" 이 요청은 경기 {fixture_id}입니다. 새 실행을 만들려면 새 request_id를 쓰세요."
        )


class request_lock:
    """같은 request_id의 동시 처리를 직렬화하는 최소 잠금.

    잠금을 못 잡으면 `RequestInFlight`다. PostgreSQL이 아닌 드라이버(검사 대역)에서는
    잠금 없이 진행한다. 이 경계가 지원하는 실제 동시 진입은 PostgreSQL이다.
    """

    def __init__(self, request_id: Any) -> None:
        self.request_id = request_id
        self._connection = None
        self._locked = False

    def _key(self) -> int:
        digest = hashlib.sha256(str(self.request_id).encode()).hexdigest()
        return int(digest[:15], 16)

    def __enter__(self):
        from app.preview.db import get_engine

        try:
            self._connection = get_engine().connect()
        except Exception:  # noqa: BLE001 - 연결 불가는 처리할 수 없는 요청 상태다
            raise RequestInFlight(
                "요청 잠금을 확인할 수 없어 실행을 시작하지 않았습니다."
            ) from None
        try:
            acquired = bool(
                self._connection.execute(
                    text("SELECT pg_try_advisory_lock(:namespace, :key)"),
                    {"namespace": _LOCK_NAMESPACE, "key": self._key()},
                ).scalar()
            )
        except Exception:  # noqa: BLE001 - PostgreSQL이 아니면 잠금 없이 진행
            return self
        if not acquired:
            self.__exit__(None, None, None)
            raise RequestInFlight(
                "같은 request_id의 요청이 처리 중입니다. 끝난 뒤 결과를 다시 조회하세요."
            )
        self._locked = True
        return self

    def __exit__(self, exc_type, exc, tb):
        connection = self._connection
        self._connection = None
        try:
            if self._locked and connection is not None:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:namespace, :key)"),
                    {"namespace": _LOCK_NAMESPACE, "key": self._key()},
                )
        finally:
            if connection is not None:
                connection.close()
        return False


def replay_response(session: Session, run_id: Any) -> dict[str, Any] | None:
    """저장된 실행 하나를 `bundle-runs` 응답 모양으로 되살린다. 모델 호출 0회.

    실행 행이 없으면 `None`. 본문은 읽지 않고, 묶음 요약과 섹션 결과의 상태 값만 쓴다.
    """
    from app.preview import store

    run_uuid = uuid.UUID(str(run_id))
    row = session.get(PreviewRun, run_uuid)
    if row is None:
        return None
    bundle = store.load_information_bundle(session, run_uuid)
    summary = dict(bundle.get("summary") or {})
    section_result_ids: dict[str, str] = {}
    section_quality: dict[str, str] = {}
    section_unavailable: dict[str, str] = {}
    for section in store.list_section_results(session, run_uuid):
        workflow_id = str(section.get("workflow_id") or "")
        if not workflow_id:
            continue
        section_result_ids[workflow_id] = str(section["section_result_id"])
        section_quality[workflow_id] = str(section.get("quality") or "")
        reason = section.get("unavailable_reason")
        if reason:
            section_unavailable[workflow_id] = str(reason)
    ledger = store.run_send_ledger_summary(session, run_uuid)
    return {
        "run_id": str(row.id),
        "mode": row.mode,
        "status": row.status,
        "quality": row.quality,
        "bundle_id": summary.get("bundle_id"),
        "bundle_hash": summary.get("bundle_hash"),
        "bundle_artifact_id": bundle.get("artifact_id") if bundle.get("available") else None,
        "section_result_ids": section_result_ids,
        "section_quality": section_quality,
        "section_unavailable": section_unavailable,
        "discovery_status": {
            str(key): str(value)
            for key, value in (summary.get("discovery_groups") or {}).items()
        },
        "external_calls": int(ledger.get("charged_requests") or 0),
        "budget": {},
        "unavailable_reason": row.failure_detail,
        "note": REPLAY_NOTE,
    }
