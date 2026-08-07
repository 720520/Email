import { http } from '@/platform/api/http'

import type {
  ContractUploadResult,
  ReportDefinition,
  ReportDefinitionPayload,
  ReportGenerateResult,
  ReportPreview,
  ReportProductFields,
  ReportRun,
  ReportTemplateItem,
} from './types'

export async function getReportTemplates() {
  return (await http.get<ReportTemplateItem[]>('/reports/templates')).data
}

export async function uploadReportTemplate(file: File, name: string, description?: string) {
  const body = new FormData()
  body.append('file', file)
  body.append('name', name)
  if (description) body.append('description', description)
  return (await http.post<ReportTemplateItem>('/reports/templates', body, { timeout: 180_000 })).data
}

export async function getReportProductFields(productId: number) {
  return (await http.get<ReportProductFields>(`/reports/product-fields/${productId}`)).data
}

export async function updateReportProductField(
  productId: number,
  fieldKey: string,
  payload: { value?: string | null; reason: string; restore_source?: boolean },
) {
  return (
    await http.patch<ReportProductFields>(`/reports/product-fields/${productId}/${fieldKey}`, payload)
  ).data
}

export async function uploadProductContract(productId: number, file: File) {
  const body = new FormData()
  body.append('file', file)
  return (
    await http.post<ContractUploadResult>(`/reports/contracts/${productId}`, body, { timeout: 180_000 })
  ).data
}

export async function getReportDefinitions() {
  return (await http.get<ReportDefinition[]>('/reports/definitions')).data
}

export async function createReportDefinition(payload: ReportDefinitionPayload) {
  return (await http.post<ReportDefinition>('/reports/definitions', payload)).data
}

export async function previewReport(payload: {
  fund_product_id: number
  report_date?: string
  settings?: Record<string, unknown>
}) {
  return (await http.post<ReportPreview>('/reports/preview', payload)).data
}

export async function generateReport(payload: {
  definition_id?: number
  fund_product_id?: number
  template_key?: string
  report_date?: string
  sections?: string[]
  settings?: Record<string, unknown>
}) {
  return (await http.post<ReportGenerateResult>('/reports/generate', payload, { timeout: 180_000 })).data
}

export async function getReportRuns() {
  return (await http.get<ReportRun[]>('/reports/runs')).data
}

export async function downloadReport(runId: number) {
  return (await http.get<Blob>(`/reports/runs/${runId}/download`, { responseType: 'blob' })).data
}
