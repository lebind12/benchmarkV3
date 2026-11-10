/**
 * 지표 → 실행 검사 연결 (MP-04 공유 라우터 소유).
 *
 * 이 파일이 확인하는 것:
 * - 지표 화면이 넘긴 실행 ID로 실행 목록 화면을 그 실행과 함께 연다.
 * - 지표 화면이 넘긴 **조회 필터**를 같은 질의로 보존해, 실행을 본 뒤 같은 조건으로
 *   지표 화면에 돌아올 수 있게 한다(대표 회귀 1건).
 * - 지표 화면이 내보내지 않은 필터는 임의로 붙이지 않는다(없는 값을 만들지 않는다).
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { emptyMetricsFilterContext } from '@/features/match-preview/metrics'

const RUN_ID = '99999999-9999-4999-8999-999999999999'

const stubEvents: { runId: string; filters: unknown }[] = []

const MetricsStub = {
  name: 'PreviewMetricsViewStub',
  emits: ['select-run'],
  template: '<button data-testid="stub-select-run" @click="emitSelect">열기</button>',
  setup() {
    function emitSelect() {
      const payload = stubEvents.shift()
      if (payload) {
        ;(window as unknown as { __emitSelectRun: (p: unknown) => void }).__emitSelectRun(payload)
      }
    }
    return { emitSelect }
  },
}

vi.mock('@/features/match-preview/PreviewMetricsView.vue', () => ({
  default: MetricsStub,
}))

async function mountRoute(payload?: { runId: string; filters: unknown }) {
  if (payload) stubEvents.push(payload)
  const { default: AdminMetricsRoute } = await import(
    '@/features/match-preview/AdminMetricsRoute.vue'
  )
  const RunsStub = { template: '<div data-testid="runs-stub">runs</div>' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/metrics', name: 'preview-metrics', component: AdminMetricsRoute },
      { path: '/admin/runs', name: 'preview-runs', component: RunsStub },
    ],
  })
  await router.push('/admin/metrics')
  const wrapper = mount(AdminMetricsRoute, {
    global: { plugins: [router] },
    attachTo: document.body,
  })
  ;(window as unknown as { __emitSelectRun: (p: unknown) => void }).__emitSelectRun = (
    emitted: unknown,
  ) => {
    wrapper.findComponent(MetricsStub).vm.$emit('select-run', emitted)
  }
  await flushPromises()
  return { wrapper, router }
}

describe('AdminMetricsRoute', () => {
  it('keeps the effective metric filters when opening a run and returning', async () => {
    const { wrapper, router } = await mountRoute({
      runId: RUN_ID,
      filters: {
        environments: ['dev'],
        modes: ['mock'],
        moduleIds: ['R1', 'R2'],
        models: [],
        contractVersions: [],
        fromAt: '2026-11-09T00:00:00.000Z',
        toAt: '2026-11-10T00:00:00.000Z',
      },
    })
    await wrapper.get('[data-testid="stub-select-run"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('preview-runs')
    const query = router.currentRoute.value.query
    expect(query.run).toBe(RUN_ID)
    expect(query.from).toBe('metrics')
    // 같은 조건이 실행 화면의 질의에 그대로 남는다(값을 잃거나 지어내지 않는다).
    expect(query.environment).toBe('dev')
    expect(query.mode).toBe('mock')
    expect(query.module_id).toEqual(['R1', 'R2'])
    expect(query.from_at).toBe('2026-11-09T00:00:00.000Z')
    expect(query.to_at).toBe('2026-11-10T00:00:00.000Z')
    expect(query.model).toBeUndefined()
    expect(query.contract_version).toBeUndefined()
  })

  it('does not invent metric filters the metrics view did not send', async () => {
    const { wrapper, router } = await mountRoute({
      runId: RUN_ID,
      filters: emptyMetricsFilterContext(),
    })
    await wrapper.get('[data-testid="stub-select-run"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('preview-runs')
    // 필터가 비어 있으면 실행 ID와 출처만 남는다(기본 조회를 조건으로 꾸미지 않는다).
    expect(Object.keys(router.currentRoute.value.query).sort()).toEqual(['from', 'run'])
  })
})
