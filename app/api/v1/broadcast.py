"""Broadcast support endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import db
from app.services import broadcast as broadcast_service


router = APIRouter(prefix="/api/v1/broadcast", tags=["broadcast"])


DbSession = Annotated[Session, Depends(db.get_db_session)]


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
