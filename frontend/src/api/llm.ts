import { apiPost } from './client';

export interface TagSuggestionRequest {
  title: string;
  description?: string | null;
  node_type?: string;
}

export interface TagSuggestionResponse {
  matched_tags: string[];
  suggested_new_tags: string[];
  available: boolean;
}

export interface EdgeSuggestionItem {
  target_node_id: string;
  target_node_title: string;
  target_node_type: string;
  confidence: number;
  suggested_edge_type: string;
  reason: string;
}

export interface EdgeSuggestionResponse {
  suggestions: EdgeSuggestionItem[];
  available: boolean;
}

export interface SummarizeResponse {
  summary: string;
  available: boolean;
}

export function suggestTags(data: TagSuggestionRequest): Promise<TagSuggestionResponse> {
  return apiPost<TagSuggestionResponse>('/api/llm/suggest-tags', data);
}

export function suggestEdges(nodeId: string): Promise<EdgeSuggestionResponse> {
  return apiPost<EdgeSuggestionResponse>('/api/llm/suggest-edges', { node_id: nodeId });
}

export function summarizeText(text: string, maxWords = 100): Promise<SummarizeResponse> {
  return apiPost<SummarizeResponse>('/api/llm/summarize', { text, max_words: maxWords });
}
