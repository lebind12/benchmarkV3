import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  } as Response
}

function setSearch(search: string) {
  window.history.pushState({}, '', `/broadcast-program.html${search}`)
}

function lineupPlayers(team: 'home' | 'away') {
  const home = [
    ['Kim Seung-Gyu', 1],
    ['Kim Min-Jae', 4],
    ['Lee Jae-Sung', 10],
    ['Son Heung-Min', 7],
    ['Hwang Hee-Chan', 11],
    ['Cho Gue-Sung', 9],
    ['Lee Kang-In', 18],
    ['Jung Woo-Young', 5],
    ['Hwang In-Beom', 6],
    ['Kim Jin-Su', 3],
    ['Kim Moon-Hwan', 2],
  ] as const
  const away = [
    ['Alisson', 1],
    ['Marquinhos', 4],
    ['Thiago Silva', 3],
    ['Casemiro', 5],
    ['Neymar', 10],
    ['Raphinha', 11],
    ['Vinicius Junior', 20],
    ['Richarlison', 9],
    ['Lucas Paqueta', 8],
    ['Danilo', 2],
    ['Alex Sandro', 6],
  ] as const

  return (team === 'home' ? home : away).map(([name, number], index) => ({
    player: {
      id: team === 'home' ? 100 + index : 200 + index,
      name,
      number,
      pos: index === 0 ? 'G' : index < 4 ? 'D' : index < 8 ? 'M' : 'F',
      grid: `${Math.floor(index / 4) + 1}:${(index % 4) + 1}`,
    },
  }))
}

function defaultFixtureEvents() {
  return [
    {
      time: { elapsed: 67 },
      team: { id: 10, name: 'Korea Republic', code: 'KOR' },
      player: { id: 106, name: 'Lee Kang-In' },
      assist: { id: 111, name: 'Hong Hyun-Seok' },
      type: 'subst',
      detail: 'Substitution',
    },
    {
      time: { elapsed: 70 },
      team: { id: 20, name: 'Brazil', code: 'BRA' },
      player: { id: 204, name: 'Neymar' },
      type: 'Card',
      detail: 'Yellow Card',
    },
  ]
}

let fixtureEvents: ReturnType<typeof defaultFixtureEvents> = []

