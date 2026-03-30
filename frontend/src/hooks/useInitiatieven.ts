import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getInitiatieven,
  getInitiatief,
  createInitiatief,
  updateInitiatief,
  deleteInitiatief,
  addInitiatiefMember,
  removeInitiatiefMember,
  updateInitiatiefMemberRole,
  addInitiatiefEenheid,
  removeInitiatiefEenheid,
  updateInitiatiefEenheidRol,
  getInitiatievenForEenheid,
} from '@/api/initiatieven';
import { queryKeys } from '@/hooks/queryKeys';
import type { InitiatiefCreate, InitiatiefUpdate } from '@/types';

export function useInitiatieven(params?: { search?: string }) {
  return useQuery({
    queryKey: queryKeys.initiatieven.list(params),
    queryFn: () => getInitiatieven(params),
  });
}

export function useInitiatief(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.initiatieven.detail(id),
    queryFn: () => getInitiatief(id!),
    enabled: !!id,
  });
}

export function useCreateInitiatief() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: InitiatiefCreate) => createInitiatief(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useUpdateInitiatief() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: InitiatiefUpdate }) =>
      updateInitiatief(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useDeleteInitiatief() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteInitiatief(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useAddInitiatiefMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      personId,
      rol,
    }: {
      initiatiefId: string;
      personId: string;
      rol?: string;
    }) => addInitiatiefMember(initiatiefId, personId, rol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useRemoveInitiatiefMember() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      personId,
    }: {
      initiatiefId: string;
      personId: string;
    }) => removeInitiatiefMember(initiatiefId, personId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useUpdateInitiatiefMemberRole() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      personId,
      rol,
    }: {
      initiatiefId: string;
      personId: string;
      rol: string;
    }) => updateInitiatiefMemberRole(initiatiefId, personId, rol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
    },
  });
}

export function useAddInitiatiefEenheid() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      eenheidId,
    }: {
      initiatiefId: string;
      eenheidId: string;
    }) => addInitiatiefEenheid(initiatiefId, eenheidId),
    onSuccess: (_data, { eenheidId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
      qc.invalidateQueries({ queryKey: ['initiatieven-for-eenheid', eenheidId] });
    },
  });
}

export function useRemoveInitiatiefEenheid() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      eenheidId,
    }: {
      initiatiefId: string;
      eenheidId: string;
    }) => removeInitiatiefEenheid(initiatiefId, eenheidId),
    onSuccess: (_data, { eenheidId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
      qc.invalidateQueries({ queryKey: ['initiatieven-for-eenheid', eenheidId] });
    },
  });
}

export function useUpdateInitiatiefEenheidRol() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      initiatiefId,
      eenheidId,
      rol,
    }: {
      initiatiefId: string;
      eenheidId: string;
      rol: string;
    }) => updateInitiatiefEenheidRol(initiatiefId, eenheidId, rol),
    onSuccess: (_data, { eenheidId }) => {
      qc.invalidateQueries({ queryKey: queryKeys.initiatieven.all });
      qc.invalidateQueries({ queryKey: ['initiatieven-for-eenheid', eenheidId] });
    },
  });
}

export function useInitiatievenForEenheid(eenheidId: string | null) {
  return useQuery({
    queryKey: ['initiatieven-for-eenheid', eenheidId],
    queryFn: () => getInitiatievenForEenheid(eenheidId!),
    enabled: !!eenheidId,
  });
}
