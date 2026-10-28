import { describe, expect, it } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NewsAnalysisView from '@/views/NewsAnalysisView.vue'
import { useAuthStore } from '@/stores/auth'
import { validateNewsInput, type NewsAnalysisResult } from '@/lib/api/news-analysis'

function render(active = true, role: 'USER' | 'STREAMER' | 'ADMIN' = 'STREAMER', analyze?: () => Promise<NewsAnalysisResult>) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().setUser({ id: 1, email: 'test@example.com', role, nickname: null, is_active: active })
  return mount(NewsAnalysisView, { props: { analyze }, global: { plugins: [pinia], stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
}
async function fill(wrapper: ReturnType<typeof render>) {
  await wrapper.get('#na-source').setValue('https://example.com/article')
  await wrapper.get('#na-article').setValue('아스널이 경기를 준비한다.')
}
describe('news analysis input', () => {
  it('requires text, bounded lengths and an HTTP(S) source without credentials', () => {
    for (const source_url of ['', 'javascript:alert(1)', 'ftp://example.com', 'https://user:pass@example.com', 'https://' + 'a'.repeat(2050)]) {
      expect(validateNewsInput({ article_text: '기사', source_url })).not.toBe('')
    }
    expect(validateNewsInput({ article_text: ' ', source_url: 'https://example.com' })).not.toBe('')
    expect(validateNewsInput({ article_text: 'a'.repeat(20001), source_url: 'https://example.com' })).not.toBe('')
    expect(validateNewsInput({ article_text: '기사', source_url: 'http://example.com' })).toBe('')
  })
})
describe('news analysis interaction', () => {
  it('does not highlight links for non-football or uncertain results', async () => {
    for (const relevance of ['not_football', 'uncertain'] as const) {
      const wrapper = render(true, 'STREAMER', async () => ({
        relevance, relevance_evidence: '아스널', source_url: 'https://example.com/article',
        mentions: [{ mention: '아스널', evidence: '아스널', entity_type: 'team', status: 'linked', reason: 'untrusted', entity: { id: 1, name: '아스널', detail_path: '/teams/arsenal' } }],
      }))
      await fill(wrapper); await wrapper.get('form').trigger('submit'); await flushPromises()
      expect(wrapper.find('.annotated-name').exists()).toBe(false)
      expect(wrapper.get('.annotated-article').element.textContent).toBe('아스널이 경기를 준비한다.')
      expect(wrapper.text()).toContain(relevance === 'not_football' ? '축구 이외의 주제' : '축구 관련성을 확인할 근거가 부족')
      wrapper.unmount()
    }
  })
  it('rejects USER and inactive managers in the view', () => {
    expect(render(true, 'USER').find('form').exists()).toBe(false)
    expect(render(false).find('form').exists()).toBe(false)
    expect(render(true, 'ADMIN').find('form').exists()).toBe(true)
  })
  it('prevents duplicate submits and discards a response after input changes', async () => {
    let resolve!: (value: NewsAnalysisResult) => void
    let calls = 0
    const wrapper = render(true, 'STREAMER', () => { calls++; return new Promise(done => { resolve = done }) })
    await fill(wrapper)
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(calls).toBe(1)
    expect(wrapper.get('[type="submit"]').attributes('disabled')).toBeDefined()
    await wrapper.get('#na-article').setValue('새로운 기사')
    resolve({ relevance: 'football', relevance_evidence: '아스널', source_url: 'https://example.com/old', mentions: [] })
    await flushPromises()
    expect(wrapper.text()).not.toContain('분석 완료')
    expect(wrapper.get('#na-article').element).toHaveProperty('value', '새로운 기사')
  })
  it('retains input on error and supports retry, empty, linked and held results', async () => {
    let fail = true
    const wrapper = render(true, 'STREAMER', async () => {
      if (fail) throw new Error('분석 실패')
      return { relevance: 'football', relevance_evidence: '아스널', source_url: 'https://example.com/article', mentions: [] }
    })
    await fill(wrapper)
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('분석 실패')
    expect(wrapper.get('#na-article').element).toHaveProperty('value', '아스널이 경기를 준비한다.')
    fail = false
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(wrapper.text()).toContain('연결할 대상을 확인하지 못했습니다')
    wrapper.unmount()
    const results = render(true, 'ADMIN', async () => ({ relevance: 'football', relevance_evidence: '아스널', source_url: 'https://example.com/article', mentions: [
      { mention: '아스널', evidence: '<script>alert(1)</script>', entity_type: 'team', status: 'linked', reason: '근거 확인', entity: { id: 1, name: '아스널', detail_path: '/teams/arsenal' } },
      { mention: '김민수', evidence: '김민수', entity_type: 'player', status: 'ambiguous', reason: '동명이인', entity: null },
      { mention: '알렉스', evidence: '알렉스', entity_type: 'player', status: 'unresolved', reason: '후보 없음', entity: null },
    ] }))
    await fill(results); await results.get('form').trigger('submit'); await flushPromises()
    expect(results.text()).toContain('연결 1 · 보류 2')
    expect(results.text()).toContain('보류 · 후보 없음')
    expect(results.find('script').exists()).toBe(false)
    expect(results.find('.annotated-article').exists()).toBe(true)
  })
})
