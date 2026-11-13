"""API-Football `/odds` 보충 읽기 (경기 한 건, 명시 실행 전용).

무엇을 하는가:

- 공개 표에서 정규시간 1X2 배당을 읽지 못했을 때, **같은 경기 한 건**의 제공자 배당을
  한 번 읽어 서로 다른 북메이커 행으로 채운다(기획: 최대 3행).
- 값은 제공자 원문 그대로다. 없는 값을 추정·합성하지 않는다.

무엇을 하지 않는가:

- **일반 GET(reader·section-results·information-bundle)에서 부르지 않는다.** 이 모듈은
  명시적 생성·배당 섹션 실행에서만 호출된다. 읽기 경로가 외부 호출을 시작하면 저장된
  결과를 다시 여는 것만으로 유료 호출이 발생한다.
- `/predictions`를 쓰지 않는다. 알고리즘 예측은 배당이 아니다.
- 라이브·다른 시장을 1X2로 바꾸지 않는다. 이름에 라이브 표시가 있으면 제외한다.

경계(AGENTS.md 개발·테스트 DB 기준):

- 기존 설정(`app.core.config.Settings.api_football_key`)만 재사용한다. 새 키·새 DSN·
  새 grant를 만들지 않는다.
- 이 한 번의 읽기 외에는 HTTP를 보내지 않는다(재시도 없음: `max_retries=1`).
- 비밀값은 출력·보고서·응답에 넣지 않는다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Sequence

from app.preview import information_bundle as bundle_contract
from app.preview.sources import api_football as api

__all__ = [
    "MAX_ODDS_ROWS",
    "PROVIDER_ODDS_IMPLEMENTATION_VERSION",
    "ProviderOddsResult",
    "ReadOnceGuard",
    "adopted_site_count",
    "has_remaining_slots",
    "read_provider_odds",
    "read_provider_odds_once",
]

# 기획의 배당 표시 상한(서로 다른 북메이커 최대 3행).
MAX_ODDS_ROWS = 3

# 이 읽기의 논리 호출 id. 새 상한·새 장부 표를 만들지 않고 기존 표기에 덧붙인다.
PROVIDER_ODDS_CALL_ID = "D0-odds"

# 배당 공급 경로의 구현 버전. 이 값이 승인 단위(워크플로우 버전 축)에 들어간다.
# 결과 의미가 바뀌는 변경에서만 올린다(문구·주석·표시 순서만 바뀌면 올리지 않는다).
# - 1(2026-11-12): 공개 표 0행일 때만이 아니라 **남는 자리**(채택 업체 3개 미만)가 있을
#   때 제공자 `/odds`를 1회 보충하고, 공개 사이트를 앞에 두고 최대 3개 고유 업체로
#   자른다. 제공자 파서 예외는 배당 결측으로 처리한다(전체 생성 중단 없음).
# - 2(2026-11-12): **채택 정책 변경**(사용자 지시). 오래됐다는 이유로 값을 버리지 않고
#   그 경기·그 업체의 가장 최근 실제 갱신값을 채택한다. 업체별 복수 레코드는 갱신시각
#   기준 최신을 고르고, `observed_at`은 제공자 원시 시각 그대로 둔다(수집 시각으로 바꾸지
#   않음, 날짜 미상은 `None`). 어떤 배당이 실리는지가 달라지므로 새 버전이다.
PROVIDER_ODDS_IMPLEMENTATION_VERSION = "mp11-provider-odds-2"

_ENV_KEYS = ("API_FOOTBALL_KEY", "PREVIEW_API_FOOTBALL_KEY")


def adopted_site_count(market: Any) -> int:
    """공개 표에서 **채택된 서로 다른 업체** 수.

    `market`은 계약 `OddsMarket`(또는 그 dict)이며, 정규시간 1X2 세 값이 모두 있는
    줄만 센다. 같은 업체가 여러 줄이어도 1로 센다(표시 행 기준).
    """
    quotes: Any = None
    if market is None:
        return 0
    if isinstance(market, Mapping):
        quotes = market.get("quotes")
    else:
        quotes = getattr(market, "quotes", None)
    sites: set[str] = set()
    for quote in quotes or ():
        if isinstance(quote, Mapping):
            site = quote.get("site")
            complete = quote.get("complete")
            if complete is None:
                complete = all(
                    quote.get(key) is not None
                    for key in ("home_decimal", "draw_decimal", "away_decimal")
                )
        else:
            site = getattr(quote, "site", None)
            complete = getattr(quote, "complete", True)
        if not complete:
            continue
        text = str(site or "").strip()
        if text:
            sites.add(text.casefold())
    return len(sites)


def has_remaining_slots(market: Any) -> bool:
    """표시 상한(3행)까지 **남는 자리**가 있는지.

    공개 표가 0행일 때만이 아니라, 채택된 서로 다른 업체가 3개 **미만**이면 참이다.
    이 판정 하나로 "0행일 때만 호출"과 "1~2행일 때 보완 안 함"을 함께 고친다.
    """
    return adopted_site_count(market) < MAX_ODDS_ROWS


class ReadOnceGuard:
    """한 실행에서 제공자 배당 읽기를 **최대 1회**로 제한하는 표시.

    병렬 갈래(배당 노드·재생성)가 동시에 도달해도 실제 요청은 하나만 나가야 한다.
    잠금 안에서 "아직 안 읽음"을 확인하고 표시하므로, 두 번째 호출자는 요청 없이
    사유만 받는다(전송 장부를 늘리지 않는다).
    """

    __slots__ = ("_lock", "_done")

    def __init__(self) -> None:
        import threading

        self._lock = threading.Lock()
        self._done = False

    def claim(self) -> bool:
        """이 호출이 유일한 읽기 권한을 얻으면 `True`."""
        with self._lock:
            if self._done:
                return False
            self._done = True
            return True

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done



@dataclass(frozen=True)
class ProviderOddsResult:
    """제공자 배당 읽기 한 번의 결론.

    `quotes`는 **실제로 읽은** 정규시간 1X2 줄만 담는다(최대 `MAX_ODDS_ROWS`).
    읽지 못했으면 비어 있고 `reason`에 사유가 있다. `sent`는 실제로 보낸 요청 수다.
    """

    quotes: tuple[bundle_contract.OddsQuote, ...] = ()
    sent: int = 0
    observed_at: datetime | None = None
    reason: str | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return bool(self.quotes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "sent": self.sent,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "reason": self.reason,
            "diagnostics": list(self.diagnostics),
            "quotes": [quote.to_dict() for quote in self.quotes],
        }


def _api_key() -> str | None:
    """제공자 키. 기존 설정을 먼저 보고, 없으면 같은 이름의 환경 변수를 본다.

    값은 절대 반환 사유·진단에 넣지 않는다(존재 여부만 다룬다).
    """
    try:
        from app.core.config import get_settings

        configured = getattr(get_settings(), "api_football_key", None)
    except Exception:  # noqa: BLE001 - 설정을 못 읽으면 환경 변수만 본다
        configured = None
    if isinstance(configured, str) and configured.strip():
        return configured.strip()
    for key in _ENV_KEYS:
        value = os.environ.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _recency_rank(record: Any) -> int | None:
    """갱신 시각 비교용 순위. 없으면 `None`(날짜 미상)."""
    updated = getattr(record, "updated_at", None)
    if not isinstance(updated, datetime):
        return None
    try:
        return int(updated.timestamp())
    except (OverflowError, OSError, ValueError):
        return None


def _decimal(value: Any) -> float | None:
    """소수 배당. 숫자가 아니거나 1 미만이면 `None`(추정 금지)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 1.0 or number > 1000.0:
        return None
    return number


