/**
 * 지표 → 실행 검사 연결 (MP-04 공유 라우터 소유).
 *
 * 이 파일이 확인하는 것:
 * - 지표 화면이 넘긴 실행 ID로 실행 목록 화면을 그 실행과 함께 연다.
 * - 지표 화면이 내보내지 않은 필터를 임의로 붙이지 않는다(없는 값을 만들지 않는다).
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

const MetricsStub = {
  name: 'PreviewMetricsViewStub',
  emits: ['select-run'],
  template: '<button data-testid="stub-select-run" @click="$emit(\'select-run\', RUN_ID)">열기</button>',
  setup() {
    return { RUN_ID: '99999999-9999-4999-8999-999999999999' }
  },
}

vi.mock('@/features/match-preview/PreviewMetricsView.vue', () => ({
  default: MetricsStub,
}))

async function mountRoute() {
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
  const wrapper = mount(AdminMetricsRoute, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('AdminMetricsRoute', () => {
  it('opens the selected run in the run inspector route', async () => {
    const { wrapper, router } = await mountRoute()
    await wrapper.get('[data-testid="stub-select-run"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(router.currentRoute.value.query.run).toBe(
      '99999999-9999-4999-8999-999999999999',
    )
    // 지표 화면이 내보내지 않은 필터를 지어내지 않는다.
    expect(Object.keys(router.currentRoute.value.query)).toEqual(['run'])
  })
})
