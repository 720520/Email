import type { PageResponse } from '@/platform/api/types'
import type { UserRole } from '@/platform/api/types'

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
  mailbox_account_id: number
  mailbox_name: string
  subject: string
  sender: string
  receive_time: string
  attachment_count: number
  status: EmailStatus
  error_message: string | null
}

export interface EmailConnectionInfo {
  mailbox_account_id: number
  display_name: string
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

export interface MailboxPermissions {
  can_read_metadata: boolean
  can_read_content: boolean
  can_operate: boolean
  can_manage_credentials: boolean
}

export interface MailboxAccount {
  id: number
  display_name: string
  provider_type: string
  host: string
  port: number
  username: string
  auth_mode: 'password' | 'oauth2'
  use_ssl: boolean
  start_tls: boolean
  timeout_seconds: number
  folder: string
  lookback_days: number
  max_messages_per_run: number
  max_attachment_bytes: number
  is_default: boolean
  is_enabled: boolean
  credential_configured: boolean
  configuration_source: string
  last_connection_status: string | null
  last_connection_at: string | null
  last_connection_error: string | null
  last_sync_status: string | null
  last_sync_at: string | null
  permissions: MailboxPermissions
}

export interface MailboxSecurityStatus {
  credential_key_configured: boolean
  audit_key_configured: boolean
  ready_for_credentials: boolean
}

export interface MailboxAccountPayload {
  display_name?: string
  host?: string
  port?: number
  username?: string
  auth_mode?: 'password' | 'oauth2'
  credential?: string
  clear_credential?: boolean
  use_ssl?: boolean
  start_tls?: boolean
  timeout_seconds?: number
  folder?: string
  lookback_days?: number
  max_messages_per_run?: number
  max_attachment_bytes?: number
  retry_attempts?: number
  retry_base_delay_seconds?: number
  uid_reservation_stale_seconds?: number
  is_default?: boolean
  is_enabled?: boolean
}

export interface TenantMember {
  user_id: number
  username: string
  role: UserRole
  is_active: boolean
}

export interface MailboxGrant {
  user_id: number
  username: string
  role: UserRole
  can_read_metadata: boolean
  can_read_content: boolean
  can_operate: boolean
  can_manage_credentials: boolean
  is_active: boolean
}

export type MailboxGrantPayload = Pick<
  MailboxGrant,
  'can_read_metadata' | 'can_read_content' | 'can_operate' | 'can_manage_credentials' | 'is_active'
>

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
  queued_attachment_count: number
}

