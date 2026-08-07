import { DataBoard } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const reportingModule: BusinessModule = {
  id: 'reporting',
  title: '报表制作',
  description: '模板、产品字段与净值报告',
  order: 20,
  navigation: [
    { path: '/reports', title: '报表中心', icon: DataBoard },
  ],
  routes: [
    {
      path: '/reports',
      name: 'reports',
      component: () => import('./views/ReportCenterView.vue'),
      meta: { title: '报表中心' },
    },
  ],
}
