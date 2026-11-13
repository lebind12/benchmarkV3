/**
 * MP-09 독자용 프리뷰 화면 검사.
 *
 * 이 파일이 확인하는 것:
 * - 독자용 본문·관전 포인트·주목 선수·외부 전망·AI 예측이 화면에 보인다.
 * - 없는 보조 항목은 **카드 자체를 만들지 않는다**(빈 카드·누락 배너 금지).
 * - 진단은 접힌 영역에서 별도 경로로 열고, 처음에는 DOM에 넣지 않는다.
 * - AI 예측은 "AI 예측" 표시와 판단 이유를 함께 보여준다.
 * - 제공자 알고리즘 예측은 매체 전망과 다른 표시를 갖는다.
 * - 조회 실패는 빈 프리뷰로 꾸미지 않고 오류를 그대로 알린다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const readerPreviewMock = vi.fn()
const diagnosticsMock = vi.fn()

vi.mock('@/features/match-preview/api', () => ({
  previewRunsApi: {
    readerPreview: (...args: unknown[]) => readerPreviewMock(...args),
    readerPreviewDiagnostics: (...args: unknown[]) => diagnosticsMock(...args),
  },
}))

import MatchPreview from '@/features/match-preview/MatchPreview.vue'

const PREVIEW = {
  fixture: {
    fixture_id: 1557474,
    home_team_id: 13,
    away_team_id: 4,
    league_id: 1,
    season: 2026,
    kickoff_at: '2026-11-21T12:30:00+00:00',
    label: 'Manchester City vs Fulham',
    league: 'Premier League',
  },
  headline: '리그 3위 Manchester City가 홈에서 하위권 Fulham을 상대합니다.',
  generated_at: '2026-11-10T12:30:00+00:00',
  data_as_of: '2026-11-10T12:00:00+00:00',
  attribution: {
    ai_forecast_label: 'AI 예측',
    ai_forecast_note: '관전 포인트와 예상은 확인된 자료를 바탕으로 한 AI 판단이며, 경기 결과를 보장하지 않습니다.',
    model: 'recorded-model',
    provider: 'recorded-model',
    executed_at: '2026-11-10T12:30:00+00:00',
  },
  body: '리그 3위 Manchester City가 홈에서 하위권 Fulham을 상대합니다.\n\n관전 포인트. 홈에서 볼 점유를 오래 가져가는 흐름을 볼 만합니다.',
  watch_points: ['Manchester City가 홈에서 볼 점유를 오래 가져가는 흐름을 볼 만합니다.'],
  players_to_watch: [
    {
      player: 'Erling Haaland',
      team: 'Manchester City',
      reason: '상대 수비가 내려서는 경기에서 먼저 지켜볼 선수입니다.',
    },
  ],
  absences_impact: 'Manchester City는 왼쪽 수비 자원이 줄어 측면 대응이 달라질 수 있습니다.',
  external_outlook: [
    {
      publisher: 'BBC Sport',
      statement: 'Manchester City가 홈에서 우세할 것으로 전망했습니다.',
      source_kind: 'external_forecast',
      published_at: '2026-11-09',
      url: 'https://www.bbc.com/sport/football/manchester-city-fulham-preview',
    },
    {
      publisher: 'API-Football',
      statement: '알고리즘은 홈팀 우세로 계산했습니다.',
      source_kind: 'api_prediction',
      source_note: '제공자 알고리즘 예측이며 매체 의견이 아닙니다.',
    },
  ],
  ai_prediction: {
    lean: 'home',
    score: '2-1',
    reasoning: ['상대가 하위권이고 홈 이점이 있어 홈팀 우세로 봅니다.'],
    note: '예상은 결과를 보장하지 않습니다.',
  },
  sources: [
    {
      label: 'Manchester City vs Fulham preview',
      kind: 'search',
      url: 'https://www.bbc.com/sport/football/manchester-city-fulham-preview',
      note: 'Google Search grounding이 제공한 출처입니다.',
    },
    {
      label: 'API-Football 저장 자료',
      kind: 'api',
      note: '수집 2026-11-10 · 저장 자료',
      observed_at: '2026-11-10T12:00:00+00:00',
    },
  ],
}

async function mountWith(runId = 'run-1') {
  const wrapper = mount(MatchPreview, { props: { runId } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  readerPreviewMock.mockReset()
  diagnosticsMock.mockReset()
})

describe('MatchPreview', () => {
  it('shows the reader body, watch points, players and forecast', async () => {
    readerPreviewMock.mockResolvedValue({ ok: true, data: PREVIEW })
    const wrapper = await mountWith()

    expect(wrapper.get('[data-testid="preview-headline"]').text()).toContain('Manchester City')
    expect(wrapper.get('[data-testid="preview-body"]').text()).toContain('관전 포인트.')
    expect(wrapper.get('[data-testid="preview-watch-points"]').text()).toContain('볼 점유')
    expect(wrapper.get('[data-testid="preview-players"]').text()).toContain('Erling Haaland')
    expect(wrapper.get('[data-testid="preview-absences"]').text()).toContain('왼쪽 수비')
    expect(wrapper.get('[data-testid="preview-outlook"]').text()).toContain('BBC Sport')
    expect(wrapper.get('[data-testid="preview-forecast"]').text()).toContain('AI 예측')
    expect(wrapper.get('[data-testid="preview-forecast"]').text()).toContain('2-1')
    expect(wrapper.get('[data-testid="preview-reasoning"]').text()).toContain('홈 이점')
    // 출처 목록은 접히지 않고 본문 아래에 그대로 보인다.
    expect(wrapper.get('[data-testid="preview-sources"]').text()).toContain('저장 자료')
  })

  it('omits cards for absent optional sections instead of showing empty state', async () => {
    readerPreviewMock.mockResolvedValue({
      ok: true,
      data: {
        ...PREVIEW,
        watch_points: [],
        players_to_watch: [],
        absences_impact: undefined,
        external_outlook: [],
        ai_prediction: { lean: 'home', score: null, reasoning: ['홈 이점이 있습니다.'] },
        sources: [],
      },
    })
    const wrapper = await mountWith()

    expect(wrapper.find('[data-testid="preview-watch-points"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-players"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-absences"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-outlook"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-sources"]').exists()).toBe(false)
    // AI 예측은 남는다(자료가 아니라 판단이므로).
    expect(wrapper.get('[data-testid="preview-forecast"]').text()).toContain('AI 예측')
    // 누락을 알리는 운영 문구를 만들지 않는다.
    const text = wrapper.text()
    for (const forbidden of ['자료 없음', '미확보', '누락', '불러오지 못']) {
      expect(text).not.toContain(forbidden)
    }
  })

  it('shows the odds table only when the server provides regular-time 1X2 values', async () => {
    readerPreviewMock.mockResolvedValue({
      ok: true,
      data: {
        ...PREVIEW,
        odds: [
          {
            bookmaker: 'example-book',
            market: '1x2_regulation',
            observed_at: '2026-11-11T00:00:00+00:00',
            home: '1.72',
            draw: '3.90',
            away: '4.60',
          },
          // 값이 전혀 없는 줄은 표에 넣지 않는다(추정 금지).
          { bookmaker: 'undecided-book' },
        ],
      },
    })
    const wrapper = await mountWith()

    const odds = wrapper.get('[data-testid="preview-odds"]')
    expect(odds.text()).toContain('example-book')
    expect(odds.text()).toContain('1.72')
    expect(odds.text()).not.toContain('undecided-book')
  })

  it('omits the odds card entirely when the server sends no odds', async () => {
    readerPreviewMock.mockResolvedValue({ ok: true, data: PREVIEW })
    const wrapper = await mountWith()
    expect(wrapper.find('[data-testid="preview-odds"]').exists()).toBe(false)
  })

  it('keeps diagnostics out of the initial DOM and loads them on demand', async () => {
    readerPreviewMock.mockResolvedValue({ ok: true, data: PREVIEW })
    diagnosticsMock.mockResolvedValue({
      ok: true,
      data: {
        run_id: 'run-1',
        workflow_id: 'section_synthesis',
        workflow_version: 'section_synthesis@abc',
        section_result_id: 'section-1',
        mode: { mode: 'mock', label: '모의 자료 (mock, 외부 호출 없음)' },
        quality: { run: 'succeeded', section: 'ready' },
        gaps: [{ module_id: 'R3', reason: '배당 자료가 제공되지 않았습니다.' }],
        excluded_claims: [],
        diagnostics: ['검색 인용 출처를 확인하지 못했습니다.'],
        unavailable_reason: null,
        selected_inputs: [
          {
            module_id: 'R1',
            result_id: 'res-1',
            version: 2,
            implementation_version: 'mp05-form-2',
            prompt_version: 'mp05-form-prompt-2',
            quality: 'ready',
            adopted_claim_count: 3,
            excluded_claim_count: 1,
          },
        ],
        contract_versions: { contract: 'mp02-1' },
        synthesis_versions: {
          implementation: 'mp09-s1-1',
          prompt: 'mp09-s1-prompt-1',
          output_contract: 'mp09-synthesis-output-1',
        },
        attempts_present: true,
      },
    })
    const wrapper = await mountWith()

    // 처음에는 진단을 요청하지도, DOM에 넣지도 않는다.
    expect(diagnosticsMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="preview-diagnostics-inputs"]').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('mp09-s1-1')

    await wrapper.get('[data-testid="preview-diagnostics-toggle"]').trigger('click')
    await flushPromises()

    expect(diagnosticsMock).toHaveBeenCalledWith('run-1')
    expect(wrapper.get('[data-testid="preview-diagnostics-mode"]').text()).toContain('mock')
    expect(wrapper.get('[data-testid="preview-diagnostics-inputs"]').text()).toContain('R1')
    expect(wrapper.get('[data-testid="preview-diagnostics-gaps"]').text()).toContain('배당')
  })

  it('marks algorithmic provider predictions apart from media forecasts', async () => {
    readerPreviewMock.mockResolvedValue({ ok: true, data: PREVIEW })
    const wrapper = await mountWith()
    const outlook = wrapper.get('[data-testid="preview-outlook"]').text()
    expect(outlook).toContain('알고리즘 예측')
    expect(outlook).toContain('BBC Sport')
  })

  it('does not fabricate a preview when the run has none', async () => {
    readerPreviewMock.mockResolvedValue({
      ok: false,
      kind: 'unknown',
      status: 404,
      message: '이 실행에는 독자용 프리뷰 결과가 없습니다. 종합 섹션을 먼저 실행해야 합니다.',
    })
    const wrapper = await mountWith('run-empty')

    expect(wrapper.get('[data-testid="preview-error"]').text()).toContain('프리뷰를 열 수 없습니다')
    expect(wrapper.find('[data-testid="preview-body"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="preview-forecast"]').exists()).toBe(false)
  })

  it('does not call the API without a run id', async () => {
    const wrapper = await mountWith('')
    expect(readerPreviewMock).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="preview-body"]').exists()).toBe(false)
  })
})
