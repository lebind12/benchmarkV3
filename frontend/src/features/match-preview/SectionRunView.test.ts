/**
 * 섹션 실행 화면 검사 (MP-05 통합).
 *
 * 이 파일이 확인하는 것:
 * - 경기 선택 → 섹션 선택 → 실행 → 저장된 본문·근거 표시 흐름이 화면에 있다.
 * - 승인 버튼은 승인 가능한(모의가 아닌) 결과에서만 열리고, 누르면 사용자 동작으로
 *   승인 요청을 보낸다.
 * - 모의 시연 결과는 승인 근거가 아니라고 화면이 먼저 알린다.
 * - 실제 구현이 없는 섹션은 live 실행을 열지 않는다.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { useAuthStore } from '@/stores/auth'

const sectionsMock = vi.fn()
const detailMock = vi.fn()
const runSectionMock = vi.fn()
const approveMock = vi.fn()
const bundleMock = vi.fn()
const regenerateMock = vi.fn()
const replayMock = vi.fn()

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: {
    sections: (...args: unknown[]) => sectionsMock(...args),
    detail: (...args: unknown[]) => detailMock(...args),
    runSection: (...args: unknown[]) => runSectionMock(...args),
    approveSection: (...args: unknown[]) => approveMock(...args),
    informationBundle: (...args: unknown[]) => bundleMock(...args),
    regenerateSection: (...args: unknown[]) => regenerateMock(...args),
    replayResult: (...args: unknown[]) => replayMock(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ fullPath: '/admin/sections', query: {} }),
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/features/match-preview/FixtureSelector.vue', () => ({
  default: {
    name: 'FixtureSelector',
    emits: ['select'],
    template: '<button data-test="fixture-stub" @click="$emit(\'select\', fixture)">경기</button>',
    data() {
      return {
        fixture: {
          fixture_id: 1557474,
          league_id: 1,
          season: 2026,
          home_team_id: 13,
          away_team_id: 4,
          home_team_name: 'Manchester City',
          away_team_name: 'Fulham',
          label: 'Manchester City vs Fulham',
          kickoff_at: '2026-11-21T12:30:00+00:00',
          selectable: true,
          origin: 'stored_db',
          origin_note: '',
          mode: null,
          run_id: null,
          league_name: 'Premier League',
          status_short: 'NS',
        },
      }
    },
  },
}))

const workflows = [
  {
    workflow_id: 'section_form',
    display_name: '경기력·주목 선수 섹션',
    description: '',
    module_ids: ['D0', 'R1'],
    output_contract_version: 'section_form-output-1',
    implemented: true,
    unrunnable_reason: null,
  },
  {
    workflow_id: 'section_synthesis',
    display_name: 'AI 예상·종합 섹션',
    description: '',
    module_ids: ['R1', 'R2', 'R3', 'S1'],
    output_contract_version: 'section_synthesis-output-1',
    implemented: false,
    unrunnable_reason: '아직 구현되지 않았습니다.',
  },
]

function sectionsResponse(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    data: {
      workflows,
      availability: {
        section_form: {
          workflow_id: 'section_form',
          display_name: '경기력·주목 선수 섹션',
          module_ids: ['D0', 'R1'],
          output_contract_version: 'section_form-output-1',
          implemented: true,
          missing_implementations: [],
          modes: ['live'],
          demo_only: false,
          real_generation_available: true,
          note: null,
          model: { configured: true },
        },
        section_synthesis: {
          workflow_id: 'section_synthesis',
          display_name: 'AI 예상·종합 섹션',
          module_ids: ['R1', 'R2', 'R3', 'S1'],
          output_contract_version: 'section_synthesis-output-1',
          implemented: false,
          missing_implementations: ['S1'],
          modes: [],
          demo_only: false,
          real_generation_available: false,
          note: '아직 구현되지 않았습니다.',
        },
        ...overrides,
      },
      mock_demo_note: '모의 시연은 승인 근거가 아닙니다.',
    },
  }
}

function detailResponse(mode: 'live' | 'mock', approvable: boolean) {
  return {
    ok: true,
    data: {
      section_results: [
        {
          section_result_id: '33333333-3333-4333-8333-333333333333',
          run_id: '44444444-4444-4444-8444-444444444444',
          workflow_id: 'section_form',
          workflow_version: 'section_form@abc',
          version: 1,
          title: '경기력과 주목 선수',
          body: 'Manchester City와 Fulham의 맞대결입니다.\n\n맨체스터 시티는 리그 3위입니다.',
          sources: [
            {
              label: 'API-Football 저장 자료',
              url: null,
              kind: 'api',
              note: '수집 2026-11-10T09:04:25+00:00',
            },
          ],
          mode,
          mode_label: mode === 'live' ? '실호출' : '모의 시연',
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
          approvable,
        },
      ],
    },
  }
}

describe('SectionRunView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().setUser({
      id: 1,
      email: 'admin@local.test',
      role: 'ADMIN',
      nickname: 'admin',
      is_active: true,
    })
    sectionsMock.mockReset()
    detailMock.mockReset()
    runSectionMock.mockReset()
    approveMock.mockReset()
    bundleMock.mockReset()
    regenerateMock.mockReset()
    replayMock.mockReset()
    // 정보 원문 조회는 기본값을 둔다(테스트마다 명시하지 않아도 되는 진단 조회).
    bundleMock.mockResolvedValue({ ok: false, kind: 'unknown', status: 404, message: '없음' })
  })

  it('경기를 고르면 섹션 실행이 본문과 근거를 보여준다', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    runSectionMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        workflow_id: 'section_form',
        workflow_version: 'section_form@abc',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: '33333333-3333-4333-8333-333333333333',
        section_result_version: 1,
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
      },
    })
    detailMock.mockResolvedValue(detailResponse('live', true))

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-test="fixture-stub"]').trigger('click')
    expect(wrapper.get('[data-testid="workspace-chosen-fixture"]').text()).toContain(
      'Manchester City vs Fulham',
    )

    await wrapper.get('[data-testid="workspace-run"]').trigger('click')
    await flushPromises()

    const body = wrapper.get('[data-testid="workspace-result-body"]').text()
    expect(body).toContain('Manchester City와 Fulham의 맞대결입니다.')
    expect(wrapper.get('[data-testid="workspace-result-sources"]').text()).toContain(
      'API-Football 저장 자료',
    )
    expect(runSectionMock).toHaveBeenCalledTimes(1)
    // 실행은 사용자가 버튼을 눌렀을 때만 일어난다.
    const payload = runSectionMock.mock.calls[0][0]
    expect(payload.workflow_id).toBe('section_form')
    expect(payload.fixture_id).toBe(1557474)

    await wrapper.unmount()
  })

  it('모의 시연 결과는 승인 버튼을 열지 않고 이유를 보여준다', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    runSectionMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        workflow_id: 'section_form',
        workflow_version: 'section_form@abc',
        mode: 'mock',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: '33333333-3333-4333-8333-333333333333',
        section_result_version: 1,
        external_calls: 0,
        budget: {},
        unavailable_reason: null,
        note: '모의 시연 실행입니다.',
      },
    })
    detailMock.mockResolvedValue(detailResponse('mock', false))

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-test="fixture-stub"]').trigger('click')
    await wrapper.get('[data-testid="workspace-run"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="workspace-result-mode"]').text()).toBe('mock')
    expect(wrapper.find('[data-testid="workspace-approve"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="workspace-approval-blocked"]').text()).toContain(
      '승인 근거로 쓸 수 없습니다',
    )
    expect(approveMock).not.toHaveBeenCalled()

    await wrapper.unmount()
  })

  it('사용자가 승인을 누르면 확인한 실행·섹션 결과 ID로 승인을 요청한다', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    runSectionMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        workflow_id: 'section_form',
        workflow_version: 'section_form@abc',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: '33333333-3333-4333-8333-333333333333',
        section_result_version: 1,
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
      },
    })
    detailMock.mockResolvedValue(detailResponse('live', true))
    approveMock.mockResolvedValue({ ok: true, data: { approval_id: 'approval-1' } })

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-test="fixture-stub"]').trigger('click')
    await wrapper.get('[data-testid="workspace-run"]').trigger('click')
    await flushPromises()

    // 승인 전에는 요청이 나가지 않는다.
    expect(approveMock).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="workspace-approve"]').trigger('click')
    await flushPromises()

    expect(approveMock).toHaveBeenCalledTimes(1)
    const [workflowId, payload] = approveMock.mock.calls[0]
    expect(workflowId).toBe('section_form')
    expect(payload.run_id).toBe('44444444-4444-4444-8444-444444444444')
    expect(payload.section_result_id).toBe('33333333-3333-4333-8333-333333333333')
    expect(wrapper.get('[data-testid="workspace-approval-done"]').text()).toContain('승인이 기록')

    await wrapper.unmount()
  })

  it('shows the stored bundle after body and sources, and never starts a write by itself', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    runSectionMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        workflow_id: 'section_form',
        workflow_version: 'section_form@abc',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: '33333333-3333-4333-8333-333333333333',
        section_result_version: 1,
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
      },
    })
    detailMock.mockResolvedValue(detailResponse('live', true))
    bundleMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        availability: { available: true, reason: null, artifact_id: 'artifact-1' },
        summary: {},
        bundle: {
          bundle_id: 'bundle-live-1',
          bundle_version: 'mp11-information-bundle-1',
          collected_at: '2026-11-11T00:16:39+00:00',
          mode: 'live',
          sources: [
            {
              source_id: 'src:example',
              requested_url: 'https://example.com/preview',
              final_url: 'https://example.com/preview',
              title: '예시 프리뷰 기사',
              nature: 'preview',
              method: 'fresh_http',
              http_status: 200,
              passages: [],
              failure: null,
              usable: false,
            },
          ],
          available_passages: [],
          section_deliveries: [],
          db_snapshot: null,
          odds: null,
          discovery_groups: [],
          diagnostics: [],
          network_usage: { http_used: 1 },
          browser_used: false,
          cross_checked_with_db: false,
          requires_grounding_chunks: false,
        },
      },
    })

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-test="fixture-stub"]').trigger('click')
    await wrapper.get('[data-testid="workspace-run"]').trigger('click')
    await flushPromises()

    // 본문 → 근거 → 정보 원문 순서가 DOM 순서로 지켜진다.
    const html = wrapper.html()
    const bodyIndex = html.indexOf('data-testid="workspace-result-body"')
    const sourcesIndex = html.indexOf('data-testid="workspace-result-sources"')
    const bundleIndex = html.indexOf('data-testid="information-bundle"')
    expect(bodyIndex).toBeGreaterThan(-1)
    expect(sourcesIndex).toBeGreaterThan(bodyIndex)
    expect(bundleIndex).toBeGreaterThan(sourcesIndex)

    expect(wrapper.get('[data-testid="bundle-id"]').text()).toBe('bundle-live-1')
    // 번들은 조회만 한다: 재생성·승인이 스스로 나가지 않는다.
    expect(regenerateMock).not.toHaveBeenCalled()
    expect(approveMock).not.toHaveBeenCalled()

    await wrapper.unmount()
  })

  it('enables reuse only when the loaded bundle provides an id', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    runSectionMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        workflow_id: 'section_form',
        workflow_version: 'section_form@abc',
        mode: 'live',
        status: 'succeeded',
        quality: 'ready',
        section_result_id: '33333333-3333-4333-8333-333333333333',
        section_result_version: 1,
        external_calls: 1,
        budget: {},
        unavailable_reason: null,
        note: '실행 결과를 저장했습니다.',
      },
    })
    detailMock.mockResolvedValue(detailResponse('live', true))
    bundleMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: '44444444-4444-4444-8444-444444444444',
        availability: { available: true, reason: null, artifact_id: null },
        summary: {},
        bundle: {
          bundle_id: 'bundle-x',
          sources: [],
          available_passages: [],
          section_deliveries: [],
          db_snapshot: null,
          odds: null,
          discovery_groups: [],
          diagnostics: [],
          network_usage: {},
        },
      },
    })

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-test="fixture-stub"]').trigger('click')
    await wrapper.get('[data-testid="workspace-run"]').trigger('click')
    await flushPromises()

    // 묶음 ID가 있으므로 재사용 모드가 열린다(차단 문구 없음).
    expect(wrapper.find('[data-testid="regen-reuse-blocked"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="section-regeneration"]').exists()).toBe(true)

    await wrapper.unmount()
  })

  it('실제 구현이 없는 섹션은 live를 고를 수 없다', async () => {
    sectionsMock.mockResolvedValue(sectionsResponse())
    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const wrapper = mount(SectionRunView)
    await flushPromises()

    await wrapper.get('[data-testid="workspace-section-section_synthesis"]').trigger('click')
    expect(wrapper.get('[data-testid="workspace-no-real-implementation"]').text()).toContain(
      '실제 조사·생성 구현이 아직 없습니다',
    )

    const liveOption = wrapper
      .get('[data-testid="workspace-mode"]')
      .findAll('option')
      .find((option) => (option.element as HTMLOptionElement).value === 'live')
    expect((liveOption?.element as HTMLOptionElement).disabled).toBe(true)

    await wrapper.unmount()
  })
})
