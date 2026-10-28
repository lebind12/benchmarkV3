#!/usr/bin/env python3
"""Explicit local harness observations and human-approved improvements.

This is bookkeeping and a bounded subprocess runner, not a security sandbox,
identity provider, transcript tap, scheduler, or automatic diagnosis service.
Only existing allowlisted regular files can be changed by this MVP.
"""

from __future__ import annotations
import argparse
import contextlib
import difflib
import datetime as dt
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import uuid

import jsonschema

HARD_PROTECTED = [
    ".git",
    ".codex/hooks",
    ".codex/state",
    ".codex/schemas",
    "scripts/harness-task-completed-guard.py",
    "scripts/harness-task-completed-guard.sh",
    "AGENTS.md",
    ".codex/config.toml",
    ".harness",
    ".harness-engineering",
    "scripts/harness-improve.py",
    "scripts/harness-improve.sh",
    ".codex/agents/harness-inspector.toml",
    ".codex/agents/harness-optimizer.toml",
    ".codex/agents/harness-evaluator.toml",
]
STATES = [
    "DIAGNOSED",
    "CLOSED",
    "PREPARED",
    "REPRODUCED",
    "CANDIDATE",
    "EVALUATED",
    "READY_FOR_APPROVAL",
    "APPROVED",
    "REJECTED",
    "APPLYING",
    "APPLIED",
    "APPLY_FAILED",
    "ROLLING_BACK",
    "ROLLED_BACK",
]


def fail(message):
    raise ValueError(message)


def require(condition, message):
    if not condition:
        fail(message)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_json(path):
    return json.loads(Path(path).read_text())


def deny_symlink_components(path):
    path = Path(path).absolute()
    for component in [path, *path.parents]:
        require(not component.is_symlink(), f"Symlink state/output path forbidden: {component}")


