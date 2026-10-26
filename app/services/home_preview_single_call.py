"""One grounded request using the existing public payload contract, never a second UI shape."""

import json
from copy import deepcopy
from pathlib import Path

from app.schemas.home_preview import PreviewPayload, structure
from app.services.home_preview_grounding import resolve_sources
from app.services.home_preview_targets import require_section_targets

SCHEMA = Path(__file__).resolve().parents[2] / "docs/spec/schemas/home-preview-payload.schema.json"


def vertex_schema(node):
    """Translate JSON Schema syntax without changing the public field names or nullability."""
    node = deepcopy(node)
    choices = node.pop("anyOf", None)
    if choices:
        real = [v for v in choices if v.get("type") != "null"]
        if len(real) != 1:
            raise ValueError("unsupported_schema_union")
        node.update(real[0])
        node["nullable"] = len(real) != len(choices)
    result = {}
    for key in (
        "type",
        "format",
        "enum",
        "required",
        "nullable",
        "minItems",
        "maxItems",
        "minimum",
        "maximum",
    ):
        if key in node:
            result[key] = node[key].upper() if key == "type" else node[key]
    if result.get("format") not in (None, "date-time", "date", "time"):
        result.pop("format")
    if "const" in node:
        if isinstance(node["const"], str):
            result["enum"] = [node["const"]]
        elif type(node["const"]) in (int, float):
            result["minimum"] = result["maximum"] = node["const"]
        else:
            raise ValueError("unsupported_vertex_constant")
    if "properties" in node:
        result["properties"] = {k: vertex_schema(v) for k, v in node["properties"].items()}
        result["propertyOrdering"] = list(node["properties"])
    if "items" in node:
        result["items"] = vertex_schema(node["items"])
    return result


def payload_vertex_schema():
    schema = vertex_schema(json.loads(SCHEMA.read_text()))

    # Vertex compiles bounded arrays and repeated enums into a large state machine.
    # Keep the exact keys/types/required/nullability; enforce the complete canonical
    # constraints with structure()/PreviewPayload before any database write.
    def compact(node):
        if not isinstance(node, dict):
            return
        if len(node.get("enum", [])) > 1:
            node.pop("enum")
        for key in ("minItems", "maxItems", "format"):
            node.pop(key, None)
        if node.get("minimum") != node.get("maximum"):
            node.pop("minimum", None)
            node.pop("maximum", None)
        for child in node.get("properties", {}).values():
            compact(child)
        if "items" in node:
            compact(node["items"])

    compact(schema)
    for group, keys in (
        ("analysis", ["key_absences", "player_watchpoints"]),
        ("facts", ["player_spotlights"]),
    ):
        block = schema["properties"][group]
        block["required"] = list(dict.fromkeys(block["required"] + keys))
    watch = schema["properties"]["analysis"]["properties"]["player_watchpoints"]["properties"][
        "data"
    ]["items"]
    watch["required"] = list(dict.fromkeys(watch["required"] + ["reason"]))
    watch["properties"]["reason"]["description"] = (
        "시즌/완전한최근/확인연속/팀흐름 중 서로 다른 확인 기록을 연결한 한국어 선정 이유. 문장 수/길이보다 실제 근거와 해석을 우선하며 불완전한 표본을 확대하지 않는다."
    )
    schema["properties"]["analysis"]["properties"]["ai_prediction"]["properties"]["data"][
        "properties"
    ]["reason"][
        "description"
    ] = "한국어 최소3문장. 최근 폼과 실제 주요 결장 변수를 함께 설명하고 독립적 예상 근거 및 반대 변수를 포함한다. 무실점 표현도 허용. 확인되지 않은 전술·심리 표현 금지."
    schema["properties"]["facts"]["properties"]["injuries"]["properties"]["data"]["items"][
        "properties"
    ]["detail"][
        "description"
    ] = "선정한 선수만 실제 부상·경위·확인 날짜를 짧게 작성한다. 비선정 선수는 원래 영어 문자열까지 그대로 복사한다."
    schema["properties"]["external"]["properties"]["predictions"]["properties"]["data"]["items"][
        "properties"
    ]["summary"][
        "description"
    ] = "원문 매체가 제시한 전망의 실제 이유를40자 이상 설명한다. 예상 스코어만 반복하거나 본문에 출처ID를 쓰지 않는다."
    spot = schema["properties"]["facts"]["properties"]["player_spotlights"]["properties"]["data"][
        "items"
    ]
    spot["required"] = list(spot["properties"])
    return schema


