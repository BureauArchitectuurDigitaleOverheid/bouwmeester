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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}

export function useDeleteOrganisatieEenheid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteOrganisatieEenheid(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['organisatie'] });
    },
  });
}
