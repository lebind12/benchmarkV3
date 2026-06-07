import { describe, expect, it } from 'vitest'
import {
  HOME_FIXTURE_LEAGUE_TABS,
  HOME_LEAGUE_TABS,
  LEAGUE_ID_TO_SLUG,
  isPrimaryHomeFixtureLeague,
  leagueLogoUrl,
  leagueVar,
  slugFromId,
} from '@/lib/league-colors'

describe('league-colors', () => {
  it('maps known league ids to slugs', () => {
    expect(slugFromId(1)).toBe('world-cup-2026')
    expect(slugFromId(39)).toBe('premier-league')
    expect(slugFromId(2)).toBe('champions-league')
    expect(slugFromId(3)).toBe('europa-league')
    expect(slugFromId(48)).toBe('carabao-cup')
    expect(slugFromId(45)).toBe('fa-cup')
  })
  it('returns null for unknown id', () => {
    expect(slugFromId(9999)).toBeNull()
    expect(slugFromId(null)).toBeNull()
  })
  it('leagueVar formats CSS var', () => {
    expect(leagueVar('premier-league', 'primary')).toBe('var(--league-epl-primary)')
    expect(leagueVar('champions-league', 'on-primary')).toBe('var(--league-ucl-on-primary)')
    expect(leagueVar('world-cup-2026', 'accent')).toBe('var(--league-wc-accent)')
  })
  it('leagueVar falls back to muted for null slug', () => {
    expect(leagueVar(null, 'primary')).toContain('--muted')
  })
  it('covers all 5 default leagues plus World Cup', () => {
    expect(Object.keys(LEAGUE_ID_TO_SLUG)).toHaveLength(6)
  })
  it('provides home tabs and API-Football logo URLs', () => {
    expect(HOME_LEAGUE_TABS.map((tab) => tab.id)).toEqual([null, 1, 39, 2, 3, 48, 45])
    expect(leagueLogoUrl(1)).toBe('https://media.api-sports.io/football/leagues/1.png')
  })
  it('adds an other tab for fixtures without treating it as a primary timeline league', () => {
    expect(HOME_FIXTURE_LEAGUE_TABS.map((tab) => tab.id)).toEqual([
      null,
      1,
      39,
      2,
      3,
      48,
      45,
      'other',
    ])
    expect(isPrimaryHomeFixtureLeague(39)).toBe(true)
    expect(isPrimaryHomeFixtureLeague(10)).toBe(false)
  })
})
