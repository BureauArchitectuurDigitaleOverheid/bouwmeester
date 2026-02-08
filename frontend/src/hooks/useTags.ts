import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getTags, createTag, getNodeTags, addTagToNode, removeTagFromNode } from '@/api/tags';
import type { TagCreate } from '@/types';

export function useTags(params?: { tree?: boolean; search?: string }) {
  return useQuery({
    queryKey: ['tags', params],
    queryFn: () => getTags(params),
  });
}

export function useNodeTags(nodeId: string) {
  return useQuery({
    queryKey: ['node-tags', nodeId],
    queryFn: () => getNodeTags(nodeId),
    enabled: !!nodeId,
  });
}

export function useCreateTag() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: TagCreate) => createTag(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tags'] });
    },
  });
}

export function useAddTagToNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { tag_id?: string; tag_name?: string } }) =>
      addTagToNode(nodeId, data),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: ['node-tags', nodeId] });
      queryClient.invalidateQueries({ queryKey: ['tags'] });
    },
  });
}

export function useRemoveTagFromNode() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ nodeId, tagId }: { nodeId: string; tagId: string }) =>
      removeTagFromNode(nodeId, tagId),
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: ['node-tags', nodeId] });
    },
  });
}
