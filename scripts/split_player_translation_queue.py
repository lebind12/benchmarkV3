from __future__ import annotations

import argparse
import csv
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Split player translation queue CSV into shards.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--rows-per-shard", type=int, default=400)
    parser.add_argument("--prefix", default="player_translation_input")
    args = parser.parse_args()

    if args.rows_per_shard <= 0:
        raise SystemExit("--rows-per-shard must be positive")

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    if not fieldnames:
        raise SystemExit(f"empty CSV header: {input_path}")

    shard_count = 0
    for index in range(0, len(rows), args.rows_per_shard):
        shard_count += 1
        shard_rows = rows[index : index + args.rows_per_shard]
        output = output_dir / f"{args.prefix}_{shard_count:03d}.csv"
        with output.open("w", encoding="utf-8", newline="") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(shard_rows)

    print(
        {
            "input": str(input_path),
            "rows": len(rows),
            "rows_per_shard": args.rows_per_shard,
            "shards": shard_count,
            "output_dir": str(output_dir),
        }
    )


if __name__ == "__main__":
    main()
