"""Post-collection home preview execution. No independent polling worker."""

from datetime import timedelta

from app.core.config import get_settings
from app.services.home_preview import eligible_rows
from app.services.home_preview_api_football import ApiFootballPreviewEvidence
from app.services.home_preview_generation import process_fixture
from app.services.home_preview_policy import utcnow
from app.services.home_preview_production import ProductionPreviewGenerator
from app.services.home_preview_retry import ModelRun
from app.services.home_preview_vertex import VertexPreviewProvider
from app.workers.daily_sync.api import ApiFootballClient


def run_cycle(
    session_factory,
    *,
    settings=None,
    execute=False,
    clock=utcnow,
    fixture_id=None,
    retry_failed=False,
    retry_research=False,
):
    settings = settings or get_settings()
    now = clock()
    with session_factory() as session:
        rows = [
            row
            for row in eligible_rows(session, start=now, end=now + timedelta(hours=6))
            if row[0].status_short == "NS"
            and now < row[0].kickoff_at
            and (fixture_id is None or row[0].external_id == fixture_id)
        ]
        rows.sort(key=lambda row: (row[4], row[0].kickoff_at, row[0].external_id))
        aliases = {
            row[0].external_id: {row[2].external_id: row[2].name, row[3].external_id: row[3].name}
            for row in rows
        }
        candidates = [(row[0].external_id, row[1].external_id, row[0].season_year) for row in rows]
    if not execute:
        return {
            "state": "dry_run",
            "candidates": [row[0] for row in candidates],
            "model": settings.home_preview_vertex_model,
        }
    if not settings.google_cloud_project or not settings.home_preview_search_enabled:
        return {"state": "not_configured", "candidates": [row[0] for row in candidates]}
    client = (
        ApiFootballClient(api_key=settings.api_football_key, requests_per_minute=60)
        if settings.api_football_key
        else None
    )
    vertex = VertexPreviewProvider(settings, clock=clock) if settings.google_cloud_project else None
    results = []
    try:
        evidence_cache = {}
        for external_id, league_id, season in candidates[: settings.home_preview_cycle_limit]:
            key = (league_id, season)
            if client and key not in evidence_cache:
                evidence_cache[key] = ApiFootballPreviewEvidence(
                    client, league_id=league_id, season_year=season
                )
            api_evidence = evidence_cache.get(key)

            generator = (
                ProductionPreviewGenerator(vertex, clock=clock, aliases=aliases.get(external_id))
                if vertex
                else None
            )

            def collect(payload, *, now, api_evidence=api_evidence):
                return api_evidence(payload, now=now) if api_evidence else (payload, {})

            runtime = ModelRun(clock=clock) if vertex else None
            if vertex:
                vertex.runtime = runtime
            results.append(
                process_fixture(
                    session_factory,
                    external_id,
                    payload_provider=generator,
                    evidence_provider=collect,
                    runtime=runtime,
                    clock=clock,
                    retry_failed=retry_failed,
                    retry_research=retry_research,
                    model=settings.home_preview_vertex_model if vertex else "facts-only",
                )
            )
    finally:
        if client:
            client.close()
    return {
        "state": "finished",
        "results": results,
        "deferred": [row[0] for row in candidates[settings.home_preview_cycle_limit :]],
    }