def _quotes_from_records(
    records: Sequence[api.OddsRecord],
    *,
    fixture_id: int,
    collected_at: datetime,
) -> tuple[list[bundle_contract.OddsQuote], list[str]]:
    """제공자 배당 레코드를 계약 배당 줄로 옮긴다. 채택 불가 사유는 진단으로 남긴다.

    **채택 정책(사용자 확정 2026-11-12):** 오래됐다는 이유로 값을 버리지 않는다.
    그 경기·그 업체의 **가장 최근 실제 갱신값**을 채택한다.

    - 업체별로 레코드가 여러 개면 `updated_at`이 **가장 최근**인 줄을 고른다. 갱신
      시각이 없는 줄은 있는 줄보다 뒤로 본다(날짜 미상은 최신이라고 주장하지 않는다).
    - `observed_at`은 **제공자가 준 원시 갱신 시각 그대로** 둔다. 수집 시각으로 바꾸지
      않는다(오래된 값이 방금 측정된 것처럼 보이면 안 된다). 갱신 시각이 없으면 `None`이며
      기존 nullable 계약과 같다.
    - 같은 업체는 한 행만 남긴다(서로 다른 업체 최대 3행 원칙).
    """
    quotes: list[bundle_contract.OddsQuote] = []
    diagnostics: list[str] = []
    # 업체별 최신 레코드만 남긴다. 순서는 처음 등장한 순서를 유지한다.
    best: dict[str, tuple[Any, int | None]] = {}
    order: list[str] = []
    for record in records:
        home = _decimal(record.home)
        draw = _decimal(record.draw)
        away = _decimal(record.away)
        if home is None or draw is None or away is None:
            diagnostics.append(
                f"{record.bookmaker or '업체 미상'}: 홈/무/원정 값이 모두 있지 않아"
                " 채택하지 않았습니다(추정 금지)."
            )
            continue
        site = str(record.bookmaker or "").strip() or "unknown"
        key = site.casefold()
        if key not in best:
            best[key] = (record, _recency_rank(record))
            order.append(key)
            continue
        _previous, previous_rank = best[key]
        current_rank = _recency_rank(record)
        if current_rank is None:
            # 날짜를 모르는 줄은 이미 고른 줄을 밀어내지 않는다(최신이라고 주장하지 않음).
            continue
        # 이전 줄의 시각을 모르면 시각이 있는 줄을 최신으로 본다(모르는 값보다 낫다).
        if previous_rank is None or current_rank > previous_rank:
            best[key] = (record, current_rank)

    for key in order:
        record, _rank = best[key]
        site = str(record.bookmaker or "").strip() or "unknown"
        observed = record.updated_at
        quotes.append(
            bundle_contract.OddsQuote(
                source_id=f"api-football:odds:{fixture_id}:{record.bookmaker_id or 'x'}",
                site=site,
                market=bundle_contract.ODDS_MARKET_REGULATION_1X2,
                # 원시 갱신 시각 보존. 없으면 `None`(수집 시각으로 대체하지 않는다).
                observed_at=observed,
                home_decimal=_decimal(record.home),
                draw_decimal=_decimal(record.draw),
                away_decimal=_decimal(record.away),
                note=(
                    "API-Football 경기 전 승무패 배당 원문 값입니다."
                    + (
                        ""
                        if observed is not None
                        else " 제공자 갱신 시각은 제공되지 않았습니다."
                    )
                ),
            )
        )
        if len(quotes) >= MAX_ODDS_ROWS:
            break
    return quotes, diagnostics


