"""DB-only public reads and deterministic pre-match evidence assembly."""

from copy import deepcopy
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Fixture, League, LeagueSyncTarget, LeagueTranslation, Team, TeamTranslation
from app.models.home_preview import HomePreviewPublication, HomePreviewVersion
from app.models.player import Player, PlayerTranslation
from app.schemas.home_preview import PreviewPayload, PreviewResponse, structure
from app.services.home_preview_policy import (
    FINISHED,
    KST,
    ONGOING,
    category,
    generation_due_at,
    identity,
    priority,
    utcnow,
)

REASONS = [
    "",
    "빅6 EPL 경기",
    "프리미어리그",
    "빅6 챔피언스리그",
    "챔피언스리그 결승",
    "챔피언스리그 4강",
    "유로파리그 결승",
    "빅6 컵대회",
    "챔피언스리그 8강",
]


def missing(reason="not_collected"):
    return {"status": "missing", "reason": reason, "as_of": None, "source_ids": [], "data": None}


# 미리보기 결과 저장소 두 표. 이 표들은 선택 기능의 저장소이며, 실제 경기·추천
# 목록의 원천이 아니다. 운영 DB에 아직 없을 수 있고, 없다고 해서 홈 추천 목록이
# 실패하면 방문자는 아무 경기도 볼 수 없다. 반대로 **이 두 표 외의** SQL 오류
# (경기·리그 조회, 권한, 연결)는 그대로 올려 보낸다.
PREVIEW_STORAGE_TABLES = frozenset({"home_preview_publication", "home_preview_version"})
STORAGE_ABSENT = "home_preview_storage_absent"


def missing_preview_storage(exc):
    """`UndefinedTable`(42P01)로 실패한 대상이 위 두 표 중 하나인지 판정한다.

    SQLSTATE만 보거나 다른 표의 부재까지 같이 넘기면, 경기·리그 조회 실패를
    "프리뷰 없음"으로 감춰 빈 성공 응답을 만들게 된다. 그래서 실패한 문장이
    그 두 표를 가리킬 때만 참이다.
    """
    orig = getattr(exc, "orig", exc)
    if getattr(orig, "sqlstate", None) != "42P01":
        return False
    table = getattr(getattr(orig, "diag", None), "table_name", None)
    if table:
        return table in PREVIEW_STORAGE_TABLES
    statement = str(getattr(exc, "statement", "") or "")
    return any(f"FROM {name}" in statement for name in PREVIEW_STORAGE_TABLES)


def preview_storage_absent(session):
    """이 세션에서 프리뷰 저장소 표 부재를 이미 확인했는지."""
    return bool(getattr(session, "info", {}).get(STORAGE_ABSENT))


def preview_row(session, model, identifier):
    """저장소 행 하나를 읽는다. 그 저장소 표만 없으면 `None`(미제공)으로 본다.

    조회를 SAVEPOINT 안에서 수행한다. PostgreSQL은 문장 실패 뒤 같은 트랜잭션이
    중단 상태가 되므로, 저장점으로 되돌려야 같은 세션의 후속 경기 조회가 계속
    정상 동작한다. 한 요청에서 표 부재를 한 번 확인하면 세션에 기억해 두고 다시
    시도하지 않는다.
    """
    if preview_storage_absent(session):
        return None
    try:
        with session.begin_nested():
            return session.get(model, identifier)
    except SQLAlchemyError as exc:
        if not missing_preview_storage(exc):
            raise
        try:
            session.info[STORAGE_ABSENT] = True
        except AttributeError:  # 세션 유사 객체(검사용)는 기억을 생략한다.
            pass
        return None


def fixture_by_external(session, external_id):
    fixture = session.scalar(select(Fixture).where(Fixture.external_id == external_id))
    if fixture is None:
        raise LookupError("fixture_not_found")
    return fixture


def names(session):
    teams = {row.id: row for row in session.scalars(select(Team))}
    translations = {
        row.team_id: row.name_ko for row in session.scalars(select(TeamTranslation)) if row.name_ko
    }
    return teams, translations


def team_ref(team, translations):
    return {"external_id": team.external_id, "name": translations.get(team.id) or team.name}


def active_pairs(session):
    targets = list(session.scalars(select(LeagueSyncTarget)))
    seasons = {}
    current = {league.id: league.current_season for league in session.scalars(select(League))}
    for target in targets:
        if current.get(target.league_id) is None or target.season_year <= current[target.league_id]:
            seasons.setdefault(target.league_id, set()).add(target.season_year)
    return {
        (target.league_id, target.season_year)
        for target in targets
        if target.is_active
        and target.season_year in sorted(seasons.get(target.league_id, set()), reverse=True)[:2]
    }


