from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


OUTPUT = Path("seeds/player_translation_epl_2025.csv")
PREVIOUS_TRANSLATIONS = Path("_Translate__202605182259.csv")

PLAYER_QUERY = text(
    """
    SELECT DISTINCT
        p.external_id,
        p.name,
        p.firstname,
        p.lastname,
        t.name AS team,
        pt.name_ko,
        pt.short_name_ko,
        COALESCE(pss.minutes, 0) AS minutes,
        COALESCE(pss.appearances, 0) AS appearances
    FROM player p
    JOIN team t ON t.id = p.current_team_id
    JOIN team_season ts ON ts.team_id = t.id
    JOIN league l ON l.id = ts.league_id
    LEFT JOIN player_translation pt ON pt.player_id = p.id
    LEFT JOIN player_season_stat pss
      ON pss.player_id = p.id
     AND pss.team_id = t.id
     AND pss.league_id = l.id
     AND pss.season_year = ts.season_year
    WHERE l.external_id = 39
      AND ts.season_year = 2025
    ORDER BY t.name, p.name, p.external_id
    """
)

# Search-verified/common Korean football media spellings override the old CSV.
OVERRIDES: dict[int, tuple[str, str]] = {
    # Arsenal
    1460: ("부카요 사카", "사카"),
    19959: ("벤 화이트", "화이트"),
    30407: ("크리스티안 뇌르고르", "뇌르고르"),
    333682: ("크리스티안 모스케라", "모스케라"),
    2937: ("데클런 라이스", "라이스"),
    19465: ("다비드 라야", "라야"),
    313236: ("에단 은와네리", "은와네리"),
    41725: ("파비우 비에이라", "비에이라"),
    643: ("가브리엘 제주스", "제주스"),
    22224: ("가브리에우 마갈량이스", "마갈량이스"),
    127769: ("가브리엘 마르티넬리", "마르티넬리"),
    61431: ("야쿠프 키비오르", "키비오르"),
    38746: ("위리엔 팀버르", "팀버르"),
    978: ("카이 하베르츠", "하베르츠"),
    2273: ("케파 아리사발라가", "케파"),
    1946: ("레안드로 트로사르", "트로사르"),
    442044: ("맥스 다우먼", "다우먼"),
    313245: ("마일스 루이스스켈리", "루이스스켈리"),
    37127: ("마르틴 외데고르", "외데고르"),
    47315: ("마르틴 수비멘디", "수비멘디"),
    47311: ("미켈 메리노", "메리노"),
    127817: ("피에로 인카피에", "인카피에"),
    157052: ("리카르도 칼라피오리", "칼라피오리"),
    18979: ("빅토르 요케레스", "요케레스"),
    22090: ("윌리엄 살리바", "살리바"),
    # Aston Villa
    162714: ("아마두 오나나", "오나나"),
    1904: ("부바카르 카마라", "카마라"),
    249: ("도니얼 말런", "말런"),
    47522: ("더글라스 루이스", "루이스"),
    158378: ("엔소 바레네체아", "바레네체아"),
    19071: ("에밀리아노 부엔디아", "부엔디아"),
    137303: ("에반 게상", "게상"),
    19354: ("에즈리 콘사", "콘사"),
    19599: ("에밀리아노 마르티네스", "마르티네스"),
    19035: ("하비 엘리엇", "엘리엇"),
    138816: ("이안 마트센", "마트센"),
    19191: ("존 맥긴", "맥긴"),
    18: ("제이든 산초", "산초"),
    983: ("레온 베일리", "베일리"),
    2724: ("뤼카 디뉴", "디뉴"),
    19298: ("매티 캐시", "캐시"),
    19170: ("모건 로저스", "로저스"),
    19366: ("올리 왓킨스", "왓킨스"),
    46815: ("파우 토레스", "토레스"),
    2287: ("로스 바클리", "바클리"),
    19194: ("태미 에이브러햄", "에이브러햄"),
    19179: ("타이론 밍스", "밍스"),
    889: ("빅토르 린델뢰프", "린델뢰프"),
    2926: ("유리 틸레만스", "틸레만스"),
    # Bournemouth
    129682: ("아민 아들리", "아들리"),
    304853: ("알렉스 스콧", "스콧"),
    18869: ("애덤 스미스", "스미스"),
    162267: ("아드리앵 트뤼페르", "트뤼페르"),
    330437: ("알렉스 히메네스", "히메네스"),
    22136: ("바포데 디아키테", "디아키테"),
    402432: ("벤 윈터번", "윈터번"),
    18870: ("데이비드 브룩스", "브룩스"),
    118307: ("조르제 페트로비치", "페트로비치"),
    368030: ("엘리 주니어 크루피", "크루피"),
    47499: ("에네스 위날", "위날"),
    152856: ("에바니우송", "에바니우송"),
    18932: ("프레이저 포스터", "포스터"),
    31057: ("하메드 트라오레", "트라오레"),
    161671: ("일리야 자바르니", "자바르니"),
    51051: ("훌리안 아라우호", "아라우호"),
    792: ("저스틴 클라위버르트", "클라위버르트"),
    18872: ("루이스 쿡", "쿡"),
    6610: ("마르코스 세네시", "세네시"),
    19245: ("마커스 태버니어", "태버니어"),
    2734: ("필립 빌링", "빌링"),
    1125: ("라이언 크리스티", "크리스티"),
    84082: ("로맹 페브르", "페브르"),
    1150: ("타일러 애덤스", "애덤스"),
    # Brentford / Brighton / Burnley
    281: ("퀴빈 켈러허", "켈러허"),
    196156: ("이고르 티아구", "티아구"),
    342022: ("마이클 카요데", "카요데"),
    19495: ("네이선 콜린스", "콜린스"),
    178077: ("케빈 샤데", "샤데"),
    292: ("조던 헨더슨", "헨더슨"),
    393193: ("케이 푸로", "푸로"),
    129058: ("바르트 페르브뤼헌", "페르브뤼헌"),
    328225: ("브라얀 그루다", "그루다"),
    18960: ("제이슨 스틸", "스틸"),
    162007: ("막심 더카이퍼", "더카이퍼"),
    92993: ("마츠 비퍼", "비퍼"),
    138815: ("타리크 램프티", "램프티"),
    1361: ("페르디 카디올루", "카디올루"),
    38695: ("얀 폴 판헤케", "판헤케"),
    18963: ("루이스 덩크", "덩크"),
    18886: ("마르틴 두브라프카", "두브라프카"),
    627: ("카일 워커", "워커"),
    179400: ("막심 에스테브", "에스테브"),
    22: ("야콥 브룬 라르센", "브룬 라르센"),
    # Chelsea / Palace / Everton / Fulham
    422780: ("아론 안셀미노", "안셀미노"),
    341642: ("요렐 하토", "하토"),
    152953: ("리바이 콜윌", "콜윌"),
    161948: ("리암 델랍", "델랍"),
    276184: ("마마두 사르", "사르"),
    334037: ("타이릭 조지", "조지"),
    5996: ("엔소 페르난데스", "페르난데스"),
    116117: ("모이세스 카이세도", "카이세도"),
    19720: ("트레보 찰로바", "찰로바"),
    18959: ("로베르트 산체스", "산체스"),
    19088: ("딘 헨더슨", "헨더슨"),
    288102: ("애덤 워튼", "워튼"),
    182201: ("타이릭 미첼", "미첼"),
    25927: ("장필리프 마테타", "마테타"),
    18862: ("나다니엘 클라인", "클라인"),
    20995: ("막상스 라크루아", "라크루아"),
    126949: ("크리스 리처즈", "리처즈"),
    431921: ("아담 아즈누", "아즈누"),
    2932: ("조던 픽포드", "픽포드"),
    895: ("제임스 가너", "가너"),
    2936: ("제임스 타코우스키", "타코우스키"),
    270139: ("제이크 오브라이언", "오브라이언"),
    2165: ("비탈리 미콜렌코", "미콜렌코"),
    18592: ("일리만 은디아예", "은디아예"),
    148099: ("키어넌 듀스버리홀", "듀스버리홀"),
    138417: ("네이선 패터슨", "패터슨"),
    82855: ("톰 킹", "킹"),
    1438: ("베른트 레노", "레노"),
    19549: ("앤토니 로빈슨", "로빈슨"),
    436443: ("요나 쿠시-아사레", "쿠시-아사레"),
    2729: ("요아킴 안데르센", "안데르센"),
    1934: ("산데르 베르게", "베르게"),
    19366: ("올리 왓킨스", "왓킨스"),
    19221: ("해리 윌슨", "윌슨"),
    19025: ("톰 케어니", "케어니"),
    # Leeds / Liverpool
    2279: ("에단 암파두", "암파두"),
    64003: ("파스칼 스트라위크", "스트라위크"),
    19321: ("조 로든", "로든"),
    19201: ("제이든 보글", "보글"),
    19128: ("잭 해리슨", "해리슨"),
    19461: ("루카스 은메차", "은메차"),
    18766: ("도미닉 칼버트르윈", "칼버트르윈"),
    47969: ("가브리엘 구드문드손", "구드문드손"),
    289: ("앤디 로버트슨", "로버트슨"),
    314661: ("제이든 댄스", "댄스"),
    290: ("버질 반 다이크", "반 다이크"),
    1096: ("도미니크 소보슬러이", "소보슬러이"),
    1145: ("이브라히마 코나테", "코나테"),
    542: ("라이언 흐라벤베르흐", "흐라벤베르흐"),
    247: ("코디 각포", "각포"),
    # Manchester City / United
    5: ("마누엘 아칸지", "아칸지"),
    1622: ("잔루이지 돈나룸마", "돈나룸마"),
    1100: ("엘링 홀란", "홀란"),
    636: ("베르나르두 실바", "베르나르두"),
    41621: ("마테우스 누네스", "누네스"),
    891: ("루크 쇼", "쇼"),
    50132: ("알타이 바이은드르", "바이은드르"),
    402329: ("에이든 헤븐", "헤븐"),
    115589: ("벤야민 세슈코", "세슈코"),
    1485: ("브루노 페르난데스", "브루노"),
    162511: ("센느 라멘스", "라멘스"),
    886: ("디오구 달로트", "달로트"),
    19220: ("메이슨 마운트", "마운트"),
    328101: ("타일러 프레드릭슨", "프레드릭슨"),
    284400: ("토비 콜리어", "콜리어"),
    # Newcastle / Nottingham / Sunderland / Tottenham / West Ham / Wolves
    169: ("키어런 트리피어", "트리피어"),
    284492: ("루이스 홀", "홀"),
    18941: ("맷 타겟", "타겟"),
    163189: ("말릭 티아우", "티아우"),
    2919: ("마츠 셀스", "셀스"),
    2817: ("니콜라 밀렌코비치", "밀렌코비치"),
    138908: ("엘리엇 앤더슨", "앤더슨"),
    138780: ("네코 윌리엄스", "윌리엄스"),
    18746: ("모건 깁스화이트", "깁스화이트"),
    6056: ("니콜라스 도밍게스", "도밍게스"),
    2771: ("올라 아이나", "아이나"),
    194536: ("로빈 뢰프스", "뢰프스"),
    119121: ("트라이 흄", "흄"),
    1464: ("그라니트 자카", "자카"),
    365331: ("노아 사디키", "사디키"),
    6168: ("오마르 알데레테", "알데레테"),
    20638: ("엔조 르 페", "르 페"),
    290545: ("젠슨 실트", "실트"),
    554280: ("제이든 티 비", "티 비"),
    37143: ("루트샤렐 헤이르트라위다", "헤이르트라위다"),
    31354: ("굴리엘모 비카리오", "비카리오"),
    328089: ("아치 그레이", "그레이"),
    152849: ("미키 판더펜", "판더펜"),
    47519: ("페드로 포로", "포로"),
    380690: ("마이키 무어", "무어"),
    270510: ("마티스 텔", "텔"),
    409303: ("엘 하지 말릭 디우프", "디우프"),
    171: ("카일 워커피터스", "워커피터스"),
    18744: ("맥스 킬먼", "킬먼"),
    336585: ("마테우스 페르난데스", "페르난데스"),
    283272: ("알피 폰드", "폰드"),
    195103: ("주앙 고메스", "고메스"),
    265784: ("안드레", "안드레"),
    135068: ("에마뉘엘 아그바두", "아그바두"),
    1590: ("조제 사", "사"),
    7722: ("사샤 칼라이지치", "칼라이지치"),
    18742: ("맷 도허티", "도허티"),
    20665: ("장리크네르 벨가르드", "벨가르드"),
    24888: ("황희찬", "황희찬"),
    22149: ("이브라힘 상가레", "상가레"),
    282770: ("호드리구 고메스", "고메스"),
    297187: ("레오 옐데", "옐데"),
    3080: ("마셜 무네치", "무네치"),
    389315: ("조슈아 킹", "킹"),
    392270: ("마르크 기우", "기우"),
    41606: ("토티 고메스", "토티"),
}

