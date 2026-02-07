import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Edge, EdgeCreate } from '@/types';

export interface EdgeFilters {
  from_node_id?: string;
  to_node_id?: string;
  edge_type_id?: string;
  node_id?: string;
}

export async function getEdges(filters?: EdgeFilters): Promise<Edge[]> {
  return apiGet<Edge[]>('/api/edges', filters as Record<string, string>);
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
