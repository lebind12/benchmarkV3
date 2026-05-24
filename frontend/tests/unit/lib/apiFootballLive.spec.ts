import { afterEach, describe, expect, it, vi } from 'vitest'

function jsonResponse(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => body,
  } as Response
}

describe('apiFootballLive', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.unstubAllGlobals()
    vi.resetModules()
  })

  it('fetches broadcast live data directly from API-Football without FastAPI', async () => {
    vi.stubEnv('VITE_USE_MOCK', 'false')
    vi.stubEnv('VITE_BROADCAST_USE_API_FOOTBALL', 'true')
    vi.stubEnv('VITE_API_FOOTBALL_KEY', 'test-key')

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const parsedUrl = new URL(url, 'http://localhost')

      if (parsedUrl.pathname === '/api/v1/broadcast/translations') {
        return jsonResponse({
          leagues: { 1: { name_ko: '월드컵', short_name_ko: '월드컵' } },
          teams: {
            10: { name_ko: '대한민국', short_name_ko: '한국' },
            20: { name_ko: '브라질', short_name_ko: '브라질' },
          },
          players: {
            7: { name_ko: '손흥민', short_name_ko: '손흥민' },
            8: { name_ko: '이강인', short_name_ko: '이강인' },
          },
          coaches: {},
        })
      }

      if (url.includes('/fixtures?') && url.includes('id=123')) {
        return jsonResponse({
          response: [
            {
              fixture: {
                id: 123,
                status: { short: '2H', elapsed: 63, extra: 2 },
                venue: { name: 'Live Stadium' },
              },
              league: { id: 1, name: 'FIFA World Cup', season: 2026 },
              teams: {
                home: {
                  id: 10,
                  name: 'Korea Republic',
                  code: 'KOR',
                  logo: 'api-home-logo',
                },
                away: {
                  id: 20,
                  name: 'Brazil',
                  code: 'BRA',
                  logo: 'api-away-logo',
                },
              },
              goals: { home: 1, away: 1 },
            },
          ],
        })
      }

      if (url.includes('/fixtures/events?')) {
        return jsonResponse({
          response: [
            {
              time: { elapsed: 58 },
              team: { id: 10, name: 'Korea Republic', code: 'KOR' },
              player: { id: 7, name: 'Son Heung-Min' },
              assist: { id: 8, name: 'Lee Kang-In' },
              type: 'Goal',
              detail: 'Normal Goal',
            },
            {
              time: { elapsed: 59 },
              team: { id: 20, name: 'Brazil', code: 'BRA' },
              player: { id: 9, name: 'Neymar' },
              type: 'Foul',
              detail: 'Foul',
            },
            {
              time: { elapsed: 60 },
              team: { id: 10, name: 'Korea Republic', code: 'KOR' },
              player: { id: 7, name: 'Son Heung-Min' },
              type: 'Unknown Event',
              detail: 'Match note',
            },
          ],
        })
      }

      if (url.includes('/fixtures/lineups?')) {
        return jsonResponse({ response: [] })
      }

      if (url.includes('/fixtures/statistics?')) {
        return jsonResponse({
          response: [
            {
              team: { id: 10, name: 'Korea Republic', code: 'KOR' },
              statistics: [
                { type: 'Ball Possession', value: '61%' },
                { type: 'Total Shots', value: 11 },
              ],
            },
            {
              team: { id: 20, name: 'Brazil', code: 'BRA' },
              statistics: [
                { type: 'Ball Possession', value: '39%' },
                { type: 'Total Shots', value: 8 },
              ],
            },
          ],
        })
      }

      if (url.includes('/fixtures/players?')) {
        return jsonResponse({ response: [] })
      }

      throw new Error(`unexpected url ${url}`)
    })

    vi.stubGlobal('fetch', fetchMock)
    const {
      fetchApiFootballBroadcastLineupsSnapshot,
      fetchApiFootballBroadcastTickSnapshot,
      fetchApiFootballBroadcastSnapshot,
      shouldUseApiFootballLive,
    } = await import('@/lib/api/apiFootballLive')

    const snapshot = await fetchApiFootballBroadcastSnapshot(123)

    expect(shouldUseApiFootballLive()).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(6)
    expect(fetchMock.mock.calls.slice(0, 5).every(([input]) => !String(input).includes('/api/v1'))).toBe(true)
    expect(fetchMock.mock.calls.slice(0, 5).every(([input]) =>
      String(input).startsWith('https://v3.football.api-sports.io/'),
    )).toBe(true)
    expect(fetchMock.mock.calls[5][0]).toBe('/api/v1/broadcast/translations')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      headers: expect.objectContaining({
        'x-apisports-key': 'test-key',
      }),
    })
    expect(snapshot).toMatchObject({
      fixtureId: 123,
      leagueName: '월드컵',
      home: '대한민국',
      away: '브라질',
      homeCode: '한국',
      awayCode: '브라질',
      homeEnglishCode: 'KOR',
      awayEnglishCode: 'BRA',
      homeLogoUrl: 'api-home-logo',
      awayLogoUrl: 'api-away-logo',
      score: '1 : 1',
      clock: '63:00',
      addedTime: '+2',
    })
    expect(snapshot.events[0]).toMatchObject({
      kind: 'goal',
      teamCode: '한국',
      player: '손흥민',
    })
    expect(snapshot.events).toHaveLength(1)
    expect(snapshot.stats[0]).toMatchObject({
      label: '점유율',
      home: '61%',
      away: '39%',
    })

    fetchMock.mockClear()
    const tickSnapshot = await fetchApiFootballBroadcastTickSnapshot(123, snapshot)
    const tickUrls = fetchMock.mock.calls.map(([input]) => String(input))

    expect(tickSnapshot).toMatchObject({
      fixtureId: 123,
      homeEnglishCode: 'KOR',
      awayEnglishCode: 'BRA',
    })
    expect(tickUrls.some((url) => url.includes('/fixtures?') && url.includes('id=123'))).toBe(true)
    expect(tickUrls.some((url) => url.includes('/fixtures/events?'))).toBe(true)
    expect(tickUrls.some((url) => url.includes('/fixtures/statistics?'))).toBe(true)
    expect(tickUrls.some((url) => url.includes('/fixtures/lineups?'))).toBe(false)
    expect(tickUrls.some((url) => url.includes('/fixtures/players?'))).toBe(true)
    expect(tickUrls.some((url) => url.includes('/teams?'))).toBe(false)

    fetchMock.mockClear()
    await fetchApiFootballBroadcastLineupsSnapshot(123, snapshot)
    const lineupsUrls = fetchMock.mock.calls.map(([input]) => String(input))

    expect(lineupsUrls.some((url) => url.includes('/fixtures/lineups?'))).toBe(true)
    expect(lineupsUrls.some((url) => url.includes('/fixtures?'))).toBe(false)
    expect(lineupsUrls.some((url) => url.includes('/fixtures/events?'))).toBe(false)
    expect(lineupsUrls.some((url) => url.includes('/fixtures/statistics?'))).toBe(false)
    expect(lineupsUrls.some((url) => url.includes('/fixtures/players?'))).toBe(false)
    expect(lineupsUrls.some((url) => url.includes('/teams?'))).toBe(false)
  })

  it('does not synthesize zero stats when API-Football returns no statistics', async () => {
    vi.stubEnv('VITE_API_FOOTBALL_KEY', 'test-key')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const parsedUrl = new URL(url, 'http://localhost')

      if (parsedUrl.pathname === '/api/v1/broadcast/translations') {
        return jsonResponse({ leagues: {}, teams: {}, players: {}, coaches: {} })
      }

      if (url.includes('/fixtures?') && url.includes('id=999')) {
        return jsonResponse({
          response: [{
            fixture: {
              id: 999,
              status: { short: 'NS', elapsed: null, extra: null },
              venue: { name: 'No Stats Stadium' },
            },
            league: { id: 1, name: 'FIFA World Cup', season: 2026 },
            teams: {
              home: { id: 10, name: 'Korea Republic', code: 'KOR' },
              away: { id: 20, name: 'Brazil', code: 'BRA' },
            },
            goals: { home: null, away: null },
          }],
        })
      }

      if (url.includes('/fixtures/events?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/lineups?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/statistics?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/players?')) return jsonResponse({ response: [] })

      throw new Error(`unexpected url ${url}`)
    }))

    const { fetchApiFootballBroadcastSnapshot } = await import('@/lib/api/apiFootballLive')
    const snapshot = await fetchApiFootballBroadcastSnapshot(999)

    expect(snapshot.stats).toEqual([])
  })

  it('hydrates unusable fixture team codes from API-Football teams endpoint', async () => {
    vi.stubEnv('VITE_API_FOOTBALL_KEY', 'test-key')
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const parsedUrl = new URL(url, 'http://localhost')

      if (parsedUrl.pathname === '/api/v1/broadcast/translations') {
        return jsonResponse({ leagues: {}, teams: {}, players: {}, coaches: {} })
      }

      if (url.includes('/fixtures?') && url.includes('id=777')) {
        return jsonResponse({
          response: [{
            fixture: {
              id: 777,
              status: { short: '1H', elapsed: 18, extra: 0 },
              venue: { name: 'Premier League Stadium' },
            },
            league: { id: 39, name: 'Premier League', season: 2025 },
            teams: {
              home: { id: 10, name: 'Arsenal', code: 'A' },
              away: { id: 20, name: 'Burnley', code: null },
            },
            goals: { home: 0, away: 0 },
          }],
        })
      }

      if (url.includes('/teams?') && url.includes('id=10')) {
        return jsonResponse({ response: [{ team: { id: 10, code: 'ARS' } }] })
      }

      if (url.includes('/teams?') && url.includes('id=20')) {
        return jsonResponse({ response: [{ team: { id: 20, code: 'BUR' } }] })
      }

      if (url.includes('/fixtures/events?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/lineups?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/statistics?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/players?')) return jsonResponse({ response: [] })

      throw new Error(`unexpected url ${url}`)
    })

    vi.stubGlobal('fetch', fetchMock)
    const { fetchApiFootballBroadcastSnapshot } = await import('@/lib/api/apiFootballLive')
    const snapshot = await fetchApiFootballBroadcastSnapshot(777)
    const requestedUrls = fetchMock.mock.calls.map(([input]) => String(input))

    expect(snapshot).toMatchObject({
      fixtureId: 777,
      homeEnglishCode: 'ARS',
      awayEnglishCode: 'BUR',
    })
    expect(requestedUrls.some((url) => url.includes('/teams?') && url.includes('id=10'))).toBe(true)
    expect(requestedUrls.some((url) => url.includes('/teams?') && url.includes('id=20'))).toBe(true)
  })

  it('falls back team code slots to Home and Away when API-Football has no usable codes', async () => {
    vi.stubEnv('VITE_API_FOOTBALL_KEY', 'test-key')
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      const parsedUrl = new URL(url, 'http://localhost')

      if (parsedUrl.pathname === '/api/v1/broadcast/translations') {
        return jsonResponse({ leagues: {}, teams: {}, players: {}, coaches: {} })
      }

      if (url.includes('/fixtures?') && url.includes('id=778')) {
        return jsonResponse({
          response: [{
            fixture: {
              id: 778,
              status: { short: '1H', elapsed: 18, extra: 0 },
              venue: { name: 'Premier League Stadium' },
            },
            league: { id: 39, name: 'Premier League', season: 2025 },
            teams: {
              home: { id: 10, name: 'Arsenal', code: 'A' },
              away: { id: 20, name: 'Burnley', code: null },
            },
            goals: { home: 0, away: 0 },
          }],
        })
      }

      if (url.includes('/teams?')) {
        return jsonResponse({ response: [{ team: { code: null } }] })
      }

      if (url.includes('/fixtures/events?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/lineups?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/statistics?')) return jsonResponse({ response: [] })
      if (url.includes('/fixtures/players?')) return jsonResponse({ response: [] })

      throw new Error(`unexpected url ${url}`)
    }))

    const { fetchApiFootballBroadcastSnapshot } = await import('@/lib/api/apiFootballLive')
    const snapshot = await fetchApiFootballBroadcastSnapshot(778)

    expect(snapshot).toMatchObject({
      fixtureId: 778,
      homeEnglishCode: 'Home',
      awayEnglishCode: 'Away',
    })
  })
})
