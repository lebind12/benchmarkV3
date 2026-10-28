"""Bounded subprocesses. Only the host owns execution receipts and log files."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def restricted_env():
    # Retain CLI authentication location, never service/API credentials from the shell.
    names = ("PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME", "SYSTEMROOT")
    return {key: os.environ[key] for key in names if key in os.environ}


def process_identity(pid):
    result = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "lstart="],
                            capture_output=True, text=True, env=restricted_env())
    return result.stdout.strip() if result.returncode == 0 else ""


def reap_interrupted(record):
    """Never signal a reused PID; refuse ambiguous surviving process identity."""
    pid = record.get("pid")
    if not pid:
        return
    observed = process_identity(pid)
    if not observed:
        return
    if not record.get("process_identity") or observed != record["process_identity"]:
        raise ValueError("Interrupted process identity is ambiguous; inspect it manually before resume")
    if os.getpgid(pid) != pid:
        raise ValueError("Interrupted process group changed; manual recovery required")
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline and process_identity(pid) == observed:
        time.sleep(0.1)
    if process_identity(pid) == observed:
        os.killpg(pid, signal.SIGKILL)


def run_process(argv, cwd, log_dir, timeout=900, cancel_path=None, input_text=None, on_start=None):
    """Run an argv without shell expansion and reap its entire process group."""
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and "\0" not in x for x in argv):
        raise ValueError("Command must be a nonempty string argv")
    target = Path(log_dir)
    target.mkdir(parents=True, exist_ok=False)
    started = time.time()
    timed_out = cancelled = False
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err, tempfile.TemporaryFile() as incoming:
        if input_text is not None:
            incoming.write(input_text.encode())
            incoming.seek(0)
        process = subprocess.Popen(argv, cwd=str(cwd), env=restricted_env(),
                                   stdin=incoming if input_text is not None else subprocess.DEVNULL,
                                   stdout=out, stderr=err, start_new_session=True)
        try:
            if on_start:
                on_start({"pid": process.pid, "process_identity": process_identity(process.pid)})
            while process.poll() is None:
                cancelled = bool(cancel_path and Path(cancel_path).exists())
                timed_out = time.time() - started >= timeout
                if cancelled or timed_out:
                    break
                time.sleep(0.1)
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            code = process.wait()
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        logs = {}
        truncated = False
        for name, handle in (("stdout", out), ("stderr", err)):
            handle.seek(0, 2)
            truncated |= handle.tell() > 8 * 1024 * 1024
            handle.seek(0)
            data = handle.read(8 * 1024 * 1024)
            path = target / (name + ".log")
            path.write_bytes(data)
            logs[name] = {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}
    receipt = {"argv": argv, "argv_sha256": digest(argv), "cwd": str(Path(cwd).resolve()),
               "started_at": started, "finished_at": time.time(), "exit_code": code,
               "timeout": timed_out, "cancelled": cancelled, "logs_truncated": truncated, "logs": logs}
    (target / "receipt.json").write_bytes(canonical(receipt))
    return receipt


def codex_argv(workspace, model=None, read_only=False, response_path=None, schema_path=None):
    instructions = (
        "You are a bounded worker inside an external workflow controller, not its operator. "
        "The caller has already selected the work mode and provided your stage. Do not start another "
        "harness, spawn management agents, ask QUICK/FULL again, or run workflow state/approval commands. "
        "Respect domain policies, source ownership, and the frozen contract. Do not reduce scope, "
        "alter approval evidence, merge, push, deploy, read secrets, or print environment variables. "
        "Repository legacy workflow instructions do not authorize restarting orchestration inside this stage. "
        "Read-only stages may inspect but must not change product files. Return unresolved issues honestly."
    )
    argv = ["codex", "exec", "--json", "--ignore-user-config", "--ignore-rules",
            "--ephemeral", "--sandbox", "read-only" if read_only else "workspace-write",
            "-C", str(workspace), "-c", 'approval_policy="never"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", 'sandbox_workspace_write.writable_roots=[]',
            "-c", 'shell_environment_policy.inherit="none"',
            "-c", "mcp_servers={}", "-c", "features.multi_agent=false",
            "-c", 'service_tier="fast"',
            "-c", "model_reasoning_effort=\"medium\"",
            "-c", "developer_instructions=" + json.dumps(instructions)]
    if model:
        argv += ["--model", model]
    if response_path:
        argv += ["--output-last-message", str(response_path)]
    if schema_path:
        argv += ["--output-schema", str(schema_path)]
    return argv + ["-"]


def parse_codex(receipt, response_path):
    events = []
    malformed = False
    for line in Path(receipt["logs"]["stdout"]["path"]).read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except ValueError:
            malformed = True
    completed = any(e.get("type") == "turn.completed" for e in events)
    failed = any(e.get("type") in ("error", "turn.failed") for e in events)
    path = Path(response_path)
    response = path.read_text() if path.is_file() else ""
    tool_evidence = []
    for event in events:
        item = event.get("item", {})
        if (event.get("type") == "item.completed" and item.get("type") == "command_execution"
                and item.get("status") == "completed" and item.get("exit_code") == 0):
            output = item.get("aggregated_output", item.get("output", ""))
            if item.get("id") and isinstance(output, str) and output.strip():
                tool_evidence.append({"id": item["id"], "command": item.get("command", ""),
                                      "exit_code": 0, "output": output,
                                      "output_sha256": hashlib.sha256(output.encode()).hexdigest()})
    return {"transport_ok": receipt["exit_code"] == 0 and completed and not failed and not malformed
            and not receipt["logs_truncated"] and not receipt["timeout"] and not receipt["cancelled"],
            "response": response, "tool_evidence": tool_evidence,
            "thread_ids": [e["thread_id"] for e in events if e.get("type") == "thread.started" and "thread_id" in e]}


def run_codex(workspace, prompt, output_dir, model=None, read_only=True, schema=None, timeout=900, cancel_path=None):
    """Public one-turn adapter for planning clients; no workflow completion inference."""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=False)
    response = target / "response.json"
    schema_path = None
    if schema is not None:
        schema_path = target / "schema.json"
        schema_path.write_bytes(canonical(schema))
    receipt = run_process(codex_argv(workspace, model, read_only, response, schema_path), workspace,
                          target / "execution", timeout, cancel_path, prompt)
    result = parse_codex(receipt, response)
    result["receipt"] = receipt
    return result


def verification_argv(workspace, argv, scratch=None):
    # The only writable root is disposable scratch; source remains outside it.
    import sys
    if scratch is None:
        return ["codex", "sandbox", "-c", 'sandbox_mode="read-only"',
                "-c", "sandbox_read_only.network_access=false", "-C", str(workspace), "--"] + argv
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=False)
    program = ("import json,os,sys; workspace,argv,scratch=json.loads(sys.argv[1]); "
               "os.environ.update({'TMPDIR':scratch,'TMP':scratch,'TEMP':scratch,'PYTHONDONTWRITEBYTECODE':'1',"
               "'PYTEST_ADDOPTS':'-p no:cacheprovider','XDG_CACHE_HOME':scratch+'/cache'}); "
               "os.chdir(workspace); os.execvpe(argv[0],argv,os.environ)")
    return ["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", "sandbox_workspace_write.writable_roots=[]", "-C", str(scratch), "--",
            sys.executable, "-c", program, json.dumps([str(workspace), argv, str(scratch)])]


def boundary_probe_argv(workspace, protected_paths):
    import sys
    program = (
        "import json,os,sys; permitted=[]\n"
        "for path in json.loads(sys.argv[1]):\n"
        " try:\n"
        "  fd=os.open(path,os.O_WRONLY); os.close(fd); permitted.append(path)\n"
        " except PermissionError: pass\n"
        "print(json.dumps({'unexpected_writable':permitted})); sys.exit(1 if permitted else 0)\n"
    )
    return ["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"',
            "-c", "sandbox_workspace_write.network_access=false",
            "-c", "sandbox_workspace_write.exclude_slash_tmp=true",
            "-c", "sandbox_workspace_write.exclude_tmpdir_env_var=true",
            "-c", "sandbox_workspace_write.writable_roots=[]",
            "-C", str(workspace), "--", sys.executable, "-c", program, json.dumps(protected_paths)]
