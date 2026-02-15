import { apiGet } from './client';
import type { MentionSearchResult, MentionReference } from '@/types';

export function searchMentionables(q: string): Promise<MentionSearchResult[]> {
  return apiGet<MentionSearchResult[]>('/api/mentions/search', { q, limit: 10 });
}

export function getReferences(targetId: string): Promise<MentionReference[]> {
  return apiGet<MentionReference[]>(`/api/mentions/references/${targetId}`);
}
