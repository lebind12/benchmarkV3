/**
 * 기간 수집·다경기 생성 진행 영역 검사.
 *
 * 확인하는 것은 사용자가 실제로 관측하는 동작 다섯 묶음이다.
 *
 * 1. 수집이 끝나도 생성 POST가 나가지 않는다(자동 생성 금지).
 * 2. '선택 경기 프리뷰 생성'은 두 경기를 순서대로 한 번씩 보내고, 첫 경기가 실패해도
 *    두 번째를 진행한다.
 * 3. 생성 성공과 저장 판정은 별개이며, 저장 판정은 같은 실행을 다시 읽은 값으로만 한다.
 * 4. 화면 새로고침은 GET만 보내고, 늦게 도착한 이전 요청의 응답은 표에 붙지 않는다.
 * 5. 요청 식별자는 재전송에서 유지되고, 명시적 새 실행에서는 새 값이다.
 *
 * 경계는 `authenticatedFetch` 한 곳만 대역으로 바꾼다. 그 위의 실제 모듈(경로·본문·정규화)을
 * 그대로 실행해 요청 본문까지 검사한다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { VueWrapper } from '@vue/test-utils'

const currentQuery = vi.hoisted(() => ({ value: {} as Record<string, string> }))
const replace = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: currentQuery.value }),
  useRouter: () => ({ replace, push: vi.fn() }),
}))

type Step =
  | { kind: 'json'; status?: number; body: unknown }
  | { kind: 'network' }
  /** 응답을 붙잡아 둔다. `release()` 전에는 이 호출이 끝나지 않는다. */
  | { kind: 'held'; gate: Promise<void>; then: Step }

type Call = { url: string; method: string; body: unknown }

const calls = vi.hoisted(() => [] as Call[])
const routes = vi.hoisted(() => new Map<string, unknown[]>())

function routeKey(method: string, url: string, fixtureId?: number): string {
  return fixtureId === undefined ? `${method} ${url}` : `${method} ${url}#${fixtureId}`
}

/** 경로 공통 응답(조회). */
function queue(method: string, url: string, ...steps: Step[]) {
  const key = routeKey(method, url)
  routes.set(key, [...(routes.get(key) ?? []), ...steps])
}

/** 경기 하나에만 해당하는 응답. 생성처럼 같은 경로를 여러 경기가 쓰는 경우에 쓴다. */
function queueFor(method: string, url: string, fixtureId: number, ...steps: Step[]) {
  const key = routeKey(method, url, fixtureId)
  routes.set(key, [...(routes.get(key) ?? []), ...steps])
}

vi.mock('@/lib/api/session', () => ({
  authenticatedFetch: async (path: string, init: RequestInit = {}) => {
    const method = (init.method ?? 'GET').toUpperCase()
    const body = typeof init.body === 'string' ? JSON.parse(init.body) : null
    calls.push({ url: path, method, body })
    const fixtureId =
      body && typeof body === 'object' && typeof (body as { fixture_id?: unknown }).fixture_id === 'number'
        ? (body as { fixture_id: number }).fixture_id
        : undefined
    const scoped = fixtureId === undefined ? [] : (routes.get(routeKey(method, path, fixtureId)) ?? [])
    const steps = (scoped.length > 0 ? scoped : (routes.get(routeKey(method, path)) ?? [])) as Step[]
    let step = steps.shift()
    if (!step) {
      return new Response(JSON.stringify({ detail: `no stub: ${method} ${path}` }), {
        status: 404,
        headers: { 'content-type': 'application/json' },
      })
    }
    if (step.kind === 'held') {
      await step.gate
      step = step.then
    }
    if (step.kind === 'network') throw new TypeError('network down')
    if (step.kind !== 'json') throw new TypeError('held step was not released')
    return new Response(JSON.stringify(step.body), {
      status: step.status ?? 200,
      headers: { 'content-type': 'application/json' },
    })
  },
  setAccessToken: vi.fn(),
  refreshSession: vi.fn(),
  logoutSession: vi.fn(),
}))

import PreviewTestPanel from './PreviewTestPanel.vue'
import {
  storageMismatchSections,
  toMatchPreviewView,
  withoutBlockedSections,
} from '@/lib/api/previewView'
import type { PreviewRunData } from '@/lib/api/preview'
import type { SectionResultView } from '@/features/match-preview/types'
import { parsePlan, parseRun } from '@/lib/api/previewTest'

const PT = '/api/v1/admin/management/preview-test'
const PV = '/api/v1/admin/preview'

const CITY_FULHAM = 1557474
const CHELSEA_LEEDS = 1557470
const TOTTENHAM_IPSWICH = 1557476

