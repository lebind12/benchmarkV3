"""원문 아티팩트 저장과 비밀값 제거.

원칙:

- 저장 전에 비밀값을 제거한다. 저장 후 가리는 방식이 아니다. 저장소와 검사
  화면 어디에도 인증 토큰·API 키·비밀번호 원문이 남지 않아야 한다.
- 이름으로 지우는 것만으로는 부족하다. 원문 문자열에 섞여 들어온 `Bearer ...`
  같은 값도 지운다. 호출자가 아는 비밀값을 넘기면 그 값도 함께 지운다.
- 보관 기간이 지나면 본문만 지우고 요약·해시·기간은 남긴다. 만료는 "읽기 실패"와
  다른 상태이며 검사 화면에서 구분해야 한다.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy.orm import Session

from app.preview.contracts import RAW_ARTIFACT_RETENTION_DAYS, ArtifactKind, ArtifactRef
from app.preview.models import PreviewArtifact, PreviewWriteAudit

REDACTED = "[REDACTED]"

# 값 자체가 비밀인 키. 접미사 매칭으로 `x-goog-api-key`, `client_secret` 등을 잡는다.
_SECRET_KEY_SUFFIXES = (
    "authorization",
    "api_key",
    "apikey",
    "api-key",
    "x-api-key",
    "x-goog-api-key",
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "secret",
    "password",
    "password_hash",
    "passwd",
    "cookie",
    "set-cookie",
    "credential",
    "credentials",
    "private_key",
    "client_secret",
    "session_token",
    "auth",
    "signature",
)

_BEARER = re.compile(r"(?i)\b(bearer|token|apikey|api_key)\b(\s*[:=]?\s*)[A-Za-z0-9\-._~+/=]{6,}")
# libpq/SQLAlchemy DSN 안에 섞인 비밀번호.
_DSN_PASSWORD = re.compile(r"(?i)(://[^:/@\s]+:)([^@\s]+)(@)")
_JSON_ESCAPED = re.compile(r'(?i)"(authorization|x-api-key|x-goog-api-key|api-key|password|secret|token)"\s*:\s*"[^"]*"')

_SUMMARY_PREVIEW_CHARS = 600


def _is_secret_key(key: str) -> bool:
    lowered = key.strip().lower().replace(" ", "-")
    return any(lowered == suffix or lowered.endswith(suffix) for suffix in _SECRET_KEY_SUFFIXES)


def _scrub_text(text: str, secret_values: Iterable[str]) -> str:
    cleaned = text
    for value in secret_values:
        if value and len(value) >= 4:
            cleaned = cleaned.replace(value, REDACTED)
    cleaned = _BEARER.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", cleaned)
    cleaned = _DSN_PASSWORD.sub(lambda m: f"{m.group(1)}{REDACTED}{m.group(3)}", cleaned)
    cleaned = _JSON_ESCAPED.sub(lambda m: f'"{m.group(1)}": "{REDACTED}"', cleaned)
    return cleaned


def redact(value: Any, secret_values: Iterable[str] = ()) -> Any:
    """중첩 구조에서 비밀값을 제거한 사본을 돌려준다. 원본은 바꾸지 않는다."""
    secrets = [s for s in secret_values if isinstance(s, str) and s]

    def _walk(node: Any, key: str | None = None) -> Any:
        if isinstance(node, Mapping):
            return {
                str(k): (REDACTED if _is_secret_key(str(k)) else _walk(v, str(k)))
                for k, v in node.items()
            }
        if isinstance(node, (list, tuple)):
            return [_walk(item) for item in node]
        if isinstance(node, str):
            return _scrub_text(node, secrets)
        return node

    if isinstance(value, (bytes, bytearray)):
        return _scrub_text(value.decode("utf-8", "replace"), secrets)
    return _walk(value)


def _serialize(content: Any) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, sort_keys=True, default=str)


def _summary(kind: ArtifactKind, body: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "kind": kind.value,
        "char_count": len(body),
        "sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        summary["preview"] = body[:_SUMMARY_PREVIEW_CHARS]
        return summary
    if isinstance(parsed, Mapping):
        summary["top_level_keys"] = sorted(str(k) for k in parsed)
    summary["preview"] = body[:_SUMMARY_PREVIEW_CHARS]
    return summary


def save_artifact(
    session: Session,
    *,
    run_id: uuid.UUID | None,
    kind: ArtifactKind,
    content: Any,
    attempt_id: uuid.UUID | None = None,
    media_type: str = "application/json",
    retention_days: int = RAW_ARTIFACT_RETENTION_DAYS,
    secret_values: Iterable[str] = (),
    actor_id: int | None = None,
    now: datetime | None = None,
) -> PreviewArtifact:
    """비밀값을 제거한 원문을 저장한다. 반환값의 `body`가 실제 저장본이다."""
    moment = now or datetime.now(timezone.utc)
    redacted = redact(content, secret_values)
    body = _serialize(redacted)
    summary = _summary(kind, body)

    row = PreviewArtifact(
        run_id=run_id,
        attempt_id=attempt_id,
        kind=kind.value,
        media_type=media_type,
        byte_size=len(body.encode("utf-8")),
        sha256=summary["sha256"],
        redacted=True,
        body=body,
        summary=summary,
        created_at=moment,
        expires_at=moment + timedelta(days=retention_days),
    )
    session.add(row)
    session.flush()

    if run_id is not None:
        session.add(
            PreviewWriteAudit(
                run_id=run_id,
                actor_id=actor_id if actor_id is not None else 0,
                action="artifact_saved",
                target_table="preview_artifacts",
                target_id=str(row.id),
                detail={"kind": kind.value, "bytes": row.byte_size},
            )
        )
    return row


def artifact_ref(row: PreviewArtifact) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=row.id,
        kind=ArtifactKind(row.kind),
        media_type=row.media_type,
        byte_size=row.byte_size,
        sha256=row.sha256,
        redacted=row.redacted,
        created_at=row.created_at,
        expires_at=row.expires_at,
        expired_at=row.expired_at,
    )


def artifact_body(row: PreviewArtifact) -> str | None:
    """만료된 아티팩트는 본문 대신 `None`을 돌려준다. 요약은 남아 있다."""
    return row.body


def artifact_view(row: PreviewArtifact) -> dict[str, Any]:
    """검사 화면이 쓰는 아티팩트 표현. 만료와 읽기 실패를 구분한다."""
    ref = artifact_ref(row)
    return {
        **ref.to_dict(),
        "status": "available" if ref.available else "expired",
        "summary": row.summary,
        "body": row.body,
        "detail": None
        if ref.available
        else "보관 기간이 지나 원문을 열 수 없습니다. 요약과 해시는 남아 있습니다.",
    }
