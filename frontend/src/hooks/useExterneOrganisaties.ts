import { useQuery } from '@tanstack/react-query';
import { getExterneOrganisaties, getExterneOrganisatie, createExterneOrganisatie, updateExterneOrganisatie, deleteExterneOrganisatie } from '@/api/externe-organisaties';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { ExterneOrganisatieCreate, ExterneOrganisatieUpdate } from '@/types';

export function useExterneOrganisaties(params?: { type?: string; search?: string }) {
  return useQuery({
    queryKey: queryKeys.externeOrganisaties.list(params),
    queryFn: () => getExterneOrganisaties(params),
  });
}

export function useExterneOrganisatie(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.externeOrganisaties.detail(id),
    queryFn: () => getExterneOrganisatie(id!),
    enabled: !!id,
  });
}

export function useCreateExterneOrganisatie() {
  return useMutationWithError({
    mutationFn: (data: ExterneOrganisatieCreate) => createExterneOrganisatie(data),
    errorMessage: 'Fout bij aanmaken externe organisatie',
    invalidateKeys: [queryKeys.externeOrganisaties.all],
  });
}

export function useUpdateExterneOrganisatie() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: ExterneOrganisatieUpdate }) => updateExterneOrganisatie(id, data),
    errorMessage: 'Fout bij bijwerken externe organisatie',
    invalidateKeys: [queryKeys.externeOrganisaties.all],
  });
}

export function useDeleteExterneOrganisatie() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteExterneOrganisatie(id),
    errorMessage: 'Fout bij verwijderen externe organisatie',
    invalidateKeys: [queryKeys.externeOrganisaties.all],
  });
}
