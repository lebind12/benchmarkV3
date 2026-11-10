/**
 * MP-10 후속: R4 선수 패널 연결과 본문 줄바꿈 보존 검사.
 *
 * 이 파일이 확인하는 두 가지(현재 사용자 요구의 미충족 항목):
 *
 * 1. R4 `PlayersPanel`이 실행 검사 화면에 실제로 마운트되고, 저장 payload의
 *    `selected_player`/`selection_reason`이 **분리된 라벨**로 보인다.
 * 2. R4 본문은 `선정 선수:`/`선정 이유:`를 한 줄 줄바꿈으로 쓰는데, 섹션 실행 화면이
 *    빈 줄(`\n\n`)로만 나누고 줄바꿈을 지우면 화면에서 한 줄로 붙는다. 그래서 문단에
 *    줄바꿈 보존(`white-space: pre-line`)이 적용됐는지 확인한다.
 *
 * 서버·DB·모델을 부르지 않는다. 고정 payload로 화면만 확인하며, 이 결과는 실제
 * R4 live 생성 증거가 아니다(오프라인 예시와 같은 성격).
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { vi as vitestVi } from 'vitest'
import RunInspector from './RunInspector.vue'

vitestVi.mock('@/features/match-preview/RunVersionCompare.vue', () => ({
  default: { name: 'RunVersionCompare', template: '<div data-test="compare-stub" />' },
}))

const RUN_ID = '6e59041a-3767-4756-a412-991008873f50'
const R4_MODULE_ID = '7a1b0000-0000-4000-8000-00000000r4'
const R4_RESULT_ID = '7a1b0000-0000-4000-8000-00000000rs'

const R4_BODY = [
  '이번 경기의 주목 선수 1명입니다.',
  '',
  '선정 선수: 엘링 홀란드',
  '선정 이유: 풀럼의 수비진을 상대로 결정력을 발휘할 가장 유력한 해결사입니다.',
].join('\n')

/** R4 저장 payload(모듈 payload 안쪽). 오프라인 예시와 같은 모양이다. */
function r4Body() {
  return {
    module_id: 'R4',
    output_contract_version: 'mp05p-r4-players-output-1',
    implementation_version: 'mp05p-r4-1',
    prompt_version: 'mp05p-r4-prompt-1',
    mode: 'mock',
    origin: 'reused_r1_selection',
    display_labels: { selected_player: '선정 선수', selection_reason: '선정 이유' },
    players: [
      {
        selected_player: '엘링 홀란드',
        selection_reason:
          '풀럼의 수비진을 상대로 결정력을 발휘할 가장 유력한 해결사입니다.',
        team: '맨체스터 시티',
        model_selected_player: 'Erling Haaland',
        name_source: 'db_korean',
        mapping_status: 'resolved',
        evidence: ['api:standings-13'],
      },
    ],
    unmapped: [],
    mapping: { resolved: 1, unresolved: 0, resolver_injected: true },
    coverage: [],
    diagnostics: [],
    uncertainties: [],
    dropped_facts: [],
    unasserted_premises: [],
    reader_sources: [],
    attempt_count: 1,
    external_calls: 0,
  }
}

