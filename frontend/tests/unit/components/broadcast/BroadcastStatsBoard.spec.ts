import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import BroadcastStatsBoard from '@/components/broadcast/BroadcastStatsBoard.vue'

const stats = [
  { label: '점유율', home: '44%', away: '56%', homePct: 44, awayPct: 56 },
  { label: 'xG', home: '1.4', away: '0.8', homePct: 64, awayPct: 36 },
  { label: '전체슈팅', home: '10', away: '8', homePct: 56, awayPct: 44 },
  { label: '유효슈팅', home: '4', away: '2', homePct: 67, awayPct: 33 },
  { label: '박스안슈팅', home: '7', away: '5', homePct: 58, awayPct: 42 },
  { label: '코너킥', home: '6', away: '3', homePct: 67, awayPct: 33 },
  { label: '패스성공률', home: '82%', away: '77%', homePct: 52, awayPct: 48 },
  { label: '오프사이드', home: '1', away: '2', homePct: 33, awayPct: 67 },
  { label: '파울', home: '9', away: '12', homePct: 43, awayPct: 57 },
  { label: '옐로카드', home: '1', away: '2', homePct: 33, awayPct: 67 },
  { label: '레드카드', home: '0', away: '0', homePct: 50, awayPct: 50 },
]

function mountBoard() {
  return mount(BroadcastStatsBoard, {
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
      fixtureId: 987,
    },
  })
}

describe('BroadcastStatsBoard', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders team logos and a data-driven ring inside the Premier League possession area', async () => {
    const wrapper = mountBoard()

    const homeLogo = wrapper.get('[data-testid=stats-possession-home-logo]')
    const awayLogo = wrapper.get('[data-testid=stats-possession-away-logo]')
    const homeValue = wrapper.get('[data-testid=stats-possession-home-value]')
    const awayValue = wrapper.get('[data-testid=stats-possession-away-value]')

    expect(homeLogo.find('img').attributes('src')).toBe('https://example.com/chelsea.png')
    expect(awayLogo.find('img').attributes('src')).toBe('https://example.com/tottenham.png')
    expect(homeValue.text()).toBe('44%')
    expect(awayValue.text()).toBe('56%')
    expect(wrapper.findAll('.dial-ring strong')).toHaveLength(0)
    expect(wrapper.get('[data-testid=stats-possession-ring]').attributes('style')).toContain(
      '--dial-possession-away-angle: 201.6deg',
    )

    await wrapper.setProps({
      stats: stats.map((stat) => stat.label === '점유율'
        ? { ...stat, home: '70%', away: '30%', homePct: 70, awayPct: 30 }
        : stat),
    })

    expect(wrapper.get('[data-testid=stats-possession-ring]').attributes('style')).toContain(
      '--dial-possession-away-angle: 108deg',
    )
  })

  it('falls back to an even possession split while possession data is unavailable', async () => {
    const wrapper = mountBoard()

    await wrapper.setProps({ stats: stats.filter((stat) => stat.label !== '점유율') })

    expect(wrapper.get('[data-testid=stats-possession-home-value]').text()).toBe('50%')
    expect(wrapper.get('[data-testid=stats-possession-away-value]').text()).toBe('50%')
    expect(wrapper.get('[data-testid=stats-possession-ring]').attributes('style')).toContain(
      '--dial-possession-away-angle: 180deg',
    )

    await wrapper.setProps({ stats: [] })

    expect(wrapper.find('[data-testid=stats-empty]').exists()).toBe(false)
    expect(wrapper.get('[data-testid=stats-possession-home-value]').text()).toBe('50%')
    expect(wrapper.get('[data-testid=stats-possession-away-value]').text()).toBe('50%')
  })

  it('groups the EPL lower stats into five tabs with three broadcast-style metrics', async () => {
    const wrapper = mountBoard()

    expect(wrapper.findAll('[role=tab]')).toHaveLength(5)
    expect(wrapper.get('[data-testid=dial-stat-tab-attack]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid=dial-stat-panel-attack]').text()).toContain('xG')
    expect(wrapper.get('[data-testid=dial-stat-panel-attack]').text()).toContain('유효슈팅')
    expect(wrapper.get('[data-testid=dial-stat-panel-attack]').text()).toContain('슈팅정확도')
    expect(wrapper.findAll('[data-testid=dial-stat-metric]')).toHaveLength(3)
    expect(wrapper.findAll('.dial-stat-bar')).toHaveLength(6)

    const attackMetrics = wrapper.findAll('[data-testid=dial-stat-metric]')
    expect(attackMetrics[0].attributes('data-scale-kind')).toBe('continuous')
    expect(attackMetrics[0].attributes('data-scale-max')).toBe('3')
    expect(attackMetrics[1].attributes('data-scale-kind')).toBe('count')
    expect(attackMetrics[1].attributes('data-scale-max')).toBe('5')
    expect(attackMetrics[2].attributes('data-scale-kind')).toBe('percentage')
    expect(attackMetrics[2].attributes('data-scale-max')).toBe('100')

    await wrapper.get('[data-testid=dial-stat-tab-chance]').trigger('click')
    expect(wrapper.get('[data-testid=dial-stat-panel-chance]').text()).toContain('박스안슈팅')
    expect(wrapper.findAll('[data-testid=dial-stat-metric]')[0].attributes('data-scale-max')).toBe('12')

    const viewport = wrapper.get('[data-testid=dial-stat-viewport]')
    await viewport.trigger('pointerdown', { clientX: 180, pointerType: 'touch' })
    await viewport.trigger('pointerup', { clientX: 80, pointerType: 'touch' })
    expect(wrapper.get('[data-testid=dial-stat-tab-control]').attributes('aria-selected')).toBe('true')
    expect(wrapper.get('[data-testid=dial-stat-panel-control]').text()).toContain('점유율')
  })

  it('keeps zero count values at zero height on a dynamic count scale', async () => {
    const wrapper = mountBoard()

    await wrapper.get('[data-testid=dial-stat-tab-discipline]').trigger('click')
    const redCardMetric = wrapper.findAll('[data-testid=dial-stat-metric]')
      .find((metric) => metric.text().includes('레드카드'))

    expect(redCardMetric?.attributes('data-scale-kind')).toBe('count')
    expect(redCardMetric?.attributes('data-scale-max')).toBe('1')
    expect(redCardMetric?.attributes('style')).toContain('--dial-home-pct: 0%')
    expect(redCardMetric?.attributes('style')).toContain('--dial-away-pct: 0%')
  })

  it('waits for the centered generate action before loading the AI match review', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        available: true,
        cached: true,
        commentary: {
          headline: '첼시가 흐름을 주도했습니다',
          oneLineSummary: '유효슈팅 우위를 바탕으로 리드를 지켰습니다.',
          mainCommentary: '토트넘의 후반 압박에도 첼시가 위험 지역을 잘 통제했습니다.',
        },
      }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountBoard()

    await wrapper.get('[data-testid=dial-stat-tab-ai]').trigger('click')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid=dial-ai-generate]').text()).toContain('AI 경기요약 생성')

    await wrapper.get('[data-testid=dial-ai-generate]').trigger('click')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/broadcast/fixtures/987/ai-review'),
      expect.objectContaining({ method: 'POST' }),
    )
    expect(wrapper.get('[data-testid=dial-ai-review]').text()).toContain('첼시가 흐름을 주도했습니다')
    expect(wrapper.get('[data-testid=dial-ai-review]').text()).toContain('유효슈팅 우위')
  })
})
