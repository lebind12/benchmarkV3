"""API-Football v3 요청 명세와 응답 해석 (MP-03).

이 모듈에는 **전송 계층이 없다.** HTTP 요청·재시도·예산·시도 기록은 MP-04의 공통
실행기(`execute_request`)가 소유한다. 여기서는 두 가지만 한다.

1. D0가 필요로 하는 논리 호출의 `RequestSpec`을 만든다. 호출 하나에 명세 하나이며,
   재시도를 여기서 만들지 않는다(숨은 재시도 금지).
2. 수신 본문을 자료 묶음으로 해석한다. 해석 실패는 "자료 없음"이 아니라 오류다.

해석 규칙(설계 §4·§5, 계획 Review Focus 2):

- 제공자가 `errors`를 돌려주거나 상태가 실패면 `CALL_ERROR`다. `API_NOT_PROVIDED`와
  섞지 않는다. 오류를 "자료 없음"으로 바꾸면 조용히 빈 프리뷰가 만들어진다.
- 부상 응답이 빈 배열이어도 "부상자 0명"이 아니다. 이 모듈은 빈 부상을 확정 사실로
  만들 방법을 제공하지 않는다(`EMPTY_INJURIES_MEANING`).
- 출전 불확실(`doubtful`/`questionable`)은 그대로 불확실로 남긴다. 결장 확정으로
  승격하지 않는다.
- 요청한 경기 ID와 다른 경기가 오면 거부한다(`WrongFixture`).
- 배당은 경기·시장·업체·기준 시각을 함께 남긴다. 경기 전 승무패 시장만 채택 대상이다.
- 시점이 없는 값은 시점이 있는 값으로 승격하지 않는다(`None` 유지).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

from app.preview.contracts import (
    AttemptOutcome,
    ProviderResponse,
    RequestSpec,
)

__all__ = [
    "API_PROVIDER",
    "APIFOOTBALL_SECRET_REF",
    "ApiEnvelope",
    "ApiExchange",
    "ApiExecutor",
    "ApiFootballCall",
    "ApiFootballError",
    "EMPTY_INJURIES_MEANING",
    "FixtureRecord",
    "InjuryRecord",
    "OddsRecord",
    "PlayerStatRecord",
    "PredictionRecord",
    "TeamFormRecord",
    "WrongFixture",
    "d0_calls",
    "injury_uncertainty",
    "parse_envelope",
    "parse_fixture_record",
    "parse_injuries",
    "parse_odds",
    "parse_player_statistics",
    "parse_prediction",
    "parse_team_statistics",
    "request_spec",
]

# 제공자 이름은 실패·시도 기록의 축이다. 모델 제공자와 섞지 않는다.
API_PROVIDER = "api-football"
API_ENDPOINT_BASE = "/v3"

# 비밀값은 이름만 계약에 담는다. 값은 실행 환경에서만 읽는다.
APIFOOTBALL_SECRET_REF = "api_football_key"

REQUEST_TIMEOUT_SECONDS = 30

# D0의 API 요청 예산(계획 §5). 페이지 조회·재시도 포함 상한이다.
D0_API_REQUEST_BUDGET = 24

# 빈 부상 응답의 의미를 한 곳에 못 박아 둔다. 화면·보고서가 같은 문장을 쓴다.
EMPTY_INJURIES_MEANING = (
    "부상 응답이 비어 있습니다. 이는 '부상자 없음'의 증거가 아니며, "
    "자료 없음(미확보)으로 기록합니다."
)

INJURY_UNCERTAIN_MARKERS = ("doubt", "question", "불확실", "출전 불투명")


class ApiFootballError(ValueError):
    """제공자 응답을 해석할 수 없다. '자료 없음'과 구분해야 한다."""


class WrongFixture(ApiFootballError):
    """요청한 경기와 다른 경기가 응답에 들어왔다."""


@dataclass(frozen=True)
class ApiExchange:
    """주입된 실행기가 돌려주는 한 번의 교환 결과.

    `response`는 MP-02 계약(`ProviderResponse`)이며 시도·원문 아티팩트 기록의
    기준이다. `body`는 파싱용 수신 본문이고, 저장은 실행기가 소유한다. 이 모듈은
    `body`를 저장하지 않는다.
    """

    response: ProviderResponse
    body: Mapping[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.response.outcome is AttemptOutcome.OK and isinstance(self.body, Mapping)


# 실행기 계약. MP-04의 `execute_request`가 같은 모양으로 붙는다.
ApiExecutor = Callable[[RequestSpec], ApiExchange]


@dataclass(frozen=True)
class ApiFootballCall:
    """논리 호출 하나. `topic`은 이 호출이 채우는 D0 자료 종류다."""

    call_id: str
    endpoint: str
    topic: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    required: bool = False
    description: str = ""


def request_spec(
    call: ApiFootballCall,
    *,
    module_id: str = "D0",
    contract_version: str | None = None,
) -> RequestSpec:
    """논리 호출 하나의 명세. `secret_refs`에는 이름만 담는다."""
    parameters = dict(call.parameters)
    parameters.setdefault("provider_endpoint", call.endpoint)
    kwargs: dict[str, Any] = {}
    if contract_version is not None:
        kwargs["contract_version"] = contract_version
    return RequestSpec(
        logical_call_id=call.call_id,
        provider=API_PROVIDER,
        model=None,
        operation=call.endpoint,
        module_id=module_id,
        endpoint=f"{API_ENDPOINT_BASE}{call.endpoint}",
        parameters=parameters,
        timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        secret_refs=(APIFOOTBALL_SECRET_REF,),
        **kwargs,
    )


def d0_calls(
    fixture_id: int,
    *,
    league_id: int,
    season: int,
    home_team_id: int,
    away_team_id: int,
    collected_date: str | None = None,
) -> tuple[ApiFootballCall, ...]:
    """D0가 필요한 논리 호출 목록(정상 경로 9회, 재시도 제외).

    순서가 곧 예산 소모 순서다. 경기 확인이 먼저이고, 그 결과가 틀리면 나머지는
    호출하지 않는다.
    """
    return (
        ApiFootballCall(
            call_id="D0-fixture",
            endpoint="/fixtures",
            topic="fixture_identity",
            parameters={"id": fixture_id},
            required=True,
            description="경기 식별·킥오프·상태 확인",
        ),
        ApiFootballCall(
            call_id="D0-form-home",
            endpoint="/teams/statistics",
            topic="recent_form",
            parameters={"league": league_id, "season": season, "team": home_team_id},
            description="홈팀 시즌 기록·최근 흐름",
        ),
        ApiFootballCall(
            call_id="D0-form-away",
            endpoint="/teams/statistics",
            topic="recent_form",
            parameters={"league": league_id, "season": season, "team": away_team_id},
            description="원정팀 시즌 기록·최근 흐름",
        ),
        ApiFootballCall(
            call_id="D0-standings",
            endpoint="/standings",
            topic="standings",
            parameters={"league": league_id, "season": season},
            description="리그 순위·폼",
        ),
        ApiFootballCall(
            call_id="D0-players-home",
            endpoint="/players",
            topic="player_stats",
            parameters={"team": home_team_id, "season": season},
            description="홈팀 선수 시즌 기록",
        ),
        ApiFootballCall(
            call_id="D0-players-away",
            endpoint="/players",
            topic="player_stats",
            parameters={"team": away_team_id, "season": season},
            description="원정팀 선수 시즌 기록",
        ),
        ApiFootballCall(
            call_id="D0-injuries",
            endpoint="/injuries",
            topic="injuries",
            parameters={"fixture": fixture_id},
            description="해당 경기 부상·출전 불확실",
        ),
        ApiFootballCall(
            call_id="D0-odds",
            endpoint="/odds",
            topic="odds",
            parameters={"fixture": fixture_id},
            description="경기 전 승무패 배당",
        ),
        ApiFootballCall(
            call_id="D0-predictions",
            endpoint="/predictions",
            topic="predictions",
            parameters={"fixture": fixture_id},
            description="제공자 알고리즘 예측(매체 의견과 구분)",
        ),
    )


def catalog_call(
    *, league_id: int, date: str, timezone_name: str, season: int
) -> ApiFootballCall:
    """경기 목록 수집 한 번. `operation_kind=fixture_catalog`의 단일 호출이다."""
    return ApiFootballCall(
        call_id="catalog-fixtures",
        endpoint="/fixtures",
        topic="fixture_catalog",
        parameters={
            "league": league_id,
            "season": season,
            "date": date,
            "timezone": timezone_name,
        },
        required=True,
        description="관리자가 지정한 리그·날짜의 경기 후보 목록",
    )


# --------------------------------------------------------------------------
# 응답 봉투
# --------------------------------------------------------------------------


def _error_texts(errors: Any) -> tuple[str, ...]:
    """`errors`는 빈 배열 또는 dict다. 둘 다 오류로 읽는다."""
    if not errors:
        return ()
    if isinstance(errors, Mapping):
        return tuple(f"{key}: {value}" for key, value in errors.items() if value)
    if isinstance(errors, (list, tuple)):
        return tuple(str(item) for item in errors if item)
    return (str(errors),)


@dataclass(frozen=True)
class ApiEnvelope:
    """API-Football 공통 봉투의 해석 결과.

    `errors`가 비어 있지 않으면 성공으로 다루지 않는다. `results == 0`은 호출이
    성공했지만 자료가 없다는 뜻이며, 이는 오류와 다른 상태다.
    """

    records: tuple[Mapping[str, Any], ...]
    errors: tuple[str, ...] = ()
    results: int | None = None
    paging_current: int | None = None
    paging_total: int | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def empty(self) -> bool:
        return self.ok and not self.records

    def require_ok(self) -> "ApiEnvelope":
        if self.errors:
            raise ApiFootballError("provider reported errors: " + "; ".join(self.errors))
        return self


def parse_envelope(body: Any) -> ApiEnvelope:
    """봉투를 해석한다. 본문 모양이 아니면 `ApiFootballError`다.

    `/teams/statistics`는 `response`가 목록이 아니라 객체 하나다. 그래서 객체 하나도
    레코드 1건으로 받는다. 이때 "목록이 아님"을 오류로 만들면 정상 응답을 실패로
    기록하게 된다.
    """
    if not isinstance(body, Mapping):
        raise ApiFootballError("provider body is not a JSON object")
    errors = _error_texts(body.get("errors"))
    raw_records = body.get("response")
    if raw_records is None:
        raw_records = []
    if isinstance(raw_records, Mapping):
        raw_records = [raw_records]
    if not isinstance(raw_records, (list, tuple)):
        raise ApiFootballError("provider 'response' is neither a list nor an object")
    records: list[Mapping[str, Any]] = []
    for item in raw_records:
        if not isinstance(item, Mapping):
            raise ApiFootballError("provider 'response' item is not an object")
        records.append(item)

    paging = body.get("paging")
    current = total = None
    if isinstance(paging, Mapping):
        current = paging.get("current")
        total = paging.get("total")
    results = body.get("results")
    return ApiEnvelope(
        records=tuple(records),
        errors=errors,
        results=int(results) if isinstance(results, (int, float)) else None,
        paging_current=int(current) if isinstance(current, (int, float)) else None,
        paging_total=int(total) if isinstance(total, (int, float)) else None,
    )


# --------------------------------------------------------------------------
# 레코드 해석
# --------------------------------------------------------------------------


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ApiFootballError(f"{label} is missing or not an object")
    return value


def _int(value: Any, label: str, *, required: bool = True) -> int | None:
    if value is None:
        if required:
            raise ApiFootballError(f"{label} is missing")
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ApiFootballError(f"{label} is not an integer") from None


def _dt(value: Any, label: str) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ApiFootballError(f"{label} is not an ISO timestamp") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class FixtureRecord:
    """`/fixtures?id=` 응답 한 건. 외부 ID와 표시용 이름을 함께 둔다."""

    fixture_id: int
    league_id: int
    season: int
    home_team_id: int
    away_team_id: int
    kickoff_at: datetime
    status_short: str | None
    status_long: str | None
    league_name: str | None
    home_team_name: str | None
    away_team_name: str | None
    venue_name: str | None
    referee: str | None
    timezone_name: str | None
    timestamp_unix: int | None

    def identity(self):
        # 순환 import를 피하려고 지역 import를 쓴다.
        from app.preview.contracts import FixtureIdentity

        return FixtureIdentity(
            fixture_id=self.fixture_id,
            league_id=self.league_id,
            season=self.season,
            home_team_id=self.home_team_id,
            away_team_id=self.away_team_id,
            kickoff_at=self.kickoff_at,
        )


def parse_fixture_record(raw: Mapping[str, Any]) -> FixtureRecord:
    fixture = _mapping(raw.get("fixture"), "fixture")
    league = _mapping(raw.get("league"), "league")
    teams = _mapping(raw.get("teams"), "teams")
    home = _mapping(teams.get("home"), "teams.home")
    away = _mapping(teams.get("away"), "teams.away")
    status = fixture.get("status") or {}
    venue = fixture.get("venue") or {}
    kickoff = _dt(fixture.get("date"), "fixture.date")
    if kickoff is None:
        raise ApiFootballError("fixture.date is missing")
    return FixtureRecord(
        fixture_id=_int(fixture.get("id"), "fixture.id"),  # type: ignore[arg-type]
        league_id=_int(league.get("id"), "league.id"),  # type: ignore[arg-type]
        season=_int(league.get("season"), "league.season"),  # type: ignore[arg-type]
        home_team_id=_int(home.get("id"), "teams.home.id"),  # type: ignore[arg-type]
        away_team_id=_int(away.get("id"), "teams.away.id"),  # type: ignore[arg-type]
        kickoff_at=kickoff,
        status_short=_text(status.get("short")) if isinstance(status, Mapping) else None,
        status_long=_text(status.get("long")) if isinstance(status, Mapping) else None,
        league_name=_text(league.get("name")),
        home_team_name=_text(home.get("name")),
        away_team_name=_text(away.get("name")),
        venue_name=_text(venue.get("name")) if isinstance(venue, Mapping) else None,
        referee=_text(fixture.get("referee")),
        timezone_name=_text(fixture.get("timezone")),
        timestamp_unix=_int(fixture.get("timestamp"), "fixture.timestamp", required=False),
    )


def verify_fixture(
    record: FixtureRecord, *, fixture_id: int, home_team_id: int, away_team_id: int
) -> FixtureRecord:
    """다른 경기가 오면 거부한다. 이름이 아니라 ID로 비교한다."""
    if record.fixture_id != fixture_id:
        raise WrongFixture(
            f"requested fixture {fixture_id} but provider returned {record.fixture_id}"
        )
    if record.home_team_id != home_team_id or record.away_team_id != away_team_id:
        raise WrongFixture(
            "requested teams "
            f"{home_team_id}-{away_team_id} but provider returned "
            f"{record.home_team_id}-{record.away_team_id}"
        )
    return record


@dataclass(frozen=True)
class TeamFormRecord:
    team_id: int
    league_id: int | None
    season: int | None
    form: str | None
    played: int | None
    wins: int | None
    draws: int | None
    losses: int | None
    goals_for: int | None
    goals_against: int | None


def parse_team_statistics(raw: Mapping[str, Any]) -> TeamFormRecord:
    team = _mapping(raw.get("team"), "team")
    league = raw.get("league")
    league = league if isinstance(league, Mapping) else {}
    fixtures = raw.get("fixtures")
    fixtures = fixtures if isinstance(fixtures, Mapping) else {}
    goals = raw.get("goals")
    goals = goals if isinstance(goals, Mapping) else {}

    def _total(container: Any, key: str, label: str) -> int | None:
        inner = container.get(key) if isinstance(container, Mapping) else None
        value = inner.get("total") if isinstance(inner, Mapping) else None
        return _int(value, label, required=False)

    goals_for = goals.get("for") if isinstance(goals.get("for"), Mapping) else {}
    goals_against = goals.get("against") if isinstance(goals.get("against"), Mapping) else {}

    def _goals_total(container: Mapping[str, Any], label: str) -> int | None:
        # `goals.for.total`는 {home, away, total} 객체이고, 합계는 그 안의 `total`이다.
        bucket = container.get("total") if isinstance(container, Mapping) else None
        value = bucket.get("total") if isinstance(bucket, Mapping) else bucket
        return _int(value, f"goals.{label}.total", required=False)

    return TeamFormRecord(
        team_id=_int(team.get("id"), "team.id"),  # type: ignore[arg-type]
        league_id=_int(league.get("id"), "league.id", required=False),
        season=_int(league.get("season"), "league.season", required=False),
        form=_text(raw.get("form")),
        played=_total(fixtures, "played", "fixtures.played.total"),
        wins=_total(fixtures, "wins", "fixtures.wins.total"),
        draws=_total(fixtures, "draws", "fixtures.draws.total"),
        losses=_total(fixtures, "loses", "fixtures.loses.total"),
        goals_for=_goals_total(goals_for, "for"),
        goals_against=_goals_total(goals_against, "against"),
    )


def injury_uncertainty(marker: str | None) -> str:
    """부상 표기의 확실성 분류.

    `uncertain`은 **불확실**이며 결장 확정이 아니다. 표기가 없으면 `unknown`이고,
    이 역시 확정으로 승격하지 않는다.
    """
    if not marker:
        return "unknown"
    lowered = marker.lower()
    if any(token in lowered for token in INJURY_UNCERTAIN_MARKERS):
        return "uncertain"
    return "confirmed"


@dataclass(frozen=True)
class InjuryRecord:
    """경기 단위 부상·출전 불확실 한 건.

    `type`·`reason` 원문을 그대로 보존한다. `uncertainty`는 그 원문에서 계산한
    분류이며, 원문을 대체하지 않는다.
    """

    player_id: int
    player_name: str | None
    team_id: int | None
    fixture_id: int | None
    type_marker: str | None
    reason: str | None
    uncertainty: str

    @property
    def is_confirmed_absence(self) -> bool:
        # 원문 표기가 있고 불확실 표기가 없을 때만 결장으로 읽는다.
        return self.uncertainty == "confirmed"


def parse_injuries(
    envelope: ApiEnvelope, *, fixture_id: int | None = None
) -> tuple[InjuryRecord, ...]:
    """부상 레코드만 뽑는다. 빈 결과를 0명으로 바꾸지 않는다(호출자가 `UNKNOWN`)."""
    envelope.require_ok()
    records: list[InjuryRecord] = []
    for raw in envelope.records:
        player = raw.get("player") or {}
        team = raw.get("team") or {}
        fixture = raw.get("fixture") or {}
        player_id = _int(player.get("id"), "player.id") if isinstance(player, Mapping) else None
        if player_id is None:
            raise ApiFootballError("injury record has no player id")
        record_fixture = (
            _int(fixture.get("id"), "fixture.id", required=False)
            if isinstance(fixture, Mapping)
            else None
        )
        if fixture_id is not None and record_fixture is not None and record_fixture != fixture_id:
            # 다른 경기의 부상 자료를 이 경기 근거로 쓰지 않는다.
            raise WrongFixture(
                f"requested injuries for fixture {fixture_id} but got {record_fixture}"
            )
        marker = _text(player.get("type")) if isinstance(player, Mapping) else None
        records.append(
            InjuryRecord(
                player_id=player_id,
                player_name=_text(player.get("name")) if isinstance(player, Mapping) else None,
                team_id=_int(team.get("id"), "team.id", required=False)
                if isinstance(team, Mapping)
                else None,
                fixture_id=record_fixture,
                type_marker=marker,
                reason=_text(player.get("reason")) if isinstance(player, Mapping) else None,
                uncertainty=injury_uncertainty(marker),
            )
        )
    return tuple(records)


# 경기 전 승무패 시장. 다른 시장은 이 단계에서 채택하지 않는다.
PRE_MATCH_MARKET_NAMES = ("match winner", "1x2")
# 라이브·이후 시장은 경기 전 자료가 아니므로 이름으로 먼저 걸러낸다.
LIVE_MARKET_MARKERS = ("live", "in-play", "inplay")

# 배당 신선도 기준(계획 §5 초기 정책).
ODDS_FRESH_HOURS = 6


@dataclass(frozen=True)
class OddsRecord:
    """경기 전 승무패 배당 한 건. 업체·시장·기준 시각을 함께 둔다."""

    bookmaker_id: int | None
    bookmaker: str | None
    market_id: int | None
    market: str | None
    home: str | None
    draw: str | None
    away: str | None
    updated_at: datetime | None

    def age_hours(self, moment: datetime) -> float | None:
        if self.updated_at is None:
            return None
        return (moment - self.updated_at).total_seconds() / 3600


def _is_pre_match_market(market_id: Any, market_name: Any) -> bool:
    """경기 전 승무패 시장인지 판정한다.

    시장 ID 5는 승무패지만 라이브 변형도 같은 ID를 쓴다. 그래서 이름에 라이브 표시가
    있으면 ID가 같아도 경기 전 시장으로 보지 않는다. 이름을 모르면 채택하지 않는다.
    """
    if not isinstance(market_name, str):
        return False
    lowered = market_name.strip().lower()
    if any(marker in lowered for marker in LIVE_MARKET_MARKERS):
        return False
    return any(token in lowered for token in PRE_MATCH_MARKET_NAMES)


def parse_odds(
    envelope: ApiEnvelope, *, fixture_id: int | None = None
) -> tuple[OddsRecord, ...]:
    """경기 전 승무패 배당만 뽑는다. 라이브·다른 시장은 제외한다."""
    envelope.require_ok()
    records: list[OddsRecord] = []
    for raw in envelope.records:
        fixture = raw.get("fixture") or {}
        record_fixture = (
            _int(fixture.get("id"), "fixture.id", required=False)
            if isinstance(fixture, Mapping)
            else None
        )
        if fixture_id is not None and record_fixture is not None and record_fixture != fixture_id:
            raise WrongFixture(
                f"requested odds for fixture {fixture_id} but got {record_fixture}"
            )
        record_update = _dt(raw.get("update"), "odds.update") if raw.get("update") else None
        bookmakers = raw.get("bookmakers") or []
        if not isinstance(bookmakers, (list, tuple)):
            raise ApiFootballError("odds bookmakers is not a list")
        for book in bookmakers:
            if not isinstance(book, Mapping):
                raise ApiFootballError("odds bookmaker is not an object")
            book_update = _dt(book.get("update"), "bookmaker.update") if book.get("update") else None
            updated_at = book_update or record_update
            bets = book.get("bets") or []
            if not isinstance(bets, (list, tuple)):
                raise ApiFootballError("bookmaker bets is not a list")
            for bet in bets:
                if not isinstance(bet, Mapping):
                    raise ApiFootballError("bet is not an object")
                if not _is_pre_match_market(bet.get("id"), bet.get("name")):
                    continue
                values = bet.get("values") or []
                if not isinstance(values, (list, tuple)):
                    raise ApiFootballError("bet values is not a list")
                odds_by_label: dict[str, str] = {}
                for value in values:
                    if not isinstance(value, Mapping):
                        raise ApiFootballError("bet value is not an object")
                    label = _text(value.get("value"))
                    odd = value.get("odd")
                    if label is None:
                        continue
                    odds_by_label[label.lower()] = None if odd is None else str(odd)
                records.append(
                    OddsRecord(
                        bookmaker_id=_int(book.get("id"), "bookmaker.id", required=False),
                        bookmaker=_text(book.get("name")),
                        market_id=_int(bet.get("id"), "bet.id", required=False),
                        market=_text(bet.get("name")),
                        home=odds_by_label.get("home"),
                        draw=odds_by_label.get("draw"),
                        away=odds_by_label.get("away"),
                        updated_at=updated_at,
                    )
                )
    return tuple(records)


@dataclass(frozen=True)
class PredictionRecord:
    """제공자 알고리즘 예측. 매체 의견이나 이 서비스의 AI 결론과 같지 않다."""

    winner_name: str | None
    winner_comment: str | None
    percent_home: str | None
    percent_draw: str | None
    percent_away: str | None
    advice: str | None
    under_over: str | None
    updated_at: datetime | None


def parse_prediction(
    envelope: ApiEnvelope, *, fixture_id: int | None = None
) -> PredictionRecord | None:
    envelope.require_ok()
    if not envelope.records:
        return None
    raw = envelope.records[0]
    fixture = raw.get("fixture") or {}
    record_fixture = (
        _int(fixture.get("id"), "fixture.id", required=False)
        if isinstance(fixture, Mapping)
        else None
    )
    if fixture_id is not None and record_fixture is not None and record_fixture != fixture_id:
        raise WrongFixture(
            f"requested predictions for fixture {fixture_id} but got {record_fixture}"
        )
    predictions = raw.get("predictions") or {}
    percent = (predictions.get("percent") if isinstance(predictions, Mapping) else None) or {}
    winner = predictions.get("winner") if isinstance(predictions, Mapping) else None
    return PredictionRecord(
        winner_name=_text(winner.get("name")) if isinstance(winner, Mapping) else None,
        winner_comment=_text(winner.get("comment")) if isinstance(winner, Mapping) else None,
        percent_home=_text(percent.get("home")) if isinstance(percent, Mapping) else None,
        percent_draw=_text(percent.get("draw")) if isinstance(percent, Mapping) else None,
        percent_away=_text(percent.get("away")) if isinstance(percent, Mapping) else None,
        advice=_text(predictions.get("advice")) if isinstance(predictions, Mapping) else None,
        under_over=_text(predictions.get("under_over"))
        if isinstance(predictions, Mapping)
        else None,
        updated_at=None,
    )


@dataclass(frozen=True)
class PlayerStatRecord:
    player_id: int
    player_name: str | None
    team_id: int | None
    position: str | None
    appearances: int | None
    minutes: int | None
    goals: int | None
    assists: int | None
    rating: str | None


def parse_player_statistics(envelope: ApiEnvelope) -> tuple[PlayerStatRecord, ...]:
    """선수 시즌 기록. 제공되지 않은 값은 `None`으로 둔다."""
    envelope.require_ok()
    records: list[PlayerStatRecord] = []
    for raw in envelope.records:
        player = raw.get("player") or {}
        statistics = raw.get("statistics") or []
        if not isinstance(statistics, (list, tuple)) or not statistics:
            raise ApiFootballError("player statistics entries are missing")
        first = statistics[0]
        if not isinstance(first, Mapping):
            raise ApiFootballError("player statistics entry is not an object")
        team = first.get("team") or {}
        games = first.get("games") or {}
        goals = first.get("goals") or {}
        player_id = _int(player.get("id"), "player.id") if isinstance(player, Mapping) else None
        if player_id is None:
            raise ApiFootballError("player record has no id")
        records.append(
            PlayerStatRecord(
                player_id=player_id,
                player_name=_text(player.get("name")) if isinstance(player, Mapping) else None,
                team_id=_int(team.get("id"), "statistics.team.id", required=False)
                if isinstance(team, Mapping)
                else None,
                position=_text(games.get("position")) if isinstance(games, Mapping) else None,
                appearances=_int(games.get("appearences"), "games.appearences", required=False)
                if isinstance(games, Mapping)
                else None,
                minutes=_int(games.get("minutes"), "games.minutes", required=False)
                if isinstance(games, Mapping)
                else None,
                goals=_int(goals.get("total"), "goals.total", required=False)
                if isinstance(goals, Mapping)
                else None,
                assists=_int(goals.get("assists"), "goals.assists", required=False)
                if isinstance(goals, Mapping)
                else None,
                rating=_text(games.get("rating")) if isinstance(games, Mapping) else None,
            )
        )
    return tuple(records)


def odds_freshness(
    record: OddsRecord, collected_at: datetime
) -> tuple[bool, str | None]:
    """계획 §5 배당 채택 조건. 시점 미확인·오래된 배당은 채택하지 않는다."""
    age = record.age_hours(collected_at)
    if age is None:
        return False, "제공자 갱신 시각이 없어 최신 배당으로 채택하지 않았습니다."
    if age > ODDS_FRESH_HOURS:
        return (
            False,
            f"수집 시점 기준 {age:.1f}시간 지난 배당이라 채택하지 않았습니다"
            f"(기준 {ODDS_FRESH_HOURS}시간).",
        )
    return True, None


def kickoff_is_past(kickoff_at: datetime, moment: datetime) -> bool:
    """킥오프 이후 자료는 경기 전 자료가 아니다."""
    return kickoff_at.astimezone(timezone.utc) <= moment.astimezone(timezone.utc)
