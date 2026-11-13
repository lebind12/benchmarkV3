"""선수 시즌 통계 읽기 (PS-02, 읽기 전용).

`public.player_season_stat`의 **필요한 열만** 읽는 좁은 경계다.

읽는 열(승인된 11개가 전부다):

`player_id`, `team_id`, `league_id`, `season_year`, `position`, `appearances`,
`minutes`, `rating`, `goals`, `assists`, `updated_at`

읽지 않는 열: `yellow_cards`, `red_cards`, `raw_stats`(jsonb 원본), `shirt_number`, `id`.
카드 수는 이번 읽기 범위에 넣지 않는다(승인 범위가 11열). 표 전체 권한도 받지 않는다.

경계:

- `SELECT`만 실행하고 연결은 `default_transaction_read_only=on`이다.
- 필터 없는 조회는 **거부한다**. 팀·리그·시즌 중 최소 하나가 없으면 전 표를 훑지 않는다.
- 설정이 없거나 권한이 없으면 붙지 않는다. 그때 상태는 `unknown`/`denied`이며 0으로
  채우지 않는다. **저장 행이 없다는 것은 "기록 0"의 증거가 아니다.**
- 한국어 이름은 이름 전용 역할(`preview_dev_names_ro`)의 값이 있을 때만 붙는다.
  이 모듈은 이름 표를 직접 읽지 않는다(이미 해석된 값을 받기만 한다).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

__all__ = [
    "PLAYER_STATS_COLUMNS",
    "PLAYER_STATS_TABLE",
    "PlayerSeasonStat",
    "PlayerStatsAccess",
    "PlayerStatsReader",
    "PlayerStatsResult",
    "open_player_stats_from_settings",
]

PLAYER_STATS_TABLE = "public.player_season_stat"

# 이 역할이 실제로 읽는 열. 이름을 넓히지 않는다.
PLAYER_STATS_COLUMNS: tuple[str, ...] = (
    "player_id",
    "team_id",
    "league_id",
    "season_year",
    "position",
    "appearances",
    "minutes",
    "rating",
    "goals",
    "assists",
    "updated_at",
)

CREDENTIALS_KEY = "PREVIEW_STATS_DATABASE_URL"

STATE_READABLE = "readable"
# 계획 PS-02: 권한·자료가 없으면 `unknown`으로 반환한다. 사유는 `reason`에 따로 남긴다.
STATE_UNKNOWN = "unknown"
STATE_DENIED = "denied"

# 상태별로 화면에 그대로 보여줄 문장. 빈 값을 성공으로 꾸미지 않는다.
_COVERAGE_NOTES = {
    "no_rows_for_team_season": (
        "이 팀·리그·시즌 범위에 저장된 선수 통계 행이 없습니다. "
        "기록이 0이라는 뜻이 아니라 확인되지 않았다는 뜻입니다."
    ),
    "read_denied": (
        "선수 통계 읽기 역할에 이 표의 SELECT 권한이 없습니다. "
        "권한 없는 값을 0으로 채우지 않습니다."
    ),
    "not_configured": (
        "선수 통계 읽기 전용 연결이 설정되지 않아 통계를 확인하지 못했습니다."
    ),
    "read_error": "선수 통계 조회가 실패해 값을 확인하지 못했습니다.",
}


@dataclass(frozen=True)
class PlayerSeasonStat:
    """선수 시즌 통계 한 행. 없는 값은 `None`이며 0으로 채우지 않는다."""

    player_id: int
    team_id: int
    league_id: int
    season_year: int
    position: str | None = None
    appearances: int | None = None
    minutes: int | None = None
    rating: float | None = None
    goals: int | None = None
    assists: int | None = None
    updated_at: datetime | None = None
    display_name_ko: str | None = None

    @property
    def key(self) -> str:
        return f"{self.player_id}:{self.team_id}:{self.league_id}:{self.season_year}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "team_id": self.team_id,
            "league_id": self.league_id,
            "season_year": self.season_year,
            "position": self.position,
            "appearances": self.appearances,
            "minutes": self.minutes,
            "rating": self.rating,
            "goals": self.goals,
            "assists": self.assists,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "display_name_ko": self.display_name_ko,
        }

    def prompt_line(self) -> str:
        """작성 단계에 넣을 한 줄. 없는 값은 생략하고 0으로 쓰지 않는다."""
        parts = [f"player_id={self.player_id}"]
        if self.display_name_ko:
            parts.append(f"이름={self.display_name_ko}")
        if self.position:
            parts.append(f"포지션={self.position}")
        for label, value in (
            ("출전", self.appearances),
            ("분", self.minutes),
            ("골", self.goals),
            ("도움", self.assists),
        ):
            if value is not None:
                parts.append(f"{label}={value}")
        if self.rating is not None:
            parts.append(f"평점={self.rating}")
        return " | ".join(parts)


@dataclass(frozen=True)
class PlayerStatsResult:
    """조회 결과와 상태. 빈 결과를 성공으로 꾸미지 않는다."""

    rows: tuple[PlayerSeasonStat, ...]
    state: str
    reason: str | None = None
    coverage_note: str | None = None
    queried_at: datetime | None = None
    scope: Mapping[str, Any] = field(default_factory=dict)

    @property
    def known(self) -> bool:
        return self.state == STATE_READABLE

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_dict() for row in self.rows],
            "state": self.state,
            "reason": self.reason,
            "coverage_note": self.coverage_note,
            "queried_at": self.queried_at.isoformat() if self.queried_at else None,
            "scope": dict(self.scope),
        }


@dataclass(frozen=True)
class PlayerStatsAccess:
    """읽기 권한 점검 결과. 권한 없음은 정상 상태가 아니지만 숨기지 않는다."""

    readable: bool
    state: str
    columns: tuple[str, ...] = ()
    extra_columns: tuple[str, ...] = ()
    role: str | None = None
    detail: str | None = None
    missing: tuple[str, ...] = ()
    reason: str | None = None
    boundary_note: str = (
        "선수 통계는 프리뷰의 다른 caller와 같은 원래 연결(`DATABASE_URL`)을 쓴다. "
        "새 역할·신규 GRANT로 권한을 만들지 않고, 읽기는 이 조회기의 SELECT로 한정한다."
    )

    @classmethod
    def absent(cls, credential_key: str = CREDENTIALS_KEY) -> "PlayerStatsAccess":
        """설정이 없을 때. 상태는 계획대로 `unknown`이고 사유가 `not_configured`다."""
        return cls(
            readable=False,
            state=STATE_UNKNOWN,
            reason="not_configured",
            missing=(f"SELECT ON {PLAYER_STATS_TABLE}",),
            detail=(
                f"{credential_key} 대신 쓰는 원래 benchmark DATABASE_URL이 설정되지 "
                "않았습니다. 새 읽기 계정을 만들지 않고 원래 연결로만 읽습니다."
            ),
        )

    @classmethod
    def probe(
        cls,
        engine: Engine,
        *,
        columns: Sequence[str] = PLAYER_STATS_COLUMNS,
    ) -> "PlayerStatsAccess":
        """실제 연결로 현재 역할과 열 단위 SELECT 권한을 확인한다(쓰기 없음)."""
        try:
            with engine.connect() as conn:
                role = conn.execute(text("SELECT current_user")).scalar()
                granted = {
                    str(row[0])
                    for row in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.column_privileges"
                            " WHERE grantee = current_user AND privilege_type = 'SELECT'"
                            " AND table_schema = 'public' AND table_name = 'player_season_stat'"
                        )
                    )
                }
        except SQLAlchemyError as exc:
            return cls(
                readable=False,
                state=STATE_DENIED,
                reason="connect_failed",
                detail=f"{type(exc).__name__}: 선수 통계 연결에 실패했습니다.",
                missing=(f"SELECT ON {PLAYER_STATS_TABLE}",),
            )

        required = set(columns)
        missing = tuple(column for column in columns if column not in granted)
        # `columns`는 "이 조회기가 실제로 쓰는 열"만 담는다. 역할이 더 넓게 가진 열은
        # `extra_columns`로 분리해 노출한다(관리자 화면이 권한 초과를 볼 수 있게).
        if missing:
            return cls(
                readable=False,
                state=STATE_DENIED,
                reason="read_denied",
                role=str(role) if role else None,
                columns=tuple(sorted(required & granted)),
                extra_columns=tuple(sorted(granted - required)),
                missing=tuple(f"{PLAYER_STATS_TABLE}.{column}" for column in missing),
                detail="허용되지 않은 열: " + ", ".join(missing),
            )
        return cls(
            readable=True,
            state=STATE_READABLE,
            role=str(role) if role else None,
            columns=tuple(sorted(required)),
            extra_columns=tuple(sorted(granted - required)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "state": self.state,
            "role": self.role,
            "columns": list(self.columns),
            "extra_columns": list(self.extra_columns),
            "reason": self.reason,
            "missing": list(self.missing),
            "required": list(self.missing),
            "detail": self.detail,
            "boundary_note": self.boundary_note,
        }


class PlayerStatsReader:
    """`player_season_stat`의 좁은 읽기 조회기.

    엔진은 읽기 전용 연결(`build_read_only_engine`)이어야 한다. 이 클래스는 `SELECT`
    하나만 실행하고, 필터 없는 조회를 거부한다.
    """

    def __init__(self, engine: Engine, *, columns: Sequence[str] = PLAYER_STATS_COLUMNS) -> None:
        unknown = set(columns) - set(PLAYER_STATS_COLUMNS)
        if unknown:
            raise ValueError(f"unknown player stat column(s): {sorted(unknown)}")
        self._engine = engine
        self._columns = tuple(columns)

    @property
    def columns(self) -> tuple[str, ...]:
        return self._columns

    def probe(self) -> PlayerStatsAccess:
        return PlayerStatsAccess.probe(self._engine, columns=self._columns)

    def _select_sql(self, scope: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
        clauses: list[str] = []
        params: dict[str, Any] = {}
        if scope.get("team_ids"):
            clauses.append("team_id = ANY(:team_ids)")
            params["team_ids"] = list(scope["team_ids"])
        if scope.get("league_id") is not None:
            clauses.append("league_id = :league_id")
            params["league_id"] = int(scope["league_id"])
        if scope.get("season_year") is not None:
            clauses.append("season_year = :season_year")
            params["season_year"] = int(scope["season_year"])
        if scope.get("player_ids"):
            clauses.append("player_id = ANY(:player_ids)")
            params["player_ids"] = list(scope["player_ids"])
        if not clauses:
            raise ValueError(
                "선수 통계 조회에는 팀·리그·시즌·선수 중 최소 하나의 범위가 필요합니다"
                "(필터 없는 전체 조회는 거부합니다)."
            )
        statement = (
            f"SELECT {', '.join(self._columns)} FROM {PLAYER_STATS_TABLE}"
            f" WHERE {' AND '.join(clauses)}"
            " ORDER BY team_id, season_year, player_id"
        )
        return text(statement), params

    def season_stats_with_state(
        self,
        *,
        team_id: int | None = None,
        league_id: int | None = None,
        season_year: int | None = None,
        team_ids: Sequence[int] | None = None,
        player_ids: Sequence[int] | None = None,
        name_lookup: Mapping[int, str] | None = None,
        now: datetime | None = None,
    ) -> PlayerStatsResult:
        """범위 안의 시즌 통계를 읽는다. 결과가 없으면 `unknown`이다."""
        scope = {
            "team_id": team_id,
            "team_ids": list(team_ids or ([] if team_id is None else [team_id])),
            "league_id": league_id,
            "season_year": season_year,
            "player_ids": list(player_ids or ()),
        }
        moment = now or datetime.now(timezone.utc)
        try:
            statement, params = self._select_sql(scope)
        except ValueError:
            raise

        try:
            with self._engine.connect() as conn:
                raw_rows = conn.execute(statement, params).mappings().all()
        except SQLAlchemyError as exc:
            return PlayerStatsResult(
                rows=(),
                state=STATE_DENIED,
                reason="read_denied",
                coverage_note=_COVERAGE_NOTES["read_denied"],
                queried_at=moment,
                scope=scope,
            )
        except Exception:  # noqa: BLE001 - 값 오류 등은 실패로 남긴다
            return PlayerStatsResult(
                rows=(),
                state=STATE_UNKNOWN,
                reason="read_error",
                coverage_note=_COVERAGE_NOTES["read_error"],
                queried_at=moment,
                scope=scope,
            )

        rows = tuple(
            PlayerSeasonStat(
                player_id=int(row["player_id"]),
                team_id=int(row["team_id"]),
                league_id=int(row["league_id"]),
                season_year=int(row["season_year"]),
                position=row.get("position"),
                appearances=row.get("appearances"),
                minutes=row.get("minutes"),
                rating=float(row["rating"]) if row.get("rating") is not None else None,
                goals=row.get("goals"),
                assists=row.get("assists"),
                updated_at=row.get("updated_at"),
                display_name_ko=(name_lookup or {}).get(int(row["player_id"])),
            )
            for row in raw_rows
        )

        if not rows:
            return PlayerStatsResult(
                rows=(),
                state=STATE_UNKNOWN,
                reason="no_rows_for_team_season",
                coverage_note=_COVERAGE_NOTES["no_rows_for_team_season"],
                queried_at=moment,
                scope=scope,
            )
        return PlayerStatsResult(
            rows=rows,
            state=STATE_READABLE,
            queried_at=moment,
            scope=scope,
        )

    def season_stats(
        self,
        *,
        team_id: int | None = None,
        league_id: int | None = None,
        season_year: int | None = None,
    ) -> tuple[PlayerSeasonStat, ...]:
        """편의 호출. 상태가 필요하면 `season_stats_with_state`를 쓴다."""
        return self.season_stats_with_state(
            team_id=team_id, league_id=league_id, season_year=season_year
        ).rows


def _settings_stats_url() -> str | None:
    """원래 benchmark `DATABASE_URL`을 돌려준다(없으면 `None`). 값은 출력하지 않는다.

    선수 통계 전용 DSN을 따로 두지 않는다. 프리뷰의 다른 caller와 **같은 연결**을
    쓴다. 옛 `PREVIEW_STATS_DATABASE_URL` 환경값은 읽지 않으므로 다른 계정으로
    분기하지 않는다.
    """
    try:
        from app.preview.config import get_settings

        settings = get_settings()
        return settings.stats_database_url
    except Exception:  # noqa: BLE001 - 설정 로드 실패는 미설정과 구분해 다루지 않는다
        return None


def open_player_stats_from_settings() -> PlayerStatsReader | None:
    """원래 연결이 설정돼 있으면 통계 조회기를 만든다.

    없으면 `None`이다. 호출자는 `PlayerStatsAccess.absent()`로 사유를 화면에 남긴다.
    """
    url = _settings_stats_url()
    if not url:
        return None
    from app.auth.identity import build_read_only_engine

    return PlayerStatsReader(build_read_only_engine(url))
