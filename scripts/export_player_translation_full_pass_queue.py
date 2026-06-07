from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import database_engine_kwargs, get_settings, normalize_database_url


FIELDNAMES = [
    "api_player_id",
    "api_name_raw",
    "firstname",
    "lastname",
    "nationality_raw",
    "birth_country_raw",
    "current_team_names",
    "current_league_names",
    "previous_name_ko",
    "previous_short_name_ko",
    "manual_override_name_ko",
    "manual_override_short_name_ko",
    "locked_common_name_ko",
    "known_aliases_ko",
    "evidence_ko_candidates",
    "evidence_source_summary",
    "popularity_tier",
    "nationality_ko_mapped",
    "birth_country_ko_mapped",
    "country_mapping_status",
]

SUPPLEMENTAL_FIELDS = [
    "manual_override_name_ko",
    "manual_override_short_name_ko",
    "locked_common_name_ko",
    "known_aliases_ko",
    "evidence_ko_candidates",
    "evidence_source_summary",
    "popularity_tier",
]

FOOTBALL_ASSOCIATION_COUNTRIES = {
    "England",
    "Scotland",
    "Wales",
    "Northern Ireland",
    "Northern-Ireland",
    "Republic of Ireland",
}

COUNTRY_KO = {
    "": "",
    "Albania": "알바니아",
    "Algeria": "알제리",
    "Argentina": "아르헨티나",
    "Armenia": "아르메니아",
    "Australia": "호주",
    "Austria": "오스트리아",
    "Azerbaijan": "아제르바이잔",
    "Belarus": "벨라루스",
    "Belgium": "벨기에",
    "Bosnia and Herzegovina": "보스니아 헤르체고비나",
    "Brazil": "브라질",
    "Bulgaria": "불가리아",
    "Cameroon": "카메룬",
    "Canada": "캐나다",
    "Colombia": "콜롬비아",
    "Costa Rica": "코스타리카",
    "Croatia": "크로아티아",
    "Czech Republic": "체코",
    "Czechia": "체코",
    "Denmark": "덴마크",
    "Ecuador": "에콰도르",
    "Egypt": "이집트",
    "England": "잉글랜드",
    "Estonia": "에스토니아",
    "Finland": "핀란드",
    "France": "프랑스",
    "Georgia": "조지아",
    "Germany": "독일",
    "Ghana": "가나",
    "Greece": "그리스",
    "Hungary": "헝가리",
    "Iceland": "아이슬란드",
    "Iran": "이란",
    "Iraq": "이라크",
    "Israel": "이스라엘",
    "Italy": "이탈리아",
    "Jamaica": "자메이카",
    "Japan": "일본",
    "Jordan": "요르단",
    "Kazakhstan": "카자흐스탄",
    "Korea Republic": "대한민국",
    "Kosovo": "코소보",
    "Lithuania": "리투아니아",
    "Mexico": "멕시코",
    "Morocco": "모로코",
    "Netherlands": "네덜란드",
    "New Zealand": "뉴질랜드",
    "Nigeria": "나이지리아",
    "North Macedonia": "북마케도니아",
    "Northern Ireland": "북아일랜드",
    "Norway": "노르웨이",
    "Panama": "파나마",
    "Paraguay": "파라과이",
    "Poland": "폴란드",
    "Portugal": "포르투갈",
    "Qatar": "카타르",
    "Republic of Ireland": "아일랜드",
    "Romania": "루마니아",
    "Russia": "러시아",
    "Saudi Arabia": "사우디아라비아",
    "Scotland": "스코틀랜드",
    "Senegal": "세네갈",
    "Serbia": "세르비아",
    "Slovakia": "슬로바키아",
    "Slovenia": "슬로베니아",
    "South Africa": "남아프리카공화국",
    "South Korea": "대한민국",
    "Spain": "스페인",
    "Sweden": "스웨덴",
    "Switzerland": "스위스",
    "Tunisia": "튀니지",
    "Turkey": "튀르키예",
    "Türkiye": "튀르키예",
    "USA": "미국",
    "Ukraine": "우크라이나",
    "Uruguay": "우루과이",
    "Wales": "웨일스",
}

