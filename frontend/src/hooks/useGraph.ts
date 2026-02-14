import { useQuery } from '@tanstack/react-query';
import { getGraphView } from '@/api/graph';

export function useGraphView(nodeTypes?: string[], limit?: number, enabled = true) {
  return useQuery({
    queryKey: ['graph', nodeTypes, limit],
    queryFn: () => getGraphView(nodeTypes, limit),
    enabled,
  });
}
