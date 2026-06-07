from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


INPUT_KEY = "api_player_id"

INPUT_FIELDNAMES = [
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

OUTPUT_FIELDNAMES = [
    "api_player_id",
    "api_name_raw",
    "firstname",
    "lastname",
    "nationality_raw",
    "birth_country_raw",
    "name_ko",
    "short_name_ko",
    "aliases_ko",
    "name_base_used",
    "name_origin_language",
    "name_structure_type",
    "source_type",
    "source_ref",
    "rule_id",
    "method",
    "confidence",
    "usage_score",
    "usage_conflict",
    "needs_review",
    "review_codes",
    "reason",
]

AUDIT_FIELDNAMES = OUTPUT_FIELDNAMES + [
    "validator_needs_review",
    "validator_review_codes",
    "validator_reason",
    "import_eligible",
    "previous_name_ko",
    "previous_short_name_ko",
    "current_team_names",
    "current_league_names",
    "popularity_tier",
    "nationality_ko_mapped",
    "birth_country_ko_mapped",
    "country_mapping_status",
]

IMPORT_FIELDNAMES = ["external_id", "eng_name", "name_ko", "short_name_ko"]

KOREAN_SURNAMES = {
    "김",
    "이",
    "박",
    "최",
    "정",
    "조",
    "강",
    "윤",
    "장",
    "임",
    "한",
    "오",
    "서",
    "신",
    "권",
    "황",
    "안",
    "송",
    "류",
    "홍",
    "전",
    "고",
    "문",
    "양",
    "손",
    "배",
    "백",
    "허",
    "남",
    "심",
    "노",
    "하",
    "곽",
    "성",
    "차",
    "주",
    "우",
    "구",
    "민",
    "진",
    "지",
    "엄",
    "채",
    "원",
}

SERIOUS_REVIEW_CODES = {
    "API_COUNTRY_MAPPING_MISSING",
    "FAMOUS_PLAYER_NO_USAGE_EVIDENCE",
    "FIRST_LAST_MISSING",
    "KOREAN_SHORT_SURNAME_ONLY",
    "LATIN_REMAINS",
    "INITIAL_OR_DOT_REMAINS",
    "LOW_CONFIDENCE_IMPORT_BLOCKED",
    "SHORT_NAME_COLLISION",
    "TOO_LONG_LEGAL_NAME",
}


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def read_csv(path: Path, expected_header: list[str] | None = None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if expected_header and reader.fieldnames != expected_header:
            raise SystemExit(f"invalid header in {path}: {reader.fieldnames!r}")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise SystemExit(f"malformed CSV row in {path}:{line_number}")
            rows.append({key: clean(value) for key, value in row.items()})
        return rows


def parse_bool(value: str) -> bool:
    return clean(value).lower() in {"1", "true", "yes", "y"}


def parse_confidence(value: str) -> int:
    try:
        return int(float(clean(value)))
    except ValueError:
        return 0


def split_codes(value: str) -> set[str]:
    return {code for code in clean(value).split(";") if code}


def join_codes(codes: set[str]) -> str:
    return ";".join(sorted(codes))


def has_latin(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value))


def has_dot_or_initial(value: str) -> bool:
    return "." in value or bool(re.search(r"\b[A-Z]\b", value))


def api_name_abbreviated(value: str) -> bool:
    return bool(re.search(r"(^|\s)[A-Z]\.", value))


def too_long_legal_name(value: str) -> bool:
    return len(value.replace(" ", "")) > 18 or value.count(" ") >= 3


def context_keys(row: dict[str, str]) -> list[tuple[str, str]]:
    teams = [item.strip() for item in row.get("current_team_names", "").split(";") if item.strip()]
    leagues = [item.strip() for item in row.get("current_league_names", "").split(";") if item.strip()]
    if not teams and not leagues:
        return [("", "")]
    if not teams:
        teams = [""]
    if not leagues:
        leagues = [""]
    return [(team, league) for team in teams for league in leagues]


def add_collision_codes(
    rows: list[dict[str, str]],
    input_by_id: dict[str, dict[str, str]],
    code_by_id: dict[str, set[str]],
) -> None:
    grouped: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    for row in rows:
        api_player_id = row[INPUT_KEY]
        short_name = row.get("short_name_ko", "")
        if not short_name:
            continue
        for team, league in context_keys(input_by_id[api_player_id]):
            grouped[(team, league, short_name)].add(api_player_id)
    for (_team, _league, _short_name), ids in grouped.items():
        if len(ids) > 1:
            for api_player_id in ids:
                code_by_id[api_player_id].add("SHORT_NAME_COLLISION")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate player translation full-pass candidates.")
    parser.add_argument("--input", required=True, help="Original full queue CSV")
    parser.add_argument("--candidates", required=True, help="Merged ChatGPT candidates CSV")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_rows = read_csv(Path(args.input), INPUT_FIELDNAMES)
    candidate_rows = read_csv(Path(args.candidates), OUTPUT_FIELDNAMES)
    input_by_id = {row[INPUT_KEY]: row for row in input_rows}
    candidate_ids = [row[INPUT_KEY] for row in candidate_rows]
    duplicate_ids = [api_id for api_id, count in Counter(candidate_ids).items() if count > 1]
    missing = sorted(set(input_by_id) - set(candidate_ids), key=int)
    extra = sorted(set(candidate_ids) - set(input_by_id), key=int)
    if duplicate_ids or missing or extra:
        raise SystemExit(
            {
                "duplicate_ids": duplicate_ids[:20],
                "missing_count": len(missing),
                "missing_sample": missing[:20],
                "extra_count": len(extra),
                "extra_sample": extra[:20],
            }
        )

    code_by_id: dict[str, set[str]] = {
        row[INPUT_KEY]: split_codes(row.get("review_codes", "")) for row in candidate_rows
    }
    add_collision_codes(candidate_rows, input_by_id, code_by_id)

    import_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    import_block_reasons: Counter[str] = Counter()

    for row in candidate_rows:
        api_player_id = row[INPUT_KEY]
        source = input_by_id[api_player_id]
        codes = code_by_id[api_player_id]
        validator_reasons: list[str] = []

        confidence = parse_confidence(row.get("confidence", ""))
        if confidence < 80:
            codes.add("LOW_CONFIDENCE_IMPORT_BLOCKED")
            validator_reasons.append("confidence below 80")
        if has_latin(row.get("name_ko", "")) or has_latin(row.get("short_name_ko", "")):
            codes.add("LATIN_REMAINS")
            validator_reasons.append("Latin characters remain")
        if has_dot_or_initial(row.get("name_ko", "")) or has_dot_or_initial(row.get("short_name_ko", "")):
            codes.add("INITIAL_OR_DOT_REMAINS")
            validator_reasons.append("dot or initial remains")
        if api_name_abbreviated(row.get("api_name_raw", "")):
            codes.add("API_NAME_ABBREVIATED")
        if not clean(row.get("firstname")) or not clean(row.get("lastname")):
            codes.add("FIRST_LAST_MISSING")
            validator_reasons.append("firstname or lastname missing")
        if source.get("country_mapping_status") == "missing":
            codes.add("API_COUNTRY_MAPPING_MISSING")
            validator_reasons.append("country mapping missing")
        if source.get("country_mapping_status") == "football_association":
            codes.add("API_COUNTRY_IS_FOOTBALL_ASSOCIATION")
        if source.get("nationality_raw") == "Korea Republic" and row.get("short_name_ko") in KOREAN_SURNAMES:
            codes.add("KOREAN_SHORT_SURNAME_ONLY")
            validator_reasons.append("Korean player short name is surname only")
        if source.get("popularity_tier") == "high" and row.get("method") == "generated_by_language_rule":
            codes.add("FAMOUS_PLAYER_NO_USAGE_EVIDENCE")
            validator_reasons.append("high-popularity player generated only by language rule")
        if too_long_legal_name(row.get("name_ko", "")):
            codes.add("TOO_LONG_LEGAL_NAME")
            validator_reasons.append("display name looks like a long legal name")
        else:
            codes.discard("TOO_LONG_LEGAL_NAME")

        llm_needs_review = parse_bool(row.get("needs_review", ""))
        serious = bool(codes & SERIOUS_REVIEW_CODES)
        import_eligible = (
            not llm_needs_review
            and not serious
            and confidence >= 80
            and bool(row.get("name_ko"))
            and bool(row.get("short_name_ko"))
        )
        if not import_eligible:
            for code in codes or {"UNKNOWN_IMPORT_BLOCKED"}:
                if code in SERIOUS_REVIEW_CODES or llm_needs_review:
                    import_block_reasons[code] += 1

        audit_row = {field: row.get(field, "") for field in OUTPUT_FIELDNAMES}
        audit_row.update(
            {
                "validator_needs_review": str(not import_eligible),
                "validator_review_codes": join_codes(codes),
                "validator_reason": "; ".join(validator_reasons),
                "import_eligible": str(import_eligible),
                "previous_name_ko": source.get("previous_name_ko", ""),
                "previous_short_name_ko": source.get("previous_short_name_ko", ""),
                "current_team_names": source.get("current_team_names", ""),
                "current_league_names": source.get("current_league_names", ""),
                "popularity_tier": source.get("popularity_tier", ""),
                "nationality_ko_mapped": source.get("nationality_ko_mapped", ""),
                "birth_country_ko_mapped": source.get("birth_country_ko_mapped", ""),
                "country_mapping_status": source.get("country_mapping_status", ""),
            }
        )
        audit_rows.append(audit_row)

        if import_eligible:
            import_rows.append(
                {
                    "external_id": api_player_id,
                    "eng_name": row.get("api_name_raw", ""),
                    "name_ko": row.get("name_ko", ""),
                    "short_name_ko": row.get("short_name_ko", ""),
                }
            )
        else:
            review_rows.append(audit_row)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    import_path = output_dir / "player_translation_import.csv"
    review_path = output_dir / "player_translation_review.csv"
    audit_path = output_dir / "player_translation_audit.csv"
    summary_path = output_dir / "validation_summary.json"

    with import_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=IMPORT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(import_rows)
    with review_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=AUDIT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(review_rows)
    with audit_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=AUDIT_FIELDNAMES)
        writer.writeheader()
        writer.writerows(audit_rows)

    summary = {
        "input_rows": len(input_rows),
        "candidate_rows": len(candidate_rows),
        "import_rows": len(import_rows),
        "review_rows": len(review_rows),
        "import_block_reasons": dict(import_block_reasons.most_common()),
        "outputs": {
            "import": str(import_path),
            "review": str(review_path),
            "audit": str(audit_path),
            "summary": str(summary_path),
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
