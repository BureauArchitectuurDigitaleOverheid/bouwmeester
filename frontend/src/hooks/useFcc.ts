import { useQuery } from '@tanstack/react-query';
import {
  triggerFccSync,
  getFccSyncLogs,
  getFccSchema,
  getFccConflicts,
  resolveFccConflict,
  pushOpdrachtToFcc,
} from '@/api/fcc';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export function useFccSyncLogs(opdrachtId?: string) {
  return useQuery({
    queryKey: queryKeys.fcc.syncLogs(opdrachtId),
    queryFn: () => getFccSyncLogs(opdrachtId),
  });
}

export function useFccSchema() {
  return useQuery({
    queryKey: queryKeys.fcc.schema(),
    queryFn: () => getFccSchema(),
    retry: false,
    // Cache for 5 minutes — FCC config rarely changes
    staleTime: 5 * 60 * 1000,
    // Silently fail for users without fcc:sync permission
    throwOnError: false,
  });
}

export function useFccConflicts() {
  return useQuery({
    queryKey: queryKeys.fcc.conflicts(),
    queryFn: () => getFccConflicts(),
  });
}

export function useTriggerFccSync() {
  return useMutationWithError({
    mutationFn: () => triggerFccSync(),
    errorMessage: 'FCC synchronisatie mislukt',
    invalidateKeys: [
      queryKeys.fcc.syncLogs(),
      queryKeys.fcc.conflicts(),
      ['opdrachten'],
    ],
  });
}

export function useResolveFccConflict() {
  return useMutationWithError({
    mutationFn: ({
      opdrachtId,
      resolution,
    }: {
      opdrachtId: string;
      resolution: 'use_ours' | 'use_theirs';
    }) => resolveFccConflict(opdrachtId, resolution),
    errorMessage: 'Conflict oplossen mislukt',
    invalidateKeys: [
      queryKeys.fcc.conflicts(),
      queryKeys.fcc.syncLogs(),
      ['opdrachten'],
    ],
  });
}

export function usePushOpdrachtToFcc() {
  return useMutationWithError({
    mutationFn: (opdrachtId: string) => pushOpdrachtToFcc(opdrachtId),
    errorMessage: 'Push naar FCC mislukt',
    invalidateKeys: [
      queryKeys.fcc.syncLogs(),
      ['opdrachten'],
    ],
  });
}
