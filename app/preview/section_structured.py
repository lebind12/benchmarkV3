"""섹션 결과의 **구조화 투영** (저장 행만 읽는다).

관리자 화면은 본문·근거를 먼저 보여주고, 표·목록은 그 위에 읽기 좋게 더한다. 이 모듈은
그 표 값을 **저장된 payload에서 그대로 꺼내** 만든다. 없는 값을 지어내지 않는다.

경계:

- 외부 호출 0회. 모델·HTTP를 부르지 않는다. 저장된 module result payload만 읽는다.
- 새 사실·선정·예측을 만들지 않는다. 화면이 이미 보여주는 값의 **모양만** 정리한다.
- 화면(D)은 `structured`가 없으면 본문 라벨만 읽는다. 그래서 여기서 만드는 값은
  "추가 정보"이며 본문을 대체하지 않는다.
- 팀별 상한(선수 2명·부상 2명)·매체 3곳은 **표시 상한**이지 자료 삭제 규칙이 아니다.
  넘는 값이 오면 자르지 않고 그대로 낸다(계약 위반을 숨기지 않는다).
- 부상 상태 문자열은 원문 표기를 그대로 쓴다. `unknown`을 확정 부상으로 바꾸지 않는다.
- 배당은 정규시간 1X2 소수점만 옮긴다. 없는 값은 `None`이다.
- **사진·로고 URL은 저장된 외부 ID에서만 만든다.** 공개 CDN 규칙
  (`https://media.api-sports.io/football/{players|teams}/{external_id}.png`)은 제공자
  문서에 적힌 값이며, 확인된 외부 ID가 없으면 URL을 만들지 않고 `null`로 둔다. DB의
  `photo_url`/`logo_url` 열을 읽지 않는다(그 열은 이 경로의 읽기 권한 밖이다).
- 내부 ID(`player_id`/`team_id`)는 **보존**한다. 값을 외부 ID로 바꾸지 않고, 외부 ID를
  별도 nullable 필드(`external_player_id`/`team_external_id`)로 덧붙인다. 두 ID 공간을
  섞으면 같은 숫자가 다른 실체를 가리킨다.

이 모듈의 출력 키 이름은 화면 파서(`sectionStructured.ts`)가 읽는 이름과 맞춘다.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

__all__ = [
    "PLAYER_PHOTO_URL_TEMPLATE",
    "STRUCTURED_VERSION",
    "TEAM_LOGO_URL_TEMPLATE",
    "StructuredIdContext",
    "player_photo_url",
    "structured_from_payload",
    "structured_row_from_section_result",
    "team_logo_url",
]

# 구조 값 버전. 2에서 선수·부상 행에 외부 ID와 사진 URL(nullable)을, 독자 fixture에
# 팀 외부 ID와 배지 URL(nullable)을 덧붙였다(기존 키는 그대로 둔다).
STRUCTURED_VERSION = "mp11-structured-2"

# API-Football 공개 CDN 규칙. 제공자 문서(v3)에 적힌 경로이며, 우리가 만드는 값이 아니라
# **확인된 외부 ID를 넣는** 자리다. 외부 ID가 없으면 빈 문자열이 아니라 `None`이다.
PLAYER_PHOTO_URL_TEMPLATE = "https://media.api-sports.io/football/players/{external_id}.png"
TEAM_LOGO_URL_TEMPLATE = "https://media.api-sports.io/football/teams/{external_id}.png"


def player_photo_url(external_player_id: Any) -> str | None:
    """확인된 외부 선수 ID로만 사진 주소를 만든다. 아니면 `None`(추정 금지)."""
    return _cdn_url(PLAYER_PHOTO_URL_TEMPLATE, external_player_id)


def team_logo_url(team_external_id: Any) -> str | None:
    """확인된 외부 팀 ID로만 배지 주소를 만든다. 아니면 `None`(추정 금지)."""
    return _cdn_url(TEAM_LOGO_URL_TEMPLATE, team_external_id)


def _cdn_url(template: str, value: Any) -> str | None:
    """양의 정수 외부 ID만 URL로 만든다. 0·음수·불리언·문자열은 거부한다.

    내부 DB 기본키를 여기에 넣으면 다른 선수의 사진이 나온다. 그래서 호출자는 **외부 ID
    임이 확인된 값**만 넘겨야 하고, 이 함수는 그 값의 모양만 확인한다.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return template.format(external_id=int(value))

