#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const KIND_CONFIG = {
  endpoint: {
    dir: "endpoint-flow",
    idField: "endpoint_id",
    finalStates: new Set(["MERGED"]),
    terminalStates: new Set(["MERGED", "ESCALATED", "SPEC_FAILED"]),
    initialState: "FE_REQUESTED",
    initialOwner: "be-test",
    stateOwners: {
      FE_REQUESTED: "be-test",
      SPEC_DRAFTING: "be-test",
      SPEC_REVIEW: "be-reviewer",
      SPEC_APPROVED: "be-dev",
      SPEC_FAILED: "team-lead",
      IMPL_IN_PROGRESS: "be-dev",
      IMPL_PUSHED: "be-test",
      TESTING: "be-test",
      TEST_FAILED: "be-dev",
      REVIEW_PENDING: "be-reviewer",
      CHANGES_REQUESTED: "be-dev",
      MERGE_GATE: "team-lead",
      PR_CREATED: "team-lead",
      MERGED: "team-lead",
      ESCALATED: "team-lead"
    },
    transitions: {
      FE_REQUESTED: ["SPEC_DRAFTING", "ESCALATED"],
      SPEC_DRAFTING: ["SPEC_REVIEW", "SPEC_FAILED", "ESCALATED"],
      SPEC_REVIEW: ["SPEC_APPROVED", "SPEC_FAILED", "SPEC_DRAFTING", "ESCALATED"],
      SPEC_APPROVED: ["IMPL_IN_PROGRESS", "ESCALATED"],
      IMPL_IN_PROGRESS: ["IMPL_PUSHED", "ESCALATED"],
      IMPL_PUSHED: ["TESTING", "ESCALATED"],
      TESTING: ["REVIEW_PENDING", "TEST_FAILED", "ESCALATED"],
      TEST_FAILED: ["IMPL_IN_PROGRESS", "ESCALATED"],
      REVIEW_PENDING: ["MERGE_GATE", "CHANGES_REQUESTED", "ESCALATED"],
      CHANGES_REQUESTED: ["IMPL_IN_PROGRESS", "ESCALATED"],
      MERGE_GATE: ["PR_CREATED", "ESCALATED"],
      PR_CREATED: ["MERGED", "ESCALATED"],
      SPEC_FAILED: ["SPEC_DRAFTING", "ESCALATED"],
      ESCALATED: [],
      MERGED: []
    },
    gateForTarget: {
      SPEC_REVIEW: requireEndpointSpecArtifacts,
      REVIEW_PENDING: requireEndpointTestPass,
      MERGE_GATE: requireEndpointReviewApproval,
      PR_CREATED: requireEndpointReviewApproval,
      MERGED: requireEndpointReviewApproval
    }
  },
  feature: {
    dir: "feature-flow",
    idField: "feature_id",
    finalStates: new Set(["FE_DONE_AWAITING_BE", "DONE"]),
    terminalStates: new Set(["FE_DONE_AWAITING_BE", "DONE", "ESCALATED", "PLAN_FAILED"]),
    initialState: "TRIGGERED",
    initialOwner: "fe-planner",
    stateOwners: {
      TRIGGERED: "fe-planner",
      PLAN_DRAFTING: "fe-planner",
      PLAN_REVIEW: "fe-reviewer",
      PLAN_APPROVED: "fe-dev",
      PLAN_FAILED: "team-lead",
      IMPL_IN_PROGRESS: "fe-dev",
      IMPL_PUSHED: "fe-dev",
      PLAYWRIGHT_RUN: "fe-dev",
      REVIEW_PENDING: "fe-reviewer",
      CHANGES_REQUESTED: "fe-dev",
      MERGE_GATE: "team-lead",
      PR_CREATED: "team-lead",
      MERGED: "fe-dev",
      BE_REQUEST_GENERATED: "fe-dev",
      FE_DONE_AWAITING_BE: "team-lead",
      INTEGRATION_TRIGGERED: "fe-dev",
      INTEGRATION_IN_PROGRESS: "fe-dev",
      INTEGRATION_PUSHED: "fe-dev",
      L3_RUN: "fe-dev",
      INTEGRATION_FAILED: "fe-dev",
      L4_SMOKE: "team-lead",
      DONE: "team-lead",
      ESCALATED: "team-lead"
    },
    transitions: {
      TRIGGERED: ["PLAN_DRAFTING", "PLAN_FAILED", "ESCALATED"],
      PLAN_DRAFTING: ["PLAN_REVIEW", "PLAN_FAILED", "ESCALATED"],
      PLAN_REVIEW: ["PLAN_APPROVED", "PLAN_DRAFTING", "PLAN_FAILED", "ESCALATED"],
      PLAN_APPROVED: ["IMPL_IN_PROGRESS", "ESCALATED"],
      IMPL_IN_PROGRESS: ["IMPL_PUSHED", "ESCALATED"],
      IMPL_PUSHED: ["PLAYWRIGHT_RUN", "ESCALATED"],
      PLAYWRIGHT_RUN: ["REVIEW_PENDING", "IMPL_IN_PROGRESS", "ESCALATED"],
      REVIEW_PENDING: ["MERGE_GATE", "IMPL_IN_PROGRESS", "CHANGES_REQUESTED", "ESCALATED"],
      CHANGES_REQUESTED: ["IMPL_IN_PROGRESS", "ESCALATED"],
      MERGE_GATE: ["PR_CREATED", "ESCALATED"],
      PR_CREATED: ["MERGED", "ESCALATED"],
      MERGED: ["BE_REQUEST_GENERATED", "L4_SMOKE", "ESCALATED"],
      BE_REQUEST_GENERATED: ["FE_DONE_AWAITING_BE", "ESCALATED"],
      FE_DONE_AWAITING_BE: ["INTEGRATION_TRIGGERED"],
      INTEGRATION_TRIGGERED: ["INTEGRATION_IN_PROGRESS", "ESCALATED"],
      INTEGRATION_IN_PROGRESS: ["INTEGRATION_PUSHED", "ESCALATED"],
      INTEGRATION_PUSHED: ["L3_RUN", "ESCALATED"],
      L3_RUN: ["REVIEW_PENDING", "INTEGRATION_FAILED", "ESCALATED"],
      INTEGRATION_FAILED: ["INTEGRATION_IN_PROGRESS", "ESCALATED"],
      L4_SMOKE: ["DONE", "ESCALATED"],
      PLAN_FAILED: ["PLAN_DRAFTING", "ESCALATED"],
      ESCALATED: [],
      DONE: []
    },
    gateForTarget: {
      PLAN_REVIEW: requireFeaturePlanArtifacts,
      PLAN_APPROVED: requireFeaturePlanApprovalActor,
      IMPL_PUSHED: requireFeatureImplCommit,
      REVIEW_PENDING: requireFeatureTestEvidence,
      MERGE_GATE: requireFeatureReviewApproval,
      PR_CREATED: requireFeatureReviewApproval,
      BE_REQUEST_GENERATED: requireFeatureEndpointRequests,
      FE_DONE_AWAITING_BE: requireFeatureEndpointRequests,
      DONE: requireFeatureReviewApproval
    }
  }
};

