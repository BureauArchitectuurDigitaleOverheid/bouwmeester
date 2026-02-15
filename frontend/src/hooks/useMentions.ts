import { useQuery } from '@tanstack/react-query';
import { getReferences } from '@/api/mentions';
import { queryKeys } from '@/hooks/queryKeys';

export function useReferences(targetId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.mentions.references(targetId),
    queryFn: () => getReferences(targetId!),
    enabled: !!targetId,
  });
}
