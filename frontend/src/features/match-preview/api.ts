/**
 * MP-02 관리자 실행 기록·검사 API 클라이언트.
 *
 * 모든 호출은 기존 `previewRequest`를 통과한다. 인증은 HttpOnly 세션 쿠키로만
 * 오가고 토큰을 JS나 URL에 담지 않는다. 조회 함수는 GET만 보낸다.
 */
import { previewRequest, type ApiResult } from '@/lib/api/http'
import type {
  AuditResponse,
  CancelRunResponse,
  CreateMockRunResponse,
  RunDetail,
  RunListResponse,
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

  /** 녹화된 모의 실행을 만든다. 관리자가 명시적으로 눌러야 실행된다. 외부 호출 0회. */
  createMockDemo(): Promise<ApiResult<CreateMockRunResponse>> {
    return previewRequest<CreateMockRunResponse>(`${BASE}/runs/mock-demo`, {
      method: 'POST',
    })
  },

  /** 이 실행이 만든 preview_dev 기록만 취소한다. */
  cancelRun(runId: string, reason: string): Promise<ApiResult<CancelRunResponse>> {
    return previewRequest<CancelRunResponse>(`${BASE}/runs/${runId}/undo`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    })
  },
}
