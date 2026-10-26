"""Pure main recommendation policy, independent of AX and display translations."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ONGOING = {"1H", "HT", "2H", "ET", "BT", "P", "INT", "LIVE"}
FINISHED = {"FT", "AET", "PEN"}
BIG_SIX = {40, 50, 33, 47, 49, 42}


def utcnow():
    return datetime.now(UTC)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def identity(fixture):
    return digest(
        [
            fixture.external_id,
            fixture.home_team_id,
            fixture.away_team_id,
            fixture.league_id,
            fixture.season_year,
            fixture.kickoff_at.isoformat(),
        ]
    )


def category(league):
    if league.external_id == 39:
        return "epl"
    if league.external_id == 2:
        return "ucl"
    if league.external_id == 3:
        return "uel"
    if league.type == "Cup" and (league.country_name or "").lower() == "england":
        return "domestic_cup"
    return "other"


def priority(league, home_id, away_id, round_):
    big = home_id in BIG_SIX or away_id in BIG_SIX
    kind = category(league)
    stage = (round_ or "").lower().strip()
    if league.external_id in {45, 48} and stage.split(" - ", 1)[0] not in {
        "4강",
        "준결승",
        "semi-finals",
        "semi-final",
        "semifinals",
        "결승",
        "final",
    }:
        return None
    quarter = stage in {"8강", "quarter-finals", "quarter-final", "quarterfinals"}
    semi = stage in {"4강", "semi-finals", "semi-final", "semifinals"}
    final = stage in {"결승", "final"}
    if kind == "epl":
        return 1 if big else 2
    if kind == "ucl" and big and (quarter or semi or final):
        return 3
    if kind == "ucl" and final:
        return 4
    if kind == "ucl" and semi:
        return 5
    if kind == "uel" and final and not big:
        return 6
    if kind in {"uel", "domestic_cup"} and big:
        return 7
    if kind == "ucl" and quarter:
        return 8
    return None


def slot_time(now):
    local = now.astimezone(KST)
    return local.replace(hour=local.hour // 6 * 6, minute=0, second=0, microsecond=0).astimezone(
        UTC
    )


def generation_due_at(kickoff):
    """Last scheduled KST 00/06/12/18 sync strictly before kickoff."""
    return slot_time(kickoff - timedelta(microseconds=1))


def in_generation_window(kickoff, now):
    return now < kickoff <= now + timedelta(hours=6)
