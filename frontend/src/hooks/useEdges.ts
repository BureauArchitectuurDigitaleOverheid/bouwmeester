import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getEdges, createEdge, deleteEdge } from '@/api/edges';
import type { EdgeCreate } from '@/types';
import type { EdgeFilters } from '@/api/edges';

export function useEdges(filters?: EdgeFilters) {
  return useQuery({
    queryKey: ['edges', filters],
    queryFn: () => getEdges(filters),
  });
}

export function useCreateEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EdgeCreate) => createEdge(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edges'] });
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
      queryClient.invalidateQueries({ queryKey: ['graph'] });
    },
  });
}

export function useDeleteEdge() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: string) => deleteEdge(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['edges'] });
      queryClient.invalidateQueries({ queryKey: ['nodes'] });
    },
  });
}
