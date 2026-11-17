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

    await router.push('/admin/runs?run=run-123')
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/admin/runs?run=run-123')

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
    expect(runsLink.attributes('href')).toBe('/admin?tab=preview')

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

    // 이유: 기존 /admin/runs 직접 진입은 깨진 별도 화면 대신 관리 프리뷰 탭(/admin?tab=preview&previewRun=...)으로 리다이렉트되어야 한다.
    // 실패 시 사용자 결과: 사용자가 기존 URL 또는 북마크로 진입하면 승인 UI가 없는 분리 화면에 갇힌다.
    await router.push('/admin/runs?run=run-123')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('admin')
    expect(router.currentRoute.value.path).toBe('/admin')
    expect(router.currentRoute.value.query).toEqual({
      tab: 'preview',
      previewRun: 'run-123',
    })

    expect(calls.some((call) => call.url.includes('/api/v1/auth/session'))).toBe(false)
    expect(
      calls.some(
        (call) =>
          call.method === 'POST' &&
          (call.url.includes('/section-runs') || call.url.endsWith('/runs')),
      ),
    ).toBe(false)

    await sectionWrapper.unmount()
    await panel.unmount()
  })

  // 이유: PreviewPanel 내부에 중첩된 RunInspector는 hideApproval=true일 때 자체 승인 UI를 숨기고 단독 실행에서는 유지해야 한다.
  // 실패 시 사용자 결과: 프리뷰 탭의 진단 아코디언을 열었을 때 승인 UI가 2중으로 렌더링된다.
  it('hides inspector-approval only when RunInspector receives hideApproval=true', async () => {
    setAccessToken('admin-token')
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input.toString()
        if (url.endsWith('/api/v1/admin/preview/runs/run-1')) {
          return json({
            summary: {
              run_id: 'run-1',
              operation_kind: 'preview',
              environment: 'dev',
              mode: 'live',
              status: 'succeeded',
              quality: 'ready',
              fixture_label: '경기',
              requested_at: '2026-11-18T00:00:00Z',
              finished_at: '2026-11-18T00:01:00Z',
              module_count: 0,
              attempt_count: 0,
              retry_count: 0,
              failure_code: null,
              label: null,
              cancelled_at: null,
            },
            actor_id: '1',
            config_version: 'c',
            limits: {},
            fixture: null,
            modules: [],
            results: [],
            sources: [],
            attempts: [],
            artifacts: [],
            contract_versions: {
              contract: 'c',
              provider: 'p',
              module_input: 'm',
              preview_document: 'd',
              inspector: 'i',
            },
            inspector_version: 'i',
            mode_detail: { mode: 'live', label: '실호출', note: '' },
            inspector_modules: [],
            registry: {
              registry_version: 'r',
              contract_version: 'c',
              inspector_version: 'i',
              modules: [],
              implemented: [],
              unavailable: [],
            },
            approvals: null,
            section_result_id: null,
            section_results: [],
            section_approvals: [],
            section_workflows: null,
            approval_note: '',
            mock_demo_module_id: '',
            availability_note: '',
            undo: {
              state: 'blocked',
              cancelled_at: null,
              cancelled_by_actor_id: null,
              reason: null,
              can_cancel: false,
              blocked_reason: null,
            },
          })
        }
        return json({ run_id: 'run-1', section_results: [] })
      }),
    )

    const RunInspector = (await import('@/features/match-preview/RunInspector.vue')).default
    const standalone = mount(RunInspector, { props: { runId: 'run-1' } })
    await flushPromises()
    expect(standalone.find('[data-testid="inspector-approval"]').exists()).toBe(true)
    await standalone.unmount()

    const embedded = mount(RunInspector, { props: { runId: 'run-1', hideApproval: true } })
    await flushPromises()
    expect(embedded.find('[data-testid="inspector-approval"]').exists()).toBe(false)
    await embedded.unmount()
  })
})
