#!/usr/bin/env python3
"""Optional stdin adapter; install in a supported runner explicitly, never auto-register."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    payload = json.load(sys.stdin)
    task_id = payload.get("task_id", payload.get("taskId"))
    if not isinstance(task_id, (str, int)) or not str(task_id).strip():
        raise ValueError("Missing task_id; cannot verify workflow completion")
    root = Path(payload.get("project_root") or payload.get("cwd") or
                os.environ.get("CODEX_PROJECT_DIR") or Path.cwd()).resolve()
    directory = Path(os.environ.get("HARNESS_STATE_ROOT", root / ".codex/state/work-flow"))
    if not directory.is_absolute():
        directory = root / directory
    matches = []
    for path in directory.glob("*.json"):
        state = json.loads(path.read_text())
        if str(state.get("task_id")) == str(task_id):
            if state.get("id") != path.stem:
                raise ValueError("State ID does not match filename")
            matches.append(state)
    if not matches:
        raise ValueError("No work-flow linked to task; legacy history cannot complete new work")
    actor = payload.get("teammate_name") or payload.get("agent_name") or payload.get("agent")
    for state in matches:
        if actor and actor != state["actors"]["operator"]:
            raise ValueError("Only the assigned operator can complete workflow tasks")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("work-flow.py")),
             "--project-root", str(root), "--state-root", str(directory),
             "guard-task-completed", state["id"]],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise ValueError(result.stderr.strip())
    print(json.dumps({"decision": "approve", "reason": "Operator-recorded MERGED verified"}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"decision": "block", "reason": str(exc)[:1200]}))
        sys.exit(2)
