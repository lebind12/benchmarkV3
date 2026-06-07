from __future__ import annotations

import argparse
import csv
from pathlib import Path


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


def load_ids(path: Path) -> set[str]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if "api_player_id" not in (reader.fieldnames or []):
            raise SystemExit(f"input CSV requires api_player_id: {path}")
        return {str(row["api_player_id"]).strip() for row in reader}


def result_paths(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for value in args.results:
        path = Path(value)
        if path.is_dir():
            paths.extend(sorted(path.glob("*.csv")))
        else:
            paths.append(path)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge ChatGPT player translation result shards.")
    parser.add_argument("--input", required=True, help="Original full queue CSV")
    parser.add_argument("--results", nargs="+", required=True, help="Result CSV files or directories")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    expected_ids = load_ids(Path(args.input))
    rows_by_id: dict[str, dict[str, str]] = {}
    duplicates: list[str] = []

    for path in result_paths(args):
        with path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)
            if reader.fieldnames != OUTPUT_FIELDNAMES:
                raise SystemExit(
                    f"invalid result header in {path}: {reader.fieldnames!r}"
                )
            for line_number, row in enumerate(reader, start=2):
                if None in row:
                    raise SystemExit(f"malformed CSV row in {path}:{line_number}")
                api_player_id = str(row["api_player_id"]).strip()
                if api_player_id in rows_by_id:
                    duplicates.append(api_player_id)
                rows_by_id[api_player_id] = row

    actual_ids = set(rows_by_id)
    missing = sorted(expected_ids - actual_ids, key=int)
    extra = sorted(actual_ids - expected_ids, key=int)
    if missing or extra or duplicates:
        raise SystemExit(
            {
                "missing_count": len(missing),
                "missing_sample": missing[:20],
                "extra_count": len(extra),
                "extra_sample": extra[:20],
                "duplicate_count": len(duplicates),
                "duplicate_sample": duplicates[:20],
            }
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=OUTPUT_FIELDNAMES)
        writer.writeheader()
        for api_player_id in sorted(expected_ids, key=int):
            writer.writerow(rows_by_id[api_player_id])

    print({"rows": len(rows_by_id), "output": str(output)})


if __name__ == "__main__":
    main()
