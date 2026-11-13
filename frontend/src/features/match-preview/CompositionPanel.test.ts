/**
 * 구성본 패널 — 마지막 AI 실행 요청 검사 (B-1 수정 확인).
 *
 * 확인하는 것은 하나다. "이 구성본으로 마지막 AI 실행"은 **실제 생성 의도**이므로 요청에
 * `mode: 'live'`를 명시해야 한다. 생략하면 서버 기본값(`mock`)으로 떨어져 reuse 경로가
 * 422로 거절된다(기능이 동작하지 않는다).
 *
 * 저장(POST /composition)은 모델·외부 호출을 쓰지 않으며, 두 요청 모두 사용자가 버튼을
 * 눌렀을 때만 나간다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const saveMock = vi.fn()
const regenerateMock = vi.fn()

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: {
    saveComposition: (...args: unknown[]) => saveMock(...args),
    regenerateSection: (...args: unknown[]) => regenerateMock(...args),
  },
}))

import CompositionPanel from '@/features/match-preview/CompositionPanel.vue'
import type { SectionResultView } from '@/features/match-preview/types'

function result(overrides: Partial<SectionResultView> = {}): SectionResultView {
  return {
    section_result_id: 'sr-players',
    run_id: 'run-base',
    workflow_id: 'section_players',
    workflow_version: 'section_players@v1',
    version: 1,
    title: '주목 선수',
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
    approvable: true,
    ...overrides,
  }
}

function mountPanel() {
  return mount(CompositionPanel, {
    props: {
      runId: 'run-base',
      results: [result()],
      fixtureId: 1557474,
    },
  })
}

beforeEach(() => {
  saveMock.mockReset()
  regenerateMock.mockReset()
  saveMock.mockResolvedValue({
    ok: true,
    data: {
      composition_id: 'composition-1',
      fixture_id: 1557474,
      items: [],
      refused: [],
      diagnostics: [],
      section_result_ids: ['sr-players'],
    },
  })
  regenerateMock.mockResolvedValue({
    ok: true,
    data: {
      run_id: 'run-final',
      workflow_id: 'section_ai_forecast',
      workflow_version: 'section_ai_forecast@v1',
      mode: 'live',
      status: 'succeeded',
      quality: 'ready',
      section_result_id: 'sr-final',
      section_result_version: 1,
      external_calls: 1,
      budget: {},
      unavailable_reason: null,
      note: '',
    },
  })
})

describe('CompositionPanel — 마지막 AI 실행 요청', () => {
  it('마운트만으로는 저장·실행 요청을 보내지 않는다', () => {
    mountPanel()

    expect(saveMock).not.toHaveBeenCalled()
    expect(regenerateMock).not.toHaveBeenCalled()
  })

  it('저장된 구성본으로 실행할 때 mode를 live로 명시한다', async () => {
    const wrapper = mountPanel()

    await wrapper.get('[data-testid="composition-save"]').trigger('click')
    await flushPromises()
    expect(saveMock).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="composition-run-final"]').trigger('click')
    await flushPromises()

    expect(regenerateMock).toHaveBeenCalledTimes(1)
    const payload = regenerateMock.mock.calls[0][0] as Record<string, unknown>
    expect(payload.workflow_id).toBe('section_ai_forecast')
    expect(payload.source_mode).toBe('reuse')
    expect(payload.composition_id).toBe('composition-1')
    expect(payload.base_run_id).toBe('run-base')
    // 생략하면 서버 기본값(mock)으로 떨어져 reuse 경로가 422로 거절된다.
    expect(payload.mode).toBe('live')
  })
})
