import { useQuery } from '@tanstack/react-query';
import {
  getSamenwerkingsverbanden,
  getSamenwerkingsverband,
  createSamenwerkingsverband,
  updateSamenwerkingsverband,
  deleteSamenwerkingsverband,
  listLeden,
  addLid,
  updateLid,
  removeLid,
  listForPerson,
} from '@/api/samenwerkingsverbanden';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type {
  SamenwerkingsverbandCreate,
  SamenwerkingsverbandLidCreate,
  SamenwerkingsverbandLidUpdate,
  SamenwerkingsverbandUpdate,
} from '@/types';

export function useSamenwerkingsverbanden(filters?: {
  search?: string;
  type?: string;
  actief?: boolean;
}) {
  return useQuery({
    queryKey: queryKeys.samenwerkingsverbanden.list(filters),
    queryFn: () => getSamenwerkingsverbanden(filters),
  });
}

export function useSamenwerkingsverband(id: string | null) {
  return useQuery({
    queryKey: queryKeys.samenwerkingsverbanden.detail(id),
    queryFn: () => getSamenwerkingsverband(id!),
    enabled: !!id,
  });
}

export function useCreateSamenwerkingsverband() {
  return useMutationWithError({
    mutationFn: (data: SamenwerkingsverbandCreate) => createSamenwerkingsverband(data),
    errorMessage: 'Fout bij aanmaken samenwerkingsverband',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}

export function useUpdateSamenwerkingsverband() {
  return useMutationWithError({
    mutationFn: ({ id, data }: { id: string; data: SamenwerkingsverbandUpdate }) =>
      updateSamenwerkingsverband(id, data),
    errorMessage: 'Fout bij bijwerken samenwerkingsverband',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}

export function useDeleteSamenwerkingsverband() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteSamenwerkingsverband(id),
    errorMessage: 'Fout bij verwijderen samenwerkingsverband',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}

export function useLeden(id: string | null, actief: boolean = true) {
  return useQuery({
    queryKey: queryKeys.samenwerkingsverbanden.leden(id, actief),
    queryFn: () => listLeden(id!, actief),
    enabled: !!id,
  });
}

export function useAddLid() {
  return useMutationWithError({
    mutationFn: ({ swvId, data }: { swvId: string; data: SamenwerkingsverbandLidCreate }) =>
      addLid(swvId, data),
    errorMessage: 'Fout bij toevoegen lid',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}

export function useUpdateLid() {
  return useMutationWithError({
    mutationFn: ({
      swvId,
      lidId,
      data,
    }: {
      swvId: string;
      lidId: string;
      data: SamenwerkingsverbandLidUpdate;
    }) => updateLid(swvId, lidId, data),
    errorMessage: 'Fout bij bijwerken lid',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}

export function useSamenwerkingsverbandenForPerson(
  personId: string | null,
  actief: boolean = true,
) {
  return useQuery({
    queryKey: queryKeys.samenwerkingsverbanden.forPerson(personId, actief),
    queryFn: () => listForPerson(personId!, actief),
    enabled: !!personId,
  });
}

export function useRemoveLid() {
  return useMutationWithError({
    mutationFn: ({ swvId, lidId }: { swvId: string; lidId: string }) =>
      removeLid(swvId, lidId),
    errorMessage: 'Fout bij verwijderen lid',
    invalidateKeys: [queryKeys.samenwerkingsverbanden.all],
  });
}
