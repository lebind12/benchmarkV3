from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from validate_player_translation_candidates import AUDIT_FIELDNAMES, IMPORT_FIELDNAMES


def read_csv(path: Path, expected_header: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames != expected_header:
            raise SystemExit(f"invalid header in {path}: {reader.fieldnames!r}")
        rows = []
        for line_number, row in enumerate(reader, start=2):
            if None in row:
                raise SystemExit(f"malformed CSV row in {path}:{line_number}")
            rows.append({key: str(value or "").strip() for key, value in row.items()})
        return rows


def sort_key(row: dict[str, str], field: str) -> tuple[int, str]:
    value = row.get(field, "")
    try:
        return (int(value), value)
    except ValueError:
        return (10**12, value)


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Combine validated player translation batch outputs."
    )
    parser.add_argument(
        "--validated-dir",
        action="append",
        default=[],
        help=(
            "Validated batch root to combine. Repeat for multiple worker roots. "
            "Defaults to out/player-translation/full-pass/codex-batches/validated."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="out/player-translation/full-pass/codex-batches/combined",
    )
    args = parser.parse_args()

    validated_dirs = [Path(path) for path in args.validated_dir] if args.validated_dir else [
        Path("out/player-translation/full-pass/codex-batches/validated")
    ]
    batch_dirs = []
    for validated_dir in validated_dirs:
        batch_dirs.extend(sorted(path for path in validated_dir.glob("batch_*") if path.is_dir()))
    batch_dirs = sorted(batch_dirs, key=lambda path: path.name)
    if not batch_dirs:
        raise SystemExit(
            "no batch directories found in "
            + ", ".join(str(path) for path in validated_dirs)
        )

    import_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    summaries: list[dict[str, object]] = []

    for batch_dir in batch_dirs:
        import_path = batch_dir / "player_translation_import.csv"
        review_path = batch_dir / "player_translation_review.csv"
        audit_path = batch_dir / "player_translation_audit.csv"
        summary_path = batch_dir / "validation_summary.json"
        missing = [
            str(path)
            for path in (import_path, review_path, audit_path, summary_path)
            if not path.exists()
        ]
        if missing:
            raise SystemExit({"batch": batch_dir.name, "missing": missing})

        import_rows.extend(read_csv(import_path, IMPORT_FIELDNAMES))
        review_rows.extend(read_csv(review_path, AUDIT_FIELDNAMES))
        audit_rows.extend(read_csv(audit_path, AUDIT_FIELDNAMES))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["batch"] = batch_dir.name
        summaries.append(summary)

    audit_ids = [row["api_player_id"] for row in audit_rows]
    duplicate_audit_ids = [api_id for api_id, count in Counter(audit_ids).items() if count > 1]
    if duplicate_audit_ids:
        raise SystemExit({"duplicate_audit_ids": duplicate_audit_ids[:20]})

    import_ids = {row["external_id"] for row in import_rows}
    review_ids = {row["api_player_id"] for row in review_rows}
    overlap = sorted(import_ids & review_ids, key=int)
    if overlap:
        raise SystemExit({"ids_in_both_import_and_review": overlap[:20]})

    if import_ids | review_ids != set(audit_ids):
        raise SystemExit(
            {
                "partition_mismatch": True,
                "audit_rows": len(audit_ids),
                "import_or_review_rows": len(import_ids | review_ids),
            }
        )

    output_dir = Path(args.output_dir)
    import_rows.sort(key=lambda row: sort_key(row, "external_id"))
    review_rows.sort(key=lambda row: sort_key(row, "api_player_id"))
    audit_rows.sort(key=lambda row: sort_key(row, "api_player_id"))

    import_output = output_dir / "player_translation_import.csv"
    review_output = output_dir / "player_translation_review.csv"
    audit_output = output_dir / "player_translation_audit.csv"
    summary_output = output_dir / "combined_summary.json"

    write_csv(import_output, IMPORT_FIELDNAMES, import_rows)
    write_csv(review_output, AUDIT_FIELDNAMES, review_rows)
    write_csv(audit_output, AUDIT_FIELDNAMES, audit_rows)

    combined_summary = {
        "batch_count": len(batch_dirs),
        "input_rows": sum(int(summary["input_rows"]) for summary in summaries),
        "candidate_rows": sum(int(summary["candidate_rows"]) for summary in summaries),
        "import_rows": len(import_rows),
        "review_rows": len(review_rows),
        "audit_rows": len(audit_rows),
        "first_batch": batch_dirs[0].name,
        "last_batch": batch_dirs[-1].name,
        "outputs": {
            "import": str(import_output),
            "review": str(review_output),
            "audit": str(audit_output),
            "summary": str(summary_output),
        },
    }
    summary_output.write_text(
        json.dumps(combined_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        {
            "event": "combined_csv_written",
            "validated_dirs": [str(path) for path in validated_dirs],
            **combined_summary,
        }
    )


if __name__ == "__main__":
    main()
