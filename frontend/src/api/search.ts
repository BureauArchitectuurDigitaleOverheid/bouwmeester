import { apiGet } from './client';
import type { SearchResponse, SearchResultType } from '@/types';

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
