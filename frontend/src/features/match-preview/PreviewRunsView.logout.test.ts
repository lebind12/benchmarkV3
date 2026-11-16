/**
 * 실행 목록 화면의 세션·로그아웃 동작.
 *
 * - 로그아웃이 실패하면 서버 세션은 살아 있다. 화면이 성공을 꾸며 로그인으로 보내면
 *   안 되고, 실패를 알린 뒤 같은 세션으로 다시 시도할 수 있어야 한다.
 * - 세션 확인은 실제 `useAuthStore.verifySession()`(/auth/refresh + /auth/me)과
 *   실제 `login` 라우트 계약을 따른다.
 */
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PreviewRunsView from '@/features/match-preview/PreviewRunsView.vue'
import { setAccessToken } from '@/lib/api/session'
import { useAuthStore } from '@/stores/auth'

const ADMIN_USER = {
  id: 1,
  email: 'admin@local.test',
  role: 'ADMIN' as const,
  nickname: 'admin',
  is_active: true,
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/admin/runs', name: 'preview-runs', component: PreviewRunsView },
      {
        path: '/auth/login',
        name: 'login',
        component: { template: '<div data-testid="login-stub">login</div>' },
      },
      {
        path: '/not-found',
        name: 'not-found',
        component: { template: '<div data-testid="not-found-stub">not-found</div>' },
      },
    ],
  })
}

async function mountRuns() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = makeRouter()
  await router.push('/admin/runs')
  const wrapper = mount(PreviewRunsView, {
    global: { plugins: [pinia, router] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, router }
}

describe('PreviewRunsView logout', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    setAccessToken(null)
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    setAccessToken(null)
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('stays on the page and reports failure when logout is rejected', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) return json({ runs: [], next_cursor: null })
      if (url.endsWith('/api/v1/auth/logout')) return json({ detail: 'boom' }, 500)
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    const alert = wrapper.get('[data-testid="logout-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('로그아웃하지 못했습니다')
    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)
    expect(useAuthStore().isLoggedIn).toBe(true)
  })

  it('reports a network failure on logout instead of navigating away', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) return json({ runs: [], next_cursor: null })
      if (url.endsWith('/api/v1/auth/logout')) throw new TypeError('offline')
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()
    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="logout-error"]').text()).toContain(
      '서버에 연결하지 못했습니다',
    )
    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(useAuthStore().isLoggedIn).toBe(true)
  })

  it('retries the same session and reaches login after the revoke succeeds', async () => {
    let logoutAttempt = 0
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) return json({ runs: [], next_cursor: null })
      if (url.endsWith('/api/v1/auth/logout')) {
        logoutAttempt += 1
        return logoutAttempt === 1
          ? json({ detail: 'boom' }, 500)
          : new Response(null, { status: 204 })
      }
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('preview-runs')

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.find('[data-testid="logout-error"]').exists()).toBe(false)
    expect(useAuthStore().isLoggedIn).toBe(false)

    // 두 번째 시도는 첫 시도와 같은 세션 쿠키로 나간다.
    const logoutCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/logout'))
    expect(logoutCalls).toHaveLength(2)
    for (const [, init] of logoutCalls) {
      expect((init as RequestInit).credentials).toBe('same-origin')
    }
  })

  it('navigates to login when logout succeeds', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) return json({ runs: [], next_cursor: null })
      if (url.endsWith('/api/v1/auth/logout')) return new Response(null, { status: 204 })
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()
    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('login')
    expect(wrapper.find('[data-testid="logout-error"]').exists()).toBe(false)
    expect(useAuthStore().isLoggedIn).toBe(false)
  })

  it('returns to login when the session is already gone', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) {
        return json({ detail: 'authentication required' }, 401)
      }
      return json({}, 404)
    })

    const { router } = await mountRuns()
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/admin/runs')
  })

  it('returns to login when an expired session is rejected on the run list request', async () => {
    // 세션 확인은 성공했지만 실행 목록 조회 시점에 서버가 만료로 401을 준다.
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) {
        return json({ detail: 'authentication required' }, 401)
      }
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()

    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.next).toBe('/admin/runs')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="runs-error"]').exists()).toBe(false)
    expect(useAuthStore().isLoggedIn).toBe(false)
  })

  it('shows an error and keeps the page when a non-admin session gets 403', async () => {
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.endsWith('/api/v1/auth/refresh')) return json({ access_token: 'admin-token' })
      if (url.endsWith('/api/v1/auth/me')) return json({ user: ADMIN_USER })
      if (url.includes('/api/v1/admin/preview/runs')) {
        return json({ detail: 'admin role required' }, 403)
      }
      return json({}, 404)
    })

    const { wrapper, router } = await mountRuns()

    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(wrapper.get('[data-testid="runs-error"]').text()).toContain(
      '관리자 권한이 없는 계정입니다',
    )
  })
})
