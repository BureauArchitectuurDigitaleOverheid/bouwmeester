import { useQuery } from '@tanstack/react-query';
import {
  triggerFccSync,
  getFccSchema,
  getLastFccSync,
} from '@/api/fcc';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

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

export function useTriggerFccSync() {
  return useMutationWithError({
    mutationFn: () => triggerFccSync(),
    errorMessage: 'FCC synchronisatie mislukt',
    invalidateKeys: [
      queryKeys.fcc.syncLogs(),
      queryKeys.fcc.lastSync(),
      queryKeys.fcc.conflicts(),
      ['opdrachten'],
    ],
  });
}

export function useLastFccSync() {
  return useQuery({
    queryKey: queryKeys.fcc.lastSync(),
    queryFn: () => getLastFccSync(),
    retry: false,
    throwOnError: false,
  });
}
