import { useQuery } from '@tanstack/react-query';
import { getReferences } from '@/api/mentions';

export function useReferences(targetId: string | undefined) {
  return useQuery({
    queryKey: ['mentions', 'references', targetId],
    queryFn: () => getReferences(targetId!),
    enabled: !!targetId,
  });
}
