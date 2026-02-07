import { apiGet } from './client';
import type { GraphViewResponse } from '@/types';

export async function getGraphView(nodeTypes?: string[], limit?: number): Promise<GraphViewResponse> {
  const params: Record<string, string | number | boolean | undefined> = {
    limit: limit ?? 200,
  };

  // The backend expects node_types as repeated query params;
  // we build a manual URL for array params below.
  if (nodeTypes && nodeTypes.length > 0) {
    const baseUrl = '/api/graph/search';
    const searchParams = new URLSearchParams();
    if (limit) searchParams.append('limit', String(limit));
    for (const nt of nodeTypes) {
      searchParams.append('node_types', nt);
    }
    const queryString = searchParams.toString();
    const url = queryString ? `${baseUrl}?${queryString}` : baseUrl;
    const response = await fetch(url, {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`API Error ${response.status}: ${response.statusText}`);
    }
    return response.json();
  }

  return apiGet<GraphViewResponse>('/api/graph/search', params);
}
