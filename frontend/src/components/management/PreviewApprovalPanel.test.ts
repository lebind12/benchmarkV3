/**
 * 관리 프리뷰 탭 내 섹션 워크플로우 승인 패널 단위/컴포넌트 검사.
 *
 * 각 검사는 수용 기준과 직결되며 실패 시 관리자에게 생기는 영향을 한 문장으로 남긴다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import PreviewApprovalPanel from './PreviewApprovalPanel.vue'
import type { ApiResult } from '@/lib/api/http'
import type { PreviewRunData } from '@/lib/api/preview'
import type { MatchPreviewView } from '@/lib/api/previewView'
import type {
  ApproveSectionResponse,
  CompositionView,
  RunDetail,
  SectionApprovalRow,
  SectionResultView,
} from '@/features/match-preview/types'

const apiMocks = vi.hoisted(() => ({
  approveSection: vi.fn(),
}))

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: apiMocks,
}))

const ok = <T>(data: T): ApiResult<T> => ({ ok: true, data })
const fail = (status: number, message: string): ApiResult<never> => ({
  ok: false,
  status,
  kind: 'server',
  message,
})

function makeResult(overrides: Partial<SectionResultView>): SectionResultView {
  return {
    section_result_id: 'sr-1',
    run_id: 'run-open',
    workflow_id: 'section_players',
    workflow_version: 'wfv-1',
    version: 1,
    title: '주목 선수',
    body: '유효한 섹션 본문',
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

function makeApprovalRow(overrides: Partial<SectionApprovalRow>): SectionApprovalRow {
  return {
    workflow_id: 'section_players',
    display_name: '주목 선수',
    description: '',
    module_ids: ['bundle_section_players'],
    implemented: true,
    unrunnable_reason: null,
    state: 'none',
    label: '미승인',
    detail: null,
    current_version: 'wfv-1',
    active_approval: null,
    pinned_approval: null,
    can_approve: true,
    ...overrides,
  }
}

function makeDetail(approvals: SectionApprovalRow[]): RunDetail {
  return {
    summary: {
      run_id: 'run-open',
      operation_kind: 'preview',
      environment: 'dev',
      mode: 'live',
      status: 'succeeded',
      quality: 'ready',
      fixture_label: '맨체스터 시티 vs 풀럼',
      requested_at: '2026-11-18T00:00:00Z',
      finished_at: '2026-11-18T00:01:00Z',
      module_count: 1,
      attempt_count: 1,
      retry_count: 0,
      failure_code: null,
      label: null,
      cancelled_at: null,
    },
    actor_id: '1',
    config_version: 'cfg-1',
    limits: {},
    fixture: {
      fixture_id: 1557474,
      kickoff_at: '2026-11-21T12:30:00Z',
      season: 2026,
      league_id: 39,
      home_team_id: 13,
      away_team_id: 4,
    },
    modules: [],
    results: [],
    sources: [],
    attempts: [],
    artifacts: [],
    contract_versions: {
      contract: 'c',
      provider: 'p',
      module_input: 'm',
      preview_document: 'd',
      inspector: 'i',
    },
    inspector_version: 'i',
    mode_detail: { mode: 'live', label: '실호출', note: '' },
    inspector_modules: [],
    registry: {
      registry_version: 'r',
      contract_version: 'c',
      inspector_version: 'i',
      modules: [],
      implemented: [],
      unavailable: [],
    },
    approvals: null,
    section_result_id: null,
    section_results: [],
    section_approvals: approvals,
    section_workflows: null,
    approval_note: '',
    mock_demo_module_id: '',
    availability_note: '',
    undo: {
      state: 'blocked',
      cancelled_at: null,
      cancelled_by_actor_id: null,
      reason: null,
      can_cancel: false,
      blocked_reason: null,
    },
  }
}

function makePreviewView(sections: MatchPreviewView['sections']): MatchPreviewView {
  return {
    fixture: {
      external_id: 1557474,
      home: { name: '맨체스터 시티', badge_url: null, external_id: 13 },
      away: { name: '풀럼', badge_url: null, external_id: 4 },
      league: null,
      kickoff_at: '2026-11-21T12:30:00Z',
      label: '맨체스터 시티 vs 풀럼',
    },
    generated_at: '2026-11-18T00:01:00Z',
    forecast: {
      forecastLines: [],
      reasoning: [],
      lean: null,
      lean_label: null,
      score: null,
    },
    playerIntro: [],
    players: [],
    injuries: [],
    media: [],
    odds: [],
    sections,
    complete: false,
    missing: [],
    team_aliases: new Map(),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('PreviewApprovalPanel', () => {
  // 이유: 단일 섹션 선택으로 한국어 이름·워크플로우 범위·메모를 표시하고 선택 결과의 ID로 정확히 1회 승인해야 한다.
  // 실패 시 사용자 결과: 관리자가 어떤 버전을 승인하는지 모르거나 다른 결과 ID로 잘못 승인할 수 있다.
  it('binds single selected section to displayed result and submits once with note', async () => {
    const playersRow = makeResult({
      section_result_id: 'sr-players-2',
      workflow_id: 'section_players',
      workflow_version: 'wfv-players-v2',
      version: 2,
      title: '주목 선수',
    })
    const availRow = makeResult({
      section_result_id: 'sr-avail-1',
      workflow_id: 'section_availability',
      workflow_version: 'wfv-avail-v1',
      version: 1,
      title: '출전 불가·부상 변수',
    })
    const runData: PreviewRunData = {
      run_id: 'run-open',
      preview: null,
      preview_error: null,
      sections: { run_id: 'run-open', section_results: [playersRow, availRow] },
      sections_error: null,
      detail: makeDetail([
        makeApprovalRow({ workflow_id: 'section_players', display_name: '주목 선수' }),
        makeApprovalRow({ workflow_id: 'section_availability', display_name: '출전 불가·부상 변수' }),
      ]),
      detail_error: null,
    }
    const previewView = makePreviewView({
      section_players: {
        section_id: 'section_players',
        title: '주목 선수',
        body: '본문',
        sources: [],
        quality: 'ready',
        partial: false,
        version: 2,
      },
      section_availability: {
        section_id: 'section_availability',
        title: '출전 불가·부상 변수',
        body: '결장 본문',
        sources: [],
        quality: 'ready',
        partial: false,
        version: 1,
      },
    })

    apiMocks.approveSection.mockResolvedValue(
      ok({
        approval_id: 'apr-2',
        workflow_id: 'section_availability',
        workflow_version: 'wfv-avail-v1',
        constituents: [],
        evidence: {
          run_id: 'run-open',
          section_result_id: 'sr-avail-1',
          reviewed_at: '2026-11-18T03:00:00Z',
        },
        approved_by_actor_id: '1',
        approved_at: '2026-11-18T03:00:00Z',
        reviewed_note: '출전 변수 확인 완료',
        supersedes_approval_id: null,
      }),
    )

    const wrapper = mount(PreviewApprovalPanel, {
      props: {
        openRunId: 'run-open',
        runData,
        previewView,
        composition: null,
        compositionLoaded: true,
        compositionError: null,
        blockedSections: [],
        canApproveRole: true,
        fixtureId: 1557474,
      },
    })

    expect(wrapper.get('[data-testid="preview-approval-scope-note"]').text()).toContain('섹션 워크플로우 버전과 그 근거 결과 행을 기록')
    await wrapper.get('[data-testid="preview-approval-item-section_availability"]').trigger('click')
    expect(wrapper.get('[data-testid="preview-approval-target-result"]').text()).toContain('sr-avail-1')

    await wrapper.get('[data-testid="preview-approval-note"]').setValue('출전 변수 확인 완료')
    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    await flushPromises()

    expect(apiMocks.approveSection).toHaveBeenCalledTimes(1)
    expect(apiMocks.approveSection).toHaveBeenCalledWith('section_availability', {
      run_id: 'run-open',
      section_result_id: 'sr-avail-1',
      note: '출전 변수 확인 완료',
    })
    expect(wrapper.get('[data-testid="preview-approval-success"]').text()).toContain('wfv-avail-v1')
    expect(wrapper.emitted('approved')?.[0]).toEqual([{ runId: 'run-open', workflowId: 'section_availability' }])
  })

  // 이유: 구성본이 다른 실행의 결과를 골랐다면 그 결과의 원래 run_id로 승인해야 하고 누락 시 대체 승인하지 않아야 한다.
  // 실패 시 사용자 결과: 재생성·구성본 실행에서 다른 run의 섹션이 잘못된 run_id로 실패하거나 엉뚱한 행으로 승인된다.
  it('uses cross-run owner run_id from composition and blocks if exact row is missing', async () => {
    const parentRow = makeResult({
      section_result_id: 'sr-parent-players',
      run_id: 'run-parent-9',
      workflow_id: 'section_players',
      workflow_version: 'wfv-parent',
      version: 1,
    })
    const composition: CompositionView = {
      composition_id: 'comp-1',
      fixture_id: 1557474,
      items: [
        {
          section_id: 'section_players',
          result_id: 'sr-parent-players',
          run_id: 'run-parent-9',
          fixture_id: 1557474,
          version: 1,
          workflow_version: 'wfv-parent',
          quality: 'ready',
          unavailable: false,
          unavailable_reason: null,
          body_chars: 120,
          mode: 'live',
          created_at: null,
        },
        {
          section_id: 'section_availability',
          result_id: 'sr-missing-avail',
          run_id: 'run-parent-8',
          fixture_id: 1557474,
          version: 1,
          workflow_version: 'wfv-avail',
          quality: 'ready',
          unavailable: false,
          unavailable_reason: null,
          body_chars: 90,
          mode: 'live',
          created_at: null,
        },
      ],
      refused: [],
      diagnostics: [],
      section_result_ids: ['sr-parent-players', 'sr-missing-avail'],
    }

    const runData: PreviewRunData = {
      run_id: 'run-child-1',
      preview: null,
      preview_error: null,
      sections: { run_id: 'run-child-1', section_results: [] },
      sections_error: null,
      composed_sections: [parentRow],
      composed_error: '구성본 행 누락: section_availability',
      detail: makeDetail([
        makeApprovalRow({ workflow_id: 'section_players', display_name: '주목 선수' }),
        makeApprovalRow({ workflow_id: 'section_availability', display_name: '출전 불가·부상 변수' }),
      ]),
      detail_error: null,
    }

    apiMocks.approveSection.mockResolvedValue(
      ok({
        approval_id: 'apr-3',
        workflow_id: 'section_players',
        workflow_version: 'wfv-parent',
        constituents: [],
        evidence: {
          run_id: 'run-parent-9',
          section_result_id: 'sr-parent-players',
          reviewed_at: '2026-11-18T03:00:00Z',
        },
        approved_by_actor_id: '1',
        approved_at: '2026-11-18T03:00:00Z',
        reviewed_note: null,
        supersedes_approval_id: null,
      }),
    )

    const wrapper = mount(PreviewApprovalPanel, {
      props: {
        openRunId: 'run-child-1',
        runData,
        previewView: null,
        composition,
        compositionLoaded: true,
        compositionError: null,
        blockedSections: [],
        canApproveRole: true,
        fixtureId: 1557474,
      },
    })

    expect(wrapper.get('[data-testid="preview-approval-target-run"]').text()).toContain('run-parent-9')
    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    await flushPromises()
    expect(apiMocks.approveSection).toHaveBeenCalledWith('section_players', {
      run_id: 'run-parent-9',
      section_result_id: 'sr-parent-players',
      note: undefined,
    })

    // 누락된 cross-run 결과는 승인 버튼을 비활성화하고 사유를 표시한다.
    await wrapper.get('[data-testid="preview-approval-item-section_availability"]').trigger('click')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('sr-missing-avail')
  })

  // 이유: mock·storage_mismatch·빈 본문·미확정 행·조회 오류·비ADMIN 상태에서는 승인을 막고 이유를 알려야 한다.
  // 실패 시 사용자 결과: 검증되지 않은 모의/불일치/오류 결과가 운영 기본 프리뷰 버전으로 잘못 승인된다.
  it('disables approval with explicit reason on mock, storage_mismatch, empty, detail/composition errors, and non-admin', async () => {
    const mockRow = makeResult({ section_result_id: 'sr-mock', workflow_id: 'section_players', mode: 'mock', mode_label: '모의' })
    const mismatchRow = makeResult({ section_result_id: 'sr-mis', workflow_id: 'section_availability', storage_mismatch: true })
    const emptyRow = makeResult({ section_result_id: 'sr-empty', workflow_id: 'section_odds', body: '   ', unavailable: false })
    const notApprovableRow = makeResult({ section_result_id: 'sr-noapp', workflow_id: 'section_outlook', approvable: false })
    const validRow = makeResult({ section_result_id: 'sr-valid', workflow_id: 'section_ai_forecast', approvable: true })

    const runData: PreviewRunData = {
      run_id: 'run-open',
      preview: null,
      preview_error: null,
      sections: {
        run_id: 'run-open',
        section_results: [mockRow, mismatchRow, emptyRow, notApprovableRow, validRow],
      },
      sections_error: null,
      detail: makeDetail([
        makeApprovalRow({ workflow_id: 'section_players', display_name: '주목 선수' }),
        makeApprovalRow({ workflow_id: 'section_availability', display_name: '출전 변수' }),
        makeApprovalRow({ workflow_id: 'section_odds', display_name: '배당 흐름' }),
        makeApprovalRow({ workflow_id: 'section_outlook', display_name: '매체 전망' }),
        makeApprovalRow({ workflow_id: 'section_ai_forecast', display_name: 'AI 전망' }),
      ]),
      detail_error: null,
    }

    const wrapper = mount(PreviewApprovalPanel, {
      props: {
        openRunId: 'run-open',
        runData,
        previewView: null,
        composition: null,
        compositionLoaded: true,
        compositionError: null,
        blockedSections: ['section_availability'],
        canApproveRole: true,
        fixtureId: 1557474,
      },
    })

    const assertBlocked = async (wf: string, textSnippet: string) => {
      await wrapper.get(`[data-testid="preview-approval-item-${wf}"]`).trigger('click')
      expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
      expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain(textSnippet)
    }

    await assertBlocked('section_players', 'mock')
    await assertBlocked('section_availability', 'storage_mismatch')
    await assertBlocked('section_odds', '본문이 비어')
    await assertBlocked('section_outlook', 'approvable=false')

    // 유효한 섹션이라도 구성본/상세 조회 오류 또는 비ADMIN이면 막힌다.
    await wrapper.get('[data-testid="preview-approval-item-section_ai_forecast"]').trigger('click')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(false)

    await wrapper.setProps({ compositionError: '구성본 503 오류' })
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('구성본 503 오류')

    await wrapper.setProps({
      compositionError: null,
      runData: { ...runData, detail_error: '상세 조회 503' },
    })
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('상세 조회 503')

    await wrapper.setProps({
      runData,
      canApproveRole: false,
    })
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('ADMIN')
    expect(apiMocks.approveSection).not.toHaveBeenCalled()
  })

  // 이유: 중복 클릭·실패 유지(자동 재시도 금지)·실행/섹션 전환 중 늦게 온 승인 응답 폐기가 동작해야 한다.
  // 실패 시 사용자 결과: 중복 승인 POST가 나가거나 다른 섹션/실행 화면에 이전 승인 완료 배너가 잘못 뜬다.
  it('prevents double-submit, preserves failure without retry, and discards stale response on selection switch', async () => {
    const playersRow = makeResult({ section_result_id: 'sr-p1', workflow_id: 'section_players', workflow_version: 'wfv-1' })
    const availRow = makeResult({ section_result_id: 'sr-a1', workflow_id: 'section_availability', workflow_version: 'wfv-a1' })
    const runData: PreviewRunData = {
      run_id: 'run-open',
      preview: null,
      preview_error: null,
      sections: { run_id: 'run-open', section_results: [playersRow, availRow] },
      sections_error: null,
      detail: makeDetail([
        makeApprovalRow({ workflow_id: 'section_players', display_name: '주목 선수' }),
        makeApprovalRow({ workflow_id: 'section_availability', display_name: '출전 변수' }),
      ]),
      detail_error: null,
    }

    // 1) 실패 유지 + 자동 재시도 금지
    apiMocks.approveSection.mockResolvedValueOnce(fail(409, '이미 충돌한 버전입니다.'))
    const wrapper = mount(PreviewApprovalPanel, {
      props: {
        openRunId: 'run-open',
        runData,
        previewView: null,
        composition: null,
        compositionLoaded: true,
        compositionError: null,
        blockedSections: [],
        canApproveRole: true,
        fixtureId: 1557474,
      },
    })

    await wrapper.get('[data-testid="preview-approval-note"]').setValue('보존될 메모')
    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    await flushPromises()

    expect(apiMocks.approveSection).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="preview-approval-error"]').text()).toContain('이미 충돌한 버전입니다.')
    expect((wrapper.get('[data-testid="preview-approval-note"]').element as HTMLInputElement).value).toBe('보존될 메모')

    // 2) 더블클릭 방지 + 섹션 전환 후 늦은 응답 폐기
    let resolveDelayed!: (v: ApiResult<ApproveSectionResponse>) => void
    apiMocks.approveSection.mockImplementationOnce(
      () =>
        new Promise<ApiResult<ApproveSectionResponse>>((resolve) => {
          resolveDelayed = resolve
        }),
    )

    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    expect(apiMocks.approveSection).toHaveBeenCalledTimes(2)

    await wrapper.get('[data-testid="preview-approval-item-section_availability"]').trigger('click')
    resolveDelayed(
      ok({
        approval_id: 'apr-late',
        workflow_id: 'section_players',
        workflow_version: 'wfv-1',
        constituents: [],
        evidence: {
          run_id: 'run-open',
          section_result_id: 'sr-p1',
          reviewed_at: '2026-11-18T03:00:00Z',
        },
        approved_by_actor_id: '1',
        approved_at: '2026-11-18T03:00:00Z',
        reviewed_note: null,
        supersedes_approval_id: null,
      }),
    )
    await flushPromises()

    expect(wrapper.find('[data-testid="preview-approval-success"]').exists()).toBe(false)
    expect(wrapper.emitted('approved')).toBeUndefined()
  })

  // 이유: raw section-results에 approvable이 없을 때 detail.section_results의 동일 (run_id, section_result_id) 판정만 결합하고 false·불일치·타 실행 행은 차단해야 한다.
  // 실패 시 사용자 결과: 정상 라이브 결과가 부당하게 차단되거나, 반대로 detail에서 거부된(false)/다른 결과의 판정이 잘못 적용된다.
  it('resolves omitted approvable strictly by (run_id, section_result_id) from detail.section_results and blocks false or mismatched rows', async () => {
    const rawPlayers = {
      ...makeResult({
        section_result_id: 'sr-p-raw',
        run_id: 'run-open',
        workflow_id: 'section_players',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    const rawAvail = {
      ...makeResult({
        section_result_id: 'sr-a-raw',
        run_id: 'run-open',
        workflow_id: 'section_availability',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    const rawOddsMismatchId = {
      ...makeResult({
        section_result_id: 'sr-o-raw',
        run_id: 'run-open',
        workflow_id: 'section_odds',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    const detail = makeDetail([
      makeApprovalRow({ workflow_id: 'section_players', display_name: '주목 선수' }),
      makeApprovalRow({ workflow_id: 'section_availability', display_name: '출전 변수' }),
      makeApprovalRow({ workflow_id: 'section_odds', display_name: '배당 흐름' }),
    ])
    detail.section_results = [
      makeResult({
        section_result_id: 'sr-p-raw',
        run_id: 'run-open',
        workflow_id: 'section_players',
        mode_label: '실제 생성',
        approvable: true,
      }),
      makeResult({
        section_result_id: 'sr-a-raw',
        run_id: 'run-open',
        workflow_id: 'section_availability',
        mode_label: '실제 생성',
        approvable: false,
      }),
      // workflow_id만 같고 section_result_id가 다른 행 — 오결합 금지
      makeResult({
        section_result_id: 'sr-o-other-id',
        run_id: 'run-open',
        workflow_id: 'section_odds',
        mode_label: '실제 생성',
        approvable: true,
      }),
    ]

    const runData: PreviewRunData = {
      run_id: 'run-open',
      preview: null,
      preview_error: null,
      sections: { run_id: 'run-open', section_results: [rawPlayers, rawAvail, rawOddsMismatchId] },
      sections_error: null,
      detail,
      detail_error: null,
    }

    const wrapper = mount(PreviewApprovalPanel, {
      props: {
        openRunId: 'run-open',
        runData,
        previewView: null,
        composition: null,
        compositionLoaded: true,
        compositionError: null,
        blockedSections: [],
        canApproveRole: true,
        fixtureId: 1557474,
      },
    })

    // 1) exact match approvable=true -> enabled + mode_label fallback
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(false)
    expect(wrapper.get('[data-testid="preview-approval-target-result"]').text()).toContain('실제 생성')

    // 2) exact match approvable=false -> blocked with approvable=false message
    await wrapper.get('[data-testid="preview-approval-item-section_availability"]').trigger('click')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('approvable=false')

    // 3) workflow_id만 일치하고 section_result_id가 다른 detail 행은 오결합하지 않고 차단
    await wrapper.get('[data-testid="preview-approval-item-section_odds"]').trigger('click')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('확인하지 못했습니다')
  })
})
