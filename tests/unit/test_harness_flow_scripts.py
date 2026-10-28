"""Legacy read-only compatibility and optional completion adapter checks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.unit.test_work_flow import Work

ROOT = Path(__file__).resolve().parents[2]
GUARD = ROOT / "scripts/harness-task-completed-guard.sh"


def run_legacy(root, kind, command, *args):
    env = {**os.environ, "HARNESS_PROJECT_ROOT": str(root)}
    env.pop("HARNESS_STATE_ROOT", None)
    return subprocess.run([str(ROOT / f"scripts/{kind}-flow.sh"), command, *args],
                          cwd=root, env=env, capture_output=True, text=True)


@pytest.fixture

def legacy(tmp_path):
    for kind in ("feature", "endpoint"):
        source = ROOT / f".codex/state/{kind}-flow"
        shutil.copytree(source, tmp_path / f".codex/state/{kind}-flow")
    return tmp_path


def snapshots(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("kind,item", [("feature", "fixture-detail"),
                                        ("endpoint", "GET__api_v1_fixtures__id")])
def test_legacy_read_commands_remain_available_without_mutation(legacy, kind, item):
    before = snapshots(legacy)
    for command, args in [("status", [item]), ("validate", [item]),
                          ("list", []), ("validate-all", [])]:
        result = run_legacy(legacy, kind, command, *args)
        assert result.returncode == 0, result.stderr
    assert snapshots(legacy) == before


@pytest.mark.parametrize("kind", ["feature", "endpoint"])
@pytest.mark.parametrize("command", ["init", "transition", "stage-completed", "start-integration",
                                      "guard-task-completed"])
def test_legacy_mutations_and_completion_are_blocked(legacy, kind, command):
    before = snapshots(legacy)
    result = run_legacy(legacy, kind, command, "fixture-detail", "--by", "team-lead")
    assert result.returncode != 0
    assert "read-only" in result.stderr
    assert snapshots(legacy) == before


def run_guard(work, payload):
    root = work.root if isinstance(work, Work) else work
    env = {**os.environ, "CODEX_PROJECT_DIR": str(root),
           "HARNESS_STATE_ROOT": str(root / ".codex/state/work-flow")}
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run([str(GUARD)], cwd=root, env=env, input=text,
                          capture_output=True, text=True)


def assert_block(result):
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["decision"] == "block"


@pytest.mark.parametrize("payload", ["{invalid", "", "null", "[]", {}, {"task_id": ""},
                                     {"task_id": {}}, {"task_id": "unlinked"}])
def test_adapter_fails_closed_for_missing_invalid_or_unlinked_payload(tmp_path, payload):
    assert_block(run_guard(tmp_path, payload))


def test_adapter_blocks_planned_work(tmp_path):
    work = Work(tmp_path)
    work.init()
    assert_block(run_guard(work, {"task_id": "work-1", "agent": "operator"}))


def merged_work(tmp_path):
    work = Work(tmp_path)
    work.prepare()
    work.decide()
    work.call("merged", "--merge-commit", work.commit, actor="operator")
    return work


def test_adapter_approves_validated_merged_work(tmp_path):
    work = merged_work(tmp_path)
    result = run_guard(work, {"task_id": "work-1", "teammate_name": "operator"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["decision"] == "approve"


@pytest.mark.parametrize("defect", ["actor", "state_id", "changed_evidence", "invalid_state"])
def test_adapter_blocks_mismatched_or_unverifiable_merged_work(tmp_path, defect):
    work = merged_work(tmp_path)
    payload = {"task_id": "work-1", "agent": "operator"}
    if defect == "actor":
        payload["agent"] = "developer"
    elif defect == "changed_evidence":
        work.write("test.log", "changed after merge")
    elif defect == "invalid_state":
        work.write(str(work.state_path.relative_to(work.root)), "{invalid")
    else:
        state = work.state()
        state["id"] = "different"
        work.write_json(str(work.state_path.relative_to(work.root)), state)
    assert_block(run_guard(work, payload))


def test_legacy_final_state_cannot_complete_new_task(legacy):
    # A preserved terminal legacy state is intentionally insufficient evidence.
    assert_block(run_guard(legacy, {"task_id": "8", "agent": "team-lead"}))
