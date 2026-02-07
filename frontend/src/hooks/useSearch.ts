import { useQuery } from '@tanstack/react-query';
import { useState, useEffect } from 'react';
import { search } from '@/api/search';
import type { NodeType } from '@/types';

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(handler);
    };
  }, [value, delay]);

  return debouncedValue;
}

export function useSearch(query: string, nodeTypes?: NodeType[]) {
  const debouncedQuery = useDebounce(query, 300);

  return useQuery({
    queryKey: ['search', debouncedQuery, nodeTypes],
    queryFn: () => search(debouncedQuery, nodeTypes),
    enabled: debouncedQuery.length >= 2,
  });
}
