import { useQuery } from '@tanstack/react-query';
import { getOpdrachten, getOpdrachtenSummary, getOpdracht, createOpdracht, updateOpdracht, deleteOpdracht, addOpdrachtNodeKoppeling, removeOpdrachtNodeKoppeling, getNodeFinancieel, getNodeOpdrachten } from '@/api/opdrachten';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { OpdrachtCreate, OpdrachtUpdate, OpdrachtNodeCreate, OpdrachtFilters, OpdrachtenSummary } from '@/types';

export function useOpdrachten(filters?: OpdrachtFilters) {
  return useQuery({
    queryKey: queryKeys.opdrachten.list(filters),
    queryFn: () => getOpdrachten(filters),
  });
}

export function useOpdrachtenSummary(filters?: OpdrachtFilters) {
  return useQuery<OpdrachtenSummary>({
    queryKey: queryKeys.opdrachten.summary(filters),
    queryFn: () => getOpdrachtenSummary(filters),
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
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.all, queryKeys.tasks.lists()],
  });
}

export function useUpdateOpdracht() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: OpdrachtUpdate }) => updateOpdracht(id, data),
    errorMessage: 'Fout bij bijwerken opdracht',
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.all, queryKeys.tasks.lists()],
  });
}

export function useDeleteOpdracht() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteOpdracht(id),
    errorMessage: 'Fout bij verwijderen opdracht',
    invalidateKeys: [queryKeys.opdrachten.all, queryKeys.financieel.all],
  });
}

export function useAddOpdrachtNodeKoppeling() {
  return useMutationWithError({
    mutationFn: ({ opdrachtId, data }: { opdrachtId: string; data: OpdrachtNodeCreate }) =>
      addOpdrachtNodeKoppeling(opdrachtId, data),
    errorMessage: 'Fout bij toevoegen koppeling',
    invalidateKeys: [queryKeys.opdrachten.all],
  });
}

export function useRemoveOpdrachtNodeKoppeling() {
  return useMutationWithError({
    mutationFn: ({ opdrachtId, koppelingId }: { opdrachtId: string; koppelingId: string }) =>
      removeOpdrachtNodeKoppeling(opdrachtId, koppelingId),
    errorMessage: 'Fout bij verwijderen koppeling',
    invalidateKeys: [queryKeys.opdrachten.all],
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