def order_for_schema(value, schema):
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        return {
            key: order_for_schema(value[key], properties.get(key, {}))
            for key in [*properties, *[k for k in value if k not in properties]]
            if key in value
        }
    if isinstance(value, list):
        return [order_for_schema(v, schema.get("items", {})) for v in value]
    return value


def validate_existing_response(value, template):
    try:
        structure("payload", value)
    except ValueError as exc:
        from jsonschema import Draft202012Validator

        from app.schemas.home_preview import FORMAT_CHECKER

        def leaves(error):
            if error.context:
                return [leaf for child in error.context for leaf in leaves(child)]
            return [error]

        errors = [
            leaf
            for error in Draft202012Validator(
                json.loads(SCHEMA.read_text()), format_checker=FORMAT_CHECKER
            ).iter_errors(value)
            for leaf in leaves(error)
        ]
        detail = "; ".join(
            "/".join(map(str, e.absolute_path)) + ": " + e.message[:180]
            for e in errors
            if e.validator != "type"
        )
        raise ValueError("invalid_payload_structure: " + detail[:1800]) from exc
    if (
        value["fixture"] != template["fixture"]
        or value["is_mock"]
        or value["schema_version"] != "1.1"
    ):
        raise ValueError("single_call_fixture_mismatch")
    for name in ("home_form", "away_form", "player_spotlights"):
        if value["facts"].get(name) != template["facts"].get(name):
            raise ValueError("single_call_changed_db_" + name)
    if value["external"]["odds"] != template["external"]["odds"]:
        raise ValueError("single_call_changed_odds")
    if {s["id"]: s for s in value["sources"] if s["kind"] != "web"} != {
        s["id"]: s for s in template["sources"] if s["kind"] != "web"
    }:
        raise ValueError("single_call_changed_db_sources")
    originals = {
        (r["team_id"], r.get("player_id")): r for r in template["facts"]["injuries"]["data"] or []
    }
    actual = value["facts"]["injuries"]["data"] or []
    if len(actual) != len(originals) or {(r["team_id"], r.get("player_id")) for r in actual} != set(
        originals
    ):
        raise ValueError("single_call_changed_injury_candidates")
    for row in actual:
        original = originals[row["team_id"], row.get("player_id")]
        for key in set(original) | set(row):
            if key not in {"cause", "detail", "source_ids"} and row.get(key) != original.get(key):
                raise ValueError("single_call_changed_injury_" + key)
    selected = {
        (p["team_id"], p["player_id"])
        for p in (value["analysis"].get("key_absences") or {}).get("data") or []
    }
    registry = {s["id"]: s for s in value["sources"]}
    violations = []
    for row in actual:
        key = row["team_id"], row.get("player_id")
        original = originals[key]
        extra = set(row["source_ids"]) - set(original["source_ids"])
        if not set(original["source_ids"]) <= set(row["source_ids"]) or any(
            sid not in registry for sid in extra
        ):
            violations.append(
                {
                    "player_id": row.get("player_id"),
                    "error": "single_call_changed_injury_sources",
                    "required_original_source_ids": original["source_ids"],
                    "unknown_web_ids": [sid for sid in extra if sid not in registry],
                }
            )
        if key not in selected and row != original:
            fields = {
                k: {"expected": original.get(k), "returned": row.get(k)}
                for k in ("detail", "source_ids", "cause")
                if row.get(k) != original.get(k)
            }
            violations.append(
                {
                    "player_id": row.get("player_id"),
                    "error": "single_call_changed_unselected_injury",
                    "restore_fields": fields,
                }
            )
        if (
            row["detail"] != original["detail"]
            and not any(registry.get(sid, {}).get("kind") == "web" for sid in row["source_ids"])
            and not (row.get("cause") or {}).get("data")
            and (
                row["detail"] not in {"부상", "부상 부위 미공개"}
                or original["detail"].lower() != "injury"
            )
        ):
            violations.append(
                {
                    "player_id": row.get("player_id"),
                    "error": "single_call_unattributed_injury_detail",
                }
            )
    if violations:
        raise ValueError(
            "single_call_contract_violations:" + json.dumps(violations, ensure_ascii=False)
        )
    prediction = value["analysis"]["ai_prediction"]
    if prediction["status"] != "available" or not prediction["data"]:
        raise ValueError("single_call_missing_ai_prediction")
    if any(
        term in prediction["data"]["reason"]
        for term in ("API-Football 자체 알고리즘", "더블 찬스를 전망")
    ):
        raise ValueError("single_call_copied_api_prediction")
    for pick in (value["analysis"].get("player_watchpoints") or {}).get("data") or []:
        if not pick.get("reason", "").strip():
            raise ValueError("single_call_missing_watch_reason")
    return value


