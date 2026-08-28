import type { SourceDocumentItem } from '@/modules/tenant-admin/api/types'

export interface InstitutionItem {
  id: number
  entity_id: number
  institution_type: string
  full_name: string
  short_name: string | null
  license_code: string | null
  contact_information: Record<string, string>
  is_active: boolean
  create_time: string
  update_time: string
}

export interface InstitutionPayload {
  institution_type: string
  full_name: string
  short_name?: string
  license_code?: string
  contact_information: Record<string, string>
}

export type SourceScope = 'organization' | 'product' | 'account_application'

export interface RequirementTemplateItem {
  id?: number
  requirement_code: string
  name: string
  source_scope: SourceScope
  required: boolean
  condition: Record<string, unknown>
  seal_requirement?: string | null
  original_required: boolean
  sort_order: number
}

export interface RequirementTemplate {
  id: number
  template_scope: 'regulatory' | 'institution'
  institution_id: number | null
  institution_name: string | null
  account_type: string
  fund_type: string
  name: string
  version: number
  effective_from: string
  effective_to: string | null
  is_active: boolean
  items: RequirementTemplateItem[]
  create_time: string
  update_time: string
}

export interface RequirementTemplatePayload {
  template_scope: 'regulatory' | 'institution'
  institution_id?: number
  account_type: string
  fund_type: string
  name: string
  version: number
  effective_from: string
  effective_to?: string
  items: RequirementTemplateItem[]
}

export interface ApplicationRequirement {
  id: number
  requirement_code: string
  name: string
  source_scope: SourceScope
  required: boolean
  condition: Record<string, unknown>
  seal_requirement: string | null
  original_required: boolean
  status: string
  document_id: number | null
  document_name: string | null
  document_version: number | null
  document_hash: string | null
  review_comment: string | null
  sort_order: number
}

export interface ApplicationSupplement {
  id: number
  requirement_id: number
  document_id: number
  document_name: string
  document_version: number
  document_hash: string
  comment: string | null
  submitted_by_user_id: number
  create_time: string
}

export interface ApplicationEvent {
  id: number
  event_type: string
  from_status: string | null
  to_status: string | null
  comment: string | null
  actor_user_id: number
  detail: Record<string, unknown>
  create_time: string
}

export interface AccountApplicationSummary {
  id: number
  product_id: number
  product_name: string
  product_code: string
  institution_id: number
  institution_name: string
  institution_type: string
  account_type: string
  settlement_mode: string
  fund_type: string
  status: string
  application_date: string
  completed_date: string | null
  closed_date: string | null
  owner_user_id: number
  reviewer_user_id: number | null
  submitted_at: string | null
  requirement_count: number
  completed_requirement_count: number
  create_time: string
  update_time: string
}

export interface AccountApplicationDetail extends AccountApplicationSummary {
  requirements: ApplicationRequirement[]
  supplements: ApplicationSupplement[]
  events: ApplicationEvent[]
}

export interface AccountApplicationPayload {
  product_id: number
  institution_id: number
  account_type: string
  settlement_mode: string
  fund_type: string
  application_date: string
}

export interface ApplicationReviewPayload {
  action: 'request_supplement' | 'approve' | 'reject' | 'open' | 'close'
  requirement_ids?: number[]
  comment?: string
}

export type AvailableDocument = SourceDocumentItem