function main() {
  const [kind, command, ...rest] = process.argv.slice(2);
  if (!KIND_CONFIG[kind]) {
    die("Usage: harness-flow.mjs <endpoint|feature> <command> [args...]");
  }
  const cfg = KIND_CONFIG[kind];
  const opts = parseArgs(rest);
  const root = opts.projectRoot || process.env.HARNESS_PROJECT_ROOT || findProjectRoot(process.cwd());

  switch (command) {
    case "init":
      return initFlow(cfg, root, opts);
    case "transition":
    case "stage-completed":
      return transitionFlow(cfg, root, opts);
    case "status":
      return statusFlow(cfg, root, opts);
    case "list":
      return listFlows(cfg, root, opts);
    case "validate":
      return validateOne(cfg, root, opts);
    case "validate-all":
      return validateAll(cfg, root, opts);
    case "guard-task-completed":
      return guardTaskCompleted(root, opts);
    case "start-integration":
      if (kind !== "feature") die("start-integration is only valid for feature flows");
      return startIntegration(cfg, root, opts);
    default:
      die(`Unknown command: ${command}`);
  }
}

function parseArgs(args) {
  const out = { _: [] };
  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    if (!arg.startsWith("--")) {
      out._.push(arg);
      continue;
    }
    const key = arg.slice(2);
    if (key === "force" || key === "strict-tasklist" || key === "json" || key === "allow-missing-evidence") {
      out[toCamel(key)] = true;
      continue;
    }
    const value = args[i + 1];
    if (value == null || value.startsWith("--")) die(`Missing value for --${key}`);
    i += 1;
    const camel = toCamel(key);
    if (camel === "endpointRequest") {
      out.endpointRequest = [...(out.endpointRequest || []), value];
    } else {
      out[camel] = value;
    }
  }
  return out;
}

