/**
 * BI-03 프리뷰 탭 검사.
 *
 * 확인하는 것은 세 묶음뿐이다(수용 기준과 1:1).
 *
 * 1. 진입·번호 확인·생성 횟수: 진입에 POST 0, 확인한 그 경기만 POST 1, 번호를 바꾸면
 *    이전 응답으로 생성하지 않음, 더블클릭해도 POST 1.
 * 2. 저장 결과 표시: 부분 본문도 표시, 다시 읽기는 GET만, 타경기 결과를 섞지 않음,
 *    `**강조**`는 strong 노드로만(HTML 미실행), 없는 배당을 합성하지 않음.
 * 3. 관리 화면 경계: 기존 관리 API 조회 실패가 프리뷰 진입을 막지 않음, ADMIN에게만
 *    프리뷰 탭·생성 UI가 보임.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import type { ApiResult } from '@/lib/api/http'
import type { FixtureCandidate } from '@/features/match-preview/fixtures'
import type {
  BundlePreviewRunResponse,
  ReaderPreview,
  RunDetail,
  SectionResultView,
  SectionResultsResponse,
} from '@/features/match-preview/types'

/** API 표면을 전부 mock한다. 실제 HTTP는 이 검사에서 나가지 않는다. */
const previewApi = vi.hoisted(() => ({
  fixture: vi.fn(),
  runBundle: vi.fn(),
  readerPreview: vi.fn(),
  sectionResults: vi.fn(),
  detail: vi.fn(),
  composition: vi.fn(),
  list: vi.fn(),
  informationBundle: vi.fn(),
  readerPreviewDiagnostics: vi.fn(),
  saveComposition: vi.fn(),
  regenerateSection: vi.fn(),
  replayResult: vi.fn(),
  approvals: vi.fn(),
  approveSection: vi.fn(),
}))

/** 관리 화면은 라우터 쿼리로 탭을 고른다. 검사에서는 쿼리만 고정한다. */
const currentQuery = vi.hoisted(() => ({ value: { tab: 'preview' } as Record<string, string> }))
const routerReplace = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: currentQuery.value }),
  useRouter: () => ({ push: vi.fn(), replace: routerReplace }),
  RouterLink: { template: '<a><slot /></a>' },
}))

vi.mock('@/features/match-preview/api', () => ({ previewRunsApi: previewApi }))

const homePreviewApi = vi.hoisted(() => ({
  getHomePreviewDocument: vi.fn(),
  getHomeRecommendations: vi.fn(),
}))

vi.mock('@/lib/api/homePreview', () => homePreviewApi)

/** 진단 하위 패널은 열릴 때만 마운트된다. 열리지 않는 기본 경로에서는 호출이 없어야 한다. */
vi.mock('@/features/match-preview/InformationBundlePanel.vue', () => ({
  default: { name: 'InformationBundlePanel', props: ['runId'], template: '<p data-testid="bundle-stub">bundle</p>' },
}))
vi.mock('@/features/match-preview/RunInspector.vue', () => ({
  default: {
    name: 'RunInspector',
    props: { runId: String, hideApproval: Boolean },
    template:
      '<p data-testid="inspector-stub" :data-hide-approval="String(Boolean(hideApproval))">inspector</p>',
  },
}))
vi.mock('@/features/match-preview/CompositionPanel.vue', () => ({
  default: { name: 'CompositionPanel', props: ['runId', 'results', 'fixtureId'], template: '<p data-testid="composition-stub">composition</p>' },
}))
/**
 * 재생성 패널 대역. 실제 패널은 별도 검사(`SectionRegenerationPanel.test.ts`)가 맡고,
 * 여기서는 **부모가 무엇을 넘기고 무엇을 받는지**(bundleId·selected_result_ids·성공 실행)만 본다.
 * 받은 props를 DOM에 드러내 검사가 읽을 수 있게 한다.
 */
vi.mock('@/features/match-preview/SectionRegenerationPanel.vue', () => ({
  default: {
    name: 'SectionRegenerationPanel',
    props: ['workflowId', 'fixtureId', 'results', 'bundleId', 'selectedResultIds', 'showApproval'],
    emits: ['regenerated'],
    template: [
      '<p data-testid="regen-stub"',
      '  :data-bundle-id="bundleId || \'\'"',
      '  :data-selected="(selectedResultIds || []).join(\',\')">regen</p>',
    ].join(' '),
  },
}))

import PreviewPanel from './PreviewPanel.vue'
import ManagementView from '@/views/ManagementView.vue'
import type { ManagementApi } from '@/lib/api/management'

const FIESTA = (overrides: Partial<FixtureCandidate> = {}): FixtureCandidate => ({
  fixture_id: 1557474,
  league_id: 39,
  league_name: 'Premier League',
  season: 2026,
  home_team_id: 13,
  home_team_name: '맨체스터 시티',
  away_team_id: 4,
  away_team_name: '풀럼',
  label: '맨체스터 시티 vs 풀럼',
  kickoff_at: '2026-11-21T12:30:00Z',
  status_short: 'NS',
  origin: 'stored_db',
  origin_note: '',
  run_id: null,
  mode: null,
  selectable: true,
  ...overrides,
})

function ok<T>(data: T): ApiResult<T> {
  return { ok: true, data }
}

function fail<T>(status: number, message = '실패'): ApiResult<T> {
  return { ok: false, kind: status === 503 ? 'server' : 'unknown', status, message }
}

const SAVED_RUN: BundlePreviewRunResponse = {
  run_id: 'run-1557474-a',
  mode: 'live',
  status: 'succeeded',
  quality: 'insufficient',
  bundle_id: 'bundle-1',
  bundle_hash: null,
  bundle_artifact_id: null,
  section_result_ids: {},
  section_quality: {},
  section_unavailable: { section_odds: '배당 없음' },
  discovery_status: {},
  external_calls: 5,
  budget: {},
  unavailable_reason: null,
  note: '',
}

function sectionResult(overrides: Partial<SectionResultView>): SectionResultView {
  return {
    section_result_id: 'sr-default',
    run_id: 'run-1557474-a',
    workflow_id: 'section_players',
    workflow_version: 'wfv-1',
    version: 1,
    title: '주목 선수',
    body: '',
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
    approvable: false,
    ...overrides,
  }
}

/** 실제 저장 run(9c079eea…)의 모양을 따른 부분 결과: 배당 본문이 비어 있다. */
function savedSections(): SectionResultsResponse {
  return {
    run_id: 'run-1557474-a',
    section_results: [
      sectionResult({
        section_result_id: 'sr-players',
        workflow_id: 'section_players',
        title: '주목 선수',
        body: '이번 경기의 주목 선수 2명입니다.\n\n선정 선수: 엘링 홀란드\n선정 이유: 리그 10경기 9골.',
        // 서버는 섹션 결과 행에 구조 값을 **평평하게** 덧붙인다(section_structured.structured_from_payload).
        available: true,
        structured: {
          players: [
            { player: '엘링 홀란드', reason: '리그 10경기 9골.', team: '맨체스터 시티' },
            { player: '조슈아 킹', reason: '복귀를 목표로 합니다.', team: '풀럼' },
          ],
        },
      } as Partial<SectionResultView>),
      sectionResult({
        section_result_id: 'sr-forecast',
        workflow_id: 'section_ai_forecast',
        title: 'AI 경기 전망',
        body: '## AI 경기 전망\n맨체스터 시티가 홈에서 주도할 것으로 봅니다.\n\n### AI 예상 스코어\n2-0\n\n- 홈 강세가 근거입니다.',
        available: true,
        structured: {
          forecast: { lean: 'home', score: '2-0', reasoning: ['홈 강세가 근거입니다.'] },
        },
      } as Partial<SectionResultView>),
      sectionResult({
        section_result_id: 'sr-odds',
        workflow_id: 'section_odds',
        title: '배당',
        body: '',
        quality: 'insufficient',
        unavailable_reason: '저장된 배당이 없습니다.',
        unavailable: true,
      }),
    ],
  }
}

function readerPreview(overrides: Partial<ReaderPreview> = {}): ReaderPreview {
  return {
    fixture: {
      fixture_id: 1557474,
      home_team_id: 13,
      away_team_id: 4,
      league_id: 39,
      season: 2026,
      kickoff_at: '2026-11-21T12:30:00Z',
      label: '맨체스터 시티 vs 풀럼',
      league: null,
    },
    headline: '맨체스터 시티 vs 풀럼',
    generated_at: '2026-11-11T10:55:21Z',
    data_as_of: null,
    attribution: { ai_forecast_label: 'AI 전망', ai_forecast_note: '모델 전망' },
    body: '본문',
    sections: [
      { section_id: 'section_players', title: '주목 선수', body: '저장 본문', sources: [], quality: 'ready', partial: false, version: 1 },
      { section_id: 'section_ai_forecast', title: 'AI 경기 전망', body: '저장 본문', sources: [], quality: 'ready', partial: false, version: 1 },
      { section_id: 'section_odds', title: '배당', body: '', sources: [], quality: 'insufficient', partial: true, version: 1 },
    ],
    complete: false,
    ...overrides,
  }
}

function runDetail(): RunDetail {
  return {
    summary: {
      run_id: 'run-1557474-a',
      operation_kind: 'preview',
      environment: 'dev',
      mode: 'live',
      status: 'succeeded',
      quality: 'insufficient',
      fixture_label: '맨체스터 시티 vs 풀럼',
      requested_at: '2026-11-11T10:55:21Z',
      finished_at: '2026-11-11T10:58:00Z',
      module_count: 6,
      attempt_count: 5,
      retry_count: 0,
      failure_code: null,
      label: null,
      cancelled_at: null,
    },
    actor_id: '1',
    config_version: 'cfg-1',
    limits: {},
    fixture: null,
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
    registry: { registry_version: 'r', contract_version: 'c', inspector_version: 'i', modules: [], implemented: [], unavailable: [] },
    approvals: null,
    section_result_id: null,
    section_results: [],
    section_approvals: [],
    section_workflows: null,
    approval_note: '',
    mock_demo_module_id: '',
    availability_note: '',
    undo: { state: 'blocked', cancelled_at: null, cancelled_by_actor_id: null, reason: null, can_cancel: false, blocked_reason: null },
  }
}

