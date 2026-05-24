import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('chart.js', () => {
  class MockChart {
    static register = vi.fn()

    data: { datasets: Array<{ backgroundColor?: unknown; data?: number[]; rotation?: number }> }
    options: unknown

    constructor(_canvas: HTMLCanvasElement, config: { data: MockChart['data']; options: unknown }) {
      this.data = config.data
      this.options = config.options
    }

    update = vi.fn()
    destroy = vi.fn()
  }

  return {
    ArcElement: {},
    Chart: MockChart,
    DoughnutController: {},
    PieController: {},
  }
})

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

function defaultFixtureEvents() {
  return [
    {
      time: { elapsed: 58 },
      team: { id: 10, name: 'Korea Republic', code: 'KOR' },
      player: { id: 7, name: 'Son Heung-Min' },
      type: 'Goal',
      detail: 'Normal Goal',
    },
    {
      time: { elapsed: 61 },
      team: { id: 20, name: 'Brazil', code: 'BRA' },
      player: { id: 9, name: 'Neymar' },
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
          7: { name_ko: '손흥민', short_name_ko: '손흥민' },
          9: { name_ko: '네이마르 주니오르', short_name_ko: '네이마르' },
          11: { name_ko: '하피냐', short_name_ko: '하피냐' },
        },
        coaches: {},
      })
    }

    if (url.pathname === '/fixtures' && url.searchParams.get('live') === 'all') {
      return jsonResponse({
        response: [{
          fixture: {
            id: 260506,
            status: { short: '2H', elapsed: 63, extra: 2 },
            venue: { name: 'Live Stadium' },
          },
          league: { id: 1, name: 'FIFA World Cup', season: 2026 },
          teams: {
            home: { id: 10, name: 'Korea Republic', code: 'KOR' },
            away: { id: 20, name: 'Brazil', code: 'BRA' },
          },
          goals: { home: 1, away: 1 },
        }],
      })
    }

    if (url.pathname === '/fixtures' && url.searchParams.has('id')) {
      return jsonResponse({
        response: [{
          fixture: {
            id: Number(url.searchParams.get('id')),
            status: { short: '2H', elapsed: 63, extra: 2 },
            venue: { name: 'Live Stadium' },
          },
          league: { id: 1, name: 'FIFA World Cup', season: 2026 },
          teams: {
            home: { id: 10, name: 'Korea Republic', code: 'KOR' },
            away: { id: 20, name: 'Brazil', code: 'BRA' },
          },
          goals: { home: 1, away: 1 },
        }],
      })
    }

    if (url.pathname === '/fixtures/events') {
      return jsonResponse({
        response: fixtureEvents,
      })
    }

    if (url.pathname === '/fixtures/lineups') {
      return jsonResponse({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            formation: '4-2-3-1',
            startXI: [
              { player: { id: 7, name: 'Son Heung-Min', number: 7, pos: 'F', grid: '1:1' } },
            ],
            substitutes: [],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            formation: '4-3-3',
            startXI: [
              { player: { id: 9, name: 'Neymar', number: 10, pos: 'F', grid: '1:1' } },
              { player: { id: 11, name: 'Raphinha', number: 11, pos: 'F', grid: '1:2' } },
            ],
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
              { type: 'Yellow Cards', value: 3 },
              { type: 'Red Cards', value: 1 },
              { type: 'Fouls', value: 12 },
            ],
          },
        ],
      })
    }

    if (url.pathname === '/fixtures/players') {
      return jsonResponse({
        response: [
          {
            team: { id: 10, name: 'Korea Republic', code: 'KOR' },
            players: [
              {
                player: {
                  id: 7,
                  name: 'Son Heung-Min',
                  photo: 'https://media.api-sports.io/football/players/186.png',
                },
                statistics: [{ games: { rating: '8.6' } }],
              },
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            players: [
              {
                player: {
                  id: 9,
                  name: 'Neymar',
                  photo: 'https://media.api-sports.io/football/players/276.png',
                },
                statistics: [{ games: { rating: '7.7' } }],
              },
              {
                player: {
                  id: 11,
                  name: 'Raphinha',
                  photo: 'https://media.api-sports.io/football/players/538.png',
                },
                statistics: [{ games: { rating: '8.1' } }],
              },
            ],
          },
        ],
      })
    }

    throw new Error(`unexpected url ${url}`)
  }))
}

async function mountProgram(search = '') {
  vi.resetModules()
  fixtureEvents = defaultFixtureEvents()
  stubApiFootballFetch()
  setSearch(search)

  const { default: BroadcastProgramApp } = await import('@/BroadcastProgramApp.vue')
  const wrapper = mount(BroadcastProgramApp)
  await flushPromises()
  await nextTick()
  await flushPromises()
  return wrapper
}

