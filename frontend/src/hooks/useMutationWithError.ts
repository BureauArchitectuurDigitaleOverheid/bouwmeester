import { useMutation, useQueryClient } from '@tanstack/react-query';
import type { MutationMeta, QueryKey } from '@tanstack/react-query';
import { useToast } from '@/contexts/ToastContext';
import { errorDetail } from '@/api/client';

interface MutationWithErrorOptions<TData, TVariables> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  errorMessage: string;
  invalidateKeys?: QueryKey[];
  onSuccess?: (data: TData, variables: TVariables) => void;
  /** `CHANGES_RIGHTS` or `touches(...)` from `hooks/useCan`. */
  meta?: MutationMeta;
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
  meta,
}: MutationWithErrorOptions<TData, TVariables>) {
  const queryClient = useQueryClient();
  const { showError } = useToast();

  return useMutation({
    mutationFn,
    meta,
    onError: (error: Error) => {
      console.error(`${errorMessage}:`, error);
      const detail = errorDetail(error);
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