function candidatesPayload() {
  return {
    as_of: '2026-11-17T10:00:00+00:00',
    timezone: 'Asia/Seoul',
    candidates: [
      {
        fixture_id: CITY_FULHAM,
        kickoff_at: '2026-11-21T12:30:00+00:00',
        home_name: '맨체스터 시티',
        away_name: '풀럼',
        league_name: 'Premier League',
        season: 2026,
        priority: 1,
      },
      {
        fixture_id: CHELSEA_LEEDS,
        kickoff_at: '2026-11-21T15:00:00+00:00',
        home_name: '첼시',
        away_name: '리즈 유나이티드',
        league_name: 'Premier League',
        season: 2026,
        priority: 2,
      },
      {
        fixture_id: TOTTENHAM_IPSWICH,
        kickoff_at: '2026-11-21T15:00:00+00:00',
        home_name: '토트넘',
        away_name: '입스위치',
        league_name: 'Premier League',
        season: 2026,
        priority: 3,
      },
    ],
    reason: null,
  }
}

function planPayload() {
  return {
    fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
    fixture_from: '2026-11-16T15:00:00+00:00',
    fixture_to: '2026-11-21T15:00:00+00:00',
    target_ids: [7],
    targets: [{ id: 7, league_name: 'Premier League', season: 2026, include_details: true }],
    can_collect: true,
    blocking_reasons: [],
    scope_notes: ['기간 안의 다른 경기 자료도 함께 갱신됩니다.'],
  }
}

function collectionRun(overrides: Record<string, unknown> = {}) {
  return {
    id: 'run-collect-1',
    status: 'running',
    actor: 'admin@example.com',
    created_at: '2026-11-17T10:00:00+00:00',
    started_at: '2026-11-17T10:00:01+00:00',
    finished_at: null,
    progress: 40,
    stage: 'fixtures',
    items: [
      {
        target_id: 7,
        name: 'Premier League',
        season: 2026,
        status: 'running',
        total_known: true,
        total: 12,
        saved: 5,
        failed: 0,
        pending: 7,
        stored_rows: 31,
      },
    ],
    logs: [],
    ...overrides,
  }
}

function finishedCollectionRun(overrides: Record<string, unknown> = {}) {
  return collectionRun({
    status: 'succeeded',
    finished_at: '2026-11-17T10:05:00+00:00',
    progress: 100,
    stage: 'done',
    items: [
      {
        target_id: 7,
        name: 'Premier League',
        season: 2026,
        status: 'succeeded',
        total_known: true,
        total: 12,
        saved: 12,
        failed: 0,
        pending: 0,
        stored_rows: 48,
      },
    ],
    logs: [{ level: 'info', message: '완료' }],
    ...overrides,
  })
}

function bundleRun(runId: string) {
  return {
    run_id: runId,
    mode: 'live',
    status: 'succeeded',
    quality: 'ready',
    bundle_id: null,
    bundle_hash: null,
    bundle_artifact_id: null,
    section_result_ids: {},
    section_quality: {},
    section_unavailable: {},
    discovery_status: {},
    external_calls: 3,
    budget: {},
    unavailable_reason: null,
    note: '',
  }
}

function readerPreview(fixtureId: number, label: string) {
  return {
    fixture: {
      fixture_id: fixtureId,
      home_team_id: 13,
      away_team_id: 4,
      league_id: 39,
      season: 2026,
      kickoff_at: '2026-11-21T12:30:00Z',
      label,
      league: 'Premier League',
    },
    headline: label,
    generated_at: '2026-11-17T10:06:00Z',
    data_as_of: null,
    attribution: { ai_forecast_label: 'AI 전망', ai_forecast_note: '모델 전망' },
    body: '본문',
    sections: [
      {
        section_id: 'section_ai_forecast',
        title: 'AI 경기 전망',
        body: '저장 본문',
        sources: [],
        quality: 'ready',
        partial: false,
        version: 1,
      },
    ],
    complete: true,
  }
}

function sectionRow(overrides: Partial<SectionResultView> = {}): SectionResultView {
  return {
    section_result_id: 'sr-forecast',
    run_id: 'run-a',
    workflow_id: 'section_ai_forecast',
    workflow_version: 'wf-1',
    version: 1,
    title: 'AI 경기 전망',
    body: '저장 본문',
    sources: [],
    mode: 'live',
    mode_label: '실호출',
    environment: 'dev',
    quality: 'ready',
    module_execution_ids: [],
    result_ids: [],
    diagnostics: [],
    unavailable_reason: null,
    unavailable: false,
    output_contract_version: 'ocv-1',
    contract_version: 'cv-1',
    created_at: null,
    supersedes_section_result_id: null,
    approvable: false,
    ...overrides,
  }
}

function sectionsPayload(runId: string, rowOverrides: Partial<SectionResultView> = {}) {
  return { run_id: runId, section_results: [sectionRow({ run_id: runId, ...rowOverrides })] }
}

/** 생성 응답과 그 실행의 저장 재조회를 함께 예약한다. */
function queueGeneratedRun(
  fixtureId: number,
  runId: string,
  label: string,
  rowOverrides: Partial<SectionResultView> = {},
) {
  queueFor('POST', `${PV}/bundle-runs`, fixtureId, { kind: 'json', body: bundleRun(runId) })
  queue('GET', `${PV}/runs/${runId}/preview`, { kind: 'json', body: readerPreview(fixtureId, label) })
  queue('GET', `${PV}/runs/${runId}/section-results`, {
    kind: 'json',
    body: sectionsPayload(runId, rowOverrides),
  })
  queue('GET', `${PV}/runs/${runId}`, { kind: 'json', body: { summary: { run_id: runId } } })
}

