"""Project role settings must preserve operator choice and deprecated history."""
from pathlib import Path
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[2]
ACTIVE_ROLES = {"tech-researcher", "service-researcher", "planning-reviewer", "operations-reviewer",
                "developer", "behavior-tester", "service-portfolio"}
LEGACY_ROLES = {"fe-planner", "fe-dev", "fe-reviewer", "be-test", "be-dev", "be-reviewer"}
IMPROVEMENT_ROLES = {"harness-inspector", "harness-optimizer", "harness-evaluator"}


def test_project_defaults_leave_operator_model_unchanged():
    config = tomllib.loads((ROOT / ".codex/config.toml").read_text())
    assert "model" not in config
    assert "model_reasoning_effort" not in config
    assert config["service_tier"] == "fast"
    assert config["agents"]["enabled"] is True
    assert config["agents"]["default_subagent_model"] == "gpt-6.1-sol"
    assert config["agents"]["default_subagent_reasoning_effort"] == "medium"
    assert config["agents"]["max_concurrent_threads_per_session"] == 3
    assert "hooks" not in config  # Optional completion adapter is never auto-installed.


def test_exact_active_and_deprecated_role_inventory():
    actual = {p.stem for p in (ROOT / ".codex/agents").glob("*.toml")}
    assert actual == ACTIVE_ROLES | IMPROVEMENT_ROLES | LEGACY_ROLES


@pytest.mark.parametrize("role", sorted(IMPROVEMENT_ROLES))
def test_improvement_roles_preserve_model_choice_and_human_approval_boundary(role):
    data = tomllib.loads((ROOT / f".codex/agents/{role}.toml").read_text())
    assert data["name"] == role
    assert data["model_reasoning_effort"] == "medium"
    assert "model" not in data
    assert "service_tier" not in data
    instructions = data["developer_instructions"]
    assert ".harness/AGENTS.md" in instructions
    assert "docs/spec/harness-self-improvement.md" in instructions
    assert "하위 에이전트는 승인 기록 생성·apply·rollback을 실행하지 않는다" in instructions


@pytest.mark.parametrize("role", sorted(ACTIVE_ROLES))
def test_active_roles_allow_explicit_model_selection(role):
    data = tomllib.loads((ROOT / f".codex/agents/{role}.toml").read_text())
    assert data["name"] == role
    assert data["model_reasoning_effort"] == "medium"
    assert "model" not in data
    assert "service_tier" not in data
    instructions = data["developer_instructions"]
    assert "docs/spec/agentic-workflow.md" in instructions
    assert "운영자" in instructions
    assert "다른 변경을 되돌리지" in instructions


@pytest.mark.parametrize("role", sorted(LEGACY_ROLES))
def test_legacy_roles_only_redirect_to_current_workflow(role):
    data = tomllib.loads((ROOT / f".codex/agents/{role}.toml").read_text())
    assert data["model_reasoning_effort"] == "medium"
    assert "model" not in data
    instructions = data["developer_instructions"]
    assert "신규 작업에 사용하지 않는다" in instructions
    assert "재배정" in instructions
    assert f".codex/legacy/agents/{role}.toml" in instructions
    assert "현재 지시가 아니다" in instructions


def test_tracked_legacy_states_have_no_changes_from_head():
    result = subprocess.run(["git", "diff", "--exit-code", "HEAD", "--",
                             ".codex/state/feature-flow", ".codex/state/endpoint-flow"],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
