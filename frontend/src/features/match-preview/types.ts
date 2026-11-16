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
  player_section_processing?: PlayerSectionProcessingViewData | null
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
 * 서버가 섹션 결과 행에 덧붙이는 **구조 값**의 계약 (PS-04).
 *
 * `GET /runs/{id}/section-results?include_structured=true`의 각 행에는 저장 payload에서
 * 옮긴 `structured`가 있고(`app/preview/section_structured.py`의
 * `structured_row_from_section_result`), 화면 파서(`sectionStructured.ts`의
 * `structuredFromSectionResult`)가 이 이름들로 읽는다. 없는 값은 빈 배열/`null`이며
 * 화면은 값을 만들지 않는다.
 *
 * 키 이름은 **서버가 내는 이름**과 **화면 파서가 읽는 이름**의 합집합이다. 서버는
 * 저장 payload를 정규화해 내보내므로(예: 선수는 항상 `player`) 파서는 예전 저장본 표기
 * (`selected_player` 등)도 함께 읽는다. 그래서 한 필드에 두 표기가 함께 적혀 있고,
 * 둘 다 서버 출력이거나 파서 입력이다(그 밖의 이름은 받지 않는다).
 */
export type SectionStructuredPlayerRow = {
  player?: string | null
  reason?: string | null
  team?: string | null
  /** 내부 선수 ID. 사진 주소를 만드는 데 쓰지 않는다(외부 ID와 다른 값). */
  player_id?: number | null
  external_player_id?: number | null
  team_external_id?: number | null
  photo_url?: string | null
  /** 파서가 함께 읽는 저장 payload 표기(R4). 서버 응답은 `player`/`reason`으로 정규화된다. */
  selected_player?: string | null
  selection_reason?: string | null
}

export type SectionStructuredInjuryRow = {
  player?: string | null
  team?: string | null
  /** 원문 상태 표기 그대로. 확정 부상으로 승격하지 않는다. */
  status?: string | null
  summary?: string | null
  player_id?: number | null
  team_id?: number | null
  external_player_id?: number | null
  team_external_id?: number | null
  photo_url?: string | null
  /** 저장 payload(`bundle_sections`)의 표기. */
  player_name?: string | null
  expected_status?: string | null
}

export type SectionStructuredMediaRow = {
  publisher?: string | null
  statement?: string | null
  /** 점수 미제시 기사는 `null`이다(0-0을 만들지 않는다). */
  predictedScore?: string | null
  publishedAt?: string | null
  url?: string | null
  predicted_score?: string | null
  published_at?: string | null
}

/** 정규시간 1X2 배당 한 줄. 값이 없는 칸은 `null`이다. */
export type SectionStructuredOddsRow = {
  bookmaker?: string | null
  observedAt?: string | null
  observed_at?: string | null
  home?: string | null
  draw?: string | null
  away?: string | null
  market?: string | null
}

export type SectionStructuredForecastRow = {
  lean?: 'home' | 'draw' | 'away' | null
  score?: string | null
  reasoning?: string[]
  note?: string | null
}

export type PlayerSectionSlotKey = 'home1' | 'home2' | 'away1' | 'away2'
export type PlayerNameSource = 'db_ko' | 'ai_candidate'
export type PlayerRegenerationReason =
  | 'missing_body'
  | 'duplicate_player'
  | 'missing_and_duplicate'
export type PlayerUnplacedReason =
  | 'missing_body'
  | 'duplicate_player'
  | 'team_unresolved'
  | 'slot_capacity_exceeded'
  | 'missing_name'
  | 'missing_name_ko'

export type PlayerSectionSlotDraftView = {
  slot_key: PlayerSectionSlotKey
  team_side: 'home' | 'away'
  team_id: number | null
  team_name: string | null
  player_id: number | null
  external_player_id: number | null
  resolution_status: 'resolved' | 'unresolved' | 'empty'
  original_name: string
  name_ko: string
  name_source: PlayerNameSource
  body: string
  unresolved_reason: string | null
  evidence: string[]
  status?: string | null
  injury?: string | null
  importance?: string | null
}

export type PlayerSectionUnplacedView = {
  original_name: string
  reason: PlayerUnplacedReason | string
  team_hint: string | null
  team_id: number | null
  player_id: number | null
  external_player_id?: number | null
  detail: string | null
}

export type PlayerSectionAttemptTraceView = {
  attempt_ordinal: number
  logical_call_id: string
  parsed_valid: boolean
  raw_text: string | null
  parsed_json: Record<string, unknown> | null
  regeneration_triggered: boolean
  regeneration_reason: PlayerRegenerationReason | string | null
  error_reason: string | null
}

