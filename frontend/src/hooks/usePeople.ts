import { useQuery } from '@tanstack/react-query';
import {
  getPeople,
  getPerson,
  createPerson,
  updatePerson,
  getPersonSummary,
  getPersonOrganisaties,
  addPersonOrganisatie,
  updatePersonOrganisatie,
  removePersonOrganisatie,
  searchPeople,
  rotateApiKey,
  addPersonEmail,
  removePersonEmail,
  setDefaultEmail,
  addPersonPhone,
  removePersonPhone,
  setDefaultPhone,
  getDuplicatePersons,
  mergePersons,
} from '@/api/people';
import { useDebounce } from '@/hooks/useDebounce';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { PersonCreate } from '@/types';

export function usePeople(options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: queryKeys.people.all,
    queryFn: getPeople,
    refetchInterval: options?.refetchInterval,
  });
}

export function usePerson(id: string | null) {
  return useQuery({
    queryKey: queryKeys.people.detail(id),
    queryFn: () => getPerson(id!),
    enabled: !!id,
  });
}

export function useCreatePerson() {
  return useMutationWithError({
    mutationFn: ({ force, ...data }: PersonCreate & { force?: boolean }) =>
      createPerson(data, force),
    errorMessage: 'Fout bij aanmaken persoon',
    invalidateKeys: [queryKeys.people.all, queryKeys.organisatie.all],
  });
}

export function usePersonSummary(id: string | null) {
  return useQuery({
    queryKey: queryKeys.people.summary(id),
    queryFn: () => getPersonSummary(id!),
    enabled: !!id,
  });
}

export function useUpdatePerson() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: Partial<PersonCreate> }) =>
      updatePerson(id, data),
    errorMessage: 'Fout bij bijwerken persoon',
    invalidateKeys: [queryKeys.people.all, queryKeys.organisatie.all],
  });
}

// Org placement hooks

export function usePersonOrganisaties(personId: string | null, actief = true) {
  return useQuery({
    queryKey: queryKeys.people.organisaties(personId, actief),
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
    errorMessage: 'Fout bij toevoegen team-indeling',
    invalidateKeys: [queryKeys.people.all, queryKeys.organisatie.all],
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
    errorMessage: 'Fout bij bijwerken team-indeling',
    invalidateKeys: [queryKeys.people.all, queryKeys.organisatie.all],
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
    errorMessage: 'Fout bij verwijderen team-indeling',
    invalidateKeys: [queryKeys.people.all, queryKeys.organisatie.all],
  });
}

export function useSearchPeople(query: string) {
  const debouncedQuery = useDebounce(query, 300);
  return useQuery({
    queryKey: queryKeys.people.search(debouncedQuery),
    queryFn: () => searchPeople(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
  });
}

// API key hooks

export function useRotateApiKey() {
  return useMutationWithError({
    mutationFn: (personId: string) => rotateApiKey(personId),
    errorMessage: 'Fout bij roteren API key',
    invalidateKeys: [queryKeys.people.all],
  });
}

// Email hooks

export function useAddPersonEmail() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      data,
    }: {
      personId: string;
      data: { email: string; is_default?: boolean };
    }) => addPersonEmail(personId, data),
    errorMessage: 'Fout bij toevoegen e-mail',
    invalidateKeys: [queryKeys.people.all],
  });
}

export function useRemovePersonEmail() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      emailId,
    }: {
      personId: string;
      emailId: string;
    }) => removePersonEmail(personId, emailId),
    errorMessage: 'Fout bij verwijderen e-mail',
    invalidateKeys: [queryKeys.people.all],
  });
}

export function useSetDefaultEmail() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      emailId,
    }: {
      personId: string;
      emailId: string;
    }) => setDefaultEmail(personId, emailId),
    errorMessage: 'Fout bij instellen standaard e-mail',
    invalidateKeys: [queryKeys.people.all],
  });
}

// Phone hooks

export function useAddPersonPhone() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      data,
    }: {
      personId: string;
      data: { phone_number: string; label: string; is_default?: boolean };
    }) => addPersonPhone(personId, data),
    errorMessage: 'Fout bij toevoegen telefoon',
    invalidateKeys: [queryKeys.people.all],
  });
}

export function useRemovePersonPhone() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      phoneId,
    }: {
      personId: string;
      phoneId: string;
    }) => removePersonPhone(personId, phoneId),
    errorMessage: 'Fout bij verwijderen telefoon',
    invalidateKeys: [queryKeys.people.all],
  });
}

export function useSetDefaultPhone() {
  return useMutationWithError({
    mutationFn: ({
      personId,
      phoneId,
    }: {
      personId: string;
      phoneId: string;
    }) => setDefaultPhone(personId, phoneId),
    errorMessage: 'Fout bij instellen standaard telefoon',
    invalidateKeys: [queryKeys.people.all],
  });
}

// Duplicate detection & merge

export function useDuplicatePersons() {
  return useQuery({
    queryKey: queryKeys.people.duplicates,
    queryFn: getDuplicatePersons,
  });
}

export function useMergePersons() {
  return useMutationWithError({
    mutationFn: ({ sourceIds, targetId }: { sourceIds: string[]; targetId: string }) =>
      mergePersons(sourceIds, targetId),
    errorMessage: 'Fout bij samenvoegen personen',
    invalidateKeys: [queryKeys.people.all, queryKeys.people.duplicates],
  });
}
