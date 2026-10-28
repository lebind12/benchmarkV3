import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { articlePieces } from './annotations'
import ArticleAnnotations from './ArticleAnnotations.vue'
import { generalApi, type PlayerDetailPayload, type TeamDetailPayload } from '@/lib/api/general'
import type { NewsMention } from '@/lib/api/news-analysis'
const mention = (name: string, evidence = name, id = 1, kind: 'team' | 'player' = 'team'): NewsMention => ({ mention: name, evidence, entity_type: kind, status: 'linked', reason: '확인', entity: { id, name, detail_path: `/${kind === 'team' ? 'teams' : 'players'}/${name.toLowerCase().replaceAll(' ', '-')}` } })
const ref = { external_id: 1, slug: 'arsenal', name: 'Arsenal', name_ko: '아스널', short_name_ko: null, logo_url: null }
const league = { external_id: 39, slug: 'premier-league' as const, name: 'Premier League', name_ko: '프리미어리그', short_name_ko: null, logo_url: null }
const team: TeamDetailPayload = { team: ref, country: null, founded: null, coach: null, venue: null, leagues: [], fixtures: [], recent_results: [], upcoming_fixtures: [], squad: [] }
const stats = { season: 2026, league, team: ref, position: null, appearances: 0, minutes: null, rating: null, goals: null, assists: 2, yellow_cards: null, red_cards: null }
const player: PlayerDetailPayload = { player: { ...ref, photo_url: null }, profile: { firstname: null, lastname: null, age: null, birth_date: null, birth_place: null, birth_country: null, nationality: null, height_cm: null, weight_kg: null }, current_team: ref, season_stats: [stats, { ...stats, league: { ...league, external_id: 2, name_ko: '챔피언스리그' } }, { ...stats, season: 2025, appearances: 99 }] }
const wrappers: ReturnType<typeof mount>[] = []
function render(text: string, mentions: NewsMention[], loadDetail?: (item: NewsMention) => Promise<{ kind: 'team'; data: TeamDetailPayload } | { kind: 'player'; data: PlayerDetailPayload }>) {
  const wrapper = mount(ArticleAnnotations, { props: { text, mentions, loadDetail }, attachTo: document.body, global: { stubs: { RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' } } } })
  wrappers.push(wrapper); return wrapper
}
afterEach(() => { wrappers.splice(0).forEach(w => w.unmount()); document.body.innerHTML = ''; vi.restoreAllMocks(); vi.useRealTimers() })

describe('original text segmentation', () => {
  it('preserves emoji/whitespace/HTML and only highlights evidence occurrence', () => {
    const text = '⚽  Arsenal 먼저\n\nArsenal의 선수 <b>Arsenal</b>  '
    const pieces = articlePieces(text, [mention('Arsenal', 'Arsenal의 선수')])
    expect(pieces.map(p => p.text).join('')).toBe(text)
    expect(pieces.filter(p => p.mention).map(p => p.start)).toEqual([text.indexOf('Arsenal의')])
    const wrapper = render(text, [mention('Arsenal', 'Arsenal의 선수')])
    expect(wrapper.get('.annotated-article').element.textContent).toBe(text)
    expect(wrapper.find('b').exists()).toBe(false)
  })
  it('rejects unsupported/partial occurrences and chooses longest overlap', () => {
    expect(articlePieces('NotArsenal', [mention('Arsenal')]).some(p => p.mention)).toBe(false)
    expect(articlePieces('NotJoão Pedro', [mention('João Pedro')]).some(p => p.mention)).toBe(false)
    expect(articlePieces('Arsenal', [mention('Arsenal', 'invented')]).some(p => p.mention)).toBe(false)
    expect(articlePieces('João Pedro가 골', [mention('Pedro'), mention('João Pedro')]).filter(p => p.mention).map(p => p.text)).toEqual(['João Pedro'])
    expect(articlePieces('아스널은 강하다', [mention('아스널')]).some(p => p.mention)).toBe(true)
  })
  it('holds identical ranges with conflicting identities and deduplicates the same identity', () => {
    expect(articlePieces('Arsenal', [mention('Arsenal'), mention('Arsenal', 'Arsenal', 2)]).some(p => p.mention)).toBe(false)
    expect(articlePieces('Arsenal', [mention('Arsenal'), mention('Arsenal', 'Arsenal', 1, 'player')]).some(p => p.mention)).toBe(false)
    expect(articlePieces('Arsenal', [mention('Arsenal'), mention('Arsenal')]).filter(p => p.mention)).toHaveLength(1)
  })
})
describe('card interaction and data', () => {
  it('retains hover movement, closes on outside/Escape and reuses GET', async () => {
    vi.useFakeTimers()
    const get = vi.spyOn(generalApi, 'team').mockResolvedValue(team)
    const wrapper = render('Arsenal의 경기', [mention('Arsenal')])
    const button = wrapper.get('button.annotated-name')
    await button.trigger('mouseenter'); await flushPromises()
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('국가정보 없음')
    await button.trigger('mouseleave')
    document.querySelector('[role="dialog"]')!.dispatchEvent(new MouseEvent('mouseenter'))
    await vi.advanceTimersByTimeAsync(250)
    expect(document.querySelector('[role="dialog"]')).not.toBeNull()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
    await button.trigger('click'); await flushPromises()
    expect(get).toHaveBeenCalledTimes(1)
    wrapper.get('.annotated-article').element.dispatchEvent(new Event('pointerdown', { bubbles: true })); await flushPromises()
    expect(document.querySelector('[role="dialog"]')).toBeNull()
  })
  it('focus opens and Tab enters card, failed GET retries', async () => {
    const get = vi.spyOn(generalApi, 'team').mockRejectedValueOnce(new Error('network')).mockResolvedValue(team)
    const wrapper = render('Arsenal', [mention('Arsenal')])
    const button = wrapper.get('button.annotated-name')
    ;(button.element as HTMLButtonElement).focus(); await flushPromises()
    expect(document.querySelector('[role="alert"]')?.textContent).toContain('불러오지 못했습니다')
    await button.trigger('keydown', { key: 'Tab' })
    expect(document.querySelector('[role="dialog"]')!.contains(document.activeElement)).toBe(true)
    ;(document.querySelector('.card-retry') as HTMLButtonElement).click(); await flushPromises()
    expect(get).toHaveBeenCalledTimes(2)
    expect(document.querySelector('[role="dialog"]')?.textContent).toContain('경기 정보 없음')
  })
  it('reverse responses stay separate; latest per competition only and NULL differs from zero', async () => {
    let resolveTeam!: (value: { kind: 'team'; data: TeamDetailPayload }) => void
    const loader = vi.fn((item: NewsMention) => item.entity_type === 'team' ? new Promise<{kind:'team';data:TeamDetailPayload}>(resolve => { resolveTeam = resolve }) : Promise.resolve({kind:'player' as const, data:player}))
    const wrapper = render('Arsenal Bukayo Saka', [mention('Arsenal'), mention('Bukayo Saka', 'Bukayo Saka', 2, 'player')], loader)
    const buttons = wrapper.findAll('button.annotated-name')
    await buttons[0]!.trigger('click'); await flushPromises()
    expect(document.querySelector('[role="status"]')?.textContent).toContain('불러오는 중')
    await buttons[1]!.trigger('click'); await flushPromises()
    resolveTeam({kind:'team', data:team}); await flushPromises()
    const content = document.querySelector('[role="dialog"]')!.textContent!
    expect(content).toContain('Bukayo Saka')
    expect(content).toContain('2026 · 프리미어리그')
    expect(content).toContain('2026 · 챔피언스리그')
    expect(content).toContain('출전 0 · 골 정보 없음 · 도움 2')
    expect(content).not.toContain('99')
    expect(content).not.toContain('홈구장')
    expect(document.querySelector('.card-detail')?.getAttribute('href')).toBe('/players/bukayo-saka')
  })
})
