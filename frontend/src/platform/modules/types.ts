import type { Component } from 'vue'
import type { RouteRecordRaw } from 'vue-router'

export interface ModuleNavigationItem {
  path: string
  title: string
  icon: Component
  permission?: 'admin' | 'operator' | 'viewer'
}

export interface BusinessModule {
  id: string
  title: string
  description: string
  order: number
  navigation: ModuleNavigationItem[]
  routes: RouteRecordRaw[]
}
