import { DataAnalysis, Document, House, MessageBox, Warning } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const fundOperationsModule: BusinessModule = {
  id: 'fund-operations',
  title: '基金运营',
  description: '邮件、净值、异常与日常复核',
  order: 10,
  navigation: [
    { path: '/overview', title: '运营概览', icon: House },
    { path: '/emails', title: '邮件管理', icon: MessageBox },
    { path: '/fund-nav', title: '基金净值', icon: DataAnalysis },
    { path: '/exceptions', title: '异常管理', icon: Warning },
    { path: '/operations', title: '人工处理', icon: Document, permission: 'operator' },
  ],
  routes: [
    {
      path: '/overview',
      name: 'overview',
      component: () => import('./views/OverviewView.vue'),
      meta: { title: '运营概览' },
    },
    {
      path: '/emails',
      name: 'emails',
      component: () => import('./views/EmailListView.vue'),
      meta: { title: '邮件管理' },
    },
    {
      path: '/fund-nav',
      name: 'fund-nav',
      component: () => import('./views/FundNavView.vue'),
      meta: { title: '基金净值' },
    },
    {
      path: '/exceptions',
      name: 'exceptions',
      component: () => import('./views/ExceptionListView.vue'),
      meta: { title: '异常管理' },
    },
    {
      path: '/operations',
      name: 'operations',
      component: () => import('./views/OperationsView.vue'),
      meta: { title: '人工处理', roles: ['admin', 'operator'] },
    },
  ],
}
