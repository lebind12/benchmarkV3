"""Insert the unmodified, structurally valid JSON; caller commits then checks fresh readback."""

from app.models.home_preview import HomePreviewPublication, HomePreviewSnapshot, HomePreviewVersion
from app.schemas.home_preview import PreviewPayload, clock
from app.services.home_preview import fixture_by_external
from app.services.home_preview_policy import digest, identity
from app.services.home_preview_targets import assert_content_preserved


def publish_existing_preview(
    session,
    payload,
    *,
    input_data,
    raw_response,
    resolution,
    grounding,
    actual_started_at,
    actual_finished_at,
    expected_version_id,
    expected_identity,
    replay_as_of=None,
    raw_text=None,
):
    PreviewPayload.model_validate(payload)
    targets = {"state": "pending_post_commit_readback"}
    assert_content_preserved(raw_response, payload)
    fixture = fixture_by_external(session, payload["fixture"]["external_id"])
    if identity(fixture) != expected_identity:
        raise ValueError("fixture_changed_during_generation")
    publication = session.get(HomePreviewPublication, fixture.id, with_for_update=True)
    if (publication.version_id if publication else None) != expected_version_id:
        raise ValueError("local_publication_changed_during_generation")
    if publication is None:
        publication = HomePreviewPublication(
            fixture_id=fixture.id, identity=expected_identity, refresh_state="idle"
        )
        session.add(publication)
    fingerprint = digest({"payload": payload, "actual_started_at": actual_started_at})
    snapshot = HomePreviewSnapshot(
        fixture_id=fixture.id,
        fingerprint=fingerprint,
        as_of=clock(payload["as_of"]),
        payload={
            "mode": "local_replay" if replay_as_of else "local_single_call",
            "input": input_data,
            "raw_llm_response": raw_response,
            "raw_llm_text": raw_text,
            "grounding": grounding,
            "resolution": resolution,
            "targets": targets,
            "actual_started_at": actual_started_at,
            "actual_finished_at": actual_finished_at,
            "replay_as_of": replay_as_of,
        },
    )
    session.add(snapshot)
    session.flush()
    version = HomePreviewVersion(
        fixture_id=fixture.id,
        snapshot_id=snapshot.id,
        fingerprint=fingerprint,
        payload=payload,
        generated_at=clock(payload["generated_at"]),
    )
    session.add(version)
    session.flush()
    publication.version_id = version.id
    publication.refresh_state = "idle"
    publication.reason = None
    session.flush()
    return {"version_id": version.id, "snapshot_id": snapshot.id}
