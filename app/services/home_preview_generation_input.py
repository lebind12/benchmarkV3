"""Prepare immutable DB facts and already fetched original metadata before generation."""

from copy import deepcopy
from datetime import UTC

from app.schemas.home_preview import clock


def missing_cause():
    return {
        "status": "missing",
        "reason": "not_collected",
        "as_of": None,
        "source_ids": [],
        "data": None,
    }


def prepare_template(data, originals):
    p = deepcopy(data["output_template"])
    stamp = data["as_of"]
    p["as_of"] = p["generated_at"] = stamp
    p["search_suggestions"] = None
    p.pop("search_suggestions_extra", None)
    # Originals have been fetched before generation. Their metadata is input, not a model guess.
    p["sources"] = [s for s in p["sources"] if s["kind"] != "web"]
    for original in originals:
        page = original["page"]
        dates = page.get("dates") or []
        published = None
        day = None
        if dates:
            try:
                dt = clock(dates[0])
                published = dt.astimezone(UTC).isoformat() if dt.tzinfo else None
                day = dt.date().isoformat()
            except ValueError:
                if len(dates[0]) == 10:
                    day = dates[0]
        source = {
            "id": original["id"],
            "fixture_id": p["fixture"]["external_id"],
            "kind": "web",
            "title": original["publisher"] + " | " + page["title"],
            "url": page["url"],
            "published_at": published,
            "retrieved_at": stamp,
        }
        if day:
            source["published_on"] = day
        p["sources"].append(source)
    for row in p["facts"]["injuries"].get("data") or []:
        row["cause"] = missing_cause()
    db_ids = [r["id"] for r in p["sources"] if r["kind"] == "db"]
    all_ids = [r["id"] for r in p["sources"]]
    for key in ("summary", "key_points", "ai_prediction", "key_absences", "player_watchpoints"):
        p["analysis"].setdefault(
            key, {"status": "missing", "reason": "generation_pending", "as_of": None, "data": None}
        )
        p["analysis"][key]["source_ids"] = db_ids if key == "player_watchpoints" else all_ids
    data["output_template"] = p
    return p
