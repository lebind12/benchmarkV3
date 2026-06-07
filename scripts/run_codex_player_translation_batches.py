from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


INPUT_FIELDNAMES = [
    "api_player_id",
    "api_name_raw",
    "firstname",
    "lastname",
    "nationality_raw",
    "birth_country_raw",
    "current_team_names",
    "current_league_names",
    "previous_name_ko",
    "previous_short_name_ko",
    "manual_override_name_ko",
    "manual_override_short_name_ko",
    "locked_common_name_ko",
    "known_aliases_ko",
    "evidence_ko_candidates",
    "evidence_source_summary",
    "popularity_tier",
    "nationality_ko_mapped",
    "birth_country_ko_mapped",
    "country_mapping_status",
]

OUTPUT_FIELDNAMES = [
    "api_player_id",
    "api_name_raw",
    "firstname",
    "lastname",
    "nationality_raw",
    "birth_country_raw",
    "name_ko",
    "short_name_ko",
    "aliases_ko",
    "name_base_used",
    "name_origin_language",
    "name_structure_type",
    "source_type",
    "source_ref",
    "rule_id",
    "method",
    "confidence",
    "usage_score",
    "usage_conflict",
    "needs_review",
    "review_codes",
    "reason",
]

PROMPT_TEMPLATE_FILE = """\
You are normalizing football player names for a Korean football service UI.

Read this input CSV:
{input_path}

Write exactly this output CSV:
{output_path}

Hard requirements:
- Use the configured Codex model; do not call OpenAI API or web search.
- Create only the requested output CSV. Do not modify source files or docs.
- The output CSV header must be exactly:
{output_header}
- Include every input api_player_id exactly once. No extra rows.
- Keep fields CSV-safe: do not use commas or raw newlines inside any field.
- Use semicolons instead of commas inside reason/source_ref/aliases_ko/review_codes.
- review_codes must be semicolon-separated only.
- Keep terminal output brief.

Decision policy:
- Prefer Korean football usage that Korean users naturally recognize.
- manual_override_name_ko/manual_override_short_name_ko wins; method=accepted_manual_override; confidence=100.
- locked_common_name_ko wins after manual override; method=accepted_service_locked_common; confidence>=95.
- evidence_ko_candidates/evidence_source_summary can justify accepted_korean_football_usage, accepted_usage_over_phonetic, or accepted_usage_over_official.
- previous_name_ko/previous_short_name_ko are useful but not automatically correct.
- Do not transliterate abbreviated api_name_raw like P. Sandler or J. Kim. Use firstname/lastname and add API_NAME_ABBREVIATED.
- Korean players: lastname+firstname, no spaces; short_name_ko is normally full name; surname-only short names require review.
- Japanese and Chinese/East Asian names: family-given order when clear.
- Spanish names: avoid long legal names; use given + primary surname or registered nickname.
- Brazilian/Portuguese names: prefer registered mononym/common football usage.
- Preserve particles like van/de/da/dos/del/de la/bin/ben/al/el when needed for identity.
- If country_mapping_status=missing, needs_review=true and add API_COUNTRY_MAPPING_MISSING.
- If country_mapping_status=football_association, add API_COUNTRY_IS_FOOTBALL_ASSOCIATION; automatic import can still be possible unless another issue exists.
- high popularity players must not be auto-imported from language_rule only; if no common usage confidence, set needs_review=true.
- Add TOO_LONG_LEGAL_NAME only when the selected name_ko itself still looks like a long legal name.
- Do not add TOO_LONG_LEGAL_NAME merely because a long legal source name was shortened successfully.

Allowed method values:
accepted_manual_override, accepted_service_locked_common, accepted_korean_football_usage, accepted_usage_over_phonetic, accepted_usage_over_official, accepted_registered_name, generated_by_language_rule, generated_from_api_first_last, generated_from_api_last_first, review_usage_conflict, review_only_candidate

Allowed source_type values:
manual_override, service_locked_common, korean_football_usage, korean_media_common, korean_community_common, official_ko, wiki_label, api_registered_name, language_rule, llm_candidate

Review codes may include:
COMMON_USAGE_OVERRIDES_PHONETIC, WIKI_LABEL_DIFFERS_FROM_USAGE, OFFICIAL_LABEL_DIFFERS_FROM_USAGE, COMMUNITY_USAGE_DOMINANT, MEDIA_USAGE_DOMINANT, USAGE_CONFLICT_REVIEW, FAMOUS_PLAYER_NO_USAGE_EVIDENCE, API_NAME_ABBREVIATED, FIRST_LAST_MISSING, SHORT_NAME_COLLISION, LATIN_REMAINS, INITIAL_OR_DOT_REMAINS, TOO_LONG_LEGAL_NAME, NATIONALITY_LANGUAGE_MISMATCH, API_COUNTRY_MAPPING_MISSING, API_COUNTRY_IS_FOOTBALL_ASSOCIATION, KOREAN_SHORT_SURNAME_ONLY, LOW_CONFIDENCE_IMPORT_BLOCKED

Confidence:
100 manual override; 95-99 service locked; 90-95 clear Korean football usage; 85-90 consistent evidence/common usage; 75-85 clear structure but weak usage; 60-75 language rule; below 60 review only.

Before finishing, verify the output file has the exact header and exactly the same api_player_id set as the input.
"""

