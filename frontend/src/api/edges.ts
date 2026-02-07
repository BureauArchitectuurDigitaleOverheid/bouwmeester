import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Edge, EdgeCreate, EdgeResponse } from '@/types';

export interface EdgeFilters {
  source_id?: string;
  target_id?: string;
  edge_type?: string;
  node_id?: string;
}

export async function getEdges(filters?: EdgeFilters): Promise<EdgeResponse> {
  return apiGet<EdgeResponse>('/api/edges', filters as Record<string, string>);
}

export async function createEdge(data: EdgeCreate): Promise<Edge> {
  return apiPost<Edge>('/api/edges', data);
}

export async function updateEdge(id: string, data: Partial<EdgeCreate>): Promise<Edge> {
  return apiPut<Edge>(`/api/edges/${id}`, data);
}

export async function deleteEdge(id: string): Promise<void> {
  return apiDelete(`/api/edges/${id}`);
}