TOKEN_MAP = {
    "adam": "애덤",
    "alex": "알렉스",
    "alexei": "알렉세이",
    "amine": "아민",
    "andres": "안드레스",
    "andre": "앙드레",
    "ben": "벤",
    "benjamin": "벤저민",
    "bradley": "브래들리",
    "brando": "브랜도",
    "christian": "크리스티안",
    "cristhian": "크리스티안",
    "daniel": "대니얼",
    "david": "데이비드",
    "declan": "데클런",
    "dominic": "도미닉",
    "douglas": "더글라스",
    "edward": "에드워드",
    "emiliano": "에밀리아노",
    "enzo": "엔소",
    "ethan": "에단",
    "fabio": "파비우",
    "fraser": "프레이저",
    "gabriel": "가브리엘",
    "harvey": "하비",
    "ian": "이안",
    "igor": "이고르",
    "jack": "잭",
    "jaden": "제이든",
    "jadon": "제이든",
    "jakub": "야쿠프",
    "james": "제임스",
    "john": "존",
    "jordan": "조던",
    "joshua": "조슈아",
    "julian": "훌리안",
    "justin": "저스틴",
    "kai": "카이",
    "leandro": "레안드로",
    "leon": "레온",
    "lewis": "루이스",
    "lucas": "뤼카",
    "marco": "마르코",
    "marcos": "마르코스",
    "marcus": "마커스",
    "martin": "마르틴",
    "martinelli": "마르티넬리",
    "matheus": "마테우스",
    "matthew": "매튜",
    "max": "맥스",
    "michael": "마이클",
    "mikel": "미켈",
    "morgan": "모건",
    "nathan": "네이선",
    "oliver": "올리버",
    "pau": "파우",
    "pedro": "페드로",
    "philip": "필립",
    "riccardo": "리카르도",
    "ross": "로스",
    "ryan": "라이언",
    "sam": "샘",
    "sander": "산데르",
    "samuel": "새뮤얼",
    "tammy": "태미",
    "theodore": "시어도어",
    "thomas": "토마스",
    "tommy": "토미",
    "tyler": "타일러",
    "tyrone": "타이론",
    "victor": "빅토르",
    "viktor": "빅토르",
    "william": "윌리엄",
    "youri": "유리",
    "zach": "잭",
}

