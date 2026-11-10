/**
 * MP-03 D0 자료 화면의 자료형과 API 호출.
 *
 * 공통 `types.ts`·`api.ts`는 MP-04 소유이므로 이 파일에서만 D0 전용 모양을 정의한다.
 * 경로는 계획 §6 MP-03이 정한 두 개다.
 *
 * - `POST /api/v1/admin/preview/fixtures/import`: 관리자가 명시한 목록 수집
 * - `GET  /api/v1/admin/preview/fixtures`: 저장된 목록 조회(외부 호출 없음)
 *
 * 라우터 등록은 MP-04가 한다. 등록 전에는 두 경로가 404이며 화면은 그 사실을
 * 그대로 보여준다(빈 목록으로 꾸미지 않는다).
 */
import { previewRequest, type ApiResult } from '@/lib/api/http'

export type RunMode = 'live' | 'replay' | 'mock'

export type FixtureCatalogQuery = {
  league_id: number
  date: string
  timezone: string
}

/** 경기 후보 한 건. 외부 ID(fixture_id)와 저장 행 ID(internal_id)를 섞지 않는다. */
export type FixtureCandidate = {
  fixture_id: number
  league_id: number
  league_name: string | null
  season: number
  home_team_id: number | null
  home_team_name: string | null
  away_team_id: number | null
  away_team_name: string | null
  label: string
  kickoff_at: string
  status_short: string | null
  origin: 'stored_db' | 'catalog_import' | string
  origin_note: string
  run_id: string | null
  mode: RunMode | null
  selectable: boolean
}

export type StoredAccess = {
  readable: boolean
  role: string | null
  tables: Record<string, boolean>
  missing: string[]
  required: string[]
  detail: string | null
  boundary_note?: string
}

export type FixtureListResponse = {
  fixtures: FixtureCandidate[]
  sources: { origin: string; label: string; count: number; external_calls: number }[]
  stored_access: StoredAccess
  note: string
  external_calls: number
}

export type ImportFixturesRequest = FixtureCatalogQuery & {
  /** 목록 수집이 몇 시즌을 대상으로 하는지. 모르면 비우고 서버가 계산한다. */
  season?: number
  mode?: RunMode
}

export type ImportFixturesResponse = {
  run_id: string
  module_execution_id: string
  result_id: string
  fixtures: FixtureCandidate[]
  mode: RunMode
  status: string
  /** 주입된 실행기를 부른 횟수. live에서만 external_calls와 같아진다. */
  provider_calls: number
  external_calls: number
  coverage: CoverageEntry[]
  diagnostics: string[]
}

export type CoverageEntry = {
  topic: string
  state: string
  detail: string | null
}

export type D0Claim = {
  claim_id: string
  kind: string
  text: string
  decision: string
  decision_reason: string | null
  snapshot_ids: string[]
}

export type D0Snapshot = {
  snapshot_id: string
  source_kind: 'api' | 'search' | string
  provider: string
  collected_at: string
  provider_updated_at: string | null
  artifact_id: string | null
  validation_status: string
  note: string | null
}

/**
 * D0 단독 실행 결과 화면 모양.
 *
 * 서버의 `D0Result.to_dict()`와 같은 이름을 쓴다. 실행 방식(mode)과 자료 출처
 * (source_kind)는 다른 축이며, 화면은 둘을 따로 표시한다.
 */
export type D0ResultView = {
  result: {
    result_id: string
    module_id: string
    module_execution_id: string
    run_id: string
    version: number
    status: string
    quality: string
    coverage: CoverageEntry[]
    diagnostics: string[]
    failure_code: string | null
    implementation_version: string
    created_at?: string | null
  }
  snapshots: D0Snapshot[]
  coverage: CoverageEntry[]
  claims: D0Claim[]
  diagnostics: string[]
  fixture: {
    fixture_id: number
    league_id: number
    season: number
    home_team_id: number
    away_team_id: number
    kickoff_at: string
  }
  mode: RunMode
  provider_calls: number
  external_calls: number
  external_calls_note?: string
}

const BASE = '/api/v1/admin/preview'

export const previewDataApi = {
  /** 저장된 경기 목록. 서버는 수집을 일으키지 않는다. */
  listFixtures(
    query: Partial<FixtureCatalogQuery> = {},
  ): Promise<ApiResult<FixtureListResponse>> {
    const params = new URLSearchParams()
    if (query.league_id !== undefined) params.set('league_id', String(query.league_id))
    if (query.date) params.set('date', query.date)
    if (query.timezone) params.set('timezone', query.timezone)
    const suffix = params.size > 0 ? `?${params.toString()}` : ''
    return previewRequest<FixtureListResponse>(`${BASE}/fixtures${suffix}`)
  },

  /** 관리자가 명시적으로 누를 때만 목록을 수집한다. */
  importFixtures(
    payload: ImportFixturesRequest,
  ): Promise<ApiResult<ImportFixturesResponse>> {
    return previewRequest<ImportFixturesResponse>(`${BASE}/fixtures/import`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}

/** 실행 방식별 화면 라벨. mock·replay를 live 성공으로 읽지 않게 한다. */
export const MODE_LABELS: Record<string, string> = {
  live: '실호출 (live)',
  replay: '저장 응답 재생 (replay)',
  mock: '모의 실행 (mock, 외부 호출 없음)',
}

/** 자료 확보 상태 라벨. '없음'과 '오류'를 같은 말로 쓰지 않는다. */
export const COVERAGE_LABELS: Record<string, string> = {
  available: '확보',
  search_not_found: '검색 미발견',
  api_not_provided: '제공자 미제공',
  not_run: '실행 안 함',
  call_error: '호출 오류',
  validation_rejected: '검증 탈락',
  source_conflict: '출처 충돌',
  unknown: '알 수 없음',
}

export function coverageLabel(state: string): string {
  return COVERAGE_LABELS[state] ?? state
}

export function modeLabel(mode: string | null | undefined): string {
  if (!mode) return '실행 방식 미상'
  return MODE_LABELS[mode] ?? mode
}