def eligible_rows(session, *, start=None, end=None, include_unranked=False):
    pairs = active_pairs(session)
    if not pairs:
        return []
    query = (
        select(Fixture, League)
        .join(League, League.id == Fixture.league_id)
        .where(
            League.is_active.is_(True),
            Fixture.home_team_id.is_not(None),
            Fixture.away_team_id.is_not(None),
            or_(
                *(
                    and_(Fixture.league_id == league_id, Fixture.season_year == season)
                    for league_id, season in pairs
                )
            ),
        )
    )
    if start is not None:
        query = query.where(Fixture.kickoff_at >= start)
    if end is not None:
        query = query.where(Fixture.kickoff_at <= end)
    teams, translations = names(session)
    result = []
    for fixture, league in session.execute(query):
        home, away = teams.get(fixture.home_team_id), teams.get(fixture.away_team_id)
        if home is None or away is None or home.id == away.id:
            continue
        rank = priority(league, home.external_id, away.external_id, fixture.round)
        if rank is not None or include_unranked:
            result.append((fixture, league, home, away, rank, translations))
    return result


def localize_injury_names(session: Session, preview):
    """Resolve display names in one DB read; leave immutable source evidence untouched."""
    injuries = list(preview["facts"]["injuries"]["data"] or []) + list(
        (preview["facts"].get("player_spotlights") or {}).get("data") or []
    )
    if not injuries:
        return
    ids = {row["player_id"] for row in injuries if row.get("player_id") is not None}
    legacy_names = {row["player_name"] for row in injuries if row.get("player_id") is None}
    rows = session.execute(
        select(Player.external_id, Player.name, PlayerTranslation.name_ko, Player.photo_url)
        .outerjoin(PlayerTranslation, PlayerTranslation.player_id == Player.id)
        .where(or_(Player.external_id.in_(ids), Player.name.in_(legacy_names)))
    ).all()
    by_id = {pid: (ko, photo) for pid, _name, ko, photo in rows}
    by_name = {}
    for pid, name, ko, photo in rows:
        by_name.setdefault(name, []).append((pid, ko, photo))
    for injury in injuries:
        if injury.get("player_id") is not None:
            translated, photo = by_id.get(injury["player_id"], (None, None))
        else:
            matches = by_name.get(injury["player_name"], [])
            translated, photo = (
                (matches[0][1], matches[0][2]) if len(matches) == 1 else (None, None)
            )
        if photo:
            injury["photo_url"] = photo
        if translated and translated.strip():
            injury["player_name"] = translated


