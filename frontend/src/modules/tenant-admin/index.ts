import { OfficeBuilding } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const tenantAdminModule: BusinessModule = {
  id: 'tenant-admin',
  title: '系统管理',
  description: '租户边界、成员与权限',
  order: 90,
  navigation: [
    { path: '/tenant-management', title: '租户与成员', icon: OfficeBuilding, permission: 'admin' },
  ],
  routes: [
    {
      path: '/tenant-management',
      name: 'tenant-management',
      component: () => import('./views/TenantManagementView.vue'),
      meta: { title: '租户与成员', roles: ['admin'] },
    },
  ],
}
