from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import get_settings
from generate_player_translation_backfill_seed import roman_word_to_ko


SPARQL_URL = "https://query.wikidata.org/sparql"
DEFAULT_OPENAI_MODEL = "gpt-3.5-turbo"


def clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def team_candidates(row: dict[str, str]) -> list[str]:
    name = clean_name(row.get("full_name") or row.get("eng_name") or "")
    candidates = [name] if name else []
    if name and not name.endswith(" F.C."):
        candidates.append(f"{name} F.C.")
    if name.endswith(" FC"):
        candidates.append(f"{name[:-3]} F.C.")
    return list(dict.fromkeys(candidates))


def wikidata_team_labels(candidates: list[str], *, batch_size: int = 35) -> dict[str, str]:
    labels: dict[str, str] = {}
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        values = " ".join(json.dumps(name, ensure_ascii=False) + "@en" for name in batch)
        query = (
            "SELECT ?en ?ko WHERE { "
            f"VALUES ?en {{ {values} }} "
            "?item rdfs:label ?en . "
            "?item rdfs:label ?ko . "
            'FILTER(LANG(?ko)="ko") '
            "FILTER("
            "EXISTS { ?item wdt:P31/wdt:P279* wd:Q476028 } || "
            "EXISTS { ?item wdt:P31/wdt:P279* wd:Q847017 } || "
            "EXISTS { ?item wdt:P641 wd:Q2736 }"
            ") "
            "}"
        )
        url = f"{SPARQL_URL}?{urlencode({'format': 'json', 'query': query})}"
        req = Request(url, headers={"User-Agent": "benchmark-backfill/0.1"})
        data = None
        for attempt in range(4):
            try:
                with urlopen(req, timeout=45) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except Exception:
                if attempt == 3:
                    data = {"results": {"bindings": []}}
                else:
                    time.sleep(2 * (attempt + 1))
        for item in data.get("results", {}).get("bindings", []):
            labels[item["en"]["value"]] = item["ko"]["value"]
        time.sleep(0.6)
    return labels


def deterministic_team_name(row: dict[str, str]) -> tuple[str, str]:
    name = clean_name(row.get("full_name") or row.get("eng_name") or "")
    ko = " ".join(roman_word_to_ko(part) for part in name.split())
    ko = ko or name
    return ko, ko


async def openai_transliterate_teams(
    rows: list[dict[str, str]],
    *,
    model: str,
    batch_size: int = 50,
) -> dict[str, tuple[str, str]]:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is required for --openai-fallback") from exc

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    translations: dict[str, tuple[str, str]] = {}
    for offset in range(0, len(rows), batch_size):
        batch = rows[offset : offset + batch_size]
        payload = [
            {
                "external_id": row["external_id"],
                "eng_name": row.get("eng_name", ""),
                "country": row.get("context", ""),
                "api_short": row.get("short_context", ""),
            }
            for row in batch
        ]
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            max_tokens=3500,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 축구 구단 영문명을 한국어 스포츠 기사에서 읽기 좋은 "
                        "한글 표기로 정리하는 편집자입니다. 검색 가능한 한글 라벨이 "
                        "없는 fallback 대상만 들어옵니다. 국내에서 널리 쓰이는 표기가 "
                        "확실하면 그 표기를 쓰고, 아니면 자연스럽게 음역하세요. "
                        "응답은 JSON 객체만 출력하고, 키 rows는 배열입니다."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "rules": [
                                "입력 rows와 같은 순서/개수로 반환",
                                "각 row는 external_id, name_ko, short_name_ko 포함",
                                "FC/AFC/United/City/Town/Rovers 같은 접미사는 통용 표기면 유지",
                                "short_name_ko는 기사 제목이나 표에서 쓰기 좋은 약칭",
                            ],
                            "rows": payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        for item in data.get("rows", []):
            external_id = str(item.get("external_id", "")).strip()
            name_ko = str(item.get("name_ko", "")).strip()
            short_name_ko = str(item.get("short_name_ko", "")).strip()
            if external_id and name_ko and short_name_ko:
                translations[external_id] = (name_ko, short_name_ko)
        time.sleep(0.2)
    return translations


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--output", required=True)
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--openai-fallback", action="store_true")
    parser.add_argument("--openai-model", default=DEFAULT_OPENAI_MODEL)
    args = parser.parse_args()

    rows = list(csv.DictReader(Path(args.input_csv).open(encoding="utf-8")))
    row_candidates: dict[str, list[str]] = {}
    all_candidates: list[str] = []
    for row in rows:
        candidates = team_candidates(row)
        row_candidates[row["external_id"]] = candidates
        all_candidates.extend(candidates)
    wd_labels = wikidata_team_labels(list(dict.fromkeys(all_candidates)))

    staged: list[tuple[dict[str, str], str, str, str, str]] = []
    fallback_rows: list[dict[str, str]] = []
    for row in rows:
        method = "phonetic-fallback"
        matched_name = ""
        name_ko = ""
        short_ko = ""
        for candidate in row_candidates[row["external_id"]]:
            if candidate in wd_labels:
                matched_name = candidate
                name_ko = wd_labels[candidate]
                short_ko = name_ko
                method = "wikidata-ko-label"
                break
        if not name_ko:
            fallback_rows.append(row)
        staged.append((row, method, matched_name, name_ko, short_ko))

    openai_fallbacks: dict[str, tuple[str, str]] = {}
    if args.openai_fallback and fallback_rows:
        openai_fallbacks = asyncio.run(
            openai_transliterate_teams(fallback_rows, model=args.openai_model)
        )

    out_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for row, method, matched_name, name_ko, short_ko in staged:
        if not name_ko:
            if row["external_id"] in openai_fallbacks:
                name_ko, short_ko = openai_fallbacks[row["external_id"]]
                method = "phonetic-fallback-openai"
            else:
                name_ko, short_ko = deterministic_team_name(row)
        out_rows.append(
            {
                "external_id": row["external_id"],
                "eng_name": row["eng_name"],
                "name_ko": name_ko,
                "short_name_ko": short_ko,
            }
        )
        audit_rows.append(
            {
                "external_id": row["external_id"],
                "eng_name": row["eng_name"],
                "country": row.get("context", ""),
                "method": method,
                "matched_name": matched_name,
                "name_ko": name_ko,
                "short_name_ko": short_ko,
            }
        )

    for path, fieldnames, data in (
        (
            Path(args.output),
            ["external_id", "eng_name", "name_ko", "short_name_ko"],
            out_rows,
        ),
        (
            Path(args.audit_output),
            [
                "external_id",
                "eng_name",
                "country",
                "method",
                "matched_name",
                "name_ko",
                "short_name_ko",
            ],
            audit_rows,
        ),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    counts: dict[str, int] = {}
    for row in audit_rows:
        counts[row["method"]] = counts.get(row["method"], 0) + 1
    print({"rows": len(out_rows), "methods": counts, "output": args.output, "audit": args.audit_output})


if __name__ == "__main__":
    main()
