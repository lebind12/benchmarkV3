"""Independent CLI behavior tests; all Git mutations stay in disposable repositories."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


CLI = Path(__file__).resolve().parents[2] / "scripts/harness-improve.py"
ALLOWED = ".codex/agents/example.toml"
BASE = "mode = 'bug'\nsafe = true\n"
GOOD = "mode = 'fixed'\nsafe = true\n"


class Improvement:
    def __init__(self, root):
        self.root = root
        self.env = os.environ.copy()
        self.baseline = root.parent / "baseline"
        self.candidate = root.parent / "candidate"
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Independent Improvement Tester")
        self.write(ALLOWED, "mode = 'old'\nsafe = true\n")
        self.write("service.txt", "service baseline\n")
        self.write(".codex/state/work-flow/service.json", '{"status":"DEVELOPING"}\n')
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.git("worktree", "add", "--detach", str(self.baseline), "HEAD")
        self.git("worktree", "add", "--detach", str(self.candidate), "HEAD")
        self.write(ALLOWED, BASE)  # Exercise active dirty harness without committing/stashing.
        self.write_json(".harness/config.json", {
            "project_id": "test", "editable_files": [ALLOWED], "protected_files": []})
        self.write("supplied-event.txt", "Synthetic fixture event: target check fails.\n")
        self.write("change-plan.md", "Change the fixture mode from bug to fixed; preserve safe=true.\n")
        self.report = {"category": "harness", "developer_id": "developer",
                       "inspector_id": "inspector", "observations": ["supplied-event.txt"],
                       "hypothesis": "The harness instruction selects the wrong mode",
                       "reproduction": "Run the frozen target check", "evidence": ["supplied-event.txt"]}
        self.write_json("report.json", self.report)
        self.suite = {"cases": [
            {"id": "target", "kind": "target", "argv": [sys.executable, "-c",
             f"from pathlib import Path; assert \"mode = 'fixed'\" in Path('{ALLOWED}').read_text()"],
             "timeout_seconds": 3},
            {"id": "regression", "kind": "regression", "argv": [sys.executable, "-c",
             f"from pathlib import Path; assert 'safe = true' in Path('{ALLOWED}').read_text()"],
             "timeout_seconds": 3}]}
        self.write_json("suite.json", self.suite)

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.root), *args], text=True, capture_output=True)
        assert p.returncode == 0, p.stderr
        return p.stdout.strip()

    def write(self, name, value):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)

    def write_json(self, name, value):
        self.write(name, json.dumps(value))

    def call(self, command, *args, ok=True, item="improve-1"):
        if command == "candidate" and "--change-plan" not in args:
            args = (*args, "--change-plan", self.root / "change-plan.md")
        if command == "evaluate" and "--behavior-report" not in args:
            args = (*args, "--behavior-report", self.behavior_report())
        argv = [sys.executable, str(CLI), "--root", str(self.root), command]
        if command not in ("observe", "list"):
            argv.append(item)
        p = subprocess.run([*argv, *map(str, args)], capture_output=True, text=True, timeout=25, env=self.env)
        if ok:
            assert p.returncode == 0, p.stderr
            return json.loads(p.stdout)
        assert p.returncode != 0, p.stdout[:1200]
        return p

    def init(self):
        return self.call("init", "--report", self.root / "report.json")

    def prepare(self):
        self.init()
        self.call("prepare", "--baseline-root", self.baseline, "--candidate-root", self.candidate,
                  "--suite", self.root / "suite.json", "--inspector", "inspector")

    def reproduce(self):
        self.prepare()
        return self.call("reproduce", "--inspector", "inspector")

    def optimize(self):
        self.reproduce()
        (self.candidate / ALLOWED).write_text(GOOD)
        return self.call("candidate", "--optimizer", "optimizer")

    def evaluate(self):
        self.optimize()
        return self.call("evaluate", "--evaluator", "evaluator")

    def behavior_report(self):
        """Synthetic schema fixture; never evidence of real agent instruction efficacy."""
        state = self.state()
        evidence = self.root / "synthetic-behavior.txt"
        evidence.write_text("SYNTHETIC TEST FIXTURE: no agent run occurred.\n")
        ref = {"path": str(evidence.resolve()), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}
        report = {"evaluator_id": "evaluator", "scenario_id": "synthetic-scenario",
                  "model": "synthetic-model", "reasoning": "medium", "settings_id": "fixture-settings",
                  "environment_id": "fixture-environment"}
        for side in ("baseline", "candidate"):
            report[side] = {"run_id": "synthetic-" + side,
                            "consumed_files": state.get(side + "_manifest", state["baseline_manifest"]),
                            "cases": [{"id": "target", "outcome": "FAIL" if side == "baseline" else "PASS"},
                                      {"id": "regression", "outcome": "PASS"}], "evidence": [ref]}
        self.write_json("behavior.json", report)
        return self.root / "behavior.json"

    def state(self):
        return json.loads(self.state_path.read_text())

    @property
    def state_path(self):
        return self.root / ".harness-engineering/proposals/improve-1/state.json"

    def approval(self, action="apply", **overrides):
        state = self.call("request-approval", "--action", action)
        evidence = {"actor": "human", "source": "user-message:test-123", "quote": "Approve this exact change",
                    "digest": state["digest"], "action": action}
        if action == "rollback":
            evidence["version"] = self.state()["version"]
        evidence.update(overrides)
        self.write_json("approval.json", evidence)
        return self.root / "approval.json"


@pytest.fixture
def flow(tmp_path):
    root = tmp_path / "live"
    root.mkdir()
    return Improvement(root)


def test_full_human_approved_apply_and_rollback_preserves_service_and_git(flow):
    initial_index = flow.git("diff", "--cached")
    initial_head = flow.git("rev-parse", "HEAD")
    evaluated = flow.evaluate()
    assert evaluated["evaluation"]["baseline"]["root"] == str(flow.baseline.resolve())
    assert evaluated["evaluation"]["candidate"]["root"] == str(flow.candidate.resolve())
    assert [x["returncode"] for x in evaluated["evaluation"]["baseline"]["cases"]] == [1, 0]
    assert [x["returncode"] for x in evaluated["evaluation"]["candidate"]["cases"]] == [0, 0]
    assert evaluated["evaluation"]["baseline"]["suite_sha256"] == evaluated["evaluation"]["candidate"]["suite_sha256"]
    assert (flow.root / ALLOWED).read_text() == BASE
    evidence = flow.approval()
    flow.call("record-approval", "--evidence", evidence)
    applied = flow.call("apply")
    assert (flow.root / ALLOWED).read_text() == GOOD
    assert (flow.root / ".harness-engineering/history" / (applied["version"] + ".json")).is_file()
    assert (flow.state_path.parent / "baseline" / ALLOWED).read_text() == BASE
    flow.call("rollback", "--evidence", evidence, ok=False)
    rollback = flow.approval("rollback")
    flow.call("rollback", "--evidence", rollback)
    assert (flow.root / ALLOWED).read_text() == BASE
    assert (flow.root / "service.txt").read_text() == "service baseline\n"
    assert (flow.root / ".codex/state/work-flow/service.json").read_text() == '{"status":"DEVELOPING"}\n'
    assert flow.git("rev-parse", "HEAD") == initial_head
    assert flow.git("diff", "--cached") == initial_index


@pytest.mark.parametrize("category", ["code", "environment", "unknown"])
def test_non_harness_diagnoses_cannot_prepare_candidate(flow, category):
    flow.report["category"] = category
    flow.write_json("report.json", flow.report)
    flow.init()
    flow.call("prepare", "--baseline-root", flow.baseline, "--candidate-root", flow.candidate,
              "--suite", flow.root / "suite.json", "--inspector", "inspector", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_snapshot_copies_dirty_active_harness_into_isolated_worktrees(flow):
    flow.prepare()
    assert (flow.baseline / ALLOWED).read_text() == BASE
    assert (flow.candidate / ALLOWED).read_text() == BASE
    assert flow.git("show", f"HEAD:{ALLOWED}") != BASE.strip()
    assert flow.state()["baseline_manifest"][ALLOWED] == hashlib.sha256(BASE.encode()).hexdigest()


def test_reproduction_and_distinct_actors_are_required(flow):
    flow.prepare()
    flow.call("candidate", "--optimizer", "optimizer", ok=False)
    flow.call("reproduce", "--inspector", "developer", ok=False)
    flow.call("reproduce", "--inspector", "inspector")
    (flow.candidate / ALLOWED).write_text(GOOD)
    flow.call("candidate", "--optimizer", "inspector", ok=False)
    flow.call("candidate", "--optimizer", "optimizer")
    flow.call("evaluate", "--evaluator", "optimizer", ok=False)


def test_json_diagnosis_without_actual_target_failure_cannot_proceed(flow):
    flow.write(ALLOWED, GOOD)
    flow.prepare()
    flow.call("reproduce", "--inspector", "inspector", ok=False)
    flow.call("candidate", "--optimizer", "optimizer", ok=False)


def test_regression_failure_blocks_approval(flow):
    flow.reproduce()
    (flow.candidate / ALLOWED).write_text("mode = 'fixed'\nsafe = false\n")
    flow.call("candidate", "--optimizer", "optimizer")
    flow.call("evaluate", "--evaluator", "evaluator", ok=False)
    flow.call("request-approval", ok=False)


@pytest.mark.parametrize("field,value", [("actor", "operator"), ("actor", "agent"),
                                          ("digest", "0" * 64), ("action", "rollback"),
                                          ("source", ""), ("source", "agent-output:test-123"), ("source", "   "), ("quote", "")])
def test_wrong_approval_evidence_never_changes_live_files(flow, field, value):
    flow.evaluate()
    evidence = flow.approval()
    approval = json.loads(evidence.read_text())
    approval[field] = value
    evidence.write_text(json.dumps(approval))
    flow.call("record-approval", "--evidence", evidence, ok=False)
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


@pytest.mark.parametrize("tamper", ["candidate", "baseline", "suite", "live"])
def test_approved_proposal_rejects_tampering_and_stale_live_baseline(flow, tamper):
    flow.evaluate()
    evidence = flow.approval()
    flow.call("record-approval", "--evidence", evidence)
    location = {"candidate": flow.candidate / ALLOWED, "baseline": flow.baseline / ALLOWED,
                "suite": flow.state_path.parent / "suite.json", "live": flow.root / ALLOWED}[tamper]
    location.write_text(location.read_text() + "\n# changed after review\n")
    before = (flow.root / ALLOWED).read_bytes()
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_bytes() == before


def test_malformed_state_is_rejected(flow):
    flow.init()
    state = flow.state()
    state["status"] = "MAGIC_APPROVED"
    flow.state_path.write_text(json.dumps(state))
    flow.call("validate", ok=False)
    flow.call("apply", ok=False)


def test_rollback_does_not_overwrite_concurrent_live_change(flow):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    flow.call("apply")
    evidence = flow.approval("rollback")
    flow.write(ALLOWED, GOOD + "# concurrent human edit\n")
    before = (flow.root / ALLOWED).read_bytes()
    flow.call("rollback", "--evidence", evidence, ok=False)
    assert (flow.root / ALLOWED).read_bytes() == before


@pytest.mark.parametrize("path", ["../escape.toml", "/tmp/escape.toml", "scripts/harness-improve.py",
                                  "AGENTS.md", ".harness/config.json", ".codex/config.toml",
                                  ".harness-engineering/proposals/forged.json"])
def test_allowlist_cannot_include_traversal_engine_or_protected_paths(flow, path):
    flow.write_json(".harness/config.json", {
        "project_id": "test", "editable_files": [ALLOWED, path], "protected_files": []})
    flow.call("init", "--report", flow.root / "report.json", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_allowed_symlink_cannot_read_or_overwrite_outside_file(flow):
    outside = flow.root.parent / "outside.toml"
    outside.write_text(BASE)
    (flow.root / ALLOWED).unlink()
    (flow.root / ALLOWED).symlink_to(outside)
    flow.call("init", "--report", flow.root / "report.json", ok=False)
    assert outside.read_text() == BASE


def test_active_worktree_cannot_be_baseline_or_candidate(flow):
    flow.init()
    flow.call("prepare", "--baseline-root", flow.root, "--candidate-root", flow.candidate,
              "--suite", flow.root / "suite.json", "--inspector", "inspector", ok=False)
    flow.call("prepare", "--baseline-root", flow.baseline, "--candidate-root", flow.root,
              "--suite", flow.root / "suite.json", "--inspector", "inspector", ok=False)


def test_untracked_allowlisted_file_is_frozen_without_active_git_changes(flow):
    new_path = ".codex/agents/untracked.toml"
    flow.write(new_path, "manual uncommitted instruction\n")
    flow.write_json(".harness/config.json", {
        "project_id": "test", "editable_files": [ALLOWED, new_path], "protected_files": []})
    before = flow.git("status", "--porcelain")
    flow.prepare()
    assert (flow.baseline / new_path).read_text() == "manual uncommitted instruction\n"
    assert (flow.candidate / new_path).read_text() == "manual uncommitted instruction\n"
    assert flow.git("diff", "--cached") == ""
    assert new_path in before


@pytest.mark.parametrize("case", [
    {"argv": [sys.executable, "-c", "import time; time.sleep(5)"], "timeout_seconds": 0.1},
    {"argv": ["/definitely/missing/test-command"], "timeout_seconds": 1},
])
def test_timeout_or_missing_command_never_counts_as_improvement(flow, case):
    flow.suite["cases"][0].update(case)
    flow.write_json("suite.json", flow.suite)
    flow.prepare()
    # Runtime may reject execution errors immediately, or record non-improving evidence.
    p = subprocess.run([sys.executable, str(CLI), "--root", str(flow.root), "reproduce",
                        "improve-1", "--inspector", "inspector"], capture_output=True, text=True, timeout=10)
    if p.returncode == 0:
        (flow.candidate / ALLOWED).write_text(GOOD)
        flow.call("candidate", "--optimizer", "optimizer")
        flow.call("evaluate", "--evaluator", "evaluator", ok=False)
    flow.call("request-approval", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_independent_worktree_heads_must_match_live_head(flow):
    p = subprocess.run(["git", "-C", str(flow.candidate), "commit", "--allow-empty", "-qm", "different"],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    flow.init()
    flow.call("prepare", "--baseline-root", flow.baseline, "--candidate-root", flow.candidate,
              "--suite", flow.root / "suite.json", "--inspector", "inspector", ok=False)


def test_candidate_cannot_include_service_code_change(flow):
    flow.reproduce()
    (flow.candidate / ALLOWED).write_text(GOOD)
    (flow.candidate / "service.txt").write_text("unauthorized service change\n")
    flow.call("candidate", "--optimizer", "optimizer", ok=False)
    assert (flow.root / "service.txt").read_text() == "service baseline\n"


def test_no_approval_command_or_service_operator_approval_can_apply(flow):
    flow.evaluate()
    flow.call("apply", ok=False)
    flow.call("approve", ok=False)
    evidence = flow.approval(actor="operator", quote="APPROVE service implementation")
    flow.call("record-approval", "--evidence", evidence, ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_truncated_execution_output_cannot_be_used_as_passing_evidence(flow):
    flow.suite["cases"][0]["argv"][-1] = (
        "print('x' * 70000); " + flow.suite["cases"][0]["argv"][-1])
    flow.write_json("suite.json", flow.suite)
    flow.prepare()
    p = subprocess.run([sys.executable, str(CLI), "--root", str(flow.root), "reproduce",
                        "improve-1", "--inspector", "inspector"], capture_output=True, text=True, timeout=10)
    if p.returncode == 0:
        (flow.candidate / ALLOWED).write_text(GOOD)
        flow.call("candidate", "--optimizer", "optimizer")
        flow.call("evaluate", "--evaluator", "evaluator", ok=False)
    flow.call("request-approval", ok=False)


@pytest.mark.parametrize("tamper", ["report", "log", "missing-log"])
def test_evidence_tampering_invalidates_exact_approval(flow, tamper):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    state = flow.state()
    report = state["evaluation"]["candidate"]
    log = flow.state_path.parent / report["cases"][0]["log"]
    if tamper == "report":
        report["run_id"] = "forged-evidence-id"
        flow.state_path.write_text(json.dumps(state))
    elif tamper == "missing-log":
        log.unlink()
    else:
        log.write_text('{"stdout":"changed","stderr":""}')
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_human_rejection_preserves_baseline_and_cannot_apply(flow):
    flow.evaluate()
    evidence = flow.approval(decision="reject", quote="Reject this harness proposal")
    state = flow.call("record-approval", "--evidence", evidence)
    assert state["status"] == "REJECTED"
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_manual_observation_redacts_supplied_secrets_without_transcript_claims(flow):
    supplied = {"kind": "error", "task_ref": "service-task-1", "metadata": {
        "password": "unmistakable-password", "message": "api_key=secret-example-token "
        "Bearer eyJabc.def.ghi sk-12345678901234567890", "supplied": "single event"},
        "evidence": ["supplied-log-line"]}
    flow.write_json("event.json", supplied)
    state = flow.call("observe", "--event", flow.root / "event.json")
    serialized = json.dumps(state)
    for secret in ("unmistakable-password", "secret-example-token", "eyJabc.def.ghi", "sk-12345678901234567890"):
        assert secret not in serialized
    assert state["metadata"]["supplied"] == "single event"
    assert state["evidence"] == ["supplied-log-line"]
    observations = list((flow.root / ".harness-engineering/observations").glob("*.jsonl"))
    assert len(observations) == 1
    assert len(observations[0].read_text().splitlines()) == 1


def test_recorded_approval_shape_is_validated_again_before_apply(flow):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    state = flow.state()
    state["approvals"][-1]["actor"] = "operator"
    flow.state_path.write_text(json.dumps(state))
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_replay_modifying_product_file_cannot_qualify(flow):
    flow.suite["cases"][0]["argv"][-1] = (
        "from pathlib import Path; Path('service.txt').write_text('contaminated'); "
        "raise SystemExit(1)")
    flow.write_json("suite.json", flow.suite)
    flow.prepare()
    flow.call("reproduce", "--inspector", "inspector", ok=False)
    flow.call("candidate", "--optimizer", "optimizer", ok=False)
    assert (flow.root / "service.txt").read_text() == "service baseline\n"


def test_static_subprocess_passes_without_behavior_report_cannot_qualify(flow):
    flow.optimize()
    p = subprocess.run([sys.executable, str(CLI), "--root", str(flow.root), "evaluate", "improve-1",
                        "--evaluator", "evaluator"], capture_output=True, text=True)
    assert p.returncode != 0, p.stdout[:1200]
    flow.call("request-approval", ok=False)


@pytest.mark.parametrize("defect", ["same_run", "wrong_evaluator", "wrong_consumed_hash",
                                    "missing_regression", "failed_regression", "baseline_target_pass",
                                    "wrong_evidence_hash", "missing_evidence"])
def test_behavior_attestation_must_match_frozen_comparison(flow, defect):
    flow.optimize()
    path = flow.behavior_report()
    report = json.loads(path.read_text())
    if defect == "same_run":
        report["candidate"]["run_id"] = report["baseline"]["run_id"]
    elif defect == "wrong_evaluator":
        report["evaluator_id"] = "optimizer"
    elif defect == "wrong_consumed_hash":
        report["candidate"]["consumed_files"][ALLOWED] = "0" * 64
    elif defect == "missing_regression":
        report["candidate"]["cases"].pop()
    elif defect == "failed_regression":
        report["candidate"]["cases"][1]["outcome"] = "FAIL"
    elif defect == "baseline_target_pass":
        report["baseline"]["cases"][0]["outcome"] = "PASS"
    elif defect == "wrong_evidence_hash":
        report["candidate"]["evidence"][0]["sha256"] = "0" * 64
    elif defect == "missing_evidence":
        report["candidate"]["evidence"] = []
    path.write_text(json.dumps(report))
    flow.call("evaluate", "--evaluator", "evaluator", "--behavior-report", path, ok=False)
    flow.call("request-approval", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_frozen_comparison_context_rejects_product_change_after_snapshot(flow):
    flow.prepare()
    (flow.baseline / "service.txt").write_text("different product context\n")
    flow.call("reproduce", "--inspector", "inspector", ok=False)


def test_change_plan_is_required_before_candidate_submission(flow):
    flow.reproduce()
    (flow.candidate / ALLOWED).write_text(GOOD)
    p = subprocess.run([sys.executable, str(CLI), "--root", str(flow.root), "candidate", "improve-1",
                        "--optimizer", "optimizer"], capture_output=True, text=True)
    assert p.returncode != 0, p.stdout[:1200]


@pytest.mark.parametrize("artifact", ["behavior.json", "change-plan.md", "diff.patch", "diagnosis", "transcript"])
def test_bound_artifact_or_attestation_tampering_blocks_apply(flow, artifact):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    if artifact == "diagnosis":
        path = flow.root / "supplied-event.txt"
    elif artifact == "transcript":
        path = flow.root / "synthetic-behavior.txt"
    else:
        path = flow.state_path.parent / artifact
    path.write_text(path.read_text() + "\nchanged after approval\n")
    flow.call("apply", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_external_runner_inputs_are_frozen_and_cannot_change_between_runs(flow):
    runner = flow.root.parent / "external-runner.py"
    runner.write_text("from pathlib import Path\nassert \"mode = 'fixed'\" in Path('" + ALLOWED + "').read_text()\n")
    flow.suite["cases"][0]["argv"] = [sys.executable, str(runner)]
    flow.write_json("suite.json", flow.suite)
    flow.prepare()
    runner.write_text("raise SystemExit(0)\n")
    flow.call("reproduce", "--inspector", "inspector", ok=False)
    flow.call("candidate", "--optimizer", "optimizer", ok=False)


@pytest.mark.parametrize("defect", ["omit", "change_command", "registry_missing"])
def test_previously_approved_criteria_cannot_be_removed_or_rewritten(flow, defect):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    flow.call("apply")
    if defect == "registry_missing":
        (flow.root / ".harness-engineering/regression-registry.json").unlink()
    flow.call("init", "--report", flow.root / "report.json", item="improve-2")
    cases = flow.suite["cases"]
    cases[0]["kind"] = "regression"
    if defect in ("omit", "registry_missing"):
        cases.pop(0)
    else:
        cases[0]["argv"] = [sys.executable, "-c", "raise SystemExit(0)"]
    cases.append({"id": "new-target", "kind": "target", "argv": [sys.executable, "-c", "raise SystemExit(1)"], "timeout_seconds": 3})
    flow.write_json("suite-next.json", {"cases": cases})
    flow.call("prepare", "--baseline-root", flow.baseline, "--candidate-root", flow.candidate,
              "--suite", flow.root / "suite-next.json", "--inspector", "inspector", item="improve-2", ok=False)
    assert (flow.root / ALLOWED).read_text() == GOOD


def test_dirty_tracked_active_product_is_not_silently_replayed_from_head(flow):
    flow.write("service.txt", "active product differs from HEAD\n")
    flow.init()
    flow.call("prepare", "--baseline-root", flow.baseline, "--candidate-root", flow.candidate,
              "--suite", flow.root / "suite.json", "--inspector", "inspector", ok=False)
    assert (flow.root / "service.txt").read_text() == "active product differs from HEAD\n"


def test_independent_actor_metadata_changes_do_not_invalidate_frozen_evaluation(flow):
    flow.env["CODEX_THREAD_ID"] = "inspector-thread"
    flow.env["AGENT_ID"] = "inspector-agent"
    flow.prepare()
    flow.env.update({"CODEX_THREAD_ID": "optimizer-thread", "AGENT_ID": "optimizer-agent",
                     "PWD": "/different/working-directory", "_": "/different/python", "SHLVL": "7"})
    flow.call("reproduce", "--inspector", "inspector")
    (flow.candidate / ALLOWED).write_text(GOOD)
    flow.call("candidate", "--optimizer", "optimizer")
    flow.env.update({"CODEX_THREAD_ID": "evaluator-thread", "AGENT_ID": "evaluator-agent"})
    flow.call("evaluate", "--evaluator", "evaluator")
    flow.call("request-approval")


def test_meaningful_evaluation_environment_changes_require_rebaseline(flow):
    flow.env["HARNESS_EVAL_SETTING"] = "baseline-setting"
    flow.prepare()
    flow.env["HARNESS_EVAL_SETTING"] = "different-setting"
    flow.call("reproduce", "--inspector", "inspector", ok=False)
    flow.call("candidate", "--optimizer", "optimizer", ok=False)
    assert (flow.root / ALLOWED).read_text() == BASE


def test_replay_receives_filtered_environment_instead_of_actor_metadata(flow):
    flow.env.update({"CODEX_THREAD_ID": "private-inspector-thread", "AGENT_ID": "private-agent"})
    flow.suite["cases"][1]["argv"][-1] = (
        "import os; assert 'CODEX_THREAD_ID' not in os.environ; assert 'AGENT_ID' not in os.environ; "
        "assert os.environ.get('HARNESS_EVAL_SETTING') == 'shared'")
    flow.env["HARNESS_EVAL_SETTING"] = "shared"
    flow.write_json("suite.json", flow.suite)
    flow.reproduce()


def test_state_parent_symlink_cannot_redirect_proposal_writes_outside_project(flow):
    outside = flow.root.parent / "outside-state"
    outside.mkdir()
    home = flow.root / ".harness-engineering"
    home.mkdir()
    (home / "proposals").symlink_to(outside, target_is_directory=True)
    flow.call("init", "--report", flow.root / "report.json", ok=False)
    assert list(outside.iterdir()) == []


def test_state_file_symlink_is_rejected_even_when_json_shape_is_valid(flow):
    flow.init()
    outside = flow.root.parent / "outside-state.json"
    outside.write_bytes(flow.state_path.read_bytes())
    flow.state_path.unlink()
    flow.state_path.symlink_to(outside)
    flow.call("status", ok=False)


def test_log_directory_symlink_cannot_receive_replay_output_outside_project(flow):
    flow.prepare()
    outside = flow.root.parent / "outside-logs"
    outside.mkdir()
    (flow.state_path.parent / "logs").symlink_to(outside, target_is_directory=True)
    flow.call("reproduce", "--inspector", "inspector", ok=False)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("defect", [None, "live_conflict", "backup_tamper"])
def test_recovery_of_simulated_interrupted_apply_preserves_unrelated_edits(flow, defect):
    flow.evaluate()
    flow.call("record-approval", "--evidence", flow.approval())
    flow.call("apply")
    state = flow.state()
    state["status"] = "APPLY_FAILED"  # Simulate an interrupted transaction with retained evidence.
    flow.state_path.write_text(json.dumps(state))
    if defect == "live_conflict":
        flow.write(ALLOWED, GOOD + "# concurrent human edit\n")
    elif defect == "backup_tamper":
        (flow.state_path.parent / "baseline" / ALLOWED).write_text("wrong backup\n")
    before = (flow.root / ALLOWED).read_bytes()
    flow.call("recover", ok=defect is None)
    if defect is None:
        assert (flow.root / ALLOWED).read_text() == BASE
        flow.call("apply", ok=False)
    else:
        assert (flow.root / ALLOWED).read_bytes() == before


def test_invalid_observation_error_does_not_echo_sensitive_input_instance(flow):
    supplied = {"kind": "invalid-kind", "task_ref": "private-user-context",
                "metadata": {"private_detail": "unpatterned-sensitive-value"},
                "evidence": ["private-evidence-text"]}
    flow.write_json("invalid-event.json", supplied)
    result = flow.call("observe", "--event", flow.root / "invalid-event.json", ok=False)
    for value in ("private-user-context", "unpatterned-sensitive-value", "private-evidence-text"):
        assert value not in result.stderr
        assert value not in result.stdout