COUNTRY_KO.update(
    {
        "Afghanistan": "아프가니스탄",
        "Andorra": "안도라",
        "Angola": "앙골라",
        "Antigua and Barbuda": "앤티가 바부다",
        "Antigua-And-Barbuda": "앤티가 바부다",
        "Aruba": "아루바",
        "Bahrain": "바레인",
        "Bangladesh": "방글라데시",
        "Barbados": "바베이도스",
        "Belize": "벨리즈",
        "Benin": "베냉",
        "Bermuda": "버뮤다",
        "Bhutan": "부탄",
        "Bolivia": "볼리비아",
        "Bosnia": "보스니아 헤르체고비나",
        "Botswana": "보츠와나",
        "British-Virgin-Islands": "영국령 버진아일랜드",
        "Burkina Faso": "부르키나파소",
        "Burkina-Faso": "부르키나파소",
        "Burundi": "부룬디",
        "Cambodia": "캄보디아",
        "Cape Verde": "카보베르데",
        "Cape-Verde-Islands": "카보베르데",
        "Cayman-Islands": "케이맨 제도",
        "Central African Republic": "중앙아프리카공화국",
        "Central-African-Republic": "중앙아프리카공화국",
        "Chad": "차드",
        "Chile": "칠레",
        "China": "중국",
        "Chinese-Taipei": "중화 타이베이",
        "Comoros": "코모로",
        "Congo": "콩고공화국",
        "Congo DR": "콩고민주공화국",
        "Congo-DR": "콩고민주공화국",
        "Costa-Rica": "코스타리카",
        "Crimea": "크림반도",
        "Cuba": "쿠바",
        "Curacao": "퀴라소",
        "Curaçao": "퀴라소",
        "Cyprus": "키프로스",
        "Czech-Republic": "체코",
        "Côte d'Ivoire": "코트디부아르",
        "Dominica": "도미니카",
        "Dominican Republic": "도미니카 공화국",
        "Dominican-Republic": "도미니카 공화국",
        "El Salvador": "엘살바도르",
        "El-Salvador": "엘살바도르",
        "Equatorial Guinea": "적도 기니",
        "Equatorial-Guinea": "적도 기니",
        "Eswatini": "에스와티니",
        "Ethiopia": "에티오피아",
        "Faroe Islands": "페로 제도",
        "Faroe-Islands": "페로 제도",
        "Fiji": "피지",
        "French Guiana": "프랑스령 기아나",
        "Gabon": "가봉",
        "Gambia": "감비아",
        "Gibraltar": "지브롤터",
        "Great Britain": "영국",
        "Grenada": "그레나다",
        "Guadeloupe": "과들루프",
        "Guam": "괌",
        "Guatemala": "과테말라",
        "Guinea": "기니",
        "Guinea-Bissau": "기니비사우",
        "Guyana": "가이아나",
        "Haiti": "아이티",
        "Honduras": "온두라스",
        "Hong-Kong": "홍콩",
        "India": "인도",
        "Indonesia": "인도네시아",
        "Ireland": "아일랜드",
        "Ivory Coast": "코트디부아르",
        "Ivory-Coast": "코트디부아르",
        "Jersey": "저지",
        "Kenya": "케냐",
        "Kuwait": "쿠웨이트",
        "Kyrgyzstan": "키르기스스탄",
        "Kyrgyz-Republic": "키르기스스탄",
        "Laos": "라오스",
        "Latvia": "라트비아",
        "Lebanon": "레바논",
        "Lesotho": "레소토",
        "Liberia": "라이베리아",
        "Libya": "리비아",
        "Liechtenstein": "리히텐슈타인",
        "Luxembourg": "룩셈부르크",
        "Macao": "마카오",
        "Macedonia": "북마케도니아",
        "Madagascar": "마다가스카르",
        "Malawi": "말라위",
        "Malaysia": "말레이시아",
        "Maldives": "몰디브",
        "Mali": "말리",
        "Malta": "몰타",
        "Martinique": "마르티니크",
        "Mauritania": "모리타니",
        "Mauritius": "모리셔스",
        "Moldova": "몰도바",
        "Monaco": "모나코",
        "Mongolia": "몽골",
        "Montenegro": "몬테네그로",
        "Montserrat": "몬트세랫",
        "Mozambique": "모잠비크",
        "Myanmar": "미얀마",
        "Namibia": "나미비아",
        "Nepal": "네팔",
        "New Caledonia": "뉴칼레도니아",
        "New-Zealand": "뉴질랜드",
        "Nicaragua": "니카라과",
        "Niger": "니제르",
        "North-Korea": "북한",
        "Northern-Ireland": "북아일랜드",
        "Oman": "오만",
        "Pakistan": "파키스탄",
        "Palestine": "팔레스타인",
        "Peru": "페루",
        "Philippines": "필리핀",
        "Puerto-Rico": "푸에르토리코",
        "Rwanda": "르완다",
        "San-Marino": "산마리노",
        "Saudi-Arabia": "사우디아라비아",
        "Sierra Leone": "시에라리온",
        "Singapore": "싱가포르",
        "Solomon-Islands": "솔로몬 제도",
        "Somalia": "소말리아",
        "South Sudan": "남수단",
        "South-Africa": "남아프리카공화국",
        "South-Korea": "대한민국",
        "Sri Lanka": "스리랑카",
        "St. Kitts and Nevis": "세인트키츠 네비스",
        "St. Lucia": "세인트루시아",
        "Saint-Vincent-and-the-Grenadin": "세인트빈센트 그레나딘",
        "Sudan": "수단",
        "Suriname": "수리남",
        "São Tomé e Príncipe": "상투메 프린시페",
        "Syria": "시리아",
        "Tajikistan": "타지키스탄",
        "Tanzania": "탄자니아",
        "Thailand": "태국",
        "Togo": "토고",
        "Trinidad and Tobago": "트리니다드 토바고",
        "Trinidad-And-Tobago": "트리니다드 토바고",
        "Turkmenistan": "투르크메니스탄",
        "Uganda": "우간다",
        "United Arab Emirates": "아랍에미리트",
        "United-Arab-Emirates": "아랍에미리트",
        "Uzbekistan": "우즈베키스탄",
        "Venezuela": "베네수엘라",
        "Vietnam": "베트남",
        "World": "세계",
        "Yemen": "예멘",
        "Yugoslavia": "유고슬라비아",
        "Zambia": "잠비아",
        "Zimbabwe": "짐바브웨",
    }
)

