import { apiGet } from './client';
import type { SearchResponse, SearchResultType, SimilarNodesResponse } from '@/types';

export async function search(
  query: string,
  resultTypes?: SearchResultType[],
): Promise<SearchResponse> {
  const params: Record<string, string> = { q: query };
  if (resultTypes && resultTypes.length > 0) {
    params.result_types = resultTypes.join(',');
  }
  return apiGet<SearchResponse>('/api/search', params);
}

export async function findSimilarNodes(
  title: string,
  excludeId?: string,
): Promise<SimilarNodesResponse> {
  const params: Record<string, string> = { title };
  if (excludeId) params.exclude_id = excludeId;
  return apiGet<SimilarNodesResponse>('/api/search/similar-nodes', params);
}
