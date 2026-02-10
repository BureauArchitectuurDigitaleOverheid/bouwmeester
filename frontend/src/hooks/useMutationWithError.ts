import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { QueryKey } from '@tanstack/react-query';
import { useToast } from '@/contexts/ToastContext';
import { ApiError } from '@/api/client';

interface MutationWithErrorOptions<TData, TVariables> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  errorMessage: string;
  invalidateKeys?: QueryKey[];
  onSuccess?: (data: TData, variables: TVariables) => void;
}

function extractDetail(error: Error): string {
  if (error instanceof ApiError && error.body) {
    const body = error.body as Record<string, unknown>;
    if (typeof body.detail === 'string') return body.detail;
  }
  return '';
}

/**
 * Wrapper around useMutation that provides consistent error logging,
 * toast notifications, and query invalidation.
 */
export function useMutationWithError<TData = unknown, TVariables = void>({
  mutationFn,
  errorMessage,
  invalidateKeys,
  onSuccess: extraOnSuccess,
}: MutationWithErrorOptions<TData, TVariables>) {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn,
    onError: (error: Error) => {
      console.error(`${errorMessage}:`, error);
      const detail = extractDetail(error);
      showError(detail ? `${errorMessage}: ${detail}` : errorMessage);
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
