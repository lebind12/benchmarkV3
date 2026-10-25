"""Resolve captured single-call URLs from Google grounding. No model calls or publication."""

import argparse
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from app.services.home_preview_grounding import resolve_sources
from app.services.home_preview_web import fetch_page


def json_schema(schema):
    if isinstance(schema, list):
        return [json_schema(value) for value in schema]
    if not isinstance(schema, dict):
        return schema
    value = {key: json_schema(item) for key, item in schema.items()}
    if "type" in value:
        value["type"] = value["type"].lower()
        if value["type"] == "object":
            value["additionalProperties"] = False
    if value.pop("nullable", False):
        value["type"] = [value["type"], "null"]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--reference-url", action="append", default=[])
    args = parser.parse_args()
    raw = (args.run_dir / "response.txt").read_text()
    grounding = json.loads((args.run_dir / "grounding.json").read_text())
    request = json.loads((args.run_dir / "request.json").read_text())
    Draft202012Validator(json_schema(request["generationConfig"]["responseSchema"])).validate(
        json.loads(raw)
    )
    # Extend the static publisher list only from provider metadata, never model JSON.
    hosts = set()
    for chunk in grounding.get("groundingChunks", []):
        web = chunk.get("web") or {}
        domain = web.get("domain") or web.get("title", "")
        if re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}", domain):
            hosts.add(domain.lower())

    def fetch(url):
        return fetch_page(url, allowed_hosts=hosts)

    result, report, pages = resolve_sources(
        raw, grounding, fetcher=fetch, reference_urls=args.reference_url
    )
    for filename, data in [
        ("resolved.json", result),
        ("source-resolution.json", report),
        ("original-pages.json", pages),
    ]:
        (args.run_dir / filename).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "state": "resolved",
                "model_requests": 0,
                "claim_links": report["claim_links"],
                "sources": report["sources"],
                "fetch_failures": report["fetch_failures"],
                "segment_diagnostics": report["segment_diagnostics"],
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
