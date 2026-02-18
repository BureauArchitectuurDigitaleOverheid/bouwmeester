import { apiPost, apiGet } from './client';
import type {
  TagSuggestionRequest,
  TagSuggestionResponse,
  GapAnalysisResponse,
  CorpusGapOverviewResponse,
  KompasGuidanceResponse,
} from '@/types';

export function suggestTags(data: TagSuggestionRequest): Promise<TagSuggestionResponse> {
  return apiPost<TagSuggestionResponse>('/api/llm/suggest-tags', data);
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
