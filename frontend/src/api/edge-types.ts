import { apiGet, apiPost } from './client';
import type { EdgeType } from '@/types';

export async function getEdgeTypes(): Promise<EdgeType[]> {
  return apiGet<EdgeType[]>('/api/edge-types');
}

export async function createEdgeType(data: Omit<EdgeType, 'id'>): Promise<EdgeType> {
  return apiPost<EdgeType>('/api/edge-types', data);
}
