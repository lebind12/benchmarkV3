from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import get_settings


SPARQL_URL = "https://query.wikidata.org/sparql"
DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"

KNOWN_KO: dict[str, str] = {
    "Aaron Ramsdale": "애런 램스데일",
    "Abdoulaye Doucouré": "압둘라예 두쿠레",
    "Adam Lallana": "애덤 랄라나",
    "Aleksandr Golovin": "알렉산드르 골로빈",
    "Alexander Djiku": "알렉산데르 지쿠",
    "Alex Meret": "알렉스 메렛",
    "Alphonso Davies": "알폰소 데이비스",
    "Alphonse Areola": "알퐁스 아레올라",
    "André Onana": "앙드레 오나나",
    "Andreas Christensen": "안드레아스 크리스텐센",
    "Andrea Cambiaso": "안드레아 캄비아소",
    "Anastasios Bakasetas": "아나스타시오스 바카세타스",
    "Armando Obispo": "아르만도 오비스포",
    "Ashley Barnes": "애슐리 반스",
    "Benjamin Davies": "벤 데이비스",
    "Benjamin Lecomte": "벤자민 르콩트",
    "Benoît Badiashile": "브누아 바디아실",
    "Brenden Aaronson": "브렌든 에런슨",
    "Callum Hudson-Odoi": "칼럼 허드슨오도이",
    "Calvin Ramsay": "캘빈 램지",
    "Carlos Alcaraz": "카를로스 알카라스",
    "Christos Mandas": "흐리스토스 만다스",
    "Cristian Romero": "크리스티안 로메로",
    "Crysencio Summerville": "크리센시오 서머빌",
    "Daniel James": "대니얼 제임스",
    "Daniel Neil": "댄 닐",
    "Diego Coppola": "디에고 코폴라",
    "Diego León": "디에고 레온",
    "Djed Spence": "제드 스펜스",
    "Dwight McNeil": "드와이트 맥닐",
    "Emil Krafth": "에밀 크라프트",
    "Ethan Pinnock": "에단 피녹",
    "Fabian Schär": "파비안 셰어",
    "Gonçalo Ramos": "곤살루 하무스",
    "Joelinton": "조엘린통",
    "Jonathan David": "조너선 데이비드",
    "Jules Koundé": "쥘 쿤데",
    "Kiernan Dewsbury-Hall": "키어넌 듀스버리홀",
    "Leandro Barreiro": "레안드로 바레이루",
    "Marco Asensio": "마르코 아센시오",
    "Mason Mount": "메이슨 마운트",
    "Maxwel Cornet": "막스웰 코르네",
    "Nicolas Jackson": "니콜라 잭슨",
    "Patrik Schick": "파트리크 시크",
    "Phil Foden": "필 포든",
    "Raheem Sterling": "라힘 스털링",
    "Scott McTominay": "스콧 맥토미니",
    "Timo Werner": "티모 베르너",
    "Wataru Endo": "엔도 와타루",
}

PARTICLES = {
    "da",
    "de",
    "del",
    "della",
    "di",
    "dos",
    "du",
    "van",
    "von",
}

WORD_EXCEPTIONS: dict[str, str] = {
    "alex": "알렉스",
    "alessandro": "알레산드로",
    "alexander": "알렉산더",
    "aleksandr": "알렉산드르",
    "andreas": "안드레아스",
    "antonio": "안토니오",
    "benjamin": "벤자민",
    "carlos": "카를로스",
    "daniel": "다니엘",
    "david": "다비드",
    "denis": "데니스",
    "diego": "디에고",
    "emil": "에밀",
    "fabian": "파비안",
    "federico": "페데리코",
    "francisco": "프란시스코",
    "gabriel": "가브리엘",
    "joao": "주앙",
    "jonathan": "조너선",
    "jose": "호세",
    "kevin": "케빈",
    "leon": "레온",
    "luca": "루카",
    "lucas": "루카스",
    "marco": "마르코",
    "marko": "마르코",
    "martin": "마르틴",
    "mateo": "마테오",
    "michael": "마이클",
    "mohamed": "모하메드",
    "mohammed": "모하메드",
    "nicolas": "니콜라",
    "paulo": "파울루",
    "pedro": "페드로",
    "robert": "로베르트",
    "samuel": "사무엘",
    "stefan": "스테판",
    "thomas": "토마스",
    "victor": "빅토르",
}

VOWELS = {
    "a": "아",
    "e": "에",
    "i": "이",
    "o": "오",
    "u": "우",
    "y": "이",
}

