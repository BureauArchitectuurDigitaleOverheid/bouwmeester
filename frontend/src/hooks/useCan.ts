import { useCallback, useMemo, useSyncExternalStore } from 'react';
import {
  skipToken,
  useQueries,
  useQuery,
  useQueryClient,
  type Query,
  type QueryClient,
  type UseQueryOptions,
} from '@tanstack/react-query';
import {
  authzProperties,
  decide,
  getEenhedenWith,
  type AuthzResource,
  type AuthzResourceType,
  type EenhedenWith,
} from '@/api/authz';
import { onForbidden } from '@/api/client';
import { useToast } from '@/contexts/ToastContext';

const AUTHZ_KEY = ['authz'] as const;

function authzQueryKey(action: string, resource: AuthzResource) {
  return [...AUTHZ_KEY, action, resource.type, resource.id ?? null, authzProperties(resource)] as const;
}

const DECISION_STALE_TIME = 5 * 60_000;

// Decisions change rarely; the mutations that change them refresh them (see
// `syncAuthzDecisions`). Without a resource the query waits (skipToken).
function decisionQuery(
  action: string,
  resource: AuthzResource | null | undefined,
): UseQueryOptions<boolean, Error, boolean, readonly unknown[]> {
  return {
    queryKey: resource ? authzQueryKey(action, resource) : [...AUTHZ_KEY, action, null],
    queryFn: resource ? () => decide({ action, resource }) : skipToken,
    staleTime: DECISION_STALE_TIME,
  };
}

export interface Decision {
  /** The backend said yes. `false` while loading and when it could not be asked. */
  allowed: boolean;
  isLoading: boolean;
  /** The decision could not be fetched (network, 5xx). */
  isError: boolean;
  /**
   * Render a primary action (edit, delete, create): when allowed, and also
   * when the decision failed, then disabled via `!allowed`. A failed request
   * should not make the main buttons of a page vanish without a trace.
   */
  showAction: boolean;
}

/**
 * May the current user do `action` on `resource`? Asked to the backend
 * (`POST /api/authz/evaluations`), so the answer is the same decision the
 * API makes on the write itself, including the dev-mode persona.
 *
 * All calls in one render tick share a single request. Pass `null` while the
 * resource is not known yet.
 *
 * While the decision loads, `allowed` is `false`: callers do not render the
 * control, so a button never flashes into view and then disappears for
 * someone who may not use it. On an error, primary actions use `showAction`
 * to stay visible but disabled; `AuthzErrorBanner` offers the retry.
 */
export function useCan(action: string, resource: AuthzResource | null | undefined): Decision {
  const query = useQuery(decisionQuery(action, resource));
  const allowed = query.data === true;
  return {
    allowed,
    isLoading: query.isPending,
    isError: query.isError,
    showAction: allowed || query.isError,
  };
}

/**
 * The eenheden where the current user may do `action` (`org:manage`,
 * `people:assign_role`, ...): one question for the whole list. Cached with
 * the other decisions, so a mutation with `CHANGES_RIGHTS` refreshes it and
 * a failure shows in `useAuthzFailures`.
 */
export function useEenhedenWith(action: string) {
  const query = useQuery({
    // Under AUTHZ_KEY; `'eenheden'` never collides with an action name.
    queryKey: [...AUTHZ_KEY, 'eenheden', action],
    queryFn: () => getEenhedenWith(action),
    staleTime: DECISION_STALE_TIME,
  });
  const data: EenhedenWith | undefined = query.data;
  const includes = useMemo(() => {
    if (!data) return () => false;
    if (data.all) return () => true;
    const ids = new Set(data.ids);
    return (eenheidId: string) => ids.has(eenheidId);
  }, [data]);
  return { includes, isLoading: query.isPending, isError: query.isError };
}

interface Decisions {
  allowed: boolean[];
  isLoading: boolean;
  isError: boolean;
}

/** `useCan` for a list: one decision per resource, in order (`false` while loading). */
export function useCanEach(action: string, resources: AuthzResource[]): Decisions {
  const results = useQueries({ queries: resources.map((r) => decisionQuery(action, r)) });
  return {
    allowed: results.map((q) => q.data === true),
    isLoading: results.some((q) => q.isPending),
    isError: results.some((q) => q.isError),
  };
}

type Combined = Omit<Decisions, 'allowed'> & { allowed: boolean };

/** `useCan` for a bulk action: allowed only when allowed on every resource. */
export function useCanAll(action: string, resources: AuthzResource[]): Combined {
  const each = useCanEach(action, resources);
  return { ...each, allowed: each.allowed.length > 0 && each.allowed.every(Boolean) };
}

