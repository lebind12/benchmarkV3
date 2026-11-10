/**
 * 실행 검사 화면 (MP-02).
 *
 * 이 파일이 확인하는 것:
 * - 저장된 실행의 네 탭(요청·원문 응답·정규화 변환·다음 입력)이 실제 값으로 보인다.
 * - 모의 실행이 실호출로 오인되지 않도록 실행 방식을 화면에 표시한다.
 * - 결과 버전 비교에서 이전 버전을 함께 보여주고, 입력이 다르면 그 사실을 알린다.
 * - 만료된 원문은 "만료"로 표시하고 읽기 실패로 꾸미지 않는다.
 * - 검사 화면은 조회만 한다(생성·취소를 스스로 호출하지 않는다).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunInspector from '@/features/match-preview/RunInspector.vue'

const RUN_ID = '11111111-1111-4111-8111-111111111111'
const MODULE_ID = '22222222-2222-4222-8222-222222222222'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function artifact(overrides: Record<string, unknown> = {}) {
  return {
    artifact_id: 'art-1',
    kind: 'raw_response',
    media_type: 'application/json',
    byte_size: 120,
    sha256: 'a'.repeat(64),
    redacted: true,
    created_at: '2026-11-10T09:00:00+00:00',
    expires_at: '2026-12-10T09:00:00+00:00',
    expired_at: null,
    available: true,
    status: 'available',
    summary: { kind: 'raw_response' },
    body: '{"marker":"recorded_mock_response"}',
    detail: null,
    ...overrides,
  }
}

function detailPayload(overrides: Record<string, unknown> = {}) {
  return {
    summary: {
      run_id: RUN_ID,
      operation_kind: 'mock_demo',
      environment: 'dev',
      mode: 'mock',
      status: 'succeeded',
      quality: 'pending',
      fixture_label: '시연 경기',
      requested_at: '2026-11-10T09:00:00+00:00',
      finished_at: '2026-11-10T09:00:05+00:00',
      module_count: 1,
      attempt_count: 1,
      retry_count: 0,
      failure_code: null,
      label: '기록 시연 (mock, 외부 호출 없음)',
      cancelled_at: null,
    },
    actor_id: '1',
    config_version: 'mp02-demo/mp02-1',
    limits: { model_requests: 0, api_requests: 0 },
    fixture: null,
    modules: [],
    results: [],
    sources: [],
    attempts: [],
    artifacts: [artifact()],
    contract_versions: {
      contract: 'mp02-1',
      provider: 'mp02-provider-1',
      module_input: 'mp02-module-input-1',
      preview_document: 'mp02-preview-1',
      inspector: 'mp02-inspector-1',
    },
    inspector_version: 'mp02-inspector-1',
    mode_detail: {
      mode: 'mock',
      label: '모의 실행 (mock, 외부 호출 없음)',
      note: '외부 모델·API를 호출하지 않은 시연 실행입니다.',
    },
    inspector_modules: [
      {
        inspector_version: 'mp02-inspector-1',
        module_execution_id: MODULE_ID,
        module_id: 'mock_demo',
        panel: {
          panel: 'generic',
          registered: true,
          display_name: '기록 시연 (모의)',
          mode_scope: ['mock'],
          available: true,
          unrunnable_reason: null,
        },
        run_mode: {
          mode: 'mock',
          label: '모의 실행 (mock, 외부 호출 없음)',
          note: '외부 모델·API를 호출하지 않은 시연 실행입니다.',
        },
        status: 'succeeded',
        quality: 'pending',
        attempt_count: 1,
        retry_count: 0,
        result_versions: [1, 2],
        started_at: '2026-11-10T09:00:00+00:00',
        finished_at: '2026-11-10T09:00:05+00:00',
        tabs_meta: [
          { id: 'request', label: '요청', description: '' },
          { id: 'response', label: '원문 응답', description: '' },
          { id: 'transform', label: '정규화 변환', description: '' },
          { id: 'next_input', label: '다음 입력', description: '' },
        ],
        tabs: {
          request: {
            available: true,
            input: { input_hash: 'abc' },
            attempts: [
              {
                attempt_id: 'att-1',
                logical_call_id: 'mock_demo-call-1',
                attempt_ordinal: 0,
                provider: 'recorded-fixture',
                model: 'mock-demo-model',
                mode: 'mock',
                outcome: 'ok',
                http_status: 200,
                error_class: null,
                error_message: null,
                usage: { input_tokens: 412, output_tokens: 188, search_queries: null },
                wait_ms: 0,
                started_at: '2026-11-10T09:00:00+00:00',
                finished_at: '2026-11-10T09:00:05+00:00',
                request_spec: {
                  logical_call_id: 'mock_demo-call-1',
                  provider: 'recorded-fixture',
                  model: 'mock-demo-model',
                  operation: 'execute_module',
                  module_id: 'mock_demo',
                  endpoint: 'recorded://mock-demo',
                  parameters: { temperature: 0.2 },
                  prompt_version: 'mock-demo-1',
                  contract_version: 'mp02-1',
                  timeout_seconds: null,
                  secret_refs: ['provider_api_key'],
                },
                request_body: artifact({
                  kind: 'raw_request',
                  body: '{"headers":{"authorization":"[REDACTED]"}}',
                }),
                response_body: artifact(),
              },
            ],
            note: null,
          },
          response: {
            available: true,
            attempts: [
              {
                attempt_id: 'att-1',
                logical_call_id: 'mock_demo-call-1',
                attempt_ordinal: 0,
                outcome: 'ok',
                http_status: 200,
                error_class: null,
                error_message: null,
                usage: { input_tokens: 412, output_tokens: 188, search_queries: null },
                content: artifact(),
              },
            ],
            note: null,
          },
          transform: {
            available: true,
            result_id: 'res-2',
            version: 2,
            status: 'succeeded',
            quality: 'pending',
            failure_code: null,
            claims: [
              {
                claim_id: 'claim-form-1',
                kind: 'fact',
                text: '홈팀은 최근 5경기 2승 2무 1패입니다.',
                decision: 'adopted',
                decision_reason: '원문에 그대로 있습니다.',
                snapshot_ids: [],
              },
              {
                claim_id: 'claim-odds-1',
                kind: 'external_forecast',
                text: '배당 자료 없음',
                decision: 'excluded',
                decision_reason: '자료가 없어 값을 만들지 않았습니다.',
                snapshot_ids: [],
              },
            ],
            coverage: [
              { topic: 'odds', state: 'not_run', detail: '배당 단계를 실행하지 않았습니다.' },
            ],
            diagnostics: ['모의 실행입니다. 외부 호출이 없습니다.'],
            contract_version: 'mp02-1',
            prompt_version: 'mock-demo-1',
            implementation_version: 'mp02-recorded-demo-2',
            input_hash: 'b'.repeat(64),
            artifacts: [],
            note: null,
          },
          next_input: {
            available: true,
            target_module_id: null,
            selected_result_ids: ['res-2'],
            uses_latest_version: true,
            latest_result_id: 'res-2',
            latest_result_version: 2,
            values: [{ key: 'adopted_claim_ids', value: ['claim-form-1'] }],
            note: null,
          },
        },
        result_versions_retained: true,
      },
    ],
    registry: {
      registry_version: 'mp02-registry-1',
      contract_version: 'mp02-1',
      inspector_version: 'mp02-inspector-1',
      modules: [],
      implemented: ['mock_demo'],
      unavailable: ['D0', 'R1', 'R2', 'R3', 'S1'],
    },
    approvals: {
      contract_version: 'mp02-approval-1',
      workflows: {},
      approved: [],
      unapproved: ['section_form'],
      scope_note: '승인 단위는 섹션 워크플로우입니다.',
    },
    section_result_id: null,
    section_approvals: [
      {
        workflow_id: 'section_form',
        state: 'none',
        label: '승인 전',
        detail: '아직 승인된 버전이 없습니다.',
        current_version: 'section_form@abc123',
        active_approval: null,
        pinned_approval: null,
        can_approve: true,
      },
    ],
    section_workflows: {
      workflows: [],
      implemented: [],
      unavailable: ['section_form'],
      approval_scope_note: '승인 단위는 섹션 워크플로우입니다.',
    },
    approval_note:
      '승인 단위는 프리뷰 섹션을 만드는 완결된 워크플로우입니다. 내부 노드와 D0 같은 자료 준비 단계에는 따로 승인하지 않으며, 모의 시연 실행은 승인 근거가 아닙니다.',
    mock_demo_module_id: 'mock_demo',
    availability_note: 'D0·R1·R2·R3·S1은 아직 구현되지 않아 실행할 수 없습니다.',
    undo: {
      state: 'cancellable',
      cancelled_at: null,
      cancelled_by_actor_id: null,
      reason: null,
      can_cancel: true,
      blocked_reason: null,
    },
    ...overrides,
  }
}

const COMPARE = {
  module_execution_id: MODULE_ID,
  module_id: 'mock_demo',
  base: {
    result_id: 'res-1',
    module_id: 'mock_demo',
    module_execution_id: MODULE_ID,
    version: 1,
    input_hash: 'c'.repeat(64),
    status: 'succeeded',
    quality: 'pending',
    failure_code: null,
    contract_version: 'mp02-1',
    prompt_version: 'mock-demo-1',
    implementation_version: 'mp02-recorded-demo-1',
    created_at: null,
    supersedes_result_id: null,
    payload: { claims: [{ claim_id: 'claim-form-1', text: '첫 번째 버전 근거' }] },
  },
  target: {
    result_id: 'res-2',
    module_id: 'mock_demo',
    module_execution_id: MODULE_ID,
    version: 2,
    input_hash: 'b'.repeat(64),
    status: 'succeeded',
    quality: 'pending',
    failure_code: null,
    contract_version: 'mp02-1',
    prompt_version: 'mock-demo-1',
    implementation_version: 'mp02-recorded-demo-2',
    created_at: null,
    supersedes_result_id: 'res-1',
    payload: { claims: [{ claim_id: 'claim-form-1', text: '두 번째 버전 근거' }] },
  },
  diff: {
    status: { from: 'succeeded', to: 'succeeded' },
    quality: { from: 'pending', to: 'pending' },
    input_hash: { from: 'c'.repeat(64), to: 'b'.repeat(64), changed: true },
    contract_version: { from: 'mp02-1', to: 'mp02-1' },
    prompt_version: { from: 'mock-demo-1', to: 'mock-demo-1' },
    claims_added: ['claim-context-2'],
    claims_removed: [],
    claims_changed: [],
    coverage_changes: {},
    payload_keys_changed: ['claims'],
  },
  versions_available: [1, 2],
}

function mountInspector() {
  return mount(RunInspector, {
    props: { runId: RUN_ID },
    attachTo: document.body,
  })
}

describe('RunInspector', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  function routeFetch(detail = detailPayload(), compare = COMPARE) {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/versions')) return Promise.resolve(json(compare))
      if (url.endsWith(`/runs/${RUN_ID}`)) return Promise.resolve(json(detail))
      return Promise.resolve(json({ detail: 'not found' }, 404))
    })
  }

  it('labels a mock run so it cannot be read as a live success', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    const banner = wrapper.get('[data-testid="mode-banner"]')
    expect(banner.text()).toContain('모의 실행 (mock, 외부 호출 없음)')
    expect(banner.text()).toContain('외부 모델·API를 호출하지 않은 시연 실행')
    expect(banner.text()).toContain('환경 dev')
    expect(wrapper.get('[data-testid="availability-note"]').text()).toContain(
      '아직 구현되지 않아 실행할 수 없습니다',
    )
  })

  it('shows the request tab with the redacted request body', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    expect(wrapper.get('[data-testid="panel-request"]').text()).toContain('recorded-fixture')
    expect(wrapper.get('[data-testid="request-body"]').text()).toContain('[REDACTED]')
    expect(wrapper.get('[data-testid="request-body"]').text()).not.toContain('Bearer ')
  })

  it('shows the raw response and reported usage', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    await wrapper.get('[data-testid="tab-response"]').trigger('click')
    const panel = wrapper.get('[data-testid="panel-response"]')
    expect(panel.text()).toContain('recorded_mock_response')
    expect(wrapper.get('[data-testid="response-outcome"]').text()).toBe('ok')
    expect(wrapper.get('[data-testid="response-usage"]').text()).toContain('input_tokens=412')
  })

  it('marks an expired raw body as expired rather than as a read failure', async () => {
    const detail = detailPayload()
    const module = detail.inspector_modules[0] as Record<string, any>
    module.tabs.response.attempts[0].content = artifact({
      status: 'expired',
      available: false,
      body: null,
      expired_at: '2026-12-11T09:00:00+00:00',
      detail: '보관 기간이 지나 원문을 열 수 없습니다. 요약과 해시는 남아 있습니다.',
    })
    routeFetch(detail)
    const wrapper = mountInspector()
    await flushPromises()

    await wrapper.get('[data-testid="tab-response"]').trigger('click')
    expect(wrapper.get('[data-testid="response-expired"]').text()).toContain('보관 기간이 지나')
  })

  it('shows the normalized transform with adopted and excluded claims', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    await wrapper.get('[data-testid="tab-transform"]').trigger('click')
    expect(wrapper.get('[data-testid="transform-version"]').text()).toBe('v2')
    const claims = wrapper.get('[data-testid="transform-claims"]').text()
    expect(claims).toContain('홈팀은 최근 5경기 2승 2무 1패입니다.')
    expect(claims).toContain('excluded')
    expect(wrapper.get('[data-testid="transform-coverage"]').text()).toContain('not_run')
    expect(wrapper.get('[data-testid="transform-diagnostics"]').text()).toContain('모의 실행')
  })

  it('shows the delivered next input with the exact version reference', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    await wrapper.get('[data-testid="tab-next_input"]').trigger('click')
    const panel = wrapper.get('[data-testid="panel-next-input"]')
    expect(panel.text()).toContain('adopted_claim_ids')
    expect(wrapper.get('[data-testid="next-input-version"]').text()).toContain('v2')
  })

  it('compares two result versions and warns when the inputs differ', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    const compare = wrapper.get('[data-testid="run-version-compare"]')
    expect(compare.text()).toContain('이전 결과 v1')
    expect(compare.text()).toContain('현재 결과 v2')
    expect(wrapper.get('[data-testid="claims-added"]').text()).toContain('claim-context-2')
    expect(wrapper.get('[data-testid="compare-input-changed"]').text()).toContain(
      '같은 입력의 수정 전후 비교가 아닙니다',
    )
  })

  it('shows section approval state and refuses approval without section evidence', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()

    const panel = wrapper.get('[data-testid="inspector-approval"]')
    expect(wrapper.get('[data-testid="section-approvals"]').text()).toContain('section_form')
    expect(panel.text()).toContain('승인 전')
    // 승인 단위가 섹션임을 화면이 밝히고, 근거가 없다는 사실도 숨기지 않는다.
    expect(panel.text()).toContain('섹션')
    expect(wrapper.get('[data-testid="approval-no-evidence"]').text()).toContain(
      '승인 근거로 쓸 섹션 결과가 아직 없습니다',
    )

    // 섹션을 고르고 승인을 눌러도 근거가 없으므로 요청을 보내지 않는다.
    await wrapper.get('[data-testid="approve-section-section_form"]').trigger('click')
    await wrapper.get('[data-testid="approval-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="approval-error"]').text()).toContain('섹션 결과가 없습니다')
    const postCalls = fetchMock.mock.calls.filter(
      ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
    )
    expect(postCalls).toHaveLength(0)
  })

  it('shows the server rejection when a section approval is refused', async () => {
    routeFetch()
    const detail = detailPayload()
    // 섹션 결과가 저장된 상황을 가정해 서버 거부 경로를 확인한다.
    ;(detail as Record<string, unknown>).section_result_id =
      '33333333-3333-4333-8333-333333333333'
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/approvals') && (init?.method ?? 'GET') === 'POST') {
        return Promise.resolve(
          json({ detail: '섹션 결과 기록이 아직 없습니다.' }, 422),
        )
      }
      if (url.includes('/versions')) return Promise.resolve(json(COMPARE))
      if (url.endsWith(`/runs/${RUN_ID}`)) return Promise.resolve(json(detail))
      return Promise.resolve(json({ detail: 'not found' }, 404))
    })

    const wrapper = mountInspector()
    await flushPromises()
    await wrapper.get('[data-testid="approve-section-section_form"]').trigger('click')
    await wrapper.get('[data-testid="approval-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="approval-error"]').text()).toContain(
      '요청을 처리하지 못했습니다',
    )
  })

  it('requests only stored data and never triggers a run', async () => {
    routeFetch()
    const wrapper = mountInspector()
    await flushPromises()
    await wrapper.get('[data-testid="tab-transform"]').trigger('click')
    await flushPromises()

    for (const [input, init] of fetchMock.mock.calls) {
      const url = String(input)
      const method = (init as RequestInit | undefined)?.method ?? 'GET'
      expect(url).toContain('/api/v1/admin/preview/')
      expect(method).toBe('GET')
    }
  })
})
