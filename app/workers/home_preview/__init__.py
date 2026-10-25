"""Post-collection home preview execution. No independent polling worker."""

from datetime import timedelta

from app.core.config import get_settings
from app.services.home_preview import eligible_rows
from app.services.home_preview_api_football import ApiFootballPreviewEvidence
from app.services.home_preview_causes import WebAbsenceCauses
from app.services.home_preview_generation import process_fixture
from app.services.home_preview_policy import utcnow
from app.services.home_preview_retry import ModelRun
from app.services.home_preview_vertex import VertexPreviewProvider
from app.services.home_preview_web import WebPreviewEvidence
from app.workers.daily_sync.api import ApiFootballClient


def run_cycle(
    session_factory,
    *,
    settings=None,
    execute=False,
    clock=utcnow,
    fixture_id=None,
    retry_failed=False,
):
    settings = settings or get_settings()
    now = clock()
    with session_factory() as session:
        rows = [
            row
            for row in eligible_rows(session, start=now, end=now + timedelta(hours=24))
            if row[0].status_short == "NS"
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
    client = (
        ApiFootballClient(api_key=settings.api_football_key, requests_per_minute=60)
        if settings.api_football_key
        else None
    )
    vertex = VertexPreviewProvider(settings) if settings.google_cloud_project else None
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

            fixture_aliases = aliases.get(external_id)

            def discover(payload, *, now, names=fixture_aliases):
                return vertex.discover(payload, now=now, aliases=names)

            web_evidence = (
                WebPreviewEvidence(discover, aliases=aliases.get(external_id), clock=clock)
                if vertex and settings.home_preview_search_enabled
                else None
            )

            def discover_causes(payload, *, targets, now, names=fixture_aliases):
                return vertex.discover_absence_causes(
                    payload, targets=targets, now=now, aliases=names
                )

            cause_evidence = (
                WebAbsenceCauses(discover_causes, aliases=fixture_aliases, clock=clock)
                if vertex and settings.home_preview_search_enabled
                else None
            )

            def collect(payload, *, now, api_evidence=api_evidence, web_evidence=web_evidence):
                usage = {}
                if api_evidence:
                    payload, api_usage = api_evidence(payload, now=now)
                    usage.update(api_usage)
                if web_evidence:
                    payload, web_usage = web_evidence(payload, now=clock())
                    usage.update(web_usage)
                return payload, usage

            runtime = ModelRun(clock=clock) if vertex else None
            if vertex:
                vertex.runtime = runtime
            results.append(
                process_fixture(
                    session_factory,
                    external_id,
                    provider=vertex.analysis if vertex else None,
                    evidence_provider=collect,
                    cause_provider=cause_evidence,
                    runtime=runtime,
                    clock=clock,
                    retry_failed=retry_failed,
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