CHUNKS = [
    ("sch", "슈"),
    ("sh", "슈"),
    ("ch", "치"),
    ("ph", "프"),
    ("th", "트"),
    ("kh", "크"),
    ("gh", "그"),
    ("ll", "야"),
    ("ck", "크"),
    ("qu", "쿠"),
    ("ou", "우"),
    ("au", "아우"),
    ("ai", "아이"),
    ("ay", "아이"),
    ("ei", "아이"),
    ("ey", "이"),
    ("ie", "이"),
    ("ea", "이"),
    ("oo", "우"),
]

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


def strip_marks(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("Ŀ", "L")).strip()


def name_candidates(row: dict[str, str]) -> list[str]:
    full = clean_name(row.get("full_name") or row.get("eng_name") or "")
    eng = clean_name(row.get("eng_name") or "")
    candidates: list[str] = []
    for value in (full, eng):
        if value and not re.fullmatch(r"[A-Z]\.\s+\S+", value):
            candidates.append(value)
    parts = [p for p in re.split(r"\s+", full) if p]
    if len(parts) >= 2 and not re.fullmatch(r"[A-Z]\.", parts[0]):
        candidates.append(f"{parts[0]} {parts[-1]}")
    if len(parts) >= 3 and parts[-2].lower() in PARTICLES:
        candidates.append(f"{parts[0]} {parts[-2]} {parts[-1]}")
    return list(dict.fromkeys(candidates))


def short_name(name_ko: str) -> str:
    tokens = [token for token in name_ko.split() if token]
    return tokens[-1] if len(tokens) > 1 else name_ko


def sparql_labels(candidates: list[str], *, batch_size: int = 35) -> dict[str, str]:
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
        url = f"{SPARQL_URL}?{urlencode({'format': 'json', 'query': query})}"
        req = Request(url, headers={"User-Agent": "benchmark-backfill/0.1"})
        data = None
        for attempt in range(4):
            try:
                with urlopen(req, timeout=45) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                if attempt == 3:
                    data = {"results": {"bindings": []}}
                else:
                    time.sleep(2 * (attempt + 1))
                    continue
        for item in data.get("results", {}).get("bindings", []):
            labels[item["en"]["value"]] = item["ko"]["value"]
        time.sleep(0.6)
    return labels


def roman_word_to_ko(word: str) -> str:
    raw = clean_name(word)
    if not raw:
        return ""
    lowered = strip_marks(raw).lower().replace("'", "")
    lowered = re.sub(r"[^a-z-]", "", lowered)
    if not lowered:
        return raw
    if lowered in WORD_EXCEPTIONS:
        return WORD_EXCEPTIONS[lowered]
    parts = lowered.split("-")
    if len(parts) > 1:
        return "-".join(roman_word_to_ko(part) for part in parts)
    out = ""
    i = 0
    while i < len(lowered):
        if lowered[i] in VOWELS:
            out += VOWELS[lowered[i]]
            i += 1
            continue
        matched = False
        for src, dst in CHUNKS:
            if lowered.startswith(src, i):
                out += dst
                i += len(src)
                matched = True
                break
        if matched:
            continue
        out += CONS.get(lowered[i], lowered[i])
        i += 1
    out = re.sub(r"으([아에이오우])", r"\1", out)
    out = out.replace("르아", "라").replace("르에", "레").replace("르이", "리")
    out = out.replace("르오", "로").replace("르우", "루")
    out = out.replace("크아", "카").replace("크에", "케").replace("크이", "키")
    out = out.replace("크오", "코").replace("크우", "쿠")
    out = out.replace("트아", "타").replace("트에", "테").replace("트이", "티")
    out = out.replace("트오", "토").replace("트우", "투")
    out = out.replace("드아", "다").replace("드에", "데").replace("드이", "디")
    out = out.replace("드오", "도").replace("드우", "두")
    out = out.replace("브아", "바").replace("브에", "베").replace("브이", "비")
    out = out.replace("브오", "보").replace("브우", "부")
    out = out.replace("프아", "파").replace("프에", "페").replace("프이", "피")
    out = out.replace("프오", "포").replace("프우", "푸")
    out = out.replace("스아", "사").replace("스에", "세").replace("스이", "시")
    out = out.replace("스오", "소").replace("스우", "수")
    out = out.replace("그아", "가").replace("그에", "게").replace("그이", "기")
    out = out.replace("그오", "고").replace("그우", "구")
    out = out.replace("느아", "나").replace("느에", "네").replace("느이", "니")
    out = out.replace("느오", "노").replace("느우", "누")
    out = out.replace("므아", "마").replace("므에", "메").replace("므이", "미")
    out = out.replace("므오", "모").replace("므우", "무")
    return out


