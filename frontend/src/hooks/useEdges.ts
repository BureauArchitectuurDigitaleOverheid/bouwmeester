import { useQuery } from '@tanstack/react-query';
import { getEdges, createEdge, deleteEdge } from '@/api/edges';
import { useMutationWithError } from '@/hooks/useMutationWithError';
import type { EdgeCreate } from '@/types';
import type { EdgeFilters } from '@/api/edges';

export function useEdges(filters?: EdgeFilters) {
  return useQuery({
    queryKey: ['edges', filters],
    queryFn: () => getEdges(filters),
  });
}

export function useCreateEdge() {
  return useMutationWithError({
    mutationFn: (data: EdgeCreate) => createEdge(data),
    errorMessage: 'Fout bij aanmaken relatie',
    invalidateKeys: [['edges'], ['nodes'], ['graph']],
  });
}

export function useDeleteEdge() {
  return useMutationWithError({
    mutationFn: (id: string) => deleteEdge(id),
    errorMessage: 'Fout bij verwijderen relatie',
    invalidateKeys: [['edges'], ['nodes']],
  });
}
