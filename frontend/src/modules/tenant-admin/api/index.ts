import { http } from '@/platform/api/http'

import type {
  TenantCreatePayload,
  TenantMember,
  TenantMemberCreatePayload,
  TenantMemberUpdatePayload,
  TenantSummary,
  TenantUpdatePayload,
} from './types'

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