def roman_name_to_ko(row: dict[str, str]) -> str:
    name = clean_name(row.get("full_name") or row.get("eng_name") or "")
    parts = [part for part in re.split(r"\s+", name) if part and part.lower() not in PARTICLES]
    if len(parts) > 3:
        parts = [parts[0], parts[-1]]
    return " ".join(roman_word_to_ko(part) for part in parts)


async def openai_transliterate(
    rows: list[dict[str, str]],
    *,
    model: str,
    batch_size: int = 40,
) -> dict[str, tuple[str, str]]:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required for --openai-fallback") from exc

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    translations: dict[str, tuple[str, str]] = {}
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        payload = [
            {
                "external_id": row["external_id"],
                "eng_name": row.get("eng_name", ""),
                "full_name": row.get("full_name", ""),
                "nationality": row.get("context", ""),
                "team": row.get("short_context", ""),
            }
            for row in batch
        ]
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 축구 선수 영문 이름을 한국어 스포츠 기사에서 읽기 좋은 "
                    "한글 표기로 음역하는 편집자입니다. 검색 근거가 없는 fallback "
                    "대상만 들어옵니다. 유명 선수 표기를 새로 추정하지 말고, "
                    "영문 full_name을 자연스럽게 음역하세요. 응답은 JSON 객체만 "
                    "출력하고, 키 rows는 배열입니다."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "rules": [
                            "입력 rows와 같은 순서/개수로 반환",
                            "각 row는 external_id, name_ko, short_name_ko 포함",
                            "short_name_ko는 성 또는 마지막 이름 기준",
                            "이니셜만 있는 eng_name보다 full_name 우선",
                            "팀명/국적은 동명이인 식별 참고용",
                        ],
                        "rows": payload,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=3500,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        for item in data.get("rows", []):
            external_id = str(item.get("external_id", "")).strip()
            name_ko = str(item.get("name_ko", "")).strip()
            short_name_ko = str(item.get("short_name_ko", "")).strip()
            if external_id and name_ko and short_name_ko:
                translations[external_id] = (name_ko, short_name_ko)
        time.sleep(0.2)
    return translations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--openai-fallback", action="store_true")
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input_csv).open(encoding="utf-8")))
    all_candidates = []
    row_candidates: dict[str, list[str]] = {}
    for row in rows:
        candidates = name_candidates(row)
        row_candidates[row["external_id"]] = candidates
        all_candidates.extend(candidates)
    all_candidates = list(dict.fromkeys(all_candidates))
    wd_labels = sparql_labels(all_candidates)

    staged: list[tuple[dict[str, str], str, str, str, str]] = []
    fallback_rows: list[dict[str, str]] = []
    for row in rows:
        matched_name = ""
        name_ko = ""
        method = "phonetic-fallback"
        for candidate in row_candidates[row["external_id"]]:
            if candidate in KNOWN_KO:
                matched_name = candidate
                name_ko = KNOWN_KO[candidate]
                method = "known-ko"
                break
            if candidate in wd_labels:
                matched_name = candidate
                name_ko = wd_labels[candidate]
                method = "wikidata-ko-label"
                break
        if not name_ko:
            fallback_rows.append(row)
        staged.append((row, method, matched_name, name_ko, short_name(name_ko) if name_ko else ""))

    openai_fallbacks: dict[str, tuple[str, str]] = {}
    if args.openai_fallback and fallback_rows:
        openai_fallbacks = asyncio.run(
            openai_transliterate(fallback_rows, model=args.openai_model)
        )

    out_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for row, method, matched_name, name_ko, short_ko in staged:
        if not name_ko:
            if row["external_id"] in openai_fallbacks:
                name_ko, short_ko = openai_fallbacks[row["external_id"]]
                method = "phonetic-fallback-openai"
            else:
                name_ko = roman_name_to_ko(row)
                short_ko = short_name(name_ko)
        out_rows.append(
            {
                "external_id": row["external_id"],
                "eng_name": row["eng_name"],
                "name_ko": name_ko,
                "short_name_ko": short_ko,
            }
        )
        audit_rows.append(
            {
                "external_id": row["external_id"],
                "eng_name": row["eng_name"],
                "full_name": row.get("full_name", ""),
                "team": row.get("short_context", ""),
                "method": method,
                "matched_name": matched_name,
                "name_ko": name_ko,
                "short_name_ko": short_ko,
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
                "eng_name",
                "full_name",
                "team",
                "method",
                "matched_name",
                "name_ko",
                "short_name_ko",
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
        counts[row["method"]] = counts.get(row["method"], 0) + 1
    print({"rows": len(out_rows), "methods": counts, "output": args.output, "audit": args.audit_output})


if __name__ == "__main__":
    main()
