import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getNodes, getNode, createNode, updateNode, deleteNode, getNodeNeighbors, getNodeStakeholders } from '@/api/nodes';
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
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CorpusNodeCreate) => createNode(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
  });
}

export function useUpdateNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: CorpusNodeUpdate }) => updateNode(id, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['nodes', variables.id] });
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
  });
}

export function useDeleteNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteNode(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
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
