from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


DEFAULT_INPUT = "out/player-translation/full-pass/review/player_translation_review_decisions.csv"

APPROVE_VALUES = {"approve", "approved", "upsert", "import", "yes", "y", "1", "true"}
SKIP_VALUES = {"", "skip", "reject", "rejected", "no", "n", "0", "false"}

UPSERT_SQL = text(
    """
    INSERT INTO player_translation (player_id, name_ko, short_name_ko, updated_at)
    SELECT p.id, :name_ko, :short_name_ko, now()
    FROM player p
    WHERE p.external_id = :external_id
    ON CONFLICT (player_id) DO UPDATE SET
        name_ko = EXCLUDED.name_ko,
        short_name_ko = EXCLUDED.short_name_ko,
        updated_at = now()
    RETURNING player_id
    """
)


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def has_latin(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value))


def has_dot_or_initial(value: str) -> bool:
    return "." in value or bool(re.search(r"\b[A-Z]\b", value))


def decision_value(row: dict[str, str]) -> str:
    return clean(row.get("decision", "")).lower()


def approved(row: dict[str, str]) -> bool:
    return decision_value(row) in APPROVE_VALUES


def validate_headers(fieldnames: list[str] | None, csv_path: Path) -> None:
    required = {
        "decision",
        "api_player_id",
        "api_name_raw",
        "final_name_ko",
        "final_short_name_ko",
    }
    missing = sorted(required - set(fieldnames or []))
    if missing:
        raise SystemExit({"csv": str(csv_path), "missing_columns": missing})


def row_errors(row: dict[str, str], *, allow_risky: bool) -> list[str]:
    errors: list[str] = []
    decision = decision_value(row)
    if decision not in APPROVE_VALUES and decision not in SKIP_VALUES:
        errors.append(f"unknown decision={decision}")
    if not approved(row):
        return errors

    name_ko = clean(row.get("final_name_ko"))
    short_name_ko = clean(row.get("final_short_name_ko"))
    if not name_ko:
        errors.append("final_name_ko is empty")
    if not short_name_ko:
        errors.append("final_short_name_ko is empty")
    if not clean(row.get("api_player_id")).isdigit():
        errors.append("api_player_id is not an integer")

    if not allow_risky:
        if has_latin(name_ko) or has_latin(short_name_ko):
            errors.append("Latin characters remain")
        if has_dot_or_initial(name_ko) or has_dot_or_initial(short_name_ko):
            errors.append("dot or initial remains")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Upsert manually approved player translation review rows. "
            "Only rows with decision=approve are applied."
        )
    )
    parser.add_argument("csv_path", nargs="?", default=DEFAULT_INPUT)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually upsert approved rows. Without this flag the command only validates and reports.",
    )
    parser.add_argument(
        "--allow-risky",
        action="store_true",
        help="Allow approved rows that still contain Latin letters, dots, or initials.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only process the first N approved rows after validation.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        validate_headers(reader.fieldnames, csv_path)
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]

    invalid: list[dict[str, object]] = []
    approved_rows: list[dict[str, str]] = []
    skipped_count = 0
    for line_number, row in enumerate(rows, start=2):
        errors = row_errors(row, allow_risky=args.allow_risky)
        if errors:
            invalid.append(
                {
                    "line": line_number,
                    "api_player_id": row.get("api_player_id", ""),
                    "errors": errors,
                }
            )
            continue
        if approved(row):
            approved_rows.append(row)
        else:
            skipped_count += 1

    duplicate_ids = sorted(
        {
            row["api_player_id"]
            for row in approved_rows
            if [item["api_player_id"] for item in approved_rows].count(row["api_player_id"]) > 1
        },
        key=int,
    )
    if duplicate_ids:
        invalid.append({"duplicate_approved_api_player_ids": duplicate_ids[:20]})

    if invalid:
        raise SystemExit(
            {
                "csv": str(csv_path),
                "invalid_count": len(invalid),
                "invalid_sample": invalid[:20],
            }
        )

    if args.limit is not None:
        approved_rows = approved_rows[: args.limit]

    if not args.apply:
        print(
            {
                "mode": "dry_run",
                "csv": str(csv_path),
                "approved_rows": len(approved_rows),
                "skipped_rows": skipped_count,
                "message": "Pass --apply to upsert approved rows.",
            }
        )
        return

    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)

    applied = 0
    missing: list[tuple[str, str]] = []
    with engine.begin() as conn:
        for row in approved_rows:
            player_id = conn.execute(
                UPSERT_SQL,
                {
                    "external_id": int(row["api_player_id"]),
                    "name_ko": row["final_name_ko"],
                    "short_name_ko": row["final_short_name_ko"],
                },
            ).scalar_one_or_none()
            if player_id is None:
                missing.append((row["api_player_id"], row.get("api_name_raw", "")))
            else:
                applied += 1

    print(
        {
            "mode": "apply",
            "csv": str(csv_path),
            "approved_rows": len(approved_rows),
            "applied": applied,
            "missing": missing[:20],
            "missing_count": len(missing),
        }
    )


if __name__ == "__main__":
    main()
