import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import BundleGenerationPanel from './BundleGenerationPanel.vue'
import InlineEmphasis from './InlineEmphasis.vue'
import type { FixtureCandidate } from './fixtures'
import type { BundlePreviewRunResponse } from './types'

const api = vi.hoisted(() => ({ fixture: vi.fn(), runBundle: vi.fn() }))
vi.mock('./api', () => ({ previewRunsApi: api }))
// 컴포넌트가 `<script setup>` 안에서 import한 RouterLink는 `global.stubs`로 바뀌지 않고
// 실제 링크가 라우터 주입을 요구한다. 검사는 라우팅이 아니라 화면 동작을 보므로 모듈을 바꾼다.
vi.mock('vue-router', () => ({
  RouterLink: { template: '<a><slot /></a>' },
}))
vi.mock('./MatchPreview.vue', () => ({
  default: { props: ['runId'], template: '<p data-testid="stored-preview">DB 조회 실행 {{ runId }}</p>' },
}))

const fixture: FixtureCandidate = {
  fixture_id: 1557474, league_id: 39, league_name: 'Premier League', season: 2026,
  home_team_id: 13, away_team_id: 4, home_team_name: '맨체스터 시티', away_team_name: '풀럼',
  label: '맨체스터 시티 vs 풀럼', kickoff_at: '2026-11-21T12:30:00Z', status_short: 'NS',
  origin: 'stored_db', origin_note: '', run_id: null, mode: null, selectable: true,
}
const saved: BundlePreviewRunResponse = {
  run_id: 'saved-run', mode: 'live', status: 'succeeded', quality: 'insufficient',
  bundle_id: 'saved-bundle', bundle_hash: null, bundle_artifact_id: null,
  section_result_ids: {}, section_quality: {}, section_unavailable: { section_odds: '배당 없음' },
  discovery_status: {}, external_calls: 6, budget: {}, unavailable_reason: null, note: '',
}
const options = {
  props: { fixture: null },
  global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
}

describe('관리자 경기 번호 전체 생성', () => {
  beforeEach(() => vi.clearAllMocks())

  it('화면 진입과 잘못된 번호 입력만으로는 생성하지 않는다', async () => {
    const wrapper = mount(BundleGenerationPanel, options)
    expect(api.runBundle).not.toHaveBeenCalled()
    expect(api.fixture).not.toHaveBeenCalled()
    await wrapper.get('input').setValue('-1')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.text()).toContain('양의 정수')
    expect(api.fixture).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="bundle-generate"]').attributes('disabled')).toBeDefined()
  })

  it('번호 확인 후 해당 경기 하나만 생성하며 재조회는 생성 요청을 반복하지 않는다', async () => {
    api.fixture.mockResolvedValue({ ok: true, data: fixture })
    api.runBundle.mockResolvedValue({ ok: true, data: saved })
    const wrapper = mount(BundleGenerationPanel, options)
    await wrapper.get('input').setValue('1557474')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.fixture).toHaveBeenCalledWith(1557474)
    expect(wrapper.get('[data-testid="bundle-confirmed-fixture"]').text()).toContain(fixture.label)
    expect(api.runBundle).not.toHaveBeenCalled()
    await wrapper.get('[data-testid="bundle-generate"]').trigger('click')
    await flushPromises()
    expect(api.runBundle).toHaveBeenCalledTimes(1)
    expect(api.runBundle).toHaveBeenCalledWith(1557474)
    expect(wrapper.get('[data-testid="stored-preview"]').text()).toContain('saved-run')
    const reread = wrapper.findAll('button').find((button) => button.text() === '저장 결과 다시 읽기')
    expect(reread).toBeDefined()
    await reread?.trigger('click')
    await flushPromises()
    expect(api.runBundle).toHaveBeenCalledTimes(1)
    expect(wrapper.get('[data-testid="stored-preview"]').text()).toContain('saved-run')
  })

  it('경기가 없으면 생성을 열지 않고, 확인 후 번호를 바꾸어도 다시 확인해야 한다', async () => {
    api.fixture.mockResolvedValueOnce({ ok: false, status: 404, kind: 'unknown', message: '' })
      .mockResolvedValueOnce({ ok: true, data: fixture })
    const wrapper = mount(BundleGenerationPanel, options)
    await wrapper.get('input').setValue('123')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('저장된 경기가 없습니다')
    expect(api.runBundle).not.toHaveBeenCalled()
    await wrapper.get('input').setValue('1557474')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('input').setValue('1557475')
    expect(wrapper.get('[data-testid="bundle-generate"]').attributes('disabled')).toBeDefined()
  })

  it('생성 중 중복 클릭을 막고 연결 오류 때 자동 재전송하지 않는다', async () => {
    let finish: (value: unknown) => void = () => undefined
    api.runBundle.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    const wrapper = mount(BundleGenerationPanel, { ...options, props: { fixture } })
    await wrapper.get('[data-testid="bundle-generate"]').trigger('click')
    await wrapper.get('[data-testid="bundle-generate"]').trigger('click')
    expect(api.runBundle).toHaveBeenCalledTimes(1)
    expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    finish({ ok: false, kind: 'network', status: 0, message: '' })
    await flushPromises()
    expect(wrapper.text()).toContain('실행 목록을 먼저 확인')
    expect(api.runBundle).toHaveBeenCalledTimes(1)
  })
})

it('응답 강조는 strong으로 표시하고 HTML은 실행하지 않는다', () => {
  const wrapper = mount(InlineEmphasis, { props: { text: '**맨체스터 시티** <img src=x onerror=alert(1)>' } })
  expect(wrapper.get('strong').text()).toBe('맨체스터 시티')
  expect(wrapper.find('img').exists()).toBe(false)
  expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
})
