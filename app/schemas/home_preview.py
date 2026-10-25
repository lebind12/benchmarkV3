"""Pydantic boundary backed by the generated FE structural contracts.

The generated schema is the single structural definition. Semantic validators
below enforce provenance and publication invariants beyond JSON Schema.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from pydantic import RootModel, model_validator

SCHEMAS = Path(__file__).resolve().parents[2] / "docs/spec/schemas"


def clock(value: str) -> datetime:
    return datetime.fromisoformat(value)


def require(condition: bool, reason: str):
    if not condition:
        raise ValueError(reason)


FORMAT_CHECKER = FormatChecker()


@FORMAT_CHECKER.checks("date-time", raises=(ValueError, TypeError))
def valid_datetime(value):
    if not isinstance(value, str):
        return True
    return (
        bool(
            re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
            )
        )
        and clock(value).tzinfo is not None
    )


def structure(name, value):
    import json

    schema = json.loads((SCHEMAS / f"home-preview-{name}.schema.json").read_text())
    errors = sorted(
        Draft202012Validator(schema, format_checker=FORMAT_CHECKER).iter_errors(value),
        key=lambda e: str(e.path),
    )
    require(not errors, f"invalid_{name}_structure")


def validate_payload(v):
    structure("payload", v)
    fixture = v["fixture"]
    kickoff = clock(fixture["kickoff_at"])
    as_of = clock(v["as_of"])
    generated = clock(v["generated_at"]) if v["generated_at"] else as_of
    require(as_of <= generated < kickoff, "invalid_snapshot_clock")
    require(fixture["home"]["external_id"] != fixture["away"]["external_id"], "same_teams")
    require(
        v["generated_at"] is not None or all(b["data"] is None for b in v["analysis"].values()),
        "analysis_without_generation",
    )
    sources = {row["id"]: row for row in v["sources"]}
    require(len(sources) == len(v["sources"]), "duplicate_source")

    def refs(ids, kinds=None):
        for source_id in ids:
            require(source_id in sources, "unknown_source")
            require(not kinds or sources[source_id]["kind"] in kinds, "wrong_source_kind")

    for source in sources.values():
        require(source["fixture_id"] == fixture["external_id"], "source_fixture_mismatch")
        require(clock(source["retrieved_at"]) <= as_of, "future_source")
        if source["published_at"]:
            require(
                clock(source["published_at"]) <= clock(source["retrieved_at"])
                and clock(source["published_at"]) < kickoff,
                "future_publication",
            )
        if source["url"]:
            require(source["url"].startswith(("http://", "https://")), "unsafe_url_scheme")
        if not v["is_mock"] and source["kind"] != "db":
            require(bool(source["url"]), "missing_external_url")
    for group in ("facts", "analysis", "external"):
        for block in v[group].values():
            refs(block["source_ids"])
            if block["status"] in ("missing", "unverified", "error"):
                require(block["data"] is None and bool(block["reason"]), "unavailable_data")
            else:
                require(
                    block["data"] is not None
                    and bool(block["as_of"])
                    and bool(block["source_ids"]),
                    "missing_available_evidence",
                )
            if block["status"] == "partial":
                require(bool(block["reason"]), "missing_partial_reason")
            if block["as_of"]:
                require(clock(block["as_of"]) <= generated, "future_section")
    for side in ("home", "away"):
        block = v["facts"][f"{side}_form"]
        refs(block["source_ids"], ["db"])
        if block["data"] is None:
            continue
        data = block["data"]
        matches = data["matches"]
        require(data["team_id"] == fixture[side]["external_id"], "form_team_mismatch")
        require(block["status"] != "available" or len(matches) == 5, "full_form_count")
        require(block["status"] != "partial" or 1 <= len(matches) <= 4, "partial_form_count")
        require(len({row["fixture_id"] for row in matches}) == len(matches), "duplicate_form")
        for row in matches:
            require(
                row["fixture_id"] != fixture["external_id"]
                and clock(row["kickoff_at"]) < kickoff
                and clock(row["kickoff_at"]) <= as_of,
                "future_form",
            )
            require(row["status"] == "PEN" or row["penalties"] is None, "non_penalty_score")
            if row["penalties"]:
                require(
                    row["goals_for"] == row["goals_against"]
                    and row["penalties"]["for"] != row["penalties"]["against"],
                    "invalid_shootout",
                )
    injuries = v["facts"]["injuries"]
    if injuries["status"] == "available" and injuries["data"] == []:
        require(injuries["reason"] == "confirmed_no_absences", "unconfirmed_empty_injuries")
    for row in injuries["data"] or []:
        require(
            not row.get("photo_url") or row["photo_url"].startswith(("http://", "https://")),
            "unsafe_photo_url",
        )
        require(
            row["team_id"] in [fixture[s]["external_id"] for s in ("home", "away")], "injury_team"
        )
        refs(row["source_ids"])
    spotlights = v["facts"].get("player_spotlights") or {}
    known, seen_players = {}, set()
    for player in spotlights.get("data") or []:
        require(
            not player.get("photo_url") or player["photo_url"].startswith(("http://", "https://")),
            "unsafe_photo_url",
        )
        key = (player["team_id"], player["player_id"])
        require(
            key not in seen_players
            and key[0] in [fixture[s]["external_id"] for s in ("home", "away")],
            "invalid_spotlight_identity",
        )
        seen_players.add(key)
        known[key] = player
        refs(player["source_ids"], ["db"])
        form = player.get("recent_form")
        if form:
            require(
                form["team_match_count"] == player["recent_match_count"]
                and form["observed_appearances"] <= form["team_match_count"],
                "invalid_recent_player_sample",
            )
            for field, sample in (
                ("goals", "goal_samples"),
                ("assists", "assist_samples"),
                ("minutes", "minute_samples"),
            ):
                require(
                    form[sample] <= form["observed_appearances"]
                    and (form[field] is None) == (form[sample] == 0),
                    "invalid_recent_player_unknowns",
                )
        for focus in ("scoring_streak", "assist_streak", "involvement_streak"):
            require(player[focus] <= player["recent_match_count"], "streak_exceeds_sample")
            require(
                not player["record_notes"][focus] or player[focus] >= 2, "unverified_streak_note"
            )
    watched, watch_counts = set(), {}
    for pick in (v["analysis"].get("player_watchpoints") or {}).get("data") or []:
        key = (pick["team_id"], pick["player_id"])
        require(
            key in known and known[key]["record_notes"].get(pick["focus"]),
            "unknown_player_watchpoint",
        )
        require(key not in watched, "duplicate_player_watchpoint")
        watched.add(key)
        watch_counts[key[0]] = watch_counts.get(key[0], 0) + 1
        require(watch_counts[key[0]] <= 2, "player_watchpoint_team_limit")
        refs(pick["evidence_ids"], ["db"])
        require(
            bool(set(pick["evidence_ids"]) & set(known[key]["source_ids"])),
            "missing_player_record_evidence",
        )
    selected = v["analysis"].get("key_absences") or {}
    seen, counts = set(), {}
    for pick in selected.get("data") or []:
        key = (pick["team_id"], pick["player_id"])
        candidate = next(
            (
                row
                for row in injuries["data"] or []
                if (row["team_id"], row.get("player_id")) == key
            ),
            None,
        )
        require(candidate is not None, "unknown_key_absence")
        require(
            candidate.get("importance_evidence", {}).get("eligible")
            and not candidate.get("status_conflict"),
            "ineligible_key_absence",
        )
        expected_reason = candidate["importance_evidence"].get("selection_reason")
        require(
            not expected_reason or pick["reason"] == expected_reason, "key_absence_reason_mismatch"
        )
        require(key not in seen, "duplicate_key_absence")
        seen.add(key)
        counts[key[0]] = counts.get(key[0], 0) + 1
        require(counts[key[0]] <= 2, "key_absence_team_limit")
        evidence = set(pick["evidence_ids"])
        require(
            bool(evidence & set(candidate["source_ids"]))
            and bool(evidence & set(candidate["importance_evidence"]["source_ids"])),
            "key_absence_missing_evidence",
        )
    for row in injuries["data"] or []:
        if row.get("importance_evidence"):
            refs(row["importance_evidence"]["source_ids"], ["db"])
    for block in v["analysis"].values():
        rows = (
            block["data"]
            if isinstance(block["data"], list)
            else [block["data"]]
            if block["data"]
            else []
        )
        for row in rows:
            refs(row["evidence_ids"])
            require(set(row["evidence_ids"]) <= set(block["source_ids"]), "unregistered_evidence")
    for row in v["external"]["predictions"]["data"] or []:
        refs([row["source_id"]], ["web", "api"])
    for row in v["external"]["odds"]["data"] or []:
        refs([row["source_id"]], ["web", "api"])
        require(
            clock(row["collected_at"]) < kickoff and clock(row["collected_at"]) <= generated,
            "future_odds",
        )
    return v


class PreviewPayload(RootModel[dict[str, Any]]):
    @model_validator(mode="after")
    def validate_contract(self):
        validate_payload(self.root)
        return self


class PreviewResponse(RootModel[dict[str, Any]]):
    @model_validator(mode="after")
    def validate_contract(self):
        v = self.root
        structure("response", v)
        preview, pub, refresh = v["preview"], v["publication"], v["refresh"]
        if preview is None:
            require(
                pub["state"] not in ("ready", "partial")
                and pub["served"] is None
                and pub["generated_at"] is None
                and pub["as_of"] is None
                and pub["reason"] is not None,
                "missing_snapshot",
            )
        else:
            validate_payload(preview)
            complete = all(
                b["status"] == "available"
                for g in ("facts", "analysis", "external")
                for b in preview[g].values()
            )
            require(
                pub["state"] == ("ready" if complete else "partial") and pub["served"] is not None,
                "invalid_coverage",
            )
            require(v["fixture_id"] == preview["fixture"]["external_id"], "cross_fixture")
            require(
                all(pub[k] == preview[k] for k in ("generated_at", "as_of"))
                and pub["reason"] is None,
                "publication_clocks",
            )
            require((pub["served"] == "current") == (refresh["state"] == "idle"), "refresh_pointer")
        if preview is None and pub["state"] == "failed":
            require(refresh["state"] == "failed", "failed_attempt_missing")
        if preview is None and pub["state"] == "unavailable":
            require(refresh["state"] == "idle", "unavailable_attempt")
        if refresh["state"] == "failed":
            require(
                bool(refresh["reason"]) and bool(refresh["last_attempt_at"]),
                "missing_failure_metadata",
            )
        if refresh["state"] == "running":
            require(bool(refresh["last_attempt_at"]), "missing_attempt_clock")
        if refresh["state"] == "idle":
            require(refresh["reason"] is None, "idle_failure")
        if (
            pub["served"] == "previous"
            and preview
            and preview["generated_at"]
            and refresh["last_attempt_at"]
        ):
            require(
                clock(refresh["last_attempt_at"]) >= clock(preview["generated_at"]), "old_refresh"
            )
        return self