def read_provider_odds(
    *,
    fixture_id: int,
    collected_at: datetime,
    client: Any = None,
) -> ProviderOddsResult:
    """이 경기 한 건의 제공자 배당을 **한 번** 읽는다.

    `client`는 `daily_sync.api.ApiFootballClient`와 같은 `get(path, **params)` 계약을
    따르는 객체다(검사에서 실제 네트워크 없이 대체한다). 주지 않으면 기존 설정으로
    만든다. 키가 없으면 **요청을 보내지 않고** 사유를 남긴다.
    """
    owned = client is None
    if owned:
        key = _api_key()
        if not key:
            return ProviderOddsResult(
                sent=0,
                reason=(
                    "API-Football 키가 설정되지 않아 배당 보충 읽기를 시작하지 않았습니다."
                    " 공개 표에서 읽은 값도 없어 배당을 표시하지 않습니다."
                ),
            )
        from app.workers.daily_sync.api import ApiFootballClient

        try:
            from app.core.config import get_settings

            settings = get_settings()
            host = getattr(settings, "api_football_host", "v3.football.api-sports.io")
            per_minute = int(
                getattr(settings, "api_football_requests_per_minute", 300) or 300
            )
        except Exception:  # noqa: BLE001 - 설정을 못 읽으면 기본 호스트만 쓴다
            host, per_minute = "v3.football.api-sports.io", 300
        client = ApiFootballClient(
            key,
            host=host,
            requests_per_minute=per_minute,
            # 재시도를 두지 않는다. 이 경로는 **한 번의 제한된 읽기**다.
            max_retries=1,
        )

    sent = 0
    try:
        try:
            payload = client.get("/odds", fixture=fixture_id)
        except Exception as exc:  # noqa: BLE001 - 실패를 사유로 남기고 배당 없이 진행
            return ProviderOddsResult(
                sent=1,
                reason=f"API-Football 배당 조회가 실패했습니다: {type(exc).__name__}",
                diagnostics=(str(exc),),
            )
        sent = 1
        # 제공자 응답 해석 실패는 **기존 명시 예외**로만 다룬다(다른 경기·봉투 모양
        # 오류). 여기서 잡지 않으면 선택(optional) 배당의 파싱 실패가 전체 생성을
        # 터뜨린다. 내부 버그까지 삼키지 않도록 `ApiFootballError` 계열만 잡는다.
        try:
            envelope = api.parse_envelope(payload)
        except api.ApiFootballError as exc:
            return ProviderOddsResult(
                sent=sent,
                reason="제공자 배당 응답을 읽지 못했습니다(봉투 모양 오류).",
                diagnostics=(str(exc),),
            )
        if envelope.errors:
            return ProviderOddsResult(
                sent=sent,
                reason="제공자가 배당 조회에 오류를 반환했습니다.",
                diagnostics=envelope.errors,
            )
        if envelope.empty:
            return ProviderOddsResult(
                sent=sent,
                reason=(
                    "제공자가 이 경기의 배당 자료를 반환하지 않았습니다. 없는 값을"
                    " 만들어 채우지 않습니다."
                ),
            )
        try:
            records = api.parse_odds(envelope, fixture_id=fixture_id)
        except api.WrongFixture as exc:
            return ProviderOddsResult(
                sent=sent,
                reason="제공자가 요청한 경기와 다른 경기의 배당을 반환해 채택하지 않았습니다.",
                diagnostics=(str(exc),),
            )
        except api.ApiFootballError as exc:
            return ProviderOddsResult(
                sent=sent,
                reason="제공자 배당 응답을 이 서비스의 정규시간 1X2로 해석하지 못했습니다.",
                diagnostics=(str(exc),),
            )
        quotes, diagnostics = _quotes_from_records(
            records, fixture_id=fixture_id, collected_at=collected_at
        )
        if not quotes:
            return ProviderOddsResult(
                sent=sent,
                reason=(
                    "제공자 응답에 정규시간 1X2 세 값이 모두 있는 배당 줄이 없습니다."
                    " 오래된 값은 버리지 않고 채택하므로, 이 경우는 값 자체가 없는"
                    " 상태입니다."
                ),
                diagnostics=tuple(diagnostics),
            )
        return ProviderOddsResult(
            quotes=tuple(quotes),
            sent=sent,
            observed_at=quotes[0].observed_at,
            diagnostics=tuple(diagnostics),
        )
    finally:
        if owned:
            close = getattr(client, "close", None)
            if callable(close):
                close()


