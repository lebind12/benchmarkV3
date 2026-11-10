/**
 * MP-02 실행 기록·검사 화면의 자료형.
 *
 * 서버의 `app/preview/contracts.py`와 같은 이름·의미를 유지한다. 필드를 바꾸려면
 * 의존 작업과 변경 이유를 먼저 조정자에게 보고한다.
 *
 * 세 축을 섞지 않는다.
 * - environment: dev | test | prod
 * - mode: live | replay | mock (실행 방식)
 * - source_kind: api | search (자료 출처)
 */

export type RunMode = 'live' | 'replay' | 'mock'
export type Environment = 'dev' | 'test' | 'prod'
export type SourceKind = 'api' | 'search'

export type RunStatus =
  | 'queued'
  | 'running'
  | 'retry_wait'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export type QualityStatus = 'pending' | 'ready' | 'insufficient'

export type ModuleStatus = 'queued' | 'running' | 'retry_wait' | 'succeeded' | 'failed'

export type OperationKind = 'preview' | 'module' | 'fixture_catalog' | 'mock_demo' | 'section'

export type InspectorTabId = 'request' | 'response' | 'transform' | 'next_input'

export type AttemptOutcome = 'ok' | 'error' | 'unknown'

export type ArtifactStatus = 'available' | 'expired'

export type ContractVersions = {
  contract: string
  provider: string
  module_input: string
  preview_document: string
  inspector: string
  /** MP-04가 더한 축. 섹션 결과 형식과 재시도 정책 버전. */
  section_result?: string
  retry_policy?: string
}

export type ModeDetail = {
  mode: string
  label: string
  note: string
}

export type FixtureIdentityPayload = {
  fixture_id: number
  league_id: number
  season: number
  home_team_id: number
  away_team_id: number
  kickoff_at: string
}

export type RunSummary = {
  run_id: string
  operation_kind: OperationKind
  environment: Environment
  mode: RunMode
  status: RunStatus
  quality: QualityStatus
  fixture_label: string | null
  requested_at: string
  finished_at: string | null
  module_count: number
  attempt_count: number
  retry_count: number
  failure_code: string | null
  label: string | null
  cancelled_at: string | null
}

export type RunListResponse = {
  runs: RunSummary[]
  next_cursor: string | null
}

export type RequestSpec = {
  logical_call_id: string
  provider: string
  model: string | null
  operation: string
  module_id: string | null
  endpoint: string | null
  parameters: Record<string, unknown>
  prompt_version: string | null
  contract_version: string
  timeout_seconds: number | null
  secret_refs: string[]
}

export type ArtifactRef = {
  artifact_id: string
  kind: 'raw_request' | 'raw_response' | 'normalized_transform'
  media_type: string
  byte_size: number
  sha256: string
  redacted: boolean
  created_at: string
  expires_at: string
  expired_at: string | null
  available: boolean
  status: ArtifactStatus
  summary: Record<string, unknown>
  body: string | null
  detail: string | null
}

export type AttemptView = {
  attempt_id: string
  logical_call_id: string
  attempt_ordinal: number
  provider: string
  model: string | null
  mode: RunMode
  outcome: AttemptOutcome
  http_status: number | null
  error_class: string | null
  error_message: string | null
  usage: Record<string, number | null> | null
  wait_ms: number | null
  started_at: string | null
  finished_at: string | null
  request_spec: RequestSpec
  request_body: ArtifactRef | null
  response_body: ArtifactRef | null
}

export type ClaimView = {
  claim_id: string
  kind: string
  text: string
  decision: string
  decision_reason: string | null
  snapshot_ids: string[]
}

export type CoverageView = {
  topic: string
  state: string
  detail: string | null
}

export type ApprovalState = 'none' | 'superseded' | 'approved'

export type ConstituentVersion = {
  module_id: string
  prompt_version: string
  implementation_version: string
  contract_version: string
}

export type ReviewedSectionEvidence = {
  run_id: string
  section_result_id: string
  reviewed_at: string | null
}

export type SectionApprovalRecord = {
  approval_id: string
  workflow_id: string
  workflow_version: string
  constituents: ConstituentVersion[]
  evidence: ReviewedSectionEvidence
  approved_by_actor_id: string
  approved_at: string
  reviewed_note: string | null
  supersedes_approval_id: string | null
}

export type SectionApprovalStatus = {
  workflow_id: string
  state: ApprovalState
  active_approval: SectionApprovalRecord | null
  pinned_approval: SectionApprovalRecord | null
  current_version: string | null
  current_constituents: ConstituentVersion[]
  candidate_note: string | null
}

export type SectionWorkflowRegistration = {
  workflow_id: string
  display_name: string
  description: string
  module_ids: string[]
  output_contract_version: string
  implemented: boolean
  unrunnable_reason: string | null
}

