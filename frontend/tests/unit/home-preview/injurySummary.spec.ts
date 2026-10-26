import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import HomeInjurySummary from '@/components/home-preview/HomeInjurySummary.vue'
import records from '@/mocks/home-preview/previews.json'
import type { HomePreview } from '@/lib/api/homePreviewSchema'

function fixture(withDate: boolean) {
  const preview = structuredClone(records['90001']) as HomePreview
  const row = preview.facts.injuries.data![0]!
  row.player_id = 123
  row.detail = '허벅지 부상'
  row.cause = { status: 'available', reason: null, as_of: preview.as_of, source_ids: ['web-injury'], data: { code: 'thigh', label: '대표팀 경기 중 허벅지 부상', occurred_on: withDate ? '2026-10-03' : null, occurred_month: null } }
  preview.analysis.key_absences = { status: 'available', reason: null, as_of: preview.as_of, source_ids: row.source_ids, data: [{ team_id: row.team_id, player_id: 123, reason: '출전 기록에 따른 내부 선정 이유', evidence_ids: row.source_ids }] }
  return preview
}

describe('compact main preview absence information', () => {
  it('shows injury, cause and confirmed date without source boilerplate or selection records', () => {
    const wrapper = mount(HomeInjurySummary, { props: { preview: fixture(true) } })
    const card = wrapper.get('[data-testid="key-absence"]')
    expect(card.text()).toContain('대표팀 경기 중 허벅지 부상')
    expect(card.text()).toContain('10월 3일 발생')
    expect(card.text()).not.toMatch(/DB 기준|API-Football|원인 출처|발생 시점 출처|시즌|내부 선정 이유/)
    expect(card.find('a').exists()).toBe(false)
  })
  it('keeps the confirmed date visible when the injury anatomy is undisclosed', () => {
    const preview = fixture(true)
    preview.facts.injuries.data![0]!.cause!.data!.code = null
    preview.facts.injuries.data![0]!.cause!.data!.label = '토트넘전 부상'
    const card = mount(HomeInjurySummary, { props: { preview } }).get('[data-testid="key-absence"]')
    expect(card.text()).toContain('토트넘전 부상')
    expect(card.text()).toContain('10월 3일 발생')
  })
  it('omits the date line when no date was confirmed', () => {
    const wrapper = mount(HomeInjurySummary, { props: { preview: fixture(false) } })
    const card = wrapper.get('[data-testid="key-absence"]')
    expect(card.find('.hp-cause-date').exists()).toBe(false)
    expect(card.text()).not.toContain('발생 시점 미확인')
  })
})
