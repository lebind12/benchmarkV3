import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  } as Response
}

function setSearch(search: string) {
  window.history.pushState({}, '', `/broadcast.html${search}`)
}

let homeFormation = '4-3-3'
let awayFormation = '4-2-3-1'
let fixtureHomeName = 'Korea Republic'
let fixtureHomeCode: string | null = 'KOR'
let fixtureHomeLogo: string | null = 'api-home-logo'
let fixtureAwayName = 'Brazil'
let fixtureAwayCode: string | null = 'BRA'
let fixtureAwayLogo: string | null = 'api-away-logo'
let teamEndpointHomeCode: string | null = 'ARS'
let teamEndpointAwayCode: string | null = 'BUR'
let reverseHomeBackLine = false
const defaultLineupGrids = [
  '1:1',
  '2:1',
  '2:2',
  '2:3',
  '2:4',
  '3:1',
  '3:2',
  '3:3',
  '4:1',
  '4:2',
  '4:3',
]
let homeLineupGrids: Array<string | undefined> = defaultLineupGrids
let awayLineupGrids: Array<string | undefined> = defaultLineupGrids
let standoutRating = '8.2'

function fixtureResponse(id = 260506) {
  return {
    fixture: {
      id,
      status: { short: '2H', elapsed: 63, extra: 2 },
      venue: { name: 'Live Stadium' },
    },
    league: { id: 1, name: 'FIFA World Cup', season: 2026 },
    teams: {
      home: { id: 10, name: fixtureHomeName, code: fixtureHomeCode, logo: fixtureHomeLogo },
      away: { id: 20, name: fixtureAwayName, code: fixtureAwayCode, logo: fixtureAwayLogo },
    },
    goals: { home: 1, away: 1 },
  }
}

function lineupPlayers(prefix: string, names: string[], grids: Array<string | undefined> = defaultLineupGrids) {
  const positions = ['G', 'D', 'D', 'D', 'D', 'M', 'M', 'M', 'F', 'F', 'F']

  return names.map((name, index) => ({
    player: {
      id: Number(`${prefix}${index + 1}`),
      name,
      number: index + 1,
      pos: positions[index],
      grid: grids[index],
    },
  }))
}

function substitutePlayers(prefix: string, names: string[]) {
  return names.map((_name, index) => ({
    player: {
      id: Number(`${prefix}${index + 12}`),
      number: index + 12,
    },
  }))
}

function maybeReverseBackLine(players: ReturnType<typeof lineupPlayers>) {
  if (!reverseHomeBackLine) return players
  return [
    players[0],
    ...players.slice(1, 5).reverse(),
    ...players.slice(5),
  ]
}

function fixturePlayerRatings(prefix: string) {
  return Array.from({ length: 14 }, (_, index) => ({
    player: {
      id: Number(`${prefix}${index + 1}`),
      name: `Player ${index + 1}`,
    },
    statistics: [{
      games: {
        rating: index === 1 ? '5.4' : index === 9 ? standoutRating : '7.1',
      },
    }],
  }))
}

