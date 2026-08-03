import 'vue-router'

import type { UserRole } from '@/platform/api/types'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    public?: boolean
    roles?: UserRole[]
  }
}
