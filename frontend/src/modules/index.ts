import { fundOperationsModule } from './fund-operations'
import { reportingModule } from './reporting'
import { tenantAdminModule } from './tenant-admin'
import type { BusinessModule, ModuleNavigationItem } from '@/platform/modules/types'

function walkNavigation(items: ModuleNavigationItem[]): ModuleNavigationItem[] {
  return items.flatMap((item) => [item, ...walkNavigation(item.children ?? [])])
}

export function registerBusinessModules(modules: BusinessModule[]): BusinessModule[] {
  const moduleIds = new Set<string>()
  const routeNames = new Set<string>()
  const navigationPaths = new Set<string>()

  for (const module of modules) {
    if (moduleIds.has(module.id)) throw new Error(`业务模块 ID 重复：${module.id}`)
    moduleIds.add(module.id)
    for (const route of module.routes) {
      const name = String(route.name ?? '')
      if (!name) throw new Error(`业务模块 ${module.id} 存在未命名路由`)
      if (routeNames.has(name)) throw new Error(`业务路由名称重复：${name}`)
      routeNames.add(name)
    }
    for (const item of walkNavigation(module.navigation)) {
      if (navigationPaths.has(item.path)) throw new Error(`业务导航路径重复：${item.path}`)
      navigationPaths.add(item.path)
    }
  }
  return [...modules].sort((a, b) => a.order - b.order)
}

export const businessModules = registerBusinessModules([
  fundOperationsModule,
  reportingModule,
  tenantAdminModule,
])

export const businessRoutes = businessModules.flatMap((module) => module.routes)
