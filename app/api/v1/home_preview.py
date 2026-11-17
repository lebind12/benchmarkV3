"""Public DB-only home preview routes; GET never invokes external adapters."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import db
from app.preview import db as preview_db
from app.services import home_preview, home_preview_document

router = APIRouter(prefix="/api/v1/home", tags=["home-preview"])
Db = Annotated[Session, Depends(db.get_db_session)]
StoredDb = Annotated[Session, Depends(preview_db.get_db)]


@router.get("/recommendations")
def recommendations(
    session: Db,
    stored: StoredDb,
    date_: Annotated[date | None, Query(alias="date")] = None,
):
    try:
        return home_preview.recommendations(session, date_, stored_session=stored)
    except (SQLAlchemyError, ValueError, home_preview_document.PreviewDocumentUnavailable):
        raise HTTPException(503, "home_preview_storage_unavailable") from None


@router.get("/fixtures/{external_id}/prematch")
def prematch(session: Db, external_id: Annotated[int, Path(gt=0)]):
    try:
        return home_preview.read_preview(session, external_id)
    except LookupError:
        raise HTTPException(404, "fixture_not_found") from None
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "home_preview_storage_unavailable") from None


def _fixture_display(session: Session, external_id: int) -> dict:
    """공개 표시에 필요한 경기·팀 값. 내부 기본키는 내보내지 않는다."""
    fixture = home_preview.fixture_by_external(session, external_id)
    teams, translations = home_preview.names(session)
    league = session.get(home_preview.League, fixture.league_id)
    home = teams.get(fixture.home_team_id)
    away = teams.get(fixture.away_team_id)

    def side(team):
        if team is None:
            return None
        from app.preview.section_structured import team_logo_url

        return {
            "external_id": team.external_id,
            "name": translations.get(team.id) or team.name,
            "logo_url": team_logo_url(team.external_id),
        }

    return {
        "external_id": external_id,
        "kickoff_at": fixture.kickoff_at.isoformat(),
        "league": league.name if league else None,
        "home": side(home),
        "away": side(away),
    }


@router.get("/fixtures/{external_id}/document")
def document(session: Db, stored: StoredDb, external_id: Annotated[int, Path(gt=0)]):
    """이 경기의 최신 공개 가능 저장 문서. 읽기 전용이며 외부 호출이 없다.

    문서 없음(`status=none`)과 저장소 읽기 실패(503)를 구분한다. 6시간 안내는 문서가
    없을 때의 안내이며 저장본 표시 제한이 아니다.
    """
    try:
        fixture = _fixture_display(session, external_id)
    except LookupError:
        raise HTTPException(404, "fixture_not_found") from None
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "home_preview_storage_unavailable") from None
    try:
        return home_preview_document.read_document(
            stored, external_id, fixtures=fixture
        )
    except home_preview_document.PreviewDocumentUnavailable:
        raise HTTPException(503, "home_preview_document_unavailable") from None
    except (SQLAlchemyError, ValueError):
        raise HTTPException(503, "home_preview_document_unavailable") from None
