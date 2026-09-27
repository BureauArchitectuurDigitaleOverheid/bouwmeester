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

// Decisions change rarely; the mutations that change them refresh them
// (`syncAuthzDecisions`).
const DECISION_STALE_TIME = 5 * 60_000;

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

interface Decision {
  /** The backend said yes; `false` while loading or when it could not be asked. */
  allowed: boolean;
  isLoading: boolean;
  isError: boolean;
  /**
   * Render a primary action when allowed, and also when the decision failed
   * (then disabled via `!allowed`), so a failed request does not make the
   * main buttons vanish without a trace.
   */
  showAction: boolean;
}

/**
 * May the current user do `action` on `resource`? The backend's own decision
 * (`POST /api/authz/evaluations`); all calls in one tick share one request.
 * Pass `null` while the resource is unknown. `allowed` is `false` while
 * loading, so a button never flashes into view for someone who may not use it.
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
 * The eenheden where the current user may do `action` (`org:manage`, ...):
 * one question for a whole list, cached with the other decisions.
 */
export function useEenhedenWith(action: string, eenheidType?: string) {
  const query = useQuery({
    // Under AUTHZ_KEY; `'eenheden'` never collides with an action name.
    queryKey: [...AUTHZ_KEY, 'eenheden', action, eenheidType ?? null],
    queryFn: () => getEenhedenWith(action, eenheidType),
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
 * For a gesture without a button to hide (a drop): ask when it happens and
 * run `action` only when allowed on the resource (or any of several);
 * otherwise toast the refusal.
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

/** Whether any decision on screen failed, and a retry: one banner per page. */
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
interface AuthzTouched {
  type: AuthzResourceType;
  id: string;
}

/**
 * A mutation's `meta.authz`: `'all'` when it changes who has access (grants,
 * roles, placements, the org tree), or the resources it changed. Without it
 * the mutation changes no decision.
 */
export type AuthzEffect = 'all' | ((variables: unknown, data: unknown) => AuthzTouched[]);

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: { authz?: AuthzEffect };
  }
}

/** `meta` for a mutation that changes who may do what. */
export const CHANGES_RIGHTS = { authz: 'all' } as const satisfies { authz: AuthzEffect };

/** `meta` for a mutation that edits resources: an edit can move one to another eenheid or owner. */
export function touches<TVariables, TData = unknown>(
  touched: (variables: TVariables, data: TData) => AuthzTouched | AuthzTouched[],
): { authz: AuthzEffect } {
  return {
    authz: (variables, data) => [touched(variables as TVariables, data as TData)].flat(),
  };
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
 * re-ask what its `meta.authz` names; after any 403 re-ask everything (the
 * UI offered something the backend refused).
 */
export function syncAuthzDecisions(queryClient: QueryClient): () => void {
  const stopMutations = queryClient.getMutationCache().subscribe((event) => {
    if (event.type !== 'updated' || event.action.type !== 'success') return;
    const effect = event.mutation.options.meta?.authz;
    if (effect === 'all') void queryClient.invalidateQueries({ queryKey: AUTHZ_KEY });
    else if (effect) void invalidateTouched(queryClient, effect(event.mutation.state.variables, event.action.data));
  });
  const stopForbidden = onForbidden(() => void queryClient.invalidateQueries({ queryKey: AUTHZ_KEY }));
  return () => {
    stopMutations();
    stopForbidden();
  };
}
