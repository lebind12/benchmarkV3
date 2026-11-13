/**
 * 섹션 재생성·비교·승인 패널 검사 (PS-04).
 *
 * 이 파일이 확인하는 것:
 * - 세 동작(정보 원문 재사용 / 새 수집 / 저장 응답 재처리)을 **누르기 전에** 구분해 보여준다.
 * - 요청은 사용자가 버튼을 눌렀을 때만 나간다(마운트만으로는 아무 요청도 없다).
 * - 저장 응답 재처리는 실제 재생성과 다른 경로이며 모델 0회임을 화면이 알린다.
 * - 승인은 자동으로 만들어지지 않는다. 승인 버튼을 눌러야만 이벤트가 나간다.
 * - 재사용할 묶음이 없으면 재사용 모드를 열지 않는다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const regenerateMock = vi.fn()

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: {
    regenerateSection: (...args: unknown[]) => regenerateMock(...args),
  },
}))

import SectionRegenerationPanel from '@/features/match-preview/SectionRegenerationPanel.vue'
import type { SectionResultView } from '@/features/match-preview/types'

function result(overrides: Partial<SectionResultView> = {}): SectionResultView {
  return {
    section_result_id: 'result-2',
    run_id: 'run-2',
    workflow_id: 'section_players',
    workflow_version: 'section_players@v2',
    version: 2,
    title: '주목 선수',
    body: '선정 선수: 엘링 홀란드\n선정 이유: 최근 득점 흐름이 좋습니다.',
    sources: [{ label: 'Manchester City squad', url: 'https://example.com/squad', kind: 'web' }],
    mode: 'live',
    mode_label: '실호출',
    environment: 'dev',
    quality: 'ready',
    module_execution_ids: [],
    result_ids: ['module-result-2'],
    diagnostics: [],
    unavailable_reason: null,
    unavailable: false,
    output_contract_version: 'section_players-output-1',
    contract_version: 'mp04-section-result-1',
    created_at: '2026-11-11T00:00:00+00:00',
    supersedes_section_result_id: null,
    approvable: true,
    ...overrides,
  }
}

/**
 * 패널을 마운트하고 **부모 리스너**를 함께 붙인다.
 *
 * 이벤트는 `wrapper.emitted()`가 아니라 리스너 호출로 확인한다. 실제 부모 연결
 * (`@regenerated`/`@approved`/`@reprocess`)과 같은 경로를 검사하기 위해서다.
 */
function mountPanel(overrides: Record<string, unknown> = {}) {
  const onRegenerated = vi.fn()
  const onApproved = vi.fn()
  const onReprocess = vi.fn()
  const wrapper = mount(SectionRegenerationPanel, {
    props: {
      workflowId: 'section_players',
      fixtureId: 1557474,
      results: [result({ version: 1, section_result_id: 'result-1' }), result()],
      bundleId: 'bundle-1',
      showApproval: true,
      onRegenerated,
      onApproved,
      onReprocess,
      ...overrides,
    },
  })
  return { wrapper, onRegenerated, onApproved, onReprocess }
}

beforeEach(() => {
  regenerateMock.mockReset()
})

