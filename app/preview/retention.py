"""보관 기간 처리.

요구사항:

- 개발 기본값은 비밀값을 제거한 원문 30일, 구조화 실행·품질·지표 기록 180일이다.
  적용 시각과 기간을 표시하고, 원문이 사라진 뒤에는 재생 불가를 표시한다.
- 만료는 "읽기 실패"가 아니다. 요약·해시·기간은 남고 본문만 사라진다.
- 운영 DB에서 배포 정책 확정 전에 자동 삭제를 돌리지 않는다. 그래서 스케줄러를
  만들지 않는다. 만료 처리는 명시적으로 호출하는 함수 하나뿐이다.
- 구조화 기록은 이 단계에서 지우지 않는다. 보관 기간 값만 계약으로 고정하고
  삭제 경로는 만들지 않는다(180일 정책의 실행 시점은 배포 전에 다시 확인한다).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.preview.contracts import (
    RAW_ARTIFACT_RETENTION_DAYS,
    STRUCTURED_RECORD_RETENTION_DAYS,
)
from app.preview.models import PreviewArtifact, PreviewWriteAudit

__all__ = [
    "expire_raw_artifacts",
    "retention_policy",
    "retention_summary",
    "RAW_ARTIFACT_RETENTION_DAYS",
    "STRUCTURED_RECORD_RETENTION_DAYS",
]


def retention_policy() -> dict[str, Any]:
    """화면과 보고서가 같은 값을 보여주도록 한 곳에서 만든다."""
    return {
        "raw_artifact_days": RAW_ARTIFACT_RETENTION_DAYS,
        "structured_record_days": STRUCTURED_RECORD_RETENTION_DAYS,
        "raw_expiry_effect": "원문 본문 삭제, 요약·해시·기간 보존. 재생 불가로 표시",
        "structured_expiry_effect": "이 단계에서는 자동 삭제하지 않음. 기간 값만 고정",
        "automatic_purge": False,
        "note": "운영 자동 삭제 스케줄러는 배포 보관 정책 확정 전까지 두지 않는다",
    }


def expire_raw_artifacts(
    session: Session, *, now: datetime | None = None, run_id=None
) -> list[PreviewArtifact]:
    """보관 기간이 지난 원문 본문을 지운다.

    지운 아티팩트 목록을 돌려준다. 요약(`summary`)·해시·기간은 그대로 남는다.
    """
    moment = now or datetime.now(timezone.utc)
    statement = select(PreviewArtifact).where(
        PreviewArtifact.expires_at <= moment,
        PreviewArtifact.expired_at.is_(None),
    )
    if run_id is not None:
        statement = statement.where(PreviewArtifact.run_id == run_id)

    expired = list(session.scalars(statement))
    for row in expired:
        row.body = None
        row.expired_at = moment
        if row.run_id is not None:
            session.add(
                PreviewWriteAudit(
                    run_id=row.run_id,
                    actor_id=0,
                    action="artifact_expired",
                    target_table="preview_artifacts",
                    target_id=str(row.id),
                    detail={"kind": row.kind, "expires_at": row.expires_at.isoformat()},
                )
            )
    session.flush()
    return expired


def retention_summary(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """검사 화면 상단에 보여줄 보관 상태."""
    moment = now or datetime.now(timezone.utc)
    total = int(session.scalar(select(func.count()).select_from(PreviewArtifact)) or 0)
    expired = int(
        session.scalar(
            select(func.count())
            .select_from(PreviewArtifact)
            .where(PreviewArtifact.expired_at.is_not(None))
        )
        or 0
    )
    due = int(
        session.scalar(
            select(func.count())
            .select_from(PreviewArtifact)
            .where(
                PreviewArtifact.expired_at.is_(None),
                PreviewArtifact.expires_at <= moment,
            )
        )
        or 0
    )
    next_expiry = session.scalar(
        select(func.min(PreviewArtifact.expires_at)).where(
            PreviewArtifact.expired_at.is_(None)
        )
    )
    return {
        "artifacts": total,
        "expired": expired,
        "due_for_expiry": due,
        "next_expiry_at": next_expiry.isoformat() if next_expiry else None,
        "checked_at": moment.isoformat(),
        "policy": retention_policy(),
    }
