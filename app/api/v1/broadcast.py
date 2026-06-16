"""Broadcast support endpoints."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import db
from app.services import broadcast as broadcast_service
from app.services import broadcast_program as broadcast_program_service
from app.services.broadcast import ALLOWED_BROADCAST_LEAGUE_SLUGS


router = APIRouter(prefix="/api/v1/broadcast", tags=["broadcast"])


DbSession = Annotated[Session, Depends(db.get_db_session)]


@dataclass(frozen=True)
class BroadcastCurrentUser:
    role: str
    user_id: int | str | None = None


class BroadcastAiReviewRequest(BaseModel):
    forceRefresh: bool = Field(default=False)


def _b64url_decode(value: str) -> bytes:
    value += "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value.encode("ascii"))


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_verified_jwt_payload(token: str) -> dict[str, Any]:
    secret = os.environ.get("JWT_SECRET") or os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(status_code=401, detail="auth_not_configured")
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=401, detail="invalid_token")
    try:
        header = json.loads(_b64url_decode(parts[0]))
        decoded = _b64url_decode(parts[1])
        data = json.loads(decoded)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid_token") from None
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise HTTPException(status_code=401, detail="unsupported_token")
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(_b64url_encode(expected), parts[2]):
        raise HTTPException(status_code=401, detail="invalid_token")
    if not isinstance(data, dict):
        raise HTTPException(status_code=401, detail="invalid_token")
    exp = data.get("exp")
    if isinstance(exp, (int, float)) and exp < time.time():
        raise HTTPException(status_code=401, detail="token_expired")
    return data


def get_broadcast_current_user(
    authorization: str | None = Header(default=None),
    x_mock_role: str | None = Header(default=None),
) -> BroadcastCurrentUser:
    normalized_mock_role = (
        x_mock_role.strip().upper()
        if isinstance(x_mock_role, str)
        else None
    )

    if not authorization or not authorization.lower().startswith("bearer "):
        if normalized_mock_role == "ADMIN":
            return BroadcastCurrentUser(role=normalized_mock_role, user_id="mock")
        raise HTTPException(status_code=401, detail="not_authenticated")

    token = authorization.split(" ", 1)[1].strip()
    claims = _decode_verified_jwt_payload(token)
    role = claims.get("role") or claims.get("app_role")
    if not isinstance(role, str):
        raise HTTPException(status_code=401, detail="invalid_token")
    user_id = claims.get("user_id") or claims.get("sub")
    return BroadcastCurrentUser(role=role, user_id=user_id)


def get_broadcast_api_football_client():
    return broadcast_service.make_broadcast_api_football_client()


def get_broadcast_cache():
    return broadcast_service.make_broadcast_cache()


def get_broadcast_overlay_service(
    session: DbSession,
    api_client: Annotated[Any, Depends(get_broadcast_api_football_client)],
    cache: Annotated[Any, Depends(get_broadcast_cache)],
):
    return broadcast_service.BroadcastOverlayService(
        session,
        api_client=api_client,
        cache=cache,
    )


BroadcastOverlayService = Annotated[Any, Depends(get_broadcast_overlay_service)]


def get_broadcast_program_snapshot_service(
    session: DbSession,
    api_client: Annotated[Any, Depends(get_broadcast_api_football_client)],
    cache: Annotated[Any, Depends(get_broadcast_cache)],
):
    return broadcast_program_service.BroadcastProgramSnapshotService(
        session,
        api_client=api_client,
        cache=cache,
    )


BroadcastProgramSnapshotService = Annotated[Any, Depends(get_broadcast_program_snapshot_service)]


class BroadcastTranslationRequest(BaseModel):
    league_ids: list[int] = Field(default_factory=list, max_length=500)
    league_names: list[str] = Field(default_factory=list, max_length=500)
    team_ids: list[int] = Field(default_factory=list, max_length=500)
    team_names: list[str] = Field(default_factory=list, max_length=500)
    player_ids: list[int] = Field(default_factory=list, max_length=500)
    player_names: list[str] = Field(default_factory=list, max_length=500)
    coach_ids: list[int] = Field(default_factory=list, max_length=500)
    coach_names: list[str] = Field(default_factory=list, max_length=500)


@router.post("/translations")
def broadcast_translations(payload: BroadcastTranslationRequest, session: DbSession):
    return broadcast_service.lookup_broadcast_translations(
        session,
        league_ids=payload.league_ids,
        league_names=payload.league_names,
        team_ids=payload.team_ids,
        team_names=payload.team_names,
        player_ids=payload.player_ids,
        player_names=payload.player_names,
        coach_ids=payload.coach_ids,
        coach_names=payload.coach_names,
    )


@router.get("/fixtures/{external_id}/overlay")
def broadcast_fixture_overlay(
    external_id: int,
    current_user: Annotated[Any, Depends(get_broadcast_current_user)],
    service: BroadcastOverlayService,
    league_slug: str | None = Query(default=None),
):
    if league_slug is not None and league_slug not in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail="unsupported league_slug")
    role = getattr(current_user, "role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        payload = service.get_overlay(
            external_id,
            current_user,
            league_slug=league_slug,
        )
    except broadcast_service.BroadcastOverlayError:
        raise HTTPException(status_code=502, detail="broadcast_upstream_unavailable")
    if payload is None:
        raise HTTPException(status_code=404, detail="fixture_not_found")
    return payload


@router.get("/program-snapshot/first-live")
def broadcast_first_live_program_snapshot(
    current_user: Annotated[Any, Depends(get_broadcast_current_user)],
    service: BroadcastProgramSnapshotService,
    league_slug: str | None = Query(default=None),
):
    if league_slug is not None and league_slug not in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail="unsupported league_slug")
    role = getattr(current_user, "role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        payload = service.get_first_live_snapshot(league_slug=league_slug)
    except broadcast_service.BroadcastOverlayError:
        raise HTTPException(status_code=502, detail="broadcast_upstream_unavailable")
    if payload is None:
        raise HTTPException(status_code=404, detail="fixture_not_found")
    return payload


@router.get("/fixtures/{external_id}/program-snapshot")
def broadcast_fixture_program_snapshot(
    external_id: int,
    current_user: Annotated[Any, Depends(get_broadcast_current_user)],
    service: BroadcastProgramSnapshotService,
    league_slug: str | None = Query(default=None),
):
    if league_slug is not None and league_slug not in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail="unsupported league_slug")
    role = getattr(current_user, "role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        payload = service.get_snapshot(external_id, league_slug=league_slug)
    except broadcast_service.BroadcastOverlayError:
        raise HTTPException(status_code=502, detail="broadcast_upstream_unavailable")
    if payload is None:
        raise HTTPException(status_code=404, detail="fixture_not_found")
    return payload


@router.post("/fixtures/{external_id}/ai-review")
def broadcast_fixture_ai_review(
    external_id: int,
    current_user: Annotated[Any, Depends(get_broadcast_current_user)],
    service: BroadcastProgramSnapshotService,
    league_slug: str | None = Query(default=None),
    request: BroadcastAiReviewRequest | None = None,
):
    if league_slug is not None and league_slug not in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail="unsupported league_slug")
    role = getattr(current_user, "role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        return service.generate_ai_review(
            external_id,
            league_slug=league_slug,
            force_refresh=bool(request.forceRefresh) if request else False,
        )
    except broadcast_service.BroadcastOverlayError as exc:
        if str(exc) == "fixture_not_found":
            raise HTTPException(status_code=404, detail="fixture_not_found") from exc
        raise HTTPException(status_code=502, detail="broadcast_upstream_unavailable") from exc


@router.post("/fixtures/{external_id}/match-preview")
def broadcast_fixture_match_preview(
    external_id: int,
    current_user: Annotated[Any, Depends(get_broadcast_current_user)],
    service: BroadcastProgramSnapshotService,
    league_slug: str | None = Query(default=None),
):
    if league_slug is not None and league_slug not in ALLOWED_BROADCAST_LEAGUE_SLUGS:
        raise HTTPException(status_code=422, detail="unsupported league_slug")
    role = getattr(current_user, "role", None)
    if role != "ADMIN":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        return service.generate_match_preview(
            external_id,
            league_slug=league_slug,
        )
    except broadcast_service.BroadcastOverlayError as exc:
        if str(exc) == "fixture_not_found":
            raise HTTPException(status_code=404, detail="fixture_not_found") from exc
        raise HTTPException(status_code=502, detail="broadcast_upstream_unavailable") from exc
