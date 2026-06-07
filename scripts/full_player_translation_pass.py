from __future__ import annotations

import argparse
import csv
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "benchmark-player-translation-full-pass/0.1"


PLAYER_SQL = text(
    """
    SELECT
        p.id AS player_id,
        p.external_id,
        p.name,
        p.firstname,
        p.lastname,
        p.nationality,
        COALESCE(string_agg(DISTINCT t.name, '; ' ORDER BY t.name), '') AS teams,
        COALESCE(string_agg(DISTINCT t.country, '; ' ORDER BY t.country), '') AS team_countries,
        COALESCE(string_agg(DISTINCT l.name, '; ' ORDER BY l.name), '') AS leagues,
        pt.name_ko AS current_name_ko,
        pt.short_name_ko AS current_short_name_ko
    FROM player p
    LEFT JOIN player_translation pt ON pt.player_id = p.id
    LEFT JOIN player_season_stat pss ON pss.player_id = p.id
    LEFT JOIN team t ON t.id = pss.team_id
    LEFT JOIN league l ON l.id = pss.league_id
    GROUP BY p.id, p.external_id, p.name, p.firstname, p.lastname, p.nationality,
             pt.name_ko, pt.short_name_ko
    ORDER BY p.external_id
    """
)


MANUAL_KO: dict[str, tuple[str, str]] = {
    "Achraf Hakimi": ("아슈라프 하키미", "하키미"),
    "Ángel Correa": ("앙헬 코레아", "코레아"),
    "Denzel Dumfries": ("덴절 둠프리스", "둠프리스"),
    "Felix Nmecha": ("펠릭스 은메차", "은메차"),
    "Callum McGregor": ("칼럼 맥그리거", "맥그리거"),
    "Henrikh Mkhitaryan": ("헨리크 미키타리안", "미키타리안"),
    "Danny Welbeck": ("대니 웰벡", "웰벡"),
    "Daniel Welbeck": ("대니얼 웰벡", "웰벡"),
    "Hakan Çalhanoğlu": ("하칸 찰하놀루", "찰하놀루"),
    "Francesco Acerbi": ("프란체스코 아체르비", "아체르비"),
    "Eduardo Camavinga": ("에두아르도 카마빙가", "카마빙가"),
    "Jefferson Lerma": ("헤페르손 레르마", "레르마"),
    "Daichi Kamada": ("가마다 다이치", "가마다"),
    "Wout Faes": ("바우트 파스", "파스"),
    "Jhon Durán": ("존 두란", "두란"),
    "Daniel Muñoz": ("다니엘 무뇨스", "무뇨스"),
    "Willian Pacho": ("윌리안 파초", "파초"),
    "Jarrad Branthwaite": ("재러드 브랜스웨이트", "브랜스웨이트"),
    "Will Hughes": ("윌 휴스", "휴스"),
    "Marko Arnautović": ("마르코 아르나우토비치", "아르나우토비치"),
    "Dominic Solanke": ("도미닉 솔란케", "솔란케"),
    "Ryan Sessegnon": ("라이언 세세뇽", "세세뇽"),
    "Tosin Adarabioyo": ("토신 아다라비오요", "아다라비오요"),
    "Cameron Carter-Vickers": ("캐머런 카터비커스", "카터비커스"),
    "Kevin Danso": ("케빈 단소", "단소"),
    "Andrea Belotti": ("안드레아 벨로티", "벨로티"),
    "Alessandro Bastoni": ("알레산드로 바스토니", "바스토니"),
    "Sultan Al Ghannam": ("술탄 알간남", "알간남"),
    "Joško Gvardiol": ("요슈코 그바르디올", "그바르디올"),
    "Filip Szymczak": ("필리프 심차크", "심차크"),
    "Carney Chukwuemeka": ("카니 추쿠에메카", "추쿠에메카"),
    "Kerem Aktürkoğlu": ("케렘 아크튀르콜루", "아크튀르콜루"),
    "Cole Palmer": ("콜 파머", "파머"),
    "Giovanni Reyna": ("조반니 레이나", "레이나"),
    "Dane Scarlett": ("데인 스칼렛", "스칼렛"),
    "Casper Tengstedt": ("카스페르 텡스테트", "텡스테트"),
    "Reo Hatate": ("하타테 레오", "하타테"),
    "Jamal Musiala": ("자말 무시알라", "무시알라"),
    "Jonas Urbig": ("요나스 우르비히", "우르비히"),
    "Pape Matar Sarr": ("파프 마타르 사르", "사르"),
    "Diego Gómez": ("디에고 고메스", "고메스"),
    "Tim Iroegbunam": ("팀 이로에그부남", "이로에그부남"),
    "Andreas Schjelderup": ("안드레아스 셸데루프", "셸데루프"),
    "Jack Hinshelwood": ("잭 힌셜우드", "힌셜우드"),
    "Luciano Valente": ("루치아노 발렌테", "발렌테"),
    "Carlos Baleba": ("카를로스 발레바", "발레바"),
    "Gaoussou Diarra": ("가우수 디아라", "디아라"),
    "Benjamin Anthony Brereton Díaz": ("벤자민 안토니 브레레톤 디아스", "브레레톤"),
    "Benjamin Anthony Brereton": ("벤자민 안토니 브레레톤 디아스", "브레레톤"),
    "Ben Brereton Díaz": ("벤 브레레톤 디아스", "브레레톤"),
    "Jacob Mikael Widell Zetterström": ("야콥 미카엘 비델 세테르스트룀", "세테르스트룀"),
    "Jacob Widell Zetterström": ("야콥 비델 세테르스트룀", "세테르스트룀"),
    "Daniel Svensson": ("다니엘 스벤손", "스벤손"),
    "Alai Fadel Ali Hussain Ghasem": ("알라이 파델 알리 후세인 가셈", "가셈"),
    "Alai Ghasem": ("알라이 가셈", "가셈"),
    "Jeremy Nosakhare Agbonifo": ("제레미 노사카레 아그보니포", "아그보니포"),
    "Jeremy Agbonifo": ("제레미 아그보니포", "아그보니포"),
    "Malcolm John Matarr Jeng": ("말콤 존 마타르 젱", "젱"),
    "Malcolm Jeng": ("말콤 젱", "젱"),
}


