"""축구 용어·대회명 한국어 표기 (공유 표시 계층).

무엇인가:

- 독자용 문장에 영어로 남는 **축구 용어와 대회·국가·도시 표기**를 한국어로 바꾸는
  단일 사전이다. 모듈마다 정규식을 흩어 두지 않고 여기 한 곳에서만 관리한다.
- 값은 **언어 표기**만 바꾼다. 점수·사건·선수/팀 신원·사실 전제는 건드리지 않는다.

무엇이 아닌가:

- **AI 번역이 아니다.** 여기 값은 고정된 표기 사전이며, 모델이 만든 번역이 아니다.
- 선수·감독·팀 이름 사전이 아니다. 그 셋은 DB를 먼저 보고, DB에 없을 때만 모델이
  같은 응답에서 준 `korean_labels`를 쓴다(`display_names`가 그 순서를 지킨다).
- 근거·원문 식별자를 바꾸지 않는다. URL·API id는 그대로 남는다.

표기 원칙:

- 사용자가 지정한 표기를 따른다(예: hat-trick → **헤트트릭**). 표기 연구·논쟁을 하지
  않는다.
- 긴 표기를 먼저 바꾼다(`Champions League`가 `League`보다 먼저).
- 낱말 경계는 라틴 문자·숫자 기준이다. 한국어 조사가 붙은 형태(`Leipzig와`)도 인식한다.
- 이미 한국어인 문장은 그대로 둔다.
"""

from __future__ import annotations

import re
from typing import Mapping

__all__ = [
    "FOOTBALL_TERMS",
    "rewrite_football_terms",
]

# 표기 사전. 키는 영어 원문(대소문자 무시), 값은 한국어 표기다.
# 여기에 없는 고유명사(팀·선수·감독)는 DB 또는 모델 제공 번역이 담당한다.
FOOTBALL_TERMS: Mapping[str, str] = {
    # 경기 사건·기록
    "hat-trick": "헤트트릭",
    "hat trick": "헤트트릭",
    "hattrick": "헤트트릭",
    "brace": "멀티골",
    "clean sheet": "무실점",
    "own goal": "자책골",
    "penalty shootout": "승부차기",
    "penalty kick": "페널티킥",
    "free kick": "프리킥",
    "corner kick": "코너킥",
    "set piece": "세트피스",
    "counter-attack": "역습",
    "counterattack": "역습",
    "assist": "도움",
    "assists": "도움",
    "yellow card": "경고",
    "red card": "퇴장",
    "offside": "오프사이드",
    "injury time": "추가 시간",
    "stoppage time": "추가 시간",
    "extra time": "연장전",
    "full time": "경기 종료",
    "half time": "하프타임",
    "halftime": "하프타임",
    "kick-off": "킥오프",
    "kickoff": "킥오프",
    # 대회
    "UEFA Champions League": "UEFA 챔피언스리그",
    "Champions League": "챔피언스리그",
    "Europa League": "유로파리그",
    "Conference League": "컨퍼런스리그",
    "UEFA": "UEFA",
    "Premier League": "프리미어리그",
    "FA Cup": "FA컵",
    "EFL Cup": "EFL컵",
    "Carabao Cup": "카라바오컵",
    "World Cup": "월드컵",
    "European Championship": "유럽선수권",
    "Copa del Rey": "코파 델 레이",
    "Serie A": "세리에 A",
    "La Liga": "라리가",
    "Bundesliga": "분데스리가",
    "Ligue 1": "리그 1",
    "Eredivisie": "에레디비시",
    # 경기·포지션·전술
    "midfielder": "미드필더",
    "striker": "스트라이커",
    "forward": "공격수",
    "winger": "윙어",
    "defender": "수비수",
    "goalkeeper": "골키퍼",
    "centre-back": "센터백",
    "center-back": "센터백",
    "full-back": "풀백",
    "playmaker": "플레이메이커",
    "formation": "포메이션",
    "press": "압박",
    "pressing": "압박",
    "possession": "점유율",
    "xG": "기대득점",
    "derby": "더비",
    "leg": "레그",
    "aggregate": "합계",
    "draw": "무승부",
    "fixture": "경기",
    "squad": "선수단",
    "lineup": "선발 라인업",
    "line-up": "선발 라인업",
    "starting XI": "선발 11인",
    "substitution": "교체",
    "transfer": "이적",
    "loan": "임대",
    "contract": "계약",
    "injury": "부상",
    "suspension": "출전 정지",
    "fitness": "컨디션",
}