function bundleCalls(): Call[] {
  return calls.filter((call) => call.url.endsWith('/bundle-runs'))
}

function requestIds(): string[] {
  return bundleCalls().map((call) => (call.body as { request_id?: string }).request_id ?? '')
}

function posts(): Call[] {
  return calls.filter((call) => call.method !== 'GET')
}

async function mountPanel(): Promise<VueWrapper> {
  const wrapper = mount(PreviewTestPanel, { props: { canGenerate: true } })
  await flushPromises()
  return wrapper
}

function queueBase() {
  queue('GET', `${PT}/candidates`, { kind: 'json', body: candidatesPayload() })
  queue('GET', `${PT}/plan?fixture_ids=${CITY_FULHAM}&fixture_ids=${CHELSEA_LEEDS}`, {
    kind: 'json',
    body: planPayload(),
  })
}

beforeEach(() => {
  calls.length = 0
  routes.clear()
  replace.mockClear()
  currentQuery.value = { tab: 'preview' }
})

describe('기간 수집 시험 — 수집과 생성의 분리', () => {
  it('수집이 끝나도 생성 POST를 보내지 않고, 사용자가 눌러야만 두 경기를 순서대로 생성한다', async () => {
    queueBase()
    queue('POST', `${PT}/runs`, { kind: 'json', body: collectionRun() })
    queue('GET', `${PT}/runs/run-collect-1`, { kind: 'json', body: finishedCollectionRun() })

    vi.useFakeTimers()
    try {
      const wrapper = await mountPanel()

      // 진입은 후보·계획 조회뿐이다. 이 단계에서 POST는 0건이다.
      expect(posts()).toEqual([])
      expect(wrapper.text()).toContain('맨체스터 시티 vs 풀럼')
      expect(wrapper.get('[data-testid="ptp-scope"]').text()).toContain('수집 기간')
      expect(wrapper.get('[data-testid="ptp-scope"]').text()).toContain('Premier League 2026')
      // 부상 자료 미갱신 안내를 먼저 보여준다.
      expect(wrapper.get('[data-testid="ptp-injuries-note"]').text()).toContain('/injuries')

      await wrapper.get('[data-testid="ptp-start-collection"]').trigger('click')
      await flushPromises()
      const started = posts()
      expect(started.length).toBe(1)
      expect(started[0].url).toBe(`${PT}/runs`)
      expect(started[0].body).toEqual({
        fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
        fixture_from: '2026-11-16T15:00:00+00:00',
        fixture_to: '2026-11-21T15:00:00+00:00',
      })

      // 폴링이 종료를 확인한다.
      await vi.advanceTimersByTimeAsync(3100)
      await flushPromises()
      expect(wrapper.get('[data-testid="ptp-collection-notice"]').text()).toContain(
        '생성은 시작하지 않았습니다',
      )
      // 수집 종료가 생성으로 이어지지 않는다.
      expect(posts().length).toBe(1)
      expect(bundleCalls()).toEqual([])

      // 사용자가 눌렀을 때만 두 경기 생성이 고른 순서대로 나간다.
      queueGeneratedRun(CITY_FULHAM, 'run-a', '맨체스터 시티 vs 풀럼')
      queueGeneratedRun(CHELSEA_LEEDS, 'run-b', '첼시 vs 리즈 유나이티드')
      await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
      await flushPromises()

      expect(bundleCalls().map((call) => (call.body as { fixture_id: number }).fixture_id)).toEqual([
        CITY_FULHAM,
        CHELSEA_LEEDS,
      ])
      expect(wrapper.get(`[data-testid="ptp-storage-${CITY_FULHAM}"]`).text()).toContain('저장 확인')
      expect(wrapper.get(`[data-testid="ptp-storage-${CHELSEA_LEEDS}"]`).text()).toContain(
        '저장 확인',
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('첫 경기가 실패해도 두 번째 경기를 계속 진행한다', async () => {
    queueBase()
    queueFor('POST', `${PV}/bundle-runs`, CITY_FULHAM, {
      kind: 'json',
      status: 500,
      body: { detail: '첫 경기 생성 실패' },
    })
    queueGeneratedRun(CHELSEA_LEEDS, 'run-b', '첼시 vs 리즈 유나이티드')

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()

    expect(bundleCalls().length).toBe(2)
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain('실패')
    expect(wrapper.get(`[data-testid="ptp-generation-${CHELSEA_LEEDS}"]`).text()).toContain(
      '생성 응답 성공',
    )
    // 두 번째는 저장까지 확인된다. 첫 경기 실패가 두 번째 저장 판정을 막지 않는다.
    expect(wrapper.get(`[data-testid="ptp-storage-${CHELSEA_LEEDS}"]`).text()).toContain('저장 확인')
  })

  it('저장 조회가 실패한 경기는 저장 성공으로 표시하지 않는다', async () => {
    queueBase()
    queueFor('POST', `${PV}/bundle-runs`, CITY_FULHAM, { kind: 'json', body: bundleRun('run-a') })
    queue('GET', `${PV}/runs/run-a/preview`, {
      kind: 'json',
      body: readerPreview(CITY_FULHAM, '맨체스터 시티 vs 풀럼'),
    })
    queue('GET', `${PV}/runs/run-a/section-results`, {
      kind: 'json',
      status: 503,
      body: { detail: '섹션 결과 조회 실패' },
    })
    queue('GET', `${PV}/runs/run-a`, { kind: 'json', body: { summary: { run_id: 'run-a' } } })
    queueGeneratedRun(CHELSEA_LEEDS, 'run-b', '첼시 vs 리즈 유나이티드')

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()

    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain(
      '생성 응답 성공',
    )
    expect(wrapper.get(`[data-testid="ptp-storage-${CITY_FULHAM}"]`).text()).toBe('저장 확인 불가')
    expect(wrapper.get(`[data-testid="ptp-storage-note-${CITY_FULHAM}"]`).text()).toContain(
      '섹션 결과 조회 실패',
    )
  })

  it('정본 저장 불일치는 저장 불일치로 표시하고 저장 성공으로 읽지 않는다', async () => {
    queueBase()
    queueGeneratedRun(CITY_FULHAM, 'run-a', '맨체스터 시티 vs 풀럼', {
      storage_status: 'storage_mismatch',
      storage_mismatch: true,
    })
    queueGeneratedRun(CHELSEA_LEEDS, 'run-b', '첼시 vs 리즈 유나이티드')

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()

    expect(wrapper.get(`[data-testid="ptp-storage-${CITY_FULHAM}"]`).text()).toContain('저장 불일치')
    expect(wrapper.get(`[data-testid="ptp-storage-note-${CITY_FULHAM}"]`).text()).toContain(
      'section_ai_forecast',
    )
  })

  it('수량 미상(legacy_unknown)을 0건으로 표시하지 않고 단위를 함께 적는다', async () => {
    queueBase()
    queue('POST', `${PT}/runs`, {
      kind: 'json',
      body: collectionRun({
        status: 'succeeded',
        counts_kind: 'legacy_unknown',
        items: [
          {
            target_id: 7,
            name: 'Premier League',
            season: 2026,
            status: 'succeeded',
            total_known: false,
            total: null,
            saved: null,
            failed: null,
            pending: null,
            stored_rows: 31,
          },
        ],
      }),
    })

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-start-collection"]').trigger('click')
    await flushPromises()

    const item = wrapper.get('[data-testid="ptp-item-7"]').text()
    // 모르는 수량을 0으로 채우면 "0건 수집"과 구분되지 않는다.
    expect(item).toContain('미상')
    expect(item).not.toContain('저장 0')
    // 기록 행 수는 서버가 준 값이므로 그대로 보인다.
    expect(item).toContain('31행')
  })

  it('처리 단위(processing_units) 수량에는 경기가 아니라 처리 단위라고 적는다', async () => {
    queueBase()
    queue('POST', `${PT}/runs`, {
      kind: 'json',
      body: collectionRun({ status: 'succeeded', counts_kind: 'processing_units' }),
    })

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-start-collection"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="ptp-item-7"]').text()).toContain('처리 단위')
    expect(wrapper.get('[data-testid="ptp-item-7"]').text()).toContain('저장 5')
  })
})

describe('기간 수집 시험 — 생성 선택은 세 경기 이상 허용', () => {
  it('세 경기를 골라도 선택이 유지되고, 생성은 그 셋을 순서대로 실행한다', async () => {
    queueBase()
    queueFor('POST', `${PV}/bundle-runs`, CITY_FULHAM, {
      kind: 'json',
      status: 500,
      body: { detail: '첫 경기 실패' },
    })
    queueGeneratedRun(CHELSEA_LEEDS, 'run-b', '첼시 vs 리즈 유나이티드')
    queueGeneratedRun(TOTTENHAM_IPSWICH, 'run-c', '토트넘 vs 입스위치')

    const wrapper = await mountPanel()
    // 기본 선택 두 개에 세 번째를 더한다. 기존 선택이 자동으로 빠지면 안 된다.
    await wrapper.get(`[data-testid="ptp-candidate-${TOTTENHAM_IPSWICH}"]`).setValue(true)
    await flushPromises()

    for (const fixtureId of [CITY_FULHAM, CHELSEA_LEEDS, TOTTENHAM_IPSWICH]) {
      const input = wrapper.get(`[data-testid="ptp-candidate-${fixtureId}"]`)
      expect((input.element as HTMLInputElement).checked).toBe(true)
    }
    // 선택이 세 개면 생성 버튼은 눌린다.
    expect(wrapper.get('[data-testid="ptp-generate"]').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="ptp-generate"]').text()).toContain('3경기')

    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()

    // 세 경기가 고른 순서대로 한 번씩 나간다.
    expect(
      bundleCalls().map((call) => (call.body as { fixture_id: number }).fixture_id),
    ).toEqual([CITY_FULHAM, CHELSEA_LEEDS, TOTTENHAM_IPSWICH])
    // 첫 경기가 실패해도 둘째·셋째가 저장까지 확인된다.
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain('실패')
    expect(wrapper.get(`[data-testid="ptp-storage-${CHELSEA_LEEDS}"]`).text()).toContain('저장 확인')
    expect(
      wrapper.get(`[data-testid="ptp-storage-${TOTTENHAM_IPSWICH}"]`).text(),
    ).toContain('저장 확인')
  })

  it('선택이 두 개가 아니면 수집 버튼이 이유를 안내하고 계획을 조회하지 않는다', async () => {
    // 계획 응답은 두 경기 조합에만 예약한다. 세 경기에서 계획을 부르면 대역이 없어 실패한다.
    // 진입 시 한 번, 선택을 두 개로 되돌릴 때 한 번이므로 두 번 예약한다.
    queue('GET', `${PT}/candidates`, { kind: 'json', body: candidatesPayload() })
    for (let index = 0; index < 2; index += 1) {
      queue('GET', `${PT}/plan?fixture_ids=${CITY_FULHAM}&fixture_ids=${CHELSEA_LEEDS}`, {
        kind: 'json',
        body: planPayload(),
      })
    }

    const wrapper = await mountPanel()
    // 진입 시 두 경기 선택으로 한 번 조회된 계획은 이미 유효한 근거다.
    const plansAtMount = calls.filter((call) => call.url.includes('/plan')).length
    expect(plansAtMount).toBe(1)

    await wrapper.get(`[data-testid="ptp-candidate-${TOTTENHAM_IPSWICH}"]`).setValue(true)
    await flushPromises()

    const hint = wrapper.get('[data-testid="ptp-collection-scope-hint"]')
    expect(hint.text()).toContain('정확히 두 경기')
    expect(hint.text()).toContain('3경기')
    expect(wrapper.get('[data-testid="ptp-start-collection"]').attributes('disabled')).toBeDefined()

    // 세 경기 상태에서는 계획 조회를 보내지 않는다(서버가 422로 거부하는 요청).
    expect(calls.filter((call) => call.url.includes('/plan')).length).toBe(plansAtMount)
    // 선택이 두 개로 돌아오면 계획이 다시 조회된다.
    await wrapper.get(`[data-testid="ptp-candidate-${TOTTENHAM_IPSWICH}"]`).setValue(false)
    await flushPromises()
    expect(wrapper.find('[data-testid="ptp-collection-scope-hint"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="ptp-scope"]').text()).toContain('수집 기간')
  })
})

describe('기간 수집 시험 — 실제 수집 근거 표시', () => {
  function evidenceRun(evidence: unknown, overrides: Record<string, unknown> = {}) {
    return collectionRun({
      status: 'succeeded',
      finished_at: '2026-11-17T10:05:00+00:00',
      collection_evidence: evidence,
      ...overrides,
    })
  }

  async function runWithEvidence(evidence: unknown) {
    queueBase()
    queue('POST', `${PT}/runs`, { kind: 'json', body: evidenceRun(evidence) })
    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-start-collection"]').trigger('click')
    await flushPromises()
    return wrapper
  }

  it('계획·저장 확인·상세 저장·미확인을 각각 표시하고 생성 대상과 합치지 않는다', async () => {
    const wrapper = await runWithEvidence({
      scope_fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
      fixture_from: '2026-11-16T15:00:00+00:00',
      fixture_to: '2026-11-21T15:00:00+00:00',
      planned_fixture_ids: [111, 222, 333],
      stored_fixture_ids: [111, 222],
      detail_stored_fixture_ids: [222],
      unverified_fixture_ids: [333],
      partial: false,
      counts: { planned: 3, stored: 2, detail_stored: 1, unverified: 1 },
      notes: ['계획 경기와 저장 경기를 구별합니다.'],
    })

    expect(wrapper.get('[data-testid="ptp-evidence-scope"]').text()).toContain(
      `${CITY_FULHAM}, ${CHELSEA_LEEDS}`,
    )
    const summary = wrapper.get('[data-testid="ptp-evidence-detail"] summary').text()
    expect(summary).toContain('계획 3')
    expect(summary).toContain('저장 확인 2')
    expect(summary).toContain('상세 응답 저장 1')
    expect(summary).toContain('미확인 1')

    expect(wrapper.get('[data-testid="ptp-evidence-planned"]').text()).toBe('111, 222, 333')
    expect(wrapper.get('[data-testid="ptp-evidence-stored"]').text()).toBe('111, 222')
    expect(wrapper.get('[data-testid="ptp-evidence-detail-stored"]').text()).toBe('222')
    expect(wrapper.get('[data-testid="ptp-evidence-unverified"]').text()).toBe('333')
    // 근거는 접힌 채로 두고 사용자가 펼친다(표 위 공간을 차지하지 않게).
    expect(
      (wrapper.get('[data-testid="ptp-evidence-detail"]').element as HTMLDetailsElement).open,
    ).toBe(false)
    // 미확인을 실패로 단정하지 않는다는 문장이 함께 있다.
    expect(wrapper.text()).toContain('저장 미확인은 실패로 단정하지 않습니다')
  })

  it('근거 객체가 없으면 0건으로 추정하지 않고 미기록으로 표시한다', async () => {
    const wrapper = await runWithEvidence(undefined)

    const missing = wrapper.get('[data-testid="ptp-evidence-missing"]')
    expect(missing.text()).toContain('근거가 기록되지 않았습니다')
    expect(missing.text()).toContain('0건으로 추정하지 않습니다')
    expect(wrapper.find('[data-testid="ptp-evidence-detail"]').exists()).toBe(false)
  })

  it('부분 확인 상태를 표시한다', async () => {
    const wrapper = await runWithEvidence({
      scope_fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
      fixture_from: '2026-11-16T15:00:00+00:00',
      fixture_to: '2026-11-21T15:00:00+00:00',
      planned_fixture_ids: [111],
      stored_fixture_ids: [],
      detail_stored_fixture_ids: [],
      unverified_fixture_ids: [111],
      partial: true,
      counts: { planned: 1, stored: 0, detail_stored: 0, unverified: 1 },
      notes: [],
    })

    expect(wrapper.get('[data-testid="ptp-evidence-partial"]').text()).toContain(
      '확인하지 못했습니다',
    )
    // 저장이 0이면 "없음(0건)"이며 목록 자체가 없는 것과 다르다.
    expect(wrapper.get('[data-testid="ptp-evidence-stored"]').text()).toBe('없음(0건)')
  })
})

describe('기간 수집 시험 — 계획 응답 경계 정규화', () => {
  /**
   * A의 실제 응답 모양에서 **존재하는 target 차단 사례 하나**를 그대로 넣어, 경계가
   * message를 안내에 쓰고 code를 보존하는지 본다.
   */
  it('target_not_found 사유의 message를 보존하고 code를 함께 남긴다', () => {
    const parsed = parsePlan({
      fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
      fixture_from: '2026-11-16T15:00:00+00:00',
      fixture_to: '2026-11-21T15:00:00+00:00',
      target_ids: [],
      targets: [],
      can_collect: false,
      blocking_reasons: [
        {
          code: 'target_not_found',
          message: '경기 1557474의 리그/시즌(39/2026)에 수집 대상이 없습니다.',
        },
      ],
      scope_notes: [],
    })

    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.value.blocking_reasons).toEqual([
      {
        code: 'target_not_found',
        message: '경기 1557474의 리그/시즌(39/2026)에 수집 대상이 없습니다.',
      },
    ])
    expect(parsed.value.can_collect).toBe(false)
  })

  it('끝 시각이 없으면 실행 불가로 확정하고 목록 해석을 계속한다', () => {
    const parsed = parsePlan({
      fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
      fixture_from: '2026-11-16T15:00:00+00:00',
      fixture_to: null,
      target_ids: [7],
      targets: [{ id: 7, league_name: 'Premier League', season: 2026, include_details: true }],
      can_collect: true,
      blocking_reasons: [{ code: 'kickoff_unknown', message: '킥오프 시각이 없습니다.' }],
      scope_notes: [],
    })

    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    // 서버가 can_collect=true라 해도 끝 시각이 없으면 기간이 성립하지 않는다.
    expect(parsed.value.can_collect).toBe(false)
    expect(parsed.value.fixture_to).toBeNull()
    expect(parsed.value.targets[0].id).toBe(7)
  })
})

describe('기간 수집 시험 — 실제 수집 근거 파싱', () => {
  it('근거 객체의 네 목록과 건수를 그대로 옮기고, 없으면 null이다', () => {
    const withEvidence = parseRun({
      id: 'run-1',
      status: 'succeeded',
      items: [],
      logs: [],
      collection_evidence: {
        scope_fixture_ids: [CITY_FULHAM, CHELSEA_LEEDS],
        planned_fixture_ids: [11, 22],
        stored_fixture_ids: [11],
        detail_stored_fixture_ids: [],
        unverified_fixture_ids: [22],
        partial: false,
        counts: { planned: 2, stored: 1, detail_stored: 0, unverified: 1 },
        notes: ['구분합니다.'],
      },
    })
    expect(withEvidence.ok).toBe(true)
    if (!withEvidence.ok) return
    const evidence = withEvidence.value.collection_evidence
    expect(evidence?.planned_fixture_ids).toEqual([11, 22])
    expect(evidence?.unverified_fixture_ids).toEqual([22])
    expect(evidence?.counts).toEqual({
      planned: 2,
      stored: 1,
      detail_stored: 0,
      unverified: 1,
    })

    // 근거 키가 없는 응답은 "미기록"이며, 0건으로 채우지 않는다.
    const without = parseRun({ id: 'run-2', status: 'succeeded', items: [], logs: [] })
    expect(without.ok).toBe(true)
    if (!without.ok) return
    expect(without.value.collection_evidence).toBeNull()
  })
})

describe('기간 수집 시험 — 서버 계획 응답의 실제 모양', () => {
  it('수집 불가 사유는 {code, message} 객체이며 message를 그대로 보여준다', async () => {
    queue('GET', `${PT}/candidates`, { kind: 'json', body: candidatesPayload() })
    queue('GET', `${PT}/plan?fixture_ids=${CITY_FULHAM}&fixture_ids=${CHELSEA_LEEDS}`, {
      kind: 'json',
      body: {
        ...planPayload(),
        can_collect: false,
        blocking_reasons: [
          { code: 'fixture_started', message: '경기 1557474의 킥오프가 이미 지났습니다.' },
          { code: 'target_inactive', message: '수집 대상 7(시즌 2026)이 비활성 상태입니다.' },
        ],
      },
    })

    const wrapper = await mountPanel()
    const blocked = wrapper.get('[data-testid="ptp-blocked"]')
    expect(blocked.text()).toContain('킥오프가 이미 지났습니다')
    expect(blocked.text()).toContain('비활성 상태입니다')
    // 실행 불가이므로 수집 버튼은 눌리지 않는다.
    expect(
      wrapper.get('[data-testid="ptp-start-collection"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('끝 시각을 확인하지 못한 계획은 실행하지 않고 사유를 보여준다', async () => {
    queue('GET', `${PT}/candidates`, { kind: 'json', body: candidatesPayload() })
    queue('GET', `${PT}/plan?fixture_ids=${CITY_FULHAM}&fixture_ids=${CHELSEA_LEEDS}`, {
      kind: 'json',
      body: {
        ...planPayload(),
        fixture_to: null,
        can_collect: false,
        blocking_reasons: [{ code: 'kickoff_unknown', message: '경기 1557470의 킥오프 시각이 없습니다.' }],
      },
    })

    const wrapper = await mountPanel()
    // 끝 시각이 없으면 기간이 성립하지 않는다. 수집을 보내면 안 된다.
    expect(
      wrapper.get('[data-testid="ptp-start-collection"]').attributes('disabled'),
    ).toBeDefined()
    expect(wrapper.get('[data-testid="ptp-blocked"]').text()).toContain('킥오프 시각이 없습니다')
    expect(posts()).toEqual([])
  })
})

describe('기간 수집 시험 — 새로고침과 늦은 응답', () => {
  it('새로고침 복원은 GET만 보내고 주소의 실행을 다시 읽는다', async () => {
    currentQuery.value = {
      tab: 'preview',
      testFixtures: `${CITY_FULHAM},${CHELSEA_LEEDS}`,
      testRuns: 'run-a',
      testCollection: 'run-collect-1',
    }
    queue('GET', `${PT}/candidates`, { kind: 'json', body: candidatesPayload() })
    queue('GET', `${PT}/plan?fixture_ids=${CITY_FULHAM}&fixture_ids=${CHELSEA_LEEDS}`, {
      kind: 'json',
      body: planPayload(),
    })
    queue('GET', `${PT}/runs/run-collect-1`, { kind: 'json', body: finishedCollectionRun() })
    queue('GET', `${PV}/runs/run-a/preview`, {
      kind: 'json',
      body: readerPreview(CITY_FULHAM, '맨체스터 시티 vs 풀럼'),
    })
    queue('GET', `${PV}/runs/run-a/section-results`, { kind: 'json', body: sectionsPayload('run-a') })
    queue('GET', `${PV}/runs/run-a`, { kind: 'json', body: { summary: { run_id: 'run-a' } } })

    const wrapper = await mountPanel()

    expect(posts()).toEqual([])
    expect(wrapper.get(`[data-testid="ptp-storage-${CITY_FULHAM}"]`).text()).toContain('저장 확인')
    expect(wrapper.get('[data-testid="ptp-collection-run"]').text()).toContain('run-collect-1')
    expect(calls.filter((call) => call.url.endsWith('/runs/run-a/preview')).length).toBe(1)
  })

  it('붙잡힌 이전 요청의 응답이 늦게 도착해도 새 실행의 표시를 덮지 않는다', async () => {
    queueBase()
    let releaseLate: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      releaseLate = resolve
    })
    queueFor('POST', `${PV}/bundle-runs`, CITY_FULHAM, {
      kind: 'held',
      gate,
      then: { kind: 'json', status: 500, body: { detail: '늦은 응답' } },
    })
    queueGeneratedRun(CITY_FULHAM, 'run-new', '맨체스터 시티 vs 풀럼')

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain('생성 중')

    // 붙잡힌 요청이 끝나기 전에 사용자가 새 실행으로 다시 생성한다(순번이 바뀐다).
    await wrapper.get(`[data-testid="ptp-retry-new-${CITY_FULHAM}"]`).trigger('click')
    await flushPromises()
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain(
      '생성 응답 성공',
    )

    // 이제서야 이전 요청의 실패 응답이 도착한다. 새 실행의 성공 표시를 덮으면 안 된다.
    releaseLate()
    await flushPromises()
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain(
      '생성 응답 성공',
    )
    expect(wrapper.get(`[data-testid="ptp-generation-detail-${CITY_FULHAM}"]`).text()).toContain(
      'run-new',
    )
  })
})

describe('기간 수집 시험 — 요청 식별자', () => {
  it('응답을 못 받은 요청의 재전송은 같은 request_id를 쓰고, 새 실행은 새 값을 쓴다', async () => {
    queueBase()
    // 두 번 모두 통신 실패로 두어 재전송 뒤에도 실패 상태가 남는다(새 실행 버튼이 유지된다).
    queueFor('POST', `${PV}/bundle-runs`, CITY_FULHAM, { kind: 'network' }, { kind: 'network' })
    queueGeneratedRun(CITY_FULHAM, 'run-new', '맨체스터 시티 vs 풀럼')
    // 두 번째 경기는 생성하지 않는다(첫 요청 흐름만 본다).
    queueFor('POST', `${PV}/bundle-runs`, CHELSEA_LEEDS, {
      kind: 'json',
      status: 500,
      body: { detail: '두 번째 경기는 이 검사에서 확인하지 않는다' },
    })

    const wrapper = await mountPanel()
    await wrapper.get('[data-testid="ptp-generate"]').trigger('click')
    await flushPromises()

    const cityIds = requestIds().slice(0, 1)
    expect(cityIds.length).toBe(1)
    const firstId = cityIds[0]
    expect(firstId.length).toBeGreaterThan(0)

    // 통신 실패만 "같은 요청 재전송"을 연다. 그 버튼은 같은 식별자를 다시 보낸다.
    await wrapper.get(`[data-testid="ptp-retry-same-${CITY_FULHAM}"]`).trigger('click')
    await flushPromises()
    expect(bundleCalls().length).toBe(3)
    expect(requestIds()[2]).toBe(firstId)

    // 명시적 새 실행은 새 식별자다. 같은 경기라도 서버가 같은 요청으로 오해하지 않는다.
    expect(wrapper.get(`[data-testid="ptp-generation-${CITY_FULHAM}"]`).text()).toContain('실패')
    await wrapper.get(`[data-testid="ptp-retry-new-${CITY_FULHAM}"]`).trigger('click')
    await flushPromises()
    expect(bundleCalls().length).toBe(4)
    expect(requestIds()[3]).not.toBe(firstId)
  })
})

describe('표시 모델 — 저장 불일치 섹션 차단', () => {
  function runData(overrides: Partial<PreviewRunData> = {}): PreviewRunData {
    const base = readerPreview(CITY_FULHAM, '맨체스터 시티 vs 풀럼')
    return {
      run_id: 'run-x',
      preview: {
        ...base,
        sections: [
          ...base.sections,
          {
            section_id: 'section_players',
            title: '주목 선수',
            body: '저장된 선수 본문',
            sources: [],
            quality: 'ready',
            partial: false,
            version: 1,
          },
        ],
      } as never,
      preview_error: null,
      sections: { run_id: 'run-x', section_results: [sectionRow({ run_id: 'run-x' })] },
      sections_error: null,
      detail: null,
      detail_error: null,
      composed_sections: [],
      composed_error: null,
      ...overrides,
    }
  }

  it('불일치 섹션은 정상 문서에서 빠지고 다른 섹션은 부분 문서로 남는다', () => {
    const data = runData({
      sections: {
        run_id: 'run-x',
        section_results: [
          sectionRow({ run_id: 'run-x', storage_status: 'storage_mismatch', storage_mismatch: true }),
          sectionRow({
            run_id: 'run-x',
            section_result_id: 'sr-players',
            workflow_id: 'section_players',
            title: '주목 선수',
            body: '저장된 선수 본문',
            available: true,
            structured: {
              players: [{ player: '엘링 홀란드', reason: '골 결정력', team: '맨체스터 시티' }],
            },
          }),
        ],
      },
    })

    expect(storageMismatchSections(data.sections)).toEqual(['section_ai_forecast'])

    const view = withoutBlockedSections(toMatchPreviewView(data), ['section_ai_forecast'])
    // 불일치 섹션(전망)은 본문도 카드도 남지 않는다.
    expect(view.sections.section_ai_forecast).toBeUndefined()
    expect(view.forecast.forecastLines).toEqual([])
    expect(view.forecast.lean).toBeNull()
    // 정상 섹션은 그대로 남는다.
    expect(view.players.map((row) => row.player)).toEqual(['엘링 홀란드'])
    expect(view.sections.section_players?.body).toBe('저장된 선수 본문')
  })

  it('구계약 행(플래그 없음)에는 차단을 강제하지 않는다', () => {
    const data = runData()
    expect(storageMismatchSections(data.sections)).toEqual([])
    const view = withoutBlockedSections(toMatchPreviewView(data), [])
    expect(view.sections.section_ai_forecast?.body).toBe('저장 본문')
  })
})
