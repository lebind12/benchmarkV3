"""Bounded internal generation pipeline; public routes never import this module."""

import re
from copy import deepcopy
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models import Fixture
from app.models.home_preview import (
    HomePreviewAttempt,
    HomePreviewPublication,
    HomePreviewSnapshot,
    HomePreviewVersion,
)
from app.schemas.home_preview import PreviewPayload
from app.services.home_preview import build_db_snapshot, eligible_rows, localize_injury_names
from app.services.home_preview_policy import digest, identity, slot_time, utcnow
from app.services.home_preview_retry import failure_details

GENERATION_VERSION = "home-preview-1.1-prompt-13"
LEASE_SECONDS = 1200


def snapshot_fingerprint(payload, *, model, now):
    canonical = deepcopy(payload)
    canonical.pop("as_of", None)
    canonical.pop("generated_at", None)
    canonical.pop("search_suggestions", None)
    for source in canonical["sources"]:
        source.pop("retrieved_at", None)
    for group in ("facts", "analysis", "external"):
        for block in canonical[group].values():
            block.pop("as_of", None)
    for row in canonical["external"]["odds"]["data"] or []:
        row.pop("collected_at", None)
    return digest(
        {
            "payload": canonical,
            "model": model,
            "generation_version": GENERATION_VERSION,
            "freshness_slot": slot_time(now),
        }
    )