PLAYER_SQL = text(
    """
    SELECT
        p.external_id AS api_player_id,
        p.name AS api_name_raw,
        COALESCE(p.firstname, '') AS firstname,
        COALESCE(p.lastname, '') AS lastname,
        COALESCE(p.nationality, '') AS nationality_raw,
        COALESCE(p.birth_country, '') AS birth_country_raw,
        COALESCE(string_agg(DISTINCT t.name, '; ' ORDER BY t.name), '') AS current_team_names,
        COALESCE(string_agg(DISTINCT l.name, '; ' ORDER BY l.name), '') AS current_league_names,
        COALESCE(pt.name_ko, '') AS previous_name_ko,
        COALESCE(pt.short_name_ko, '') AS previous_short_name_ko
    FROM player p
    LEFT JOIN player_translation pt ON pt.player_id = p.id
    LEFT JOIN player_season_stat pss ON pss.player_id = p.id
    LEFT JOIN team t ON t.id = pss.team_id
    LEFT JOIN league l ON l.id = pss.league_id
    GROUP BY p.id, p.external_id, p.name, p.firstname, p.lastname, p.nationality,
             p.birth_country, pt.name_ko, pt.short_name_ko
    ORDER BY p.external_id
    """
)


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def load_supplemental(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    merged: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.exists():
            raise SystemExit(f"supplemental CSV not found: {path}")
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            if "api_player_id" not in (reader.fieldnames or []):
                raise SystemExit(f"supplemental CSV requires api_player_id: {path}")
            for row in reader:
                api_player_id = clean(row.get("api_player_id"))
                if not api_player_id:
                    continue
                target = merged.setdefault(api_player_id, {})
                for field in SUPPLEMENTAL_FIELDS:
                    value = clean(row.get(field))
                    if value:
                        target[field] = value
    return merged


def mapped_country(value: str) -> tuple[str, str]:
    raw = clean(value)
    if not raw:
        return "", "missing"
    mapped = COUNTRY_KO.get(raw, "")
    if not mapped:
        return "", "missing"
    if raw in FOOTBALL_ASSOCIATION_COUNTRIES:
        return mapped, "football_association"
    return mapped, "mapped"


def infer_popularity_tier(row: dict[str, str]) -> str:
    if row.get("manual_override_name_ko") or row.get("locked_common_name_ko"):
        return "high"
    leagues = row.get("current_league_names", "")
    teams = row.get("current_team_names", "")
    previous = row.get("previous_name_ko", "")
    major_tokens = (
        "Premier League",
        "UEFA Champions League",
        "World Cup",
        "UEFA Europa League",
    )
    major_teams = (
        "Arsenal",
        "Bayern",
        "Chelsea",
        "Liverpool",
        "Manchester City",
        "Manchester United",
        "Paris Saint Germain",
        "Real Madrid",
        "Tottenham",
    )
    if previous and any(token in leagues for token in major_tokens):
        return "high"
    if any(token in leagues for token in major_tokens) or any(token in teams for token in major_teams):
        return "mid"
    return "low"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export full-pass player name normalization queue."
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--supplemental", action="append", default=[], help="Optional CSV keyed by api_player_id")
    args = parser.parse_args()

    supplemental = load_supplemental(Path(path) for path in args.supplemental)
    settings = get_settings()
    engine = create_engine(
        normalize_database_url(settings.database_url),
        **database_engine_kwargs(settings),
    )
    with engine.connect() as conn:
        rows = [dict(row) for row in conn.execute(PLAYER_SQL).mappings()]
    engine.dispose()

    output_rows: list[dict[str, str]] = []
    for raw_row in rows:
        row = {key: clean(value) for key, value in raw_row.items()}
        row.update({field: "" for field in SUPPLEMENTAL_FIELDS})
        row.update(supplemental.get(row["api_player_id"], {}))
        nationality_ko, nationality_status = mapped_country(row["nationality_raw"])
        birth_country_ko, birth_status = mapped_country(row["birth_country_raw"])
        row["nationality_ko_mapped"] = nationality_ko
        row["birth_country_ko_mapped"] = birth_country_ko
        statuses = {nationality_status, birth_status}
        if "missing" in statuses:
            row["country_mapping_status"] = "missing"
        elif "football_association" in statuses:
            row["country_mapping_status"] = "football_association"
        else:
            row["country_mapping_status"] = "mapped"
        if not row["popularity_tier"]:
            row["popularity_tier"] = infer_popularity_tier(row)
        output_rows.append({field: row.get(field, "") for field in FIELDNAMES})

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(output_rows)

    missing_country = sum(1 for row in output_rows if row["country_mapping_status"] == "missing")
    print({"rows": len(output_rows), "missing_country_mapping": missing_country, "output": str(output)})


if __name__ == "__main__":
    main()