SEED_FILES = [
    Path("seeds/player_translation_epl_2025.csv"),
    Path("seeds/player_translation_epl_2025_remaining.csv"),
    Path("seeds/player_translation_ucl_2025_priority.csv"),
    Path("seeds/player_translation_ucl_2025_remaining.csv"),
    Path("seeds/player_translation_uel_2025_remaining.csv"),
    Path("seeds/player_translation_league_cup_2025_final.csv"),
    Path("seeds/player_translation_league_cup_2025_remaining.csv"),
    Path("seeds/player_translation_fa_cup_2025.csv"),
    Path("seeds/player_translation_world_cup_2022.csv"),
    Path("seeds/player_translation_world_cup_2026.current_team.csv"),
    Path("seeds/player_translation_corrections_20260519.csv"),
]


INITIAL_SOUND_PREFIXES = (
    "에이 ",
    "비 ",
    "씨 ",
    "디 ",
    "이 ",
    "에프 ",
    "지 ",
    "제이 ",
    "케이 ",
    "엘 ",
    "엠 ",
    "엔 ",
    "오 ",
    "피 ",
    "큐 ",
    "알 ",
    "에스 ",
    "티 ",
    "유 ",
    "브이 ",
    "더블유 ",
    "엑스 ",
    "와이 ",
    "제트 ",
)


PARTICLES = {
    "al",
    "bin",
    "da",
    "de",
    "del",
    "della",
    "di",
    "dos",
    "du",
    "el",
    "la",
    "le",
    "van",
    "von",
}


