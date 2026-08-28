import { describe, expect, it } from 'vitest'

import type { BusinessModule } from '@/platform/modules/types'

import { businessModules, businessRoutes, registerBusinessModules } from './index'

const fakeModule = (id: string, routeName: string, path: string, order = 10): BusinessModule => ({
  id,
  title: id,
  description: id,
  order,
  navigation: [{ path, title: id, icon: {} }],
  routes: [{ path, name: routeName, component: {} }],
})

describe('业务模块注册中心', () => {
  it('聚合基金运营与租户管理模块的导航和路由', () => {
    expect(businessModules.map((module) => module.id)).toEqual([
      'fund-operations', 'reporting', 'account-opening', 'tenant-admin',
    ])
    expect(businessRoutes.map((route) => route.name)).toEqual([
      'overview', 'emails', 'mailboxes', 'fund-nav', 'fund-products', 'exceptions', 'operations',
      'reports', 'report-fields', 'report-editor',
      'institutions', 'account-applications',
      'filing-profile', 'tenant-management',
    ])
  })

  it('按排序值注册新业务模块且不修改输入数组', () => {
    const later = fakeModule('later', 'later-page', '/later', 20)
    const earlier = fakeModule('earlier', 'earlier-page', '/earlier', 5)
    const source = [later, earlier]
    expect(registerBusinessModules(source).map((module) => module.id)).toEqual(['earlier', 'later'])
    expect(source[0]).toBe(later)
  })

  it('拒绝重复的模块 ID、路由名称和导航路径', () => {
    expect(() => registerBusinessModules([
      fakeModule('same', 'one', '/one'), fakeModule('same', 'two', '/two'),
    ])).toThrow('业务模块 ID 重复')
    expect(() => registerBusinessModules([
      fakeModule('one', 'same-route', '/one'), fakeModule('two', 'same-route', '/two'),
    ])).toThrow('业务路由名称重复')
    expect(() => registerBusinessModules([
      fakeModule('one', 'one', '/same'), fakeModule('two', 'two', '/same'),
    ])).toThrow('业务导航路径重复')
  })

  it('对子导航同样执行路径重复校验', () => {
    const first = fakeModule('one', 'one', '/one')
    first.navigation[0].children = [{ path: '/nested', title: '子页面', icon: {} }]
    expect(() => registerBusinessModules([first, fakeModule('two', 'two', '/nested')]))
      .toThrow('业务导航路径重复')
  })
})
