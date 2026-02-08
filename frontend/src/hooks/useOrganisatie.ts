import { useQuery } from '@tanstack/react-query';
import {
  getOrganisatieTree,
  getOrganisatieFlat,
  getOrganisatieEenheid,
  createOrganisatieEenheid,
  updateOrganisatieEenheid,
  deleteOrganisatieEenheid,
  getOrganisatiePersonen,
  getOrganisatiePersonenRecursive,
  getManagedEenheden,
} from '@/api/organisatie';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { OrganisatieEenheidCreate, OrganisatieEenheidUpdate } from '@/types';

export function useOrganisatieTree() {
  return useQuery({
    queryKey: ['organisatie', 'tree'],
    queryFn: getOrganisatieTree,
  });
}

export function useOrganisatieFlat() {
  return useQuery({
    queryKey: ['organisatie', 'flat'],
    queryFn: getOrganisatieFlat,
  });
}

export function useOrganisatieEenheid(id: string | null) {
  return useQuery({
    queryKey: ['organisatie', id],
    queryFn: () => getOrganisatieEenheid(id!),
    enabled: !!id,
  });
}

export function useOrganisatiePersonen(id: string | null) {
  return useQuery({
    queryKey: ['organisatie', id, 'personen'],
    queryFn: () => getOrganisatiePersonen(id!),
    enabled: !!id,
  });
}

export function useOrganisatiePersonenRecursive(id: string | null) {
  return useQuery({
    queryKey: ['organisatie', id, 'personen', 'recursive'],
    queryFn: () => getOrganisatiePersonenRecursive(id!),
    enabled: !!id,
  });
}

export function useCreateOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: (data: OrganisatieEenheidCreate) => createOrganisatieEenheid(data),
    errorMessage: 'Fout bij aanmaken eenheid',
    invalidateKeys: [['organisatie']],
  });
}

export function useUpdateOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: OrganisatieEenheidUpdate }) =>
      updateOrganisatieEenheid(id, data),
    errorMessage: 'Fout bij bijwerken eenheid',
    invalidateKeys: [['organisatie']],
  });
}

export function useDeleteOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteOrganisatieEenheid(id),
    errorMessage: 'Fout bij verwijderen eenheid',
    invalidateKeys: [['organisatie']],
  });
}

export function useManagedEenheden(personId: string | undefined) {
  return useQuery({
    queryKey: ['organisatie', 'managed-by', personId],
    queryFn: () => getManagedEenheden(personId!),
    enabled: !!personId,
  });
}