function detailPayload() {
  return {
    summary: {
      run_id: RUN_ID,
      operation_kind: 'preview',
      environment: 'dev',
      mode: 'mock',
      mode_label: '모의 (외부 호출 없음)',
      status: 'succeeded',
      quality: 'ready',
      fixture_label: '맨체스터 시티 vs 풀럼',
      requested_at: '2026-11-11T03:00:00+00:00',
      finished_at: '2026-11-11T03:01:00+00:00',
      module_count: 1,
      attempt_count: 1,
      retry_count: 0,
      failure_code: null,
      label: '전체 프리뷰 · 관리자 시험 (승인 근거 아님) · 모의',
      cancelled_at: null,
    },
    availability_note: '진단용 화면입니다.',
    mode_detail: {
      mode: 'mock',
      label: '모의 실행 (mock, 외부 호출 없음)',
      note: '외부 모델·API를 호출하지 않은 시연 실행입니다.',
    },
    inspector_modules: [
      {
        inspector_version: 'mp02-inspector-1',
        module_execution_id: R4_MODULE_ID,
        module_id: 'R4',
        panel: {
          panel: 'players',
          registered: true,
          display_name: '주목 선수 선정',
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
        quality: 'ready',
        attempt_count: 1,
        retry_count: 0,
        tabs: {
          request: { attempts: [], artifacts: [] },
          response: { attempts: [], artifacts: [] },
          transform: { values: [] },
          next_input: { values: [] },
        },
      },
    ],
    results: [
      {
        result_id: R4_RESULT_ID,
        module_id: 'R4',
        module_execution_id: R4_MODULE_ID,
        version: 1,
        status: 'succeeded',
        quality: 'ready',
        input_hash: 'a'.repeat(64),
        contract_version: 'mp02-1',
        prompt_version: 'mp05p-r4-prompt-1',
        implementation_version: 'mp05p-r4-1',
        created_at: '2026-11-11T03:00:30+00:00',
        supersedes_result_id: null,
        payload: { payload: r4Body() },
      },
    ],
    section_results: [
      {
        section_result_id: '7a1b0000-0000-4000-8000-00000000se',
        run_id: RUN_ID,
        workflow_id: 'section_players',
        workflow_version: 'section_players@0f4df25ac59c0476',
        version: 1,
        title: '주목 선수',
        body: R4_BODY,
        sources: [],
        mode: 'mock',
        environment: 'dev',
        quality: 'ready',
        module_execution_ids: [R4_MODULE_ID],
        result_ids: [R4_RESULT_ID],
        diagnostics: [],
        unavailable_reason: null,
        unavailable: false,
        output_contract_version: 'mp05p-r4-players-output-1',
        contract_version: 'mp04-section-result-1',
        created_at: '2026-11-11T03:01:00+00:00',
        supersedes_section_result_id: null,
        approvable: true,
      },
    ],
    section_approvals: [],
    section_workflows: { implemented: [], workflows: [] },
    approval_note: '승인은 사용자 몫입니다.',
    registry: { modules: [] },
    approvals: { workflows: {}, approved: [], unapproved: [] },
    sources: [],
    artifacts: [],
    attempts: [],
    contract_versions: {},
    undo: { removable: {}, kept: [], allowed: false, reason: '없음' },
  }
}

/** RunVersionCompare가 요구하는 비교 payload. 이 화면 비교 자체는 검사 대상이 아니다. */
function comparePayload() {
  const row = {
    result_id: R4_RESULT_ID,
    module_id: 'R4',
    module_execution_id: R4_MODULE_ID,
    version: 1,
    input_hash: 'a'.repeat(64),
    status: 'succeeded',
    quality: 'ready',
    failure_code: null,
    contract_version: 'mp02-1',
    prompt_version: 'mp05p-r4-prompt-1',
    implementation_version: 'mp05p-r4-1',
    created_at: null,
    supersedes_result_id: null,
    payload: r4Body(),
  }
  return {
    module_execution_id: R4_MODULE_ID,
    module_id: 'R4',
    base: row,
    target: row,
    diff: {
      status: { from: 'succeeded', to: 'succeeded' },
      quality: { from: 'ready', to: 'ready' },
      input_hash: { from: 'a'.repeat(64), to: 'a'.repeat(64), changed: false },
      contract_version: { from: 'mp02-1', to: 'mp02-1' },
      prompt_version: { from: 'mp05p-r4-prompt-1', to: 'mp05p-r4-prompt-1' },
      claims_added: [],
      claims_removed: [],
      claims_changed: [],
      coverage_changes: {},
      payload_keys_changed: [],
    },
    changes: {},
    versions_available: [1],
  }
}

function json(body: unknown, status = 200) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as Response)
}

describe('R4 선수 패널과 본문 줄바꿈', () => {
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

  it('실행 검사 화면이 R4 선수 패널을 마운트하고 선정 선수·이유를 분리해 보여준다', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/versions')) return json(comparePayload())
      if (url.includes('/runs/')) return json(detailPayload())
      return json({ detail: 'not found' }, 404)
    })

    const wrapper = mount(RunInspector, {
      props: { runId: RUN_ID },
      attachTo: document.body,
    })
    await flushPromises()

    // R4 패널이 실제로 붙었는지(마운트되지 않으면 data-testid가 없다).
    const panel = wrapper.find('[data-testid="players-panel"]')
    expect(panel.exists()).toBe(true)
    expect(wrapper.text()).toContain('주목 선수 선정 (R4)')

    // 두 표시 필드가 분리된 라벨로 나온다. 한 문장으로 합치지 않는다.
    expect(wrapper.text()).toContain('선정 선수')
    expect(wrapper.text()).toContain('선정 이유')
    expect(wrapper.text()).toContain('엘링 홀란드')

    // 모의·재사용 경로를 실제 생성으로 읽히게 하지 않는다.
    expect(wrapper.text()).toContain('모의')
    wrapper.unmount()
  })

  it('본문 문단이 선정 선수와 선정 이유를 같은 문단의 두 줄로 보존한다', async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/versions')) return json(comparePayload())
      if (url.includes('/runs/')) return json(detailPayload())
      return json({ detail: 'not found' }, 404)
    })

    const wrapper = mount(RunInspector, {
      props: { runId: RUN_ID },
      attachTo: document.body,
    })
    await flushPromises()

    // R4 본문은 빈 줄로만 문단을 나눈다. 그래서 두 라벨은 **같은 문단 안의 두 줄**이다.
    // 줄바꿈이 데이터 단계에서 지워지면 여기서 이미 한 줄로 붙는다.
    const paragraphs = wrapper.findAll('[data-testid="section-result-body"] p')
    expect(paragraphs.length).toBeGreaterThan(0)
    const playerParagraph = paragraphs
      .map((node) => node.element.textContent ?? '')
      .find((text) => text.includes('선정 선수:'))
    expect(playerParagraph).toBeDefined()
    expect(playerParagraph).toContain('\n')
    expect(playerParagraph).toContain('선정 이유:')
    // 두 라벨이 서로 다른 줄에 있다(합쳐진 한 문장이 아니다).
    expect(playerParagraph!.split('\n').length).toBeGreaterThanOrEqual(2)

    wrapper.unmount()
  })
})
