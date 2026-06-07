from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path

from openai import OpenAI

from app.core.config import get_settings


DEFAULT_MODEL = "gpt-4.1"
KOREAN_SOURCE_DOMAINS = [
    "ko.wikipedia.org",
    "sports.naver.com",
    "sports.daum.net",
    "mksports.co.kr",
    "sports.chosun.com",
    "sports.khan.co.kr",
    "interfootball.heraldcorp.com",
    "sportalkorea.com",
    "footballist.co.kr",
    "spotvnews.co.kr",
    "goal.com",
]

RESPONSE_SCHEMA = {
    "name": "player_translation_batch",
    "schema": {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "external_id": {"type": "integer"},
                        "name_ko": {"type": "string"},
                        "short_name_ko": {"type": "string"},
                        "method": {"type": "string"},
                        "sources": {
                            "type": "array",
                            "items": {"type": "string"},
                            "maxItems": 3,
                        },
                    },
                    "required": [
                        "external_id",
                        "name_ko",
                        "short_name_ko",
                        "method",
                        "sources",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    },
    "strict": True,
}


def clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def bad_ko(name_ko: str, short_name_ko: str) -> bool:
    if not name_ko or not short_name_ko:
        return True
    if re.search(r"[A-Za-z]", name_ko + short_name_ko):
        return True
    if "." in name_ko or "." in short_name_ko:
        return True
    return False


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fp:
        return list(csv.DictReader(fp))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_prompt(rows: list[dict[str, str]]) -> str:
    payload = [
        {
            "external_id": int(row["external_id"]),
            "api_name": row["name"],
            "full_name": row["full_name"],
            "firstname": row["firstname"],
            "lastname": row["lastname"],
            "nationality": row["nationality"],
            "teams": row["teams"],
            "team_countries": row.get("team_countries", ""),
            "leagues": row["leagues"],
            "current_db_ko": row["current_name_ko"],
            "draft_ko": row["name_ko"],
        }
        for row in rows
    ]
    return json.dumps(
        {
            "task": (
                "축구 선수 이름을 한국어 통용 표기로 검증/보정한다. 먼저 한국어 웹 검색 "
                "결과에서 축구 선수로 확인되는 표기가 있으면 그 표기를 사용한다. 한국어 "
                "사용례가 없으면 선수 이름의 언어권/국가권을 추정해 한국어 외래어 표기 "
                "관례에 맞게 음역한다. 영문 이니셜을 한글로 읽어 넣지 말고, 이름을 알 수 "
                "없는 약자형은 약자를 제거한 성/식별 가능한 이름 중심으로 표기한다."
            ),
            "rules": [
                "반드시 입력 rows와 같은 external_id를 모두 반환한다.",
                "name_ko와 short_name_ko에는 라틴 문자를 절대 남기지 않는다.",
                "한국어 출처에서 축구 선수로 확인되면 method='korean-web-source'를 사용한다.",
                "한국어 출처가 없으면 method='phonetic-web-checked'를 사용하고 sources는 빈 배열로 둔다.",
                "short_name_ko는 성 또는 한국 매체가 짧게 부를 표기다.",
                "응답은 지정된 JSON schema만 따른다.",
            ],
            "rows": payload,
        },
        ensure_ascii=False,
    )


def call_batch(
    client: OpenAI,
    *,
    model: str,
    rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    response = client.responses.create(
        model=model,
        tools=[
            {
                "type": "web_search",
                "filters": {"allowed_domains": KOREAN_SOURCE_DOMAINS},
            }
        ],
        input=build_prompt(rows),
        text={"format": {"type": "json_schema", **RESPONSE_SCHEMA}},
    )
    data = json.loads(response.output_text)
    return data["rows"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-csv", required=True)
    parser.add_argument("--audit-csv", required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    settings = get_settings()
    client = OpenAI(api_key=settings.openai_api_key)

    translation_path = Path(args.translation_csv)
    audit_path = Path(args.audit_csv)
    translation_rows = load_csv(translation_path)
    audit_rows = load_csv(audit_path)
    translation_by_external_id = {
        int(row["external_id"]): row for row in translation_rows
    }

    targets = [
        row
        for row in audit_rows
        if row["method"].startswith("unknown-phonetic")
        or bad_ko(row["name_ko"], row["short_name_ko"])
    ]
    if args.limit is not None:
        targets = targets[: args.limit]

    updated = 0
    for offset in range(0, len(targets), args.batch_size):
        batch = targets[offset : offset + args.batch_size]
        results = call_batch(client, model=args.model, rows=batch)
        result_by_id = {int(item["external_id"]): item for item in results}
        for audit_row in batch:
            external_id = int(audit_row["external_id"])
            result = result_by_id.get(external_id)
            if not result:
                raise RuntimeError(f"missing result for external_id={external_id}")
            name_ko = clean(str(result["name_ko"]))
            short_name_ko = clean(str(result["short_name_ko"]))
            if bad_ko(name_ko, short_name_ko):
                raise RuntimeError(
                    f"bad Korean result external_id={external_id}: "
                    f"{name_ko!r} / {short_name_ko!r}"
                )
            method = clean(str(result["method"]))
            sources = result.get("sources") or []
            audit_row["name_ko"] = name_ko
            audit_row["short_name_ko"] = short_name_ko
            audit_row["method"] = f"openai-web:{method}"
            audit_row["matched_name"] = "; ".join(str(source) for source in sources)
            translation_row = translation_by_external_id[external_id]
            translation_row["name_ko"] = name_ko
            translation_row["short_name_ko"] = short_name_ko
            updated += 1
        print(
            json.dumps(
                {
                    "updated": updated,
                    "total": len(targets),
                    "last_external_id": int(batch[-1]["external_id"]),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        time.sleep(0.5)

    audit_fieldnames = list(audit_rows[0].keys())
    translation_fieldnames = list(translation_rows[0].keys())
    write_csv(translation_path, translation_rows, translation_fieldnames)
    write_csv(audit_path, audit_rows, audit_fieldnames)
    print(json.dumps({"updated": updated, "total": len(targets)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
