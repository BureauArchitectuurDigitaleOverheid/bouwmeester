import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';

interface MutationWithErrorOptions<TData, TVariables> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  errorMessage: string;
  invalidateKeys?: QueryKey[];
  onSuccess?: (data: TData, variables: TVariables) => void;
}

/**
 * Wrapper around useMutation that provides consistent error logging
 * and query invalidation.
 */
export function useMutationWithError<TData = unknown, TVariables = void>({
  mutationFn,
  errorMessage,
  invalidateKeys,
  onSuccess: extraOnSuccess,
}: MutationWithErrorOptions<TData, TVariables>) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn,
    onError: (error: Error) => {
      console.error(`${errorMessage}:`, error);
    },
    onSuccess: (data, variables) => {
      if (invalidateKeys) {
        for (const key of invalidateKeys) {
          queryClient.invalidateQueries({ queryKey: key as unknown[] });
        }
      }
      extraOnSuccess?.(data, variables);
    },
  });
}
