"""Bounded DB-only player records. Unknown games never extend a streak."""

from sqlalchemy import select

from app.models import Fixture, FixtureDetail, Team
from app.models.player import Player, PlayerSeasonStat, PlayerTranslation
from app.services.home_preview_injuries import groups
from app.services.home_preview_policy import FINISHED

FOCUSES = ("season_contribution", "scoring_streak", "assist_streak", "involvement_streak")


def nonnegative(value):
    return value if type(value) is int and value >= 0 else None


def streaks(matches, player_id):
    counts = dict.fromkeys(FOCUSES[1:], 0)
    continuing = dict.fromkeys(counts, True)
    for entries in matches:
        player = next(
            (row for row in entries or [] if row.get("player", {}).get("id") == player_id), None
        )
        stats = (player.get("statistics") or []) if player else []
        goals = stats[0].get("goals") or {} if stats else {}
        scored, assists = nonnegative(goals.get("total")), nonnegative(goals.get("assists"))
        checks = {
            "scoring_streak": (scored or 0) > 0,
            "assist_streak": (assists or 0) > 0,
            "involvement_streak": (scored or 0) > 0 or (assists or 0) > 0,
        }
        for key in counts:
            if continuing[key] and checks[key]:
                counts[key] += 1
            else:
                continuing[key] = False
    return counts


def recent_form(matches, player_id):
    result = {
        "team_match_count": len(matches),
        "observed_appearances": 0,
        "goals": None,
        "assists": None,
        "minutes": None,
        "goal_samples": 0,
        "assist_samples": 0,
        "minute_samples": 0,
    }
    for entries in matches:
        player = next(
            (row for row in entries or [] if row.get("player", {}).get("id") == player_id), None
        )
        stats = (player.get("statistics") or []) if player else []
        if not stats:
            continue
        values = {
            "goals": nonnegative((stats[0].get("goals") or {}).get("total")),
            "assists": nonnegative((stats[0].get("goals") or {}).get("assists")),
            "minutes": nonnegative((stats[0].get("games") or {}).get("minutes")),
        }
        if not any((value or 0) > 0 for value in values.values()):
            continue
        result["observed_appearances"] += 1
        for field, sample in (
            ("goals", "goal_samples"),
            ("assists", "assist_samples"),
            ("minutes", "minute_samples"),
        ):
            if values[field] is not None:
                result[field] = (result[field] or 0) + values[field]
                result[sample] += 1
    return result


def record_notes(player):
    season = []
    for field, unit in (
        ("appearances", "경기 출전"),
        ("goals", "골"),
        ("assists", "도움"),
        ("minutes", "분"),
    ):
        if player[field] is not None:
            season.append(f"{player[field]}{unit}")
    notes = {
        "season_contribution": f"{player['season_year']}시즌 이 대회에서 " + " · ".join(season)
        if season
        else None
    }
    for key, label in (
        ("scoring_streak", "득점"),
        ("assist_streak", "도움"),
        ("involvement_streak", "공격포인트"),
    ):
        n = player[key]
        notes[key] = f"확인된 최근 팀 {n}경기에서 연속 {label}" if n >= 2 else None
    form = player.get("recent_form")
    notes["recent_contribution"] = None
    if form and form["observed_appearances"]:
        parts = [
            f"최근 팀 {form['team_match_count']}경기 중 출전 확인 {form['observed_appearances']}경기"
        ]
        for field, sample, label, unit in (
            ("goals", "goal_samples", "득점", "골"),
            ("assists", "assist_samples", "도움", "도움"),
            ("minutes", "minute_samples", "출전 시간", "분"),
        ):
            if form[field] is not None:
                parts.append(f"{label} 자료 {form[sample]}경기 합계 {form[field]}{unit}")
        notes["recent_contribution"] = " · ".join(parts)
    return notes


