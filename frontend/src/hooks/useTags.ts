import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getTags, createTag, getNodeTags, addTagToNode, removeTagFromNode } from '@/api/tags';
import { useMutationWithError } from '@/hooks/useMutationWithError';
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
  return useMutationWithError({
    mutationFn: (data: TagCreate) => createTag(data),
    errorMessage: 'Fout bij aanmaken tag',
    invalidateKeys: [['tags']],
  });
}

export function useAddTagToNode() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { tag_id?: string; tag_name?: string } }) =>
      addTagToNode(nodeId, data),
    errorMessage: 'Fout bij toevoegen tag',
    invalidateKeys: [['tags']],
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: ['node-tags', nodeId] });
    },
  });
}

export function useRemoveTagFromNode() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, tagId }: { nodeId: string; tagId: string }) =>
      removeTagFromNode(nodeId, tagId),
    errorMessage: 'Fout bij verwijderen tag',
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: ['node-tags', nodeId] });
    },
  });
}
