"""Public DB-only home preview routes; GET never invokes external adapters."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.services import home_preview

router = APIRouter(prefix="/api/v1/home", tags=["home-preview"])
Db = Annotated[Session, Depends(db.get_db_session)]


@router.get("/recommendations")
def recommendations(session: Db, date_: Annotated[date | None, Query(alias="date")] = None):
    try:
        return home_preview.recommendations(session, date_)
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "home_preview_storage_unavailable") from None


@router.get("/fixtures/{external_id}/prematch")
def prematch(session: Db, external_id: Annotated[int, Path(gt=0)]):
    try:
        return home_preview.read_preview(session, external_id)
    except LookupError:
        raise HTTPException(404, "fixture_not_found") from None
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "home_preview_storage_unavailable") from None
