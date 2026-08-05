import type { UserRole } from '@/platform/api/types'

export interface TenantSummary {
  id: number
  code: string
  name: string
  is_active: boolean
  current_user_role: UserRole | null
  is_current: boolean
  can_manage: boolean
  member_count: number
  mailbox_count: number
  create_time: string
}

export interface TenantMember {
  membership_id: number
  user_id: number
  username: string
  role: UserRole
  is_active: boolean
  user_is_active: boolean
  is_platform_admin: boolean
  create_time: string
}

export interface TenantCreatePayload {
  code: string
  name: string
}

export interface TenantUpdatePayload {
  name?: string
  is_active?: boolean
}

export interface TenantMemberCreatePayload {
  username: string
  password?: string
  role: UserRole
}

export interface TenantMemberUpdatePayload {
  role: UserRole
  is_active: boolean
}
