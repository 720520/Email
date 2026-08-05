import { createRouter, createWebHistory } from 'vue-router'

import { businessRoutes } from '@/modules'
import { useAuthStore } from '@/platform/auth/auth.store'
import type { UserRole } from '@/platform/api/types'

const roleRank: Record<UserRole, number> = { viewer: 1, operator: 2, admin: 3 }

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true, title: '登录' },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppShell.vue'),
      children: [
        { path: '', redirect: '/overview' },
        ...businessRoutes,
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/overview' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.initialized) await auth.restore()

  if (to.meta.public) {
    if (to.name === 'login' && auth.isAuthenticated) return '/overview'
    return true
  }
  if (!auth.user) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  const roles = to.meta.roles as UserRole[] | undefined
  if (
    roles
    && !auth.user.is_platform_admin
    && !roles.some((role) => roleRank[auth.user!.role] >= roleRank[role])
  ) {
    return '/overview'
  }
  return true
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? '基金运营'} · 运营工作台`
})
