import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FEATURE_FLOW = ROOT / "scripts" / "feature-flow.sh"
ENDPOINT_FLOW = ROOT / "scripts" / "endpoint-flow.sh"
TASK_COMPLETED_GUARD = ROOT / "scripts" / "harness-task-completed-guard.sh"


def run(cmd, cwd, *, env=None, check=True):
    merged_env = os.environ.copy()
    merged_env["HARNESS_PROJECT_ROOT"] = str(cwd)
    if env:
        merged_env.update(env)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result


def test_feature_owner_mismatch_is_rejected(tmp_path):
    run([FEATURE_FLOW, "init", "main-home", "--task-id", "8"], tmp_path)

    result = run(
        [FEATURE_FLOW, "transition", "main-home", "PLAN_DRAFTING", "--by", "fe-dev"],
        tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "Owner mismatch" in result.stderr


def test_feature_plan_review_requires_plan_artifacts(tmp_path):
    run([FEATURE_FLOW, "init", "main-home", "--task-id", "8"], tmp_path)
    run([FEATURE_FLOW, "transition", "main-home", "PLAN_DRAFTING", "--by", "fe-planner"], tmp_path)

    result = run(
        [FEATURE_FLOW, "transition", "main-home", "PLAN_REVIEW", "--by", "fe-planner"],
        tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "PLAN_REVIEW requires artifacts.spec_path" in result.stderr


def test_task_completed_is_blocked_until_feature_final_state(tmp_path):
    run([FEATURE_FLOW, "init", "main-home", "--task-id", "8"], tmp_path)

    result = run(
        [FEATURE_FLOW, "guard-task-completed", "--task-id", "8", "--by", "fe-planner"],
        tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "task_completed rejected" in result.stderr


def test_task_completed_blocks_unlinked_workflow_task(tmp_path):
    task_dir = tmp_path / "home" / ".codex" / "tasks" / tmp_path.name
    task_dir.mkdir(parents=True)
    (task_dir / "8.json").write_text(
        json.dumps(
            {
                "id": "8",
                "subject": "FE1: main-home 페이지 mockup 구현",
                "owner": "fe-planner",
                "status": "in_progress",
                "description": "fe-planner -> fe-dev Mock 라이프사이클",
            }
        )
    )

    result = run(
        [FEATURE_FLOW, "guard-task-completed", "--task-id", "8", "--by", "fe-planner"],
        tmp_path,
        env={"HOME": str(tmp_path / "home")},
        check=False,
    )

    assert result.returncode != 0
    assert "no workflow state is linked" in result.stderr


def test_task_completed_hook_blocks_non_final_feature_state(tmp_path):
    run([FEATURE_FLOW, "init", "main-home", "--task-id", "8"], tmp_path)

    result = subprocess.run(
        [TASK_COMPLETED_GUARD],
        cwd=tmp_path,
        env={**os.environ, "CODEX_PROJECT_DIR": str(tmp_path)},
        input=json.dumps({"task_id": "8", "teammate_name": "fe-planner", "cwd": str(tmp_path)}),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 2
    assert json.loads(result.stdout)["decision"] == "block"
    assert "task_completed rejected" in result.stdout


def test_task_completed_allows_final_feature_state(tmp_path):
    state_dir = tmp_path / ".codex" / "state" / "feature-flow"
    state_dir.mkdir(parents=True)
    (state_dir / "main-home.json").write_text(
        json.dumps(
            {
                "feature_id": "main-home",
                "tasklist_id": "8",
                "current_stage": "FE_DONE_AWAITING_BE",
                "feature": {"title": "Main home", "requirements_doc": "docs/features/main-home.md"},
                "phase": "mock",
                "state": "FE_DONE_AWAITING_BE",
                "owner": "team-lead",
                "iteration": {
                    "plan_review_loop": 0,
                    "playwright_loop": 0,
                    "review_loop": 0,
                    "integration_loop": 0,
                },
                "endpoint_requests": ["GET__api_v1_home"],
                "be_dependency_state": {},
                "artifacts": {},
                "evidence": {},
                "gates": {},
                "blockers": [],
                "next_action": {"agent": "team-lead", "command": "complete"},
            }
        )
    )

    result = run([FEATURE_FLOW, "guard-task-completed", "--task-id", "8", "--by", "team-lead"], tmp_path)

    assert "approve" in result.stdout


def test_endpoint_transition_requires_test_pass_before_review(tmp_path):
    run([ENDPOINT_FLOW, "init", "phase-1", "--task-id", "1"], tmp_path)
    run([ENDPOINT_FLOW, "transition", "phase-1", "SPEC_DRAFTING", "--by", "be-test"], tmp_path)
    run(
        [
            ENDPOINT_FLOW,
            "transition",
            "phase-1",
            "SPEC_REVIEW",
            "--by",
            "be-test",
            "--spec-path",
            "docs/spec/endpoints/phase-1.md",
            "--testplan-path",
            "docs/spec/endpoints/phase-1.testplan.md",
        ],
        tmp_path,
    )
    run([ENDPOINT_FLOW, "transition", "phase-1", "SPEC_APPROVED", "--by", "be-reviewer"], tmp_path)
    run([ENDPOINT_FLOW, "transition", "phase-1", "IMPL_IN_PROGRESS", "--by", "be-dev"], tmp_path)
    run([ENDPOINT_FLOW, "transition", "phase-1", "IMPL_PUSHED", "--by", "be-dev", "--impl-commit", "abc1234"], tmp_path)
    run([ENDPOINT_FLOW, "transition", "phase-1", "TESTING", "--by", "be-test"], tmp_path)

    result = run(
        [ENDPOINT_FLOW, "transition", "phase-1", "REVIEW_PENDING", "--by", "be-test"],
        tmp_path,
        check=False,
    )

    assert result.returncode != 0
    assert "test_verdict" in result.stderr
