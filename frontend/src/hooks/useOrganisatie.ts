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
import { queryKeys } from '@/hooks/queryKeys';
import type { OrganisatieEenheidCreate, OrganisatieEenheidUpdate } from '@/types';

export function useOrganisatieTree(includeHistorisch = false) {
  return useQuery({
    queryKey: [...queryKeys.organisatie.tree(), { includeHistorisch }],
    queryFn: () => getOrganisatieTree(includeHistorisch),
  });
}

export function useOrganisatieFlat() {
  return useQuery({
    queryKey: queryKeys.organisatie.flat(),
    queryFn: getOrganisatieFlat,
  });
}

export function useOrganisatieEenheid(id: string | null) {
  return useQuery({
    queryKey: queryKeys.organisatie.detail(id),
    queryFn: () => getOrganisatieEenheid(id!),
    enabled: !!id,
  });
}

export function useOrganisatiePersonen(id: string | null) {
  return useQuery({
    queryKey: queryKeys.organisatie.personen(id),
    queryFn: () => getOrganisatiePersonen(id!),
    enabled: !!id,
  });
}

export function useOrganisatiePersonenRecursive(id: string | null) {
  return useQuery({
    queryKey: queryKeys.organisatie.personenRecursive(id),
    queryFn: () => getOrganisatiePersonenRecursive(id!),
    enabled: !!id,
  });
}

export function useCreateOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: (data: OrganisatieEenheidCreate) => createOrganisatieEenheid(data),
    errorMessage: 'Fout bij aanmaken eenheid',
    invalidateKeys: [queryKeys.organisatie.all],
  });
}

export function useUpdateOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: OrganisatieEenheidUpdate }) =>
      updateOrganisatieEenheid(id, data),
    errorMessage: 'Fout bij bijwerken eenheid',
    invalidateKeys: [queryKeys.organisatie.all],
  });
}

export function useDeleteOrganisatieEenheid() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteOrganisatieEenheid(id),
    errorMessage: 'Fout bij verwijderen eenheid',
    invalidateKeys: [queryKeys.organisatie.all],
  });
}

export function useManagedEenheden(personId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.organisatie.managedBy(personId),
    queryFn: () => getManagedEenheden(personId!),
    enabled: !!personId,
  });
}
