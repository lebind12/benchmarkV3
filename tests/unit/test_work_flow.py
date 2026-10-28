"""Independent, network-free operator/developer/tester CLI contract checks.

Every scenario uses a disposable Git repository. The real project index, branches,
legacy states and service data are never changed by these tests.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest


CLI = Path(__file__).resolve().parents[2] / "scripts/work-flow.sh"


class Work:
    def __init__(self, root):
        self.root = root
        self.git("init", "-q")
        self.git("config", "user.email", "harness-test@example.invalid")
        self.git("config", "user.name", "Independent Harness Test")
        self.write("code.txt", "base\n")
        self.git("add", "code.txt")
        self.git("commit", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.write("code.txt", "tested behavior\n")
        self.git("add", "code.txt")
        self.git("commit", "-qm", "implementation")
        self.commit = self.git("rev-parse", "HEAD")
        self.write("Plans.md", "Service plan and acceptance expectations\n")
        self.brief = {"goal": "Verify the feature", "acceptance_criteria": [
            {"id": "A", "description": "Normal behavior"},
            {"id": "B", "description": "Failure behavior"}],
            "owned_paths": ["code.txt"], "constraints": ["No network"],
            "service_plan": "Plans.md"}
        self.write_json("brief.json", self.brief)
        self.write_json("test-brief.json", {"goal": "Independently verify behavior", "scenarios": [
            {"criterion_id": x["id"], "description": x["description"]}
            for x in self.brief["acceptance_criteria"]]})
        self.write("developer.md", "Implemented the requested behavior.\n")
        self.write("review.md", "Read the implementation and independent evidence.\n")
        self.write("test.log", "Independent local checks: A PASS, B PASS\n")
        self.report = {"commit": self.commit, "revision": 1, "verdict": "PASS", "scenarios": [
            {"criterion_id": x, "status": "PASS", "evidence": "test.log"}
            for x in ("A", "B")], "summary": "Both acceptance criteria verified"}
        self.write_json("test-report.json", self.report)

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args], text=True, capture_output=True)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def write_json(self, name, value):
        self.write(name, json.dumps(value))

    def call(self, command, *args, actor=None, ok=True, item="work-1"):
        argv = [str(CLI), "--project-root", str(self.root), "--state-root",
                str(self.root / ".codex/state/work-flow"), command]
        if command not in ("list", "validate-all"):
            argv.append(item)
        if actor:
            argv.extend(["--by", actor])
        result = subprocess.run([*argv, *args], capture_output=True, text=True)
        if ok:
            assert result.returncode == 0, result.stderr
            return json.loads(result.stdout)
        assert result.returncode != 0, f"Unexpected success: {result.stdout}"
        return result

    def init(self, **kwargs):
        return self.call("init", "--service-id", "service", "--brief", "brief.json",
                         "--developer", "developer", "--tester", "tester", actor="operator", **kwargs)

    def start(self):
        self.call("start", actor="operator")

    def submit(self):
        self.call("submit", "--commit", self.commit, "--report", "developer.md", actor="developer")

    def test_start(self):
        self.call("test-start", "--brief", "test-brief.json", actor="operator")

    def test_report(self):
        self.call("test-report", "--report", "test-report.json", actor="tester")

    def decide(self, verdict="APPROVE", **kwargs):
        return self.call("decide", "--verdict", verdict, "--review", "review.md", actor="operator", **kwargs)

    def prepare(self, stage="reported"):
        self.init()
        self.start()
        if stage == "developing":
            return
        self.submit()
        if stage == "submitted":
            return
        self.test_start()
        if stage == "testing":
            return
        self.test_report()

    @property
    def state_path(self):
        return self.root / ".codex/state/work-flow/work-1.json"

    def state(self):
        return json.loads(self.state_path.read_text())


@pytest.fixture
def work(tmp_path):
    return Work(tmp_path)


def test_complete_lifecycle_and_legacy_preservation(work):
    legacy = {"feature-flow/old.json": '{"status":"TEST_PASSED"}',
              "endpoint-flow/old.json": '{"status":"REVIEW_PENDING"}'}
    for name, value in legacy.items():
        work.write(".codex/state/" + name, value)
    work.prepare()
    work.call("guard-task-completed", ok=False)
    work.decide()
    work.call("merged", "--merge-commit", work.commit, actor="operator")
    assert work.call("guard-task-completed")["status"] == "MERGED"
    state = work.call("status")
    assert state["actors"] == {"operator": "operator", "developer": "developer", "tester": "tester"}
    assert [x["command"] for x in state["events"]] == [
        "init", "start", "submit", "test-start", "test-report", "decide", "merged"]
    assert work.call("validate-all")[0]["status"] == "MERGED"
    assert work.call("list")[0]["id"] == "work-1"
    for name, value in legacy.items():
        assert (work.root / ".codex/state" / name).read_text() == value


@pytest.mark.parametrize("stage,command,args,actor", [
    ("developing", "submit", ("--commit", "COMMIT", "--report", "developer.md"), "tester"),
    ("submitted", "test-start", ("--brief", "test-brief.json"), "developer"),
    ("testing", "test-report", ("--report", "test-report.json"), "developer"),
    ("reported", "decide", ("--verdict", "APPROVE", "--review", "review.md"), "tester"),
])
def test_wrong_actor_is_rejected_without_state_mutation(work, stage, command, args, actor):
    work.prepare(stage)
    before = work.state_path.read_bytes()
    work.call(command, *(work.commit if x == "COMMIT" else x for x in args), actor=actor, ok=False)
    assert work.state_path.read_bytes() == before


def test_distinct_developer_and_tester_are_required(work):
    work.call("init", "--service-id", "service", "--brief", "brief.json", "--developer", "same",
              "--tester", "same", actor="operator", ok=False)
    assert not work.state_path.exists()


@pytest.mark.parametrize("bad_id", ["../escape", "a/b", ".hidden", "a b", "a" * 129])
def test_safe_work_ids(work, bad_id):
    work.init(item=bad_id, ok=False)
    assert not work.state_path.exists()


@pytest.mark.parametrize("report", ["missing.md", "empty.md", "report.txt"])
def test_submission_requires_existing_nonempty_markdown(work, report):
    work.prepare("developing")
    work.write("empty.md", "")
    work.write("report.txt", "Not a Markdown report")
    work.call("submit", "--commit", work.commit, "--report", report, actor="developer", ok=False)


@pytest.mark.parametrize("defect", ["missing_criterion", "failed_scenario", "missing_evidence",
                                    "empty_evidence", "wrong_commit", "invalid_json", "unknown_criterion"])
def test_pass_requires_valid_complete_current_evidence(work, defect):
    work.prepare("testing")
    if defect == "missing_criterion":
        work.report["scenarios"].pop()
    elif defect == "failed_scenario":
        work.report["scenarios"][0]["status"] = "FAIL"
    elif defect == "missing_evidence":
        work.report["scenarios"][0]["evidence"] = "does-not-exist.log"
    elif defect == "empty_evidence":
        work.write("test.log", " ")
    elif defect == "wrong_commit":
        work.report["commit"] = work.base
    elif defect == "unknown_criterion":
        work.report["scenarios"][0]["criterion_id"] = "UNKNOWN"
    work.write_json("test-report.json", work.report)
    if defect == "invalid_json":
        work.write("test-report.json", "{broken")
    work.call("test-report", "--report", "test-report.json", actor="tester", ok=False)
    assert work.state()["status"] == "TESTING"


@pytest.mark.parametrize("verdict", ["FAIL", "BLOCKED"])
def test_fail_or_blocked_cannot_be_approved(work, verdict):
    work.prepare("testing")
    work.report["verdict"] = verdict
    work.report["scenarios"][0]["status"] = verdict
    work.write_json("test-report.json", work.report)
    work.test_report()
    work.decide(ok=False)


@pytest.mark.parametrize("changed_file", ["brief.json", "Plans.md", "test-brief.json", "developer.md", "test-report.json", "test.log"])
@pytest.mark.parametrize("phase", ["approval", "merged"])
def test_changed_inputs_invalidate_pass_at_every_gate(work, changed_file, phase):
    work.prepare()
    if phase == "merged":
        work.decide()
    with (work.root / changed_file).open("a") as handle:
        handle.write("\nchanged after testing\n")
    if phase == "approval":
        work.decide(ok=False)
    else:
        work.call("merged", "--merge-commit", work.commit, actor="operator", ok=False)


def test_merge_requires_approval_and_contains_tested_commit(work):
    work.prepare("submitted")
    work.decide(ok=False)
    work.call("merged", "--merge-commit", work.commit, actor="operator", ok=False)
    work.test_start()
    work.test_report()
    work.decide()
    work.call("merged", "--merge-commit", work.base, actor="operator", ok=False)
    assert work.state()["status"] == "MERGE_APPROVED"


def test_rework_clears_old_test_and_approval_and_increments_revision(work):
    work.prepare()
    work.decide("REQUEST_CHANGES")
    work.start()
    state = work.state()
    assert state["revision"] == 2
    assert not {"test", "test_brief", "approval", "submission"}.intersection(state)
    work.write("code.txt", "fixed implementation\n")
    work.git("add", "code.txt")
    work.git("commit", "-qm", "fix")
    work.commit = work.git("rev-parse", "HEAD")
    work.submit()
    work.test_start()
    work.call("test-report", "--report", "test-report.json", actor="tester", ok=False)


def test_three_change_requests_escalate_and_stop_restart(work):
    work.prepare("submitted")
    for attempt in range(3):
        result = work.decide("REQUEST_CHANGES")
        if attempt < 2:
            work.start()
            work.submit()
    assert result["status"] == "ESCALATED"
    assert work.state()["failed_attempts"] == 3
    work.call("start", actor="operator", ok=False)


@pytest.mark.parametrize("defect", ["missing_submission", "missing_test", "missing_approval", "bad_revision", "unknown_property"])
def test_incomplete_or_invalid_state_is_rejected(work, defect):
    work.prepare()
    work.decide()
    state = work.state()
    if defect.startswith("missing_"):
        state.pop(defect.removeprefix("missing_"))
    elif defect == "bad_revision":
        state["revision"] = -1
    else:
        state["unrecognized"] = True
    work.write_json(str(work.state_path.relative_to(work.root)), state)
    work.call("validate", ok=False)


def test_test_handoff_must_cover_all_acceptance_criteria(work):
    work.prepare("submitted")
    work.write_json("incomplete-brief.json", {"goal": "Only one scenario", "scenarios": [
        {"criterion_id": "A", "description": "Missing B"}]})
    work.call("test-start", "--brief", "incomplete-brief.json", actor="operator", ok=False)


def test_mutations_require_actor_and_full_commit_sha(work):
    work.init()
    work.call("start", ok=False)
    work.start()
    work.call("submit", "--commit", work.commit[:8], "--report", "developer.md", actor="developer", ok=False)


def test_old_pass_cannot_be_replayed_in_same_commit_rework(work):
    work.prepare()
    work.decide("REQUEST_CHANGES")
    work.start()
    work.submit()
    work.test_start()
    work.call("test-report", "--report", "test-report.json", actor="tester", ok=False)
    assert work.state()["status"] == "TESTING"
    work.report["revision"] = 2
    work.write_json("test-report.json", work.report)
    work.test_report()
    work.decide()


def test_changed_evidence_can_be_rejected_then_retested(work):
    work.prepare()
    work.write("test.log", "Additional evidence requires a fresh test\n")
    work.decide(ok=False)
    work.decide("REQUEST_CHANGES")
    work.start()
    work.submit()
    work.test_start()
    work.report["revision"] = 2
    work.write_json("test-report.json", work.report)
    work.test_report()
    work.decide()
    assert work.state()["status"] == "MERGE_APPROVED"


def test_changed_operator_review_blocks_merge(work):
    work.prepare()
    work.decide()
    work.write("review.md", "Changed review after approval\n")
    work.call("merged", "--merge-commit", work.commit, actor="operator", ok=False)


def test_merge_descendant_is_valid_without_cli_changing_git(work):
    work.prepare()
    work.decide()
    work.write("code.txt", "integration descendant\n")
    work.git("add", "code.txt")
    work.git("commit", "-qm", "integration")
    descendant = work.git("rev-parse", "HEAD")
    work.call("merged", "--merge-commit", descendant, actor="operator")
    assert work.git("rev-parse", "HEAD") == descendant
    assert work.state()["submission"]["commit"] == work.commit


def test_duplicate_criterion_ids_are_rejected(work):
    work.brief["acceptance_criteria"][1]["id"] = "A"
    work.write_json("brief.json", work.brief)
    work.init(ok=False)