def read_provider_odds_once(
    *,
    fixture_id: int,
    collected_at: datetime,
    guard: "ReadOnceGuard",
    client: Any = None,
) -> ProviderOddsResult:
    """`ReadOnceGuard`를 통과한 호출만 실제로 읽는다. 두 번째부터는 요청 0회.

    이 함수가 "호출 최대 1회"의 단일 지점이다. 호출자는 조건(남는 자리 유무)만
    판단하고, 실제 중복 방지는 여기서 한다.
    """
    if not guard.claim():
        return ProviderOddsResult(
            sent=0,
            reason=(
                "이 실행에서 제공자 배당 읽기는 이미 한 번 시도했습니다."
                " 같은 실행에서 다시 보내지 않습니다."
            ),
        )
    return read_provider_odds(
        fixture_id=fixture_id, collected_at=collected_at, client=client
    )


def market_with_provider_quote(
    base: bundle_contract.OddsMarket | None,
    result: ProviderOddsResult,
    *,
    collected_at: datetime,
    public_quote_limit: int = 1,
) -> bundle_contract.OddsMarket:
    """공개 표 배당을 **먼저** 두고 남는 자리를 제공자 북메이커로 채운다(최대 3행).

    공개 표 값이 있으면 그것을 1행으로 유지하고, 제공자 줄은 서로 다른 업체만 덧붙인다.
    값이 하나도 없으면 빈 시장과 사유를 남긴다(합성값 금지).
    """
    base_quotes = list((base.quotes if base is not None else ()) or ())
    public = [quote for quote in base_quotes if quote.complete][: max(0, public_quote_limit)]
    seen = {quote.site.casefold() for quote in public}
    combined = list(public)
    for quote in result.quotes:
        if len(combined) >= MAX_ODDS_ROWS:
            break
        key = quote.site.casefold()
        if key in seen:
            continue
        seen.add(key)
        combined.append(quote)
    diagnostics = list((base.diagnostics if base is not None else ()) or ())
    diagnostics.extend(result.diagnostics)
    if result.reason:
        diagnostics.append(result.reason)
    if not combined:
        diagnostics.append(
            "공개 표와 API-Football /odds 어느 쪽에서도 정규시간 1X2 값을 확인하지"
            " 못했습니다. 배당을 표시하지 않습니다."
        )
    return bundle_contract.OddsMarket(
        quotes=tuple(combined),
        collected_at=(
            result.observed_at
            or (base.collected_at if base is not None else None)
            or collected_at
        ),
        diagnostics=tuple(dict.fromkeys(diagnostics)),
        unsupported_sites=tuple(base.unsupported_sites if base is not None else ()),
    )
