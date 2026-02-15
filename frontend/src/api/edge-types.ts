import { apiGet, apiPost, apiDelete } from './client';
import type { EdgeType, ValidEdgeTypesResponse, EdgeSchemaRule, EdgeSchemaRuleCreate } from '@/types';

export async function getEdgeTypes(): Promise<EdgeType[]> {
  return apiGet<EdgeType[]>('/api/edge-types');
}

export async function createEdgeType(data: Omit<EdgeType, 'id'>): Promise<EdgeType> {
  return apiPost<EdgeType>('/api/edge-types', data);
}

export async function getValidEdgeTypes(
  fromNodeType?: string,
  toNodeType?: string,
): Promise<ValidEdgeTypesResponse> {
  const params = new URLSearchParams();
  if (fromNodeType) params.set('from_node_type', fromNodeType);
  if (toNodeType) params.set('to_node_type', toNodeType);
  const qs = params.toString();
  return apiGet<ValidEdgeTypesResponse>(`/api/edge-types/valid${qs ? `?${qs}` : ''}`);
}

export async function getEdgeSchemaRules(): Promise<EdgeSchemaRule[]> {
  return apiGet<EdgeSchemaRule[]>('/api/edge-schema-rules');
}

export async function createEdgeSchemaRule(data: EdgeSchemaRuleCreate): Promise<EdgeSchemaRule> {
  return apiPost<EdgeSchemaRule>('/api/edge-schema-rules', data);
}

export async function deleteEdgeSchemaRule(id: string): Promise<void> {
  return apiDelete<void>(`/api/edge-schema-rules/${id}`);
}
