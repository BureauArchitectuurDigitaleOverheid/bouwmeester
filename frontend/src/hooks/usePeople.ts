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
  addPersonEmail,
  removePersonEmail,
  setDefaultEmail,
  addPersonPhone,
  removePersonPhone,
  setDefaultPhone,
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
    invalidateKeys: [['people']],
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
    invalidateKeys: [['people']],
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
    invalidateKeys: [['people']],
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
    invalidateKeys: [['people']],
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
    invalidateKeys: [['people']],
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
    invalidateKeys: [['people']],
  });
}
