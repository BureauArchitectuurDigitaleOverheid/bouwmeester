import { apiGet } from './client';

export interface MentionSearchResult {
  id: string;
  label: string;
  type: string;
  subtitle?: string;
}

export interface MentionReference {
  source_type: string;
  source_id: string;
  source_title: string;
}

export function searchMentionables(q: string): Promise<MentionSearchResult[]> {
  return apiGet<MentionSearchResult[]>('/api/mentions/search', { q, limit: 10 });
}

export function getReferences(targetId: string): Promise<MentionReference[]> {
  return apiGet<MentionReference[]>(`/api/mentions/references/${targetId}`);
}