# 긴 표기 우선. 같은 길이면 사전 순서를 유지한다.
_ORDERED: tuple[tuple[str, str], ...] = tuple(
    sorted(FOOTBALL_TERMS.items(), key=lambda item: (-len(item[0]), item[0]))
)

_PATTERN: re.Pattern[str] | None = None
_MAP: dict[str, str] = {}


def _pattern() -> tuple[re.Pattern[str], dict[str, str]]:
    global _PATTERN, _MAP
    if _PATTERN is None:
        alternatives = "|".join(re.escape(surface) for surface, _ in _ORDERED)
        # 라틴 문자·숫자 기준 낱말 경계. `Leipzig와`처럼 한국어 조사가 붙은 형태도 잡는다.
        _PATTERN = re.compile(
            rf"(?<![0-9A-Za-z_])(?:{alternatives})(?![0-9A-Za-z_])",
            re.IGNORECASE,
        )
        _MAP = {surface.casefold(): replacement for surface, replacement in _ORDERED}
    return _PATTERN, _MAP


_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'\u3000]+", re.IGNORECASE)

# 조사 짝. 영어 표기를 한국어로 바꾸면 앞 낱말의 받침이 달라져 조사가 어긋난다
# (`clean sheet를` → `무실점를`). 받침에 맞춰 조사만 고쳐 쓴다. 낱말·수치·사건은
# 건드리지 않는다.
_PARTICLE_PAIRS: Mapping[str, tuple[str, str]] = {
    # (받침 있을 때, 받침 없을 때)
    "을": ("을", "를"),
    "를": ("을", "를"),
    "은": ("은", "는"),
    "는": ("은", "는"),
    "이": ("이", "가"),
    "가": ("이", "가"),
    "과": ("과", "와"),
    "와": ("과", "와"),
}


def _has_batchim(text: str) -> bool | None:
    """마지막 글자에 받침이 있는지. 한글이 아니면 판단하지 않는다(`None`)."""
    if not text:
        return None
    last = text[-1]
    if not ("\uac00" <= last <= "\ud7a3"):
        return None
    return (ord(last) - 0xAC00) % 28 != 0


def _fix_particle(word: str, particle: str) -> str:
    """앞 낱말의 받침에 맞는 조사로 바꾼다. 판단할 수 없으면 그대로 둔다."""
    pair = _PARTICLE_PAIRS.get(particle)
    if pair is None:
        return particle
    batchim = _has_batchim(word)
    if batchim is None:
        return particle
    return pair[0] if batchim else pair[1]


def rewrite_football_terms(text: str) -> str:
    """문장의 축구 용어·대회명을 한국어 표기로 바꾼다. URL 구간은 그대로 둔다.

    신원·수치·사건은 건드리지 않는다. 사전에 없는 고유명사는 그대로 남는다.
    한국어로 바뀐 낱말 바로 뒤의 조사는 받침에 맞춰 함께 고친다.
    """
    value = str(text or "")
    if not value:
        return ""
    pattern, mapping = _pattern()

    def _rewrite(segment: str) -> str:
        out: list[str] = []
        cursor = 0
        for match in pattern.finditer(segment):
            surface = match.group(0)
            replacement = mapping.get(surface.casefold())
            if replacement is None:
                continue
            out.append(segment[cursor : match.start()])
            out.append(replacement)
            cursor = match.end()
            # 바로 뒤에 조사가 붙어 있으면 받침에 맞춰 고친다.
            if cursor < len(segment) and segment[cursor] in _PARTICLE_PAIRS:
                particle = segment[cursor]
                fixed = _fix_particle(replacement, particle)
                # 조사 뒤에 다른 글자가 이어지면(예: `은데`) 조사로 보지 않는다.
                nxt = segment[cursor + 1] if cursor + 1 < len(segment) else ""
                if not ("\uac00" <= nxt <= "\ud7a3"):
                    out.append(fixed)
                    cursor += 1
        out.append(segment[cursor:])
        return "".join(out)

    pieces: list[str] = []
    cursor = 0
    for url_match in _URL.finditer(value):
        pieces.append(_rewrite(value[cursor : url_match.start()]))
        pieces.append(url_match.group(0))
        cursor = url_match.end()
    pieces.append(_rewrite(value[cursor:]))
    return "".join(pieces)
