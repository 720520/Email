import type { AxiosRequestConfig } from 'axios'

import { http } from '@/platform/api/http'

import type {
  DashboardData,
  EmailConnectionInfo,
  EmailConnectionTest,
  EmailDetail,
  EmailSyncResult,
  EmailPage,
  ExceptionItem,
  ExceptionPage,
  FundHistory,
  FundNavPage,
  LatestFundNavDate,
  ManualReparseResult,
  ProductOption,
} from './types'

export async function getDashboard() {
  return (await http.get<DashboardData>('/dashboard')).data
}

export async function getEmails(params: AxiosRequestConfig['params']) {
  return (await http.get<EmailPage>('/emails', { params })).data
}

export async function getEmailDetail(id: number) {
  return (await http.get<EmailDetail>(`/emails/${id}`)).data
}

export async function downloadRawEmail(id: number) {
  return (await http.get<Blob>(`/emails/${id}/raw`, { responseType: 'blob' })).data
}

export async function getEmailConnectionInfo() {
  return (await http.get<EmailConnectionInfo>('/emails/connection')).data
}

export async function testEmailConnection() {
  return (await http.post<EmailConnectionTest>('/emails/connection/test')).data
}

export async function syncEmailNow() {
  return (await http.post<EmailSyncResult>('/emails/sync')).data
}

export async function getFundNav(params: AxiosRequestConfig['params']) {
  return (await http.get<FundNavPage>('/fund-nav', { params })).data
}

export async function getLatestFundNavDate() {
  return (await http.get<LatestFundNavDate>('/fund-nav/latest-date')).data
}

export async function searchProducts(keyword?: string) {
  return (await http.get<ProductOption[]>('/fund-nav/products', {
    params: { keyword: keyword?.trim() || undefined },
  })).data
}

export async function getFundHistory(productCode: string) {
  return (await http.get<FundHistory>('/fund-nav/history', { params: { product_code: productCode } })).data
}

export async function downloadDailyExport(reportDate: string) {
  return (await http.get<Blob>('/fund-nav/export', { params: { report_date: reportDate }, responseType: 'blob' })).data
}

export async function getExceptions(params: AxiosRequestConfig['params']) {
  return (await http.get<ExceptionPage>('/exceptions', { params })).data
}

export async function updateExceptionStatus(id: number, status: 'open' | 'resolved' | 'ignored') {
  return (await http.patch<ExceptionItem>(`/exceptions/${id}/status`, { status })).data
}

export async function uploadForReparse(file: File, sourceAttachmentId?: number) {
  const body = new FormData()
  body.append('file', file)
  if (sourceAttachmentId) body.append('source_attachment_id', String(sourceAttachmentId))
  return (await http.post<ManualReparseResult>('/operations/manual-reparse', body)).data
}
