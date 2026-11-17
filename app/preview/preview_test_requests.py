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

잠금 함수 서명(2026-11-17 정정):

- PostgreSQL 17이 실제로 제공하는 형태는 `pg_try_advisory_lock(bigint)`과
  `pg_try_advisory_lock(integer, integer)` 둘뿐이다. `(integer, bigint)` 조합은 없다.
  이전 코드는 해시 15자리 hex를 `key`로 넘겨 `(integer, bigint)` 호출이 되었고,
  `UndefinedFunction`이 났으며, 광범위한 `except`가 그 오류를 삼켜 **잠금 없이 생성을
  진행**했다. 그래서 정작 필요한 순간에 중복 호출이 가능했다. 지금은 **단일 bigint 인자**
  형태를 lock/unlock에 같이 쓰고, 키는 이 모듈 전용 상위 비트(구 namespace)와 해시 하위
  32비트를 합쳐 다른 잠금(일일 수집 등)과 겹치지 않게 한다.
- 잠금을 확인하지 못하면 **생성을 시작하지 않는다**(`RequestLockUnavailable`). 지원
  대상은 이 앱이 실제로 쓰는 PostgreSQL 하나이며, 다른 DB 조합으로 일반화하지 않는다.
  조용히 잠금 없이 진행하던 이전 동작은 제거했다.

소유 경계:

- 재전달 채택은 **같은 ADMIN의 실행**으로 제한한다(`find_requested_run`의 `actor_id`).
  다른 관리자의 실행을 내 요청의 결과로 돌려주지 않는다.
- 요청 표기는 서버가 label **끝에** 붙인다. 클라이언트가 보낸 label에 같은 표기가 있으면
  지우므로, label 문자열만 적어 다른 실행을 정상 재전달처럼 채택시킬 수 없다. 조회도
  마지막 표기(suffix)만 인정한다.

경계:

- 이 모듈은 `request_id`가 있을 때만 쓰인다. 없으면 기존 호출 경로가 그대로 동작한다.
- 재전달 응답은 **저장된 행만** 읽어 만든다. 재전송은 모델 호출 0회다.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.preview.models import PreviewRun

__all__ = [
    "ERROR_PREFIX",
    "MARKER_PREFIX",
    "REPLAY_NOTE",
    "RequestConflict",
    "RequestInFlight",
    "RequestLockUnavailable",
    "find_requested_run",
    "label_with_request",
    "replay_response",
    "request_lock",
    "request_marker",
]

# 실행 label에 붙는 요청 표기. 형식이 바뀌면 과거 요청과 이어지지 않으므로 고정한다.
MARKER_PREFIX = "request="

# 클라이언트가 보낸 label에서 지워야 하는, 실패를 알리는 서버 표기.
ERROR_PREFIX = "error="

REPLAY_NOTE = (
    "이미 접수된 요청입니다. 새 실행·모델 호출 없이 저장된 실행 결과를 돌려줍니다."
    " 새로 만들려면 새 request_id로 요청하세요."
)

# 잠금 키 공간. 이 잠금은 **단일 bigint** 키를 쓰므로 상위 비트로 갈래를 나눈다.
#
#   상위 32비트 = 잠금 종류(구 namespace 730_002를 그대로 옮겨 온다)
#   하위 32비트 = 요청 표기의 해시
#
# 다른 잠금은 이 조합을 쓰지 않는다(일일 수집 202605240001, 홈 프리뷰 (730_001, fixture)).
# PostgreSQL의 두 인자 형태는 `(integer, integer)`만 존재하므로 단일 키 형태로 넘긴다.
_LOCK_NAMESPACE = 730_002
_LOCK_KEY_SHIFT = 32
_LOCK_KEY_MASK = (1 << _LOCK_KEY_SHIFT) - 1


class RequestConflict(RuntimeError):
    """같은 request_id가 다른 경기·다른 실행 문맥으로 다시 쓰였다."""


class RequestInFlight(RuntimeError):
    """같은 request_id의 요청이 지금 처리 중이다."""


class RequestLockUnavailable(RuntimeError):
    """잠금을 확인할 수 없어 실행을 시작하지 않았다(모델 전송 전 중단)."""


def request_marker(request_id: Any) -> str:
    return f"{MARKER_PREFIX}{request_id}"


def sanitize_label(label: str | None) -> str | None:
    """클라이언트 label에서 **서버만 쓰는 표기**를 지운다.

    요청 표기는 재전달 채택의 근거다. 클라이언트가 label에 다른 요청의 표기를 적어
    보내면, 남의 실행이 내 요청의 결과로 채택될 수 있다. 그래서 서버는 표기를 **직접
    끝에 붙이고**, 클라이언트가 보낸 표기는 지운다(거부하지 않고 무시한다: label은
    표시용 자유 문자열이고 기존 호출부의 계약을 깨지 않는다).

    표기는 구분자 위치와 무관하게 지운다. 구분자(`·`)로만 나눠 지우면
    `foo request=<id>`처럼 구분자 없이 붙은 표기가 남아, 그 실행이 재전달 후보가 된다.
    """
    if label is None:
        return None
    text_value = str(label)
    for prefix in (MARKER_PREFIX, ERROR_PREFIX):
        text_value = re.sub(rf"{re.escape(prefix)}\S*", "", text_value)
    # 표기를 지운 자리에 남은 구분자·공백을 정리한다(빈 조각은 버린다).
    tokens = [token.strip() for token in text_value.replace("\n", " ").split("·")]
    cleaned = " · ".join(token for token in tokens if token)
    return cleaned or None


