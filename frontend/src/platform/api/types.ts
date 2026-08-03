export type UserRole = 'admin' | 'operator' | 'viewer'

export interface CurrentUser {
  id: number
  username: string
  role: UserRole
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
