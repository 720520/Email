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
  FundProductDetail,
  FundProductNavUpdateSummary,
  FundProductPage,
  FundProductProfilePayload,
  FundProductSummary,
  LatestFundNavDate,
  ManualReparseResult,
  MailboxAccount,
  MailboxAccountPayload,
  MailboxGrant,
  MailboxGrantPayload,
  MailboxSecurityStatus,
  ProductOption,
  TenantMember,
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

export async function getEmailConnectionInfo(mailboxAccountId?: number) {
  return (await http.get<EmailConnectionInfo>('/emails/connection', {
    params: { mailbox_account_id: mailboxAccountId },
  })).data
}

export async function testEmailConnection(mailboxAccountId?: number) {
  return (await http.post<EmailConnectionTest>('/emails/connection/test', undefined, {
    params: { mailbox_account_id: mailboxAccountId },
  })).data
}

export async function syncEmailNow(mailboxAccountId?: number) {
  return (await http.post<EmailSyncResult>('/emails/sync', undefined, {
    params: { mailbox_account_id: mailboxAccountId },
  })).data
}

export async function getMailboxes() {
  return (await http.get<MailboxAccount[]>('/mailboxes')).data
}

export async function getMailboxSecurityStatus() {
  return (await http.get<MailboxSecurityStatus>('/mailboxes/security-status')).data
}

export async function createMailbox(payload: MailboxAccountPayload) {
  return (await http.post<MailboxAccount>('/mailboxes', payload)).data
}

export async function updateMailbox(id: number, payload: MailboxAccountPayload) {
  return (await http.patch<MailboxAccount>(`/mailboxes/${id}`, payload)).data
}

export async function testMailboxConnection(id: number) {
  return (await http.post<EmailConnectionTest>(`/mailboxes/${id}/connection-test`)).data
}

export async function syncMailbox(id: number) {
  return (await http.post<EmailSyncResult>(`/mailboxes/${id}/sync`)).data
}

export async function getTenantMembers() {
  return (await http.get<TenantMember[]>('/mailboxes/members')).data
}

export async function getMailboxGrants(id: number) {
  return (await http.get<MailboxGrant[]>(`/mailboxes/${id}/grants`)).data
}

export async function updateMailboxGrant(
  mailboxId: number,
  userId: number,
  payload: MailboxGrantPayload,
) {
  return (await http.put<MailboxGrant>(`/mailboxes/${mailboxId}/grants/${userId}`, payload)).data
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

export async function getFundProductSummary() {
  return (await http.get<FundProductSummary>('/fund-products/summary')).data
}

export async function getFundProductNavUpdateStatus(navDate: string) {
  return (
    await http.get<FundProductNavUpdateSummary>('/fund-products/nav-update-status', {
      params: { nav_date: navDate },
    })
  ).data
}

export async function getFundProducts(params: AxiosRequestConfig['params']) {
  return (await http.get<FundProductPage>('/fund-products', { params })).data
}

export async function getFundProduct(id: number) {
  return (await http.get<FundProductDetail>(`/fund-products/${id}`)).data
}

export async function updateFundProductProfile(id: number, payload: FundProductProfilePayload) {
  return (await http.patch<FundProductDetail>(`/fund-products/${id}/profile`, payload)).data
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

export async function uploadForReparse(
  file: File,
  sourceAttachmentId?: number,
  mailboxAccountId?: number,
) {
  const body = new FormData()
  body.append('file', file)
  if (sourceAttachmentId) body.append('source_attachment_id', String(sourceAttachmentId))
  if (mailboxAccountId) body.append('mailbox_account_id', String(mailboxAccountId))
  return (await http.post<ManualReparseResult>('/operations/manual-reparse', body)).data
}
