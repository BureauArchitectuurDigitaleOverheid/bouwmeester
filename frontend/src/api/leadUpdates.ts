import { apiDelete, apiGet, apiPost, apiPut, BASE_URL, getCsrfToken } from '@/api/client';
import type {
  LeadUpdateExtractResult,
  LeadUpdatePost,
  LeadUpdatePostCreate,
  LeadUpdatePostEdit,
} from '@/types';

export async function listLeadUpdates(leadId: string): Promise<LeadUpdatePost[]> {
  return apiGet<LeadUpdatePost[]>(`/api/leads/${leadId}/updates`);
}

export async function createLeadUpdate(
  leadId: string,
  data: LeadUpdatePostCreate,
): Promise<LeadUpdatePost> {
  return apiPost<LeadUpdatePost>(`/api/leads/${leadId}/updates`, data);
}

export async function editLeadUpdate(
  leadId: string,
  postId: string,
  data: LeadUpdatePostEdit,
): Promise<LeadUpdatePost> {
  return apiPut<LeadUpdatePost>(`/api/leads/${leadId}/updates/${postId}`, data);
}

export async function publishLeadUpdate(
  leadId: string,
  postId: string,
): Promise<LeadUpdatePost> {
  return apiPost<LeadUpdatePost>(`/api/leads/${leadId}/updates/${postId}/publish`);
}

export async function unpublishLeadUpdate(
  leadId: string,
  postId: string,
): Promise<LeadUpdatePost> {
  return apiPost<LeadUpdatePost>(`/api/leads/${leadId}/updates/${postId}/unpublish`);
}

export async function deleteLeadUpdate(leadId: string, postId: string): Promise<void> {
  return apiDelete(`/api/leads/${leadId}/updates/${postId}`);
}

export async function parseLeadUpdate(
  leadId: string,
  options: {
    rawText?: string;
    useLeadHistory?: boolean;
    includeAttachments?: boolean;
    files?: File[];
  },
): Promise<LeadUpdateExtractResult> {
  const formData = new FormData();
  if (options.rawText) formData.append('raw_text', options.rawText);
  if (options.useLeadHistory) formData.append('use_lead_history', 'true');
  if (options.includeAttachments) formData.append('include_attachments', 'true');
  if (options.files) {
    for (const file of options.files) formData.append('files', file);
  }
  const url = `${BASE_URL}/api/leads/${leadId}/updates/parse`;
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

export function getLeadUpdateEmlUrl(leadId: string, postId: string): string {
  return `${BASE_URL}/api/leads/${leadId}/updates/${postId}/eml`;
}
