/**
 * 실행 목록 화면의 로그아웃 동작.
 *
 * 로그아웃이 실패하면 서버 세션은 살아 있다. 화면이 성공을 꾸며 로그인으로 보내면
 * 안 되고, 실패를 알린 뒤 같은 세션으로 다시 시도할 수 있어야 한다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import PreviewRunsView from '@/views/PreviewRunsView.vue'

const SESSION = {
  user_id: 1,
  email: 'admin@local.test',
  role: 'admin',
  session_id: '00000000-0000-4000-8000-000000000002',
  expires_at: new Date(Date.now() + 3600_000).toISOString(),
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
        path: '/admin/login',
        name: 'admin-login',
        component: { template: '<div data-testid="login-stub">login</div>' },
      },
    ],
  })
}

async function mountRuns() {
  const router = makeRouter()
  await router.push('/admin/runs')
  const wrapper = mount(PreviewRunsView, {
    global: { plugins: [router] },
    attachTo: document.body,
  })
  await flushPromises()
  return { wrapper, router }
}

describe('PreviewRunsView logout', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.body.innerHTML = ''
  })

  it('stays on the page and reports failure when logout is rejected', async () => {
    fetchMock
      .mockResolvedValueOnce(json(SESSION))
      .mockResolvedValueOnce(json({ runs: [], next_cursor: null }))
      .mockResolvedValueOnce(json({ detail: 'boom' }, 500))

    const { wrapper, router } = await mountRuns()
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    const alert = wrapper.get('[data-testid="logout-error"]')
    expect(alert.attributes('role')).toBe('alert')
    expect(alert.text()).toContain('로그아웃하지 못했습니다')
    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(true)
  })

  it('reports a network failure on logout instead of navigating away', async () => {
    fetchMock
      .mockResolvedValueOnce(json(SESSION))
      .mockResolvedValueOnce(json({ runs: [], next_cursor: null }))
      .mockRejectedValueOnce(new TypeError('offline'))

    const { wrapper, router } = await mountRuns()
    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="logout-error"]').text()).toContain(
      '서버에 연결하지 못했습니다',
    )
    expect(router.currentRoute.value.name).toBe('preview-runs')
  })

  it('retries the same session and reaches login after the revoke succeeds', async () => {
    fetchMock
      .mockResolvedValueOnce(json(SESSION))
      .mockResolvedValueOnce(json({ runs: [], next_cursor: null }))
      .mockResolvedValueOnce(json({ detail: 'boom' }, 500))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    const { wrapper, router } = await mountRuns()

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('preview-runs')

    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('admin-login')
    expect(wrapper.find('[data-testid="logout-error"]').exists()).toBe(false)

    // 두 번째 시도는 첫 시도와 같은 세션 쿠키로 나간다.
    const logoutCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith('/logout'))
    expect(logoutCalls).toHaveLength(2)
    for (const [, init] of logoutCalls) {
      expect((init as RequestInit).credentials).toBe('same-origin')
    }
  })

  it('navigates to login when logout succeeds', async () => {
    fetchMock
      .mockResolvedValueOnce(json(SESSION))
      .mockResolvedValueOnce(json({ runs: [], next_cursor: null }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    const { wrapper, router } = await mountRuns()
    await wrapper.get('[data-testid="logout"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('admin-login')
    expect(wrapper.find('[data-testid="logout-error"]').exists()).toBe(false)
  })

  it('returns to login when the session is already gone', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'authentication required' }, 401))

    const { router } = await mountRuns()
    expect(router.currentRoute.value.name).toBe('admin-login')
  })

  it('returns to login when an expired session is rejected on the run list request', async () => {
    // 세션 확인은 성공했지만 실행 목록 조회 시점에 서버가 만료로 401을 준다.
    fetchMock
      .mockResolvedValueOnce(json(SESSION))
      .mockResolvedValueOnce(json({ detail: 'authentication required' }, 401))

    const { wrapper, router } = await mountRuns()

    expect(router.currentRoute.value.name).toBe('admin-login')
    expect(wrapper.find('[data-testid="runs-empty"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="runs-error"]').exists()).toBe(false)
  })

  it('shows an error and keeps the page when a non-admin session gets 403', async () => {
    fetchMock
      .mockResolvedValueOnce(json({ ...SESSION, role: 'streamer' }))
      .mockResolvedValueOnce(json({ detail: 'admin role required' }, 403))

    const { wrapper, router } = await mountRuns()

    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(wrapper.get('[data-testid="runs-error"]').text()).toContain(
      '관리자 권한이 없는 계정입니다',
    )
  })
})
