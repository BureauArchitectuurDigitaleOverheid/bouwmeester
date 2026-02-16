import { useQuery } from '@tanstack/react-query';
import { getOpdrachten, getOpdracht, createOpdracht, updateOpdracht, deleteOpdracht, getNodeFinancieel, getNodeOpdrachten } from '@/api/opdrachten';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { OpdrachtCreate, OpdrachtUpdate, OpdrachtFilters } from '@/types';

export function useOpdrachten(filters?: OpdrachtFilters) {
  return useQuery({
    queryKey: queryKeys.opdrachten.list(filters),
    queryFn: () => getOpdrachten(filters),
  });
}

export function useOpdracht(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.opdrachten.detail(id),
    queryFn: () => getOpdracht(id!),
    enabled: !!id,
  });
}

export function useCreateOpdracht() {
  return useMutationWithError({
    mutationFn: (data: OpdrachtCreate) => createOpdracht(data),
    errorMessage: 'Fout bij aanmaken opdracht',
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.overzicht(undefined)],
  });
}

export function useUpdateOpdracht() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: OpdrachtUpdate }) => updateOpdracht(id, data),
    errorMessage: 'Fout bij bijwerken opdracht',
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.overzicht(undefined)],
  });
}

export function useDeleteOpdracht() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteOpdracht(id),
    errorMessage: 'Fout bij verwijderen opdracht',
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.overzicht(undefined)],
  });
}

export function useNodeFinancieel(nodeId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.financieel.overzicht(nodeId),
    queryFn: () => getNodeFinancieel(nodeId!),
    enabled: !!nodeId,
  });
}

export function useNodeOpdrachten(nodeId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.financieel.opdrachten(nodeId),
    queryFn: () => getNodeOpdrachten(nodeId!),
    enabled: !!nodeId,
  });
}