export type ApprovalsSummary = {
  contract_version: string
  workflows: Record<string, SectionApprovalStatus>
  approved: string[]
  unapproved: string[]
  scope_note: string
  sections?: {
    workflows: SectionWorkflowRegistration[]
    implemented: string[]
    unavailable: string[]
    approval_scope_note: string
  }
  mock_demo_module_id?: string
  mock_demo_note?: string
}

export type SectionApprovalRow = {
  workflow_id: string
  /** 사람이 읽는 섹션 이름. 표의 첫 열은 이것을 쓴다. */
  display_name: string
  description: string
  /** 이 섹션을 구성하는 모듈들(D0 포함). 섹션과 모듈은 1:1이 아니다. */
  module_ids: string[]
  implemented: boolean
  unrunnable_reason: string | null
  state: ApprovalState
  label: string
  detail: string | null
  current_version: string | null
  active_approval: SectionApprovalRecord | null
  pinned_approval: SectionApprovalRecord | null
  can_approve: boolean
}

export type ModulePanelInfo = {
  panel: string
  registered: boolean
  display_name: string
  description?: string
  mode_scope: string[]
  available: boolean
  unrunnable_reason: string | null
  expected_model_calls?: number
  prompt_version?: string | null
  contract_version?: string
}

export type ModuleInspection = {
  inspector_version: string
  module_execution_id: string
  module_id: string
  panel: ModulePanelInfo
  run_mode: ModeDetail
  status: ModuleStatus
  quality: QualityStatus
  attempt_count: number
  retry_count: number
  result_versions: number[]
  started_at: string | null
  finished_at: string | null
  tabs_meta: { id: InspectorTabId; label: string; description: string }[]
  tabs: {
    request: {
      available: boolean
      input: Record<string, unknown> | null
      attempts: AttemptView[]
      note: string | null
    }
    response: {
      available: boolean
      attempts: {
        attempt_id: string
        logical_call_id: string
        attempt_ordinal: number
        outcome: AttemptOutcome
        http_status: number | null
        error_class: string | null
        error_message: string | null
        usage: Record<string, number | null> | null
        content: ArtifactRef | null
      }[]
      note: string | null
    }
    transform: {
      available: boolean
      result_id: string | null
      version: number | null
      status: string | null
      quality: string | null
      failure_code: string | null
      claims: ClaimView[]
      coverage: CoverageView[]
      diagnostics: string[]
      contract_version: string | null
      prompt_version: string | null
      implementation_version: string | null
      input_hash: string | null
      artifacts: ArtifactRef[]
      note: string | null
    }
    next_input: {
      available: boolean
      target_module_id: string | null
      selected_result_ids: string[]
      uses_latest_version: boolean
      latest_result_id: string | null
      latest_result_version: number | null
      values: { key: string; value: unknown }[]
      note: string | null
    }
  }
}

export type ResultVersionView = {
  result_id: string
  module_id: string
  module_execution_id: string
  version: number
  input_hash: string
  status: string
  quality: string
  failure_code: string | null
  contract_version: string
  prompt_version: string
  implementation_version: string
  created_at: string | null
  supersedes_result_id: string | null
  payload: Record<string, unknown>
}

export type VersionComparison = {
  module_execution_id: string
  module_id: string
  base: ResultVersionView | null
  target: ResultVersionView
  diff: {
    status: { from: string | null; to: string }
    quality: { from: string | null; to: string }
    input_hash: { from: string | null; to: string; changed: boolean }
    contract_version: { from: string | null; to: string }
    prompt_version: { from: string | null; to: string }
    claims_added: string[]
    claims_removed: string[]
    claims_changed: string[]
    coverage_changes: Record<string, { from: string | null; to: string | null }>
    payload_keys_changed: string[]
  }
  versions_available: number[]
}

export type UndoState = {
  state: 'cancellable' | 'blocked' | 'cancelled'
  cancelled_at: string | null
  cancelled_by_actor_id: string | null
  reason: string | null
  can_cancel: boolean
  blocked_reason: string | null
}

/**
 * 섹션 워크플로우 결과 (MP-04).
 *
 * 승인 근거는 개별 노드 결과가 아니라 이 본문 결과다. `mode`가 `mock`이면 모의
 * 시연이며 승인 근거가 아니다. `approvable`은 그 판단을 서버가 내린 값이다.
 */
export type SectionResultView = {
  section_result_id: string
  run_id: string
  workflow_id: string
  workflow_version: string
  version: number
  title: string
  /** 독자용 본문. 노드 상태·JSON이 아니라 사람이 읽는 문장이다. */
  body: string
  sources: SectionResultSource[]
  mode: RunMode
  mode_label: string
  environment: Environment
  quality: QualityStatus
  module_execution_ids: string[]
  result_ids: string[]
  /** 관리자 전용 진단. 독자용 본문에는 포함되지 않는다. */
  diagnostics: string[]
  unavailable_reason: string | null
  unavailable: boolean
  output_contract_version: string
  contract_version: string
  created_at: string | null
  supersedes_section_result_id: string | null
  /** 이 결과를 승인 근거로 쓸 수 있는지(모의·본문 없음은 false). */
  approvable: boolean
}

