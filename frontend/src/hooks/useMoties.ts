import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getMotieImports,
  getMotieImport,
  getMotieImportByNode,
  triggerMotieImport,
  rejectMotieImport,
  completeMotieReview,
  getReviewQueue,
  approveSuggestedEdge,
  rejectSuggestedEdge,
} from '@/api/moties';
import type { MotieImportFilters } from '@/api/moties';

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

export function useMotieImportByNode(nodeId: string | null | undefined) {
  return useQuery({
    queryKey: ['motie-imports', 'by-node', nodeId],
    queryFn: () => getMotieImportByNode(nodeId!),
    enabled: !!nodeId,
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}

export function useCompleteMotieReview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => completeMotieReview(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}

export function useApproveSuggestedEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => approveSuggestedEdge(id),
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['motie-imports'] });
      queryClient.invalidateQueries({ queryKey: ['motie-review-queue'] });
    },
  });
}