const mountOptions = () => ({
  props: { canGenerate: true },
  global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
})

async function typeNumber(wrapper: ReturnType<typeof mount>, value: string) {
  await wrapper.get('[data-testid="preview-fixture-number"]').setValue(value)
}

async function submitLookup(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-testid="preview-fixture-form"]').trigger('submit')
  await flushPromises()
}

async function submitOpenRun(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('[data-testid="preview-run-form"]').trigger('submit')
  await flushPromises()
}

/** vitest 버전에 `toHaveBeenCalledExactlyOnceWith`가 없어 직접 단언한다. */
function expectCalledOnceWith(mock: { mock: { calls: unknown[][] } }, ...args: unknown[]) {
  expect(mock.mock.calls.length).toBe(1)
  expect(mock.mock.calls[0]).toEqual(args)
}

beforeEach(() => {
  vi.clearAllMocks()
  currentQuery.value = { tab: 'preview' }
  previewApi.composition.mockResolvedValue(ok({ run_id: 'run-1557474-a', available: false, reason: '구성본 없음', composition: null }))
  previewApi.readerPreviewDiagnostics.mockResolvedValue(fail(404))
  previewApi.approvals.mockResolvedValue(
    ok({
      contract_version: 'c',
      workflows: {},
      approved: [],
      unapproved: [],
      scope_note: '',
    }),
  )
  homePreviewApi.getHomePreviewDocument.mockRejectedValue(new Error('not mocked'))
  homePreviewApi.getHomeRecommendations.mockRejectedValue(new Error('not mocked'))
})

