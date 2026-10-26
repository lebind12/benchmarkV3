import { defineStore } from 'pinia'
import type { AuthUser } from '@/lib/api/auth'
import { authenticatedFetch, refreshSession, setAccessToken } from '@/lib/api/session'

export type Role = 'public' | 'USER' | 'STREAMER' | 'ADMIN'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    role: 'public' as Role,
    user: null as AuthUser | null,
    verified: false,
  }),
  getters: {
    isStreamer: (s) => s.role === 'STREAMER',
    isAdmin: (s) => s.role === 'ADMIN',
    isLoggedIn: (s) => s.verified && s.role !== 'public',
  },
  actions: {
    async verifySession() {
      try {
        await refreshSession()
        const response = await authenticatedFetch('/api/v1/auth/me')
        if (!response.ok) throw new Error('인증 정보를 확인하지 못했습니다.')
        this.setUser((await response.json()).user)
        return true
      } catch { this.logout(); return false }
    },
    hydrateFromMock() {
      if (import.meta.env.VITE_USE_MOCK !== 'true') return
      this.verified = true
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
      const v = (import.meta.env.VITE_USE_MOCK === 'true' && typeof localStorage !== 'undefined' && localStorage.getItem('mockRole')) || 'public'
      if (v === 'public' || v === 'USER' || v === 'STREAMER' || v === 'ADMIN') this.role = v
    },
    setRole(r: Role) {
      this.role = r
      if (typeof localStorage !== 'undefined') localStorage.setItem('mockRole', r)
    },
    setUser(user: AuthUser) {
      this.user = user
      this.verified = true
      this.setRole(user.role)
      if (typeof localStorage !== 'undefined') {
        localStorage.setItem('authUser', JSON.stringify(user))
      }
    },
    logout() {
      setAccessToken(null)
      this.user = null
      this.verified = false
      this.role = 'public'
      if (typeof localStorage !== 'undefined') {
        localStorage.removeItem('authUser')
        localStorage.setItem('mockRole', 'public')
      }
    },
  },
})
