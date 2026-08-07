import { Collection, DataAnalysis, Document, House, Message, MessageBox, Setting, Warning } from '@element-plus/icons-vue'

import type { BusinessModule } from '@/platform/modules/types'

export const fundOperationsModule: BusinessModule = {
  id: 'fund-operations',
  title: '基金运营',
  description: '概览、邮件中心与业务数据',
  order: 10,
  navigation: [
    { path: '/overview', title: '运营概览', icon: House },
    {
      path: '/email-center',
      title: '邮件中心',
      icon: Message,
      children: [
        { path: '/emails', title: '邮件管理', icon: MessageBox },
        { path: '/mailboxes', title: '邮箱账户', icon: Setting },
        { path: '/exceptions', title: '异常管理', icon: Warning },
        { path: '/operations', title: '人工处理', icon: Document, permission: 'operator' },
      ],
    },
    { path: '/fund-nav', title: '基金净值', icon: DataAnalysis },
    { path: '/fund-products', title: '产品要素', icon: Collection },
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
      path: '/mailboxes',
      name: 'mailboxes',
      component: () => import('./views/MailboxAccountsView.vue'),
      meta: { title: '邮箱账户' },
    },
    {
      path: '/fund-nav',
      name: 'fund-nav',
      component: () => import('./views/FundNavView.vue'),
      meta: { title: '基金净值' },
    },
    {
      path: '/fund-products',
      name: 'fund-products',
      component: () => import('./views/FundProductsView.vue'),
      meta: { title: '产品要素' },
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
