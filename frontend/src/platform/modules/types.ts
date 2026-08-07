import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

export interface ModuleNavigationItem {
  path: string
  title: string
  icon: Component
  permission?: 'admin' | 'operator' | 'viewer'
  /** 子导航用于把同一业务域的页面折叠到一个一级入口中。 */
  children?: ModuleNavigationItem[]
}

export interface BusinessModule {
  id: string
  title: string
  description: string
  order: number
  navigation: ModuleNavigationItem[]
  routes: RouteRecordRaw[]
}
