import { defineStore } from 'pinia'

import { http } from '@/platform/api/http'
import type { CurrentUser, TenantOption } from '@/platform/api/types'

export interface LoginResponse {
  requires_tenant_selection: boolean
  tenants: TenantOption[]
  user: CurrentUser | null
  expires_at: string | null
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null as CurrentUser | null,
    tenants: [] as TenantOption[],
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
        await this.loadTenants()
      } catch {
        this.user = null
        this.tenants = []
      } finally {
        this.initialized = true
      }
    },
    async login(username: string, password: string, tenantId?: number) {
      const { data } = await http.post<LoginResponse>('/auth/login', {
        username,
        password,
        tenant_id: tenantId,
      })
      this.user = data.user
      this.tenants = data.tenants
      this.initialized = true
      if (data.user) await this.loadTenants()
      return data
    },
    async loadTenants() {
      if (!this.user) {
        this.tenants = []
        return
      }
      const { data } = await http.get<TenantOption[]>('/auth/tenants')
      this.tenants = data
    },
    async switchTenant(tenantId: number) {
      const { data } = await http.post<LoginResponse>('/auth/switch-tenant', {
        tenant_id: tenantId,
      })
      if (!data.user) throw new Error('租户切换响应缺少用户信息')
      this.user = data.user
      await this.loadTenants()
      return data.user
    },
    async logout() {
      try {
        await http.post('/auth/logout')
      } finally {
        this.user = null
        this.tenants = []
        this.initialized = true
      }
    },
    clearSession() {
      this.user = null
      this.tenants = []
      this.initialized = true
    },
  },
})
