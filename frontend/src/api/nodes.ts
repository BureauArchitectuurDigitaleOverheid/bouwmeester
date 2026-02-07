import { apiGet, apiPost, apiPatch, apiDelete } from './client';
import type { CorpusNode, CorpusNodeCreate, CorpusNodeUpdate, GraphViewResponse, NodeType } from '@/types';

export async function getNodes(nodeType?: NodeType): Promise<CorpusNode[]> {
  return apiGet<CorpusNode[]>('/api/nodes', {
    node_type: nodeType,
  });
}

export async function getNode(id: string): Promise<CorpusNode> {
  return apiGet<CorpusNode>(`/api/nodes/${id}`);
}

export async function createNode(data: CorpusNodeCreate): Promise<CorpusNode> {
  return apiPost<CorpusNode>('/api/nodes', data);
}

export async function updateNode(id: string, data: CorpusNodeUpdate): Promise<CorpusNode> {
  return apiPatch<CorpusNode>(`/api/nodes/${id}`, data);
}

export async function deleteNode(id: string): Promise<void> {
  return apiDelete(`/api/nodes/${id}`);
}

export async function getNodeNeighbors(id: string): Promise<CorpusNode[]> {
  return apiGet<CorpusNode[]>(`/api/nodes/${id}/neighbors`);
}

export async function getNodeGraph(id: string, depth?: number): Promise<GraphViewResponse> {
  return apiGet<GraphViewResponse>(`/api/nodes/${id}/graph`, { depth });
}
