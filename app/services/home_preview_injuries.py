"""Deterministic injury identity and DB participation evidence, never LLM facts."""

from copy import deepcopy

from sqlalchemy import select

from app.models import Fixture, FixtureDetail, LeagueSyncTarget, Team
from app.models.player import Player, PlayerSeasonStat
from app.services.home_preview_policy import FINISHED


def deduplicate_injuries(rows):
    unique = {}
    for raw in rows:
        row = deepcopy(raw)
        key = (row["team_id"], row.get("player_id") or row["player_name"])
        if key not in unique:
            unique[key] = row
            continue
        existing = unique[key]
        existing["source_ids"] = list(dict.fromkeys(existing["source_ids"] + row["source_ids"]))
        if existing["availability"] != row["availability"] or row.get("status_conflict"):
            existing.update(
                availability="doubtful",
                status_conflict=True,
                detail="자료 간 결장 상태 불일치",
                impact="출전 상태 추가 확인 필요",
            )
        elif not existing.get("status_conflict") and row["detail"] != existing["detail"]:
            existing["detail"] = " / ".join(dict.fromkeys([existing["detail"], row["detail"]]))
    return list(unique.values())


def groups(value):
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return groups(value.get("response"))
    return []


def qualifies(evidence):
    return (
        (evidence["recent_starts"] or 0) >= 3
        or (evidence["recent_minutes"] or 0) >= 180
        or any(
            (row["appearances"] or 0) >= 5 or (row["minutes"] or 0) >= 450
            for row in evidence["seasons"]
        )
    )


def selection_reason(evidence):
    parts = []
    if evidence["recent_starts"] is not None:
        parts.append(
            f"선발 정보가 확인된 최근 {evidence['lineup_games']}경기 중 선발 {evidence['recent_starts']}회"
        )
    if evidence["recent_minutes"] is not None:
        parts.append(f"확인된 최근 출전 시간 합계 {evidence['recent_minutes']}분")
    for season in evidence["seasons"]:
        numbers = []
        if season["appearances"] is not None:
            numbers.append(f"{season['appearances']}경기 출전")
        if season["minutes"] is not None:
            numbers.append(f"{season['minutes']}분")
        if numbers:
            parts.append(f"{season['season_year']}시즌 " + "·".join(numbers))
    return ". ".join(parts) + ". 출전 기록을 근거로 주요 결장 변수로 선별했습니다."


def enrich_importance(session, payload, *, now):
    block = payload["facts"]["injuries"]
    if not block["data"]:
        return
    block["data"] = deduplicate_injuries(block["data"])
    fixture = session.scalar(
        select(Fixture).where(Fixture.external_id == payload["fixture"]["external_id"])
    )
    cutoff = min(now, fixture.kickoff_at)
    years = list(
        session.scalars(
            select(LeagueSyncTarget.season_year)
            .where(
                LeagueSyncTarget.league_id == fixture.league_id,
                LeagueSyncTarget.season_year <= fixture.season_year,
            )
            .order_by(LeagueSyncTarget.season_year.desc())
            .limit(2)
        )
    )
    for injury in block["data"]:
        injury.pop("importance_evidence", None)
    for side in ("home", "away"):
        team_id = payload["fixture"][side]["external_id"]
        team = session.scalar(select(Team).where(Team.external_id == team_id))
        injuries = [
            row for row in block["data"] if row["team_id"] == team_id and row.get("player_id")
        ]
        if not team or not injuries:
            continue
        ids = {row["player_id"] for row in injuries}
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
        details = list(
            session.scalars(
                select(FixtureDetail).where(
                    FixtureDetail.fixture_id.in_([row.id for row in recent]),
                    FixtureDetail.updated_at <= cutoff,
                    FixtureDetail.fetched_at <= cutoff,
                )
            )
        )
        stats = session.execute(
            select(Player.external_id, PlayerSeasonStat)
            .join(PlayerSeasonStat, PlayerSeasonStat.player_id == Player.id)
            .where(
                Player.external_id.in_(ids),
                PlayerSeasonStat.team_id == team.id,
                PlayerSeasonStat.league_id == fixture.league_id,
                PlayerSeasonStat.season_year.in_(years),
                PlayerSeasonStat.updated_at <= cutoff,
            )
        ).all()
        lineups = []
        player_groups = []
        for detail in details:
            for lineup in groups(detail.lineups):
                starters = lineup.get("startXI")
                if (
                    lineup.get("team", {}).get("id") == team_id
                    and isinstance(starters, list)
                    and len(starters) == 11
                ):
                    start_ids = {
                        entry.get("player", {}).get("id")
                        for entry in starters
                        if isinstance(entry, dict)
                    }
                    if len(start_ids) == 11 and None not in start_ids:
                        lineups.append(start_ids)
                        break
            for group in groups(detail.players):
                if group.get("team", {}).get("id") == team_id and isinstance(
                    group.get("players"), list
                ):
                    player_groups.append(group["players"])
                    break
        observations = [detail.updated_at for detail in details] + [
            stat.updated_at for _pid, stat in stats
        ]
        if not lineups and not player_groups and not stats:
            continue
        sid = f"db-injury-participation-{team_id}"
        observed = max(observations).isoformat()
        payload["sources"].append(
            {
                "id": sid,
                "fixture_id": fixture.external_id,
                "kind": "db",
                "title": f"{payload['fixture'][side]['name']} DB 출전 기록 (최근 최대 10경기·리그 최신 2시즌)",
                "url": None,
                "published_at": None,
                "retrieved_at": observed,
            }
        )
        for injury in injuries:
            pid = injury["player_id"]
            minutes = []
            for entries in player_groups:
                for entry in entries:
                    if entry.get("player", {}).get("id") != pid:
                        continue
                    statistics = entry.get("statistics") or []
                    value = (
                        (statistics[0].get("games") or {}).get("minutes") if statistics else None
                    )
                    if type(value) is int and value >= 0:
                        minutes.append(value)
                    break
            seasons = [
                {
                    "season_year": stat.season_year,
                    "appearances": stat.appearances,
                    "minutes": stat.minutes,
                }
                for stat_pid, stat in stats
                if stat_pid == pid
            ]
            evidence = {
                "eligible": False,
                "recent_games": len(recent),
                "lineup_games": len(lineups),
                "player_games": len(player_groups),
                "recent_starts": sum(pid in lineup for lineup in lineups) if lineups else None,
                "recent_minutes": sum(minutes) if minutes else None,
                "seasons": seasons,
                "source_ids": [sid],
            }
            evidence["eligible"] = qualifies(evidence) and not injury.get("status_conflict", False)
            evidence["selection_reason"] = selection_reason(evidence)
            injury["importance_evidence"] = evidence
