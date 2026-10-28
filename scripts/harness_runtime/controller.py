"""Host-owned state machine; agent responses are submissions, never authority."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .process import boundary_probe_argv, canonical, codex_argv, digest, parse_codex, reap_interrupted, run_process, verification_argv
from .requirements import REVIEW_SCHEMA, contract_hash, readiness_issues, validate_contract, validate_review


STATES = {"WAITING_REQUIREMENTS", "READY", "DEVELOPING", "VERIFYING", "CHANGES_REQUESTED",
          "VERIFIED", "BLOCKED", "INTERRUPTED", "CANCELLED"}


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Controller:
    def __init__(self, state_root, workspace):
        self.workspace = Path(workspace).expanduser().resolve(strict=True)
        self.root = Path(state_root).expanduser().resolve()
        if self.root == self.workspace or self.root.is_relative_to(self.workspace):
            raise ValueError("State root must be outside the worker workspace")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)
        self.database = self.root / "controller.sqlite3"
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS work(id TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    work_id TEXT NOT NULL, at REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, work_id TEXT NOT NULL,
                    stage TEXT NOT NULL, started REAL NOT NULL, finished REAL, receipt TEXT);
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.database, timeout=15)
        try:
            db.execute("PRAGMA busy_timeout=15000")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @contextmanager
    def _active(self, work_id):
        # One active execution across the workspace, even when work IDs differ.
        with (self.root / "active.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("Another controller execution is active") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def _runtime(self):
        base = Path(__file__).resolve().parent
        return {p.name: file_hash(p) for p in sorted(base.glob("*.py"))}

    def _read(self, work_id):
        with self._db() as db:
            row = db.execute("SELECT state FROM work WHERE id=?", (work_id,)).fetchone()
        if not row:
            raise ValueError("Unknown work ID")
        state = json.loads(row[0])
        if Path(state["workspace"]) != self.workspace:
            raise ValueError("Work belongs to another workspace")
        return state

    def _save(self, state, kind, payload=None):
        if state["status"] not in STATES:
            raise ValueError("Invalid controller status")
        state["updated_at"] = time.time()
        with self._db() as db:
            old = db.execute("SELECT state FROM work WHERE id=?", (state["id"],)).fetchone()
            if old and json.loads(old[0])["revision"] != state["revision"]:
                raise ValueError("Concurrent state change; reload before continuing")
            state["revision"] += 1
            db.execute("INSERT INTO work(id,state) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                       (state["id"], canonical(state).decode()))
            db.execute("INSERT INTO events(work_id,at,kind,payload) VALUES(?,?,?,?)",
                       (state["id"], time.time(), kind, canonical(payload or {"status": state["status"]}).decode()))
        return state

    def _artifact(self, state, name, value):
        path = self.root / state["id"] / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # A fresh version/attempt name is required; never overwrite linked evidence.
        with path.open("xb") as handle:
            handle.write(value if isinstance(value, bytes) else canonical(value))
        return {"path": str(path), "sha256": file_hash(path)}

    def _freeze_files(self, contract):
        frozen = {}
        for name in contract.get("verification_files", []):
            path = (self.workspace / name).resolve(strict=True)
            if not path.is_relative_to(self.workspace) or not path.is_file():
                raise ValueError("Verification files must be regular files within workspace")
            frozen[name] = file_hash(path)
        return frozen

    def _copy_verifiers(self, state):
        for name in state["verification_files"]:
            self._artifact(state, f"frozen-v{state['contract_version']}/" + name,
                           (self.workspace / name).read_bytes())

    def _request_context(self, state):
        return state["original_request"] + "".join(
            "\n\nExplicit scope change:\n" + receipt["message"] for receipt in state.get("request_additions", []))

    def _integrity(self, state):
        if state["runtime"] != self._runtime():
            return "Controller runtime changed; create a new work item"
        for name in ("request_file", "contract_file"):
            record = state[name]
            if not Path(record["path"]).is_file() or file_hash(record["path"]) != record["sha256"]:
                return "Immutable input changed: " + name
        if contract_hash(state["contract"]) != state["contract_hash"]:
            return "Contract digest mismatch"
        for name, fingerprint in state["verification_files"].items():
            path = (self.workspace / name).resolve()
            if not path.is_relative_to(self.workspace) or not path.is_file() or file_hash(path) != fingerprint:
                return "Frozen verification file changed: " + name
        return None

    def create(self, request, contract):
        if not isinstance(request, str) or not request.strip():
            raise ValueError("Original user request is required")
        contract = validate_contract(contract, request=request)
        issues = readiness_issues(contract, request=request)
        work_id = uuid.uuid4().hex
        state = {"id": work_id, "workspace": str(self.workspace), "status": "WAITING_REQUIREMENTS" if issues else "READY",
                 "revision": 0, "created_at": time.time(), "original_request": request,
                 "contract": contract, "contract_hash": contract_hash(contract), "contract_version": 1,
                 "runtime": self._runtime(), "verification_files": self._freeze_files(contract),
                 "issues": issues, "repairs": 0, "spec_review": None, "last_attempt": None}
        state["request_additions"] = []
        state["request_file"] = self._artifact(state, "request.txt", request.encode())
        state["contract_file"] = self._artifact(state, "contract-v1.json", contract)
        self._copy_verifiers(state)
        return self._save(state, "created")

    def _check(self, state):
        issue = self._integrity(state)
        if issue:
            state["status"], state["issues"] = "BLOCKED", [issue]
            self._save(state, "integrity_failed")
            raise ValueError(issue)

    def status(self, work_id):
        state = self._read(work_id)
        issue = self._integrity(state)
        if not issue and state["status"] == "VERIFIED" and state.get("verified_workspace") != self._workspace_fingerprint():
            issue = "Workspace changed after verification"
        if issue and (state["status"] != "BLOCKED" or state["issues"] != [issue]):
            state["status"], state["issues"] = "BLOCKED", [issue]
            self._save(state, "integrity_failed")
        # RUNNING after a crash is not success; resume reconciles under the execution lock.
        return state

    def _execute(self, state, stage, argv, timeout, prompt=None):
        attempt = uuid.uuid4().hex
        state["last_attempt"] = attempt
        self._save(state, "attempt_started", {"id": attempt, "stage": stage, "argv_sha256": digest(argv)})
        with self._db() as db:
            db.execute("INSERT INTO attempts(id,work_id,stage,started) VALUES(?,?,?,?)",
                       (attempt, state["id"], stage, time.time()))
        def started(identity):
            with self._db() as db:
                db.execute("UPDATE attempts SET receipt=? WHERE id=?", (canonical(identity).decode(), attempt))
        try:
            receipt = run_process(argv, self.workspace, self.root / state["id"] / "attempts" / attempt,
                                  timeout=timeout, cancel_path=self.root / state["id"] / "cancel", input_text=prompt,
                                  on_start=started)
        except BaseException as exc:
            with self._db() as db:
                db.execute("UPDATE attempts SET finished=?,receipt=? WHERE id=?",
                           (time.time(), canonical({"error_type": type(exc).__name__, "success": False}).decode(), attempt))
            raise
        with self._db() as db:
            db.execute("UPDATE attempts SET finished=?,receipt=? WHERE id=?",
                       (time.time(), canonical(receipt).decode(), attempt))
        self._save(state, "attempt_finished", {"id": attempt, "stage": stage, "receipt_sha256": digest(receipt)})
        self._check(state)
        if receipt["cancelled"]:
            state["status"] = "CANCELLED"
            self._save(state, "cancelled")
            raise InterruptedError("Work cancelled")
        return receipt

    def _agent(self, state, stage, prompt, model, read_only=True, schema=None):
        nonce = uuid.uuid4().hex
        response = self.root / state["id"] / (stage + "-" + nonce + ".response.json")
        schema_path = None
        if schema:
            schema_path = Path(self._artifact(state, stage + "-" + nonce + ".schema.json", schema)["path"])
        argv = codex_argv(self.workspace, model=model, read_only=read_only,
                          response_path=response, schema_path=schema_path)
        receipt = self._execute(state, stage, argv, state["contract"].get("timeout_seconds", 900), prompt)
        result = parse_codex(receipt, response)
        result["receipt"] = receipt
        return result

    def _boundary(self, state):
        paths = [str(self.database), state["request_file"]["path"], state["contract_file"]["path"]]
        paths += [str(p) for p in Path(__file__).resolve().parent.glob("*.py")]
        paths += [str(self.root / state["id"] / f"frozen-v{state['contract_version']}" / p)
                  for p in state["verification_files"]]
        receipt = self._execute(state, "sandbox-boundary", boundary_probe_argv(self.workspace, paths), 30)
        if receipt["exit_code"] != 0 or receipt["timeout"] or receipt["logs_truncated"]:
            state["status"], state["issues"] = "BLOCKED", [
                "Sandbox boundary unavailable or control files writable; run controller from outside workspace"]
            self._save(state, "sandbox_boundary_failed")
            raise ValueError(state["issues"][0])
        state["boundary_receipt"] = receipt

    def _findings(self, state, result, commands=None, observed=None):
        if not result["transport_ok"]:
            return None, "Reviewer execution did not complete successfully"
        try:
            report = json.loads(result["response"])
            validate_review(report, state["contract"])
            expected = {(r["id"], s["id"]) for r in state["contract"]["requirements"] if r.get("required", True)
                        for s in r["scenarios"]}
            findings = report["findings"]
            actual = [(f["requirement_id"], f["scenario_id"]) for f in findings]
            if set(actual) != expected or len(actual) != len(expected):
                return report, "Reviewer findings must match every required scenario exactly"
            if report["verdict"] != "PASS" or report["coverage_gaps"] or not report["summary"].strip():
                return report, "Reviewer reported missing coverage or non-PASS verdict"
            for finding in findings:
                if finding["status"] != "PASS" or not finding["evidence"].strip():
                    return report, "Every required scenario needs passing evidence"
                if commands is not None or observed is not None:
                    relevant = [c["id"] for c in (commands or []) if finding["requirement_id"] in c["requirement_ids"]]
                    relevant += [value for item in (observed or []) for value in (item["id"], item["command"]) if value.strip()]
                    if not any(command in finding["evidence"] for command in relevant):
                        return report, "Code reviewer must cite an externally executed command covering this requirement"
            return report, None
        except (KeyError, TypeError, ValueError, AttributeError):
            return None, "Malformed reviewer report"

    def _review_spec(self, state, model):
        self._check(state)
        issues = readiness_issues(state["contract"], request=self._request_context(state))
        if issues:
            state["status"], state["issues"] = "WAITING_REQUIREMENTS", issues
            return self._save(state, "requirements_incomplete")
        self._boundary(state)
        prompt = ("Read-only independent requirements review. Compare the ENTIRE original request with the contract. "
                  "Find omissions, unsupported assumptions, ambiguity and non-verifiable scenarios. Do not edit files. "
                  "Return the supplied report schema. PASS only if every required scenario is adequately specified, "
                  "with exact requirement/scenario IDs and concrete rationale in evidence. Any semantic omission goes in coverage_gaps.\n"
                  + json.dumps({"original_request": state["original_request"], "request_additions": state.get("request_additions", []),
                                "contract": state["contract"]}, ensure_ascii=False))
        try:
            result = self._agent(state, "spec-review", prompt, model, schema=REVIEW_SCHEMA)
        except OSError as exc:
            state["status"], state["issues"] = "BLOCKED", ["Spec review process could not start: " + type(exc).__name__]
            return self._save(state, "spec_review_environment_failed")
        report, issue = self._findings(state, result)
        state["spec_review"] = {"contract_hash": state["contract_hash"], "report": report,
                                "receipt": result["receipt"], "thread_ids": result["thread_ids"], "passed": issue is None}
        if not result["transport_ok"]:
            state["status"], state["issues"] = "BLOCKED", [issue]
        else:
            state["status"], state["issues"] = ("WAITING_REQUIREMENTS", [issue]) if issue else ("READY", [])
        return self._save(state, "spec_reviewed")

    def review_spec(self, work_id, model=None):
        with self._active(work_id):
            state = self._read(work_id)
            if state["status"] in ("CANCELLED", "VERIFIED"):
                raise ValueError("Terminal work cannot be reviewed again")
            return self._review_spec(state, model)

    def _workspace_manifest(self):
        # Code/tool logs alone do not prove the tested tree remained unchanged.
        result = {}
        ignored = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".next"}
        for directory, directories, files in os.walk(self.workspace, followlinks=False):
            directories[:] = sorted(d for d in directories if d not in ignored)
            for name in list(directories):
                path = Path(directory) / name
                if path.is_symlink():
                    result[str(path.relative_to(self.workspace))] = "symlink:" + os.readlink(path)
                    directories.remove(name)
            for name in sorted(files):
                path = Path(directory) / name
                relative = str(path.relative_to(self.workspace))
                result[relative] = ("symlink:" + os.readlink(path)) if path.is_symlink() else file_hash(path)
        return result

    def _workspace_fingerprint(self):
        return digest(self._workspace_manifest())

    def _scope_violations(self, before, after, contract):
        changed = [name for name in set(before) | set(after) if before.get(name) != after.get(name)]
        return sorted(name for name in changed if "harness_runtime/" in name or not any(
            fnmatch.fnmatchcase(name, pattern) or name.startswith(pattern.rstrip("/") + "/")
            for pattern in contract["owned_paths"]))

    def _run(self, state, model):
        self._check(state)
        if state["status"] == "VERIFIED":
            if state.get("verified_workspace") != self._workspace_fingerprint():
                state["status"], state["issues"] = "BLOCKED", ["Workspace changed after verification"]
                return self._save(state, "verified_tree_changed")
            return state
        if state["status"] not in ("READY", "CHANGES_REQUESTED"):
            raise ValueError("Work is not ready; resolve requirements or resume interruption first")
        if (not state.get("spec_review") or not state["spec_review"].get("passed")
                or state["spec_review"].get("contract_hash") != state["contract_hash"]):
            state = self._review_spec(state, model)
            if state["status"] != "READY":
                return state
        else:
            self._boundary(state)
        contract = state["contract"]
        while True:
            state["status"] = "DEVELOPING"
            self._save(state, "development_started")
            before = self._workspace_manifest()
            prompt = ("Implement this frozen contract within owned_paths. Do not alter verification_files, "
                      "runtime/controller sources, contract, approval records, git branches, credentials, or deployment. "
                      "Do not merge/push/deploy. A final message is a submission only. Run no host tests; the external controller "
                      "executes frozen verification. Preserve every requirement.\n" + json.dumps({"original_request": state["original_request"],
                      "request_additions": state.get("request_additions", []), "contract": contract,
                      "previous_feedback": state.get("feedback")}, ensure_ascii=False))
            developed = self._agent(state, "development", prompt, model, read_only=False)
            violations = self._scope_violations(before, self._workspace_manifest(), contract)
            if violations:
                state["status"], state["issues"] = "BLOCKED", ["Worker changed paths outside ownership: " + ", ".join(violations)]
                return self._save(state, "ownership_violation")
            if not developed["transport_ok"]:
                state["status"], state["issues"] = "BLOCKED", ["Development subprocess failed or timed out"]
                return self._save(state, "development_failed")
            state["status"] = "VERIFYING"
            self._save(state, "verification_started")
            tree = self._workspace_fingerprint()
            receipts = []
            for command in contract["verification_commands"]:
                scratch = self.root / "scratch" / uuid.uuid4().hex
                receipt = self._execute(state, "verify:" + command["id"], verification_argv(self.workspace, command["argv"], scratch),
                                        command.get("timeout_seconds", 120))
                receipts.append({"id": command["id"], "requirement_ids": command["requirement_ids"], "receipt": receipt})
            if tree != self._workspace_fingerprint():
                state["status"], state["issues"] = "BLOCKED", ["Workspace changed during read-only verification"]
                return self._save(state, "verification_tree_changed")
            command_pass = (bool(receipts) or contract["mode"] == "QUICK") and all(item["receipt"]["exit_code"] == 0 and not item["receipt"]["timeout"]
                                                   and not item["receipt"]["logs_truncated"] for item in receipts)
            report, issue = None, "Externally executed verification commands failed"
            if command_pass:
                prompt = ("Read-only independent CODE and behavior review. Inspect implementation against the complete original request "
                          "and frozen contract. External verification commands below were actually run by the host. Read their logs. "
                          "Do not claim a test ran solely from a model report. For each exact required scenario ID give actual "
                          "observations and cite the relevant command ID in evidence. Return PASS only with no coverage gaps, "
                          "passing external receipts and correct implementation. Actually execute appropriate read-only inspection "
                          "commands producing meaningful output. For QUICK copy/style changes do not invent tests. Each finding's "
                          "evidence must cite the exact inspection command string you actually executed (or known actual tool item ID), "
                          "or the relevant external verification command ID. Never edit files.\n" + json.dumps({
                              "original_request": state["original_request"], "request_additions": state.get("request_additions", []),
                              "contract": contract, "verification": receipts}, ensure_ascii=False))
                reviewed = self._agent(state, "code-review", prompt, model, schema=REVIEW_SCHEMA)
                observations = reviewed["tool_evidence"]
                report, issue = self._findings(state, reviewed, receipts, observations)
                if not observations:
                    issue = "Code reviewer produced no successful observed command execution evidence"
                state["code_review_execution"] = {"receipt": reviewed["receipt"], "thread_ids": reviewed["thread_ids"],
                                                    "tool_evidence": reviewed["tool_evidence"]}
                if tree != self._workspace_fingerprint():
                    issue = "Workspace changed during read-only review"
            state["verification"] = receipts
            state["code_review"] = report
            if command_pass and not issue:
                self._check(state)
                state["status"], state["issues"], state["verified_workspace"] = "VERIFIED", [], tree
                return self._save(state, "external_gate_verified", {"contract_hash": state["contract_hash"], "workspace": tree})
            state["feedback"] = {"issue": issue, "review": report, "verification": receipts}
            if state["repairs"] >= contract.get("max_repairs", 2):
                state["status"], state["issues"] = "BLOCKED", [issue or "Verification failed"]
                return self._save(state, "repair_budget_exhausted")
            state["repairs"] += 1
            state["status"], state["issues"] = "CHANGES_REQUESTED", [issue or "Verification failed"]
            self._save(state, "changes_requested")

    def run(self, work_id, model=None):
        with self._active(work_id):
            state = self._read(work_id)
            try:
                return self._run(state, model)
            except InterruptedError:
                return self._read(work_id)
            except BaseException as exc:
                current = self._read(work_id)
                if current["status"] in ("DEVELOPING", "VERIFYING"):
                    current["status"], current["issues"] = "INTERRUPTED", ["Execution interrupted; explicit resume required"]
                    self._save(current, "interrupted", {"error_type": type(exc).__name__})
                raise

    def cancel(self, work_id):
        state = self._read(work_id)
        if state["status"] == "VERIFIED":
            raise ValueError("Verified work cannot be cancelled")
        # No concurrent DB mutation: active worker observes this durable cancellation flag.
        (self.root / work_id / "cancel").touch(exist_ok=True)
        try:
            with self._active(work_id):
                state = self._read(work_id)
                state["status"] = "CANCELLED"
                return self._save(state, "cancelled")
        except ValueError as exc:
            if "Another controller" not in str(exc):
                raise
            return {**state, "cancel_requested": True}

    def resume(self, work_id, model=None):
        with self._active(work_id):
            state = self._read(work_id)
            self._check(state)
            if state["status"] not in ("INTERRUPTED", "DEVELOPING", "VERIFYING", "BLOCKED"):
                raise ValueError("Only interrupted or blocked execution can resume; cancellation is final")
            if state["status"] == "BLOCKED" and state["repairs"] >= state["contract"].get("max_repairs", 2) and state.get("feedback"):
                raise ValueError("Repair budget exhausted; explicit new contract and scope receipt required")
            with self._db() as db:
                unfinished = db.execute("SELECT receipt FROM attempts WHERE work_id=? AND finished IS NULL", (work_id,)).fetchall()
            for row in unfinished:
                reap_interrupted(json.loads(row[0]) if row[0] else {})
            with self._db() as db:
                db.execute("UPDATE attempts SET finished=?,receipt=? WHERE work_id=? AND finished IS NULL",
                           (time.time(), canonical({"interrupted": True, "success": False}).decode(), work_id))
            state["status"], state["issues"] = "READY", []
            self._save(state, "resumed_after_interruption")
            return self._run(state, model)

    def record_scope_change(self, work_id, new_contract, human_receipt):
        """Record a host-asserted receipt; this is not same-UID identity authentication."""
        with self._active(work_id):
            state = self._read(work_id)
            self._check(state)
            if state["status"] == "CANCELLED":
                raise ValueError("Cancellation is final; create a new work item with the follow-up request")
            if not isinstance(human_receipt, dict) or not str(human_receipt.get("message", "")).strip():
                raise ValueError("Human receipt needs the actual explicit message")
            updated_request = self._request_context(state) + "\n\nExplicit scope change:\n" + human_receipt["message"]
            contract = validate_contract(new_contract, request=updated_request)
            new_hash = contract_hash(contract)
            if human_receipt.get("old_hash") != state["contract_hash"] or human_receipt.get("new_hash") != new_hash:
                raise ValueError("Human receipt must bind exact old_hash and new_hash")
            if not human_receipt.get("source"):
                raise ValueError("Human receipt source reference required")
            version = state["contract_version"] + 1
            receipt = self._artifact(state, f"scope-receipt-v{version}.json", human_receipt)
            state["contract_file"] = self._artifact(state, f"contract-v{version}.json", contract)
            state["contract"], state["contract_hash"], state["contract_version"] = contract, new_hash, version
            state.setdefault("request_additions", []).append(human_receipt)
            state["verification_files"] = self._freeze_files(contract)
            self._copy_verifiers(state)
            state["spec_review"], state["code_review"], state["verification"] = None, None, []
            state["repairs"] = 0
            state["issues"] = readiness_issues(contract, request=self._request_context(state))
            state["status"] = "WAITING_REQUIREMENTS" if state["issues"] else "READY"
            return self._save(state, "scope_changed", {"receipt": receipt, "old_hash": human_receipt["old_hash"], "new_hash": new_hash})