def enrich_player_spotlights(session, payload, *, now):
    fixture = session.scalar(
        select(Fixture).where(Fixture.external_id == payload["fixture"]["external_id"])
    )
    cutoff = min(now, fixture.kickoff_at)
    all_candidates, source_ids, observed_times = [], [], []
    unavailable = {
        (row["team_id"], row.get("player_id"))
        for row in payload["facts"]["injuries"]["data"] or []
        if row["availability"] == "out" or row.get("status_conflict")
    }
    for side in ("home", "away"):
        team_id = payload["fixture"][side]["external_id"]
        team = session.scalar(select(Team).where(Team.external_id == team_id))
        if not team:
            continue
        recent = list(
            session.scalars(
                select(Fixture)
                .where(
                    (Fixture.home_team_id == team.id) | (Fixture.away_team_id == team.id),
                    Fixture.id != fixture.id,
                    Fixture.kickoff_at < cutoff,
                    Fixture.updated_at <= cutoff,
                    Fixture.status_short.in_(FINISHED),
                )
                .order_by(Fixture.kickoff_at.desc(), Fixture.external_id.desc())
                .limit(10)
            )
        )
        details = {
            row.fixture_id: row
            for row in session.scalars(
                select(FixtureDetail).where(
                    FixtureDetail.fixture_id.in_([row.id for row in recent]),
                    FixtureDetail.updated_at <= cutoff,
                    FixtureDetail.fetched_at <= cutoff,
                )
            )
        }
        observations = []
        matches = []
        for match in recent:
            detail = details.get(match.id)
            entries = next(
                (
                    group.get("players")
                    for group in groups(detail.players if detail else None)
                    if group.get("team", {}).get("id") == team_id
                ),
                None,
            )
            entries = entries if isinstance(entries, list) else None
            matches.append(entries)
            if detail and entries:
                observations.append(detail.updated_at)
        rows = session.execute(
            select(Player, PlayerSeasonStat, PlayerTranslation.name_ko)
            .join(PlayerSeasonStat, PlayerSeasonStat.player_id == Player.id)
            .outerjoin(PlayerTranslation, PlayerTranslation.player_id == Player.id)
            .where(
                PlayerSeasonStat.team_id == team.id,
                PlayerSeasonStat.league_id == fixture.league_id,
                PlayerSeasonStat.season_year == fixture.season_year,
                PlayerSeasonStat.updated_at <= cutoff,
                Player.updated_at <= cutoff,
                (Player.current_team_id == team.id) | Player.current_team_id.is_(None),
            )
        ).all()
        # Current-season stats establish the player's team. Do not reuse a transfer's old team data.
        candidates = []
        for player, stats, name_ko in rows:
            pid = player.external_id
            if (team_id, pid) in unavailable:
                continue
            item = {
                "team_id": team_id,
                "player_id": pid,
                "player_name": name_ko or player.name,
                "photo_url": player.photo_url,
                "canonical_name": player.name,
                "season_year": stats.season_year,
                **{
                    field: nonnegative(getattr(stats, field))
                    for field in ("appearances", "goals", "assists", "minutes")
                },
                "recent_match_count": len(recent),
                **streaks(matches, pid),
                "source_ids": [f"db-player-spotlights-{team_id}"],
            }
            item["recent_form"] = recent_form(matches, pid)
            item["record_notes"] = record_notes(item)
            if not any(item["record_notes"].values()):
                continue
            candidates.append((item, stats.updated_at))
        candidates.sort(
            key=lambda row: (
                -max(row[0][key] if row[0][key] >= 2 else 0 for key in FOCUSES[1:]),
                -((row[0]["goals"] or 0) + (row[0]["assists"] or 0)),
                -(row[0]["minutes"] or 0),
                row[0]["player_id"],
            )
        )
        selected = candidates[:4]
        if not selected:
            continue
        sid = f"db-player-spotlights-{team_id}"
        observations.extend(row[1] for row in selected)
        at = max(observations)
        payload["sources"].append(
            {
                "id": sid,
                "fixture_id": fixture.external_id,
                "kind": "db",
                "title": f"{payload['fixture'][side]['name']} DB 선수 시즌 기록·최근 팀 경기 기록",
                "url": None,
                "published_at": None,
                "retrieved_at": at.isoformat(),
            }
        )
        source_ids.append(sid)
        observed_times.append(at)
        all_candidates.extend(row[0] for row in selected)
    if not all_candidates:
        payload["facts"]["player_spotlights"] = {
            "status": "missing",
            "reason": "not_collected",
            "as_of": None,
            "source_ids": [],
            "data": None,
        }
    else:
        at = max(observed_times).isoformat()
        payload["as_of"] = max(payload["as_of"], at)
        payload["facts"]["player_spotlights"] = {
            "status": "available",
            "reason": None,
            "as_of": at,
            "source_ids": source_ids,
            "data": all_candidates,
        }
