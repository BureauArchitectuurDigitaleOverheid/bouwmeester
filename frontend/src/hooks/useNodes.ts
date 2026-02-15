import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getNodes, getNode, createNode, updateNode, deleteNode,
  getNodeNeighbors, getNodeStakeholders, addNodeStakeholder,
  updateNodeStakeholder, removeNodeStakeholder, getNodeParlementairItem,
  getNodeTitleHistory, getNodeStatusHistory,
  getNodeBronDetail, getBijlageInfo, getNodeGraph,
} from '@/api/nodes';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { CorpusNodeCreate, CorpusNodeUpdate, NodeType } from '@/types';

export function useNodes(nodeType?: NodeType, search?: string) {
  return useQuery({
    queryKey: queryKeys.nodes.list(nodeType, search),
    queryFn: () => getNodes(nodeType, search),
  });
}

export function useNode(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.nodes.detail(id),
    queryFn: () => getNode(id!),
    enabled: !!id,
  });
}

export function useCreateNode() {
  return useMutationWithError({
    mutationFn: (data: CorpusNodeCreate) => createNode(data),
    errorMessage: 'Fout bij aanmaken node',
    invalidateKeys: [queryKeys.nodes.lists(), queryKeys.graph.all],
  });
}

export function useUpdateNode() {
  return useMutationWithError({
    mutationFn: ({ id, data, actorId }: { id: string; data: CorpusNodeUpdate; actorId?: string }) => updateNode(id, data, actorId),
    errorMessage: 'Fout bij bijwerken node',
    invalidateKeys: [queryKeys.nodes.details(), queryKeys.nodes.lists()],
  });
}

export function useDeleteNode() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteNode(id),
    errorMessage: 'Fout bij verwijderen node',
    invalidateKeys: [queryKeys.nodes.lists()],
  });
}

export function useNodeNeighbors(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.nodes.neighbors(id),
    queryFn: () => getNodeNeighbors(id!),
    enabled: !!id,
  });
}

export function useNodeStakeholders(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.nodes.stakeholders(id),
    queryFn: () => getNodeStakeholders(id!),
    enabled: !!id,
  });
}

export function useAddNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { person_id: string; rol: string } }) =>
      addNodeStakeholder(nodeId, data),
    errorMessage: 'Fout bij toevoegen stakeholder',
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.stakeholders(variables.nodeId) });
    },
  });
}

export function useUpdateNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, stakeholderId, data }: { nodeId: string; stakeholderId: string; data: { rol: string } }) =>
      updateNodeStakeholder(nodeId, stakeholderId, data),
    errorMessage: 'Fout bij bijwerken stakeholder',
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.stakeholders(variables.nodeId) });
    },
  });
}

export function useRemoveNodeStakeholder() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, stakeholderId }: { nodeId: string; stakeholderId: string }) =>
      removeNodeStakeholder(nodeId, stakeholderId),
    errorMessage: 'Fout bij verwijderen stakeholder',
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.nodes.stakeholders(variables.nodeId) });
    },
  });
}

export function useNodeTitleHistory(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.nodes.titleHistory(id),
    queryFn: () => getNodeTitleHistory(id!),
    enabled: !!id,
  });
}

export function useNodeStatusHistory(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.nodes.statusHistory(id),
    queryFn: () => getNodeStatusHistory(id!),
    enabled: !!id,
  });
}

export function useNodeParlementairItem(id: string | undefined, nodeType?: string) {
  return useQuery({
    queryKey: queryKeys.nodes.parlementairItem(id),
    queryFn: () => getNodeParlementairItem(id!),
    enabled: !!id && nodeType === 'politieke_input',
  });
}

export function useNodeBronDetail(id: string | undefined, nodeType?: string) {
  return useQuery({
    queryKey: queryKeys.nodes.bronDetail(id),
    queryFn: () => getNodeBronDetail(id!),
    enabled: !!id && nodeType === 'bron',
  });
}

export function useNodeBijlage(id: string | undefined, nodeType?: string) {
  return useQuery({
    queryKey: queryKeys.nodes.bijlage(id),
    queryFn: () => getBijlageInfo(id!),
    enabled: !!id && nodeType === 'bron',
  });
}

export function useNodeGraph(id: string | undefined, depth: number = 2, enabled: boolean = true) {
  return useQuery({
    queryKey: queryKeys.nodes.graph(id, depth),
    queryFn: () => getNodeGraph(id!, depth),
    enabled: !!id && enabled,
  });
}