function toCamel(value) {
  return value.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

function initFlow(cfg, root, opts) {
  const id = opts._[0];
  if (!id) die("init requires an id");
  const statePath = flowPath(cfg, root, id);
  ensureDir(path.dirname(statePath));
  if (fs.existsSync(statePath) && !opts.force) {
    die(`${statePath} already exists; pass --force to replace`);
  }
  const state = baseState(cfg, id, opts);
  writeJSONAtomic(statePath, state);
  appendHistory(cfg, root, id, {
    from: null,
    to: state.state,
    by: opts.by || "team-lead",
    note: opts.note || "init"
  });
  printJSON(state);
}

function baseState(cfg, id, opts) {
  if (cfg.dir === "endpoint-flow") {
    return {
      endpoint_id: id,
      tasklist_id: opts.taskId || null,
      current_stage: cfg.initialState,
      endpoint: {
        method: opts.method || "N/A",
        path: opts.path || "N/A",
        fe_mockup_ref: opts.feMockup || null
      },
      state: cfg.initialState,
      owner: cfg.initialOwner,
      iteration: { test_loop: 0, review_loop: 0 },
      artifacts: {
        spec_path: opts.specPath || null,
        test_plan_path: opts.testplanPath || opts.testPlanPath || null,
        test_code_path: opts.testCodePath || null,
        integration_test_code_path: opts.integrationTestCodePath || null,
        impl_branch: opts.branch || null,
        impl_commit: opts.commit || opts.implCommit || null,
        migrations: []
      },
      evidence: {},
      gates: {
        spec_approved_by: null,
        test_passed_at: null,
        review_approved_by: null,
        merge_approved_by: null
      },
      blockers: [],
      next_action: {
        agent: cfg.initialOwner,
        command: "start endpoint workflow"
      }
    };
  }
  return {
    feature_id: id,
    tasklist_id: opts.taskId || null,
    current_stage: cfg.initialState,
    feature: {
      title: opts.title || id,
      requirements_doc: opts.requirements || `docs/features/${id}.md`
    },
    phase: opts.phase || "mock",
    state: cfg.initialState,
    owner: cfg.initialOwner,
    iteration: {
      plan_review_loop: 0,
      playwright_loop: 0,
      review_loop: 0,
      integration_loop: 0
    },
    endpoint_requests: [],
    be_dependency_state: {},
    artifacts: {
      spec_path: opts.specPath || null,
      devplan_path: opts.devplanPath || null,
      testplan_path: opts.testplanPath || null,
      branch: opts.branch || null,
      commit: opts.commit || null,
      playwright_e2e_paths: []
    },
    evidence: {},
    gates: {
      plan_approved_by: null,
      review_approved_by: null,
      merge_approved_by: null
    },
    blockers: [],
    next_action: {
      agent: cfg.initialOwner,
      command: "start feature workflow"
    }
  };
}

function transitionFlow(cfg, root, opts) {
  const [id, nextState] = opts._;
  if (!id || !nextState) die("transition requires <id> <new_state>");
  const statePath = flowPath(cfg, root, id);
  const state = readJSON(statePath);
  const current = state.state;
  const allowed = cfg.transitions[current] || [];
  if (!allowed.includes(nextState)) {
    die(`Invalid transition for ${id}: ${current} -> ${nextState}`);
  }
  const actor = opts.by;
  if (!actor) die("transition requires --by <agent>");
  if (!opts.force && actor !== state.owner) {
    die(`Owner mismatch for ${id}: current owner is ${state.owner}, got ${actor}`);
  }
  if (opts.force && actor !== "team-lead") {
    die("--force transitions are only allowed for team-lead");
  }

  applyOptions(state, opts);
  const gate = cfg.gateForTarget[nextState];
  if (gate) gate(state, actor, opts);

  updateCounters(state, current, nextState, cfg.dir);
  applyAutoGates(state, cfg.dir, nextState, actor);

  state.state = nextState;
  state.current_stage = nextState;
  state.owner = cfg.stateOwners[nextState] || state.owner;
  state.next_action = nextActionFor(cfg, nextState);

  writeJSONAtomic(statePath, state);
  appendHistory(cfg, root, id, {
    from: current,
    to: nextState,
    by: actor,
    note: opts.note || ""
  });
  printJSON(state);
}

function startIntegration(cfg, root, opts) {
  const id = opts._[0];
  if (!id) die("start-integration requires <feature_id>");
  const statePath = flowPath(cfg, root, id);
  const state = readJSON(statePath);
  if (state.state !== "FE_DONE_AWAITING_BE") {
    die(`Cannot start integration from ${state.state}; expected FE_DONE_AWAITING_BE`);
  }
  const actor = opts.by || "team-lead";
  state.phase = "integration";
  state.state = "INTEGRATION_TRIGGERED";
  state.current_stage = "INTEGRATION_TRIGGERED";
  state.owner = "fe-dev";
  state.next_action = nextActionFor(cfg, "INTEGRATION_TRIGGERED");
  writeJSONAtomic(statePath, state);
  appendHistory(cfg, root, id, {
    from: "FE_DONE_AWAITING_BE",
    to: "INTEGRATION_TRIGGERED",
    by: actor,
    note: opts.note || "start integration"
  });
  printJSON(state);
}

function applyOptions(state, opts) {
  state.artifacts ||= {};
  state.evidence ||= {};
  state.gates ||= {};
  if (opts.taskId) state.tasklist_id = opts.taskId;
  if (opts.branch) state.artifacts.branch = opts.branch;
  if (opts.implBranch) state.artifacts.impl_branch = opts.implBranch;
  if (opts.commit) state.artifacts.commit = opts.commit;
  if (opts.implCommit) state.artifacts.impl_commit = opts.implCommit;
  if (opts.specPath) state.artifacts.spec_path = opts.specPath;
  if (opts.devplanPath) state.artifacts.devplan_path = opts.devplanPath;
  if (opts.testplanPath) {
    state.artifacts.testplan_path = opts.testplanPath;
    state.artifacts.test_plan_path = opts.testplanPath;
  }
  if (opts.testPlanPath) state.artifacts.test_plan_path = opts.testPlanPath;
  if (opts.testCodePath) state.artifacts.test_code_path = opts.testCodePath;
  if (opts.integrationTestCodePath) state.artifacts.integration_test_code_path = opts.integrationTestCodePath;
  if (opts.unitLog) state.evidence.unit_test_log = opts.unitLog;
  if (opts.integrationLog) state.evidence.integration_test_log = opts.integrationLog;
  if (opts.playwrightLog) state.evidence.playwright_mock_log = opts.playwrightLog;
  if (opts.testVerdict) state.evidence.test_verdict = opts.testVerdict;
  if (opts.reviewPath) state.evidence.review_artifact = opts.reviewPath;
  if (opts.endpointRequest) {
    state.endpoint_requests = Array.from(new Set([...(state.endpoint_requests || []), ...opts.endpointRequest]));
  }
}

function applyAutoGates(state, kind, nextState, actor) {
  const now = new Date().toISOString();
  if (kind === "endpoint-flow") {
    if (nextState === "SPEC_APPROVED") state.gates.spec_approved_by = actor;
    if (nextState === "REVIEW_PENDING") state.gates.test_passed_at ||= now;
    if (nextState === "MERGE_GATE") state.gates.review_approved_by = actor;
    if (nextState === "PR_CREATED" || nextState === "MERGED") state.gates.merge_approved_by ||= actor;
  } else {
    if (nextState === "PLAN_APPROVED") state.gates.plan_approved_by = actor;
    if (nextState === "MERGE_GATE") state.gates.review_approved_by = actor;
    if (nextState === "PR_CREATED" || nextState === "MERGED") state.gates.merge_approved_by ||= actor;
  }
}

function updateCounters(state, current, nextState, kind) {
  state.iteration ||= {};
  if (kind === "endpoint-flow") {
    if (current === "TESTING" && nextState === "TEST_FAILED") {
      state.iteration.test_loop = (state.iteration.test_loop || 0) + 1;
    }
    if (current === "REVIEW_PENDING" && nextState === "CHANGES_REQUESTED") {
      state.iteration.review_loop = (state.iteration.review_loop || 0) + 1;
    }
    return;
  }
  if (current === "PLAN_REVIEW" && nextState === "PLAN_DRAFTING") {
    state.iteration.plan_review_loop = (state.iteration.plan_review_loop || 0) + 1;
  }
  if (current === "PLAYWRIGHT_RUN" && nextState === "IMPL_IN_PROGRESS") {
    state.iteration.playwright_loop = (state.iteration.playwright_loop || 0) + 1;
  }
  if (current === "REVIEW_PENDING" && (nextState === "IMPL_IN_PROGRESS" || nextState === "CHANGES_REQUESTED")) {
    state.iteration.review_loop = (state.iteration.review_loop || 0) + 1;
  }
  if (current === "L3_RUN" && nextState === "INTEGRATION_FAILED") {
    state.iteration.integration_loop = (state.iteration.integration_loop || 0) + 1;
  }
}

function requireEndpointSpecArtifacts(state) {
  requireField(state.artifacts, "spec_path", "SPEC_REVIEW requires artifacts.spec_path");
  requireField(state.artifacts, "test_plan_path", "SPEC_REVIEW requires artifacts.test_plan_path");
}

function requireEndpointTestPass(state) {
  const verdict = String(state.evidence?.test_verdict || "");
  if (!["PASS", "ALL_PASS"].includes(verdict)) {
    die("REVIEW_PENDING requires evidence.test_verdict PASS or ALL_PASS");
  }
}

function requireEndpointReviewApproval(state) {
  if (!state.gates?.review_approved_by && state.state !== "REVIEW_PENDING") {
    die("Merge states require gates.review_approved_by");
  }
}

function requireFeaturePlanArtifacts(state) {
  requireField(state.artifacts, "spec_path", "PLAN_REVIEW requires artifacts.spec_path");
  requireField(state.artifacts, "devplan_path", "PLAN_REVIEW requires artifacts.devplan_path");
  requireField(state.artifacts, "testplan_path", "PLAN_REVIEW requires artifacts.testplan_path");
}

function requireFeaturePlanApprovalActor(_state, actor) {
  if (actor !== "fe-reviewer" && actor !== "team-lead") {
    die("PLAN_APPROVED requires fe-reviewer or explicit team-lead approval");
  }
}

function requireFeatureImplCommit(state) {
  if (!state.artifacts?.commit && !state.artifacts?.impl_commit) {
    die("IMPL_PUSHED requires --commit or artifacts.commit");
  }
}

function requireFeatureTestEvidence(state, _actor, opts) {
  if (opts.allowMissingEvidence) return;
  const verdict = String(state.evidence?.test_verdict || "");
  if (!["PASS", "ALL_PASS"].includes(verdict)) {
    die("REVIEW_PENDING requires --test-verdict PASS|ALL_PASS");
  }
}

function requireFeatureReviewApproval(state) {
  if (!state.gates?.review_approved_by && state.state !== "REVIEW_PENDING") {
    die("Merge states require gates.review_approved_by");
  }
}

function requireFeatureEndpointRequests(state) {
  if (!Array.isArray(state.endpoint_requests) || state.endpoint_requests.length === 0) {
    die("BE handoff/final mock state requires endpoint_requests");
  }
}

function requireField(obj, key, message) {
  if (!obj || !obj[key]) die(message);
}

function nextActionFor(cfg, state) {
  const agent = cfg.stateOwners[state] || null;
  return {
    agent,
    command: commandForState(cfg.dir, state)
  };
}

function commandForState(kind, state) {
  const common = {
    ESCALATED: "await team-lead decision"
  };
  const endpoint = {
    FE_REQUESTED: "draft endpoint spec",
    SPEC_DRAFTING: "draft endpoint spec",
    SPEC_REVIEW: "review endpoint spec/testplan/tests",
    SPEC_APPROVED: "implement approved endpoint spec",
    IMPL_IN_PROGRESS: "implement endpoint",
    IMPL_PUSHED: "run tests against implementation",
    TESTING: "run unit/integration tests",
    TEST_FAILED: "fix implementation against failing tests",
    REVIEW_PENDING: "review implementation",
    CHANGES_REQUESTED: "fix review findings",
    MERGE_GATE: "perform merge gate",
    PR_CREATED: "merge approved PR",
    MERGED: "workflow complete"
  };
  const feature = {
    TRIGGERED: "draft feature plan",
    PLAN_DRAFTING: "draft spec/devplan/testplan",
    PLAN_REVIEW: "review feature plan",
    PLAN_APPROVED: "implement mock feature",
    IMPL_IN_PROGRESS: "implement mock feature",
    IMPL_PUSHED: "run L1/L2 tests",
    PLAYWRIGHT_RUN: "run L1/L2 tests",
    REVIEW_PENDING: "review implementation",
    CHANGES_REQUESTED: "fix review findings",
    MERGE_GATE: "perform merge gate",
    PR_CREATED: "merge approved PR",
    MERGED: "generate endpoint requests or run smoke",
    BE_REQUEST_GENERATED: "finalize FE mock handoff",
    FE_DONE_AWAITING_BE: "mock lifecycle complete",
    INTEGRATION_TRIGGERED: "start mock-to-real integration",
    INTEGRATION_IN_PROGRESS: "implement integration",
    INTEGRATION_PUSHED: "run L3",
    L3_RUN: "run integration Playwright tests",
    INTEGRATION_FAILED: "fix L3 failures",
    L4_SMOKE: "run prod smoke",
    DONE: "workflow complete",
    PLAN_FAILED: "await team-lead decision"
  };
  return (kind === "endpoint-flow" ? endpoint : feature)[state] || common[state] || "continue workflow";
}

function statusFlow(cfg, root, opts) {
  const id = opts._[0];
  if (!id) die("status requires an id");
  const state = readJSON(flowPath(cfg, root, id));
  printJSON(state);
}

function listFlows(cfg, root) {
  const dir = path.join(stateRoot(root), cfg.dir);
  if (!fs.existsSync(dir)) return;
  for (const file of fs.readdirSync(dir).sort()) {
    if (!isFlowStateFile(file)) continue;
    const full = path.join(dir, file);
    const state = readJSON(full);
    console.log([state[cfg.idField] || file.replace(/\.json$/, ""), state.state, state.owner, state.tasklist_id || ""].join("\t"));
  }
}

function validateOne(cfg, root, opts) {
  const id = opts._[0];
  if (!id) die("validate requires an id");
  const errors = validateState(cfg, root, readJSON(flowPath(cfg, root, id)), opts);
  if (errors.length > 0) die(errors.join("\n"));
  console.log(`ok ${cfg.dir}/${id}`);
}

function validateAll(cfg, root, opts) {
  const errors = [];
  const dir = path.join(stateRoot(root), cfg.dir);
  if (!fs.existsSync(dir)) {
    console.log(`ok ${cfg.dir} states`);
    return;
  }
  for (const file of fs.readdirSync(dir).sort()) {
    if (!isFlowStateFile(file)) continue;
    const full = path.join(dir, file);
    try {
      errors.push(...validateState(cfg, root, readJSON(full), opts).map((e) => `${cfg.dir}/${file}: ${e}`));
    } catch (err) {
      errors.push(`${cfg.dir}/${file}: ${err.message}`);
    }
  }
  if (errors.length > 0) die(errors.join("\n"));
  console.log(`ok ${cfg.dir} states`);
}

function validateState(cfg, root, state, opts = {}) {
  const errors = [];
  const id = state[cfg.idField];
  if (!id) errors.push(`missing ${cfg.idField}`);
  if (!state.state) errors.push("missing state");
  if (!state.current_stage) errors.push("missing current_stage");
  if (state.current_stage && state.state && state.current_stage !== state.state) {
    errors.push(`current_stage ${state.current_stage} does not match state ${state.state}`);
  }
  if (!state.owner) errors.push("missing owner");
  if (state.state && !Object.hasOwn(cfg.stateOwners, state.state)) {
    errors.push(`unknown state ${state.state}`);
  }
  const expectedOwner = cfg.stateOwners[state.state];
  if (expectedOwner && state.owner !== expectedOwner) {
    errors.push(`owner ${state.owner} does not match expected owner ${expectedOwner} for ${state.state}`);
  }
  if (opts.strictTasklist) {
    errors.push(...validateTaskListLink(cfg, root, state));
  }
  return errors;
}

function validateTaskListLink(cfg, root, state) {
  const errors = [];
  if (!state.tasklist_id) {
    errors.push("strict tasklist mode requires tasklist_id");
    return errors;
  }
  const task = readTask(root, state.tasklist_id);
  if (!task) {
    errors.push(`tasklist_id ${state.tasklist_id} not found`);
    return errors;
  }
  if (!cfg.terminalStates.has(state.state) && task.owner && task.owner !== state.owner) {
    errors.push(`TaskList owner ${task.owner} != workflow owner ${state.owner}`);
  }
  if (task.status === "completed" && !cfg.finalStates.has(state.state)) {
    errors.push(`TaskList completed but workflow state is non-final ${state.state}`);
  }
  if (task.status !== "completed" && cfg.finalStates.has(state.state)) {
    errors.push(`workflow final ${state.state} but TaskList status is ${task.status}`);
  }
  return errors;
}

function guardTaskCompleted(root, opts) {
  const taskId = opts.taskId || opts._[0];
  if (!taskId) die("guard-task-completed requires --task-id <id>");
  const actor = opts.by || opts.teammate || opts.agent || "";
  const matches = findStatesByTaskId(root, taskId);
  if (matches.length === 0) {
    const task = readTask(root, taskId);
    if (task && looksLikeHarnessWorkflowTask(task)) {
      die(`task_completed rejected; task ${taskId} looks like a harness workflow task but no workflow state is linked. Initialize endpoint-flow/feature-flow with --task-id ${taskId} or migrate the legacy state first.`);
    }
    console.log(`approve: no workflow state linked to task ${taskId}`);
    return;
  }
  const errors = [];
  for (const { cfg, state, file } of matches) {
    if (!cfg.finalStates.has(state.state)) {
      errors.push(`${file}: task_completed rejected; ${state.state} is not final. Use stage transition first.`);
    }
    if (actor && actor !== state.owner && !["team-lead"].includes(actor)) {
      errors.push(`${file}: task_completed actor ${actor} != workflow owner ${state.owner}`);
    }
  }
  if (errors.length > 0) die(errors.join("\n"));
  console.log(`approve: task ${taskId} is in final workflow state`);
}

function findStatesByTaskId(root, taskId) {
  const matches = [];
  for (const cfg of Object.values(KIND_CONFIG)) {
    const dir = path.join(stateRoot(root), cfg.dir);
    if (!fs.existsSync(dir)) continue;
    for (const file of fs.readdirSync(dir).sort()) {
      if (!isFlowStateFile(file)) continue;
      const full = path.join(dir, file);
      const state = readJSON(full);
      if (String(state.tasklist_id || "") === String(taskId)) {
        matches.push({ cfg, state, file: full });
      }
    }
  }
  return matches;
}

function readTask(root, taskId) {
  for (const file of taskFiles(root, taskId)) {
    if (fs.existsSync(file)) return readJSON(file);
  }
  return null;
}

function taskProjectName(root) {
  return path.basename(root).replace(/\.(fe|be)-.*$/, "");
}

function looksLikeHarnessWorkflowTask(task) {
  const owner = String(task.owner || task.teammate || "");
  if (["be-test", "be-dev", "be-reviewer", "fe-planner", "fe-dev", "fe-reviewer"].includes(owner)) {
    return true;
  }
  const text = [task.subject, task.title, task.description].filter(Boolean).join(" ");
  return /\b(endpoint-flow|feature-flow|be-ep-|fe-feat-|fe-planner|fe-dev|fe-reviewer|be-test|be-dev|be-reviewer)\b|Mock 라이프사이클|풀 사이클|mockup 구현|워커 구현/.test(text);
}

function flowPath(cfg, root, id) {
  return path.join(stateRoot(root), cfg.dir, `${id}.json`);
}

function isFlowStateFile(file) {
  return file.endsWith(".json") && !file.endsWith(".review.json");
}

function appendHistory(cfg, root, id, entry) {
  const file = path.join(stateRoot(root), cfg.dir, `${id}.history.jsonl`);
  ensureDir(path.dirname(file));
  const payload = {
    ts: new Date().toISOString(),
    from: entry.from,
    to: entry.to,
    by: entry.by,
    note: entry.note || ""
  };
  fs.appendFileSync(file, `${JSON.stringify(payload)}\n`);
}

function readJSON(file) {
  if (!fs.existsSync(file)) die(`Missing file: ${file}`);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJSONAtomic(file, data) {
  ensureDir(path.dirname(file));
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(data, null, 2)}\n`);
  fs.renameSync(tmp, file);
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function printJSON(value) {
  console.log(JSON.stringify(value, null, 2));
}

function findProjectRoot(start) {
  let current = path.resolve(start);
  while (true) {
    if (fs.existsSync(path.join(current, "Plans.md")) || fs.existsSync(path.join(current, ".git"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) return path.resolve(start);
    current = parent;
  }
}

function stateRoot(root) {
  return process.env.HARNESS_STATE_ROOT || process.env.HARNESS_STATE_DIR || path.join(root, ".codex", "state");
}

function taskFiles(root, taskId) {
  if (process.env.HARNESS_TASKS_DIR) {
    return [path.join(process.env.HARNESS_TASKS_DIR, `${taskId}.json`)];
  }
  const home = process.env.HOME || "";
  const projectName = taskProjectName(root);
  return [
    path.join(home, ".codex", "tasks", projectName, `${taskId}.json`),
    path.join(home, ".claude", "tasks", projectName, `${taskId}.json`)
  ];
}

function die(message) {
  console.error(message);
  process.exit(1);
}

main();