SURNAME_MAP = {
    "adams": "애덤스",
    "andersen": "안데르센",
    "anderson": "앤더슨",
    "annous": "아누스",
    "araujo": "아라우호",
    "bailey": "베일리",
    "barkley": "바클리",
    "berge": "베르게",
    "billing": "빌링",
    "bogle": "보글",
    "brooks": "브룩스",
    "cash": "캐시",
    "christie": "크리스티",
    "collins": "콜린스",
    "cook": "쿡",
    "digne": "디뉴",
    "donnarumma": "돈나룸마",
    "dunk": "덩크",
    "elliott": "엘리엇",
    "fernandes": "페르난데스",
    "gakpo": "각포",
    "garner": "가너",
    "gibbs-white": "깁스화이트",
    "gomes": "고메스",
    "henderson": "헨더슨",
    "hume": "흄",
    "jesus": "제주스",
    "kelleher": "켈러허",
    "konsa": "콘사",
    "konate": "코나테",
    "lacroux": "라크루아",
    "lacroix": "라크루아",
    "leno": "레노",
    "martinez": "마르티네스",
    "mings": "밍스",
    "mitchell": "미첼",
    "nunes": "누네스",
    "onana": "오나나",
    "pickford": "픽포드",
    "rice": "라이스",
    "richards": "리처즈",
    "rogers": "로저스",
    "saka": "사카",
    "saliba": "살리바",
    "sanchez": "산체스",
    "sancho": "산초",
    "scott": "스콧",
    "senesi": "세네시",
    "shaw": "쇼",
    "silva": "실바",
    "smith": "스미스",
    "struijk": "스트라위크",
    "szoboszlai": "소보슬러이",
    "tarkowski": "타코우스키",
    "tielemans": "틸레만스",
    "torres": "토레스",
    "van dijk": "반 다이크",
    "vicario": "비카리오",
    "walker": "워커",
    "watkins": "왓킨스",
    "white": "화이트",
    "wilson": "윌슨",
    "williams": "윌리엄스",
    "xhaka": "자카",
}

