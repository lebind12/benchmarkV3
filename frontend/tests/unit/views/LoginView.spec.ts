import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LoginView from '@/views/LoginView.vue'
import SignupView from '@/views/SignupView.vue'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status >= 200 && status < 300 ? 'OK' : 'Error',
    json: async () => body,
  } as Response
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/auth/login', name: 'login', component: LoginView },
      { path: '/auth/signup', name: 'signup', component: SignupView },
    ],
  })
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('LoginView', () => {
  it('submits login, stores auth state, and shows success', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      user: {
        id: 8,
        email: 'login@example.com',
        role: 'USER',
        nickname: 'Login User',
        is_active: true,
      },
    }))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'setTimeout').mockImplementation((callback: TimerHandler) => {
      if (typeof callback === 'function') callback()
      return 0
    })

    const router = makeRouter()
    router.push('/auth/login')
    await router.isReady()
    const wrapper = mount(LoginView, {
      global: { plugins: [createPinia(), router] },
    })

    await wrapper.get('[data-testid=login-email]').setValue('login@example.com')
    await wrapper.get('[data-testid=login-password]').setValue('Bench1234')
    await wrapper.get('[data-testid=login-form]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        email: 'login@example.com',
        password: 'Bench1234',
      }),
    }))
    expect(wrapper.get('[data-testid=login-success]').text()).toContain('로그인')
    expect(localStorage.getItem('mockRole')).toBe('USER')
    expect(JSON.parse(localStorage.getItem('authUser') ?? '{}')).toMatchObject({
      email: 'login@example.com',
      role: 'USER',
    })
  })

  it('shows invalid credential errors from the login API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      detail: 'invalid_credentials',
    }, 401)))

    const router = makeRouter()
    router.push('/auth/login')
    await router.isReady()
    const wrapper = mount(LoginView, {
      global: { plugins: [createPinia(), router] },
    })

    await wrapper.get('[data-testid=login-email]').setValue('wrong@example.com')
    await wrapper.get('[data-testid=login-password]').setValue('Wrong1234')
    await wrapper.get('[data-testid=login-form]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid=login-error]').text()).toContain('올바르지 않습니다')
  })
})
