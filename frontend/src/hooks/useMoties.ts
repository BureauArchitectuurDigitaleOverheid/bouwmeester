import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

export function useTriggerMotieImport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => triggerMotieImport(),
    onError: (error) => {
      console.error('Fout bij importeren moties:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}

export function useRejectMotieImport() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => rejectMotieImport(id),
    onError: (error) => {
      console.error('Fout bij afwijzen motie:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}

export function useCompleteMotieReview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CompleteReviewData }) =>
      completeMotieReview(id, data),
    onError: (error) => {
      console.error('Fout bij afronden review:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
  });
}

export function useApproveSuggestedEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => approveSuggestedEdge(id),
    onError: (error) => {
      console.error('Fout bij goedkeuren relatie:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}

export function useRejectSuggestedEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => rejectSuggestedEdge(id),
    onError: (error) => {
      console.error('Fout bij afwijzen relatie:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}