export type SectionResultSource = {
  label?: string
  url?: string | null
  kind?: string
  note?: string | null
}

export type SectionAvailability = {
  workflow_id: string
  display_name: string
  module_ids: string[]
  output_contract_version: string
  /** 모든 단계 구현이 등록됐는지. 모의 시연만 있어도 true가 될 수 있다. */
  implemented: boolean
  missing_implementations: string[]
  modes: string[]
  /** 등록된 구현이 모의 시연뿐인지. 실제 생성과 구분하기 위한 값이다. */
  demo_only: boolean
  /** 실제 조사·생성 구현이 하나라도 등록됐는지. */
  real_generation_available: boolean
  note: string | null
  /** 모델 전송 설정 상태(설정됨/없음). 모델 이름 대체 판단은 하지 않는다. */
  model?: { provider?: string; mode?: string; configured?: boolean; problem?: string | null }
}

export type SectionAvailabilityResponse = {
  workflows: SectionWorkflowRegistration[]
  availability: Record<string, SectionAvailability>
  mock_demo_note: string
}

export type SectionRunResponse = {
  run_id: string
  workflow_id: string
  workflow_version: string
  mode: RunMode
  status: RunStatus
  quality: QualityStatus
  section_result_id: string | null
  section_result_version: number | null
  external_calls: number
  budget: Record<string, number | string | string[] | null>
  unavailable_reason: string | null
  note: string
}

export type ReplayResultResponse = {
  run_id: string
  source_result_id: string
  new_result_id: string
  new_version: number
  raw_artifact_id: string | null
  external_calls: number
  note: string
}

export type RunDetail = {
  summary: RunSummary
  actor_id: string
  config_version: string
  limits: Record<string, number | null>
  fixture: FixtureIdentityPayload | null
  modules: Record<string, unknown>[]
  results: ResultVersionView[]
  sources: {
    snapshot_id: string
    source_kind: SourceKind
    provider: string
    collected_at: string
    provider_updated_at: string | null
    validation_status: string
    fixture: FixtureIdentityPayload | null
    catalog_query: Record<string, unknown> | null
    artifact_id: string | null
    note: string | null
  }[]
  attempts: AttemptView[]
  artifacts: ArtifactRef[]
  contract_versions: ContractVersions
  inspector_version: string
  mode_detail: ModeDetail
  inspector_modules: ModuleInspection[]
  registry: ModuleRegistry
  approvals: ApprovalsSummary | null
  /**
   * 이 실행의 섹션 결과 중 승인 근거로 쓸 수 있는 결과 ID.
   *
   * 모의 시연 결과만 있으면 null이다. 화면은 이 값이 없을 때 승인 요청을 만들지
   * 않는다(서버도 거부한다).
   */
  section_result_id: string | null
  /** 이 실행이 저장한 섹션 본문 결과들. 본문·근거를 먼저 보여준다. */
  section_results: SectionResultView[]
  section_approvals: SectionApprovalRow[]
  section_workflows: {
    workflows: SectionWorkflowRegistration[]
    implemented: string[]
    unavailable: string[]
    approval_scope_note: string
  } | null
  approval_note: string
  mock_demo_module_id: string
  availability_note: string
  undo: UndoState
}

export type ModuleRegistration = {
  module_id: string
  display_name: string
  description: string
  operation: string
  depends_on: string[]
  contract_version: string
  prompt_version: string | null
  inspector_panel: string
  implemented: boolean
  mode_scope: string[]
  expected_model_calls: number
  unrunnable_reason: string | null
}

export type ModuleRegistry = {
  registry_version: string
  contract_version: string
  inspector_version: string
  modules: ModuleRegistration[]
  implemented: string[]
  unavailable: string[]
}

export type RetentionPolicy = {
  raw_artifact_days: number
  structured_record_days: number
  raw_expiry_effect: string
  structured_expiry_effect: string
  automatic_purge: boolean
  note: string
}

export type RetentionStatus = {
  artifacts: number
  expired: number
  due_for_expiry: number
  next_expiry_at: string | null
  checked_at: string
  policy: RetentionPolicy
}

export type CreateMockRunResponse = {
  run_id: string
  module_execution_id: string
  result_ids: string[]
  mode: RunMode
  label: string
  external_calls: number
  note: string
}

export type UndoReport = {
  run_id: string
  write_scope: string
  would_remove: Record<string, number>
  undo: UndoState
}

export type CancelRunResponse = {
  run_id: string
  cancelled_at: string
  removed: Record<string, number>
  kept: string[]
  reason: string
}

export type AuditResponse = {
  run_id: string
  write_scope: string
  events: {
    action: string
    target_table: string
    target_id: string | null
    detail: Record<string, unknown>
    actor_id: string
    created_at: string | null
  }[]
}

export type ApproveSectionResponse = SectionApprovalRecord
