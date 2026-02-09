import { apiGet, apiPost, apiPut, apiPatch } from './client';
import type { ParlementairItem, SuggestedEdge } from '@/types';

export interface ParlementairItemFilters {
  status?: string;
  bron?: string;
  type?: string;
}

export async function getParlementairItems(filters?: ParlementairItemFilters): Promise<ParlementairItem[]> {
  return apiGet<ParlementairItem[]>('/api/parlementair/imports', filters as Record<string, string>);
}

export async function getParlementairItem(id: string): Promise<ParlementairItem> {
  return apiGet<ParlementairItem>(`/api/parlementair/imports/${id}`);
}

export async function triggerParlementairImport(): Promise<{ message: string; imported: number }> {
  return apiPost('/api/parlementair/imports/trigger');
}

export async function rejectParlementairItem(id: string): Promise<ParlementairItem> {
  return apiPut<ParlementairItem>(`/api/parlementair/imports/${id}/reject`);
}

export interface CompleteReviewData {
  eigenaar_id: string;
  tasks?: { title: string; description?: string; assignee_id?: string; deadline?: string }[];
}

export async function completeParlementairReview(id: string, data: CompleteReviewData): Promise<ParlementairItem> {
  return apiPost<ParlementairItem>(`/api/parlementair/imports/${id}/complete`, data);
}

export async function getReviewQueue(): Promise<ParlementairItem[]> {
  return apiGet<ParlementairItem[]>('/api/parlementair/review-queue');
}

export async function updateSuggestedEdge(id: string, data: { edge_type_id: string }): Promise<SuggestedEdge> {
  return apiPatch<SuggestedEdge>(`/api/parlementair/edges/${id}`, data);
}

export async function approveSuggestedEdge(id: string): Promise<SuggestedEdge> {
  return apiPut<SuggestedEdge>(`/api/parlementair/edges/${id}/approve`);
}

export async function rejectSuggestedEdge(id: string): Promise<SuggestedEdge> {
  return apiPut<SuggestedEdge>(`/api/parlementair/edges/${id}/reject`);
}

export async function resetSuggestedEdge(id: string): Promise<SuggestedEdge> {
  return apiPut<SuggestedEdge>(`/api/parlementair/edges/${id}/reset`);
}
