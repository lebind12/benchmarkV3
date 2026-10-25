"""Prune only this feature's storage; shared football entities are never deleted."""

from sqlalchemy import delete, func, select

from app.models import Fixture, League, LeagueSyncTarget
from app.models.home_preview import (
    HomePreviewAttempt,
    HomePreviewPublication,
    HomePreviewSnapshot,
    HomePreviewVersion,
)


def prune_home_previews(session, *, dry_run=True):
    current = {league.id: league.current_season for league in session.scalars(select(League))}
    years = {}
    for target in session.scalars(select(LeagueSyncTarget)):
        if (
            current.get(target.league_id) is not None
            and target.season_year <= current[target.league_id]
        ):
            years.setdefault(target.league_id, set()).add(target.season_year)
    lower = {
        league_id: sorted(seasons, reverse=True)[1]
        for league_id, seasons in years.items()
        if len(seasons) >= 2
    }
    cached = (
        set(session.scalars(select(HomePreviewSnapshot.fixture_id)))
        | set(session.scalars(select(HomePreviewPublication.fixture_id)))
        | set(session.scalars(select(HomePreviewAttempt.fixture_id)))
    )
    expired = (
        [
            (row.id, row.external_id)
            for row in session.scalars(select(Fixture).where(Fixture.id.in_(cached)))
            if row.league_id in lower and row.season_year < lower[row.league_id]
        ]
        if cached
        else []
    )
    ids = [row[0] for row in expired]
    models = (HomePreviewPublication, HomePreviewAttempt, HomePreviewVersion, HomePreviewSnapshot)
    counts = {
        model.__tablename__: session.scalar(
            select(func.count()).select_from(model).where(model.fixture_id.in_(ids))
        )
        if ids
        else 0
        for model in models
    }
    if not dry_run and ids:
        for model in models:
            session.execute(delete(model).where(model.fixture_id.in_(ids)))
        session.commit()
    return {
        "state": "retention_plan" if dry_run else "retention_applied",
        "fixture_ids": [row[1] for row in expired],
        "counts": counts,
    }