def label_with_request(label: str | None, request_id: Any, *, default: str) -> str:
    """실행 label에 요청 표기를 **한 번만, 끝에** 붙인 사본.

    클라이언트가 같은 표기를 보냈어도 지우고 다시 붙이므로, 표기가 앞이나 중간에 남아
    조회 접미사 판정과 어긋나지 않는다.
    """
    base = sanitize_label(label) or default
    return f"{base} · {request_marker(request_id)}"


def find_requested_run(
    session: Session, request_id: Any, *, actor_id: int | None = None
) -> PreviewRun | None:
    """이 request_id로 **같은 관리자가** 만든 실행. 없으면 `None`.

    조회는 표기로 시작하는 label을 좁힌 뒤, **label 끝의 표기가 정확히 이 요청**인 행만
    채택한다. 부분 일치(`request=<uuid>`가 다른 문자열의 앞부분인 경우)를 재전달로 읽지
    않는다. `actor_id`가 주어지면 그 관리자의 실행만 후보다(다른 관리자의 실행을 내 요청의
    결과로 돌려주지 않는다).

    `request_id`가 없는 과거 실행은 이 조회 대상이 아니다(기존 동작 보존).
    """
    marker = request_marker(request_id)
    statement = (
        select(PreviewRun)
        .where(PreviewRun.label.contains(marker, autoescape=True))
        .order_by(PreviewRun.requested_at.desc())
        .limit(20)
    )
    if actor_id is not None:
        statement = statement.where(PreviewRun.actor_id == int(actor_id))
    for row in session.scalars(statement):
        label = row.label or ""
        if label.endswith(marker):
            return row
    return None


def ensure_same_fixture(run: PreviewRun, *, fixture_id: int) -> None:
    """같은 request_id가 같은 경기의 실행인지 확인한다. 다르면 `RequestConflict`."""
    if run.fixture_id is None or int(run.fixture_id) != int(fixture_id):
        raise RequestConflict(
            f"같은 request_id가 다른 경기({run.fixture_id})로 이미 사용되었습니다."
            f" 이 요청은 경기 {fixture_id}입니다. 새 실행을 만들려면 새 request_id를 쓰세요."
        )


class request_lock:
    """같은 request_id의 동시 처리를 직렬화하는 최소 잠금.

    실제 동작:

    - **단일 bigint 인자** `pg_try_advisory_lock(key)` / `pg_advisory_unlock(key)`를 쓴다.
      두 인자 형태는 `(integer, bigint)` overload가 없어 실제 PostgreSQL에서 오류가 난다.
    - 잠금을 못 잡으면 `RequestInFlight`(다른 요청이 처리 중)다.
    - 연결·SQL 오류는 `RequestLockUnavailable`이며 **본문을 실행하지 않는다**. 이전처럼
      예외를 삼켜 잠금 없이 진행하지 않는다. 그 동작이 중복 모델 호출을 허용했다.
    - 해제는 잠금을 잡은 **같은 연결**에서 한다(advisory lock은 세션 단위다). 예외가
      나도 `finally`에서 해제하고 연결을 닫는다.
    """

    def __init__(self, request_id: Any) -> None:
        self.request_id = request_id
        self._connection = None
        self._locked = False

    def _key(self) -> int:
        """이 요청의 잠금 키(단일 bigint). 상위 32비트는 잠금 종류다."""
        digest = hashlib.sha256(str(self.request_id).encode()).digest()
        low = int.from_bytes(digest[:4], "big") & _LOCK_KEY_MASK
        return (_LOCK_NAMESPACE << _LOCK_KEY_SHIFT) | low

    def __enter__(self):
        from app.preview.db import get_engine

        try:
            self._connection = get_engine().connect()
        except Exception as exc:  # noqa: BLE001 - 연결 불가는 실행 불가 사유다
            raise RequestLockUnavailable(
                "요청 잠금을 확인할 수 없어 실행을 시작하지 않았습니다."
                " 모델 호출은 없었습니다."
            ) from exc
        try:
            acquired = bool(
                self._connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"), {"key": self._key()}
                ).scalar()
            )
        except Exception as exc:  # noqa: BLE001 - SQL 오류도 실행 불가 사유다
            # 잠금이 걸렸는지 알 수 없으므로 생성으로 진행하지 않는다. 연결은 닫는다.
            self.__exit__(exc, exc, exc.__traceback__)
            raise RequestLockUnavailable(
                "요청 잠금을 걸지 못해 실행을 시작하지 않았습니다."
                " 모델 호출은 없었습니다."
            ) from exc
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
        locked = self._locked
        self._locked = False
        try:
            if locked and connection is not None:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": self._key()}
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