function stubApiFootballFetch() {
  vi.stubEnv('VITE_API_FOOTBALL_KEY', 'test-key')
  vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://localhost')

    if (url.pathname === '/api/v1/broadcast/translations') {
      return jsonResponse({
        leagues: { 1: { name_ko: '월드컵', short_name_ko: '월드컵' } },
        teams: {
          10: { name_ko: '대한민국', short_name_ko: '한국' },
          20: { name_ko: '브라질', short_name_ko: '브라질' },
        },
        players: {
          100: { name_ko: '김승규', short_name_ko: '김승규' },
          101: { name_ko: '김민재', short_name_ko: '김민재' },
          102: { name_ko: '이재성', short_name_ko: '이재성' },
          103: { name_ko: '손흥민', short_name_ko: '손흥민' },
          104: { name_ko: '황희찬', short_name_ko: '황희찬' },
          105: { name_ko: '조규성', short_name_ko: '조규성' },
          106: { name_ko: '이강인', short_name_ko: '이강인' },
          107: { name_ko: '정우영', short_name_ko: '정우영' },
          108: { name_ko: '황인범', short_name_ko: '황인범' },
          109: { name_ko: '김진수', short_name_ko: '김진수' },
          110: { name_ko: '김문환', short_name_ko: '김문환' },
          111: { name_ko: '홍현석', short_name_ko: '홍현석' },
          204: { name_ko: '네이마르 주니오르', short_name_ko: '네이마르' },
        },
        coaches: {
          1000: { name_ko: '홍명보', short_name_ko: '홍명보' },
          2000: { name_ko: '카를로 안첼로티', short_name_ko: '안첼로티' },
        },
      })
    }

    if (url.pathname === '/fixtures' && url.searchParams.has('id')) {
      return jsonResponse({
        response: [{
          fixture: {
            id: Number(url.searchParams.get('id')),
            status: { short: '2H', elapsed: 72, extra: 2 },
            venue: { name: 'Live Stadium' },
          },
          league: { id: 1, name: 'FIFA World Cup', season: 2026 },
          teams: {
            home: { id: 10, name: 'Korea Republic', code: 'KOR', logo: 'https://example.com/korea.png' },
            away: { id: 20, name: 'Brazil', code: 'BRA', logo: 'https://example.com/brazil.png' },
          },
          goals: { home: 1, away: 1 },
        }],
      })
    }

    if (url.pathname === '/fixtures/events') {
      return jsonResponse({ response: fixtureEvents })
    }

    if (url.pathname === '/fixtures/lineups') {
      return jsonResponse({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            coach: { id: 1000, name: 'Hong Myung-Bo' },
            formation: '4-2-3-1',
            startXI: lineupPlayers('home'),
            substitutes: [
              { player: { id: 111, name: 'Hong Hyun-Seok', number: 17 } },
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            coach: { id: 2000, name: 'Carlo Ancelotti' },
            formation: '4-3-3',
            startXI: lineupPlayers('away'),
            substitutes: [],
          },
        ],
      })
    }

    if (url.pathname === '/fixtures/statistics') {
      return jsonResponse({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            statistics: [
              { type: 'Ball Possession', value: '61%' },
              { type: 'Total Shots', value: 11 },
              { type: 'Shots on Goal', value: 5 },
              { type: 'Corner Kicks', value: 6 },
              { type: 'Offsides', value: 2 },
              { type: 'Passes %', value: '86%' },
              { type: 'Yellow Cards', value: 1 },
              { type: 'Red Cards', value: 0 },
              { type: 'Fouls', value: 8 },
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            statistics: [
              { type: 'Ball Possession', value: '39%' },
              { type: 'Total Shots', value: 8 },
              { type: 'Shots on Goal', value: 3 },
              { type: 'Corner Kicks', value: 4 },
              { type: 'Offsides', value: 1 },
              { type: 'Passes %', value: '79%' },
              { type: 'Yellow Cards', value: 3 },
              { type: 'Red Cards', value: 1 },
              { type: 'Fouls', value: 12 },
            ],
          },
        ],
      })
    }

    if (url.pathname === '/fixtures/players') {
      return jsonResponse({ response: [] })
    }

    if (url.pathname === '/teams') {
      return jsonResponse({ response: [] })
    }

    throw new Error(`unexpected url ${url}`)
  }))
}

async function mountProgram(search = '?fixtureId=260506&league=world-cup-2026') {
  vi.resetModules()
  localStorage.setItem('mockRole', 'ADMIN')
  fixtureEvents = defaultFixtureEvents()
  stubApiFootballFetch()
  setSearch(search)

  const { default: BroadcastProgramApp } = await import('@/BroadcastProgramApp.vue')
  const wrapper = mount(BroadcastProgramApp, { attachTo: document.body })
  await flushPromises()
  await nextTick()
  await flushPromises()
  return wrapper
}

