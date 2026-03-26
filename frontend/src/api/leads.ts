import { apiGet, apiPost, apiPut, apiDelete, getCsrfToken, BASE_URL } from './client';
import type {
  Lead,
  LeadDetail,
  LeadCreate,
  LeadUpdate,
  LeadActivity,
  LeadActivityCreate,
  LeadMetrics,
  LeadFilters,
  LeadAttachment,
  LeadParseResult,
  CommunityGraphResponse,
} from '@/types';

export async function getLeads(filters?: LeadFilters): Promise<Lead[]> {
  const params: Record<string, string> = {};
  if (filters?.stage) params.stage = filters.stage;
  if (filters?.tag) params.tag = filters.tag;
  if (filters?.assignee_id) params.assignee_id = filters.assignee_id;
  return apiGet<Lead[]>('/api/leads', params);
}

export async function getLead(id: string): Promise<LeadDetail> {
  return apiGet<LeadDetail>(`/api/leads/${id}`);
}

export async function createLead(data: LeadCreate): Promise<Lead> {
  return apiPost<Lead>('/api/leads', data);
}

export async function updateLead(id: string, data: LeadUpdate): Promise<Lead> {
  return apiPut<Lead>(`/api/leads/${id}`, data);
}

export async function deleteLead(id: string): Promise<void> {
  return apiDelete(`/api/leads/${id}`);
}

export async function moveLead(id: string, stage: string): Promise<Lead> {
  return apiPut<Lead>(`/api/leads/${id}/move`, { stage });
}

export async function reorderLeads(leadIds: string[], stage: string): Promise<void> {
  return apiPut(`/api/leads/reorder`, { lead_ids: leadIds, stage });
}

export async function getLeadActivities(leadId: string): Promise<LeadActivity[]> {
  return apiGet<LeadActivity[]>(`/api/leads/${leadId}/activities`);
}

export async function createLeadActivity(
  leadId: string,
  data: LeadActivityCreate,
): Promise<LeadActivity> {
  return apiPost<LeadActivity>(`/api/leads/${leadId}/activities`, data);
}

export async function addLeadContact(
  leadId: string,
  personId: string,
  rol: string,
): Promise<void> {
  return apiPost(`/api/leads/${leadId}/contacts`, { person_id: personId, rol });
}

export async function removeLeadContact(leadId: string, contactId: string): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/contacts/${contactId}`);
}

export async function linkLeadNode(leadId: string, nodeId: string): Promise<void> {
  return apiPost(`/api/leads/${leadId}/nodes`, { node_id: nodeId });
}

export async function unlinkLeadNode(leadId: string, linkId: string): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/nodes/${linkId}`);
}

export async function getLeadMetrics(): Promise<LeadMetrics> {
  return apiGet<LeadMetrics>('/api/leads/metrics');
}

export async function uploadLeadAttachment(leadId: string, file: File): Promise<LeadAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  const url = `${BASE_URL}/api/leads/${leadId}/attachments`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Upload failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function deleteLeadAttachment(
  leadId: string,
  attachmentId: string,
): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/attachments/${attachmentId}`);
}

export function getLeadAttachmentDownloadUrl(leadId: string, attachmentId: string): string {
  return `${BASE_URL}/api/leads/${leadId}/attachments/${attachmentId}/download`;
}

export async function getCommunityGraph(): Promise<CommunityGraphResponse> {
  return apiGet<CommunityGraphResponse>('/api/graph/community');
}

export async function parseLeadIntake(rawText?: string, files?: File[]): Promise<LeadParseResult> {
  const formData = new FormData();
  if (rawText) formData.append('raw_text', rawText);
  if (files) {
    for (const file of files) {
      formData.append('files', file);
    }
  }
  const url = `${BASE_URL}/api/leads/parse-intake`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Parse failed: ${response.status} ${text}`);
  }
  return response.json();
}