function defaultFixtureEvents() {
  return [
    {
      time: { elapsed: 58 },
      team: { id: 10, name: 'Korea Republic', code: 'KOR' },
      player: { id: 7, name: 'Son Heung-Min' },
      assist: { id: 8, name: 'Lee Kang-In' },
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

let fixtureEvents = defaultFixtureEvents()

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
          8: { name_ko: '이강인', short_name_ko: '이강인' },
          9: { name_ko: '네이마르', short_name_ko: '네이마르' },
          1010: { name_ko: '손흥민 풀네임', short_name_ko: '손흥민' },
          1012: { name_ko: '조규성 풀네임', short_name_ko: '조규성' },
          208: { name_ko: '네이마르', short_name_ko: '네이마르' },
        },
        coaches: {},
      })
    }

    if (url.pathname === '/fixtures' && url.searchParams.get('live') === 'all') {
      return jsonResponse({ response: [fixtureResponse(260506)] })
    }

    if (url.pathname === '/fixtures' && url.searchParams.has('id')) {
      return jsonResponse({ response: [fixtureResponse(Number(url.searchParams.get('id')))] })
    }

    if (url.pathname === '/teams') {
      const id = Number(url.searchParams.get('id'))
      const code = id === 10 ? teamEndpointHomeCode : id === 20 ? teamEndpointAwayCode : null
      return jsonResponse({
        response: [{ team: { id, code } }],
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
            formation: homeFormation,
            startXI: maybeReverseBackLine(lineupPlayers('10', [
              'Kim Seung-Gyu',
              'Kim Jin-Su',
              'Kim Min-Jae',
              'Kim Young-Gwon',
              'Kim Moon-Hwan',
              'Jung Woo-Young',
              'Hwang In-Beom',
              'Lee Kang-In',
              'Hwang Hee-Chan',
              'Son Heung-Min',
              'Lee Jae-Sung',
            ], homeLineupGrids)),
            substitutes: substitutePlayers('10', [
              'Cho Gue-Sung',
              'Paik Seung-Ho',
              'Na Sang-Ho',
            ]),
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            formation: awayFormation,
            startXI: lineupPlayers('20', [
              'Alisson',
              'Renan Lodi',
              'Marquinhos',
              'Thiago Silva',
              'Danilo',
              'Bruno Guimaraes',
              'Casemiro',
              'Neymar',
              'Vinicius Junior',
              'Richarlison',
              'Raphinha',
            ], awayLineupGrids),
            substitutes: substitutePlayers('20', [
              'Gabriel Jesus',
              'Antony',
              'Rodrygo',
            ]),
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
            ],
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            statistics: [
              { type: 'Ball Possession', value: '39%' },
              { type: 'Total Shots', value: 8 },
              { type: 'Shots on Goal', value: 3 },
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
            players: fixturePlayerRatings('10'),
          },
          {
            team: { id: 20, name: 'Brazil', code: 'BRA' },
            players: fixturePlayerRatings('20'),
          },
        ],
      })
    }

    throw new Error(`unexpected url ${url}`)
  }))
}

async function mountBroadcast(search = '') {
  vi.resetModules()
  localStorage.setItem('mockRole', 'ADMIN')
  stubApiFootballFetch()
  setSearch(search)

  const { default: BroadcastApp } = await import('@/BroadcastApp.vue')
  const wrapper = mount(BroadcastApp)
  await flushPromises()
  await nextTick()
  await flushPromises()
  return wrapper
}

