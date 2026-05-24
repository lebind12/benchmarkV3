from __future__ import annotations

import csv
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import get_settings, normalize_database_url


UPSERT_SQL = text(
    """
    INSERT INTO league_translation (league_id, name_ko, short_name_ko, updated_at)
    SELECT l.id, :name_ko, :short_name_ko, now()
    FROM league l
    WHERE l.external_id = :external_id
    ON CONFLICT (league_id) DO UPDATE SET
        name_ko = EXCLUDED.name_ko,
        short_name_ko = EXCLUDED.short_name_ko,
        updated_at = now()
    RETURNING league_id
    """
)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: import_league_translations.py <csv_path>")

    csv_path = Path(sys.argv[1])
    settings = get_settings()
    engine = create_engine(normalize_database_url(settings.database_url), future=True)

    with csv_path.open("r", encoding="utf-8", newline="") as fp:
        rows = list(csv.DictReader(fp))

    applied = 0
    missing: list[tuple[str, str]] = []
    with engine.begin() as conn:
        for row in rows:
            league_id = conn.execute(
                UPSERT_SQL,
                {
                    "external_id": int(row["external_id"]),
                    "name_ko": row["name_ko"],
                    "short_name_ko": row["short_name_ko"],
                },
            ).scalar_one_or_none()
            if league_id is None:
                missing.append((row["external_id"], row["eng_name"]))
            else:
                applied += 1

    print({"applied": applied, "missing": missing})


if __name__ == "__main__":
    main()