/** `useCan` for a choice: allowed when allowed on at least one resource. */
export function useCanAny(action: string, resources: AuthzResource[]): Combined {
  const each = useCanEach(action, resources);
  return { ...each, allowed: each.allowed.some(Boolean) };
}

/**
 * For a gesture that has no button to hide (a drop, a drag): ask the
 * decision when it happens, through the same cache and batch as `useCan`.
 * Runs `action` only when allowed on the resource (or on any of several);
 * otherwise a toast says why not.
 */
export function useIfAllowed() {
  const queryClient = useQueryClient();
  const { showError } = useToast();
  return useCallback(
    async (
      question: string,
      resources: AuthzResource | AuthzResource[],
      refusal: string,
      action: () => void,
    ) => {
      let allowed: boolean[];
      try {
        allowed = await Promise.all(
          [resources].flat().map((resource) =>
            queryClient.fetchQuery({
              queryKey: authzQueryKey(question, resource),
              queryFn: () => decide({ action: question, resource }),
              staleTime: DECISION_STALE_TIME,
            }),
          ),
        );
      } catch {
        showError('Je rechten konden niet worden opgehaald. Probeer het opnieuw.');
        return;
      }
      if (allowed.some(Boolean)) action();
      else showError(refusal);
    },
    [queryClient, showError],
  );
}

const isFailedDecision = (query: Query) => query.state.status === 'error';

/**
 * Whether any decision on screen failed, and a way to ask those again.
 * One banner for the whole page instead of a retry next to every button.
 */
export function useAuthzFailures(): { failed: boolean; retry: () => void } {
  const queryClient = useQueryClient();
  const cache = queryClient.getQueryCache();
  const failed = useSyncExternalStore(
    (onChange) => cache.subscribe(onChange),
    () => cache.findAll({ queryKey: AUTHZ_KEY, type: 'active', predicate: isFailedDecision }).length > 0,
  );
  const retry = useCallback(() => {
    void queryClient.refetchQueries({ queryKey: AUTHZ_KEY, type: 'active', predicate: isFailedDecision });
  }, [queryClient]);
  return { failed, retry };
}

/** A resource whose decisions a mutation may have changed. */
export interface AuthzTouched {
  type: AuthzResourceType;
  id: string;
}

/**
 * What a successful mutation does to the decisions (a mutation's
 * `meta.authz`): `'all'` for changes to who has access (grants, roles,
 * placements, the org tree), or the resources it changed. Without it the
 * mutation changes no decision: creating, commenting, moving on a board.
 */
export type AuthzEffect = 'all' | ((variables: unknown, data: unknown) => AuthzTouched[]);

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: { authz?: AuthzEffect };
  }
}

/** `meta` for a mutation that changes who may do what. */
export const CHANGES_RIGHTS = { authz: 'all' } as const satisfies { authz: AuthzEffect };

/**
 * `meta` for a mutation that edits resources: their decisions are asked
 * again, since an edit can move a resource to another eenheid or owner.
 */
export function touches<TVariables, TData = unknown>(
  touched: (variables: TVariables, data: TData) => AuthzTouched | AuthzTouched[],
): { authz: AuthzEffect } {
  return {
    authz: (variables, data) => [touched(variables as TVariables, data as TData)].flat(),
  };
}

/** Drop every cached decision; active ones refetch in one batched request. */
function invalidateAuthz(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: AUTHZ_KEY });
}

function invalidateTouched(queryClient: QueryClient, touched: AuthzTouched[]) {
  if (touched.length === 0) return;
  return queryClient.invalidateQueries({
    queryKey: AUTHZ_KEY,
    // Key layout: see authzQueryKey.
    predicate: ({ queryKey }) => touched.some((t) => queryKey[2] === t.type && queryKey[3] === t.id),
  });
}

/**
 * Keep cached decisions in step with writes: after a successful mutation,
 * re-ask what its `meta.authz` names; after any 403, re-ask everything (the
 * UI offered something the backend refused, so its answers are stale).
 */
export function syncAuthzDecisions(queryClient: QueryClient): () => void {
  const stopMutations = queryClient.getMutationCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;
    const effect = event.mutation.options.meta?.authz;
    if (effect === 'all') void invalidateAuthz(queryClient);
    else if (effect) void invalidateTouched(queryClient, effect(event.mutation.state.variables, event.action.data));
  });
  const stopForbidden = onForbidden(() => void invalidateAuthz(queryClient));
  return () => {
    stopMutations();
    stopForbidden();
  };
}
