/**
 * 운영 지표 화면 (MP-08).
 *
 * 이 파일이 확인하는 것:
 * - 지표 표가 분자·분모·표본 수·분모 범위를 함께 보여준다(비율만 보여주지 않는다).
 * - 표본이 없으면 0%가 아니라 "표본 없음"으로 표시하고, 없는 막대를 그리지 않는다.
 * - 제공자가 주지 않은 사용량·비용은 0이 아니라 "미확인"이다.
 * - 개발·모의 기록이 기본 조회에서 빠졌다는 사실과 걸러낸 건수가 화면에 남는다.
 * - 지표에서 내려간 실행 목록이 조회 필터를 그대로 반영하고, 실행 상세에 실패 시도가 남는다.
 * - 이 화면은 조회만 한다(실행 생성·취소를 스스로 호출하지 않는다).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PreviewMetricsView from '@/features/match-preview/PreviewMetricsView.vue'
import {
  metricsFilterContextFromQuery,
  metricsFilterRouteQuery,
  metricsQueryString,
} from '@/features/match-preview/metrics'

const PROD_RUN = '11111111-1111-4111-8111-111111111111'
const MODULE_EXEC = '22222222-2222-4222-8222-222222222222'
const RATE_LIMITED_ATTEMPT = '33333333-3333-4333-8333-333333333333'
const RECOVERED_ATTEMPT = '44444444-4444-4444-8444-444444444444'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function row(overrides: Record<string, unknown> = {}) {
  return {
    metric: 'module_execution_success_rate',
    label: '모듈 실행 성공률',
    scope: 'preview_module_executions',
    numerator: 2,
    denominator: 2,
    ratio: 1,
    available: true,
    sample_size: 2,
    window: {
      from_at: '2026-11-09T00:00:00+00:00',
      to_at: '2026-11-10T00:00:00+00:00',
      source: 'explicit',
      days: 1,
    },
    filters: {
      environments: ['prod'],
      modes: ['live'],
      module_ids: [],
      models: [],
      contract_versions: [],
      defaulted_environments: false,
      defaulted_modes: false,
      note: '지정한 필터로 조회했습니다.',
    },
    detail_run_ids: [PROD_RUN],
    note: '전체 프리뷰 실행 안의 종료된 논리적 모듈 실행 기준입니다.',
    breakdown: {},
    ...overrides,
  }
}

function payload(overrides: Record<string, unknown> = {}) {
  return {
    metric_version: 'mp08-metrics-1',
    window: {
      from_at: '2026-11-09T00:00:00+00:00',
      to_at: '2026-11-10T00:00:00+00:00',
      source: 'default',
      days: 1,
    },
    filters: {
      environments: ['prod'],
      modes: ['live'],
      module_ids: [],
      models: [],
      contract_versions: [],
      defaulted_environments: true,
      defaulted_modes: true,
      note: '기본 조회는 운영(prod)·실호출(live) 기록만 집계합니다.',
    },
    rows: [
      row(),
      row({
        metric: 'attempt_429_rate',
        label: '429 응답',
        scope: 'preview_and_module_attempts',
        numerator: 1,
        denominator: 3,
        ratio: 1 / 3,
        sample_size: 3,
      }),
      row({
        metric: 'evidence_coverage_rate',
        label: '자료 확보율',
        numerator: 1,
        denominator: 2,
        ratio: 0.5,
        sample_size: 2,
      }),
      row({
        metric: 'retry_attempt_rate',
        label: '추가 재시도 시도',
        scope: 'preview_and_module_attempts',
        numerator: 1,
        denominator: 3,
        ratio: 1 / 3,
        sample_size: 3,
      }),
      row({
        metric: 'preview_in_flight_count',
        label: '진행 중 실행 (분모 제외)',
        scope: 'preview_runs',
        numerator: 1,
        denominator: null,
        ratio: null,
        available: true,
        sample_size: 1,
        detail_run_ids: [],
        note: '종료되지 않은 실행 수입니다. 완료율 분모에 들어가지 않습니다.',
      }),
      row({
        metric: 'module_only_success_rate',
        label: '모듈 단독 실행 성공률',
        scope: 'module_runs',
        numerator: null,
        denominator: 0,
        ratio: null,
        available: false,
        sample_size: 0,
        detail_run_ids: [],
        note: '모듈 단독 실행 기록이 없습니다(표본 없음).',
      }),
    ],
    timings: {
      run_wall_clock: {
        label: '전체 실행 시간(대기 포함)',
        sample_size: 1,
        median_ms: 179000,
        p95_ms: 179000,
        note: '표본이 적으면 중앙값·95백분위를 일반 성능으로 단정하지 마세요.',
      },
      attempt_duration: {
        label: '요청 시도 소요 시간',
        sample_size: 3,
        median_ms: 1800,
        p95_ms: 2400,
        note: '표본이 적으면 중앙값·95백분위를 일반 성능으로 단정하지 마세요.',
      },
      wait_total_ms: 2000,
      wait_samples: 1,
      wait_note: '재시도 대기로 기록된 wait_ms 합계입니다.',
    },
    usage: {
      input_tokens: 1000,
      output_tokens: 250,
      search_queries: null,
      attempts_total: 3,
      attempts_with_usage: 1,
      attempts_missing_usage: 2,
      cost: null,
      cost_note: '비용은 가격 기준·적용 시각이 확인되지 않아 계산하지 않았습니다.',
      note: '제공자가 돌려준 값만 합산합니다.',
    },
    runs: [
      {
        run_id: PROD_RUN,
        operation_kind: 'preview',
        environment: 'prod',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        label: '대표 실행',
        fixture_label: '홈 대 원정',
        requested_at: '2026-11-09T01:00:00+00:00',
        finished_at: '2026-11-09T01:04:00+00:00',
        failure_code: null,
        modules: [
          {
            module_execution_id: MODULE_EXEC,
            module_id: 'R1',
            status: 'succeeded',
            quality: 'ready',
            failure_code: null,
            attempt_ids: [RATE_LIMITED_ATTEMPT, RECOVERED_ATTEMPT],
            attempts: [
              {
                attempt_id: RATE_LIMITED_ATTEMPT,
                logical_call_id: 'live-r1-call',
                attempt_ordinal: 0,
                provider: 'vertex',
                model: 'gemini-3.8-flash',
                outcome: 'error',
                http_status: 429,
                error_class: 'rate_limited',
                usage_reported: false,
                duration_ms: 320,
              },
              {
                attempt_id: RECOVERED_ATTEMPT,
                logical_call_id: 'live-r1-call',
                attempt_ordinal: 1,
                provider: 'vertex',
                model: 'gemini-3.8-flash',
                outcome: 'ok',
                http_status: 200,
                error_class: null,
                usage_reported: true,
                duration_ms: 2400,
              },
            ],
          },
        ],
      },
    ],
    excluded: {
      by_environment: 3,
      by_mode: 0,
      fixture_catalog_runs: 1,
      fixture_catalog_attempts: 1,
      other_operation_runs: 0,
      duplicate_events_dropped: 0,
      note: '경기 목록 수집과 그 밖의 작업 실행은 전체 프리뷰 완료율에 넣지 않습니다.',
    },
    notes: ['지표는 저장된 실행 기록만 읽어 계산합니다.'],
    empty: false,
    read_only: true,
    ...overrides,
  }
}

function emptyPayload() {
  return payload({
    rows: [],
    runs: [],
    empty: true,
    usage: {
      input_tokens: null,
      output_tokens: null,
      search_queries: null,
      attempts_total: 0,
      attempts_with_usage: 0,
      attempts_missing_usage: 0,
      cost: null,
      cost_note: '계산하지 않았습니다.',
      note: '표본이 없습니다.',
    },
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/admin/metrics', name: 'preview-metrics', component: PreviewMetricsView }],
  })
}

async function mountView(body: unknown = payload(), initialPath = '/admin/metrics') {
  const fetchMock = vi.fn().mockResolvedValue(json(body))
  vi.stubGlobal('fetch', fetchMock)
  const selectRun = vi.fn()
  const router = makeRouter()
  await router.push(initialPath)
  await router.isReady()
  const wrapper = mount(PreviewMetricsView, {
    props: { onSelectRun: selectRun },
    global: { plugins: [router] },
  })
  await flushPromises()
  return { wrapper, fetchMock, selectRun, router }
}

beforeEach(() => {
  vi.restoreAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('운영 지표 화면', () => {
  it('지표 표에 분자·분모·표본 수와 분모 범위를 함께 보여준다', async () => {
    const { wrapper } = await mountView()

    const table = wrapper.get('[data-testid="metrics-table"]')
    const text = table.text()
    expect(text).toContain('모듈 실행 성공률')
    expect(text).toContain('2 / 2')
    expect(text).toContain('1 / 3')
    expect(text).toContain('1 / 2')
    // 분모 범위를 숨기지 않는다.
    expect(text).toContain('프리뷰 내부 모듈 실행')
    expect(text).toContain('요청 시도')
    expect(text).toContain('모듈 단독 실행')
    // 비율만 크게 보여주고 분모를 감추지 않는다.
    expect(text).toContain('100%')
    expect(text).toContain('50%')

    // 분모가 없는 건수 지표는 비율처럼 꾸미지 않고 건수로 표시한다.
    const inFlight = wrapper.get('[data-testid="metric-preview_in_flight_count"]')
    expect(inFlight.text()).toContain('1건')
    expect(inFlight.text()).toContain('건수 표시')
  })

  it('표본이 없는 지표는 0%가 아니라 표본 없음으로 표시하고 막대를 그리지 않는다', async () => {
    const { wrapper } = await mountView()

    const moduleOnly = wrapper.get('[data-testid="metric-module_only_success_rate"]')
    expect(moduleOnly.text()).toContain('표본 없음')
    expect(moduleOnly.text()).not.toContain('0%')
    expect(moduleOnly.classes()).toContain('row--muted')

    const chart = wrapper.get('[data-testid="metrics-chart"]')
    const chartLabels = chart.findAll('.bars__label').map((node) => node.text())
    expect(chartLabels).not.toContain('모듈 단독 실행 성공률')
    expect(chartLabels).not.toContain('진행 중 실행 (분모 제외)')
    // 표본이 있는 비율 지표는 막대가 있다.
    expect(chart.findAll('.bars__fill').length).toBeGreaterThan(0)
  })

  it('제공자가 주지 않은 사용량·비용은 0이 아니라 미확인으로 표시한다', async () => {
    const { wrapper } = await mountView()

    const usage = wrapper.get('[data-testid="metrics-usage"]')
    const text = usage.text()
    // 검색 사용량과 비용은 미확인이다(0이 아니다).
    expect(text).toContain('미확인')
    expect(text).toContain('1000')
    expect(text).toContain('250')
    expect(wrapper.get('[data-testid="metrics-usage-note"]').text()).toContain('누락 2건')
  })

  it('걸러낸 개발·모의 기록과 목록 수집 제외를 숨기지 않는다', async () => {
    const { wrapper } = await mountView()

    const excluded = wrapper.get('[data-testid="metrics-excluded"]').text()
    expect(excluded).toContain('3건')
    expect(excluded).toContain('경기 목록 수집')
    expect(wrapper.get('[data-testid="metrics-filter-summary"]').text()).toContain('prod')
  })

  it('모의 실행은 실호출로 표시하지 않는다', async () => {
    const body = payload()
    body.runs[0].mode = 'mock'
    body.runs[0].environment = 'dev'
    const { wrapper } = await mountView(body)

    const runButton = wrapper.get(`[data-testid="open-run-${PROD_RUN}"]`)
    expect(runButton.text()).toContain('mock')
    expect(runButton.text()).not.toContain('실호출')
    expect(runButton.get('.chip').classes()).toContain('chip--mock')
  })

  it('지표에서 실행으로 내려가면 조회 필터를 유지하고 실패 시도도 남는다', async () => {
    const { wrapper, fetchMock, selectRun } = await mountView()

    await wrapper.get('[data-testid="drilldown-attempt_429_rate"]').trigger('click')
    await flushPromises()

    // 내려가기는 다시 조회하지 않는다: 이미 받은 목록을 필터링한다.
    expect(fetchMock).toHaveBeenCalledTimes(1)

    const list = wrapper.get('[data-testid="metrics-drilldown"]')
    expect(list.text()).toContain(PROD_RUN.slice(0, 8))

    await wrapper.get(`[data-testid="open-run-${PROD_RUN}"]`).trigger('click')
    await flushPromises()

    // 실행 열기는 이 화면이 라우팅하지 않고 이벤트로 넘긴다(공유 라우터 소유자 연결).
    // 넘길 때 적용 중인 조회 필터도 함께 실어, 이동 뒤 같은 조건으로 돌아올 수 있게 한다.
    expect(selectRun).toHaveBeenCalledTimes(1)
    const emitted = selectRun.mock.calls[0][0] as {
      runId: string
      filters: { environments: string[]; modes: string[] }
    }
    expect(emitted.runId).toBe(PROD_RUN)
    expect(emitted.filters.environments).toEqual([])
    expect(emitted.filters.modes).toEqual([])

    const detail = wrapper.get('[data-testid="metrics-run-detail"]').text()
    // 429 실패 시도와 그 뒤 성공 시도가 함께 남는다.
    expect(detail).toContain('429')
    expect(detail).toContain('200')
    expect(detail).toContain('미확인')
  })

  it('표본이 없으면 0%가 아니라 표본 없음 빈 상태를 보여준다', async () => {
    const { wrapper } = await mountView(emptyPayload())

    const empty = wrapper.get('[data-testid="metrics-empty"]')
    expect(empty.text()).toContain('0%가 아니라 표본이 없다는 뜻입니다')
    expect(wrapper.find('[data-testid="metrics-table"]').exists()).toBe(false)
  })

  it('조회 실패를 0으로 꾸미지 않고 오류로 알린다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(json({ detail: 'admin role required' }, 403)),
    )
    const router = makeRouter()
    await router.push('/admin/metrics')
    await router.isReady()
    const wrapper = mount(PreviewMetricsView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.get('[data-testid="metrics-error"]').text()).toContain('관리자 권한이 없는 계정입니다')
    expect(wrapper.find('[data-testid="metrics-table"]').exists()).toBe(false)
  })

  it('필터를 보내면 조회 조건이 요청에 그대로 실린다', async () => {
    const { wrapper, fetchMock } = await mountView()

    await wrapper.get('[data-testid="env-dev"]').trigger('click')
    await wrapper.get('[data-testid="mode-mock"]').trigger('click')
    await wrapper.get('[data-testid="module-ids"]').setValue('R1, R2')
    await wrapper.get('[data-testid="apply-filters"]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const url = String(fetchMock.mock.calls[1][0])
    expect(url).toContain('environment=dev')
    expect(url).toContain('mode=mock')
    expect(url).toContain('module_id=R1')
    expect(url).toContain('module_id=R2')
  })
})

describe('metricsQueryString', () => {
  it('지정한 조건만 질의 문자열로 만든다', () => {
    expect(metricsQueryString({})).toBe('')
    const query = metricsQueryString({
      environments: ['prod'],
      modes: ['live'],
      moduleIds: ['R1'],
      models: ['gemini-3.8-flash'],
      contractVersions: ['mp02-1'],
      metrics: ['attempt_429_rate'],
    })
    expect(query).toContain('environment=prod')
    expect(query).toContain('mode=live')
    expect(query).toContain('module_id=R1')
    expect(query).toContain('model=gemini-3.8-flash')
    expect(query).toContain('contract_version=mp02-1')
    expect(query).toContain('metric=attempt_429_rate')
  })
})

describe('필터 문맥 왕복', () => {
  it('URL 질의로 실어 보낸 필터를 같은 값으로 복원한다', () => {
    const context = {
      fromAt: '2026-11-09T00:00:00.000Z',
      toAt: '2026-11-10T00:00:00.000Z',
      environments: ['dev' as const, 'test' as const],
      modes: ['mock' as const],
      moduleIds: ['R1', 'R2'],
      models: [],
      contractVersions: ['mp02-1'],
    }
    const routeQuery = metricsFilterRouteQuery(context)
    // 지표 선택·모르는 값은 싣지 않는다.
    expect(routeQuery.metric).toBeUndefined()
    const restored = metricsFilterContextFromQuery(routeQuery)
    expect(restored).toEqual(context)
    const bogus = metricsFilterContextFromQuery({ environment: ['nope'], mode: ['live'] })
    expect(bogus.environments).toEqual([])
    expect(bogus.modes).toEqual(['live'])
  })
})