def process_fixture(
    session_factory,
    external_id,
    *,
    provider=None,
    evidence_provider=None,
    cause_provider=None,
    clock=utcnow,
    model="facts-only",
    retry_failed=False,
    retry_research=False,
    runtime=None,
):
    now = clock()
    owner = str(uuid4())
    with session_factory() as session:
        fixture = session.scalar(
            select(Fixture).where(Fixture.external_id == external_id).with_for_update()
        )
        if fixture is None:
            return {"state": "not_found"}
        if fixture.status_short != "NS" or not now < fixture.kickoff_at <= now + timedelta(
            hours=24
        ):
            return {"state": "outside_window"}
        if fixture.id not in {
            row[0].id for row in eligible_rows(session, start=now, end=now + timedelta(hours=24))
        }:
            return {"state": "ineligible"}
        session.execute(
            insert(HomePreviewPublication)
            .values(fixture_id=fixture.id, identity=identity(fixture), refresh_state="idle")
            .on_conflict_do_nothing()
        )
        publication = session.get(HomePreviewPublication, fixture.id)
        if (
            publication.refresh_state == "running"
            and publication.last_attempt_at
            and now - publication.last_attempt_at < timedelta(seconds=LEASE_SECONDS)
        ):
            return {"state": "busy"}
        if publication.refresh_state == "running":
            publication.refresh_state = "failed"
            publication.reason = "generation_failed"
            for attempt in session.scalars(
                select(HomePreviewAttempt).where(
                    HomePreviewAttempt.fixture_id == fixture.id,
                    HomePreviewAttempt.state == "running",
                )
            ):
                attempt.state = "interrupted"
                attempt.finished_at = now
                attempt.reason = "generation_failed"
        slot = slot_time(now)
        existing = session.scalar(
            select(HomePreviewAttempt).where(
                HomePreviewAttempt.fixture_id == fixture.id, HomePreviewAttempt.slot == slot
            )
        )
        research_incomplete = False
        if retry_research and publication.version_id:
            from app.services.home_preview_causes import targets_from

            previous_body = session.get(HomePreviewVersion, publication.version_id).payload
            research_incomplete = any(
                not row.get("cause", {}).get("data")
                or not (
                    row["cause"]["data"]["occurred_on"] or row["cause"]["data"]["occurred_month"]
                )
                for row in targets_from(previous_body)
            )
        optional_retry = bool(
            existing
            and existing.state == "succeeded"
            and (existing.usage.get("cause_search_failed") or research_incomplete)
        )
        retry = bool(
            existing
            and (retry_failed or retry_research)
            and (existing.state in ("failed", "interrupted") or optional_retry)
            and (not runtime or existing.usage.get("model_requests", 0) < 6)
            and existing.usage.get("executions", 1) < 2
        )
        if existing and not retry:
            session.commit()
            return {"state": "already_processed"}
        count = session.scalar(
            select(func.count())
            .select_from(HomePreviewAttempt)
            .where(HomePreviewAttempt.fixture_id == fixture.id)
        )
        if not retry and count >= 4:
            session.commit()
            return {"state": "limit_reached"}
        if publication.identity != identity(fixture):
            publication.version_id = None
            publication.identity = identity(fixture)
        publication.refresh_state = "running"
        publication.last_attempt_at = now
        publication.reason = None
        if retry:
            attempt = existing
            attempt.state = "running"
            attempt.owner = owner
            attempt.started_at = now
            attempt.finished_at = None
            attempt.reason = None
            initial_usage = {**attempt.usage, "executions": attempt.usage.get("executions", 1) + 1}
            if retry_research:
                initial_usage["research_retries"] = initial_usage.get("research_retries", 0) + 1
        else:
            initial_usage = {"executions": 1, "model_requests": 0}
            attempt = HomePreviewAttempt(
                fixture_id=fixture.id,
                slot=slot,
                state="running",
                owner=owner,
                started_at=now,
                usage=initial_usage,
            )
        attempt.usage = deepcopy(initial_usage)
        session.add(attempt)
        session.flush()
        attempt_id = attempt.id
        fixture_id = fixture.id
        expected_identity = identity(fixture)
        previous_publication_id = publication.version_id
        snapshot = build_db_snapshot(session, fixture, now=now)
        session.commit()
    usage = dict(initial_usage)
    if retry:
        old_failure = {
            key: usage[key]
            for key in (
                "failure_type",
                "failure_code",
                "validation_code",
                "failure_detail",
                "cause_failure_type",
                "cause_failure_code",
            )
            if key in usage
        }
        if old_failure:
            usage["previous_failures"] = usage.get("previous_failures", []) + [old_failure]
        for key in (
            "failure_type",
            "failure_code",
            "validation_code",
            "failure_detail",
            "cause_search_failed",
            "cause_failure_type",
            "cause_failure_code",
        ):
            usage.pop(key, None)
    checkpoints = deepcopy(usage.get("checkpoints", {}))

    def persist_runtime(metadata):
        usage.update(metadata)
        with session_factory() as checkpoint_session:
            active = checkpoint_session.get(HomePreviewAttempt, attempt_id)
            if active.owner != owner or active.state != "running":
                raise ValueError("generation_ownership_lost")
            active.usage = deepcopy(usage)
            checkpoint_session.commit()

    def guard():
        current = clock()
        with session_factory() as check_session:
            actual = check_session.get(Fixture, fixture_id)
            active = check_session.get(HomePreviewAttempt, attempt_id)
            if active.owner != owner or active.state != "running":
                raise ValueError("generation_ownership_lost")
            if (
                identity(actual) != expected_identity
                or actual.status_short != "NS"
                or current >= actual.kickoff_at
                or current - now > timedelta(seconds=LEASE_SECONDS)
            ):
                raise ValueError("generation_no_longer_eligible")
            if fixture_id not in {
                row[0].id
                for row in eligible_rows(
                    check_session, start=current, end=current + timedelta(hours=24)
                )
            }:
                raise ValueError("target_disabled")

    def load_checkpoint(stage, *, input_hash=None):
        if not retry or stage not in checkpoints:
            return None
        with session_factory() as cp_session:
            record = cp_session.get(HomePreviewSnapshot, checkpoints[stage])
            if record is None or record.fixture_id != fixture_id:
                return None
            meta = record.payload.get("checkpoint", {})
            if (
                meta.get("identity") != expected_identity
                or meta.get("slot") != slot.isoformat()
                or meta.get("generation_version") != GENERATION_VERSION
                or meta.get("model") != model
                or meta.get("attempt_id") != attempt_id
                or (input_hash and meta.get("input_hash") != input_hash)
            ):
                return None
            candidate = deepcopy(record.payload["preview"])
            PreviewPayload.model_validate(candidate)
            if candidate["fixture"] != snapshot["fixture"] or clock() - record.as_of > timedelta(
                hours=6
            ):
                return None
            return candidate

    def save_checkpoint(stage, body, *, input_hash=None):
        if runtime is None:
            return
        if runtime:
            usage.update(runtime.summary())
        guard()
        with session_factory() as cp_session:
            active = cp_session.scalar(
                select(HomePreviewAttempt)
                .where(HomePreviewAttempt.id == attempt_id)
                .with_for_update()
            )
            if active.owner != owner or active.state != "running":
                raise ValueError("generation_ownership_lost")
            meta = {
                "stage": stage,
                "identity": expected_identity,
                "slot": slot.isoformat(),
                "model": model,
                "generation_version": GENERATION_VERSION,
                "attempt_id": attempt_id,
                "input_hash": input_hash,
            }
            record = HomePreviewSnapshot(
                fixture_id=fixture_id,
                fingerprint=digest({"checkpoint": meta, "preview": body, "owner": owner}),
                payload={"preview": deepcopy(body), "checkpoint": meta},
                as_of=datetime.fromisoformat(body["as_of"]),
            )
            cp_session.add(record)
            cp_session.flush()
            checkpoints[stage] = record.id
            usage["checkpoints"] = deepcopy(checkpoints)
            active.usage = deepcopy(usage)
            cp_session.commit()

    if runtime:
        runtime.start(
            usage=usage,
            deadline=min(
                now + timedelta(seconds=LEASE_SECONDS),
                datetime.fromisoformat(snapshot["fixture"]["kickoff_at"]),
            ),
            guard=guard,
            persist=persist_runtime,
        )
    try:
        resumed_evidence = load_checkpoint("evidence")
        payload = resumed_evidence or deepcopy(snapshot)
        if evidence_provider and resumed_evidence is None:
            payload, evidence_usage = evidence_provider(payload, now=clock())
            previous_counts = {
                key: usage.get(key, 0)
                for key in ("model_requests", "api_football_requests", "search_queries")
            }
            usage.update(evidence_usage)
            for key, count in previous_counts.items():
                if key in evidence_usage:
                    usage[key] = count + evidence_usage[key]
        from app.services.home_preview_injuries import enrich_importance
        from app.services.home_preview_players import enrich_player_spotlights

        if resumed_evidence is None:
            with session_factory() as session:
                enrich_importance(session, payload, now=now)
                enrich_player_spotlights(session, payload, now=now)
        PreviewPayload.model_validate(payload)
        if payload["is_mock"] is not False:
            raise ValueError("mock_payload_not_publishable")
        if payload["fixture"] != snapshot["fixture"]:
            raise ValueError("evidence_identity_mismatch")
        if resumed_evidence is None:
            save_checkpoint("evidence", payload)
        evidence_snapshot = {
            "preview": deepcopy(payload),
            "verification": usage.get("_evidence", []),
            "generation": {
                "model": model,
                "generation_version": GENERATION_VERSION,
                "schema_version": payload["schema_version"],
            },
        }
        input_hash = snapshot_fingerprint(payload, model=model, now=now)
        with session_factory() as session:
            previous = session.scalar(
                select(HomePreviewVersion).where(
                    HomePreviewVersion.fixture_id == fixture_id,
                    HomePreviewVersion.fingerprint == input_hash,
                )
            )
            previous_id = previous.id if previous and not optional_retry else None
        if previous_id is None:
            resumed_analysis = load_checkpoint("analysis", input_hash=input_hash)
            if resumed_analysis is not None:
                payload = resumed_analysis
            if provider and payload["sources"] and resumed_analysis is None:
                usage["model_requests"] = usage.get("model_requests", 0) + 1
                model_input = deepcopy(payload)
                with session_factory() as session:
                    localize_injury_names(session, model_input)
                for row in list(model_input["facts"]["injuries"]["data"] or []) + list(
                    (model_input["facts"].get("player_spotlights") or {}).get("data") or []
                ):
                    row.pop("photo_url", None)
                analysis, model_usage = provider(model_input)
                payload["analysis"] = analysis
                payload["generated_at"] = clock().isoformat()
                usage.update(model_usage)
            PreviewPayload.model_validate(payload)
            if resumed_analysis is None:
                save_checkpoint("analysis", payload, input_hash=input_hash)
            resumed_causes = (
                None if retry_research else load_checkpoint("causes", input_hash=input_hash)
            )
            if optional_retry and previous_publication_id:
                with session_factory() as reuse_session:
                    previous_payload = deepcopy(
                        reuse_session.get(HomePreviewVersion, previous_publication_id).payload
                    )

                def facts_without_causes(value):
                    value = deepcopy(value["facts"])
                    for row in value["injuries"]["data"] or []:
                        row.pop("cause", None)
                    return value

                if (
                    previous_payload["analysis"] == payload["analysis"]
                    and previous_payload["external"] == payload["external"]
                    and facts_without_causes(previous_payload) == facts_without_causes(payload)
                ):
                    payload = previous_payload
            if resumed_causes is not None:
                payload = resumed_causes
            if (
                resumed_causes is None
                and cause_provider
                and (payload["analysis"].get("key_absences") or {}).get("data")
                and clock() - now < timedelta(seconds=LEASE_SECONDS - 480)
            ):
                before_causes = deepcopy(payload)
                usage["model_requests"] = usage.get("model_requests", 0) + 1
                payload, cause_usage = cause_provider(deepcopy(payload), now=clock())

                def without_causes(value):
                    value = deepcopy(value)
                    for row in value["facts"]["injuries"]["data"] or []:
                        row.pop("cause", None)
                    return value["facts"]

                if (
                    payload["sources"][: len(before_causes["sources"])] != before_causes["sources"]
                    or payload["is_mock"] is not False
                    or payload["analysis"] != before_causes["analysis"]
                    or payload["fixture"] != before_causes["fixture"]
                    or payload["external"] != before_causes["external"]
                    or without_causes(payload) != without_causes(before_causes)
                ):
                    raise ValueError("cause_research_changed_selection")
                for key in ("api_football_requests", "search_queries"):
                    usage[key] = usage.get(key, 0) + cause_usage.get(key, 0)
                usage["_evidence"] = usage.get("_evidence", []) + cause_usage.pop("_evidence", [])
                usage.update(
                    {
                        key: value
                        for key, value in cause_usage.items()
                        if key not in ("model_requests", "api_football_requests", "search_queries")
                    }
                )
                evidence_snapshot["verification"] = usage.get("_evidence", [])
                evidence_snapshot["post_selection_causes"] = {
                    "players": [
                        {
                            "team_id": row["team_id"],
                            "player_id": row.get("player_id"),
                            "cause": row["cause"],
                        }
                        for row in payload["facts"]["injuries"]["data"] or []
                        if row.get("cause")
                    ],
                    "sources": [
                        row
                        for row in payload["sources"]
                        if row["id"] not in {source["id"] for source in before_causes["sources"]}
                    ],
                }
            PreviewPayload.model_validate(payload)
            if not usage.get("cause_search_failed") and resumed_causes is None:
                save_checkpoint("causes", payload, input_hash=input_hash)
        if runtime:
            usage.update(runtime.summary())
        finished = clock()
        with session_factory() as session:
            fixture = session.scalar(
                select(Fixture).where(Fixture.id == fixture_id).with_for_update()
            )
            publication = session.get(HomePreviewPublication, fixture_id)
            attempt = session.get(HomePreviewAttempt, attempt_id)
            if attempt.owner != owner or attempt.state != "running":
                return {"state": "ownership_lost"}
            if (
                identity(fixture) != expected_identity
                or fixture.status_short != "NS"
                or finished >= fixture.kickoff_at
                or finished - now > timedelta(seconds=LEASE_SECONDS)
            ):
                raise ValueError("generation_no_longer_eligible")
            if fixture.id not in {
                row[0].id
                for row in eligible_rows(
                    session, start=finished, end=finished + timedelta(hours=24)
                )
            }:
                raise ValueError("target_disabled")
            if previous_id is not None:
                version = session.get(HomePreviewVersion, previous_id)
            else:
                # Preserve complete sections of the previous valid version on degraded refresh.
                old = (
                    session.get(HomePreviewVersion, publication.version_id)
                    if publication.version_id
                    else None
                )
                if old:
                    old_blocks = {
                        f"{g}.{k}": b
                        for g in ("facts", "external", "analysis")
                        for k, b in old.payload[g].items()
                    }
                    new_blocks = {
                        f"{g}.{k}": b
                        for g in ("facts", "external", "analysis")
                        for k, b in payload[g].items()
                    }
                    if any(
                        b["status"] == "available"
                        and new_blocks[k]["status"] != "available"
                        and not (
                            k == "external.predictions"
                            and new_blocks[k].get("coverage")
                            and {row["source_id"] for row in b["data"] or []}.issubset(
                                {row["source_id"] for row in new_blocks[k]["data"] or []}
                            )
                        )
                        for k, b in old_blocks.items()
                    ):
                        raise ValueError("degraded_refresh")
                publication_hash = (
                    digest({"input_hash": input_hash, "optional_retry": usage["executions"]})
                    if optional_retry
                    else input_hash
                )
                evidence = HomePreviewSnapshot(
                    fixture_id=fixture_id,
                    fingerprint=publication_hash,
                    payload=evidence_snapshot,
                    as_of=datetime.fromisoformat(payload["as_of"]),
                )
                session.add(evidence)
                session.flush()
                version = HomePreviewVersion(
                    fixture_id=fixture_id,
                    snapshot_id=evidence.id,
                    fingerprint=publication_hash,
                    payload=payload,
                    generated_at=datetime.fromisoformat(payload["generated_at"])
                    if payload["generated_at"]
                    else None,
                )
                session.add(version)
                session.flush()
            publication.version_id = version.id
            publication.refresh_state = "idle"
            publication.reason = None
            attempt.state = "unchanged" if previous_id else "succeeded"
            attempt.finished_at = finished
            attempt.usage = usage
            session.commit()
        return {
            "state": "unchanged" if previous_id else "succeeded",
            "fixture_id": external_id,
            "usage": usage,
        }
    except Exception as exc:  # noqa: BLE001 - publication boundary preserves the last valid version
        if runtime:
            usage.update(runtime.summary())
        usage["failure_detail"] = failure_details(exc, now=clock())
        with session_factory() as session:
            fixture = session.scalar(
                select(Fixture).where(Fixture.id == fixture_id).with_for_update()
            )
            attempt = session.get(HomePreviewAttempt, attempt_id)
            publication = session.get(HomePreviewPublication, fixture_id)
            if attempt and attempt.owner == owner and attempt.state == "running":
                attempt.usage = {**usage, "failure_type": type(exc).__name__}
                if isinstance(exc, ValidationError):
                    codes = [
                        str((error.get("ctx") or {}).get("error", ""))
                        for error in exc.errors(include_input=False)
                    ]
                    codes = [code for code in codes if re.fullmatch(r"[a-z_]{1,80}", code)]
                    if codes:
                        attempt.usage["validation_code"] = codes[0]
                if isinstance(exc, ValueError) and str(exc) in {
                    "incomplete_model_response",
                    "empty_model_response",
                    "generation_no_longer_eligible",
                    "target_disabled",
                    "degraded_refresh",
                    "mock_payload_not_publishable",
                    "evidence_identity_mismatch",
                }:
                    attempt.usage["failure_code"] = str(exc)
                attempt.state = "failed"
                attempt.finished_at = clock()
                attempt.reason = "generation_failed"
                publication.refresh_state = "failed"
                publication.reason = "generation_failed"
                session.commit()
        return {"state": "failed", "fixture_id": external_id, "reason": "generation_failed"}
