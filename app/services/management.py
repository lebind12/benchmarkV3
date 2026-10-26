"""Evaluated management UI data, shared targets and optimistic translation edits."""

from __future__ import annotations
from sqlalchemy import Text, and_, case, func, literal, or_, select, text, update
import json
from pathlib import Path
import re
from sqlalchemy.dialects.postgresql import insert
from app.models import (
    AppUser,
    League,
    LeagueTranslation,
    Team,
    TeamTranslation,
    Player,
    PlayerTranslation,
    Coach,
    CoachTranslation,
    ApiFootballLeagueCatalog,
    LeagueSyncTarget,
    TranslationAudit,
    Fixture,
    PlayerSeasonStat,
    Standings,
    TeamSeason,
    TeamCoach,
    Injury,
)
from app.services import admin
from app.workers.daily_sync.mappers import select_latest_two_actual_seasons

ENTITIES = {
    "league": (League, LeagueTranslation),
    "team": (Team, TeamTranslation),
    "player": (Player, PlayerTranslation),
    "coach": (Coach, CoachTranslation),
}


class ManagementError(ValueError):
    def __init__(
        self, message: str, status: int = 422, code: str = "invalid_request", current=None
    ):
        super().__init__(message)
        self.status, self.code, self.current = status, code, current


def iso(value):
    return value.isoformat() if value else None


def allowed_seasons(catalog):
    return select_latest_two_actual_seasons({"seasons": catalog.seasons or []})


DISCOVERY = json.loads(
    (Path(__file__).resolve().parents[1] / "data/catalog_discovery.json").read_text()
)
CATALOG_HINTS = {item["id"]: item for item in DISCOVERY["competitions"]}


def catalog_hint(row):
    hint = CATALOG_HINTS.get(row.external_id)
    return hint if hint and hint["source"] == row.name else None


def normalize_catalog(value):
    return re.sub(r"[\s_-]+", "", value.lower())


def catalog_payload(row, translated=None, human_modified=False):
    years = allowed_seasons(row)
    supported = [s for s in (row.seasons or []) if s.get("year") in years]
    hint = catalog_hint(row)
    return {
        "id": row.external_id,
        "name": (translated or "").strip()
        or (hint["name"] if hint and not human_modified else row.name),
        "type": row.type,
        "country_label": DISCOVERY["countries"].get(
            row.country_name, row.country_name or "국가 정보 없음"
        ),
        "aliases": hint["aliases"] if hint else [],
        "featured": bool(hint),
        "name_en": row.name,
        "logo_url": row.logo_url,
        "country": row.country_name or "",
        "seasons": years,
        "standings": any(s.get("coverage", {}).get("standings") for s in supported),
    }