PROMPT_TEMPLATE_FINAL = """\
You are normalizing football player names for a Korean football service UI.

Read this input CSV:
{input_path}

Hard requirements:
- Use the configured Codex model; do not call OpenAI API or web search.
- Do not modify or create any files.
- Your final response must be CSV only. No markdown fence, no explanation.
- The final CSV header must be exactly:
{output_header}
- Include every input api_player_id exactly once. No extra rows.
- Keep fields CSV-safe: do not use commas or raw newlines inside any field.
- Use semicolons instead of commas inside reason/source_ref/aliases_ko/review_codes.
- review_codes must be semicolon-separated only.

Decision policy:
- Prefer Korean football usage that Korean users naturally recognize.
- manual_override_name_ko/manual_override_short_name_ko wins; method=accepted_manual_override; confidence=100.
- locked_common_name_ko wins after manual override; method=accepted_service_locked_common; confidence>=95.
- evidence_ko_candidates/evidence_source_summary can justify accepted_korean_football_usage, accepted_usage_over_phonetic, or accepted_usage_over_official.
- previous_name_ko/previous_short_name_ko are useful but not automatically correct.
- Do not transliterate abbreviated api_name_raw like P. Sandler or J. Kim. Use firstname/lastname and add API_NAME_ABBREVIATED.
- Korean players: lastname+firstname, no spaces; short_name_ko is normally full name; surname-only short names require review.
- Japanese and Chinese/East Asian names: family-given order when clear.
- Spanish names: avoid long legal names; use given + primary surname or registered nickname.
- Brazilian/Portuguese names: prefer registered mononym/common football usage.
- Preserve particles like van/de/da/dos/del/de la/bin/ben/al/el when needed for identity.
- If country_mapping_status=missing, needs_review=true and add API_COUNTRY_MAPPING_MISSING.
- If country_mapping_status=football_association, add API_COUNTRY_IS_FOOTBALL_ASSOCIATION; automatic import can still be possible unless another issue exists.
- high popularity players must not be auto-imported from language_rule only; if no common usage confidence, set needs_review=true.
- Add TOO_LONG_LEGAL_NAME only when the selected name_ko itself still looks like a long legal name.
- Do not add TOO_LONG_LEGAL_NAME merely because a long legal source name was shortened successfully.

Allowed method values:
accepted_manual_override, accepted_service_locked_common, accepted_korean_football_usage, accepted_usage_over_phonetic, accepted_usage_over_official, accepted_registered_name, generated_by_language_rule, generated_from_api_first_last, generated_from_api_last_first, review_usage_conflict, review_only_candidate

Allowed source_type values:
manual_override, service_locked_common, korean_football_usage, korean_media_common, korean_community_common, official_ko, wiki_label, api_registered_name, language_rule, llm_candidate

Review codes may include:
COMMON_USAGE_OVERRIDES_PHONETIC, WIKI_LABEL_DIFFERS_FROM_USAGE, OFFICIAL_LABEL_DIFFERS_FROM_USAGE, COMMUNITY_USAGE_DOMINANT, MEDIA_USAGE_DOMINANT, USAGE_CONFLICT_REVIEW, FAMOUS_PLAYER_NO_USAGE_EVIDENCE, API_NAME_ABBREVIATED, FIRST_LAST_MISSING, SHORT_NAME_COLLISION, LATIN_REMAINS, INITIAL_OR_DOT_REMAINS, TOO_LONG_LEGAL_NAME, NATIONALITY_LANGUAGE_MISMATCH, API_COUNTRY_MAPPING_MISSING, API_COUNTRY_IS_FOOTBALL_ASSOCIATION, KOREAN_SHORT_SURNAME_ONLY, LOW_CONFIDENCE_IMPORT_BLOCKED

Confidence:
100 manual override; 95-99 service locked; 90-95 clear Korean football usage; 85-90 consistent evidence/common usage; 75-85 clear structure but weak usage; 60-75 language rule; below 60 review only.

Before finishing, verify the CSV you return has the exact header and exactly the same api_player_id set as the input.
"""


