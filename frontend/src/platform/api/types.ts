export type UserRole = 'admin' | 'operator' | 'viewer'

export interface CurrentUser {
  id: number
  username: string
  role: UserRole
  tenant_id: number
  tenant_code: string
  tenant_name: string
  is_platform_admin: boolean
}

export interface TenantOption {
  id: number
  code: string
  name: string
  role: UserRole
  is_current: boolean
}

export interface PageResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

export interface ApiErrorBody {
  success: false
  error: {
    code: string
    message: string
    details?: unknown
  }
  request_id: string
}
