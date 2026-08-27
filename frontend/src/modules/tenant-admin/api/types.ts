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

export interface EntityItem {
  id: number
  entity_type: 'organization' | 'product' | string
  display_name: string
  external_code: string | null
  status: string
  create_time: string
  update_time: string
}

export interface FieldDefinitionItem {
  id: number
  entity_type: string
  field_code: string
  label: string
  data_type: string
  category: string
  sensitivity: 'normal' | 'sensitive' | 'highly_sensitive'
  is_multivalue: boolean
  validation_schema: Record<string, unknown>
  display_schema: Record<string, unknown>
  sort_order: number
  is_system: boolean
  is_active: boolean
}

export interface FieldValueItem {
  id: number
  entity_id: number
  field_definition_id: number
  value: unknown
  status: string
  valid_from: string
  valid_to: string | null
  source_type: string
  source_document_id: number | null
  source_locator: Record<string, unknown>
  confidence: number | null
  entered_by_user_id: number | null
  reviewed_by_user_id: number | null
  create_time: string
}

export interface SourceDocumentItem {
  id: number
  document_key: string
  entity_id: number | null
  document_type: string
  original_name: string
  mime_type: string
  content_hash: string
  file_size: number
  version: number
  source_channel: string
  sensitivity: 'normal' | 'sensitive' | 'highly_sensitive'
  create_time: string
  download_url: string
}

export interface ProfileDetail {
  entity: EntityItem
  field_definitions: FieldDefinitionItem[]
  facts: FieldValueItem[]
  documents: SourceDocumentItem[]
}

export interface ProductProfileSummary {
  entity: EntityItem
  fund_product_id: number
  product_code: string
  product_name: string
  document_count: number
}

export interface ProductMaterialAttributionItem {
  id: number
  status: 'pending' | 'assigned'
  document: SourceDocumentItem
  product_entity_id: number | null
  assigned_by_user_id: number | null
  assigned_at: string | null
  notes: string | null
}
