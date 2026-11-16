/**
 * 관리자 섹션 실행·이력 라우팅·인증·진입 스모크 검사.
 *
 * 확인 대상:
 * - 실제 router에 `/admin/sections`와 `/admin/runs`(name=preview-runs)가 등록돼 있다.
 * - 비로그인은 `verifySession` 확인 후 실제 `login` 라우트(`next` 포함)로 이동한다.
 * - 비ADMIN(`STREAMER`/`USER`)은 `not-found`로 이동하고 `PreviewPanel` 진입 링크가 숨겨진다.
 * - 정상 ADMIN은 `PreviewPanel`에서 `/admin/sections`·`/admin/runs`로 이동하고 새로고침이 가능하다.
 * - `SectionRunView`/`PreviewRunsView`는 `/api/v1/auth/session`이나 `admin-login`을 쓰지 않고
 *   조회 중 모델 실행(POST `/section-runs`·`/runs`)을 호출하지 않는다.
 */
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PreviewPanel from '@/components/management/PreviewPanel.vue'
import { setAccessToken } from '@/lib/api/session'
import { router } from '@/router'
import { useAuthStore } from '@/stores/auth'

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('관리자 프리뷰 라우팅·인증 스모크', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    setAccessToken(null)
    useAuthStore().logout()
    window.history.replaceState({}, '', '/')
    await router.push('/')
    await router.isReady()
  })

  afterEach(() => {
    setAccessToken(null)
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('redirects unauthenticated requests on /admin/sections and /admin/runs to login without calling /auth/session', async () => {
    const calledUrls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        calledUrls.push(url)
        return json({ detail: 'authentication required' }, 401)
      }),
    )

    await router.push('/admin/sections')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/admin/sections')

    await router.push('/admin/runs')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/admin/runs')

    expect(calledUrls.some((url) => url.includes('/api/v1/auth/session'))).toBe(false)
    expect(calledUrls.some((url) => url.includes('/api/v1/auth/refresh'))).toBe(true)
  })

  it('blocks non-admin sessions with not-found and hides admin links in PreviewPanel', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url.endsWith('/api/v1/auth/refresh')) {
          return json({ access_token: 'streamer-token' }, 200)
        }
        if (url.endsWith('/api/v1/auth/me')) {
          return json({
            user: {
              id: 2,
              email: 'streamer@local.test',
              role: 'STREAMER',
              nickname: 'streamer',
              is_active: true,
            },
          })
        }
        return json({}, 404)
      }),
    )

    await router.push('/admin/sections')
    expect(router.currentRoute.value.name).toBe('not-found')

    await router.push('/admin/runs')
    expect(router.currentRoute.value.name).toBe('not-found')

    const panel = mount(PreviewPanel, {
      props: { canGenerate: false },
      global: { plugins: [router] },
    })
    expect(panel.find('[data-testid="preview-admin-links"]').exists()).toBe(false)
    expect(panel.find('[data-testid="preview-open-sections"]').exists()).toBe(false)
  })

  it('lets ADMIN enter /admin/sections and /admin/runs from PreviewPanel and refresh cleanly with zero model calls', async () => {
    const calls: Array<{ url: string; method: string }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = typeof input === 'string' ? input : input.toString()
        const method = (init?.method ?? 'GET').toUpperCase()
        calls.push({ url, method })

        if (url.endsWith('/api/v1/auth/refresh')) {
          return json({ access_token: 'admin-token' }, 200)
        }
        if (url.endsWith('/api/v1/auth/me')) {
          return json({
            user: {
              id: 1,
              email: 'admin@local.test',
              role: 'ADMIN',
              nickname: 'admin',
              is_active: true,
            },
          })
        }
        if (url.endsWith('/api/v1/admin/preview/sections')) {
          return json({
            workflows: [
              {
                workflow_id: 'section_players',
                display_name: '주목 선수',
                description: '주목 선수 섹션',
                module_ids: ['bundle_section_players'],
                output_contract_version: 'mp11-player-section-1',
                implemented: true,
                unrunnable_reason: null,
              },
            ],
            availability: {
              section_players: {
                workflow_id: 'section_players',
                display_name: '주목 선수',
                module_ids: ['bundle_section_players'],
                output_contract_version: 'mp11-player-section-1',
                implemented: true,
                missing_implementations: [],
                modes: ['mock', 'live'],
                demo_only: false,
                real_generation_available: true,
                note: null,
              },
            },
            mock_demo_note: '모의 시연은 승인 근거가 아닙니다.',
          })
        }
        if (url.includes('/api/v1/admin/preview/runs')) {
          return json({ runs: [], next_cursor: null })
        }
        if (url.includes('/api/v1/admin/preview/fixtures')) {
          return json({ fixtures: [] })
        }
        return json({}, 404)
      }),
    )

    const panel = mount(PreviewPanel, {
      props: { canGenerate: true },
      global: { plugins: [router] },
      attachTo: document.body,
    })

    const sectionsLink = panel.get('[data-testid="preview-open-sections"]')
    const runsLink = panel.get('[data-testid="preview-open-runs"]')
    expect(sectionsLink.attributes('href')).toBe('/admin/sections')
    expect(runsLink.attributes('href')).toBe('/admin/runs')

    await sectionsLink.trigger('click')
    await vi.waitFor(() => {
      expect(router.currentRoute.value.name).toBe('preview-sections')
    })
    expect(router.currentRoute.value.path).toBe('/admin/sections')

    const SectionRunView = (await import('@/features/match-preview/SectionRunView.vue')).default
    const sectionWrapper = mount(SectionRunView, {
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(sectionWrapper.find('[data-testid="workspace-sections"]').exists()).toBe(true)

    await router.push({ name: 'preview-runs' })
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(router.currentRoute.value.path).toBe('/admin/runs')

    const PreviewRunsView = (await import('@/features/match-preview/PreviewRunsView.vue')).default
    const runsWrapper = mount(PreviewRunsView, {
      global: { plugins: [router] },
    })
    await flushPromises()
    expect(runsWrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)

    expect(calls.some((call) => call.url.includes('/api/v1/auth/session'))).toBe(false)
    expect(
      calls.some(
        (call) =>
          call.method === 'POST' &&
          (call.url.includes('/section-runs') || call.url.endsWith('/runs')),
      ),
    ).toBe(false)

    await sectionWrapper.unmount()
    await runsWrapper.unmount()
    await panel.unmount()
  })
})
