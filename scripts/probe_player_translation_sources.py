from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API = "https://www.wikidata.org/w/api.php"


def _get_json(params: dict[str, str]) -> dict:
    url = f"{API}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "benchmark-backfill/0.1"})
    for attempt in range(5):
        try:
            with urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code != 429 or attempt == 4:
                raise
            time.sleep(2 * (attempt + 1))
    raise RuntimeError("unreachable")


def search_ko_label(name: str) -> tuple[str, str] | None:
    data = _get_json(
        {
            "action": "wbsearchentities",
            "format": "json",
            "language": "en",
            "uselang": "ko",
            "search": name,
            "limit": "5",
        }
    )
    ids = [item["id"] for item in data.get("search", []) if item.get("id")]
    if not ids:
        return None
    entities = _get_json(
        {
            "action": "wbgetentities",
            "format": "json",
            "ids": "|".join(ids),
            "languages": "ko|en",
            "props": "labels|descriptions",
        }
    ).get("entities", {})
    for entity_id in ids:
        entity = entities.get(entity_id) or {}
        desc = ((entity.get("descriptions") or {}).get("en") or {}).get("value", "")
        labels = entity.get("labels") or {}
        ko = (labels.get("ko") or {}).get("value")
        en = (labels.get("en") or {}).get("value")
        if ko and en and "football" in desc.lower():
            return ko, entity_id
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.csv_path).open(encoding="utf-8")))
    matched = 0
    for row in rows[: args.limit]:
        name = row.get("full_name") or row["eng_name"]
        found = search_ko_label(name)
        if found:
            matched += 1
        print({"external_id": row["external_id"], "name": name, "found": found})
        time.sleep(0.75)
    print({"checked": min(args.limit, len(rows)), "matched": matched})


if __name__ == "__main__":
    main()
