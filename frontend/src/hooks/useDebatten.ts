import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import {
  getAankomendeDebatten,
  getDebatAankondigingen,
  getGevolgdeDebatten,
  hervatDebat,
  kondigDebatAan,
  startDebat,
  stopDebat,
  verwijderDebatAankondiging,
} from '@/api/debatten';
import { volgendeOffset } from '@/pages/debatten';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { DebatAankondiging, DebatStartResult, DebatVolgenResult } from '@/types/debat';

export function useAankomendeDebatten() {
  return useQuery({
    queryKey: queryKeys.debatten.aankomend(),
    queryFn: getAankomendeDebatten,
    // What is on right now does change by the minute, so the list refreshes
    // itself while the page is in front. React Query keeps showing the list
    // it has while the next one is on its way, so nothing blinks. The backend
    // reads Debat Direct at most once per half minute, whoever asks.
    refetchInterval: 60 * 1000,
    staleTime: 30 * 1000,
  });
}

const GEVOLGD_PAGE = 20;

/**
 * The debates that were followed and are over, a page at a time.
 *
 * No interval: what is over does not change by the minute. A start, a stop
 * or a resume invalidates it along with the upcoming list.
 */
export function useGevolgdeDebatten() {
  return useInfiniteQuery({
    queryKey: queryKeys.debatten.gevolgd(),
    queryFn: ({ pageParam }) => getGevolgdeDebatten(GEVOLGD_PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (_last, pages) => volgendeOffset(pages),
    staleTime: 60 * 1000,
  });
}

export function useStartDebat() {
  return useMutationWithError<DebatStartResult, { activiteitId: string; teamId: string }>({
    mutationFn: ({ activiteitId, teamId }) => startDebat(activiteitId, teamId),
    errorMessage: 'Fout bij het opzetten van het kanaal',
    invalidateKeys: [queryKeys.debatten.all],
  });
}

export function useStopDebat() {
  return useMutationWithError<DebatVolgenResult, { sessieId: string }>({
    mutationFn: ({ sessieId }) => stopDebat(sessieId),
    errorMessage: 'Fout bij het stoppen met volgen',
    invalidateKeys: [queryKeys.debatten.all],
  });
}

export function useHervatDebat() {
  return useMutationWithError<DebatVolgenResult, { sessieId: string }>({
    mutationFn: ({ sessieId }) => hervatDebat(sessieId),
    errorMessage: 'Fout bij het hervatten van het volgen',
    invalidateKeys: [queryKeys.debatten.all],
  });
}

/**
 * The agenda of the Kamer, for picking a debate to announce.
 *
 * The same list as the Debatten page, under the same key, but read only
 * while someone is searching and not refreshed by the minute: what is
 * running right now does not matter for choosing a debate of next week.
 */
export function useDebatAgenda(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.debatten.aankomend(),
    queryFn: getAankomendeDebatten,
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useDebatAankondigingen(initiatiefId: string) {
  return useQuery({
    queryKey: queryKeys.initiatieven.debatten(initiatiefId),
    queryFn: () => getDebatAankondigingen(initiatiefId),
  });
}

export function useKondigDebatAan(initiatiefId: string) {
  return useMutationWithError<DebatAankondiging, { activiteitId: string }>({
    mutationFn: ({ activiteitId }) => kondigDebatAan(initiatiefId, activiteitId),
    errorMessage: 'Aankondigen is niet gelukt',
    // Also the agenda: the Debatten page says per debate which initiatieven
    // it was announced for.
    invalidateKeys: [queryKeys.initiatieven.debatten(initiatiefId), queryKeys.debatten.all],
  });
}

export function useVerwijderDebatAankondiging(initiatiefId: string) {
  return useMutationWithError<void, { aankondigingId: string }>({
    mutationFn: ({ aankondigingId }) => verwijderDebatAankondiging(initiatiefId, aankondigingId),
    errorMessage: 'Van de lijst halen is niet gelukt',
    // Also the agenda: the Debatten page says per debate which initiatieven
    // it was announced for.
    invalidateKeys: [queryKeys.initiatieven.debatten(initiatiefId), queryKeys.debatten.all],
  });
}
