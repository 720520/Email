import type { PageResponse } from '@/platform/api/types'

export type EmailStatus = 'discovered' | 'archived' | 'processing' | 'success' | 'partial_success' | 'failed' | 'skipped'
export type AttachmentStatus = 'pending' | 'archived' | 'parsing' | 'success' | 'partial_success' | 'failed' | 'duplicate' | 'unsupported'
export type ExceptionStatus = 'open' | 'resolved' | 'ignored'
export type ExceptionSeverity = 'error' | 'warning'

export interface RecentException {
  id: number
  category: string
  message: string
  source: string
  severity: ExceptionSeverity
  create_time: string
}

export interface DashboardData {
  business_date: string
  today_email_count: number
  success_email_count: number
  fund_count: number
  open_exception_count: number
  latest_nav_date: string | null
  latest_nav_count: number
  recent_exceptions: RecentException[]
}

export interface EmailItem {
  id: number
  subject: string
  sender: string
  receive_time: string
  attachment_count: number
  status: EmailStatus
  error_message: string | null
}

export interface EmailConnectionInfo {
  host: string
  port: number
  username: string
  auth_mode: 'password' | 'oauth2'
  folder: string
  transport: string
  timeout_seconds: number
  credential_configured: boolean
  configured: boolean
}

export interface EmailAttachmentDetail {
  id: number
  original_name: string
  file_type: string | null
  parse_status: AttachmentStatus
  error_message: string | null
}

export interface EmailDetail {
  id: number
  subject: string
  sender: string
  receive_time: string
  status: EmailStatus
  error_message: string | null
  attachments: EmailAttachmentDetail[]
  body_text: string
  body_truncated: boolean
  original_available: boolean
}

export interface EmailConnectionTest {
  success: boolean
  message: string
  checked_at: string
  latency_ms: number
  uid_validity: string | null
  message_count: number | null
}

export interface EmailSyncResult {
  success: boolean
  message: string
  job_run_id: number
  attempts: number
  discovered_count: number
  archived_count: number
  ignored_count: number
  duplicate_count: number
  failed_count: number
}

export interface FundNavItem {
  id: number
  product_name: string
  product_code: string
  nav_date: string
  unit_nav: string | null
  total_nav: string | null
  asset_value: string | null
  source_file: string
  fund_group_name: string
  share_class: string | null
}

export interface LatestFundNavDate {
  latest_nav_date: string | null
}

export interface ProductOption {
  product_name: string
  product_code: string
  fund_group_name: string
  share_class: string | null
}

export interface HistoryPoint {
  nav_date: string
  unit_nav: string | null
  total_nav: string | null
}

export interface FundHistory {
  product_name: string
  product_code: string
  points: HistoryPoint[]
}

export interface ExceptionItem {
  id: number
  email_id: number | null
  category: string
  exception_type: string
  severity: ExceptionSeverity
  product_code: string | null
  product_name: string | null
  source: string
  sheet_name: string | null
  row_number: number | null
  field_name: string | null
  raw_value: string | null
  message: string
  status: ExceptionStatus
  create_time: string
}

export interface ManualReparseResult {
  email_id: number
  attachment_id: number
  inserted_count: number
  duplicate_count: number
  exception_count: number
  status: string
  source_file: string
}

export type EmailPage = PageResponse<EmailItem>
export type FundNavPage = PageResponse<FundNavItem>
export type ExceptionPage = PageResponse<ExceptionItem>
