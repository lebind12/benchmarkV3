"""팀·선수 **표시 이름**을 기존 DB의 한국어 값으로 맞춘다 (읽기 전용).

배경: 경기 프리뷰 본문은 모델이 만든 영어 이름을 그대로 보여 줬다. 예를 들어 저장된
본문에는 `Manchester City`, `Erling Haaland`가 나가지만, 기존 DB에는 이미 사람이
검수한 한국어 이름(`맨체스터 시티`, `엘링 홀란드`)이 있다. 이 모듈은 **표시 경계에서만**
DB 값을 쓰고, 생성·저장된 원문은 건드리지 않는다.

이 파일의 규칙:

- **번역하지 않는다.** 한국어 값은 DB의 `team_translation.name_ko`,
  `player_translation.name_ko`/`short_name_ko`에 있는 값만 쓴다. 음차·추측·모델 번역을
  만들지 않는다. DB에 한국어 값이 없으면 원래 이름을 그대로 두고 사유를 남긴다.
- **동일성은 ID로 잡는다.** DB 기본키(`team.id`, `player.id`)와 외부 ID
  (`external_id`, API-Football ID)는 서로 다른 공간이다. 호출자는 어느 공간의 ID인지
  `id_space`로 명시한다. 맞지 않으면 다른 팀·선수를 고르지 않고 미해결로 돌려준다.
- **애매하면 고르지 않는다.** 같은 범위에서 후보가 둘 이상이면 무작위 선택 대신
  미해결(`ambiguous`)로 돌려주고 원래 이름을 유지한다.
- **본문 치환은 문자열 통째 치환이 아니다.** 긴 표기를 먼저 맞추고, 낱말 경계를
  요구하며, URL·전자우편 안은 건드리지 않고, 한 번만 훑는다(치환 결과를 다시
  치환하지 않는다). 그래서 `Muniz`가 `Rodrigo Muniz` 안에서 따로 바뀌거나,
  치환된 한국어가 다시 영어 표기와 충돌하지 않는다.
- **NLP 라이브러리를 쓰지 않는다.** 유니코드 정규화·낱말 경계·정렬된 정규식만 쓴다.
- 읽기는 **필요한 엔티티만 묶어서** 한다. 필터 없는 전체 조회를 거부한다.

읽기 권한은 열 단위 `SELECT`만 가진 별도 역할(`preview_dev_names_ro`)이 갖는다.
준비 스크립트는 `scripts/preview_dev_names_ro_provision.py`다.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.auth.identity import build_read_only_engine

__all__ = [
    "CoachNameRow",
    "DbNameLookup",
    "DisplayNames",
    "LocalizedNameIndex",
    "NameReason",
    "NameSource",
    "COACH_NAME_COLUMNS",
    "PLAYER_NAME_COLUMNS",
    "PlayerNameRow",
    "PlayerResolution",
    "ResolvedPlayer",
    "ResolvedTeam",
    "TEAM_NAME_COLUMNS",
    "TeamNameRow",
    "UnmappedName",
    "WatchPlayersResult",
    "load_name_index",
    "normalize_name",
]

READ_ONLY_STATEMENT_TIMEOUT_MS = 5_000

# 이 모듈이 읽는 열. 이름 확인에 필요한 최소 항목만 둔다(통계·계정·연락처 없음).
TEAM_NAME_COLUMNS: tuple[str, ...] = (
    "id",
    "external_id",
    "name",
    "name_ko",
    "short_name_ko",
)
COACH_NAME_COLUMNS: tuple[str, ...] = (
    "id",
    "external_id",
    "name",
    "name_ko",
    "short_name_ko",
)
PLAYER_NAME_COLUMNS: tuple[str, ...] = (
    "id",
    "external_id",
    "name",
    "firstname",
    "lastname",
    "current_team_id",
    "name_ko",
    "short_name_ko",
)

# 이름 하나로 확인할 때 돌려받는 최대 후보 수. 동명이 엔티티가 많으면 고르지 않는다.
MAX_NAME_CANDIDATES = 5

# 한 번에 읽는 상한. 필요한 범위를 넘는 전체 조회를 막는다.
MAX_TEAMS_PER_QUERY = 60
MAX_PLAYERS_PER_QUERY = 800

# 본문 치환에 쓰는 최소 길이. 너무 짧은 표기는 다른 낱말 안에서 잘못 걸린다.
MIN_LATIN_SURFACE_LEN = 3
MIN_KOREAN_SURFACE_LEN = 2

# DB 표기 정리에 쓰는 HTML 엔티티. 실제 `public.player.name`에 `O&apos;Reilly` 형태가
# 저장돼 있어 매칭 전에 같은 문자로 맞춘다. 사전 확장이 아니라 값 비교용 정규화다.
_HTML_ENTITIES = (("&apos;", "'"), ("&#39;", "'"), ("&amp;", "&"), ("&quot;", '"'))

_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'\u3000]+", re.IGNORECASE)
_WS = re.compile(r"\s+")


class NameSource(str, Enum):
    """표시 이름이 어디서 왔는지. 관리자 진단과 보고에서 구분한다."""

    DB_KOREAN = "db_korean"
    DB_SHORT_KOREAN = "db_short_korean"
    ORIGINAL = "original"
    # DB에 그 엔티티나 한국어 값이 없어, **같은 생성 응답에서 모델이 준** 한국어 표기를
    # 쓴 경우다. 고정 사전이나 이 코드가 만든 번역이 아니다. 관리자 진단에서만 구분한다.
    AI_TRANSLATION = "ai_translation"


class NameReason(str, Enum):
    """이름을 DB 한국어 값으로 맞추지 못한 사유."""

    AMBIGUOUS = "ambiguous"
    DB_KOREAN_MISSING = "db_korean_missing"
    NOT_FOUND = "not_found"
    EMPTY = "empty"
    # 호출자가 준 신뢰 ID와 이름 표기가 서로 다른 선수를 가리킨다. 둘 중 하나를 임의로
    # 고르지 않는다(다른 사람 이름을 붙이는 것이 가장 나쁜 결과다).
    CONFLICT = "conflict"


def normalize_name(value: Any) -> str:
    """비교용 정규화. 표시 문구를 만들지 않고 같은 이름인지 판단할 때만 쓴다."""
    raw = str(value or "")
    for entity, replacement in _HTML_ENTITIES:
        raw = raw.replace(entity, replacement)
    decomposed = unicodedata.normalize("NFKD", raw)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.casefold()
    # 이름 머리글자 표기(`E.`)의 마침표를 떼어 `e haaland`로 맞춘다.
    without_dots = lowered.replace(".", " ")
    return _WS.sub(" ", without_dots).strip()


def _tokens(value: Any) -> tuple[str, ...]:
    normalized = normalize_name(value)
    return tuple(part for part in normalized.split(" ") if part)


def _surface_key(value: Any) -> str:
    """표기 키. 정규화 결과에 낱말 경계를 붙여 서로 다른 표기가 섞이지 않게 한다."""
    normalized = normalize_name(value)
    return f" {normalized} " if normalized else ""


def _korean_surface_allowed(surface: str) -> bool:
    """한국어 표기는 2자 이상, 라틴 표기는 3자 이상만 치환 대상으로 쓴다."""
    compact = _WS.sub("", surface)
    if any("\uac00" <= ch <= "\ud7a3" for ch in compact):
        return len(compact) >= MIN_KOREAN_SURFACE_LEN
    return len(compact) >= MIN_LATIN_SURFACE_LEN


@dataclass(frozen=True)
class TeamNameRow:
    """`public.team` + `public.team_translation`의 이름 관련 열만 담는다."""

    team_id: int
    external_id: int | None
    english_name: str
    name_ko: str | None = None
    short_name_ko: str | None = None

    @property
    def korean(self) -> str | None:
        return _first_text(self.name_ko, self.short_name_ko)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "external_id": self.external_id,
            "english_name": self.english_name,
            "name_ko": self.name_ko,
            "short_name_ko": self.short_name_ko,
        }


@dataclass(frozen=True)
class PlayerNameRow:
    """`public.player` + `public.player_translation`의 이름 관련 열만 담는다."""

    player_id: int
    external_id: int | None
    english_name: str
    firstname: str | None = None
    lastname: str | None = None
    current_team_id: int | None = None
    name_ko: str | None = None
    short_name_ko: str | None = None

    @property
    def korean(self) -> str | None:
        return _first_text(self.name_ko, self.short_name_ko)

    @property
    def surname_candidates(self) -> tuple[str, ...]:
        """성 후보. **DB `name` 표기**에서 먼저 뽑는다.

        실제 저장 값은 `name`이 화면 표기이고 `lastname`이 성 전체인 경우가 섞여 있다.
        (`E. Haaland` + lastname `Braut Haaland`, `Rodrigo Muniz` + lastname
        `Muniz Carvalho`.) 그래서 `name`의 첫 낱말(이름)을 뺀 나머지를 성 후보로 쓰고,
        `name`이 한 낱말이면(`Kevin`) `lastname` 낱말을 후보로 쓴다. 3자 미만 낱말은
        너무 흔해(`de`, `E.`) 후보에서 뺀다. 이 값들은 **저장된 표기**이며 새 이름이 아니다.
        """
        name_tokens = _tokens(self.english_name)
        tail = [token for token in name_tokens[1:] if len(token) >= 3]
        if tail:
            return tuple(dict.fromkeys(tail))
        last_tokens = [token for token in _tokens(self.lastname) if len(token) >= 3]
        return tuple(dict.fromkeys(last_tokens))

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "external_id": self.external_id,
            "english_name": self.english_name,
            "firstname": self.firstname,
            "lastname": self.lastname,
            "current_team_id": self.current_team_id,
            "name_ko": self.name_ko,
            "short_name_ko": self.short_name_ko,
        }


def _first_text(*values: Any) -> str | None:
    for value in values:
        cleaned = _WS.sub(" ", str(value or "")).strip()
        if cleaned:
            return cleaned
    return None


@dataclass(frozen=True)
class CoachNameRow:
    """`public.coach` + `public.coach_translation`의 이름 관련 열만 담는다.

    감독은 선수와 다른 표다. 이름·ID·한국어 값만 읽고, 경력·통계·계약 정보는 가져오지
    않는다.
    """

    coach_id: int
    external_id: int | None
    english_name: str
    name_ko: str | None = None
    short_name_ko: str | None = None

    @property
    def korean(self) -> str | None:
        return _first_text(self.name_ko, self.short_name_ko)

    def to_dict(self) -> dict[str, Any]:
        return {
            "coach_id": self.coach_id,
            "external_id": self.external_id,
            "english_name": self.english_name,
            "name_ko": self.name_ko,
            "short_name_ko": self.short_name_ko,
        }


@dataclass(frozen=True)
class UnmappedName:
    """DB 한국어 값으로 맞추지 못한 이름 하나. 원래 표기를 유지한 채 사유를 남긴다."""

    kind: str
    original: str
    reason: NameReason
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "original": self.original,
            "reason": self.reason.value,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ResolvedTeam:
    """표시용 팀. `display_name`만 화면에 내보낸다."""

    team_id: int | None
    external_id: int | None
    english_name: str
    display_name: str
    source: NameSource
    name_ko: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "external_id": self.external_id,
            "english_name": self.english_name,
            "display_name": self.display_name,
            "name_ko": self.name_ko,
            "source": self.source.value,
        }


@dataclass(frozen=True)
class ResolvedPlayer:
    """표시용 선수. 팀 표시 이름도 함께 둔다(본문 `이름(팀)` 표기용)."""

    player_id: int | None
    external_id: int | None
    english_name: str
    display_name: str
    source: NameSource
    name_ko: str | None = None
    team_display_name: str | None = None
    team_name_ko: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "player_id": self.player_id,
            "external_id": self.external_id,
            "english_name": self.english_name,
            "display_name": self.display_name,
            "name_ko": self.name_ko,
            "source": self.source.value,
            "team_display_name": self.team_display_name,
            "team_name_ko": self.team_name_ko,
        }


@dataclass(frozen=True)
class PlayerResolution:
    """선수 한 명 해석 결과. 맞췄으면 `player`, 아니면 `unmapped`에 사유가 있다."""

    original: str
    team_hint: str | None = None
    player: ResolvedPlayer | None = None
    unmapped: UnmappedName | None = None

    @property
    def display_name(self) -> str:
        """화면에 쓸 이름. 해석 실패면 원래 표기를 그대로 돌려준다."""
        if self.player is not None:
            return self.player.display_name
        return self.original


@dataclass(frozen=True)
class WatchPlayersResult:
    """주목 선수 목록 변환 결과. 본문용 행과 관리자용 미해결 목록을 함께 준다."""

    rows: tuple[Mapping[str, Any], ...] = ()
    unmapped: tuple[UnmappedName, ...] = ()


@dataclass
class LocalizedNameIndex:
    """읽어 온 팀·선수 이름 묶음. 조회·매칭·치환 표기를 여기서 만든다."""

    teams: tuple[TeamNameRow, ...] = ()
    players: tuple[PlayerNameRow, ...] = ()
    coaches: tuple[CoachNameRow, ...] = ()
    # 본문에 나온 범위 밖 이름을 DB에서 직접 확인할 때 쓰는 좁은 조회기(선택).
    catalog: Any = None
    _teams_by_id: dict[int, TeamNameRow] = field(default_factory=dict, init=False, repr=False)
    _teams_by_external: dict[int, TeamNameRow] = field(default_factory=dict, init=False, repr=False)
    _players_by_id: dict[int, PlayerNameRow] = field(default_factory=dict, init=False, repr=False)
    _players_by_external: dict[int, PlayerNameRow] = field(default_factory=dict, init=False, repr=False)
    _players_by_team: dict[int | None, tuple[PlayerNameRow, ...]] = field(
        default_factory=dict, init=False, repr=False
    )
    _coaches_by_id: dict[int, CoachNameRow] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        by_team: dict[int | None, list[PlayerNameRow]] = {}
        for row in self.teams:
            self._teams_by_id[row.team_id] = row
            if row.external_id is not None:
                self._teams_by_external.setdefault(int(row.external_id), row)
        for player in self.players:
            self._players_by_id[player.player_id] = player
            if player.external_id is not None:
                self._players_by_external.setdefault(int(player.external_id), player)
            by_team.setdefault(player.current_team_id, []).append(player)
        self._players_by_team = {
            key: tuple(value) for key, value in by_team.items()
        }
        self._coaches_by_id = {row.coach_id: row for row in self.coaches}

    # --- 팀 ---------------------------------------------------------------

    def team(self, *, team_id: int | None = None, external_id: int | None = None) -> TeamNameRow | None:
        if team_id is not None and external_id is not None:
            raise ValueError("pass exactly one of team_id or external_id")
        if team_id is not None:
            return self._teams_by_id.get(int(team_id))
        if external_id is not None:
            return self._teams_by_external.get(int(external_id))
        return None

    def team_by_name(self, value: Any) -> list[TeamNameRow]:
        """표시 이름(영어·한국어·짧은 한국어)으로 팀 후보를 찾는다. 후보를 모두 준다."""
        key = _surface_key(value)
        if not key:
            return []
        found: list[TeamNameRow] = []
        for row in self.teams:
            surfaces = {_surface_key(row.english_name), _surface_key(row.name_ko), _surface_key(row.short_name_ko)}
            if key in surfaces:
                found.append(row)
        return found

    def coach_by_name(self, value: Any) -> list[CoachNameRow]:
        """표시 이름(영어·한국어·짧은 한국어)으로 감독 후보를 찾는다. 후보를 모두 준다."""
        key = _surface_key(value)
        if not key:
            return []
        found: list[CoachNameRow] = []
        for row in self.coaches:
            surfaces = {
                _surface_key(row.english_name),
                _surface_key(row.name_ko),
                _surface_key(row.short_name_ko),
            }
            if key in surfaces:
                found.append(row)
        return found

    def roster(self, team_ids: Iterable[int] | None) -> tuple[PlayerNameRow, ...]:
        if team_ids is None:
            return self.players
        wanted = {int(value) for value in team_ids}
        collected: list[PlayerNameRow] = []
        for team_id in wanted:
            collected.extend(self._players_by_team.get(team_id, ()))
        return tuple(collected)

    # --- 선수 -------------------------------------------------------------

    def player(self, *, player_id: int | None = None, external_id: int | None = None) -> PlayerNameRow | None:
        if player_id is not None and external_id is not None:
            raise ValueError("pass exactly one of player_id or external_id")
        if player_id is not None:
            return self._players_by_id.get(int(player_id))
        if external_id is not None:
            return self._players_by_external.get(int(external_id))
        return None

    def match_player(self, name: Any, *, candidates: Sequence[PlayerNameRow]) -> list[PlayerNameRow]:
        """정해진 후보 안에서 이름이 맞는 선수를 고른다. 가장 센 등급만 남긴다.

        등급(높을수록 강함):

        1. DB `player.name`과 같다(`E. Haaland` = `E. Haaland`).
        2. 이름+성을 붙인 표기와 같다(`Erling Braut Haaland`).
        3. 이름+성 한 낱말과 같다(`Erling Haaland`).
        4. 머리글자+성(`E. Haaland` ↔ `Erling Haaland`).
        5. 성만 같다(`Haaland`).

        가장 센 등급의 후보가 **정확히 하나**일 때만 그 선수를 고른다. 동률이면
        호출자는 미해결(`ambiguous`)로 처리해야 한다.
        """
        tokens = _tokens(name)
        if not tokens:
            return []
        target = " ".join(tokens)
        scored: dict[int, list[PlayerNameRow]] = {}
        for row in candidates:
            rank = _match_rank(tokens=tokens, target=target, row=row)
            if rank is not None:
                scored.setdefault(rank, []).append(row)
        if not scored:
            return []
        best = min(scored)
        return scored[best]


def _match_rank(*, tokens: tuple[str, ...], target: str, row: PlayerNameRow) -> int | None:
    """이름 표기와 저장된 표기의 일치 등급. 낮을수록 강한 일치다.

    0. **저장된 한국어 표기와 같다**(`마크 게히` = `name_ko`/`short_name_ko`).

       모델이 처음부터 한국어 이름을 쓰는 경우가 있다(부상 섹션 본문·구조 값). 그때
       영어 표기 규칙만 보면 `not_found`가 되어 사진·외부 ID가 비었다(실제 사용자 생성
       run에서 관측). 비교는 **DB에 저장된 한국어 값과 정확히 같은 표기**일 때만 한다.
       부분 일치·음차 추정은 하지 않는다(동명이인·오표기를 붙이지 않는다).

    1. DB `name`과 같다.
    2. 이름 + 성 전체와 같다.
    3. 이름 + 성 낱말과 같다.
    4. 머리글자 + 성 낱말(`E. Haaland` ↔ `Erling Haaland`).
    5. 성 낱말만 같다.
    """
    name_tokens = _tokens(row.english_name)
    first_tokens = _tokens(row.firstname)
    last_tokens = _tokens(row.lastname)
    surnames = row.surname_candidates

    if tokens and _has_korean(str(row.name_ko or "") + str(row.short_name_ko or "")):
        # 한국어 표기는 저장된 한국어 값과 **정확히 같을 때만** 인정한다.
        # 주의: `normalize_name`은 NFKD로 한글 음절을 자모로 분해하므로, 정규화된
        # 문자열에 한글 음절 범위 검사를 하면 항상 거짓이 된다. 그래서 한국어 여부는
        # **저장된 원문**으로 보고, 동등성은 정규화 토큰으로 비교한다(음절·자모 표기
        # 차이만 흡수하고 부분 일치·음차 추정은 하지 않는다).
        for korean in (row.name_ko, row.short_name_ko):
            if korean and _tokens(korean) == tokens:
                return 0

    if target and target == " ".join(name_tokens):
        return 1
    if first_tokens and last_tokens and target == " ".join(first_tokens + last_tokens):
        return 2
    if first_tokens and any(target == " ".join((first_tokens[0], surname)) for surname in surnames):
        return 3
    # 머리글자 표기. 어느 쪽이 머리글자여도 같은 규칙으로 본다.
    if len(tokens) == 2 and tokens[1] in surnames:
        if first_tokens and tokens[0][:1] == first_tokens[0][:1]:
            return 4
        if len(name_tokens) >= 2 and tokens[0][:1] == name_tokens[0][:1]:
            return 4
    if len(tokens) == 1 and target in surnames:
        return 5
    return None


@dataclass(frozen=True)
class _Alias:
    """해석 과정에서 확인한 표기(모델이 쓴 영어 이름 등)와 그 표시 값."""

    surface: str
    replacement: str
    entity_key: str


@dataclass(frozen=True)
class _Term:
    """본문 치환 표기 하나와 그 대체 값."""

    surface: str
    replacement: str
    entity_key: str
    korean: bool
    # 띄어쓰기 없는 짧은 한국어 표기(성·약칭). 바로 앞에 다른 한국어 낱말이 붙어
    # 있으면(`알렉스 이워비`) 그 이름의 일부로 보고 바꾸지 않는다.
    bare_korean: bool


class DisplayNames:
    """렌더러가 쓰는 표시 이름 파사드.

    사용 순서:

    1. 팀·선수를 해석한다(`resolve_team`, `resolve_player`, `watch_players`).
    2. 경기 제목을 만든다(`fixture_label`).
    3. 본문 문장을 고친다(`rewrite_body`). 1에서 확인한 표기는 자동으로 등록되므로
       본문에 같은 선수가 다시 나와도 같은 한국어 값으로 바뀐다.

    **치환 범위의 한계(의도된 동작).** 본문 치환은 (a) DB에 저장된 표기
    (`A. Iwobi`, `Rodrigo Muniz`, `Manchester City`)와 (b) 이 실행에서
    `resolve_player`/`watch_players`로 **확인된** 모델 표기만 바꾼다. 본문에만 나오고
    아무 단계에서도 확인하지 않은 이름은 추측으로 바꾸지 않고 원문을 유지한다.
    그래서 렌더러는 화면에 내보낼 선수를 먼저 확인한 뒤 본문을 치환해야 한다.
    """

    def __init__(self, index: LocalizedNameIndex | None = None) -> None:
        self._index = index or LocalizedNameIndex()
        self._aliases: dict[str, _Alias] = {}
        self._unmapped: list[UnmappedName] = []
        self._terms: tuple[_Term, ...] | None = None
        self._pattern: re.Pattern[str] | None = None
        self._term_map: dict[str, _Term] = {}
        self._fold_map: dict[str, _Term] = {}
        # 같은 생성 응답이 준 한국어 표기(DB 값이 없을 때만 반영). 진단 추적용.
        self._model_labels: dict[str, dict[str, Any]] = {}

    def fork(self) -> "DisplayNames":
        """섹션별 격리 실행을 위해 가변 상태를 분리한 복제본을 만든다."""
        clone = DisplayNames(self._index)
        clone._aliases = dict(self._aliases)
        clone._unmapped = list(self._unmapped)
        clone._model_labels = {key: dict(val) for key, val in self._model_labels.items()}
        return clone

    # --- 구성 -------------------------------------------------------------

    @property
    def index(self) -> LocalizedNameIndex:
        return self._index

    @property
    def unmapped(self) -> tuple[UnmappedName, ...]:
        """지금까지 해석하지 못한 이름. 관리자 진단에 그대로 넘긴다."""
        return tuple(self._unmapped)

    def _note_unmapped(self, item: UnmappedName) -> UnmappedName:
        self._unmapped.append(item)
        return item

    # --- 팀 ---------------------------------------------------------------

    def resolve_team(
        self,
        value: Any = None,
        *,
        team_id: int | None = None,
        external_id: int | None = None,
        id_space: str = "internal",
    ) -> ResolvedTeam | None:
        """팀 표시 이름을 해석한다.

        `id_space`는 ID가 어느 공간인지 명시한다. `internal`은 `public.team.id`,
        `external`은 API-Football 팀 ID(`public.team.external_id`)다. 섞어 쓰지 않는다.
        """
        row: TeamNameRow | None = None
        explicit_id = team_id if team_id is not None else external_id
        if explicit_id is not None:
            if id_space == "internal":
                row = self._index.team(team_id=team_id, external_id=external_id)
            elif id_space == "external":
                row = self._index.team(external_id=explicit_id)
            else:
                raise ValueError(f"unknown id_space: {id_space!r}")
            if row is None:
                # ID가 그 공간에 없으면 이름으로 대신 찾지 않는다. 다른 공간의 같은 숫자를
                # 다른 팀으로 읽는 사고를 막기 위해서다.
                original = _first_text(value) or ""
                self._note_unmapped(
                    UnmappedName(
                        "team",
                        original or f"team {explicit_id}",
                        NameReason.NOT_FOUND,
                        (
                            f"{id_space} ID {explicit_id}에 해당하는 저장된 팀이 없어 "
                            "다른 팀 이름을 붙이지 않았습니다."
                        ),
                    )
                )
                if not original:
                    return None
                return ResolvedTeam(
                    team_id=None,
                    external_id=None,
                    english_name=original,
                    display_name=original,
                    source=NameSource.ORIGINAL,
                )
        if row is None:
            original = _first_text(value)
            if not original:
                self._note_unmapped(
                    UnmappedName("team", "", NameReason.EMPTY, "팀 이름과 ID가 모두 비었습니다.")
                )
                return None
            candidates = self._index.team_by_name(original)
            if len(candidates) > 1:
                self._note_unmapped(
                    UnmappedName(
                        "team",
                        original,
                        NameReason.AMBIGUOUS,
                        f"같은 이름의 팀이 {len(candidates)}건이라 하나를 고르지 않았습니다.",
                    )
                )
                return None
            if not candidates:
                self._note_unmapped(
                    UnmappedName("team", original, NameReason.NOT_FOUND, "저장된 팀에서 찾지 못했습니다.")
                )
                return ResolvedTeam(
                    team_id=None,
                    external_id=None,
                    english_name=original,
                    display_name=original,
                    source=NameSource.ORIGINAL,
                )
            row = candidates[0]

        korean = row.korean
        source = NameSource.DB_KOREAN if _first_text(row.name_ko) else NameSource.DB_SHORT_KOREAN
        display = korean or row.english_name
        if not _first_text(row.name_ko):
            # 한국어 값이 아예 없는 경우와 짧은 한국어만 있는 경우를 구분해 남긴다.
            if not korean:
                self._note_unmapped(
                    UnmappedName(
                        "team",
                        row.english_name,
                        NameReason.DB_KOREAN_MISSING,
                        "저장된 팀 번역에 한국어 이름이 없어 원래 이름을 유지합니다.",
                    )
                )
        resolved = ResolvedTeam(
            team_id=row.team_id,
            external_id=row.external_id,
            english_name=row.english_name,
            display_name=display,
            source=source if korean else NameSource.ORIGINAL,
            name_ko=korean,
        )
        self._register_team_surfaces(row, display)
        return resolved

    def fixture_label(
        self,
        *,
        home_team_id: int | None = None,
        away_team_id: int | None = None,
        id_space: str = "internal",
        home_name: str | None = None,
        away_name: str | None = None,
        fallback: str | None = None,
    ) -> str:
        """`홈 vs 원정` 표시 이름. 해석한 값만 쓰고 새 이름을 만들지 않는다."""
        home = self.resolve_team(home_name, team_id=home_team_id, id_space=id_space)
        away = self.resolve_team(away_name, team_id=away_team_id, id_space=id_space)
        home_display = home.display_name if home else (_first_text(home_name) or "홈팀")
        away_display = away.display_name if away else (_first_text(away_name) or "원정팀")
        if home or away:
            return f"{home_display} vs {away_display}"
        stored = _first_text(fallback)
        return stored or f"{home_display} vs {away_display}"

    # --- 선수 -------------------------------------------------------------

    def resolve_player(
        self,
        name: Any,
        *,
        team_hint: Any = None,
        scope_team_ids: Iterable[int] | None = None,
        player_id: int | None = None,
        external_id: int | None = None,
        id_space: str = "internal",
        id_is_hint: bool = False,
    ) -> PlayerResolution:
        """선수 한 명을 해석한다. 애매하거나 없으면 원래 표기를 유지한다.

        `id_is_hint=True`는 넘어온 ID가 **검증되지 않은 참조**(모델이 응답에 적은
        `player_ref` 등)임을 뜻한다. 이때 ID가 우리 DB에서 확인되지 않으면 ID를 버리고
        이름 표기로 다시 확인한다. 모델이 숫자를 잘못 적었다고 해서 확실한 한국어 이름을
        포기하지 않기 위해서다. 반대로 기본값(`False`, 신뢰 ID)에서는 ID가 없으면 이름으로
        대신 찾지 않는다(호출자가 지정한 실체와 다른 사람을 붙이지 않는다).
        """
        original = _first_text(name) or ""
        hint = _first_text(team_hint)

        row: PlayerNameRow | None = None
        explicit_id = player_id if player_id is not None else external_id
        id_unmatched = False
        if explicit_id is not None:
            if id_space == "internal":
                row = self._index.player(player_id=player_id, external_id=external_id)
            elif id_space == "external":
                row = self._index.player(external_id=explicit_id)
            else:
                raise ValueError(f"unknown id_space: {id_space!r}")
            if row is None:
                if not id_is_hint:
                    # 신뢰 ID가 그 공간에 없으면 이름으로 대신 찾지 않는다(다른 공간의 같은
                    # 숫자 또는 동명이인을 다른 선수로 읽는 사고 방지).
                    unmapped = self._note_unmapped(
                        UnmappedName(
                            "player",
                            original or f"player {explicit_id}",
                            NameReason.NOT_FOUND,
                            (
                                f"{id_space} ID {explicit_id}에 해당하는 저장된 선수가 없어 "
                                "다른 선수 이름을 붙이지 않았습니다."
                            ),
                        )
                    )
                    return PlayerResolution(
                        original=original, team_hint=hint, unmapped=unmapped
                    )
                # 검증되지 않은 참조(모델이 적은 값)였다. ID를 버리고 이름으로 확인한다.
                id_unmatched = True

        if row is not None and original:
            # ID로 확정했더라도, 이름 표기가 **다른 선수**를 강하게 가리키면 어느 쪽도
            # 임의로 고르지 않는다. ID와 표기가 충돌하는 상태를 조용히 넘기지 않는다.
            others = [
                candidate
                for candidate in self._index.match_player(
                    original, candidates=self._candidate_players(hint=hint, scope_team_ids=scope_team_ids)
                )
                if candidate.player_id != row.player_id
            ]
            if others:
                unmapped = self._note_unmapped(
                    UnmappedName(
                        "player",
                        original,
                        NameReason.CONFLICT,
                        (
                            f"ID로는 저장된 선수 {row.player_id}가 확인되지만 이름 표기 "
                            f"'{original}'는 다른 선수를 가리킵니다. 한쪽을 임의로 고르지 "
                            "않았습니다."
                        ),
                    )
                )
                return PlayerResolution(
                    original=original, team_hint=hint, unmapped=unmapped
                )

        if row is None and original:
            candidates = self._candidate_players(hint=hint, scope_team_ids=scope_team_ids)
            matched = self._index.match_player(original, candidates=candidates)
            if len(matched) > 1:
                unmapped = self._note_unmapped(
                    UnmappedName(
                        "player",
                        original,
                        NameReason.AMBIGUOUS,
                        f"같은 범위에서 후보가 {len(matched)}명이라 한 명을 고르지 않았습니다.",
                    )
                )
                return PlayerResolution(original=original, team_hint=hint, unmapped=unmapped)
            if matched:
                row = matched[0]

        if row is None:
            if not original:
                unmapped = self._note_unmapped(
                    UnmappedName("player", "", NameReason.EMPTY, "선수 이름이 비었습니다.")
                )
            else:
                unmapped = self._note_unmapped(
                    UnmappedName(
                        "player",
                        original,
                        NameReason.NOT_FOUND,
                        "저장된 선수 이름·별칭과 확실히 맞는 항목이 없어 원래 이름을 유지합니다.",
                    )
                )
            return PlayerResolution(original=original, team_hint=hint, unmapped=unmapped)

        korean = row.korean
        unmapped: UnmappedName | None = None
        if not korean:
            unmapped = self._note_unmapped(
                UnmappedName(
                    "player",
                    original,
                    NameReason.DB_KOREAN_MISSING,
                    f"저장된 선수 번역({row.english_name})에 한국어 이름이 없어 원래 이름을 유지합니다.",
                )
            )
        display = korean or original or row.english_name
        team_row = self._index.team(team_id=row.current_team_id) if row.current_team_id else None
        team_display = team_row.korean if team_row else None
        resolved = ResolvedPlayer(
            player_id=row.player_id,
            external_id=row.external_id,
            english_name=row.english_name,
            display_name=display,
            source=NameSource.DB_KOREAN if korean else NameSource.ORIGINAL,
            name_ko=korean,
            team_display_name=team_display,
            team_name_ko=team_display,
        )
        if original:
            # 모델이 쓴 영어 표기(`Erling Haaland`)를 실제 매칭 결과와 연결해 등록한다.
            # 본문의 같은 표기가 다음에 나와도 같은 한국어 값으로 바뀐다.
            self._register_alias(original, resolved.display_name, f"player:{row.player_id}")
        if team_row is not None:
            self._register_team_surfaces(team_row, team_row.korean or team_row.english_name)
        self._invalidate_terms()
        return PlayerResolution(
            original=original, team_hint=hint, player=resolved, unmapped=unmapped
        )

    def _candidate_players(
        self, *, hint: str | None, scope_team_ids: Iterable[int] | None
    ) -> tuple[PlayerNameRow, ...]:
        """선수 후보 범위. 팀 힌트가 있으면 그 팀 로스터로 좁힌다."""
        if hint:
            teams = self._index.team_by_name(hint)
            if len(teams) == 1:
                roster = self._index.roster([teams[0].team_id])
                if roster:
                    return roster
        if scope_team_ids is not None:
            roster = self._index.roster(scope_team_ids)
            if roster:
                return roster
        return self._index.players

    def watch_players(
        self,
        items: Sequence[Mapping[str, Any]],
        *,
        scope_team_ids: Iterable[int] | None = None,
    ) -> WatchPlayersResult:
        """주목 선수 목록의 `player`·`team` 표기를 DB 한국어 값으로 바꾼다.

        원래 키(`reason` 등)는 그대로 두고 이름만 바꾼다. 해석하지 못한 항목은 원래
        이름을 유지하고 `unmapped`에 사유를 남긴다(무작위 선택 없음).
        """
        rows: list[Mapping[str, Any]] = []
        unmapped: list[UnmappedName] = []
        for item in items:
            row = dict(item)
            resolution = self.resolve_player(
                item.get("player"), team_hint=item.get("team"), scope_team_ids=scope_team_ids
            )
            if resolution.player is not None:
                row["player"] = resolution.player.display_name
                if item.get("team"):
                    # 팀 표기도 DB 한국어 값이 있으면 그 값을 쓴다(없으면 원래 값 유지).
                    team = self.resolve_team(item.get("team"))
                    if team is not None:
                        row["team"] = team.display_name
            if resolution.unmapped is not None:
                unmapped.append(resolution.unmapped)
            rows.append(row)
        return WatchPlayersResult(rows=tuple(rows), unmapped=tuple(unmapped))

    # --- 표기 등록 --------------------------------------------------------

    def _register_team_surfaces(self, row: TeamNameRow, display: str) -> None:
        key = f"team:{row.team_id}"
        for surface in (row.english_name, row.name_ko, row.short_name_ko):
            self._register_alias(surface, display, key)

    # --- 모델 제공 번역 표기 -----------------------------------------------

    def register_model_labels(self, labels: Any) -> tuple[dict[str, Any], ...]:
        """같은 생성 응답이 준 한국어 표기를 **DB 값이 없는 경우에만** 등록한다.

        `labels`는 모델이 낸 구조 목록이며 각 항목은
        `{"original": <영어 표기>, "korean": <한국어 표기>, "kind": "team|player|coach",
        "db_id": <선택>}` 모양이다.

        우선순위(사용자 확정): **DB 한국어 값이 있으면 그 값이 이긴다.** 모델이 다른
        표기를 줬더라도 DB 값을 덮어쓰지 않는다. DB에 그 엔티티나 한국어 값이 없을 때만
        모델 표기를 `ai_translation`으로 쓴다.

        번역은 표시에만 쓴다. 신원(ID)·소속·역할을 만들지 않는다. 같은 영어 표기가
        이미 다른 엔티티에 묶여 있으면(충돌) 어느 쪽도 고르지 않는다.

        반환: 반영 결과 목록(관리자 진단용). 각 항목은
        `{"original", "korean", "kind", "applied", "reason", "source"}`.
        """
        results: list[dict[str, Any]] = []
        for entry in _iter_model_labels(labels):
            original = _first_text(entry.get("original"))
            korean = _first_text(entry.get("korean"))
            kind = str(entry.get("kind") or "").strip().lower() or "unknown"
            if not original or not korean:
                results.append(
                    {
                        "original": original or "",
                        "korean": korean or "",
                        "kind": kind,
                        "applied": False,
                        "reason": "empty",
                        "source": NameSource.AI_TRANSLATION.value,
                    }
                )
                continue
            if not _has_korean(korean):
                # 한국어 표기가 아니면 번역으로 쓰지 않는다(영어를 그대로 넣지 않는다).
                results.append(
                    {
                        "original": original,
                        "korean": korean,
                        "kind": kind,
                        "applied": False,
                        "reason": "not_korean",
                        "source": NameSource.AI_TRANSLATION.value,
                    }
                )
                continue

            db_display, db_source, entity_key = self._db_korean_for(
                kind=kind, original=original, entry=entry
            )
            if db_display:
                # DB 값이 이긴다. 그 값을 **본문 치환 표기로 등록**해서, 모델 표기
                # (`RB Leipzig`)가 본문에 있으면 DB 한국어로 바뀌게 한다. 모델이 준
                # 표기는 쓰지 않는다.
                if entity_key:
                    self._register_alias(original, db_display, entity_key)
                results.append(
                    {
                        "original": original,
                        "korean": korean,
                        "kind": kind,
                        "applied": False,
                        "reason": "db_value_wins",
                        "db_display": db_display,
                        "source": db_source,
                    }
                )
                continue

            # DB에 그 엔티티가 있으나 한국어 값이 비어 있으면, 그 **엔티티 키**로 묶는다.
            # 합성 키를 쓰면 같은 표기에 대한 엔티티 항목과 충돌해 둘 다 사라진다.
            key = entity_key or f"{kind}:model:{_surface_key(original)}"
            existing = self._aliases.get(_surface_key(original))
            if existing is not None and existing.entity_key != key:
                # 다른 엔티티가 같은 표기를 이미 쓰고 있다. 덮어쓰지 않는다.
                results.append(
                    {
                        "original": original,
                        "korean": korean,
                        "kind": kind,
                        "applied": False,
                        "reason": "surface_conflict",
                        "source": NameSource.AI_TRANSLATION.value,
                    }
                )
                continue
            self._register_alias(original, korean, key)
            self._model_labels[_surface_key(original)] = {
                "original": original,
                "korean": korean,
                "kind": kind,
            }
            results.append(
                {
                    "original": original,
                    "korean": korean,
                    "kind": kind,
                    "applied": True,
                    "reason": "db_value_missing",
                    "source": NameSource.AI_TRANSLATION.value,
                }
            )
        return tuple(results)

    def _db_korean_for(
        self, *, kind: str, original: str, entry: Mapping[str, Any]
    ) -> tuple[str | None, str | None, str | None]:
        """이 표기에 대응하는 DB 한국어 값과 엔티티 키를 돌려준다.

        반환: (한국어 값 또는 None, 값의 출처 또는 None, 엔티티 키 또는 None).
        엔티티가 DB에 있으면 한국어 값이 비어 있어도 그 키를 돌려준다. 호출자는 모델
        표기를 그 키에 묶어, 같은 엔티티의 기존 항목과 충돌하지 않게 한다.
        

        DB 값이 있으면 모델 번역을 쓰지 않는다. 엔티티를 새로 만들지 않고, 저장된
        이름 표기와 일치할 때만 그 행의 한국어 값을 쓴다.
        """
        if kind == "team":
            team = self._index.team_by_name(original)
            if len(team) == 1:
                row = team[0]
                key = f"team:{row.team_id}"
                if row.korean:
                    return row.korean, self._source_for_team(row), key
                return None, None, key
        if kind == "player":
            candidates = self._index.match_player(original, candidates=self._index.players)
            if len(candidates) == 1:
                row = candidates[0]
                key = f"player:{row.player_id}"
                if row.korean:
                    return row.korean, self._source_for_player(row), key
                return None, None, key
        # 1차: 이 실행이 이미 읽은 범위(그 경기의 두 팀·로스터·감독).
        if kind == "coach":
            coaches = self._index.coach_by_name(original)
            if len(coaches) == 1:
                row = coaches[0]
                key = f"coach:{row.coach_id}"
                if row.korean:
                    return row.korean, NameSource.DB_KOREAN.value, key
                return None, None, key
            coach_label = self._coach_korean(original)
            if coach_label:
                return coach_label, NameSource.DB_KOREAN.value, None

        # 2차: 메모리 범위에 없으면 **DB 카탈로그를 이름으로 직접** 확인한다.
        # 범위 밖 상대 팀·감독(예: 본문에만 나온 클럽)이 여기서 걸린다. 정확 일치만
        # 보고, 후보가 하나일 때만 인정한다(동명이면 고르지 않는다).
        return self._catalog_lookup(kind=kind, original=original)

    def _catalog_lookup(
        self, *, kind: str, original: str
    ) -> tuple[str | None, str | None, str | None]:
        """이름으로 DB 카탈로그를 한 번 조회한다. 없거나 모호하면 (None, None, None)."""
        catalog = self._index.catalog
        if catalog is None or not _catalog_allowed(original):
            return None, None, None
        try:
            if kind == "team":
                rows = catalog.find_teams_by_name(original)
            elif kind == "coach":
                rows = catalog.find_coaches_by_name(original)
            else:
                return None, None, None
        except Exception:  # noqa: BLE001 - 이름 확인 실패로 실행을 깨지 않는다
            return None, None, None
        row = _pick_unique_name_match(original, rows)
        if row is None:
            return None, None, None
        if not row.korean:
            # DB에 엔티티는 있으나 한국어 값이 비어 있다. 그 사실은 관리자에게 남긴다.
            key = (
                f"team:{row.team_id}"
                if kind == "team"
                else f"coach:{getattr(row, 'coach_id', '')}"
            )
            return None, None, key
        source = (
            NameSource.DB_KOREAN.value
            if (getattr(row, "name_ko", None) or "")
            else NameSource.DB_SHORT_KOREAN.value
        )
        key = (
            f"team:{row.team_id}"
            if kind == "team"
            else f"coach:{getattr(row, 'coach_id', '')}"
        )
        return row.korean, source, key

    def _source_for_team(self, row: TeamNameRow) -> str:
        if row.name_ko:
            return NameSource.DB_KOREAN.value
        return NameSource.DB_SHORT_KOREAN.value

    def _source_for_player(self, row: PlayerNameRow) -> str:
        if getattr(row, "name_ko", None):
            return NameSource.DB_KOREAN.value
        return NameSource.DB_SHORT_KOREAN.value

    def _coach_korean(self, original: Any) -> str | None:
        """감독 한국어 이름. 이름 인덱스에 없으면 `None`(이 코드는 번역하지 않는다)."""
        text = _first_text(original)
        if not text:
            return None
        lookup = getattr(self._index, "coach_by_name", None)
        if not callable(lookup):
            return None
        rows = lookup(text)
        if len(rows) != 1:
            return None
        row = rows[0]
        return _first_text(getattr(row, "name_ko", None))

    def model_label_rows(self) -> tuple[dict[str, Any], ...]:
        """반영된 모델 번역 목록(관리자 진단용). 화면 본문에는 쓰지 않는다."""
        return tuple(dict(item) for item in self._model_labels.values())

    def _register_alias(self, surface: Any, replacement: str, entity_key: str) -> None:
        text = _first_text(surface)
        if not text or not _korean_surface_allowed(text):
            return
        key = _surface_key(text)
        if not key:
            return
        current = self._aliases.get(key)
        if current is not None and current.entity_key != entity_key:
            # 서로 다른 엔티티가 같은 표기를 쓰면 어느 쪽도 고르지 않는다.
            return
        self._aliases[key] = _Alias(
            surface=text, replacement=replacement, entity_key=entity_key
        )
        self._invalidate_terms()

    def _invalidate_terms(self) -> None:
        self._terms = None
        self._pattern = None

    def _build_terms(self) -> tuple[_Term, ...]:
        if self._terms is not None:
            return self._terms
        collected: dict[str, _Term] = {}
        conflicts: set[str] = set()

        def add(surface: Any, replacement: str, entity_key: str) -> None:
            text = _first_text(surface)
            if not text or not _korean_surface_allowed(text):
                return
            key = _surface_key(text)
            if not key:
                return
            existing = collected.get(key)
            if existing is not None and existing.entity_key != entity_key:
                conflicts.add(key)
                return
            if existing is not None and existing.replacement == replacement:
                return
            collected[key] = _Term(
                surface=text,
                replacement=replacement,
                entity_key=entity_key,
                korean=_has_korean(text),
                bare_korean=_has_korean(text) and " " not in text.strip(),
            )

        for row in self._index.teams:
            display = row.korean or row.english_name
            key = f"team:{row.team_id}"
            add(row.english_name, display, key)
            add(row.name_ko, display, key)
            add(row.short_name_ko, display, key)

        for player in self._index.players:
            key = f"player:{player.player_id}"
            # 한국어 값이 없는 선수는 영어 표기를 그대로 두는 것이 맞다.
            display = player.korean or player.english_name
            add(player.english_name, display, key)
            add(player.name_ko, display, key)
            # 선수의 **짧은 한국어 표기**(`이워비`, `홀란드`)는 등록하지 않는다. 본문에
            # `알렉스 이워비`처럼 다른 한국어 이름과 붙어 나오면 어디까지가 한 사람
            # 이름인지 확정할 수 없고, 잘못 합치면 없는 이름을 만든다. 짧은 한국어
            # 이름을 정확히 잇는 일은 음차 규칙이 필요하므로 이 모듈 범위가 아니다.
            first_tokens = _tokens(player.firstname)
            last_tokens = _tokens(player.lastname)
            if first_tokens and last_tokens:
                add(" ".join(first_tokens + last_tokens), display, key)
            for surname in player.surname_candidates:
                if first_tokens:
                    add(" ".join((first_tokens[0], surname)), display, key)
            # 성만 쓰는 표기(`Iwobi`)는 **치환 대상으로 등록하지 않는다.**
            # 본문의 `Alex Iwobi`가 `Alex 알렉산더 츄카 이워비`처럼 이름이 깨진다.
            # 성 단독 해석은 `resolve_player`가 범위·유일성 검사를 거쳐 처리하고,
            # 본문 치환은 DB 표기(`A. Iwobi`)와 이름+성 표기만 쓴다.

        for coach in self._index.coaches:
            # 감독 한국어 값이 DB에 있으면 그 값이 이긴다(모델 번역보다 우선).
            if not coach.korean:
                continue
            key = f"coach:{coach.coach_id}"
            add(coach.english_name, coach.korean, key)
            add(coach.name_ko, coach.korean, key)

        for alias in self._aliases.values():
            add(alias.surface, alias.replacement, alias.entity_key)

        for key in conflicts:
            collected.pop(key, None)

        ordered = sorted(collected.values(), key=lambda term: (-len(term.surface), term.surface))
        self._terms = tuple(ordered)
        self._term_map = {term.surface: term for term in ordered}
        self._fold_map = {term.surface.casefold(): term for term in ordered}
        self._pattern = None
        return self._terms

    def confirm_player(self, name: Any, *, team_hint: Any = None, scope_team_ids: Iterable[int] | None = None) -> PlayerResolution:
        """화면에 쓸 선수 이름 하나를 확인하고, 확인된 영어 표기를 치환 표기로 등록한다.

        `rewrite_body`는 **확인된 표기**만 바꾼다. 모델이 쓴 다른 표기(`Alex Iwobi`)
        까지 바꾸려면 그 표기를 먼저 확정해야 하고, 그 역할이 이 메서드다. 확인하지
        않은 표기를 추측으로 바꾸지 않는다.
        """
        return self.resolve_player(name, team_hint=team_hint, scope_team_ids=scope_team_ids)

    def rewrite_body(self, body: Any) -> str:
        """본문 문장의 팀·선수 표기를 DB 한국어 값으로 바꾼다.

        규칙: 긴 표기 우선, 낱말 경계 필요, URL·전자우편 구간 제외, 한 번만 훑기.
        같은 표기가 여러 번 나오면 모두 바꾼다.
        """
        text_value = str(body or "")
        if not text_value:
            return ""
        pattern = self._pattern
        if pattern is None:
            terms = self._build_terms()
            if not terms:
                return text_value
            alternatives = "|".join(re.escape(term.surface) for term in terms)
            # 경계는 **라틴 문자·숫자**만 본다. 한국어 조사가 붙은 표기
            # (`Manchester City와`, `Fulham는`)도 같은 이름으로 인식해야 하기 때문이다.
            pattern = re.compile(
                rf"(?<![0-9A-Za-z_])(?:{alternatives})(?![0-9A-Za-z_])",
                re.IGNORECASE,
            )
            self._pattern = pattern
            self._fold_map = {term.surface.casefold(): term for term in terms}
        return self._rewrite_outside_urls(text_value, pattern)

    def _rewrite_outside_urls(self, value: str, pattern: re.Pattern[str]) -> str:
        pieces: list[str] = []
        cursor = 0
        for match in _URL.finditer(value):
            pieces.append(
                _replace_segment(value[cursor : match.start()], pattern, self._term_map, self._fold_map)
            )
            # URL은 그대로 둔다. 링크 안의 이름을 바꾸면 주소가 깨진다.
            pieces.append(match.group(0))
            cursor = match.end()
        pieces.append(_replace_segment(value[cursor:], pattern, self._term_map, self._fold_map))
        return "".join(pieces)


def _pick_unique_name_match(original: str, rows: Sequence[Any]) -> Any | None:
    """조회 후보 중 이 표기를 확정하는 단 하나를 고른다. 못 고르면 `None`.

    결정적 규칙만 쓴다(선수 이름 해석과 같은 방식).

    1. 표기가 DB `name`과 같다.
    2. 표기가 DB `name`으로 시작한다(긴 이름: `AEK Athens` ↔ `AEK Athens FC`).
       이때 후보가 **하나**일 때만 인정한다.
    3. DB `name`이 머리글자+성(`E. Maresca`)이고 표기가 이름+성(`Enzo Maresca`)이면
       성이 같고 이름 첫 글자가 같을 때 인정한다.
    """
    if not rows:
        return None
    target = " ".join(_tokens(original))
    if not target:
        return None
    exact = [row for row in rows if " ".join(_tokens(row.english_name)) == target]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    # 모델 표기가 DB 이름으로 시작한다(`AEK Athens` → `AEK Athens FC`).
    prefixed = [
        row
        for row in rows
        if " ".join(_tokens(row.english_name)).startswith(target + " ")
    ]
    if len(prefixed) == 1:
        return prefixed[0]
    if len(prefixed) > 1:
        return None
    # 또는 DB 이름이 모델 표기로 시작한다(`Coventry` → `Coventry City`).
    shortened = [
        row
        for row in rows
        if target.startswith(" ".join(_tokens(row.english_name)) + " ")
    ]
    if len(shortened) == 1:
        return shortened[0]
    if len(shortened) > 1:
        return None
    # 머리글자 표기(DB `E. Maresca` ↔ 모델 `Enzo Maresca`).
    tokens = tuple(_tokens(original))
    if len(tokens) == 2:
        initials = [
            row
            for row in rows
            if len(_tokens(row.english_name)) == 2
            and _tokens(row.english_name)[1] == tokens[1]
            and _tokens(row.english_name)[0].rstrip(".") == tokens[0][:1]
        ]
        if len(initials) == 1:
            return initials[0]
    return None


def _catalog_allowed(name: str) -> bool:
    """이 표기로 DB 카탈로그를 조회해도 되는지. 너무 짧거나 일반적인 문자열은 막는다.

    이름 하나를 정확 일치로만 찾으므로 전수 스캔은 아니지만, `FC`·`1` 같은 표기로
    엉뚱한 다수 후보를 부르지 않도록 최소 길이를 요구한다.
    """
    compact = _WS.sub("", name or "")
    if len(compact) < MIN_LATIN_SURFACE_LEN:
        return False
    return bool(compact)


def _iter_model_labels(labels: Any):
    """모델이 준 번역 표기 목록을 항목 단위로 넘긴다. 모양이 다르면 건너뛴다."""
    if not isinstance(labels, (list, tuple)):
        return
    for entry in labels:
        if isinstance(entry, Mapping):
            yield entry


def _replace_segment(
    segment: str,
    pattern: re.Pattern[str],
    terms: Mapping[str, _Term],
    folded: Mapping[str, _Term],
) -> str:
    if not segment:
        return segment

    def _sub(match: re.Match[str]) -> str:
        surface = match.group(0)
        term = terms.get(surface) or folded.get(surface.casefold())
        if term is None:
            return surface
        if term.bare_korean and _touching_korean(segment, match.start()):
            # 한국어가 **바로 붙어** 있으면 더 큰 낱말의 일부다(`맨시티팬`). 그때는
            # 바꾸지 않는다. 띄어 쓴 `로서 맨시티의`는 독립 표기이므로 바꾼다.
            return surface
        # DB 값으로 바꾼다. 표기가 이미 같으면 결과도 같다.
        return term.replacement

    return pattern.sub(_sub, segment)


def _touching_korean(value: str, start: int) -> bool:
    """매치 바로 앞 글자가 한국어인지 확인한다(공백이 있으면 False)."""
    return start > 0 and _has_korean(value[start - 1])


def _has_korean(value: str) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in value)


class DbNameLookup:
    """기존 DB에서 팀·선수 이름 열만 읽는다(읽기 전용, 범위 한정).

    한 번의 실행에 필요한 엔티티만 묶어서 읽는다. 필터 없는 전체 조회는 거부한다.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    @classmethod
    def from_url(cls, url: str) -> "DbNameLookup":
        return cls(build_read_only_engine(url))

    def close(self) -> None:
        self._engine.dispose()

    def _rows(self, statement: str, parameters: Mapping[str, Any]) -> list[Mapping[str, Any]]:
        with self._engine.connect() as conn:
            conn.execute(
                text(f"SET LOCAL statement_timeout = {READ_ONLY_STATEMENT_TIMEOUT_MS}")
            )
            return [dict(row) for row in conn.execute(text(statement), dict(parameters)).mappings()]

    def load_teams(
        self,
        *,
        team_ids: Sequence[int] | None = None,
        external_ids: Sequence[int] | None = None,
    ) -> tuple[TeamNameRow, ...]:
        """팀 이름 행. `team_ids`는 DB 기본키, `external_ids`는 API-Football 팀 ID다."""
        if not team_ids and not external_ids:
            raise ValueError("team_ids or external_ids is required")
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        if team_ids:
            ids = sorted({int(value) for value in team_ids})[:MAX_TEAMS_PER_QUERY]
            clauses.append("t.id = ANY(:team_ids)")
            parameters["team_ids"] = ids
        if external_ids:
            ids = sorted({int(value) for value in external_ids})[:MAX_TEAMS_PER_QUERY]
            clauses.append("t.external_id = ANY(:external_ids)")
            parameters["external_ids"] = ids
        statement = f"""
            SELECT t.id, t.external_id, t.name,
                   tt.name_ko, tt.short_name_ko
            FROM public.team t
            LEFT JOIN public.team_translation tt ON tt.team_id = t.id
            WHERE {' OR '.join(clauses)}
        """
        return tuple(
            TeamNameRow(
                team_id=int(row["id"]),
                external_id=int(row["external_id"]) if row["external_id"] is not None else None,
                english_name=str(row["name"]),
                name_ko=row["name_ko"],
                short_name_ko=row["short_name_ko"],
            )
            for row in self._rows(statement, parameters)
        )

    def find_teams_by_name(self, name: Any) -> tuple[TeamNameRow, ...]:
        """이름 표기로 팀을 **DB 카탈로그에서 직접** 찾는다(정확 일치만).

        본문에 등장한 상대 팀처럼 그 경기의 두 팀 범위 밖에 있는 이름을 확인하는
        경로다. 정확 일치(`name`)만 보고, 퍼지 검색이나 전체 스캔을 하지 않는다.
        후보가 여럿이면 호출자가 고르지 않는다(동명이 팀).
        """
        text = _first_text(name)
        if not text:
            return ()
        statement = """
            SELECT t.id, t.external_id, t.name,
                   tt.name_ko, tt.short_name_ko
            FROM public.team t
            LEFT JOIN public.team_translation tt ON tt.team_id = t.id
            WHERE upper(t.name) = upper(:name)
               OR upper(t.name) LIKE upper(:name) || ' %'
               OR upper(:name) LIKE upper(t.name) || ' %'
            LIMIT :limit
        """
        return tuple(
            TeamNameRow(
                team_id=int(row["id"]),
                external_id=int(row["external_id"]) if row["external_id"] is not None else None,
                english_name=str(row["name"]),
                name_ko=row["name_ko"],
                short_name_ko=row["short_name_ko"],
            )
            for row in self._rows(
                statement, {"name": text, "limit": MAX_NAME_CANDIDATES}
            )
        )

    def find_coaches_by_name(self, name: Any) -> tuple[CoachNameRow, ...]:
        """이름 표기로 감독을 DB에서 직접 찾는다(정확 일치만, 범위 한정)."""
        text = _first_text(name)
        if not text:
            return ()
        statement = """
            SELECT c.id, c.external_id, c.name,
                   ct.name_ko, ct.short_name_ko
            FROM public.coach c
            LEFT JOIN public.coach_translation ct ON ct.coach_id = c.id
            WHERE upper(c.name) = upper(:name)
               OR upper(c.name) LIKE '% ' || upper(:surname)
            LIMIT :limit
        """
        return tuple(
            CoachNameRow(
                coach_id=int(row["id"]),
                external_id=int(row["external_id"]) if row["external_id"] is not None else None,
                english_name=str(row["name"]),
                name_ko=row["name_ko"],
                short_name_ko=row["short_name_ko"],
            )
            for row in self._rows(
                statement,
                {
                    "name": text,
                    "surname": (_tokens(text) or ("",))[-1],
                    "limit": MAX_NAME_CANDIDATES,
                },
            )
        )

    def load_coaches(
        self,
        *,
        team_ids: Sequence[int] | None = None,
        coach_ids: Sequence[int] | None = None,
    ) -> tuple[CoachNameRow, ...]:
        """감독 이름 행. 팀(`team_coach`) 또는 지정한 감독만 읽는다(이름 열만)."""
        if not team_ids and not coach_ids:
            raise ValueError("team_ids or coach_ids is required")
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        if team_ids:
            ids = sorted({int(value) for value in team_ids})[:MAX_TEAMS_PER_QUERY]
            clauses.append(
                "c.id IN (SELECT tc.coach_id FROM public.team_coach tc"
                " WHERE tc.team_id = ANY(:team_ids))"
            )
            parameters["team_ids"] = ids
        if coach_ids:
            ids = sorted({int(value) for value in coach_ids})[:MAX_PLAYERS_PER_QUERY]
            clauses.append("c.id = ANY(:coach_ids)")
            parameters["coach_ids"] = ids
        statement = f"""
            SELECT c.id, c.external_id, c.name,
                   ct.name_ko, ct.short_name_ko
            FROM public.coach c
            LEFT JOIN public.coach_translation ct ON ct.coach_id = c.id
            WHERE {' OR '.join(clauses)}
        """
        return tuple(
            CoachNameRow(
                coach_id=int(row["id"]),
                external_id=int(row["external_id"]) if row["external_id"] is not None else None,
                english_name=str(row["name"]),
                name_ko=row["name_ko"],
                short_name_ko=row["short_name_ko"],
            )
            for row in self._rows(statement, parameters)
        )

    def load_players(
        self,
        *,
        team_ids: Sequence[int] | None = None,
        player_ids: Sequence[int] | None = None,
        external_ids: Sequence[int] | None = None,
    ) -> tuple[PlayerNameRow, ...]:
        """선수 이름 행. 로스터(`team_ids`) 또는 지정한 선수만 읽는다."""
        if not team_ids and not player_ids and not external_ids:
            raise ValueError("team_ids, player_ids or external_ids is required")
        clauses: list[str] = []
        parameters: dict[str, Any] = {}
        if team_ids:
            ids = sorted({int(value) for value in team_ids})[:MAX_TEAMS_PER_QUERY]
            clauses.append("p.current_team_id = ANY(:team_ids)")
            parameters["team_ids"] = ids
        if player_ids:
            ids = sorted({int(value) for value in player_ids})[:MAX_PLAYERS_PER_QUERY]
            clauses.append("p.id = ANY(:player_ids)")
            parameters["player_ids"] = ids
        if external_ids:
            ids = sorted({int(value) for value in external_ids})[:MAX_PLAYERS_PER_QUERY]
            clauses.append("p.external_id = ANY(:external_ids)")
            parameters["external_ids"] = ids
        statement = f"""
            SELECT p.id, p.external_id, p.name, p.firstname, p.lastname,
                   p.current_team_id, pt.name_ko, pt.short_name_ko
            FROM public.player p
            LEFT JOIN public.player_translation pt ON pt.player_id = p.id
            WHERE {' OR '.join(clauses)}
            ORDER BY p.id ASC
            LIMIT {MAX_PLAYERS_PER_QUERY}
        """
        return tuple(
            PlayerNameRow(
                player_id=int(row["id"]),
                external_id=int(row["external_id"]) if row["external_id"] is not None else None,
                english_name=str(row["name"]),
                firstname=row["firstname"],
                lastname=row["lastname"],
                current_team_id=(
                    int(row["current_team_id"]) if row["current_team_id"] is not None else None
                ),
                name_ko=row["name_ko"],
                short_name_ko=row["short_name_ko"],
            )
            for row in self._rows(statement, parameters)
        )


