import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: OrganisatieEenheidCreate) => createOrganisatieEenheid(data),
    onError: (error) => {
      console.error('Fout bij aanmaken eenheid:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useUpdateOrganisatieEenheid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: OrganisatieEenheidUpdate }) =>
      updateOrganisatieEenheid(id, data),
    onError: (error) => {
      console.error('Fout bij bijwerken eenheid:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useDeleteOrganisatieEenheid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrganisatieEenheid(id),
    onError: (error) => {
      console.error('Fout bij verwijderen eenheid:', error);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useManagedEenheden(personId: string | undefined) {
  return useQuery({
    queryKey: ['organisatie', 'managed-by', personId],
    queryFn: () => getManagedEenheden(personId!),
    enabled: !!personId,
  });
}
