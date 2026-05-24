"""League-by-league API-Football backfill runner."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url
from app.workers.daily_sync import LeagueSyncSpec, default_league_sync_specs
from app.workers.daily_sync.api import ApiFootballClient
from app.workers.daily_sync.mappers import parse_int, select_latest_two_actual_seasons
from app.workers.daily_sync.store import (
    StoreCounts,
    ensure_team_season_from_fixtures,
    list_active_sync_specs,
    upsert_fixture_detail,
    upsert_fixture_entry,
    upsert_league,
    upsert_player_entry,
    upsert_standings_entry,
    upsert_team_entry,
)
from app.workers.daily_sync.translation_seed import (
    PlayerTranslationSeedResult,
    import_player_translation_seed,
)


class ProgressReporter(Protocol):
    def log(self, message: str) -> None: ...

    def add_total(self, amount: int) -> None: ...

    def set_total(self, amount: int) -> None: ...

    def advance(self, amount: int = 1, message: str | None = None) -> None: ...


def _progress_log(progress: ProgressReporter | None, message: str) -> None:
    if progress is not None:
        progress.log(message)


def _progress_set_total(progress: ProgressReporter | None, amount: int) -> None:
    if progress is not None:
        progress.set_total(max(0, amount))


def _progress_advance(
    progress: ProgressReporter | None,
    amount: int = 1,
    message: str | None = None,
) -> None:
    if progress is not None and amount > 0:
        progress.advance(amount, message)


def _player_entry_team_external_id(
    entry: dict[str, Any],
    *,
    league_external_id: int,
    season_year: int,
) -> int | None:
    fallback: int | None = None
    for stat in entry.get("statistics") or []:
        if not isinstance(stat, dict):
            continue
        team = stat.get("team") if isinstance(stat.get("team"), dict) else {}
        league = stat.get("league") if isinstance(stat.get("league"), dict) else {}
        team_external_id = parse_int(team.get("id"))
        if team_external_id is None:
            continue
        fallback = fallback or team_external_id
        if (
            parse_int(league.get("id")) == league_external_id
            and parse_int(league.get("season")) == season_year
        ):
            return team_external_id
    return fallback


def _league_payload_name(entry: dict[str, Any], league_external_id: int) -> str:
    league = entry.get("league") if isinstance(entry.get("league"), dict) else {}
    return str(league.get("name") or f"League {league_external_id}")


def _league_label(name: str, league_external_id: int) -> str:
    return f"{name} (#{league_external_id})"


def _response_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response")
    return response if isinstance(response, list) else []


@dataclass
class MeasuredEndpoint:
    path: str
    params: dict[str, Any]
    payload: dict[str, Any] | None = None
    error: str | None = None

    @property
    def response(self) -> list[dict[str, Any]]:
        if self.payload is None:
            return []
        return _response_from_payload(self.payload)


@dataclass
class SeasonSyncPlan:
    season_year: int
    teams: MeasuredEndpoint
    fixtures: MeasuredEndpoint
    standings: MeasuredEndpoint | None = None
    players_first_page: MeasuredEndpoint | None = None
    player_total_pages: int = 0
    fixture_external_ids: list[int] = field(default_factory=list)

    def unit_count(self, *, include_details: bool, include_players: bool) -> int:
        total = 2  # teams + fixtures
        if self.standings is not None:
            total += 1
        if include_players:
            total += max(1, self.player_total_pages)
        if include_details:
            total += len(self.fixture_external_ids) * 4
        return total


@dataclass
class LeagueSyncPlan:
    league_external_id: int
    league_entry: dict[str, Any]
    league_name: str
    seasons: list[SeasonSyncPlan]
    detected_seasons: list[int]

    def unit_count(self, *, include_details: bool, include_players: bool) -> int:
        return 1 + sum(
            season.unit_count(include_details=include_details, include_players=include_players)
            for season in self.seasons
        )


@dataclass
class SeasonBackfillResult:
    season_year: int
    fixtures_seen: int = 0
    fixture_details_seen: int = 0
    teams_seen: int = 0
    player_pages_seen: int = 0
    player_rows_seen: int = 0
    standings_seen: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class LeagueBackfillResult:
    league_external_id: int
    seasons: list[SeasonBackfillResult] = field(default_factory=list)
    counts: StoreCounts = field(default_factory=StoreCounts)
    api_calls_total: int = 0
    api_calls_failed: int = 0
    translation_seed: PlayerTranslationSeedResult | None = None
    duration_seconds: float = 0.0

    def to_log_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


@dataclass
class LeagueSyncFailure:
    league_external_id: int
    seasons: list[int] | None
    error: str
    duration_seconds: float = 0.0


@dataclass
class DailySyncBatchResult:
    specs: list[dict[str, Any]] = field(default_factory=list)
    leagues: list[LeagueBackfillResult] = field(default_factory=list)
    failures: list[LeagueSyncFailure] = field(default_factory=list)
    api_calls_total: int = 0
    api_calls_failed: int = 0
    duration_seconds: float = 0.0

    @property
    def has_errors(self) -> bool:
        if self.failures:
            return True
        return any(season.errors for league in self.leagues for season in league.seasons)

    def to_log_payload(self) -> dict[str, Any]:
        return {
            "specs": self.specs,
            "leagues": [league.to_log_payload() for league in self.leagues],
            "failures": [asdict(failure) for failure in self.failures],
            "api_calls_total": self.api_calls_total,
            "api_calls_failed": self.api_calls_failed,
            "duration_seconds": self.duration_seconds,
            "has_errors": self.has_errors,
        }


def _fetch_parallel_endpoints(
    client: ApiFootballClient,
    endpoints: list[MeasuredEndpoint],
    *,
    max_workers: int,
    progress: ProgressReporter | None = None,
    log_prefix: str | None = None,
) -> None:
    if not endpoints:
        return
    workers = max(1, min(max_workers, len(endpoints)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(client.get, endpoint.path, **endpoint.params): endpoint
            for endpoint in endpoints
        }
        for future in as_completed(futures):
            endpoint = futures[future]
            try:
                endpoint.payload = future.result()
            except Exception as exc:  # noqa: BLE001 - preserve per-endpoint failure
                endpoint.error = str(exc)
            if progress is not None:
                fixture = endpoint.params.get("fixture")
                page = endpoint.params.get("page")
                suffix = f" fixture={fixture}" if fixture is not None else ""
                suffix += f" page={page}" if page is not None else ""
                state = "failed" if endpoint.error else "done"
                _progress_advance(
                    progress,
                    message=f"{log_prefix or 'api'}: {endpoint.path}{suffix} {state}",
                )


def measure_league_sync_plan(
    client: ApiFootballClient,
    *,
    league_external_id: int,
    seasons: list[int] | None,
    include_players: bool,
    include_standings: bool,
    include_details: bool,
    fixture_limit: int | None,
    max_workers: int,
    progress: ProgressReporter | None = None,
) -> LeagueSyncPlan:
    league_entries = client.response("/leagues", id=league_external_id)
    if not league_entries:
        raise RuntimeError(f"API-Football returned no league for id={league_external_id}")
    league_entry = league_entries[0]
    detected_seasons = select_latest_two_actual_seasons(league_entry)
    target_seasons = seasons or detected_seasons
    league_name = _league_payload_name(league_entry, league_external_id)
    label = _league_label(league_name, league_external_id)
    _progress_log(progress, f"daily-sync: measuring {label} seasons={target_seasons}")

    season_plans: list[SeasonSyncPlan] = []
    endpoints: list[MeasuredEndpoint] = []
    for season_year in target_seasons:
        teams = MeasuredEndpoint("/teams", {"league": league_external_id, "season": season_year})
        fixtures = MeasuredEndpoint("/fixtures", {"league": league_external_id, "season": season_year})
        standings = (
            MeasuredEndpoint("/standings", {"league": league_external_id, "season": season_year})
            if include_standings
            else None
        )
        players_first_page = (
            MeasuredEndpoint(
                "/players",
                {"league": league_external_id, "season": season_year, "page": 1},
            )
            if include_players
            else None
        )
        endpoints.extend([teams, fixtures])
        if standings is not None:
            endpoints.append(standings)
        if players_first_page is not None:
            endpoints.append(players_first_page)
        season_plans.append(
            SeasonSyncPlan(
                season_year=season_year,
                teams=teams,
                fixtures=fixtures,
                standings=standings,
                players_first_page=players_first_page,
            )
        )

    _fetch_parallel_endpoints(client, endpoints, max_workers=max_workers)

    for season_plan in season_plans:
        fixture_entries = season_plan.fixtures.response
        if fixture_limit is not None:
            fixture_entries = fixture_entries[:fixture_limit]
        season_plan.fixture_external_ids = [
            fixture_id
            for fixture_id in (
                parse_int((entry.get("fixture") or {}).get("id"))
                for entry in fixture_entries
                if isinstance(entry, dict)
            )
            if fixture_id is not None
        ]
        if season_plan.players_first_page is not None:
            payload = season_plan.players_first_page.payload or {}
            paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
            season_plan.player_total_pages = int(paging.get("total") or 1)

    total_units = 1 + sum(
        season_plan.unit_count(include_details=include_details, include_players=include_players)
        for season_plan in season_plans
    )
    _progress_log(
        progress,
        f"daily-sync: measured {label} units={total_units}",
    )
    return LeagueSyncPlan(
        league_external_id=league_external_id,
        league_entry=league_entry,
        league_name=league_name,
        seasons=season_plans,
        detected_seasons=detected_seasons,
    )


def backfill_measured_league(
    session,
    client: ApiFootballClient,
    *,
    plan: LeagueSyncPlan,
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    translation_csv: str | Path | None = None,
    commit_every: int = 100,
    progress: ProgressReporter | None = None,
    max_workers: int = 6,
) -> LeagueBackfillResult:
    started = time.monotonic()
    calls_started = client.calls_total
    failed_started = client.calls_failed
    league_external_id = plan.league_external_id
    label = _league_label(plan.league_name, league_external_id)
    result = LeagueBackfillResult(league_external_id=league_external_id)
    counts = result.counts

    league_id, detected_seasons = upsert_league(session, plan.league_entry, counts)
    session.commit()
    season_years = [season.season_year for season in plan.seasons]
    _progress_advance(progress, message=f"{label}: catalog synced, seasons={season_years}")

    for season_plan in plan.seasons:
        season_year = season_plan.season_year
        season_label = f"{label} season {season_year}"
        season_result = SeasonBackfillResult(season_year=season_year)
        result.seasons.append(season_result)
        _progress_log(progress, f"{season_label}: start")

        if season_plan.teams.error:
            season_result.errors.append(f"teams:{season_plan.teams.error}")
            _progress_advance(progress, message=f"{season_label}: teams failed: {season_plan.teams.error}")
        else:
            for entry in season_plan.teams.response:
                upsert_team_entry(session, entry, counts)
                season_result.teams_seen += 1
            session.commit()
            _progress_advance(progress, message=f"{season_label}: teams={season_result.teams_seen}")

        if season_plan.fixtures.error:
            season_result.errors.append(f"fixtures:{season_plan.fixtures.error}")
            _progress_advance(
                progress,
                message=f"{season_label}: fixtures failed: {season_plan.fixtures.error}",
            )
        else:
            allowed_fixture_ids = set(season_plan.fixture_external_ids)
            fixture_entries = [
                entry
                for entry in season_plan.fixtures.response
                if parse_int((entry.get("fixture") or {}).get("id")) in allowed_fixture_ids
            ]
            for index, entry in enumerate(fixture_entries, start=1):
                upsert_fixture_entry(session, entry, counts)
                season_result.fixtures_seen += 1
                if index % commit_every == 0:
                    session.commit()
            session.commit()
            ensure_team_season_from_fixtures(
                session,
                league_id=league_id,
                season_year=season_year,
                counts=counts,
            )
            session.commit()
            _progress_advance(progress, message=f"{season_label}: fixtures={season_result.fixtures_seen}")

        if include_standings and season_plan.standings is not None:
            if season_plan.standings.error:
                season_result.errors.append(f"standings:{season_plan.standings.error}")
                _progress_advance(
                    progress,
                    message=f"{season_label}: standings failed: {season_plan.standings.error}",
                )
            else:
                for entry in season_plan.standings.response:
                    upsert_standings_entry(session, entry, counts)
                    season_result.standings_seen += 1
                session.commit()
                _progress_advance(
                    progress,
                    message=f"{season_label}: standings={season_result.standings_seen}",
                )

        if include_players and season_plan.players_first_page is not None:
            current_season = detected_seasons[0] if detected_seasons else season_year
            total_pages = max(1, season_plan.player_total_pages)
            player_page_payloads: dict[int, dict[str, Any] | None] = {1: season_plan.players_first_page.payload}
            if season_plan.players_first_page.error:
                season_result.errors.append(f"players:page=1:{season_plan.players_first_page.error}")
                _progress_advance(
                    progress,
                    message=f"{season_label}: players page=1/{total_pages} failed: {season_plan.players_first_page.error}",
                )
            else:
                _progress_advance(progress, message=f"{season_label}: players page=1/{total_pages} fetched")

            remaining_pages = [
                MeasuredEndpoint(
                    "/players",
                    {"league": league_external_id, "season": season_year, "page": page},
                )
                for page in range(2, total_pages + 1)
            ]
            _fetch_parallel_endpoints(
                client,
                remaining_pages,
                max_workers=max_workers,
                progress=progress,
                log_prefix=f"{season_label}: players",
            )
            for endpoint in remaining_pages:
                page = int(endpoint.params["page"])
                if endpoint.error:
                    season_result.errors.append(f"players:page={page}:{endpoint.error}")
                player_page_payloads[page] = endpoint.payload

            for page in range(1, total_pages + 1):
                payload = player_page_payloads.get(page) or {}
                page_rows = 0
                for entry in _response_from_payload(payload):
                    team_external_id = _player_entry_team_external_id(
                        entry,
                        league_external_id=league_external_id,
                        season_year=season_year,
                    )
                    if team_external_id is None:
                        continue
                    upsert_player_entry(
                        session,
                        entry,
                        counts,
                        current_team_external_id=team_external_id,
                        set_current_team=season_year == current_season,
                    )
                    season_result.player_rows_seen += 1
                    page_rows += 1
                season_result.player_pages_seen += 1
                session.commit()
                _progress_log(progress, f"{season_label}: players page={page}/{total_pages} rows={page_rows}")

        if include_details:
            detail_endpoints: list[MeasuredEndpoint] = []
            for fixture_external_id in season_plan.fixture_external_ids:
                detail_endpoints.extend(
                    [
                        MeasuredEndpoint("/fixtures/events", {"fixture": fixture_external_id}),
                        MeasuredEndpoint("/fixtures/statistics", {"fixture": fixture_external_id}),
                        MeasuredEndpoint("/fixtures/lineups", {"fixture": fixture_external_id}),
                        MeasuredEndpoint("/fixtures/players", {"fixture": fixture_external_id}),
                    ]
                )
            _fetch_parallel_endpoints(
                client,
                detail_endpoints,
                max_workers=max_workers,
                progress=progress,
                log_prefix=f"{season_label}: detail",
            )
            by_fixture: dict[int, dict[str, MeasuredEndpoint]] = {}
            for endpoint in detail_endpoints:
                fixture_external_id = int(endpoint.params["fixture"])
                by_fixture.setdefault(fixture_external_id, {})[endpoint.path] = endpoint
            empty_endpoint = MeasuredEndpoint("", {})
            for index, fixture_external_id in enumerate(season_plan.fixture_external_ids, start=1):
                endpoint_map = by_fixture.get(fixture_external_id, {})
                errors = [
                    f"{path}:{endpoint.error}"
                    for path, endpoint in endpoint_map.items()
                    if endpoint.error
                ]
                if errors:
                    season_result.errors.append(f"details:{fixture_external_id}:{'; '.join(errors)}")
                upsert_fixture_detail(
                    session,
                    fixture_external_id=fixture_external_id,
                    events=endpoint_map.get("/fixtures/events", empty_endpoint).response,
                    statistics=endpoint_map.get("/fixtures/statistics", empty_endpoint).response,
                    lineups=endpoint_map.get("/fixtures/lineups", empty_endpoint).response,
                    players=endpoint_map.get("/fixtures/players", empty_endpoint).response,
                    counts=counts,
                )
                season_result.fixture_details_seen += 1
                if index % commit_every == 0:
                    session.commit()
                _progress_log(progress, f"{season_label}: details fixture={fixture_external_id}")
            session.commit()
        _progress_log(progress, f"{season_label}: complete")

    if translation_csv is not None:
        result.translation_seed = import_player_translation_seed(session, translation_csv)

    result.api_calls_total = client.calls_total - calls_started
    result.api_calls_failed = client.calls_failed - failed_started
    result.duration_seconds = round(time.monotonic() - started, 4)
    return result


def backfill_league(
    session,
    client: ApiFootballClient,
    *,
    league_external_id: int,
    seasons: list[int] | None = None,
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    fixture_limit: int | None = None,
    translation_csv: str | Path | None = None,
    commit_every: int = 100,
    progress: ProgressReporter | None = None,
    max_workers: int | None = None,
) -> LeagueBackfillResult:
    settings = get_settings()
    workers = max_workers or settings.api_football_concurrency
    plan = measure_league_sync_plan(
        client,
        league_external_id=league_external_id,
        seasons=seasons,
        include_details=include_details,
        include_players=include_players,
        include_standings=include_standings,
        fixture_limit=fixture_limit,
        max_workers=workers,
        progress=progress,
    )
    _progress_set_total(
        progress,
        plan.unit_count(include_details=include_details, include_players=include_players),
    )
    return backfill_measured_league(
        session,
        client,
        plan=plan,
        include_details=include_details,
        include_players=include_players,
        include_standings=include_standings,
        translation_csv=translation_csv,
        commit_every=commit_every,
        progress=progress,
        max_workers=workers,
    )


def run_backfill_batch(
    *,
    specs: list[LeagueSyncSpec] | tuple[LeagueSyncSpec, ...],
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    fixture_limit: int | None = None,
    translation_csv: str | Path | None = None,
    database_url: str | None = None,
    api_key: str | None = None,
    progress: ProgressReporter | None = None,
) -> DailySyncBatchResult:
    settings = get_settings()
    resolved_key = api_key or settings.api_football_key
    if not resolved_key:
        raise RuntimeError("API_FOOTBALL_KEY is required")

    started = time.monotonic()
    batch = DailySyncBatchResult(specs=[spec.to_log_payload() for spec in specs])
    engine = create_engine(
        normalize_database_url(database_url or settings.database_url),
        **database_engine_kwargs(settings),
    )
    client = ApiFootballClient(
        api_key=resolved_key,
        host=settings.api_football_host,
        requests_per_minute=settings.api_football_requests_per_minute,
    )
    try:
        measured: list[tuple[LeagueSyncSpec, LeagueSyncPlan]] = []
        _progress_log(progress, "daily-sync: measuring update size")
        for spec in specs:
            league_started = time.monotonic()
            try:
                measured.append(
                    (
                        spec,
                        measure_league_sync_plan(
                            client,
                            league_external_id=spec.league_external_id,
                            seasons=list(spec.seasons) if spec.seasons is not None else None,
                            include_details=include_details and spec.include_details,
                            include_players=include_players and spec.include_players,
                            include_standings=include_standings and spec.include_standings,
                            fixture_limit=spec.fixture_limit if spec.fixture_limit is not None else fixture_limit,
                            max_workers=settings.api_football_concurrency,
                            progress=progress,
                        ),
                    )
                )
            except Exception as exc:  # noqa: BLE001 - keep other leagues moving
                batch.failures.append(
                    LeagueSyncFailure(
                        league_external_id=spec.league_external_id,
                        seasons=list(spec.seasons) if spec.seasons is not None else None,
                        error=str(exc),
                        duration_seconds=round(time.monotonic() - league_started, 4),
                    )
                )
                _progress_log(progress, f"daily-sync: measure failed league={spec.league_external_id}: {exc}")

        total_units = sum(
            plan.unit_count(
                include_details=include_details and spec.include_details,
                include_players=include_players and spec.include_players,
            )
            for spec, plan in measured
        )
        _progress_set_total(progress, total_units)
        _progress_log(
            progress,
            "daily-sync: measured "
            f"total_units={total_units} leagues={len(measured)} "
            f"concurrency={settings.api_football_concurrency} "
            f"requests_per_minute={settings.api_football_requests_per_minute}",
        )

        with Session(engine) as session:
            for spec, plan in measured:
                league_started = time.monotonic()
                label = _league_label(plan.league_name, spec.league_external_id)
                _progress_log(
                    progress,
                    f"daily-sync: start {label} seasons={[season.season_year for season in plan.seasons]}",
                )
                try:
                    batch.leagues.append(
                        backfill_measured_league(
                            session,
                            client,
                            plan=plan,
                            include_details=include_details and spec.include_details,
                            include_players=include_players and spec.include_players,
                            include_standings=include_standings and spec.include_standings,
                            translation_csv=translation_csv,
                            progress=progress,
                            max_workers=settings.api_football_concurrency,
                        )
                    )
                    _progress_log(progress, f"daily-sync: complete {label}")
                except Exception as exc:  # noqa: BLE001 - keep the rest of the batch moving
                    session.rollback()
                    batch.failures.append(
                        LeagueSyncFailure(
                            league_external_id=spec.league_external_id,
                            seasons=list(spec.seasons) if spec.seasons is not None else None,
                            error=str(exc),
                            duration_seconds=round(time.monotonic() - league_started, 4),
                        )
                    )
                    _progress_log(progress, f"daily-sync: failed {label}: {exc}")
    finally:
        batch.api_calls_total = client.calls_total
        batch.api_calls_failed = client.calls_failed
        batch.duration_seconds = round(time.monotonic() - started, 4)
        client.close()
        engine.dispose()
    return batch


def load_configured_sync_specs(
    *,
    database_url: str | None = None,
    fallback_defaults: bool = False,
) -> list[LeagueSyncSpec]:
    settings = get_settings()
    engine = create_engine(
        normalize_database_url(database_url or settings.database_url),
        **database_engine_kwargs(settings),
    )
    try:
        with Session(engine) as session:
            specs = list_active_sync_specs(session)
    finally:
        engine.dispose()
    if not specs and fallback_defaults:
        return list(default_league_sync_specs(include_world_cup_2026=True))
    return specs


def run_configured_daily_sync(
    *,
    fallback_defaults: bool = False,
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    fixture_limit: int | None = None,
    translation_csv: str | Path | None = None,
    database_url: str | None = None,
    api_key: str | None = None,
    progress: ProgressReporter | None = None,
) -> DailySyncBatchResult:
    specs = load_configured_sync_specs(
        database_url=database_url,
        fallback_defaults=fallback_defaults,
    )
    return run_backfill_batch(
        specs=specs,
        include_details=include_details,
        include_players=include_players,
        include_standings=include_standings,
        fixture_limit=fixture_limit,
        translation_csv=translation_csv,
        database_url=database_url,
        api_key=api_key,
        progress=progress,
    )


def run_backfill(
    *,
    league_external_id: int,
    seasons: list[int] | None = None,
    include_details: bool = True,
    include_players: bool = True,
    include_standings: bool = True,
    fixture_limit: int | None = None,
    translation_csv: str | Path | None = None,
    database_url: str | None = None,
    api_key: str | None = None,
    progress: ProgressReporter | None = None,
) -> LeagueBackfillResult:
    settings = get_settings()
    resolved_key = api_key or settings.api_football_key
    if not resolved_key:
        raise RuntimeError("API_FOOTBALL_KEY is required")

    engine = create_engine(
        normalize_database_url(database_url or settings.database_url),
        **database_engine_kwargs(settings),
    )
    client = ApiFootballClient(
        api_key=resolved_key,
        host=settings.api_football_host,
        requests_per_minute=settings.api_football_requests_per_minute,
    )
    try:
        with Session(engine) as session:
            return backfill_league(
                session,
                client,
                league_external_id=league_external_id,
                seasons=seasons,
                include_details=include_details,
                include_players=include_players,
                include_standings=include_standings,
                fixture_limit=fixture_limit,
                translation_csv=translation_csv,
                progress=progress,
            )
    finally:
        client.close()
        engine.dispose()


def emit_json(result: LeagueBackfillResult) -> None:
    print(json.dumps(result.to_log_payload(), ensure_ascii=False, default=str))


def emit_batch_json(result: DailySyncBatchResult) -> None:
    print(json.dumps(result.to_log_payload(), ensure_ascii=False, default=str))
