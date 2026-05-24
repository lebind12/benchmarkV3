"""Database upsert helpers for API-Football backfills."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from app.workers.daily_sync import LeagueSyncSpec
from app.workers.daily_sync.mappers import (
    compact_coach,
    compact_team,
    compact_venue,
    fixture_from_api,
    league_from_api,
    player_from_api,
    player_stat_from_api,
    standing_rows_from_api,
)


@dataclass
class StoreCounts:
    league: int = 0
    venue: int = 0
    team: int = 0
    fixture: int = 0
    fixture_detail: int = 0
    standings: int = 0
    player: int = 0
    player_season_stat: int = 0
    coach: int = 0
    team_coach: int = 0
    team_season: int = 0
    translation_rows: dict[str, int] = field(
        default_factory=lambda: {"league": 0, "team": 0, "player": 0, "coach": 0}
    )


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


_ENSURE_TRANSLATION = {
    "league": text(
        "INSERT INTO league_translation (league_id) VALUES (:id) "
        "ON CONFLICT (league_id) DO NOTHING"
    ),
    "team": text(
        "INSERT INTO team_translation (team_id) VALUES (:id) "
        "ON CONFLICT (team_id) DO NOTHING"
    ),
    "player": text(
        "INSERT INTO player_translation (player_id) VALUES (:id) "
        "ON CONFLICT (player_id) DO NOTHING"
    ),
    "coach": text(
        "INSERT INTO coach_translation (coach_id) VALUES (:id) "
        "ON CONFLICT (coach_id) DO NOTHING"
    ),
}


def _ensure_translation(session, entity_type: str, internal_id: int, counts: StoreCounts) -> None:
    result = session.execute(_ENSURE_TRANSLATION[entity_type], {"id": internal_id})
    if result.rowcount:
        counts.translation_rows[entity_type] += result.rowcount


_UPSERT_LEAGUE = text(
    """
    INSERT INTO league (
        external_id, name, type, logo_url, country_name, country_code,
        country_flag, slug, current_season, is_active, updated_at
    )
    VALUES (
        :external_id, :name, :type, :logo_url, :country_name, :country_code,
        :country_flag, :slug, :current_season, true, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        type = EXCLUDED.type,
        logo_url = EXCLUDED.logo_url,
        country_name = EXCLUDED.country_name,
        country_code = EXCLUDED.country_code,
        country_flag = EXCLUDED.country_flag,
        slug = EXCLUDED.slug,
        current_season = EXCLUDED.current_season,
        is_active = true,
        updated_at = now()
    RETURNING id
    """
)


def upsert_league(session, entry: dict[str, Any], counts: StoreCounts) -> tuple[int, list[int]]:
    mapped = league_from_api(entry)
    if mapped is None:
        raise ValueError("league response missing league.id")
    league_id = session.execute(_UPSERT_LEAGUE, mapped).scalar_one()
    counts.league += 1
    _ensure_translation(session, "league", league_id, counts)
    from app.workers.daily_sync.mappers import select_latest_two_actual_seasons

    return league_id, select_latest_two_actual_seasons(entry)


_UPSERT_VENUE = text(
    """
    INSERT INTO venue (
        external_id, name, city, country, capacity, surface, address, image_url,
        updated_at
    )
    VALUES (
        :external_id, :name, :city, :country, :capacity, :surface, :address,
        :image_url, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        city = COALESCE(EXCLUDED.city, venue.city),
        country = COALESCE(EXCLUDED.country, venue.country),
        capacity = COALESCE(EXCLUDED.capacity, venue.capacity),
        surface = COALESCE(EXCLUDED.surface, venue.surface),
        address = COALESCE(EXCLUDED.address, venue.address),
        image_url = COALESCE(EXCLUDED.image_url, venue.image_url),
        updated_at = now()
    RETURNING id
    """
)


def upsert_venue_payload(session, venue_payload: dict[str, Any] | None, counts: StoreCounts) -> int | None:
    mapped = compact_venue(venue_payload)
    if mapped is None:
        return None
    venue_id = session.execute(_UPSERT_VENUE, mapped).scalar_one()
    counts.venue += 1
    return venue_id


_UPSERT_TEAM = text(
    """
    INSERT INTO team (
        external_id, name, code, country, founded, is_national, logo_url,
        venue_id, slug, updated_at
    )
    VALUES (
        :external_id, :name, :code, :country, :founded, :is_national, :logo_url,
        (SELECT id FROM venue WHERE external_id = :venue_external_id),
        :slug, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        code = COALESCE(EXCLUDED.code, team.code),
        country = COALESCE(EXCLUDED.country, team.country),
        founded = COALESCE(EXCLUDED.founded, team.founded),
        is_national = EXCLUDED.is_national,
        logo_url = COALESCE(EXCLUDED.logo_url, team.logo_url),
        venue_id = COALESCE(EXCLUDED.venue_id, team.venue_id),
        slug = EXCLUDED.slug,
        updated_at = now()
    RETURNING id
    """
)


def upsert_team_payload(
    session,
    team_payload: dict[str, Any] | None,
    counts: StoreCounts,
    *,
    venue_external_id: int | None = None,
) -> int | None:
    mapped = compact_team(team_payload)
    if mapped is None:
        return None
    mapped["venue_external_id"] = venue_external_id
    team_id = session.execute(_UPSERT_TEAM, mapped).scalar_one()
    counts.team += 1
    _ensure_translation(session, "team", team_id, counts)
    return team_id


def upsert_team_entry(session, entry: dict[str, Any], counts: StoreCounts) -> int | None:
    venue_payload = entry.get("venue") or {}
    venue = compact_venue(venue_payload)
    if venue is not None:
        upsert_venue_payload(session, venue_payload, counts)
    return upsert_team_payload(
        session,
        entry.get("team"),
        counts,
        venue_external_id=venue["external_id"] if venue else None,
    )


_UPSERT_COACH_BY_EXTERNAL_ID = text(
    """
    INSERT INTO coach (
        external_id, name, photo_url, slug, updated_at
    )
    VALUES (
        :external_id, :name, :photo_url, :slug, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        photo_url = COALESCE(EXCLUDED.photo_url, coach.photo_url),
        slug = EXCLUDED.slug,
        updated_at = now()
    RETURNING id
    """
)


_UPSERT_COACH_BY_SLUG = text(
    """
    INSERT INTO coach (
        external_id, name, photo_url, slug, updated_at
    )
    VALUES (
        NULL, :name, :photo_url, :slug, now()
    )
    ON CONFLICT (slug) DO UPDATE SET
        name = EXCLUDED.name,
        photo_url = COALESCE(EXCLUDED.photo_url, coach.photo_url),
        updated_at = now()
    RETURNING id
    """
)


_UPSERT_TEAM_COACH = text(
    """
    INSERT INTO team_coach (
        team_id, coach_id, league_id, season_year, first_seen_at, last_seen_at,
        updated_at
    )
    SELECT
        t.id, :coach_id, f.league_id, f.season_year, f.kickoff_at, f.kickoff_at,
        now()
    FROM fixture f
    JOIN team t ON t.external_id = :team_external_id
    WHERE f.external_id = :fixture_external_id
    ON CONFLICT (team_id, coach_id) DO UPDATE SET
        league_id = COALESCE(EXCLUDED.league_id, team_coach.league_id),
        season_year = COALESCE(EXCLUDED.season_year, team_coach.season_year),
        first_seen_at = LEAST(
            COALESCE(team_coach.first_seen_at, EXCLUDED.first_seen_at),
            COALESCE(EXCLUDED.first_seen_at, team_coach.first_seen_at)
        ),
        last_seen_at = GREATEST(
            COALESCE(team_coach.last_seen_at, EXCLUDED.last_seen_at),
            COALESCE(EXCLUDED.last_seen_at, team_coach.last_seen_at)
        ),
        updated_at = now()
    """
)


def upsert_coach_payload(
    session,
    coach_payload: dict[str, Any] | None,
    counts: StoreCounts,
) -> int | None:
    mapped = compact_coach(coach_payload)
    if mapped is None:
        return None
    statement = _UPSERT_COACH_BY_EXTERNAL_ID if mapped["external_id"] is not None else _UPSERT_COACH_BY_SLUG
    coach_id = session.execute(statement, mapped).scalar_one()
    counts.coach += 1
    _ensure_translation(session, "coach", coach_id, counts)
    return coach_id


def upsert_coaches_from_lineups(
    session,
    *,
    fixture_external_id: int,
    lineups: Any,
    counts: StoreCounts,
) -> int:
    if not isinstance(lineups, list):
        return 0
    linked = 0
    for lineup in lineups:
        if not isinstance(lineup, dict):
            continue
        team = lineup.get("team") if isinstance(lineup.get("team"), dict) else {}
        team_external_id = team.get("id")
        if team_external_id is None:
            continue
        coach_id = upsert_coach_payload(session, lineup.get("coach"), counts)
        if coach_id is None:
            continue
        result = session.execute(
            _UPSERT_TEAM_COACH,
            {
                "coach_id": coach_id,
                "team_external_id": team_external_id,
                "fixture_external_id": fixture_external_id,
            },
        )
        linked += result.rowcount or 0
    counts.team_coach += linked
    return linked


_UPSERT_FIXTURE = text(
    """
    INSERT INTO fixture (
        external_id, league_id, season_year, round, home_team_id, away_team_id,
        venue_id, referee, timezone, kickoff_at, timestamp_unix, status_long,
        status_short, status_elapsed, period_first, period_second, goals_home,
        goals_away, score_ht_home, score_ht_away, score_ft_home, score_ft_away,
        score_et_home, score_et_away, score_pen_home, score_pen_away,
        home_winner, away_winner, updated_at
    )
    VALUES (
        :external_id,
        (SELECT id FROM league WHERE external_id = :league_external_id),
        :season_year, :round,
        (SELECT id FROM team WHERE external_id = :home_team_external_id),
        (SELECT id FROM team WHERE external_id = :away_team_external_id),
        (SELECT id FROM venue WHERE external_id = :venue_external_id),
        :referee, :timezone, :kickoff_at, :timestamp_unix, :status_long,
        :status_short, :status_elapsed, :period_first, :period_second,
        :goals_home, :goals_away, :score_ht_home, :score_ht_away,
        :score_ft_home, :score_ft_away, :score_et_home, :score_et_away,
        :score_pen_home, :score_pen_away, :home_winner, :away_winner, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        league_id = EXCLUDED.league_id,
        season_year = EXCLUDED.season_year,
        round = EXCLUDED.round,
        home_team_id = EXCLUDED.home_team_id,
        away_team_id = EXCLUDED.away_team_id,
        venue_id = COALESCE(EXCLUDED.venue_id, fixture.venue_id),
        referee = EXCLUDED.referee,
        timezone = EXCLUDED.timezone,
        kickoff_at = EXCLUDED.kickoff_at,
        timestamp_unix = EXCLUDED.timestamp_unix,
        status_long = EXCLUDED.status_long,
        status_short = EXCLUDED.status_short,
        status_elapsed = EXCLUDED.status_elapsed,
        period_first = EXCLUDED.period_first,
        period_second = EXCLUDED.period_second,
        goals_home = EXCLUDED.goals_home,
        goals_away = EXCLUDED.goals_away,
        score_ht_home = EXCLUDED.score_ht_home,
        score_ht_away = EXCLUDED.score_ht_away,
        score_ft_home = EXCLUDED.score_ft_home,
        score_ft_away = EXCLUDED.score_ft_away,
        score_et_home = EXCLUDED.score_et_home,
        score_et_away = EXCLUDED.score_et_away,
        score_pen_home = EXCLUDED.score_pen_home,
        score_pen_away = EXCLUDED.score_pen_away,
        home_winner = EXCLUDED.home_winner,
        away_winner = EXCLUDED.away_winner,
        updated_at = now()
    RETURNING id
    """
)


def upsert_fixture_entry(session, entry: dict[str, Any], counts: StoreCounts) -> int | None:
    fixture_payload = entry.get("fixture") or {}
    venue_payload = fixture_payload.get("venue") or {}
    venue = compact_venue(venue_payload)
    if venue is not None:
        upsert_venue_payload(session, venue_payload, counts)
    teams = entry.get("teams") or {}
    upsert_team_payload(session, teams.get("home"), counts)
    upsert_team_payload(session, teams.get("away"), counts)
    mapped = fixture_from_api(entry)
    if mapped is None:
        return None
    fixture_id = session.execute(_UPSERT_FIXTURE, mapped).scalar_one()
    counts.fixture += 1
    return fixture_id


_UPSERT_TEAM_SEASON_FROM_FIXTURES = text(
    """
    INSERT INTO team_season (team_id, league_id, season_year)
    SELECT DISTINCT team_id, league_id, season_year
    FROM (
        SELECT home_team_id AS team_id, league_id, season_year
        FROM fixture
        WHERE league_id = :league_id AND season_year = :season_year
        UNION ALL
        SELECT away_team_id AS team_id, league_id, season_year
        FROM fixture
        WHERE league_id = :league_id AND season_year = :season_year
    ) t
    WHERE team_id IS NOT NULL
    ON CONFLICT DO NOTHING
    """
)


def ensure_team_season_from_fixtures(
    session, *, league_id: int, season_year: int, counts: StoreCounts
) -> None:
    result = session.execute(
        _UPSERT_TEAM_SEASON_FROM_FIXTURES,
        {"league_id": league_id, "season_year": season_year},
    )
    counts.team_season += result.rowcount or 0


_LIST_TEAM_EXTERNAL_IDS = text(
    """
    SELECT t.external_id
    FROM team_season ts
    JOIN team t ON t.id = ts.team_id
    JOIN league l ON l.id = ts.league_id
    WHERE l.external_id = :league_external_id
      AND ts.season_year = :season_year
    ORDER BY t.external_id
    """
)


def list_team_external_ids(session, *, league_external_id: int, season_year: int) -> list[int]:
    return [
        int(row[0])
        for row in session.execute(
            _LIST_TEAM_EXTERNAL_IDS,
            {"league_external_id": league_external_id, "season_year": season_year},
        )
    ]


_LIST_FIXTURE_EXTERNAL_IDS = text(
    """
    SELECT f.external_id
    FROM fixture f
    JOIN league l ON l.id = f.league_id
    WHERE l.external_id = :league_external_id
      AND f.season_year = :season_year
    ORDER BY f.kickoff_at, f.external_id
    """
)


def list_fixture_external_ids(session, *, league_external_id: int, season_year: int) -> list[int]:
    return [
        int(row[0])
        for row in session.execute(
            _LIST_FIXTURE_EXTERNAL_IDS,
            {"league_external_id": league_external_id, "season_year": season_year},
        )
    ]


_LIST_ACTIVE_SYNC_TARGETS = text(
    """
    SELECT
        l.external_id AS league_external_id,
        st.season_year,
        st.include_details,
        st.include_players,
        st.include_standings,
        st.fixture_limit
    FROM league_sync_target st
    JOIN league l ON l.id = st.league_id
    WHERE st.is_active = true
    ORDER BY l.external_id, st.season_year DESC
    """
)


def list_active_sync_specs(session) -> list[LeagueSyncSpec]:
    rows = session.execute(_LIST_ACTIVE_SYNC_TARGETS).mappings().all()
    return [
        LeagueSyncSpec(
            league_external_id=int(row["league_external_id"]),
            seasons=(int(row["season_year"]),),
            include_details=bool(row["include_details"]),
            include_players=bool(row["include_players"]),
            include_standings=bool(row["include_standings"]),
            fixture_limit=int(row["fixture_limit"]) if row["fixture_limit"] is not None else None,
        )
        for row in rows
    ]


_UPSERT_STANDING = text(
    """
    INSERT INTO standings (
        league_id, season_year, team_id, group_name, rank, points, played,
        win, draw, loss, goals_for, goals_against, goals_diff, form, status,
        description, home_away_breakdown, raw_data, updated_at
    )
    VALUES (
        (SELECT id FROM league WHERE external_id = :league_external_id),
        :season_year,
        (SELECT id FROM team WHERE external_id = :team_external_id),
        :group_name, :rank, :points, :played, :win, :draw, :loss, :goals_for,
        :goals_against, :goals_diff, :form, :status, :description,
        CAST(:home_away_breakdown AS jsonb), CAST(:raw_data AS jsonb), now()
    )
    ON CONFLICT (
        league_id, season_year, team_id, (COALESCE(group_name, ''::text))
    ) DO UPDATE SET
        rank = EXCLUDED.rank,
        points = EXCLUDED.points,
        played = EXCLUDED.played,
        win = EXCLUDED.win,
        draw = EXCLUDED.draw,
        loss = EXCLUDED.loss,
        goals_for = EXCLUDED.goals_for,
        goals_against = EXCLUDED.goals_against,
        goals_diff = EXCLUDED.goals_diff,
        form = EXCLUDED.form,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        home_away_breakdown = EXCLUDED.home_away_breakdown,
        raw_data = EXCLUDED.raw_data,
        updated_at = now()
    """
)


def upsert_standings_entry(session, entry: dict[str, Any], counts: StoreCounts) -> None:
    for row in standing_rows_from_api(entry):
        row = dict(row)
        row["home_away_breakdown"] = _json(row["home_away_breakdown"])
        row["raw_data"] = _json(row["raw_data"])
        session.execute(_UPSERT_STANDING, row)
        counts.standings += 1


_UPSERT_PLAYER = text(
    """
    INSERT INTO player (
        external_id, name, firstname, lastname, age, birth_date, birth_place,
        birth_country, nationality, height_cm, weight_kg, injured, photo_url,
        current_team_id, slug, updated_at
    )
    VALUES (
        :external_id, :name, :firstname, :lastname, :age, :birth_date, :birth_place,
        :birth_country, :nationality, :height_cm, :weight_kg, :injured, :photo_url,
        (SELECT id FROM team WHERE external_id = :current_team_external_id),
        :slug, now()
    )
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        firstname = EXCLUDED.firstname,
        lastname = EXCLUDED.lastname,
        age = EXCLUDED.age,
        birth_date = EXCLUDED.birth_date,
        birth_place = EXCLUDED.birth_place,
        birth_country = EXCLUDED.birth_country,
        nationality = EXCLUDED.nationality,
        height_cm = EXCLUDED.height_cm,
        weight_kg = EXCLUDED.weight_kg,
        injured = EXCLUDED.injured,
        photo_url = COALESCE(EXCLUDED.photo_url, player.photo_url),
        current_team_id = COALESCE(EXCLUDED.current_team_id, player.current_team_id),
        slug = EXCLUDED.slug,
        updated_at = now()
    RETURNING id
    """
)


_UPSERT_PLAYER_STAT = text(
    """
    INSERT INTO player_season_stat (
        player_id, team_id, league_id, season_year, position, shirt_number,
        appearances, minutes, rating, goals, assists, yellow_cards, red_cards,
        raw_stats, updated_at
    )
    SELECT
        :player_id, t.id, l.id, :season_year, :position, :shirt_number,
        :appearances, :minutes, :rating, :goals, :assists, :yellow_cards,
        :red_cards, CAST(:raw_stats AS jsonb), now()
    FROM team t, league l
    WHERE t.external_id = :team_external_id
      AND l.external_id = :league_external_id
    ON CONFLICT (player_id, team_id, league_id, season_year) DO UPDATE SET
        position = EXCLUDED.position,
        shirt_number = EXCLUDED.shirt_number,
        appearances = EXCLUDED.appearances,
        minutes = EXCLUDED.minutes,
        rating = EXCLUDED.rating,
        goals = EXCLUDED.goals,
        assists = EXCLUDED.assists,
        yellow_cards = EXCLUDED.yellow_cards,
        red_cards = EXCLUDED.red_cards,
        raw_stats = EXCLUDED.raw_stats,
        updated_at = now()
    RETURNING id
    """
)


def upsert_player_entry(
    session,
    entry: dict[str, Any],
    counts: StoreCounts,
    *,
    current_team_external_id: int,
    set_current_team: bool,
) -> int | None:
    mapped = player_from_api(
        entry.get("player") or {},
        current_team_external_id=current_team_external_id if set_current_team else None,
    )
    if mapped is None:
        return None
    player_id = session.execute(_UPSERT_PLAYER, mapped).scalar_one()
    counts.player += 1
    _ensure_translation(session, "player", player_id, counts)
    for stat in entry.get("statistics") or []:
        stat_mapped = player_stat_from_api(stat)
        if stat_mapped is None:
            continue
        stat_mapped = dict(stat_mapped)
        stat_mapped["player_id"] = player_id
        stat_mapped["raw_stats"] = _json(stat_mapped["raw_stats"])
        stat_id = session.execute(_UPSERT_PLAYER_STAT, stat_mapped).scalar_one_or_none()
        if stat_id is not None:
            counts.player_season_stat += 1
    return player_id


_UPSERT_FIXTURE_DETAIL = text(
    """
    INSERT INTO fixture_detail (
        fixture_id, events, statistics, lineups, players, fetched_at, updated_at
    )
    SELECT
        f.id, CAST(:events AS jsonb), CAST(:statistics AS jsonb),
        CAST(:lineups AS jsonb), CAST(:players AS jsonb), now(), now()
    FROM fixture f
    WHERE f.external_id = :fixture_external_id
    ON CONFLICT (fixture_id) DO UPDATE SET
        events = EXCLUDED.events,
        statistics = EXCLUDED.statistics,
        lineups = EXCLUDED.lineups,
        players = EXCLUDED.players,
        fetched_at = now(),
        updated_at = now()
    RETURNING fixture_id
    """
)


def upsert_fixture_detail(
    session,
    *,
    fixture_external_id: int,
    events: Any,
    statistics: Any,
    lineups: Any,
    players: Any,
    counts: StoreCounts,
) -> bool:
    fixture_id = session.execute(
        _UPSERT_FIXTURE_DETAIL,
        {
            "fixture_external_id": fixture_external_id,
            "events": _json(events),
            "statistics": _json(statistics),
            "lineups": _json(lineups),
            "players": _json(players),
        },
    ).scalar_one_or_none()
    if fixture_id is None:
        return False
    counts.fixture_detail += 1
    upsert_coaches_from_lineups(
        session,
        fixture_external_id=fixture_external_id,
        lineups=lineups,
        counts=counts,
    )
    return True
