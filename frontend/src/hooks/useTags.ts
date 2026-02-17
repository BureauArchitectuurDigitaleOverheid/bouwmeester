import { useQuery, useQueryClient } from '@tanstack/react-query';
import { getTags, createTag, getNodeTags, addTagToNode, removeTagFromNode } from '@/api/tags';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { TagCreate } from '@/types';

export function useTags(params?: { tree?: boolean; search?: string }) {
  return useQuery({
    queryKey: queryKeys.tags.list(params),
    queryFn: () => getTags(params),
  });
}

export function useNodeTags(nodeId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.tags.forNode(nodeId ?? ''),
    queryFn: () => getNodeTags(nodeId!),
    enabled: !!nodeId,
  });
}

export function useCreateTag() {
  return useMutationWithError({
    mutationFn: (data: TagCreate) => createTag(data),
    errorMessage: 'Fout bij aanmaken tag',
    invalidateKeys: [queryKeys.tags.all],
  });
}

export function useAddTagToNode() {
  const queryClient = useQueryClient();

  return useMutationWithError({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { tag_id?: string; tag_name?: string } }) =>
      addTagToNode(nodeId, data),
    errorMessage: 'Fout bij toevoegen tag',
    invalidateKeys: [queryKeys.tags.all],
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.forNode(nodeId) });
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
      queryClient.invalidateQueries({ queryKey: queryKeys.tags.forNode(nodeId) });
    },
  });
}