export interface FundNavItem {
  id: number
  mailbox_account_id: number
  mailbox_name: string
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

export interface FundProductSummary {
  product_count: number
  share_count: number
  latest_nav_date: string | null
  latest_asset_value: string | null
  missing_manager_count: number
  missing_strategy_count: number
}

export type FundProductNavUpdateStatus = 'updated' | 'partial' | 'pending'

export interface FundProductNavUpdateItem {
  product_id: number
  product_code: string
  product_name: string
  nav_date: string
  status: FundProductNavUpdateStatus
  updated_share_count: number
  expected_share_count: number
  updated_share_codes: string[]
  missing_share_codes: string[]
  latest_update_date: string | null
}

export interface FundProductNavUpdateSummary {
  nav_date: string
  total_count: number
  updated_count: number
  partial_count: number
  pending_count: number
  items: FundProductNavUpdateItem[]
}

export interface FundProductItem {
  id: number
  product_code: string
  product_name: string
  latest_source_date: string | null
  share_count: number
  summary_source: 'total_share' | 'single_share' | 'share_aggregate' | 'unavailable'
  has_share_detail: boolean
  unit_nav: string | null
  total_nav: string | null
  asset_value: string | null
  paid_in_capital: string | null
  total_assets: string | null
  investment_manager_info: string | null
  investment_strategy_info: string | null
  investment_manager_manual: boolean
  investment_strategy_manual: boolean
  latest_source_file: string | null
  inception_date: string | null
  strategy_category: string | null
  manager_name: string | null
  custodian_name: string | null
  risk_level: string | null
  custodian_platform_url: string | null
}

export interface FundProductSnapshot {
  id: number
  mailbox_account_id: number
  nav_date: string
  product_code: string
  product_name: string
  asset_code: string | null
  registration_code: string | null
  share_class: string | null
  unit_nav: string | null
  total_nav: string | null
  asset_value: string | null
  asset_share: string | null
  paid_in_capital: string | null
  holding_shares: string | null
  reference_market_value: string | null
  total_assets: string | null
  total_assets_nav_ratio: string | null
  investor_name: string | null
  investor_account: string | null
  parent_unit_nav: string | null
  parent_total_nav: string | null
  parent_asset_value: string | null
  parent_product_code: string | null
  parent_product_name: string | null
  notes: string | null
  parent_paid_in_capital: string | null
  source_file: string
  available_field_count: number
  total_field_count: number
}

export interface FundProductDetail extends FundProductItem {
  source_investment_manager_info: string | null
  source_investment_strategy_info: string | null
  manual_investment_manager_info: string | null
  manual_investment_strategy_info: string | null
  create_time: string
  update_time: string
  latest_snapshots: FundProductSnapshot[]
}

export interface FundProductProfilePayload {
  investment_manager_info?: string | null
  investment_strategy_info?: string | null
  restore_investment_manager_from_source?: boolean
  restore_investment_strategy_from_source?: boolean
  custodian_platform_url?: string | null
}

export interface ExceptionItem {
  id: number
  mailbox_account_id: number
  mailbox_name: string
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
  parse_session_id: number
  inserted_count: number
  duplicate_count: number
  exception_count: number
  valid_count: number
  invalid_count: number
  status: string
  source_file: string
  message: string
  records: ParseReviewRow[]
  issues: ParseReviewIssue[]
}

export interface ParseReviewIssue {
  code: string
  severity: string
  message: string
  sheet_name: string | null
  row_number: number | null
  field_name: string | null
  raw_value: unknown
  raw_data: Record<string, unknown> | null
}

export interface ParseReviewRow {
  id: number
  status: string
  source_sheet: string
  source_row: number
  source_type: string
  product_name: string | null
  product_code: string | null
  asset_code: string | null
  registration_code: string | null
  share_class: string | null
  nav_date: string | null
  unit_nav: string | null
  total_nav: string | null
  asset_value: string | null
  asset_share: string | null
  paid_in_capital: string | null
  holding_shares: string | null
  reference_market_value: string | null
  total_assets: string | null
  total_assets_nav_ratio: string | null
  investor_name: string | null
  investor_account: string | null
  parent_unit_nav: string | null
  parent_total_nav: string | null
  parent_asset_value: string | null
  parent_product_code: string | null
  parent_product_name: string | null
  notes: string | null
  parent_paid_in_capital: string | null
  investment_manager_info: string | null
  investment_strategy_info: string | null
  issues: ParseReviewIssue[]
  original_data: Record<string, unknown>
  validation_message: string | null
  is_edited: boolean
  edit_reason: string | null
  row_version: number
  conflict_action: 'unresolved' | 'keep_existing' | 'replace_existing'
  existing_nav_id: number | null
  committed_nav_id: number | null
}

export interface ParseReviewSession {
  id: number
  attachment_id: number
  source_attachment_id: number | null
  status: string
  parser_version: string
  source_file: string
  row_count: number
  valid_count: number
  invalid_count: number
  ignored_count: number
  duplicate_count: number
  inserted_count: number
  error_message: string | null
  create_time: string
  update_time: string
  confirmed_at: string | null
  file_issues: ParseReviewIssue[]
  rows: ParseReviewRow[]
}

export interface ParseReviewRowUpdate {
  product_name?: string | null
  product_code?: string | null
  asset_code?: string | null
  registration_code?: string | null
  share_class?: string | null
  nav_date?: string | null
  unit_nav?: string | null
  total_nav?: string | null
  asset_value?: string | null
  asset_share?: string | null
  paid_in_capital?: string | null
  parent_product_code?: string | null
  parent_product_name?: string | null
  notes?: string | null
  ignored?: boolean
  conflict_action?: 'unresolved' | 'keep_existing' | 'replace_existing'
  edit_reason: string
  expected_version: number
}

export interface ParseCommitResult {
  parse_session_id: number
  status: string
  inserted_count: number
  duplicate_count: number
  exception_count: number
  message: string
}

export interface ParseTaskItem {
  id: number
  attachment_id: number
  source_file: string
  mailbox_name: string
  status: string
  attempt_count: number
  max_attempts: number
  parser_version: string | null
  inserted_count: number
  duplicate_count: number
  exception_count: number
  error_message: string | null
  queued_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ParseTaskSummary {
  queued: number
  running: number
  success: number
  partial_success: number
  duplicate: number
  failed: number
  recent: ParseTaskItem[]
}

export type EmailPage = PageResponse<EmailItem>
export type FundNavPage = PageResponse<FundNavItem>
export type FundProductPage = PageResponse<FundProductItem>
export type ExceptionPage = PageResponse<ExceptionItem>
