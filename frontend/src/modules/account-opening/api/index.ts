import { governanceHttp } from '@/platform/api/http'

import type {
  AccountApplicationDetail,
  AccountApplicationPayload,
  AccountApplicationSummary,
  ApplicationReviewPayload,
  AvailableDocument,
  InstitutionItem,
  InstitutionPayload,
  RequirementTemplate,
  RequirementTemplatePayload,
  SourceScope,
} from './types'

export async function listInstitutions(includeInactive = false): Promise<InstitutionItem[]> {
  return (
    await governanceHttp.get<InstitutionItem[]>('/institutions', {
      params: { include_inactive: includeInactive },
    })
  ).data
}

export async function createInstitution(payload: InstitutionPayload): Promise<InstitutionItem> {
  return (await governanceHttp.post<InstitutionItem>('/institutions', payload)).data
}

export async function updateInstitution(
  id: number,
  payload: Partial<InstitutionPayload> & { is_active?: boolean },
): Promise<InstitutionItem> {
  return (await governanceHttp.patch<InstitutionItem>(`/institutions/${id}`, payload)).data
}

export async function listRequirementTemplates(
  includeInactive = false,
): Promise<RequirementTemplate[]> {
  return (
    await governanceHttp.get<RequirementTemplate[]>('/requirement-templates', {
      params: { include_inactive: includeInactive },
    })
  ).data
}

export async function createRequirementTemplate(
  payload: RequirementTemplatePayload,
): Promise<RequirementTemplate> {
  return (await governanceHttp.post<RequirementTemplate>('/requirement-templates', payload)).data
}

export async function setRequirementTemplateState(
  id: number,
  isActive: boolean,
): Promise<RequirementTemplate> {
  return (
    await governanceHttp.patch<RequirementTemplate>(`/requirement-templates/${id}/state`, {
      is_active: isActive,
    })
  ).data
}

export async function listAccountApplications(): Promise<AccountApplicationSummary[]> {
  return (await governanceHttp.get<AccountApplicationSummary[]>('/account-applications')).data
}

export async function createAccountApplication(
  payload: AccountApplicationPayload,
): Promise<AccountApplicationDetail> {
  return (await governanceHttp.post<AccountApplicationDetail>('/account-applications', payload)).data
}

export async function getAccountApplication(id: number): Promise<AccountApplicationDetail> {
  return (await governanceHttp.get<AccountApplicationDetail>(`/account-applications/${id}`)).data
}

export async function attachRequirementDocument(
  applicationId: number,
  requirementId: number,
  documentId: number,
): Promise<AccountApplicationDetail> {
  return (
    await governanceHttp.put<AccountApplicationDetail>(
      `/account-applications/${applicationId}/requirements/${requirementId}`,
      { document_id: documentId },
    )
  ).data
}

export async function submitAccountApplication(id: number): Promise<AccountApplicationDetail> {
  return (await governanceHttp.post<AccountApplicationDetail>(`/account-applications/${id}/submit`)).data
}

export async function addApplicationSupplement(
  applicationId: number,
  requirementId: number,
  documentId: number,
  comment?: string,
): Promise<AccountApplicationDetail> {
  return (
    await governanceHttp.post<AccountApplicationDetail>(
      `/account-applications/${applicationId}/supplements`,
      { requirement_id: requirementId, document_id: documentId, comment },
    )
  ).data
}

export async function reviewAccountApplication(
  applicationId: number,
  payload: ApplicationReviewPayload,
): Promise<AccountApplicationDetail> {
  return (
    await governanceHttp.post<AccountApplicationDetail>(
      `/account-applications/${applicationId}/review`,
      payload,
    )
  ).data
}

export async function listAvailableDocuments(
  applicationId: number,
  sourceScope: SourceScope,
): Promise<AvailableDocument[]> {
  return (
    await governanceHttp.get<AvailableDocument[]>(
      `/account-applications/${applicationId}/available-documents`,
      { params: { source_scope: sourceScope } },
    )
  ).data
}
