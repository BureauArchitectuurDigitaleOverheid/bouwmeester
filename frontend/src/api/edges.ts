import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Edge, EdgeCreate, EdgeFilters } from '@/types';

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
