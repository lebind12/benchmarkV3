"""Post-storage field checks. Natural-language meaning is reviewed against sources.

No sentence extraction, keyword acceptance, or field reconstruction is performed.
"""

from urllib.parse import urlsplit

from app.services.home_preview_forecasts import forecast_source_keys


def form_metrics(payload):
    result = {}
    for side in ("home", "away"):
        team = payload["fixture"][side]
        matches = (payload["facts"][side + "_form"].get("data") or {}).get("matches", [])
        wins = sum(m["goals_for"] > m["goals_against"] for m in matches)
        draws = sum(m["goals_for"] == m["goals_against"] for m in matches)
        count = len(matches)
        result[str(team["external_id"])] = {
            "name": team["name"],
            "match_count": count,
            "wins": wins,
            "draws": draws,
            "losses": count - wins - draws,
            "goals_for": sum(m["goals_for"] for m in matches),
            "goals_against": sum(m["goals_against"] for m in matches),
            "clean_sheets": sum(m["goals_against"] == 0 for m in matches),
            "at_most_one_goal_games": sum(m["goals_for"] <= 1 for m in matches),
        }
    return result


def section_target_report(payload, *, source_urls=None, expected_incidents=()):
    sections = {}

    def put(name, checks):
        sections[name] = {"passed": all(checks.values()), "checks": checks}

    registry = {s["id"]: s for s in payload["sources"]}
    a = payload["analysis"]
    teams = {payload["fixture"][s]["external_id"] for s in ("home", "away")}
    put("summary", {"text_present": bool((a["summary"].get("data") or {}).get("text"))})
    points = a["key_points"].get("data") or []
    put(
        "key_points",
        {
            "one_or_two": 1 <= len(points) <= 2,
            "content_present": all(
                p["title"] and p["description"] and p["evidence_ids"] for p in points
            ),
        },
    )
    watches = (a.get("player_watchpoints") or {}).get("data") or []
    spot = {
        (r["team_id"], r["player_id"]): r
        for r in (payload["facts"].get("player_spotlights") or {}).get("data") or []
    }
    put(
        "player_watchpoints",
        {
            "both_teams": {p["team_id"] for p in watches} == teams,
            "max_two_each": all(sum(p["team_id"] == t for p in watches) <= 2 for t in teams),
            "reason_and_records_present": bool(watches)
            and all(
                p.get("reason")
                and p.get("evidence_ids")
                and spot.get((p["team_id"], p["player_id"]), {})
                .get("record_notes", {})
                .get(p["focus"])
                for p in watches
            ),
            "photos_present": all(
                spot.get((p["team_id"], p["player_id"]), {}).get("photo_url") for p in watches
            ),
        },
    )
    selected = (a.get("key_absences") or {}).get("data") or []
    injuries = {
        (r["team_id"], r.get("player_id")): r
        for r in payload["facts"]["injuries"].get("data") or []
    }
    expected = {r["player_id"]: r for r in expected_incidents}
    occurrence = []
    causes = []
    for pick in selected:
        row = injuries[(pick["team_id"], pick["player_id"])]
        block = row.get("cause") or {}
        data = block.get("data") or {}
        e = expected.get(pick["player_id"], {})
        if e.get("occurred_on"):
            occurrence.append(
                {
                    "player_id": pick["player_id"],
                    "expected": e["occurred_on"],
                    "actual": data.get("occurred_on"),
                    "passed": data.get("occurred_on") == e["occurred_on"]
                    and (not e.get("source_id") or e["source_id"] in block.get("source_ids", [])),
                }
            )
        if e.get("code"):
            causes.append(
                {
                    "player_id": pick["player_id"],
                    "expected_code": e["code"],
                    "actual_code": data.get("code"),
                    "passed": data.get("code") == e["code"]
                    and (
                        not e.get("cause_source_id")
                        or e["cause_source_id"] in block.get("source_ids", [])
                    ),
                }
            )
    put(
        "key_absences",
        {
            "selection_present": bool(selected),
            "max_two_each": all(sum(p["team_id"] == t for p in selected) <= 2 for t in teams),
            "selected_cause_fields_present": all(
                (
                    (injuries[(p["team_id"], p["player_id"])].get("cause") or {}).get("data") or {}
                ).get("label")
                for p in selected
            ),
            "confirmed_dates_in_typed_fields": all(r["passed"] for r in occurrence),
            "confirmed_causes_in_typed_fields": all(r["passed"] for r in causes),
        },
    )
    ai = a["ai_prediction"].get("data") or {}
    put(
        "ai_prediction",
        {
            "score_confidence_reason": type(ai.get("home_goals")) is int
            and type(ai.get("away_goals")) is int
            and ai.get("confidence") in ("low", "medium", "high")
            and bool(ai.get("reason"))
        },
    )
    forecasts = payload["external"]["predictions"].get("data") or []
    hosts = {
        (
            urlsplit(
                (source_urls or {}).get(p["source_id"]) or registry[p["source_id"]].get("url") or ""
            ).hostname
            or ""
        ).removeprefix("www.")
        for p in forecasts
        if registry[p["source_id"]]["kind"] == "web"
    }
    _, api_forecasts = forecast_source_keys(payload)
    hosts = {"bbc.com" if host == "bbc.co.uk" else host for host in hosts}
    put(
        "external_forecasts",
        {
            "three_total_forecasts": len(hosts - {""}) + len(api_forecasts) >= 3,
            "outlooks_and_reasons": bool(forecasts)
            and all(p.get("outlook") and p.get("summary") for p in forecasts),
        },
    )
    put(
        "recent_form",
        {
            s: len((payload["facts"][s + "_form"].get("data") or {}).get("matches") or []) == 5
            for s in ("home", "away")
        },
    )
    odds = payload["external"]["odds"].get("data") or []
    put(
        "odds",
        {
            "collected_home_draw_away": bool(odds)
            and all(
                all(k in r for k in ("home", "draw", "away", "bookmaker", "collected_at"))
                for r in odds
            )
        },
    )
    return {
        "passed": all(r["passed"] for r in sections.values()),
        "sections": sections,
        "failed_sections": [k for k, v in sections.items() if not v["passed"]],
        "occurrence_checks": occurrence,
        "structured_cause_checks": causes,
        "manual_review_required": [
            "claims_against_originals",
            "player_reason_logic",
            "selection_importance",
            "prediction_logic",
        ],
    }


def require_section_targets(payload, *, expected_incidents=()):
    report = section_target_report(payload, expected_incidents=expected_incidents)
    if not report["passed"]:
        exc = ValueError("section_targets_failed:" + ",".join(report["failed_sections"]))
        exc.target_report = report
        raise exc
    return report


def assert_content_preserved(raw, stored):
    if raw != stored:
        raise ValueError("llm_json_changed_during_storage")
