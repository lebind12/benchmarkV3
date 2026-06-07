from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], root: Path) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=root, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run player translation Codex batches and post-process each completed chunk."
        )
    )
    parser.add_argument(
        "--source-csv",
        default="out/player-translation/full-pass/input/player_translation_full_pass_queue.csv",
    )
    parser.add_argument(
        "--work-dir",
        default="out/player-translation/full-pass/codex-batches",
    )
    parser.add_argument("--rows-per-batch", type=int, default=10)
    parser.add_argument("--start-batch", type=int, required=True)
    parser.add_argument("--limit-batches", type=int)
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.start_batch <= 0:
        raise SystemExit("--start-batch must be positive")
    if args.chunk_batches <= 0:
        raise SystemExit("--chunk-batches must be positive")
    if args.limit_batches is not None and args.limit_batches <= 0:
        raise SystemExit("--limit-batches must be positive")

    root = Path(args.root).resolve()
    work_dir = Path(args.work_dir)
    if not work_dir.is_absolute():
        work_dir = root / work_dir

    remaining = args.limit_batches
    current = args.start_batch
    while remaining is None or remaining > 0:
        chunk = args.chunk_batches if remaining is None else min(args.chunk_batches, remaining)
        runner_cmd = [
            sys.executable,
            "-u",
            "scripts/run_codex_player_translation_batches.py",
            "--source-csv",
            args.source_csv,
            "--work-dir",
            args.work_dir,
            "--rows-per-batch",
            str(args.rows_per_batch),
            "--start-batch",
            str(current),
            "--limit-batches",
            str(chunk),
            "--timeout-sec",
            str(args.timeout_sec),
            "--reasoning-effort",
            args.reasoning_effort,
            "--output-mode",
            args.output_mode,
            "--root",
            str(root),
        ]
        if args.fallback_model_on_usage_limit:
            runner_cmd.extend(
                [
                    "--fallback-model-on-usage-limit",
                    args.fallback_model_on_usage_limit,
                ]
            )
        if args.model:
            runner_cmd.extend(["--model", args.model])
        if args.force:
            runner_cmd.append("--force")
        run(runner_cmd, root)

        for batch_index in range(current, current + chunk):
            stem = f"player_translation_codex_batch_{batch_index:04d}"
            input_path = work_dir / "input" / f"{stem}.csv"
            result_path = work_dir / "results" / f"{stem}_result.csv"
            merged_path = work_dir / "merged" / f"{stem}_candidates.csv"
            validated_dir = work_dir / "validated" / f"batch_{batch_index:04d}"
            run(
                [
                    sys.executable,
                    "-u",
                    "scripts/merge_player_translation_results.py",
                    "--input",
                    str(input_path),
                    "--result",
                    str(result_path),
                    "--output",
                    str(merged_path),
                ],
                root,
            )
            run(
                [
                    sys.executable,
                    "-u",
                    "scripts/validate_player_translation_candidates.py",
                    "--input",
                    str(input_path),
                    "--candidates",
                    str(merged_path),
                    "--output-dir",
                    str(validated_dir),
                ],
                root,
            )

        run(
            [
                sys.executable,
                "-u",
                "scripts/combine_player_translation_validated_batches.py",
                "--validated-dir",
                str(work_dir / "validated"),
                "--output-dir",
                str(work_dir / "combined"),
            ],
            root,
        )

        current += chunk
        if remaining is not None:
            remaining -= chunk


if __name__ == "__main__":
    main()
