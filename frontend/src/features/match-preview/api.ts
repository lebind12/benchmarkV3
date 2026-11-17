/**
 * MP-02 관리자 실행 기록·검사 API 클라이언트.
 *
 * 모든 호출은 기존 `previewRequest`를 통과한다. 인증은 HttpOnly 세션 쿠키로만
 * 오가고 토큰을 JS나 URL에 담지 않는다. 조회 함수는 GET만 보낸다.
 */
import { previewRequest, type ApiResult } from '@/lib/api/http'
import type { FixtureCandidate } from './fixtures'
import type {
  ApproveSectionResponse,
  ApprovalsSummary,
  AuditResponse,
  BundlePreviewRunResponse,
  CancelRunResponse,
  CompositionView,
  CreateMockRunResponse,
  ReplayResultResponse,
  RunDetail,
  ReaderPreview,
  ReaderPreviewDiagnostics,
  RunListResponse,
  SectionAvailabilityResponse,
  SectionRegenerationRequest,
  SectionResultsResponse,
  SectionRunResponse,
  UndoReport,
  VersionComparison,
} from './types'

const BASE = '/api/v1/admin/preview'

/**
 * 정보 원문 묶음 조회 경로.
 *
 * PS-01(A)의 `section-interface-manifest.md`가 경로·필드 이름을 확정한다. 확정 전에는
 * 계획서의 표기(`GET /runs/{run_id}/information-bundle`)를 쓴다. 이름이 바뀌면 이
 * 상수와 `informationBundle()`만 고치면 된다.
 */
const INFORMATION_BUNDLE_PATH = (runId: string): string =>
  `${BASE}/runs/${runId}/information-bundle`

/**
 * 섹션 재생성 요청 경로.
 *
 * 계획서는 "기존 `/section-runs`를 유지·확장"으로 적었다. 재생성은 같은 경로에
 * `source_mode`·기준 실행/묶음/결과 ID를 더해 보낸다. A manifest가 별도 경로를
 * 확정하면 이 상수만 바꾼다.
 */
const SECTION_REGENERATION_PATH = `${BASE}/section-runs`

