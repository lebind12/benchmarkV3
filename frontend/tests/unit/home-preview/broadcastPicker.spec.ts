import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useAuthStore, type Role } from '@/stores/auth'
import BroadcastPickerButton from '@/components/common/BroadcastPickerButton.vue'

beforeEach(() => { setActivePinia(createPinia()); localStorage.clear() })
afterEach(() => localStorage.clear())

describe('shared match broadcast permissions and destinations', () => {
  it.each(['public', 'USER', 'STREAMER'] as Role[])('hides broadcasting for %s, including a forged ADMIN cache', role => {
    localStorage.setItem('mockRole', 'ADMIN')
    const auth = useAuthStore()
    auth.role = role; auth.verified = role !== 'public'
    const wrapper = mount(BroadcastPickerButton, { props: { fixtureId: 123 } })
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
  it('requires the ADMIN session to be verified', () => {
    const auth = useAuthStore(); auth.role = 'ADMIN'
    const wrapper = mount(BroadcastPickerButton, { props: { fixtureId: 123 } })
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })
  it('builds both destinations from the current fixture and league', async () => {
    const auth = useAuthStore(); auth.role = 'ADMIN'; auth.verified = true
    const wrapper = mount(BroadcastPickerButton, { props: { fixtureId: 123, leagueSlug: 'champions-league' }, global: { stubs: { teleport: true } } })
    expect(wrapper.get('[data-testid="program-link"]').attributes('href')).toBe('/broadcast-program.html?fixtureId=123&league=champions-league')
    expect(wrapper.get('[data-testid="watch-together-link"]').attributes('target')).toBe('_blank')
    await wrapper.setProps({ fixtureId: 456, leagueSlug: null })
    expect(wrapper.get('[data-testid="watch-together-link"]').attributes('href')).toBe('/broadcast.html?fixtureId=456')
    wrapper.unmount()
  })
  it('disables the ADMIN launcher when no match is selected', () => {
    const auth = useAuthStore(); auth.role = 'ADMIN'; auth.verified = true
    const wrapper = mount(BroadcastPickerButton)
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
