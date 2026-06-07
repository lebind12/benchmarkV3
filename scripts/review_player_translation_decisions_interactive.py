from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


DEFAULT_INPUT = "out/player-translation/full-pass/review/player_translation_review_decisions.csv"

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

REQUIRED_FIELDS = {
    "decision",
    "final_name_ko",
    "final_short_name_ko",
    "review_note",
    "api_player_id",
    "api_name_raw",
    "firstname",
    "lastname",
    "name_ko",
    "short_name_ko",
}


def clean(value: object) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def has_latin(value: str) -> bool:
    return bool(re.search(r"[A-Za-z]", value))


def has_dot_or_initial(value: str) -> bool:
    return "." in value or bool(re.search(r"\b[A-Z]\b", value))


def read_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        fieldnames = list(reader.fieldnames or [])
        missing = sorted(REQUIRED_FIELDS - set(fieldnames))
        if missing:
            raise SystemExit({"csv": str(path), "missing_columns": missing})
        rows = [{key: clean(value) for key, value in row.items()} for row in reader]
    return fieldnames, rows


def write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def row_status(row: dict[str, str]) -> str:
    decision = clean(row.get("decision")).lower()
    return decision or "pending"


def validate_approved_row(row: dict[str, str], *, allow_risky: bool) -> list[str]:
    errors: list[str] = []
    api_player_id = clean(row.get("api_player_id"))
    name_ko = clean(row.get("final_name_ko"))
    short_name_ko = clean(row.get("final_short_name_ko"))
    if not api_player_id.isdigit():
        errors.append("api_player_id is not an integer")
    if not name_ko:
        errors.append("final_name_ko is empty")
    if not short_name_ko:
        errors.append("final_short_name_ko is empty")
    if not allow_risky:
        if has_latin(name_ko) or has_latin(short_name_ko):
            errors.append("Latin characters remain")
        if has_dot_or_initial(name_ko) or has_dot_or_initial(short_name_ko):
            errors.append("dot or initial remains")
    return errors


def show_row(row: dict[str, str], index: int, total: int) -> None:
    print()
    print("=" * 88)
    print(f"[{index + 1}/{total}] status={row_status(row)} api_player_id={row.get('api_player_id', '')}")
    print(f"raw        : {row.get('api_name_raw', '')}")
    print(f"first/last : {row.get('firstname', '')} / {row.get('lastname', '')}")
    print(f"country    : nationality={row.get('nationality_raw', '')} birth={row.get('birth_country_raw', '')}")
    print(f"team/league: {row.get('current_team_names', '')} / {row.get('current_league_names', '')}")
    print(f"candidate  : {row.get('name_ko', '')} / {row.get('short_name_ko', '')}")
    print(f"final      : {row.get('final_name_ko', '')} / {row.get('final_short_name_ko', '')}")
    print(f"previous   : {row.get('previous_name_ko', '')} / {row.get('previous_short_name_ko', '')}")
    print(f"confidence : {row.get('confidence', '')} usage={row.get('usage_score', '')}")
    print(f"codes      : {row.get('validator_review_codes') or row.get('review_codes', '')}")
    print(f"reason     : {row.get('validator_reason') or row.get('reason', '')}")
    note = row.get("review_note", "")
    if note:
        print(f"note       : {note}")
    print("-" * 88)
    print("Commands: [Enter/n] next, e edit, a approve+upsert, s skip, r reject, p prev, g goto, q quit")


def prompt_line(prompt: str) -> str:
    print(prompt, end="", flush=True)
    raw = sys.stdin.buffer.readline()
    if raw == b"":
        raise EOFError
    return raw.decode("utf-8", errors="replace").strip()


def prompt_edit(row: dict[str, str]) -> None:
    current_name = row.get("final_name_ko", "")
    current_short = row.get("final_short_name_ko", "")
    print("Leave blank to keep the current value.")
    name = prompt_line(f"final_name_ko [{current_name}]: ")
    short = prompt_line(f"final_short_name_ko [{current_short}]: ")
    note = prompt_line("review_note append: ")
    if name:
        row["final_name_ko"] = clean(name)
    if short:
        row["final_short_name_ko"] = clean(short)
    if note:
        existing = row.get("review_note", "")
        row["review_note"] = f"{existing}; {note}" if existing else note


def mark(row: dict[str, str], decision: str, note: str = "") -> None:
    row["decision"] = decision
    if note:
        existing = row.get("review_note", "")
        row["review_note"] = f"{existing}; {note}" if existing else note


