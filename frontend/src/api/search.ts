import { apiGet } from './client';
import type { SearchResponse, NodeType } from '@/types';

export async function search(query: string, nodeTypes?: NodeType[]): Promise<SearchResponse> {
  const params: Record<string, string> = { q: query };
  if (nodeTypes && nodeTypes.length > 0) {
    params.node_types = nodeTypes.join(',');
  }
  return apiGet<SearchResponse>('/api/search', params);
}
