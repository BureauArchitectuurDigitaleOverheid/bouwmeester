import { useQuery } from '@tanstack/react-query';
import {
  getMotieImports,
  getMotieImport,
  triggerMotieImport,
  rejectMotieImport,
  completeMotieReview,
  getReviewQueue,
  approveSuggestedEdge,
  rejectSuggestedEdge,
} from '@/api/moties';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { MotieImportFilters, CompleteReviewData } from '@/api/moties';

export function useMotieImports(filters?: MotieImportFilters) {
  return useQuery({
    queryKey: ['motie-imports', filters],
    queryFn: () => getMotieImports(filters),
  });
}

export function useMotieImport(id: string) {
  return useQuery({
    queryKey: ['motie-imports', id],
    queryFn: () => getMotieImport(id),
    enabled: !!id,
  });
}

export function useReviewQueue() {
  return useQuery({
    queryKey: ['motie-review-queue'],
    queryFn: () => getReviewQueue(),
  });
}

const MOTIE_INVALIDATE_KEYS = [['motie-imports'], ['motie-review-queue']];

export function useTriggerMotieImport() {
  return useMutationWithError({
    mutationFn: () => triggerMotieImport(),
    errorMessage: 'Fout bij importeren moties',
    invalidateKeys: MOTIE_INVALIDATE_KEYS,
  });
}

export function useRejectMotieImport() {
  return useMutationWithError({
    mutationFn: (id: string) => rejectMotieImport(id),
    errorMessage: 'Fout bij afwijzen motie',
    invalidateKeys: MOTIE_INVALIDATE_KEYS,
  });
}

export function useCompleteMotieReview() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: CompleteReviewData }) =>
      completeMotieReview(id, data),
    errorMessage: 'Fout bij afronden review',
    invalidateKeys: [...MOTIE_INVALIDATE_KEYS, ['tasks', 'list'], ['nodes', 'list']],
  });
}

export function useApproveSuggestedEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => approveSuggestedEdge(id),
    errorMessage: 'Fout bij goedkeuren relatie',
    invalidateKeys: MOTIE_INVALIDATE_KEYS,
  });
}

export function useRejectSuggestedEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => rejectSuggestedEdge(id),
    errorMessage: 'Fout bij afwijzen relatie',
    invalidateKeys: MOTIE_INVALIDATE_KEYS,
  });
}