INITIAL_PREFIXES = {
    "A": "에이",
    "B": "비",
    "C": "시",
    "D": "디",
    "E": "이",
    "F": "에프",
    "G": "지",
    "H": "에이치",
    "I": "아이",
    "J": "제이",
    "K": "케이",
    "L": "엘",
    "M": "엠",
    "N": "엔",
    "O": "오",
    "P": "피",
    "R": "알",
    "S": "에스",
    "T": "티",
    "V": "브이",
}


def normalize(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("Đ", "Dj").replace("đ", "dj").replace("Ø", "O").replace("ø", "o")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("’", "'").replace("`", "'")
    return re.sub(r"\s+", " ", text).strip()


def key(text: str) -> str:
    return normalize(text).lower().replace(".", "").strip()


def split_player_name(row: dict) -> tuple[str, str]:
    api_name = normalize(row["name"] or "")
    firstname = normalize(row["firstname"] or "")
    lastname = normalize(row["lastname"] or "")

    if re.match(r"^[A-Z]\.\s+", api_name) and firstname and lastname:
        first = firstname.split()[0]
        short = compact_lastname(lastname)
        return f"{first} {short}".strip(), short

    if api_name:
        parts = api_name.split()
        if len(parts) == 1:
            return api_name, api_name
        return api_name, compact_lastname(" ".join(parts[1:]))

    if firstname or lastname:
        first = firstname.split()[0] if firstname else ""
        short = compact_lastname(lastname)
        return f"{first} {short}".strip(), short
    return "", ""


def compact_lastname(lastname: str) -> str:
    cleaned = normalize(lastname)
    particles = {
        "de",
        "da",
        "dos",
        "do",
        "del",
        "van",
        "von",
        "la",
        "le",
        "bin",
    }
    parts = cleaned.split()
    if not parts:
        return ""
    if len(parts) >= 2 and parts[0].lower() in {"van", "de", "le"}:
        return " ".join(parts[:2])
    parts = [part for part in parts if part.lower() not in particles]
    return parts[0] if parts else cleaned


def transliterate_token(token: str) -> str:
    token = key(token)
    token = token.replace("'", "")
    if not token:
        return ""
    if token in TOKEN_MAP:
        return TOKEN_MAP[token]
    if token in SURNAME_MAP:
        return SURNAME_MAP[token]
    if "-" in token:
        return "-".join(transliterate_token(part) for part in token.split("-") if part)

    replacements = [
        ("x", "크스"),
        ("j", "지"),
        ("ch", "치"),
        ("sh", "시"),
        ("th", "스"),
        ("ph", "프"),
        ("ck", "크"),
        ("qu", "쿠"),
        ("oo", "우"),
        ("ou", "우"),
        ("ay", "에이"),
        ("ey", "이"),
        ("son", "슨"),
        ("sen", "센"),
        ("ton", "턴"),
        ("ford", "포드"),
        ("field", "필드"),
        ("wood", "우드"),
        ("ham", "햄"),
        ("berg", "베르그"),
        ("man", "먼"),
        ("well", "웰"),
        ("ley", "리"),
    ]
    for src, dst in replacements:
        if token.endswith(src):
            stem = token[: -len(src)]
            return transliterate_token(stem) + dst if stem else dst

    rough = token
    rough = rough.replace("a", "아")
    rough = rough.replace("e", "에")
    rough = rough.replace("i", "이")
    rough = rough.replace("o", "오")
    rough = rough.replace("u", "우")
    rough = rough.replace("b", "브")
    rough = rough.replace("c", "크")
    rough = rough.replace("d", "드")
    rough = rough.replace("f", "프")
    rough = rough.replace("g", "그")
    rough = rough.replace("h", "흐")
    rough = rough.replace("k", "크")
    rough = rough.replace("l", "르")
    rough = rough.replace("m", "므")
    rough = rough.replace("n", "느")
    rough = rough.replace("p", "프")
    rough = rough.replace("r", "르")
    rough = rough.replace("s", "스")
    rough = rough.replace("t", "트")
    rough = rough.replace("v", "브")
    rough = rough.replace("w", "우")
    rough = rough.replace("y", "이")
    rough = rough.replace("z", "즈")
    return re.sub(r"(으|흐|느|므|르)$", "", rough)


def transliterate_phrase(phrase: str) -> str:
    words = normalize(phrase).split()
    return " ".join(transliterate_token(word) for word in words if transliterate_token(word))


def load_previous() -> dict[int, tuple[str, str]]:
    if not PREVIOUS_TRANSLATIONS.exists():
        return {}
    result: dict[int, tuple[str, str]] = {}
    with PREVIOUS_TRANSLATIONS.open("r", encoding="utf-8-sig", newline="") as fp:
        for row in csv.DictReader(fp):
            try:
                player_id = int(row["player_id"])
            except (KeyError, ValueError):
                continue
            name_ko = (row.get("kor_name") or "").strip()
            short_name_ko = (row.get("kor_short_name") or "").strip()
            if name_ko and short_name_ko:
                result[player_id] = (name_ko, short_name_ko)
    return result


def looks_initial_based(row: dict, value: str | None) -> bool:
    if not value:
        return True
    if re.match(r"^[가-힣]{1,3}\.\s", value):
        return True
    first_token = value.split()[0] if value.split() else ""
    if first_token in set(INITIAL_PREFIXES.values()):
        return True
    api_name = normalize(row["name"] or "")
    match = re.match(r"^([A-Z])\.\s+", api_name)
    if not match:
        return False
    prefix = INITIAL_PREFIXES.get(match.group(1))
    if not prefix:
        return False
    return value.startswith(prefix + " ") or value.startswith(prefix + ".")


def choose_translation(row: dict, previous: dict[int, tuple[str, str]]) -> tuple[str, str, str]:
    player_id = int(row["external_id"])
    if player_id in OVERRIDES:
        name_ko, short_name_ko = OVERRIDES[player_id]
        return name_ko, short_name_ko, "curated"

    previous_value = previous.get(player_id)
    if previous_value and not looks_initial_based(row, previous_value[0]):
        return previous_value[0], previous_value[1], "previous_csv"

    full_name, short_name = split_player_name(row)
    name_ko = transliterate_phrase(full_name)
    short_name_ko = transliterate_phrase(short_name) or name_ko
    if not name_ko:
        name_ko = normalize(row["name"] or f"Player {player_id}")
        short_name_ko = name_ko
    return name_ko, short_name_ko, "generated"


def main() -> None:
    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)
    previous = load_previous()

    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(PLAYER_QUERY).mappings()]

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "external_id",
                "eng_name",
                "team",
                "name_ko",
                "short_name_ko",
                "source",
            ],
        )
        writer.writeheader()
        for row in rows:
            name_ko, short_name_ko, source = choose_translation(row, previous)
            if source == "generated":
                continue
            writer.writerow(
                {
                    "external_id": row["external_id"],
                    "eng_name": normalize(row["name"] or ""),
                    "team": row["team"],
                    "name_ko": name_ko,
                    "short_name_ko": short_name_ko,
                    "source": source,
                }
            )

    counts: dict[str, int] = {}
    with OUTPUT.open("r", encoding="utf-8", newline="") as fp:
        for row in csv.DictReader(fp):
            counts[row["source"]] = counts.get(row["source"], 0) + 1
    print({"output": str(OUTPUT), "rows": len(rows), "sources": counts})


if __name__ == "__main__":
    main()
