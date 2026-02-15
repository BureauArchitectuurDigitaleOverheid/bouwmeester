import { apiPost } from './client';
import type { TagSuggestionRequest, TagSuggestionResponse, EdgeSuggestionResponse, SummarizeResponse } from '@/types';

export function suggestTags(data: TagSuggestionRequest): Promise<TagSuggestionResponse> {
  return apiPost<TagSuggestionResponse>('/api/llm/suggest-tags', data);
}

export function suggestEdges(nodeId: string): Promise<EdgeSuggestionResponse> {
  return apiPost<EdgeSuggestionResponse>('/api/llm/suggest-edges', { node_id: nodeId });
}

export function summarizeText(text: string, maxWords = 100): Promise<SummarizeResponse> {
  return apiPost<SummarizeResponse>('/api/llm/summarize', { text, max_words: maxWords });
}
