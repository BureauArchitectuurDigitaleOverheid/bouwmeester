import { apiGet, apiPost, apiPut, apiDelete } from './client';
import type { Tag, TagCreate, NodeTagResponse } from '@/types';

export async function getTags(params?: { tree?: boolean; search?: string }): Promise<Tag[]> {
  if (params?.tree) {
    return apiGet<Tag[]>('/api/tags/tree');
  }
  if (params?.search) {
    return apiGet<Tag[]>('/api/tags/search', { q: params.search });
  }
  return apiGet<Tag[]>('/api/tags');
}

export async function getTag(id: string): Promise<Tag> {
  return apiGet<Tag>(`/api/tags/${id}`);
}

export async function createTag(data: TagCreate): Promise<Tag> {
  return apiPost<Tag>('/api/tags', data);
}

export async function updateTag(id: string, data: Partial<TagCreate>): Promise<Tag> {
  return apiPut<Tag>(`/api/tags/${id}`, data);
}

export async function deleteTag(id: string): Promise<void> {
  return apiDelete(`/api/tags/${id}`);
}

export async function getNodeTags(nodeId: string): Promise<NodeTagResponse[]> {
  return apiGet<NodeTagResponse[]>(`/api/nodes/${nodeId}/tags`);
}

export async function addTagToNode(nodeId: string, data: { tag_id?: string; tag_name?: string }): Promise<NodeTagResponse> {
  return apiPost<NodeTagResponse>(`/api/nodes/${nodeId}/tags`, data);
}

export async function removeTagFromNode(nodeId: string, tagId: string): Promise<void> {
  return apiDelete(`/api/nodes/${nodeId}/tags/${tagId}`);
}
