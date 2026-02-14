import { useQuery } from '@tanstack/react-query';
import {
  getParlementairItems,
  getParlementairItem,
  triggerParlementairImport,
  reprocessParlementairItems,
  rejectParlementairItem,
  reopenParlementairItem,
  completeParlementairReview,
  getReviewQueue,
  updateSuggestedEdge,
  approveSuggestedEdge,
  rejectSuggestedEdge,
  resetSuggestedEdge,
} from '@/api/parlementair';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { ParlementairItemFilters, CompleteReviewData, ReprocessResult } from '@/api/parlementair';

export function useParlementairItems(filters?: ParlementairItemFilters) {
  return useQuery({
    queryKey: ['parlementair-items', filters],
    queryFn: () => getParlementairItems(filters),
  });
}

export function useParlementairItem(id: string) {
  return useQuery({
    queryKey: ['parlementair-items', id],
    queryFn: () => getParlementairItem(id),
    enabled: !!id,
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ['parlementair-review-queue'],
    queryFn: () => getReviewQueue(),
  });
}

const PARLEMENTAIR_INVALIDATE_KEYS = [['parlementair-items'], ['parlementair-review-queue']];

export function useTriggerParlementairImport() {
  return useMutationWithError({
    mutationFn: () => triggerParlementairImport(),
    errorMessage: 'Fout bij importeren kamerstukken',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useReprocessParlementairItems(options?: {
  onSuccess?: (data: ReprocessResult) => void;
}) {
  return useMutationWithError({
    mutationFn: (itemType?: string) => reprocessParlementairItems(itemType),
    errorMessage: 'Fout bij herverwerken kamerstukken',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
    onSuccess: options?.onSuccess,
  });
}

export function useRejectParlementairItem() {
  return useMutationWithError({
    mutationFn: (id: string) => rejectParlementairItem(id),
    errorMessage: 'Fout bij afwijzen kamerstuk',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useReopenParlementairItem() {
  return useMutationWithError({
    mutationFn: (id: string) => reopenParlementairItem(id),
    errorMessage: 'Fout bij heropenen kamerstuk',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useCompleteParlementairReview() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: CompleteReviewData }) =>
      completeParlementairReview(id, data),
    errorMessage: 'Fout bij afronden review',
    invalidateKeys: [...PARLEMENTAIR_INVALIDATE_KEYS, ['tasks', 'list'], ['nodes', 'list']],
  });
}

export function useUpdateSuggestedEdge() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: { edge_type_id: string } }) =>
      updateSuggestedEdge(id, data),
    errorMessage: 'Fout bij bijwerken relatie',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useApproveSuggestedEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => approveSuggestedEdge(id),
    errorMessage: 'Fout bij goedkeuren relatie',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useRejectSuggestedEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => rejectSuggestedEdge(id),
    errorMessage: 'Fout bij afwijzen relatie',
    invalidateKeys: PARLEMENTAIR_INVALIDATE_KEYS,
  });
}

export function useResetSuggestedEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => resetSuggestedEdge(id),
    errorMessage: 'Fout bij ongedaan maken',
    invalidateKeys: [...PARLEMENTAIR_INVALIDATE_KEYS, ['edges']],
  });
}
