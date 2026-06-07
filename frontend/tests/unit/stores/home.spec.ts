import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { useHomeStore } from '@/stores/home'
import type { FixtureSummary } from '@/types/home'

function fixture(id: number, leagueId: number, leagueName: string): FixtureSummary {
  return {
    external_id: id,
    league: {
      external_id: leagueId,
      slug: leagueId === 39 ? 'premier-league' : 'friendlies',
      name_ko: leagueName,
      short_name_ko: leagueName,
      name: leagueName,
    } as FixtureSummary['league'],
    home: {
      external_id: 100 + id,
      slug: `home-${id}`,
      name_ko: `홈${id}`,
      short_name_ko: `홈${id}`,
      name: `Home ${id}`,
      logo_url: null,
    },
    away: {
      external_id: 200 + id,
      slug: `away-${id}`,
      name_ko: `원정${id}`,
      short_name_ko: `원정${id}`,
      name: `Away ${id}`,
      logo_url: null,
    },
    kickoff_at: '2026-06-07T12:00:00Z',
    status_short: 'NS',
    goals_home: null,
    goals_away: null,
  }
}

function stubFixtures(items: FixtureSummary[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ items, filters_applied: {} }),
    })),
  )
}

describe('useHomeStore (cube + filter actions)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    vi.unstubAllGlobals()
  })

  it('initial state defaults', () => {
    const s = useHomeStore()
    expect(s.cube.activeFace).toBe(0)
    expect(s.fixtures.filter.period).toBe('day')
    expect(s.fixtures.filter.league_id).toBeNull()
    expect(s.standings.league_id).toBe(39)
    expect(s.topPlayers.metric).toBe('goals')
  })

  it('nextFace cycles 0→1→2→3→0', () => {
    const s = useHomeStore()
    s.nextFace(); expect(s.cube.activeFace).toBe(1)
    s.nextFace(); expect(s.cube.activeFace).toBe(2)
    s.nextFace(); expect(s.cube.activeFace).toBe(3)
    s.nextFace(); expect(s.cube.activeFace).toBe(0)
  })

  it('setFace updates activeFace', () => {
    const s = useHomeStore()
    s.setFace(2)
    expect(s.cube.activeFace).toBe(2)
  })

  it('pauseAutoRotate clears timer', () => {
    const s = useHomeStore()
    s.startAutoRotate()
    expect(s.cube.timerHandle).not.toBeNull()
    s.pauseAutoRotate()
    expect(s.cube.paused).toBe(true)
    expect(s.cube.timerHandle).toBeNull()
  })

  it('resetFixtureFilters returns to defaults', () => {
    const s = useHomeStore()
    s.fixtures.filter.league_id = 39
    s.fixtures.filter.period = 'week'
    // stub fetch
    s.fetchFixtures = vi.fn() as any
    s.resetFixtureFilters()
    expect(s.fixtures.filter.league_id).toBeNull()
    expect(s.fixtures.filter.period).toBe('day')
  })

  it('excludes other leagues from the default fixture timeline', async () => {
    stubFixtures([
      fixture(1, 39, 'EPL'),
      fixture(2, 10, '친선전'),
    ])
    const s = useHomeStore()

    await s.fetchFixtures()

    expect(s.fixtures.data.value?.map((fx) => fx.external_id)).toEqual([1])
  })

  it('shows non-primary leagues only when the other fixture tab is selected', async () => {
    stubFixtures([
      fixture(1, 39, 'EPL'),
      fixture(2, 10, '친선전'),
    ])
    const s = useHomeStore()
    s.fixtures.filter.league_id = 'other'

    await s.fetchFixtures()

    expect(s.fixtures.data.value?.map((fx) => fx.external_id)).toEqual([2])
  })
})
