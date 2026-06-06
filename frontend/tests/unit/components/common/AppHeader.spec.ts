import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'
import AppHeader from '@/components/common/AppHeader.vue'
import { useAuthStore } from '@/stores/auth'

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'home', component: { template: '<div />' } },
      { path: '/fixtures', component: { template: '<div />' } },
      { path: '/standings', component: { template: '<div />' } },
      { path: '/teams', component: { template: '<div />' } },
      { path: '/players', component: { template: '<div />' } },
      { path: '/stats', component: { template: '<div />' } },
      { path: '/news', component: { template: '<div />' } },
      { path: '/auth/login', component: { template: '<div />' } },
      { path: '/auth/signup', component: { template: '<div />' } },
    ],
  })
}

afterEach(() => {
  localStorage.clear()
})

describe('AppHeader', () => {
  it('shows logout for signed-in users and clears local auth state', async () => {
    const pinia = createPinia()
    const router = makeRouter()
    const auth = useAuthStore(pinia)
    auth.setUser({
      id: 3,
      email: 'user@example.com',
      role: 'USER',
      nickname: 'Bench User',
      is_active: true,
    })

    const wrapper = mount(AppHeader, {
      global: { plugins: [pinia, router] },
    })

    expect(wrapper.get('[data-testid=auth-profile]').text()).toBe('Bench User')
    expect(wrapper.find('[data-testid=auth-login]').exists()).toBe(false)

    await wrapper.get('[data-testid=auth-logout]').trigger('click')

    expect(auth.role).toBe('public')
    expect(auth.user).toBeNull()
    expect(localStorage.getItem('authUser')).toBeNull()
    expect(localStorage.getItem('mockRole')).toBe('public')
    expect(wrapper.get('[data-testid=auth-login]').text()).toBe('로그인')
  })
})
