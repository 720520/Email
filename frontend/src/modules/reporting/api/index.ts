import { http } from '@/platform/api/http'

import type {
  ContractUploadResult,
  DynamicReportField,
  DynamicReportFieldPayload,
  ProductReportFieldValue,
  OnlyOfficeSession,
  ReportDefinition,
  ReportDefinitionPayload,
  ReportBatch,
  ReportBatchItem,
  ReportGenerateResult,
  ReportFileVersion,
  ReportPreview,
  ReportProductFields,
  ReportRun,
  ReportTemplateItem,
  ResolvedDynamicField,
} from './types'

export async function getReportTemplates() {
  return (await http.get<ReportTemplateItem[]>('/reports/templates')).data
}

export async function getDynamicReportFields(includeInactive = false) {
  return (
    await http.get<DynamicReportField[]>('/report-fields', {
      params: { include_inactive: includeInactive },
    })
  ).data
}

export async function createDynamicReportField(payload: DynamicReportFieldPayload) {
  return (await http.post<DynamicReportField>('/report-fields', payload)).data
}

export async function updateDynamicReportField(
  id: number,
  payload: Partial<Omit<DynamicReportFieldPayload, 'field_key'>>,
) {
  return (await http.patch<DynamicReportField>(`/report-fields/${id}`, payload)).data
}

export async function disableDynamicReportField(id: number) {
  return (await http.post<DynamicReportField>(`/report-fields/${id}/disable`)).data
}

export async function getProductReportFieldValues(productId: number) {
  return (
    await http.get<ProductReportFieldValue[]>(`/report-fields/products/${productId}/values`)
  ).data
}

export async function setProductReportFieldValue(
  productId: number,
  fieldKey: string,
  payload: { value: unknown; effective_date?: string; source_reference?: string },
) {
  return (
    await http.put<ProductReportFieldValue>(
      `/report-fields/products/${productId}/values/${fieldKey}`,
      payload,
    )
  ).data
}

export async function resolveDynamicReportFields(payload: {
  field_keys: string[]
  product_id?: number
  report_date?: string
}) {
  return (
    await http.post<{ fields: Record<string, ResolvedDynamicField> }>(
      '/report-fields/resolve',
      payload,
    )
  ).data
}

export async function uploadReportTemplate(file: File, name: string, description?: string) {
  const body = new FormData()
  body.append('file', file)
  body.append('name', name)
  if (description) body.append('description', description)
  return (await http.post<ReportTemplateItem>('/reports/templates', body, { timeout: 180_000 })).data
}

export async function validateReportTemplate(templateId: number) {
  return (
    await http.post<ReportTemplateItem>(`/reports/templates/${templateId}/validate`)
  ).data
}

export async function publishReportTemplate(templateId: number) {
  return (
    await http.post<ReportTemplateItem>(`/reports/templates/${templateId}/publish`)
  ).data
}

export async function uploadReportTemplateVersion(templateId: number, file: File) {
  const body = new FormData()
  body.append('file', file)
  return (
    await http.post<ReportTemplateItem>(`/reports/templates/${templateId}/versions`, body, {
      timeout: 180_000,
    })
  ).data
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

export async function regenerateReport(runId: number) {
  return (await http.post<ReportGenerateResult>(`/reports/runs/${runId}/regenerate`, undefined, {
    timeout: 180_000,
  })).data
}

export async function getReportFileVersions(runId: number) {
  return (await http.get<ReportFileVersion[]>(`/reports/runs/${runId}/versions`)).data
}

export async function createReportBatch(payload: {
  product_ids: number[]
  template_key: string
  report_date: string
  sections: string[]
  settings: Record<string, unknown>
  idempotency_key: string
}) {
  return (await http.post<ReportBatch>('/reports/batches', payload)).data
}

export async function getReportBatch(batchId: number) {
  return (await http.get<ReportBatch>(`/reports/batches/${batchId}`)).data
}

export async function getReportBatchItems(batchId: number) {
  return (await http.get<ReportBatchItem[]>(`/reports/batches/${batchId}/items`)).data
}

export async function retryReportBatch(batchId: number) {
  return (await http.post<ReportBatch>(`/reports/batches/${batchId}/retry`)).data
}

export async function cancelReportBatch(batchId: number) {
  return (await http.post<ReportBatch>(`/reports/batches/${batchId}/cancel`)).data
}

export async function downloadReportBatch(batchId: number) {
  return (
    await http.get<Blob>(`/reports/batches/${batchId}/download`, { responseType: 'blob' })
  ).data
}

export async function createOnlyOfficeSession(runId: number) {
  return (
    await http.post<OnlyOfficeSession>(`/reports/runs/${runId}/onlyoffice/session`)
  ).data
}