describe('BroadcastApp', () => {
  afterEach(() => {
    setSearch('')
    localStorage.removeItem('mockRole')
    homeFormation = '4-3-3'
    awayFormation = '4-2-3-1'
    fixtureHomeName = 'Korea Republic'
    fixtureHomeCode = 'KOR'
    fixtureHomeLogo = 'api-home-logo'
    fixtureAwayName = 'Brazil'
    fixtureAwayCode = 'BRA'
    fixtureAwayLogo = 'api-away-logo'
    teamEndpointHomeCode = 'ARS'
    teamEndpointAwayCode = 'BUR'
    reverseHomeBackLine = false
    homeLineupGrids = defaultLineupGrids
    awayLineupGrids = defaultLineupGrids
    standoutRating = '8.2'
    fixtureEvents = defaultFixtureEvents()
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('loads API-Football live data without query params', async () => {
    const wrapper = await mountBroadcast()

    expect(wrapper.get('[data-testid=broadcast-stage]').attributes('data-league')).toBe(
      'premier-league',
    )
    expect(wrapper.get('[data-testid=stats-card]').text()).toContain('61%')
    expect(wrapper.text()).toContain('대한민국')
    expect(wrapper.text()).toContain('브라질')
    expect(wrapper.get('[data-testid=score-team-home] strong').text()).toBe('한국')
    expect(wrapper.get('[data-testid=score-team-away] strong').text()).toBe('브라질')
    const scoreBadges = wrapper.findAll('[data-testid=country-badge]')
    expect(scoreBadges[0].attributes('aria-label')).toBe('KOR')
    expect(scoreBadges[1].attributes('aria-label')).toBe('BRA')
    expect(wrapper.get('.dial-header').text()).toContain('KOR')
    expect(wrapper.get('.dial-header').text()).toContain('BRA')
  })

  it('uses fixtureId and league query params for the broadcast fixture', async () => {
    const wrapper = await mountBroadcast('?fixtureId=260506&league=world-cup-2026')

    expect(wrapper.get('[data-testid=broadcast-stage]').attributes('data-league')).toBe(
      'world-cup-2026',
    )
    expect(wrapper.text()).toContain('대한민국')
    expect(wrapper.text()).toContain('손흥민')
  })

  it('uses API-Football team codes for Premier League badges when fixture codes are unusable', async () => {
    fixtureHomeName = 'Arsenal'
    fixtureHomeCode = 'A'
    fixtureAwayName = 'Burnley'
    fixtureAwayCode = 'B'

    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const scoreBadges = wrapper.findAll('[data-testid=country-badge]')

    expect(scoreBadges[0].attributes('aria-label')).toBe('ARS')
    expect(scoreBadges[1].attributes('aria-label')).toBe('BUR')
    expect(wrapper.get('.dial-header').text()).toContain('ARS')
    expect(wrapper.get('.dial-header').text()).toContain('BUR')
  })

  it('falls back Premier League code slots to Home and Away when API-Football has no usable code', async () => {
    fixtureHomeName = 'Arsenal'
    fixtureHomeCode = 'A'
    fixtureHomeLogo = null
    fixtureAwayName = 'Burnley'
    fixtureAwayCode = null
    fixtureAwayLogo = null
    teamEndpointHomeCode = null
    teamEndpointAwayCode = null

    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const scoreBadges = wrapper.findAll('[data-testid=country-badge]')

    expect(scoreBadges[0].text()).toBe('Home')
    expect(scoreBadges[0].attributes('aria-label')).toBe('Home')
    expect(scoreBadges[1].text()).toBe('Away')
    expect(scoreBadges[1].attributes('aria-label')).toBe('Away')
    expect(wrapper.get('.dial-header').text()).toContain('Home')
    expect(wrapper.get('.dial-header').text()).toContain('Away')
  })

  it('supports manual match clock, added time editors, and team-side pause/play controls', async () => {
    vi.useFakeTimers()
    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const promptSpy = vi.spyOn(window, 'prompt')
      .mockReturnValueOnce('70:15')
      .mockReturnValueOnce('+5')

    expect(wrapper.get('[data-testid=manual-clock-button]').text()).toContain('00:00')
    expect(wrapper.get('[data-testid=manual-added-time-button]').text()).toContain('00:00')

    await wrapper.get('[data-testid=score-team-home]').trigger('click')
    vi.advanceTimersByTime(3_000)
    await nextTick()
    expect(wrapper.get('[data-testid=manual-clock-button]').text()).toContain('00:00')

    await wrapper.get('[data-testid=score-team-away]').trigger('click')
    vi.advanceTimersByTime(2_000)
    await nextTick()
    expect(wrapper.get('[data-testid=manual-clock-button]').text()).toContain('00:02')

    await wrapper.get('[data-testid=score-team-home]').trigger('click')
    await wrapper.get('[data-testid=manual-clock-button]').trigger('click')
    expect(promptSpy).toHaveBeenCalledWith('경기시간 입력', '00:02')
    expect(wrapper.get('[data-testid=manual-clock-button]').text()).toContain('70:15')

    await wrapper.get('[data-testid=manual-added-time-button]').trigger('click')
    expect(promptSpy).toHaveBeenCalledWith('추가시간 입력', '00:00')
    expect(wrapper.get('[data-testid=manual-added-time-button]').text()).toContain('05:00')
  })

  it('polls live-changing API-Football endpoints and refreshes player ratings after the initial snapshot', async () => {
    vi.useFakeTimers()
    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>

    standoutRating = '8.6'
    fetchMock.mockClear()
    vi.advanceTimersByTime(10_000)
    await flushPromises()
    await nextTick()

    const urls = fetchMock.mock.calls.map(([input]) => String(input))
    expect(urls.some((url) => url.includes('/fixtures?') && url.includes('id=260506'))).toBe(true)
    expect(urls.some((url) => url.includes('/fixtures/events?'))).toBe(true)
    expect(urls.some((url) => url.includes('/fixtures/statistics?'))).toBe(true)
    expect(urls.some((url) => url.includes('/fixtures/lineups?'))).toBe(false)
    expect(urls.some((url) => url.includes('/fixtures/players?'))).toBe(true)
    expect(urls.some((url) => url.includes('/teams?'))).toBe(false)
    expect(wrapper.findAll('.rating-chip').map((node) => node.text())).toContain('8.6')
  })

  it('refreshes API-Football lineups every 120 seconds without reloading teams', async () => {
    vi.useFakeTimers()
    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>

    homeFormation = '5-4-1'
    fetchMock.mockClear()
    vi.advanceTimersByTime(119_999)
    await flushPromises()
    await nextTick()

    expect(fetchMock.mock.calls.some(([input]) => String(input).includes('/fixtures/lineups?'))).toBe(false)

    fetchMock.mockClear()
    vi.advanceTimersByTime(1)
    await flushPromises()
    await nextTick()

    const urls = fetchMock.mock.calls.map(([input]) => String(input))
    expect(urls.filter((url) => url.includes('/fixtures/lineups?'))).toHaveLength(1)
    expect(urls.some((url) => url.includes('/fixtures/players?'))).toBe(true)
    expect(urls.some((url) => url.includes('/teams?'))).toBe(false)
    expect(wrapper.findAll('[data-testid=formation-trigger]').map((node) => node.text())).toContain('5-4-1')
  })

  it.each([
    ['premier-league', 'dial'],
    ['champions-league', 'matrix'],
    ['europa-league', 'timeline'],
    ['carabao-cup', 'ticket'],
    ['fa-cup', 'tower'],
    ['world-cup-2026', 'ribbon'],
  ])('maps %s to the recommended stats board variant', async (league, variant) => {
    const wrapper = await mountBroadcast(`?fixtureId=260506&league=${league}`)

    expect(wrapper.get('[data-testid=stats-card]').attributes('data-variant')).toBe(variant)
  })

  it('renders live formation cards from API-Football lineups', async () => {
    const wrapper = await mountBroadcast('?fixtureId=260506&league=champions-league')

    expect(wrapper.get('[data-testid=character-safe-zone]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid=formation-card]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid=formation-trigger]').map((node) => node.text())).toEqual([
      '4-3-3',
      '4-2-3-1',
    ])
    expect(wrapper.findAll('[data-testid=player-marker]')).toHaveLength(22)
    expect(wrapper.text()).toContain('손흥민')
    expect(wrapper.text()).not.toContain('손흥민 풀네임')
    expect(wrapper.text()).toContain('네이마르')
  })

  it('replaces the formation player directly when a substitution event is received', async () => {
    vi.useFakeTimers()
    const wrapper = await mountBroadcast('?fixtureId=260506&league=champions-league')

    expect(wrapper.findAll('.player-name').map((node) => node.text())).toContain('손흥민')
    expect(wrapper.findAll('.player-name').map((node) => node.text())).not.toContain('조규성')

    fixtureEvents = [
      ...defaultFixtureEvents(),
      {
        time: { elapsed: 64 },
        team: { id: 10, name: 'Korea Republic', code: 'KOR' },
        player: { id: 1010, name: 'Son Heung-Min' },
        assist: { id: 1012, name: 'Cho Gue-Sung' },
        type: 'subst',
        detail: 'Substitution 1',
      },
    ]

    vi.advanceTimersByTime(10_000)
    await flushPromises()
    await nextTick()

    const playerNames = wrapper.findAll('.player-name').map((node) => node.text())
    expect(playerNames).toContain('조규성')
    expect(playerNames).not.toContain('조규성 풀네임')
    expect(playerNames).not.toContain('손흥민')
    const substitutedNode = wrapper
      .findAll('.player-node')
      .find((node) => node.text().includes('조규성'))
    expect(substitutedNode?.find('.shirt').text()).toBe('12')
    expect(
      substitutedNode
        ?.find('[data-testid=player-status-icons]')
        .exists(),
    ).toBe(true)
  })

  it('renders pitch markings and live player rating chips instead of position chips', async () => {
    const wrapper = await mountBroadcast('?fixtureId=260506')

    expect(wrapper.findAll('[data-testid=field-markings]')).toHaveLength(2)
    expect(wrapper.findAll('[data-testid=center-circle]')).toHaveLength(2)
    expect(wrapper.findAll('.penalty-box')).toHaveLength(4)
    expect(wrapper.findAll('.rating-chip').length).toBeGreaterThan(0)
    expect(wrapper.findAll('.rating-chip').map((node) => node.text())).toContain('8.2')
    const lowRating = wrapper.findAll('.rating-chip').find((node) => node.text() === '5.4')
    const highRating = wrapper.findAll('.rating-chip').find((node) => node.text() === '8.2')
    expect(lowRating?.attributes('style')).toContain('--rating-bg-top: hsl(356')
    expect(highRating?.attributes('style')).toContain('--rating-bg-top: hsl(221')
    expect(wrapper.findAll('.position-chip')).toHaveLength(0)
  })

  it('places formation players by API-Football grid instead of startXI array order', async () => {
    reverseHomeBackLine = true
    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const homeNodes = wrapper.findAll('[data-testid=formation-card]')[0].findAll('.player-node')
    const leftBack = homeNodes.find((node) => node.text().includes('Jin-Su'))
    const rightBack = homeNodes.find((node) => node.text().includes('Moon-Hwan'))

    expect(leftBack?.attributes('style')).toContain('left: 12%; top: 70%;')
    expect(rightBack?.attributes('style')).toContain('left: 88%; top: 70%;')
  })

  it('uses API-Football grid rows for every formation line', async () => {
    homeFormation = '4-2-3-1'
    homeLineupGrids = [
      '1:1',
      '2:4',
      '2:3',
      '2:2',
      '2:1',
      '3:2',
      '3:1',
      '4:3',
      '4:2',
      '4:1',
      '5:1',
    ]
    const wrapper = await mountBroadcast('?fixtureId=260506&league=premier-league')
    const homeNodes = wrapper.findAll('[data-testid=formation-card]')[0].findAll('.player-node')
    const leftAttacker = homeNodes.find((node) => node.text().includes('손흥민'))
    const rightAttacker = homeNodes.find((node) => node.text().includes('Kang-In'))
    const striker = homeNodes.find((node) => node.text().includes('Jae-Sung'))

    expect(leftAttacker?.attributes('style')).toContain('left: 22%; top: 36.8%;')
    expect(rightAttacker?.attributes('style')).toContain('left: 78%; top: 36.8%;')
    expect(striker?.attributes('style')).toContain('left: 50%; top: 14%;')
  })

  it('generates absolute coordinates for uncommon 3-back to 6-back shapes', async () => {
    homeFormation = '6-3-1'
    awayFormation = '3-1-1-1-1-1-1-1'
    homeLineupGrids = Array(11).fill(undefined)
    awayLineupGrids = Array(11).fill(undefined)
    const wrapper = await mountBroadcast('?fixtureId=260506')
    const cards = wrapper.findAll('[data-testid=formation-card]')

    expect(wrapper.findAll('[data-testid=formation-trigger]').map((node) => node.text())).toEqual([
      '6-3-1',
      '3-1-1-1-1-1-1-1',
    ])
    expect(cards[0].findAll('.player-node')[1].attributes('style')).toContain('left: 7%; top: 70%;')
    expect(cards[1].findAll('.player-node')[1].attributes('style')).toContain('left: 22%; top: 75%;')
  })

  it('keeps non-data broadcast slots and does not alert initial snapshot events', async () => {
    const wrapper = await mountBroadcast('?fixtureId=260506')

    expect(wrapper.get('[data-testid=chat-reserve]').text()).toBe('')
    expect(wrapper.find('[data-testid=event-logo-circle]').exists()).toBe(false)
    expect(wrapper.find('[data-testid=event-live-empty]').exists()).toBe(false)
  })

  it('queues newly appended live events and shows them one per alert cycle', async () => {
    vi.useFakeTimers()
    const wrapper = await mountBroadcast('?fixtureId=260506')

    fixtureEvents = [
      ...defaultFixtureEvents(),
      {
        time: { elapsed: 64 },
        team: { id: 10, name: 'Korea Republic', code: 'KOR' },
        player: { id: 7, name: 'Son Heung-Min' },
        assist: { id: 8, name: 'Lee Kang-In' },
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

    expect(wrapper.find('[data-testid=event-logo-circle]').exists()).toBe(false)

    vi.advanceTimersByTime(6_800)
    await nextTick()

    expect(wrapper.get('[data-testid=event-logo-circle]').text()).toBe('한국')
    expect(wrapper.get('[data-testid=event-title]').text()).toContain("64'")
    expect(wrapper.get('[data-testid=event-detail]').text()).toContain('손흥민')

    vi.advanceTimersByTime(8_400)
    await flushPromises()
    await nextTick()

    expect(wrapper.get('[data-testid=event-toast]').text()).toContain("66'")
    expect(wrapper.get('[data-testid=event-toast]').text()).toContain('네이마르')
  })

  it('keeps broadcast UI CSS away from chroma key colors', () => {
    const broadcastSourcePath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      '../../src/BroadcastApp.vue',
    )
    const statsBoardSourcePath = resolve(
      dirname(fileURLToPath(import.meta.url)),
      '../../src/components/broadcast/BroadcastStatsBoard.vue',
    )
    const source = [
      readFileSync(broadcastSourcePath, 'utf8'),
      readFileSync(statsBoardSourcePath, 'utf8'),
    ].join('\n')
    const sourceWithoutStageBackground = source.replace('background: #00B140;', '')

    expect(sourceWithoutStageBackground).not.toMatch(/#00B140|#00ff00|rgb\(0,\s*177,\s*64\)/i)
    expect(sourceWithoutStageBackground).not.toMatch(/backdrop-filter/i)
    expect(source.match(/#00B140/g) ?? []).toHaveLength(1)
  })
})
