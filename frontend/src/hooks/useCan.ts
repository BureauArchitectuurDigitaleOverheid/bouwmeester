import { skipToken, useQueries, useQuery, type QueryClient, type UseQueryOptions } from '@tanstack/react-query';
import { authzProperties, decide, type AuthzResource } from '@/api/authz';

const AUTHZ_KEY = ['authz'] as const;

export function authzQueryKey(action: string, resource: AuthzResource) {
  return [...AUTHZ_KEY, action, resource.type, resource.id ?? null, authzProperties(resource)] as const;
}

// Decisions change rarely; a mutation refreshes them anyway (see below).
// Without a resource the query waits (skipToken) instead of asking.
function decisionQuery(
  action: string,
  resource: AuthzResource | null | undefined,
): UseQueryOptions<boolean, Error, boolean, readonly unknown[]> {
  return {
    queryKey: resource ? authzQueryKey(action, resource) : [...AUTHZ_KEY, action, null],
    queryFn: resource ? () => decide({ action, resource }) : skipToken,
    staleTime: 5 * 60_000,
  };
}

/**
 * May the current user do `action` on `resource`? Asked to the backend
 * (`POST /api/authz/evaluations`), so the answer is the same decision the
 * API makes on the write itself, including the dev-mode persona.
 *
 * All calls in one render tick share a single request. Pass `null` while the
 * resource is not known yet.
 *
 * While the decision loads, and when it fails, `allowed` is `false`: callers
 * do not render the control at all, so a button never flashes into view and
 * then disappears for someone who may not use it.
 */
export function useCan(
  action: string,
  resource: AuthzResource | null | undefined,
): { allowed: boolean; isLoading: boolean } {
  const query = useQuery(decisionQuery(action, resource));
  return { allowed: query.data === true, isLoading: query.isPending };
}

/** `useCan` for a list: one decision per resource, in order (`false` while loading). */
export function useCanEach(
  action: string,
  resources: AuthzResource[],
): { allowed: boolean[]; isLoading: boolean } {
  const results = useQueries({ queries: resources.map((r) => decisionQuery(action, r)) });
  return {
    allowed: results.map((q) => q.data === true),
    isLoading: results.some((q) => q.isPending),
  };
}

/** `useCan` for a bulk action: allowed only when allowed on every resource. */
export function useCanAll(
  action: string,
  resources: AuthzResource[],
): { allowed: boolean; isLoading: boolean } {
  const { allowed, isLoading } = useCanEach(action, resources);
  return { allowed: allowed.length > 0 && allowed.every(Boolean), isLoading };
}

/** Drop every cached decision; active ones refetch in one batched request. */
export function invalidateAuthz(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: AUTHZ_KEY });
}

/**
 * Re-ask all decisions after any successful mutation.
 *
 * Rights move with more than role and grant changes: editing a resource can
 * move it to another eenheid, adding a member changes who may edit an
 * initiatief. Listing which mutations matter would be a second copy of the
 * backend rules, so every write refreshes the (batched, cheap) decisions.
 */
export function refreshAuthzOnMutation(queryClient: QueryClient): () => void {
  return queryClient.getMutationCache().subscribe((event) => {
    if (event.type === 'updated' && event.action.type === 'success') {
      void invalidateAuthz(queryClient);
    }
  });
}