export type PlayerSectionProcessingViewData = {
  workflow_id: 'section_players' | 'section_availability' | string
  fixture_id: number
  home_team_id: number | null
  away_team_id: number | null
  output_contract_version: string
  persisted: boolean
  storage_status: string
  mode: string
  ok: boolean
  failed_reason: string | null
  home1: PlayerSectionSlotDraftView | null
  home2: PlayerSectionSlotDraftView | null
  away1: PlayerSectionSlotDraftView | null
  away2: PlayerSectionSlotDraftView | null
  home_etc: null
  away_etc: null
  regeneration_count: number
  regeneration_reason: PlayerRegenerationReason | string | null
  module_attempt_count: number
  adopted_attempt_ordinal: number | null
  attempts: PlayerSectionAttemptTraceView[]
  unplaced_items: PlayerSectionUnplacedView[]
  translation_defects: string[]
  diagnostics: string[]
  korean_labels: Array<Record<string, unknown>>
  dropped_evidence_count: number
}

/** 섹션 결과 행의 `structured` 전체. 값이 없는 항목은 빈 배열/`null`이다. */
export type SectionStructuredProjection = {
  structured_version?: string
  workflow_id?: string | null
  players?: SectionStructuredPlayerRow[]
  injuries?: SectionStructuredInjuryRow[]
  media?: SectionStructuredMediaRow[]
  odds?: SectionStructuredOddsRow[]
  forecast?: SectionStructuredForecastRow | null
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
  /**
   * 서버가 이 행에 덧붙인 구조 값. `include_structured=true`(기본)일 때만 있고,
   * 저장 payload가 없으면 비어 있다. 값은 저장된 것만 옮기며 화면이 만들지 않는다.
   */
  structured?: SectionStructuredProjection
  /**
   * 구조 값에 표시할 내용이 하나라도 있는지(서버 계산). `structured`와 같은 응답에만 있다.
   * `unavailable`(본문을 만들지 못했는지)과 다른 값이므로 섞어 쓰지 않는다.
   */
  available?: boolean
  /** NS-02 선수/부상 섹션 고정 슬롯·재생성·제외 사유 진단(저장 예정 값 또는 저장값). */
  player_section_processing?: PlayerSectionProcessingViewData | null
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
  /**
   * 재생성 응답 확장 필드 (manifest §5, 계획).
   *
   * 서버가 아직 이 필드들을 내려주지 않을 수 있으므로 모두 선택으로 둔다. 화면은 값이
   * 있을 때만 표시하고, 없으면 추측해 채우지 않는다.
   */
  source_mode?: SourceMode
  bundle_id?: string | null
  /** 저장된 묶음을 실제로 재사용했는지. */
  bundle_reused?: boolean
  /** 이 실행에서 예상한 모델 호출 수. */
  expected_model_calls?: number
  parent_run_id?: string | null
  base_result_id?: string | null
  /** 이 실행이 만든 결과의 버전. */
  new_version?: number | null
  /** 모델 호출이 없었는지(`true`면 재처리·배당처럼 무전송). */
  no_model_call?: boolean
  /** 이 실행이 실제로 쓴 구성본 ID. 쓰지 않았으면 null. */
  composition_id?: string | null
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
  player_section_processing?: Record<string, PlayerSectionProcessingViewData>
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

/**
 * 저장된 응답 재처리와 실제 재생성을 구분하는 축 (PS-04).
 *
 * - `reprocess`: 저장된 응답만 다시 변환한다. 모델 전송 0회(무료·무호출).
 *   경로는 기존 `POST /runs/{run_id}/results/.../replay`이며 재생성 요청이 아니다.
 * - `refresh`: 새 수집·새 모델 호출을 한다. 예상 전송 수를 먼저 보여줘야 한다.
 *
 * 이 값은 화면 표시 문구를 정하는 값이며, 서버의 실제 전송 여부를 대신하지 않는다.
 * 서버가 응답에 준 실제 전송 수(`external_calls`)와 `no_model_call`을 항상 함께 표시한다.
 */
export type SectionReprocessMode = 'reprocess' | 'refresh'

/** 재생성·재처리가 재사용하는 기준 자료. `reuse`는 저장된 묶음을, `refresh`는 새 수집. */
export type SourceMode = 'reuse' | 'refresh'

/**
 * 섹션 재생성 요청 (PS-04 → A manifest §5 상호 ACK 대상).
 *
 * 필드 이름은 `docs/implementation/match-preview/section-interface-manifest.md` §5가
 * 고정한 값을 그대로 쓴다. 재생성은 기존 `POST /section-runs` 본문에 다음 필드를 더한다.
 *
 * | 필드 | 뜻 |
 * |---|---|
 * | `source_mode` | `reuse`(저장 묶음 재사용, 새 수집 없음) / `refresh`(새 수집 포함) |
 * | `bundle_id` | `reuse`일 때 필수인 저장 묶음 ID |
 * | `base_run_id` | 비교 기준 실행(선택) |
 * | `base_result_id` | 비교 기준 결과 버전(선택) |
 * | `selected_result_ids` | `section_ai_forecast`가 읽는 앞 섹션 결과 |
 *
 * 저장 응답만 재처리하는 동작은 이 요청이 아니라 기존
 * `POST /runs/{run_id}/results/{module_execution_id}/replay` 경로다(무전송).
 */
export type SectionRegenerationRequest = {
  workflow_id: string
  mode?: string
  fixture_id: number
  league_id?: number
  season?: number
  home_team_id?: number
  away_team_id?: number
  kickoff_at?: string
  fixture_label?: string
  source_mode: SourceMode
  /** `source_mode: 'reuse'`일 때 필수. */
  bundle_id?: string
  base_run_id?: string
  base_result_id?: string
  selected_result_ids?: string[]
  /**
   * 관리자가 저장한 구성본 ID. 주면 그 구성본의 선택 결과가 최종 AI 입력이 된다.
   * 저장된 값과 다르면 서버가 422로 거부한다(값을 덮어쓰지 않는다).
   */
  composition_id?: string
}

/** 이 실행이 저장한 섹션 본문 결과 목록 (기존 `/section-results` 경로). */
export type SectionResultsResponse = {
  run_id: string
  section_results: SectionResultView[]
}

/**
 * MP-09 독자용 프리뷰 (GET /runs/{run_id}/preview).
 *
 * 서버는 저장된 S1 종합 결과를 **허용 목록으로 다시 투영**해 내려준다. 그래서 이 타입은
 * 진단·커버리지·스냅샷·결과 ID·시도 정보를 담지 않는다. 같은 실행의 진단은
 * `ReaderPreviewDiagnostics`(별도 경로)로 받는다.
 *
 * 없는 보조 항목은 키 자체가 없다. 코드는 `undefined`를 "그 항목이 없음"으로 읽고
 * 빈 카드나 누락 안내를 그리지 않는다.
 */
export type ReaderPreviewSource = {
  label: string
  kind: 'search' | 'api' | string
  url?: string
  note?: string
  observed_at?: string
}

export type ReaderPreviewPlayer = {
  player: string
  team?: string
  reason: string
}

export type ReaderPreviewOutlook = {
  publisher: string
  statement: string
  /** 제공자 알고리즘 예측은 매체 의견과 다른 종류다. */
  source_kind: 'external_forecast' | 'api_prediction' | string
  published_at?: string
  url?: string
  source_note?: string
}

export type ReaderPreviewPrediction = {
  lean?: 'home' | 'draw' | 'away'
  score?: string
  reasoning?: string[]
  note?: string
}

/**
 * 독자용 배당 한 줄 (선택 섹션).
 *
 * 정규시간 1X2 소수점만 담는다. 서버가 `odds`를 내려주지 않으면 키 자체가 없고, 화면은
 * 배당 카드를 만들지 않는다. 값이 없는 칸은 비워 두며 추정해 채우지 않는다.
 */
export type ReaderPreviewOdds = {
  bookmaker: string
  market?: string
  observed_at?: string
  home?: string
  draw?: string
  away?: string
}

export type ReaderPreviewAttribution = {  ai_forecast_label: string
  ai_forecast_note: string
  model?: string | null
  provider?: string | null
  executed_at?: string | null
}

export type ReaderPreview = {
  fixture: {
    fixture_id: number
    /** 내부 팀 ID. 사진·로고 주소를 만드는 데 쓰지 않는다(외부 ID와 다른 값). */
    home_team_id: number
    away_team_id: number
    league_id: number
    season: number
    kickoff_at: string
    label: string
    league?: string | null
    /**
     * 외부(API-Football) 팀 ID와 로고 주소. 서버가 줄 때만 있으며, 없으면 `null`이다.
     * 예전 저장본에는 이 키가 아예 없으므로 모두 선택으로 둔다.
     */
    home_team_external_id?: number | null
    away_team_external_id?: number | null
    home_team_logo_url?: string | null
    away_team_logo_url?: string | null
  }
  headline: string
  generated_at: string
  data_as_of: string | null
  attribution: ReaderPreviewAttribution
  /** 독자용 본문. 문단은 빈 줄로 나뉜다. */
  body: string
  watch_points?: string[]
  players_to_watch?: ReaderPreviewPlayer[]
  absences_impact?: string
  external_outlook?: ReaderPreviewOutlook[]
  ai_prediction?: ReaderPreviewPrediction
  /** 선택 섹션. 서버가 내려줄 때만 있고, 없으면 화면은 카드를 만들지 않는다. */
  odds?: ReaderPreviewOdds[]
  sources?: ReaderPreviewSource[]
  /**
   * 새 정보 원문 묶음 경로의 구성본 투영. 저장된 섹션 본문을 표시 순서로 담는다.
   * 옛 S1 경로 응답에는 이 키가 없다(그때는 기존 필드만 쓴다).
   */
  sections?: ReaderPreviewSection[]
  /** 필수 섹션 본문이 모두 준비됐는지. false면 부분 결과이며 정상 완료가 아니다. */
  complete?: boolean
  /**
   * 부분 결과 사유. **관리자 진단용**이며 독자 본문에 넣지 않는다.
   * 화면도 이 값을 본문 영역에 표시하지 않는다.
   */
  unavailable_reason?: string | null
}

/**
 * 구성본에서 온 독자 섹션 하나. `body`는 완성 본문이고, 진단·실패 사유는 들어 있지 않다.
 */
export type ReaderPreviewSection = {
  section_id: string
  title: string
  body: string
  sources: ReaderPreviewSource[]
  quality: string | null
  /** 부분 결과(필수 항목 누락 등). true여도 본문이 있으면 그대로 보여준다. */
  partial: boolean
  version?: number | null
  workflow_version?: string | null
}

/**
 * 관리자가 고른 섹션 결과 버전 묶음(구성본) 항목.
 * `run_id`가 항목마다 다를 수 있다(서로 다른 실행에서 고를 수 있다).
 */
export type CompositionItem = {
  section_id: string
  result_id: string
  run_id: string
  fixture_id: number | null
  version: number
  workflow_version: string
  quality: string
  unavailable: boolean
  unavailable_reason: string | null
  body_chars: number
  mode: string
  created_at: string | null
}

/** 구성본 저장/조회 응답. 서버가 고르지 않은 결과를 채우지 않는다. */
export type CompositionView = {
  composition_id: string
  fixture_id: number | null
  items: CompositionItem[]
  /** 넣지 않은 선택과 그 사유(다른 경기·없는 결과·중복 섹션). */
  refused: { result_id: string; section_id?: string; reason: string }[]
  diagnostics: string[]
  section_result_ids: string[]
}

/** 같은 실행의 관리자 진단. 독자용 응답과 분리된 경로다. */
export type ReaderPreviewDiagnostics = {
  run_id: string
  workflow_id: string
  workflow_version: string | null
  section_result_id: string | null
  mode: { mode: RunMode; label: string }
  quality: { run: QualityStatus; section: QualityStatus | null }
  gaps: { module_id: string; reason: string }[]
  excluded_claims: {
    claim_id: string | null
    kind: string | null
    text: string | null
    reason: string | null
  }[]
  diagnostics: string[]
  unavailable_reason: string | null
  selected_inputs: {
    module_id: string
    result_id: string
    version: number
    implementation_version: string
    prompt_version: string
    quality: QualityStatus
    adopted_claim_count: number
    excluded_claim_count: number
  }[]
  /**
   * 새 묶음 경로에서 **저장 구성본에 실제로 들어간** 결과 버전들. 구성본이 없으면 빈 배열이다.
   * 화면은 이 목록으로 "무엇을 골라 마지막 AI에 넣었는지"를 확인한다.
   */
  composition_inputs: CompositionItem[]
  contract_versions: Record<string, string>
  synthesis_versions: {
    implementation: string
    prompt: string
    output_contract: string
  }
  attempts_present: boolean
}

export type BundlePreviewRunResponse = {
  run_id: string
  mode: string
  status: string
  quality: string
  bundle_id: string | null
  bundle_hash: string | null
  bundle_artifact_id: string | null
  section_result_ids: Record<string, string>
  section_quality: Record<string, string>
  section_unavailable: Record<string, string>
  discovery_status: Record<string, string>
  external_calls: number
  budget: Record<string, unknown>
  unavailable_reason: string | null
  note: string
}
