import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getPeople, createPerson, updatePerson, getPersonSummary } from '@/api/people';
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['people'] });
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}
