import { apiGet, apiPost, apiPut, apiPatch, apiDelete, getCsrfToken, BASE_URL } from './client';
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
  LeadGitHubLink,
  LeadParseResult,
  CommunityGraphResponse,
  LeadTimelineResponse,
  NodeTagResponse,
} from '@/types';

export async function getLeads(filters?: LeadFilters): Promise<Lead[]> {
  const params: Record<string, string> = {};
  if (filters?.stage) params.stage = filters.stage;
  if (filters?.tag) params.tag = filters.tag;
  if (filters?.assignee_id) params.assignee_id = filters.assignee_id;
  if (filters?.date_from) params.date_from = filters.date_from;
  if (filters?.date_to) params.date_to = filters.date_to;
  if (filters?.next_action_filter) params.next_action_filter = filters.next_action_filter;
  if (filters?.sort_by) params.sort_by = filters.sort_by;
  if (filters?.initiatief_id) params.initiatief_id = filters.initiatief_id;
  return apiGet<Lead[]>('/api/leads', params);
}

export async function getLeadTimeline(params?: {
  stage?: string;
  assignee_id?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  initiatief_id?: string;
}): Promise<LeadTimelineResponse> {
  const query: Record<string, string | number> = {};
  if (params?.stage) query.stage = params.stage;
  if (params?.assignee_id) query.assignee_id = params.assignee_id;
  if (params?.date_from) query.date_from = params.date_from;
  if (params?.date_to) query.date_to = params.date_to;
  if (params?.limit) query.limit = params.limit;
  if (params?.initiatief_id) query.initiatief_id = params.initiatief_id;
  return apiGet<LeadTimelineResponse>('/api/leads/timeline', query);
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
  return apiPost<Lead>(`/api/leads/${id}/move`, { stage });
}

export async function reorderLeads(leadIds: string[], stage: string): Promise<void> {
  return apiPost(`/api/leads/reorder`, { lead_ids: leadIds, stage });
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

export async function deleteLeadActivity(
  leadId: string,
  activityId: string,
): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/activities/${activityId}`);
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

export async function getCommunityGraph(
  initiatiefId?: string,
): Promise<CommunityGraphResponse> {
  const qs = initiatiefId ? `?initiatief_id=${encodeURIComponent(initiatiefId)}` : '';
  return apiGet<CommunityGraphResponse>(`/api/graph/community${qs}`);
}

// --- Lead tags ---

export async function getLeadTags(leadId: string): Promise<NodeTagResponse[]> {
  return apiGet<NodeTagResponse[]>(`/api/leads/${leadId}/tags`);
}

export async function addTagToLead(leadId: string, data: { tag_id?: string; tag_name?: string }): Promise<NodeTagResponse> {
  return apiPost<NodeTagResponse>(`/api/leads/${leadId}/tags`, data);
}

export async function removeTagFromLead(leadId: string, tagId: string): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/tags/${tagId}`);
}

export async function checkDuplicateLeads(
  title: string,
  organization?: string,
): Promise<Lead[]> {
  const params: Record<string, string> = { title };
  if (organization) params.organization = organization;
  return apiGet<Lead[]>('/api/leads/check-duplicates', params);
}

export async function mergeLeads(sourceId: string, targetId: string): Promise<Lead> {
  return apiPost<Lead>('/api/leads/merge', { source_id: sourceId, target_id: targetId });
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

export async function listLeadGitHubLinks(leadId: string): Promise<LeadGitHubLink[]> {
  return apiGet<LeadGitHubLink[]>(`/api/leads/${leadId}/github-links`);
}

export async function addLeadGitHubLink(
  leadId: string,
  url: string,
  title?: string | null,
): Promise<LeadGitHubLink> {
  return apiPost<LeadGitHubLink>(`/api/leads/${leadId}/github-links`, { url, title });
}

export async function updateLeadGitHubLink(
  leadId: string,
  linkId: string,
  title: string | null,
): Promise<LeadGitHubLink> {
  return apiPatch<LeadGitHubLink>(
    `/api/leads/${leadId}/github-links/${linkId}`,
    { title },
  );
}

export async function deleteLeadGitHubLink(leadId: string, linkId: string): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/github-links/${linkId}`);
}

export async function refreshLeadGitHubLink(
  leadId: string,
  linkId: string,
): Promise<LeadGitHubLink> {
  return apiPost<LeadGitHubLink>(
    `/api/leads/${leadId}/github-links/${linkId}/refresh`,
    {},
  );
}
