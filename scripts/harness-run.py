#!/usr/bin/env python3
"""Load an immutable controller copy outside the coding workspace."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parent


def option(name, default):
    for index, arg in enumerate(sys.argv[1:], 1):
        if arg == name and index + 1 < len(sys.argv):
            return sys.argv[index + 1]
        if arg.startswith(name + "="):
            return arg.split("=", 1)[1]
    return default


def main():
    workspace = Path(option("--workspace", str(Path.cwd()))).expanduser().resolve()
    key = hashlib.sha256(str(workspace).encode()).hexdigest()[:20]
    default = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "benchmark-harness" / key
    state = Path(option("--state-root", str(default))).expanduser().resolve()
    os.environ["BENCHMARK_HARNESS_SOURCE_ROOT"] = str(SOURCE.parent)
    os.environ["BENCHMARK_HARNESS_STATE_ROOT"] = str(state)
    if "--help" in sys.argv or "-h" in sys.argv or len(sys.argv) == 1:
        sys.path.insert(0, str(SOURCE))
    else:
        if state == workspace or state.is_relative_to(workspace):
            raise ValueError("Controller state must be outside the development workspace")
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        modules = sorted((SOURCE / "harness_runtime").glob("*.py"))
        digest = hashlib.sha256()
        for path in modules:
            digest.update(path.name.encode() + b"\0" + path.read_bytes() + b"\0")
        versions = state / "runtimes"
        versions.mkdir(exist_ok=True)
        target = versions / digest.hexdigest()
        if not target.exists():
            temporary = Path(tempfile.mkdtemp(prefix=".runtime-", dir=versions))
            package = temporary / "harness_runtime"
            package.mkdir()
            for path in modules:
                shutil.copyfile(path, package / path.name)
                (package / path.name).chmod(0o400)
            try:
                temporary.rename(target)
            except FileExistsError:
                shutil.rmtree(temporary)
        for path in modules:
            if (target / "harness_runtime" / path.name).read_bytes() != path.read_bytes():
                raise ValueError("Frozen controller copy changed")
        sys.path.insert(0, str(target))
    from harness_runtime.cli import main as cli
    return cli()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"Harness: {error}", file=sys.stderr)
        raise SystemExit(2)