def catalog_list(
    session, query="", league_id=None, *, country="", kind="", group="", page=1, page_size=100
):
    catalog = ApiFootballLeagueCatalog

    def recognized(hint):
        return and_(catalog.external_id == hint["id"], catalog.name == hint["source"])

    hinted_name = case(
        *[(recognized(h), h["name"]) for h in CATALOG_HINTS.values()], else_=catalog.name
    )
    display_name = func.coalesce(
        func.nullif(func.btrim(LeagueTranslation.name_ko), ""),
        case((LeagueTranslation.human_modified.is_(True), catalog.name), else_=hinted_name),
    )
    country_name = case(
        *[(catalog.country_name == key, value) for key, value in DISCOVERY["countries"].items()],
        else_=catalog.country_name,
    )
    statement = (
        select(catalog, LeagueTranslation.name_ko, LeagueTranslation.human_modified)
        .outerjoin(League, League.external_id == catalog.external_id)
        .outerjoin(LeagueTranslation, LeagueTranslation.league_id == League.id)
    )
    normalized = normalize_catalog(query.strip())
    escaped = normalized.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    if league_id is not None:
        statement = statement.where(catalog.external_id == league_id)
    elif normalized:
        combined = func.concat_ws(
            " ",
            catalog.name,
            display_name,
            catalog.country_name,
            country_name,
            LeagueTranslation.short_name_ko,
        )
        normalized_column = func.regexp_replace(func.lower(combined), r"[[:space:]_-]+", "", "g")
        matches = [
            recognized(h)
            for h in CATALOG_HINTS.values()
            if normalized in normalize_catalog(" ".join([h["source"], h["name"], *h["aliases"]]))
        ]
        # Short Latin prefixes start at a word boundary: EPL must not match
        # "LeaguE PLay-offs" merely because spaces were removed.
        text_match = (
            combined.op("~*")(rf"\m{re.escape(normalized)}")
            if re.fullmatch(r"[a-z]{1,4}", normalized)
            else normalized_column.ilike(f"%{escaped}%", escape="\\")
        )
        statement = statement.where(or_(text_match, *matches))
    if country:
        statement = statement.where(catalog.country_name == country)
    if kind:
        statement = statement.where(catalog.type == kind)
    if group:
        statement = statement.where(
            or_(
                literal(False),
                *[recognized(h) for h in CATALOG_HINTS.values() if group in h["groups"]],
            )
        )
    total = session.scalar(select(func.count()).select_from(statement.subquery()))
    # Exact aliases outrank partial results. Stable curated ordering helps event discovery.
    exact = [
        recognized(h)
        for h in CATALOG_HINTS.values()
        if normalized
        and normalized in [normalize_catalog(v) for v in [h["source"], h["name"], *h["aliases"]]]
    ]
    rank = case(
        *[(recognized(h), index) for index, h in enumerate(CATALOG_HINTS.values())], else_=10000
    )
    exact_rank = case((or_(literal(False), *exact), 0), else_=1)
    rows = session.execute(
        statement.order_by(
            case((display_name.op("~")("[가-힣]"), 0), else_=1),
            exact_rank,
            rank,
            catalog.name,
            catalog.external_id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    countries = session.scalars(
        select(catalog.country_name)
        .where(catalog.country_name.is_not(None))
        .distinct()
        .order_by(catalog.country_name)
    ).all()
    return {
        "items": [
            catalog_payload(row, translated, protected) for row, translated, protected in rows
        ],
        "total": total,
        "catalog_total": session.scalar(select(func.count()).select_from(catalog)),
        "page": page,
        "page_size": page_size,
        "countries": [
            {"value": value, "label": DISCOVERY["countries"].get(value, value)}
            for value in sorted(
                countries,
                key=lambda value: (
                    not bool(re.search("[가-힣]", DISCOVERY["countries"].get(value, value))),
                    DISCOVERY["countries"].get(value, value),
                ),
            )
        ],
        "updated_at": iso(session.scalar(select(func.max(catalog.last_synced_at)))),
    }


def reconcile_league(session, league_id):
    league = session.scalar(select(League).where(League.id == league_id).with_for_update())
    catalog = session.scalar(
        select(ApiFootballLeagueCatalog).where(
            ApiFootballLeagueCatalog.external_id == league.external_id
        )
    )
    years = allowed_seasons(catalog) if catalog else []
    targets = session.scalars(
        select(LeagueSyncTarget).where(LeagueSyncTarget.league_id == league_id)
    ).all()
    for target in targets:
        if target.season_year not in years:
            target.is_active = False
    league.is_active = any(t.is_active and t.season_year in years for t in targets)
    return league.is_active


def target_payload(session, target):
    league = session.get(League, target.league_id)
    translated = session.get(LeagueTranslation, league.id)
    return {
        "id": target.id,
        "league_id": league.external_id,
        "name": (translated.name_ko if translated else None) or league.name,
        "name_en": league.name,
        "logo_url": league.logo_url,
        "country": league.country_name or "",
        "season": target.season_year,
        "is_active": target.is_active,
        "include_details": target.include_details,
        "include_players": target.include_players,
        "include_standings": target.include_standings,
        "fixture_limit": target.fixture_limit,
        "initial_status": target.initial_status,
        "last_sync": iso(target.last_sync),
    }


def targets_list(session):
    targets = session.scalars(select(LeagueSyncTarget).order_by(LeagueSyncTarget.id)).all()
    return {
        "items": [target_payload(session, row) for row in targets],
        "persistence_available": True,
    }


def save_target(session, changes, target_id=None):
    if target_id is None:
        cat = session.scalar(
            select(ApiFootballLeagueCatalog).where(
                ApiFootballLeagueCatalog.external_id == changes["league_id"]
            )
        )
        if not cat:
            raise ManagementError("저장된 카탈로그에서 리그를 찾지 못했습니다.", 404)
        if changes["season"] not in allowed_seasons(cat):
            raise ManagementError("최신 두 실제 개최 시즌만 수집할 수 있습니다.")
        result = admin.upsert_sync_target(
            session,
            league_external_id=cat.external_id,
            season_year=changes["season"],
            options=admin.SyncTargetOptions(
                **{k: v for k, v in changes.items() if k not in {"league_id", "season"}}
            ),
        )
        target = session.get(LeagueSyncTarget, result["id"])
    else:
        target = session.get(LeagueSyncTarget, target_id)
        if not target:
            raise ManagementError("수집 대상이 없습니다.", 404)
        session.scalar(select(League).where(League.id == target.league_id).with_for_update())
        # League and season identity are immutable for an existing setting.
        league_ref = session.get(League, target.league_id)
        if ("league_id" in changes and changes["league_id"] != league_ref.external_id) or (
            "season" in changes and changes["season"] != target.season_year
        ):
            raise ManagementError(
                "등록된 대상의 리그·시즌은 변경할 수 없습니다. 새 대상을 추가하세요."
            )
        for key in ("league_id", "season"):
            changes.pop(key, None)
        if changes.get("is_active"):
            league = session.get(League, target.league_id)
            cat = session.scalar(
                select(ApiFootballLeagueCatalog).where(
                    ApiFootballLeagueCatalog.external_id == league.external_id
                )
            )
            if not cat or target.season_year not in allowed_seasons(cat):
                raise ManagementError("최신 두 개최 시즌 밖의 대상은 활성화할 수 없습니다.")
        for key, value in changes.items():
            setattr(target, key, value)
    session.flush()
    league = session.get(League, target.league_id)
    cat = session.scalar(
        select(ApiFootballLeagueCatalog).where(
            ApiFootballLeagueCatalog.external_id == league.external_id
        )
    )
    coverage = (
        next(
            (s.get("coverage", {}) for s in cat.seasons if s.get("year") == target.season_year), {}
        )
        if cat
        else {}
    )
    if not coverage.get("standings"):
        target.include_standings = False
    reconcile_league(session, target.league_id)
    session.commit()
    return target_payload(session, target)


def remove_target(session, target_id):
    target = session.get(LeagueSyncTarget, target_id)
    if not target:
        raise ManagementError("수집 대상이 없습니다.", 404)
    league_id = target.league_id
    session.scalar(select(League).where(League.id == league_id).with_for_update())
    session.delete(target)
    session.flush()
    reconcile_league(session, league_id)
    session.commit()
    return {"removed": True}


def translation_models(kind):
    if kind not in ENTITIES:
        raise ManagementError("지원하지 않는 번역 종류입니다.", 404)
    entity, translation = ENTITIES[kind]
    return entity, translation, getattr(translation, f"{kind}_id")


def translation_payload(entity, translation, kind, editor=None):
    return {
        "id": entity.id,
        "type": kind,
        "original": entity.name,
        "context": f"#{entity.external_id}",
        "name_ko": translation.name_ko if translation else None,
        "short_name_ko": translation.short_name_ko if translation else None,
        "version": translation.version if translation else 0,
        "protected": translation.human_modified if translation else False,
        "editor": editor.nickname or editor.email if editor else "자동번역/기존 자료",
        "updated_at": iso(translation.updated_at if translation else entity.updated_at),
    }


def _affiliation_relation(kind):
    if kind == "player":
        return select(
            PlayerSeasonStat.player_id.label("entity_id"),
            PlayerSeasonStat.team_id.label("team_id"),
            PlayerSeasonStat.league_id.label("league_id"),
        ).subquery()
    if kind == "coach":
        # team_coach stores the last observed competition, not one row per league.
        # Include the same team's recorded league memberships to avoid missing cup coaches.
        direct = select(
            TeamCoach.coach_id.label("entity_id"),
            TeamCoach.team_id.label("team_id"),
            TeamCoach.league_id.label("league_id"),
        )
        membership = select(
            TeamCoach.coach_id.label("entity_id"),
            TeamCoach.team_id.label("team_id"),
            TeamSeason.league_id.label("league_id"),
        ).join(TeamSeason, TeamSeason.team_id == TeamCoach.team_id)
        return direct.union_all(membership).subquery()
    raise ManagementError("리그·팀 조건은 선수와 감독 검색에서 사용할 수 있습니다.")


def translation_affiliation_filters(session, kind="player", league_id=None):
    relation = _affiliation_relation(kind)
    league_name = func.coalesce(func.nullif(LeagueTranslation.name_ko, ""), League.name).label(
        "name"
    )
    team_name = func.coalesce(func.nullif(TeamTranslation.name_ko, ""), Team.name).label("name")
    leagues = (
        session.execute(
            select(
                League.external_id.label("id"),
                league_name,
                League.name.label("name_en"),
                League.logo_url,
            )
            .select_from(relation)
            .join(League, League.id == relation.c.league_id)
            .outerjoin(LeagueTranslation, LeagueTranslation.league_id == League.id)
            .distinct()
            .order_by("name", League.external_id)
        )
        .mappings()
        .all()
    )
    statement = (
        select(Team.external_id.label("id"), team_name, Team.name.label("name_en"), Team.logo_url)
        .select_from(relation)
        .join(Team, Team.id == relation.c.team_id)
        .outerjoin(TeamTranslation, TeamTranslation.team_id == Team.id)
    )
    if league_id is not None:
        statement = statement.join(League, League.id == relation.c.league_id).where(
            League.external_id == league_id
        )
    teams = (
        session.execute(statement.distinct().order_by("name", Team.external_id)).mappings().all()
    )
    return {"leagues": [dict(row) for row in leagues], "teams": [dict(row) for row in teams]}


def _translation_affiliation_match(kind, entity, league_id, team_id):
    relation = _affiliation_relation(kind)
    statement = (
        select(1)
        .select_from(relation.join(Team, Team.id == relation.c.team_id))
        .where(relation.c.entity_id == entity.id)
    )
    if league_id is not None:
        statement = statement.join(League, League.id == relation.c.league_id).where(
            League.external_id == league_id
        )
    if team_id is not None:
        statement = statement.where(Team.external_id == team_id)
    return statement.correlate(entity).exists()


def translations_list(
    session, *, query="", kind="all", status="all", page=1, league_id=None, team_id=None
):
    # Query all four types in SQL; pagination never limits the searchable domain.
    from sqlalchemy import literal, union_all

    if (league_id is not None or team_id is not None) and kind not in {"player", "coach"}:
        raise ManagementError("리그·팀 조건은 선수와 감독 검색에서 사용할 수 있습니다.")
    statements = []
    missing_count = 0
    for key, (entity, trans) in ENTITIES.items():
        fk = getattr(trans, f"{key}_id")
        missing_count += session.scalar(
            select(func.count())
            .select_from(entity)
            .outerjoin(trans, fk == entity.id)
            .where(func.coalesce(func.btrim(trans.name_ko), "") == "")
        )
        if kind != "all" and key != kind:
            continue
        stmt = (
            select(
                literal(key).label("type"),
                entity.id.label("id"),
                entity.external_id.label("external_id"),
                entity.name.label("name"),
                trans.name_ko.label("name_ko"),
                trans.short_name_ko.label("short_name_ko"),
                func.coalesce(trans.version, 0).label("version"),
                func.coalesce(trans.human_modified, False).label("protected"),
                func.coalesce(trans.updated_at, entity.updated_at).label("updated_at"),
                func.coalesce(AppUser.nickname, AppUser.email, "자동번역/기존 자료").label(
                    "editor"
                ),
            )
            .outerjoin(trans, fk == entity.id)
            .outerjoin(AppUser, AppUser.id == trans.editor_id)
        )
        if league_id is not None or team_id is not None:
            stmt = stmt.where(_translation_affiliation_match(key, entity, league_id, team_id))
        if query:
            pattern = f"%{query}%"
            stmt = stmt.where(
                or_(
                    entity.name.ilike(pattern),
                    trans.name_ko.ilike(pattern),
                    trans.short_name_ko.ilike(pattern),
                    entity.external_id.cast(Text).ilike(pattern),
                )
            )
        if status == "translated":
            stmt = stmt.where(func.coalesce(func.btrim(trans.name_ko), "") != "")
        elif status == "untranslated":
            stmt = stmt.where(func.coalesce(func.btrim(trans.name_ko), "") == "")
        statements.append(stmt)
    if not statements:
        raise ManagementError("지원하지 않는 번역 종류입니다.")
    entries = union_all(*statements).subquery()
    total = session.scalar(select(func.count()).select_from(entries))
    result = (
        session.execute(
            select(entries)
            .order_by(entries.c.type, entries.c.name, entries.c.id)
            .offset((page - 1) * 50)
            .limit(50)
        )
        .mappings()
        .all()
    )
    items = [
        {
            **dict(row),
            "original": row["name"],
            "context": f"#{row['external_id']}",
            "updated_at": iso(row["updated_at"]),
        }
        for row in result
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": 50,
        "missing_count": missing_count,
    }


def edit_translation(session, kind, entity_id, values, user):
    entity, trans, fk = translation_models(kind)
    original = session.get(entity, entity_id)
    if original is None:
        raise ManagementError("번역 대상이 없습니다.", 404)
    # Ensure absent translation row without overwriting existing translations.
    session.execute(insert(trans).values({f"{kind}_id": entity_id}).on_conflict_do_nothing())
    row = session.scalar(select(trans).where(fk == entity_id).with_for_update())
    expected = values["expected_version"]
    if expected != row.version and not (
        expected == 0 and row.version == 1 and row.name_ko is None and not row.human_modified
    ):
        current = translation_payload(
            original, row, kind, session.get(AppUser, row.editor_id) if row.editor_id else None
        )
        session.rollback()
        raise ManagementError(
            "다른 사용자가 먼저 수정했습니다. 최신값과 비교해 주세요.",
            409,
            "version_conflict",
            current,
        )
    before = {"name_ko": row.name_ko, "short_name_ko": row.short_name_ko}
    after = {key: (values[key] or "").strip() or None for key in ("name_ko", "short_name_ko")}
    session.execute(text("SELECT set_config('app.translation_edit', 'on', true)"))
    session.execute(
        update(trans)
        .where(fk == entity_id, trans.version == row.version)
        .values(**after, human_modified=True, editor_id=user.id)
    )
    session.refresh(row)
    session.add(
        TranslationAudit(
            entity_type=kind,
            entity_id=entity_id,
            version=row.version,
            editor_id=user.id,
            editor_name=user.nickname or user.email,
            before=before,
            after=after,
        )
    )
    session.commit()
    return translation_payload(original, row, kind, user)


def translation_history(session, kind, entity_id):
    entity, _, _ = translation_models(kind)
    if not session.get(entity, entity_id):
        raise ManagementError("번역 대상이 없습니다.", 404)
    rows = session.scalars(
        select(TranslationAudit)
        .where(TranslationAudit.entity_type == kind, TranslationAudit.entity_id == entity_id)
        .order_by(TranslationAudit.version.desc())
        .limit(100)
    ).all()
    return {
        "items": [
            {
                "version": r.version,
                "editor": r.editor_name,
                "at": iso(r.created_at),
                "before": r.before,
                "after": r.after,
            }
            for r in rows
        ]
    }


def prune_league_seasons(session, league_id, years):
    """Apply the existing two-season retention only within the collected league."""
    if not years:
        return
    from sqlalchemy import delete

    for model in (Injury, PlayerSeasonStat, Standings, TeamSeason, TeamCoach, Fixture):
        session.execute(
            delete(model).where(model.league_id == league_id, model.season_year.not_in(years))
        )
