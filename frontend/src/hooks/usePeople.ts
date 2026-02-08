import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPeople,
  createPerson,
  updatePerson,
  getPersonSummary,
  getPersonOrganisaties,
  addPersonOrganisatie,
  updatePersonOrganisatie,
  removePersonOrganisatie,
} from '@/api/people';
import type { PersonCreate } from '@/types';

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: getPeople,
  });
}

export function useCreatePerson() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PersonCreate) => createPerson(data),
    onError: (error) => {
      console.error('Fout bij aanmaken persoon:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PersonCreate> }) =>
      updatePerson(id, data),
    onError: (error) => {
      console.error('Fout bij bijwerken persoon:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      personId,
      data,
    }: {
      personId: string;
      data: { organisatie_eenheid_id: string; dienstverband?: string; start_datum: string };
    }) => addPersonOrganisatie(personId, data),
    onError: (error) => {
      console.error('Fout bij toevoegen plaatsing:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useUpdatePersonOrganisatie() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      personId,
      placementId,
      data,
    }: {
      personId: string;
      placementId: string;
      data: { dienstverband?: string; eind_datum?: string | null };
    }) => updatePersonOrganisatie(personId, placementId, data),
    onError: (error) => {
      console.error('Fout bij bijwerken plaatsing:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useRemovePersonOrganisatie() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      personId,
      placementId,
    }: {
      personId: string;
      placementId: string;
    }) => removePersonOrganisatie(personId, placementId),
    onError: (error) => {
      console.error('Fout bij verwijderen plaatsing:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}