describe('BroadcastProgramApp', () => {
  afterEach(() => {
    setSearch('')
    localStorage.removeItem('mockRole')
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
    document.body.innerHTML = ''
  })

  it('renders the program shell with a lineup bottom panel and no carousel cards', async () => {
    const wrapper = await mountProgram()

    expect(wrapper.get('[data-testid=program-stage]').attributes('data-league')).toBe(
      'world-cup-2026',
    )
    expect(wrapper.get('[data-testid=program-stage]').attributes('data-active-bottom-view')).toBe(
      'lineup',
    )
    expect(wrapper.get('[data-testid=program-left]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-feed-surface]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-bottom-panel]').exists()).toBe(true)
    expect(wrapper.find('[data-testid=program-bottom-carousel]').exists()).toBe(false)
    expect(wrapper.find('[data-testid=program-info-card]').exists()).toBe(false)
    expect(wrapper.find('[data-testid=program-event-splash-image]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=program-chat-slot]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-character-slot]').exists()).toBe(true)
    expect(wrapper.find('[data-testid=program-scorebug]').exists()).toBe(false)
    expect(wrapper.find('[data-testid=program-lower-third]').exists()).toBe(false)
  })

  it('renders both current XIs and applies substitution events to the lineup only', async () => {
    vi.useFakeTimers()
    const wrapper = await mountProgram()
    const players = wrapper.findAll('[data-testid=program-lineup-player]')
    const lineupView = wrapper.get('[data-testid=program-lineup-view]')

    expect(wrapper.findAll('[data-testid=program-lineup-team]')).toHaveLength(2)
    expect(players).toHaveLength(22)
    expect(wrapper.findAll('[data-testid=program-lineup-coach]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid=program-lineup-substitution-animation]')).toHaveLength(1)
    expect(lineupView.text()).toContain('이강인')
    expect(lineupView.text()).toContain('홍현석')
    expect(lineupView.text()).toContain('홍명보')
    expect(lineupView.text()).toContain('안첼로티')
    expect(wrapper.text()).not.toContain('선수 교체')
    expect(wrapper.text()).not.toContain('네이마르 주니오르')

    vi.advanceTimersByTime(3000)
    await nextTick()

    expect(wrapper.find('[data-testid=program-lineup-substitution-animation]').exists()).toBe(true)
    const substitutedInPlayer = wrapper.get('[data-testid=program-lineup-player][data-sub-in="true"]')
    expect(substitutedInPlayer.text()).toContain('홍현석')
    expect(substitutedInPlayer.text()).toContain('IN')

    vi.advanceTimersByTime(5000)
    await nextTick()

    expect(wrapper.find('[data-testid=program-lineup-substitution-animation]').exists()).toBe(false)
    expect(lineupView.text()).toContain('홍현석')
    expect(lineupView.text()).not.toContain('이강인')
  })

  it('toggles stats shortcuts back to lineup', async () => {
    const wrapper = await mountProgram()
    const stage = wrapper.get('[data-testid=program-stage]')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('attack')
    expect(wrapper.get('[data-testid=program-stats-view]').attributes('data-stats-view')).toBe('attack')
    expect(wrapper.text()).toContain('공격 지표')
    expect(wrapper.text()).toContain('점유율')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('lineup')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'c', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('chance')
    expect(wrapper.text()).toContain('찬스 지표')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'v', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('control')
    expect(wrapper.text()).toContain('경기 운영')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('discipline')
    expect(wrapper.text()).toContain('징계/수비')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'z', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('lineup')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'b', ctrlKey: true }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('discipline')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(stage.attributes('data-active-bottom-view')).toBe('lineup')
  })

  it('ignores bottom view shortcuts from editable elements', async () => {
    const wrapper = await mountProgram()
    const input = document.createElement('input')
    document.body.append(input)

    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', ctrlKey: true, bubbles: true }))
    await nextTick()

    expect(wrapper.get('[data-testid=program-stage]').attributes('data-active-bottom-view')).toBe('lineup')
    input.remove()
  })

  it('shows a stable empty state when live mode is unavailable', async () => {
    vi.resetModules()
    localStorage.setItem('mockRole', 'ADMIN')
    vi.stubGlobal('fetch', vi.fn())
    setSearch('')

    const { default: BroadcastProgramApp } = await import('@/BroadcastProgramApp.vue')
    const wrapper = mount(BroadcastProgramApp)
    await flushPromises()

    expect(wrapper.get('[data-testid=program-live-empty]').text()).toContain(
      'API-Football 라이브 모드가 설정되지 않았습니다',
    )
  })
})
