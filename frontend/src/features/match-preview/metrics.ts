/**
 * MP-08 운영 지표 조회 클라이언트와 자료형.
 *
 * 서버의 `app/preview/metrics.py`가 만드는 응답과 같은 의미를 유지한다. 이 파일은
 * 조회만 한다. 지표 조회는 외부 모델·API 호출을 일으키지 않는다.
 *
 * 세 축을 섞지 않는다.
 * - environment: dev | test | prod
 * - mode: live | replay | mock (실행 방식)
 * - scope: 이 지표의 분모가 무엇인지(전체 프리뷰 / 프리뷰 내부 모듈 / 모듈 단독 실행 / 시도)
 *
 * 없는 값을 0으로 채우지 않는다. `available: false`면 분모가 없다는 뜻이고,
 * `null`은 0이 아니라 "미확인"이다.
 */
import { previewRequest, type ApiResult } from '@/lib/api/http'

export type MetricsEnvironment = 'dev' | 'test' | 'prod'
export type MetricsMode = 'live' | 'replay' | 'mock'
export type MetricScope =
  | 'preview_runs'
  | 'preview_module_executions'
  | 'module_runs'
  | 'preview_and_module_attempts'

export type MetricRowPayload = {
  metric: string
  label: string
  scope: MetricScope
  numerator: number | null
  denominator: number | null
  ratio: number | null
  available: boolean
  sample_size: number
  window: MetricsWindow
  filters: MetricsFiltersEcho
  detail_run_ids: string[]
  note: string
  breakdown: Record<string, unknown>
}

export type MetricsWindow = {
  from_at: string
  to_at: string
  source: 'default' | 'explicit'
  days: number
}

export type MetricsFiltersEcho = {
  environments: string[]
  modes: string[]
  module_ids: string[]
  models: string[]
  contract_versions: string[]
  defaulted_environments: boolean
  defaulted_modes: boolean
  note: string
}

export type TimingBlock = {
  label: string
  sample_size: number
  median_ms: number | null
  p95_ms: number | null
  note: string
}

export type MetricsUsage = {
  input_tokens: number | null
  output_tokens: number | null
  search_queries: number | null
  attempts_total: number
  attempts_with_usage: number
  attempts_missing_usage: number
  cost: number | null
  cost_note: string
  note: string
}

export type MetricsAttemptPayload = {
  attempt_id: string
  logical_call_id: string
  attempt_ordinal: number
  provider: string
  model: string | null
  outcome: string
  http_status: number | null
  error_class: string | null
  usage_reported: boolean
  duration_ms: number | null
}

export type MetricsModulePayload = {
  module_execution_id: string
  module_id: string
  status: string
  quality: string
  failure_code: string | null
  attempt_ids: string[]
  attempts: MetricsAttemptPayload[]
}

export type MetricsRunPayload = {
  run_id: string
  operation_kind: string
  environment: string
  mode: string
  status: string
  quality: string
  label: string | null
  fixture_label: string | null
  requested_at: string
  finished_at: string | null
  failure_code: string | null
  modules: MetricsModulePayload[]
}

export type MetricsResponse = {
  metric_version: string
  window: MetricsWindow
  filters: MetricsFiltersEcho
  rows: MetricRowPayload[]
  timings: {
    run_wall_clock: TimingBlock
    attempt_duration: TimingBlock
    wait_total_ms: number | null
    wait_samples: number
    wait_note: string
  }
  usage: MetricsUsage
  runs: MetricsRunPayload[]
  excluded: {
    by_environment: number
    by_mode: number
    fixture_catalog_runs: number
    fixture_catalog_attempts: number
    other_operation_runs: number
    duplicate_events_dropped: number
    note: string
  }
  notes: string[]
  empty: boolean
  read_only: boolean
}

export type MetricsRequest = {
  fromAt?: string
  toAt?: string
  environments?: MetricsEnvironment[]
  modes?: MetricsMode[]
  moduleIds?: string[]
  models?: string[]
  contractVersions?: string[]
  metrics?: string[]
}

export function metricsQueryString(request: MetricsRequest): string {
  const params = new URLSearchParams()
  if (request.fromAt) params.set('from_at', request.fromAt)
  if (request.toAt) params.set('to_at', request.toAt)
  for (const env of request.environments ?? []) params.append('environment', env)
  for (const mode of request.modes ?? []) params.append('mode', mode)
  for (const moduleId of request.moduleIds ?? []) params.append('module_id', moduleId)
  for (const model of request.models ?? []) params.append('model', model)
  for (const version of request.contractVersions ?? []) {
    params.append('contract_version', version)
  }
  for (const metric of request.metrics ?? []) params.append('metric', metric)
  return params.toString()
}

export const previewMetricsApi = {
  /** 저장된 기록만 집계한다. 조회는 외부 모델·API를 호출하지 않는다. */
  query(request: MetricsRequest = {}): Promise<ApiResult<MetricsResponse>> {
    const suffix = metricsQueryString(request)
    return previewRequest<MetricsResponse>(
      `/api/v1/admin/preview/metrics${suffix ? `?${suffix}` : ''}`,
    )
  },
}

/**
 * 비율을 화면 표기로 바꾼다.
 *
 * - 표본이 없으면 0%가 아니라 "표본 없음"이다.
 * - 분모가 없는 지표(진행 중 건수 같은 단순 건수)는 비율이 아니라 건수로 표기한다.
 */
export function formatRatio(row: MetricRowPayload): string {
  if (row.denominator === null) {
    return row.numerator === null ? '—' : `${row.numerator}건`
  }
  if (!row.available) return '표본 없음'
  if (row.ratio === null) return '—'
  const percent = row.ratio * 100
  // 소수점이 의미 없이 붙지 않게 다듬는다(50.0% → 50%). 33.3%는 그대로 둔다.
  const rounded = Math.round(percent * 10) / 10
  return `${Number.isInteger(rounded) ? rounded : rounded.toFixed(1)}%`
}

/** 분자/분모를 숨기지 않고 함께 표기한다. 단순 건수 지표는 분모가 없다고 밝힌다. */
export function formatFraction(row: MetricRowPayload): string {
  if (row.denominator === null) return '건수 표시(분모 없음)'
  if (!row.available) return '—'
  return `${row.numerator ?? '—'} / ${row.denominator ?? '—'}`
}

export function formatCount(value: number | null): string {
  return value === null ? '미확인' : String(value)
}

export function formatMs(value: number | null): string {
  if (value === null) return '미확인'
  if (value < 1000) return `${Math.round(value)}ms`
  return `${(value / 1000).toFixed(1)}s`
}

export function scopeLabel(scope: MetricScope): string {
  if (scope === 'preview_runs') return '전체 프리뷰 실행'
  if (scope === 'preview_module_executions') return '프리뷰 내부 모듈 실행'
  if (scope === 'module_runs') return '모듈 단독 실행'
  return '요청 시도'
}

/** 차트용 비율. 표본이 없거나 비율이 아니면 막대를 그리지 않는다(0으로 그리지 않는다). */
export function barPercent(row: MetricRowPayload): number | null {
  if (row.denominator === null || !row.available || row.ratio === null) return null
  return Math.round(row.ratio * 1000) / 10
}
