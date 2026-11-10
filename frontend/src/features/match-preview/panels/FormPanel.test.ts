/**
 * R1 경기력·주목 선수 패널 검사 (MP-05).
 *
 * 이 파일이 확인하는 것:
 * - 확인된 사실과 AI 해석을 별도 영역으로 나눠 보여준다.
 * - 제외된 항목과 사유를 지우지 않고 그대로 보여준다(관리자 진단).
 * - 검색 출처가 없으면 "없다"고 표시하고, 미확보 사실을 독자용 본문처럼 꾸미지 않는다.
 * - 모의 실행이면 그 사실을 먼저 알린다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FormPanel from '@/features/match-preview/panels/FormPanel.vue'
import type { ModuleInspection, SectionResultView } from '@/features/match-preview/types'

function inspection(overrides: Partial<ModuleInspection> = {}): ModuleInspection {
  const base = {
    inspector_version: 'mp02-inspector-1',
    module_execution_id: '11111111-1111-4111-8111-111111111111',
    module_id: 'R1',
    panel: {
      panel: 'form',
      registered: true,
      display_name: '경기력·주목 선수 조사',
      description: '',
      mode_scope: ['live', 'replay'],
      available: true,
      unrunnable_reason: null,
      expected_model_calls: 1,
      prompt_version: 'mp05-form-prompt-1',
      contract_version: 'mp02-module-input-1',
    },
    run_mode: {
      mode: 'live',
      label: '실호출',
      note: '실제 제공자 호출로 만든 결과입니다.',
    },
    status: 'succeeded',
    quality: 'ready',
    attempt_count: 1,
    retry_count: 0,
    result_versions: [1],
    started_at: null,
    finished_at: null,
    tabs_meta: [],
    tabs: {
      request: { available: true, input: null, attempts: [], note: null },
      response: { available: true, attempts: [], note: null },
      transform: {
        available: true,
        result_id: '22222222-2222-4222-8222-222222222222',
        version: 1,
        status: 'succeeded',
        quality: 'ready',
        failure_code: null,
        claims: [
          {
            claim_id: 'r1-form-0',
            kind: 'fact',
            text: 'Manchester City는 10경기 7승 3패, 승점 21로 리그 3위입니다.',
            decision: 'adopted',
            decision_reason: null,
            snapshot_ids: ['99999999-9999-4999-8999-999999999999'],
          },
          {
            claim_id: 'r1-watch-0',
            kind: 'ai_interpretation',
            text: '측면 전개 속도가 경기 리듬을 정합니다.',
            decision: 'adopted',
            decision_reason: null,
            snapshot_ids: [],
          },
          {
            claim_id: 'r1-player-1',
            kind: 'ai_interpretation',
            text: 'Erling Haaland: 리그 최고의 스트라이커입니다.',
            decision: 'excluded',
            decision_reason: '단정 표현에 대한 근거가 없어 채택하지 않았습니다.',
            snapshot_ids: [],
          },
        ],
        coverage: [
          {
            topic: '매체·맥락 검색',
            state: 'search_not_found',
            detail: '검색 출처를 확보하지 못했습니다.',
          },
        ],
        diagnostics: ['주목 선수 Erling Haaland: 단정 표현에 대한 근거가 없어 채택하지 않았습니다.'],
        contract_version: 'mp02-1',
        prompt_version: 'mp05-form-prompt-1',
        implementation_version: 'mp05-form-1',
        input_hash: 'abc123',
        artifacts: [],
        note: null,
      },
      next_input: {
        available: false,
        target_module_id: null,
        selected_result_ids: [],
        uses_latest_version: false,
        latest_result_id: null,
        latest_result_version: null,
        values: [],
        note: null,
      },
    },
  } as unknown as ModuleInspection
  return { ...base, ...overrides }
}

function sectionResult(overrides: Partial<SectionResultView> = {}): SectionResultView {
  return {
    section_result_id: '33333333-3333-4333-8333-333333333333',
    run_id: '44444444-4444-4444-8444-444444444444',
    workflow_id: 'section_form',
    workflow_version: 'section_form@abc',
    version: 1,
    title: '경기력과 주목 선수',
    body: '본문',
    sources: [
      {
        label: 'BBC preview',
        url: 'https://www.bbc.com/sport/football/manchester-city-fulham-preview',
        kind: 'search',
        note: 'Google Search grounding 인용 출처',
      },
      {
        label: 'API-Football 저장 자료',
        url: null,
        kind: 'api',
        note: '수집 2026-11-10T09:04:25+00:00',
      },
    ],
    mode: 'live',
    mode_label: '실호출',
    environment: 'dev',
    quality: 'ready',
    module_execution_ids: [],
    result_ids: [],
    diagnostics: [],
    unavailable_reason: null,
    unavailable: false,
    output_contract_version: 'section_form-output-1',
    contract_version: 'mp04-section-result-1',
    created_at: null,
    supersedes_section_result_id: null,
    approvable: true,
    ...overrides,
  }
}

describe('FormPanel', () => {
  it('확인된 사실과 AI 해석을 분리해서 보여준다', () => {
    const wrapper = mount(FormPanel, {
      props: { module: inspection(), sectionResult: sectionResult() },
    })

    const facts = wrapper.get('[data-testid="form-panel-facts"]')
    expect(facts.text()).toContain('Manchester City는 10경기 7승 3패')
    expect(facts.text()).not.toContain('측면 전개 속도')

    const interpretation = wrapper.get('[data-testid="form-panel-interpretation"]')
    expect(interpretation.text()).toContain('측면 전개 속도')
    expect(interpretation.text()).not.toContain('Manchester City는 10경기')

    wrapper.unmount()
  })

  it('제외 항목과 사유를 지우지 않는다', () => {
    const wrapper = mount(FormPanel, {
      props: { module: inspection(), sectionResult: sectionResult() },
    })

    const excluded = wrapper.get('[data-testid="form-panel-excluded"]')
    expect(excluded.text()).toContain('리그 최고의 스트라이커')
    expect(excluded.text()).toContain('단정 표현에 대한 근거가 없어')

    wrapper.unmount()
  })

  it('검색 출처가 없으면 없다고 표시하고 미확보를 본문처럼 꾸미지 않는다', () => {
    const wrapper = mount(FormPanel, {
      props: {
        module: inspection(),
        sectionResult: sectionResult({
          sources: [
            { label: 'API-Football 저장 자료', url: null, kind: 'api', note: null },
          ],
        }),
      },
    })

    expect(wrapper.get('[data-testid="form-panel-no-search-sources"]').text()).toContain(
      '검색 출처가 저장되지 않았습니다',
    )
    expect(wrapper.get('[data-testid="form-panel-search-state"]').text()).toContain(
      'search_not_found',
    )
    // 검색 출처 목록은 비어 있고 API 출처만 남는다.
    expect(wrapper.find('[data-testid="form-panel-search-sources"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="form-panel-api-sources"]').text()).toContain(
      'API-Football 저장 자료',
    )

    wrapper.unmount()
  })

  it('모의 실행이면 승인 근거가 아니라는 사실을 먼저 알린다', () => {
    const wrapper = mount(FormPanel, {
      props: {
        module: inspection({
          run_mode: {
            mode: 'mock',
            label: '모의 시연 (외부 호출 없음)',
            note: '외부 호출 없이 만든 예시입니다.',
          },
        }),
      },
    })

    expect(wrapper.get('[data-testid="form-panel-mock-notice"]').text()).toContain(
      '승인 근거가 아닙니다',
    )
    expect(wrapper.find('[data-testid="form-panel-no-search-sources"]').exists()).toBe(true)

    wrapper.unmount()
  })
})
