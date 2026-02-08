import { apiGet, apiPost, apiPut } from './client';
import type { MotieImport, SuggestedEdge } from '@/types';

export interface MotieImportFilters {
  status?: string;
  bron?: string;
}

export async function getMotieImports(filters?: MotieImportFilters): Promise<MotieImport[]> {
  return apiGet<MotieImport[]>('/api/moties/imports', filters as Record<string, string>);
}

export async function getMotieImport(id: string): Promise<MotieImport> {
  return apiGet<MotieImport>(`/api/moties/imports/${id}`);
}

export async function getMotieImportByNode(nodeId: string): Promise<MotieImport> {
  return apiGet<MotieImport>(`/api/moties/imports/by-node/${nodeId}`);
}

export async function triggerMotieImport(): Promise<{ message: string; imported: number }> {
  return apiPost('/api/moties/imports/trigger');
}

export async function rejectMotieImport(id: string): Promise<MotieImport> {
  return apiPut<MotieImport>(`/api/moties/imports/${id}/reject`);
}

export async function completeMotieReview(id: string): Promise<MotieImport> {
  return apiPost<MotieImport>(`/api/moties/imports/${id}/complete`);
}

export async function getReviewQueue(): Promise<MotieImport[]> {
  return apiGet<MotieImport[]>('/api/moties/review-queue');
}

export async function approveSuggestedEdge(id: string): Promise<SuggestedEdge> {
  return apiPut<SuggestedEdge>(`/api/moties/edges/${id}/approve`);
}

export async function rejectSuggestedEdge(id: string): Promise<SuggestedEdge> {
  return apiPut<SuggestedEdge>(`/api/moties/edges/${id}/reject`);
}
