import { useQuery } from '@tanstack/react-query';
import { getAankomendeDebatten, startDebat } from '@/api/debatten';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { DebatStartResult } from '@/types/debat';

export function useAankomendeDebatten() {
  return useQuery({
    queryKey: queryKeys.debatten.aankomend(),
    queryFn: getAankomendeDebatten,
    // The agenda of the Kamer does not change by the minute, and every fetch
    // is a call to the TK API.
    staleTime: 5 * 60 * 1000,
  });
}

export function useStartDebat() {
  return useMutationWithError<DebatStartResult, { activiteitId: string; teamId: string }>({
    mutationFn: ({ activiteitId, teamId }) => startDebat(activiteitId, teamId),
    errorMessage: 'Fout bij het opzetten van het kanaal',
    invalidateKeys: [queryKeys.debatten.all],
  });
}
