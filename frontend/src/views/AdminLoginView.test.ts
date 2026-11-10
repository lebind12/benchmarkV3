/**
 * 관리자 로그인 화면 동작.
 *
 * 서버를 흉내 내지 않고 fetch 경계만 대체한다. 검증 대상은 화면이 실제로
 * 보여주는 것(상태, 문구, 리다이렉트)이다.
 */
import { describe, expect, it, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import AdminLoginView from '@/views/AdminLoginView.vue'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', redirect: '/admin/runs' },
      { path: '/admin/login', name: 'admin-login', component: AdminLoginView },
      {
        path: '/admin/runs',
        name: 'preview-runs',
        component: { template: '<div data-testid="runs-stub">runs</div>' },
      },
    ],
  })
}

async function mountLogin(router = makeRouter()) {
  await router.push('/admin/login')
  // 포커스 이동은 실제 문서에 붙어 있어야 확인할 수 있다.
  const wrapper = mount(AdminLoginView, {
    global: { plugins: [router] },
    attachTo: document.body,
  })
  return { wrapper, router }
}

async function fillAndSubmit(wrapper: Awaited<ReturnType<typeof mountLogin>>['wrapper']) {
  await wrapper.get('[data-testid="login-email"]').setValue('admin@local.test')
  await wrapper.get('[data-testid="login-password"]').setValue('correct-horse-battery-9')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
}

describe('AdminLoginView', () => {
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

  it('renders the labelled login form without any credential in the markup', async () => {
    const { wrapper } = await mountLogin()
    expect(wrapper.get('label[for="login-email"]').text()).toBe('이메일')
    expect(wrapper.get('label[for="login-password"]').text()).toBe('비밀번호')
    expect(wrapper.get('[data-testid="login-email"]').attributes('autocomplete')).toBe('username')
    expect(wrapper.get('[data-testid="login-password"]').attributes('type')).toBe('password')
    expect(wrapper.html()).not.toContain('correct-horse-battery-9')
  })

  it('shows one combined message for wrong credentials and clears the password', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ detail: 'invalid credentials' }, 401),
    )
    const { wrapper } = await mountLogin()
    await fillAndSubmit(wrapper)

    const alert = wrapper.get('[data-testid="login-error"]')
    expect(alert.text()).toBe('이메일 또는 비밀번호가 올바르지 않습니다.')
    expect(alert.attributes('role')).toBe('alert')
    expect(
      (wrapper.get('[data-testid="login-password"]').element as HTMLInputElement).value,
    ).toBe('')
  })

  it('shows the admin-role message when a valid non-admin account tries to sign in', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'admin role required' }, 403))
    const { wrapper } = await mountLogin()
    await fillAndSubmit(wrapper)

    expect(wrapper.get('[data-testid="login-error"]').text()).toBe(
      '관리자 권한이 없는 계정입니다.',
    )
  })

  it('reports a network failure instead of pretending success', async () => {
    fetchMock.mockRejectedValue(new TypeError('network down'))
    const { wrapper } = await mountLogin()
    await fillAndSubmit(wrapper)

    expect(wrapper.get('[data-testid="login-error"]').text()).toContain('서버에 연결하지 못했습니다')
  })

  it('reports a server error with its own message', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'boom' }, 500))
    const { wrapper } = await mountLogin()
    await fillAndSubmit(wrapper)

    expect(wrapper.get('[data-testid="login-error"]').text()).toContain('서버 오류가 발생했습니다')
  })

  it('keeps the submit button disabled while the request is in flight', async () => {
    let resolveRequest: (value: Response) => void = () => {}
    fetchMock.mockReturnValue(
      new Promise<Response>((resolve) => {
        resolveRequest = resolve
      }),
    )
    const { wrapper } = await mountLogin()
    await wrapper.get('[data-testid="login-email"]').setValue('admin@local.test')
    await wrapper.get('[data-testid="login-password"]').setValue('correct-horse-battery-9')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    const button = wrapper.get('[data-testid="login-submit"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toBe('확인 중…')

    resolveRequest(
      jsonResponse({
        user_id: '1b0e0b7e-0000-4000-8000-000000000001',
        email: 'admin@local.test',
        role: 'admin',
        session_id: '1b0e0b7e-0000-4000-8000-000000000002',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }),
    )
    await flushPromises()
  })

  it('navigates to the protected run list after a successful login', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        user_id: '1b0e0b7e-0000-4000-8000-000000000001',
        email: 'admin@local.test',
        role: 'admin',
        session_id: '1b0e0b7e-0000-4000-8000-000000000002',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }),
    )
    const { wrapper, router } = await mountLogin()
    await fillAndSubmit(wrapper)

    expect(router.currentRoute.value.name).toBe('preview-runs')
    expect(wrapper.find('[data-testid="login-error"]').exists()).toBe(false)
  })

  it('sends credentials only in the POST body with credentials, never in the URL', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        user_id: '1b0e0b7e-0000-4000-8000-000000000001',
        email: 'admin@local.test',
        role: 'admin',
        session_id: '1b0e0b7e-0000-4000-8000-000000000002',
        expires_at: new Date(Date.now() + 3600_000).toISOString(),
      }),
    )
    const { wrapper } = await mountLogin()
    await fillAndSubmit(wrapper)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/auth/login')
    expect(url).not.toContain('password')
    expect(init.method).toBe('POST')
    expect(init.credentials).toBe('same-origin')
    expect(JSON.parse(String(init.body))).toEqual({
      email: 'admin@local.test',
      password: 'correct-horse-battery-9',
    })
  })

  it('blocks an empty submit locally and focuses the first empty field', async () => {
    const { wrapper } = await mountLogin()
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="login-error"]').text()).toBe(
      '이메일과 비밀번호를 모두 입력하세요.',
    )
    expect(document.activeElement).toBe(wrapper.get('[data-testid="login-email"]').element)
  })
})