def atomic(path, data):
    path = Path(path)
    deny_symlink_components(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deny_symlink_components(path)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix=".harness-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2, ensure_ascii=False).encode() + b"\n")


def redact(value):
    if isinstance(value, dict):
        return {
            k: (
                "[REDACTED]"
                if re.search(r"(?i)(password|secret|token|api.?key|authorization|cookie)", k)
                else redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1[REDACTED]", value)
    value = re.sub(
        r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\b",
        "[REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)((?:password|secret|token|api[_-]?key|authorization)\s*[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        value,
    )
    for key, secret in os.environ.items():
        if len(secret) >= 8 and re.search(r"(?i)(password|secret|token|api.?key)", key):
            value = value.replace(secret, "[REDACTED]")
    return value


class Harness:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.home = self.root / ".harness-engineering"
        self.config_path = self.root / ".harness/config.json"
        for name in [
            ".harness",
            ".harness/config.json",
            ".harness-engineering",
            ".harness-engineering/proposals",
        ]:
            self.safe(self.root, name, existing=False)
        self.config = read_json(self.config_path)
        self.schema("config", self.config)
        self.paths = self.config["editable_files"]
        require(
            len(self.paths) == len(set(self.paths)) and self.paths,
            "editable_files must be unique and nonempty",
        )
        for path in self.paths:
            self.safe(self.root, path, existing=False)
            require(not self.protected(path), f"Protected candidate path: {path}")
        self.config_sha = sha(self.config_path.read_bytes())

    def schema(self, name, value):
        path = (
            Path(__file__).resolve().parent.parent
            / ".harness-engineering/schemas"
            / (name + ".schema.json")
        )
        jsonschema.validate(value, read_json(path))

    def protected(self, name):
        protections = HARD_PROTECTED + self.config.get("protected_files", [])
        return any(name == p or name.startswith(p.rstrip("/") + "/") for p in protections)

    def safe(self, root, name, existing=True):
        require(
            isinstance(name, str)
            and name
            and not Path(name).is_absolute()
            and ".." not in Path(name).parts
            and name == Path(name).as_posix()
            and name != ".",
            "Unsafe relative path",
        )
        require(not root.is_symlink(), "Symlink root forbidden")
        path = root / name
        cursor = root
        for part in Path(name).parts:
            cursor = cursor / part
            require(not cursor.is_symlink(), f"Symlink forbidden: {name}")
        require(path.resolve().is_relative_to(root.resolve()), "Path escapes root")
        if existing:
            require(path.is_file(), f"Existing regular file required: {path}")
        return path

    def proposal(self, ident):
        require(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", ident), "Invalid proposal ID")
        return self.safe(self.home, "proposals/" + ident, existing=False)

    def load(self, ident):
        value = read_json(self.safe(self.proposal(ident), "state.json"))
        self.schema("state", value)
        self.schema("diagnosis", value["diagnosis"])
        for approval in value["approvals"]:
            self.check_approval_shape(approval)
        require(
            value["id"] == ident and value["project_id"] == self.config["project_id"],
            "Proposal identity mismatch",
        )
        return value

    def save(self, state, action):
        state["updated_at"] = now()
        state["events"].append({"at": now(), "action": action, "status": state["status"]})
        self.schema("state", state)
        write_json(self.proposal(state["id"]) / "state.json", state)

    @contextlib.contextmanager
    def lock(self):
        self.home.mkdir(parents=True, exist_ok=True)
        require(not self.home.is_symlink(), "State directory must not be a symlink")
        path = self.home / "lock"
        require(not path.is_symlink(), "Lock must not be a symlink")
        with open(path, "a") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fail("Another harness operation is in progress")
            yield

    def git(self, root, *args):
        run = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True)
        require(run.returncode == 0, f"Git validation failed: {redact(run.stderr)}")
        return run.stdout.strip()

    def manifest(self, root):
        return {p: sha(self.safe(root, p).read_bytes()) for p in self.paths}

    def check_workspace(self, root, require_existing=True):
        require(root != self.root, "Active root cannot be replay workspace")
        require(
            self.git(root, "rev-parse", "--show-toplevel") == str(root), "Use exact worktree root"
        )
        common = Path(
            self.git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve()
        active_common = Path(
            self.git(self.root, "rev-parse", "--path-format=absolute", "--git-common-dir")
        ).resolve()
        require(common == active_common, "Worktrees must share the active repository common-dir")
        require(
            self.git(root, "rev-parse", "HEAD") == self.git(self.root, "rev-parse", "HEAD"),
            "Worktrees must share active HEAD",
        )
        # NUL records avoid quoting and whitespace ambiguities, including renames.
        raw = subprocess.check_output(
            ["git", "-C", str(root), "status", "--porcelain=v1", "-z", "--untracked-files=all"]
        )
        records = raw.split(b"\0")
        index = 0
        while index < len(records):
            item = records[index]
            index += 1
            if not item:
                continue
            status, path = item[:2].decode(), os.fsdecode(item[3:])
            require(path in self.paths, f"Unrelated worktree change: {path}")
            require(
                not any(c in status for c in "DRCU"), "Deletion/rename/conflict is not supported"
            )
            if any(c in status for c in "RC"):
                index += 1
        for name in self.paths:
            self.safe(root, name, existing=require_existing)

    def workspaces(self, state):
        require(
            state["config_sha256"] == self.config_sha, "Configuration changed; restart proposal"
        )
        baseline, candidate = Path(state["baseline_root"]), Path(state["candidate_root"])
        require(
            baseline.resolve() == baseline
            and candidate.resolve() == candidate
            and baseline != candidate,
            "Invalid workspace paths",
        )
        for root in (baseline, candidate):
            self.check_workspace(root)
        require(self.manifest(baseline) == state["baseline_manifest"], "Baseline snapshot changed")
        require(
            sha((self.proposal(state["id"]) / "suite.json").read_bytes()) == state["suite_sha256"],
            "Frozen suite changed",
        )
        for root in (baseline, candidate):
            require(
                self.context(root) == state["context_manifest"],
                "Frozen non-harness context changed",
            )
        self.check_live_product_context(state["context_manifest"])
        require(
            state["runtime_sha256"] == self.runtime_fingerprint(),
            "Runtime environment/dependencies changed; explicit rebaseline required",
        )
        for path, digest in state.get("runner_inputs", {}).items():
            require(
                Path(path).is_file() and sha(Path(path).read_bytes()) == digest,
                "Frozen evaluator input changed: " + path,
            )
        self.check_evidence(state["diagnosis_evidence"])
        return baseline, candidate

    def suite(self, state):
        suite = read_json(self.proposal(state["id"]) / "suite.json")
        self.schema("suite", suite)
        require(len(suite["cases"]) <= self.config.get("max_cases", 30), "Too many cases")
        require(len({c["id"] for c in suite["cases"]}) == len(suite["cases"]), "Duplicate case ID")
        require(
            {c["kind"] for c in suite["cases"]} == {"target", "regression"},
            "Require target and regression cases",
        )
        for case in suite["cases"]:
            require(
                case.get("timeout_seconds", 30) <= self.config.get("max_timeout_seconds", 120),
                "Timeout exceeds configured bound",
            )
        return suite

    def run_suite(self, state, root, label):
        suite = self.suite(state)
        expected_manifest = self.manifest(root)
        expected_suite = (self.proposal(state["id"]) / "suite.json").read_bytes()
        results = []
        logs = self.proposal(state["id"]) / "logs"
        logs.mkdir(exist_ok=True)
        for case in suite["cases"]:
            start = time.monotonic()
            timed_out = False
            # Temporary file output bounds memory. Logs are truncated to 64 KiB per stream.
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                process = subprocess.Popen(
                    case["argv"],
                    cwd=root,
                    stdout=out,
                    stderr=err,
                    start_new_session=True,
                    env=self.evaluation_environment(),
                )
                try:
                    code = process.wait(timeout=case.get("timeout_seconds", 30))
                except subprocess.TimeoutExpired:
                    timed_out = True
                    os.killpg(process.pid, signal.SIGKILL)
                    code = process.wait()
                # Kill any same-group child left behind by the completed parent.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout_truncated = out.tell() > 65536
                stderr_truncated = err.tell() > 65536
                out.seek(0)
                err.seek(0)
                output = {
                    "stdout": redact(out.read(65536).decode(errors="replace")),
                    "stderr": redact(err.read(65536).decode(errors="replace")),
                }
            log_name = f"{label}-{case['id']}.json"
            write_json(logs / log_name, output)
            results.append(
                {
                    "id": case["id"],
                    "kind": case["kind"],
                    "argv_sha256": sha(canonical(case["argv"])),
                    "returncode": code,
                    "timeout": timed_out,
                    "stdout_truncated": stdout_truncated,
                    "stderr_truncated": stderr_truncated,
                    "wall_seconds": round(time.monotonic() - start, 4),
                    "log": "logs/" + log_name,
                    "log_sha256": sha((logs / log_name).read_bytes()),
                }
            )
            require(self.manifest(root) == expected_manifest, "Replay modified harness snapshot")
            require(
                (self.proposal(state["id"]) / "suite.json").read_bytes() == expected_suite,
                "Replay modified frozen suite",
            )
            self.check_workspace(root)
            require(
                self.context(root) == state["context_manifest"], "Replay modified frozen context"
            )
            self.workspaces(state)
        return {
            "run_id": str(uuid.uuid4()),
            "at": now(),
            "root": str(root),
            "suite_sha256": state["suite_sha256"],
            "manifest": expected_manifest,
            "cases": results,
        }

    def verify_report(self, state, report, expected_manifest):
        require(
            report["manifest"] == expected_manifest
            and report["suite_sha256"] == state["suite_sha256"],
            "Report snapshot mismatch",
        )
        cases = self.suite(state)["cases"]
        require(len(report["cases"]) == len(cases), "Missing evaluation cases")
        for actual, case in zip(report["cases"], cases):
            require(
                actual["id"] == case["id"]
                and actual["kind"] == case["kind"]
                and actual["argv_sha256"] == sha(canonical(case["argv"])),
                "Evaluation case mismatch",
            )
            require(not actual["timeout"], "Timed-out evaluation cannot qualify")
            require(actual["returncode"] >= 0, "Signal/crash cannot qualify as criterion outcome")
            require(
                not actual["stdout_truncated"] and not actual["stderr_truncated"],
                "Truncated evaluation output cannot qualify",
            )
            require(
                sha(self.safe(self.proposal(state["id"]), actual["log"]).read_bytes())
                == actual["log_sha256"],
                "Evaluation log changed",
            )

    def current_digest(self, state):
        baseline, candidate = self.workspaces(state)
        require(
            self.manifest(candidate) == state["candidate_manifest"], "Candidate snapshot changed"
        )
        self.verify_report(state, state["reproduction_report"], state["baseline_manifest"])
        evaluation = state["evaluation"]
        self.verify_report(state, evaluation["baseline"], state["baseline_manifest"])
        self.verify_report(state, evaluation["candidate"], state["candidate_manifest"])
        self.qualify(state)
        self.check_evidence(state["behavior_evidence"])
        require(
            sha((self.proposal(state["id"]) / "change-plan.md").read_bytes())
            == state["change_plan_sha256"],
            "Change plan changed",
        )
        require(
            sha((self.proposal(state["id"]) / "behavior.json").read_bytes())
            == state["behavior_sha256"],
            "Behavior report changed",
        )
        require(
            sha((self.proposal(state["id"]) / "diff.patch").read_bytes()) == state["diff_sha256"],
            "Candidate diff changed",
        )
        self.verify_behavior(state, read_json(self.proposal(state["id"]) / "behavior.json"))
        payload = {
            key: state[key]
            for key in [
                "id",
                "project_id",
                "config_sha256",
                "diagnosis",
                "baseline_manifest",
                "candidate_manifest",
                "suite_sha256",
                "inspector_id",
                "optimizer_id",
                "evaluator_id",
                "reproduction_report",
                "evaluation",
                "diagnosis_evidence",
                "context_manifest",
                "runner_inputs",
                "runtime_sha256",
                "change_plan_sha256",
                "diff_sha256",
                "behavior_sha256",
                "behavior_evidence",
            ]
        }
        return sha(canonical(payload))

    def qualify(self, state):
        require(state["diagnosis"]["category"] == "harness", "Only harness diagnosis may proceed")
        require(
            state["inspector_id"] != state["diagnosis"]["developer_id"],
            "Inspector must differ from developer",
        )
        require(
            state["optimizer_id"]
            not in [state["inspector_id"], state["diagnosis"]["developer_id"]],
            "Optimizer must be separate from inspector/developer",
        )
        require(
            state["evaluator_id"]
            not in [
                state["optimizer_id"],
                state["inspector_id"],
                state["diagnosis"]["developer_id"],
            ],
            "Evaluator must be independent",
        )
        for replay in [state["reproduction_report"], state["evaluation"]["baseline"]]:
            require(
                all(
                    c["returncode"] != 0 if c["kind"] == "target" else c["returncode"] == 0
                    for c in replay["cases"]
                ),
                "Baseline must reproduce every target and pass regressions",
            )
        require(
            all(c["returncode"] == 0 for c in state["evaluation"]["candidate"]["cases"]),
            "Candidate must pass every case",
        )

    def approval(self, path, digest, action, version=None):
        value = read_json(path)
        self.check_approval_shape(value)
        require(
            value["digest"] == digest and value.get("action", "apply") == action,
            "Human approval digest/action mismatch",
        )
        if version is not None:
            require(value.get("version") == version, "Rollback approval version mismatch")
        # This is an explicit human-evidence record; origin is verified by operator, not CLI.
        return {**value, "recorded_at": now()}

    def rollback_digest(self, state):
        return sha(
            canonical(
                {
                    "action": "rollback",
                    "id": state["id"],
                    "version": state["version"],
                    "approved_digest": state["digest"],
                    "before": state["baseline_manifest"],
                    "after": state["candidate_manifest"],
                    "files": state["changed_files"],
                }
            )
        )

    def transaction(self, state, reverse=False):
        changed = state["changed_files"]
        expected = state["candidate_manifest"] if reverse else state["baseline_manifest"]
        live = self.manifest(self.root)
        checked = changed if reverse else self.paths
        require(
            all(live[p] == expected[p] for p in checked),
            "Live baseline changed; refusing stale operation",
        )
        folder = self.proposal(state["id"])
        # Preflight every byte before the first live mutation.
        writes = {}
        originals = {}
        for name in changed:
            target = self.safe(self.root, name)
            originals[name] = target.read_bytes()
            source = (
                self.safe(folder / "baseline", name)
                if reverse
                else self.safe(Path(state["candidate_root"]), name)
            )
            data = source.read_bytes()
            want = (
                state["baseline_manifest"][name] if reverse else state["candidate_manifest"][name]
            )
            require(sha(data) == want, f"Approved content changed: {name}")
            writes[name] = data
        state["status"] = "ROLLING_BACK" if reverse else "APPLYING"
        self.save(state, "begin-rollback" if reverse else "begin-apply")
        done = []
        try:
            for name, data in writes.items():
                require(
                    sha(self.safe(self.root, name).read_bytes()) == expected[name],
                    f"Concurrent edit: {name}",
                )
                atomic(self.safe(self.root, name), data)
                done.append(name)
            after = self.manifest(self.root)
            desired = state["baseline_manifest"] if reverse else state["candidate_manifest"]
            require(
                all(after[p] == desired[p] for p in checked),
                "Concurrent changes detected during transaction",
            )
        except BaseException:
            conflicts = []
            for name in reversed(done):
                if sha(self.safe(self.root, name).read_bytes()) == sha(writes[name]):
                    atomic(self.safe(self.root, name), originals[name])
                else:
                    conflicts.append(name)
            state["status"] = "APPLY_FAILED"
            state["recovery_conflicts"] = conflicts
            self.save(state, "transaction-failed-restoration-attempted")
            raise
        state["status"] = "ROLLED_BACK" if reverse else "APPLIED"
        self.save(state, "rolled-back" if reverse else "applied")
        history = (
            self.home / "history" / (state["version"] + ("-rollback" if reverse else "") + ".json")
        )
        write_json(
            history,
            {
                "id": state["id"],
                "version": state["version"],
                "at": now(),
                "action": "rollback" if reverse else "apply",
                "digest": state["digest"],
                "files": changed,
                "before": expected,
                "after": self.manifest(self.root),
            },
        )

    def check_approval_shape(self, value):
        clean = {k: v for k, v in value.items() if k != "recorded_at"}
        self.schema("approval", clean)
        require(
            clean["source"].startswith(("user-message:", "human-message:"))
            and clean["source"].split(":", 1)[1].strip(),
            "Approval source must identify an actual human message",
        )
        require(clean["quote"].strip(), "Human approval quote must be nonblank")

    def check_live_product_context(self, replay):
        # Explicit scope: tracked product files. Operational state and governed
        # harness paths may be dirty; arbitrary product dirt may not be replayed as HEAD.
        ignored = (
            HARD_PROTECTED
            + list(self.config.get("live_paths", {}).values())
            + ["scripts/work-flow.py", "scripts/work-flow.sh"]
        )
        raw = subprocess.check_output(["git", "-C", str(self.root), "ls-files", "-z", "--cached"])
        for name in set(os.fsdecode(v) for v in raw.split(b"\0") if v):
            if name in self.paths or any(
                name == p or name.startswith(p.rstrip("/") + "/") for p in ignored
            ):
                continue
            require(
                name in replay and sha(self.safe(self.root, name).read_bytes()) == replay[name],
                "Live tracked product differs from frozen replay context: " + name,
            )

    def evaluation_environment(self):
        # Launch/session metadata is deliberately absent from BOTH fingerprint and
        # child env. All meaningful evaluation settings, paths and secrets remain
        # unchanged in the child; only their aggregate hash is persisted.
        transient = {
            "PWD",
            "OLDPWD",
            "_",
            "SHLVL",
            "TERM",
            "COLORTERM",
            "COLUMNS",
            "LINES",
            "TERM_SESSION_ID",
            "TTY",
            "SSH_TTY",
            "PS1",
            "PS2",
            "PROMPT",
            "PYTEST_CURRENT_TEST",
            "AGENT_ID",
            "THREAD_ID",
            "SESSION_ID",
            "TURN_ID",
        }
        session_key = re.compile(
            r"^CODEX_(?:.*_)?(?:THREAD|AGENT|SESSION|TURN|CONVERSATION)(?:_ID)?$"
        )
        return {
            k: v
            for k, v in os.environ.items()
            if k not in transient and not session_key.fullmatch(k)
        }

    def runtime_fingerprint(self):
        # Hash only: never persist raw environment or dependency inventory.
        packages = sorted(
            (d.metadata.get("Name", ""), d.version) for d in importlib.metadata.distributions()
        )
        return sha(
            canonical(
                {
                    "python": sys.version,
                    "environment": self.evaluation_environment(),
                    "packages": packages,
                }
            )
        )

    def context(self, root):
        raw = subprocess.check_output(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]
        )
        paths = sorted(set(os.fsdecode(p) for p in raw.split(b"\0") if p))
        return {p: sha(self.safe(root, p).read_bytes()) for p in paths if p not in self.paths}

    def runner_inputs(self, suite, roots):
        files = {}
        import shutil

        for case in suite["cases"]:
            for index, arg in enumerate(case["argv"]):
                resolved = shutil.which(arg) if index == 0 else arg
                if resolved and Path(resolved).is_absolute() and Path(resolved).is_file():
                    path = Path(resolved).resolve()
                    require(
                        not any(path.is_relative_to(root) for root in roots),
                        "Absolute runner inputs may not target a replay worktree",
                    )
                    files[str(path)] = sha(path.read_bytes())
        for value in suite.get("inputs", []):
            path = Path(value).resolve()
            require(
                path.is_file() and not any(path.is_relative_to(root) for root in roots),
                "Explicit suite inputs must be external existing files",
            )
            files[str(path)] = sha(path.read_bytes())
        return files

    def freeze_evidence(self, items):
        frozen = []
        for item in items:
            value = item if isinstance(item, dict) else {"path": item}
            path = Path(value["path"])
            if not path.is_absolute():
                path = self.root / path
            require(
                path.is_file() and not path.is_symlink(),
                "Existing regular evidence file required: " + str(path),
            )
            digest = sha(path.read_bytes())
            require("sha256" not in value or value["sha256"] == digest, "Evidence hash mismatch")
            frozen.append({"path": str(path.resolve()), "sha256": digest})
        require(frozen, "At least one evidence file required")
        return frozen

    def check_evidence(self, items):
        self.freeze_evidence(items)

    def diagnosis_evidence(self, report):
        evidence = list(report["evidence"])
        events = {}
        for path in (self.home / "observations").glob("*.jsonl"):
            for line in path.read_text().splitlines():
                event = json.loads(line)
                capture = self.home / "observation-captures" / (event["id"] + ".json")
                if not capture.exists():
                    write_json(capture, event)
                events[event["id"]] = str(capture)
        for ref in report["observations"]:
            evidence.append(events.get(ref, ref))
        return self.freeze_evidence(evidence)

    def verify_behavior(self, state, report):
        self.schema("behavior", report)
        require(report["evaluator_id"] == state["evaluator_id"], "Behavior evaluator mismatch")
        require(
            report["baseline"]["run_id"] != report["candidate"]["run_id"],
            "Behavior requires separate baseline/candidate agent runs",
        )
        for side in ["baseline", "candidate"]:
            run = report[side]
            require(
                run["consumed_files"] == state[side + "_manifest"],
                "Behavior consumed harness hashes mismatch",
            )
            cases = self.suite(state)["cases"]
            require(
                [c["id"] for c in run["cases"]] == [c["id"] for c in cases],
                "Behavior must cover every frozen criterion in order",
            )
            for case, actual in zip(cases, run["cases"]):
                expected = "FAIL" if side == "baseline" and case["kind"] == "target" else "PASS"
                require(actual["outcome"] == expected, "Behavior criterion failed")
            self.freeze_evidence(run["evidence"])

    def registry(self):
        path = self.safe(self.home, "regression-registry.json", existing=False)
        registry = read_json(path) if path.exists() else {"cases": []}
        cases = {c["id"]: c for c in registry["cases"]}
        # Recover accumulation after interruption between applied state/history
        # and the convenience registry append. Retained approved suites are the
        # durable source; deleting the index never silently drops regressions.
        for folder in sorted((self.home / "proposals").glob("*")):
            state_file = folder / "state.json"
            if not state_file.is_file():
                continue
            previous = read_json(state_file)
            history = self.home / "history" / (previous.get("version", "") + ".json")
            if (
                previous.get("status") not in ["APPLIED", "ROLLING_BACK", "ROLLED_BACK"]
                and not history.is_file()
            ):
                continue
            self.schema("state", previous)
            approvals = previous["approvals"]
            require(
                approvals
                and approvals[0]["digest"] == previous["digest"]
                and approvals[0].get("decision", "approve") == "approve",
                "Historical human approval missing",
            )
            self.check_approval_shape(approvals[0])
            suite_path = folder / "suite.json"
            require(
                suite_path.is_file() and sha(suite_path.read_bytes()) == previous["suite_sha256"],
                "Historical regression suite unavailable or changed; explicit rebaseline needed",
            )
            old_suite = read_json(suite_path)
            self.schema("suite", old_suite)
            for case in old_suite["cases"]:
                require(
                    case["id"] not in cases or cases[case["id"]]["argv"] == case["argv"],
                    "Conflicting historical regression criterion; explicit rebaseline needed",
                )
                cases[case["id"]] = {**case, "kind": "regression"}
        return {**registry, "cases": list(cases.values())}

    def enforce_registry(self, suite):
        present = {c["id"]: c for c in suite["cases"]}
        for old in self.registry()["cases"]:
            require(
                old["id"] in present
                and present[old["id"]]["kind"] == "regression"
                and present[old["id"]]["argv"] == old["argv"],
                "Previously approved criterion must remain an unchanged regression; explicit rebaseline needed: "
                + old["id"],
            )

    def update_registry(self, state):
        registry = self.registry()
        cases = {c["id"]: c for c in registry["cases"]}
        for case in self.suite(state)["cases"]:
            cases[case["id"]] = {**case, "kind": "regression"}
        registry["cases"] = list(cases.values())
        registry["updated_at"] = now()
        write_json(self.home / "regression-registry.json", registry)

    def execute(self, args):
        cmd = args.command
        if cmd == "observe":
            event = read_json(args.event)
            self.schema("observation", event)
            event = redact(event)
            event.update(
                {"id": str(uuid.uuid4()), "at": now(), "project_id": self.config["project_id"]}
            )
            directory = self.home / "observations"
            directory.mkdir(parents=True, exist_ok=True)
            output = self.safe(self.home, "observations/" + now()[:10] + ".jsonl", existing=False)
            with open(output, "a") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
            return event
        if cmd in ("list", "status", "validate") and not getattr(args, "id", None):
            values = [
                self.load(p.name) for p in sorted((self.home / "proposals").glob("*")) if p.is_dir()
            ]
            if cmd == "validate":
                for value in values:
                    self.validate(value)
            return values
        if cmd == "init":
            folder = self.proposal(args.id)
            require(not folder.exists(), "Proposal already exists")
            report = read_json(args.report)
            self.schema("diagnosis", report)
            state = {
                "schema_version": 1,
                "id": args.id,
                "project_id": self.config["project_id"],
                "status": "DIAGNOSED",
                "created_at": now(),
                "updated_at": now(),
                "diagnosis": redact(report),
                "diagnosis_evidence": self.diagnosis_evidence(report),
                "config_sha256": self.config_sha,
                "events": [],
                "approvals": [],
            }
            folder.mkdir(parents=True)
            self.save(state, "diagnosed")
            return state
        state = self.load(args.id)
        if cmd == "status":
            if state["status"] == "APPLIED":
                return {**state, "rollback_digest": self.rollback_digest(state)}
            return state
        if cmd == "validate":
            self.validate(state)
            return {"valid": True, "id": args.id, "status": state["status"]}
        if cmd == "close":
            require(state["status"] == "DIAGNOSED", "Only diagnosed proposals may close")
            state["status"] = "CLOSED"
        elif cmd == "prepare":
            require(
                state["status"] == "DIAGNOSED" and state["diagnosis"]["category"] == "harness",
                "Only harness diagnosis may prepare",
            )
            require(
                args.inspector == state["diagnosis"]["inspector_id"]
                and args.inspector != state["diagnosis"]["developer_id"],
                "Independent inspector required",
            )
            roots = [Path(args.baseline_root).resolve(), Path(args.candidate_root).resolve()]
            require(roots[0] != roots[1], "Baseline and candidate must be distinct")
            for root in roots:
                self.check_workspace(root, require_existing=False)
            suite = read_json(args.suite)
            self.schema("suite", suite)
            self.enforce_registry(suite)
            require(
                not Path(args.suite).resolve().is_relative_to(roots[0])
                and not Path(args.suite).resolve().is_relative_to(roots[1]),
                "Suite must be evaluator-owned outside replay roots",
            )
            context = self.context(roots[0])
            self.check_live_product_context(context)
            require(
                context == self.context(roots[1]), "Baseline/candidate non-harness contexts differ"
            )
            suite_bytes = canonical(suite)
            folder = self.proposal(args.id)
            state.update(
                {
                    "baseline_root": str(roots[0]),
                    "candidate_root": str(roots[1]),
                    "baseline_manifest": self.manifest(self.root),
                    "inspector_id": args.inspector,
                    "context_manifest": context,
                    "runner_inputs": self.runner_inputs(suite, roots),
                    "runtime_sha256": self.runtime_fingerprint(),
                    "suite_sha256": sha(suite_bytes),
                }
            )
            atomic(folder / "suite.json", suite_bytes)
            self.suite(state)
            for name in self.paths:
                data = self.safe(self.root, name).read_bytes()
                atomic(folder / "baseline" / name, data)
                for root in roots:
                    atomic(self.safe(root, name, existing=False), data)
            state["status"] = "PREPARED"
        elif cmd == "reproduce":
            require(
                state["status"] == "PREPARED" and args.inspector == state["inspector_id"],
                "Prepared proposal and original inspector required",
            )
            baseline, _ = self.workspaces(state)
            replay = self.run_suite(state, baseline, "reproduction")
            state["last_reproduction"] = replay
            self.save(state, "reproduction-executed")
            self.verify_report(state, replay, state["baseline_manifest"])
            require(
                all(
                    c["returncode"] != 0 if c["kind"] == "target" else c["returncode"] == 0
                    for c in replay["cases"]
                ),
                "Baseline did not reproduce targets or failed a regression",
            )
            state["reproduction_report"] = replay
            state["status"] = "REPRODUCED"
        elif cmd == "candidate":
            require(
                state["status"] == "REPRODUCED", "Real independent baseline reproduction required"
            )
            _, candidate = self.workspaces(state)
            require(
                args.optimizer not in [state["inspector_id"], state["diagnosis"]["developer_id"]],
                "Independent optimizer required",
            )
            plan = Path(args.change_plan).read_bytes()
            require(plan.strip(), "Expected effect/risk change plan must be nonempty")
            atomic(self.proposal(args.id) / "change-plan.md", plan)
            state["change_plan_sha256"] = sha(plan)
            state["optimizer_id"] = args.optimizer
            state["candidate_manifest"] = self.manifest(candidate)
            state["changed_files"] = [
                p
                for p in self.paths
                if state["candidate_manifest"][p] != state["baseline_manifest"][p]
            ]
            require(state["changed_files"], "Candidate has no changes")
            diff = ""
            for name in state["changed_files"]:
                before = (
                    self.safe(self.proposal(args.id) / "baseline", name)
                    .read_text()
                    .splitlines(keepends=True)
                )
                after = self.safe(candidate, name).read_text().splitlines(keepends=True)
                diff += "".join(
                    difflib.unified_diff(before, after, fromfile="a/" + name, tofile="b/" + name)
                )
            atomic(self.proposal(args.id) / "diff.patch", diff.encode())
            state["diff_sha256"] = sha(diff.encode())
            state["status"] = "CANDIDATE"
        elif cmd == "evaluate":
            require(state["status"] == "CANDIDATE", "Candidate submission required")
            require(
                args.evaluator
                not in [
                    state["optimizer_id"],
                    state["inspector_id"],
                    state["diagnosis"]["developer_id"],
                ],
                "Independent evaluator required",
            )
            baseline, candidate = self.workspaces(state)
            require(
                self.manifest(candidate) == state["candidate_manifest"],
                "Candidate changed since submission",
            )
            state["evaluator_id"] = args.evaluator
            behavior = read_json(args.behavior_report)
            self.verify_behavior(state, behavior)
            behavior_bytes = canonical(behavior)
            atomic(self.proposal(args.id) / "behavior.json", behavior_bytes)
            state["behavior_sha256"] = sha(behavior_bytes)
            state["behavior_evidence"] = self.freeze_evidence(
                [e for side in ["baseline", "candidate"] for e in behavior[side]["evidence"]]
            )
            reports = {
                "baseline": self.run_suite(state, baseline, "evaluation-baseline"),
                "candidate": self.run_suite(state, candidate, "evaluation-candidate"),
            }
            state["last_evaluation"] = reports
            self.save(state, "evaluation-executed")
            for name, report in reports.items():
                self.verify_report(state, report, state[name + "_manifest"])
            state["evaluation"] = reports
            self.qualify(state)
            state["status"] = "EVALUATED"
        elif cmd == "request-approval":
            if args.action == "rollback":
                require(state["status"] == "APPLIED", "Applied version required")
                digest = self.rollback_digest(state)
                summary = (
                    f"# Human approval requested: rollback {state['version']}\n\nDigest: `{digest}`\n\nRestore only: "
                    + ", ".join(state["changed_files"])
                    + "\n"
                )
                atomic(self.proposal(args.id) / "rollback-approval.md", summary.encode())
                return {
                    "id": args.id,
                    "action": "rollback",
                    "digest": digest,
                    "version": state["version"],
                    "summary": summary,
                }
            require(
                state["status"] in ["EVALUATED", "READY_FOR_APPROVAL"],
                "Successful independent evaluation required",
            )
            digest = self.current_digest(state)
            state["digest"] = digest
            state["status"] = "READY_FOR_APPROVAL"
            summary = (
                f"# Human approval requested: {args.id}\n\nDigest: `{digest}`\n\nDiagnosis: {state['diagnosis']['hypothesis']}\n\nChanged files:\n"
                + "".join(
                    f"- `{p}`: `{state['baseline_manifest'][p]}` → `{state['candidate_manifest'][p]}`\n"
                    for p in state["changed_files"]
                )
                + "\nBaseline targets fail; candidate targets and all regressions pass. Review the actual candidate diff and linked logs before explicit human approval. This CLI cannot authenticate human identity.\n"
            )
            summary += (
                "\nExpected effect and risks:\n\n"
                + (self.proposal(args.id) / "change-plan.md").read_text()
                + "\n\nExact candidate diff:\n\n```diff\n"
                + (self.proposal(args.id) / "diff.patch").read_text()
                + "\n```\n\nFrozen behavioral attestation and command results:\n\n```json\n"
                + json.dumps(
                    {
                        "behavior": read_json(self.proposal(args.id) / "behavior.json"),
                        "evaluation": state["evaluation"],
                    },
                    indent=2,
                )
                + "\n```\n"
            )
            atomic(self.proposal(args.id) / "approval.md", summary.encode())
        elif cmd == "record-approval":
            require(state["status"] == "READY_FOR_APPROVAL", "Concrete approval request required")
            require(self.current_digest(state) == state["digest"], "Approval request stale")
            evidence = self.approval(args.evidence, state["digest"], "apply")
            state["approvals"].append(evidence)
            state["status"] = (
                "REJECTED" if evidence.get("decision", "approve") == "reject" else "APPROVED"
            )
        elif cmd == "apply":
            require(state["status"] == "APPROVED", "Explicit human approval required")
            require(self.current_digest(state) == state["digest"], "Approval stale")
            require(
                state["approvals"]
                and state["approvals"][-1]["digest"] == state["digest"]
                and state["approvals"][-1].get("decision", "approve") == "approve",
                "Human approval missing",
            )
            self.check_approval_shape(state["approvals"][-1])
            state["version"] = now().replace(":", "-").replace(".", "-") + "-" + args.id
            self.transaction(state)
            self.update_registry(state)
            return state
        elif cmd == "rollback":
            require(state["status"] == "APPLIED", "Applied proposal required")
            evidence = self.approval(
                args.evidence, self.rollback_digest(state), "rollback", state["version"]
            )
            require(evidence.get("decision", "approve") == "approve", "Rollback rejected")
            state["approvals"].append(evidence)
            self.transaction(state, reverse=True)
            return state
        elif cmd == "recover":
            require(
                state["status"] in ["APPLYING", "ROLLING_BACK", "APPLY_FAILED"],
                "No interrupted transaction",
            )
            require(
                state["config_sha256"] == self.config_sha,
                "Configuration changed; manual recovery review required",
            )
            require(
                state.get("approvals")
                and state["approvals"][0].get("action", "apply") == "apply"
                and state["approvals"][0].get("decision", "approve") == "approve"
                and state["approvals"][0]["digest"] == state.get("digest"),
                "Original apply approval required for recovery",
            )
            self.check_approval_shape(state["approvals"][0])
            require(
                self.current_digest(state) == state["digest"],
                "Recovery evidence changed; manual recovery review required",
            )
            # Conservatively restore only files still exactly matching one known side.
            # A fresh approval is needed for any new apply after recovery.
            for name in state["changed_files"]:
                current = sha(self.safe(self.root, name).read_bytes())
                require(
                    current
                    in [state["baseline_manifest"][name], state["candidate_manifest"][name]],
                    f"Manual recovery required; unrelated edit: {name}",
                )
            for name in state["changed_files"]:
                data = self.safe(self.proposal(args.id) / "baseline", name).read_bytes()
                require(sha(data) == state["baseline_manifest"][name], "Recovery backup corrupt")
            for name in state["changed_files"]:
                atomic(
                    self.safe(self.root, name),
                    self.safe(self.proposal(args.id) / "baseline", name).read_bytes(),
                )
            state["status"] = "APPLY_FAILED"
            state["recovered_at"] = now()
        else:
            fail("Unsupported command")
        self.save(state, cmd)
        return state

    def validate(self, state):
        self.schema("state", state)
        if "baseline_manifest" in state:
            self.workspaces(state)
            self.suite(state)
            for name, digest in state["baseline_manifest"].items():
                require(
                    sha(self.safe(self.proposal(state["id"]) / "baseline", name).read_bytes())
                    == digest,
                    "Baseline backup corrupt",
                )
        if state["status"] in [
            "EVALUATED",
            "READY_FOR_APPROVAL",
            "APPROVED",
            "APPLYING",
            "APPLIED",
        ]:
            require(
                self.current_digest(state) == state.get("digest", self.current_digest(state)),
                "Digest mismatch",
            )


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    commands = p.add_subparsers(dest="command", required=True)
    c = commands.add_parser("observe")
    c.add_argument("--event", required=True)
    c = commands.add_parser("init")
    c.add_argument("id")
    c.add_argument("--report", required=True)
    for name in ["status", "validate"]:
        c = commands.add_parser(name)
        c.add_argument("id", nargs="?")
    commands.add_parser("list")
    for name in ["close", "apply", "recover"]:
        c = commands.add_parser(name)
        c.add_argument("id")
    c = commands.add_parser("prepare")
    c.add_argument("id")
    for name in ["baseline-root", "candidate-root", "suite", "inspector"]:
        c.add_argument("--" + name, required=True)
    for name, actor in [
        ("reproduce", "inspector"),
        ("candidate", "optimizer"),
        ("evaluate", "evaluator"),
    ]:
        c = commands.add_parser(name)
        c.add_argument("id")
        c.add_argument("--" + actor, required=True)
        if name == "candidate":
            c.add_argument("--change-plan", required=True)
        if name == "evaluate":
            c.add_argument("--behavior-report", required=True)
    c = commands.add_parser("request-approval")
    c.add_argument("id")
    c.add_argument("--action", choices=["apply", "rollback"], default="apply")
    for name in ["record-approval", "rollback"]:
        c = commands.add_parser(name)
        c.add_argument("id")
        c.add_argument("--evidence", required=True)
    return p


def main():
    try:
        args = parser().parse_args()
        harness = Harness(args.root)
        with harness.lock():
            value = harness.execute(args)
        print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except (ValueError, OSError, KeyError, TypeError, jsonschema.ValidationError) as exc:
        if isinstance(exc, jsonschema.ValidationError):
            detail = (
                "Schema validation failed: "
                + str(exc.validator)
                + " at "
                + ".".join(map(str, exc.absolute_path))
            )
        else:
            detail = str(exc)
        print("ERROR: " + str(redact(detail)), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
