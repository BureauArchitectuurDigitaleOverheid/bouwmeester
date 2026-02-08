import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getNodes, getNode, createNode, updateNode, deleteNode,
  getNodeNeighbors, getNodeStakeholders, addNodeStakeholder,
  updateNodeStakeholder, removeNodeStakeholder, getNodeMotieImport,
} from '@/api/nodes';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { CorpusNodeCreate, CorpusNodeUpdate, NodeType } from '@/types';

export function useNodes(nodeType?: NodeType) {
  return useQuery({
    queryKey: ['nodes', nodeType],
    queryFn: () => getNodes(nodeType),
  });
}

export function useNode(id: string | undefined) {
  return useQuery({
    queryKey: ['nodes', id],
    queryFn: () => getNode(id!),
    enabled: !!id,
  });
}

export function useCreateNode() {
  return useMutationWithError({
    mutationFn: (data: CorpusNodeCreate) => createNode(data),
    errorMessage: 'Fout bij aanmaken node',
    invalidateKeys: [['nodes'], ['graph']],
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CorpusNodeUpdate }) => updateNode(id, data),
    onError: (error: Error) => {
      console.error('Fout bij bijwerken node:', error);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['nodes', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
  });
}

export function useDeleteNode() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteNode(id),
    errorMessage: 'Fout bij verwijderen node',
    invalidateKeys: [['nodes']],
  });
}

export function useNodeNeighbors(id: string | undefined) {
  return useQuery({
    queryKey: ['nodes', id, 'neighbors'],
    queryFn: () => getNodeNeighbors(id!),
    enabled: !!id,
  });
}

export function useNodeStakeholders(id: string | undefined) {
  return useQuery({
    queryKey: ['nodes', id, 'stakeholders'],
    queryFn: () => getNodeStakeholders(id!),
    enabled: !!id,
  });
}

export function useAddNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { person_id: string; rol: string } }) =>
      addNodeStakeholder(nodeId, data),
    onError: (error: Error) => {
      console.error('Fout bij toevoegen stakeholder:', error);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['nodes', variables.nodeId, 'stakeholders'] });
    },
  });
}

export function useUpdateNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ nodeId, stakeholderId, data }: { nodeId: string; stakeholderId: string; data: { rol: string } }) =>
      updateNodeStakeholder(nodeId, stakeholderId, data),
    onError: (error: Error) => {
      console.error('Fout bij bijwerken stakeholder:', error);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['nodes', variables.nodeId, 'stakeholders'] });
    },
  });
}

export function useRemoveNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ nodeId, stakeholderId }: { nodeId: string; stakeholderId: string }) =>
      removeNodeStakeholder(nodeId, stakeholderId),
    onError: (error: Error) => {
      console.error('Fout bij verwijderen stakeholder:', error);
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['nodes', variables.nodeId, 'stakeholders'] });
    },
  });
}

export function useNodeMotieImport(id: string | undefined, nodeType?: string) {
  return useQuery({
    queryKey: ['nodes', id, 'motie-import'],
    queryFn: () => getNodeMotieImport(id!),
    enabled: !!id && nodeType === 'politieke_input',
  });
}
