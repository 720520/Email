import { DataBoard, SetUp } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const reportingModule: BusinessModule = {
  id: 'reporting',
  title: '报表制作',
  description: '模板、产品字段与净值报告',
  order: 20,
  navigation: [
    { path: '/reports', title: '报表中心', icon: DataBoard },
    { path: '/report-fields', title: '字段中心', icon: SetUp, permission: 'operator' },
  ],
  routes: [
    {
      path: '/reports',
      name: 'reports',
      component: () => import('./views/ReportCenterView.vue'),
      meta: { title: '报表中心' },
    },
    {
      path: '/report-fields',
      name: 'report-fields',
      component: () => import('./views/ReportFieldCenterView.vue'),
      meta: { title: '字段中心' },
    },
    {
      path: '/reports/runs/:runId/editor',
      name: 'report-editor',
      component: () => import('./views/ReportEditorView.vue'),
      meta: { title: '报表在线预览' },
    },
  ],
}
