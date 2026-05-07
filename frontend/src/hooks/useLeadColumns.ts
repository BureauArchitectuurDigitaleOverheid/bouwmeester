import { useQuery } from '@tanstack/react-query';
import {
  createLeadColumn,
  deleteLeadColumn,
  listLeadColumns,
  reorderLeadColumns,
  updateLeadColumn,
  type LeadColumnCreate,
  type LeadColumnUpdate,
} from '@/api/leadColumns';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import { DEFAULT_LEAD_COLUMNS, type LeadColumn } from '@/types';

/**
 * Geef de funnel-kolommen van een initiatief terug.
 *
 * Zonder `initiatiefId` valt de hook terug op de 7 default-kolommen, zodat
 * orphan-leads (geen initiatief) en de loading-flow van bv. de intake-dialog
 * meteen iets renderbaars hebben in plaats van een lege lijst.
 */
export function useLeadColumns(initiatiefId: string | undefined) {
  const query = useQuery({
    queryKey: queryKeys.leadColumns.list(initiatiefId),
    queryFn: () => listLeadColumns(initiatiefId as string),
    enabled: !!initiatiefId,
  });

  const columns: LeadColumn[] =
    initiatiefId && query.data ? query.data : DEFAULT_LEAD_COLUMNS;

  return {
    columns,
    isLoading: !!initiatiefId && query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
  };
}

export function useCreateLeadColumn(initiatiefId: string) {
  return useMutationWithError({
    mutationFn: (data: LeadColumnCreate) => createLeadColumn(initiatiefId, data),
    errorMessage: 'Fout bij aanmaken kolom',
    invalidateKeys: [queryKeys.leadColumns.list(initiatiefId)],
  });
}

export function useUpdateLeadColumn(initiatiefId: string) {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: LeadColumnUpdate }) =>
      updateLeadColumn(initiatiefId, id, data),
    errorMessage: 'Fout bij bijwerken kolom',
    invalidateKeys: [queryKeys.leadColumns.list(initiatiefId)],
  });
}

export function useDeleteLeadColumn(initiatiefId: string) {
  return useMutationWithError({
    mutationFn: ({ id, moveTo }: { id: string; moveTo?: string }) =>
      deleteLeadColumn(initiatiefId, id, moveTo),
    errorMessage: 'Fout bij verwijderen kolom',
    invalidateKeys: [
      queryKeys.leadColumns.list(initiatiefId),
      queryKeys.leads.lists(),
      queryKeys.leads.metrics(),
    ],
  });
}

export function useReorderLeadColumns(initiatiefId: string) {
  return useMutationWithError({
    mutationFn: (columnIds: string[]) =>
      reorderLeadColumns(initiatiefId, columnIds),
    errorMessage: 'Fout bij herordenen kolommen',
    invalidateKeys: [queryKeys.leadColumns.list(initiatiefId)],
  });
}