describe('프리뷰 탭 — 생성 요청 횟수', () => {
  it('진입과 번호 확인만으로는 POST를 보내지 않는다', async () => {
    previewApi.fixture.mockResolvedValue(ok(FIESTA()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await flushPromises()

    expect(previewApi.fixture).not.toHaveBeenCalled()
    expect(previewApi.runBundle).not.toHaveBeenCalled()

    await typeNumber(wrapper, 'not-a-number')
    await submitLookup(wrapper)
    expect(wrapper.text()).toContain('양의 정수')
    expect(previewApi.fixture).not.toHaveBeenCalled()

    await typeNumber(wrapper, '1557474')
    await submitLookup(wrapper)
    expectCalledOnceWith(previewApi.fixture, 1557474)
    // 확인은 조회일 뿐이다. 여기서 생성이 나가면 안 된다.
    expect(previewApi.runBundle).not.toHaveBeenCalled()
  })

  it('확인한 그 경기 하나만 생성하고, 더블클릭해도 POST는 한 번이다', async () => {
    previewApi.fixture.mockResolvedValue(ok(FIESTA()))
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    let finish: (value: ApiResult<BundlePreviewRunResponse>) => void = () => undefined
    previewApi.runBundle.mockImplementation(
      () => new Promise<ApiResult<BundlePreviewRunResponse>>((resolve) => { finish = resolve }),
    )
    const wrapper = mount(PreviewPanel, mountOptions())

    await typeNumber(wrapper, '1557474')
    await submitLookup(wrapper)
    await wrapper.get('[data-testid="preview-generate"]').trigger('click')
    await wrapper.get('[data-testid="preview-generate"]').trigger('click')

    expectCalledOnceWith(previewApi.runBundle, 1557474)
    // 생성 중에는 시작한 경기를 화면에 남긴다.
    expect(wrapper.get('[data-testid="preview-generating"]').text()).toContain('맨체스터 시티 vs 풀럼')

    finish(ok(SAVED_RUN))
    await flushPromises()
    expect(previewApi.runBundle).toHaveBeenCalledTimes(1)
  })

  it('번호를 바꾸면 이전 조회 응답으로 생성하지 않고, 늦은 응답을 화면에 붙이지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    previewApi.runBundle.mockResolvedValue(ok({ ...SAVED_RUN, fixture_id: 1557475 }))
    let finishFirst: (value: ApiResult<FixtureCandidate>) => void = () => undefined
    previewApi.fixture
      .mockImplementationOnce(
        () => new Promise<ApiResult<FixtureCandidate>>((resolve) => { finishFirst = resolve }),
      )
      .mockResolvedValueOnce(ok(FIESTA({ fixture_id: 1557475, label: '리버풀 vs 첼시' })))
    const wrapper = mount(PreviewPanel, mountOptions())

    await typeNumber(wrapper, '1557474')
    await wrapper.get('[data-testid="preview-fixture-form"]').trigger('submit')
    // 응답 전에 번호를 바꾸고 다시 확인한다.
    await typeNumber(wrapper, '1557475')
    await submitLookup(wrapper)
    expect(wrapper.get('[data-testid="preview-confirmed-fixture"]').text()).toContain('리버풀 vs 첼시')

    // 이제서야 첫 응답이 도착한다. 이 값은 현재 입력(1557475)의 것이 아니다.
    finishFirst(ok(FIESTA()))
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-confirmed-fixture"]').text()).toContain('리버풀 vs 첼시')

    await wrapper.get('[data-testid="preview-generate"]').trigger('click')
    await flushPromises()
    expectCalledOnceWith(previewApi.runBundle, 1557475)
  })
})

describe('프리뷰 탭 — 저장 결과 표시', () => {
  it('부분 본문도 표시하고 다시 읽기는 GET만 보낸다', async () => {
    previewApi.fixture.mockResolvedValue(ok(FIESTA()))
    previewApi.runBundle.mockResolvedValue(ok(SAVED_RUN))
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())

    await typeNumber(wrapper, '1557474')
    await submitLookup(wrapper)
    await wrapper.get('[data-testid="preview-generate"]').trigger('click')
    await flushPromises()

    const body = wrapper.get('[data-testid="preview-body"]')
    expect(body.text()).toContain('엘링 홀란드')
    // 점수 카드는 홈·원정을 따로 그린다(목업과 같은 배치).
    const score = body.get('.mpv-prediction__score').text().replace(/\s+/g, '')
    expect(score).toBe('2:0')
    expect(body.text()).toContain('홈 강세가 근거입니다.')

    // 수용 기준: 주목 선수와 AI 경기 전망은 본문에서 **각각 한 번**만 나온다.
    // 실패하면 사용자는 같은 선수·전망을 두 번 읽고 어느 쪽이 저장된 결론인지 알 수 없다.
    const titles = body.findAll('.mpv-section__title').map((node) => node.text())
    expect(titles.filter((title) => title === '주목 선수').length).toBe(1)
    expect(titles.filter((title) => title === 'AI 경기 전망').length).toBe(1)
    // 도입 문장은 지우지 않고 주목 선수 섹션 안에서 한 번 읽힌다.
    expect(body.text().split('이번 경기의 주목 선수 2명입니다.').length - 1).toBe(1)

    // 품질 표기가 낮아도(부분 결과) 받은 본문은 위에 그대로 있다. 그 사실은 진단에서 확인한다.
    const details = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    details.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-complete"]').text()).toContain('부분 결과')
    expect(body.text()).toContain('엘링 홀란드')

    const postsBefore = previewApi.runBundle.mock.calls.length
    await wrapper.get('[data-testid="preview-reread"]').trigger('click')
    await flushPromises()
    expect(previewApi.runBundle).toHaveBeenCalledTimes(postsBefore)
    expect(previewApi.readerPreview).toHaveBeenCalledWith('run-1557474-a')
    expect(previewApi.sectionResults).toHaveBeenCalledWith('run-1557474-a')
  })

  it('타경기 결과를 섞지 않고 reader가 고른 버전만 쓴다', async () => {
    previewApi.runBundle.mockResolvedValue(ok(SAVED_RUN))
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    // 같은 실행 안에 v2(다른 버전)와 타경기 실행의 결과가 함께 온다.
    const mixed: SectionResultsResponse = {
      run_id: 'run-1557474-a',
      section_results: [
        ...savedSections().section_results,
        sectionResult({
          section_result_id: 'sr-players-v2',
          workflow_id: 'section_players',
          version: 2,
          body: '다른 버전 본문 — reader가 고르지 않았다.',
          structured: {},
        }),
        sectionResult({
          section_result_id: 'sr-other-fixture',
          run_id: 'run-other-fixture',
          workflow_id: 'section_outlook',
          version: 1,
          body: '타경기 매체 본문',
        }),
      ],
    }
    previewApi.sectionResults.mockResolvedValue(ok(mixed))
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()

    const body = wrapper.get('[data-testid="preview-body"]')
    expect(body.text()).not.toContain('다른 버전 본문')
    expect(body.text()).not.toContain('타경기 매체 본문')
    expect(body.text()).toContain('엘링 홀란드')
  })

  it('강조는 strong 노드로만 표시하고 HTML을 실행하지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-a',
        section_results: [
          sectionResult({
            section_result_id: 'sr-forecast',
            workflow_id: 'section_ai_forecast',
            title: 'AI 경기 전망',
            body: '**맨체스터 시티**가 주도합니다. <img src=x onerror=alert(1)>',
            structured: {},
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()

    const body = wrapper.get('[data-testid="preview-body"]')
    expect(body.find('strong').exists()).toBe(true)
    expect(body.find('img').exists()).toBe(false)
    expect(body.text()).toContain('<img src=x onerror=alert(1)>')
  })

  it('저장된 한국어 라벨로 팀 좌우를 정하고, 순서가 뒤집혀도 홈/원정이 바뀌지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            {
              section_id: 'section_availability',
              title: '부상·결장',
              body: '## 부상·결장 영향',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    // 실제 저장본과 같은 혼합: 선수는 한국어 팀명, 부상은 영어 팀명, 원정이 먼저 온다.
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-a',
        section_results: [
          sectionResult({
            section_result_id: 'sr-availability',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '## 부상·결장 영향',
            available: true,
            structured: {
              injuries: [
                { player: '톰 케어니', team: 'Fulham', status: 'doubtful', summary: '무릎 부상.' },
                { player: '액셀 디사시', team: 'Manchester City', status: 'confirmed_absence', summary: '장기 결장.' },
              ],
            },
          }),
        ],
      }),
    )
    // 실행 상세가 저장된 번역 쌍을 들고 온다(R4 payload의 korean_labels).
    previewApi.detail.mockResolvedValue(
      ok({
        ...runDetail(),
        results: [
          {
            payload: {
              payload: {
                korean_labels: [
                  { kind: 'team', original: 'Manchester City', korean: '맨체스터 시티' },
                  { kind: 'team', original: 'Fulham', korean: '풀럼' },
                ],
              },
            },
          },
        ],
      } as unknown as RunDetail),
    )

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    const teams = wrapper.findAll('.mpv-team')
    const away = teams.find((team) => team.classes().includes('mpv-team--away'))
    const home = teams.find((team) => team.classes().includes('mpv-team--home'))
    expect(away?.text()).toContain('톰 케어니')
    expect(home?.text()).toContain('액셀 디사시')
  })

  it('없는 배당을 합성하지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()

    const body = wrapper.get('[data-testid="preview-body"]')
    // 저장된 배당이 없으므로 소스별 1X2 칸도 만들지 않는다.
    expect(body.text()).not.toContain('무승부')
    expect(body.findAll('.mpv-odds__cells').length).toBe(0)

    // 수용 기준: 배당 자료 미제공 원인은 **관리자 진단**에서 확인할 수 있어야 한다.
    // 본문에는 사유를 섞지 않고, 저장된 섹션 사유를 그대로 보여준다.
    // 실패하면 사용자는 배당이 없는 이유를 알 수 없어 연결 오류와 자료 부재를 구분하지 못한다.
    const details = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    details.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-missing"]').text()).toContain('배당 표를 표시하지 않았습니다.')
    expect(wrapper.get('[data-testid="preview-missing"]').text()).toContain('저장된 배당이 없습니다.')
    expect(body.text()).not.toContain('저장된 배당이 없습니다.')
  })

  it('섹션 결과 조회 실패를 자료 없음으로 표시하지 않고, 읽힌 독자 본문은 계속 보여준다 (D-1)', async () => {
    // 독자 본문은 읽혔고 섹션 결과 조회만 503으로 실패한 경우.
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            {
              section_id: 'section_players',
              title: '주목 선수',
              body: '독자 응답이 준 저장 본문입니다.',
              sources: [{ label: 'Manchester City squad', kind: 'web', url: 'https://example.com/squad' }],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    previewApi.sectionResults.mockResolvedValue(fail(503, '섹션 결과 조회 실패(503)'))
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()

    const details = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    details.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()

    // 조회 실패는 조회 오류로 표시하고 사유를 보존한다.
    const alert = wrapper.get('[data-testid="preview-sections-error"]')
    expect(alert.text()).toContain('읽지 못했습니다')
    expect(alert.text()).toContain('섹션 결과 조회 실패(503)')
    // 실제 빈 목록과 같은 문구("저장된 섹션 결과가 없습니다")로 위장하지 않는다.
    expect(wrapper.text()).not.toContain('저장된 섹션 결과가 없습니다')
    // 실행 전체를 실패로 만들지 않고, 읽힌 독자 본문은 그대로 보여준다.
    expect(wrapper.find('[data-testid="preview-run-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain(
      '독자 응답이 준 저장 본문입니다.',
    )
    // 조회 실패가 새 생성·재생성을 자동 호출하지 않는다.
    expect(previewApi.runBundle).not.toHaveBeenCalled()
    expect(previewApi.regenerateSection).not.toHaveBeenCalled()
  })

  it('구성본이 고른 다른 실행의 섹션을 이 실행의 행 목록에 없어도 표시한다 (D-2)', async () => {
    // 마지막 AI만 다시 실행한 run을 연다. 구성본은 앞 섹션을 **부모 실행**에서 골랐으므로
    // 이 실행의 /section-results에는 선수 섹션 행이 없다. reader 응답에는 그 본문이 있다.
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            {
              section_id: 'section_players',
              title: '주목 선수',
              body: '부모 실행에서 고른 주목 선수 본문입니다.',
              sources: [
                { label: 'Manchester City squad', kind: 'web', url: 'https://example.com/parent-squad' },
              ],
              quality: 'ready',
              partial: false,
              version: 3,
            },
            {
              section_id: 'section_ai_forecast',
              title: 'AI 경기 전망',
              body: '## AI 경기 전망\n마지막 AI 전망 본문입니다.',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-final',
        section_results: [
          sectionResult({
            section_result_id: 'sr-final-forecast',
            run_id: 'run-final',
            workflow_id: 'section_ai_forecast',
            title: 'AI 경기 전망',
            body: '## AI 경기 전망\n마지막 AI 전망 본문입니다.',
            structured: {},
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-final')
    await submitOpenRun(wrapper)
    await flushPromises()

    // 이 실행의 행 목록에 없어도 reader가 고른 본문을 그대로 보여준다.
    const body = wrapper.get('[data-testid="preview-body"]')
    expect(body.text()).toContain('부모 실행에서 고른 주목 선수 본문입니다.')
    expect(body.text()).toContain('마지막 AI 전망 본문입니다.')

    // 근거도 reader가 준 값을 그대로 쓴다. 같은 섹션의 다른 버전으로 바꾸지 않는다.
    const details = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    details.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    const picked = wrapper.get('[data-testid="preview-reader-sections"]')
    expect(picked.text()).toContain('v3')
    expect(picked.html()).toContain('https://example.com/parent-squad')
    // 조회 실패가 아니므로 조회 오류 문구를 쓰지 않는다.
    expect(wrapper.find('[data-testid="preview-sections-error"]').exists()).toBe(false)
  })
})

describe('프리뷰 탭 — 정본 저장 불일치 문서 처리', () => {
  /**
   * 생성 응답은 왔지만 선수 섹션의 정본 저장 행을 찾지 못한 실행을 연다.
   * 사용자가 보면 안 되는 것: 응답에서 만든 본문이 정상 저장 문서처럼 보이는 화면.
   */
  async function openMismatchedRun() {
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            {
              section_id: 'section_players',
              title: '주목 선수',
              body: '응답에서 만든 선수 본문입니다.',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
            {
              section_id: 'section_ai_forecast',
              title: 'AI 경기 전망',
              body: '## AI 경기 전망\n저장된 전망 본문입니다.',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-mismatch',
        section_results: [
          sectionResult({
            section_result_id: 'sr-players-mismatch',
            run_id: 'run-mismatch',
            workflow_id: 'section_players',
            title: '주목 선수',
            body: '응답에서 만든 선수 본문입니다.',
            storage_status: 'storage_mismatch',
            storage_mismatch: true,
            storage_error: '정본 저장 행을 찾지 못했습니다(output_contract_version="psc-1").',
            available: false,
          }),
          sectionResult({
            section_result_id: 'sr-forecast-ok',
            run_id: 'run-mismatch',
            workflow_id: 'section_ai_forecast',
            title: 'AI 경기 전망',
            body: '## AI 경기 전망\n저장된 전망 본문입니다.',
            structured: {},
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-mismatch')
    await submitOpenRun(wrapper)
    await flushPromises()
    return wrapper
  }

  it('불일치 섹션은 정상 문서로 그리지 않고 문서 위에 사유를 표시한다', async () => {
    const wrapper = await openMismatchedRun()

    const banner = wrapper.get('[data-testid="preview-storage-blocked"]')
    expect(banner.text()).toContain('section_players')
    expect(banner.text()).toContain('정본 저장 행을 찾지 못했습니다')

    const body = wrapper.get('[data-testid="preview-body"]')
    // 응답 본문이 정상 카드/본문으로 보이면 사용자가 저장된 결과로 오인한다.
    expect(body.text()).not.toContain('응답에서 만든 선수 본문입니다.')
    // 정본이 확인된 다른 섹션은 부분 문서로 남는다.
    expect(body.text()).toContain('저장된 전망 본문입니다.')

    // 원문은 접힌 참고 진단에만 남는다(진단 자체를 펼쳐야 보인다).
    const diagnostics = wrapper.get('[data-testid="preview-diagnostics"]')
      .element as HTMLDetailsElement
    diagnostics.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-body"]').text()).not.toContain(
      '응답에서 만든 선수 본문입니다.',
    )
    const raw = wrapper.get('[data-testid="preview-blocked-raw"]')
    expect(raw.element.tagName.toLowerCase()).toBe('details')
    expect((raw.element as HTMLDetailsElement).open).toBe(false)
    expect(raw.text()).toContain('응답에서 만든 선수 본문입니다.')
    expect(raw.text()).toContain('정본 저장 행을 찾지 못했습니다')
  })

  it('구계약 실행(플래그 없음)에는 차단 배너를 만들지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()

    expect(wrapper.find('[data-testid="preview-storage-blocked"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-blocked-raw"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('엘링 홀란드')
  })
})

describe('프리뷰 탭 — 기간 수집 시험 영역 연결', () => {
  it('ADMIN에게 기간 수집·다경기 영역을 기존 탭 안에 보여주고, 진입만으로는 POST를 보내지 않는다', async () => {
    const wrapper = mount(PreviewPanel, mountOptions())
    await flushPromises()

    expect(wrapper.find('[data-testid="preview-test-panel"]').exists()).toBe(true)
    // 기존 단일 경기 흐름도 그대로 남아 있다.
    expect(wrapper.find('[data-testid="preview-fixture-form"]').exists()).toBe(true)
    expect(previewApi.runBundle).not.toHaveBeenCalled()
  })

  it('시험 영역이 연 저장 문서는 같은 실행을 GET으로 열고 생성은 보내지 않는다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await flushPromises()

    // 시험 표에서 "저장된 문서 보기"를 누른 것과 같은 경로로 연다.
    const panel = wrapper.findComponent({ name: 'PreviewTestPanel' })
    panel.vm.$emit('openDocument', { runId: 'run-1557474-a' })
    await flushPromises()

    expect(previewApi.readerPreview).toHaveBeenCalledWith('run-1557474-a')
    expect(previewApi.runBundle).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('엘링 홀란드')
  })
})

describe('프리뷰 탭 — 저장된 실행 주소', () => {
  it('주소의 previewRun으로 진입하면 저장 결과를 GET으로 열고 POST는 보내지 않는다', async () => {
    currentQuery.value = { tab: 'preview', previewRun: '9c079eea-6f66-46bb-83e2-460850f0a22f' }
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await flushPromises()

    expect(previewApi.readerPreview).toHaveBeenCalledWith('9c079eea-6f66-46bb-83e2-460850f0a22f')
    expect(wrapper.find('[data-testid="preview-body"]').exists()).toBe(true)
    expect(previewApi.runBundle).not.toHaveBeenCalled()
    expect(previewApi.fixture).not.toHaveBeenCalled()
  })

  it('수집 실행의 run 쿼리와 섞이지 않는다', async () => {
    // 수집 실행 이력의 `run`은 프리뷰가 읽지 않는다.
    currentQuery.value = { tab: 'preview', run: 'collection-run-1' }
    const wrapper = mount(PreviewPanel, mountOptions())
    await flushPromises()

    expect(previewApi.readerPreview).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="preview-body"]').exists()).toBe(false)
  })
})

describe('프리뷰 탭 — 사진·로고 nullable 계약', () => {
  /**
   * 예전 저장본(추가 필드 없음)을 연다. 사진·로고 키가 아예 없어도 **본문은 그대로** 나와야
   * 하고, 없는 사진 자리에 엉뚱한 URL을 만들면 안 된다.
   */
  /** reader 가 고른 섹션 목록. 서버의 구성본 선택을 흉내 낸다(고른 것만 표시된다). */
  function readerChoosing(sectionIds: string[]): ReaderPreview {
    return readerPreview({
      sections: sectionIds.map((id) => ({
        section_id: id,
        title: id,
        body: '저장 본문',
        sources: [],
        quality: 'ready',
        partial: false,
        version: 1,
      })),
    })
  }

  async function openLegacyRun() {
    previewApi.readerPreview.mockResolvedValue(
      ok(readerChoosing(['section_players', 'section_availability'])),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-legacy',
        section_results: [
          sectionResult({
            section_result_id: 'sr-legacy-players',
            run_id: 'run-legacy',
            workflow_id: 'section_players',
            title: '주목 선수',
            body: '이번 경기의 주목 선수 1명입니다.\n\n선정 선수: 엘링 홀란드\n선정 이유: 리그 10경기 9골.',
            // 내부 player_id 만 있고 external_player_id/photo_url 은 없다(이전 스키마).
            available: true,
            structured: {
              players: [
                { player: '엘링 홀란드', reason: '리그 10경기 9골.', team: '맨체스터 시티', player_id: 533 },
              ],
            },
          }),
          sectionResult({
            section_result_id: 'sr-legacy-availability',
            run_id: 'run-legacy',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '## 부상·결장 영향',
            available: true,
            structured: {
              injuries: [
                { player: '앙투안 세메뇨', team: '맨체스터 시티', status: 'confirmed_absence', summary: '장기 결장.', player_id: 88 },
              ],
            },
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-legacy')
    await submitOpenRun(wrapper)
    return wrapper
  }

  it('추가 필드가 없는 이전 스키마에서도 본문을 그리고, 내부 ID로 사진 URL을 만들지 않는다', async () => {
    const wrapper = await openLegacyRun()
    const body = wrapper.get('[data-testid="preview-body"]')

    // 본문(이름·이유·부상)은 그대로 보인다.
    expect(body.text()).toContain('엘링 홀란드')
    expect(body.text()).toContain('리그 10경기 9골.')
    expect(body.text()).toContain('앙투안 세메뇨')

    // 사진은 하나도 그리지 않는다. 특히 내부 ID(533·88)로 CDN 주소를 만들면 안 된다.
    expect(body.find('img').exists()).toBe(false)
    expect(body.html()).not.toContain('media.api-sports.io')
    expect(body.html()).not.toContain('/players/533')
    expect(body.html()).not.toContain('/players/88')

    // 사진이 실제로 빠졌다는 사실은 진단 영역에 남는다(본문 문장에는 섞지 않는다).
    const details = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    details.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-missing"]').text()).toContain('사진')
  })

  it('서버가 준 photo_url·로고를 주목/부상 사진과 두 팀 로고에 연결한다', async () => {
    previewApi.readerPreview.mockResolvedValue(
      ok(readerChoosing(['section_players', 'section_availability'])),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-photos',
        section_results: [
          sectionResult({
            section_result_id: 'sr-photos',
            run_id: 'run-photos',
            workflow_id: 'section_players',
            title: '주목 선수',
            body: '저장 본문',
            available: true,
            structured: {
              players: [
                {
                  player: '엘링 홀란드',
                  reason: '리그 10경기 9골.',
                  team: '맨체스터 시티',
                  // 내부 ID(533)와 외부 ID(1100)는 다른 값이다. 사진은 서버가 준 URL만 쓴다.
                  player_id: 533,
                  external_player_id: 1100,
                  team_external_id: 50,
                  photo_url: 'https://media.api-sports.io/football/players/1100.png',
                },
                {
                  // 원정 팀도 한 명 둬서 두 팀 로고가 모두 그려지는지 확인한다.
                  player: '조슈아 킹',
                  reason: '복귀를 목표로 합니다.',
                  team: '풀럼',
                  player_id: 139,
                  external_player_id: 156477,
                  team_external_id: 36,
                  photo_url: 'https://media.api-sports.io/football/players/156477.png',
                },
              ],
            },
          }),
          sectionResult({
            section_result_id: 'sr-photos-availability',
            run_id: 'run-photos',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '## 부상·결장 영향',
            available: true,
            structured: {
              injuries: [
                {
                  player: '앙투안 세메뇨',
                  team: '맨체스터 시티',
                  status: 'confirmed_absence',
                  summary: '장기 결장.',
                  player_id: 88,
                  external_player_id: 19281,
                  team_external_id: 50,
                  photo_url: 'https://media.api-sports.io/football/players/19281.png',
                },
              ],
            },
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const base = readerChoosing(['section_players', 'section_availability'])
    previewApi.readerPreview.mockResolvedValue(
      ok({
        ...base,
        fixture: {
          ...base.fixture,
          home_team_external_id: 50,
          away_team_external_id: 36,
          home_team_logo_url: 'https://media.api-sports.io/football/teams/50.png',
          away_team_logo_url: 'https://media.api-sports.io/football/teams/36.png',
        },
      }),
    )

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-photos')
    await submitOpenRun(wrapper)

    const html = wrapper.get('[data-testid="preview-body"]').html()
    // 선수·부상 사진
    expect(html).toContain('https://media.api-sports.io/football/players/1100.png')
    expect(html).toContain('https://media.api-sports.io/football/players/19281.png')
    // 두 팀 로고(서버가 준 값)
    expect(html).toContain('https://media.api-sports.io/football/teams/50.png')
    expect(html).toContain('https://media.api-sports.io/football/teams/36.png')
    // 외부 ID를 내부 ID로 바꿔 쓰지 않는다.
    expect(html).not.toContain('/players/533.png')
  })

  it('내부 팀 ID·이름으로 확인되지 않으면 배열 순서로 홈/원정을 만들지 않는다', async () => {
    // 외부 팀 ID도 없고 이름도 라벨과 맞지 않는 두 팀이 원정이 먼저 오는 순서로 온다.
    previewApi.readerPreview.mockResolvedValue(ok(readerChoosing(['section_availability'])))
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-unknown',
        section_results: [
          sectionResult({
            section_result_id: 'sr-unknown',
            run_id: 'run-unknown',
            workflow_id: 'section_availability',
            title: '부상·결장',
            body: '저장 본문',
            available: true,
            structured: {
              injuries: [
                { player: '제레미 도쿠', team: 'Man City', status: 'doubtful', summary: '종아리.' },
                { player: '조쉬 킹', team: 'Fulham', status: 'doubtful', summary: '사타구니.' },
              ],
            },
          }),
        ],
      }),
    )
    previewApi.detail.mockResolvedValue(
      ok({ ...runDetail(), results: [] } as unknown as RunDetail),
    )

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-unknown')
    await submitOpenRun(wrapper)

    const teams = wrapper.findAll('.mpv-team')
    expect(teams.length).toBe(2)
    // 팀 이름이 라벨(맨체스터 시티/풀럼)과 맞지 않고 외부 ID도 없으므로 홈/원정을 확인할 수 없다.
    // 그래서 어느 묶음에도 "홈"/"원정" 글자를 붙이지 않는다(배열 순서로 단정하지 않는다).
    for (const team of teams) {
      const label = team.get('.mpv-team__head').text()
      expect(label).not.toContain('홈')
      expect(label).not.toContain('원정')
    }
    // 본문(선수명)은 그대로 보인다.
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('제레미 도쿠')
  })
})

/**
 * 재생성 패널 연결 (PF-REUSE).
 *
 * 사용자가 본 결함: 이 실행에는 정보 원문 묶음이 있는데도(`information-bundle` GET이
 * `available=true`, `bundle_id=bundle-…`) 재생성 패널이 "재사용할 정보 원문 묶음이 없습니다"로
 * 비활성화됐다. 원인은 부모가 `bundleId`를 넘기지 않은 것이다.
 */
describe('프리뷰 탭 — 재생성 패널의 저장 묶음 연결', () => {
  /** 실제 응답 모양: availability.available=true + bundle.bundle_id. */
  const bundlePayload = (bundleId: string) => ({
    run_id: 'run-1557474-a',
    availability: { available: true, reason: null },
    bundle: { bundle_id: bundleId, sources: [] },
  })

  async function openRunForRegeneration() {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    await flushPromises()
    return wrapper
  }

  /**
   * 진단 접힌 영역을 펼치고 재생성 영역까지 연다. 재생성 패널은 진단 안쪽에만 마운트된다
   * (`v-if="diagnosticsOpen"`). 이 순서를 지켜야 묶음 조회 시점을 관측할 수 있다.
   */
  async function expandAndSelect(wrapper: ReturnType<typeof mount>, sectionId: string) {
    const diagnostics = wrapper.get('[data-testid="preview-diagnostics"]')
      .element as HTMLDetailsElement
    diagnostics.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()

    const regeneration = wrapper.get('[data-testid="preview-regeneration"]')
      .element as HTMLDetailsElement
    regeneration.open = true
    await wrapper.get('[data-testid="preview-regeneration"]').trigger('toggle')
    await flushPromises()

    await wrapper.get('[data-testid="preview-regeneration-section"]').setValue(sectionId)
    await flushPromises()
  }

  it('사용자가 재생성 영역을 열 때 기존 information-bundle API로 이 실행의 bundleId를 넘긴다', async () => {
    previewApi.informationBundle.mockResolvedValue(ok(bundlePayload('bundle-524b60b9eb084a06')))
    const wrapper = await openRunForRegeneration()

    // 접힌 상태에서는 조회하지 않는다(자동 조회 아님).
    expect(previewApi.informationBundle).not.toHaveBeenCalled()

    await expandAndSelect(wrapper, 'section_odds')

    expectCalledOnceWith(previewApi.informationBundle, 'run-1557474-a')
    expect(wrapper.get('[data-testid="regen-stub"]').attributes('data-bundle-id')).toBe(
      'bundle-524b60b9eb084a06',
    )
  })

  it('묶음 조회가 실패하면 재사용을 열지 않고 사유를 보인다(묶음 없음으로 숨기지 않는다)', async () => {
    previewApi.informationBundle.mockResolvedValue(fail(503, '정보 원문 조회 실패(503)'))
    const wrapper = await openRunForRegeneration()

    await expandAndSelect(wrapper, 'section_odds')

    const alert = wrapper.get('[data-testid="preview-regeneration-bundle-error"]')
    expect(alert.text()).toContain('읽지 못했습니다')
    expect(alert.text()).toContain('정보 원문 조회 실패(503)')
    expect(alert.text()).toContain('묶음 없음이 아닙니다')
    // 재사용 모드가 열리지 않는다(bundleId 없음).
    expect(wrapper.get('[data-testid="regen-stub"]').attributes('data-bundle-id')).toBe('')
  })

  it('run을 바꾸면 이전 run의 늦은 묶음 응답을 새 run에 붙이지 않는다', async () => {
    let finishOld: (value: ApiResult<unknown>) => void = () => undefined
    previewApi.informationBundle
      .mockImplementationOnce(
        () => new Promise<ApiResult<unknown>>((resolve) => { finishOld = resolve }),
      )
      .mockResolvedValueOnce(ok(bundlePayload('bundle-new-run')))
    const wrapper = await openRunForRegeneration()

    await expandAndSelect(wrapper, 'section_odds')
    // 첫 조회가 끝나기 전에 다른 run을 연다.
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-other')
    await submitOpenRun(wrapper)
    await flushPromises()
    await expandAndSelect(wrapper, 'section_odds')
    expect(wrapper.get('[data-testid="regen-stub"]').attributes('data-bundle-id')).toBe(
      'bundle-new-run',
    )

    // 이제서야 이전 run의 응답이 도착한다. 새 run 화면에 붙으면 안 된다.
    finishOld(ok(bundlePayload('bundle-old-run')))
    await flushPromises()
    expect(wrapper.get('[data-testid="regen-stub"]').attributes('data-bundle-id')).toBe(
      'bundle-new-run',
    )
  })

  it('다른 섹션의 현재 표시 버전을 selected_result_ids로 넘기고, 재생성 성공 뒤 새 실행을 열 수 있다', async () => {
    previewApi.informationBundle.mockResolvedValue(ok(bundlePayload('bundle-1')))
    const wrapper = await openRunForRegeneration()

    await expandAndSelect(wrapper, 'section_odds')

    // 화면이 보여주는 다른 섹션의 결과 ID만 넘긴다(재생성 대상 섹션은 뺀다).
    const selected = wrapper.get('[data-testid="regen-stub"]').attributes('data-selected') ?? ''
    expect(selected.split(',').filter(Boolean).sort()).toEqual(['sr-forecast', 'sr-players'])

    // 재생성 성공 이벤트 → 새 실행 열기 버튼이 나타난다(자동 열기 아님).
    const stub = wrapper.getComponent({ name: 'SectionRegenerationPanel' })
    stub.vm.$emit('regenerated', {
      run_id: 'run-regenerated-1',
      workflow_id: 'section_odds',
      workflow_version: 'section_odds@v2',
      mode: 'live',
      status: 'succeeded',
      quality: 'ready',
      section_result_id: 'result-new',
      section_result_version: 2,
      external_calls: 0,
      budget: {},
      unavailable_reason: null,
      note: '',
      no_model_call: true,
    })
    await flushPromises()

    // 열기 전에는 새 run을 읽지 않는다.
    expect(previewApi.readerPreview).toHaveBeenCalledTimes(1)
    const resultBlock = wrapper.get('[data-testid="preview-regeneration-result"]')
    expect(resultBlock.text()).toContain('run-regenerated-1')

    await wrapper.get('[data-testid="preview-regeneration-open"]').trigger('click')
    await flushPromises()
    expect(previewApi.readerPreview).toHaveBeenLastCalledWith('run-regenerated-1')
  })
})

describe('프리뷰 탭 — 관리 화면 경계', () => {
  const failingApi: ManagementApi = {
    catalog: vi.fn().mockRejectedValue(new Error('카탈로그 조회 실패')),
    refreshCatalog: vi.fn(),
    targets: vi.fn().mockRejectedValue(new Error('대상 조회 실패')),
    saveTarget: vi.fn(),
    toggleTarget: vi.fn(),
    removeTarget: vi.fn(),
    run: vi.fn(),
    runs: vi.fn().mockRejectedValue(new Error('실행 조회 실패')),
    start: vi.fn(),
    cancel: vi.fn(),
    translationAffiliationFilters: vi.fn(),
    translations: vi.fn().mockRejectedValue(new Error('번역 조회 실패')),
    saveTranslation: vi.fn(),
    translationHistory: vi.fn(),
  } as unknown as ManagementApi

  /**
   * 관리 화면을 그 역할로 마운트한다. 인증 store는 **마운트 전에** 정한다(마운트 중
   * `verifySession`이 실제 네트워크를 타지 않게 하려는 것도 같은 이유다).
   */
  async function mountManagement(role: 'ADMIN' | 'STREAMER', tab: string) {
    currentQuery.value = { tab }
    const pinia = createPinia()
    setActivePinia(pinia)
    const { useAuthStore } = await import('@/stores/auth')
    const auth = useAuthStore()
    auth.role = role
    auth.verified = true
    const wrapper = mount(ManagementView, {
      props: { api: failingApi },
      global: {
        plugins: [pinia],
        stubs: {
          RouterLink: { template: '<a><slot /></a>' },
          TargetsPanel: true,
          ExecutionPanel: true,
          HistoryPanel: true,
          TranslationsPanel: true,
        },
      },
    })
    return wrapper
  }

  it('기존 관리 API 조회가 실패해도 프리뷰 탭은 열린다', async () => {
    const wrapper = await mountManagement('ADMIN', 'preview')
    await flushPromises()

    expect(wrapper.find('[data-testid="preview-panel"]').exists()).toBe(true)
    // ADMIN에게는 프리뷰 탭 자체가 보인다.
    expect(wrapper.find('[data-testid="management-tab-preview"]').exists()).toBe(true)
    // 다른 탭의 조회는 아예 나가지 않는다(실패할 조회를 기다리지 않는다).
    expect(failingApi.targets).not.toHaveBeenCalled()
    expect(failingApi.translations).not.toHaveBeenCalled()
    // 다른 탭 데이터를 읽으려다 실패한 흔적이 프리뷰를 가리지 않는다.
    expect(wrapper.text()).not.toContain('관리 데이터를 확인하지 못했습니다')
    expect(previewApi.fixture).not.toHaveBeenCalled()
  })

  it('STREAMER에게는 프리뷰 탭과 생성 UI가 보이지 않는다', async () => {
    const wrapper = await mountManagement('STREAMER', 'preview')
    await flushPromises()

    expect(wrapper.find('[data-testid="management-tab-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-panel"]').exists()).toBe(false)
  })
})

describe('프리뷰 탭 — 실행 전환 비움 및 홈 반영 상태', () => {
  it('실행을 전환할 때 새 응답 전까지 이전 실행 본문을 비우고 늦은 이전 응답을 무시한다', async () => {
    previewApi.readerPreview.mockImplementation((runId: string) => {
      if (runId === 'run-1557474-a') {
        return Promise.resolve(
          ok(
            readerPreview({
              headline: '첫 실행 제목',
              sections: [
                {
                  section_id: 'section_ai_forecast',
                  title: 'AI 경기 전망',
                  body: '첫 실행 고유 본문',
                  sources: [],
                  quality: 'ready',
                  partial: false,
                  version: 1,
                },
              ],
            }),
          ),
        )
      }
      return new Promise(() => undefined)
    })
    previewApi.sectionResults.mockResolvedValue(ok({ run_id: 'run-1557474-a', section_results: [] }))
    previewApi.detail.mockResolvedValue(ok(runDetail()))

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('첫 실행 고유 본문')

    // 두 번째 실행을 열면 응답 도착 전 즉시 이전 본문과 홈 반영 박스가 비워져야 한다.
    let resolveSecond: (value: ApiResult<ReaderPreview>) => void = () => undefined
    previewApi.readerPreview.mockImplementationOnce(
      () => new Promise<ApiResult<ReaderPreview>>((resolve) => { resolveSecond = resolve }),
    )
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-b')
    await wrapper.get('[data-testid="preview-run-form"]').trigger('submit')

    expect(wrapper.find('[data-testid="preview-body"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-run-loading"]').exists()).toBe(true)

    resolveSecond(
      ok(
        readerPreview({
          headline: '둘째 실행 제목',
          sections: [
            {
              section_id: 'section_ai_forecast',
              title: 'AI 경기 전망',
              body: '둘째 실행 본문',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('둘째 실행 본문')
    expect(wrapper.get('[data-testid="preview-body"]').text()).not.toContain('첫 실행 고유 본문')
  })

  it('같은 관리자 화면에서 홈 반영 상태(부분 반영·미승인·오류·선수 NULL 안내)를 구분해 보여준다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    homePreviewApi.getHomePreviewDocument.mockResolvedValue({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'available',
      reason: null,
      reason_text: null,
      saved_at: '2026-11-18T00:00:00Z',
      run_id: 'run-1557474-a',
      complete: false,
      fixture: { external_id: 1557474 },
      headline: '전망',
      sections: [
        {
          section_result_id: 'sr-1',
          run_id: 'run-1557474-a',
          workflow_id: 'section_ai_forecast',
          workflow_version: 'v1',
          version: 1,
          title: 'AI 경기 전망',
          body: '본문',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
          structured: {
            structured_version: 'mp11-structured-2',
            workflow_id: 'section_players',
            players: [{ player: '조슈아 킹', reason: '복귀', unresolved: true, external_player_id: null, photo_url: null }],
            injuries: [],
            media: [],
            odds: [],
            forecast: null,
          },
        },
      ],
    })
    homePreviewApi.getHomeRecommendations.mockResolvedValue({
      schema_version: '1.0',
      requested_date: '2026-11-21',
      display_date: '2026-11-21',
      timezone: 'Asia/Seoul',
      as_of: '2026-11-18T00:00:00Z',
      policy_version: 'home-priority-2026-10-25',
      fallback_reason: null,
      items: [
        {
          fixture_id: 1557474,
          kickoff_at: '2026-11-21T12:30:00Z',
          status_as_of: '2026-11-18T00:00:00Z',
          competition: { external_id: 39, name: 'Premier League', category: 'epl', round: '12' },
          home: { external_id: 50, name: '맨체스터 시티' },
          away: { external_id: 36, name: '풀럼' },
          state: 'scheduled',
          priority: 1,
          reason: '빅식스',
          preview: {
            state: 'partial',
            served: 'current',
            generated_at: '2026-11-18T00:00:00Z',
            as_of: '2026-11-18T00:00:00Z',
          },
        },
      ],
      today_results: [],
    })

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    const panel = wrapper.get('[data-testid="preview-home-reflection"]')
    expect(panel.get('[data-testid="preview-home-document-status"]').text()).toContain('부분 반영(complete=false')
    expect(panel.get('[data-testid="preview-home-recommendation-status"]').text()).toContain('partial')
    expect(panel.find('[data-testid="preview-home-unresolved-note"]').exists()).toBe(true)
    expect(panel.find('[data-testid="preview-home-link"]').exists()).toBe(true)

    // 미승인 상태 새로고침
    homePreviewApi.getHomePreviewDocument.mockResolvedValueOnce({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'none',
      reason: 'no_approved_version',
      reason_text: '승인된 워크플로우 버전의 저장 문서가 없습니다.',
      absence: { state: 'upcoming', remaining_seconds: 86400 },
      saved_at: null,
      run_id: null,
      complete: null,
      fixture: { external_id: 1557474 },
      headline: null,
      sections: [],
    })
    homePreviewApi.getHomeRecommendations.mockRejectedValueOnce(new Error('home_preview_http_503'))
    await wrapper.get('[data-testid="preview-home-reflection-refresh"]').trigger('click')
    await flushPromises()

    expect(panel.get('[data-testid="preview-home-document-status"]').text()).toContain('no_approved_version')
    expect(panel.get('[data-testid="preview-home-recommendations-error"]').text()).toContain('home_preview_http_503')
  })

  it('as_of가 null이면 자료 기준 미기록으로 표시한다', async () => {
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview()))
    previewApi.sectionResults.mockResolvedValue(ok(savedSections()))
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    homePreviewApi.getHomePreviewDocument.mockResolvedValue({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'available',
      reason: null,
      reason_text: null,
      saved_at: '2026-11-18T00:00:00Z',
      run_id: 'run-1557474-a',
      complete: true,
      fixture: { external_id: 1557474 },
      headline: '전망',
      sections: [],
    })
    homePreviewApi.getHomeRecommendations.mockResolvedValue({
      schema_version: '1.0',
      requested_date: '2026-11-21',
      display_date: '2026-11-21',
      timezone: 'Asia/Seoul',
      as_of: '2026-11-18T00:00:00Z',
      policy_version: 'home-priority-2026-10-25',
      fallback_reason: null,
      items: [
        {
          fixture_id: 1557474,
          kickoff_at: '2026-11-21T12:30:00Z',
          status_as_of: '2026-11-18T00:00:00Z',
          competition: { external_id: 39, name: 'Premier League', category: 'epl', round: '12' },
          home: { external_id: 50, name: '맨체스터 시티' },
          away: { external_id: 36, name: '풀럼' },
          state: 'scheduled',
          priority: 1,
          reason: '빅식스',
          preview: {
            state: 'ready',
            served: 'current',
            generated_at: '2026-11-18T00:00:00Z',
            as_of: null,
          },
        },
      ],
      today_results: [],
    })

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    expect(wrapper.get('[data-testid="preview-home-recommendation-status"]').text()).toContain('자료 기준 미기록')
  })

  it('같은 run_id와 complete=true여도 선택 섹션 누락·다른 section_result_id·구성본 기준·조회 실패를 구분한다', async () => {
    const availabilityRow = sectionResult({
      section_result_id: 'sr-availability',
      workflow_id: 'section_availability',
      title: '결장·부상',
      body: '출전 의심 1명',
      unavailable: false,
    })
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview({ complete: true })))
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-a',
        section_results: [...savedSections().section_results, availabilityRow],
      }),
    )
    previewApi.detail.mockResolvedValue(ok(runDetail()))
    homePreviewApi.getHomePreviewDocument.mockResolvedValue({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'available',
      reason: null,
      reason_text: null,
      saved_at: '2026-11-18T00:00:00Z',
      run_id: 'run-1557474-a',
      complete: true,
      fixture: { external_id: 1557474 },
      headline: '전망',
      sections: [
        {
          section_result_id: 'sr-players',
          run_id: 'run-1557474-a',
          workflow_id: 'section_players',
          workflow_version: 'v1',
          version: 1,
          title: '주목 선수',
          body: '본문',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
        {
          section_result_id: 'sr-forecast',
          run_id: 'run-1557474-a',
          workflow_id: 'section_ai_forecast',
          workflow_version: 'v1',
          version: 1,
          title: 'AI 경기 전망',
          body: '본문',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
      ],
    })
    homePreviewApi.getHomeRecommendations.mockResolvedValue({
      schema_version: '1.0',
      requested_date: '2026-11-21',
      display_date: '2026-11-21',
      timezone: 'Asia/Seoul',
      as_of: '2026-11-18T00:00:00Z',
      policy_version: 'home-priority-2026-10-25',
      fallback_reason: null,
      items: [],
      today_results: [],
    })

    // 1) 같은 run_id + complete=true 여도 section_availability 누락을 그대로 표시
    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    const statusText = wrapper.get('[data-testid="preview-home-document-status"]').text()
    expect(statusText).toContain('누락')
    expect(statusText).toContain('section_availability')
    expect(statusText).not.toContain('일치합니다')
    expect(wrapper.get('[data-testid="preview-home-section-diff-section_availability"]').text()).toContain('누락')
    expect(wrapper.get('[data-testid="preview-home-section-diff-section_players"]').text()).toContain('일치')

    // 2) 같은 workflow_id의 다른 section_result_id면 '다른 버전' 표시
    homePreviewApi.getHomePreviewDocument.mockResolvedValueOnce({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'available',
      reason: null,
      reason_text: null,
      saved_at: '2026-11-18T00:00:00Z',
      run_id: 'run-1557474-a',
      complete: true,
      fixture: { external_id: 1557474 },
      headline: '전망',
      sections: [
        {
          section_result_id: 'sr-players',
          run_id: 'run-1557474-a',
          workflow_id: 'section_players',
          workflow_version: 'v1',
          version: 1,
          title: '주목 선수',
          body: '본문',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
        {
          section_result_id: 'sr-availability',
          run_id: 'run-1557474-a',
          workflow_id: 'section_availability',
          workflow_version: 'v1',
          version: 1,
          title: '결장·부상',
          body: '출전 의심 1명',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
        {
          section_result_id: 'sr-forecast-old',
          run_id: 'run-1557474-a',
          workflow_id: 'section_ai_forecast',
          workflow_version: 'v1',
          version: 1,
          title: 'AI 경기 전망',
          body: '구본문',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
      ],
    })
    await wrapper.get('[data-testid="preview-home-reflection-refresh"]').trigger('click')
    await flushPromises()
    const diffForecast = wrapper.get('[data-testid="preview-home-section-diff-section_ai_forecast"]').text()
    expect(diffForecast).toContain('다른 버전')
    expect(diffForecast).toContain('sr-forecast')
    expect(diffForecast).toContain('sr-forecast-old')

    // 3) 활성 구성본이 있으면 구성본 항목만 기준으로 대조하고 과거 미선택 버전은 무시한다
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-b',
        section_results: [
          sectionResult({ section_result_id: 'sr-forecast-v1', workflow_id: 'section_ai_forecast', version: 1, body: '구버전' }),
          sectionResult({ section_result_id: 'sr-forecast-v2', workflow_id: 'section_ai_forecast', version: 2, body: '신버전' }),
        ],
      }),
    )
    previewApi.readerPreview.mockResolvedValue(ok(readerPreview({ complete: false })))
    previewApi.detail.mockResolvedValue(ok({ ...runDetail(), summary: { ...runDetail().summary, run_id: 'run-1557474-b' } }))
    previewApi.composition.mockResolvedValue(
      ok({
        run_id: 'run-1557474-b',
        available: true,
        reason: null,
        composition: {
          composition_id: 'comp-1',
          fixture_id: 1557474,
          items: [
            {
              section_id: 'section_ai_forecast',
              result_id: 'sr-forecast-v2',
              run_id: 'run-1557474-b',
              fixture_id: 1557474,
              version: 2,
              workflow_version: 'v1',
              quality: 'ready',
              unavailable: false,
              unavailable_reason: null,
              body_chars: 10,
              mode: 'live',
              created_at: '2026-11-18T00:00:00Z',
            },
          ],
          refused: [],
          diagnostics: [],
          section_result_ids: ['sr-forecast-v2'],
        },
      }),
    )
    homePreviewApi.getHomePreviewDocument.mockResolvedValue({
      schema_version: '1.0',
      fixture_id: 1557474,
      status: 'available',
      reason: null,
      reason_text: null,
      saved_at: '2026-11-18T00:00:00Z',
      run_id: 'run-1557474-b',
      complete: false,
      fixture: { external_id: 1557474 },
      headline: '전망',
      sections: [
        {
          section_result_id: 'sr-forecast-v2',
          run_id: 'run-1557474-b',
          workflow_id: 'section_ai_forecast',
          workflow_version: 'v1',
          version: 2,
          title: 'AI 경기 전망',
          body: '신버전',
          sources: [],
          quality: 'ready',
          partial: false,
          created_at: '2026-11-18T00:00:00Z',
        },
      ],
    })
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-b')
    await submitOpenRun(wrapper)
    expect(wrapper.get('[data-testid="preview-home-document-status"]').text()).toContain('일치합니다')
    expect(wrapper.get('[data-testid="preview-home-section-diff-section_ai_forecast"]').text()).toContain('일치')

    // 4) 구성본 조회 실패 시 대조 미확인 표시 + 늦은 이전 실행 구성본 응답 무시
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          complete: false,
          sections: [
            { section_id: 'section_ai_forecast', title: 'AI 경기 전망', body: '신버전', sources: [], quality: 'ready', partial: false, version: 2 },
          ],
        }),
      ),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-d',
        section_results: [
          sectionResult({ section_result_id: 'sr-forecast-v2', workflow_id: 'section_ai_forecast', version: 2, body: '신버전' }),
        ],
      }),
    )
    let resolveDelayedComp!: (v: unknown) => void
    previewApi.composition.mockImplementation((rid: string) => {
      if (rid === 'run-1557474-c') {
        return new Promise((resolve) => {
          resolveDelayedComp = resolve
        })
      }
      if (rid === 'run-1557474-d') {
        return Promise.resolve(fail(503, '구성본 서버 오류'))
      }
      return Promise.resolve(ok({ run_id: rid, available: false, reason: '구성본 없음', composition: null }))
    })
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-c')
    await wrapper.get('[data-testid="preview-run-form"]').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-d')
    await submitOpenRun(wrapper)
    resolveDelayedComp(ok({ run_id: 'run-1557474-c', available: false, reason: '이전 응답', composition: null }))
    await flushPromises()
    expect(wrapper.get('[data-testid="preview-home-document-status"]').text()).toContain('대조 미확인')
  })
})

describe('프리뷰 탭 — 섹션 워크플로우 승인 연동 및 중복 UI 차단', () => {
  // 이유: 프리뷰 탭에서 바로 승인 시 detail/홈 반영 GET이 함께 갱신되고 RunInspector 승인은 숨겨져야 한다.
  // 실패 시 사용자 결과: 승인 직후 홈 반영 여부를 알 수 없거나 한 화면에 승인 UI가 두 번 떠 다른 버전을 누를 수 있다.
  it('승인 성공 후 detail·홈 반영 GET을 함께 갱신하고 중첩 RunInspector 승인은 숨긴다', async () => {
    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            {
              section_id: 'section_players',
              title: '주목 선수',
              body: '저장된 주목 선수 본문',
              sources: [],
              quality: 'ready',
              partial: false,
              version: 1,
            },
          ],
        }),
      ),
    )
    previewApi.sectionResults.mockResolvedValue(
      ok({
        run_id: 'run-1557474-a',
        section_results: [
          sectionResult({
            section_result_id: 'sr-players-live',
            workflow_id: 'section_players',
            workflow_version: 'wfv-players-2',
            version: 1,
            title: '주목 선수',
            body: '저장된 주목 선수 본문',
            mode: 'live',
            approvable: true,
          }),
        ],
      }),
    )
    previewApi.detail
      .mockResolvedValueOnce(
        ok({
          ...runDetail(),
          fixture: {
            fixture_id: 1557474,
            kickoff_at: '2026-11-21T12:30:00Z',
            season: 2026,
            league_id: 39,
            home_team_id: 13,
            away_team_id: 4,
          },
          section_approvals: [
            {
              workflow_id: 'section_players',
              display_name: '주목 선수',
              description: '',
              module_ids: ['bundle_section_players'],
              implemented: true,
              unrunnable_reason: null,
              state: 'none',
              label: '미승인',
              detail: null,
              current_version: 'wfv-players-2',
              active_approval: null,
              pinned_approval: null,
              can_approve: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        ok({
          ...runDetail(),
          fixture: {
            fixture_id: 1557474,
            kickoff_at: '2026-11-21T12:30:00Z',
            season: 2026,
            league_id: 39,
            home_team_id: 13,
            away_team_id: 4,
          },
          section_approvals: [
            {
              workflow_id: 'section_players',
              display_name: '주목 선수',
              description: '',
              module_ids: ['bundle_section_players'],
              implemented: true,
              unrunnable_reason: null,
              state: 'approved',
              label: '승인됨',
              detail: null,
              current_version: 'wfv-players-2',
              active_approval: {
                approval_id: 'apr-1',
                workflow_id: 'section_players',
                workflow_version: 'wfv-players-2',
                constituents: [],
                evidence: {
                  run_id: 'run-1557474-a',
                  section_result_id: 'sr-players-live',
                  reviewed_at: '2026-11-18T03:20:00Z',
                },
                approved_by_actor_id: '1',
                approved_at: '2026-11-18T03:20:00Z',
                reviewed_note: '검토 완료',
                supersedes_approval_id: null,
              },
              pinned_approval: null,
              can_approve: true,
            },
          ],
        }),
      )
    previewApi.approveSection.mockResolvedValue(
      ok({
        approval_id: 'apr-1',
        workflow_id: 'section_players',
        workflow_version: 'wfv-players-2',
        constituents: [],
        evidence: {
          run_id: 'run-1557474-a',
          section_result_id: 'sr-players-live',
          reviewed_at: '2026-11-18T03:20:00Z',
        },
        approved_by_actor_id: '1',
        approved_at: '2026-11-18T03:20:00Z',
        reviewed_note: '검토 완료',
        supersedes_approval_id: null,
      }),
    )
    homePreviewApi.getHomePreviewDocument
      .mockResolvedValueOnce({ status: 'none', fixture_id: 1557474, reason: 'no_approved_version', reason_text: null, run_id: null, generated_at: null, data_as_of: null, complete: false, sections: [] })
      .mockResolvedValueOnce({
        schema_version: '1.0',
        status: 'available',
        fixture_id: 1557474,
        reason: null,
        reason_text: null,
        saved_at: '2026-11-18T03:20:00Z',
        run_id: 'run-1557474-a',
        complete: false,
        fixture: { external_id: 1557474 },
        headline: '전망',
        sections: [
          {
            section_result_id: 'sr-players-live',
            run_id: 'run-1557474-a',
            workflow_id: 'section_players',
            workflow_version: 'wfv-players-2',
            version: 1,
            title: '주목 선수',
            body: '저장된 주목 선수 본문',
            sources: [],
            quality: 'ready',
            partial: false,
            created_at: '2026-11-18T03:20:00Z',
          },
        ],
      })
    homePreviewApi.getHomeRecommendations.mockResolvedValue({ as_of: null, items: [] })

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    expect(wrapper.get('[data-testid="preview-home-document-status"]').text()).toContain('no_approved_version')
    expect(wrapper.get('[data-testid="preview-approval"]').text()).toContain('미승인')

    await wrapper.get('[data-testid="preview-approval-note"]').setValue('검토 완료')
    await wrapper.get('[data-testid="preview-approval-submit"]').trigger('click')
    await flushPromises()

    expectCalledOnceWith(previewApi.approveSection, 'section_players', {
      run_id: 'run-1557474-a',
      section_result_id: 'sr-players-live',
      note: '검토 완료',
    })
    expect(previewApi.runBundle).not.toHaveBeenCalled()
    expect(previewApi.detail).toHaveBeenCalledTimes(2)
    expect(homePreviewApi.getHomePreviewDocument).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="preview-approval-active-version"]').text()).toContain('wfv-players-2')
    expect(wrapper.get('[data-testid="preview-home-section-diff-section_players"]').text()).toContain('일치')

    // 진단의 RunInspector에는 hideApproval=true가 전달되어 중복 승인 UI를 숨긴다.
    const diag = wrapper.get('[data-testid="preview-diagnostics"]').element as HTMLDetailsElement
    diag.open = true
    await wrapper.get('[data-testid="preview-diagnostics"]').trigger('toggle')
    await flushPromises()
    const insp = wrapper.get('[data-testid="preview-inspector"]').element as HTMLDetailsElement
    insp.open = true
    await wrapper.get('[data-testid="preview-inspector"]').trigger('toggle')
    await flushPromises()
    expect(wrapper.get('[data-testid="inspector-stub"]').attributes('data-hide-approval')).toBe('true')
  })

  // 이유: 실서버 /section-results 응답에 approvable·mode_label이 빠져도 detail.section_results 및 cross-run 원 실행 detail에서 같은 (run_id, section_result_id)의 서버 판정을 정확히 결합해야 한다.
  // 실패 시 사용자 결과: 정상 ADMIN이 live/ready 본문을 보고도 승인 버튼이 잠겨 승인할 수 없거나, 원 실행에서 불가 판정한 cross-run 결과를 잘못 승인할 수 있다.
  it('실서버처럼 raw section-results에 approvable이 없어도 detail.section_results와 cross-run 원 실행 판정으로 정확히 승인 가능 여부를 결정한다', async () => {
    const rawPlayers = {
      ...sectionResult({
        section_result_id: 'sr-live-players',
        run_id: 'run-1557474-a',
        workflow_id: 'section_players',
        workflow_version: 'wfv-players-live',
        version: 1,
        title: '주목 선수',
        body: '실호출 주목 선수 본문',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    const rawParentAvail = {
      ...sectionResult({
        section_result_id: 'sr-parent-avail',
        run_id: 'run-parent-1',
        workflow_id: 'section_availability',
        workflow_version: 'wfv-avail-parent',
        version: 1,
        title: '출전 불가·부상 변수',
        body: '원 실행 출전 변수 본문',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    const rawParentUnconfirmed = {
      ...sectionResult({
        section_result_id: 'sr-parent-odds',
        run_id: 'run-parent-2',
        workflow_id: 'section_odds',
        workflow_version: 'wfv-odds-parent',
        version: 1,
        title: '배당 흐름',
        body: '미확인 원 실행 본문',
        mode: 'live',
      }),
      approvable: undefined,
      mode_label: undefined,
    } as unknown as SectionResultView

    previewApi.readerPreview.mockResolvedValue(
      ok(
        readerPreview({
          sections: [
            { section_id: 'section_players', title: '주목 선수', body: '실호출 주목 선수 본문', sources: [], quality: 'ready', partial: false, version: 1 },
            { section_id: 'section_availability', title: '출전 불가·부상 변수', body: '원 실행 출전 변수 본문', sources: [], quality: 'ready', partial: false, version: 1 },
            { section_id: 'section_odds', title: '배당 흐름', body: '미확인 원 실행 본문', sources: [], quality: 'ready', partial: false, version: 1 },
          ],
        }),
      ),
    )

    previewApi.sectionResults.mockImplementation((rid: string) => {
      if (rid === 'run-parent-1') {
        return Promise.resolve(ok({ run_id: 'run-parent-1', section_results: [rawParentAvail] }))
      }
      if (rid === 'run-parent-2') {
        return Promise.resolve(ok({ run_id: 'run-parent-2', section_results: [rawParentUnconfirmed] }))
      }
      return Promise.resolve(ok({ run_id: 'run-1557474-a', section_results: [rawPlayers] }))
    })

    previewApi.detail.mockImplementation((rid: string) => {
      if (rid === 'run-parent-1') {
        return Promise.resolve(
          ok({
            ...runDetail(),
            summary: { ...runDetail().summary, run_id: 'run-parent-1' },
            section_results: [
              sectionResult({
                section_result_id: 'sr-parent-avail',
                run_id: 'run-parent-1',
                workflow_id: 'section_availability',
                mode: 'live',
                mode_label: '실제 생성',
                approvable: true,
              }),
            ],
          }),
        )
      }
      if (rid === 'run-parent-2') {
        // 원 실행 detail에는 section_odds 행이 없으므로(같은 workflow_id가 openRun에 있더라도) 승인 불가여야 한다.
        return Promise.resolve(
          ok({
            ...runDetail(),
            summary: { ...runDetail().summary, run_id: 'run-parent-2' },
            section_results: [],
          }),
        )
      }
      return Promise.resolve(
        ok({
          ...runDetail(),
          section_results: [
            sectionResult({
              section_result_id: 'sr-live-players',
              run_id: 'run-1557474-a',
              workflow_id: 'section_players',
              mode: 'live',
              mode_label: '실제 생성',
              approvable: true,
            }),
            // cross-run section_odds와 workflow_id만 같고 result_id/run_id가 다른 행 — 절대 차용하면 안 된다.
            sectionResult({
              section_result_id: 'sr-other-odds-in-open-run',
              run_id: 'run-1557474-a',
              workflow_id: 'section_odds',
              mode: 'live',
              mode_label: '실제 생성',
              approvable: true,
            }),
          ],
          section_approvals: [
            {
              workflow_id: 'section_players',
              display_name: '주목 선수',
              description: '',
              module_ids: ['bundle_section_players'],
              implemented: true,
              unrunnable_reason: null,
              state: 'none',
              label: '미승인',
              detail: null,
              current_version: 'wfv-players-live',
              active_approval: null,
              pinned_approval: null,
              can_approve: true,
            },
            {
              workflow_id: 'section_availability',
              display_name: '출전 불가·부상 변수',
              description: '',
              module_ids: ['bundle_section_availability'],
              implemented: true,
              unrunnable_reason: null,
              state: 'none',
              label: '미승인',
              detail: null,
              current_version: 'wfv-avail-parent',
              active_approval: null,
              pinned_approval: null,
              can_approve: true,
            },
            {
              workflow_id: 'section_odds',
              display_name: '배당 흐름',
              description: '',
              module_ids: ['bundle_section_odds'],
              implemented: true,
              unrunnable_reason: null,
              state: 'none',
              label: '미승인',
              detail: null,
              current_version: 'wfv-odds-parent',
              active_approval: null,
              pinned_approval: null,
              can_approve: true,
            },
          ],
        }),
      )
    })

    previewApi.composition.mockResolvedValue(
      ok({
        run_id: 'run-1557474-a',
        available: true,
        reason: null,
        composition: {
          composition_id: 'comp-live-check',
          fixture_id: 1557474,
          items: [
            {
              section_id: 'section_players',
              result_id: 'sr-live-players',
              run_id: 'run-1557474-a',
              fixture_id: 1557474,
              version: 1,
              workflow_version: 'wfv-players-live',
              quality: 'ready',
              unavailable: false,
              unavailable_reason: null,
              body_chars: 12,
              mode: 'live',
              created_at: null,
            },
            {
              section_id: 'section_availability',
              result_id: 'sr-parent-avail',
              run_id: 'run-parent-1',
              fixture_id: 1557474,
              version: 1,
              workflow_version: 'wfv-avail-parent',
              quality: 'ready',
              unavailable: false,
              unavailable_reason: null,
              body_chars: 12,
              mode: 'live',
              created_at: null,
            },
            {
              section_id: 'section_odds',
              result_id: 'sr-parent-odds',
              run_id: 'run-parent-2',
              fixture_id: 1557474,
              version: 1,
              workflow_version: 'wfv-odds-parent',
              quality: 'ready',
              unavailable: false,
              unavailable_reason: null,
              body_chars: 12,
              mode: 'live',
              created_at: null,
            },
          ],
          refused: [],
          diagnostics: [],
          section_result_ids: ['sr-live-players', 'sr-parent-avail', 'sr-parent-odds'],
        },
      }),
    )

    const wrapper = mount(PreviewPanel, mountOptions())
    await wrapper.get('[data-testid="preview-run-id"]').setValue('run-1557474-a')
    await submitOpenRun(wrapper)

    // 1) openRunId의 raw section_players + detail.section_results 일치 -> 승인 가능 + mode_label 결합
    expect(wrapper.get('[data-testid="preview-approval-target-result"]').text()).toContain('실제 생성')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(false)

    // 2) cross-run section_availability + run-parent-1 detail 일치 -> 승인 가능
    await wrapper.get('[data-testid="preview-approval-item-section_availability"]').trigger('click')
    expect(wrapper.get('[data-testid="preview-approval-target-run"]').text()).toContain('run-parent-1')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(false)

    // 3) cross-run section_odds의 원 실행 detail(run-parent-2)에 해당 결과 없음 -> openRunId의 같은 workflow_id 판정을 빌려오지 않고 차단
    await wrapper.get('[data-testid="preview-approval-item-section_odds"]').trigger('click')
    expect((wrapper.get('[data-testid="preview-approval-submit"]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.get('[data-testid="preview-approval-blocked-reason"]').text()).toContain('approvable=true')
  })
})
