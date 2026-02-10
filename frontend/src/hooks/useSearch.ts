import { useQuery } from '@tanstack/react-query';
import { search } from '@/api/search';
import { useDebounce } from '@/hooks/useDebounce';
import type { SearchResultType } from '@/types';

export function useSearch(query: string, resultTypes?: SearchResultType[]) {
  const debouncedQuery = useDebounce(query, 300);

  return useQuery({
    queryKey: ['search', debouncedQuery, resultTypes],
    queryFn: () => search(debouncedQuery, resultTypes),
    enabled: debouncedQuery.length >= 2,
  });
}