def resolve_existing_response(
    raw, grounding, template, *, fetcher, now, original_sources=(), expected_incidents=()
):
    value = validate_existing_response(json.loads(raw), template)
    # Add only an internal citation index AFTER the original bytes. Provider offsets stay intact.
    catalog = [
        {"id": s["id"], "title": s["title"], "publisher": s["title"].split(" | ", 1)[0]}
        for s in value["sources"]
        if s["kind"] == "web"
    ]
    augmented = (
        raw.rstrip()[:-1] + ',"source_catalog":' + json.dumps(catalog, ensure_ascii=False) + "}"
    )
    resolved, report, pages = resolve_sources(augmented, grounding, fetcher=fetcher)
    sources = {s["id"]: s for s in resolved["source_catalog"]}
    # These originals were fetched by the caller BEFORE generation and supplied in the
    # request with fixed IDs; never obtain an original URL from the model response.
    for original in original_sources:
        if original["id"] not in sources:
            continue
        source = sources[original["id"]]
        page = original["page"]
        source.update(
            url=page["url"],
            title=page["title"],
            verification="server_original_linked",
            published_at=None,
            published_on=None,
        )
        for stamp in page.get("dates", [])[:1]:
            try:
                from app.schemas.home_preview import clock

                parsed = clock(stamp)
                if parsed.tzinfo:
                    source.update(
                        published_at=parsed.isoformat(), published_on=parsed.date().isoformat()
                    )
            except ValueError:
                if len(stamp) == 10:
                    source["published_on"] = stamp
        for row in report["sources"]:
            if row["id"] == original["id"]:
                row.update(
                    state="server_original_linked", url=page["url"], origin="server_original_input"
                )
        if not any(p["url"] == page["url"] for p in pages):
            pages.append(
                {
                    "page": page,
                    "url": page["url"],
                    "origin": "server_original_input",
                    "chunk_index": None,
                }
            )
    result = deepcopy(value)
    result["as_of"] = result["generated_at"] = now.isoformat()
    unavailable = {sid for sid, s in sources.items() if not s.get("url")}
    # Preserve every model-returned cause/date. Unresolved evidence rejects the candidate
    # as a whole; it must never silently delete the content and publish a degraded version.
    used = set()

    def refs(v):
        if isinstance(v, dict):
            used.update(v.get("source_ids", []))
            used.update(v.get("evidence_ids", []))
            if isinstance(v.get("source_id"), str):
                used.add(v["source_id"])
            for child in v.values():
                refs(child)
        elif isinstance(v, list):
            for child in v:
                refs(child)

    for group in ("analysis", "facts", "external"):
        refs(result[group])
    unresolved_used = sorted(used & unavailable)
    if unresolved_used:
        exc = ValueError("single_call_unresolved_sources:" + ",".join(unresolved_used))
        exc.preview_resolution = report
        exc.preview_pages = pages
        raise exc
    registered = []
    for source in value["sources"]:
        if source["kind"] != "web":
            registered.append(deepcopy(source))
            continue
        if source["id"] not in used:
            continue
        original = sources[source["id"]]
        registered.append(
            {
                "id": source["id"],
                "fixture_id": value["fixture"]["external_id"],
                "kind": "web",
                "title": original["title"],
                "url": original["url"],
                "published_at": original.get("published_at"),
                "retrieved_at": now.isoformat(),
                **(
                    {"published_on": original["published_on"]}
                    if original.get("published_on")
                    else {}
                ),
            }
        )
    result["sources"] = registered
    suggestion = (grounding.get("searchEntryPoint") or {}).get("renderedContent")
    result["search_suggestions"] = (
        {
            "provider": "google",
            "rendered_content": suggestion,
            "queries": grounding.get("webSearchQueries") or [],
        }
        if suggestion
        else None
    )
    from app.services.home_preview_web import update_prediction_coverage

    update_prediction_coverage(result, candidate_count=len(catalog), checked_at=now)
    try:
        PreviewPayload.model_validate(result)
        # Legacy URL resolver only. Native direct-storage runner bypasses this path.
        if value["analysis"] != result["analysis"] or value["facts"] != result["facts"]:
            raise ValueError("llm_content_changed_before_storage")
        report["targets"] = require_section_targets(result, expected_incidents=expected_incidents)
    except ValueError as exc:
        exc.preview_resolution = report
        exc.preview_pages = pages
        exc.preview_candidate = result
        raise
    report["dropped_unverified_causes"] = []
    return result, report, pages
