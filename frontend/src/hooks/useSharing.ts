import { useQuery } from '@tanstack/react-query';
import { apiGet, apiPost, apiDelete } from '@/api/client';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';

export interface SharingGrant {
  id: string;
  source_node_id?: string | null;
  source_eenheid_id?: string | null;
  source_eenheid_naam?: string | null;
  target_eenheid_id: string;
  target_eenheid_naam?: string | null;
  access_level: 'read' | 'edit';
  shared_by_id?: string | null;
  reason?: string | null;
  geldig_van: string;
  geldig_tot?: string | null;
  created_at: string;
}

export interface SharingGrantCreate {
  source_node_id?: string;
  source_eenheid_id?: string;
  target_eenheid_id: string;
  access_level: 'read' | 'edit';
  reason?: string;
  geldig_van?: string;
  geldig_tot?: string;
}

export function useSharing() {
  return useQuery({
    queryKey: queryKeys.admin.sharing(),
    queryFn: () => apiGet<SharingGrant[]>('/api/sharing'),
  });
}

export function useCreateSharing() {
  return useMutationWithError({
    mutationFn: (data: SharingGrantCreate) =>
      apiPost<SharingGrant>('/api/sharing', data),
    errorMessage: 'Fout bij aanmaken van deling',
    invalidateKeys: [queryKeys.admin.sharing()],
  });
}

export function useDeleteSharing() {
  return useMutationWithError({
    mutationFn: (id: string) => apiDelete(`/api/sharing/${id}`),
    errorMessage: 'Fout bij verwijderen van deling',
    invalidateKeys: [queryKeys.admin.sharing()],
  });
}