export const previewRunsApi = {
  fixture(fixtureId: number): Promise<ApiResult<FixtureCandidate>> {
    return previewRequest<FixtureCandidate>(`${BASE}/fixtures/${fixtureId}`)
  },

  /**
   * 경기 하나의 전체 프리뷰를 만든다(사용자가 명시적으로 누를 때만).
   *
   * `requestId`는 같은 논리 요청을 서버가 알아보게 하는 값이다. 응답을 받지 못한 요청을
   * 그대로 다시 보낼 때 같은 값을 다시 쓰면 서버가 기존 실행을 돌려주거나 충돌로 알려 주므로
   * 두 번째 모델 호출이 생기지 않는다. 사용자가 **새 실행**을 명시하면 새 값을 쓴다.
   */
  runBundle(
    fixtureId: number,
    options: { requestId?: string } = {},
  ): Promise<ApiResult<BundlePreviewRunResponse>> {
    const body: Record<string, unknown> = { fixture_id: fixtureId, mode: 'live' }
    if (options.requestId) body.request_id = options.requestId
    return previewRequest<BundlePreviewRunResponse>(`${BASE}/bundle-runs`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },

  /** 저장된 실행 목록. 서버는 DB 행만 읽는다. */
  list(): Promise<ApiResult<RunListResponse>> {
    return previewRequest<RunListResponse>(`${BASE}/runs`)
  },

  /** 실행 상세. 요청·원문·변환·다음 입력과 결과 버전을 함께 받는다. */
  detail(runId: string): Promise<ApiResult<RunDetail>> {
    return previewRequest<RunDetail>(`${BASE}/runs/${runId}`)
  },

  /** 같은 모듈 실행의 두 결과 버전 비교. 이전 버전은 남아 있다. */
  compareVersions(
    runId: string,
    moduleExecutionId: string,
    params: { baseVersion?: number; targetVersion?: number } = {},
  ): Promise<ApiResult<VersionComparison>> {
    const query = new URLSearchParams()
    if (params.baseVersion !== undefined) query.set('base_version', String(params.baseVersion))
    if (params.targetVersion !== undefined) {
      query.set('target_version', String(params.targetVersion))
    }
    const suffix = query.size > 0 ? `?${query.toString()}` : ''
    return previewRequest<VersionComparison>(
      `${BASE}/runs/${runId}/results/${moduleExecutionId}/versions${suffix}`,
    )
  },

  /** 취소하면 무엇이 지워지는지 먼저 확인한다. */
  undoReport(runId: string): Promise<ApiResult<UndoReport>> {
    return previewRequest<UndoReport>(`${BASE}/runs/${runId}/undo`)
  },

  /** 이 실행이 남긴 개발 영역 쓰기 내역. */
  audit(runId: string): Promise<ApiResult<AuditResponse>> {
    return previewRequest<AuditResponse>(`${BASE}/runs/${runId}/audit`)
  },

  /** 섹션 워크플로우 승인 현황. 승인 기록이 없으면 없다고 온다. */
  approvals(): Promise<ApiResult<ApprovalsSummary>> {
    return previewRequest<ApprovalsSummary>(`${BASE}/approvals`)
  },

  /**
   * 관리자가 확인한 섹션 워크플로우 버전을 승인한다. 승인 근거로 실행·섹션 결과 ID를
   * 함께 보낸다. 이 호출은 개발 완료 보고나 테스트로 대신할 수 없다.
   */
  approveSection(
    workflowId: string,
    payload: { run_id: string; section_result_id: string; note?: string },
  ): Promise<ApiResult<ApproveSectionResponse>> {
    return previewRequest<ApproveSectionResponse>(
      `${BASE}/sections/${workflowId}/approvals`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },

  /** 섹션 워크플로우별 실행 가능성. 미구현을 숨기지 않고 그대로 온다. */
  sections(): Promise<ApiResult<SectionAvailabilityResponse>> {
    return previewRequest<SectionAvailabilityResponse>(`${BASE}/sections`)
  },

  /**
   * 이 실행이 쓴 **정보 원문 묶음**. 저장된 행만 읽는 조회이며 외부 호출이 없다.
   *
   * 응답은 `unknown`으로 온다. 서버 계약 이름이 아직 확정 전이므로 화면은
   * `parseInformationBundle`로 한 번만 해석한다(새 값을 만들지 않음).
   */
  informationBundle(runId: string): Promise<ApiResult<unknown>> {
    return previewRequest<unknown>(INFORMATION_BUNDLE_PATH(runId))
  },

  /** 이 실행이 저장한 섹션 본문 결과들. 저장된 행만 읽는다. */
  sectionResults(runId: string): Promise<ApiResult<SectionResultsResponse>> {
    return previewRequest<SectionResultsResponse>(`${BASE}/runs/${runId}/section-results`)
  },

  /**
   * 선택 섹션 하나를 **사용자가 명시적으로 요청할 때만** 다시 만든다.
   *
   * `source_mode: 'reuse'`는 저장된 정보 원문을 다시 쓰고, `'refresh'`는 새 수집을
   * 한다. `reprocess_mode: 'reprocess'`는 저장 응답만 다시 변환하는 요청이다(모델 0회).
   * 이 함수는 어느 화면에서도 자동 호출하지 않는다 — 사용자가 버튼을 눌러야 한다.
   */
  regenerateSection(
    payload: SectionRegenerationRequest,
  ): Promise<ApiResult<SectionRunResponse>> {
    return previewRequest<SectionRunResponse>(SECTION_REGENERATION_PATH, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /**
   * 섹션 워크플로우 하나를 실행하고 실행 ID를 받는다.
   *
   * 관리자는 이 ID로 저장된 본문·근거·노드 진단을 다시 연다. 지금 열려 있는 실행
   * 방식은 명시적 모의(mock)이며, 그 결과는 승인 근거가 아니다.
   */
  runSection(payload: {
    workflow_id: string
    mode?: string
    fixture_label?: string
    label?: string
    /** 실제 실행(live)에는 경기 식별자가 필요하다. 모의 시연은 없어도 된다. */
    fixture_id?: number
    league_id?: number
    season?: number
    home_team_id?: number
    away_team_id?: number
    kickoff_at?: string
  }): Promise<ApiResult<SectionRunResponse>> {
    return previewRequest<SectionRunResponse>(`${BASE}/section-runs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  /**
   * 저장된 응답으로 변환만 다시 한다. 외부 모델 호출은 0회이며, 이는 LangGraph
   * 체크포인트 재실행(유료)이나 DB undo와 다른 동작이다.
   */
  replayResult(
    resultId: string,
    note?: string,
  ): Promise<ApiResult<ReplayResultResponse>> {
    return previewRequest<ReplayResultResponse>(`${BASE}/results/${resultId}/replays`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    })
  },

  /** 녹화된 모의 실행을 만든다. 관리자가 명시적으로 눌러야 실행된다. 외부 호출 0회. */
  createMockDemo(): Promise<ApiResult<CreateMockRunResponse>> {
    return previewRequest<CreateMockRunResponse>(`${BASE}/runs/mock-demo`, {
      method: 'POST',
    })
  },

  /**
   * MP-09 독자용 프리뷰. 서버가 저장된 S1 종합 결과를 허용 목록으로 투영해 내려준다.
   * 이 호출은 외부 모델·API를 새로 부르지 않는다(조회 전용).
   */
  readerPreview(runId: string): Promise<ApiResult<ReaderPreview>> {
    return previewRequest<ReaderPreview>(`${BASE}/runs/${runId}/preview`)
  },

  /**
   * 같은 실행의 관리자 진단. 독자용 응답과 다른 경로이며, 누락 사유·제외된 주장·
   * 선택된 입력 버전이 여기에만 있다.
   */
  readerPreviewDiagnostics(runId: string): Promise<ApiResult<ReaderPreviewDiagnostics>> {
    return previewRequest<ReaderPreviewDiagnostics>(
      `${BASE}/runs/${runId}/preview/diagnostics`,
    )
  },

  /**
   * 관리자가 고른 섹션 결과 버전들을 **구성본**으로 저장한다.
   *
   * 선택 ID는 서버가 각자 자기 실행에서 확인하며, 다른 경기의 결과나 없는 결과는
   * 조용히 대체하지 않고 `refused`로 돌려받는다. 이 호출은 모델·HTTP를 쓰지 않는다.
   */
  saveComposition(
    runId: string,
    payload: { fixture_id?: number; selected_result_ids: string[] },
  ): Promise<ApiResult<CompositionView & { note?: string; external_calls?: number }>> {
    return previewRequest<CompositionView & { note?: string; external_calls?: number }>(
      `${BASE}/runs/${runId}/composition`,
      { method: 'POST', body: JSON.stringify(payload) },
    )
  },

  /** 이 실행의 저장된 구성본. 없으면 서버가 `available=false`와 사유를 준다. */
  composition(runId: string): Promise<ApiResult<{ run_id: string; available: boolean; reason: string | null; composition: CompositionView | null }>> {
    return previewRequest<{ run_id: string; available: boolean; reason: string | null; composition: CompositionView | null }>(
      `${BASE}/runs/${runId}/composition`,
    )
  },

  /** 이 실행이 만든 preview_dev 기록만 취소한다. */
  cancelRun(runId: string, reason: string): Promise<ApiResult<CancelRunResponse>> {
    return previewRequest<CancelRunResponse>(`${BASE}/runs/${runId}/undo`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  },
}