LANGUAGE_BY_NATIONALITY: dict[str, str] = {
    "England": "english",
    "USA": "english",
    "Scotland": "english",
    "Wales": "english",
    "Northern Ireland": "english",
    "Republic of Ireland": "english",
    "Australia": "english",
    "New Zealand": "english",
    "Canada": "english",
    "Jamaica": "english",
    "Ghana": "english",
    "Nigeria": "english",
    "South Africa": "english",
    "Spain": "spanish",
    "Argentina": "spanish",
    "Uruguay": "spanish",
    "Colombia": "spanish",
    "Ecuador": "spanish",
    "Paraguay": "spanish",
    "Costa Rica": "spanish",
    "Panama": "spanish",
    "Mexico": "spanish",
    "Brazil": "portuguese",
    "Portugal": "portuguese",
    "France": "french",
    "Senegal": "french",
    "Côte d'Ivoire": "french",
    "Ivory Coast": "french",
    "Mali": "french",
    "Cameroon": "french",
    "Belgium": "french",
    "Guinea": "french",
    "Burkina Faso": "french",
    "Gabon": "french",
    "Central African Republic": "french",
    "Benin": "french",
    "Haiti": "french",
    "Madagascar": "french",
    "Comoros": "french",
    "Guadeloupe": "french",
    "Congo": "french",
    "Congo DR": "french",
    "Togo": "french",
    "Luxembourg": "french",
    "Martinique": "french",
    "Germany": "german",
    "Austria": "german",
    "Switzerland": "german",
    "Netherlands": "dutch",
    "Suriname": "dutch",
    "Denmark": "danish",
    "Faroe Islands": "faroese",
    "Norway": "norwegian",
    "Sweden": "swedish",
    "Finland": "finnish",
    "Iceland": "icelandic",
    "Estonia": "estonian",
    "Latvia": "latvian",
    "Lithuania": "lithuanian",
    "Italy": "italian",
    "Japan": "japanese",
    "Korea Republic": "korean",
    "Croatia": "croatian",
    "Serbia": "serbian",
    "Montenegro": "serbian",
    "Bosnia and Herzegovina": "bosnian",
    "Slovenia": "slovenian",
    "Slovakia": "slovak",
    "Poland": "polish",
    "Czechia": "czech",
    "Czech Republic": "czech",
    "Bulgaria": "bulgarian",
    "North Macedonia": "macedonian",
    "Belarus": "belarusian",
    "Georgia": "georgian",
    "Armenia": "armenian",
    "Albania": "albanian",
    "Kosovo": "albanian",
    "Hungary": "hungarian",
    "Romania": "romanian",
    "Moldova": "romanian",
    "Greece": "greek",
    "Türkiye": "turkish",
    "Turkey": "turkish",
    "Azerbaijan": "turkish",
    "Russia": "russian",
    "Ukraine": "ukrainian",
    "Kazakhstan": "kazakh",
    "Uzbekistan": "uzbek",
    "Saudi Arabia": "arabic",
    "Qatar": "arabic",
    "Iraq": "arabic",
    "Jordan": "arabic",
    "Egypt": "arabic",
    "Algeria": "arabic",
    "Morocco": "arabic",
    "Tunisia": "arabic",
    "Lebanon": "arabic",
    "Libya": "arabic",
    "Mauritania": "arabic",
    "United Arab Emirates": "arabic",
    "Iran": "persian",
    "Peru": "spanish",
    "Venezuela": "spanish",
    "Chile": "spanish",
    "Cuba": "spanish",
    "Guatemala": "spanish",
    "Honduras": "spanish",
    "Bolivia": "spanish",
    "Nicaragua": "spanish",
    "Equatorial Guinea": "spanish",
    "Mozambique": "portuguese",
    "Guinea-Bissau": "portuguese",
    "Cape Verde": "portuguese",
    "Cyprus": "greek",
    "Indonesia": "indonesian",
    "Israel": "hebrew",
    "Tanzania": "swahili",
    "Rwanda": "kinyarwanda",
    "El Salvador": "spanish",
    "Uganda": "swahili",
    "Burundi": "kirundi",
    "Niger": "french",
    "Sudan": "arabic",
    "Chad": "arabic",
    "Kenya": "swahili",
    "Malta": "maltese",
    "Philippines": "filipino",
    "Botswana": "tswana",
    "Zimbabwe": "shona",
    "Zambia": "english",
    "Dominican Republic": "spanish",
    "Bermuda": "english",
    "Gibraltar": "english",
    "Grenada": "english",
    "St. Lucia": "english",
    "Antigua and Barbuda": "english",
    "Trinidad and Tobago": "english",
}


@dataclass
class PlayerRow:
    player_id: int
    external_id: int
    name: str
    firstname: str
    lastname: str
    nationality: str
    teams: str
    team_countries: str
    leagues: str
    current_name_ko: str
    current_short_name_ko: str


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("Ŀ", "L")).strip()


def strip_marks(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def full_name(row: PlayerRow) -> str:
    value = clean(f"{row.firstname} {row.lastname}")
    return value or clean(row.name)


def first_token(value: str) -> str:
    parts = [part for part in re.split(r"\s+", clean(value)) if part]
    return parts[0] if parts else ""


def surname_tokens(value: str) -> list[str]:
    return [part for part in re.split(r"\s+", clean(value)) if part]


def candidate_names(row: PlayerRow) -> list[str]:
    first = clean(row.firstname)
    last = clean(row.lastname)
    full = full_name(row)
    first_parts = surname_tokens(first)
    last_parts = surname_tokens(last)
    candidates = [full]
    if first_parts and last_parts:
        candidates.append(f"{first_parts[0]} {' '.join(last_parts)}")
        candidates.append(f"{first_parts[0]} {last_parts[0]}")
        candidates.append(f"{first_parts[0]} {last_parts[-1]}")
        if len(first_parts) >= 2:
            candidates.append(f"{first_parts[0]} {first_parts[1]} {last_parts[0]}")
        if len(last_parts) >= 2 and last_parts[0].lower() in PARTICLES:
            candidates.append(f"{first_parts[0]} {last_parts[0]} {last_parts[1]}")
    if clean(row.name) and not re.fullmatch(r"[A-ZÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÇÑŞĞİÖÜ]\.\s+\S+", clean(row.name)):
        candidates.append(clean(row.name))
    return list(dict.fromkeys(name for name in candidates if name))


def has_ascii(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value or ""))