def read_preview(session: Session, external_id: int, *, now=None):
    now = now or utcnow()
    fixture = fixture_by_external(session, external_id)
    publication = preview_row(session, HomePreviewPublication, fixture.id)
    preview = None
    if publication and publication.version_id and publication.identity == identity(fixture):
        version = preview_row(session, HomePreviewVersion, publication.version_id)
        if version and version.fixture_id == fixture.id:
            try:
                candidate = PreviewPayload.model_validate(version.payload).root
                teams = [
                    session.get(Team, fixture.home_team_id),
                    session.get(Team, fixture.away_team_id),
                ]
                same_teams = all(
                    team and candidate["fixture"][side]["external_id"] == team.external_id
                    for side, team in zip(("home", "away"), teams)
                )
                if (
                    not candidate["is_mock"]
                    and candidate["fixture"]["external_id"] == external_id
                    and same_teams
                    and datetime.fromisoformat(candidate["fixture"]["kickoff_at"])
                    == fixture.kickoff_at
                ):
                    preview = deepcopy(candidate)
            except ValueError:
                pass
    refresh = {"state": "idle", "last_attempt_at": None, "reason": None}
    if publication and publication.identity == identity(fixture):
        refresh = {
            "state": publication.refresh_state,
            "last_attempt_at": publication.last_attempt_at.isoformat()
            if publication.last_attempt_at
            else None,
            "reason": publication.reason,
        }
    if preview is not None:
        from app.services.home_preview_injuries import deduplicate_injuries
        from app.services.home_preview_web import update_prediction_coverage

        if not preview["external"]["predictions"].get("coverage"):
            update_prediction_coverage(preview)

        rows = preview["facts"]["injuries"]["data"]
        if rows:
            preview["facts"]["injuries"]["data"] = deduplicate_injuries(rows)
            if any(row.get("status_conflict") for row in preview["facts"]["injuries"]["data"]):
                preview["facts"]["injuries"].update(status="partial", reason="source_unverified")
        localize_injury_names(session, preview)
        complete = all(
            block["status"] == "available"
            for group in ("analysis", "facts", "external")
            for block in preview[group].values()
        )
        pub = {
            "state": "ready" if complete else "partial",
            "served": "current" if refresh["state"] == "idle" else "previous",
            "reason": None,
            "generated_at": preview["generated_at"],
            "as_of": preview["as_of"],
        }
    else:
        # A stale publication belongs to a changed identity and cannot leak into the new fixture.
        failed = refresh["state"] == "failed"
        before_window = fixture.kickoff_at > now + timedelta(hours=6)
        kickoff_passed = fixture.kickoff_at <= now or fixture.status_short != "NS"
        unavailable = (
            before_window or kickoff_passed or bool(publication and publication.version_id)
        )
        reason = (
            "generation_failed"
            if failed
            else "kickoff_passed"
            if kickoff_passed
            else "outside_generation_window"
            if before_window
            else "no_valid_snapshot"
            if unavailable
            else "generation_pending"
        )
        if unavailable and not failed:
            refresh = {"state": "idle", "last_attempt_at": None, "reason": None}
        pub = {
            "state": "failed" if failed else "unavailable" if unavailable else "pending",
            "served": None,
            "reason": reason,
            "generated_at": None,
            "as_of": None,
        }
    league = session.get(League, fixture.league_id)
    home = session.get(Team, fixture.home_team_id)
    away = session.get(Team, fixture.away_team_id)
    scheduled = bool(
        league
        and league.is_active
        and home
        and away
        and (fixture.league_id, fixture.season_year) in active_pairs(session)
        and priority(league, home.external_id, away.external_id, fixture.round) is not None
    )
    return PreviewResponse.model_validate(
        {
            "schema_version": "1.0",
            "fixture_id": external_id,
            "generation_due_at": generation_due_at(fixture.kickoff_at).isoformat()
            if scheduled
            else None,
            "publication": pub,
            "refresh": refresh,
            "preview": preview,
        }
    ).root


def recommendations(session, requested_date=None, *, now=None, stored_session=None):
    now = now or utcnow()
    day = requested_date or now.astimezone(KST).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=KST)
    rows = eligible_rows(session, start=start, include_unranked=True)
    today = [r for r in rows if r[0].kickoff_at.astimezone(KST).date() == day]
    selected = [r for r in today if r[4] is not None and r[0].status_short in ONGOING | {"NS"}]
    display = day
    if not selected:
        future = [
            r
            for r in rows
            if r[4] is not None
            and r[0].kickoff_at.astimezone(KST).date() > day
            and r[0].status_short == "NS"
        ]
        if future:
            display = min(r[0].kickoff_at.astimezone(KST).date() for r in future)
            selected = [r for r in future if r[0].kickoff_at.astimezone(KST).date() == display]
    selected.sort(
        key=lambda r: (r[0].status_short not in ONGOING, r[4], r[0].kickoff_at, r[0].external_id)
    )
    league_names = {
        t.league_id: t.name_ko for t in session.scalars(select(LeagueTranslation)) if t.name_ko
    }

    def item(row):
        f, l, h, a, _rank, tr = row
        return {
            "fixture_id": f.external_id,
            "kickoff_at": f.kickoff_at.isoformat(),
            "status_as_of": f.updated_at.isoformat(),
            "competition": {
                "external_id": l.external_id,
                "name": league_names.get(l.id) or l.name,
                "category": category(l),
                "round": f.round or "미정",
            },
            "home": team_ref(h, tr),
            "away": team_ref(a, tr),
        }

    approved = None
    evidence = None
    if stored_session is not None and selected:
        from app.services import home_preview_document

        try:
            approval_rows = home_preview_document._read_approvals(stored_session)
        except SQLAlchemyError as exc:
            raise home_preview_document.PreviewDocumentUnavailable(str(exc)) from exc
        approved = home_preview_document.approved_versions(approval_rows)
        evidence = home_preview_document.approved_evidence(approval_rows)

    items = []
    for row in selected:
        value = item(row)
        fixture_row = row[0]
        if stored_session is not None:
            from app.services import home_preview_document

            preview_summary = home_preview_document.recommendation_preview_status(
                stored_session,
                fixture_row.external_id,
                kickoff_at=fixture_row.kickoff_at,
                status_short=fixture_row.status_short,
                now=now,
                approved=approved,
                evidence=evidence,
            )
        else:
            pub = read_preview(session, fixture_row.external_id, now=now)["publication"]
            preview_summary = {
                key: pub[key] for key in ("state", "served", "generated_at", "as_of")
            }
        value.update(
            state="ongoing" if fixture_row.status_short in ONGOING else "scheduled",
            priority=row[4],
            reason=REASONS[row[4]],
            preview=preview_summary,
        )
        items.append(value)
    results = []
    for row in sorted(today, key=lambda r: (r[0].kickoff_at, r[0].external_id)):
        f = row[0]
        if f.status_short in FINISHED and f.goals_home is not None and f.goals_away is not None:
            results.append(
                dict(
                    **item(row), state="finished", goals_home=f.goals_home, goals_away=f.goals_away
                )
            )
    latest = max((r[0].updated_at for r in rows), default=None)
    value = {
        "schema_version": "1.0",
        "requested_date": day.isoformat(),
        "display_date": display.isoformat(),
        "timezone": "Asia/Seoul",
        "as_of": latest.isoformat() if latest else None,
        "policy_version": "home-priority-2026-10-25",
        "fallback_reason": "no_eligible_today" if display != day else None,
        "items": items,
        "today_results": results,
    }
    structure("recommendations", value)
    return value