describe('BroadcastProgramApp', () => {
  afterEach(() => {
    setSearch('')
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('renders the 78/22 program regions without mock cards before live data', async () => {
    vi.resetModules()
    setSearch('')
    const { default: BroadcastProgramApp } = await import('@/BroadcastProgramApp.vue')
    const wrapper = mount(BroadcastProgramApp)

    expect(wrapper.get('[data-testid=program-stage]').attributes('data-league')).toBe(
      'world-cup-2026',
    )
    expect(wrapper.get('[data-testid=program-bottom-carousel]').attributes('data-carousel-interval-ms')).toBe(
      '7000',
    )
    expect(wrapper.get('[data-testid=program-bottom-carousel]').attributes('data-event-insert-index')).toBe(
      '1',
    )
    expect(wrapper.get('[data-testid=program-left]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-feed-surface]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-live-empty]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid=program-info-card]')).toHaveLength(0)
    expect(wrapper.get('[data-testid=program-chat-slot]').exists()).toBe(true)
    expect(wrapper.get('[data-testid=program-character-slot]').exists()).toBe(true)
    expect(wrapper.find('[data-testid=program-scorebug]').exists()).toBe(false)
    expect(wrapper.find('[data-testid=program-lower-third]').exists()).toBe(false)
  })

  it('uses fixtureId query params and queues initial events with the World Cup image banner first', async () => {
    const wrapper = await mountProgram('?fixtureId=260506&league=world-cup-2026')

    expect(wrapper.get('[data-testid=program-stage]').attributes('data-league')).toBe(
      'world-cup-2026',
    )
    expect(wrapper.text()).toContain('대한민국')
    const cards = wrapper.findAll('[data-testid=program-info-card]')
    expect(cards.map((card) => card.attributes('data-card-id'))).toEqual([
      'worldcup-kickoff-banner',
      '58-0-Goal-Normal_Goal-10-7-assist-splash',
      '58-0-Goal-Normal_Goal-10-7-assist',
      '61-0-Card-Yellow_Card-20-9-assist-splash',
      '61-0-Card-Yellow_Card-20-9-assist',
      'live-banner',
      'match-stats-intro',
      'possession-stat',
      'attack-stats',
      'discipline-stats',
      'top-rated-player',
    ])
    expect(wrapper.get('[data-testid=program-image-banner]').attributes('src')).toContain(
      'worldcup-kickoff-2026-banner',
    )
    expect(cards[7].attributes('data-card-kind')).toBe('possession-stat')
    expect(cards[8].attributes('data-card-kind')).toBe('metric-group')
    expect(cards[9].attributes('data-card-kind')).toBe('metric-group')
    expect(cards[10].attributes('data-card-kind')).toBe('player-rating')
    expect(cards.filter((card) => card.attributes('data-event-type') === 'goal')).toHaveLength(2)
    expect(cards.filter((card) => card.attributes('data-event-type') === 'card')).toHaveLength(2)
    expect(
      cards.find((card) => card.attributes('data-card-id') === '61-0-Card-Yellow_Card-20-9-assist')?.text(),
    ).toContain('네이마르 주니오르')
    expect(wrapper.findAll('[data-testid=program-info-card-clone]')).toHaveLength(1)
    expect(wrapper.get('[data-testid=program-info-card-clone]').attributes('data-card-id')).toBe(
      'worldcup-kickoff-banner',
    )
  })

  it('advances upward every 7 seconds and rotates the live queue after the transition', async () => {
    vi.useFakeTimers()
    const wrapper = await mountProgram('?fixtureId=260506&league=world-cup-2026')

    const track = wrapper.get('[data-testid=program-info-track]')
    expect(track.attributes('style')).toContain('translateY(-0%)')

    vi.advanceTimersByTime(6999)
    await nextTick()
    expect(track.attributes('style')).toContain('translateY(-0%)')

    vi.advanceTimersByTime(1)
    await nextTick()
    expect(track.attributes('style')).toContain('translateY(-100%)')

    await track.trigger('transitionend', { propertyName: 'transform' })
    await nextTick()

    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      '58-0-Goal-Normal_Goal-10-7-assist-splash',
    )
    expect(track.attributes('style')).toContain('translateY(-0%)')
  })

  it('queues every event splash in demoEvents=all mode without API polling', async () => {
    const wrapper = await mountProgram('?league=world-cup-2026&demoEvents=all')
    const cards = wrapper.findAll('[data-testid=program-info-card]')

    expect(cards.map((card) => card.attributes('data-card-id'))).toEqual([
      'worldcup-kickoff-banner',
      'demo-goal-splash',
      'demo-goal',
      'demo-own-goal-splash',
      'demo-own-goal',
      'demo-substitution-splash',
      'demo-substitution',
      'demo-yellow-card-splash',
      'demo-yellow-card',
      'demo-red-card-splash',
      'demo-red-card',
      'demo-var-splash',
      'demo-var',
      'live-banner',
      'match-stats-intro',
      'possession-stat',
      'attack-stats',
      'discipline-stats',
      'top-rated-player',
    ])
    expect(
      cards
        .filter((card) => card.attributes('data-card-kind') === 'event-splash')
        .map((card) => card.attributes('data-event-splash-type')),
    ).toEqual([
      'goal',
      'own-goal',
      'substitution',
      'yellow-card',
      'red-card',
      'var',
    ])
    expect(cards.find((card) => card.attributes('data-card-id') === 'demo-var')?.text()).not.toContain(
      '#--',
    )
  })

  it('stops auto rotation and uses i/k keys in demoEvents=all mode', async () => {
    vi.useFakeTimers()
    const wrapper = await mountProgram('?league=world-cup-2026&demoEvents=all')
    const track = wrapper.get('[data-testid=program-info-track]')

    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      'worldcup-kickoff-banner',
    )
    expect(track.attributes('style')).toContain('translateY(-0%)')

    vi.advanceTimersByTime(7000)
    await nextTick()

    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      'worldcup-kickoff-banner',
    )
    expect(track.attributes('style')).toContain('translateY(-0%)')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'k' }))
    await nextTick()
    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      'demo-goal-splash',
    )
    expect(track.attributes('style')).toContain('translateY(-0%)')
    expect(track.attributes('style')).toContain('transition: none')

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'i' }))
    await nextTick()
    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      'worldcup-kickoff-banner',
    )
    expect(track.attributes('style')).toContain('translateY(-0%)')
  })

  it('inserts multiple new live events after the current card and removes each after display', async () => {
    vi.useFakeTimers()
    const wrapper = await mountProgram('?fixtureId=260506&league=world-cup-2026')
    const track = wrapper.get('[data-testid=program-info-track]')

    fixtureEvents = [
      ...defaultFixtureEvents(),
      {
        time: { elapsed: 64 },
        team: { id: 10, name: 'Korea Republic', code: 'KOR' },
        player: { id: 7, name: 'Son Heung-Min' },
        type: 'Goal',
        detail: 'Normal Goal',
      },
      {
        time: { elapsed: 66 },
        team: { id: 20, name: 'Brazil', code: 'BRA' },
        player: { id: 9, name: 'Neymar' },
        type: 'Card',
        detail: 'Yellow Card',
      },
    ]

    vi.advanceTimersByTime(10_000)
    await flushPromises()
    await nextTick()
    await track.trigger('transitionend', { propertyName: 'transform' })
    await nextTick()

    expect(wrapper.findAll('[data-testid=program-info-card]').map((card) => card.attributes('data-card-id'))).toEqual([
      '58-0-Goal-Normal_Goal-10-7-assist-splash',
      '64-0-Goal-Normal_Goal-10-7-assist-splash',
      '64-0-Goal-Normal_Goal-10-7-assist',
      '66-0-Card-Yellow_Card-20-9-assist-splash',
      '66-0-Card-Yellow_Card-20-9-assist',
      '58-0-Goal-Normal_Goal-10-7-assist',
      '61-0-Card-Yellow_Card-20-9-assist-splash',
      '61-0-Card-Yellow_Card-20-9-assist',
      'live-banner',
      'match-stats-intro',
      'possession-stat',
      'attack-stats',
      'discipline-stats',
      'top-rated-player',
      'worldcup-kickoff-banner',
    ])
    const insertedCards = wrapper.findAll('[data-testid=program-info-card]')
    expect(insertedCards[1].attributes('data-card-kind')).toBe('event-splash')
    expect(insertedCards[1].attributes('data-event-splash-type')).toBe('goal')
    expect(insertedCards[1].get('[data-testid=program-event-splash-image]').attributes('src')).toContain(
      'event-goal',
    )
    expect(insertedCards[3].attributes('data-card-kind')).toBe('event-splash')
    expect(insertedCards[3].attributes('data-event-splash-type')).toBe('yellow-card')
    expect(insertedCards[3].get('[data-testid=program-event-splash-image]').attributes('src')).toContain(
      'event-yellow-card',
    )

    vi.advanceTimersByTime(7000)
    await nextTick()
    await track.trigger('transitionend', { propertyName: 'transform' })
    await nextTick()

    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      '64-0-Goal-Normal_Goal-10-7-assist-splash',
    )

    vi.advanceTimersByTime(7000)
    await nextTick()
    await track.trigger('transitionend', { propertyName: 'transform' })
    await nextTick()

    expect(wrapper.findAll('[data-testid=program-info-card]')[0].attributes('data-card-id')).toBe(
      '64-0-Goal-Normal_Goal-10-7-assist',
    )
    expect(wrapper.findAll('[data-testid=program-info-card]').map((card) => card.attributes('data-card-id'))).not.toContain(
      '64-0-Goal-Normal_Goal-10-7-assist-splash',
    )

    vi.advanceTimersByTime(7000)
    await nextTick()
    await track.trigger('transitionend', { propertyName: 'transform' })
    await nextTick()

    const cardIdsAfterGoalDisplay = wrapper
      .findAll('[data-testid=program-info-card]')
      .map((card) => card.attributes('data-card-id'))
    expect(cardIdsAfterGoalDisplay[0]).toBe('66-0-Card-Yellow_Card-20-9-assist-splash')
    expect(cardIdsAfterGoalDisplay).not.toContain('64-0-Goal-Normal_Goal-10-7-assist')
  })
})
