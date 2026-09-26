import { useMemo } from 'react';
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
import { CHANGES_RIGHTS, useCanEach } from '@/hooks/useCan';

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
    meta: CHANGES_RIGHTS,
    mutationFn: (data: OrganisatieEenheidCreate) => createOrganisatieEenheid(data),
    errorMessage: 'Fout bij aanmaken eenheid',
    invalidateKeys: [queryKeys.organisatie.all],
  });
}

export function useUpdateOrganisatieEenheid() {
  return useMutationWithError({
    meta: CHANGES_RIGHTS,
    mutationFn: ({ id, data }: { id: string; data: OrganisatieEenheidUpdate }) =>
      updateOrganisatieEenheid(id, data),
    errorMessage: 'Fout bij bijwerken eenheid',
    invalidateKeys: [queryKeys.organisatie.all],
  });
}

export function useDeleteOrganisatieEenheid() {
  return useMutationWithError({
    meta: CHANGES_RIGHTS,
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

/**
 * The eenheden (flat list order) on which the backend allows `action`, such
 * as `org:manage` for module toggles and sharing. One batched question per
 * eenheid: a role on an eenheid applies below it, so the frontend knows no
 * smaller candidate set.
 */
export function useEenhedenAllowed(action: string) {
  const { data: eenheden, isLoading } = useOrganisatieFlat();
  const questions = useMemo(
    () => (eenheden ?? []).map((e) => ({ type: 'organisatie_eenheid' as const, id: e.id })),
    [eenheden],
  );
  const decisions = useCanEach(action, questions);
  return {
    eenheden: (eenheden ?? []).filter((_, i) => decisions.allowed[i]),
    isLoading: isLoading || decisions.isLoading,
  };
}