def read_csv(path: Path, expected_header: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fp:
        reader = csv.DictReader(fp)
        if reader.fieldnames != expected_header:
            raise SystemExit(f"invalid header in {path}: {reader.fieldnames!r}")
        rows = list(reader)
    malformed = [index for index, row in enumerate(rows, start=2) if None in row]
    if malformed:
        raise SystemExit(f"malformed CSV rows in {path}: {malformed[:20]}")
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def validate_result(input_path: Path, output_path: Path) -> dict[str, object]:
    input_rows = read_csv(input_path, INPUT_FIELDNAMES)
    output_rows = read_csv(output_path, OUTPUT_FIELDNAMES)
    input_ids = [row["api_player_id"].strip() for row in input_rows]
    output_ids = [row["api_player_id"].strip() for row in output_rows]
    missing = sorted(set(input_ids) - set(output_ids), key=int)
    extra = sorted(set(output_ids) - set(input_ids), key=int)
    duplicates = sorted({api_id for api_id in output_ids if output_ids.count(api_id) > 1}, key=int)
    ok = not missing and not extra and not duplicates and len(input_ids) == len(output_ids)
    return {
        "ok": ok,
        "input_rows": len(input_rows),
        "output_rows": len(output_rows),
        "missing": missing[:20],
        "extra": extra[:20],
        "duplicates": duplicates[:20],
    }


def batch_rows(rows: list[dict[str, str]], rows_per_batch: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + rows_per_batch] for index in range(0, len(rows), rows_per_batch)]


def strip_final_csv(value: str) -> str:
    text = value.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text + "\n"


def run_codex(
    root: Path,
    input_path: Path,
    output_path: Path,
    log_path: Path,
    timeout: int,
    model: str | None,
    reasoning_effort: str | None,
    output_mode: str,
) -> int:
    template = PROMPT_TEMPLATE_FINAL if output_mode == "final" else PROMPT_TEMPLATE_FILE
    prompt = template.format(
        input_path=input_path,
        output_path=output_path,
        output_header=",".join(OUTPUT_FIELDNAMES),
    )
    last_message_path = log_path.with_suffix(".last-message.txt")
    cmd = [
        "codex",
        "exec",
        "-C",
        str(root),
        "--output-last-message",
        str(last_message_path),
    ]
    if output_mode == "file":
        cmd.extend(["-s", "workspace-write"])
    if model:
        cmd.extend(["-c", f'model="{model}"'])
    if reasoning_effort:
        cmd.extend(["-c", f'model_reasoning_effort="{reasoning_effort}"'])
    cmd.append(prompt)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log_fp:
        proc = subprocess.run(
            cmd,
            cwd=root,
            text=True,
            stdout=log_fp,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    if output_mode == "final" and proc.returncode == 0 and last_message_path.exists():
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            strip_final_csv(last_message_path.read_text(encoding="utf-8")),
            encoding="utf-8",
        )
    return proc.returncode


USAGE_LIMIT_MARKERS = (
    "usage limit",
    "rate limit",
    "quota",
    "too many requests",
    "429",
    "limit reached",
    "usage_limit",
    "rate_limit",
)


