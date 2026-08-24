import { http } from '@/platform/api/http'

import type {
  FilingProfile,
  FilingProfilePayload,
  FilingFieldDefinition,
  FilingFieldPayload,
  FilingFileVersion,
  TenantCreatePayload,
  TenantMember,
  TenantMemberCreatePayload,
  TenantMemberUpdatePayload,
  TenantSummary,
  TenantUpdatePayload,
} from './types'

export async function getFilingProfile(): Promise<FilingProfile> {
  return (await http.get<FilingProfile>('/filing-profile')).data
}

export async function updateFilingProfile(payload: FilingProfilePayload): Promise<FilingProfile> {
  return (await http.put<FilingProfile>('/filing-profile', payload)).data
}

export async function downloadFilingProfile(): Promise<Blob> {
  return (await http.get<Blob>('/filing-profile/export.txt', { responseType: 'blob' })).data
}

export async function createFilingField(payload: FilingFieldPayload): Promise<FilingFieldDefinition> {
  return (await http.post<FilingFieldDefinition>('/filing-profile/fields', payload)).data
}

export async function updateFilingField(id: number, payload: FilingFieldPayload): Promise<FilingFieldDefinition> {
  return (await http.patch<FilingFieldDefinition>(`/filing-profile/fields/${id}`, payload)).data
}

export async function deleteFilingField(id: number): Promise<void> {
  await http.delete(`/filing-profile/fields/${id}`)
}

export async function uploadFilingFile(fieldId: number, file: File): Promise<FilingFileVersion> {
  const form = new FormData()
  form.append('file', file)
  return (await http.post<FilingFileVersion>(`/filing-profile/fields/${fieldId}/files`, form)).data
}

export async function downloadFilingFile(url: string): Promise<Blob> {
  return (await http.get<Blob>(url.replace('/api/v1', ''), { responseType: 'blob' })).data
}

export async function getTenants(): Promise<TenantSummary[]> {
  const { data } = await http.get<TenantSummary[]>('/tenants')
  return data
}

export async function createTenant(payload: TenantCreatePayload): Promise<TenantSummary> {
  const { data } = await http.post<TenantSummary>('/tenants', payload)
  return data
}

export async function updateTenant(id: number, payload: TenantUpdatePayload): Promise<TenantSummary> {
  const { data } = await http.patch<TenantSummary>(`/tenants/${id}`, payload)
  return data
}

export async function getTenantMembers(tenantId: number): Promise<TenantMember[]> {
  const { data } = await http.get<TenantMember[]>(`/tenants/${tenantId}/members`)
  return data
}

export async function createTenantMember(
  tenantId: number,
  payload: TenantMemberCreatePayload,
): Promise<TenantMember> {
  const { data } = await http.post<TenantMember>(`/tenants/${tenantId}/members`, payload)
  return data
}

export async function updateTenantMember(
  tenantId: number,
  userId: number,
  payload: TenantMemberUpdatePayload,
): Promise<TenantMember> {
  const { data } = await http.put<TenantMember>(
    `/tenants/${tenantId}/members/${userId}`,
    payload,
  )
  return data
}