# 저장 payload가 실제로 쓰는 키. 다른 이름을 추측해 읽지 않는다.
_PLAYER_KEYS = ("selected_player", "display_name", "player", "name")
_PLAYER_REASON_KEYS = ("selection_reason", "reason", "why")
_INJURY_KEYS = ("player_name", "selected_player", "player", "name", "display_name")
_INJURY_STATUS_KEYS = ("expected_status", "status", "api_status")
_INJURY_SUMMARY_KEYS = ("reason", "impact", "summary", "note", "detail")
_MEDIA_KEYS = ("publisher", "media", "outlet", "source_name", "name")
_MEDIA_STATEMENT_KEYS = ("statement", "forecast", "summary", "text", "prediction")
_SCORE_KEYS = ("predicted_score", "score", "predicted", "result")


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _first_text(row: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    for key in keys:
        found = _text(row.get(key))
        if found:
            return found
    return None


def _score_text(row: Mapping[str, Any]) -> str | None:
    """예상 스코어 표기. 홈·원정이 따로 있으면 합쳐 표기한다.

    없는 쪽을 0으로 채우지 않는다. 둘 다 없으면 `None`이다.
    """
    home = row.get("home_goals", row.get("home_score", row.get("home")))
    away = row.get("away_goals", row.get("away_score", row.get("away")))
    if isinstance(home, int) and isinstance(away, int):
        return f"{home}-{away}"
    return _first_text(row, _SCORE_KEYS)


def _decimal_text(value: Any) -> str | None:
    """배당 소수점 표기. 숫자가 아니면 `None`(추정 금지)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value < 1.0 or value > 1000.0:
            return None
        return f"{float(value):.3f}".rstrip("0").rstrip(".")
    if isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
        except ValueError:
            return None
        return _decimal_text(number)
    return None


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [dict(item) for item in value or () if isinstance(item, Mapping)]


class StructuredIdContext:
    """저장 payload의 **내부** ID와 **이름**을 DB에서 확인해 주는 좁은 경계.

    왜 필요한가: 저장 payload의 `player_id`/`team_id`는 우리 DB 기본키이고, 화면의
    사진·배지 주소는 API-Football **외부** ID를 요구한다. 두 공간은 숫자가 다르다
    (예: 내부 13 = 맨체스터 시티, 외부 50). 같은 숫자를 그대로 쓰면 다른 팀 로고가 나온다.

    저장 payload에 ID가 없고 **이름만** 있는 경우(모델이 `player_id: null`로 낸 부상 행)도
    있다. 그때는 같은 경기 두 팀 범위에서 **유일하게 확인된** 이름만 ID로 굳힌다.
    확인되지 않으면 `None`이고 사진 주소를 만들지 않는다.

    경계:

    - 확인은 **이미 열린 이름 해석기**(`DisplayNameBridge.names`, 경기 두 팀 범위)에만
      묻는다. 새 연결·새 쿼리·새 grant를 만들지 않는다.
    - 확인되지 않은 ID·이름은 `None`이다. ID나 이름을 추측해 채우지 않는다.
    - 조회는 한 요청 안에서 반복되므로 결과를 기억한다(같은 선수를 두 번 묻지 않는다).
    """

    def __init__(self, names: Any, *, scope_team_ids: Sequence[int] = ()) -> None:
        self._names = names
        # 이름으로 확인할 때 쓰는 범위. 비어 있으면 범위 없는 조회를 하지 않는다
        # (전체 표에서 동명이인을 붙이는 사고를 막는다).
        self._scope = tuple(int(item) for item in scope_team_ids if item is not None)
        self._players: dict[int, int | None] = {}
        self._teams: dict[int, int | None] = {}
        self._team_names: dict[int, str | None] = {}
        self._by_name: dict[tuple[str, str], dict[str, Any] | None] = {}

    @property
    def active(self) -> bool:
        return self._names is not None

    def player_external_id(self, player_id: int) -> int | None:
        """내부 선수 ID → 외부 선수 ID. 확인되지 않으면 `None`."""
        key = int(player_id)
        if key not in self._players:
            self._players[key] = self._resolve_player(key)
        return self._players[key]

    def team_external_id(self, team_id: int) -> int | None:
        """내부 팀 ID → 외부 팀 ID. 확인되지 않으면 `None`."""
        key = int(team_id)
        if key not in self._teams:
            self._teams[key] = self._resolve_team(key)
        return self._teams[key]

    def team_display_name(self, team_id: int) -> str | None:
        """내부 팀 ID → 확인된 팀 표시 이름(한국어 우선). 없으면 `None`."""
        key = int(team_id)
        if key not in self._team_names:
            self._team_names[key] = self._resolve_team_name(key)
        return self._team_names[key]

    def player_by_name(
        self, name: Any, *, team_hint: Any = None
    ) -> dict[str, Any] | None:
        """이름 하나로 선수를 확인한다. 확인된 값만 돌려주고 아니면 `None`.

        반환 키는 `player_id`(내부) · `external_player_id` · `display_name`(DB 한국어 값,
        없으면 원래 표기)이다. 팀은 `team_id`/`team_external_id`/`team`(한국어 팀명)이며
        확인되지 않으면 `None`이다.

        같은 범위에서 후보가 둘 이상이면(동명이인) `None`이다. 추측해 한 명을 고르지 않는다.
        """
        text = _text(name)
        if text is None or self._names is None or not self._scope:
            return None
        hint = _text(team_hint) or ""
        key = (text.casefold(), hint.casefold())
        if key in self._by_name:
            return self._by_name[key]
        resolve = getattr(self._names, "resolve_player", None)
        entry: dict[str, Any] | None = None
        if callable(resolve):
            try:
                resolution = resolve(
                    text,
                    team_hint=hint or None,
                    scope_team_ids=list(self._scope),
                )
            except Exception:  # noqa: BLE001 - 확인 실패로 표를 없애지 않는다
                resolution = None
            player = getattr(resolution, "player", None)
            player_id = getattr(player, "player_id", None)
            if player is not None and isinstance(player_id, int) and not isinstance(
                player_id, bool
            ):
                external = getattr(player, "external_id", None)
                entry = {
                    "player_id": int(player_id),
                    "external_player_id": (
                        int(external) if isinstance(external, int) else None
                    ),
                    "display_name": _text(getattr(player, "display_name", None)),
                    "team_id": None,
                    "team_external_id": None,
                    "team": None,
                }
                team_name = _text(getattr(player, "team_display_name", None))
                if team_name:
                    resolved_team = self.team_by_name(team_name)
                    if resolved_team is not None:
                        entry["team"] = resolved_team["display_name"]
                        entry["team_id"] = resolved_team["team_id"]
                        entry["team_external_id"] = resolved_team["team_external_id"]
        self._by_name[key] = entry
        return entry

    def team_by_name(self, name: Any) -> dict[str, Any] | None:
        """이름 하나로 팀을 확인한다. 확인되지 않으면 `None`(추측 금지)."""
        text = _text(name)
        if text is None or self._names is None:
            return None
        resolve = getattr(self._names, "resolve_team", None)
        if not callable(resolve):
            return None
        try:
            resolved = resolve(text)
        except Exception:  # noqa: BLE001 - 확인 실패로 표를 없애지 않는다
            return None
        team_id = getattr(resolved, "team_id", None)
        if not isinstance(team_id, int) or isinstance(team_id, bool):
            return None
        external = getattr(resolved, "external_id", None)
        return {
            "team_id": int(team_id),
            "team_external_id": int(external) if isinstance(external, int) else None,
            "display_name": _text(getattr(resolved, "display_name", None)),
        }

    def _resolve_player(self, player_id: int) -> int | None:
        resolve = getattr(self._names, "resolve_player", None)
        if not callable(resolve):
            return None
        try:
            # 이름 없이 ID만 넘긴다(`id_is_hint=False`). 이 ID는 저장 DB에서 온 값이며
            # 확인되지 않으면 다른 선수를 붙이지 않는다.
            resolution = resolve("", player_id=player_id, id_is_hint=False)
        except Exception:  # noqa: BLE001 - 확인 실패로 표를 없애지 않는다
            return None
        player = getattr(resolution, "player", None)
        external = getattr(player, "external_id", None)
        return int(external) if isinstance(external, int) and not isinstance(external, bool) else None

    def _resolve_team(self, team_id: int) -> int | None:
        resolve = getattr(self._names, "resolve_team", None)
        if not callable(resolve):
            return None
        try:
            resolved = resolve(team_id=team_id, id_space="internal")
        except Exception:  # noqa: BLE001 - 확인 실패로 표를 없애지 않는다
            return None
        external = getattr(resolved, "external_id", None)
        return int(external) if isinstance(external, int) and not isinstance(external, bool) else None

    def _resolve_team_name(self, team_id: int) -> str | None:
        resolve = getattr(self._names, "resolve_team", None)
        if not callable(resolve):
            return None
        try:
            resolved = resolve(team_id=team_id, id_space="internal")
        except Exception:  # noqa: BLE001 - 확인 실패로 표를 없애지 않는다
            return None
        return _first_text(
            {
                "display_name": getattr(resolved, "display_name", None),
                "name_ko": getattr(resolved, "name_ko", None),
                "english_name": getattr(resolved, "english_name", None),
            },
            ("display_name", "name_ko", "english_name"),
        )


def _int_id(value: Any) -> int | None:
    """저장된 정수 ID. 불리언·실수·문자열은 받지 않는다(다른 실체로 붙이지 않는다)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return int(value)


def _players(
    payload: Mapping[str, Any],
    *,
    team_label: str | None,
    id_context: "StructuredIdContext | None" = None,
) -> list[dict[str, Any]]:
    players: list[dict[str, Any]] = []
    for row in _rows(payload.get("players")):
        player = _first_text(row, _PLAYER_KEYS)
        reason = _first_text(row, _PLAYER_REASON_KEYS)
        if not player or not reason:
            # 선수명과 이유가 분리돼 있지 않으면 표 행으로 만들지 않는다(합쳐 쓰지 않는다).
            continue
        team = _first_text(row, ("team", "team_name", "team_label")) or team_label
        # 저장 payload는 **내부** player_id를 쓴다. 외부 ID는 확인된 경우에만 덧붙인다.
        player_id = _int_id(row.get("player_id"))
        external_id = None
        if id_context is not None and player_id is not None:
            external_id = id_context.player_external_id(player_id)
        # 팀 ID는 **내부/외부를 섞지 않는다.** 저장 payload의 `team_id`는 우리 DB 기본키이고,
        # 화면의 팀 로고는 API-Football **외부** ID를 요구한다(내부 13 = 외부 50).
        # 확인 순서: ① 저장된 내부 `team_id` ② 저장된 팀 이름 → DB 한국어 값/ID.
        # 어느 쪽도 확인되지 않으면 `None`이며, 배열 순서나 이름 유사도로 추측하지 않는다.
        team_id = _int_id(row.get("team_id"))
        team_name = _first_text(row, ("team", "team_name", "team_label"))
        if id_context is not None:
            if team_id is None and team_name:
                resolved_team = id_context.team_by_name(team_name)
                if resolved_team is not None:
                    team_id = resolved_team["team_id"]
                    if resolved_team["display_name"]:
                        # 저장된 DB 한국어 값이 있으면 그 값을 쓴다(번역이 아니다).
                        team = resolved_team["display_name"]
        players.append(
            {
                "player": player,
                "reason": reason,
                "team": team,
                # 기존 키(내부 ID)는 그대로 둔다.
                "player_id": player_id,
                # 표시용 부가 값. 확인되지 않으면 `null`이다(추정하지 않는다).
                "external_player_id": external_id,
                # 주목 선수 카드의 팀 로고를 **ID로** 확정하기 위한 값(부상 행과 같은 계약).
                "team_id": team_id,
                "team_external_id": (
                    id_context.team_external_id(team_id)
                    if id_context is not None and team_id is not None
                    else None
                ),
                "photo_url": player_photo_url(external_id),
            }
        )
    return players


def _injuries(
    payload: Mapping[str, Any],
    *,
    id_context: "StructuredIdContext | None" = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("absences", "injuries", "injury_rows", "adopted"):
        for row in _rows(payload.get(key)):
            player = _first_text(row, _INJURY_KEYS)
            if not player:
                continue
            player_id = _int_id(row.get("player_id"))
            team_id = _int_id(row.get("team_id"))
            external_id = None
            if id_context is not None and player_id is not None:
                external_id = id_context.player_external_id(player_id)
            # 저장 payload에 ID가 없고 이름만 있을 때(모델이 `player_id: null`로 낸 행)는
            # 같은 경기 두 팀 범위에서 **유일하게 확인된** 이름만 ID로 굳힌다. 이 경로가
            # 없으면 사진·한국어 이름이 비고 본문 표기만 남는다.
            name_team = _first_text(row, ("team", "team_name", "team_label"))
            if id_context is not None and player_id is None:
                resolved = id_context.player_by_name(player, team_hint=name_team)
                if resolved is not None:
                    player_id = resolved["player_id"]
                    external_id = resolved["external_player_id"]
                    team_id = team_id if team_id is not None else resolved["team_id"]
                    if resolved["display_name"]:
                        # DB 한국어 값이 있으면 그 값을 표시 이름으로 쓴다(번역이 아니다).
                        player = resolved["display_name"]
                    if not name_team and resolved["team"]:
                        name_team = resolved["team"]
            elif id_context is not None and player_id is not None:
                # ID가 확인된 경우에도 DB 한국어 표기를 표시 이름으로 쓴다(같은 값이면 그대로).
                resolved_id = id_context.player_by_name(player, team_hint=name_team)
                if resolved_id is not None and resolved_id["player_id"] == player_id:
                    if resolved_id["display_name"]:
                        player = resolved_id["display_name"]
                    if not name_team and resolved_id["team"]:
                        name_team = resolved_id["team"]
            # 팀 표시 이름도 저장된 DB 한국어 값이 있으면 그 값을 쓴다(추측 없음).
            if id_context is not None and name_team:
                resolved_team = id_context.team_by_name(name_team)
                if resolved_team is not None and resolved_team["display_name"]:
                    name_team = resolved_team["display_name"]
            rows.append(
                {
                    "player": player,
                    "team": name_team,
                    # 확정 부상으로 승격하지 않는다. 원문 표기를 그대로 둔다.
                    "status": _first_text(row, _INJURY_STATUS_KEYS),
                    "summary": _first_text(row, _INJURY_SUMMARY_KEYS),
                    # 기존 키(내부 ID) 보존 + 확인된 외부 ID/사진만 덧붙인다.
                    "player_id": player_id,
                    "team_id": team_id,
                    "external_player_id": external_id,
                    "team_external_id": (
                        id_context.team_external_id(team_id)
                        if id_context is not None and team_id is not None
                        else None
                    ),
                    "photo_url": player_photo_url(external_id),
                }
            )
    return rows


def _media(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _rows(payload.get("media")):
        publisher = _first_text(row, _MEDIA_KEYS)
        statement = _first_text(row, _MEDIA_STATEMENT_KEYS)
        if not publisher or not statement:
            continue
        rows.append(
            {
                "publisher": publisher,
                "statement": statement,
                # 점수 미제시 기사는 점수를 만들지 않는다.
                "predictedScore": _score_text(row),
                "publishedAt": _text(row.get("published_at")),
                "url": _text(row.get("url")),
            }
        )
    return rows


def _odds(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _rows(payload.get("odds")):
        market = _text(row.get("market"))
        if market and market != "1x2_regulation":
            # 정규시간 1X2가 아니면 표에 넣지 않는다(진출/라이브/핸디캡 혼합 금지).
            continue
        rows.append(
            {
                "bookmaker": _first_text(row, ("bookmaker", "site", "name")) or "unknown",
                "observedAt": _text(row.get("observed_at")),
                "home": _decimal_text(row.get("home") or row.get("home_decimal")),
                "draw": _decimal_text(row.get("draw") or row.get("draw_decimal")),
                "away": _decimal_text(row.get("away") or row.get("away_decimal")),
                "market": market,
            }
        )
    return rows


def _forecast(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """AI 전망 구조 값. 새 경로의 `structured.forecast`를 **먼저** 읽는다.

    새 경로(`bundle_sections._forecast_section`)는 `{lean, score, reasoning}`을
    `structured.forecast` 아래에 둔다. 옛 S1 저장본은 `ai_prediction`을 쓴다. 둘 다
    같은 모양으로 옮기며, 없는 값은 만들지 않는다.
    """
    prediction = payload.get("forecast")
    if not isinstance(prediction, Mapping):
        prediction = payload.get("ai_prediction")
    if not isinstance(prediction, Mapping):
        prediction = (
            payload if "score" in payload or "lean" in payload or "reasoning" in payload else None
        )
    if not isinstance(prediction, Mapping):
        return None
    lean_raw = _text(prediction.get("lean") or prediction.get("predicted_outcome"))
    lean = lean_raw if lean_raw in ("home", "draw", "away") else None
    reasoning: list[str] = []
    for item in prediction.get("reasoning") or prediction.get("reasons") or ():
        if isinstance(item, str) and item.strip():
            reasoning.append(item.strip())
        elif isinstance(item, Mapping):
            text = _first_text(item, ("text", "reason", "statement"))
            if text:
                reasoning.append(text)
    return {
        "lean": lean,
        "score": _score_text(prediction),
        "reasoning": reasoning,
        "note": _text(prediction.get("note")),
    }


def structured_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    workflow_id: str | None = None,
    team_label: str | None = None,
    id_context: "StructuredIdContext | None" = None,
) -> dict[str, Any]:
    """저장 payload → 화면 구조 값. 없는 항목은 빈 목록이다.

    `payload`는 `ModuleResult.payload`(한 겹 감싼 모양)일 수도 있고 실제 payload일
    수도 있다. 두 모양 모두 읽는다.
    """
    data = dict(payload or {})
    # `ModuleResult.to_dict()`가 payload를 한 겹 감싼다. 옛 기록은 두 겹인 경우도 있어
    # 감싼 값을 **꺼내며** 벗긴다(키를 남기면 같은 값을 계속 벗기게 된다).
    for _ in range(4):  # 중첩은 최대 2겹이며, 무한 반복을 만들지 않는다.
        inner = data.pop("payload", None)
        if not isinstance(inner, Mapping) or not inner:
            break
        data = {**dict(inner), **data}
    # 작성 어댑터는 `structured` 안에 표 값을 모아 둔다. 그 값이 있으면 그것을 먼저 읽고,
    # 없으면 예전처럼 payload 최상위 키를 읽는다(두 모양 모두 지원).
    structured = data.get("structured")
    if isinstance(structured, Mapping) and structured:
        data = {**dict(structured), **data}

    forecast = _forecast(data)
    return {
        "structured_version": STRUCTURED_VERSION,
        "workflow_id": workflow_id,
        "players": _players(data, team_label=team_label, id_context=id_context),
        "injuries": _injuries(data, id_context=id_context),
        "media": _media(data),
        "odds": _odds(data),
        "forecast": forecast,
        # 진단은 여기 넣지 않는다. 화면은 본문·근거를 먼저 보여준다.
    }


def structured_row_from_section_result(
    section_result: Mapping[str, Any],
    *,
    payload: Mapping[str, Any] | None = None,
    id_context: "StructuredIdContext | None" = None,
) -> dict[str, Any]:
    """섹션 결과 행에 붙일 구조 값. payload가 없으면 빈 구조(값을 만들지 않는다)."""
    structured = structured_from_payload(
        payload,
        workflow_id=str(section_result.get("workflow_id") or "") or None,
        id_context=id_context,
    )
    return {
        "section_result_id": section_result.get("section_result_id"),
        "workflow_id": section_result.get("workflow_id"),
        "structured": structured,
        "available": any(
            structured[key]
            for key in ("players", "injuries", "media", "odds", "forecast")
        ),
    }
