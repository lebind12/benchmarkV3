from copy import deepcopy

import pytest

from app.schemas.home_preview import PreviewPayload
from app.services.home_preview_injuries import deduplicate_injuries, qualifies
from tests.unit.test_home_preview_api_football import snapshot


def test_deduplication_keeps_team_identity_and_marks_conflicting_status():
    row = {
        "team_id": 40,
        "player_id": 100,
        "player_name": "P",
        "availability": "out",
        "detail": "Injury",
        "impact": "Out",
        "source_ids": ["a"],
    }
    other = {**row, "source_ids": ["b"]}
    assert len(deduplicate_injuries([row, row, other])) == 1
    merged = deduplicate_injuries([row, {**other, "availability": "doubtful"}])[0]
    assert merged["status_conflict"] and merged["availability"] == "doubtful"
    assert merged["source_ids"] == ["a", "b"]
    assert len(deduplicate_injuries([row, {**row, "team_id": 51}])) == 2
    assert "status_conflict" not in row


def selection_payload():
    value = snapshot()
    value["generated_at"] = value["as_of"]
    for sid, kind in [("inj", "api"), ("usage", "db")]:
        value["sources"].append(
            {
                "id": sid,
                "fixture_id": 1557444,
                "kind": kind,
                "title": sid,
                "url": "https://source.example.test/injury" if kind == "api" else None,
                "published_at": None,
                "retrieved_at": value["as_of"],
            }
        )
    evidence = {
        "eligible": True,
        "recent_games": 10,
        "lineup_games": 8,
        "player_games": 8,
        "recent_starts": 5,
        "recent_minutes": 450,
        "seasons": [],
        "source_ids": ["usage"],
    }
    value["facts"]["injuries"] = {
        "status": "available",
        "reason": None,
        "as_of": value["as_of"],
        "source_ids": ["inj"],
        "data": [
            {
                "team_id": 40,
                "player_id": pid,
                "player_name": str(pid),
                "availability": "out",
                "detail": "Injury",
                "impact": "Out",
                "source_ids": ["inj"],
                "importance_evidence": deepcopy(evidence),
            }
            for pid in (1, 2, 3)
        ],
    }
    value["analysis"]["key_absences"] = {
        "status": "available",
        "reason": None,
        "as_of": value["as_of"],
        "source_ids": ["inj", "usage"],
        "data": [
            {
                "team_id": 40,
                "player_id": 1,
                "reason": "최근 선발 5회",
                "evidence_ids": ["inj", "usage"],
            }
        ],
    }
    return value


@pytest.mark.parametrize(
    "mutation",
    ["unknown", "ineligible", "conflict", "duplicate", "team_limit", "no_usage"],
)
def test_model_cannot_select_unknown_unqualified_or_excessive_absences(mutation):
    value = selection_payload()
    picks = value["analysis"]["key_absences"]["data"]
    if mutation == "unknown":
        picks[0]["player_id"] = 999
    if mutation == "ineligible":
        value["facts"]["injuries"]["data"][0]["importance_evidence"]["eligible"] = False
    if mutation == "conflict":
        value["facts"]["injuries"]["data"][0]["status_conflict"] = True
    if mutation == "duplicate":
        picks.append(deepcopy(picks[0]))
    if mutation == "team_limit":
        picks.extend([{**picks[0], "player_id": pid} for pid in (2, 3)])
    if mutation == "no_usage":
        picks[0]["evidence_ids"] = ["inj"]
    with pytest.raises(ValueError):
        PreviewPayload.model_validate(value)


def test_long_absence_can_qualify_from_explicit_season_records_and_missing_data_does_not():
    evidence = {"recent_starts": None, "recent_minutes": None, "seasons": []}
    assert not qualifies(evidence)
    evidence["seasons"] = [{"appearances": 20, "minutes": 1500}]
    assert qualifies(evidence)
    PreviewPayload.model_validate(selection_payload())


def test_llm_absence_reason_need_not_copy_the_internal_importance_sentence():
    value = selection_payload()
    value["analysis"]["key_absences"]["data"][0]["reason"] = (
        "최근 선발 비중을 고려하면 이번 경기에서 살펴볼 결장 변수입니다."
    )
    PreviewPayload.model_validate(value)
