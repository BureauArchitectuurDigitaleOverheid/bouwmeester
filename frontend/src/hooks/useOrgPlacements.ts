import { useQuery } from '@tanstack/react-query';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import * as api from '@/api/orgPlacements';

export function usePendingPlacements() {
  return useQuery({
    queryKey: queryKeys.orgPlacements.pending(),
    queryFn: api.getPendingPlacements,
  });
}

export function useMyPlacementRequests() {
  return useQuery({
    queryKey: queryKeys.orgPlacements.myRequests(),
    queryFn: api.getMyPlacementRequests,
  });
}

export function useApprovePlacement() {
  return useMutationWithError({
    mutationFn: (id: string) => api.approvePlacement(id),
    errorMessage: 'Fout bij goedkeuren plaatsingsverzoek',
    invalidateKeys: [queryKeys.orgPlacements.all],
  });
}

export function useDenyPlacement() {
  return useMutationWithError({
    mutationFn: (id: string) => api.denyPlacement(id),
    errorMessage: 'Fout bij afwijzen plaatsingsverzoek',
    invalidateKeys: [queryKeys.orgPlacements.all],
  });
}
