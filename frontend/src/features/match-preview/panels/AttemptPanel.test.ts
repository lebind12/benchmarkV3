/**
 * 시도 진단 패널 (MP-04).
 *
 * 이 파일이 확인하는 것:
 * - 429 뒤 성공한 논리 호출에서 **두 시도가 모두** 보인다(성공만 골라 표시하지 않는다).
 * - 재시도 대기 시간이 그대로 표시된다.
 * - 제공자가 사용량을 주지 않았을 때 0이 아니라 "제공되지 않음"으로 표시된다.
 * - 결과 불명확한 시도는 성공처럼 보이지 않는다.
 *
 * 이 패널은 진단이다. 승인은 섹션 워크플로우 결과 단위이며, 여기 시도 단위가 아니다.
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AttemptPanel from '@/features/match-preview/panels/AttemptPanel.vue'
import type { AttemptView } from '@/features/match-preview/types'

function attempt(overrides: Record<string, unknown> = {}): AttemptView {
  return {
    attempt_id: 'att-1',
    logical_call_id: 'section_form/research-1',
    attempt_ordinal: 0,
    provider: 'vertex',
    model: 'gemini-observed-model',
    mode: 'live',
    outcome: 'ok',
    http_status: 200,
    error_class: null,
    error_message: null,
    usage: { input_tokens: 120, output_tokens: 40, search_queries: null },
    wait_ms: 0,
    started_at: '2026-11-10T09:00:00+00:00',
    finished_at: '2026-11-10T09:00:01+00:00',
    request_spec: {
      logical_call_id: 'section_form/research-1',
      provider: 'vertex',
      model: 'gemini-observed-model',
      operation: 'request_model',
      module_id: 'R1',
      endpoint: null,
      parameters: {},
      prompt_version: 'r1-p1',
      contract_version: 'mp02-provider-1',
      timeout_seconds: 300,
      secret_refs: ['google_application_credentials_json'],
    },
    request_body: null,
    response_body: null,
    ...overrides,
  } as AttemptView
}

describe('AttemptPanel', () => {
  it('keeps the failed 429 attempt next to the successful retry', () => {
    const wrapper = mount(AttemptPanel, {
      props: {
        attempts: [
          attempt({
            attempt_id: 'att-0',
            attempt_ordinal: 0,
            outcome: 'error',
            http_status: 429,
            error_class: 'rate_limited',
            error_message: 'quota exceeded',
            usage: null,
            wait_ms: 0,
          }),
          attempt({
            attempt_id: 'att-1',
            attempt_ordinal: 1,
            outcome: 'ok',
            http_status: 200,
            wait_ms: 2000,
          }),
        ],
      },
    })

    // 두 시도가 모두 남는다.
    expect(wrapper.find('[data-testid="attempt-section_form/research-1-0"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="attempt-section_form/research-1-1"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="attempt-summary"]').text()).toContain('시도 2건')
    expect(wrapper.get('[data-testid="attempt-summary"]').text()).toContain('재시도 1건')

    // 실패한 시도의 HTTP 상태와 오류 분류가 보인다.
    const first = wrapper.get('[data-testid="attempt-section_form/research-1-0"]')
    expect(first.text()).toContain('HTTP 429')
    expect(first.get('[data-testid="attempt-error"]').text()).toContain('rate_limited')
    // 제공자가 사용량을 주지 않은 시도는 0이 아니라 unknown으로 표시된다.
    expect(first.get('[data-testid="attempt-usage"]').text()).toContain('제공되지 않음')

    // 재시도 대기가 표시된다.
    const second = wrapper.get('[data-testid="attempt-section_form/research-1-1"]')
    expect(second.get('[data-testid="attempt-wait"]').text()).toContain('2.0초')
  })

  it('marks an unknown outcome as unknown, not as success', () => {
    const wrapper = mount(AttemptPanel, {
      props: {
        attempts: [
          attempt({ outcome: 'unknown', http_status: null, error_class: 'transport_timeout' }),
        ],
      },
    })
    expect(wrapper.get('[data-testid="attempt-outcome"]').text()).toBe('결과 불명확')
    expect(wrapper.get('[data-testid="attempt-summary"]').text()).toContain('결과 불명확 1건')
  })

  it('says there are no attempts instead of implying one succeeded', () => {
    const wrapper = mount(AttemptPanel, { props: { attempts: [] } })
    expect(wrapper.get('[data-testid="attempt-empty"]').text()).toContain('아직')
  })
})