def has_abbreviated_source(value: str) -> bool:
    return bool(re.search(r"\b[A-ZÁÉÍÓÚÀÈÌÒÙÄËÏÖÜÇÑŞĞİÖÜ]\.", clean(value)))


def has_initial_sound_prefix(value: str) -> bool:
    normalized = clean(value)
    return any(normalized.startswith(prefix) for prefix in INITIAL_SOUND_PREFIXES)


def usable_ko(name_ko: str, short_ko: str, *, source_name: str = "") -> bool:
    if not name_ko or not short_ko:
        return False
    if has_ascii(name_ko) or has_ascii(short_ko):
        return False
    if re.search(r"[.]", name_ko) or re.search(r"[.]", short_ko):
        return False
    if has_abbreviated_source(source_name) and has_initial_sound_prefix(name_ko):
        return False
    return True


def load_seed_translations() -> dict[int, tuple[str, str, str]]:
    seed_by_external_id: dict[int, tuple[str, str, str]] = {}
    for path in SEED_FILES:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", newline="") as fp:
            for row in csv.DictReader(fp):
                raw_external_id = row.get("external_id") or row.get("player_id")
                if not raw_external_id:
                    continue
                try:
                    external_id = int(raw_external_id)
                except ValueError:
                    continue
                name_ko = clean(row.get("name_ko") or row.get("kor_name"))
                short_ko = clean(row.get("short_name_ko") or row.get("kor_short_name"))
                eng_name = clean(row.get("eng_name") or row.get("name"))
                if usable_ko(name_ko, short_ko, source_name=eng_name):
                    seed_by_external_id[external_id] = (
                        name_ko,
                        short_ko,
                        path.name,
                    )
    return seed_by_external_id


def query_wikidata_labels(candidates: list[str], *, batch_size: int = 35) -> dict[str, str]:
    labels: dict[str, str] = {}
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        values = " ".join(json.dumps(name, ensure_ascii=False) + "@en" for name in batch)
        query = (
            "SELECT ?en ?ko WHERE { "
            f"VALUES ?en {{ {values} }} "
            "?item (rdfs:label|<http://www.w3.org/2004/02/skos/core#altLabel>) ?en . "
            "?item rdfs:label ?ko . "
            'FILTER(LANG(?ko)="ko") '
            "?item wdt:P106 wd:Q937857 . "
            "}"
        )
        req = Request(
            f"{SPARQL_URL}?{urlencode({'format': 'json', 'query': query})}",
            headers={"User-Agent": USER_AGENT},
        )
        data: dict = {"results": {"bindings": []}}
        for attempt in range(5):
            try:
                with urlopen(req, timeout=45) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                if attempt == 4:
                    raise
                time.sleep(2 * (attempt + 1))
        for item in data.get("results", {}).get("bindings", []):
            labels[item["en"]["value"]] = item["ko"]["value"]
        time.sleep(0.6)
    return labels


SYLLABLE_EXCEPTIONS = {
    "aaron": "애런",
    "adam": "애덤",
    "alex": "알렉스",
    "aleksandr": "알렉산드르",
    "alexander": "알렉산더",
    "alessandro": "알레산드로",
    "andrea": "안드레아",
    "andreas": "안드레아스",
    "angel": "앙헬",
    "antonio": "안토니오",
    "benjamin": "벤자민",
    "bruno": "브루누",
    "callum": "칼럼",
    "carlos": "카를로스",
    "christian": "크리스천",
    "daniel": "다니엘",
    "david": "다비드",
    "diego": "디에고",
    "eduardo": "에두아르도",
    "felix": "펠릭스",
    "fernando": "페르난도",
    "francesco": "프란체스코",
    "gabriel": "가브리엘",
    "giovanni": "조반니",
    "jose": "호세",
    "juan": "후안",
    "kevin": "케빈",
    "luca": "루카",
    "lucas": "루카스",
    "manuel": "마누엘",
    "marco": "마르코",
    "mario": "마리오",
    "martin": "마르틴",
    "michael": "마이클",
    "mohamed": "모하메드",
    "mohammed": "모하메드",
    "paulo": "파울루",
    "pedro": "페드루",
    "robert": "로베르트",
    "samuel": "사무엘",
    "santiago": "산티아고",
    "thomas": "토마스",
    "victor": "빅토르",
}


