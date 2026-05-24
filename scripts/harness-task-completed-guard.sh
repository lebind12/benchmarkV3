#!/usr/bin/env bash
set -euo pipefail

payload="$(cat)"
{
  IFS= read -r task_id
  IFS= read -r actor
  IFS= read -r project_root
} < <(
  PAYLOAD="$payload" node -e '
    let input = {};
    try {
      input = JSON.parse(process.env.PAYLOAD || "{}");
    } catch {
      input = {};
    }
    const fields = [
      input.task_id ?? input.taskId ?? "",
      input.teammate_name ?? input.agent_name ?? input.teammate ?? input.agent_type ?? "",
      input.project_root ?? input.cwd ?? process.env.CODEX_PROJECT_DIR ?? process.env.CLAUDE_PROJECT_DIR ?? process.cwd(),
    ];
    process.stdout.write(fields.map((v) => String(v).replace(/\r?\n/g, " ")).join("\n") + "\n");
  '
)

if [ -z "$task_id" ]; then
  printf '{"decision":"approve","reason":"workflow guard skipped: no task_id"}\n'
  exit 0
fi

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/harness-task-guard.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT
touch "$tmpdir/feature.err" "$tmpdir/endpoint.err"

if node "$(dirname "$0")/harness-flow.mjs" feature guard-task-completed --project-root "$project_root" --task-id "$task_id" --by "$actor" >"$tmpdir/feature.out" 2>"$tmpdir/feature.err"; then
  if node "$(dirname "$0")/harness-flow.mjs" endpoint guard-task-completed --project-root "$project_root" --task-id "$task_id" --by "$actor" >"$tmpdir/endpoint.out" 2>"$tmpdir/endpoint.err"; then
    printf '{"decision":"approve","reason":"workflow final-state guard passed"}\n'
    exit 0
  fi
fi

reason="$(cat "$tmpdir/feature.err" "$tmpdir/endpoint.err" 2>/dev/null | tr '\n' ' ' | cut -c1-900)"
if [ -z "$reason" ]; then
  reason="TaskCompleted rejected by workflow final-state guard"
fi
encoded_reason="$(REASON="$reason" node -e 'process.stdout.write(JSON.stringify(process.env.REASON || ""))')"
printf '{"decision":"block","reason":%s}\n' "$encoded_reason"
exit 2
