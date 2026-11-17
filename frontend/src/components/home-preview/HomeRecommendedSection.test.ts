import { describe, expect, it, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

/**
 * 홈 추천 경기의 저장 문서 분기 검사.
 *
 * 검사 이유(실패 시 사용자 영향): 저장 문서가 없는 경기와 조회가 실패한 경기를 같은
 * 화면으로 보여주면, 일시적 장애가 "생성 예정" 안내로 위장되어 사용자가 기다리면 되는
 * 상황과 확인이 필요한 상황을 구분하지 못한다.
 *
 * 저장 문서 응답만 바꿔 끼우고 나머지는 그대로 둔다. 이 검사는 GET 클라이언트를
 * mock하므로 실제 서버·DB를 호출하지 않는다.
 */

const recommendations = {
  schema_version: '1.0',
  requested_date: '2026-11-13',
  display_date: '2026-11-13',
  timezone: 'Asia/Seoul',
  as_of: '2026-11-13T00:00:00Z',
  policy_version: 'home-priority-2026-10-25',
  fallback_reason: null,
  items: [
    {
      fixture_id: 90001,
      kickoff_at: '2026-11-13T11:00:00Z',
      status_as_of: '2026-11-13T00:00:00Z',
      competition: { external_id: 39, name: '프리미어리그', category: 'epl', round: '38' },
      home: { external_id: 50, name: '맨체스터 시티' },
      away: { external_id: 36, name: '풀럼' },
      state: 'scheduled',
      priority: 1,
      reason: '빅6 EPL 경기',
      preview: { state: 'pending', served: null, generated_at: null, as_of: null },
    },
  ],
  today_results: [],
}

/** 두 경기 추천. 경기 전환 중 늦은 응답 가드를 검사하기 위한 입력이다. */
function twoMatchRecommendations() {
  const second = {
    ...recommendations.items[0]!,
    fixture_id: 90002,
    home: { external_id: 42, name: '아스널' },
    away: { external_id: 33, name: '브렌트퍼드' },
  }
  return { ...recommendations, items: [recommendations.items[0]!, second] }
}

const getHomePreviewDocument = vi.fn()
const getHomeRecommendations = vi.fn()

vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return { ...actual, RouterLink: { template: '<a><slot /></a>' } }
})

vi.mock('@/lib/api/homePreview', () => ({
  getHomeRecommendations: (...args: unknown[]) => getHomeRecommendations(...args),
  getHomePreviewDocument: (...args: unknown[]) => getHomePreviewDocument(...args),
}))

const storedDocument = {
  schema_version: '1.0',
  fixture_id: 90001,
  status: 'available',
  reason: null,
  reason_text: null,
  saved_at: '2026-11-12T12:00:00Z',
  run_id: 'run-1',
  complete: true,
  fixture: {
    external_id: 90001,
    kickoff_at: '2026-11-13T11:00:00Z',
    league: '프리미어리그',
    home: { external_id: 50, name: '맨체스터 시티', logo_url: null },
    away: { external_id: 36, name: '풀럼', logo_url: null },
  },
  headline: '주목 선수',
  sections: [
    {
      section_result_id: 's1',
      run_id: 'run-1',
      workflow_id: 'section_players',
      workflow_version: 'v1',
      version: 1,
      title: '주목 선수',
      body: '저장된 본문 문단',
      sources: [],
      quality: 'ready',
      partial: false,
      created_at: '2026-11-12T12:00:00Z',
    },
  ],
}

