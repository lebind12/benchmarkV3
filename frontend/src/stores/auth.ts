import { defineStore } from 'pinia'
import type { AuthUser } from '@/lib/api/auth'

export type Role = 'public' | 'USER' | 'STREAMER' | 'ADMIN'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    role: 'public' as Role,
    user: null as AuthUser | null,
  }),
  getters: {
    isStreamer: (s) => s.role === 'STREAMER',
    isAdmin: (s) => s.role === 'ADMIN',
    isLoggedIn: (s) => s.role !== 'public',
  },
  actions: {
    hydrateFromMock() {
      if (typeof localStorage !== 'undefined') {
        const userRaw = localStorage.getItem('authUser')
        if (userRaw) {
          try {
            const user = JSON.parse(userRaw) as AuthUser
            this.user = user
            this.role = user.role
            localStorage.setItem('mockRole', user.role)
            return
          } catch {
            localStorage.removeItem('authUser')
          }
        }
      }
      const v = (typeof localStorage !== 'undefined' && localStorage.getItem('mockRole')) || 'public'
      if (v === 'public' || v === 'USER' || v === 'STREAMER' || v === 'ADMIN') this.role = v
    },
    setRole(r: Role) {
      this.role = r
      if (typeof localStorage !== 'undefined') localStorage.setItem('mockRole', r)
    },
    setUser(user: AuthUser) {
      this.user = user
      this.setRole(user.role)
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('authUser', JSON.stringify(user))
      }
    },
    logout() {
      this.user = null
      this.role = 'public'
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('authUser')
        localStorage.setItem('mockRole', 'public')
      }
    },
  },
})
