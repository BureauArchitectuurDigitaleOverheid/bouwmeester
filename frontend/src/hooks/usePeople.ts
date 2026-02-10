import { useQuery } from '@tanstack/react-query';
import {
  getPeople,
  createPerson,
  updatePerson,
  getPersonSummary,
  getPersonOrganisaties,
  addPersonOrganisatie,
  updatePersonOrganisatie,
  removePersonOrganisatie,
  searchPeople,
} from '@/api/people';
import { useDebounce } from '@/hooks/useDebounce';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { PersonCreate } from '@/types';

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: getPeople,
  });
}

export function useCreatePerson() {
  return useMutationWithError({
    mutationFn: (data: PersonCreate) => createPerson(data),
    errorMessage: 'Fout bij aanmaken persoon',
    invalidateKeys: [['people'], ['organisatie']],
  });
}

export function usePersonSummary(id: string | null) {
  return useQuery({
    queryKey: ['people', id, 'summary'],
    queryFn: () => getPersonSummary(id!),
    enabled: !!id,
  });
}

export function useUpdatePerson() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: Partial<PersonCreate> }) =>
      updatePerson(id, data),
    errorMessage: 'Fout bij bijwerken persoon',
    invalidateKeys: [['people'], ['organisatie']],
  });
}

// Org placement hooks

export function usePersonOrganisaties(personId: string | null, actief = true) {
  return useQuery({
    queryKey: ['people', personId, 'organisaties', { actief }],
    queryFn: () => getPersonOrganisaties(personId!, actief),
    enabled: !!personId,
  });
}

export function useAddPersonOrganisatie() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      data,
    }: {
      personId: string;
      data: { organisatie_eenheid_id: string; dienstverband?: string; start_datum: string };
    }) => addPersonOrganisatie(personId, data),
    errorMessage: 'Fout bij toevoegen plaatsing',
    invalidateKeys: [['people'], ['organisatie']],
  });
}

export function useUpdatePersonOrganisatie() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      placementId,
      data,
    }: {
      personId: string;
      placementId: string;
      data: { dienstverband?: string; eind_datum?: string | null };
    }) => updatePersonOrganisatie(personId, placementId, data),
    errorMessage: 'Fout bij bijwerken plaatsing',
    invalidateKeys: [['people'], ['organisatie']],
  });
}

export function useRemovePersonOrganisatie() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      placementId,
    }: {
      personId: string;
      placementId: string;
    }) => removePersonOrganisatie(personId, placementId),
    errorMessage: 'Fout bij verwijderen plaatsing',
    invalidateKeys: [['people'], ['organisatie']],
  });
}

export function useSearchPeople(query: string) {
  const debouncedQuery = useDebounce(query, 300);
  return useQuery({
    queryKey: ['people', 'search', debouncedQuery],
    queryFn: () => searchPeople(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
  });
}
