"""저장된 경기 자료 읽기 (MP-03, 읽기 전용).

기존 운영 DB의 경기·팀·부상·순위 자료를 **읽기 전용**으로 쓴다. 이 모듈이 하는 일:

1. 저장된 경기 후보를 조회한다(목록·단건). 외부 API를 부르지 않는다.
2. 읽기 권한이 있는지 알려준다. 권한이 없으면 어떤 SELECT가 필요한지 정확히 알린다.
3. 응답 본문이 아니라 DB 행에서 D0 자료 묶음을 만든다.

경계:

- `SELECT`만 실행한다. 연결은 `default_transaction_read_only=on`이며 트랜잭션마다
  statement timeout을 건다.
- 스키마를 항상 명시한다(`public.fixture`). 전역 `search_path`에 의존하지 않는다.
- 실제로 필요한 읽기 경계는 `public.fixture`, `public.team`, `public.league`,
  `public.injury`, `public.standings`의 `SELECT`다. `public.venue`는 이 경계 밖이라
  조회하지 않는다. 장소 이름이 필요하면 별도 승인된 읽기 경계를 먼저 정한다. 기존 역할을 넓히지 않고, 앱이
  `postgres`로 접속하지도 않는다. 권한이 없으면 `FixtureReadAccess.probe()`가
  받은 거부를 그대로 보고한다.
- 저장된 부상 행이 없다는 것은 "부상자 0명"의 증거가 아니다. `coverage`에서
  `unknown`으로 남긴다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.auth.identity import build_read_only_engine
from app.preview.contracts import FixtureCatalogQuery, FixtureIdentity

__all__ = [
    "FIXTURE_READ_TABLES",
    "FixtureReadAccess",
    "FixtureReadDenied",
    "StoredFixture",
    "StoredFixtureReader",
    "StoredInjury",
]

# 이 기능이 실제로 읽어야 하는 기존 표. 이름만 보고 넓히지 않는다.
FIXTURE_READ_TABLES: tuple[str, ...] = (
    "public.fixture",
    "public.team",
    "public.league",
    "public.injury",
    "public.standings",
)

READ_ONLY_STATEMENT_TIMEOUT_MS = 5_000


class FixtureReadDenied(RuntimeError):
    """저장된 경기 자료를 읽을 권한이 없다. 대상과 필요한 권한 이름을 담는다."""

    def __init__(self, missing: Sequence[str], detail: str = "") -> None:
        self.missing = tuple(missing)
        message = (
            "저장된 경기 자료를 읽을 권한이 없습니다. 필요한 경계: "
            + ", ".join(f"SELECT ON {table}" for table in self.missing)
        )
        if detail:
            message = f"{message} ({detail})"
        super().__init__(message)


@dataclass(frozen=True)
class FixtureReadAccess:
    """읽기 권한 점검 결과. 권한 없음은 정상 상태가 아니지만 숨기지도 않는다."""

    readable: bool
    tables: Mapping[str, bool]
    role: str | None = None
    detail: str | None = None

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name, ok in self.tables.items() if not ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "readable": self.readable,
            "role": self.role,
            "tables": dict(self.tables),
            "missing": list(self.missing),
            "required": [f"SELECT ON {name}" for name in self.missing],
            "detail": self.detail,
            "boundary_note": (
                "읽기 역할은 기존 영역에 SELECT만 가진다. 권한을 넓히거나 앱이 "
                "관리자 역할로 접속하지 않는다. 필요한 것은 위 SELECT 목록뿐이다."
            ),
        }

    @classmethod
    def probe(cls, engine: Engine, *, tables: Sequence[str] = FIXTURE_READ_TABLES):
        """실제 연결로 표별 SELECT 권한과 현재 역할을 확인한다."""
        status: dict[str, bool] = {}
        role: str | None = None
        detail: str | None = None
        try:
            with engine.connect() as conn:
                role = conn.execute(text("SELECT current_user")).scalar()
                for table in tables:
                    ok = conn.execute(
                        text("SELECT has_table_privilege(current_user, :qualified, 'SELECT')"),
                        {"qualified": table},
                    ).scalar()
                    status[table] = bool(ok)
        except SQLAlchemyError as exc:
            # 연결 자체가 안 되면 어떤 표도 읽을 수 없다고 보고한다.
            return cls(
                readable=False,
                tables={table: False for table in tables},
                role=role,
                detail=f"{type(exc).__name__}: 저장된 경기 자료 연결에 실패했습니다.",
            )
        missing = [name for name, ok in status.items() if not ok]
        if missing:
            detail = "권한 없는 표: " + ", ".join(missing)
        return cls(
            readable=not missing,
            tables=status,
            role=role,
            detail=detail,
        )


@dataclass(frozen=True)
class StoredFixture:
    """저장된 경기 한 건. 내부 ID와 외부 ID를 구분해 둔다.

    `internal_id`는 DB 기본키, `fixture_id`는 API-Football 외부 경기 ID다. 화면·계약은
    외부 ID를 동일성 키로 쓰고, 내부 ID는 저장된 행을 가리킬 때만 쓴다.
    """

    internal_id: int
    fixture_id: int
    league_id: int
    league_name: str | None
    season: int
    home_team_id: int | None
    home_team_name: str | None
    away_team_id: int | None
    away_team_name: str | None
    kickoff_at: datetime
    status_short: str | None
    referee: str | None
    updated_at: datetime | None

    @property
    def label(self) -> str:
        home = self.home_team_name or f"team {self.home_team_id}"
        away = self.away_team_name or f"team {self.away_team_id}"
        return f"{home} vs {away}"

    def identity(self) -> FixtureIdentity:
        """D0 계약의 경기 식별자. 팀 ID가 비면 만들지 않는다.

        컵 대진처럼 팀이 확정되지 않은 경기는 D0 대상이 아니다. 0으로 채우지 않는다.
        """
        if self.home_team_id is None or self.away_team_id is None:
            raise FixtureReadDenied(
                (), "이 경기는 홈·원정 팀이 확정되지 않아 D0 대상이 아닙니다."
            )
        return FixtureIdentity(
            fixture_id=self.fixture_id,
            league_id=self.league_id,
            season=self.season,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            kickoff_at=self.kickoff_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "internal_id": self.internal_id,
            "fixture_id": self.fixture_id,
            "league_id": self.league_id,
            "league_name": self.league_name,
            "season": self.season,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "label": self.label,
            "kickoff_at": self.kickoff_at.isoformat(),
            "status_short": self.status_short,
            "referee": self.referee,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "id_note": (
                "internal_id는 DB 행, fixture_id는 API-Football 외부 경기 ID입니다. "
                "동일성 판단에는 fixture_id를 씁니다."
            ),
        }


@dataclass(frozen=True)
class StoredInjury:
    """저장된 부상 행. 원문 표기를 그대로 보존한다."""

    player_id: int
    player_name: str | None
    team_id: int | None
    type_marker: str | None
    reason: str | None
    reported_at: datetime | None
    fixture_id: int | None


_FIXTURE_COLUMNS = """
    f.id AS internal_id,
    f.external_id AS fixture_id,
    f.league_id,
    l.name AS league_name,
    f.season_year AS season,
    f.home_team_id,
    ht.name AS home_team_name,
    f.away_team_id,
    at.name AS away_team_name,
    f.kickoff_at,
    f.status_short,
    f.referee,
    f.updated_at