describe('SectionRegenerationPanel', () => {
  it('distinguishes reprocess (no model call) from paid regeneration before any click', () => {
    const { wrapper } = mountPanel()

    const reprocess = wrapper.get('[data-testid="regen-action-reprocess"]').element
      .parentElement as HTMLElement
    expect(reprocess.textContent).toContain('모델 전송 0회')
    const refresh = wrapper.get('[data-testid="regen-action-refresh"]').element
      .parentElement as HTMLElement
    // 다른 섹션은 새 수집 HTTP + 모델 호출을 알린다.
    expect(refresh.textContent).toContain('외부 HTTP 요청과 모델 호출을 새로 발생')

    // 마운트만으로는 아무 요청도 나가지 않는다.
    expect(regenerateMock).not.toHaveBeenCalled()
  })

  it('sends a reuse request with the stored bundle id only when the user clicks', async () => {
    regenerateMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-3',
        workflow_id: 'section_players',
        workflow_version: 'section_players@v3',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: 'result-3',
        section_result_version: 3,
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
        source_mode: 'reuse',
        bundle_id: 'bundle-1',
        bundle_reused: true,
      },
    })
    const { wrapper, onRegenerated } = mountPanel()

    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    expect(regenerateMock).toHaveBeenCalledTimes(1)
    const payload = regenerateMock.mock.calls[0][0]
    expect(payload.workflow_id).toBe('section_players')
    expect(payload.fixture_id).toBe(1557474)
    expect(payload.source_mode).toBe('reuse')
    expect(payload.bundle_id).toBe('bundle-1')
    // 실제 생성 의도이므로 mode를 명시한다. 생략하면 서버 기본값(mock)으로 떨어져
    // 눌린 동작(재생성)이 실행되지 않고 모의 본문이 저장된다.
    expect(payload.mode).toBe('live')
    expect(payload.base_result_id).toBe('result-2')
    // 서버가 bundle_reused=true로 확인했을 때만 재사용이라고 쓴다.
    expect(wrapper.get('[data-testid="regen-done"]').text()).toContain('재사용')
    expect(onRegenerated).toHaveBeenCalledTimes(1)
    expect((onRegenerated.mock.calls[0][0] as { run_id: string }).run_id).toBe('run-3')
  })

  it('keeps the other sections\' current versions in selected_result_ids and drops its own', async () => {
    regenerateMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-keep',
        workflow_id: 'section_odds',
        workflow_version: 'section_odds@v2',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: 'result-keep',
        section_result_version: 2,
        external_calls: 0,
        budget: {},
        unavailable_reason: null,
        note: '',
        no_model_call: true,
      },
    })
    const { wrapper } = mountPanel({
      workflowId: 'section_odds',
      selectedResultIds: ['players-result', 'forecast-result', 'odds-old'],
      results: [result({ section_result_id: 'odds-old', workflow_id: 'section_odds' })],
    })

    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    const payload = regenerateMock.mock.calls[0][0]
    // 다른 섹션의 현재 표시 버전은 새 run 구성본에 그대로 남는다.
    expect(payload.selected_result_ids).toEqual(['players-result', 'forecast-result'])
    // 다시 만드는 섹션은 자기 결과를 선택 목록에 넣지 않는다(중복 섹션 거부 회피).
    expect(payload.selected_result_ids).not.toContain('odds-old')
    // 기준 실행·결과·묶음·모드는 함께 보존된다.
    expect(payload.base_run_id).toBe('run-2')
    expect(payload.base_result_id).toBe('odds-old')
    expect(payload.bundle_id).toBe('bundle-1')
    expect(payload.mode).toBe('live')
    expect(payload.source_mode).toBe('reuse')
  })

  it('does not tell the user that the odds section calls a model', () => {
    const { wrapper } = mountPanel({ workflowId: 'section_odds' })
    const reuse = wrapper.get('[data-testid="regen-action-reuse"]').element
      .parentElement as HTMLElement
    const text = (reuse.textContent ?? '').replace(/\s+/g, ' ')
    // 배당 **재사용**은 저장 자료를 다시 쓰고 필요 시 배당 API를 1회 보완하며 모델 0회다.
    expect(text).toContain('저장된 정보 원문을 재사용')
    expect(text).toContain('배당 API를 1회 보완합니다')
    expect(text).toContain('이 재사용 경로는 모델 호출이 0회입니다')
    // 다른 섹션에 쓰는 "모델 호출은 발생합니다" 문구가 배당에는 나오지 않는다.
    expect(text).not.toContain('모델 호출은 발생합니다')
  })

  it('does not claim zero model calls for an odds refresh (research model runs)', () => {
    const { wrapper } = mountPanel({ workflowId: 'section_odds' })
    const refresh = wrapper.get('[data-testid="regen-action-refresh"]').element
      .parentElement as HTMLElement
    const text = (refresh.textContent ?? '').replace(/\s+/g, ' ')
    // 배당 본문 작성만 모델을 쓰지 않는다. 새 수집은 조사 모델과 외부 API 조회가 발생한다.
    expect(text).toContain('자료 검색 모델 호출')
    expect(text).toContain('외부 API 조회')
    expect(text).not.toContain('모델을 부르지 않습니다(모델 0회)')
    expect(text).not.toContain('모델 호출이 0회')
  })

  it('shows zero model calls for an odds reuse only because the response says so', async () => {
    regenerateMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-odds-reuse',
        workflow_id: 'section_odds',
        workflow_version: 'section_odds@v2',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: 'odds-new',
        section_result_version: 2,
        // reuse 응답: 모델 전송 0회.
        external_calls: 0,
        budget: {},
        unavailable_reason: null,
        note: '',
        source_mode: 'reuse',
        bundle_reused: true,
        no_model_call: true,
      },
    })
    const { wrapper } = mountPanel({
      workflowId: 'section_odds',
      results: [result({ section_result_id: 'odds-old', workflow_id: 'section_odds' })],
    })

    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    const done = wrapper.get('[data-testid="regen-done"]').text().replace(/\s+/g, ' ')
    expect(done).toContain('모델 호출 없이 처리됐습니다')
    expect(done).toContain('모델 전송 0회')
  })

  it('follows the odds refresh response instead of assuming zero model calls', async () => {
    regenerateMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-odds-refresh',
        workflow_id: 'section_odds',
        workflow_version: 'section_odds@v3',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: 'odds-new',
        section_result_version: 3,
        // refresh 응답: 조사 모델 1회. `external_calls`는 budget.model_used(모델 전송 수)다.
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '',
        source_mode: 'refresh',
        bundle_reused: false,
        no_model_call: false,
      },
    })
    const { wrapper } = mountPanel({
      workflowId: 'section_odds',
      results: [result({ section_result_id: 'odds-old', workflow_id: 'section_odds' })],
    })

    await wrapper.get('[data-testid="regen-action-refresh"]').setValue()
    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    const done = wrapper.get('[data-testid="regen-done"]').text().replace(/\s+/g, ' ')
    // 응답이 모델 전송 1회라고 했으므로 모델 0회를 표시하지 않는다.
    expect(done).not.toContain('모델 호출 없이')
    expect(done).toContain('모델 전송 1회')
  })

  it('marks the refresh request as new collection', async () => {
    regenerateMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-4',
        workflow_id: 'section_players',
        workflow_version: 'section_players@v4',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: 'result-4',
        section_result_version: 4,
        external_calls: 2,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
      },
    })
    const { wrapper } = mountPanel()

    await wrapper.get('[data-testid="regen-action-refresh"]').setValue()
    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    const payload = regenerateMock.mock.calls[0][0]
    expect(payload.source_mode).toBe('refresh')
    // 새 수집 재생성도 실제 생성이다. mode를 빼면 서버가 mock으로 처리해 모의 본문을 저장한다.
    expect(payload.mode).toBe('live')
    expect(payload.bundle_id).toBeUndefined()
    expect(wrapper.get('[data-testid="regen-done"]').text()).toContain('새 수집')
  })

  it('routes stored-response reprocessing to the no-call path, not the paid one', async () => {
    const { wrapper, onReprocess } = mountPanel()

    await wrapper.get('[data-testid="regen-action-reprocess"]').setValue()
    await wrapper.get('[data-testid="regen-run"]').trigger('click')
    await flushPromises()

    // 저장 응답 재처리는 재생성 API를 부르지 않는다.
    expect(regenerateMock).not.toHaveBeenCalled()
    expect(onReprocess).toHaveBeenCalledTimes(1)
    // 재처리 경로는 모듈 결과 ID를 쓴다(섹션 결과 ID가 아니다).
    expect((onReprocess.mock.calls[0][0] as { resultId: string }).resultId).toBe('module-result-2')
  })

  it('blocks reuse when the run has no stored bundle', () => {
    const { wrapper } = mountPanel({ bundleId: null })

    // 조회 실패와 "묶음 없음"을 화면이 단정하지 않는다(부모가 구체 사유를 보인다).
    expect(wrapper.get('[data-testid="regen-reuse-blocked"]').text()).toContain(
      '재사용할 정보 원문 묶음을 확인하지 못했습니다',
    )
    const runButton = wrapper.get('[data-testid="regen-run"]')
    expect((runButton.element as HTMLButtonElement).disabled).toBe(true)
    expect(regenerateMock).not.toHaveBeenCalled()
  })

  it('never creates an approval by itself and only emits on the user click', async () => {
    const { wrapper, onApproved } = mountPanel()

    // 승인 요청은 마운트 시점에 없다.
    expect(onApproved).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="regen-approve"]').trigger('click')
    expect(onApproved).toHaveBeenCalledTimes(1)
    expect((onApproved.mock.calls[0][0] as { sectionResultId: string }).sectionResultId).toBe(
      'result-2',
    )
  })

  it('does not open the approval button for a non-approvable result', () => {
    const { wrapper } = mountPanel({
      results: [result({ approvable: false, mode: 'mock', mode_label: '모의 시연' })],
    })

    expect(wrapper.find('[data-testid="regen-approve"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="regen-approval-blocked"]').text()).toContain(
      '승인 근거로 쓸 수 없습니다',
    )
  })

  it('shows the previous version next to the selected one when two versions exist', () => {
    const { wrapper } = mountPanel()

    expect(wrapper.get('[data-testid="regen-compare-base"]').text()).toContain('이전 v1')
    expect(wrapper.get('[data-testid="regen-compare-target"]').text()).toContain('선택 v2')
  })
})
