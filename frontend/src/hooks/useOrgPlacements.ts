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

export function useUpdatePlacement() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: api.UpdatePlacementRequest }) =>
      api.updatePlacement(id, data),
    errorMessage: 'Fout bij wijzigen teamverzoek',
    invalidateKeys: [queryKeys.orgPlacements.all],
  });
}

export function useApprovePlacement() {
  return useMutationWithError({
    mutationFn: (id: string) => api.approvePlacement(id),
    errorMessage: 'Fout bij goedkeuren teamverzoek',
    // Approving places the person: org chart and people views change.
    invalidateKeys: [queryKeys.orgPlacements.all, queryKeys.organisatie.all, queryKeys.people.all],
  });
}

export function useDenyPlacement() {
  return useMutationWithError({
    mutationFn: (id: string) => api.denyPlacement(id),
    errorMessage: 'Fout bij afwijzen teamverzoek',
    invalidateKeys: [queryKeys.orgPlacements.all],
  });
}
