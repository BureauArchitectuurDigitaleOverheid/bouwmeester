import { apiGet } from './client';
import type { MentionReference } from '@/types';

export function getReferences(targetId: string): Promise<MentionReference[]> {
  return apiGet<MentionReference[]>(`/api/mentions/references/${targetId}`);
}
