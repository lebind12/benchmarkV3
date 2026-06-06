import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
      { path: '/auth/signup', name: 'signup', component: SignupView },
    ],
  })
}

afterEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('SignupView', () => {
  it('submits signup, stores USER auth state, and shows success', async () => {
    const fetchMock = vi.fn(async () => jsonResponse({
      user: {
        id: 7,
        email: 'new@example.com',
        role: 'USER',
        nickname: 'New User',
        is_active: true,
      },
    }, 201))
    vi.stubGlobal('fetch', fetchMock)
    vi.spyOn(window, 'setTimeout').mockImplementation((callback: TimerHandler) => {
      if (typeof callback === 'function') callback()
      return 0
    })

    const router = makeRouter()
    router.push('/auth/signup')
    await router.isReady()
    const wrapper = mount(SignupView, {
      global: { plugins: [createPinia(), router] },
    })

    await wrapper.get('[data-testid=signup-email]').setValue('New@Example.com')
    await wrapper.get('[data-testid=signup-nickname]').setValue('New User')
    await wrapper.get('[data-testid=signup-password]').setValue('Bench1234')
    await wrapper.get('[data-testid=signup-confirm-password]').setValue('Bench1234')
    await wrapper.get('[data-testid=signup-form]').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/signup', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        email: 'New@Example.com',
        password: 'Bench1234',
        nickname: 'New User',
      }),
    }))
    expect(wrapper.get('[data-testid=signup-success]').text()).toContain('가입이 완료')
    expect(localStorage.getItem('mockRole')).toBe('USER')
    expect(JSON.parse(localStorage.getItem('authUser') ?? '{}')).toMatchObject({
      email: 'new@example.com',
      role: 'USER',
    })
  })

  it('shows duplicate email errors from the signup API', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      detail: 'email_already_registered',
    }, 409)))

    const router = makeRouter()
    router.push('/auth/signup')
    await router.isReady()
    const wrapper = mount(SignupView, {
      global: { plugins: [createPinia(), router] },
    })

    await wrapper.get('[data-testid=signup-email]').setValue('dupe@example.com')
    await wrapper.get('[data-testid=signup-password]').setValue('Bench1234')
    await wrapper.get('[data-testid=signup-confirm-password]').setValue('Bench1234')
    await wrapper.get('[data-testid=signup-form]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid=signup-error]').text()).toContain('이미 등록')
  })
})