def load_name_index(
    lookup: DbNameLookup,
    *,
    team_ids: Sequence[int] | None = None,
    team_external_ids: Sequence[int] | None = None,
    include_rosters: bool = True,
    player_ids: Sequence[int] | None = None,
) -> LocalizedNameIndex:
    """필요한 팀·선수만 읽어 인덱스를 만든다.

    로스터는 이름 매칭 범위를 좁히는 데만 쓰고, 이름 관련 열만 가져온다.
    """
    teams = lookup.load_teams(team_ids=team_ids, external_ids=team_external_ids)
    internal_ids = [team.team_id for team in teams]
    players: tuple[PlayerNameRow, ...] = ()
    coaches: tuple[CoachNameRow, ...] = ()
    # 본문에 나온 범위 밖 이름을 DB에서 직접 확인할 때 쓰는 좁은 조회기.
    # 이미 열려 있는 읽기 전용 조회기를 그대로 재사용한다(새 연결·권한 없음).
    catalog: Any = lookup
    if include_rosters and internal_ids:
        players = lookup.load_players(team_ids=internal_ids)
        # 감독 이름도 같은 범위에서 읽는다. 이름 열만 읽고 권한이 없으면 건너뛴다.
        try:
            coaches = lookup.load_coaches(team_ids=internal_ids)
        except Exception:  # noqa: BLE001 - 감독 이름 권한이 없어도 나머지는 동작한다
            coaches = ()
    if player_ids:
        picked = lookup.load_players(player_ids=player_ids)
        merged = {row.player_id: row for row in players}
        for row in picked:
            merged[row.player_id] = row
        players = tuple(merged[key] for key in sorted(merged))
    return LocalizedNameIndex(
        teams=teams, players=players, coaches=coaches, catalog=catalog
    )