def looks_like_usage_limit(log_path: Path) -> bool:
    if not log_path.exists():
        return False
    text = log_path.read_text(encoding="utf-8", errors="replace").lower()
    return any(marker in text for marker in USAGE_LIMIT_MARKERS)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Codex CLI batches for player Korean name normalization."
    )
    parser.add_argument("--source-csv", required=True)
    parser.add_argument("--work-dir", default="out/player-translation/full-pass/codex-batches")
    parser.add_argument("--rows-per-batch", type=int, default=50)
    parser.add_argument("--start-batch", type=int, default=1)
    parser.add_argument("--limit-batches", type=int)
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument(
        "--model",
        help="Override the Codex model for batch calls, for example gpt-5.3-spark.",
    )
    parser.add_argument(
        "--fallback-model-on-usage-limit",
        help="Retry a failed batch once with this model when Codex logs indicate a usage/rate limit.",
    )
    parser.add_argument(
        "--reasoning-effort",
        choices=("minimal", "low", "medium", "high"),
        default="medium",
        help="Override Codex model_reasoning_effort for batch calls.",
    )
    parser.add_argument(
        "--output-mode",
        choices=("file", "final"),
        default="file",
        help="file lets Codex write the result CSV; final captures the final response as CSV.",
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    if args.rows_per_batch <= 0:
        raise SystemExit("--rows-per-batch must be positive")
    if args.start_batch <= 0:
        raise SystemExit("--start-batch is 1-based and must be positive")

    root = Path(args.root).resolve()
    source_csv = Path(args.source_csv)
    if not source_csv.is_absolute():
        source_csv = root / source_csv
    work_dir = Path(args.work_dir)
    if not work_dir.is_absolute():
        work_dir = root / work_dir

    rows = read_csv(source_csv, INPUT_FIELDNAMES)
    batches = batch_rows(rows, args.rows_per_batch)
    selected = list(enumerate(batches, start=1))
    selected = [(idx, batch) for idx, batch in selected if idx >= args.start_batch]
    if args.limit_batches is not None:
        selected = selected[: args.limit_batches]

    input_dir = work_dir / "input"
    result_dir = work_dir / "results"
    log_dir = work_dir / "logs"
    summary_path = work_dir / "run_summary.jsonl"
    work_dir.mkdir(parents=True, exist_ok=True)

    completed = 0
    failed = 0
    with summary_path.open("a", encoding="utf-8") as summary_fp:
        for batch_index, batch in selected:
            stem = f"player_translation_codex_batch_{batch_index:04d}"
            input_path = input_dir / f"{stem}.csv"
            output_path = result_dir / f"{stem}_result.csv"
            log_path = log_dir / f"{stem}.log"
            write_csv(input_path, INPUT_FIELDNAMES, batch)

            if output_path.exists() and not args.force:
                validation = validate_result(input_path, output_path)
                status = "skipped_existing" if validation["ok"] else "invalid_existing"
                if validation["ok"]:
                    completed += 1
                else:
                    failed += 1
                summary = {
                    "batch": batch_index,
                    "status": status,
                    "input": str(input_path),
                    "output": str(output_path),
                    "validation": validation,
                }
                summary_fp.write(json.dumps(summary, ensure_ascii=False) + "\n")
                summary_fp.flush()
                print(summary, flush=True)
                continue

            returncode = run_codex(
                root,
                input_path,
                output_path,
                log_path,
                args.timeout_sec,
                args.model,
                args.reasoning_effort,
                args.output_mode,
            )
            fallback_used = False
            if (
                returncode != 0
                and args.fallback_model_on_usage_limit
                and looks_like_usage_limit(log_path)
            ):
                fallback_used = True
                fallback_log_path = log_path.with_name(f"{log_path.stem}.fallback.log")
                returncode = run_codex(
                    root,
                    input_path,
                    output_path,
                    fallback_log_path,
                    args.timeout_sec,
                    args.fallback_model_on_usage_limit,
                    args.reasoning_effort,
                    args.output_mode,
                )
                log_path = fallback_log_path
            if returncode != 0:
                failed += 1
                summary = {
                    "batch": batch_index,
                    "status": "codex_failed",
                    "returncode": returncode,
                    "fallback_used": fallback_used,
                    "input": str(input_path),
                    "output": str(output_path),
                    "log": str(log_path),
                }
                summary_fp.write(json.dumps(summary, ensure_ascii=False) + "\n")
                summary_fp.flush()
                print(summary, flush=True)
                continue

            validation = validate_result(input_path, output_path)
            if validation["ok"]:
                completed += 1
                status = "completed"
            else:
                failed += 1
                status = "validation_failed"
            summary = {
                "batch": batch_index,
                "status": status,
                "input": str(input_path),
                "output": str(output_path),
                "log": str(log_path),
                "fallback_used": fallback_used,
                "validation": validation,
            }
            summary_fp.write(json.dumps(summary, ensure_ascii=False) + "\n")
            summary_fp.flush()
            print(summary)

    final = {
        "source_rows": len(rows),
        "total_batches": len(batches),
        "selected_batches": len(selected),
        "completed_or_skipped": completed,
        "failed": failed,
        "work_dir": str(work_dir),
    }
    print(final, flush=True)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
