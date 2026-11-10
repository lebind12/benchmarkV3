/**
 * MP-02 관리자 실행 기록·검사 API 클라이언트.
 *
 * 모든 호출은 기존 `previewRequest`를 통과한다. 인증은 HttpOnly 세션 쿠키로만
 * 오가고 토큰을 JS나 URL에 담지 않는다. 조회 함수는 GET만 보낸다.
 */
import { previewRequest, type ApiResult } from '@/lib/api/http'
import type {
  ApproveSectionResponse,
  ApprovalsSummary,
  AuditResponse,
  CancelRunResponse,
  CreateMockRunResponse,
  ReplayResultResponse,
  RunDetail,
  ReaderPreview,
  ReaderPreviewDiagnostics,
  RunListResponse,
  SectionAvailabilityResponse,
  SectionRunResponse,
  UndoReport,
  VersionComparison,
} from './types'

const BASE = '/api/v1/admin/preview'

export const previewRunsApi = {
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

  /** 이 실행이 만든 preview_dev 기록만 취소한다. */
  cancelRun(runId: string, reason: string): Promise<ApiResult<CancelRunResponse>> {
    return previewRequest<CancelRunResponse>(`${BASE}/runs/${runId}/undo`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  },
}
