from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


MANUAL_FIXES = {
    "628356": ("파비치", "파비치"),
    "568380": ("폴", "폴"),
    "568099": ("안카마피오", "안카마피오"),
    "555376": ("피콜론", "피콜론"),
    "443719": ("프네브모니디스", "프네브모니디스"),
    "568156": ("산체스", "산체스"),
    "584077": ("홀", "홀"),
    "386852": ("제레미 아그보니포", "아그보니포"),
    "414188": ("말콤 젱", "젱"),
}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: clean_player_translation_seed.py <csv_path>")
    path = Path(sys.argv[1])
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    for row in rows:
        if row["external_id"] in MANUAL_FIXES:
            row["name_ko"], row["short_name_ko"] = MANUAL_FIXES[row["external_id"]]
        row["name_ko"] = re.sub(
            r"^[A-Z](?:\.\s*[A-Z])*\.\s*", "", row["name_ko"]
        ).strip()
        if not row["name_ko"]:
            row["name_ko"] = row["short_name_ko"]
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(
            fp, fieldnames=["external_id", "eng_name", "name_ko", "short_name_ko"]
        )
        writer.writeheader()
        writer.writerows(rows)
    print({"rows": len(rows), "path": str(path)})


if __name__ == "__main__":
    main()
