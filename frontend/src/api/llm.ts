import { apiPost, apiGet } from './client';
import type {
  TagSuggestionRequest,
  TagSuggestionResponse,
  EdgeSuggestionResponse,
  SummarizeResponse,
  TaskSuggestionResponse,
  GapAnalysisResponse,
  CorpusGapOverviewResponse,
  KompasGuidanceResponse,
} from '@/types';

export function suggestTags(data: TagSuggestionRequest): Promise<TagSuggestionResponse> {
  return apiPost<TagSuggestionResponse>('/api/llm/suggest-tags', data);
}

export function suggestEdges(nodeId: string): Promise<EdgeSuggestionResponse> {
  return apiPost<EdgeSuggestionResponse>('/api/llm/suggest-edges', { node_id: nodeId });
}

export function summarizeText(text: string, maxWords = 100): Promise<SummarizeResponse> {
  return apiPost<SummarizeResponse>('/api/llm/summarize', { text, max_words: maxWords });
}

export function suggestTask(
  nodeTitle: string,
  nodeDescription?: string,
  nodeType = 'dossier',
): Promise<TaskSuggestionResponse> {
  return apiPost<TaskSuggestionResponse>('/api/llm/suggest-task', {
    node_title: nodeTitle,
    node_description: nodeDescription,
    node_type: nodeType,
  });
}

export function analyzeGaps(dossierId: string): Promise<GapAnalysisResponse> {
  return apiPost<GapAnalysisResponse>('/api/llm/gap-analysis', { dossier_id: dossierId });
}

export function getCorpusGapOverview(): Promise<CorpusGapOverviewResponse> {
  return apiGet<CorpusGapOverviewResponse>('/api/llm/corpus-gaps');
}

export function suggestKompasLinks(
  dossierId: string,
  stepNodeTypes: string[],
  stepDescription = '',
): Promise<KompasGuidanceResponse> {
  return apiPost<KompasGuidanceResponse>('/api/llm/kompas-guidance', {
    dossier_id: dossierId,
    step_node_types: stepNodeTypes,
    step_description: stepDescription,
  });
}
