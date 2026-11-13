"""전송 사용량의 **내구성 있는 장부**(durable send ledger).

왜 필요한가:

- 이전 프로토타입에서 실제 전송이 있었는데도 응답 원문과 사용량이 **DB 롤백으로
  사라졌다**. 그래서 실행을 재시작하거나 후처리에서 예외가 나면 실제 전송 상한(8회)이
  초기화되는 것처럼 보였다.
- 이 장부는 **전송 직후, 후처리·정규화 전에** 별도 트랜잭션으로 커밋된다. 그래서
  이후에 어떤 예외가 나거나 실행 트랜잭션이 롤백돼도 "몇 번 보냈는지"와 redacted
  요청/응답은 남는다.

경계:

- 새 테이블·마이그레이션을 만들지 않는다. 기존 `preview_dev.preview_write_audit` 행이
  `run_id`에 FK가 없어 **실행 행이 아직 커밋되지 않았어도** 쓸 수 있다. 그래서 이
  장부는 실행 트랜잭션과 독립적으로 남는다.
- 시도 행(`preview_attempts`)과 원문 아티팩트는 FK가 실행 행을 가리킨다. 실행 행이
  아직 커밋되지 않았으면 넣을 수 없으므로, 그때는 redacted 원문을 장부 행의
  `detail`에 담아 **잃지 않는다**. 넣을 수 있으면 아티팩트로 남기고 장부에는 ID만 둔다.
- 값(비밀값)은 어디에도 남기지 않는다. `artifacts.redact`를 저장 직전에 한 번 더 쓴다.
- 장부 쓰기가 실패하면 **전송을 시작하지 않는다**(`SendJournalUnavailable`). 사용량이
  기록되지 않는 전송을 허용하면 상한이 다시 새는 구조가 되기 때문이다.

이 모듈은 외부 네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.preview import artifacts as artifact_store
from app.preview.contracts import ArtifactKind, RequestClass
from app.preview.models import PreviewRun, PreviewWriteAudit

__all__ = [
    "CHARGE_ACTION",
    "JournalOutcome",
    "SendJournalUnavailable",
    "bind_send_session_factory",
    "charged_model_attempts",
    "charged_requests",
    "journal_send",
    "reconcile_budget_from_journal",
    "unresolved_sends",
    "send_session_factory",
]

# 사용량 계수의 단일 근거. 이 action 이름이 바뀌면 과거 장부와 이어지지 않는다.
CHARGE_ACTION = "send_charged"

# 실행 행이 아직 커밋되지 않아 아티팩트를 만들 수 없을 때 `detail`에 담는 원문 상한.
# 이것은 진단용 사본이며, 정상 경로에서는 아티팩트가 원문을 보관한다.
_EMBEDDED_BODY_LIMIT = 200_000

_SESSION_FACTORY: sessionmaker | None = None


class SendJournalUnavailable(RuntimeError):
    """전송 사용량 장부를 쓸 수 없다. 전송을 시작하면 안 되는 상태다."""


def bind_send_session_factory(factory: sessionmaker) -> None:
    """장부 세션 팩토리. 테스트·실행기가 자기 DB로 고정할 때 쓴다."""
    global _SESSION_FACTORY
    _SESSION_FACTORY = factory


def send_session_factory() -> sessionmaker:
    if _SESSION_FACTORY is None:
        from app.preview.db import get_session_factory

        return get_session_factory()
    return _SESSION_FACTORY


@dataclass(frozen=True)
class JournalOutcome:
    """장부에 남긴 결과. `artifact_ids`는 FK가 커밋된 실행에서만 채워진다."""

    audit_id: uuid.UUID
    request_artifact_id: uuid.UUID | None = None
    response_artifact_id: uuid.UUID | None = None
    embedded_request: bool = False
    embedded_response: bool = False
    attempt_row_written: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": str(self.audit_id),
            "request_artifact_id": str(self.request_artifact_id)
            if self.request_artifact_id
            else None,
            "response_artifact_id": str(self.response_artifact_id)
            if self.response_artifact_id
            else None,
            "embedded_request": self.embedded_request,
            "embedded_response": self.embedded_response,
            "attempt_row_written": self.attempt_row_written,
        }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bounded(value: Any) -> Any:
    """장부에 담을 원문 크기를 제한한다. 잘렸다는 사실을 값으로 남긴다."""
    if isinstance(value, str):
        if len(value) <= _EMBEDDED_BODY_LIMIT:
            return value
        return {
            "truncated": True,
            "original_chars": len(value),
            "body": value[:_EMBEDDED_BODY_LIMIT],
        }
    if isinstance(value, Mapping):
        return {str(k): _bounded(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_bounded(item) for item in value]
    return value


def journal_send(
    *,
    run_id: uuid.UUID,
    actor_id: int,
    logical_call_id: str,
    attempt_ordinal: int,
    request_class: RequestClass,
    provider: str,
    model: str | None,
    mode: str,
    request_body: Any,
    response_body: Any = None,
    http_status: int | None = None,
    outcome: str = "pending",
    error_class: str | None = None,
    error_message: str | None = None,
    usage: Mapping[str, Any] | None = None,
    not_sent: bool = False,
    counts_toward_cap: bool = True,
    note: str | None = None,
    secret_values: Sequence[str] = (),
    now: datetime | None = None,
    session_factory: sessionmaker | None = None,
) -> JournalOutcome:
    """전송 한 건을 **독립 트랜잭션으로 커밋**한다.

    `not_sent=True`(설정 부족 등 실제 전송 없음)는 사용량으로 세지 않도록 `outcome`과
    `detail.not_sent`에 그 사실을 남긴다. 실제 전송보다 **먼저** 불러 상한을 지키고,
    응답을 받은 뒤 같은 논리 호출의 결과를 남길 때 다시 불러도 된다(둘 다 남는다).
    """
    moment = now or _now()
    redacted_request = artifact_store.redact(request_body, secret_values)
    redacted_response = (
        artifact_store.redact(response_body, secret_values)
        if response_body is not None
        else None
    )

    embedded_request = False
    embedded_response = False
    request_artifact_id: uuid.UUID | None = None
    response_artifact_id: uuid.UUID | None = None

    # 실행 세션이 있으면 **그 세션과 같은 DB**에 쓴다. 전역 팩토리에 의존하면 실행이
    # 다른 DB로 간 경우(테스트·다중 대상) 장부가 엉뚱한 곳에 남거나 실패한다.
    factory = session_factory or send_session_factory()
    session: Session = factory()
    try:
        # 실행 행이 커밋돼 있으면 FK가 걸린 아티팩트를 만들 수 있다. 아니면 장부에 담는다.
        # 커밋되지 않은 실행 행을 참조하면 FK 검사가 그 트랜잭션을 기다리며 멈출 수 있으므로,
        # 먼저 별도 트랜잭션에서 실행 행이 **보이는지** 확인한다. 안 보이면 아티팩트를 만들지
        # 않고 redacted 원문을 장부 행에 담는다(원문 유실 없음).
        try:
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            visible = session.scalar(
                select(PreviewRun.id).where(PreviewRun.id == run_id)
            )
            if visible is None:
                raise LookupError("run row is not committed yet")
            request_row = artifact_store.save_artifact(
                session,
                run_id=run_id,
                kind=ArtifactKind.RAW_REQUEST,
                content=request_body,
                media_type="application/json",
                secret_values=secret_values,
                actor_id=actor_id,
                now=moment,
            )
            request_artifact_id = request_row.id
            if redacted_response is not None:
                response_row = artifact_store.save_artifact(
                    session,
                    run_id=run_id,
                    kind=ArtifactKind.RAW_RESPONSE,
                    content=response_body,
                    media_type="application/json",
                    secret_values=secret_values,
                    actor_id=actor_id,
                    now=moment,
                )
                response_artifact_id = response_row.id
            session.flush()
        except Exception:  # noqa: BLE001 - FK 위반 포함. 장부에 직접 담는다.
            session.rollback()
            embedded_request = True
            embedded_response = redacted_response is not None

        # 상한에 세는 것은 **실제 live 요청 1건**뿐이다. 같은 요청의 결과 행은 세지 않는다.
        counted = bool(counts_toward_cap) and mode == "live" and not bool(not_sent)
        detail: dict[str, Any] = {
            "logical_call_id": logical_call_id,
            "counted": counted,
            "attempt_ordinal": int(attempt_ordinal),
            "request_class": request_class.value,
            "provider": provider,
            "model": model,
            "mode": mode,
            "http_status": http_status,
            "outcome": outcome,
            "error_class": error_class,
            "error_message": error_message,
            "usage": dict(usage) if usage else None,
            "not_sent": bool(not_sent),
            "request_artifact_id": str(request_artifact_id) if request_artifact_id else None,
            "response_artifact_id": str(response_artifact_id)
            if response_artifact_id
            else None,
            "journal_note": note,
        }
        if embedded_request:
            detail["request_body"] = _bounded(redacted_request)
        if embedded_response:
            detail["response_body"] = _bounded(redacted_response)

        row = PreviewWriteAudit(
            run_id=run_id,
            actor_id=actor_id,
            action=CHARGE_ACTION,
            target_table="preview_attempts",
            target_id=None,
            detail=detail,
            created_at=moment,
        )
        session.add(row)
        session.commit()
        return JournalOutcome(
            audit_id=row.id,
            request_artifact_id=request_artifact_id,
            response_artifact_id=response_artifact_id,
            embedded_request=embedded_request,
            embedded_response=embedded_response,
        )
    except Exception as exc:  # noqa: BLE001 - 장부 없이는 전송하지 않는다
        session.rollback()
        raise SendJournalUnavailable(
            f"전송 사용량 장부를 기록하지 못해 요청을 보내지 않았습니다: {exc}"
        ) from None
    finally:
        session.close()


def charged_requests(
    session: Session,
    *,
    run_id: uuid.UUID,
    request_class: RequestClass | None = None,
) -> int:
    """장부에 남은 **실제 전송** 수. `not_sent` 행은 세지 않는다."""
    statement = select(PreviewWriteAudit).where(
        PreviewWriteAudit.run_id == run_id,
        PreviewWriteAudit.action == CHARGE_ACTION,
    )
    counted = 0
    for row in session.scalars(statement):
        detail = dict(row.detail or {})
        if not detail.get("counted"):
            continue
        if request_class is not None and detail.get("request_class") != request_class.value:
            continue
        counted += 1
    return counted


def charged_model_attempts(
    session: Session, *, run_id: uuid.UUID, logical_call_id: str
) -> int:
    """논리 호출 하나의 실제 전송 시도 수(장부 기준)."""
    statement = select(PreviewWriteAudit).where(
        PreviewWriteAudit.run_id == run_id,
        PreviewWriteAudit.action == CHARGE_ACTION,
    )
    counted = 0
    for row in session.scalars(statement):
        detail = dict(row.detail or {})
        if not detail.get("counted"):
            continue
        if detail.get("request_class") != RequestClass.MODEL.value:
            continue
        if str(detail.get("logical_call_id")) == logical_call_id:
            counted += 1
    return counted


def reconcile_budget_from_journal(
    budget: Any,
    session: Session,
    *,
    run_id: uuid.UUID,
) -> dict[str, Any]:
    """재개·재시작 뒤 예산을 장부와 맞춘다. 8회 상한을 새로 주지 않는다.

    인메모리 예산이 장부보다 적게 세고 있으면(프로세스 재시작·롤백) 장부 값을 채택한다.
    반대 방향(장부가 더 적음)은 인메모리 값을 유지한다. 즉 **둘 중 큰 값**을 쓴다.
    """
    journal_model = charged_requests(
        session, run_id=run_id, request_class=RequestClass.MODEL
    )
    journal_api = charged_requests(
        session, run_id=run_id, request_class=RequestClass.API
    )
    adjusted = {
        "model_used_before": int(getattr(budget, "model_used", 0)),
        "api_used_before": int(getattr(budget, "api_used", 0)),
        "journal_model_used": journal_model,
        "journal_api_used": journal_api,
        "raised_from_journal": False,
    }
    if journal_model > budget.model_used:
        budget.model_used = journal_model
        adjusted["raised_from_journal"] = True
    if journal_api > budget.api_used:
        budget.api_used = journal_api
        adjusted["raised_from_journal"] = True
    adjusted["model_used_after"] = int(budget.model_used)
    adjusted["api_used_after"] = int(budget.api_used)
    return adjusted


def unresolved_sends(
    session: Session, *, run_id: uuid.UUID
) -> tuple[dict[str, Any], ...]:
    """전송 **전** 예약만 남고 결과 행이 없는 전송들.

    프로세스가 전송 직전·직후에 죽으면 이 상태가 된다. 이런 전송은 **이미 사용량으로
    세었다**(상한을 잃지 않기 위한 보수적 선택). 이 함수는 그 사실을 보고에 드러내는
    용도이며, 결과를 "성공"이나 "실패"로 단정하지 않는다.
    """
    statement = select(PreviewWriteAudit).where(
        PreviewWriteAudit.run_id == run_id,
        PreviewWriteAudit.action == CHARGE_ACTION,
    ).order_by(PreviewWriteAudit.created_at)
    reserved: dict[tuple[str, int], dict[str, Any]] = {}
    resolved: set[tuple[str, int]] = set()
    for row in session.scalars(statement):
        detail = dict(row.detail or {})
        if detail.get("request_class") != RequestClass.MODEL.value:
            continue
        key = (str(detail.get("logical_call_id")), int(detail.get("attempt_ordinal") or 0))
        if detail.get("outcome") == "pending":
            reserved[key] = {**detail, "audit_id": str(row.id)}
        else:
            resolved.add(key)
    return tuple(
        {**value, "note": "전송 후 결과 행이 없습니다. 사용량으로는 세었습니다."}
        for key, value in reserved.items()
        if key not in resolved
    )


def audit_row_count(session: Session, *, run_id: uuid.UUID) -> int:
    """장부 행 수(검사·테스트용)."""
    return int(
        session.scalar(
            select(func.count())
            .select_from(PreviewWriteAudit)
            .where(
                PreviewWriteAudit.run_id == run_id,
                PreviewWriteAudit.action == CHARGE_ACTION,
            )
        )
        or 0
    )
