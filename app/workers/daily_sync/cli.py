"""CLI entrypoint for league-by-league API-Football backfills."""
from __future__ import annotations

import argparse
import json

from app.workers.daily_sync import (
    DEFAULT_LEAGUE_EXTERNAL_IDS,
    WORLD_CUP_EXTERNAL_ID,
    WORLD_CUP_2026_SEASON,
    default_league_sync_specs,
)
from app.workers.daily_sync.runner import (
    emit_batch_json,
    emit_json,
    load_configured_sync_specs,
    run_backfill,
    run_backfill_batch,
    run_configured_daily_sync,
)
from app.workers.daily_sync.translation_seed import as_log_payload, run as run_translation_seed


def _parse_seasons(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(part.strip()) for part in value.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.workers.daily_sync.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backfill = subparsers.add_parser("backfill-league")
    backfill.add_argument("--league", type=int, required=True)
    backfill.add_argument("--seasons", help="Comma-separated API-Football season years")
    backfill.add_argument("--translation-csv")
    backfill.add_argument("--skip-details", action="store_true")
    backfill.add_argument("--skip-players", action="store_true")
    backfill.add_argument("--skip-standings", action="store_true")
    backfill.add_argument("--fixture-limit", type=int)

    backfill_defaults = subparsers.add_parser("backfill-default-leagues")
    backfill_defaults.add_argument("--include-world-cup", action="store_true")
    backfill_defaults.add_argument("--translation-csv")
    backfill_defaults.add_argument("--skip-details", action="store_true")
    backfill_defaults.add_argument("--skip-players", action="store_true")
    backfill_defaults.add_argument("--skip-standings", action="store_true")
    backfill_defaults.add_argument("--fixture-limit", type=int)

    sync_all = subparsers.add_parser(
        "sync-all-leagues",
        help="Update the default five leagues plus the 2026 FIFA World Cup.",
    )
    sync_all.add_argument("--skip-world-cup", action="store_true")
    sync_all.add_argument("--world-cup-season", type=int, default=WORLD_CUP_2026_SEASON)
    sync_all.add_argument("--translation-csv")
    sync_all.add_argument("--skip-details", action="store_true")
    sync_all.add_argument("--skip-players", action="store_true")
    sync_all.add_argument("--skip-standings", action="store_true")
    sync_all.add_argument("--fixture-limit", type=int)
    sync_all.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the league/season plan without touching API-Football or DB.",
    )
    sync_all.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit non-zero when any league or season records errors.",
    )

    sync_configured = subparsers.add_parser(
        "sync-configured-targets",
        help="Run daily-sync from ADMIN-managed league_sync_target rows.",
    )
    sync_configured.add_argument("--fallback-defaults", action="store_true")
    sync_configured.add_argument("--translation-csv")
    sync_configured.add_argument("--skip-details", action="store_true")
    sync_configured.add_argument("--skip-players", action="store_true")
    sync_configured.add_argument("--skip-standings", action="store_true")
    sync_configured.add_argument("--fixture-limit", type=int)
    sync_configured.add_argument("--plan-only", action="store_true")
    sync_configured.add_argument("--fail-on-errors", action="store_true")

    translation_seed = subparsers.add_parser("import-player-translations")
    translation_seed.add_argument("--csv", required=True)

    args = parser.parse_args()

    if args.command == "import-player-translations":
        result = run_translation_seed(args.csv)
        print(as_log_payload(result))
        return

    if args.command == "backfill-league":
        result = run_backfill(
            league_external_id=args.league,
            seasons=_parse_seasons(args.seasons),
            include_details=not args.skip_details,
            include_players=not args.skip_players,
            include_standings=not args.skip_standings,
            fixture_limit=args.fixture_limit,
            translation_csv=args.translation_csv,
        )
        emit_json(result)
        return

    if args.command == "sync-all-leagues":
        specs = default_league_sync_specs(
            include_world_cup_2026=not args.skip_world_cup,
            world_cup_season=args.world_cup_season,
        )
        if args.plan_only:
            print(
                json.dumps(
                    {"specs": [spec.to_log_payload() for spec in specs]},
                    ensure_ascii=False,
                )
            )
            return
        result = run_backfill_batch(
            specs=specs,
            include_details=not args.skip_details,
            include_players=not args.skip_players,
            include_standings=not args.skip_standings,
            fixture_limit=args.fixture_limit,
            translation_csv=args.translation_csv,
        )
        emit_batch_json(result)
        if args.fail_on_errors and result.has_errors:
            raise SystemExit(1)
        return

    if args.command == "sync-configured-targets":
        if args.plan_only:
            specs = load_configured_sync_specs(fallback_defaults=args.fallback_defaults)
            print(
                json.dumps(
                    {"specs": [spec.to_log_payload() for spec in specs]},
                    ensure_ascii=False,
                )
            )
            return
        result = run_configured_daily_sync(
            fallback_defaults=args.fallback_defaults,
            include_details=not args.skip_details,
            include_players=not args.skip_players,
            include_standings=not args.skip_standings,
            fixture_limit=args.fixture_limit,
            translation_csv=args.translation_csv,
        )
        emit_batch_json(result)
        if args.fail_on_errors and result.has_errors:
            raise SystemExit(1)
        return

    league_ids = list(DEFAULT_LEAGUE_EXTERNAL_IDS)
    if args.include_world_cup:
        league_ids.append(WORLD_CUP_EXTERNAL_ID)
    for league_external_id in league_ids:
        result = run_backfill(
            league_external_id=league_external_id,
            include_details=not args.skip_details,
            include_players=not args.skip_players,
            include_standings=not args.skip_standings,
            fixture_limit=args.fixture_limit,
            translation_csv=args.translation_csv,
        )
        emit_json(result)


if __name__ == "__main__":
    main()