def build_db_snapshot(session, fixture, *, now):
    teams, tr = names(session)
    home, away = teams[fixture.home_team_id], teams[fixture.away_team_id]
    cutoff = min(now, fixture.kickoff_at)
    sources = []

    def form(team):
        query = (
            select(Fixture)
            .where(
                or_(Fixture.home_team_id == team.id, Fixture.away_team_id == team.id),
                Fixture.id != fixture.id,
                Fixture.kickoff_at < cutoff,
                Fixture.updated_at <= now,
                Fixture.status_short.in_(FINISHED),
                Fixture.goals_home.is_not(None),
                Fixture.goals_away.is_not(None),
            )
            .order_by(Fixture.kickoff_at.desc(), Fixture.external_id.desc())
            .limit(5)
        )
        rows = list(session.scalars(query))
        matches = []
        observed = []
        for row in rows:
            is_home = row.home_team_id == team.id
            opponent = teams.get(row.away_team_id if is_home else row.home_team_id)
            if opponent is None:
                continue
            league = session.get(League, row.league_id)
            penalties = None
            if (
                row.status_short == "PEN"
                and row.score_pen_home is not None
                and row.score_pen_away is not None
            ):
                penalties = {
                    "for": row.score_pen_home if is_home else row.score_pen_away,
                    "against": row.score_pen_away if is_home else row.score_pen_home,
                }
            matches.append(
                {
                    "fixture_id": row.external_id,
                    "kickoff_at": row.kickoff_at.isoformat(),
                    "opponent": tr.get(opponent.id) or opponent.name,
                    "competition": league.name,
                    "goals_for": row.goals_home if is_home else row.goals_away,
                    "goals_against": row.goals_away if is_home else row.goals_home,
                    "status": row.status_short,
                    "penalties": penalties,
                }
            )
            observed.append(row.updated_at)
        if not matches:
            return missing()
        at = max(observed).isoformat()
        source_id = f"db-form-{team.external_id}"
        sources.append(
            {
                "id": source_id,
                "fixture_id": fixture.external_id,
                "kind": "db",
                "title": f"{tr.get(team.id) or team.name} DB 완료 경기",
                "url": None,
                "published_at": None,
                "retrieved_at": at,
            }
        )
        return {
            "status": "available" if len(matches) == 5 else "partial",
            "reason": None if len(matches) == 5 else "insufficient_sample",
            "as_of": at,
            "source_ids": [source_id],
            "data": {"team_id": team.external_id, "expected_count": 5, "matches": matches},
        }

    facts = {"injuries": missing(), "home_form": form(home), "away_form": form(away)}
    as_of = max([fixture.updated_at] + [datetime.fromisoformat(s["retrieved_at"]) for s in sources])
    if as_of > now:
        raise ValueError("future_db_observation")
    payload = {
        "schema_version": "1.1",
        "is_mock": False,
        "search_suggestions": None,
        "fixture": {
            "external_id": fixture.external_id,
            "kickoff_at": fixture.kickoff_at.isoformat(),
            "home": team_ref(home, tr),
            "away": team_ref(away, tr),
        },
        "generated_at": None,
        "as_of": as_of.isoformat(),
        "sources": sources,
        "analysis": {
            key: missing("generation_pending") for key in ("summary", "key_points", "ai_prediction")
        },
        "facts": facts,
        "external": {"predictions": missing(), "odds": missing()},
    }
    return PreviewPayload.model_validate(payload).root