// jsdom에는 matchMedia가 없다. 컴포넌트는 모션 설정을 읽기만 하므로 최소 구현을 세운다.
function installMatchMedia() {
  if (typeof window.matchMedia === 'function') return
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

async function mountSection() {
  const { default: HomeRecommendedSection } = await import(
    '@/components/home-preview/HomeRecommendedSection.vue'
  )
  installMatchMedia()
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(HomeRecommendedSection, {
    global: {
      plugins: [pinia],
      stubs: { BroadcastPickerButton: true },
    },
  })
}

describe('home recommended section stored document states', () => {
  beforeEach(() => {
    getHomeRecommendations.mockResolvedValue(recommendations)
      getHomePreviewDocument.mockReset()
  })

  it('renders the stored body when a document exists', async () => {
    getHomePreviewDocument.mockResolvedValue(storedDocument)
    const wrapper = await mountSection()
    await flushPromises()
    expect(wrapper.find('[data-testid="stored-preview-document"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('저장된 본문 문단')
  })

  it('shows one absence notice with no body, cards, or buttons', async () => {
    getHomePreviewDocument.mockResolvedValue({
      ...storedDocument,
      status: 'none',
      reason: 'no_stored_run',
      reason_text: '이 경기의 저장 실행이 없습니다.',
      absence: { state: 'upcoming', remaining_seconds: 259200 },
      saved_at: null,
      run_id: null,
      complete: null,
      headline: null,
      sections: [],
    })
    const wrapper = await mountSection()
    await flushPromises()
    expect(wrapper.find('[data-testid="stored-preview-document"]').exists()).toBe(false)
    const absent = wrapper.find('[data-testid="stored-document-absent"]')
    expect(absent.exists()).toBe(true)
    expect(absent.text()).toContain('킥오프 6시간')
    // 빈 본문 카드와 재확인 버튼을 붙이지 않는다.
    expect(absent.find('button').exists()).toBe(false)
  })

  it('shows the not-yet-generated notice inside the 6 hour window', async () => {
    getHomePreviewDocument.mockResolvedValue({
      ...storedDocument,
      status: 'none',
      reason: 'no_stored_run',
      reason_text: '이 경기의 저장 실행이 없습니다.',
      absence: { state: 'upcoming_overdue', remaining_seconds: 3600 },
      saved_at: null,
      run_id: null,
      complete: null,
      headline: null,
      sections: [],
    })
    const wrapper = await mountSection()
    await flushPromises()
    // 기본 생성 시점 설명 대신 미생성 문제 안내를 쓴다.
    expect(wrapper.text()).toContain('아직 생성되지 않았습니다')
    // 실제 실패 근거가 없으므로 생성 실패로 단정하지 않는다.
    expect(wrapper.text()).not.toContain('실패했습니다')
  })

  it('keeps a read failure separate from absence and offers a retry', async () => {
    getHomePreviewDocument.mockRejectedValue(new Error('home_preview_http_503'))
    const wrapper = await mountSection()
    await flushPromises()
    const error = wrapper.find('[data-testid="stored-document-error"]')
    expect(error.exists()).toBe(true)
    expect(error.text()).toContain('다시 확인')
    // 조회 실패를 '문서 없음' 6시간 안내로 바꾸지 않는다.
    expect(wrapper.text()).not.toContain('저장 실행이 없습니다')
  })

  it('keeps the newly selected fixture body when the previous response arrives late', async () => {
    const twoMatches = twoMatchRecommendations()
    getHomeRecommendations.mockResolvedValue(twoMatches)

    // 첫 경기 문서 응답을 붙잡아 두고, 둘째 경기로 전환한 뒤 늦게 resolve한다.
    let releaseFirst: (value: unknown) => void = () => {}
    const held = new Promise((resolve) => { releaseFirst = resolve })
    getHomePreviewDocument.mockImplementation((fixtureId: number) => {
      if (fixtureId === 90001) return held
      return Promise.resolve({
        ...storedDocument,
        fixture_id: 90002,
        run_id: 'run-2',
        headline: '둘째 경기 제목',
        fixture: {
          external_id: 90002,
          kickoff_at: '2026-11-13T11:00:00Z',
          league: '프리미어리그',
          home: { external_id: 42, name: '아스널', logo_url: null },
          away: { external_id: 33, name: '브렌트퍼드', logo_url: null },
        },
        sections: [{ ...storedDocument.sections[0]!, section_result_id: 's2', run_id: 'run-2', body: '둘째 경기 본문' }],
      })
    })

    const wrapper = await mountSection()
    await flushPromises()

    // 둘째 경기로 전환하고 그 응답을 기다린다.
    const strip = wrapper.findAll('.hp-match-strip button')
    await strip[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('둘째 경기 본문')

    // 이제 늦게 도착한 첫 경기 응답. 새 경기 본문을 덮으면 안 된다.
    releaseFirst({
      ...storedDocument,
      fixture_id: 90001,
      run_id: 'run-1',
      headline: '첫 경기 제목',
      sections: [{ ...storedDocument.sections[0]!, body: '첫 경기 본문' }],
    })
    await flushPromises()

    const body = wrapper.find('[data-testid="stored-preview-document"]')
    expect(body.exists()).toBe(true)
    expect(body.text()).toContain('둘째 경기 본문')
    expect(body.text()).not.toContain('첫 경기 본문')
    expect(wrapper.find('[data-testid="selected-preview"]').attributes('data-fixture-id')).toBe('90002')
  })

  it('shows a partial-document notice when required sections are missing (complete=false)', async () => {
    getHomePreviewDocument.mockResolvedValue({
      ...storedDocument,
      fixture_id: 90001,
      run_id: '4f90e50b-ce55-4beb-8a17-20ef6e9192fb',
      complete: false,
      sections: [
        { ...storedDocument.sections[0]!, workflow_id: 'section_outlook', title: '경기 흐름 전망' },
      ],
    })
    const wrapper = await mountSection()
    await flushPromises()

    expect(wrapper.find('[data-testid="stored-preview-document"]').exists()).toBe(true)
    const notice = wrapper.find('[data-testid="stored-document-partial"]')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('부분 표시')
  })
})