"""

_FIXTURE_FROM = """
    FROM public.fixture f
    LEFT JOIN public.league l ON l.id = f.league_id
    LEFT JOIN public.team ht ON ht.id = f.home_team_id
    LEFT JOIN public.team at ON at.id = f.away_team_id
"""


def _row_to_fixture(row: Mapping[str, Any]) -> StoredFixture:
    return StoredFixture(
        internal_id=int(row["internal_id"]),
        fixture_id=int(row["fixture_id"]),
        league_id=int(row["league_id"]),
        league_name=row["league_name"],
        season=int(row["season"]),
        home_team_id=int(row["home_team_id"]) if row["home_team_id"] is not None else None,
        home_team_name=row["home_team_name"],
        away_team_id=int(row["away_team_id"]) if row["away_team_id"] is not None else None,
        away_team_name=row["away_team_name"],
        kickoff_at=row["kickoff_at"],
        status_short=row["status_short"],
        referee=row["referee"],
        updated_at=row["updated_at"],
    )


class StoredFixtureReader:
    """저장된 경기 자료 조회기. 외부 호출이 없고 쓰기가 없다."""

    def __init__(self, engine: Engine, *, access: FixtureReadAccess | None = None) -> None:
        self._engine = engine
        self._access = access

    @classmethod
    def from_url(cls, url: str) -> "StoredFixtureReader":
        return cls(build_read_only_engine(url))

    def close(self) -> None:
        self._engine.dispose()

    def access(self) -> FixtureReadAccess:
        if self._access is None:
            self._access = FixtureReadAccess.probe(self._engine)
        return self._access

    def _connect(self):
        if not self.access().readable:
            raise FixtureReadDenied(self.access().missing, self.access().detail or "")
        return self._engine.connect()

    def _rows(self, statement: str, parameters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        with self._connect() as conn:
            conn.execute(
                text(f"SET LOCAL statement_timeout = {READ_ONLY_STATEMENT_TIMEOUT_MS}")
            )
            return [dict(row) for row in conn.execute(text(statement), dict(parameters)).mappings()]

    def list_fixtures(
        self,
        *,
        league_id: int | None = None,
        date: str | None = None,
        limit: int = 50,
        upcoming_only: bool = False,
        now: datetime | None = None,
    ) -> list[StoredFixture]:
        """저장된 경기 후보. 저장된 행만 읽으며 외부 수집을 일으키지 않는다."""
        clauses: list[str] = []
        parameters: dict[str, Any] = {"limit": max(1, min(int(limit), 200))}
        if league_id is not None:
            clauses.append("f.league_id = :league_id")
            parameters["league_id"] = league_id
        if date is not None:
            # 저장된 킥오프 시각(UTC)의 날짜로 거른다. 리그 현지 날짜와 다를 수 있으며,
            # 그 차이는 화면에 표시한다.
            clauses.append("(f.kickoff_at AT TIME ZONE 'UTC')::date = :kickoff_date")
            parameters["kickoff_date"] = date
        if upcoming_only:
            parameters["now"] = now or datetime.now(timezone.utc)
            clauses.append("f.kickoff_at >= :now")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        statement = (
            f"SELECT {_FIXTURE_COLUMNS} {_FIXTURE_FROM} {where} "
            "ORDER BY f.kickoff_at ASC, f.id ASC LIMIT :limit"
        )
        return [_row_to_fixture(row) for row in self._rows(statement, parameters)]

    def catalog_query(
        self,
        query: FixtureCatalogQuery,
        *,
        limit: int = 50,
        upcoming_only: bool = False,
        now: datetime | None = None,
    ) -> list[StoredFixture]:
        """`FixtureCatalogQuery`로 저장된 경기 목록을 조회한다."""
        return self.list_fixtures(
            league_id=query.league_id,
            date=query.date,
            limit=limit,
            upcoming_only=upcoming_only,
            now=now,
        )

    def get_fixture(self, *, fixture_id: int | None = None, internal_id: int | None = None):
        """외부 ID 또는 내부 ID 하나로 저장된 경기를 읽는다. 둘 다 주면 거부한다."""
        if (fixture_id is None) == (internal_id is None):
            raise ValueError("pass exactly one of fixture_id or internal_id")
        if fixture_id is not None:
            statement = f"SELECT {_FIXTURE_COLUMNS} {_FIXTURE_FROM} WHERE f.external_id = :key"
            parameters = {"key": fixture_id}
        else:
            statement = f"SELECT {_FIXTURE_COLUMNS} {_FIXTURE_FROM} WHERE f.id = :key"
            parameters = {"key": internal_id}
        rows = self._rows(statement + " LIMIT 1", parameters)
        return _row_to_fixture(rows[0]) if rows else None

    def injuries_for_fixture(self, fixture_id: int) -> list[StoredInjury]:
        """저장된 부상 행. 빈 결과는 '부상자 없음'이 아니다."""
        # `public.player`는 승인된 읽기 경계 밖이다. 선수 이름은 여기서 붙이지 않고
        # ID만 남긴다. 이름이 필요하면 별도 읽기 경계를 먼저 승인받는다.
        statement = """
            SELECT i.player_id, i.team_id,
                   i.type AS type_marker, i.reason, i.reported_at, i.fixture_id
            FROM public.injury i
            WHERE i.fixture_id = :fixture_id
            ORDER BY i.player_id ASC
        """
        rows = self._rows(statement, {"fixture_id": fixture_id})
        return [
            StoredInjury(
                player_id=int(row["player_id"]),
                player_name=None,
                team_id=int(row["team_id"]) if row["team_id"] is not None else None,
                type_marker=row["type_marker"],
                reason=row["reason"],
                reported_at=row["reported_at"],
                fixture_id=(
                    int(row["fixture_id"]) if row["fixture_id"] is not None else None
                ),
            )
            for row in rows
        ]

    def standings_for_league(
        self, *, league_id: int, season: int, limit: int = 60
    ) -> list[Mapping[str, Any]]:
        """저장된 순위 행. 폼 문자열을 포함한다."""
        statement = """
            SELECT s.team_id, s.rank, s.points, s.played,
                   s.win, s.draw, s.loss, s.goals_for, s.goals_against, s.form
            FROM public.standings s
            WHERE s.league_id = :league_id AND s.season_year = :season
            ORDER BY s.rank ASC
            LIMIT :limit
        """
        return self._rows(
            statement,
            {"league_id": league_id, "season": season, "limit": max(1, min(limit, 100))},
        )


def describe_read_boundary(missing: Iterable[str]) -> dict[str, Any]:
    """권한이 없을 때 조정자에게 그대로 넘길 문장. 앱이 우회하지 않는다."""
    names = list(missing)
    return {
        "status": "blocked_on_permission",
        "missing_tables": names,
        "required_grants": [f"GRANT SELECT ON TABLE {name} TO <read_only_role>" for name in names],
        "forbidden": [
            "앱이 postgres 관리자 역할로 접속",
            "기존 역할 권한 확대",
            "공개 스키마 DDL/DML",
        ],
        "note": (
            "저장된 경기 자료 읽기는 읽기 전용 역할의 SELECT만 필요합니다. "
            "권한이 생기기 전에는 모의 실행기와 UI로 검증합니다."
        ),
    }
