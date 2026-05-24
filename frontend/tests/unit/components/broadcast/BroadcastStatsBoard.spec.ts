import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BroadcastStatsBoard from '@/components/broadcast/BroadcastStatsBoard.vue'

const stats = [
  { label: '점유율', home: '44%', away: '56%', homePct: 44, awayPct: 56 },
  { label: '전체슈팅', home: '2', away: '1', homePct: 67, awayPct: 33 },
]

describe('BroadcastStatsBoard', () => {
  it('renders team logos inside the Premier League possession area', () => {
    const wrapper = mount(BroadcastStatsBoard, {
      props: {
        league: 'premier-league',
        themeLabel: '프리미어리그',
        home: '첼시',
        away: '토트넘',
        homeCode: 'CHE',
        awayCode: 'TOT',
        homeLogoUrl: 'https://example.com/chelsea.png',
        awayLogoUrl: 'https://example.com/tottenham.png',
        score: '1 : 0',
        clock: '90:00',
        status: '종료',
        stats,
      },
    })

    const homeLogo = wrapper.get('[data-testid=stats-possession-home-logo]')
    const awayLogo = wrapper.get('[data-testid=stats-possession-away-logo]')

    expect(homeLogo.find('img').attributes('src')).toBe('https://example.com/chelsea.png')
    expect(awayLogo.find('img').attributes('src')).toBe('https://example.com/tottenham.png')
  })
})
