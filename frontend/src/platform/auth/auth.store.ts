import { defineStore } from 'pinia'

import { http } from '@/platform/api/http'
import type { CurrentUser } from '@/platform/api/types'

interface LoginResponse {
  user: CurrentUser
  expires_at: string
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as CurrentUser | null,
    initialized: false,
  }),
  getters: {
    isAuthenticated: (state) => state.user !== null,
  },
  actions: {
    async restore() {
      if (this.initialized) return
      try {
        const { data } = await http.get<CurrentUser>('/auth/me')
        this.user = data
      } catch {
        this.user = null
      } finally {
        this.initialized = true
      }
    },
    async login(username: string, password: string) {
      const { data } = await http.post<LoginResponse>('/auth/login', { username, password })
      this.user = data.user
      this.initialized = true
    },
    async logout() {
      try {
        await http.post('/auth/logout')
      } finally {
        this.user = null
        this.initialized = true
      }
    },
    clearSession() {
      this.user = null
      this.initialized = true
    },
  },
})
