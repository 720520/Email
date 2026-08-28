import { OfficeBuilding, Tickets } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const accountOpeningModule: BusinessModule = {
  id: 'account-opening',
  title: '机构开户',
  description: '机构材料模板与产品开户台账',
  order: 30,
  navigation: [
    { path: '/institutions', title: '机构与模板', icon: OfficeBuilding },
    { path: '/account-applications', title: '开户台账', icon: Tickets },
  ],
  routes: [
    {
      path: '/institutions',
      name: 'institutions',
      component: () => import('./views/InstitutionTemplatesView.vue'),
      meta: { title: '机构与模板' },
    },
    {
      path: '/account-applications',
      name: 'account-applications',
      component: () => import('./views/AccountApplicationsView.vue'),
      meta: { title: '开户台账' },
    },
  ],
}