LANG_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "english": [
        ("th", "ㅆ"),
        ("sh", "슈"),
        ("ch", "치"),
        ("ph", "프"),
        ("j", "지"),
        ("w", "우"),
    ],
    "spanish": [
        ("ll", "이"),
        ("ñ", "니"),
        ("j", "ㅎ"),
        ("ge", "헤"),
        ("gi", "히"),
        ("que", "케"),
        ("qui", "키"),
        ("z", "스"),
        ("v", "브"),
    ],
    "portuguese": [
        ("ão", "앙"),
        ("lh", "류"),
        ("nh", "뉴"),
        ("j", "주"),
        ("ç", "스"),
        ("g", "그"),
    ],
    "french": [
        ("ch", "슈"),
        ("ou", "우"),
        ("oi", "와"),
        ("ai", "에"),
        ("au", "오"),
        ("eau", "오"),
        ("gn", "뉴"),
        ("j", "주"),
        ("h", ""),
    ],
    "german": [
        ("sch", "슈"),
        ("ch", "흐"),
        ("ei", "아이"),
        ("ie", "이"),
        ("ö", "외"),
        ("ü", "위"),
        ("ä", "에"),
        ("w", "브"),
        ("z", "츠"),
        ("j", "요"),
    ],
    "dutch": [
        ("ij", "에이"),
        ("ui", "아위"),
        ("oe", "우"),
        ("g", "흐"),
        ("j", "이"),
        ("v", "프"),
    ],
    "italian": [
        ("chi", "키"),
        ("che", "케"),
        ("ci", "치"),
        ("ce", "체"),
        ("gli", "리"),
        ("gn", "니"),
        ("j", "이"),
    ],
    "japanese": [
        ("shi", "시"),
        ("chi", "치"),
        ("tsu", "쓰"),
        ("fu", "후"),
        ("ji", "지"),
        ("ka", "카"),
        ("ga", "가"),
        ("da", "다"),
    ],
    "turkish": [
        ("ç", "치"),
        ("ş", "슈"),
        ("ğ", ""),
        ("ö", "외"),
        ("ü", "위"),
        ("ı", "으"),
        ("c", "지"),
    ],
    "polish": [
        ("sz", "슈"),
        ("cz", "치"),
        ("rz", "주"),
        ("ł", "우"),
        ("w", "프"),
        ("j", "이"),
        ("ń", "니"),
    ],
    "russian": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
        ("y", "이"),
    ],
    "ukrainian": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
        ("yi", "이"),
        ("y", "이"),
    ],
    "croatian": [
        ("lj", "류"),
        ("nj", "니"),
        ("č", "치"),
        ("ć", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("đ", "지"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "serbian": [
        ("lj", "류"),
        ("nj", "니"),
        ("č", "치"),
        ("ć", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("đ", "지"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "bosnian": [
        ("lj", "류"),
        ("nj", "니"),
        ("č", "치"),
        ("ć", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("đ", "지"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "slovenian": [
        ("lj", "류"),
        ("nj", "니"),
        ("č", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "slovak": [
        ("ch", "흐"),
        ("č", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "czech": [
        ("ch", "흐"),
        ("č", "치"),
        ("š", "시"),
        ("ž", "지"),
        ("ř", "르시"),
        ("j", "이"),
        ("c", "츠"),
    ],
    "bulgarian": [
        ("zh", "지"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
        ("y", "이"),
    ],
    "macedonian": [
        ("gj", "기"),
        ("kj", "키"),
        ("zh", "지"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
    ],
    "belarusian": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
        ("y", "이"),
    ],
    "georgian": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
        ("dz", "즈"),
    ],
    "armenian": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("ts", "츠"),
    ],
    "albanian": [
        ("xh", "즈"),
        ("gj", "쟈"),
        ("q", "치"),
        ("ç", "치"),
        ("sh", "시"),
        ("th", "트"),
        ("dh", "드"),
        ("j", "이"),
    ],
    "hungarian": [
        ("sz", "스"),
        ("cs", "치"),
        ("zs", "주"),
        ("gy", "지"),
        ("ny", "니"),
        ("ly", "이"),
        ("á", "아"),
        ("é", "에"),
    ],
    "romanian": [
        ("ș", "시"),
        ("ş", "시"),
        ("ț", "츠"),
        ("ţ", "츠"),
        ("ci", "치"),
        ("ce", "체"),
        ("ch", "키"),
        ("gh", "기"),
    ],
    "greek": [
        ("ch", "흐"),
        ("th", "트"),
        ("ph", "프"),
        ("gi", "이"),
        ("ge", "예"),
        ("ou", "우"),
    ],
    "finnish": [
        ("j", "이"),
        ("y", "위"),
        ("ö", "외"),
        ("ä", "애"),
        ("aa", "아"),
        ("ee", "에"),
    ],
    "icelandic": [
        ("þ", "트"),
        ("ð", "드"),
        ("j", "이"),
        ("á", "아우"),
        ("é", "예"),
        ("ö", "외"),
    ],
    "estonian": [
        ("j", "이"),
        ("õ", "어"),
        ("ä", "애"),
        ("ö", "외"),
        ("ü", "위"),
    ],
    "latvian": [
        ("š", "시"),
        ("ž", "지"),
        ("č", "치"),
        ("j", "이"),
        ("ā", "아"),
        ("ē", "에"),
    ],
    "lithuanian": [
        ("š", "시"),
        ("ž", "지"),
        ("č", "치"),
        ("j", "이"),
        ("ė", "에"),
        ("ū", "우"),
    ],
    "kazakh": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("zh", "지"),
        ("y", "이"),
    ],
    "uzbek": [
        ("kh", "흐"),
        ("sh", "시"),
        ("ch", "치"),
        ("g'", "그"),
        ("o'", "오"),
    ],
    "faroese": [
        ("ð", ""),
        ("j", "이"),
        ("ø", "외"),
        ("á", "오아"),
        ("ó", "오우"),
    ],
    "indonesian": [
        ("ny", "니"),
        ("ng", "응"),
        ("sy", "시"),
        ("c", "치"),
        ("j", "지"),
    ],
    "arabic": [
        ("kh", "흐"),
        ("gh", "그"),
        ("sh", "시"),
        ("q", "크"),
        ("al ", "알 "),
    ],
    "hebrew": [
        ("tz", "츠"),
        ("ts", "츠"),
        ("kh", "흐"),
        ("ch", "흐"),
        ("sh", "시"),
        ("y", "이"),
    ],
    "swahili": [
        ("ny", "니"),
        ("ng", "응"),
        ("sh", "시"),
        ("ch", "치"),
        ("j", "지"),
    ],
    "kinyarwanda": [
        ("ny", "니"),
        ("ng", "응"),
        ("sh", "시"),
        ("ch", "치"),
        ("j", "지"),
    ],
    "kirundi": [
        ("ny", "니"),
        ("ng", "응"),
        ("sh", "시"),
        ("ch", "치"),
        ("j", "지"),
    ],
    "maltese": [
        ("għ", ""),
        ("gh", ""),
        ("x", "시"),
        ("ċ", "치"),
        ("ġ", "지"),
        ("j", "이"),
        ("ż", "즈"),
    ],
    "filipino": [
        ("ng", "응"),
        ("ny", "니"),
        ("ll", "이"),
        ("j", "지"),
        ("c", "크"),
    ],
    "tswana": [
        ("tlh", "틀"),
        ("kg", "크흐"),
        ("ny", "니"),
        ("ng", "응"),
        ("ts", "츠"),
        ("sh", "시"),
    ],
    "shona": [
        ("ny", "니"),
        ("ng", "응"),
        ("dz", "즈"),
        ("sv", "스브"),
        ("sh", "시"),
        ("ch", "치"),
    ],
}


VOWELS = {
    "a": "아",
    "e": "에",
    "i": "이",
    "o": "오",
    "u": "우",
    "y": "이",
}

CONS = {
    "b": "브",
    "c": "크",
    "d": "드",
    "f": "프",
    "g": "그",
    "h": "흐",
    "j": "지",
    "k": "크",
    "l": "르",
    "m": "므",
    "n": "느",
    "p": "프",
    "q": "크",
    "r": "르",
    "s": "스",
    "t": "트",
    "v": "브",
    "w": "우",
    "x": "크스",
    "z": "즈",
}


def postprocess(value: str) -> str:
    replacements = [
        ("르아", "라"),
        ("르에", "레"),
        ("르이", "리"),
        ("르오", "로"),
        ("르우", "루"),
        ("크아", "카"),
        ("크에", "케"),
        ("크이", "키"),
        ("크오", "코"),
        ("크우", "쿠"),
        ("트아", "타"),
        ("트에", "테"),
        ("트이", "티"),
        ("트오", "토"),
        ("트우", "투"),
        ("드아", "다"),
        ("드에", "데"),
        ("드이", "디"),
        ("드오", "도"),
        ("드우", "두"),
        ("브아", "바"),
        ("브에", "베"),
        ("브이", "비"),
        ("브오", "보"),
        ("브우", "부"),
        ("프아", "파"),
        ("프에", "페"),
        ("프이", "피"),
        ("프오", "포"),
        ("프우", "푸"),
        ("스아", "사"),
        ("스에", "세"),
        ("스이", "시"),
        ("스오", "소"),
        ("스우", "수"),
        ("그아", "가"),
        ("그에", "게"),
        ("그이", "기"),
        ("그오", "고"),
        ("그우", "구"),
        ("느아", "나"),
        ("느에", "네"),
        ("느이", "니"),
        ("느오", "노"),
        ("느우", "누"),
        ("므아", "마"),
        ("므에", "메"),
        ("므이", "미"),
        ("므오", "모"),
        ("므우", "무"),
        ("ㅆ", "스"),
    ]
    for src, dst in replacements:
        value = value.replace(src, dst)
    return value


def transliterate_word(word: str, lang: str) -> str:
    raw = clean(word)
    if not raw:
        return ""
    lowered_keep = raw.lower().replace("'", "")
    lowered_ascii = strip_marks(raw).lower().replace("'", "")
    lowered = lowered_keep if lang in {"spanish", "portuguese", "french", "german", "turkish", "polish"} else lowered_ascii
    lowered = re.sub(r"[^a-zà-ÿıłđšžčćñçğşöüäéèêëáàâãíìîïóòôõúùûýæøå-]", "", lowered)
    if not lowered:
        return raw
    key = strip_marks(lowered).lower()
    if key in SYLLABLE_EXCEPTIONS:
        return SYLLABLE_EXCEPTIONS[key]
    if "-" in lowered:
        return "-".join(transliterate_word(part, lang) for part in lowered.split("-") if part)
    out = ""
    i = 0
    replacements = LANG_REPLACEMENTS.get(lang, []) + [
        ("sch", "슈"),
        ("sh", "슈"),
        ("ch", "치"),
        ("ph", "프"),
        ("kh", "흐"),
        ("gh", "그"),
        ("qu", "쿠"),
        ("ou", "우"),
        ("au", "아우"),
        ("ai", "아이"),
        ("ei", "아이"),
        ("ie", "이"),
        ("oo", "우"),
    ]
    while i < len(lowered):
        matched = False
        for src, dst in replacements:
            if lowered.startswith(src, i):
                out += dst
                i += len(src)
                matched = True
                break
        if matched:
            continue
        ch = lowered[i]
        base = strip_marks(ch).lower()
        out += VOWELS.get(base, CONS.get(base, ch))
        i += 1
    return postprocess(out)


def is_particle(token: str) -> bool:
    return strip_marks(token).lower() in PARTICLES


def unique_team_countries(row: PlayerRow) -> list[str]:
    countries = []
    for country in row.team_countries.split(";"):
        country = clean(country)
        if country and country.lower() != "world" and country not in countries:
            countries.append(country)
    return countries


def effective_country(row: PlayerRow) -> tuple[str, str]:
    if row.nationality:
        return row.nationality, "nationality"
    countries = unique_team_countries(row)
    if len(countries) == 1:
        return countries[0], "team-country"
    return "", "unknown"


def transliterate_name(row: PlayerRow) -> tuple[str, str, str]:
    country, source = effective_country(row)
    lang = LANGUAGE_BY_NATIONALITY.get(country, "english")
    first_parts = [p for p in surname_tokens(row.firstname) if not is_particle(p)]
    last_parts = [p for p in surname_tokens(row.lastname) if not is_particle(p)]
    if not first_parts and not last_parts:
        parts = [p for p in surname_tokens(row.name) if not re.fullmatch(r"[A-Z]\.", p) and not is_particle(p)]
    elif lang == "japanese":
        parts = last_parts + first_parts
    elif lang == "korean":
        parts = last_parts + first_parts
    else:
        if len(first_parts) + len(last_parts) > 4:
            parts = [first_parts[0]] + last_parts[:1] if first_parts and last_parts else first_parts + last_parts
        else:
            parts = first_parts + last_parts
    name_ko = " ".join(transliterate_word(part, lang) for part in parts if part)
    short_source = last_parts[0] if last_parts else (parts[-1] if parts else row.name)
    short_ko = transliterate_word(short_source, lang)
    return name_ko, short_ko, f"{source}-phonetic:{country or 'unknown'}:{lang}"


def short_from_ko(name_ko: str) -> str:
    tokens = [token for token in name_ko.split() if token]
    return tokens[-1] if len(tokens) > 1 else name_ko


def quality_bad(name_ko: str, short_ko: str) -> bool:
    if has_ascii(name_ko) or has_ascii(short_ko):
        return True
    if re.match(r"^[A-ZÁÉÍÓÚ]\.", name_ko or ""):
        return True
    return False


def load_rows() -> list[PlayerRow]:
    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(PLAYER_SQL).mappings()]
    return [
        PlayerRow(
            player_id=int(row["player_id"]),
            external_id=int(row["external_id"]),
            name=clean(row["name"]),
            firstname=clean(row["firstname"]),
            lastname=clean(row["lastname"]),
            nationality=clean(row["nationality"]),
            teams=clean(row["teams"]),
            team_countries=clean(row["team_countries"]),
            leagues=clean(row["leagues"]),
            current_name_ko=clean(row["current_name_ko"]),
            current_short_name_ko=clean(row["current_short_name_ko"]),
        )
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--skip-wikidata", action="store_true")
    args = parser.parse_args()

    rows = load_rows()
    row_candidates = {row.external_id: candidate_names(row) for row in rows}
    candidates = list(dict.fromkeys(candidate for items in row_candidates.values() for candidate in items))
    labels = {} if args.skip_wikidata else query_wikidata_labels(candidates)
    seed_translations = load_seed_translations()

    out_rows: list[dict[str, str | int]] = []
    audit_rows: list[dict[str, str | int]] = []
    for row in rows:
        method = ""
        matched = ""
        name_ko = ""
        short_ko = ""
        for candidate in row_candidates[row.external_id]:
            manual = MANUAL_KO.get(candidate)
            if manual:
                name_ko, short_ko = manual
                method = "manual-common-name"
                matched = candidate
                break
        if not name_ko and row.external_id in seed_translations:
            name_ko, short_ko, seed_name = seed_translations[row.external_id]
            method = "verified-seed-csv"
            matched = seed_name
        if not name_ko:
            for candidate in row_candidates[row.external_id]:
                if candidate in labels and usable_ko(labels[candidate], short_from_ko(labels[candidate]), source_name=candidate):
                    name_ko = labels[candidate]
                    short_ko = short_from_ko(name_ko)
                    method = "wikidata-ko-label"
                    matched = candidate
                    break
        if (
            not name_ko
            and usable_ko(
                row.current_name_ko,
                row.current_short_name_ko,
                source_name=row.name,
            )
        ):
            name_ko = row.current_name_ko
            short_ko = row.current_short_name_ko
            method = "current-clean-ko"
            matched = "player_translation"
        if not name_ko:
            name_ko, short_ko, method = transliterate_name(row)
            matched = full_name(row)
        if not usable_ko(name_ko, short_ko, source_name=row.name):
            fallback_name_ko, fallback_short_ko, fallback_method = transliterate_name(row)
            if usable_ko(fallback_name_ko, fallback_short_ko, source_name=row.name):
                name_ko = fallback_name_ko
                short_ko = fallback_short_ko
                method = f"{method}|clean-fallback:{fallback_method}"
                matched = full_name(row)
        if not name_ko:
            name_ko = row.current_name_ko or row.name
            short_ko = row.current_short_name_ko or row.name
            method = "fallback-unresolved"
        out_rows.append(
            {
                "external_id": row.external_id,
                "eng_name": row.name,
                "name_ko": name_ko,
                "short_name_ko": short_ko,
            }
        )
        audit_rows.append(
            {
                "external_id": row.external_id,
                "player_id": row.player_id,
                "name": row.name,
                "firstname": row.firstname,
                "lastname": row.lastname,
                "full_name": full_name(row),
                "nationality": row.nationality,
                "teams": row.teams,
                "team_countries": row.team_countries,
                "leagues": row.leagues,
                "current_name_ko": row.current_name_ko,
                "current_short_name_ko": row.current_short_name_ko,
                "method": method,
                "matched_name": matched,
                "name_ko": name_ko,
                "short_name_ko": short_ko,
                "current_quality_bad": str(quality_bad(row.current_name_ko, row.current_short_name_ko)),
            }
        )

    for path, fieldnames, data in (
        (
            Path(args.output),
            ["external_id", "eng_name", "name_ko", "short_name_ko"],
            out_rows,
        ),
        (
            Path(args.audit_output),
            [
                "external_id",
                "player_id",
                "name",
                "firstname",
                "lastname",
                "full_name",
                "nationality",
                "teams",
                "team_countries",
                "leagues",
                "current_name_ko",
                "current_short_name_ko",
                "method",
                "matched_name",
                "name_ko",
                "short_name_ko",
                "current_quality_bad",
            ],
            audit_rows,
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    counts: dict[str, int] = {}
    for row in audit_rows:
        method = str(row["method"])
        counts[method] = counts.get(method, 0) + 1
    print(json.dumps({"rows": len(out_rows), "methods": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
