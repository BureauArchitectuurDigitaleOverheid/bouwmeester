import { apiGet } from './client';
import type { Person } from '@/types';

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

export function searchPeople(q: string): Promise<Person[]> {
  return apiGet<Person[]>('/api/people/search', { q, limit: 10 });
}

export function searchMentionables(q: string): Promise<MentionSearchResult[]> {
  return apiGet<MentionSearchResult[]>('/api/mentions/search', { q, limit: 10 });
}

export function getReferences(targetId: string): Promise<MentionReference[]> {
  return apiGet<MentionReference[]>(`/api/mentions/references/${targetId}`);
}
