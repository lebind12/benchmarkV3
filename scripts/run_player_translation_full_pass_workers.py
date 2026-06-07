from __future__ import annotations

import ast
import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_codex_player_translation_batches import INPUT_FIELDNAMES


def read_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames != INPUT_FIELDNAMES:
            raise SystemExit(f"invalid header in {path}: {reader.fieldnames!r}")
        return sum(1 for _ in reader)


def write_jsonl(path: Path, payload: dict[str, object], *, echo: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(payload, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")
    if echo:
        print(payload, flush=True)


def mirror_result_file(source: Path, mirror_dir: Path) -> Path | None:
    if not source.exists():
        return None
    mirror_dir.mkdir(parents=True, exist_ok=True)
    target = mirror_dir / source.name
    shutil.copy2(source, target)
    return target


def worker_progress(worker: dict[str, object]) -> dict[str, object]:
    worker_dir = Path(worker["work_dir"])
    start_batch = int(worker["start_batch"])
    end_batch = int(worker["end_batch"])
    total = int(worker["limit_batches"])
    done_batches: list[int] = []
    results_dir = worker_dir / "results"
    for path in results_dir.glob("player_translation_codex_batch_*_result.csv"):
        name = path.name
        try:
            batch = int(name.removeprefix("player_translation_codex_batch_").split("_", 1)[0])
        except ValueError:
            continue
        if start_batch <= batch <= end_batch:
            done_batches.append(batch)
    done = len(set(done_batches))
    percent = round((done / total) * 100, 1) if total else 0
    return {
        "worker_index": int(worker["worker_index"]),
        "start_batch": start_batch,
        "end_batch": end_batch,
        "done_batches": done,
        "total_batches": total,
        "percent": percent,
        "last_batch": max(done_batches) if done_batches else None,
        "status": worker["status"],
    }


def parse_batch_report(line: str) -> dict[str, object] | None:
    text = line.strip()
    if not text.startswith("{") or not text.endswith("}"):
        return None
    try:
        payload = ast.literal_eval(text)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if "batch" not in payload or "status" not in payload:
        return None
    return payload


def stream_worker_output(
    proc: subprocess.Popen[str],
    log_fp,
    report_path: Path,
    shared_results_dir: Path,
    worker_index: int,
    prefix: str,
) -> None:
    assert proc.stdout is not None
    for raw_line in iter(proc.stdout.readline, ""):
        log_fp.write(raw_line)
        log_fp.flush()

        payload = parse_batch_report(raw_line)
        if payload is None:
            continue

        batch = payload.get("batch")
        status = payload.get("status")
        output = payload.get("output")
        summary = {
            "event": "batch_complete",
            "worker_index": worker_index,
            "batch": batch,
            "status": status,
            "output": output,
        }
        if "validation" in payload:
            summary["validation"] = payload["validation"]
        if "fallback_used" in payload:
            summary["fallback_used"] = payload["fallback_used"]
        write_jsonl(report_path, summary, echo=False)

        mirrored = None
        if isinstance(output, str):
            mirrored = mirror_result_file(Path(output), shared_results_dir)

        if mirrored is not None:
            print(
                f"{prefix} batch {batch} {status} -> {mirrored.name}",
                flush=True,
            )
        else:
            print(f"{prefix} batch {batch} {status}", flush=True)


def partition_batches(start_batch: int, batch_count: int, worker_count: int) -> list[dict[str, int]]:
    if worker_count <= 0:
        raise SystemExit("--worker-count must be positive")
    if batch_count <= 0:
        raise SystemExit("no batches selected")

    base = batch_count // worker_count
    remainder = batch_count % worker_count
    partitions: list[dict[str, int]] = []
    current = start_batch
    for worker_index in range(1, worker_count + 1):
        size = base + (1 if worker_index <= remainder else 0)
        if size <= 0:
            continue
        partitions.append(
            {
                "worker_index": worker_index,
                "start_batch": current,
                "limit_batches": size,
                "end_batch": current + size - 1,
            }
        )
        current += size
    return partitions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run player translation full-pass workers in parallel and report completion."
    )
    parser.add_argument(
        "--source-csv",
        default="out/player-translation/full-pass/input/player_translation_full_pass_queue.csv",
    )
    parser.add_argument(
        "--work-root",
        default="out/player-translation/full-pass",
    )
    parser.add_argument(
        "--work-dir-prefix",
        default="codex-batches-worker",
        help="Per-worker directory prefix created under --work-root.",
    )
    parser.add_argument("--rows-per-batch", type=int, default=10)
    parser.add_argument("--start-batch", type=int, default=1)
    parser.add_argument("--limit-batches", type=int)
    parser.add_argument("--worker-count", type=int, default=5)
    parser.add_argument("--chunk-batches", type=int, default=5)
    parser.add_argument("--timeout-sec", type=int, default=1200)
    parser.add_argument("--model")
    parser.add_argument("--fallback-model-on-usage-limit")
    parser.add_argument(
        "--reasoning-effort",
        choices=("minimal", "low", "medium", "high"),
        default="medium",
    )
    parser.add_argument(
        "--output-mode",
        choices=("file", "final"),
        default="file",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--root", default=".")
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    return parser.parse_args()


def build_worker_command(
    root: Path,
    source_csv: str,
    work_dir: Path,
    rows_per_batch: int,
    start_batch: int,
    limit_batches: int,
    chunk_batches: int,
    timeout_sec: int,
    model: str | None,
    fallback_model_on_usage_limit: str | None,
    reasoning_effort: str,
    output_mode: str,
    force: bool,
) -> list[str]:
    cmd = [
        sys.executable,
        "-u",
        "scripts/run_player_translation_full_pass_pipeline.py",
        "--source-csv",
        source_csv,
        "--work-dir",
        str(work_dir),
        "--rows-per-batch",
        str(rows_per_batch),
        "--start-batch",
        str(start_batch),
        "--limit-batches",
        str(limit_batches),
        "--chunk-batches",
        str(chunk_batches),
        "--timeout-sec",
        str(timeout_sec),
        "--reasoning-effort",
        reasoning_effort,
        "--output-mode",
        output_mode,
        "--root",
        str(root),
    ]
    if fallback_model_on_usage_limit:
        cmd.extend(
            [
                "--fallback-model-on-usage-limit",
                fallback_model_on_usage_limit,
            ]
        )
    if model:
        cmd.extend(["--model", model])
    if force:
        cmd.append("--force")
    return cmd


def main() -> None:
    args = parse_args()
    if args.rows_per_batch <= 0:
        raise SystemExit("--rows-per-batch must be positive")
    if args.start_batch <= 0:
        raise SystemExit("--start-batch must be positive")
    if args.limit_batches is not None and args.limit_batches <= 0:
        raise SystemExit("--limit-batches must be positive")

    root = Path(args.root).resolve()
    source_csv = Path(args.source_csv)
    if not source_csv.is_absolute():
        source_csv = root / source_csv
    work_root = Path(args.work_root)
    if not work_root.is_absolute():
        work_root = root / work_root
    report_path = work_root / "session_reports.jsonl"
    final_output_dir = work_root / "combined"

    total_rows = read_row_count(source_csv)
    total_batches = (total_rows + args.rows_per_batch - 1) // args.rows_per_batch
    if args.start_batch > total_batches:
        raise SystemExit(
            f"--start-batch {args.start_batch} exceeds total batches {total_batches}"
        )

    selected_total = total_batches - args.start_batch + 1
    if args.limit_batches is not None:
        selected_total = min(selected_total, args.limit_batches)
    if selected_total <= 0:
        raise SystemExit("no batches selected")

    partitions = partition_batches(args.start_batch, selected_total, args.worker_count)
    if not partitions:
        raise SystemExit("no worker partitions were generated")

    work_root.mkdir(parents=True, exist_ok=True)
    shared_results_dir = work_root / "results"
    shared_results_dir.mkdir(parents=True, exist_ok=True)

    workers: list[dict[str, object]] = []
    for partition in partitions:
        worker_index = int(partition["worker_index"])
        worker_dir = work_root / f"{args.work_dir_prefix}{worker_index:02d}"
        worker_dir.mkdir(parents=True, exist_ok=True)
        worker_log = worker_dir / "worker.log"
        cmd = build_worker_command(
            root=root,
            source_csv=str(source_csv),
            work_dir=worker_dir,
            rows_per_batch=args.rows_per_batch,
            start_batch=int(partition["start_batch"]),
            limit_batches=int(partition["limit_batches"]),
            chunk_batches=args.chunk_batches,
            timeout_sec=args.timeout_sec,
            model=args.model,
            fallback_model_on_usage_limit=args.fallback_model_on_usage_limit,
            reasoning_effort=args.reasoning_effort,
            output_mode=args.output_mode,
            force=args.force,
        )
        log_fp = worker_log.open("w", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        stream_thread = threading.Thread(
            target=stream_worker_output,
            args=(
                proc,
                log_fp,
                report_path,
                shared_results_dir,
                worker_index,
                f"[worker{worker_index:02d}]",
            ),
            daemon=True,
        )
        stream_thread.start()
        workers.append(
            {
                "worker_index": worker_index,
                "start_batch": int(partition["start_batch"]),
                "end_batch": int(partition["end_batch"]),
                "limit_batches": int(partition["limit_batches"]),
                "work_dir": worker_dir,
                "process": proc,
                "log_fp": log_fp,
                "stream_thread": stream_thread,
                "status": "running",
            }
        )
        write_jsonl(
            report_path,
            {
                "event": "worker_launched",
                "worker_index": worker_index,
                "start_batch": int(partition["start_batch"]),
                "end_batch": int(partition["end_batch"]),
                "limit_batches": int(partition["limit_batches"]),
                "work_dir": str(worker_dir),
                "log": str(worker_log),
            },
        )

    completed_workers: list[dict[str, object]] = []
    failed_workers: list[dict[str, object]] = []
    last_heartbeat = time.monotonic()

    while workers:
        for worker in list(workers):
            proc = worker["process"]
            assert isinstance(proc, subprocess.Popen)
            rc = proc.poll()
            if rc is None:
                continue

            log_fp = worker.pop("log_fp", None)
            if log_fp is not None:
                log_fp.close()
            stream_thread = worker.pop("stream_thread", None)
            if stream_thread is not None:
                stream_thread.join(timeout=5)

            worker_dir = Path(worker["work_dir"])
            worker_index = int(worker["worker_index"])
            worker_report: dict[str, object] = {
                "event": "worker_complete",
                "worker_index": worker_index,
                "start_batch": int(worker["start_batch"]),
                "end_batch": int(worker["end_batch"]),
                "limit_batches": int(worker["limit_batches"]),
                "work_dir": str(worker_dir),
                "returncode": rc,
            }
            if rc == 0:
                combined_summary_path = worker_dir / "combined" / "combined_summary.json"
                if combined_summary_path.exists():
                    worker_report["combined_summary"] = json.loads(
                        combined_summary_path.read_text(encoding="utf-8")
                    )
                shared_combined_path = shared_results_dir / f"worker_{worker_index:02d}_combined_summary.json"
                shared_combined_path.write_text(
                    json.dumps(worker_report.get("combined_summary", {}), ensure_ascii=False, indent=2)
                    + "\n",
                    encoding="utf-8",
                )
                completed_workers.append(worker_report)
                worker["status"] = "completed"
            else:
                worker_report["failed"] = True
                failed_workers.append(worker_report)
                worker["status"] = "failed"
            write_jsonl(report_path, worker_report)
            print(
                f"[worker{worker_index:02d}] complete rc={rc} range={worker['start_batch']}-{worker['end_batch']}",
                flush=True,
            )
            workers.remove(worker)

        now = time.monotonic()
        if workers and now - last_heartbeat >= args.heartbeat_sec:
            progress = [worker_progress(worker) for worker in workers]
            heartbeat = {
                "event": "worker_heartbeat",
                "running_workers": progress,
                "completed_workers": len(completed_workers),
                "failed_workers": len(failed_workers),
            }
            write_jsonl(report_path, heartbeat)
            print(
                "[progress] "
                + " ".join(
                    f"w{item['worker_index']:02d}={item['done_batches']}/{item['total_batches']}({item['percent']}%)"
                    for item in progress
                ),
                flush=True,
            )
            last_heartbeat = now
        if workers:
            time.sleep(5)

    if failed_workers:
        failure_report = {
            "event": "full_pass_failed",
            "reason": "one_or_more_workers_failed",
            "completed_workers": completed_workers,
            "failed_workers": failed_workers,
        }
        write_jsonl(report_path, failure_report)
        raise SystemExit(1)

    validated_dirs = [str(Path(worker["work_dir"]) / "validated") for worker in completed_workers]
    combine_cmd = [
        sys.executable,
        "scripts/combine_player_translation_validated_batches.py",
    ]
    for validated_dir in validated_dirs:
        combine_cmd.extend(["--validated-dir", validated_dir])
    combine_cmd.extend(["--output-dir", str(final_output_dir)])

    print("+ " + " ".join(combine_cmd), flush=True)
    subprocess.run(combine_cmd, cwd=root, check=True)

    final_summary_path = final_output_dir / "combined_summary.json"
    final_summary = (
        json.loads(final_summary_path.read_text(encoding="utf-8"))
        if final_summary_path.exists()
        else {}
    )
    final_report = {
        "event": "full_pass_complete",
        "source_rows": total_rows,
        "total_batches": total_batches,
        "selected_batches": selected_total,
        "worker_count": len(completed_workers),
        "validated_dirs": validated_dirs,
        "combined_summary": final_summary,
    }
    write_jsonl(report_path, final_report)
    print(
        {
            "event": "final_complete",
            "results_dir": str(shared_results_dir),
            "combined_dir": str(final_output_dir),
            "selected_batches": selected_total,
            "worker_count": len(completed_workers),
        },
        flush=True,
    )


if __name__ == "__main__":
    main()