def upsert_row(conn, row: dict[str, str]) -> bool:
    player_id = conn.execute(
        UPSERT_SQL,
        {
            "external_id": int(row["api_player_id"]),
            "name_ko": row["final_name_ko"],
            "short_name_ko": row["final_short_name_ko"],
        },
    ).scalar_one_or_none()
    return player_id is not None


def first_pending_index(rows: list[dict[str, str]]) -> int:
    for index, row in enumerate(rows):
        if not clean(row.get("decision")):
            return index
    return 0


def goto_index(rows: list[dict[str, str]], value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        as_index = int(value) - 1
        if 0 <= as_index < len(rows):
            return as_index
        for index, row in enumerate(rows):
            if row.get("api_player_id") == value:
                return index
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactively review player translation decisions and upsert approved rows."
    )
    parser.add_argument("csv_path", nargs="?", default=DEFAULT_INPUT)
    parser.add_argument("--dry-run", action="store_true", help="Do not write to the database.")
    parser.add_argument("--allow-risky", action="store_true", help="Allow Latin letters, dots, or initials.")
    parser.add_argument("--start-index", type=int, help="1-based row index to start from.")
    parser.add_argument("--player-id", help="Start from a specific api_player_id.")
    parser.add_argument(
        "--include-decided",
        action="store_true",
        help="Do not automatically jump past rows that already have a decision.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv_path)
    fieldnames, rows = read_rows(csv_path)
    if not rows:
        raise SystemExit(f"no rows in {csv_path}")

    if args.player_id:
        index = goto_index(rows, args.player_id)
        if index is None:
            raise SystemExit(f"api_player_id not found: {args.player_id}")
    elif args.start_index:
        index = max(0, min(args.start_index - 1, len(rows) - 1))
    else:
        index = first_pending_index(rows)

    engine = None
    conn_context = None
    conn = None
    if not args.dry_run:
        settings = get_settings()
        engine = create_engine(normalize_database_url(settings.database_url), future=True)
        conn_context = engine.begin()
        conn = conn_context.__enter__()

    applied = 0
    try:
        while 0 <= index < len(rows):
            row = rows[index]
            if not args.include_decided and clean(row.get("decision")):
                next_index = first_pending_index(rows[index + 1 :])
                if next_index == 0 and all(clean(item.get("decision")) for item in rows[index + 1 :]):
                    print("No more pending rows.")
                    break
                index = index + 1 + next_index
                continue

            show_row(row, index, len(rows))
            try:
                command = prompt_line("> ").lower()
            except EOFError:
                break
            if command in {"", "n", "next"}:
                index += 1
                continue
            if command in {"q", "quit", "exit"}:
                break
            if command in {"p", "prev", "previous"}:
                index = max(0, index - 1)
                continue
            if command in {"g", "goto"}:
                target = prompt_line("row number or api_player_id: ")
                found = goto_index(rows, target)
                if found is None:
                    print("Not found.")
                else:
                    index = found
                continue
            if command in {"e", "edit"}:
                prompt_edit(row)
                write_rows(csv_path, fieldnames, rows)
                continue
            if command in {"s", "skip"}:
                mark(row, "skip")
                write_rows(csv_path, fieldnames, rows)
                index += 1
                continue
            if command in {"r", "reject"}:
                mark(row, "reject")
                write_rows(csv_path, fieldnames, rows)
                index += 1
                continue
            if command in {"a", "approve", "upsert"}:
                errors = validate_approved_row(row, allow_risky=args.allow_risky)
                if errors:
                    print({"blocked": errors})
                    continue
                mark(row, "approve")
                if args.dry_run:
                    print({"dry_run": True, "would_upsert": row["api_player_id"]})
                else:
                    assert conn is not None
                    if upsert_row(conn, row):
                        applied += 1
                        mark(row, "approve", "upserted")
                        print({"upserted": row["api_player_id"], "applied": applied})
                    else:
                        mark(row, "approve", "missing_player")
                        print({"missing_player": row["api_player_id"]})
                write_rows(csv_path, fieldnames, rows)
                index += 1
                continue
            print("Unknown command.")
    finally:
        if conn_context is not None:
            conn_context.__exit__(None, None, None)

    write_rows(csv_path, fieldnames, rows)
    pending = sum(1 for row in rows if not clean(row.get("decision")))
    approved = sum(1 for row in rows if clean(row.get("decision")).lower() == "approve")
    skipped = sum(1 for row in rows if clean(row.get("decision")).lower() == "skip")
    rejected = sum(1 for row in rows if clean(row.get("decision")).lower() == "reject")
    print(
        {
            "csv": str(csv_path),
            "applied_this_session": applied,
            "approved_total": approved,
            "skipped_total": skipped,
            "rejected_total": rejected,
            "pending": pending,
        }
    )


if __name__ == "__main__":
    main()
