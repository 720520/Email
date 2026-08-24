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

export interface FilingFieldDefinition {
  id: number
  key: string
  label: string
  category: string
  field_type: 'text' | 'file'
  sensitive: boolean
  multiline: boolean
  source_forms: string[]
  sort_order: number
  file_versions: FilingFileVersion[]
}

export interface FilingProfile {
  tenant_name: string
  can_edit: boolean
  fields: FilingFieldDefinition[]
  field_values: Record<string, string>
  update_time: string | null
}

export interface FilingProfilePayload {
  field_values: Record<string, string>
}

export interface FilingFileVersion {
  id: number
  version: number
  original_name: string
  file_size: number
  content_type: string | null
  content_hash: string
  created_by: string
  create_time: string
  download_url: string
}

export interface FilingFieldPayload {
  label: string
  category: string
  field_type: 'text' | 'file'
  sensitive: boolean
  multiline: boolean
  source_forms: string[]
  sort_order: number
}
