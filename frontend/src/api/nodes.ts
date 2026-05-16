import { apiGet, apiPost, apiPut, apiDelete, BASE_URL, getCsrfToken } from './client';
import type { CorpusNode, CorpusNodeCreate, CorpusNodeUpdate, GraphViewResponse, NodeStakeholder, NodeTitleRecord, NodeStatusRecord, NodeType, NodeParlementairItem, NodeBronDetail, BijlageInfo } from '@/types';

export async function getNodes(nodeType?: NodeType, search?: string, limit?: number): Promise<CorpusNode[]> {
  return apiGet<CorpusNode[]>('/api/nodes', {
    node_type: nodeType,
    search: search || undefined,
    limit,
  });
}

export async function getNode(id: string): Promise<CorpusNode> {
  return apiGet<CorpusNode>(`/api/nodes/${id}`);
}

export async function createNode(data: CorpusNodeCreate): Promise<CorpusNode> {
  return apiPost<CorpusNode>('/api/nodes', data);
}

export async function updateNode(id: string, data: CorpusNodeUpdate, actorId?: string): Promise<CorpusNode> {
  const url = actorId ? `/api/nodes/${id}?actor_id=${actorId}` : `/api/nodes/${id}`;
  return apiPut<CorpusNode>(url, data);
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

export async function getNodeStakeholders(id: string): Promise<NodeStakeholder[]> {
  return apiGet<NodeStakeholder[]>(`/api/nodes/${id}/stakeholders`);
}

export async function addNodeStakeholder(
  nodeId: string,
  data: { person_id: string; rol: string },
): Promise<NodeStakeholder> {
  return apiPost<NodeStakeholder>(`/api/nodes/${nodeId}/stakeholders`, data);
}

export async function updateNodeStakeholder(
  nodeId: string,
  stakeholderId: string,
  data: { rol: string },
): Promise<NodeStakeholder> {
  return apiPut<NodeStakeholder>(`/api/nodes/${nodeId}/stakeholders/${stakeholderId}`, data);
}

export async function removeNodeStakeholder(
  nodeId: string,
  stakeholderId: string,
): Promise<void> {
  return apiDelete(`/api/nodes/${nodeId}/stakeholders/${stakeholderId}`);
}

export async function getNodeTitleHistory(id: string): Promise<NodeTitleRecord[]> {
  return apiGet<NodeTitleRecord[]>(`/api/nodes/${id}/history/titles`);
}

export async function getNodeStatusHistory(id: string): Promise<NodeStatusRecord[]> {
  return apiGet<NodeStatusRecord[]>(`/api/nodes/${id}/history/statuses`);
}

export async function getNodeParlementairItem(id: string): Promise<NodeParlementairItem | null> {
  return apiGet<NodeParlementairItem | null>(`/api/nodes/${id}/parlementair-item`);
}

// --- Bron detail ---

export async function getNodeBronDetail(id: string): Promise<NodeBronDetail | null> {
  return apiGet<NodeBronDetail | null>(`/api/nodes/${id}/bron-detail`);
}

export async function updateNodeBronDetail(id: string, data: Partial<NodeBronDetail>): Promise<NodeBronDetail> {
  return apiPut<NodeBronDetail>(`/api/nodes/${id}/bron-detail`, data);
}

// --- Bijlage ---

export async function getBijlageInfo(nodeId: string): Promise<BijlageInfo | null> {
  return apiGet<BijlageInfo | null>(`/api/nodes/${nodeId}/bijlage`);
}

export async function uploadBijlage(nodeId: string, file: File): Promise<BijlageInfo> {
  const formData = new FormData();
  formData.append('file', file);
  const url = `${BASE_URL}/api/nodes/${nodeId}/bijlage`;
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'X-CSRF-Token': getCsrfToken() },
    body: formData,
    credentials: 'include',
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Upload failed: ${response.status} ${text}`);
  }
  return response.json();
}

export async function deleteBijlage(nodeId: string): Promise<void> {
  return apiDelete(`/api/nodes/${nodeId}/bijlage`);
}

export function getBijlageDownloadUrl(nodeId: string): string {
  return `${BASE_URL}/api/nodes/${nodeId}/bijlage/download`;
}
