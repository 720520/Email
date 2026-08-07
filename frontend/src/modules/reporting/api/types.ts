export interface ReportTemplateItem {
  key: string
  id: number | null
  name: string
  description: string | null
  kind: 'builtin' | 'uploaded'
  original_name: string | null
  is_active: boolean
  create_time: string | null
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
  error_message: string | null
  create_time: string
}

export interface ReportGenerateResult {
  run: ReportRun
  download_url: string | null
}

export interface ContractUploadResult {
  document_id: number
  original_name: string
  extracted_fields: Record<string, string>
  extracted_count: number
}
