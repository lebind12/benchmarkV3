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

GENERATION_VERSION = "home-preview-1.1-prompt-8"
LEASE_SECONDS = 300


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
    clock=utcnow,
    model="facts-only",
    retry_failed=False,
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
        retry = bool(
            existing
            and retry_failed
            and existing.state == "failed"
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
        session.add(attempt)
        session.flush()
        attempt_id = attempt.id
        fixture_id = fixture.id
        expected_identity = identity(fixture)
        snapshot = build_db_snapshot(session, fixture, now=now)
        session.commit()
    try:
        payload = deepcopy(snapshot)
        usage = dict(initial_usage)
        if evidence_provider:
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

        with session_factory() as session:
            enrich_importance(session, payload, now=now)
            enrich_player_spotlights(session, payload, now=now)
        PreviewPayload.model_validate(payload)
        if payload["is_mock"] is not False:
            raise ValueError("mock_payload_not_publishable")
        if payload["fixture"] != snapshot["fixture"]:
            raise ValueError("evidence_identity_mismatch")
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
            previous_id = previous.id if previous else None
        if previous_id is None:
            if provider and payload["sources"]:
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
                        b["status"] == "available" and new_blocks[k]["status"] != "available"
                        for k, b in old_blocks.items()
                    ):
                        raise ValueError("degraded_refresh")
                evidence = HomePreviewSnapshot(
                    fixture_id=fixture_id,
                    fingerprint=input_hash,
                    payload=evidence_snapshot,
                    as_of=datetime.fromisoformat(payload["as_of"]),
                )
                session.add(evidence)
                session.flush()
                version = HomePreviewVersion(
                    fixture_id=fixture_id,
                    snapshot_id=evidence.id,
                    fingerprint=input_hash,
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
