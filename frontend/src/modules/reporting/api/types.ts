export interface ReportTemplateItem {
  key: string
  id: number | null
  name: string
  description: string | null
  kind: 'builtin' | 'uploaded'
  original_name: string | null
  is_active: boolean
  create_time: string | null
  version_id: number | null
  version: number | null
  status: 'builtin' | 'draft' | 'validating' | 'published' | 'archived'
  required_fields: string[]
  required_components: string[]
  validation_errors: Array<{ code: string; message: string; slide?: number; location?: string }>
}

export interface ReportProductField {
  key: string
  label: string
  group: string
  value: string | null
  source_type: string | null
  source_reference: string | null
  is_manual: boolean
  editable: boolean
}

export interface ReportProductFields {
  product_id: number
  product_code: string
  product_name: string
  fields: ReportProductField[]
}

export interface ReportDefinitionPayload {
  name: string
  fund_product_id: number
  template_key: string
  report_type: 'weekly' | 'custom'
  sections: string[]
  settings: Record<string, unknown>
}

export interface ReportDefinition extends ReportDefinitionPayload {
  id: number
  create_time: string
  update_time: string
}

export interface ReportPreview {
  product_id: number
  product_code: string
  product_name: string
  report_date: string
  fields: Record<string, string | null>
  field_provenance: ReportProductField[]
  performance: Record<string, string | null>
  nav_series: Array<{ date: string; unit_nav: string | null; total_nav: string | null }>
}

export interface ReportRun {
  id: number
  definition_id: number | null
  fund_product_id: number
  product_name: string
  template_key: string
  report_date: string
  status: string
  output_filename: string | null
  current_version_id: number | null
  current_version: number | null
  template_version_id: number | null
  error_stage: string | null
  error_code: string | null
  error_message: string | null
  create_time: string
}

export interface ReportFileVersion {
  id: number
  report_run_id: number
  version: number
  source: string
  filename: string
  content_hash: string
  file_size: number
  create_time: string
}

export interface ReportGenerateResult {
  run: ReportRun
  download_url: string | null
}

export interface ReportBatch {
  id: number
  template_key: string
  template_version_id: number | null
  report_date: string
  status: string
  total_count: number
  success_count: number
  failed_count: number
  cancelled_count: number
  create_time: string
}

export interface ReportBatchItem {
  id: number
  fund_product_id: number
  product_name: string
  status: string
  report_run_id: number | null
  attempt_count: number
  error_code: string | null
  error_message: string | null
}

export interface OnlyOfficeSession {
  api_url: string
  config: Record<string, unknown>
}

export interface ReportLayoutPlacement {
  id: string
  token: string
  slide: number
  x: number
  y: number
  width: number
  height: number
  font_size: number
  bold: boolean
  color: string
}

export interface ReportDesignMetadata {
  slide_count: number
  slide_width: number
  slide_height: number
  placements: ReportLayoutPlacement[]
}

export interface ContractUploadResult {
  document_id: number
  original_name: string
  extracted_fields: Record<string, string>
  extracted_count: number
}

export type ReportFieldDataType =
  | 'string' | 'number' | 'percentage' | 'date' | 'boolean' | 'rich_text'
  | 'image' | 'list' | 'table' | 'chart' | 'json'

export interface DynamicReportField {
  id: number | null
  field_key: string
  label: string
  description: string | null
  data_type: ReportFieldDataType
  value_kind: string
  source_type: string
  format_config: Record<string, unknown>
  default_value: string | null
  is_required: boolean
  is_sensitive: boolean
  is_active: boolean
  is_system: boolean
  version: number
  create_time: string | null
  update_time: string | null
}

export interface DynamicReportFieldPayload {
  field_key: string
  label: string
  description?: string
  data_type: ReportFieldDataType
  value_kind: string
  default_value?: string
  is_required: boolean
  is_sensitive: boolean
  format_config: Record<string, unknown>
}

export interface ProductReportFieldValue {
  field_key: string
  label: string
  data_type: ReportFieldDataType
  value: unknown
  effective_date: string | null
  source_type: string | null
  source_reference: string | null
  version: number
}

export interface ResolvedDynamicField {
  field_key: string
  value: unknown
  data_type: string
  source_type: string | null
  source_reference: string | null
  used_default: boolean
}
