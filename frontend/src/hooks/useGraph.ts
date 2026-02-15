import { useQuery } from '@tanstack/react-query';
import { getGraphView } from '@/api/graph';
import { queryKeys } from '@/hooks/queryKeys';

export function useGraphView(nodeTypes?: string[], limit?: number, enabled = true) {
  return useQuery({
    queryKey: queryKeys.graph.view(nodeTypes, limit),
    queryFn: () => getGraphView(nodeTypes, limit),
    enabled,
  });
}
