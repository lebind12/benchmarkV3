from __future__ import annotations

import argparse
import csv
from pathlib import Path


DEFAULT_INPUT = "out/player-translation/full-pass/combined/player_translation_review.csv"
DEFAULT_OUTPUT = "out/player-translation/full-pass/review/player_translation_review_decisions.csv"

DECISION_FIELDS = [
    "decision",
    "final_name_ko",
    "final_short_name_ko",
    "review_note",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create one editable CSV for manually deciding reviewed player translations."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise SystemExit(f"{output_path} already exists. Pass --force to overwrite.")

    with input_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if not reader.fieldnames:
            raise SystemExit(f"empty CSV: {input_path}")
        input_fields = list(reader.fieldnames)
        rows = list(reader)

    fieldnames = DECISION_FIELDS + input_fields
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output_row = {
                "decision": "",
                "final_name_ko": row.get("name_ko", ""),
                "final_short_name_ko": row.get("short_name_ko", ""),
                "review_note": "",
            }
            output_row.update(row)
            writer.writerow(output_row)

    print(
        {
            "input": str(input_path),
            "output": str(output_path),
            "rows": len(rows),
            "decision_values": ["approve", "skip", "reject"],
            "upsert_rule": "Only decision=approve rows are upserted by the review import CLI.",
        }
    )


if __name__ == "__main__":
    main()
