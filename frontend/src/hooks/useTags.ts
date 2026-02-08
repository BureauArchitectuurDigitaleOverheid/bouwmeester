import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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

  return useMutation({
    mutationFn: ({ nodeId, data }: { nodeId: string; data: { tag_id?: string; tag_name?: string } }) =>
      addTagToNode(nodeId, data),
    onError: (error: Error) => {
      console.error('Fout bij toevoegen tag:', error);
    },
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
    onError: (error: Error) => {
      console.error('Fout bij verwijderen tag:', error);
    },
    onSuccess: (_, { nodeId }) => {
      queryClient.invalidateQueries({ queryKey: ['node-tags', nodeId] });
    },
  });
}
