"""API-Football backfill/daily-sync worker package.

The package is intentionally usable from a one-shot CLI first. The scheduled
daily-sync wrapper can call the same backfill functions later.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LEAGUE_EXTERNAL_IDS = (39, 2, 3, 48, 45)
WORLD_CUP_EXTERNAL_ID = 1
WORLD_CUP_2026_SEASON = 2026


@dataclass(frozen=True)
class LeagueSyncSpec:
    """A single league/season target for the daily-sync batch."""

    league_external_id: int
    seasons: tuple[int, ...] | None = None
    include_details: bool = True
    include_players: bool = True
    include_standings: bool = True
    fixture_limit: int | None = None

    def to_log_payload(self) -> dict[str, object]:
        return {
            "league_external_id": self.league_external_id,
            "seasons": list(self.seasons) if self.seasons is not None else None,
            "include_details": self.include_details,
            "include_players": self.include_players,
            "include_standings": self.include_standings,
            "fixture_limit": self.fixture_limit,
        }


def default_league_sync_specs(
    *,
    include_world_cup_2026: bool = False,
    world_cup_season: int = WORLD_CUP_2026_SEASON,
) -> tuple[LeagueSyncSpec, ...]:
    """Return the default five leagues, optionally with the 2026 World Cup.

    Default leagues keep the worker's existing season detection behavior
    (current season + previous season). The World Cup is explicit because the
    API-Football World Cup season list also contains past tournaments, while
    this daily-sync batch must only add the 2026 tournament.
    """

    specs = [LeagueSyncSpec(league_external_id=league_id) for league_id in DEFAULT_LEAGUE_EXTERNAL_IDS]
    if include_world_cup_2026:
        specs.append(
            LeagueSyncSpec(
                league_external_id=WORLD_CUP_EXTERNAL_ID,
                seasons=(world_cup_season,),
            )
        )
    return tuple(specs)
