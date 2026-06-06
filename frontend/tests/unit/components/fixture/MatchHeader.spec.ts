import { afterEach, describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MatchHeader from '@/components/fixture/MatchHeader.vue'
import match1 from '@/mocks/data/fixture-detail/match.1000001.json'
import match2 from '@/mocks/data/fixture-detail/match.1000002.json'
import type { MatchDetail } from '@/types/fixtureDetail'

describe('MatchHeader', () => {
  afterEach(() => {
    localStorage.removeItem('mockRole')
  })

  it('renders score for FT match', () => {
    const w = mount(MatchHeader, {
      props: { match: match1 as unknown as MatchDetail },
    })
    expect(w.find('[data-testid=match-score]').text()).toContain('3 - 1')
    expect(w.find('[data-testid=goal-history]').exists()).toBe(true)
  })

  it('renders "vs" + kickoff label for NS match', () => {
    const w = mount(MatchHeader, {
      props: { match: match2 as unknown as MatchDetail },
    })
    expect(w.find('[data-testid=match-score]').text()).toContain('vs')
    expect(w.find('[data-testid=match-score]').text()).toMatch(/kickoff .* KST/)
  })

  it('shows 6h SLA notice', () => {
    const w = mount(MatchHeader, {
      props: { match: match1 as unknown as MatchDetail },
    })
    expect(w.text()).toContain('6시간')
  })

  it('omits null referee from meta', () => {
    const w = mount(MatchHeader, {
      props: { match: match2 as unknown as MatchDetail },
    })
    expect(w.find('[data-testid=match-meta]').text()).not.toContain('null')
  })

  it('falls back to English name when name_ko is missing', () => {
    const m = {
      ...(match1 as unknown as MatchDetail),
      home: { ...(match1 as unknown as MatchDetail).home, name_ko: null },
    }
    const w = mount(MatchHeader, { props: { match: m } })
    expect(w.html()).toContain('Liverpool')
  })

  it('opens a streaming picker with watch-together and program page links', async () => {
    localStorage.setItem('mockRole', 'ADMIN')
    const w = mount(MatchHeader, {
      props: { match: match1 as unknown as MatchDetail },
    })
    const trigger = w.find('[data-testid=broadcast-picker-trigger]')
    expect(trigger.exists()).toBe(true)
    expect(trigger.text()).toContain('스트리밍')
    expect(w.find('[data-testid=broadcast-picker]').exists()).toBe(false)

    await trigger.trigger('click')

    expect(w.find('[data-testid=broadcast-picker]').exists()).toBe(true)
    const watchTogetherLink = w.find('[data-testid=watch-together-link]')
    const programLink = w.find('[data-testid=program-link]')
    expect(watchTogetherLink.attributes('href')).toBe(
      '/broadcast.html?fixtureId=1000001&league=premier-league',
    )
    expect(watchTogetherLink.text()).toContain('같이보기 화면')
    expect(programLink.attributes('href')).toBe(
      '/broadcast-program.html?fixtureId=1000001&league=premier-league',
    )
    expect(programLink.text()).toContain('중계용 화면')
    expect(watchTogetherLink.attributes('target')).toBe('_blank')
    expect(programLink.attributes('target')).toBe('_blank')
  })

  it('closes the streaming picker from the close button', async () => {
    localStorage.setItem('mockRole', 'ADMIN')
    const w = mount(MatchHeader, {
      props: { match: match1 as unknown as MatchDetail },
    })
    await w.find('[data-testid=broadcast-picker-trigger]').trigger('click')
    expect(w.find('[data-testid=broadcast-picker]').exists()).toBe(true)

    await w.find('[data-testid=broadcast-picker-close]').trigger('click')

    expect(w.find('[data-testid=broadcast-picker]').exists()).toBe(false)
  })
})
