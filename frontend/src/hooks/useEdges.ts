import { useQuery } from '@tanstack/react-query';
import { getEdges, createEdge, deleteEdge } from '@/api/edges';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import { queryKeys } from '@/hooks/queryKeys';
import type { EdgeCreate, EdgeFilters } from '@/types';

export function useEdges(filters?: EdgeFilters) {
  return useQuery({
    queryKey: queryKeys.edges.list(filters),
    queryFn: () => getEdges(filters),
  });
}

export function useCreateEdge() {
  return useMutationWithError({
    mutationFn: (data: EdgeCreate) => createEdge(data),
    errorMessage: 'Fout bij aanmaken relatie',
    invalidateKeys: [queryKeys.edges.all, queryKeys.nodes.all, ['graph'], queryKeys.parlementair.all, queryKeys.parlementair.reviewQueue()],
  });
}

export function useDeleteEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteEdge(id),
    errorMessage: 'Fout bij verwijderen relatie',
    invalidateKeys: [queryKeys.edges.all, queryKeys.nodes.all, ['graph'], queryKeys.parlementair.all, queryKeys.parlementair.reviewQueue()],
  });
}
